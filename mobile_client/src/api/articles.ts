/**
 * Consulta básica de artículos (nombre/descripción/precio/categoría), solo lectura, + la FICHA
 * completa de un artículo (módulo "Info Artículo" de escritorio, pestañas Buscar/Imagen — petición
 * explícita: mismos datos que escritorio, sin excepción).
 *
 * Espejo de `src/api/routers/articles.py`:
 *   GET /articles?q=              -> {codigo, nombre, descripcion, categoria, seccion, precio,
 *                                      precio_promo, promo_activa, imagen}[]
 *   GET /articles/<codigo>/ficha  -> `FichaArticulo` (ver abajo) — EXACTAMENTE los mismos datos
 *                                     que `gui.info_articulo.InfoArticuloWindow._buscar` en
 *                                     escritorio, reutilizando ahí mismo las mismas funciones de
 *                                     servicio/datos (nunca una consulta paralela).
 *   POST/DELETE /articles/<codigo>/image -> sube/borra la foto (mismo destino en disco que la
 *                                     pestaña "Imagen artículo" de escritorio).
 *
 * Distinto del catálogo web (`/catalogo/productos`): sin filtro de visibilidad, cualquier artículo
 * es consultable — pensado para el personal de tienda, no para el escaparate online.
 */
import {API_BASE_URL} from '@/config/env';
import {getAccessToken} from './tokenStore';
import {api, type ArchivoAdjunto} from './client';

export interface Articulo {
  codigo: string;
  nombre: string;
  descripcion: string | null;
  categoria: string | null;
  seccion: string | null;
  /** DECIMAL de MariaDB — el backend lo serializa como STRING (evita pérdida de precisión en
   * dinero al pasar por JSON/float), no como number. Parsear con `Number(...)` al usarlo. */
  precio: string;
  precio_promo: string;
  promo_activa: number;
  imagen: string | null;
}

export async function buscarArticulos(q: string): Promise<Articulo[]> {
  const r = await api.get<Articulo[]>('/articles', {params: {q}});
  return Array.isArray(r.json) ? r.json : [];
}

/** URL de la foto del artículo, con el token de acceso como cabecera (para `<Image source={{uri,
 * headers}}>` — igual que `location.ts::imagenMapaSource()`, la imagen vive detrás de autenticación).
 * Espejo de `GET /articles/<codigo>/image`. */
export function imagenArticuloSource(codigo: string): {uri: string; headers: Record<string, string>} {
  const token = getAccessToken();
  return {
    uri: `${API_BASE_URL}/articles/${encodeURIComponent(codigo)}/image`,
    headers: token ? {Authorization: `Bearer ${token}`} : {},
  };
}

/** Ficha completa de un artículo — mismos campos que escritorio (`info_articulo.py`), ya
 * resueltos en el servidor (stock reservado, familia, precio ref., física de seguridad...). Los
 * importes vienen como `number` (el backend ya los convierte de DECIMAL), a diferencia de
 * `Articulo.precio` arriba. */
export interface FichaArticulo {
  codigo: string;
  nombre: string | null;
  stock_lineal: number | null;
  stock_almacen: number | null;
  stock_central: number | null;
  stock_reservado: number;
  precio: number;
  ubicacion_tienda: string | null;
  ubicacion_almacen: string | null;
  proxima_recepcion: string | null;
  ventas_7_dias: number;
  familia: string | null;
  precio_ref: number | null;
  peso_unitario: number | null;
  tolerancia_peso: number | null;
  requiere_lote: boolean;
  tiene_imagen: boolean;
}

/** `GET /articles/<codigo>/ficha`. `null` si el código no existe (404) o hay error de red —
 * nunca lanza, el consumidor distingue "no encontrado" de "cargando" por el propio `null`. */
export async function obtenerFichaArticulo(codigo: string): Promise<FichaArticulo | null> {
  const r = await api.get<FichaArticulo>(`/articles/${encodeURIComponent(codigo)}/ficha`);
  return r.ok ? r.json : null;
}

/** Sube/reemplaza la foto del artículo (cámara o galería del móvil). Espejo de
 * `POST /articles/<codigo>/image` — mismo destino en disco que "Imagen artículo" en escritorio. */
export async function subirImagenArticulo(
  codigo: string,
  archivo: ArchivoAdjunto,
): Promise<{ok: boolean; error?: string}> {
  const r = await api.postMultipart<{ok?: boolean; error?: string}>(
    `/articles/${encodeURIComponent(codigo)}/image`, 'foto', archivo, {});
  return r.ok ? {ok: true} : {ok: false, error: r.json?.error || 'No se pudo subir la imagen.'};
}

/** Borra la foto asociada al artículo. Espejo de `DELETE /articles/<codigo>/image`. */
export async function borrarImagenArticulo(codigo: string): Promise<{ok: boolean}> {
  const r = await api.del(`/articles/${encodeURIComponent(codigo)}/image`);
  return {ok: r.ok};
}
