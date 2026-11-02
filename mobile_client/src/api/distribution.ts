/**
 * Pedidos — dos dominios distintos en la misma pantalla móvil (fusión pedida por el usuario):
 *  · B2B (pedidos mayoristas): SOLO picking — caminar el almacén siguiendo la ruta óptima para recoger
 *    un pedido de cliente. Crear el pedido / elegir transportista y expedir se quedan en escritorio.
 *  · Online (tienda web/Click&Collect): ciclo Preparar→Enviar→Entregar sobre `online_orders_service`
 *    — motor completamente distinto del B2B, solo comparten pantalla.
 *
 * Espejo de `src/api/routers/distribution.py`.
 */
import {api} from './client';

export interface Pedido {
  id: number;
  id_cliente: number;
  numero: string;
  estado: string;
  total: number;
  id_venta: number | null;
  observaciones: string | null;
  usuario: string | null;
  fecha: string;
}

export async function listarPedidos(estado?: string): Promise<Pedido[]> {
  const r = await api.get<Pedido[]>('/distribution/orders', {
    params: estado ? {estado} : undefined,
  });
  return Array.isArray(r.json) ? r.json : [];
}

export async function prepararPicking(
  idPedido: number,
): Promise<{ok: boolean; id_picking?: number; error?: string}> {
  const r = await api.post<{ok: boolean; id_picking?: number; error?: string}>(
    `/distribution/orders/${idPedido}/picking`,
  );
  return r.json ?? {ok: false, error: 'No se pudo preparar el picking.'};
}

export interface LineaRuta {
  id: number;
  codigo_articulo: string;
  cantidad: number;
  ubicacion: string | null;
  estado: string;
  orden: number;
}

export interface RutaPicking {
  lineas: LineaRuta[];
  resumen: {lineas: number; pasillos: number};
}

export async function obtenerRuta(idPicking: number): Promise<RutaPicking> {
  const r = await api.get<RutaPicking>(`/distribution/picking/${idPicking}/route`);
  return r.json ?? {lineas: [], resumen: {lineas: 0, pasillos: 0}};
}

// ── Pedidos ONLINE (tienda web/Click&Collect) ───────────────────────────────────────────────────────
export interface PedidoOnline {
  id_pedido: string;
  cliente_nombre: string | null;
  cliente_telefono: string | null;
  total: string;
  estado: 'PENDIENTE' | 'PAGADO' | 'PREPARANDO' | 'ENVIADO' | 'ENTREGADO' | 'CANCELADO';
  fecha: string;
  transportista: string | null;
  seguimiento: string | null;
  /** true si este empleado lo ve porque su ALMACÉN es el origen del encargo (el destino es OTRA
   * tienda, no la suya) — lo añade el backend (`/distribution/online-orders`) solo cuando puede
   * resolver la tienda del empleado autenticado. Ausente/false para un pedido local normal. */
  es_encargo_origen?: boolean;
  /** Nombre (o código) de la tienda de destino, solo presente cuando `es_encargo_origen` es true. */
  tienda_destino_nombre?: string | null;
}

export async function listarPedidosOnline(estado?: string): Promise<PedidoOnline[]> {
  const r = await api.get<PedidoOnline[]>('/distribution/online-orders', {
    params: estado ? {estado} : undefined,
  });
  return Array.isArray(r.json) ? r.json : [];
}

export async function marcarPedidoPreparado(idPedido: string): Promise<{ok: boolean}> {
  const r = await api.post<{ok?: boolean}>(`/distribution/online-orders/${idPedido}/prepare`);
  return {ok: !!r.json?.ok};
}

export async function marcarPedidoEnviado(
  idPedido: string,
  transportista: string,
  seguimiento: string,
): Promise<{ok: boolean}> {
  const r = await api.post<{ok?: boolean}>(`/distribution/online-orders/${idPedido}/ship`, {
    body: {transportista, seguimiento},
  });
  return {ok: !!r.json?.ok};
}

export async function marcarPedidoEntregado(idPedido: string): Promise<{ok: boolean}> {
  const r = await api.post<{ok?: boolean}>(`/distribution/online-orders/${idPedido}/deliver`);
  return {ok: !!r.json?.ok};
}
