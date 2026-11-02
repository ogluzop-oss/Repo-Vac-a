/**
 * Ubicación (capacidad "ubicacion" -> /api/v1/location/*). SOLO 2 pestañas — las únicas que exigen
 * presencia física real: Asignar ubicación (escanear la etiqueta de una estantería) y GPS interno
 * (escanear el QR de un satélite para autolocalizarse y trazar ruta). "Buscar producto" se quedó en
 * escritorio (rediseño móvil Grupo A — es un buscador puro, sin componente físico).
 */
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Image,
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
  asignarUbicacion,
  calcularRuta,
  coordsArticulo,
  imagenMapaSource,
  obtenerMapa,
  type MapaInfo,
  type ReferenciaMapa,
  type TipoUbicacion,
} from '@/api/location';
import {obtenerBadgesSubtab, marcarVistoSubtab} from '@/api/badges';
import {colors} from '@/theme/colors';
import TabBadge from '@/components/TabBadge';
import type {UbicacionProps} from '@/navigation/types';

type Pestana = 'asignar' | 'gps';
type ObjetivoEscaneo = 'asignar-estanteria' | 'asignar-articulo' | 'gps-origen' | null;

const PESTANAS: {key: Pestana; labelKey: string; label: string}[] = [
  {key: 'asignar', labelKey: 'ubicacion.pestana_asignar', label: 'Asignar ubicación'},
  {key: 'gps', labelKey: 'ubicacion.pestana_gps', label: 'GPS interno'},
];

export default function UbicacionScreen({navigation, route}: UbicacionProps) {
  const {t} = useTranslation();
  const [pestana, setPestana] = useState<Pestana>('asignar');
  const objetivoEscaneo = useRef<ObjetivoEscaneo>(null);
  const [ultimoEscaneo, setUltimoEscaneo] = useState<{objetivo: ObjetivoEscaneo; valor: string} | null>(
    null,
  );
  // Badge de pestaña (Centro de Actividad): solo "asignar" tiene slug mapeado
  // (`mapeo.TIPO_A_SUBTAB["UBICACION_ASIGNADA"] = "asignar"`).
  const [badgesPestana, setBadgesPestana] = useState<Record<string, number>>({});

  useEffect(() => {
    const escaneado = route.params?.escaneado;
    if (escaneado) {
      setUltimoEscaneo({objetivo: objetivoEscaneo.current, valor: escaneado});
      objetivoEscaneo.current = null;
      navigation.setParams({escaneado: undefined});
    }
  }, [route.params?.escaneado, navigation]);

  const refrescarBadges = useCallback(() => {
    obtenerBadgesSubtab('ubicacion').then(setBadgesPestana);
  }, []);

  useEffect(() => {
    refrescarBadges();
    const unsub = navigation.addListener('focus', refrescarBadges);
    return unsub;
  }, [navigation, refrescarBadges]);

  const pedirEscaneo = useCallback(
    (objetivo: ObjetivoEscaneo) => {
      objetivoEscaneo.current = objetivo;
      navigation.navigate('Scanner', {volverA: 'Ubicacion'});
    },
    [navigation],
  );

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('ubicacion.titulo', 'Ubicación')}</Text>
        <View style={{width: 90}} />
      </View>

      <View style={styles.tabsRow}>
        {PESTANAS.map(p => (
          <TouchableOpacity
            key={p.key}
            style={[styles.tab, pestana === p.key && styles.tabActive]}
            onPress={() => {
              setPestana(p.key);
              if (p.key === 'asignar') {
                setBadgesPestana(b => ({...b, asignar: 0}));
                marcarVistoSubtab('ubicacion', 'asignar');
              }
            }}>
            <Text style={[styles.tabText, pestana === p.key && styles.tabTextActive]}>
              {t(p.labelKey, p.label)}
            </Text>
            {p.key === 'asignar' ? <TabBadge n={badgesPestana.asignar ?? 0} /> : null}
          </TouchableOpacity>
        ))}
      </View>

      {pestana === 'asignar' ? (
        <TabAsignar pedirEscaneo={pedirEscaneo} ultimoEscaneo={ultimoEscaneo} />
      ) : (
        <TabGps pedirEscaneo={pedirEscaneo} ultimoEscaneo={ultimoEscaneo} />
      )}
    </SafeAreaView>
  );
}

/** Payload de la etiqueta impresa de una estantería: "EPC:<epc>|LOC:<pasillo>-<estanteria>". */
function parseEtiquetaEstanteria(payload: string): {pasillo: string; estanteria: string} | null {
  const m = /LOC:([^-|]+)-([^|]+)/.exec(payload);
  if (!m || !m[1] || !m[2]) {
    return null;
  }
  return {pasillo: m[1].trim(), estanteria: m[2].trim()};
}

