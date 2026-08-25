/**
 * Consulta de stock (capacidad "stock" -> GET /api/v1/stock, solo lectura).
 *
 * El escaneo de recepción (escritura, offline-first) sigue siendo un flujo aparte: `ScannerScreen`,
 * accesible desde el botón flotante "Escanear" del Dashboard.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {buscarStock, type ArticuloStock} from '@/api/stock';
import {colors} from '@/theme/colors';
import type {StockProps} from '@/navigation/types';

export default function StockScreen({navigation}: StockProps) {
  const [q, setQ] = useState('');
  const [resultados, setResultados] = useState<ArticuloStock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async (texto: string) => {
    setLoading(true);
    setError(null);
    try {
      setResultados(await buscarStock(texto.trim()));
    } catch {
      setError('No se pudo consultar el stock. Revisa la conexión.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => buscar(q), 350);
    return () => clearTimeout(t);
  }, [q, buscar]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Stock</Text>
        <TouchableOpacity onPress={() => navigation.navigate('Scanner')}>
          <Text style={styles.scanLink}>Escanear</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="Buscar por código o nombre…"
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={q}
          onChangeText={setQ}
        />
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
          data={resultados}
          keyExtractor={item => item.codigo}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>
                {q.trim() ? 'Sin resultados.' : 'Escribe para buscar artículos.'}
              </Text>
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.nombre} numberOfLines={1}>
                  {item.nombre}
                </Text>
                <Text style={styles.codigo}>{item.codigo}</Text>
              </View>
              <View style={styles.stockRow}>
                <View style={styles.stockBox}>
                  <Text style={styles.stockValor}>{item.stock_tienda}</Text>
                  <Text style={styles.stockLabel}>Tienda</Text>
                </View>
                <View style={styles.stockBox}>
                  <Text style={styles.stockValor}>{item.stock_total}</Text>
                  <Text style={styles.stockLabel}>Total</Text>
                </View>
                <View style={styles.stockBox}>
                  <Text style={styles.stockValor}>{item.stock_central}</Text>
                  <Text style={styles.stockLabel}>Central</Text>
                </View>
              </View>
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
  scanLink: {color: colors.cyan, fontSize: 14, fontWeight: '700'},
  searchBox: {paddingHorizontal: 16, marginBottom: 8},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
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
  nombre: {color: colors.text, fontWeight: '800', fontSize: 15, flex: 1, marginRight: 8},
  codigo: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  stockRow: {flexDirection: 'row', marginTop: 10, gap: 8},
  stockBox: {
    flex: 1,
    backgroundColor: colors.panelAlt,
    borderRadius: 10,
    alignItems: 'center',
    paddingVertical: 8,
  },
  stockValor: {color: colors.cyan, fontWeight: '800', fontSize: 16},
  stockLabel: {color: colors.textDim, fontSize: 11, marginTop: 2},
});
