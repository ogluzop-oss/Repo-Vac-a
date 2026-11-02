/**
 * MRP (capacidad "mrp"). Rediseño móvil · Grupo B, módulo 7 (último): fotografiar el lote producido ES
 * el trabajo físico — repetible, cada "Registrar producción" es un lote y una foto nuevos. Consumir
 * materiales es una acción plana sin foto: no hay nada fotografiable en ese instante.
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
  consumirMateriales,
  finalizarOrden,
  iniciarOrden,
  listarConsumos,
  listarOrdenes,
  listarProducciones,
  obtenerOrden,
  pausarOrden,
  registrarProduccion,
  type Consumo,
  type OrdenFabricacion,
  type Produccion,
} from '@/api/mrp';
import {colors} from '@/theme/colors';
import type {MRPProps} from '@/navigation/types';

export default function MRPScreen({navigation}: MRPProps) {
  const {t} = useTranslation();
  const [cargando, setCargando] = useState(true);
  const [ordenes, setOrdenes] = useState<OrdenFabricacion[]>([]);
  const [orden, setOrden] = useState<OrdenFabricacion | null>(null);
  const [consumos, setConsumos] = useState<Consumo[]>([]);
  const [producciones, setProducciones] = useState<Produccion[]>([]);
  const [cantidad, setCantidad] = useState('1');
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const cargarOrdenes = useCallback(async () => {
    setCargando(true);
    try {
      setOrdenes(await listarOrdenes());
    } catch {
      setOrdenes([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarOrdenes();
  }, [cargarOrdenes]);

  const abrirOrden = useCallback(async (o: OrdenFabricacion) => {
    setAviso(null);
    setOrden(o);
    setConsumos(await listarConsumos(o.id));
    setProducciones(await listarProducciones(o.id));
  }, []);

  const refrescarOrdenActual = useCallback(async () => {
    if (!orden) return;
    const actualizada = await obtenerOrden(orden.id);
    if (actualizada) setOrden(actualizada);
    setConsumos(await listarConsumos(orden.id));
    setProducciones(await listarProducciones(orden.id));
  }, [orden]);

  const accion = useCallback(
    async (fn: (id: number) => Promise<{ok: true} | {ok: false; error: string}>) => {
      if (!orden) return;
      setProcesando(true);
      setAviso(null);
      try {
        const r = await fn(orden.id);
        if (r.ok) {
          await refrescarOrdenActual();
        } else {
          setAviso({ok: false, texto: r.error});
        }
      } catch {
        setAviso({ok: false, texto: t('mrp.sin_conexion', 'No hay conexión con el servidor.')});
      } finally {
        setProcesando(false);
      }
    },
    [orden, refrescarOrdenActual, t],
  );

  const consumir = useCallback(async () => {
    if (!orden) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await consumirMateriales(orden.id);
      if (r.ok) {
        setAviso({
          ok: true,
          texto: r.faltantes.length > 0
            ? t('mrp.materiales_consumidos_con_faltantes', 'Materiales consumidos (con faltantes).')
            : t('mrp.materiales_consumidos', 'Materiales consumidos.'),
        });
        await refrescarOrdenActual();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('mrp.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [orden, refrescarOrdenActual, t]);

  const producir = useCallback(async () => {
    if (!orden || !fotoUri) return;
    const cant = Number(cantidad);
    if (!Number.isFinite(cant) || cant <= 0) {
      setAviso({ok: false, texto: t('mrp.cantidad_invalida', 'La cantidad debe ser un número mayor que 0.')});
      return;
    }
    setProcesando(true);
    setAviso(null);
    try {
      const r = await registrarProduccion(orden.id, cant, fotoUri);
      if (r.ok) {
        setAviso({
          ok: true,
          texto: r.lote
            ? t('mrp.produccion_registrada_lote', 'Producción registrada (lote {{l}}).', {l: r.lote})
            : t('mrp.produccion_registrada', 'Producción registrada.'),
        });
        setCantidad('1');
        setFotoUri(null);
        await refrescarOrdenActual();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('mrp.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [orden, cantidad, fotoUri, refrescarOrdenActual, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => (orden ? setOrden(null) : navigation.goBack())}>
          <Text style={styles.back}>‹ {orden ? t('mrp.ofs_lbl', 'OFs') : t('common.volver_sin_flecha', 'Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('mrp.titulo', 'Producción')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('mrp.foto_lote', 'Foto del lote')}</Text>
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

      {!orden ? (
        cargando ? (
          <ActivityIndicator color={colors.cyan} size="large" style={{marginTop: 40}} />
        ) : (
          <FlatList
            data={ordenes}
            keyExtractor={item => String(item.id)}
            contentContainerStyle={styles.form}
            ListEmptyComponent={<Text style={styles.hint}>{t('mrp.sin_ofs_abiertas', 'Sin órdenes de fabricación abiertas.')}</Text>}
            renderItem={({item}) => (
              <TouchableOpacity style={styles.card} onPress={() => abrirOrden(item)}>
                <Text style={styles.cardTitle}>{item.codigo} · {item.articulo_final}</Text>
                <Text style={styles.cardDetail}>
                  {t('mrp.producido_de_estado', '{{p}} / {{c}} · estado {{e}}',
                     {p: item.cantidad_producida, c: item.cantidad, e: item.estado})}
                </Text>
              </TouchableOpacity>
            )}
          />
        )
      ) : (
        <ScrollView contentContainerStyle={styles.form}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{orden.codigo} · {orden.articulo_final}</Text>
            <Text style={styles.cardDetail}>
              {t('mrp.producido_estado', 'producido {{p}} / {{c}} · estado {{e}}',
                 {p: orden.cantidad_producida, c: orden.cantidad, e: orden.estado})}
            </Text>
            {orden.lote_destino ? (
              <Text style={styles.cardDetail}>{t('mrp.lote_destino_lbl', 'Lote destino: {{l}}', {l: orden.lote_destino})}</Text>
            ) : null}
          </View>

          <View style={styles.row}>
            {orden.estado === 'liberada' ? (
              <TouchableOpacity
                style={[styles.button, {flex: 1}, procesando && styles.buttonDisabled]}
                onPress={() => accion(iniciarOrden)}
                disabled={procesando}>
                <Text style={styles.buttonText}>{t('mrp.iniciar_btn', 'Iniciar')}</Text>
              </TouchableOpacity>
            ) : null}
            {orden.estado === 'en_curso' ? (
              <TouchableOpacity
                style={[styles.button, styles.buttonSecundario, {flex: 1}, procesando && styles.buttonDisabled]}
                onPress={() => accion(pausarOrden)}
                disabled={procesando}>
                <Text style={styles.buttonTextSecundario}>{t('mrp.pausar_btn', 'Pausar')}</Text>
              </TouchableOpacity>
            ) : null}
            {orden.estado === 'pausada' ? (
              <TouchableOpacity
                style={[styles.button, {flex: 1}, procesando && styles.buttonDisabled]}
                onPress={() => accion(iniciarOrden)}
                disabled={procesando}>
                <Text style={styles.buttonText}>{t('mrp.reanudar_btn', 'Reanudar')}</Text>
              </TouchableOpacity>
            ) : null}
          </View>

          <Text style={styles.sectionTitle}>{t('mrp.materiales_h2', 'Materiales')}</Text>
          {consumos.length === 0 ? (
            <Text style={styles.hint}>{t('mrp.sin_materiales', 'Sin materiales previstos.')}</Text>
          ) : (
            consumos.map(c => (
              <View key={c.id} style={styles.lineaRow}>
                <Text style={styles.cardDetail}>
                  {c.consumido ? '✅' : '⬜'} {c.componente} ·{' '}
                  {c.consumido
                    ? t('mrp.plan_real', 'plan {{p}} · real {{r}}', {p: c.cantidad_plan, r: c.cantidad_real})
                    : t('mrp.plan_lbl', 'plan {{p}}', {p: c.cantidad_plan})}
                </Text>
              </View>
            ))
          )}
          <TouchableOpacity
            style={[styles.button, styles.buttonSecundario, procesando && styles.buttonDisabled]}
            onPress={consumir}
            disabled={procesando}>
            <Text style={styles.buttonTextSecundario}>{t('mrp.consumir_materiales_btn', 'Consumir materiales')}</Text>
          </TouchableOpacity>

          <Text style={styles.sectionTitle}>{t('mrp.registrar_produccion_h2', 'Registrar producción')}</Text>
          <TextInput
            style={[styles.input, {width: 120}]}
            placeholder={t('mrp.cantidad_ph', 'Cantidad')}
            placeholderTextColor={colors.textDim}
            keyboardType="numeric"
            value={cantidad}
            onChangeText={setCantidad}
          />
          {fotoUri ? (
            <View style={styles.fotoPreviewWrap}>
              <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
              <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
                <Text style={styles.buttonText}>{t('mrp.repetir_foto_btn', 'Repetir foto')}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
              <Text style={styles.scanBtnText}>{t('mrp.hacer_foto_lote_btn', 'Hacer foto del lote')}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.button, styles.buttonFull, (!fotoUri || procesando) && styles.buttonDisabled]}
            onPress={producir}
            disabled={!fotoUri || procesando}>
            {procesando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>{t('mrp.registrar_produccion_btn', 'Registrar producción')}</Text>
            )}
          </TouchableOpacity>

          {producciones.length > 0 ? (
            <>
              <Text style={styles.sectionTitle}>{t('mrp.lotes_producidos_h2', 'Lotes producidos')}</Text>
              {producciones.map(p => (
                <View key={p.id} style={styles.lineaRow}>
                  <Text style={styles.cardDetail}>
                    {p.id_documento_foto ? '📷 ' : ''}
                    {p.fecha} ·{' '}
                    {p.lote
                      ? t('mrp.uds_lote', '{{c}} uds · lote {{l}}', {c: p.cantidad, l: p.lote})
                      : t('mrp.uds_lbl', '{{c}} uds', {c: p.cantidad})}
                  </Text>
                </View>
              ))}
            </>
          ) : null}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

          <TouchableOpacity
            style={[styles.button, styles.buttonFull, procesando && styles.buttonDisabled]}
            onPress={() => accion(finalizarOrden)}
            disabled={procesando}>
            <Text style={styles.buttonText}>{t('mrp.finalizar_of_btn', 'Finalizar OF')}</Text>
          </TouchableOpacity>
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
  lineaRow: {
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
  buttonSecundario: {backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, marginTop: 8},
  buttonFull: {marginTop: 12},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  buttonTextSecundario: {color: colors.text, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 8, fontSize: 12},
  error: {color: colors.danger, marginTop: 8, fontSize: 12},
});
