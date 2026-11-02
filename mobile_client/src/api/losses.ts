/**
 * Mermas — registrar una merma CON foto de evidencia del producto dañado/caducado (Rediseño móvil ·
 * Grupo B, módulo 1). A diferencia de la pantalla retirada en el Grupo A (un formulario sin foto,
 * idéntico a lo que ya hace escritorio), la foto es el componente físico: solo tiene sentido
 * fotografiar el producto estando delante de él. Espejo de `src/api/routers/losses.py`.
 */
import {API_BASE_URL} from '@/config/env';
import {getAccessToken} from './tokenStore';
import {api, type ArchivoAdjunto} from './client';

export interface Merma {
  id: number;
  codigo: string;
  nombre: string;
  cantidad: number;
  motivo: string;
  fecha: string;
  id_documento_foto: string | null;
}

export async function listarMermas(limite = 20): Promise<Merma[]> {
  const r = await api.get<Merma[]>('/losses', {params: {limite}});
  return Array.isArray(r.json) ? r.json : [];
}

export interface NuevaMerma {
  codigo: string;
  cantidad: number;
  motivo: string;
  origen: 'lineal' | 'almacen';
  /** URI local de la foto tomada con la cámara (obligatoria — es el motivo de que este módulo exista
   * en el móvil). */
  fotoUri: string;
}

export async function registrarMerma(
  datos: NuevaMerma,
): Promise<{ok: true; id: number; id_documento?: string} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: datos.fotoUri, name: 'merma.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; id?: number; id_documento?: string; error?: string}>(
    '/losses',
    'foto',
    archivo,
    {codigo: datos.codigo, cantidad: datos.cantidad, motivo: datos.motivo, origen: datos.origen},
  );
  if (r.ok && r.json?.ok && r.json.id) {
    return {ok: true, id: r.json.id, id_documento: r.json.id_documento};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la merma.'};
}

/** URL + cabecera de auth de la foto de evidencia de una merma ya registrada (mismo patrón que
 * `articles.ts::imagenArticuloSource`). Espejo de `GET /losses/photo/<id_documento>`. */
export function imagenMermaSource(idDocumento: string): {uri: string; headers: Record<string, string>} {
  const token = getAccessToken();
  return {
    uri: `${API_BASE_URL}/losses/photo/${encodeURIComponent(idDocumento)}`,
    headers: token ? {Authorization: `Bearer ${token}`} : {},
  };
}
