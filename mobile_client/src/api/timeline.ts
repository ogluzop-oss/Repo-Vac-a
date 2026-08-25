/**
 * Cronología unificada de comunicaciones (salientes de cualquier canal + correos entrantes).
 *
 * Espejo de `src/api/routers/timeline.py`:
 *   GET /timeline?correo=  -> EventoTimeline[]
 */
import {api} from './client';

export interface EventoTimeline {
  sentido: 'saliente' | 'entrante';
  canal: string;
  fecha: string;
  asunto: string | null;
  contraparte: string | null;
  com_id: string | null;
  estado: string;
  conversation_id: number | null;
}

export async function listarTimeline(correo?: string): Promise<EventoTimeline[]> {
  const r = await api.get<EventoTimeline[]>('/timeline', {params: {correo}});
  return Array.isArray(r.json) ? r.json : [];
}
