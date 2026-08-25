/**
 * Navegación raíz. Conmuta entre el flujo de autenticación (Login/MFA) y la app autenticada
 * (Dashboard + Scanner) según el estado de `useAuth`.
 */
import React from 'react';
import {ActivityIndicator, View, StyleSheet} from 'react-native';
import {NavigationContainer, DefaultTheme} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import LoginScreen from '@/screens/LoginScreen';
import DashboardScreen from '@/screens/DashboardScreen';
import ScannerScreen from '@/screens/ScannerScreen';
import DirectorioScreen from '@/screens/DirectorioScreen';
import ComunicacionesScreen from '@/screens/ComunicacionesScreen';
import ClientesScreen from '@/screens/ClientesScreen';
import ProveedoresScreen from '@/screens/ProveedoresScreen';
import PedidosScreen from '@/screens/PedidosScreen';
import ProximamenteScreen from '@/screens/ProximamenteScreen';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import type {AppStackParamList} from './types';

const Stack = createNativeStackNavigator<AppStackParamList>();

const navTheme = {
  ...DefaultTheme,
  colors: {...DefaultTheme.colors, background: colors.bg, card: colors.bg, text: colors.text},
};

export default function RootNavigator() {
  const {status} = useAuth();

  if (status === 'loading') {
    return (
      <View style={styles.splash}>
        <ActivityIndicator color={colors.cyan} size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      {status === 'signedIn' ? (
        <Stack.Navigator screenOptions={{headerShown: false}}>
          <Stack.Screen name="Dashboard" component={DashboardScreen} />
          <Stack.Screen name="Scanner" component={ScannerScreen} />
          <Stack.Screen name="Directorio" component={DirectorioScreen} />
          <Stack.Screen name="Comunicaciones" component={ComunicacionesScreen} />
          <Stack.Screen name="Clientes" component={ClientesScreen} />
          <Stack.Screen name="Proveedores" component={ProveedoresScreen} />
          <Stack.Screen name="Pedidos" component={PedidosScreen} />
          <Stack.Screen name="Proximamente" component={ProximamenteScreen} />
        </Stack.Navigator>
      ) : (
        // signedOut + mfaRequired → la propia LoginScreen alterna a la vista de código MFA.
        <LoginScreen />
      )}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center'},
});
