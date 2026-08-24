import type {NativeStackScreenProps} from '@react-navigation/native-stack';

/** Rutas de la pila principal (usuario autenticado). */
export type AppStackParamList = {
  Dashboard: undefined;
  Scanner: undefined;
};

export type DashboardProps = NativeStackScreenProps<AppStackParamList, 'Dashboard'>;
export type ScannerProps = NativeStackScreenProps<AppStackParamList, 'Scanner'>;
