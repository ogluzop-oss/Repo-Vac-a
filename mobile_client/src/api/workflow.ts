/**
 * Bandeja de aprobaciones (motor BPM/workflow transversal).
 *
 * Espejo de `src/api/routers/workflow.py`:
 *   GET  /workflow/tasks?estado=          -> TareaAprobacion[] (solo las que puedo resolver)
 *   POST /workflow/tasks/<id>/aprobar     -> {estado, instancia, tarea}
 *   POST /workflow/tasks/<id>/rechazar    -> {estado, instancia}
 */
import {api} from './client';

export interface TareaAprobacion {
  id: number;
  id_instancia: number;
  id_paso: number;
  entidad: string;
  entidad_id: string;
  estado: 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'CANCELADA';
  asignado_rol: string | null;
  asignado_usuario: number | null;
  permiso_requerido: string | null;
  comentario: string | null;
  fecha_creacion: string;
}

export async function listarBandeja(): Promise<TareaAprobacion[]> {
  const r = await api.get<TareaAprobacion[]>('/workflow/tasks');
  return Array.isArray(r.json) ? r.json : [];
}

export type ResolverResult =
  | {kind: 'ok'; estado: string}
  | {kind: 'error'; status: number; mensaje: string};

export async function aprobarTarea(id: number, comentario?: string): Promise<ResolverResult> {
  const r = await api.post<{estado?: string; error?: string}>(`/workflow/tasks/${id}/aprobar`, {
    body: {comentario},
  });
  if (r.ok && r.json?.estado) {
    return {kind: 'ok', estado: r.json.estado};
  }
  return {kind: 'error', status: r.status, mensaje: r.json?.error ?? 'No se pudo aprobar.'};
}

export async function rechazarTarea(id: number, comentario?: string): Promise<ResolverResult> {
  const r = await api.post<{estado?: string; error?: string}>(`/workflow/tasks/${id}/rechazar`, {
    body: {comentario},
  });
  if (r.ok && r.json?.estado) {
    return {kind: 'ok', estado: r.json.estado};
  }
  return {kind: 'error', status: r.status, mensaje: r.json?.error ?? 'No se pudo rechazar.'};
}
