/**
 * Pedidos de RECEPCIÓN de palets (no pedidos de venta ni de compra — ver el docstring de
 * `src/services/pedidos.py`: es, hoy, el único modelo real de "pedido" en la base de datos).
 *
 * Espejo de `src/api/routers/orders.py`:
 *   GET /orders?procesado=  -> Pedido[]
 */
import {api} from './client';

export interface ItemPedido {
  [clave: string]: unknown;
}

export interface Pedido {
  id: number;
  pale_codigo: string;
  items: ItemPedido[];
  procesado: boolean;
  fecha: string;
  id_tienda: number | null;
}

export async function listarPedidos(procesado?: boolean): Promise<Pedido[]> {
  const r = await api.get<Pedido[]>('/orders', {
    params: {procesado: procesado === undefined ? undefined : String(procesado)},
  });
  return Array.isArray(r.json) ? r.json : [];
}
