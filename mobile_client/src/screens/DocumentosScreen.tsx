/**
 * Registro documental (capacidad "documentos" -> GET /api/v1/documents). Solo metadatos: la
 * descarga del fichero no está expuesta todavía desde el backend (ver README).
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
import {buscarDocumentos, type Documento} from '@/api/documents';
import {colors} from '@/theme/colors';
import type {DocumentosProps} from '@/navigation/types';

function formatoTamano(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentosScreen({navigation}: DocumentosProps) {
  const [q, setQ] = useState('');
  const [resultados, setResultados] = useState<Documento[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async (texto: string) => {
    setLoading(true);
    setError(null);
    try {
      setResultados(await buscarDocumentos(texto.trim()));
    } catch {
      setError('No se pudo consultar el registro documental. Revisa la conexión.');
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
        <Text style={styles.title}>Documentos</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="Buscar por nombre, referencia, cliente…"
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={q}
          onChangeText={setQ}
        />
        <Text style={styles.hintSmall}>Solo consulta de metadatos; la descarga aún no está disponible.</Text>
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
          keyExtractor={item => item.id_documento}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>Sin resultados.</Text>
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.nombre} numberOfLines={2}>
                  {item.nombre}
                </Text>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{item.tipo_documento}</Text>
                </View>
              </View>
              <Text style={styles.detalle} numberOfLines={1}>
                {[item.cliente, item.trabajador, item.referencia].filter(Boolean).join(' · ') || '—'}
              </Text>
              <Text style={styles.fecha}>
                {item.fecha_generacion}
                {item.size_bytes ? ` · ${formatoTamano(item.size_bytes)}` : ''}
              </Text>
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
  hintSmall: {color: colors.textDim, fontSize: 11, marginTop: 6},
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
  nombre: {color: colors.text, fontWeight: '800', fontSize: 14, flex: 1, marginRight: 8},
  badge: {
    backgroundColor: colors.panelAlt,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: {color: colors.cyan, fontSize: 11, fontWeight: '700'},
  detalle: {color: colors.textDim, marginTop: 4, fontSize: 12},
  fecha: {color: colors.textDim, marginTop: 4, fontSize: 11},
});
