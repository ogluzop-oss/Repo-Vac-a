/**
 * Gastos de viaje (capacidad "gastos_viaje" -> /api/v1/rrhh/me/gastos). Único trozo de
 * autoservicio RRHH en el móvil (petición explícita, decisión confirmada: nóminas/vacaciones/
 * documentos se quedan en escritorio, donde ya existen y maduran — ver RRHH y Portal del Empleado
 * — porque son formularios/consultas SIN componente físico; fotografiar el ticket EN EL MOMENTO,
 * con lectura automática por IA, SÍ lo tiene, por eso esta es la única pieza que vuelve aquí,
 * mismo criterio que Mermas/Calidad/SAT). "La IA propone, el humano confirma": la foto se manda a
 * `extraerTicket` para un borrador editable, nunca registra el gasto directamente.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import CameraScanner from '@/components/CameraScanner';
import {
  extraerTicket,
  listarMisGastos,
  registrarGasto,
  type GastoViaje,
} from '@/api/gastosViaje';
import {colors} from '@/theme/colors';
import type {GastosViajeProps} from '@/navigation/types';

const CATEGORIAS: {valor: GastoViaje['categoria']; label: string}[] = [
  {valor: 'transporte', label: 'Transporte'},
  {valor: 'alojamiento', label: 'Alojamiento'},
  {valor: 'dietas', label: 'Dietas'},
  {valor: 'otros', label: 'Otros'},
];

const ESTADO_LABEL: Record<GastoViaje['estado'], string> = {
  pendiente: 'Pendiente',
  aprobado: 'Aprobado',
  rechazado: 'Rechazado',
  reembolsado: 'Reembolsado',
};

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function GastosViajeScreen({navigation}: GastosViajeProps) {
  const {t} = useTranslation();
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [leyendoTicket, setLeyendoTicket] = useState(false);
  const [ocrOrigen, setOcrOrigen] = useState(false);
  const [categoria, setCategoria] = useState<GastoViaje['categoria']>('transporte');
  const [fecha, setFecha] = useState(hoyISO());
  const [importe, setImporte] = useState('');
  const [concepto, setConcepto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const [recientes, setRecientes] = useState<GastoViaje[]>([]);
  const [cargandoLista, setCargandoLista] = useState(true);

  const cargarRecientes = useCallback(async () => {
    setCargandoLista(true);
    try {
      setRecientes(await listarMisGastos());
    } catch {
      setRecientes([]);
    } finally {
      setCargandoLista(false);
    }
  }, []);

  useEffect(() => {
    cargarRecientes();
  }, [cargarRecientes]);

  const reiniciarFormulario = useCallback(() => {
    setFotoUri(null);
    setOcrOrigen(false);
    setCategoria('transporte');
    setFecha(hoyISO());
    setImporte('');
    setConcepto('');
  }, []);

  const onFotoCapturada = useCallback(async (uri: string) => {
    setFotoUri(uri);
    setCamaraAbierta(false);
    setLeyendoTicket(true);
    setAviso(null);
    try {
      const r = await extraerTicket(uri);
      if (r.ok) {
        const d = r.datos;
        if (d.importe !== undefined) setImporte(String(d.importe));
        if (d.fecha) setFecha(d.fecha);
        if (d.concepto || d.comercio) setConcepto(d.concepto || d.comercio || '');
        if (d.categoria_sugerida) setCategoria(d.categoria_sugerida);
        setOcrOrigen(true);
        setAviso({
          ok: true,
          texto: t('gastos.ocr_ok', 'Datos leídos del ticket — revísalos antes de registrar.'),
        });
      } else {
        setOcrOrigen(false);
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setOcrOrigen(false);
      setAviso({ok: false, texto: t('gastos.ocr_sin_conexion', 'No se pudo leer el ticket (sin conexión).')});
    } finally {
      setLeyendoTicket(false);
    }
  }, [t]);

  const enviar = useCallback(async () => {
    const imp = Number(importe.replace(',', '.'));
    if (!Number.isFinite(imp) || imp <= 0) {
      setAviso({ok: false, texto: t('gastos.importe_invalido', 'Introduce un importe válido.')});
      return;
    }
    if (!fecha.trim()) {
      setAviso({ok: false, texto: t('gastos.fecha_obligatoria', 'Indica la fecha del gasto.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await registrarGasto({
        fecha_gasto: fecha.trim(),
        categoria,
        importe: imp,
        concepto: concepto.trim() || undefined,
        fotoUri: fotoUri || undefined,
        ocrOrigen,
      });
      if (r.ok) {
        setAviso({
          ok: true,
          texto: t('gastos.registrado_ok', 'Gasto {{codigo}} registrado — pendiente de aprobación.', {
            codigo: r.codigo,
          }),
        });
        reiniciarFormulario();
        await cargarRecientes();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('gastos.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [importe, fecha, categoria, concepto, fotoUri, ocrOrigen, reiniciarFormulario, cargarRecientes, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('gastos.titulo', 'Gastos de viaje')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>
                ‹ {t('common.cancelar', 'Cancelar')}
              </Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('gastos.foto_ticket', 'Foto del ticket')}</Text>
            <View style={{width: 90}} />
          </View>
          <View style={{flex: 1, margin: 16}}>
            <CameraScanner active={camaraAbierta} modo="foto" onCaptured={onFotoCapturada} />
          </View>
        </SafeAreaView>
      </Modal>

      <ScrollView contentContainerStyle={styles.form}>
        <Text style={styles.sectionTitle}>{t('gastos.ticket_h2', 'Ticket')}</Text>
        {fotoUri ? (
          <View style={styles.fotoPreviewWrap}>
            <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
            <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
              <Text style={styles.buttonText}>{t('gastos.repetir_foto_btn', 'Repetir foto')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
            <Text style={styles.scanBtnText}>{t('gastos.escanear_ticket_btn', '📷 Escanear ticket')}</Text>
          </TouchableOpacity>
        )}
        {leyendoTicket ? (
          <View style={styles.row}>
            <ActivityIndicator color={colors.cyan} />
            <Text style={styles.hint}>{t('gastos.leyendo', 'Leyendo ticket con IA…')}</Text>
          </View>
        ) : null}

        <Text style={styles.sectionTitle}>{t('gastos.detalles_h2', 'Detalles')}</Text>
        <View style={styles.chipsRow}>
          {CATEGORIAS.map(c => (
            <TouchableOpacity
              key={c.valor}
              style={[styles.chip, categoria === c.valor && styles.chipActivo]}
              onPress={() => setCategoria(c.valor)}>
              <Text style={[styles.chipTexto, categoria === c.valor && styles.chipTextoActivo]}>
                {t(`gastos.categoria_${c.valor}`, c.label)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={styles.row}>
          <TextInput
            style={[styles.input, {flex: 1}]}
            placeholder={t('gastos.fecha_ph', 'Fecha (AAAA-MM-DD)')}
            placeholderTextColor={colors.textDim}
            value={fecha}
            onChangeText={setFecha}
          />
          <TextInput
            style={[styles.input, {width: 120}]}
            placeholder={t('gastos.importe_ph', 'Importe €')}
            placeholderTextColor={colors.textDim}
            keyboardType="decimal-pad"
            value={importe}
            onChangeText={setImporte}
          />
        </View>
        <TextInput
          style={styles.input}
          placeholder={t('gastos.concepto_ph', 'Concepto (p. ej. Taxi aeropuerto)')}
          placeholderTextColor={colors.textDim}
          value={concepto}
          onChangeText={setConcepto}
        />

        {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

        <TouchableOpacity
          style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
          onPress={enviar}
          disabled={enviando}>
          {enviando ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.buttonText}>{t('gastos.registrar_btn', 'Registrar gasto')}</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>{t('gastos.mis_gastos_h2', 'Mis gastos')}</Text>
        {cargandoLista ? (
          <ActivityIndicator color={colors.cyan} />
        ) : (
          <FlatList
            data={recientes}
            keyExtractor={item => String(item.id)}
            scrollEnabled={false}
            ListEmptyComponent={
              <Text style={styles.hint}>{t('gastos.sin_gastos', 'Sin gastos registrados todavía.')}</Text>
            }
            renderItem={({item}) => (
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardTitle} numberOfLines={1}>
                    {item.concepto || t(`gastos.categoria_${item.categoria}`, item.categoria)}
                  </Text>
                  <Text style={styles.cardDetail}>{item.importe.toFixed(2)} €</Text>
                </View>
                <Text style={styles.cardDetail}>
                  {item.codigo} · {item.fecha_gasto} · {t(`gastos.estado_${item.estado}`, ESTADO_LABEL[item.estado])}
                </Text>
              </View>
            )}
          />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 90},
  title: {color: colors.text, fontSize: 18, fontWeight: '800'},
  form: {padding: 16, paddingBottom: 32},
  sectionTitle: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 14, marginBottom: 8},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    marginBottom: 8,
  },
  scanBtn: {backgroundColor: colors.cyan, borderRadius: 10, paddingVertical: 14, alignItems: 'center'},
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 14},
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  row: {flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap'},
  chipsRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8},
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActivo: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  chipTexto: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  chipTextoActivo: {color: colors.bg},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonFull: {marginTop: 8, marginBottom: 8},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginBottom: 8, fontSize: 12},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12},
  hint: {color: colors.textDim, fontSize: 12},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 14, flex: 1, marginRight: 8},
  cardDetail: {color: colors.textDim, marginTop: 2, fontSize: 12},
});
