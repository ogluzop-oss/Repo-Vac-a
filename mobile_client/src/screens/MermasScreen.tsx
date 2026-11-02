/**
 * Mermas (capacidad "mermas" -> /api/v1/losses). Rediseño móvil Grupo B, módulo 1: fotografiar el
 * producto dañado/caducado ES el trabajo físico — a diferencia de la pantalla-formulario retirada en
 * el Grupo A (idéntica a lo que ya hace escritorio, sin foto), aquí la foto es obligatoria y es la
 * razón de que este módulo exista en el móvil.
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
import {imagenMermaSource, listarMermas, registrarMerma, type Merma} from '@/api/losses';
import {colors} from '@/theme/colors';
import type {MermasProps} from '@/navigation/types';

// Valores CANÓNICOS en español — se envían tal cual al backend (`db.mermas`, compartido con
// escritorio), nunca traducidos: solo la ETIQUETA visible usa `t(\`mermas.motivo_${slug}\`, m)`.
const MOTIVOS = ['Caducidad', 'Rotura', 'Robo', 'Muestra', 'Error de Inventario', 'Otro'];
const MOTIVO_SLUG: Record<string, string> = {
  Caducidad: 'caducidad',
  Rotura: 'rotura',
  Robo: 'robo',
  Muestra: 'muestra',
  'Error de Inventario': 'error_inventario',
  Otro: 'otro',
};

export default function MermasScreen({navigation}: MermasProps) {
  const {t} = useTranslation();
  const [q, setQ] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [articulo, setArticulo] = useState<Articulo | null>(null);
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [motivo, setMotivo] = useState(MOTIVOS[0] ?? 'Rotura');
  const [cantidad, setCantidad] = useState('1');
  const [origen, setOrigen] = useState<'lineal' | 'almacen'>('lineal');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const [recientes, setRecientes] = useState<Merma[]>([]);
  const [cargandoLista, setCargandoLista] = useState(true);
  const [fotoVista, setFotoVista] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cargarRecientes = useCallback(async () => {
    setCargandoLista(true);
    try {
      setRecientes(await listarMermas(15));
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

  const reiniciarFormulario = useCallback(() => {
    setQ('');
    setArticulo(null);
    setFotoUri(null);
    setMotivo(MOTIVOS[0] ?? 'Rotura');
    setCantidad('1');
    setOrigen('lineal');
  }, []);

  const enviar = useCallback(async () => {
    if (!articulo) {
      setAviso({ok: false, texto: t('mermas.busca_articulo', 'Busca primero el artículo.')});
      return;
    }
    if (!fotoUri) {
      setAviso({ok: false, texto: t('mermas.haz_foto', 'Haz una foto de la merma antes de registrarla.')});
      return;
    }
    const cant = Number(cantidad);
    if (!Number.isFinite(cant) || cant <= 0) {
      setAviso({ok: false, texto: t('mermas.cantidad_invalida', 'La cantidad debe ser un número mayor que 0.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await registrarMerma({codigo: articulo.codigo, cantidad: cant, motivo, origen, fotoUri});
      if (r.ok) {
        setAviso({ok: true, texto: t('mermas.registrada_ok', 'Merma registrada con la foto de evidencia.')});
        reiniciarFormulario();
        await cargarRecientes();
      } else {
        setAviso({ok: false, texto: r.error});
      }
    } catch {
      setAviso({ok: false, texto: t('mermas.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [articulo, fotoUri, cantidad, motivo, origen, reiniciarFormulario, cargarRecientes, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('mermas.titulo', 'Mermas')}</Text>
        <View style={{width: 90}} />
      </View>

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('mermas.foto_merma', 'Foto de la merma')}</Text>
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

      <Modal visible={!!fotoVista} transparent animationType="fade" onRequestClose={() => setFotoVista(null)}>
        <TouchableOpacity
          style={styles.fotoModalFondo}
          activeOpacity={1}
          onPress={() => setFotoVista(null)}>
          {fotoVista ? (
            <Image source={imagenMermaSource(fotoVista)} style={styles.fotoModalImagen} resizeMode="contain" />
          ) : null}
        </TouchableOpacity>
      </Modal>

      <ScrollView contentContainerStyle={styles.form}>
        <Text style={styles.sectionTitle}>{t('mermas.articulo_h2', 'Artículo')}</Text>
        <TextInput
          style={styles.input}
          placeholder={t('mermas.buscar_articulo_ph', 'Buscar artículo (código o nombre)')}
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

        <Text style={styles.sectionTitle}>{t('mermas.foto_evidencia_h2', 'Foto de evidencia')}</Text>
        {fotoUri ? (
          <View style={styles.fotoPreviewWrap}>
            <Image source={{uri: fotoUri}} style={styles.fotoPreview} />
            <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
              <Text style={styles.buttonText}>{t('mermas.repetir_foto_btn', 'Repetir foto')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity style={styles.scanBtn} onPress={() => setCamaraAbierta(true)}>
            <Text style={styles.scanBtnText}>{t('mermas.hacer_foto_btn', 'Hacer foto')}</Text>
          </TouchableOpacity>
        )}

        <Text style={styles.sectionTitle}>{t('mermas.detalles_h2', 'Detalles')}</Text>
        <View style={styles.chipsRow}>
          {MOTIVOS.map(m => (
            <TouchableOpacity
              key={m}
              style={[styles.chip, motivo === m && styles.chipActivo]}
              onPress={() => setMotivo(m)}>
              <Text style={[styles.chipTexto, motivo === m && styles.chipTextoActivo]}>
                {t(`mermas.motivo_${MOTIVO_SLUG[m]}`, m)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={styles.row}>
          <TextInput
            style={[styles.input, {width: 100}]}
            placeholder={t('mermas.cantidad_ph', 'Cantidad')}
            placeholderTextColor={colors.textDim}
            keyboardType="numeric"
            value={cantidad}
            onChangeText={setCantidad}
          />
          <TouchableOpacity
            style={[styles.chip, origen === 'lineal' && styles.chipActivo]}
            onPress={() => setOrigen('lineal')}>
            <Text style={[styles.chipTexto, origen === 'lineal' && styles.chipTextoActivo]}>
              {t('mermas.stock_lineal', 'Stock lineal')}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.chip, origen === 'almacen' && styles.chipActivo]}
            onPress={() => setOrigen('almacen')}>
            <Text style={[styles.chipTexto, origen === 'almacen' && styles.chipTextoActivo]}>
              {t('mermas.almacen', 'Almacén')}
            </Text>
          </TouchableOpacity>
        </View>

        {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

        <TouchableOpacity
          style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
          onPress={enviar}
          disabled={enviando}>
          {enviando ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.buttonText}>{t('mermas.registrar_btn', 'Registrar merma')}</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>{t('mermas.ultimas_h2', 'Últimas mermas')}</Text>
        {cargandoLista ? (
          <ActivityIndicator color={colors.cyan} />
        ) : (
          <FlatList
            data={recientes}
            keyExtractor={item => String(item.id)}
            scrollEnabled={false}
            ListEmptyComponent={<Text style={styles.hint}>{t('mermas.sin_mermas', 'Sin mermas registradas todavía.')}</Text>}
            renderItem={({item}) => (
              <TouchableOpacity
                style={styles.card}
                disabled={!item.id_documento_foto}
                onPress={() => item.id_documento_foto && setFotoVista(item.id_documento_foto)}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardTitle} numberOfLines={1}>{item.nombre}</Text>
                  <Text style={styles.cardDetail}>{item.id_documento_foto ? t('mermas.ver_foto', '📷 Ver foto') : ''}</Text>
                </View>
                <Text style={styles.cardDetail}>
                  {item.codigo} · {t('mermas.uds_lbl', '{{c}} uds', {c: item.cantidad})} · {t(`mermas.motivo_${MOTIVO_SLUG[item.motivo] ?? 'otro'}`, item.motivo)}
                </Text>
                <Text style={styles.cardDetail}>{item.fecha}</Text>
              </TouchableOpacity>
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
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 14},
  fotoPreviewWrap: {alignItems: 'center', gap: 8},
  fotoPreview: {width: '100%', height: 200, borderRadius: 12, backgroundColor: colors.panel},
  row: {flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap'},
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
  hint: {color: colors.textDim, fontSize: 12},
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
  fotoModalFondo: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.9)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  fotoModalImagen: {width: '100%', height: '80%'},
});
