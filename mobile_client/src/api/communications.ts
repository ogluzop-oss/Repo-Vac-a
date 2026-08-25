/**
 * Comunicaciones corporativas (CCP).
 *
 * Espejo de `src/api/routers/communications.py`:
 *   GET  /communications?canal=  -> fila cruda de `ccp_comunicaciones` (ver migración 0124)
 *   POST /communications {destinatario, asunto, cuerpo, contexto?} -> Resultado (ver ccp/modelo.py)
 *
 * `enviar` exige el permiso `comunicaciones.enviar`; si el usuario no lo tiene, el backend responde
 * 403 y este módulo lo propaga tal cual (sin intentar simular un envío).
 */
import {api} from './client';

export interface ComunicacionHistorial {
  id: number;
  com_id: string | null;
  id_empresa: string | null;
  canal: string;
  estado: string;
  destinatario: string | null;
  asunto: string | null;
  contexto: string | null;
  usuario: string | null;
  detalle: string | null;
  creado: string;
  actualizado: string | null;
}

export interface EnviarComunicacionInput {
  destinatario: string;
  asunto: string;
  cuerpo: string;
  contexto?: string;
}

export interface ResultadoEnvio {
  ok: boolean;
  canal: string;
  com_id: string | null;
  estado: string;
  mensaje: string;
}

/** Historial de comunicaciones de la empresa (más recientes primero). */
export async function historial(canal?: string): Promise<ComunicacionHistorial[]> {
  const r = await api.get<ComunicacionHistorial[]>('/communications', {
    params: {canal},
  });
  return Array.isArray(r.json) ? r.json : [];
}

export type EnviarResult =
  | {kind: 'ok'; data: ResultadoEnvio}
  | {kind: 'error'; status: number; mensaje: string};

/** Envía (o prepara) una comunicación. Requiere el permiso `comunicaciones.enviar`. */
export async function enviar(input: EnviarComunicacionInput): Promise<EnviarResult> {
  const r = await api.post<ResultadoEnvio & {error?: string}>('/communications', {
    body: input,
  });
  if (r.status === 200 && r.json?.ok) {
    return {kind: 'ok', data: r.json};
  }
  return {
    kind: 'error',
    status: r.status,
    mensaje: r.json?.mensaje || r.json?.error || 'No se pudo enviar la comunicación.',
  };
}
