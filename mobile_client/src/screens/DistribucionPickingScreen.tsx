/**
 * Pedidos — ciclo de vida de los pedidos ONLINE de la tienda web/Click&Collect
 * (`services.tpv.online_orders_service`, mismo motor que el Portal Web de escritorio). Al marcar
 * "preparado" o "entregado" el cliente recibe un correo automático (ya lo hacía escritorio para
 * preparado→enviado→entregado; "preparado" es nuevo, ver `online_orders_service._notificar_cliente`).
 *
 * La pestaña "B2B" (picking de pedidos mayoristas) que estuvo fusionada aquí se ha retirado a
 * petición del usuario: es redundante con el módulo Logística → pestaña Recepción, que ya cubre el
 * mismo flujo físico de almacén. La gestión B2B (crear pedido/elegir transportista/expedir) sigue en
 * escritorio (`gui/distribucion_gui.py`), sin cambios.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {
  listarPedidosOnline,
  marcarPedidoEnviado,
  marcarPedidoEntregado,
  marcarPedidoPreparado,
  type PedidoOnline,
} from '@/api/distribution';
import {colors} from '@/theme/colors';
import type {DistribucionProps} from '@/navigation/types';

type Pestana = 'preparar' | 'enviar' | 'entregar';

const PESTANAS: {key: Pestana; labelKey: string; label: string}[] = [
  {key: 'preparar', labelKey: 'dist.pestana_preparar', label: 'Preparar'},
  {key: 'enviar', labelKey: 'dist.pestana_enviar', label: 'Enviar'},
  {key: 'entregar', labelKey: 'dist.pestana_entregar', label: 'Entregar'},
];

export default function DistribucionPickingScreen({navigation}: DistribucionProps) {
  const {t} = useTranslation();
  const [pestana, setPestana] = useState<Pestana>('preparar');

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('dist.titulo', 'Pedidos')}</Text>
        <View style={{width: 90}} />
      </View>

      <View style={styles.tabsRow}>
        {PESTANAS.map(p => (
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

      {pestana === 'preparar' ? (
        <TabOnline
          key="preparar"
          estadoFiltro="PAGADO"
          etiquetaAccion={t('dist.marcar_preparado_btn', 'Marcar preparado')}
          onAccion={marcarPedidoPreparado}
        />
      ) : null}
      {pestana === 'enviar' ? <TabEnviar /> : null}
      {pestana === 'entregar' ? (
        <TabOnline
          key="entregar"
          estadoFiltro="ENVIADO"
          etiquetaAccion={t('dist.marcar_entregado_btn', 'Marcar entregado')}
          onAccion={marcarPedidoEntregado}
        />
      ) : null}
    </SafeAreaView>
  );
}

// ── Online: Preparar / Entregar (misma estructura, distinta acción) ─────────────────────────────────
function TabOnline({
  estadoFiltro,
  etiquetaAccion,
  onAccion,
}: {
  estadoFiltro: string;
  etiquetaAccion: string;
  onAccion: (idPedido: string) => Promise<{ok: boolean}>;
}) {
  const {t} = useTranslation();
  const [pedidos, setPedidos] = useState<PedidoOnline[]>([]);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setPedidos(await listarPedidosOnline(estadoFiltro));
    } catch {
      setPedidos([]);
    } finally {
      setCargando(false);
    }
  }, [estadoFiltro]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const accionar = useCallback(
    async (idPedido: string) => {
      setProcesando(idPedido);
      try {
        const r = await onAccion(idPedido);
        if (r.ok) {
          await cargar();
        }
      } finally {
        setProcesando(null);
      }
    },
    [onAccion, cargar],
  );

  if (cargando) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.cyan} />
      </View>
    );
  }

  return (
    <FlatList
      style={styles.tabFlex}
      data={pedidos}
      keyExtractor={item => item.id_pedido}
      contentContainerStyle={styles.list}
      ListEmptyComponent={
        <View style={styles.centered}>
          <Text style={styles.hint}>{t('dist.sin_pedidos_estado', 'No hay pedidos en este estado.')}</Text>
        </View>
      }
      renderItem={({item}) => (
        <View style={styles.card}>
          <View style={{flex: 1}}>
            <Text style={styles.cardTitle}>{item.cliente_nombre || t('dist.cliente_generico', 'Cliente')}</Text>
            <Text style={styles.cardDetail}>
              {item.id_pedido.slice(0, 8)} · {Number(item.total).toFixed(2)} € · {item.fecha}
            </Text>
            {item.cliente_telefono ? (
              <Text style={styles.cardDetail}>{t('dist.tel_lbl', 'Tel.: {{t}}', {t: item.cliente_telefono})}</Text>
            ) : null}
            {item.es_encargo_origen ? (
              <Text style={styles.badgeEncargo}>
                {t('dist.encargo_solicitado_por', 'Encargo solicitado por: {{tienda}}',
                   {tienda: item.tienda_destino_nombre || t('dist.otra_tienda', 'otra tienda')})}
              </Text>
            ) : null}
            {estadoFiltro === 'ENVIADO' && (item.transportista || item.seguimiento) ? (
              <Text style={styles.cardDetail}>
                {item.transportista || '—'}{item.seguimiento ? ` · ${item.seguimiento}` : ''}
              </Text>
            ) : null}
          </View>
          <TouchableOpacity
            style={[styles.button, styles.buttonSmall, procesando === item.id_pedido && styles.buttonDisabled]}
            disabled={procesando === item.id_pedido}
            onPress={() => accionar(item.id_pedido)}>
            {procesando === item.id_pedido ? (
              <ActivityIndicator color={colors.bg} size="small" />
            ) : (
              <Text style={styles.buttonText}>{etiquetaAccion}</Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    />
  );
}

// ── Online: Enviar (pide transportista/seguimiento antes de marcar) ─────────────────────────────────
function TabEnviar() {
  const {t} = useTranslation();
  const [pedidos, setPedidos] = useState<PedidoOnline[]>([]);
  const [cargando, setCargando] = useState(true);
  const [pedidoActivo, setPedidoActivo] = useState<PedidoOnline | null>(null);
  const [transportista, setTransportista] = useState('');
  const [seguimiento, setSeguimiento] = useState('');
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setPedidos(await listarPedidosOnline('PREPARANDO'));
    } catch {
      setPedidos([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const confirmarEnvio = useCallback(async () => {
    if (!pedidoActivo) {
      return;
    }
    setEnviando(true);
    try {
      const r = await marcarPedidoEnviado(pedidoActivo.id_pedido, transportista, seguimiento);
      if (r.ok) {
        setPedidoActivo(null);
        setTransportista('');
        setSeguimiento('');
        await cargar();
      }
    } finally {
      setEnviando(false);
    }
  }, [pedidoActivo, transportista, seguimiento, cargar]);

  return (
    <>
      {cargando ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
        </View>
      ) : (
        <FlatList
          style={styles.tabFlex}
          data={pedidos}
          keyExtractor={item => item.id_pedido}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>{t('dist.sin_pedidos_enviar', 'No hay pedidos preparados pendientes de enviar.')}</Text>
            </View>
          }
          renderItem={({item}) => (
            <TouchableOpacity style={styles.card} onPress={() => setPedidoActivo(item)}>
              <View style={{flex: 1}}>
                <Text style={styles.cardTitle}>{item.cliente_nombre || t('dist.cliente_generico', 'Cliente')}</Text>
                <Text style={styles.cardDetail}>
                  {item.id_pedido.slice(0, 8)} · {Number(item.total).toFixed(2)} € · {item.fecha}
                </Text>
                {item.cliente_telefono ? (
                  <Text style={styles.cardDetail}>{t('dist.tel_lbl', 'Tel.: {{t}}', {t: item.cliente_telefono})}</Text>
                ) : null}
                {item.es_encargo_origen ? (
                  <Text style={styles.badgeEncargo}>
                    {t('dist.encargo_solicitado_por', 'Encargo solicitado por: {{tienda}}',
                       {tienda: item.tienda_destino_nombre || t('dist.otra_tienda', 'otra tienda')})}
                  </Text>
                ) : null}
              </View>
            </TouchableOpacity>
          )}
        />
      )}

      <Modal visible={!!pedidoActivo} transparent animationType="fade">
        <View style={styles.modalFondo}>
          <View style={styles.modalTarjeta}>
            <Text style={styles.cardTitle}>{t('dist.enviar_pedido_titulo', 'Enviar pedido')}</Text>
            <TextInput
              style={styles.input}
              placeholder={t('dist.transportista_ph', 'Transportista')}
              placeholderTextColor={colors.textDim}
              value={transportista}
              onChangeText={setTransportista}
            />
            <TextInput
              style={styles.input}
              placeholder={t('dist.num_seguimiento_ph', 'Nº de seguimiento')}
              placeholderTextColor={colors.textDim}
              value={seguimiento}
              onChangeText={setSeguimiento}
            />
            <TouchableOpacity
              style={[styles.button, enviando && styles.buttonDisabled]}
              disabled={enviando}
              onPress={confirmarEnvio}>
              {enviando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>{t('dist.confirmar_envio_btn', 'Confirmar envío')}</Text>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.cancelar}
              onPress={() => {
                setPedidoActivo(null);
                setTransportista('');
                setSeguimiento('');
              }}>
              <Text style={styles.cancelarTexto}>{t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
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
  title: {color: colors.text, fontSize: 18, fontWeight: '800', flex: 1, textAlign: 'center'},
  tabsRow: {flexDirection: 'row', gap: 8, paddingHorizontal: 16, marginBottom: 8},
  tab: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: 10,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  tabActive: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  tabText: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  tabTextActive: {color: colors.bg},
  tabFlex: {flex: 1},
  progreso: {color: colors.textDim, fontSize: 12, marginHorizontal: 16, marginBottom: 4},
  hint: {color: colors.textDim, fontSize: 12, marginBottom: 8},
  error: {color: colors.danger, fontSize: 12, marginHorizontal: 16, marginBottom: 8},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
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
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 14},
  cardDetail: {color: colors.textDim, marginTop: 2, fontSize: 12},
  badgeEncargo: {color: colors.cyan, marginTop: 4, fontSize: 11, fontWeight: '700'},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginHorizontal: 16,
    marginBottom: 16,
  },
  buttonSmall: {marginHorizontal: 0, marginBottom: 0, paddingVertical: 10, paddingHorizontal: 14},
  buttonDisabled: {opacity: 0.5},
  buttonText: {color: colors.bg, fontWeight: '800'},
  input: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    marginTop: 12,
    marginBottom: 4,
  },
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
    padding: 20,
    width: '100%',
    maxWidth: 360,
  },
  cancelar: {marginTop: 10, alignItems: 'center', paddingVertical: 8},
  cancelarTexto: {color: colors.textDim, fontWeight: '700'},
});
