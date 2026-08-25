/**
 * Notificaciones dirigidas al usuario autenticado (por id o por rol).
 *
 * Espejo de `src/api/routers/notifications.py`:
 *   GET  /notifications             -> Notificacion[] (solo pendientes/no leídas)
 *   POST /notifications/<id>/leida  -> marca como leída
 */
import {api} from './client';

export interface Notificacion {
  id: number;
  tipo: string;
  modulo: string | null;
  titulo: string;
  mensaje: string;
  prioridad: 'baja' | 'normal' | 'alta' | 'critica';
  ref_entidad: string | null;
  ref_id: string | null;
  fecha_creacion: string;
}

export async function listarNotificaciones(): Promise<Notificacion[]> {
  const r = await api.get<Notificacion[]>('/notifications');
  return Array.isArray(r.json) ? r.json : [];
}

export async function marcarLeida(id: number): Promise<boolean> {
  const r = await api.post(`/notifications/${id}/leida`);
  return r.ok;
}
