/**
 * Tareas asignadas al usuario autenticado.
 *
 * Espejo de `src/api/routers/tasks.py`:
 *   GET  /tasks?estado=            -> Tarea[] (todas las asignadas a mí)
 *   POST /tasks {titulo, ...}      -> {id}   (sin `asignado_a`, se autoasigna a mí)
 *   POST /tasks/<id>/estado {estado} -> marca el nuevo estado
 */
import {api} from './client';

export type EstadoTarea = 'pendiente' | 'en_progreso' | 'bloqueada' | 'completada' | 'cancelada';

export interface Tarea {
  id: number;
  titulo: string;
  descripcion: string | null;
  asignado_a: number | null;
  creado_por: number | null;
  estado: EstadoTarea;
  prioridad: 'baja' | 'normal' | 'alta' | 'critica';
  vencimiento: string | null;
  fecha_creacion: string;
  fecha_cierre: string | null;
}

export async function listarTareas(estado?: EstadoTarea): Promise<Tarea[]> {
  const r = await api.get<Tarea[]>('/tasks', {params: {estado}});
  return Array.isArray(r.json) ? r.json : [];
}

export async function crearTarea(titulo: string, prioridad: Tarea['prioridad'] = 'normal'): Promise<number | null> {
  const r = await api.post<{id?: number}>('/tasks', {body: {titulo, prioridad}});
  return r.status === 201 ? (r.json?.id ?? null) : null;
}

export async function cambiarEstadoTarea(id: number, estado: EstadoTarea): Promise<boolean> {
  const r = await api.post(`/tasks/${id}/estado`, {body: {estado}});
  return r.ok;
}
