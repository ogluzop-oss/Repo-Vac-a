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
import {CAPABILITIES, type Capability} from '@/api/capabilities';
import {api} from '@/api/client';
import {outbox} from '@/db/sync';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import type {DashboardProps} from '@/navigation/types';

export default function DashboardScreen({navigation}: DashboardProps) {
  const {usuario, empresa, signOut} = useAuth();
  const [pendientes, setPendientes] = useState(0);
  const [online, setOnline] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const refrescar = useCallback(async () => {
    setPendientes(await outbox.contarPendientes());
    try {
      const r = await api.get('/system/health', {auth: false});
      setOnline(r.ok);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    refrescar();
    const unsub = navigation.addListener('focus', refrescar);
    return unsub;
  }, [navigation, refrescar]);

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
      } else if (cap.key === 'directorio') {
        navigation.navigate('Directorio');
      } else if (cap.key === 'ccp') {
        navigation.navigate('Comunicaciones');
      } else if (cap.key === 'clientes') {
        navigation.navigate('Clientes');
      } else if (cap.key === 'proveedores') {
        navigation.navigate('Proveedores');
      } else if (cap.key === 'pedidos') {
        navigation.navigate('Pedidos');
      } else if (cap.key === 'notificaciones') {
        navigation.navigate('Notificaciones');
      } else if (cap.key === 'agenda') {
        navigation.navigate('Agenda');
      } else if (cap.key === 'tareas') {
        navigation.navigate('Tareas');
      } else {
        // El resto del catálogo aún no tiene endpoint REST en el backend (ver core.py):
        // se muestra un estado honesto en vez de datos simulados.
        navigation.navigate('Proximamente', {
          label: cap.label,
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
          <Text style={styles.hello}>Hola{usuario ? `, ${usuario}` : ''}</Text>
          <Text style={styles.sub}>
            Empresa {empresa ?? '—'} ·{' '}
            <Text style={{color: online === false ? colors.danger : colors.ok}}>
              {online === null ? 'comprobando…' : online ? 'en línea' : 'sin conexión'}
            </Text>
          </Text>
        </View>
        <TouchableOpacity onPress={signOut}>
          <Text style={styles.logout}>Salir</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.syncBar}>
        <Text style={styles.syncText}>
          {pendientes > 0
            ? `${pendientes} operación(es) pendiente(s) de sincronizar`
            : 'Todo sincronizado'}
        </Text>
        <TouchableOpacity
          style={[styles.syncBtn, (busy || pendientes === 0) && styles.syncBtnOff]}
          onPress={sincronizar}
          disabled={busy || pendientes === 0}>
          <Text style={styles.syncBtnText}>{busy ? 'Sincronizando…' : 'Sincronizar'}</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={CAPABILITIES}
        keyExtractor={item => item.key}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.grid}
        refreshControl={
          <RefreshControl refreshing={false} onRefresh={refrescar} tintColor={colors.cyan} />
        }
        renderItem={({item}) => (
          <TouchableOpacity style={styles.tile} onPress={() => abrirCapacidad(item)}>
            <Text style={styles.tileIcon}>{item.icon}</Text>
            <Text style={styles.tileLabel}>{item.label}</Text>
            <Text style={styles.tileEndpoint}>{item.endpoint}</Text>
          </TouchableOpacity>
        )}
      />

      <TouchableOpacity
        style={styles.scanFab}
        onPress={() => navigation.navigate('Scanner')}>
        <Text style={styles.scanFabText}>Escanear</Text>
      </TouchableOpacity>
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
  tileEndpoint: {color: colors.textDim, fontSize: 11, marginTop: 2},
  scanFab: {
    position: 'absolute',
    right: 20,
    bottom: 24,
    backgroundColor: colors.cyan,
    borderRadius: 30,
    paddingHorizontal: 22,
    paddingVertical: 14,
    shadowColor: colors.cyan,
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 6,
  },
  scanFabText: {color: colors.bg, fontWeight: '900', letterSpacing: 1},
});
