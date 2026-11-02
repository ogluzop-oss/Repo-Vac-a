/**
 * Obrador (capacidad "obrador" -> /api/v1/obrador/parts, edición Bakery). Rediseño móvil · Grupo B,
 * módulo 6: registrar un parte de producción diaria CON foto obligatoria del lote terminado — un único
 * punto de guardado (a diferencia de GMAO/SAT, no hay iniciar/finalizar), una foto por parte, no por
 * línea. Espejo de `src/api/routers/obrador.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface Parte {
  id: number;
  fecha: string;
  turno: string | null;
  responsable: string | null;
  usuario: string | null;
  id_documento_foto: string | null;
}

export async function listarPartes(limite = 20): Promise<Parte[]> {
  const r = await api.get<Parte[]>('/obrador/parts', {params: {limite}});
  return Array.isArray(r.json) ? r.json : [];
}

export interface LineaProduccion {
  codigo: string;
  cantidad: number;
}

export interface NuevoParte {
  turno?: string;
  responsable?: string;
  items: LineaProduccion[];
  /** URI local de la foto del lote terminado (obligatoria). */
  fotoUri: string;
}

export async function registrarParte(
  datos: NuevoParte,
): Promise<{ok: true; parte: number} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: datos.fotoUri, name: 'produccion.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; parte?: number; error?: string}>(
    '/obrador/parts',
    'foto',
    archivo,
    {
      items: JSON.stringify(datos.items),
      ...(datos.turno ? {turno: datos.turno} : {}),
      ...(datos.responsable ? {responsable: datos.responsable} : {}),
    },
  );
  if (r.ok && r.json?.ok && r.json.parte) {
    return {ok: true, parte: r.json.parte};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la producción.'};
}
