/**
 * Directorio de proveedores (capacidad "proveedores" -> GET /api/v1/suppliers).
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
import {buscarProveedores, type Proveedor} from '@/api/suppliers';
import {colors} from '@/theme/colors';
import type {ProveedoresProps} from '@/navigation/types';

export default function ProveedoresScreen({navigation}: ProveedoresProps) {
  const [q, setQ] = useState('');
  const [resultados, setResultados] = useState<Proveedor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async (texto: string) => {
    setLoading(true);
    setError(null);
    try {
      setResultados(await buscarProveedores(texto.trim()));
    } catch {
      setError('No se pudo consultar los proveedores. Revisa la conexión.');
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
        <Text style={styles.title}>Proveedores</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="Buscar por razón social, CIF…"
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
          keyExtractor={item => String(item.id_proveedor)}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>Sin resultados.</Text>
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.nombre} numberOfLines={1}>
                  {item.nombre_comercial || item.razon_social}
                </Text>
                {item.bloqueado ? (
                  <View style={[styles.badge, styles.badgeDanger]}>
                    <Text style={[styles.badgeText, styles.badgeTextDanger]}>Bloqueado</Text>
                  </View>
                ) : item.homologado ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>Homologado</Text>
                  </View>
                ) : null}
              </View>
              <Text style={styles.detalle} numberOfLines={1}>
                {item.cif_nif || '—'} {item.telefono ? `· ${item.telefono}` : ''}
              </Text>
              {item.email ? (
                <Text style={styles.detalle} numberOfLines={1}>
                  {item.email}
                </Text>
              ) : null}
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
  badge: {
    backgroundColor: colors.panelAlt,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeDanger: {backgroundColor: colors.danger},
  badgeText: {color: colors.cyan, fontSize: 11, fontWeight: '700'},
  badgeTextDanger: {color: colors.text},
  detalle: {color: colors.textDim, marginTop: 4},
});
