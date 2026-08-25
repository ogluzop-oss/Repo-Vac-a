/**
 * Directorio de clientes (ficha comercial completa, distinta del directorio genérico de contactos).
 *
 * Espejo de `src/api/routers/customers.py`:
 *   GET /customers?q=      -> Cliente[]        (búsqueda por nombre/NIF/teléfono/email)
 *   GET /customers/<id>    -> Cliente | 404
 */
import {api} from './client';

export interface Cliente {
  id: number;
  nombre: string;
  nif: string | null;
  telefono: string | null;
  email: string | null;
  direccion: string | null;
  estado: string;
  segmento: string | null;
  categoria: string | null;
  limite_credito: string | number | null;
  saldo_monedero: string | number | null;
}

export async function buscarClientes(q: string): Promise<Cliente[]> {
  const r = await api.get<Cliente[]>('/customers', {params: {q}});
  return Array.isArray(r.json) ? r.json : [];
}
