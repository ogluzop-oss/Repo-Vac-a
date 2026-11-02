/**
 * GMAO (capacidad "gmao" -> /api/v1/gmao/*). Rediseño móvil · Grupo B, módulo 2: localizar un activo
 * escaneando su QR (impreso desde escritorio, "Imprimir QR" en la pestaña Activos) y ejecutar in situ
 * el ciclo de su OT — iniciar, ver repuestos pendientes, fotografiar la reparación y finalizar. Las OTs
 * se crean/planifican desde escritorio; esto solo cubre la ejecución física. Espejo de
 * `src/api/routers/gmao.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface Activo {
  id: number;
  codigo: string;
  nombre: string;
  tipo: string;
  estado: string;
  criticidad: string;
}

export interface OrdenTrabajo {
  id: number;
  codigo: string;
  tipo: string;
  id_activo: number;
  descripcion: string | null;
  prioridad: string;
  estado: string;
  tecnico: number | null;
}

export interface Repuesto {
  id: number;
  tipo: string;
  referencia: string;
  cantidad: number;
  consumido: number;
  coste_unitario: number;
}

export async function buscarActivoPorCodigo(codigo: string): Promise<Activo | null> {
  const r = await api.get<Activo>('/gmao/assets/by-code', {params: {codigo}});
  return r.ok ? r.json : null;
}

export async function listarOrdenesDeActivo(idActivo: number): Promise<OrdenTrabajo[]> {
  const r = await api.get<OrdenTrabajo[]>(`/gmao/assets/${idActivo}/orders`);
  return Array.isArray(r.json) ? r.json : [];
}

export async function iniciarOrden(
  idOrden: number,
): Promise<{ok: true; estado: string} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; estado?: string; error?: string}>(
    `/gmao/orders/${idOrden}/start`,
  );
  if (r.ok && r.json?.ok && r.json.estado) {
    return {ok: true, estado: r.json.estado};
  }
  return {ok: false, error: r.json?.error || 'No se pudo iniciar la OT.'};
}

export async function listarRepuestos(idOrden: number): Promise<Repuesto[]> {
  const r = await api.get<Repuesto[]>(`/gmao/orders/${idOrden}/parts`);
  return Array.isArray(r.json) ? r.json : [];
}

export async function finalizarOrden(
  idOrden: number,
  fotoUri: string,
): Promise<{ok: true} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'reparacion.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; error?: string}>(
    `/gmao/orders/${idOrden}/finish`,
    'foto',
    archivo,
    {},
  );
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo finalizar la OT.'};
}
