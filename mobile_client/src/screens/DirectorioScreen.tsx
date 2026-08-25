/**
 * Directorio de contactos corporativos (capacidad "directorio" -> GET /api/v1/contacts).
 *
 * Búsqueda por texto libre con el Recipient Resolution Service (CCP): clientes, proveedores y
 * cualquier destinatario corporativo resuelto por el backend, no una agenda local.
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
import {buscarContactos, type Destinatario} from '@/api/contacts';
import {colors} from '@/theme/colors';
import type {DirectorioProps} from '@/navigation/types';

export default function DirectorioScreen({navigation}: DirectorioProps) {
  const [q, setQ] = useState('');
  const [resultados, setResultados] = useState<Destinatario[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [buscado, setBuscado] = useState(false);

  const buscar = useCallback(async (texto: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await buscarContactos(texto.trim());
      setResultados(r);
    } catch {
      setError('No se pudo consultar el directorio. Revisa la conexión.');
    } finally {
      setBuscado(true);
      setLoading(false);
    }
  }, []);

  // Búsqueda con debounce: evita una petición por cada pulsación.
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
        <Text style={styles.title}>Directorio</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="Buscar por nombre, correo, NIF…"
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
          keyExtractor={item => item.correo}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            buscado ? (
              <View style={styles.centered}>
                <Text style={styles.hint}>
                  {q.trim() ? 'Sin resultados.' : 'Escribe para buscar en el directorio.'}
                </Text>
              </View>
            ) : null
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.nombre} numberOfLines={1}>
                  {item.nombre_mostrado || item.correo}
                </Text>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{item.etiqueta}</Text>
                </View>
              </View>
              <Text style={styles.correo} numberOfLines={1}>
                {item.correo}
              </Text>
              {item.cargo || item.departamento ? (
                <Text style={styles.detalle} numberOfLines={1}>
                  {[item.cargo, item.departamento].filter(Boolean).join(' · ')}
                </Text>
              ) : null}
              {item.avisos.length > 0 ? (
                <Text style={styles.aviso} numberOfLines={2}>
                  ⚠ {item.avisos.join(' · ')}
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
  badgeText: {color: colors.cyan, fontSize: 11, fontWeight: '700'},
  correo: {color: colors.textDim, marginTop: 4},
  detalle: {color: colors.textDim, marginTop: 2, fontSize: 12},
  aviso: {color: colors.warning, marginTop: 6, fontSize: 12},
});
