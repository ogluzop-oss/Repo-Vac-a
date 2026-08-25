/**
 * Incidencias OPERATIVAS de tienda/almacén (roturas, limpieza, averías, incidencias con clientes…).
 * DISTINTO de incidentes de seguridad (fuera del alcance del móvil).
 *
 * Espejo de `src/api/routers/incidents.py`:
 *   GET  /incidents?estado=        -> Incidencia[] (las mías: reportadas o asignadas a mí)
 *   POST /incidents {tipo,titulo,...} -> {id}
 *   POST /incidents/<id>/estado {estado,resolucion?} -> marca el nuevo estado
 */
import {api} from './client';

export type EstadoIncidencia = 'abierta' | 'en_curso' | 'resuelta' | 'cancelada';
export type PrioridadIncidencia = 'baja' | 'normal' | 'alta' | 'critica';

export interface Incidencia {
  id: number;
  tipo: string;
  titulo: string;
  descripcion: string | null;
  prioridad: PrioridadIncidencia;
  estado: EstadoIncidencia;
  ubicacion: string | null;
  reportado_por: number | null;
  asignado_a: number | null;
  resolucion: string | null;
  fecha_creacion: string;
  fecha_cierre: string | null;
}

export const TIPOS_INCIDENCIA = [
  'limpieza',
  'rotura',
  'equipamiento',
  'seguridad_fisica',
  'cliente',
  'otro',
] as const;

export async function listarIncidencias(estado?: EstadoIncidencia): Promise<Incidencia[]> {
  const r = await api.get<Incidencia[]>('/incidents', {params: {estado}});
  return Array.isArray(r.json) ? r.json : [];
}

export interface NuevaIncidencia {
  tipo: string;
  titulo: string;
  descripcion?: string;
  prioridad?: PrioridadIncidencia;
  ubicacion?: string;
}

export async function reportarIncidencia(input: NuevaIncidencia): Promise<number | null> {
  const r = await api.post<{id?: number}>('/incidents', {body: input});
  return r.status === 201 ? (r.json?.id ?? null) : null;
}

export async function cambiarEstadoIncidencia(
  id: number,
  estado: EstadoIncidencia,
  resolucion?: string,
): Promise<boolean> {
  const r = await api.post(`/incidents/${id}/estado`, {body: {estado, resolucion}});
  return r.ok;
}
