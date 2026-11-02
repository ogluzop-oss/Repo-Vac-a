/**
 * Logística (capacidad "logistica" -> /api/v1/logistics/*). SOLO Recepción (escanear palet al llegar)
 * y Traspaso/Picking (checklist mientras se camina el almacén, salida de stock entre tiendas — mismo
 * flujo que la pestaña "Traspasos" de escritorio) — los dos únicos pasos de este módulo que exigen
 * presencia física. Crear traspaso/Expediciones/Incidencias/Historial se quedan en escritorio
 * (rediseño móvil Grupo A).
 *
 * La pestaña Traspaso está gateada por RBAC (`logistica.traspasos`, mismo permiso que ya bloquea esta
 * función en escritorio para OPERARIO — ver `GET /me/modules`): un operario sin ese permiso ni una
 * concesión individual no la ve, igual que en escritorio.
 */
import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {
  itemsEsperadosPalet,
  listarTraspasos,
  obtenerTraspaso,
  recibirPalet,
  type ItemEsperado,
  type Traspaso,
  type TraspasoDetalle,
} from '@/api/logistics';
import {modulosEfectivos} from '@/api/capabilities';
import {colors} from '@/theme/colors';
import type {LogisticaProps} from '@/navigation/types';

type Pestana = 'recepcion' | 'preparacion';

const PESTANAS: {key: Pestana; labelKey: string; label: string}[] = [
  {key: 'recepcion', labelKey: 'logistica.pestana_recepcion', label: 'Recepción'},
  {key: 'preparacion', labelKey: 'logistica.pestana_traspaso', label: 'Traspaso'},
];

