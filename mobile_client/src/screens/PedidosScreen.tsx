/**
 * Pedidos de RECEPCIÓN de palets (capacidad "pedidos" -> GET /api/v1/orders).
 *
 * Nota de dominio (ver `src/services/pedidos.py`): en Smart Manager, hoy, un "pedido" es la
 * recepción de un palet en almacén (escaneo RFID/código), no un pedido de venta ni de compra.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {listarPedidos, type Pedido} from '@/api/orders';
import {colors} from '@/theme/colors';
import type {PedidosProps} from '@/navigation/types';

type Filtro = 'todos' | 'pendientes' | 'procesados';

export default function PedidosScreen({navigation}: PedidosProps) {
  const [filtro, setFiltro] = useState<Filtro>('todos');
  const [items, setItems] = useState<Pedido[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async (f: Filtro) => {
    setError(null);
    try {
      const procesado = f === 'todos' ? undefined : f === 'procesados';
      setItems(await listarPedidos(procesado));
    } catch {
      setError('No se pudo consultar las recepciones. Revisa la conexión.');
    }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await cargar(filtro);
      setLoading(false);
    })();
  }, [filtro, cargar]);

  const onRefresh = useCallback(async () => {
    setRefrescando(true);
    await cargar(filtro);
    setRefrescando(false);
  }, [filtro, cargar]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Pedidos (recepción)</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.tabs}>
        {(['todos', 'pendientes', 'procesados'] as Filtro[]).map(f => (
          <TouchableOpacity
            key={f}
            style={[styles.tab, filtro === f && styles.tabActive]}
            onPress={() => setFiltro(f)}>
            <Text style={[styles.tabText, filtro === f && styles.tabTextActive]}>
              {f === 'todos' ? 'Todos' : f === 'pendientes' ? 'Pendientes' : 'Procesados'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
        </View>
      ) : error ? (
        <View style={styles.centered}>
          <Text style={styles.error}>{error}</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={item => String(item.id)}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refrescando} onRefresh={onRefresh} tintColor={colors.cyan} />
          }
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>No hay recepciones{filtro !== 'todos' ? ` ${filtro}` : ''}.</Text>
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.pale} numberOfLines={1}>
                  Palet {item.pale_codigo}
                </Text>
                <View
                  style={[
                    styles.badge,
                    {backgroundColor: item.procesado ? colors.ok : colors.warning},
                  ]}>
                  <Text style={styles.badgeText}>{item.procesado ? 'Procesado' : 'Pendiente'}</Text>
                </View>
              </View>
              <Text style={styles.detalle}>
                {item.items.length} artículo(s) · tienda {item.id_tienda ?? '—'}
              </Text>
              <Text style={styles.fecha}>{item.fecha}</Text>
            </View>
          )}
        />
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
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 60},
  title: {color: colors.text, fontSize: 18, fontWeight: '800'},
  tabs: {flexDirection: 'row', paddingHorizontal: 16, marginBottom: 8, gap: 8},
  tab: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: 'center',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabActive: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  tabText: {color: colors.textDim, fontWeight: '700', fontSize: 12},
  tabTextActive: {color: colors.bg},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
  error: {color: colors.danger, textAlign: 'center'},
  list: {padding: 16, paddingTop: 4},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  pale: {color: colors.text, fontWeight: '800', fontSize: 15, flex: 1, marginRight: 8},
  badge: {borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3},
  badgeText: {color: colors.bg, fontSize: 11, fontWeight: '800'},
  detalle: {color: colors.textDim, marginTop: 4},
  fecha: {color: colors.textDim, marginTop: 2, fontSize: 11},
});
