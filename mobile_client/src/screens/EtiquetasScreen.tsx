/**
 * Etiquetas (capacidad "etiquetas" -> /api/v1/labels/*). Dos pestañas:
 *  · "Localizar": buscar un artículo, ver qué etiqueta(s) ESL tiene vinculadas y hacerlas parpadear
 *    para encontrarlas físicamente en el lineal — el paso original de este módulo.
 *  · "Cambiar precio": cambiar el precio de un artículo e imprimir su etiqueta de papel con el precio
 *    nuevo — restringida a ADMINISTRADOR/SUPERADMIN (permiso `etiquetas.precio.editar`, ver
 *    `api/capabilities.ts::modulosEfectivos`); un operario sin esa concesión ni verá la pestaña.
 * Sincronizar precios en bloque se queda en escritorio (rediseño móvil Grupo A).
 */
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {buscarArticulos, type Articulo} from '@/api/articles';
import {
  buscarEtiquetasDeArticulo,
  cambiarPrecio,
  localizarEtiqueta,
  urlPdfEtiqueta,
  TAMANOS_ETIQUETA,
  type EtiquetaEsl,
  type TamanoEtiqueta,
  type TipoEtiqueta,
} from '@/api/labels';
import {modulosEfectivos} from '@/api/capabilities';
import {obtenerBadgesSubtab, marcarVistoSubtab} from '@/api/badges';
import {abrirPdf} from '@/services/impresion';
import {colors} from '@/theme/colors';
import TabBadge from '@/components/TabBadge';
import type {EtiquetasProps} from '@/navigation/types';

type Pestana = 'localizar' | 'precio';

export default function EtiquetasScreen({navigation}: EtiquetasProps) {
  const {t} = useTranslation();
  const [pestana, setPestana] = useState<Pestana>('localizar');
  // Por defecto oculta hasta que llegue la respuesta de `/me/modules` (a diferencia de las capacidades
  // "base": esta SÍ empieza restringida, ya que la mayoría de usuarios no tendrán el permiso).
  const [puedeCambiarPrecio, setPuedeCambiarPrecio] = useState(false);
  // Badge de pestaña (granularidad fina del Centro de Actividad): solo "precio" tiene slug mapeado
  // (`mapeo.TIPO_A_SUBTAB["PRECIO_ACTUALIZADO"] = "precio"`) — mismo criterio que el Dashboard.
  const [badgesPestana, setBadgesPestana] = useState<Record<string, number>>({});

  useEffect(() => {
    let vivo = true;
    modulosEfectivos().then(m => {
      if (vivo) {
        setPuedeCambiarPrecio(m['etiquetas.precio'] === true);
      }
    });
    return () => {
      vivo = false;
    };
  }, []);

  const refrescarBadges = useCallback(() => {
    obtenerBadgesSubtab('etiquetas').then(setBadgesPestana);
  }, []);

  useEffect(() => {
    refrescarBadges();
    const unsub = navigation.addListener('focus', refrescarBadges);
    return unsub;
  }, [navigation, refrescarBadges]);

  const pestanas = useMemo<{key: Pestana; labelKey: string; label: string}[]>(
    () => [
      {key: 'localizar', labelKey: 'etiquetas.pestana_localizar', label: 'Localizar'},
      ...(puedeCambiarPrecio
        ? [{key: 'precio' as const, labelKey: 'etiquetas.pestana_cambiar_precio', label: 'Cambiar precio'}]
        : []),
    ],
    [puedeCambiarPrecio],
  );

  useEffect(() => {
    if (!puedeCambiarPrecio && pestana === 'precio') {
      setPestana('localizar');
    }
  }, [puedeCambiarPrecio, pestana]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('etiquetas.titulo', 'Etiquetas')}</Text>
        <View style={{width: 90}} />
      </View>

      {pestanas.length > 1 && (
        <View style={styles.tabsRow}>
          {pestanas.map(p => (
            <TouchableOpacity
              key={p.key}
              style={[styles.tab, pestana === p.key && styles.tabActive]}
              onPress={() => {
                setPestana(p.key);
                if (p.key === 'precio') {
                  setBadgesPestana(b => ({...b, precio: 0}));
                  marcarVistoSubtab('etiquetas', 'precio');
                }
              }}>
              <Text style={[styles.tabText, pestana === p.key && styles.tabTextActive]}>
                {t(p.labelKey, p.label)}
              </Text>
              {p.key === 'precio' ? <TabBadge n={badgesPestana.precio ?? 0} /> : null}
            </TouchableOpacity>
          ))}
        </View>
      )}

      {pestana === 'localizar' ? <TabLocalizar /> : <TabCambiarPrecio />}
    </SafeAreaView>
  );
}

