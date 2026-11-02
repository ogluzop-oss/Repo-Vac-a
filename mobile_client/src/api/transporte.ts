/**
 * Transporte/Reparto (capacidad "transporte" -> /api/v1/transporte/routes). Rediseño móvil · Grupo B,
 * módulo 5: entregar una parada CON foto obligatoria (mismo criterio que GMAO/SAT), o reportar una
 * incidencia (cliente ausente/rechazo/dirección incorrecta) con foto opcional. Sin firma: no existe hoy
 * ningún momento de conformidad de cliente en el modelo de Transporte. Espejo de
 * `src/api/routers/transporte.py`.
 */
import {api, type ArchivoAdjunto} from './client';

export interface Parada {
  id: number;
  id_ruta: number;
  orden: number;
  cliente: string | null;
  direccion: string | null;
  estado: string;
  motivo_incidencia: string | null;
}

export interface Ruta {
  id: number;
  fecha: string;
  id_vehiculo: number | null;
  conductor: string | null;
  estado: string;
  paradas?: Parada[];
}

export async function listarRutas(): Promise<Ruta[]> {
  const r = await api.get<Ruta[]>('/transporte/routes');
  return Array.isArray(r.json) ? r.json : [];
}

export async function obtenerRuta(idRuta: number): Promise<Ruta | null> {
  const r = await api.get<Ruta>(`/transporte/routes/${idRuta}`);
  return r.ok ? r.json : null;
}

export async function iniciarRuta(
  idRuta: number,
): Promise<{ok: true} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; error?: string}>(`/transporte/routes/${idRuta}/start`);
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo iniciar la ruta.'};
}

export async function entregarParada(
  idParada: number,
  fotoUri: string,
): Promise<{ok: true} | {ok: false; error: string}> {
  const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'entrega.jpg', type: 'image/jpeg'};
  const r = await api.postMultipart<{ok?: boolean; error?: string}>(
    `/transporte/stops/${idParada}/deliver`,
    'foto',
    archivo,
    {},
  );
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la entrega.'};
}

export async function reportarIncidencia(
  idParada: number,
  motivo: string,
  fotoUri?: string,
): Promise<{ok: true} | {ok: false; error: string}> {
  let r;
  if (fotoUri) {
    const archivo: ArchivoAdjunto = {uri: fotoUri, name: 'incidencia.jpg', type: 'image/jpeg'};
    r = await api.postMultipart<{ok?: boolean; error?: string}>(
      `/transporte/stops/${idParada}/incident`,
      'foto',
      archivo,
      {motivo},
    );
  } else {
    r = await api.post<{ok?: boolean; error?: string}>(`/transporte/stops/${idParada}/incident`, {
      body: {motivo},
    });
  }
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo registrar la incidencia.'};
}

export async function cerrarRuta(
  idRuta: number,
): Promise<{ok: true} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; error?: string}>(`/transporte/routes/${idRuta}/close`);
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo cerrar la ruta.'};
}
