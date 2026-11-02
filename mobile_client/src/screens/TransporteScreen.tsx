/**
 * Transporte/Reparto (capacidad "transporte"). Rediseño móvil · Grupo B, módulo 5: fotografiar la
 * entrega ES el trabajo físico (mismo criterio que GMAO/SAT) — o reportar que no se pudo entregar
 * (cliente ausente/rechazo/dirección incorrecta), con foto opcional. Sin firma: no hay hoy ningún
 * momento de conformidad de cliente en el modelo de Transporte.
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
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import CameraScanner from '@/components/CameraScanner';
import {
  cerrarRuta,
  entregarParada,
  iniciarRuta,
  listarRutas,
  obtenerRuta,
  reportarIncidencia,
  type Parada,
  type Ruta,
} from '@/api/transporte';
import {colors} from '@/theme/colors';
import type {TransporteProps} from '@/navigation/types';

// Valores CANÓNICOS en español — se envían tal cual al backend, nunca traducidos: solo la
// ETIQUETA visible usa `t(\`transporte.motivo_${slug}\`, m)`.
const MOTIVOS = ['Cliente ausente', 'Rechazado', 'Dirección incorrecta', 'Otro'];
const MOTIVO_SLUG: Record<string, string> = {
  'Cliente ausente': 'cliente_ausente',
  Rechazado: 'rechazado',
  'Dirección incorrecta': 'direccion_incorrecta',
  Otro: 'otro',
};

export default function TransporteScreen({navigation}: TransporteProps) {
  const {t} = useTranslation();
  const [cargando, setCargando] = useState(true);
  const [rutas, setRutas] = useState<Ruta[]>([]);
  const [ruta, setRuta] = useState<Ruta | null>(null);
  const [parada, setParada] = useState<Parada | null>(null);
  const [accion, setAccion] = useState<'entregar' | 'incidencia' | null>(null);
  const [motivo, setMotivo] = useState(MOTIVOS[0] ?? 'Otro');
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const cargarRutas = useCallback(async () => {
    setCargando(true);
    try {
      setRutas(await listarRutas());
    } catch {
      setRutas([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarRutas();
  }, [cargarRutas]);

  const abrirRuta = useCallback(async (r: Ruta) => {
    setAviso(null);
    const completa = await obtenerRuta(r.id);
    setRuta(completa || r);
  }, []);

  const refrescarRutaActual = useCallback(async () => {
    if (!ruta) return;
    const completa = await obtenerRuta(ruta.id);
    if (completa) setRuta(completa);
  }, [ruta]);

  const iniciar = useCallback(async () => {
    if (!ruta) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await iniciarRuta(ruta.id);
      if (r.ok) {
        await refrescarRutaActual();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('transporte.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [ruta, refrescarRutaActual, t]);

  const abrirParada = useCallback((p: Parada) => {
    setParada(p);
    setAccion(null);
    setMotivo(MOTIVOS[0] ?? 'Otro');
    setFotoUri(null);
    setAviso(null);
  }, []);

  const enviarEntrega = useCallback(async () => {
    if (!parada || !fotoUri) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await entregarParada(parada.id, fotoUri);
      if (r.ok) {
        setAviso({ok: true, texto: t('transporte.entrega_registrada_ok', 'Entrega registrada con la foto de evidencia.')});
        setParada(null);
        setAccion(null);
        await refrescarRutaActual();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('transporte.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [parada, fotoUri, refrescarRutaActual, t]);

  const enviarIncidencia = useCallback(async () => {
    if (!parada) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await reportarIncidencia(parada.id, motivo, fotoUri || undefined);
      if (r.ok) {
        setAviso({ok: true, texto: t('transporte.incidencia_registrada_ok', 'Incidencia registrada.')});
        setParada(null);
        setAccion(null);
        await refrescarRutaActual();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('transporte.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [parada, motivo, fotoUri, refrescarRutaActual, t]);

  const cerrar = useCallback(async () => {
    if (!ruta) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await cerrarRuta(ruta.id);
      if (r.ok) {
        setAviso({ok: true, texto: t('transporte.ruta_cerrada_ok', 'Ruta cerrada.')});
        setRutas(prev => prev.filter(x => x.id !== ruta.id));
        setRuta(null);
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('transporte.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [ruta, t]);

  const volver = () => {
    if (parada) {
      setParada(null);
      setAccion(null);
    } else if (ruta) {
      setRuta(null);
    } else {
      navigation.goBack();
    }
  };

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={volver}>
          <Text style={styles.back}>
            ‹ {parada ? t('transporte.paradas_lbl', 'Paradas') : ruta ? t('transporte.rutas_lbl', 'Rutas') : t('common.volver_sin_flecha', 'Volver')}
          </Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('transporte.titulo', 'Reparto')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('transporte.foto_lbl', 'Foto')}</Text>
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

      {!ruta ? (
        cargando ? (
          <ActivityIndicator color={colors.cyan} size="large" style={{marginTop: 40}} />
        ) : (
          <FlatList
            data={rutas}
            keyExtractor={item => String(item.id)}
            contentContainerStyle={styles.form}
            ListEmptyComponent={<Text style={styles.hint}>{t('transporte.sin_rutas', 'Sin rutas asignadas pendientes.')}</Text>}
            renderItem={({item}) => (
              <TouchableOpacity style={styles.card} onPress={() => abrirRuta(item)}>
                <Text style={styles.cardTitle}>{t('transporte.ruta_num', 'Ruta #{{n}} · {{f}}', {n: item.id, f: item.fecha})}</Text>
                <Text style={styles.cardDetail}>{t('transporte.estado_lbl', 'estado {{e}}', {e: item.estado})}</Text>
              </TouchableOpacity>
            )}
          />
        )
      ) : !parada ? (
        <ScrollView contentContainerStyle={styles.form}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t('transporte.ruta_num', 'Ruta #{{n}} · {{f}}', {n: ruta.id, f: ruta.fecha})}</Text>
            <Text style={styles.cardDetail}>{t('transporte.estado_lbl', 'estado {{e}}', {e: ruta.estado})}</Text>
            {ruta.conductor ? (
              <Text style={styles.cardDetail}>{t('transporte.conductor_lbl', 'Conductor: {{c}}', {c: ruta.conductor})}</Text>
            ) : null}
            {ruta.id_vehiculo != null ? (
              <Text style={styles.cardDetail}>{t('transporte.vehiculo_lbl', 'Vehículo: #{{n}}', {n: ruta.id_vehiculo})}</Text>
            ) : null}
          </View>

          {ruta.estado === 'planificada' ? (
            <TouchableOpacity
              style={[styles.button, procesando && styles.buttonDisabled]}
              onPress={iniciar}
              disabled={procesando}>
              {procesando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>{t('transporte.iniciar_ruta_btn', 'Iniciar ruta')}</Text>
              )}
            </TouchableOpacity>
          ) : null}

          <Text style={styles.sectionTitle}>{t('transporte.paradas_lbl', 'Paradas')}</Text>
          {(ruta.paradas || []).length === 0 ? (
            <Text style={styles.hint}>{t('transporte.ruta_sin_paradas', 'Esta ruta no tiene paradas.')}</Text>
          ) : (
            (ruta.paradas || []).map(p => (
              <TouchableOpacity
                key={p.id}
                style={styles.card}
                disabled={p.estado !== 'pendiente'}
                onPress={() => abrirParada(p)}>
                <Text style={styles.cardTitle}>
                  {p.orden}. {p.cliente || t('transporte.sin_cliente', '(sin cliente)')}
                </Text>
                <Text style={styles.cardDetail}>{p.direccion || t('transporte.sin_direccion', '(sin dirección)')}</Text>
                <Text style={styles.cardDetail}>
                  {t('transporte.estado_lbl', 'estado {{e}}', {e: p.estado})}
                  {p.motivo_incidencia ? ` · ${t(`transporte.motivo_${MOTIVO_SLUG[p.motivo_incidencia] ?? 'otro'}`, p.motivo_incidencia)}` : ''}
                </Text>
              </TouchableOpacity>
            ))
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

          <TouchableOpacity
            style={[styles.button, styles.buttonFull, procesando && styles.buttonDisabled]}
            onPress={cerrar}
            disabled={procesando}>
            <Text style={styles.buttonText}>{t('transporte.cerrar_ruta_btn', 'Cerrar ruta')}</Text>
          </TouchableOpacity>
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={styles.form}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              {parada.orden}. {parada.cliente || t('transporte.sin_cliente', '(sin cliente)')}
            </Text>
            <Text style={styles.cardDetail}>{parada.direccion || t('transporte.sin_direccion', '(sin dirección)')}</Text>
          </View>

          {!accion ? (
            <View style={styles.row}>
              <TouchableOpacity
                style={[styles.button, {flex: 1}]}
                onPress={() => setAccion('entregar')}>
                <Text style={styles.buttonText}>{t('transporte.entregado_btn', 'Entregado')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.button, styles.buttonSecundario, {flex: 1}]}
                onPress={() => setAccion('incidencia')}>
                <Text style={styles.buttonTextSecundario}>{t('transporte.incidencia_btn', 'Incidencia')}</Text>
              </TouchableOpacity>
            </View>
          ) : accion === 'entregar' ? (
            <View>
              <Text style={styles.sectionTitle}>{t('transporte.foto_entrega_h2', 'Foto de la entrega')}</Text>
              {fotoUri ? (
                <View style={styles.fotoPreviewWrap}>
                  <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
                  <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
                    <Text style={styles.buttonText}>{t('transporte.repetir_foto_btn', 'Repetir foto')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
                  <Text style={styles.scanBtnText}>{t('transporte.hacer_foto_btn', 'Hacer foto')}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity
                style={[
                  styles.button,
                  styles.buttonFull,
                  (!fotoUri || procesando) && styles.buttonDisabled,
                ]}
                onPress={enviarEntrega}
                disabled={!fotoUri || procesando}>
                {procesando ? (
                  <ActivityIndicator color={colors.bg} />
                ) : (
                  <Text style={styles.buttonText}>{t('transporte.registrar_entrega_btn', 'Registrar entrega')}</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setAccion(null)}>
                <Text style={styles.link}>{t('common.cancelar', 'Cancelar')}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View>
              <Text style={styles.sectionTitle}>{t('transporte.motivo_h2', 'Motivo')}</Text>
              <View style={styles.chipsRow}>
                {MOTIVOS.map(m => (
                  <TouchableOpacity
                    key={m}
                    style={[styles.chip, motivo === m && styles.chipActivo]}
                    onPress={() => setMotivo(m)}>
                    <Text style={[styles.chipTexto, motivo === m && styles.chipTextoActivo]}>
                      {t(`transporte.motivo_${MOTIVO_SLUG[m]}`, m)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.sectionTitle}>{t('transporte.foto_opc_h2', 'Foto (opcional)')}</Text>
              {fotoUri ? (
                <View style={styles.fotoPreviewWrap}>
                  <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
                  <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
                    <Text style={styles.buttonText}>{t('transporte.repetir_foto_btn', 'Repetir foto')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
                  <Text style={styles.scanBtnText}>{t('transporte.hacer_foto_btn', 'Hacer foto')}</Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                style={[styles.button, styles.buttonFull, procesando && styles.buttonDisabled]}
                onPress={enviarIncidencia}
                disabled={procesando}>
                {procesando ? (
                  <ActivityIndicator color={colors.bg} />
                ) : (
                  <Text style={styles.buttonText}>{t('transporte.registrar_incidencia_btn', 'Registrar incidencia')}</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setAccion(null)}>
                <Text style={styles.link}>{t('common.cancelar', 'Cancelar')}</Text>
              </TouchableOpacity>
            </View>
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
        </ScrollView>
      )}
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
  hint: {color: colors.textDim, textAlign: 'center', fontSize: 14, marginTop: 20},
  row: {flexDirection: 'row', gap: 8},
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 14},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 15},
  cardDetail: {color: colors.textDim, marginTop: 4, fontSize: 12},
  link: {color: colors.cyan, fontWeight: '700', fontSize: 12, marginTop: 8, textAlign: 'center'},
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
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonSecundario: {backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border},
  buttonFull: {marginTop: 12},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  buttonTextSecundario: {color: colors.text, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 8, fontSize: 12},
  error: {color: colors.danger, marginTop: 8, fontSize: 12},
});
