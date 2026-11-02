/**
 * Correo (capacidad "correo" -> /api/v1/correo/*). Espejo de `src/api/routers/correo.py`: bandeja
 * unificada (Gmail solo lectura + circulares/encuestas internas), detalle, reenvío, respuesta
 * AUTENTICADA (sin contraseña, reutiliza la identidad del token), compositor básico (Nuevo
 * mensaje/Nueva encuesta) con Para/CC/Cco real, marcado de leído, y las 5 carpetas reales
 * (Borradores/Programados/Papelera/Pospuestos/Importantes) + Enviados — paridad completa con
 * escritorio (ver el docstring de `screens/CorreoScreen.tsx` para el razonamiento y los
 * compromisos honestos de esta ronda, p. ej. el selector de fecha/hora sin date-picker nativo).
 */
import {api} from './client';

export type TipoMensaje = 'gmail' | 'circular' | 'encuesta';

export interface MensajeBandeja {
  tipo: TipoMensaje;
  id: number;
  remitente_o_emisor: string;
  asunto_o_titulo: string;
  fecha: string | null;
  leido: boolean;
}

/** `GET /correo/bandeja` puede devolver la lista simple o, si algún día se activa la convención de
 * paginación (`?limit=...`), el sobre `{data, total, ...}` — aquí NUNCA se activa esa convención
 * (no se pasan esos parámetros), así que siempre llega la lista simple; se normaliza igualmente por
 * si acaso. */
export async function bandeja(): Promise<MensajeBandeja[]> {
  const r = await api.get<MensajeBandeja[] | {data: MensajeBandeja[]}>('/correo/bandeja');
  if (Array.isArray(r.json)) {
    return r.json;
  }
  if (r.json && Array.isArray((r.json as {data: MensajeBandeja[]}).data)) {
    return (r.json as {data: MensajeBandeja[]}).data;
  }
  return [];
}

export interface GmailDetalle {
  id: number;
  remitente: string;
  asunto: string;
  cuerpo: string | null;
  fecha: string | null;
  leido: number;
}

export async function gmailDetalle(id: number): Promise<GmailDetalle | null> {
  const r = await api.get<GmailDetalle>(`/correo/gmail/${id}`);
  return r.ok ? r.json : null;
}

export interface Destinatario {
  usuario_id: number | null;
  usuario_nombre: string | null;
  tipo: 'PARA' | 'CC' | 'CCO';
  reenviado_por: string | null;
  leido: number;
  creado: string;
}

export interface Confirmacion {
  id: number;
  usuario_nombre: string;
  id_centro: string | null;
  comentario: string | null;
  creado: string;
}

export interface CircularDetalle {
  id: number;
  titulo: string;
  cuerpo: string;
  creador_nombre: string;
  creado: string;
  estado: string;
  confirmaciones: Confirmacion[];
  destinatarios: Destinatario[];
}

export async function circularDetalle(id: number): Promise<CircularDetalle | null> {
  const r = await api.get<CircularDetalle>(`/correo/circular/${id}`);
  return r.ok ? r.json : null;
}

export type TipoPregunta = 'OPCIONES' | 'TEXTO';

export interface OpcionPregunta {
  id: number;
  orden: number;
  texto: string;
}

export interface PreguntaEncuestaDetalle {
  id: number;
  orden: number;
  texto: string;
  tipo: TipoPregunta;
  opciones: OpcionPregunta[];
}

export interface EncuestaDetalle {
  id: number;
  titulo: string;
  intro: string;
  creador_nombre: string;
  creado: string;
  estado: string;
  preguntas: PreguntaEncuestaDetalle[];
  destinatarios: Destinatario[];
}

export async function encuestaDetalle(id: number): Promise<EncuestaDetalle | null> {
  const r = await api.get<EncuestaDetalle>(`/correo/encuesta/${id}`);
  return r.ok ? r.json : null;
}

/** Las 3 formas de destinatario que acepta el backend (Para/CC/Cco) — igual que
 * `services.comunicacion_interna.usuarios_internos.expandir_destinatarios`. */
export type DestinatarioEntrada =
  | {usuario_id: number; nombre?: string; tipo: 'PARA' | 'CC' | 'CCO'}
  | {centro_codigo: string; tipo: 'PARA' | 'CC' | 'CCO'}
  | {email_externo: string; nombre?: string; tipo: 'PARA' | 'CC' | 'CCO'};

