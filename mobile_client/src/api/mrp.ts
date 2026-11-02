/**
 * MRP (capacidad "mrp" -> /api/v1/mrp/orders). Rediseño móvil · Grupo B, módulo 7 (último): consumir
 * los materiales previstos de una OF y registrar producción CON foto obligatoria — repetible, una foto
 * por lote producido (`referencia=f"OFPROD:{id}"`, no por OF). Consumir materiales no lleva foto: no
 * hay ningún dato de operario ni artefacto fotografiable en ese instante. Espejo de
 * `src/api/routers/mrp.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface OrdenFabricacion {
  id: number;
  codigo: string;
  articulo_final: string;
  cantidad: number;
  cantidad_producida: number;
  estado: string;
  lote_destino: string | null;
}

export interface Consumo {
  id: number;
  componente: string;
  cantidad_plan: number;
  cantidad_real: number;
  consumido: number;
}

export interface Produccion {
  id: number;
  cantidad: number;
  lote: string | null;
  fecha: string;
  id_documento_foto: string | null;
}

export async function listarOrdenes(): Promise<OrdenFabricacion[]> {
  const r = await api.get<OrdenFabricacion[]>('/mrp/orders');
  return Array.isArray(r.json) ? r.json : [];
}

export async function obtenerOrden(id: number): Promise<OrdenFabricacion | null> {
  const r = await api.get<OrdenFabricacion>(`/mrp/orders/${id}`);
  return r.ok ? r.json : null;
}

async function accionSimple(
  path: string,
): Promise<{ok: true; estado?: string} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; estado?: string; error?: string}>(path);
  if (r.ok && r.json?.ok) {
    return {ok: true, estado: r.json.estado};
  }
  return {ok: false, error: r.json?.error || 'No se pudo completar la acción.'};
}

export const iniciarOrden = (id: number) => accionSimple(`/mrp/orders/${id}/start`);
export const pausarOrden = (id: number) => accionSimple(`/mrp/orders/${id}/pause`);
export const finalizarOrden = (id: number) => accionSimple(`/mrp/orders/${id}/finish`);

export async function listarConsumos(id: number): Promise<Consumo[]> {
  const r = await api.get<Consumo[]>(`/mrp/orders/${id}/consumptions`);
  return Array.isArray(r.json) ? r.json : [];
}

export async function consumirMateriales(
  id: number,
): Promise<{ok: true; faltantes: unknown[]} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; faltantes?: unknown[]; error?: string}>(
    `/mrp/orders/${id}/consume`,
  );
  if (r.ok && r.json?.ok) {
    return {ok: true, faltantes: r.json.faltantes || []};
  }
  return {ok: false, error: r.json?.error || 'No se pudieron consumir los materiales.'};
}

export async function listarProducciones(id: number): Promise<Produccion[]> {
  const r = await api.get<Produccion[]>(`/mrp/orders/${id}/productions`);
  return Array.isArray(r.json) ? r.json : [];
}

export async function registrarProduccion(
  id: number,
  cantidad: number,
  fotoUri: string,
): Promise<{ok: true; lote: string | null} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'produccion.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; lote?: string; error?: string}>(
    `/mrp/orders/${id}/produce`,
    'foto',
    archivo,
    {cantidad},
  );
  if (r.ok && r.json?.ok) {
    return {ok: true, lote: r.json.lote ?? null};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la producción.'};
}
