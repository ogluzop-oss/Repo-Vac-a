/**
 * Calidad (capacidad "calidad" -> /api/v1/calidad/inspections). Rediseño móvil · Grupo B, módulo 3:
 * registrar una inspección de un artículo/lote CON foto obligatoria — el mismo criterio que Mermas/
 * GMAO, la foto es el motivo de que este módulo exista en el móvil. Si el resultado es "rechazada",
 * el backend abre una No Conformidad automáticamente (igual que ya hace escritorio) y la devuelve en
 * `no_conformidad`. Espejo de `src/api/routers/calidad.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface Inspeccion {
  id: number;
  fase: string;
  articulo: string | null;
  cantidad_inspeccionada: number;
  cantidad_rechazada: number;
  resultado: string;
  observaciones: string | null;
  fecha: string;
  id_documento_foto: string | null;
}

export async function listarInspecciones(limite = 20): Promise<Inspeccion[]> {
  const r = await api.get<Inspeccion[]>('/calidad/inspections', {params: {limite}});
  return Array.isArray(r.json) ? r.json : [];
}

export interface NuevaInspeccion {
  fase: 'recepcion' | 'produccion' | 'final';
  articulo: string;
  cantidad_inspeccionada: number;
  cantidad_rechazada: number;
  resultado: 'aceptada' | 'rechazada' | 'condicional';
  observaciones?: string;
  /** URI local de la foto del artículo/lote inspeccionado (obligatoria). */
  fotoUri: string;
}

export async function registrarInspeccion(
  datos: NuevaInspeccion,
): Promise<
  | {ok: true; inspeccion: number; no_conformidad: number | null; id_documento: string}
  | {ok: false; error: string}
> {
  const archivo: ArchivoAdjunto = {uri: datos.fotoUri, name: 'inspeccion.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{
    ok?: boolean;
    inspeccion?: number;
    no_conformidad?: number | null;
    id_documento?: string;
    error?: string;
  }>('/calidad/inspections', 'foto', archivo, {
    fase: datos.fase,
    articulo: datos.articulo,
    cantidad_inspeccionada: datos.cantidad_inspeccionada,
    cantidad_rechazada: datos.cantidad_rechazada,
    resultado: datos.resultado,
    ...(datos.observaciones ? {observaciones: datos.observaciones} : {}),
  });
  if (r.ok && r.json?.ok && r.json.inspeccion && r.json.id_documento) {
    return {
      ok: true,
      inspeccion: r.json.inspeccion,
      no_conformidad: r.json.no_conformidad ?? null,
      id_documento: r.json.id_documento,
    };
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la inspección.'};
}
