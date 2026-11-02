/**
 * SAT (capacidad "sat"). Rediseño móvil · Grupo B, módulo 4: fotografiar la intervención técnica ES el
 * trabajo físico — un ticket puede llevar varias visitas antes de resolverse, cada una con su propia
 * foto de evidencia. Sin firma (ver `api/sat.ts`): no hay hoy ningún momento de conformidad de cliente
 * en el modelo de SAT.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import CameraScanner from '@/components/CameraScanner';
import {
  iniciarTicket,
  listarIntervenciones,
  listarTickets,
  registrarIntervencion,
  resolverTicket,
  type Intervencion,
  type Ticket,
} from '@/api/sat';
import {colors} from '@/theme/colors';
import type {SATProps} from '@/navigation/types';

const TIPOS: {key: 'visita' | 'taller' | 'remota' | 'telefonica'; label: string}[] = [
  {key: 'visita', label: 'Visita'},
  {key: 'taller', label: 'Taller'},
  {key: 'remota', label: 'Remota'},
  {key: 'telefonica', label: 'Telefónica'},
];

export default function SATScreen({navigation}: SATProps) {
  const {t} = useTranslation();
  const [cargando, setCargando] = useState(true);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [intervenciones, setIntervenciones] = useState<Intervencion[]>([]);
  const [registrando, setRegistrando] = useState(false);
  const [tipo, setTipo] = useState<'visita' | 'taller' | 'remota' | 'telefonica'>('visita');
  const [descripcion, setDescripcion] = useState('');
  const [horas, setHoras] = useState('1');
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const cargarTickets = useCallback(async () => {
    setCargando(true);
    try {
      setTickets(await listarTickets());
    } catch {
      setTickets([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarTickets();
  }, [cargarTickets]);

  const abrirTicket = useCallback(async (tk: Ticket) => {
    setTicket(tk);
    setRegistrando(false);
    setAviso(null);
    setIntervenciones(await listarIntervenciones(tk.id));
  }, []);

  const iniciar = useCallback(async () => {
    if (!ticket) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await iniciarTicket(ticket.id);
      if (r.ok) {
        const actualizado = {...ticket, estado: r.estado};
        setTicket(actualizado);
        setTickets(prev => prev.map(x => (x.id === ticket.id ? actualizado : x)));
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('sat.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [ticket, t]);

  const reiniciarFormularioIntervencion = useCallback(() => {
    setTipo('visita');
    setDescripcion('');
    setHoras('1');
    setFotoUri(null);
    setRegistrando(false);
  }, []);

  const enviarIntervencion = useCallback(async () => {
    if (!ticket) return;
    if (!fotoUri) {
      setAviso({ok: false, texto: t('sat.haz_foto', 'Haz una foto de la intervención antes de registrarla.')});
      return;
    }
    const h = Number(horas);
    if (!Number.isFinite(h) || h < 0) {
      setAviso({ok: false, texto: t('sat.horas_invalidas', 'Las horas deben ser un número válido.')});
      return;
    }
    setProcesando(true);
    setAviso(null);
    try {
      const r = await registrarIntervencion(ticket.id, {
        tipo,
        descripcion: descripcion.trim() || undefined,
        horas: h,
        fotoUri,
      });
      if (r.ok) {
        setAviso({ok: true, texto: t('sat.registrada_ok', 'Intervención registrada con la foto de evidencia.')});
        reiniciarFormularioIntervencion();
        setIntervenciones(await listarIntervenciones(ticket.id));
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('sat.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [ticket, tipo, descripcion, horas, fotoUri, reiniciarFormularioIntervencion, t]);

  const resolver = useCallback(async () => {
    if (!ticket) return;
    setProcesando(true);
    setAviso(null);
    try {
      const r = await resolverTicket(ticket.id);
      if (r.ok) {
        setAviso({ok: true, texto: t('sat.resuelto_ok', 'Ticket {{c}} resuelto.', {c: ticket.codigo})});
        setTickets(prev => prev.filter(x => x.id !== ticket.id));
        setTicket(null);
        setIntervenciones([]);
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('sat.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setProcesando(false);
    }
  }, [ticket, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => (ticket ? setTicket(null) : navigation.goBack())}>
          <Text style={styles.back}>‹ {ticket ? t('sat.tickets_lbl', 'Tickets') : t('common.volver_sin_flecha', 'Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>SAT</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('sat.foto_intervencion', 'Foto de la intervención')}</Text>
            <View style={{width: 90}} />
          </View>
          <View style={{flex: 1, margin: 16}}>
            <CameraScanner
              active={camaraAbierta}
              modo="foto"
              onCaptured={uri => {
                setFotoUri(uri);
                setCamaraAbierta(false);
              }}
            />
          </View>
        </SafeAreaView>
      </Modal>

      {!ticket ? (
        cargando ? (
          <ActivityIndicator color={colors.cyan} size="large" style={{marginTop: 40}} />
        ) : (
          <FlatList
            data={tickets}
            keyExtractor={item => String(item.id)}
            contentContainerStyle={styles.form}
            ListEmptyComponent={<Text style={styles.hint}>{t('sat.sin_tickets', 'Sin tickets asignados pendientes.')}</Text>}
            renderItem={({item}) => (
              <TouchableOpacity style={styles.card} onPress={() => abrirTicket(item)}>
                <Text style={styles.cardTitle}>{item.codigo} · {item.asunto}</Text>
                <Text style={styles.cardDetail}>
                  {t('sat.prioridad_estado', 'prioridad {{p}} · estado {{e}}', {p: item.prioridad, e: item.estado})}
                </Text>
              </TouchableOpacity>
            )}
          />
        )
      ) : (
        <ScrollView contentContainerStyle={styles.form}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{ticket.codigo} · {ticket.asunto}</Text>
            <Text style={styles.cardDetail}>{ticket.descripcion || t('sat.sin_descripcion', '(sin descripción)')}</Text>
            <Text style={styles.cardDetail}>
              {t('sat.prioridad_estado', 'prioridad {{p}} · estado {{e}}', {p: ticket.prioridad, e: ticket.estado})}
            </Text>
            {ticket.tecnico != null ? (
              <Text style={styles.cardDetail}>{t('sat.tecnico_lbl', 'Técnico: #{{n}}', {n: ticket.tecnico})}</Text>
            ) : null}
          </View>

          {ticket.estado !== 'en_proceso' ? (
            <TouchableOpacity
              style={[styles.button, procesando && styles.buttonDisabled]}
              onPress={iniciar}
              disabled={procesando}>
              {procesando ? (
                <ActivityIndicator color={colors.bg} />
              ) : (
                <Text style={styles.buttonText}>{t('sat.iniciar_btn', 'Iniciar')}</Text>
              )}
            </TouchableOpacity>
          ) : null}

          <Text style={styles.sectionTitle}>{t('sat.intervenciones_h2', 'Intervenciones')}</Text>
          {intervenciones.length === 0 ? (
            <Text style={styles.hint}>{t('sat.sin_intervenciones', 'Sin intervenciones registradas todavía.')}</Text>
          ) : (
            intervenciones.map(iv => (
              <View key={iv.id} style={styles.repuestoRow}>
                <Text style={styles.cardDetail}>
                  {iv.id_documento_foto ? '📷 ' : ''}
                  {iv.fecha} · {t(`sat.tipo_${iv.tipo}`, iv.tipo)} · {iv.horas}h{iv.descripcion ? ` · ${iv.descripcion}` : ''}
                </Text>
              </View>
            ))
          )}

          {!registrando ? (
            <TouchableOpacity style={styles.scanBtn} onPress={() => setRegistrando(true)}>
              <Text style={styles.scanBtnText}>+ {t('sat.registrar_intervencion_btn', 'Registrar intervención')}</Text>
            </TouchableOpacity>
          ) : (
            <View>
              <Text style={styles.sectionTitle}>{t('sat.tipo_h2', 'Tipo')}</Text>
              <View style={styles.chipsRow}>
                {TIPOS.map(tp => (
                  <TouchableOpacity
                    key={tp.key}
                    style={[styles.chip, tipo === tp.key && styles.chipActivo]}
                    onPress={() => setTipo(tp.key)}>
                    <Text style={[styles.chipTexto, tipo === tp.key && styles.chipTextoActivo]}>
                      {t(`sat.tipo_${tp.key}`, tp.label)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.sectionTitle}>{t('sat.descripcion_opc_h2', 'Descripción (opcional)')}</Text>
              <TextInput
                style={[styles.input, {minHeight: 60}]}
                placeholder={t('sat.descripcion_ph', 'Descripción')}
                placeholderTextColor={colors.textDim}
                multiline
                value={descripcion}
                onChangeText={setDescripcion}
              />

              <Text style={styles.sectionTitle}>{t('sat.horas_h2', 'Horas')}</Text>
              <TextInput
                style={[styles.input, {width: 100}]}
                placeholder={t('sat.horas_ph', 'Horas')}
                placeholderTextColor={colors.textDim}
                keyboardType="numeric"
                value={horas}
                onChangeText={setHoras}
              />

              <Text style={styles.sectionTitle}>{t('sat.foto_intervencion', 'Foto de la intervención')}</Text>
              {fotoUri ? (
                <View style={styles.fotoPreviewWrap}>
                  <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
                  <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
                    <Text style={styles.buttonText}>{t('sat.repetir_foto_btn', 'Repetir foto')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
                  <Text style={styles.scanBtnText}>{t('sat.hacer_foto_btn', 'Hacer foto')}</Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                style={[
                  styles.button,
                  styles.buttonFull,
                  (!fotoUri || procesando) && styles.buttonDisabled,
                ]}
                onPress={enviarIntervencion}
                disabled={!fotoUri || procesando}>
                {procesando ? (
                  <ActivityIndicator color={colors.bg} />
                ) : (
                  <Text style={styles.buttonText}>{t('sat.guardar_intervencion_btn', 'Guardar intervención')}</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity onPress={reiniciarFormularioIntervencion}>
                <Text style={styles.link}>{t('common.cancelar', 'Cancelar')}</Text>
              </TouchableOpacity>
            </View>
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

          <TouchableOpacity
            style={[styles.button, styles.buttonFull, procesando && styles.buttonDisabled]}
            onPress={resolver}
            disabled={procesando}>
            <Text style={styles.buttonText}>{t('sat.marcar_resuelto_btn', 'Marcar resuelto')}</Text>
          </TouchableOpacity>
        </ScrollView>
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
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 90},
  title: {color: colors.text, fontSize: 18, fontWeight: '800'},
  form: {padding: 16, paddingBottom: 32},
  sectionTitle: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 14, marginBottom: 8},
  hint: {color: colors.textDim, textAlign: 'center', fontSize: 14, marginTop: 20},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    marginBottom: 8,
  },
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 14},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 15},
  cardDetail: {color: colors.textDim, marginTop: 4, fontSize: 12},
  link: {color: colors.cyan, fontWeight: '700', fontSize: 12, marginTop: 8, textAlign: 'center'},
  repuestoRow: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 6,
  },
  chipsRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8},
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActivo: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  chipTexto: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  chipTextoActivo: {color: colors.bg},
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonFull: {marginTop: 12},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 8, fontSize: 12},
  error: {color: colors.danger, marginTop: 8, fontSize: 12},
});
