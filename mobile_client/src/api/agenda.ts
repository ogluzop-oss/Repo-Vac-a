/**
 * Calendario/agenda corporativa (eventos + participantes).
 *
 * Espejo de `src/api/routers/agenda.py`:
 *   GET  /agenda?desde=&hasta=  -> Evento[] (mes en curso si no se indica rango)
 *   POST /agenda {titulo, inicio, fin?, tipo?, descripcion?, participantes?} -> {id}
 */
import {api} from './client';

export type TipoEvento = 'evento' | 'reunion' | 'cita' | 'recordatorio' | 'auditoria' | 'revision';

export interface EventoAgenda {
  id: number;
  titulo: string;
  tipo: TipoEvento;
  inicio: string;
  fin: string | null;
  descripcion: string | null;
  creado_por: number | null;
  ref_entidad: string | null;
  ref_id: string | null;
}

export async function listarAgenda(desde?: string, hasta?: string): Promise<EventoAgenda[]> {
  const r = await api.get<EventoAgenda[]>('/agenda', {params: {desde, hasta}});
  return Array.isArray(r.json) ? r.json : [];
}

export interface NuevoEvento {
  titulo: string;
  inicio: string;
  fin?: string;
  tipo?: TipoEvento;
  descripcion?: string;
}

export async function crearEvento(input: NuevoEvento): Promise<number | null> {
  const r = await api.post<{id?: number; error?: string}>('/agenda', {body: input});
  return r.status === 201 ? (r.json?.id ?? null) : null;
}
