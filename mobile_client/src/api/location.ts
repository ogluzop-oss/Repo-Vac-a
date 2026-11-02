/**
 * Ubicación — SOLO Asignar ubicación (escanear la etiqueta de una estantería) y GPS interno (escanear
 * el QR de un satélite para autolocalizarse y trazar ruta hasta un artículo) — los dos únicos pasos de
 * este módulo que exigen presencia física. "Buscar producto" se quedó en escritorio (rediseño móvil
 * Grupo A). Espejo de `src/api/routers/location.py`.
 *
 * GPS interno calcula la ruta con el mismo motor A* que usa el escritorio
 * (`services/ubicacion/pathfinding.py`). El origen se resuelve escaneando el QR físico de un satélite
 * (`epc`, buscado en `puntos_infraestructura` ya cargado) — nunca a mano.
 */
import {API_BASE_URL} from '@/config/env';
import {getAccessToken} from './tokenStore';
import {api} from './client';

export interface UbicacionArticulo {
  codigo: string;
  nombre: string;
  ubicacion_tienda: string | null;
  ubicacion_almacen: string | null;
  pasillo: string | null;
  estanteria: string | null;
  balda: string | null;
  pasillo_almacen: string | null;
  estanteria_almacen: string | null;
  nivel_almacen: string | null;
  verificado: number | null;
  stock_tienda: number;
  stock_total: number;
}

export async function buscarUbicacion(q: string): Promise<UbicacionArticulo[]> {
  const r = await api.get<UbicacionArticulo[]>('/location', {params: {q}});
  return Array.isArray(r.json) ? r.json : [];
}

export type TipoUbicacion = 'lineal' | 'almacen';

export async function asignarUbicacion(datos: {
  codigo: string;
  pasillo: string;
  estanteria: string;
  nivel: string;
  tipo: TipoUbicacion;
}): Promise<{ok: boolean; error?: string}> {
  const r = await api.post<{ok: boolean; error?: string}>('/location/assign', {body: datos});
  return r.json ?? {ok: false, error: 'No se pudo guardar la ubicación.'};
}

// ── GPS interno ──────────────────────────────────────────────────────────────────────────────────
export interface PuntoInfraestructura {
  tipo: string;
  nombre: string;
  x: number;
  y: number;
  /** Identificador físico del satélite (p.ej. "SAT_842_513") — el mismo `epc` que codifica su QR. */
  epc?: string;
}

export interface MapaInfo {
  planta_index: number;
  tipo: string;
  titulo: string;
  escala_px_metro: number | null;
  ancla_x: number | null;
  ancla_y: number | null;
  puntos_infraestructura: PuntoInfraestructura[];
  tiene_imagen: boolean;
}

export async function obtenerMapa(planta?: number): Promise<MapaInfo | null> {
  const r = await api.get<MapaInfo>('/location/map', {
    params: planta != null ? {planta} : undefined,
  });
  return r.ok ? r.json : null;
}

/** URL de la imagen del plano, con el token de acceso como cabecera (para `<Image source={{uri,
 * headers}}>` — la imagen vive detrás de autenticación, igual que el resto de la API). */
export function imagenMapaSource(planta?: number): {uri: string; headers: Record<string, string>} {
  const qs = planta != null ? `?planta=${planta}` : '';
  const token = getAccessToken();
  return {
    uri: `${API_BASE_URL}/location/map/image${qs}`,
    headers: token ? {Authorization: `Bearer ${token}`} : {},
  };
}

export async function coordsArticulo(codigo: string): Promise<{x: number; y: number} | null> {
  const r = await api.get<{x: number; y: number}>('/location/map/coords', {params: {codigo}});
  return r.ok ? r.json : null;
}

export type ReferenciaMapa =
  | {tipo: 'articulo'; codigo: string}
  | {tipo: 'punto'; x: number; y: number};

export interface RutaCalculada {
  ok: boolean;
  ruta?: {x: number; y: number}[];
  distancia_celdas?: number;
  motivo?: 'sin_plano' | 'origen_no_localizado' | 'destino_no_localizado' | 'sin_ruta';
}

export async function calcularRuta(
  planta: number,
  origen: ReferenciaMapa,
  destino: ReferenciaMapa,
): Promise<RutaCalculada> {
  const r = await api.post<RutaCalculada>('/location/map/route', {
    body: {planta, origen, destino},
  });
  return r.json ?? {ok: false, motivo: 'sin_plano'};
}
