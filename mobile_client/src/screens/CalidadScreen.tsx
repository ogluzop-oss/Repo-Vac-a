/**
 * Calidad (capacidad "calidad" -> /api/v1/calidad/inspections). Rediseño móvil Grupo B, módulo 3:
 * fotografiar el artículo/lote inspeccionado ES el trabajo físico — mismo criterio que Mermas. Si el
 * resultado es "rechazada", el backend abre una No Conformidad sola (igual que ya hace escritorio); el
 * aviso de éxito lo menciona.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
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
import {buscarArticulos, type Articulo} from '@/api/articles';
import {listarInspecciones, registrarInspeccion, type Inspeccion} from '@/api/calidad';
import {colors} from '@/theme/colors';
import type {CalidadProps} from '@/navigation/types';

const FASES: {key: 'recepcion' | 'produccion' | 'final'; label: string}[] = [
  {key: 'recepcion', label: 'Recepción'},
  {key: 'produccion', label: 'Producción'},
  {key: 'final', label: 'Final'},
];
const RESULTADOS: {key: 'aceptada' | 'rechazada' | 'condicional'; label: string}[] = [
  {key: 'aceptada', label: 'Aceptada'},
  {key: 'rechazada', label: 'Rechazada'},
  {key: 'condicional', label: 'Condicional'},
];

export default function CalidadScreen({navigation}: CalidadProps) {
  const {t} = useTranslation();
  const [q, setQ] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [articulo, setArticulo] = useState<Articulo | null>(null);
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [fase, setFase] = useState<'recepcion' | 'produccion' | 'final'>('recepcion');
  const [resultado, setResultado] = useState<'aceptada' | 'rechazada' | 'condicional'>('aceptada');
  const [cantInsp, setCantInsp] = useState('1');
  const [cantRech, setCantRech] = useState('0');
  const [observaciones, setObservaciones] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const [recientes, setRecientes] = useState<Inspeccion[]>([]);
  const [cargandoLista, setCargandoLista] = useState(true);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cargarRecientes = useCallback(async () => {
    setCargandoLista(true);
    try {
      setRecientes(await listarInspecciones(15));
    } catch {
      setRecientes([]);
    } finally {
      setCargandoLista(false);
    }
  }, []);

  useEffect(() => {
    cargarRecientes();
  }, [cargarRecientes]);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (!q.trim() || articulo) {
      setSugerencias([]);
      return;
    }
    debounce.current = setTimeout(async () => {
      try {
        setSugerencias(await buscarArticulos(q.trim()));
      } catch {
        setSugerencias([]);
      }
    }, 300);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [q, articulo]);

  const elegir = useCallback((a: Articulo) => {
    setArticulo(a);
    setQ(`${a.codigo} – ${a.nombre}`);
    setSugerencias([]);
  }, []);

  const reiniciarFormulario = useCallback(() => {
    setQ('');
    setArticulo(null);
    setFotoUri(null);
    setFase('recepcion');
    setResultado('aceptada');
    setCantInsp('1');
    setCantRech('0');
    setObservaciones('');
  }, []);

  const enviar = useCallback(async () => {
    if (!articulo) {
      setAviso({ok: false, texto: t('calidad.busca_articulo', 'Busca primero el artículo.')});
      return;
    }
    if (!fotoUri) {
      setAviso({ok: false, texto: t('calidad.haz_foto', 'Haz una foto del artículo/lote antes de registrar la inspección.')});
      return;
    }
    const ci = Number(cantInsp);
    const cr = Number(cantRech);
    if (!Number.isFinite(ci) || ci <= 0) {
      setAviso({ok: false, texto: t('calidad.cant_insp_invalida', 'La cantidad inspeccionada debe ser un número mayor que 0.')});
      return;
    }
    if (!Number.isFinite(cr) || cr < 0) {
      setAviso({ok: false, texto: t('calidad.cant_rech_invalida', 'La cantidad rechazada no puede ser negativa.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await registrarInspeccion({
        fase,
        articulo: articulo.codigo,
        cantidad_inspeccionada: ci,
        cantidad_rechazada: cr,
        resultado,
        observaciones: observaciones.trim() || undefined,
        fotoUri,
      });
      if (r.ok) {
        setAviso({
          ok: true,
          texto: r.no_conformidad
            ? t('calidad.registrada_con_nc', 'Inspección registrada. Se ha abierto la No Conformidad NC{{n}} automáticamente.',
                {n: String(r.no_conformidad).padStart(6, '0')})
            : t('calidad.registrada_ok', 'Inspección registrada con la foto de evidencia.'),
        });
        reiniciarFormulario();
        await cargarRecientes();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('calidad.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [articulo, fotoUri, fase, resultado, cantInsp, cantRech, observaciones, reiniciarFormulario, cargarRecientes, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('calidad.titulo', 'Calidad')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('calidad.foto_articulo_lote', 'Foto del artículo/lote')}</Text>
            <View style={{width: 90}} />
          </View>
          <View style={{flex: 1, margin: 16}}>
            <CameraScanner
              active={camaraAbierta}
              modo="foto"
              onCaptured={uri => {
                setFotoUri(uri);
                setCamaraAbierta(false);
              }}
            />
          </View>
        </SafeAreaView>
      </Modal>

      <ScrollView contentContainerStyle={styles.form}>
        <Text style={styles.sectionTitle}>{t('calidad.articulo_h2', 'Artículo')}</Text>
        <TextInput
          style={styles.input}
          placeholder={t('calidad.buscar_articulo_ph', 'Buscar artículo (código o nombre)')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={q}
          onChangeText={texto => {
            setQ(texto);
            setArticulo(null);
          }}
        />
        {sugerencias.length > 0 ? (
          <View style={styles.sugerencias}>
            {sugerencias.map(a => (
              <TouchableOpacity key={a.codigo} style={styles.sugerenciaItem} onPress={() => elegir(a)}>
                <Text style={styles.sugerenciaNombre} numberOfLines={1}>{a.nombre}</Text>
                <Text style={styles.sugerenciaCodigo}>{a.codigo}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : null}

        <Text style={styles.sectionTitle}>{t('calidad.foto_articulo_lote', 'Foto del artículo/lote')}</Text>
        {fotoUri ? (
          <View style={styles.fotoPreviewWrap}>
            <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
            <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
              <Text style={styles.buttonText}>{t('calidad.repetir_foto_btn', 'Repetir foto')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
            <Text style={styles.scanBtnText}>{t('calidad.hacer_foto_btn', 'Hacer foto')}</Text>
          </TouchableOpacity>
        )}

        <Text style={styles.sectionTitle}>{t('calidad.fase_h2', 'Fase')}</Text>
        <View style={styles.chipsRow}>
          {FASES.map(f => (
            <TouchableOpacity
              key={f.key}
              style={[styles.chip, fase === f.key && styles.chipActivo]}
              onPress={() => setFase(f.key)}>
              <Text style={[styles.chipTexto, fase === f.key && styles.chipTextoActivo]}>
                {t(`calidad.fase_${f.key}`, f.label)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.sectionTitle}>{t('calidad.resultado_h2', 'Resultado')}</Text>
        <View style={styles.chipsRow}>
          {RESULTADOS.map(r => (
            <TouchableOpacity
              key={r.key}
              style={[styles.chip, resultado === r.key && styles.chipActivo]}
              onPress={() => setResultado(r.key)}>
              <Text style={[styles.chipTexto, resultado === r.key && styles.chipTextoActivo]}>
                {t(`calidad.resultado_${r.key}`, r.label)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.sectionTitle}>{t('calidad.cantidades_h2', 'Cantidades')}</Text>
        <View style={styles.row}>
          <TextInput
            style={[styles.input, {width: 140}]}
            placeholder={t('calidad.inspeccionada_ph', 'Inspeccionada')}
            placeholderTextColor={colors.textDim}
            keyboardType="numeric"
            value={cantInsp}
            onChangeText={setCantInsp}
          />
          <TextInput
            style={[styles.input, {width: 140}]}
            placeholder={t('calidad.rechazada_ph', 'Rechazada')}
            placeholderTextColor={colors.textDim}
            keyboardType="numeric"
            value={cantRech}
            onChangeText={setCantRech}
          />
        </View>

        <Text style={styles.sectionTitle}>{t('calidad.observaciones_opc_h2', 'Observaciones (opcional)')}</Text>
        <TextInput
          style={[styles.input, {minHeight: 60}]}
          placeholder={t('calidad.observaciones_ph', 'Observaciones')}
          placeholderTextColor={colors.textDim}
          multiline
          value={observaciones}
          onChangeText={setObservaciones}
        />

        {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

        <TouchableOpacity
          style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
          onPress={enviar}
          disabled={enviando}>
          {enviando ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.buttonText}>{t('calidad.registrar_inspeccion_btn', 'Registrar inspección')}</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>{t('calidad.ultimas_h2', 'Últimas inspecciones')}</Text>
        {cargandoLista ? (
          <ActivityIndicator color={colors.cyan} />
        ) : (
          <FlatList
            data={recientes}
            keyExtractor={item => String(item.id)}
            scrollEnabled={false}
            ListEmptyComponent={<Text style={styles.hint}>{t('calidad.sin_inspecciones', 'Sin inspecciones registradas todavía.')}</Text>}
            renderItem={({item}) => (
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardTitle} numberOfLines={1}>{item.articulo || t('calidad.sin_articulo', '(sin artículo)')}</Text>
                  <Text style={styles.cardDetail}>{item.fecha}{item.id_documento_foto ? ' 📷' : ''}</Text>
                </View>
                <Text style={styles.cardDetail}>
                  {t(`calidad.fase_${item.fase}`, item.fase)} · {t(`calidad.resultado_${item.resultado}`, item.resultado)} ·{' '}
                  {t('calidad.insp_rech', 'insp. {{i}} / rech. {{r}}', {i: item.cantidad_inspeccionada, r: item.cantidad_rechazada})}
                </Text>
                {item.observaciones ? (
                  <Text style={styles.cardDetail}>{t('calidad.obs_lbl', 'Obs.: {{o}}', {o: item.observaciones})}</Text>
                ) : null}
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
  sugerencias: {
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    marginTop: -4,
    marginBottom: 8,
    overflow: 'hidden',
  },
  sugerenciaItem: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  sugerenciaNombre: {color: colors.text, fontWeight: '700', fontSize: 13},
  sugerenciaCodigo: {color: colors.textDim, fontSize: 11, marginTop: 2},
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
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
