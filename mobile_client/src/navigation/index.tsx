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
import StockScreen from '@/screens/StockScreen';
import CorreoScreen from '@/screens/CorreoScreen';
import MermasScreen from '@/screens/MermasScreen';
import UbicacionScreen from '@/screens/UbicacionScreen';
import EtiquetasScreen from '@/screens/EtiquetasScreen';
import LogisticaScreen from '@/screens/LogisticaScreen';
import LogisticaPickingScreen from '@/screens/LogisticaPickingScreen';
import DistribucionPickingScreen from '@/screens/DistribucionPickingScreen';
import GMAOScreen from '@/screens/GMAOScreen';
import CalidadScreen from '@/screens/CalidadScreen';
import SATScreen from '@/screens/SATScreen';
import TransporteScreen from '@/screens/TransporteScreen';
import ObradorScreen from '@/screens/ObradorScreen';
import MRPScreen from '@/screens/MRPScreen';
import GastosViajeScreen from '@/screens/GastosViajeScreen';
import InfoArticuloScreen from '@/screens/InfoArticuloScreen';
import EscaneoRemotoFulfillScreen from '@/screens/EscaneoRemotoFulfillScreen';
import ProximamenteScreen from '@/screens/ProximamenteScreen';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import {navigationRef} from './navigationRef';
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
    <NavigationContainer ref={navigationRef} theme={navTheme}>
      {status === 'signedIn' ? (
        <Stack.Navigator screenOptions={{headerShown: false}}>
          <Stack.Screen name="Dashboard" component={DashboardScreen} />
          <Stack.Screen name="Scanner" component={ScannerScreen} />
          <Stack.Screen name="Stock" component={StockScreen} />
          <Stack.Screen name="Correo" component={CorreoScreen} />
          <Stack.Screen name="Mermas" component={MermasScreen} />
          <Stack.Screen name="Ubicacion" component={UbicacionScreen} />
          <Stack.Screen name="Etiquetas" component={EtiquetasScreen} />
          <Stack.Screen name="Logistica" component={LogisticaScreen} />
          <Stack.Screen name="LogisticaPicking" component={LogisticaPickingScreen} />
          <Stack.Screen name="Distribucion" component={DistribucionPickingScreen} />
          <Stack.Screen name="GMAO" component={GMAOScreen} />
          <Stack.Screen name="Calidad" component={CalidadScreen} />
          <Stack.Screen name="SAT" component={SATScreen} />
          <Stack.Screen name="Transporte" component={TransporteScreen} />
          <Stack.Screen name="Obrador" component={ObradorScreen} />
          <Stack.Screen name="MRP" component={MRPScreen} />
          <Stack.Screen name="GastosViaje" component={GastosViajeScreen} />
          <Stack.Screen name="InfoArticulo" component={InfoArticuloScreen} />
          <Stack.Screen name="EscaneoRemotoFulfill" component={EscaneoRemotoFulfillScreen} />
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
