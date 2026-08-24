/**
 * Capacidades de la plataforma móvil — espejo de `src/services/mobile/core.py`.
 *
 * Mapa `capacidad -> recurso REST oficial` que las alimenta (SIEMPRE /api/v1, nunca SQL). El
 * Dashboard construye su menú a partir de este catálogo, de modo que añadir una capacidad en el
 * servidor se refleja aquí con una sola línea.
 */

export interface Capability {
  key: string;
  /** Etiqueta legible para el menú. */
  label: string;
  /** Ruta REST (relativa a /api/v1) que alimenta la capacidad. */
  endpoint: string;
  /** Emoji/símbolo para la tarjeta (placeholder hasta integrar un set de iconos). */
  icon: string;
}

/** Coincide 1:1 con CAPACIDADES de core.py (mismos endpoints). */
export const CAPABILITIES: Capability[] = [
  {key: 'dashboard', label: 'Estado del sistema', endpoint: '/system/health', icon: '📊'},
  {key: 'notificaciones', label: 'Notificaciones', endpoint: '/notifications', icon: '🔔'},
  {key: 'agenda', label: 'Agenda', endpoint: '/agenda', icon: '📅'},
  {key: 'directorio', label: 'Directorio', endpoint: '/contacts', icon: '📇'},
  {key: 'clientes', label: 'Clientes', endpoint: '/customers', icon: '👥'},
  {key: 'proveedores', label: 'Proveedores', endpoint: '/suppliers', icon: '🏭'},
  {key: 'pedidos', label: 'Pedidos', endpoint: '/orders', icon: '🧾'},
  {key: 'stock', label: 'Stock', endpoint: '/stock', icon: '📦'},
  {key: 'incidencias', label: 'Incidencias', endpoint: '/incidents', icon: '⚠️'},
  {key: 'tareas', label: 'Tareas', endpoint: '/tasks', icon: '✅'},
  {key: 'workflow', label: 'Aprobaciones', endpoint: '/workflow', icon: '🔀'},
  {key: 'documentos', label: 'Documentos', endpoint: '/documents', icon: '📄'},
  {key: 'ccp', label: 'Comunicaciones', endpoint: '/communications', icon: '💬'},
  {key: 'timeline', label: 'Actividad', endpoint: '/timeline', icon: '🕒'},
];

export const PLATFORM = {
  version: '1.0.0',
  offlineFirst: true,
} as const;
