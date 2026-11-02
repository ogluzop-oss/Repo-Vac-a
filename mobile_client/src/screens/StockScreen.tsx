/**
 * Stock (capacidad "stock" -> /api/v1/stock/inventory/*). Rediseño móvil (Grupo A): de las 5 pestañas
 * que tenía este módulo, SOLO el recuento físico exige presencia real en el lineal (hay que estar
 * delante de la estantería para saber cuánto hay) — Stock tienda/Almacén/Editar Stock/Lotes eran
 * búsquedas y formularios idénticos a lo que ya hace escritorio, y se retiraron. Solo permite registrar
 * un recuento sobre una sesión de inventario YA abierta en escritorio (crear/abrir/cerrar sesiones
 * sigue siendo una decisión de escritorio).
 */
import React, {useCallback, useEffect, useState} from 'react';
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
import {
  inventariosAbiertos,
  lineasInventario,
  registrarRecuento,
  type InventarioAbierto,
  type InventarioDetalle,
} from '@/api/stock';
import {colors} from '@/theme/colors';
import type {StockProps} from '@/navigation/types';

export default function StockScreen({navigation}: StockProps) {
  const {t} = useTranslation();
  const [sesiones, setSesiones] = useState<InventarioAbierto[]>([]);
  const [seleccion, setSeleccion] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<InventarioDetalle | null>(null);
  const [cargandoSesiones, setCargandoSesiones] = useState(true);
  const [codigo, setCodigo] = useState('');
  const [contado, setContado] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  const cargarSesiones = useCallback(async () => {
    setCargandoSesiones(true);
    try {
      setSesiones(await inventariosAbiertos());
    } finally {
      setCargandoSesiones(false);
    }
  }, []);

  useEffect(() => {
    cargarSesiones();
  }, [cargarSesiones]);

  const cargarLineas = useCallback(async (id: number) => {
    setDetalle(await lineasInventario(id));
  }, []);

  useEffect(() => {
    if (seleccion != null) {
      cargarLineas(seleccion);
    }
  }, [seleccion, cargarLineas]);

  const contar = useCallback(async () => {
    if (seleccion == null) {
      return;
    }
    if (!codigo.trim()) {
      setAviso({ok: false, texto: t('stock.indica_codigo', 'Indica el código del artículo.')});
      return;
    }
    const c = Number(contado);
    if (!Number.isFinite(c) || c < 0) {
      setAviso({ok: false, texto: t('stock.cantidad_invalida', 'La cantidad contada debe ser un número válido.')});
      return;
    }
    setEnviando(true);
    setAviso(null);
    try {
      const r = await registrarRecuento(seleccion, {
        codigo: codigo.trim(),
        contado: c,
        ...(observaciones.trim() ? {observaciones: observaciones.trim()} : {}),
      });
      if (r.ok) {
        setAviso({ok: true, texto: t('stock.registrado_ok', 'Inventario registrado.')});
        setCodigo('');
        setContado('');
        setObservaciones('');
        await cargarLineas(seleccion);
      } else {
        setAviso({ok: false, texto: r.error || t('stock.no_se_pudo_registrar', 'No se pudo registrar el inventario.')});
      }
    } catch {
      setAviso({ok: false, texto: t('stock.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [seleccion, codigo, contado, observaciones, cargarLineas, t]);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('common.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{t('stock.titulo', 'Inventario')}</Text>
        <TouchableOpacity onPress={() => navigation.navigate('Scanner')}>
          <Text style={styles.scanLink}>{t('stock.escanear_link', 'Escanear')}</Text>
        </TouchableOpacity>
      </View>

      {cargandoSesiones ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.cyan} />
        </View>
      ) : !sesiones.length ? (
        <View style={styles.centered}>
          <Text style={styles.hint}>{t('stock.sin_inventarios_abiertos', 'No hay inventarios abiertos ahora mismo.')}</Text>
        </View>
      ) : (
        <View style={styles.tabBody}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
            <View style={styles.tabsRow}>
              {sesiones.map(s => (
                <TouchableOpacity
                  key={s.id}
                  style={[styles.chip, seleccion === s.id && styles.chipActivo]}
                  onPress={() => setSeleccion(s.id)}>
                  <Text style={[styles.chipTexto, seleccion === s.id && styles.chipTextoActivo]}>
                    {s.nombre}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>

          {seleccion != null ? (
            <>
              <View style={styles.form}>
                <View style={styles.formRow}>
                  <TextInput
                    style={[styles.input, styles.inputFlex]}
                    placeholder={t('stock.codigo_articulo_ph', 'Código artículo')}
                    placeholderTextColor={colors.textDim}
                    autoCapitalize="none"
                    value={codigo}
                    onChangeText={setCodigo}
                  />
                  <TextInput
                    style={[styles.input, {width: 90}]}
                    placeholder={t('stock.contado_ph', 'Contado')}
                    placeholderTextColor={colors.textDim}
                    keyboardType="numeric"
                    value={contado}
                    onChangeText={setContado}
                  />
                </View>
                <TextInput
                  style={styles.input}
                  placeholder={t('stock.observaciones_opc_ph', 'Observaciones (opcional)')}
                  placeholderTextColor={colors.textDim}
                  value={observaciones}
                  onChangeText={setObservaciones}
                />
                <TouchableOpacity
                  style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
                  onPress={contar}
                  disabled={enviando}>
                  {enviando ? (
                    <ActivityIndicator color={colors.bg} />
                  ) : (
                    <Text style={styles.buttonText}>{t('stock.registrar_btn', 'Registrar')}</Text>
                  )}
                </TouchableOpacity>
                {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
              </View>

              <FlatList
                data={detalle?.lineas ?? []}
                keyExtractor={item => String(item.id)}
                contentContainerStyle={styles.list}
                ListEmptyComponent={
                  <View style={styles.centered}>
                    <Text style={styles.hint}>{t('stock.sin_conteos', 'Sin conteos todavía en esta sesión.')}</Text>
                  </View>
                }
                renderItem={({item}) => (
                  <View style={styles.card}>
                    <Text style={styles.nombre}>{item.codigo_articulo}</Text>
                    <Text style={styles.detalle}>
                      {t('stock.esperado_contado_diferencia',
                         'Esperado {{e}} · Contado {{c}} · Diferencia {{d}}',
                         {e: item.stock_esperado, c: item.stock_contado ?? '—', d: item.diferencia ?? '—'})}
                    </Text>
                    {item.observaciones ? (
                      <Text style={styles.detalle}>{t('stock.obs_lbl', 'Obs.: {{o}}', {o: item.observaciones})}</Text>
                    ) : null}
                  </View>
                )}
              />
            </>
          ) : (
            <View style={styles.centered}>
              <Text style={styles.hint}>{t('stock.elige_inventario', 'Elige un inventario para registrar conteos.')}</Text>
            </View>
          )}
        </View>
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
  scanLink: {color: colors.cyan, fontSize: 14, fontWeight: '700'},
  tabsScroll: {flexGrow: 0, marginBottom: 8},
  tabsRow: {flexDirection: 'row', gap: 8, paddingHorizontal: 16},
  tabBody: {flex: 1},
  formRow: {flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8},
  form: {paddingHorizontal: 16, paddingTop: 4},
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
  buttonFull: {width: '100%'},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  hint: {color: colors.textDim, textAlign: 'center'},
  error: {color: colors.danger, textAlign: 'center', marginBottom: 8},
  ok: {color: colors.ok, textAlign: 'center', marginBottom: 8},
  list: {padding: 16, paddingTop: 4},
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  nombre: {color: colors.text, fontWeight: '800', fontSize: 15},
  detalle: {color: colors.textDim, marginTop: 4, fontSize: 12},
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
});
