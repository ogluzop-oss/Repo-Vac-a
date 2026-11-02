/**
 * GMAO (capacidad "gmao"). Rediseño móvil · Grupo B, módulo 2: escanear el QR de un activo (impreso
 * desde escritorio, gmao_dashboard.py → pestaña Activos → "Imprimir QR") para abrir sus OTs pendientes,
 * iniciarlas, ver los repuestos pendientes y fotografiar la reparación antes de finalizar. Crear/
 * planificar OTs sigue siendo trabajo de escritorio — aquí solo se ejecuta in situ.
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
  buscarActivoPorCodigo,
  finalizarOrden,
  iniciarOrden,
  listarOrdenesDeActivo,
  listarRepuestos,
  type Activo,
  type OrdenTrabajo,
  type Repuesto,
} from '@/api/gmao';
import {colors} from '@/theme/colors';
import type {GMAOProps} from '@/navigation/types';

export default function GMAOScreen({navigation, route}: GMAOProps) {
  const {t} = useTranslation();
  const [buscando, setBuscando] = useState(false);
  const [activo, setActivo] = useState<Activo | null>(null);
  const [ordenes, setOrdenes] = useState<OrdenTrabajo[]>([]);
  const [orden, setOrden] = useState<OrdenTrabajo | null>(null);
  const [repuestos, setRepuestos] = useState<Repuesto[]>([]);
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const reiniciar = useCallback(() => {
    setActivo(null);
    setOrdenes([]);
    setOrden(null);
    setRepuestos([]);
    setFotoUri(null);
    setAviso(null);
  }, []);

  const buscarActivo = useCallback(async (payload: string) => {
    setBuscando(true);
    setAviso(null);
    try {
      let codigo = payload;
      try {
        const datos = JSON.parse(payload);
        if (datos?.tipo === 'ACTIVO' && datos.codigo) {
          codigo = datos.codigo;
        }
      } catch {
        // No es JSON: se usa el propio valor escaneado como código (entrada manual del lector).
      }
      const a = await buscarActivoPorCodigo(codigo);
      if (!a) {
        setAviso({ok: false, texto: t('gmao.activo_no_encontrado', 'No se encontró ningún activo con el código «{{c}}».', {c: codigo})});
        return;
      }
      setActivo(a);
      setOrdenes(await listarOrdenesDeActivo(a.id));
    } catch {
      setAviso({ok: false, texto: t('gmao.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setBuscando(false);
    }
  }, [t]);

  useEffect(() => {
    const escaneado = route.params?.escaneado;
    if (escaneado) {
      navigation.setParams({escaneado: undefined});
      buscarActivo(escaneado);
    }
  }, [route.params?.escaneado, navigation, buscarActivo]);

  const abrirOrden = useCallback(async (o: OrdenTrabajo) => {
    setOrden(o);
    setFotoUri(null);
    setAviso(null);
    if (o.estado === 'en_curso') {
      setRepuestos(await listarRepuestos(o.id));
    } else {
      setRepuestos([]);
    }
  }, []);

  const iniciar = useCallback(async () => {
    if (!orden) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await iniciarOrden(orden.id);
      if (r.ok) {
        const actualizada = {...orden, estado: r.estado};
        setOrden(actualizada);
        setOrdenes(prev => prev.map(x => (x.id === orden.id ? actualizada : x)));
        setRepuestos(await listarRepuestos(orden.id));
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('gmao.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [orden, t]);

  const finalizar = useCallback(async () => {
    if (!orden || !fotoUri) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await finalizarOrden(orden.id, fotoUri);
      if (r.ok) {
        setAviso({ok: true, texto: t('gmao.ot_finalizada', 'OT {{c}} finalizada.', {c: orden.codigo})});
        setOrdenes(prev => prev.filter(x => x.id !== orden.id));
        setOrden(null);
        setRepuestos([]);
        setFotoUri(null);
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('gmao.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [orden, fotoUri, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => (orden ? setOrden(null) : navigation.goBack())}>
          <Text style={styles.back}>‹ {orden ? t('gmao.ots_lbl', 'OTs') : t('common.volver_sin_flecha', 'Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('gmao.titulo', 'Mantenimiento')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('gmao.foto_reparacion', 'Foto de la reparación')}</Text>
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

      {!activo ? (
        <View style={styles.centered}>
          {buscando ? (
            <ActivityIndicator color={colors.cyan} size="large" />
          ) : (
            <Text style={styles.hint}>
              {aviso?.texto || t('gmao.escanea_qr_hint', 'Escanea el QR de un activo para ver sus órdenes de trabajo pendientes.')}
            </Text>
          )}
          <TouchableOpacity
            style={styles.scanBtn}
            onPress={() => navigation.navigate('Scanner', {volverA: 'GMAO'})}>
            <Text style={styles.scanBtnText}>{t('gmao.escanear_activo_btn', 'Escanear activo')}</Text>
          </TouchableOpacity>
        </View>
      ) : orden ? (
        <ScrollView contentContainerStyle={styles.form}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{orden.codigo}</Text>
            <Text style={styles.cardDetail}>{orden.descripcion || t('gmao.sin_descripcion', '(sin descripción)')}</Text>
            <Text style={styles.cardDetail}>
              {t('gmao.tipo_prioridad_estado', '{{ti}} · prioridad {{p}} · estado {{e}}',
                 {ti: orden.tipo, p: orden.prioridad, e: orden.estado})}
            </Text>
            {orden.tecnico != null ? (
              <Text style={styles.cardDetail}>{t('gmao.tecnico_lbl', 'Técnico: #{{n}}', {n: orden.tecnico})}</Text>
            ) : null}
          </View>

          {orden.estado !== 'en_curso' ? (
            <TouchableOpacity
              style={[styles.button, procesando && styles.buttonDisabled]}
              onPress={iniciar}
              disabled={procesando}>
              {procesando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>{t('gmao.iniciar_ot_btn', 'Iniciar OT')}</Text>
              )}
            </TouchableOpacity>
          ) : (
            <>
              <Text style={styles.sectionTitle}>{t('gmao.repuestos_h2', 'Repuestos')}</Text>
              {repuestos.length === 0 ? (
                <Text style={styles.hint}>{t('gmao.sin_repuestos', 'Sin repuestos asociados a esta OT.')}</Text>
              ) : (
                repuestos.map(r => (
                  <View key={r.id} style={styles.repuestoRow}>
                    <Text style={styles.cardDetail}>
                      {r.consumido ? '✅' : '⬜'} {r.tipo} · {r.referencia} × {r.cantidad}
                      {r.coste_unitario ? ` · ${r.coste_unitario} €/ud` : ''}
                    </Text>
                  </View>
                ))
              )}

              <Text style={styles.sectionTitle}>{t('gmao.foto_reparacion', 'Foto de la reparación')}</Text>
              {fotoUri ? (
                <View style={styles.fotoPreviewWrap}>
                  <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
                  <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
                    <Text style={styles.buttonText}>{t('gmao.repetir_foto_btn', 'Repetir foto')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
                  <Text style={styles.scanBtnText}>{t('gmao.hacer_foto_btn', 'Hacer foto')}</Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                style={[
                  styles.button,
                  styles.buttonFull,
                  (!fotoUri || procesando) && styles.buttonDisabled,
                ]}
                onPress={finalizar}
                disabled={!fotoUri || procesando}>
                {procesando ? (
                  <ActivityIndicator color={colors.bg} />
                ) : (
                  <Text style={styles.buttonText}>{t('gmao.finalizar_ot_btn', 'Finalizar OT')}</Text>
                )}
              </TouchableOpacity>
            </>
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
        </ScrollView>
      ) : (
        <View style={{flex: 1}}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{activo.nombre}</Text>
            <Text style={styles.cardDetail}>
              {activo.codigo} · {activo.tipo} · {activo.estado}
            </Text>
            <Text style={styles.cardDetail}>{t('gmao.criticidad_lbl', 'Criticidad: {{c}}', {c: activo.criticidad})}</Text>
            <TouchableOpacity onPress={reiniciar}>
              <Text style={styles.link}>{t('gmao.escanear_otro_btn', 'Escanear otro activo')}</Text>
            </TouchableOpacity>
          </View>
          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
          <FlatList
            data={ordenes}
            keyExtractor={item => String(item.id)}
            contentContainerStyle={styles.form}
            ListEmptyComponent={<Text style={styles.hint}>{t('gmao.sin_ots_pendientes', 'Sin órdenes de trabajo pendientes.')}</Text>}
            renderItem={({item}) => (
              <TouchableOpacity style={styles.card} onPress={() => abrirOrden(item)}>
                <Text style={styles.cardTitle}>{item.codigo}</Text>
                <Text style={styles.cardDetail} numberOfLines={1}>
                  {item.descripcion || t('gmao.sin_descripcion', '(sin descripción)')}
                </Text>
                <Text style={styles.cardDetail}>
                  {t('gmao.tipo_prioridad_estado', '{{ti}} · prioridad {{p}} · estado {{e}}',
                     {ti: item.tipo, p: item.prioridad, e: item.estado})}
                </Text>
              </TouchableOpacity>
            )}
          />
        </View>
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
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 20},
  hint: {color: colors.textDim, textAlign: 'center', fontSize: 14},
  form: {padding: 16, paddingBottom: 32},
  sectionTitle: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 14, marginBottom: 8},
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 12,
    paddingVertical: 16,
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 16},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 4,
  },
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 15},
  cardDetail: {color: colors.textDim, marginTop: 4, fontSize: 12},
  link: {color: colors.cyan, fontWeight: '700', fontSize: 12, marginTop: 8},
  repuestoRow: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 6,
  },
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonFull: {marginTop: 12},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 8, marginHorizontal: 16, fontSize: 12},
  error: {color: colors.danger, marginTop: 8, marginHorizontal: 16, fontSize: 12},
});
