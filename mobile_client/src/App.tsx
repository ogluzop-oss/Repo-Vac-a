/**
 * Componente raíz de la app móvil de Smart Manager.
 *
 * Providers: SafeArea + Auth. Inicializa la base de datos local (SQLite / Outbox) al arrancar.
 * La navegación decide entre Login y la app autenticada.
 */
import React, {useEffect, useState} from 'react';
import {StatusBar} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {I18nextProvider} from 'react-i18next';
import {AuthProvider} from '@/store/AuthContext';
import RootNavigator from '@/navigation';
import EscaneoRemotoOverlay from '@/components/EscaneoRemotoOverlay';
import AntihurtoOverlay from '@/components/AntihurtoOverlay';
import {getDatabase} from '@/db/database';
import {colors} from '@/theme/colors';
import i18n, {iniciarI18n} from '@/i18n';

export default function App() {
  const [i18nListo, setI18nListo] = useState(false);

  useEffect(() => {
    // Abre/crea la BD local y garantiza el esquema del Outbox lo antes posible.
    getDatabase().catch(() => {
      // La app sigue funcionando en modo solo-online si SQLite no está disponible.
    });
  }, []);

  useEffect(() => {
    iniciarI18n().finally(() => setI18nListo(true));
  }, []);

  if (!i18nListo) {
    // Arranque casi instantáneo (solo lee AsyncStorage + el idioma activo): sin splash propio,
    // evita parpadeo de texto sin traducir en el primer frame.
    return null;
  }

  return (
    <I18nextProvider i18n={i18n}>
      <SafeAreaProvider>
        <StatusBar barStyle="light-content" backgroundColor={colors.bg} />
        <AuthProvider>
          <RootNavigator />
          <EscaneoRemotoOverlay />
          <AntihurtoOverlay />
        </AuthProvider>
      </SafeAreaProvider>
    </I18nextProvider>
  );
}
