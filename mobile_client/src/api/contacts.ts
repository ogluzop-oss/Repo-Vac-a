/**
 * Directorio de contactos corporativos.
 *
 * Espejo de `src/api/routers/contacts.py::buscar` (Recipient Resolution Service / CCP):
 *   GET /contacts?q=&contexto= -> Destinatario[]  (ver `src/services/destinatarios/modelo.py`)
 *
 * Sin paginación: el router solo activa el sobre `{data,total,...}` si se envían parámetros de
 * paginación (`limit`/`page`/...), que este cliente no usa todavía — la respuesta es un array plano.
 */
import {api} from './client';

export interface Destinatario {
  correo: string;
  nombre_mostrado: string;
  tipo: string;
  etiqueta: string;
  estado: string | null;
  avisos: string[];
  favorito: boolean;
  reciente: boolean;
  num_envios: number;
  departamento?: string | null;
  cargo?: string | null;
}

/** Busca destinatarios por texto libre (nombre/correo/nif…), opcionalmente acotado por contexto. */
export async function buscarContactos(
  q: string,
  contexto?: string,
): Promise<Destinatario[]> {
  const r = await api.get<Destinatario[]>('/contacts', {
    params: {q, contexto},
  });
  return Array.isArray(r.json) ? r.json : [];
}