// ── Asignar ubicación (lineal/almacén fusionadas, con un selector de tipo) ─────────────────────────
function TabAsignar({
  pedirEscaneo,
  ultimoEscaneo,
}: {
  pedirEscaneo: (objetivo: ObjetivoEscaneo) => void;
  ultimoEscaneo: {objetivo: ObjetivoEscaneo; valor: string} | null;
}) {
  const {t} = useTranslation();
  const [tipo, setTipo] = useState<TipoUbicacion>('lineal');
  const [codigo, setCodigo] = useState('');
  const [pasillo, setPasillo] = useState('');
  const [estanteria, setEstanteria] = useState('');
  const [nivel, setNivel] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  useEffect(() => {
    if (!ultimoEscaneo) {
      return;
    }
    if (ultimoEscaneo.objetivo === 'asignar-estanteria') {
      const datos = parseEtiquetaEstanteria(ultimoEscaneo.valor);
      if (datos) {
        setPasillo(datos.pasillo);
        setEstanteria(datos.estanteria);
        setAviso(null);
      } else {
        setAviso({ok: false, texto: t('ubicacion.etiqueta_no_valida', 'Ese código no es una etiqueta de estantería válida.')});
      }
    } else if (ultimoEscaneo.objetivo === 'asignar-articulo') {
      setCodigo(ultimoEscaneo.valor);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ultimoEscaneo]);

  const confirmar = useCallback(async () => {
    if (!codigo.trim() || !pasillo.trim() || !estanteria.trim() || !nivel.trim()) {
      setAviso({ok: false, texto: t('ubicacion.completa_campos', 'Completa código, pasillo, estantería y nivel.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await asignarUbicacion({
        codigo: codigo.trim(),
        pasillo: pasillo.trim(),
        estanteria: estanteria.trim(),
        nivel: nivel.trim(),
        tipo,
      });
      if (r.ok) {
        setAviso({ok: true, texto: t('ubicacion.registrada_ok', 'Ubicación registrada.')});
        setCodigo('');
        setPasillo('');
        setEstanteria('');
        setNivel('');
      } else {
        setAviso({ok: false, texto: r.error || t('ubicacion.no_se_pudo_registrar', 'No se pudo registrar la ubicación.')});
      }
    } catch {
      setAviso({ok: false, texto: t('ubicacion.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [codigo, pasillo, estanteria, nivel, tipo, t]);

  return (
    <ScrollView style={styles.tabBody} contentContainerStyle={styles.form}>
      <View style={styles.chipsRow}>
        <TouchableOpacity
          style={[styles.chip, tipo === 'lineal' && styles.chipActivo]}
          onPress={() => setTipo('lineal')}>
          <Text style={[styles.chipTexto, tipo === 'lineal' && styles.chipTextoActivo]}>{t('ubicacion.lineal_lbl', 'Lineal')}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, tipo === 'almacen' && styles.chipActivo]}
          onPress={() => setTipo('almacen')}>
          <Text style={[styles.chipTexto, tipo === 'almacen' && styles.chipTextoActivo]}>{t('ubicacion.almacen_lbl', 'Almacén')}</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.paso}>{t('ubicacion.estanteria_escanea_h3', 'Estantería (escanea su etiqueta)')}</Text>
      <TouchableOpacity
        style={styles.scanBtn}
        onPress={() => pedirEscaneo('asignar-estanteria')}>
        <Text style={styles.scanBtnText}>{t('ubicacion.escanear_etiqueta_estanteria_btn', 'Escanear etiqueta de estantería')}</Text>
      </TouchableOpacity>
      <View style={styles.formRow}>
        <TextInput
          style={[styles.input, styles.inputFlex]}
          placeholder={t('ubicacion.pasillo_ph', 'Pasillo')}
          placeholderTextColor={colors.textDim}
          value={pasillo}
          onChangeText={setPasillo}
        />
        <TextInput
          style={[styles.input, styles.inputFlex]}
          placeholder={t('ubicacion.estanteria_ph', 'Estantería')}
          placeholderTextColor={colors.textDim}
          value={estanteria}
          onChangeText={setEstanteria}
        />
      </View>
      <TextInput
        style={styles.input}
        placeholder={t('ubicacion.nivel_balda_ph', 'Nivel / balda')}
        placeholderTextColor={colors.textDim}
        value={nivel}
        onChangeText={setNivel}
      />

      <Text style={styles.paso}>{t('ubicacion.articulo_h3', 'Artículo')}</Text>
      <View style={styles.formRow}>
        <TextInput
          style={[styles.input, styles.inputFlex]}
          placeholder={t('ubicacion.codigo_articulo_ph', 'Código del artículo')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={codigo}
          onChangeText={setCodigo}
        />
        <TouchableOpacity style={styles.button} onPress={() => pedirEscaneo('asignar-articulo')}>
          <Text style={styles.buttonText}>{t('ubicacion.escanear_btn', 'Escanear')}</Text>
        </TouchableOpacity>
      </View>

      {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
      <TouchableOpacity
        style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
        onPress={confirmar}
        disabled={enviando}>
        {enviando ? (
          <ActivityIndicator color={colors.bg} />
        ) : (
          <Text style={styles.buttonText}>{t('ubicacion.confirmar_registrar_btn', 'Confirmar y registrar')}</Text>
        )}
      </TouchableOpacity>
    </ScrollView>
  );
}

// ── GPS interno ──────────────────────────────────────────────────────────────────────────────────
interface PuntoResuelto {
  ref: ReferenciaMapa;
  etiqueta: string;
  x: number;
  y: number;
}

function TabGps({
  pedirEscaneo,
  ultimoEscaneo,
}: {
  pedirEscaneo: (objetivo: ObjetivoEscaneo) => void;
  ultimoEscaneo: {objetivo: ObjetivoEscaneo; valor: string} | null;
}) {
  const {t} = useTranslation();
  const [mapa, setMapa] = useState<MapaInfo | null>(null);
  const [cargandoMapa, setCargandoMapa] = useState(true);
  const [natural, setNatural] = useState<{w: number; h: number} | null>(null);
  const [contenedor, setContenedor] = useState<{w: number; h: number} | null>(null);
  const [cambiandoPlanta, setCambiandoPlanta] = useState(false);

  const [qDestino, setQDestino] = useState('');
  const [destino, setDestino] = useState<PuntoResuelto | null>(null);
  const [origen, setOrigen] = useState<PuntoResuelto | null>(null);

  const [calculando, setCalculando] = useState(false);
  const [ruta, setRuta] = useState<{x: number; y: number}[] | null>(null);
  const [distanciaRuta, setDistanciaRuta] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setCargandoMapa(true);
      setMapa(await obtenerMapa());
      setCargandoMapa(false);
    })();
  }, []);

  // Navegar entre plantas (mismo criterio que `navegar_planta` de escritorio: incluye tanto plantas de
  // tipo tienda como de almacén, indistintamente — son solo índices consecutivos). Al cambiar de planta
  // se limpia el rastreo de ruta activo, igual que en escritorio, para no mezclar puntos de plantas
  // distintas.
  const navegarPlanta = useCallback(
    async (direccion: 1 | -1) => {
      if (!mapa || cambiandoPlanta) {
        return;
      }
      const siguiente = mapa.planta_index + direccion;
      if (siguiente < 0) {
        setAviso(t('ubicacion.primera_planta', 'Ya estás en la primera planta.'));
        return;
      }
      setCambiandoPlanta(true);
      setAviso(null);
      try {
        const nuevoMapa = await obtenerMapa(siguiente);
        if (!nuevoMapa) {
          setAviso(t('ubicacion.no_mas_plantas', 'No hay más plantas en esa dirección.'));
          return;
        }
        setMapa(nuevoMapa);
        setNatural(null);
        setOrigen(null);
        setDestino(null);
        setRuta(null);
        setQDestino('');
      } catch {
        setAviso(t('ubicacion.sin_conexion', 'No hay conexión con el servidor.'));
      } finally {
        setCambiandoPlanta(false);
      }
    },
    [mapa, cambiandoPlanta, t],
  );

  useEffect(() => {
    if (!ultimoEscaneo || ultimoEscaneo.objetivo !== 'gps-origen' || !mapa) {
      return;
    }
    let epc: string | null = null;
    try {
      const datos = JSON.parse(ultimoEscaneo.valor);
      epc = typeof datos?.epc === 'string' ? datos.epc : null;
    } catch {
      epc = null;
    }
    const punto = epc ? mapa.puntos_infraestructura.find(p => p.epc === epc) : undefined;
    if (punto) {
      setOrigen({ref: {tipo: 'punto', x: punto.x, y: punto.y}, etiqueta: punto.nombre, x: punto.x, y: punto.y});
      setRuta(null);
      setAviso(null);
    } else {
      setAviso(t('ubicacion.qr_no_corresponde', 'Este QR no corresponde a un satélite de esta planta.'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ultimoEscaneo, mapa]);

  const buscarDestino = useCallback(async (texto: string) => {
    if (!texto.trim()) {
      return;
    }
    const items = await buscarArticulos(texto.trim());
    const primero = items[0];
    if (!primero) {
      setAviso(t('ubicacion.articulo_no_encontrado', 'No se encontró ese artículo.'));
      return;
    }
    const coords = await coordsArticulo(primero.codigo);
    if (!coords) {
      setAviso(t('ubicacion.sin_coordenadas', '"{{n}}" no tiene coordenadas en el plano todavía.', {n: primero.nombre}));
      return;
    }
    setAviso(null);
    setDestino({ref: {tipo: 'articulo', codigo: primero.codigo}, etiqueta: primero.nombre, ...coords});
    setRuta(null);
  }, [t]);

  const iniciarRuta = useCallback(async () => {
    if (!mapa || !origen || !destino) {
      return;
    }
    setCalculando(true);
    setAviso(null);
    try {
      const r = await calcularRuta(mapa.planta_index, origen.ref, destino.ref);
      if (r.ok && r.ruta) {
        setRuta(r.ruta);
        setDistanciaRuta(r.distancia_celdas ?? null);
      } else {
        const motivos: Record<string, string> = {
          sin_plano: t('ubicacion.motivo_sin_plano', 'No hay un plano calibrado.'),
          origen_no_localizado: t('ubicacion.motivo_origen_no_localizado', 'No se pudo localizar el origen en el plano.'),
          destino_no_localizado: t('ubicacion.motivo_destino_no_localizado', 'No se pudo localizar el destino en el plano.'),
          sin_ruta: t('ubicacion.motivo_sin_ruta', 'No existe una ruta libre de obstáculos entre esos dos puntos.'),
        };
        setAviso(motivos[r.motivo || ''] || t('ubicacion.no_se_pudo_calcular_ruta', 'No se pudo calcular la ruta.'));
        setRuta(null);
        setDistanciaRuta(null);
      }
    } catch {
      setAviso(t('ubicacion.sin_conexion', 'No hay conexión con el servidor.'));
    } finally {
      setCalculando(false);
    }
  }, [mapa, origen, destino, t]);

  // Escala "contain": el plano se ajusta dentro del contenedor manteniendo proporción.
  const transformacion = useMemo(() => {
    if (!natural || !contenedor) {
      return null;
    }
    const escala = Math.min(contenedor.w / natural.w, contenedor.h / natural.h);
    const offsetX = (contenedor.w - natural.w * escala) / 2;
    const offsetY = (contenedor.h - natural.h * escala) / 2;
    return {escala, offsetX, offsetY};
  }, [natural, contenedor]);

  const aPantalla = useCallback(
    (x: number, y: number) => {
      if (!transformacion) {
        return null;
      }
      return {
        left: transformacion.offsetX + x * transformacion.escala,
        top: transformacion.offsetY + y * transformacion.escala,
      };
    },
    [transformacion],
  );

  if (cargandoMapa) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.cyan} />
      </View>
    );
  }

  if (!mapa || !mapa.tiene_imagen) {
    return (
      <View style={styles.centered}>
        <Text style={styles.hint}>{t('ubicacion.sin_plano', 'No hay ningún plano cargado todavía.')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.tabBody} contentContainerStyle={styles.form}>
      <View style={styles.plantaNav}>
        <TouchableOpacity
          style={[styles.plantaBtn, cambiandoPlanta && styles.buttonDisabled]}
          onPress={() => navegarPlanta(-1)}
          disabled={cambiandoPlanta}>
          <Text style={styles.plantaBtnText}>‹</Text>
        </TouchableOpacity>
        <View style={styles.plantaTitulo}>
          <Text style={styles.paso}>{mapa.titulo}</Text>
          <Text style={styles.plantaTipo}>{mapa.tipo}</Text>
        </View>
        <TouchableOpacity
          style={[styles.plantaBtn, cambiandoPlanta && styles.buttonDisabled]}
          onPress={() => navegarPlanta(1)}
          disabled={cambiandoPlanta}>
          <Text style={styles.plantaBtnText}>›</Text>
        </TouchableOpacity>
      </View>
      <View
        style={styles.mapaContenedor}
        onLayout={e => setContenedor({w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height})}>
        <Image
          source={imagenMapaSource(mapa.planta_index)}
          style={StyleSheet.absoluteFillObject}
          resizeMode="contain"
          onLoad={e => {
            const src = (e.nativeEvent as unknown as {source?: {width: number; height: number}}).source;
            if (src) {
              setNatural({w: src.width, h: src.height});
            }
          }}
        />
        {ruta?.map((p, i) => {
          const pos = aPantalla(p.x, p.y);
          if (!pos) {
            return null;
          }
          return <View key={i} style={[styles.rutaPunto, pos]} />;
        })}
        {origen
          ? (() => {
              const pos = aPantalla(origen.x, origen.y);
              return pos ? <View style={[styles.marcadorOrigen, pos]} /> : null;
            })()
          : null}
        {destino
          ? (() => {
              const pos = aPantalla(destino.x, destino.y);
              return pos ? <View style={[styles.marcadorDestino, pos]} /> : null;
            })()
          : null}
      </View>

      <Text style={styles.paso}>{t('ubicacion.origen_escanea_h3', 'Origen — escanea el QR del satélite donde estás')}</Text>
      <TouchableOpacity style={styles.scanBtn} onPress={() => pedirEscaneo('gps-origen')}>
        <Text style={styles.scanBtnText}>{t('ubicacion.escanear_qr_satelite_btn', 'Escanear QR de satélite')}</Text>
      </TouchableOpacity>
      {origen ? <Text style={styles.detalle}>{t('ubicacion.origen_lbl', 'Origen: {{e}}', {e: origen.etiqueta})}</Text> : null}

      <Text style={styles.paso}>{t('ubicacion.destino_articulo_h3', 'Destino (artículo)')}</Text>
      <View style={styles.formRow}>
        <TextInput
          style={[styles.input, styles.inputFlex]}
          placeholder={t('ubicacion.codigo_nombre_articulo_ph', 'Código o nombre del artículo')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          value={qDestino}
          onChangeText={setQDestino}
          onSubmitEditing={() => buscarDestino(qDestino)}
        />
        <TouchableOpacity style={styles.button} onPress={() => buscarDestino(qDestino)}>
          <Text style={styles.buttonText}>{t('ubicacion.buscar_btn', 'Buscar')}</Text>
        </TouchableOpacity>
      </View>
      {destino ? <Text style={styles.detalle}>{t('ubicacion.destino_lbl', 'Destino: {{e}}', {e: destino.etiqueta})}</Text> : null}

      {aviso ? <Text style={styles.error}>{aviso}</Text> : null}

      <TouchableOpacity
        style={[
          styles.button,
          styles.buttonFull,
          (calculando || !origen || !destino) && styles.buttonDisabled,
        ]}
        onPress={iniciarRuta}
        disabled={calculando || !origen || !destino}>
        {calculando ? (
          <ActivityIndicator color={colors.bg} />
        ) : (
          <Text style={styles.buttonText}>{t('ubicacion.iniciar_ruta_btn', 'Iniciar ruta')}</Text>
        )}
      </TouchableOpacity>
      {distanciaRuta != null ? (
        <Text style={styles.detalle}>{t('ubicacion.distancia_celdas', 'Distancia: {{d}} celdas', {d: distanciaRuta})}</Text>
      ) : null}
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
  tabBody: {flex: 1},
  formRow: {flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8},
  form: {padding: 16},
  paso: {color: colors.textDim, fontWeight: '700', fontSize: 12, marginBottom: 6, marginTop: 4},
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
  inputFlex: {flex: 1, marginBottom: 0},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonFull: {marginTop: 4},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  scanBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginBottom: 8,
  },
  scanBtnText: {color: colors.bg, fontWeight: '800', fontSize: 13},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
  error: {color: colors.danger, marginBottom: 8, fontSize: 12},
  ok: {color: colors.ok, marginBottom: 8, fontSize: 12},
  detalle: {color: colors.textDim, marginTop: 4, marginBottom: 8, fontSize: 12},
  mapaContenedor: {
    height: 260,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    overflow: 'hidden',
    marginBottom: 12,
  },
  marcadorOrigen: {
    position: 'absolute',
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.ok,
    marginLeft: -6,
    marginTop: -6,
    borderWidth: 2,
    borderColor: colors.bg,
  },
  marcadorDestino: {
    position: 'absolute',
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.danger,
    marginLeft: -7,
    marginTop: -7,
    borderWidth: 2,
    borderColor: colors.bg,
  },
  rutaPunto: {
    position: 'absolute',
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.cyan,
    marginLeft: -3,
    marginTop: -3,
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
  plantaNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  plantaBtn: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  plantaBtnText: {color: colors.cyan, fontSize: 22, fontWeight: '800'},
  plantaTitulo: {flex: 1, alignItems: 'center'},
  plantaTipo: {color: colors.textDim, fontSize: 11, fontWeight: '700', marginTop: -4},
});
