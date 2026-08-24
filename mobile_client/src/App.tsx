/**
 * Componente raíz de la app móvil de Smart Manager.
 *
 * Providers: SafeArea + Auth. Inicializa la base de datos local (SQLite / Outbox) al arrancar.
 * La navegación decide entre Login y la app autenticada.
 */
import React, {useEffect} from 'react';
import {StatusBar} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {AuthProvider} from '@/store/AuthContext';
import RootNavigator from '@/navigation';
import {getDatabase} from '@/db/database';
import {colors} from '@/theme/colors';

export default function App() {
  useEffect(() => {
    // Abre/crea la BD local y garantiza el esquema del Outbox lo antes posible.
    getDatabase().catch(() => {
      // La app sigue funcionando en modo solo-online si SQLite no está disponible.
    });
  }, []);

  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />
      <AuthProvider>
        <RootNavigator />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
