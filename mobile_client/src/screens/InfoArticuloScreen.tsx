/**
 * Info Artículo (capacidad "info_articulo" -> /api/v1/articles). Petición explícita: SOLO las dos
 * pestañas de escritorio que tienen sentido de pie frente al lineal — "Buscar artículo" (consultar
 * stock/ubicación/precio sin ir a buscar un terminal) e "Imagen artículo" (Grupo B: fotografiar el
 * artículo in situ, mismo patrón que Mermas/Calidad/SAT). "Editar artículo" y "Familias"
 * (administración pura) se quedan en escritorio.
 *
 * La ficha mostrada en "Buscar artículo" es la MISMA que `gui.info_articulo.InfoArticuloWindow`
 * muestra en escritorio, campo a campo (ver `api/articles.ts::FichaArticulo` y
 * `api/routers/articles.py::articles_ficha`) — nunca un subconjunto.
 */
import React, {useCallback, useState} from 'react';
import {
  ActivityIndicator,
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
  borrarImagenArticulo,
  buscarArticulos,
  imagenArticuloSource,
  obtenerFichaArticulo,
  subirImagenArticulo,
  type Articulo,
  type FichaArticulo,
} from '@/api/articles';
import type {ArchivoAdjunto} from '@/api/client';
import {colors} from '@/theme/colors';
import type {InfoArticuloProps} from '@/navigation/types';

type Pestana = 'buscar' | 'imagen';

