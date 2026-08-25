/**
 * Actividad (capacidad "timeline" -> GET /api/v1/timeline). Cronología unificada de comunicaciones:
 * salientes (cualquier canal) + correos entrantes, más recientes primero.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {listarTimeline, type EventoTimeline} from '@/api/timeline';
import {colors} from '@/theme/colors';
import type {TimelineProps} from '@/navigation/types';

export default function TimelineScreen({navigation}: TimelineProps) {
  const [correo, setCorreo] = useState('');
  const [items, setItems] = useState<EventoTimeline[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async (filtro: string) => {
    setError(null);
    try {
      setItems(await listarTimeline(filtro.trim() || undefined));
    } catch {
      setError('No se pudo consultar la actividad. Revisa la conexión.');
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true);
      await cargar(correo);
      setLoading(false);
    }, 350);
    return () => clearTimeout(t);
  }, [correo, cargar]);

  const onRefresh = useCallback(async () => {
    setRefrescando(true);
    await cargar(correo);
    setRefrescando(false);
  }, [correo, cargar]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Actividad</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="Filtrar por correo del contacto…"
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={correo}
          onChangeText={setCorreo}
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
          data={items}
          keyExtractor={(item, idx) => `${item.com_id ?? 'in'}-${idx}`}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refrescando} onRefresh={onRefresh} tintColor={colors.cyan} />
          }
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>Sin actividad.</Text>
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.direccion}>
                  {item.sentido === 'saliente' ? '↑ Enviado' : '↓ Recibido'} · {item.canal}
                </Text>
                <Text style={styles.estado}>{item.estado}</Text>
              </View>
              <Text style={styles.asunto} numberOfLines={1}>
                {item.asunto || '(sin asunto)'}
              </Text>
              <Text style={styles.detalle} numberOfLines={1}>
                {item.contraparte}
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
  direccion: {color: colors.cyan, fontWeight: '700', fontSize: 12},
  estado: {color: colors.textDim, fontSize: 11},
  asunto: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 6},
  detalle: {color: colors.textDim, marginTop: 2},
  fecha: {color: colors.textDim, marginTop: 4, fontSize: 11},
});
