/**
 * Agenda del mes en curso (capacidad "agenda" -> GET/POST /api/v1/agenda).
 * Solo eventos creados por el usuario o en los que participa (lo acota el backend).
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
import {crearEvento, listarAgenda, type EventoAgenda} from '@/api/agenda';
import {colors} from '@/theme/colors';
import type {AgendaProps} from '@/navigation/types';

const ETIQUETA_TIPO: Record<string, string> = {
  evento: 'Evento',
  reunion: 'Reunión',
  cita: 'Cita',
  recordatorio: 'Recordatorio',
  auditoria: 'Auditoría',
  revision: 'Revisión',
};

export default function AgendaScreen({navigation}: AgendaProps) {
  const [items, setItems] = useState<EventoAgenda[]>([]);
  const [loading, setLoading] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mostrarForm, setMostrarForm] = useState(false);
  const [titulo, setTitulo] = useState('');
  const [inicio, setInicio] = useState('');
  const [creando, setCreando] = useState(false);
  const [avisoForm, setAvisoForm] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setItems(await listarAgenda());
    } catch {
      setError('No se pudo consultar la agenda. Revisa la conexión.');
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
    if (!titulo.trim() || !inicio.trim()) {
      setAvisoForm('Título y fecha de inicio son obligatorios.');
      return;
    }
    setCreando(true);
    setAvisoForm(null);
    try {
      const id = await crearEvento({titulo: titulo.trim(), inicio: inicio.trim()});
      if (id) {
        setTitulo('');
        setInicio('');
        setMostrarForm(false);
        await cargar();
      } else {
        setAvisoForm('No se pudo crear el evento. Revisa el formato de fecha (AAAA-MM-DD HH:MM).');
      }
    } catch {
      setAvisoForm('No hay conexión con el servidor.');
    } finally {
      setCreando(false);
    }
  }, [titulo, inicio, cargar]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.root}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.back}>‹ Volver</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Agenda</Text>
          <TouchableOpacity onPress={() => setMostrarForm(v => !v)}>
            <Text style={styles.addLink}>{mostrarForm ? 'Cancelar' : '+ Nuevo'}</Text>
          </TouchableOpacity>
        </View>

        {mostrarForm ? (
          <View style={styles.form}>
            <TextInput
              style={styles.input}
              placeholder="Título"
              placeholderTextColor={colors.textDim}
              value={titulo}
              onChangeText={setTitulo}
            />
            <TextInput
              style={styles.input}
              placeholder="Inicio (AAAA-MM-DD HH:MM)"
              placeholderTextColor={colors.textDim}
              autoCapitalize="none"
              value={inicio}
              onChangeText={setInicio}
            />
            {avisoForm ? <Text style={styles.error}>{avisoForm}</Text> : null}
            <TouchableOpacity
              style={[styles.button, creando && styles.buttonDisabled]}
              onPress={onCrear}
              disabled={creando}>
              {creando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>Crear evento</Text>
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
                <Text style={styles.hint}>Sin eventos este mes.</Text>
              </View>
            }
            renderItem={({item}) => (
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.tituloItem} numberOfLines={1}>
                    {item.titulo}
                  </Text>
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{ETIQUETA_TIPO[item.tipo] ?? item.tipo}</Text>
                  </View>
                </View>
                <Text style={styles.fecha}>
                  {item.inicio}
                  {item.fin ? ` – ${item.fin}` : ''}
                </Text>
                {item.descripcion ? (
                  <Text style={styles.descripcion} numberOfLines={2}>
                    {item.descripcion}
                  </Text>
                ) : null}
              </View>
            )}
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
  badge: {
    backgroundColor: colors.panelAlt,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: {color: colors.cyan, fontSize: 11, fontWeight: '700'},
  fecha: {color: colors.textDim, marginTop: 4, fontSize: 12},
  descripcion: {color: colors.textDim, marginTop: 6},
});
