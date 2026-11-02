/**
 * SAT (capacidad "sat" -> /api/v1/sat/tickets). Rediseño móvil · Grupo B, módulo 4: registrar una
 * intervención técnica CON foto obligatoria — un ticket puede llevar varias intervenciones (visitas)
 * antes de resolverse, cada una con su propia foto. Sin firma: no existe hoy ningún flujo de
 * conformidad de cliente en SAT (ver contexto del plan). Espejo de `src/api/routers/sat.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface Ticket {
  id: number;
  codigo: string;
  asunto: string;
  descripcion: string | null;
  prioridad: string;
  estado: string;
  tecnico: number | null;
}

export interface Intervencion {
  id: number;
  id_ticket: number;
  tecnico: number | null;
  tipo: string;
  descripcion: string | null;
  horas: number;
  fecha: string;
  id_documento_foto: string | null;
}

export async function listarTickets(): Promise<Ticket[]> {
  const r = await api.get<Ticket[]>('/sat/tickets');
  return Array.isArray(r.json) ? r.json : [];
}

export async function iniciarTicket(
  idTicket: number,
): Promise<{ok: true; estado: string} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; estado?: string; error?: string}>(
    `/sat/tickets/${idTicket}/start`,
  );
  if (r.ok && r.json?.ok && r.json.estado) {
    return {ok: true, estado: r.json.estado};
  }
  return {ok: false, error: r.json?.error || 'No se pudo iniciar el ticket.'};
}

export async function listarIntervenciones(idTicket: number): Promise<Intervencion[]> {
  const r = await api.get<Intervencion[]>(`/sat/tickets/${idTicket}/interventions`);
  return Array.isArray(r.json) ? r.json : [];
}

export interface NuevaIntervencion {
  tipo: 'visita' | 'taller' | 'remota' | 'telefonica';
  descripcion?: string;
  horas: number;
  /** URI local de la foto de la intervención (obligatoria). */
  fotoUri: string;
}

export async function registrarIntervencion(
  idTicket: number,
  datos: NuevaIntervencion,
): Promise<{ok: true; intervencion: number} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: datos.fotoUri, name: 'intervencion.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; intervencion?: number; error?: string}>(
    `/sat/tickets/${idTicket}/interventions`,
    'foto',
    archivo,
    {
      tipo: datos.tipo,
      horas: datos.horas,
      ...(datos.descripcion ? {descripcion: datos.descripcion} : {}),
    },
  );
  if (r.ok && r.json?.ok && r.json.intervencion) {
    return {ok: true, intervencion: r.json.intervencion};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la intervención.'};
}

export async function resolverTicket(
  idTicket: number,
): Promise<{ok: true; estado: string} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; estado?: string; error?: string}>(
    `/sat/tickets/${idTicket}/resolve`,
  );
  if (r.ok && r.json?.ok && r.json.estado) {
    return {ok: true, estado: r.json.estado};
  }
  return {ok: false, error: r.json?.error || 'No se pudo resolver el ticket.'};
}
