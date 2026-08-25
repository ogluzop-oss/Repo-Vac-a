/**
 * Consulta de artículos + niveles de stock (solo lectura).
 *
 * Espejo de `src/api/routers/stock.py`:
 *   GET /stock?q=  -> {codigo, nombre, stock_tienda, stock_total, stock_central}[]
 *
 * Distinto del flujo de ESCANEO (`ScannerScreen` / Outbox), que es de escritura offline-first y no
 * tiene todavía un endpoint de sincronización en el backend (ver README).
 */
import {api} from './client';

export interface ArticuloStock {
  codigo: string;
  nombre: string;
  stock_tienda: number;
  stock_total: number;
  stock_central: number;
}

export async function buscarStock(q: string): Promise<ArticuloStock[]> {
  const r = await api.get<ArticuloStock[]>('/stock', {params: {q}});
  return Array.isArray(r.json) ? r.json : [];
}