export interface ResultadoEnvio {
  ok: boolean;
  id?: number;
  error?: string;
  externos_fallidos?: string[];
}

export async function crearCircular(datos: {
  titulo: string;
  cuerpo: string;
  destinatarios: DestinatarioEntrada[];
}): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/circular', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo crear la circular.'};
}

export interface PreguntaNueva {
  texto: string;
  tipo: TipoPregunta;
  opciones?: string[];
}

export async function crearEncuesta(datos: {
  titulo: string;
  intro: string;
  preguntas: PreguntaNueva[];
  destinatarios: DestinatarioEntrada[];
}): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/encuesta', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo crear la encuesta.'};
}

export async function reenviarCircular(
  id: number,
  destinatarios: DestinatarioEntrada[],
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/circular/${id}/reenviar`, {
    body: {destinatarios},
  });
  return r.json ?? {ok: false, error: 'No se pudo reenviar la circular.'};
}

export async function reenviarEncuesta(
  id: number,
  destinatarios: DestinatarioEntrada[],
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/encuesta/${id}/reenviar`, {
    body: {destinatarios},
  });
  return r.json ?? {ok: false, error: 'No se pudo reenviar la encuesta.'};
}

export async function marcarLeidoGmail(id: number): Promise<boolean> {
  const r = await api.post<{ok?: boolean}>(`/correo/gmail/${id}/leido`);
  return !!r.json?.ok;
}

export async function marcarLeidoCircular(id: number): Promise<boolean> {
  const r = await api.post<{ok?: boolean}>(`/correo/circular/${id}/leido`);
  return !!r.json?.ok;
}

export async function marcarLeidoEncuesta(id: number): Promise<boolean> {
  const r = await api.post<{ok?: boolean}>(`/correo/encuesta/${id}/leido`);
  return !!r.json?.ok;
}

export type OrigenSugerencia = 'usuario' | 'centro' | 'externo';

export interface SugerenciaDestinatario {
  origen: OrigenSugerencia;
  icono: string;
  texto: string;
  tooltip: string;
  identidad: Record<string, unknown>;
}

export async function sugerenciasDestinatarios(q: string): Promise<SugerenciaDestinatario[]> {
  if (!q.trim()) {
    return [];
  }
  const r = await api.get<SugerenciaDestinatario[]>('/correo/destinatarios/sugerencias', {
    params: {q: q.trim()},
  });
  return Array.isArray(r.json) ? r.json : [];
}

// ── Responder (identidad YA AUTENTICADA del token — sin contraseña) ────────────────────────────
// Paralelo de `confirmar_lectura`/`responder_encuesta` (escritorio, terminal compartido): aquí el
// JWT YA prueba quién eres, así que no tiene sentido re-pedir una contraseña para un comentario o
// una respuesta rápida. `respuestas` tiene la misma forma que espera `encuestas.
// responder_encuesta_autenticado`: {id_pregunta: {opciones:[id_opcion,...], otro, texto}}.
export interface RespuestaPregunta {
  opciones?: number[];
  otro?: string;
  texto?: string;
}

export async function responderCircular(
  id: number,
  comentario: string,
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/circular/${id}/responder`, {
    body: {comentario},
  });
  return r.json ?? {ok: false, error: 'No se pudo responder.'};
}

export async function responderEncuesta(
  id: number,
  respuestas: Record<number, RespuestaPregunta>,
  comentario = '',
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/encuesta/${id}/responder`, {
    body: {respuestas, comentario},
  });
  return r.json ?? {ok: false, error: 'No se pudo responder.'};
}

// ── Las 5 carpetas reales + Enviados (mismo backend/misma normalización que escritorio) ────────
async function _lista(ruta: string): Promise<MensajeBandeja[]> {
  const r = await api.get<MensajeBandeja[]>(ruta);
  return Array.isArray(r.json) ? r.json : [];
}

export const enviados = () => _lista('/correo/enviados');
export const borradores = () => _lista('/correo/borradores');
export const programados = () => _lista('/correo/programados');
export const papelera = () => _lista('/correo/papelera');
export const pospuestos = () => _lista('/correo/pospuestos');
export const importantes = () => _lista('/correo/importantes');

/** Mueve a la papelera (LOCAL, soft — nunca toca Gmail real). */
export async function moverPapelera(tipo: TipoMensaje, id: number): Promise<boolean> {
  const ruta = tipo === 'gmail' ? `/correo/gmail/${id}/papelera`
    : tipo === 'circular' ? `/correo/circular/${id}/papelera`
    : `/correo/encuesta/${id}/papelera`;
  const r = await api.post<{ok?: boolean}>(ruta);
  return !!r.json?.ok;
}

