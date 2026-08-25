import type {NativeStackScreenProps} from '@react-navigation/native-stack';

/** Rutas de la pila principal (usuario autenticado). */
export type AppStackParamList = {
  Dashboard: undefined;
  Scanner: undefined;
  Directorio: undefined;
  Comunicaciones: undefined;
  /** Placeholder honesto para capacidades del catálogo cuyo endpoint aún no existe en el backend. */
  Proximamente: {label: string; endpoint: string; icon: string};
};

export type DashboardProps = NativeStackScreenProps<AppStackParamList, 'Dashboard'>;
export type ScannerProps = NativeStackScreenProps<AppStackParamList, 'Scanner'>;
export type DirectorioProps = NativeStackScreenProps<AppStackParamList, 'Directorio'>;
export type ComunicacionesProps = NativeStackScreenProps<AppStackParamList, 'Comunicaciones'>;
export type ProximamenteProps = NativeStackScreenProps<AppStackParamList, 'Proximamente'>;
