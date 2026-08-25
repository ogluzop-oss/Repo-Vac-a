/**
 * Registro documental (solo lectura de metadatos).
 *
 * Espejo de `src/api/routers/documents.py`:
 *   GET /documents?q=&tipo=  -> Documento[]
 *
 * La descarga del fichero no está expuesta todavía (ver README, sección de honestidad).
 */
import {api} from './client';

export interface Documento {
  id_documento: string;
  id_tienda: number | null;
  tipo_documento: string;
  nombre: string;
  referencia: string | null;
  cliente: string | null;
  trabajador: string | null;
  importe: number | string | null;
  estado: string;
  fecha_generacion: string;
  mime_type: string | null;
  size_bytes: number | null;
}

export async function buscarDocumentos(q: string, tipo?: string): Promise<Documento[]> {
  const r = await api.get<Documento[]>('/documents', {params: {q, tipo}});
  return Array.isArray(r.json) ? r.json : [];
}
