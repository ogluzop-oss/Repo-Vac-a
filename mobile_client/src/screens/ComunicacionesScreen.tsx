/**
 * Comunicaciones corporativas (capacidad "ccp" -> GET/POST /api/v1/communications).
 *
 * Envía una comunicación puntual (resuelta por el Corporate Identity Resolver en el backend) y
 * muestra el historial unificado por Communication ID. El envío exige el permiso
 * `comunicaciones.enviar`; si el usuario no lo tiene, el backend responde 403 y se muestra tal cual.
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
import {enviar, historial, type ComunicacionHistorial} from '@/api/communications';
import {colors} from '@/theme/colors';
import type {ComunicacionesProps} from '@/navigation/types';

const COLOR_ESTADO: Record<string, string> = {
  enviado: colors.ok,
  entregado: colors.ok,
  fallido: colors.danger,
  preparada: colors.warning,
  no_operativo: colors.textDim,
};

export default function ComunicacionesScreen({navigation}: ComunicacionesProps) {
  const [items, setItems] = useState<ComunicacionHistorial[]>([]);
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [errorLista, setErrorLista] = useState<string | null>(null);

  const [destinatario, setDestinatario] = useState('');
  const [asunto, setAsunto] = useState('');
  const [cuerpo, setCuerpo] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [avisoEnvio, setAvisoEnvio] = useState<{ok: boolean; texto: string} | null>(null);

  const cargar = useCallback(async () => {
    setErrorLista(null);
    try {
      setItems(await historial());
    } catch {
      setErrorLista('No se pudo cargar el historial. Revisa la conexión.');
    }
  }, []);

  useEffect(() => {
    (async () => {
      setCargando(true);
      await cargar();
      setCargando(false);
    })();
  }, [cargar]);

  const onRefresh = useCallback(async () => {
    setRefrescando(true);
    await cargar();
    setRefrescando(false);
  }, [cargar]);

  const onEnviar = useCallback(async () => {
    if (!destinatario.trim() || !asunto.trim()) {
      setAvisoEnvio({ok: false, texto: 'Destinatario y asunto son obligatorios.'});
      return;
    }
    setEnviando(true);
    setAvisoEnvio(null);
    try {
      const r = await enviar({
        destinatario: destinatario.trim(),
        asunto: asunto.trim(),
        cuerpo: cuerpo.trim(),
        contexto: 'mobile',
      });
      if (r.kind === 'ok') {
        setAvisoEnvio({ok: true, texto: `Enviado (${r.data.com_id ?? r.data.estado}).`});
        setDestinatario('');
        setAsunto('');
        setCuerpo('');
        await cargar();
      } else {
        setAvisoEnvio({
          ok: false,
          texto: r.status === 403 ? 'No tienes permiso para enviar comunicaciones.' : r.mensaje,
        });
      }
    } catch {
      setAvisoEnvio({ok: false, texto: 'No hay conexión con el servidor.'});
    } finally {
      setEnviando(false);
    }
  }, [destinatario, asunto, cuerpo, cargar]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.root}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.back}>‹ Volver</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Comunicaciones</Text>
          <View style={{width: 60}} />
        </View>

        <View style={styles.form}>
          <TextInput
            style={styles.input}
            placeholder="Destinatario (correo)"
            placeholderTextColor={colors.textDim}
            autoCapitalize="none"
            keyboardType="email-address"
            value={destinatario}
            onChangeText={setDestinatario}
          />
          <TextInput
            style={styles.input}
            placeholder="Asunto"
            placeholderTextColor={colors.textDim}
            value={asunto}
            onChangeText={setAsunto}
          />
          <TextInput
            style={[styles.input, styles.textarea]}
            placeholder="Mensaje"
            placeholderTextColor={colors.textDim}
            value={cuerpo}
            onChangeText={setCuerpo}
            multiline
          />
          {avisoEnvio ? (
            <Text style={avisoEnvio.ok ? styles.ok : styles.error}>{avisoEnvio.texto}</Text>
          ) : null}
          <TouchableOpacity
            style={[styles.button, enviando && styles.buttonDisabled]}
            onPress={onEnviar}
            disabled={enviando}>
            {enviando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>Enviar</Text>
            )}
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionTitle}>Historial</Text>

        {cargando ? (
          <View style={styles.centered}>
            <ActivityIndicator color={colors.cyan} />
          </View>
        ) : errorLista ? (
          <View style={styles.centered}>
            <Text style={styles.error}>{errorLista}</Text>
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
                <Text style={styles.hint}>Todavía no hay comunicaciones registradas.</Text>
              </View>
            }
            renderItem={({item}) => (
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.asunto} numberOfLines={1}>
                    {item.asunto || '(sin asunto)'}
                  </Text>
                  <View
                    style={[
                      styles.badge,
                      {backgroundColor: COLOR_ESTADO[item.estado] ?? colors.textDim},
                    ]}>
                    <Text style={styles.badgeText}>{item.estado}</Text>
                  </View>
                </View>
                <Text style={styles.detalle} numberOfLines={1}>
                  {item.destinatario} · {item.canal}
                </Text>
                <Text style={styles.fecha}>{item.creado}</Text>
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
  textarea: {minHeight: 70, textAlignVertical: 'top'},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 2,
  },
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginBottom: 8, fontSize: 12},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12, textAlign: 'center'},
  sectionTitle: {color: colors.textDim, fontWeight: '700', marginHorizontal: 16, marginBottom: 4},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
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
  asunto: {color: colors.text, fontWeight: '800', fontSize: 15, flex: 1, marginRight: 8},
  badge: {borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3},
  badgeText: {color: colors.bg, fontSize: 11, fontWeight: '800'},
  detalle: {color: colors.textDim, marginTop: 4},
  fecha: {color: colors.textDim, marginTop: 2, fontSize: 11},
});
