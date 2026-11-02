/**
 * Obrador (capacidad "obrador", edición Bakery). Rediseño móvil Grupo B, módulo 6: fotografiar el lote
 * terminado ES el trabajo físico — mismo criterio que Mermas/Transporte. Formulario de captura-y-envío,
 * no lista→detalle (a diferencia de GMAO/SAT/Transporte): un parte de obrador no existe hasta que se
 * envía, no hay nada preexistente que abrir.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
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
import {buscarArticulos, type Articulo} from '@/api/articles';
import {listarPartes, registrarParte, type Parte} from '@/api/obrador';
import {colors} from '@/theme/colors';
import type {ObradorProps} from '@/navigation/types';

interface LineaLocal {
  codigo: string;
  nombre: string;
  cantidad: number;
}

export default function ObradorScreen({navigation}: ObradorProps) {
  const {t} = useTranslation();
  const [turno, setTurno] = useState('');
  const [responsable, setResponsable] = useState('');
  const [q, setQ] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [articulo, setArticulo] = useState<Articulo | null>(null);
  const [cantidadLinea, setCantidadLinea] = useState('1');
  const [items, setItems] = useState<LineaLocal[]>([]);
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const [recientes, setRecientes] = useState<Parte[]>([]);
  const [cargandoLista, setCargandoLista] = useState(true);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cargarRecientes = useCallback(async () => {
    setCargandoLista(true);
    try {
      setRecientes(await listarPartes(15));
    } catch {
      setRecientes([]);
    } finally {
      setCargandoLista(false);
    }
  }, []);

  useEffect(() => {
    cargarRecientes();
  }, [cargarRecientes]);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (!q.trim() || articulo) {
      setSugerencias([]);
      return;
    }
    debounce.current = setTimeout(async () => {
      try {
        setSugerencias(await buscarArticulos(q.trim()));
      } catch {
        setSugerencias([]);
      }
    }, 300);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [q, articulo]);

  const elegir = useCallback((a: Articulo) => {
    setArticulo(a);
    setQ(`${a.codigo} – ${a.nombre}`);
    setSugerencias([]);
  }, []);

  const anadirLinea = useCallback(() => {
    if (!articulo) {
      setAviso({ok: false, texto: t('obrador.busca_articulo', 'Busca primero el artículo producido.')});
      return;
    }
    const cant = Number(cantidadLinea);
    if (!Number.isFinite(cant) || cant <= 0) {
      setAviso({ok: false, texto: t('obrador.cantidad_invalida', 'La cantidad debe ser un número mayor que 0.')});
      return;
    }
    setItems(prev => [...prev, {codigo: articulo.codigo, nombre: articulo.nombre, cantidad: cant}]);
    setQ('');
    setArticulo(null);
    setCantidadLinea('1');
    setAviso(null);
  }, [articulo, cantidadLinea, t]);

  const quitarLinea = useCallback((idx: number) => {
    setItems(prev => prev.filter((_, i) => i !== idx));
  }, []);

  const reiniciarFormulario = useCallback(() => {
    setTurno('');
    setResponsable('');
    setQ('');
    setArticulo(null);
    setCantidadLinea('1');
    setItems([]);
    setFotoUri(null);
  }, []);

  const enviar = useCallback(async () => {
    if (items.length === 0) {
      setAviso({ok: false, texto: t('obrador.anade_linea', 'Añade al menos una línea de producción.')});
      return;
    }
    if (!fotoUri) {
      setAviso({ok: false, texto: t('obrador.haz_foto', 'Haz una foto del lote terminado antes de registrarlo.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await registrarParte({
        turno: turno.trim() || undefined,
        responsable: responsable.trim() || undefined,
        items: items.map(i => ({codigo: i.codigo, cantidad: i.cantidad})),
        fotoUri,
      });
      if (r.ok) {
        setAviso({ok: true, texto: t('obrador.registrado_ok', 'Parte de producción registrado con la foto del lote.')});
        reiniciarFormulario();
        await cargarRecientes();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('obrador.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [items, fotoUri, turno, responsable, reiniciarFormulario, cargarRecientes, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('obrador.titulo', 'Obrador')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('obrador.foto_lote', 'Foto del lote')}</Text>
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

      <ScrollView contentContainerStyle={styles.form}>
        <Text style={styles.sectionTitle}>{t('obrador.turno_responsable_h2', 'Turno / Responsable (opcional)')}</Text>
        <View style={styles.row}>
          <TextInput
            style={[styles.input, {flex: 1}]}
            placeholder={t('obrador.turno_ph', 'Turno')}
            placeholderTextColor={colors.textDim}
            value={turno}
            onChangeText={setTurno}
          />
          <TextInput
            style={[styles.input, {flex: 1}]}
            placeholder={t('obrador.responsable_ph', 'Responsable')}
            placeholderTextColor={colors.textDim}
            value={responsable}
            onChangeText={setResponsable}
          />
        </View>

        <Text style={styles.sectionTitle}>{t('obrador.anadir_linea_h2', 'Añadir línea producida')}</Text>
        <TextInput
          style={styles.input}
          placeholder={t('obrador.buscar_articulo_ph', 'Buscar artículo (código o nombre)')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={q}
          onChangeText={texto => {
            setQ(texto);
            setArticulo(null);
          }}
        />
        {sugerencias.length > 0 ? (
          <View style={styles.sugerencias}>
            {sugerencias.map(a => (
              <TouchableOpacity key={a.codigo} style={styles.sugerenciaItem} onPress={() => elegir(a)}>
                <Text style={styles.sugerenciaNombre} numberOfLines={1}>{a.nombre}</Text>
                <Text style={styles.sugerenciaCodigo}>{a.codigo}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : null}
        <View style={styles.row}>
          <TextInput
            style={[styles.input, {width: 100}]}
            placeholder={t('obrador.cantidad_ph', 'Cantidad')}
            placeholderTextColor={colors.textDim}
            keyboardType="numeric"
            value={cantidadLinea}
            onChangeText={setCantidadLinea}
          />
          <TouchableOpacity style={styles.button} onPress={anadirLinea}>
            <Text style={styles.buttonText}>＋ {t('obrador.anadir_linea_btn', 'Añadir línea')}</Text>
          </TouchableOpacity>
        </View>

        {items.length > 0 ? (
          <>
            <Text style={styles.sectionTitle}>{t('obrador.lineas_parte_h2', 'Líneas de este parte')}</Text>
            {items.map((it, idx) => (
              <View key={`${it.codigo}-${idx}`} style={styles.lineaRow}>
                <Text style={styles.cardDetail} numberOfLines={1}>
                  {it.nombre} ({it.codigo}) × {it.cantidad}
                </Text>
                <TouchableOpacity onPress={() => quitarLinea(idx)}>
                  <Text style={styles.quitar}>{t('obrador.quitar_btn', 'Quitar')}</Text>
                </TouchableOpacity>
              </View>
            ))}
          </>
        ) : null}

        <Text style={styles.sectionTitle}>{t('obrador.foto_lote_terminado_h2', 'Foto del lote terminado')}</Text>
        {fotoUri ? (
          <View style={styles.fotoPreviewWrap}>
            <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
            <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
              <Text style={styles.buttonText}>{t('obrador.repetir_foto_btn', 'Repetir foto')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
            <Text style={styles.scanBtnText}>{t('obrador.hacer_foto_btn', 'Hacer foto')}</Text>
          </TouchableOpacity>
        )}

        {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

        <TouchableOpacity
          style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
          onPress={enviar}
          disabled={enviando}>
          {enviando ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.buttonText}>{t('obrador.registrar_produccion_btn', 'Registrar producción')}</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>{t('obrador.ultimos_partes_h2', 'Últimos partes')}</Text>
        {cargandoLista ? (
          <ActivityIndicator color={colors.cyan} />
        ) : (
          <FlatList
            data={recientes}
            keyExtractor={item => String(item.id)}
            scrollEnabled={false}
            ListEmptyComponent={<Text style={styles.hint}>{t('obrador.sin_partes', 'Sin partes registrados todavía.')}</Text>}
            renderItem={({item}) => (
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardTitle} numberOfLines={1}>
                    {item.fecha} {item.turno ? `· ${item.turno}` : ''}
                  </Text>
                  <Text style={styles.cardDetail}>{item.id_documento_foto ? '📷' : ''}</Text>
                </View>
                <Text style={styles.cardDetail}>{item.responsable || item.usuario || '—'}</Text>
              </View>
            )}
          />
        )}
      </ScrollView>
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
  hint: {color: colors.textDim, fontSize: 12},
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
  row: {flexDirection: 'row', gap: 8, alignItems: 'center'},
  sugerencias: {
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    marginTop: -4,
    marginBottom: 8,
    overflow: 'hidden',
  },
  sugerenciaItem: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  sugerenciaNombre: {color: colors.text, fontWeight: '700', fontSize: 13},
  sugerenciaCodigo: {color: colors.textDim, fontSize: 11, marginTop: 2},
  lineaRow: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  quitar: {color: colors.danger, fontWeight: '700', fontSize: 12},
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 14},
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonFull: {marginTop: 8, marginBottom: 8},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginBottom: 8, fontSize: 12},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 14, flex: 1, marginRight: 8},
  cardDetail: {color: colors.textDim, marginTop: 2, fontSize: 12},
});
