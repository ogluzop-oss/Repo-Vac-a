/**
 * Dashboard / Menú principal. Construye las tarjetas a partir del catálogo de capacidades
 * (espejo de core.py) y muestra el estado offline-first: nº de operaciones pendientes en el
 * Outbox y acción de sincronizar contra la REST API.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {CAPABILITIES, capacidadesVisibles, type Capability} from '@/api/capabilities';
import {obtenerBadges, type Badges} from '@/api/badges';
import {api} from '@/api/client';
import Badge from '@/components/Badge';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import {outbox} from '@/db/sync';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import type {DashboardProps} from '@/navigation/types';

// Módulos con badge de notificación (mismo criterio que el círculo rojo del menú de escritorio) —
// solo las capacidades que `GET /activity/badges` sabe contar (ver `src/api/routers/activity.py`).
const BADGE_INTERVALO_MS = 60_000; // mismo refresco periódico que usa el escritorio (60s)

export default function DashboardScreen({navigation}: DashboardProps) {
  const {t} = useTranslation();
  const {usuario, empresa, signOut} = useAuth();
  const [pendientes, setPendientes] = useState(0);
  const [online, setOnline] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [badges, setBadges] = useState<Badges>({
    logistica: 0,
    pedidos: 0,
    etiquetas: 0,
  });
  // Catálogo filtrado por la edición/vertical de esta instalación (Obrador vs Producción/MRP, etc.)
  // — arranca con el catálogo completo para no mostrar la lista vacía mientras llega la respuesta.
  const [capacidades, setCapacidades] = useState<Capability[]>(CAPABILITIES);

  const refrescar = useCallback(async () => {
    setPendientes(await outbox.contarPendientes());
    try {
      const r = await api.get('/system/health', {auth: false});
      setOnline(r.ok);
    } catch {
      setOnline(false);
    }
    setBadges(await obtenerBadges());
  }, []);

  useEffect(() => {
    refrescar();
    const unsub = navigation.addListener('focus', refrescar);
    const intervalo = setInterval(refrescar, BADGE_INTERVALO_MS);
    return () => {
      unsub();
      clearInterval(intervalo);
    };
  }, [navigation, refrescar]);

  useEffect(() => {
    let vivo = true;
    capacidadesVisibles().then(c => {
      if (vivo) {
        setCapacidades(c);
      }
    });
    return () => {
      vivo = false;
    };
  }, []);

  const sincronizar = useCallback(async () => {
    setBusy(true);
    try {
      await outbox.sincronizar();
    } finally {
      setBusy(false);
      refrescar();
    }
  }, [refrescar]);

  const abrirCapacidad = useCallback(
    (cap: Capability) => {
      if (cap.key === 'stock') {
        navigation.navigate('Stock');
      } else if (cap.key === 'correo') {
        navigation.navigate('Correo');
      } else if (cap.key === 'mermas') {
        navigation.navigate('Mermas');
      } else if (cap.key === 'ubicacion') {
        navigation.navigate('Ubicacion');
      } else if (cap.key === 'etiquetas') {
        navigation.navigate('Etiquetas');
      } else if (cap.key === 'logistica') {
        navigation.navigate('Logistica');
      } else if (cap.key === 'pedidos') {
        navigation.navigate('Distribucion');
      } else if (cap.key === 'gmao') {
        navigation.navigate('GMAO');
      } else if (cap.key === 'calidad') {
        navigation.navigate('Calidad');
      } else if (cap.key === 'sat') {
        navigation.navigate('SAT');
      } else if (cap.key === 'transporte') {
        navigation.navigate('Transporte');
      } else if (cap.key === 'obrador') {
        navigation.navigate('Obrador');
      } else if (cap.key === 'mrp') {
        navigation.navigate('MRP');
      } else if (cap.key === 'gastos_viaje') {
        navigation.navigate('GastosViaje');
      } else if (cap.key === 'info_articulo') {
        navigation.navigate('InfoArticulo');
      } else {
        // El resto del catálogo aún no tiene endpoint REST en el backend (ver core.py):
        // se muestra un estado honesto en vez de datos simulados.
        navigation.navigate('Proximamente', {
          label: t(`cap.${cap.key}`, cap.label),
          endpoint: cap.endpoint,
          icon: cap.icon,
        });
      }
    },
    [navigation],
  );

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.hello}>
            {usuario ? t('dash.hola_nombre', 'Hola, {{n}}', {n: usuario}) : t('dash.hola', 'Hola')}
          </Text>
          <Text style={styles.sub}>
            {t('dash.empresa', 'Empresa {{e}}', {e: empresa ?? '—'})} ·{' '}
            <Text style={{color: online === false ? colors.danger : colors.ok}}>
              {online === null
                ? t('dash.comprobando', 'comprobando…')
                : online
                  ? t('dash.en_linea', 'en línea')
                  : t('dash.sin_conexion', 'sin conexión')}
            </Text>
          </Text>
        </View>
        <View style={styles.headerAcciones}>
          <LanguageSwitcher />
          <TouchableOpacity onPress={signOut}>
            <Text style={styles.logout}>{t('dash.salir', 'Salir')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.syncBar}>
        <Text style={styles.syncText}>
          {pendientes > 0
            ? t('dash.operaciones_pendientes', '{{n}} operación(es) pendiente(s) de sincronizar',
                {n: pendientes})
            : t('dash.todo_sincronizado', 'Todo sincronizado')}
        </Text>
        <TouchableOpacity
          style={[styles.syncBtn, (busy || pendientes === 0) && styles.syncBtnOff]}
          onPress={sincronizar}
          disabled={busy || pendientes === 0}>
          <Text style={styles.syncBtnText}>
            {busy ? t('dash.sincronizando', 'Sincronizando…') : t('dash.sincronizar', 'Sincronizar')}
          </Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={capacidades}
        keyExtractor={item => item.key}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.grid}
        refreshControl={
          <RefreshControl refreshing={false} onRefresh={refrescar} tintColor={colors.cyan} />
        }
        renderItem={({item}) => (
          <TouchableOpacity style={styles.tile} onPress={() => abrirCapacidad(item)}>
            <Badge n={badges[item.key as keyof Badges] ?? 0} />
            <Text style={styles.tileIcon}>{item.icon}</Text>
            <Text style={styles.tileLabel}>{t(`cap.${item.key}`, item.label)}</Text>
          </TouchableOpacity>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
  },
  hello: {color: colors.text, fontSize: 20, fontWeight: '800'},
  sub: {color: colors.textDim, marginTop: 2},
  headerAcciones: {flexDirection: 'row', alignItems: 'center', gap: 10},
  logout: {color: colors.danger, fontWeight: '700'},
  syncBar: {
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  syncText: {color: colors.textDim, flex: 1, marginRight: 8},
  syncBtn: {backgroundColor: colors.cyan, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8},
  syncBtnOff: {opacity: 0.5},
  syncBtnText: {color: colors.bg, fontWeight: '800'},
  grid: {padding: 12, paddingBottom: 96},
  row: {justifyContent: 'space-between'},
  tile: {
    flex: 1,
    margin: 6,
    backgroundColor: colors.panel,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
    minHeight: 110,
  },
  tileIcon: {fontSize: 28},
  tileLabel: {color: colors.text, fontWeight: '800', marginTop: 8, fontSize: 15},
});
