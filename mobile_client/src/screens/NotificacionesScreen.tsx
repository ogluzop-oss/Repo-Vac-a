/**
 * Notificaciones pendientes del usuario (capacidad "notificaciones" -> GET /api/v1/notifications).
 * Tocar una notificación la marca como leída y la retira de la lista (igual que el backend: solo
 * se listan las NO leídas).
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
import {listarNotificaciones, marcarLeida, type Notificacion} from '@/api/notifications';
import {colors} from '@/theme/colors';
import type {NotificacionesProps} from '@/navigation/types';

const COLOR_PRIORIDAD: Record<string, string> = {
  critica: colors.danger,
  alta: colors.warning,
  normal: colors.cyan,
  baja: colors.textDim,
};

export default function NotificacionesScreen({navigation}: NotificacionesProps) {
  const [items, setItems] = useState<Notificacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setItems(await listarNotificaciones());
    } catch {
      setError('No se pudo consultar las notificaciones. Revisa la conexión.');
    }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await cargar();
      setLoading(false);
    })();
  }, [cargar]);

  const onRefresh = useCallback(async () => {
    setRefrescando(true);
    await cargar();
    setRefrescando(false);
  }, [cargar]);

  const onTocar = useCallback(async (n: Notificacion) => {
    setItems(prev => prev.filter(x => x.id !== n.id));
    const ok = await marcarLeida(n.id);
    if (!ok) {
      // Reintroduce la notificación si el backend no pudo marcarla (p. ej. sin conexión).
      setItems(prev => [n, ...prev]);
    }
  }, []);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Notificaciones</Text>
        <View style={{width: 60}} />
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
              <Text style={styles.hint}>No tienes notificaciones pendientes.</Text>
            </View>
          }
          renderItem={({item}) => (
            <TouchableOpacity style={styles.card} onPress={() => onTocar(item)}>
              <View
                style={[
                  styles.franja,
                  {backgroundColor: COLOR_PRIORIDAD[item.prioridad] ?? colors.textDim},
                ]}
              />
              <View style={styles.cardBody}>
                <Text style={styles.tituloItem} numberOfLines={1}>
                  {item.titulo}
                </Text>
                {item.mensaje ? (
                  <Text style={styles.mensaje} numberOfLines={2}>
                    {item.mensaje}
                  </Text>
                ) : null}
                <Text style={styles.fecha}>
                  {item.modulo ? `${item.modulo} · ` : ''}
                  {item.fecha_creacion}
                </Text>
              </View>
            </TouchableOpacity>
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
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
  error: {color: colors.danger, textAlign: 'center'},
  list: {padding: 16, paddingTop: 4},
  card: {
    flexDirection: 'row',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    marginBottom: 10,
    overflow: 'hidden',
  },
  franja: {width: 5},
  cardBody: {flex: 1, padding: 14},
  tituloItem: {color: colors.text, fontWeight: '800', fontSize: 15},
  mensaje: {color: colors.textDim, marginTop: 4},
  fecha: {color: colors.textDim, marginTop: 6, fontSize: 11},
});