// ── Localizar (comportamiento original de esta pantalla) ────────────────────────────────────────────
function TabLocalizar() {
  const {t} = useTranslation();
  const [q, setQ] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [articulo, setArticulo] = useState<Articulo | null>(null);
  const [etiquetas, setEtiquetas] = useState<EtiquetaEsl[]>([]);
  const [cargando, setCargando] = useState(false);
  const [localizando, setLocalizando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const elegir = useCallback(async (a: Articulo) => {
    setArticulo(a);
    setQ(`${a.codigo} – ${a.nombre}`);
    setSugerencias([]);
    setAviso(null);
    setCargando(true);
    try {
      setEtiquetas(await buscarEtiquetasDeArticulo(a.codigo));
    } finally {
      setCargando(false);
    }
  }, []);

  const localizar = useCallback(async (labelId: string) => {
    setLocalizando(labelId);
    setAviso(null);
    try {
      const r = await localizarEtiqueta(labelId);
      if (r.ok) {
        setAviso({ok: true, texto: t('etiquetas.parpadeando_ok', 'La etiqueta debería estar parpadeando ahora — búscala en el lineal.')});
      } else {
        setAviso({ok: false, texto: t('etiquetas.no_se_pudo_localizar', 'No se pudo enviar la orden de localización.')});
      }
    } catch {
      setAviso({ok: false, texto: t('etiquetas.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setLocalizando(null);
    }
  }, [t]);

  return (
    <View style={styles.tabFlex}>
      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder={t('etiquetas.buscar_articulo_ph', 'Buscar artículo (código o nombre)')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={q}
          onChangeText={texto => {
            setQ(texto);
            setArticulo(null);
            setEtiquetas([]);
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
      </View>

      {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

      {cargando ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
        </View>
      ) : (
        <FlatList
          data={etiquetas}
          keyExtractor={item => String(item.id)}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            articulo ? (
              <View style={styles.centered}>
                <Text style={styles.hint}>{t('etiquetas.sin_esl_vinculadas', 'Este artículo no tiene etiquetas ESL vinculadas.')}</Text>
              </View>
            ) : (
              <View style={styles.centered}>
                <Text style={styles.hint}>{t('etiquetas.busca_para_ver', 'Busca un artículo para ver sus etiquetas.')}</Text>
              </View>
            )
          }
          renderItem={({item}) => (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardTitle}>{item.label_id}</Text>
                <Text style={styles.cardEstado}>{item.estado}</Text>
              </View>
              {item.precio_sincronizado != null ? (
                <Text style={styles.cardDetail}>
                  {t('etiquetas.precio_en_etiqueta', 'Precio en la etiqueta: {{p}} €', {p: Number(item.precio_sincronizado).toFixed(2)})}
                </Text>
              ) : null}
              <TouchableOpacity
                style={[styles.button, localizando === item.label_id && styles.buttonDisabled]}
                onPress={() => localizar(item.label_id)}
                disabled={localizando === item.label_id}>
                {localizando === item.label_id ? (
                  <ActivityIndicator color={colors.bg} size="small" />
                ) : (
                  <Text style={styles.buttonText}>{t('etiquetas.localizar_parpadear_btn', 'Localizar (parpadear)')}</Text>
                )}
              </TouchableOpacity>
            </View>
          )}
        />
      )}
    </View>
  );
}

// ── Cambiar precio + imprimir etiqueta ──────────────────────────────────────────────────────────────
function TabCambiarPrecio() {
  const {t} = useTranslation();
  const [q, setQ] = useState('');
  const [sugerencias, setSugerencias] = useState<Articulo[]>([]);
  const [articulo, setArticulo] = useState<Articulo | null>(null);
  const [nuevoPrecio, setNuevoPrecio] = useState('');
  const [formato, setFormato] = useState<TamanoEtiqueta>('70x35');
  const [tipo, setTipo] = useState<TipoEtiqueta>('normal');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    setAviso(null);
    setNuevoPrecio(a.precio ? String(Number(a.precio)) : '');
  }, []);

  const generarEImprimir = useCallback(async () => {
    if (!articulo) {
      setAviso({ok: false, texto: t('etiquetas.busca_articulo', 'Busca primero un artículo.')});
      return;
    }
    const precio = Number((nuevoPrecio || '').replace(',', '.'));
    if (!Number.isFinite(precio) || precio < 0) {
      setAviso({ok: false, texto: t('etiquetas.precio_invalido', 'Introduce un precio válido.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await cambiarPrecio({codigo: articulo.codigo, nuevoPrecio: precio, formato, tipo});
      if (!r.ok || !r.id_documento) {
        setAviso({ok: false, texto: r.error || t('etiquetas.no_se_pudo_cambiar_precio', 'No se pudo cambiar el precio.')});
        return;
      }
      const {url, headers} = urlPdfEtiqueta(r.id_documento);
      const abierto = await abrirPdf(url, headers, `etiqueta_${articulo.codigo}.pdf`);
      setAviso(
        abierto.ok
          ? {ok: true, texto: t('etiquetas.precio_actualizado_ok', 'Precio actualizado. Elige dónde imprimir/compartir la etiqueta.')}
          : {ok: true, texto: t('etiquetas.precio_actualizado_pero', 'Precio actualizado, pero {{e}}', {e: abierto.error?.toLowerCase()})},
      );
    } catch {
      setAviso({ok: false, texto: t('etiquetas.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [articulo, nuevoPrecio, formato, tipo, t]);

  return (
    <ScrollView style={styles.tabFlex} contentContainerStyle={styles.form}>
      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder={t('etiquetas.buscar_articulo_ph', 'Buscar artículo (código o nombre)')}
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
      </View>

      {articulo ? (
        <>
          <Text style={styles.paso}>{t('etiquetas.nuevo_precio_de', 'Nuevo precio de {{n}}', {n: articulo.nombre})}</Text>
          <TextInput
            style={styles.input}
            placeholder={t('etiquetas.precio_ph', 'Precio')}
            placeholderTextColor={colors.textDim}
            keyboardType="decimal-pad"
            value={nuevoPrecio}
            onChangeText={setNuevoPrecio}
          />

          <Text style={styles.paso}>{t('etiquetas.tamano_etiqueta_lbl', 'Tamaño de etiqueta')}</Text>
          <View style={styles.chipsRow}>
            {TAMANOS_ETIQUETA.map(tam => (
              <TouchableOpacity
                key={tam}
                style={[styles.chip, formato === tam && styles.chipActivo]}
                onPress={() => setFormato(tam)}>
                <Text style={[styles.chipTexto, formato === tam && styles.chipTextoActivo]}>{tam}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.paso}>{t('etiquetas.tipo_lbl', 'Tipo')}</Text>
          <View style={styles.chipsRow}>
            {(
              [
                {key: 'normal', labelKey: 'etiquetas.tipo_normal', label: 'Normal'},
                {key: 'rebajado', labelKey: 'etiquetas.tipo_rebajado', label: 'Rebajado'},
                {key: 'nuevo', labelKey: 'etiquetas.tipo_nuevo', label: 'Nuevo'},
              ] as const
            ).map(tp => (
              <TouchableOpacity
                key={tp.key}
                style={[styles.chip, tipo === tp.key && styles.chipActivo]}
                onPress={() => setTipo(tp.key)}>
                <Text style={[styles.chipTexto, tipo === tp.key && styles.chipTextoActivo]}>
                  {t(tp.labelKey, tp.label)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

          <TouchableOpacity
            style={[styles.button, enviando && styles.buttonDisabled]}
            onPress={generarEImprimir}
            disabled={enviando}>
            {enviando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>{t('etiquetas.generar_imprimir_btn', 'Generar e imprimir')}</Text>
            )}
          </TouchableOpacity>
        </>
      ) : (
        <View style={styles.centered}>
          <Text style={styles.hint}>{t('etiquetas.busca_para_cambiar_precio', 'Busca un artículo para cambiar su precio.')}</Text>
        </View>
      )}
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
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 10,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabActive: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  tabText: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  tabTextActive: {color: colors.bg},
  tabFlex: {flex: 1},
  form: {padding: 16, paddingTop: 0},
  paso: {color: colors.textDim, fontWeight: '700', fontSize: 12, marginBottom: 6, marginTop: 12},
  chipsRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 4},
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
  searchBox: {paddingHorizontal: 16},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
  },
  sugerencias: {
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    marginTop: 4,
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
  ok: {color: colors.ok, marginHorizontal: 16, marginTop: 8, fontSize: 12},
  error: {color: colors.danger, marginHorizontal: 16, marginTop: 8, fontSize: 12},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32},
  hint: {color: colors.textDim, textAlign: 'center'},
  list: {padding: 16, paddingTop: 12},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10},
  cardTitle: {color: colors.text, fontWeight: '800', fontSize: 15},
  cardEstado: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  cardDetail: {color: colors.textDim, fontSize: 12, marginBottom: 8},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800', fontSize: 13},
});
