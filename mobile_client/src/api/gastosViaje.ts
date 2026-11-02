/**
 * Gastos de viaje (capacidad "gastos_viaje" -> /api/v1/rrhh/me/gastos). Único trozo de
 * autoservicio RRHH que SÍ vuelve al móvil (a diferencia de nóminas/vacaciones/documentos, que se
 * quedan en escritorio — decisión explícita): fotografiar el ticket EN EL MOMENTO con lectura
 * automática por IA es justo el tipo de paso físico que este catálogo reúne (mismo criterio que
 * Mermas/Calidad/SAT). Espejo de `src/api/routers/rrhh_self_service.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface GastoViaje {
  id: number;
  codigo: string;
  fecha_gasto: string;
  categoria: 'transporte' | 'alojamiento' | 'dietas' | 'otros';
  concepto: string | null;
  importe: number;
  estado: 'pendiente' | 'aprobado' | 'rechazado' | 'reembolsado';
}

export interface TicketOcrDatos {
  comercio?: string;
  fecha?: string;
  importe?: number;
  categoria_sugerida?: 'transporte' | 'alojamiento' | 'dietas' | 'otros';
  concepto?: string;
}

export async function listarMisGastos(): Promise<GastoViaje[]> {
  const r = await api.get<GastoViaje[]>('/rrhh/me/gastos');
  return Array.isArray(r.json) ? r.json : [];
}

/** Sube la foto del ticket y pide a la IA un borrador (importe/fecha/categoría/concepto) — NUNCA
 * crea el gasto todavía, solo devuelve el borrador para que la pantalla lo muestre editable. */
export async function extraerTicket(
  fotoUri: string,
): Promise<{ok: true; datos: TicketOcrDatos} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'ticket.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; datos?: TicketOcrDatos; error?: string}>(
    '/rrhh/me/gastos/ocr',
    'foto',
    archivo,
    {},
  );
  if (r.ok && r.json?.ok && r.json.datos) {
    return {ok: true, datos: r.json.datos};
  }
  return {ok: false, error: r.json?.error || 'No se pudo leer el ticket.'};
}

export interface NuevoGasto {
  fecha_gasto: string;
  categoria: 'transporte' | 'alojamiento' | 'dietas' | 'otros';
  importe: number;
  concepto?: string;
  /** URI local de la foto del ticket (opcional — se puede registrar un gasto sin foto). */
  fotoUri?: string;
  /** `true` si los datos del formulario vinieron de `extraerTicket` (trazabilidad del origen). */
  ocrOrigen?: boolean;
}

export async function registrarGasto(
  datos: NuevoGasto,
): Promise<{ok: true; codigo: string} | {ok: false; error: string}> {
  const campos: Record<string, string | number> = {
    fecha_gasto: datos.fecha_gasto,
    categoria: datos.categoria,
    importe: datos.importe,
    ocr_origen: datos.ocrOrigen ? '1' : '0',
    ...(datos.concepto ? {concepto: datos.concepto} : {}),
  };
  if (datos.fotoUri) {
    const archivo: ArchivoAdjunto = {uri: datos.fotoUri, name: 'ticket.jpg', type: 'image/jpeg'};
    const r = await api.postMultipart<{ok?: boolean; codigo?: string; error?: string}>(
      '/rrhh/me/gastos',
      'foto',
      archivo,
      campos,
    );
    if (r.ok && r.json?.ok && r.json.codigo) {
      return {ok: true, codigo: r.json.codigo};
    }
    return {ok: false, error: r.json?.error || 'No se pudo registrar el gasto.'};
  }
  const r = await api.post<{ok?: boolean; codigo?: string; error?: string}>('/rrhh/me/gastos', {
    body: campos,
  });
  if (r.ok && r.json?.ok && r.json.codigo) {
    return {ok: true, codigo: r.json.codigo};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar el gasto.'};
}
