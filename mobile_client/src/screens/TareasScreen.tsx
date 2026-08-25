/**
 * Mis tareas (capacidad "tareas" -> GET/POST /api/v1/tasks). Solo las asignadas al usuario.
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
  cambiarEstadoTarea,
  crearTarea,
  listarTareas,
  type EstadoTarea,
  type Tarea,
} from '@/api/tasks';
import {colors} from '@/theme/colors';
import type {TareasProps} from '@/navigation/types';

type Filtro = 'activas' | 'todas' | 'completadas';

const COLOR_PRIORIDAD: Record<string, string> = {
  critica: colors.danger,
  alta: colors.warning,
  normal: colors.cyan,
  baja: colors.textDim,
};

function pasaFiltro(t: Tarea, f: Filtro): boolean {
  if (f === 'todas') return true;
  if (f === 'completadas') return t.estado === 'completada' || t.estado === 'cancelada';
  return t.estado === 'pendiente' || t.estado === 'en_progreso' || t.estado === 'bloqueada';
}

export default function TareasScreen({navigation}: TareasProps) {
  const [filtro, setFiltro] = useState<Filtro>('activas');
  const [items, setItems] = useState<Tarea[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nuevoTitulo, setNuevoTitulo] = useState('');
  const [creando, setCreando] = useState(false);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setItems(await listarTareas());
    } catch {
      setError('No se pudo consultar las tareas. Revisa la conexión.');
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

  const onCrear = useCallback(async () => {
    if (!nuevoTitulo.trim()) return;
    setCreando(true);
    try {
      const id = await crearTarea(nuevoTitulo.trim());
      if (id) {
        setNuevoTitulo('');
        await cargar();
      }
    } finally {
      setCreando(false);
    }
  }, [nuevoTitulo, cargar]);

  const onCompletar = useCallback(
    async (t: Tarea) => {
      const anterior = items;
      setItems(prev => prev.map(x => (x.id === t.id ? {...x, estado: 'completada'} : x)));
      const ok = await cambiarEstadoTarea(t.id, 'completada');
      if (!ok) {
        setItems(anterior);
      }
    },
    [items],
  );

  const visibles = items.filter(t => pasaFiltro(t, filtro));

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Tareas</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.addRow}>
        <TextInput
          style={styles.input}
          placeholder="Nueva tarea…"
          placeholderTextColor={colors.textDim}
          value={nuevoTitulo}
          onChangeText={setNuevoTitulo}
          onSubmitEditing={onCrear}
        />
        <TouchableOpacity
          style={[styles.addBtn, creando && styles.buttonDisabled]}
          onPress={onCrear}
          disabled={creando}>
          {creando ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.addBtnText}>Añadir</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={styles.tabs}>
        {(['activas', 'todas', 'completadas'] as Filtro[]).map(f => (
          <TouchableOpacity
            key={f}
            style={[styles.tab, filtro === f && styles.tabActive]}
            onPress={() => setFiltro(f)}>
            <Text style={[styles.tabText, filtro === f && styles.tabTextActive]}>
              {f === 'activas' ? 'Activas' : f === 'todas' ? 'Todas' : 'Completadas'}
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
          data={visibles}
          keyExtractor={item => String(item.id)}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refrescando} onRefresh={onRefresh} tintColor={colors.cyan} />
          }
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.hint}>Nada por aquí.</Text>
            </View>
          }
          renderItem={({item}) => {
            const hecha = item.estado === 'completada' || item.estado === 'cancelada';
            return (
              <View style={styles.card}>
                <TouchableOpacity
                  style={[styles.check, hecha && styles.checkDone]}
                  disabled={hecha}
                  onPress={() => onCompletar(item)}>
                  {hecha ? <Text style={styles.checkMark}>✓</Text> : null}
                </TouchableOpacity>
                <View style={styles.cardBody}>
                  <Text style={[styles.tituloItem, hecha && styles.tituloHecho]} numberOfLines={2}>
                    {item.titulo}
                  </Text>
                  <View style={styles.metaRow}>
                    <View
                      style={[
                        styles.badge,
                        {backgroundColor: COLOR_PRIORIDAD[item.prioridad] ?? colors.textDim},
                      ]}>
                      <Text style={styles.badgeText}>{item.prioridad}</Text>
                    </View>
                    <Text style={styles.estado}>{item.estado}</Text>
                  </View>
                </View>
              </View>
            );
          }}
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
  addRow: {flexDirection: 'row', paddingHorizontal: 16, marginBottom: 8, gap: 8},
  input: {
    flex: 1,
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
  },
  addBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  buttonDisabled: {opacity: 0.6},
  addBtnText: {color: colors.bg, fontWeight: '800'},
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
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    gap: 12,
  },
  check: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.cyan,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  checkDone: {backgroundColor: colors.ok, borderColor: colors.ok},
  checkMark: {color: colors.bg, fontWeight: '900', fontSize: 13},
  cardBody: {flex: 1},
  tituloItem: {color: colors.text, fontWeight: '700', fontSize: 15},
  tituloHecho: {color: colors.textDim, textDecorationLine: 'line-through'},
  metaRow: {flexDirection: 'row', alignItems: 'center', marginTop: 8, gap: 8},
  badge: {borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3},
  badgeText: {color: colors.bg, fontSize: 11, fontWeight: '800'},
  estado: {color: colors.textDim, fontSize: 12},
});
