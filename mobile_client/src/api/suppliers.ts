/**
 * Directorio de proveedores.
 *
 * Espejo de `src/api/routers/suppliers.py`:
 *   GET /suppliers?q=      -> Proveedor[]      (búsqueda por razón social/nombre comercial/CIF)
 *   GET /suppliers/<id>    -> Proveedor | 404
 */
import {api} from './client';

export interface Proveedor {
  id_proveedor: number;
  razon_social: string;
  nombre_comercial: string | null;
  cif_nif: string | null;
  email: string | null;
  telefono: string | null;
  estado: string;
  homologado: number | boolean;
  bloqueado: number | boolean;
  plazo_pago: number | null;
  lead_time_dias: number | null;
}

export async function buscarProveedores(q: string): Promise<Proveedor[]> {
  const r = await api.get<Proveedor[]>('/suppliers', {params: {q}});
  return Array.isArray(r.json) ? r.json : [];
}
