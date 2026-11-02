/**
 * Logística — SOLO Recepción (escanear palet al llegar) y Preparación/Picking (checklist mientras se
 * camina el almacén). Traspasos (crear)/Expediciones/Incidencias/Historial se quedan en escritorio
 * (formularios/listados sin componente físico, ver el rediseño móvil Grupo A). Espejo de
 * `src/api/routers/logistics.py`.
 *
 * El centro receptor al recibir se resuelve SIEMPRE en el servidor desde el perfil del usuario
 * (`centro_codigo`) — el cliente nunca lo envía ni lo elige.
 */
import {api} from './client';

export type EstadoTraspaso = 'EN PREPARACION';

export interface Traspaso {
  id_documento: string;
  origen: string;
  destino: string;
  fecha_envio: string;
  estado: string;
  agencia: string | null;
  bultos: number;
}

export interface LineaTraspaso {
  id_linea: number;
  id_documento: string;
  id_pale: string;
  id_visual: string;
  codigo: string;
  nombre: string;
  cantidad: number;
  cantidad_recibida: number;
  estado_linea: string;
  peso_bulto: number | null;
  picking_completo: number;
}

export interface TraspasoDetalle {
  id_documento: string;
  origen: string;
  destino: string;
  fecha_envio: string;
  fecha_recepcion: string | null;
  estado: string;
  agencia: string | null;
  observaciones: string | null;
  usuario: string | null;
  usuario_receptor: string | null;
  resumen: string | null;
  lineas: LineaTraspaso[];
}

export interface ItemEsperado {
  codigo: string;
  nombre: string;
  cantidad: number;
  origen: string;
  id_documento: string;
  id_visual: string;
  id_pale: string;
}

export async function listarTraspasos(opts: {
  estado?: EstadoTraspaso;
  limite?: number;
} = {}): Promise<Traspaso[]> {
  const {estado = 'EN PREPARACION', limite = 100} = opts;
  const r = await api.get<Traspaso[]>('/logistics/transfers', {
    params: {estado, limite},
  });
  return Array.isArray(r.json) ? r.json : [];
}

export async function obtenerTraspaso(idDocumento: string): Promise<TraspasoDetalle | null> {
  const r = await api.get<TraspasoDetalle>(`/logistics/transfers/${encodeURIComponent(idDocumento)}`);
  return r.ok ? r.json : null;
}

export async function itemsEsperadosPalet(idPale: string): Promise<ItemEsperado[]> {
  const r = await api.get<ItemEsperado[]>(`/logistics/pallets/${encodeURIComponent(idPale)}/expected`);
  return Array.isArray(r.json) ? r.json : [];
}

export async function recibirPalet(
  idPale: string,
): Promise<{ok: true} | {ok: false; motivo: string}> {
  const r = await api.post<{ok?: boolean; motivo?: string; error?: string}>('/logistics/receive', {
    body: {id_pale: idPale},
  });
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, motivo: r.json?.motivo || r.json?.error || 'error'};
}

export async function marcarPicking(
  idDocumento: string,
  idLinea: number,
  pickeado: boolean,
): Promise<boolean> {
  const r = await api.post(
    `/logistics/transfers/${encodeURIComponent(idDocumento)}/lines/${idLinea}/pick`,
    {body: {pickeado}},
  );
  return r.ok;
}

export async function confirmarPicking(
  idDocumento: string,
): Promise<{ok: true} | {ok: false; motivo: string; faltan?: number}> {
  const r = await api.post<{ok?: boolean; motivo?: string; faltan?: number}>(
    `/logistics/transfers/${encodeURIComponent(idDocumento)}/confirm-picking`,
  );
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, motivo: r.json?.motivo || 'error', faltan: r.json?.faltan};
}
