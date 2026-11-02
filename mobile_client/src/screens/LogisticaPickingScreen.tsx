/**
 * Picking de un traspaso EN PREPARACION (capacidad "logistica"). Checklist por línea/palé — al marcar
 * todas las líneas, "Confirmar picking y expedir" pasa el documento a EN TRANSITO (mismo motor que
 * escritorio, `db.logistica.confirmar_picking_y_expedir`).
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {
  confirmarPicking,
  marcarPicking,
  obtenerTraspaso,
  type LineaTraspaso,
  type TraspasoDetalle,
} from '@/api/logistics';
import {colors} from '@/theme/colors';
import type {LogisticaPickingProps} from '@/navigation/types';

export default function LogisticaPickingScreen({navigation, route}: LogisticaPickingProps) {
  const {t} = useTranslation();
  const {id_documento} = route.params;
  const [lineas, setLineas] = useState<LineaTraspaso[]>([]);
  const [albaran, setAlbaran] = useState<TraspasoDetalle | null>(null);
  const [cargando, setCargando] = useState(true);
  const [confirmando, setConfirmando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const cargar = useCallback(async () => {
    const detalle = await obtenerTraspaso(id_documento);
    setAlbaran(detalle);
    setLineas(detalle?.lineas ?? []);
  }, [id_documento]);

  useEffect(() => {
    (async () => {
      setCargando(true);
      await cargar();
      setCargando(false);
    })();
  }, [cargar]);

  const toggle = useCallback(async (linea: LineaTraspaso) => {
    const nuevo = !linea.picking_completo;
    setLineas(prev =>
      prev.map(l => (l.id_linea === linea.id_linea ? {...l, picking_completo: nuevo ? 1 : 0} : l)),
    );
    const ok = await marcarPicking(id_documento, linea.id_linea, nuevo);
    if (!ok) {
      setLineas(prev =>
        prev.map(l =>
          l.id_linea === linea.id_linea ? {...l, picking_completo: nuevo ? 0 : 1} : l,
        ),
      );
      setAviso({ok: false, texto: t('logpick.no_se_pudo_actualizar_linea', 'No se pudo actualizar esa línea.')});
    }
  }, [id_documento, t]);

  const hechas = lineas.filter(l => l.picking_completo).length;
  const total = lineas.length;
  const completo = total > 0 && hechas === total;

  const confirmar = useCallback(async () => {
    setConfirmando(true);
    setAviso(null);
    try {
      const r = await confirmarPicking(id_documento);
      if (r.ok) {
        setAviso({ok: true, texto: t('logpick.expedido_ok', 'Traspaso expedido correctamente (EN TRÁNSITO).')});
        setTimeout(() => navigation.goBack(), 900);
      } else if (r.motivo === 'picking_incompleto') {
        setAviso({ok: false, texto: t('logpick.faltan_lineas', 'Aún faltan {{n}} línea(s) por recoger.', {n: r.faltan})});
      } else {
        setAviso({ok: false, texto: t('logpick.no_se_pudo_confirmar', 'No se pudo confirmar el picking.')});
      }
    } catch {
      setAviso({ok: false, texto: t('logpick.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setConfirmando(false);
    }
  }, [id_documento, navigation, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title} numberOfLines={1}>{id_documento}</Text>
        <View style={{width: 90}} />
      </View>

      {cargando ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
        </View>
      ) : (
        <>
          {albaran ? (
            <View style={styles.albaranCard}>
              <Text style={styles.albaranLinea}>{albaran.origen} → {albaran.destino}</Text>
              <Text style={styles.albaranDetalle}>
                {albaran.agencia ? t('logpick.agencia_prefijo', 'Agencia: {{a}} · ', {a: albaran.agencia}) : ''}
                {t('logpick.envio_lbl', 'Envío: {{f}}', {f: albaran.fecha_envio})}
                {albaran.usuario ? ` · ${albaran.usuario}` : ''}
              </Text>
              {albaran.observaciones ? (
                <Text style={styles.albaranDetalle}>
                  {t('logpick.obs_lbl', 'Obs.: {{o}}', {o: albaran.observaciones})}
                </Text>
              ) : null}
            </View>
          ) : null}
          <Text style={styles.progreso}>
            {t('logpick.progreso', '{{h}} de {{n}} líneas recogidas', {h: hechas, n: total})}
          </Text>
          <FlatList
            data={lineas}
            keyExtractor={item => String(item.id_linea)}
            contentContainerStyle={styles.list}
            renderItem={({item}) => (
              <TouchableOpacity style={styles.card} onPress={() => toggle(item)}>
                <View style={[styles.check, item.picking_completo ? styles.checkOn : null]}>
                  {item.picking_completo ? <Text style={styles.checkMark}>✓</Text> : null}
                </View>
                <View style={{flex: 1}}>
                  <Text style={styles.cardTitle}>{item.id_visual} · {item.codigo}</Text>
                  <Text style={styles.cardDetail}>
                    {item.nombre} x{item.cantidad}{item.peso_bulto != null ? ` · ${item.peso_bulto} kg` : ''}
                  </Text>
                </View>
              </TouchableOpacity>
            )}
          />
          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
          <TouchableOpacity
            style={[styles.button, (!completo || confirmando) && styles.buttonDisabled]}
            onPress={confirmar}
            disabled={!completo || confirmando}>
            {confirmando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>
                {t('logpick.confirmar_expedir_btn', 'Confirmar picking y expedir')}
              </Text>
            )}
          </TouchableOpacity>
        </>
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
  title: {color: colors.text, fontSize: 16, fontWeight: '800', flex: 1, textAlign: 'center'},
  progreso: {color: colors.textDim, fontSize: 12, marginHorizontal: 16, marginBottom: 4},
  albaranCard: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 12,
    marginHorizontal: 16,
    marginBottom: 10,
  },
  albaranLinea: {color: colors.text, fontWeight: '800', fontSize: 13},
  albaranDetalle: {color: colors.textDim, fontSize: 11, marginTop: 3},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center'},
  list: {padding: 16, paddingTop: 4},
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    gap: 12,
  },
  check: {
    width: 26,
    height: 26,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkOn: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  checkMark: {color: colors.bg, fontWeight: '900'},
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 14},
  cardDetail: {color: colors.textDim, marginTop: 2, fontSize: 12},
  ok: {color: colors.ok, marginHorizontal: 16, marginBottom: 8, fontSize: 12},
  error: {color: colors.danger, marginHorizontal: 16, marginBottom: 8, fontSize: 12},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginHorizontal: 16,
    marginBottom: 16,
  },
  buttonDisabled: {opacity: 0.5},
  buttonText: {color: colors.bg, fontWeight: '800'},
});
