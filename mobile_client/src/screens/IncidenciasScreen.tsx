/**
 * Incidencias operativas de tienda/almacén (capacidad "incidencias" -> /api/v1/incidents).
 * Solo las mías: reportadas por mí o asignadas a mí (lo acota el backend). Distinto de los
 * incidentes de SEGURIDAD, que no se exponen en el móvil.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {
  cambiarEstadoIncidencia,
  listarIncidencias,
  reportarIncidencia,
  TIPOS_INCIDENCIA,
  type Incidencia,
  type PrioridadIncidencia,
} from '@/api/incidents';
import {colors} from '@/theme/colors';
import type {IncidenciasProps} from '@/navigation/types';

const ETIQUETA_TIPO: Record<string, string> = {
  limpieza: 'Limpieza',
  rotura: 'Rotura',
  equipamiento: 'Equipamiento',
  seguridad_fisica: 'Seguridad física',
  cliente: 'Cliente',
  otro: 'Otro',
};

const PRIORIDADES: PrioridadIncidencia[] = ['baja', 'normal', 'alta', 'critica'];

const COLOR_ESTADO: Record<string, string> = {
  abierta: colors.warning,
  en_curso: colors.cyan,
  resuelta: colors.ok,
  cancelada: colors.textDim,
};

export default function IncidenciasScreen({navigation}: IncidenciasProps) {
  const [items, setItems] = useState<Incidencia[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mostrarForm, setMostrarForm] = useState(false);
  const [tipo, setTipo] = useState<string>('otro');
  const [prioridad, setPrioridad] = useState<PrioridadIncidencia>('normal');
  const [titulo, setTitulo] = useState('');
  const [ubicacion, setUbicacion] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [avisoForm, setAvisoForm] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setItems(await listarIncidencias());
    } catch {
      setError('No se pudo consultar las incidencias. Revisa la conexión.');
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

  const onReportar = useCallback(async () => {
    if (!titulo.trim()) {
      setAvisoForm('Describe brevemente la incidencia.');
      return;
    }
    setEnviando(true);
    setAvisoForm(null);
    try {
      const id = await reportarIncidencia({
        tipo,
        titulo: titulo.trim(),
        prioridad,
        ubicacion: ubicacion.trim() || undefined,
      });
      if (id) {
        setTitulo('');
        setUbicacion('');
        setPrioridad('normal');
        setMostrarForm(false);
        await cargar();
      } else {
        setAvisoForm('No se pudo reportar la incidencia.');
      }
    } catch {
      setAvisoForm('No hay conexión con el servidor.');
    } finally {
      setEnviando(false);
    }
  }, [tipo, titulo, prioridad, ubicacion, cargar]);

  const onResolver = useCallback(
    async (item: Incidencia) => {
      const anterior = items;
      setItems(prev => prev.map(x => (x.id === item.id ? {...x, estado: 'resuelta'} : x)));
      const ok = await cambiarEstadoIncidencia(item.id, 'resuelta');
      if (!ok) {
        setItems(anterior);
      }
    },
    [items],
  );

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.root}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.back}>‹ Volver</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Incidencias</Text>
          <TouchableOpacity onPress={() => setMostrarForm(v => !v)}>
            <Text style={styles.addLink}>{mostrarForm ? 'Cancelar' : '+ Reportar'}</Text>
          </TouchableOpacity>
        </View>

        {mostrarForm ? (
          <View style={styles.form}>
            <Text style={styles.label}>Tipo</Text>
            <View style={styles.chipRow}>
              {TIPOS_INCIDENCIA.map(t => (
                <TouchableOpacity
                  key={t}
                  style={[styles.chip, tipo === t && styles.chipActive]}
                  onPress={() => setTipo(t)}>
                  <Text style={[styles.chipText, tipo === t && styles.chipTextActive]}>
                    {ETIQUETA_TIPO[t] ?? t}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Prioridad</Text>
            <View style={styles.chipRow}>
              {PRIORIDADES.map(p => (
                <TouchableOpacity
                  key={p}
                  style={[styles.chip, prioridad === p && styles.chipActive]}
                  onPress={() => setPrioridad(p)}>
                  <Text style={[styles.chipText, prioridad === p && styles.chipTextActive]}>
                    {p}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput
              style={styles.input}
              placeholder="¿Qué ha pasado?"
              placeholderTextColor={colors.textDim}
              value={titulo}
              onChangeText={setTitulo}
            />
            <TextInput
              style={styles.input}
              placeholder="Ubicación (pasillo, sección…)"
              placeholderTextColor={colors.textDim}
              value={ubicacion}
              onChangeText={setUbicacion}
            />
            {avisoForm ? <Text style={styles.error}>{avisoForm}</Text> : null}
            <TouchableOpacity
              style={[styles.button, enviando && styles.buttonDisabled]}
              onPress={onReportar}
              disabled={enviando}>
              {enviando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>Reportar</Text>
              )}
            </TouchableOpacity>
          </View>
        ) : null}

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
                <Text style={styles.hint}>No has reportado ninguna incidencia.</Text>
              </View>
            }
            renderItem={({item}) => {
              const activa = item.estado === 'abierta' || item.estado === 'en_curso';
              return (
                <View style={styles.card}>
                  <View style={styles.cardHeader}>
                    <Text style={styles.tituloItem} numberOfLines={2}>
                      {item.titulo}
                    </Text>
                    <View style={[styles.badge, {backgroundColor: COLOR_ESTADO[item.estado]}]}>
                      <Text style={styles.badgeText}>{item.estado}</Text>
                    </View>
                  </View>
                  <Text style={styles.detalle}>
                    {ETIQUETA_TIPO[item.tipo] ?? item.tipo}
                    {item.ubicacion ? ` · ${item.ubicacion}` : ''} · {item.prioridad}
                  </Text>
                  <Text style={styles.fecha}>{item.fecha_creacion}</Text>
                  {activa ? (
                    <TouchableOpacity style={styles.resolverBtn} onPress={() => onResolver(item)}>
                      <Text style={styles.resolverBtnText}>Marcar resuelta</Text>
                    </TouchableOpacity>
                  ) : item.resolucion ? (
                    <Text style={styles.resolucion} numberOfLines={2}>
                      ✓ {item.resolucion}
                    </Text>
                  ) : null}
                </View>
              );
            }}
          />
        )}
      </KeyboardAvoidingView>
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
  addLink: {color: colors.cyan, fontSize: 14, fontWeight: '700'},
  form: {
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 14,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
  },
  label: {color: colors.textDim, fontWeight: '700', fontSize: 12, marginBottom: 6},
  chipRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10},
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.bg,
  },
  chipActive: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  chipText: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  chipTextActive: {color: colors.bg},
  input: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 8,
    fontSize: 15,
  },
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 2,
  },
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12, textAlign: 'center'},
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
  tituloItem: {color: colors.text, fontWeight: '800', fontSize: 15, flex: 1, marginRight: 8},
  badge: {borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3},
  badgeText: {color: colors.bg, fontSize: 11, fontWeight: '800'},
  detalle: {color: colors.textDim, marginTop: 4, fontSize: 12},
  fecha: {color: colors.textDim, marginTop: 2, fontSize: 11},
  resolverBtn: {
    marginTop: 10,
    alignSelf: 'flex-start',
    backgroundColor: colors.panelAlt,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  resolverBtnText: {color: colors.ok, fontWeight: '700', fontSize: 12},
  resolucion: {color: colors.ok, marginTop: 8, fontSize: 12},
});