export default function InfoArticuloScreen({navigation}: InfoArticuloProps) {
  const {t} = useTranslation();
  const [pestana, setPestana] = useState<Pestana>('buscar');

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('info.titulo', 'Info Artículo')}</Text>
        <View style={{width: 90}} />
      </View>

      <View style={styles.tabsRow}>
        <TouchableOpacity
          style={[styles.chip, pestana === 'buscar' && styles.chipActivo]}
          onPress={() => setPestana('buscar')}>
          <Text style={[styles.chipTexto, pestana === 'buscar' && styles.chipTextoActivo]}>
            {t('info.tab_buscar', 'Buscar artículo')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, pestana === 'imagen' && styles.chipActivo]}
          onPress={() => setPestana('imagen')}>
          <Text style={[styles.chipTexto, pestana === 'imagen' && styles.chipTextoActivo]}>
            {t('info.tab_imagen', 'Imagen artículo')}
          </Text>
        </TouchableOpacity>
      </View>

      {pestana === 'buscar' ? <BuscarArticuloTab /> : <ImagenArticuloTab />}
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Pestaña "Buscar artículo"
// ─────────────────────────────────────────────────────────────────────────
function BuscarArticuloTab() {
  const {t} = useTranslation();
  const [texto, setTexto] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [ficha, setFicha] = useState<FichaArticulo | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buscarSugerencias = useCallback(async (q: string) => {
    setTexto(q);
    if (q.trim().length < 2) {
      setSugerencias([]);
      return;
    }
    setSugerencias(await buscarArticulos(q.trim()));
  }, []);

  const resolver = useCallback(async (codigo: string) => {
    const cod = codigo.trim();
    if (!cod) {
      return;
    }
    setCargando(true);
    setError(null);
    setSugerencias([]);
    try {
      const r = await obtenerFichaArticulo(cod);
      if (r) {
        setFicha(r);
        setTexto(`${r.codigo} – ${r.nombre ?? ''}`);
      } else {
        setFicha(null);
        setError(t('info.not_found_msg', 'Este código de artículo no existe en el sistema.'));
      }
    } finally {
      setCargando(false);
    }
  }, [t]);

  const campo = (etiqueta: string, valor: string | number | null | undefined) => (
    <View style={styles.filaCampo} key={etiqueta}>
      <Text style={styles.campoEtiqueta}>{etiqueta}</Text>
      <Text style={styles.campoValor}>
        {valor === null || valor === undefined || valor === '' ? '—' : String(valor)}
      </Text>
    </View>
  );

  return (
    <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
      <TextInput
        style={styles.input}
        placeholder={t('info.search_ph', 'Código o nombre del artículo…')}
        placeholderTextColor={colors.textDim}
        autoCapitalize="none"
        value={texto}
        onChangeText={buscarSugerencias}
        onSubmitEditing={() => resolver(texto)}
      />
      <TouchableOpacity style={styles.button} onPress={() => resolver(texto)} disabled={cargando}>
        {cargando ? <ActivityIndicator color={colors.bg} /> : (
          <Text style={styles.buttonText}>{t('info.search_btn', '🔍 Buscar')}</Text>
        )}
      </TouchableOpacity>

      {sugerencias.length > 0 ? (
        <View style={styles.sugerencias}>
          {sugerencias.slice(0, 8).map(a => (
            <TouchableOpacity key={a.codigo} style={styles.sugerenciaItem} onPress={() => resolver(a.codigo)}>
              <Text style={styles.sugerenciaTexto}>{a.codigo} – {a.nombre}</Text>
            </TouchableOpacity>
          ))}
        </View>
      ) : null}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {ficha ? (
        <View style={styles.card}>
          {campo(t('info.f_code', 'CÓDIGO SKU'), ficha.codigo)}
          {campo(t('info.f_desc', 'DESCRIPCIÓN'), ficha.nombre)}
          {campo(t('info.f_shelf', 'STOCK LINEAL'),
                ficha.stock_reservado > 0
                  ? `${ficha.stock_lineal ?? '-'}  (-${ficha.stock_reservado} ${t('info.stock_reservado', 'reservado')})`
                  : ficha.stock_lineal)}
          {campo(t('info.f_warehouse', 'STOCK ALMACÉN'), ficha.stock_almacen)}
          {campo(t('info.f_central', 'STOCK CENTRAL'), ficha.stock_central)}
          {campo(t('info.f_price', 'P.V.P'), `${ficha.precio.toFixed(2)} €`)}
          {campo(t('info.f_loc_store', 'UBIC. TIENDA'), ficha.ubicacion_tienda)}
          {campo(t('info.f_loc_warehouse', 'UBIC. ALMACÉN'), ficha.ubicacion_almacen)}
          {campo(t('info.f_reception', 'PRÓX. ENTRADA'), ficha.proxima_recepcion)}
          {campo(t('info.f_sales', 'VENTAS 7 DÍAS'), ficha.ventas_7_dias)}
          {campo(t('info.f_familia', 'FAMILIA'), ficha.familia)}
          {campo(t('info.f_precio_ref', 'PRECIO REF.'),
                ficha.precio_ref != null ? `${ficha.precio_ref.toFixed(2)} €` : null)}
          {campo(t('info.f_peso_unit', 'PESO UNIT. (kg)'), ficha.peso_unitario)}
          {campo(t('info.f_tolerancia', 'TOLERANCIA (kg)'), ficha.tolerancia_peso)}
          {campo(t('info.f_requiere_lote', 'TRAZABILIDAD POR LOTE'),
                ficha.requiere_lote ? t('common.si', 'Sí') : t('common.no', 'No'))}
        </View>
      ) : null}
    </ScrollView>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Pestaña "Imagen artículo"
// ─────────────────────────────────────────────────────────────────────────
function ImagenArticuloTab() {
  const {t} = useTranslation();
  const [texto, setTexto] = useState('');
  const [codigoResuelto, setCodigoResuelto] = useState<FichaArticulo | null>(null);
  const [fotoUri, setFotoUri] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  // Refresca el <Image> tras guardar/borrar (la URL es la misma, solo cambia el contenido).
  const [vistaKey, setVistaKey] = useState(0);

  const resolver = useCallback(async () => {
    const cod = texto.trim();
    if (!cod) {
      return;
    }
    setCargando(true);
    setAviso(null);
    try {
      const r = await obtenerFichaArticulo(cod);
      setCodigoResuelto(r);
      setFotoUri(null);
      setVistaKey(k => k + 1);
      if (!r) {
        setAviso({ok: false, texto: t('info.not_found_msg', 'Este código de artículo no existe en el sistema.')});
      }
    } finally {
      setCargando(false);
    }
  }, [texto, t]);

  const guardar = useCallback(async () => {
    if (!codigoResuelto || !fotoUri) {
      return;
    }
    setGuardando(true);
    setAviso(null);
    try {
      const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'articulo.jpg', type: 'image/jpeg'};
      const r = await subirImagenArticulo(codigoResuelto.codigo, archivo);
      if (r.ok) {
        setAviso({ok: true, texto: t('info.img_saved', 'Imagen guardada.')});
        setFotoUri(null);
        setVistaKey(k => k + 1);
        setCodigoResuelto({...codigoResuelto, tiene_imagen: true});
      } else {
        setAviso({ok: false, texto: r.error || t('info.img_save_error_simple', 'No se pudo guardar la imagen.')});
      }
    } finally {
      setGuardando(false);
    }
  }, [codigoResuelto, fotoUri, t]);

  const borrar = useCallback(async () => {
    if (!codigoResuelto) {
      return;
    }
    setGuardando(true);
    try {
      await borrarImagenArticulo(codigoResuelto.codigo);
      setCodigoResuelto({...codigoResuelto, tiene_imagen: false});
      setFotoUri(null);
      setVistaKey(k => k + 1);
      // Abreviado a propósito (petición explícita) + color de aviso rojo.
      setAviso({ok: false, texto: t('info.img_deleted', 'Imagen eliminada')});
    } finally {
      setGuardando(false);
    }
  }, [codigoResuelto, t]);

  return (
    <ScrollView contentContainerStyle={styles.body}>
      <TextInput
        style={styles.input}
        placeholder={t('info.image_search_ph', 'Código o nombre del artículo…')}
        placeholderTextColor={colors.textDim}
        autoCapitalize="none"
        value={texto}
        onChangeText={setTexto}
        onSubmitEditing={resolver}
      />
      <TouchableOpacity style={styles.button} onPress={resolver} disabled={cargando}>
        {cargando ? <ActivityIndicator color={colors.bg} /> : (
          <Text style={styles.buttonText}>{t('info.search_btn', '🔍 Buscar')}</Text>
        )}
      </TouchableOpacity>

      {codigoResuelto ? (
        <>
          <Text style={styles.nombreArticulo}>{codigoResuelto.codigo} – {codigoResuelto.nombre}</Text>

          <View style={styles.previewWrap}>
            {fotoUri ? (
              <Image source={{uri: fotoUri}} style={styles.preview} />
            ) : codigoResuelto.tiene_imagen ? (
              <Image key={vistaKey} source={imagenArticuloSource(codigoResuelto.codigo)} style={styles.preview} />
            ) : (
              <Text style={styles.hint}>{t('info.no_image', 'SIN IMAGEN')}</Text>
            )}
          </View>

          <TouchableOpacity style={styles.button} onPress={() => setCamaraAbierta(true)}>
            <Text style={styles.buttonText}>{t('info.img_take_photo', '📷 Hacer foto')}</Text>
          </TouchableOpacity>

          {fotoUri ? (
            <TouchableOpacity
              style={[styles.button, styles.buttonOk, guardando && styles.buttonDisabled]}
              onPress={guardar}
              disabled={guardando}>
              {guardando ? <ActivityIndicator color={colors.bg} /> : (
                <Text style={styles.buttonText}>{t('info.img_save_btn', 'Guardar imagen')}</Text>
              )}
            </TouchableOpacity>
          ) : null}

          {codigoResuelto.tiene_imagen ? (
            <TouchableOpacity
              style={[styles.button, styles.buttonDanger, guardando && styles.buttonDisabled]}
              onPress={borrar}
              disabled={guardando}>
              <Text style={styles.buttonText}>{t('info.img_delete_btn', 'Borrar imagen')}</Text>
            </TouchableOpacity>
          ) : null}
        </>
      ) : null}

      {aviso ? (
        <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text>
      ) : null}

      <Modal visible={camaraAbierta} animationType="slide">
        <SafeAreaView style={styles.root} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setCamaraAbierta(false)}>
              <Text style={[styles.back, {width: 110}]} numberOfLines={1}>‹ {t('common.cancelar', 'Cancelar')}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{t('info.img_take_photo', '📷 Hacer foto')}</Text>
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
    </ScrollView>
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
  tabsRow: {flexDirection: 'row', gap: 8, paddingHorizontal: 16, marginBottom: 8},
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActivo: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  chipTexto: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  chipTextoActivo: {color: colors.bg},
  body: {padding: 16, paddingTop: 4},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    marginBottom: 8,
  },
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 10,
  },
  buttonOk: {backgroundColor: colors.ok},
  buttonDanger: {backgroundColor: colors.danger},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  sugerencias: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    marginBottom: 10,
    overflow: 'hidden',
  },
  sugerenciaItem: {paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border},
  sugerenciaTexto: {color: colors.text, fontSize: 13},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
  },
  filaCampo: {flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, gap: 10},
  campoEtiqueta: {color: colors.textDim, fontSize: 12, fontWeight: '700', flex: 1},
  campoValor: {color: colors.text, fontSize: 13, fontWeight: '800', flex: 1, textAlign: 'right'},
  nombreArticulo: {color: colors.text, fontWeight: '800', fontSize: 15, marginBottom: 10},
  previewWrap: {
    height: 220,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panel,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 10,
    overflow: 'hidden',
  },
  preview: {width: '100%', height: '100%'},
  hint: {color: colors.textDim},
  error: {color: colors.danger, textAlign: 'center', marginTop: 4},
  ok: {color: colors.ok, textAlign: 'center', marginTop: 4},
});
