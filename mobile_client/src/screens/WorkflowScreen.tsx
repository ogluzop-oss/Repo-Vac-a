/**
 * Bandeja de aprobaciones (capacidad "workflow" -> /api/v1/workflow/tasks). Solo se listan las
 * tareas que el usuario puede resolver (el motor ya filtra por rol/permiso/delegación).
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
import {
  aprobarTarea,
  listarBandeja,
  rechazarTarea,
  type TareaAprobacion,
} from '@/api/workflow';
import {colors} from '@/theme/colors';
import type {WorkflowProps} from '@/navigation/types';

export default function WorkflowScreen({navigation}: WorkflowProps) {
  const [items, setItems] = useState<TareaAprobacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comentarios, setComentarios] = useState<Record<number, string>>({});
  const [procesando, setProcesando] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setItems(await listarBandeja());
    } catch {
      setError('No se pudo consultar la bandeja. Revisa la conexión.');
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

  const onResolver = useCallback(
    async (t: TareaAprobacion, accion: 'aprobar' | 'rechazar') => {
      setProcesando(t.id);
      const comentario = comentarios[t.id];
      const r = accion === 'aprobar' ? await aprobarTarea(t.id, comentario) : await rechazarTarea(t.id, comentario);
      setProcesando(null);
      if (r.kind === 'ok') {
        setItems(prev => prev.filter(x => x.id !== t.id));
      } else {
        setError(r.mensaje);
      }
    },
    [comentarios],
  );

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Aprobaciones</Text>
        <View style={{width: 60}} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
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
              {error ? (
                <Text style={styles.error}>{error}</Text>
              ) : (
                <Text style={styles.hint}>No tienes aprobaciones pendientes.</Text>
              )}
            </View>
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <Text style={styles.tituloItem}>
                {item.entidad} #{item.entidad_id}
              </Text>
              <Text style={styles.detalle}>
                {item.asignado_rol ? `Requiere rol ${item.asignado_rol}` : 'Requiere tu aprobación'}
              </Text>
              <Text style={styles.fecha}>{item.fecha_creacion}</Text>
              <TextInput
                style={styles.input}
                placeholder="Comentario (opcional)"
                placeholderTextColor={colors.textDim}
                value={comentarios[item.id] ?? ''}
                onChangeText={txt => setComentarios(prev => ({...prev, [item.id]: txt}))}
              />
              <View style={styles.acciones}>
                <TouchableOpacity
                  style={[styles.btn, styles.btnRechazar]}
                  disabled={procesando === item.id}
                  onPress={() => onResolver(item, 'rechazar')}>
                  <Text style={styles.btnRechazarText}>Rechazar</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btn, styles.btnAprobar]}
                  disabled={procesando === item.id}
                  onPress={() => onResolver(item, 'aprobar')}>
                  {procesando === item.id ? (
                    <ActivityIndicator color={colors.bg} />
                  ) : (
                    <Text style={styles.btnAprobarText}>Aprobar</Text>
                  )}
                </TouchableOpacity>
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
  tituloItem: {color: colors.text, fontWeight: '800', fontSize: 15},
  detalle: {color: colors.textDim, marginTop: 4},
  fecha: {color: colors.textDim, marginTop: 2, fontSize: 11},
  input: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginTop: 10,
    fontSize: 13,
  },
  acciones: {flexDirection: 'row', gap: 8, marginTop: 10},
  btn: {flex: 1, borderRadius: 10, paddingVertical: 10, alignItems: 'center'},
  btnAprobar: {backgroundColor: colors.ok},
  btnAprobarText: {color: colors.bg, fontWeight: '800'},
  btnRechazar: {backgroundColor: colors.panelAlt, borderWidth: 1, borderColor: colors.danger},
  btnRechazarText: {color: colors.danger, fontWeight: '800'},
});