export async function restaurarDePapelera(tipo: TipoMensaje, id: number): Promise<boolean> {
  const ruta = tipo === 'gmail' ? `/correo/gmail/${id}/restaurar`
    : tipo === 'circular' ? `/correo/circular/${id}/restaurar`
    : `/correo/encuesta/${id}/restaurar`;
  const r = await api.post<{ok?: boolean}>(ruta);
  return !!r.json?.ok;
}

export async function marcarImportante(
  tipo: TipoMensaje,
  id: number,
  valor: boolean,
): Promise<boolean> {
  const ruta = tipo === 'gmail' ? `/correo/gmail/${id}/importante`
    : tipo === 'circular' ? `/correo/circular/${id}/importante`
    : `/correo/encuesta/${id}/importante`;
  const r = await api.post<{ok?: boolean}>(ruta, {body: {valor}});
  return !!r.json?.ok;
}

/** `hasta` en ISO (`YYYY-MM-DDTHH:MM`). */
export async function posponer(tipo: TipoMensaje, id: number, hasta: string): Promise<boolean> {
  const ruta = tipo === 'gmail' ? `/correo/gmail/${id}/posponer`
    : tipo === 'circular' ? `/correo/circular/${id}/posponer`
    : `/correo/encuesta/${id}/posponer`;
  const r = await api.post<{ok?: boolean}>(ruta, {body: {hasta}});
  return !!r.json?.ok;
}

/** Solo circular/encuesta (Gmail no tiene "programado": su sync es de solo lectura). */
export async function cancelarProgramacion(
  tipo: 'circular' | 'encuesta',
  id: number,
): Promise<ResultadoEnvio> {
  const ruta = tipo === 'circular'
    ? `/correo/circular/${id}/cancelar_programacion`
    : `/correo/encuesta/${id}/cancelar_programacion`;
  const r = await api.post<ResultadoEnvio>(ruta);
  return r.json ?? {ok: false, error: 'No se pudo cancelar la programación.'};
}

export async function eliminarBorrador(
  tipo: 'circular' | 'encuesta',
  id: number,
): Promise<ResultadoEnvio> {
  const ruta = tipo === 'circular'
    ? `/correo/circular/${id}/eliminar_borrador`
    : `/correo/encuesta/${id}/eliminar_borrador`;
  const r = await api.post<ResultadoEnvio>(ruta);
  return r.json ?? {ok: false, error: 'No se pudo eliminar el borrador.'};
}

export interface DatosBorradorCircular {
  id_circular?: number;
  titulo: string;
  cuerpo: string;
  destinatarios?: DestinatarioEntrada[];
}

export async function guardarBorradorCircular(
  datos: DatosBorradorCircular,
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/circular/borrador', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo guardar el borrador.'};
}

export interface DatosBorradorEncuesta {
  id_encuesta?: number;
  titulo: string;
  intro: string;
  preguntas?: PreguntaNueva[];
  destinatarios?: DestinatarioEntrada[];
}

export async function guardarBorradorEncuesta(
  datos: DatosBorradorEncuesta,
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/encuesta/borrador', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo guardar el borrador.'};
}

export async function publicarBorradorCircular(
  id: number,
  datos: {titulo?: string; cuerpo?: string; destinatarios: DestinatarioEntrada[]},
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/circular/${id}/publicar`, {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo publicar.'};
}

export async function publicarBorradorEncuesta(
  id: number,
  datos: {
    titulo?: string;
    intro?: string;
    preguntas?: PreguntaNueva[];
    destinatarios: DestinatarioEntrada[];
  },
): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>(`/correo/encuesta/${id}/publicar`, {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo publicar.'};
}

export async function programarCircular(datos: {
  id_circular_borrador?: number;
  titulo?: string;
  cuerpo?: string;
  fecha_programada: string;
  destinatarios: DestinatarioEntrada[];
}): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/circular/programar', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo programar el envío.'};
}

export async function programarEncuesta(datos: {
  id_encuesta_borrador?: number;
  titulo?: string;
  intro?: string;
  preguntas?: PreguntaNueva[];
  fecha_programada: string;
  destinatarios: DestinatarioEntrada[];
}): Promise<ResultadoEnvio> {
  const r = await api.post<ResultadoEnvio>('/correo/encuesta/programar', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo programar el envío.'};
}
