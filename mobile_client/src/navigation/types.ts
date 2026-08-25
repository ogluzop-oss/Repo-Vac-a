import type {NativeStackScreenProps} from '@react-navigation/native-stack';

/** Rutas de la pila principal (usuario autenticado). */
export type AppStackParamList = {
  Dashboard: undefined;
  Scanner: undefined;
  Directorio: undefined;
  Comunicaciones: undefined;
  Clientes: undefined;
  Proveedores: undefined;
  Pedidos: undefined;
  Stock: undefined;
  Notificaciones: undefined;
  Agenda: undefined;
  Tareas: undefined;
  Incidencias: undefined;
  Workflow: undefined;
  Documentos: undefined;
  Timeline: undefined;
  /** Placeholder honesto para capacidades del catálogo cuyo endpoint aún no existe en el backend. */
  Proximamente: {label: string; endpoint: string; icon: string};
};

export type DashboardProps = NativeStackScreenProps<AppStackParamList, 'Dashboard'>;
export type ScannerProps = NativeStackScreenProps<AppStackParamList, 'Scanner'>;
export type DirectorioProps = NativeStackScreenProps<AppStackParamList, 'Directorio'>;
export type ComunicacionesProps = NativeStackScreenProps<AppStackParamList, 'Comunicaciones'>;
export type ClientesProps = NativeStackScreenProps<AppStackParamList, 'Clientes'>;
export type ProveedoresProps = NativeStackScreenProps<AppStackParamList, 'Proveedores'>;
export type PedidosProps = NativeStackScreenProps<AppStackParamList, 'Pedidos'>;
export type StockProps = NativeStackScreenProps<AppStackParamList, 'Stock'>;
export type NotificacionesProps = NativeStackScreenProps<AppStackParamList, 'Notificaciones'>;
export type AgendaProps = NativeStackScreenProps<AppStackParamList, 'Agenda'>;
export type TareasProps = NativeStackScreenProps<AppStackParamList, 'Tareas'>;
export type IncidenciasProps = NativeStackScreenProps<AppStackParamList, 'Incidencias'>;
export type WorkflowProps = NativeStackScreenProps<AppStackParamList, 'Workflow'>;
export type DocumentosProps = NativeStackScreenProps<AppStackParamList, 'Documentos'>;
export type TimelineProps = NativeStackScreenProps<AppStackParamList, 'Timeline'>;
export type ProximamenteProps = NativeStackScreenProps<AppStackParamList, 'Proximamente'>;
