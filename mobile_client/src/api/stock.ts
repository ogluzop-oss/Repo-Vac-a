/**
 * Stock — SOLO recuento físico de inventario (rediseño móvil, Grupo A). Espejo de
 * `src/api/routers/stock.py` (endpoints `/stock/inventory/*` únicamente; el resto de `/stock/*` sigue
 * existiendo en el backend para escritorio pero ya no se consume desde móvil).
 */
import {api} from './client';

export interface InventarioAbierto {
  id: number;
  nombre: string;
  estado: string;
  id_almacen: number | null;
  usuario_creacion: string | null;
}

export async function inventariosAbiertos(): Promise<InventarioAbierto[]> {
  const r = await api.get<InventarioAbierto[]>('/stock/inventory/open');
  return Array.isArray(r.json) ? r.json : [];
}

export interface LineaInventario {
  id: number;
  codigo_articulo: string;
  stock_esperado: number;
  stock_contado: number | null;
  diferencia: number | null;
  observaciones: string | null;
}

export interface InventarioDetalle {
  cabecera: InventarioAbierto;
  lineas: LineaInventario[];
}

export async function lineasInventario(idInv: number): Promise<InventarioDetalle | null> {
  const r = await api.get<InventarioDetalle>(`/stock/inventory/${idInv}/lines`);
  return r.ok ? r.json : null;
}

export async function registrarRecuento(
  idInv: number,
  datos: {codigo: string; contado: number; observaciones?: string},
): Promise<{ok: boolean; error?: string}> {
  const r = await api.post<{ok: boolean; error?: string}>(`/stock/inventory/${idInv}/count`, {
    body: datos,
  });
  return r.json ?? {ok: false, error: 'No se pudo registrar el recuento.'};
}
