import type {NativeStackScreenProps} from '@react-navigation/native-stack';

/**
 * Rutas de la pila principal (usuario autenticado). Rediseño móvil (Grupo A): solo quedan las
 * pantallas que resuelven un paso físico que escritorio no puede ejecutar (ver
 * `src/api/capabilities.ts` para el porqué de cada una).
 */
export type AppStackParamList = {
  Dashboard: undefined;
  /** `volverA` (opcional): si se indica, cada lectura se devuelve como `{escaneado}` a esa ruta en vez
   * de encolarse en el Outbox de stock (comportamiento por defecto). */
  Scanner: {volverA?: keyof AppStackParamList} | undefined;
  Stock: undefined;
  Correo: undefined;
  Mermas: undefined;
  Ubicacion: {escaneado?: string} | undefined;
  Etiquetas: undefined;
  Logistica: {escaneado?: string} | undefined;
  LogisticaPicking: {id_documento: string};
  Distribucion: undefined;
  GMAO: {escaneado?: string} | undefined;
  Calidad: undefined;
  SAT: undefined;
  Transporte: undefined;
  Obrador: undefined;
  MRP: undefined;
  /** Única pieza de autoservicio RRHH que vuelve al móvil (decisión explícita, ver
   * `api/gastosViaje.ts`): fotografiar el ticket + lectura automática por IA. Nóminas/vacaciones/
   * documentos pendientes de firma se quedan en escritorio (Portal del Empleado). */
  GastosViaje: undefined;
  /** Info Artículo (petición explícita): solo "Buscar artículo" e "Imagen artículo" de escritorio —
   * ver `api/capabilities.ts` para el porqué de incluir "Buscar", que no es puramente físico. */
  InfoArticulo: undefined;
  /** Ruta OCULTA (no aparece en el catálogo de capacidades ni en el Dashboard): solo se entra desde
   * `EscaneoRemotoOverlay` al aceptar un aviso de escaneo remoto. `idSolicitud` llega al aceptar;
   * `escaneado` se añade al volver de `Scanner` (mismo mecanismo `volverA` que el resto de pantallas). */
  EscaneoRemotoFulfill: {idSolicitud: string; escaneado?: string};
  /** Placeholder honesto para capacidades del catálogo cuyo endpoint aún no existe en el backend. */
  Proximamente: {label: string; endpoint: string; icon: string};
};

export type DashboardProps = NativeStackScreenProps<AppStackParamList, 'Dashboard'>;
export type ScannerProps = NativeStackScreenProps<AppStackParamList, 'Scanner'>;
export type StockProps = NativeStackScreenProps<AppStackParamList, 'Stock'>;
export type CorreoProps = NativeStackScreenProps<AppStackParamList, 'Correo'>;
export type MermasProps = NativeStackScreenProps<AppStackParamList, 'Mermas'>;
export type UbicacionProps = NativeStackScreenProps<AppStackParamList, 'Ubicacion'>;
export type EtiquetasProps = NativeStackScreenProps<AppStackParamList, 'Etiquetas'>;
export type LogisticaProps = NativeStackScreenProps<AppStackParamList, 'Logistica'>;
export type LogisticaPickingProps = NativeStackScreenProps<AppStackParamList, 'LogisticaPicking'>;
export type DistribucionProps = NativeStackScreenProps<AppStackParamList, 'Distribucion'>;
export type GMAOProps = NativeStackScreenProps<AppStackParamList, 'GMAO'>;
export type CalidadProps = NativeStackScreenProps<AppStackParamList, 'Calidad'>;
export type SATProps = NativeStackScreenProps<AppStackParamList, 'SAT'>;
export type TransporteProps = NativeStackScreenProps<AppStackParamList, 'Transporte'>;
export type ObradorProps = NativeStackScreenProps<AppStackParamList, 'Obrador'>;
export type MRPProps = NativeStackScreenProps<AppStackParamList, 'MRP'>;
export type GastosViajeProps = NativeStackScreenProps<AppStackParamList, 'GastosViaje'>;
export type InfoArticuloProps = NativeStackScreenProps<AppStackParamList, 'InfoArticulo'>;
export type EscaneoRemotoFulfillProps = NativeStackScreenProps<AppStackParamList, 'EscaneoRemotoFulfill'>;
export type ProximamenteProps = NativeStackScreenProps<AppStackParamList, 'Proximamente'>;