export default function LogisticaScreen({navigation, route}: LogisticaProps) {
  const {t} = useTranslation();
  const [pestana, setPestana] = useState<Pestana>('recepcion');
  const [idPaleEscaneado, setIdPaleEscaneado] = useState<string | null>(null);
  // Por defecto visible (degradable) hasta que llegue la respuesta de `/me/modules`.
  const [puedeTraspaso, setPuedeTraspaso] = useState(true);

  useEffect(() => {
    let vivo = true;
    modulosEfectivos().then(m => {
      if (vivo) {
        setPuedeTraspaso(m['logistica.traspaso'] !== false);
      }
    });
    return () => {
      vivo = false;
    };
  }, []);

  useEffect(() => {
    if (!puedeTraspaso && pestana === 'preparacion') {
      setPestana('recepcion');
    }
  }, [puedeTraspaso, pestana]);

  const pestanas = useMemo(
    () => (puedeTraspaso ? PESTANAS : PESTANAS.filter(p => p.key !== 'preparacion')),
    [puedeTraspaso],
  );

  useEffect(() => {
    const escaneado = route.params?.escaneado;
    if (escaneado) {
      setIdPaleEscaneado(escaneado);
      setPestana('recepcion');
      navigation.setParams({escaneado: undefined});
    }
  }, [route.params?.escaneado, navigation]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('logistica.titulo', 'Logística')}</Text>
        <View style={{width: 90}} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabsRow}>
          {pestanas.map(p => (
            <TouchableOpacity
              key={p.key}
              style={[styles.tab, pestana === p.key && styles.tabActive]}
              onPress={() => setPestana(p.key)}>
              <Text style={[styles.tabText, pestana === p.key && styles.tabTextActive]}>
                {t(p.labelKey, p.label)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {pestana === 'recepcion' && (
        <TabRecepcion
          navigation={navigation}
          idPaleInicial={idPaleEscaneado}
          onConsumido={() => setIdPaleEscaneado(null)}
        />
      )}
      {pestana === 'preparacion' && puedeTraspaso && <TabPreparacion navigation={navigation} />}
    </SafeAreaView>
  );
}

// ── Recepción ────────────────────────────────────────────────────────────────

function TabRecepcion({
  navigation,
  idPaleInicial,
  onConsumido,
}: {
  navigation: LogisticaProps['navigation'];
  idPaleInicial: string | null;
  onConsumido: () => void;
}) {
  const {t} = useTranslation();
  const [idPale, setIdPale] = useState('');
  const [esperados, setEsperados] = useState<ItemEsperado[] | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [recibiendo, setRecibiendo] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const [albaran, setAlbaran] = useState<TraspasoDetalle | null>(null);
  const [cargandoAlbaran, setCargandoAlbaran] = useState(false);

  useEffect(() => {
    if (idPaleInicial) {
      setIdPale(idPaleInicial);
      onConsumido();
    }
  }, [idPaleInicial, onConsumido]);

  const buscar = useCallback(async () => {
    if (!idPale.trim()) {
      return;
    }
    setBuscando(true);
    setAviso(null);
    setEsperados(null);
    try {
      const items = await itemsEsperadosPalet(idPale.trim());
      setEsperados(items);
      if (items.length === 0) {
        setAviso({ok: false, texto: t('logistica.pale_sin_pendientes', 'Ese palé no tiene artículos pendientes de recibir.')});
      }
    } catch {
      setAviso({ok: false, texto: t('logistica.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setBuscando(false);
    }
  }, [idPale, t]);

  const verAlbaran = useCallback(async () => {
    const primero = esperados?.[0];
    if (!primero) {
      return;
    }
    setCargandoAlbaran(true);
    try {
      setAlbaran(await obtenerTraspaso(primero.id_documento));
    } finally {
      setCargandoAlbaran(false);
    }
  }, [esperados]);

  const confirmar = useCallback(async () => {
    if (!idPale.trim()) {
      return;
    }
    setRecibiendo(true);
    setAviso(null);
    try {
      const r = await recibirPalet(idPale.trim());
      if (r.ok) {
        setAviso({ok: true, texto: t('logistica.recepcion_confirmada_ok', 'Recepción confirmada correctamente.')});
        setEsperados(null);
        setIdPale('');
      } else {
        const motivos: Record<string, string> = {
          destino_incorrecto: t('logistica.motivo_destino_incorrecto', 'Este palé no está destinado a tu centro.'),
          pale_ya_recibido: t('logistica.motivo_pale_ya_recibido', 'Este palé ya se recibió antes.'),
          sin_centro_receptor: t('logistica.motivo_sin_centro_receptor', 'Tu perfil no tiene tienda/almacén asociado.'),
        };
        setAviso({ok: false, texto: motivos[r.motivo] || t('logistica.no_se_pudo_confirmar', 'No se pudo confirmar la recepción.')});
      }
    } catch {
      setAviso({ok: false, texto: t('logistica.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setRecibiendo(false);
    }
  }, [idPale, t]);

  return (
    <ScrollView style={styles.tabBody} contentContainerStyle={styles.tabBodyContent}>
      <Text style={styles.sectionTitle}>{t('logistica.recibir_pale_h2', 'Recibir palé')}</Text>
      <Text style={styles.hint}>
        {t('logistica.centro_automatico_hint', 'El centro receptor se resuelve automáticamente según tu perfil — no hace falta elegirlo.')}
      </Text>
      <View style={styles.row}>
        <TextInput
          style={[styles.input, {flex: 1}]}
          placeholder={t('logistica.id_pale_ph', 'ID del palé')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="characters"
          value={idPale}
          onChangeText={setIdPale}
        />
        <TouchableOpacity
          style={styles.scanBtn}
          onPress={() => navigation.navigate('Scanner', {volverA: 'Logistica'})}>
          <Text style={styles.scanBtnText}>{t('logistica.escanear_btn', 'Escanear')}</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity
        style={[styles.button, buscando && styles.buttonDisabled]}
        onPress={buscar}
        disabled={buscando || !idPale.trim()}>
        {buscando ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.buttonText}>{t('logistica.buscar_btn', 'Buscar')}</Text>}
      </TouchableOpacity>

      {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

      {esperados && esperados.length > 0 ? (
        <>
          <View style={styles.rowEntreLineas}>
            <Text style={styles.sectionTitle}>{t('logistica.contenido_esperado_h2', 'Contenido esperado')}</Text>
            <TouchableOpacity onPress={verAlbaran} disabled={cargandoAlbaran}>
              {cargandoAlbaran ? (
                <ActivityIndicator color={colors.cyan} size="small" />
              ) : (
                <Text style={styles.enlace}>{t('logistica.ver_albaran_completo', 'Ver albarán completo')}</Text>
              )}
            </TouchableOpacity>
          </View>
          {esperados.map((it, i) => (
            <View key={`${it.codigo}-${i}`} style={styles.card}>
              <Text style={styles.cardTitle}>{it.nombre}</Text>
              <Text style={styles.cardDetail}>{it.codigo} · {it.cantidad} uds · {it.id_visual}</Text>
            </View>
          ))}
          <TouchableOpacity
            style={[styles.button, recibiendo && styles.buttonDisabled]}
            onPress={confirmar}
            disabled={recibiendo}>
            {recibiendo ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>{t('logistica.confirmar_recepcion_btn', 'Confirmar recepción')}</Text>
            )}
          </TouchableOpacity>
        </>
      ) : null}

      <Modal visible={!!albaran} transparent animationType="fade" onRequestClose={() => setAlbaran(null)}>
        <View style={styles.modalFondo}>
          <ScrollView style={styles.modalTarjeta} contentContainerStyle={{padding: 20}}>
            {albaran ? (
              <>
                <Text style={styles.sectionTitle}>{t('logistica.albaran_num', 'Albarán {{id}}', {id: albaran.id_documento})}</Text>
                <Text style={styles.cardDetail}>{albaran.origen} → {albaran.destino}</Text>
                <Text style={styles.cardDetail}>
                  {albaran.agencia ? t('logistica.agencia_prefijo', 'Agencia: {{a}} · ', {a: albaran.agencia}) : ''}
                  {t('logistica.envio_lbl', 'Envío: {{f}}', {f: albaran.fecha_envio})}
                </Text>
                {albaran.usuario ? (
                  <Text style={styles.cardDetail}>{t('logistica.preparado_por_lbl', 'Preparado por: {{u}}', {u: albaran.usuario})}</Text>
                ) : null}
                {albaran.observaciones ? (
                  <Text style={styles.cardDetail}>{t('logistica.obs_lbl', 'Obs.: {{o}}', {o: albaran.observaciones})}</Text>
                ) : null}
                <Text style={[styles.sectionTitle, {marginTop: 14}]}>
                  {t('logistica.todos_los_pales', 'Todos los palés ({{n}} líneas)', {n: albaran.lineas.length})}
                </Text>
                {albaran.lineas.map(l => (
                  <View key={l.id_linea} style={styles.card}>
                    <Text style={styles.cardTitle}>{l.id_visual} · {l.codigo}</Text>
                    <Text style={styles.cardDetail}>
                      {l.nombre} x{l.cantidad}{l.peso_bulto != null ? ` · ${l.peso_bulto} kg` : ''}
                    </Text>
                  </View>
                ))}
              </>
            ) : null}
            <TouchableOpacity style={styles.button} onPress={() => setAlbaran(null)}>
              <Text style={styles.buttonText}>{t('common.cerrar', 'Cerrar')}</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>
    </ScrollView>
  );
}

// ── Preparación (picking) ──────────────────────────────────────────────────

function TabPreparacion({navigation}: {navigation: LogisticaProps['navigation']}) {
  const {t} = useTranslation();
  const [items, setItems] = useState<Traspaso[]>([]);
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setItems(await listarTraspasos({estado: 'EN PREPARACION', limite: 100}));
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => {
    (async () => {
      setCargando(true);
      await cargar();
      setCargando(false);
    })();
  }, [cargar]);

  return (
    <FlatList
      style={styles.tabBody}
      data={items}
      keyExtractor={item => item.id_documento}
      contentContainerStyle={styles.list}
      refreshControl={
        <RefreshControl
          refreshing={refrescando}
          onRefresh={async () => {
            setRefrescando(true);
            await cargar();
            setRefrescando(false);
          }}
          tintColor={colors.cyan}
        />
      }
      ListHeaderComponent={
        <Text style={styles.hint}>{t('logistica.picking_hint', 'Documentos pendientes de picking — toca uno para gestionarlo.')}</Text>
      }
      ListEmptyComponent={
        cargando ? (
          <View style={styles.centered}>
            <ActivityIndicator color={colors.cyan} />
          </View>
        ) : (
          <View style={styles.centered}>
            <Text style={styles.hint}>{t('logistica.sin_docs_preparacion', 'No hay documentos en preparación.')}</Text>
          </View>
        )
      }
      renderItem={({item}) => (
        <TouchableOpacity
          style={styles.card}
          onPress={() => navigation.navigate('LogisticaPicking', {id_documento: item.id_documento})}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>{item.id_documento}</Text>
            <Text style={[styles.badge, {color: colors.warning}]}>{t('logistica.n_bultos', '{{n}} bultos', {n: item.bultos})}</Text>
          </View>
          <Text style={styles.cardDetail}>{item.origen} → {item.destino}</Text>
        </TouchableOpacity>
      )}
    />
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
  tabsScroll: {flexGrow: 0, marginBottom: 4},
  tabsRow: {flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingBottom: 10},
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabActive: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  tabText: {color: colors.textDim, fontSize: 13, fontWeight: '700'},
  tabTextActive: {color: colors.bg},
  tabBody: {flex: 1},
  tabBodyContent: {padding: 16, paddingBottom: 32},
  sectionTitle: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 12, marginBottom: 8},
  rowEntreLineas: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  enlace: {color: colors.cyan, fontWeight: '700', fontSize: 12},
  modalFondo: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  modalTarjeta: {
    backgroundColor: colors.panel,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    width: '100%',
    maxHeight: '80%',
  },
  hint: {color: colors.textDim, fontSize: 12, marginBottom: 8},
  row: {flexDirection: 'row', gap: 8, alignItems: 'center'},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 8,
    fontSize: 15,
  },
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 8,
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 13},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 4,
    marginBottom: 8,
  },
  buttonDisabled: {opacity: 0.5},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginBottom: 8, fontSize: 12},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12},
  centered: {alignItems: 'center', justifyContent: 'center', padding: 32},
  list: {padding: 16, paddingTop: 8},
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
  cardDetail: {color: colors.textDim, marginTop: 4, fontSize: 12},
  badge: {fontSize: 11, fontWeight: '800'},
});
