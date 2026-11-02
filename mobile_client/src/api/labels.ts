/**
 * Etiquetas: "Localizar etiqueta ESL" (hacer parpadear una etiqueta electrónica física para encontrarla
 * en el lineal) y "Cambiar precio + imprimir" (cambia el precio del artículo y genera su etiqueta de
 * papel con el precio nuevo — pestaña restringida a ADMINISTRADOR/SUPERADMIN, ver
 * `api/capabilities.ts::modulosEfectivos`). Espejo de `src/api/routers/labels.py`.
 */
import {API_BASE_URL} from '@/config/env';
import {getAccessToken} from './tokenStore';
import {api} from './client';

export interface EtiquetaEsl {
  id: number;
  codigo_articulo: string;
  label_id: string;
  estado: string;
  precio_sincronizado: number | null;
}

export async function buscarEtiquetasDeArticulo(codigo: string): Promise<EtiquetaEsl[]> {
  const r = await api.get<EtiquetaEsl[]>('/labels/esl/by-article', {params: {codigo}});
  return Array.isArray(r.json) ? r.json : [];
}

export async function localizarEtiqueta(labelId: string): Promise<{ok: boolean; detalle?: string}> {
  const r = await api.post<{ok?: boolean; detalle?: string; error?: string}>('/labels/esl/locate', {
    body: {label_id: labelId},
  });
  return {ok: !!r.json?.ok, detalle: r.json?.detalle};
}

export const TAMANOS_ETIQUETA = ['40x26', '65x35', '70x35', '95x35', '100x70', '148x70'] as const;
export type TamanoEtiqueta = (typeof TAMANOS_ETIQUETA)[number];
export type TipoEtiqueta = 'normal' | 'rebajado' | 'nuevo';

export interface CambiarPrecioResultado {
  ok: boolean;
  id_documento?: string;
  error?: string;
}

/** Cambia el precio del artículo Y genera su etiqueta de papel con el precio nuevo (mismo flujo que
 * `gui/etiquetas_precios.py` en escritorio). */
export async function cambiarPrecio(datos: {
  codigo: string;
  nuevoPrecio: number;
  formato?: TamanoEtiqueta;
  tipo?: TipoEtiqueta;
}): Promise<CambiarPrecioResultado> {
  const r = await api.post<CambiarPrecioResultado>('/labels/price', {
    body: {
      codigo: datos.codigo,
      nuevo_precio: datos.nuevoPrecio,
      formato: datos.formato ?? '70x35',
      tipo: datos.tipo ?? 'normal',
    },
  });
  return r.json ?? {ok: false, error: 'No se pudo cambiar el precio.'};
}

/** URL + cabecera de auth del PDF de una etiqueta ya generada (mismo patrón que
 * `location.ts::imagenMapaSource` / `articles.ts::imagenArticuloSource`). */
export function urlPdfEtiqueta(idDocumento: string): {url: string; headers: Record<string, string>} {
  const token = getAccessToken();
  return {
    url: `${API_BASE_URL}/labels/price/${encodeURIComponent(idDocumento)}/pdf`,
    headers: token ? {Authorization: `Bearer ${token}`} : {},
  };
}
