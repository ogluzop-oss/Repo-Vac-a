/**
 * Escaneo remoto (`/api/v1/remote-scan/*`). Delegación universal de escaneo QR/código de barras:
 * escritorio crea una solicitud y se DIFUNDE a todos los móviles de la MISMA tienda/almacén (nunca a
 * otras) — el primero en reclamarla es el único que puede completarla. Espejo de
 * `src/api/routers/escaneo_remoto.py` / `src/services/escaneo_remoto.py`.
 *
 * Sin pantalla propia: `EscaneoRemotoOverlay` (montado en la raíz de la app) sondea
 * `listarPendientes()` cada pocos segundos y muestra el aviso; al aceptar, `reclamarSolicitud()` y
 * luego la cámara (reutilizando `ScannerScreen`) + `completarSolicitud()`.
 */
import {api} from './client';

export interface SolicitudEscaneo {
  id: string;
  contexto: string | null;
  estado: string;
  creado: string;
  expira: string;
}

/** Solicitudes vivas de la tienda del usuario autenticado, aún sin reclamar por nadie. */
export async function listarPendientes(): Promise<SolicitudEscaneo[]> {
  const r = await api.get<SolicitudEscaneo[]>('/remote-scan/pending');
  return Array.isArray(r.json) ? r.json : [];
}

/** Reclama la solicitud (atómico: solo un dispositivo gana). */
export async function reclamarSolicitud(
  id: string,
): Promise<{ok: true} | {ok: false; error: string; motivo?: string}> {
  const r = await api.post<{ok?: boolean; error?: string; motivo?: string}>(
    `/remote-scan/requests/${id}/claim`,
  );
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {
    ok: false,
    error: r.json?.error || 'No se pudo reclamar la solicitud.',
    motivo: r.json?.motivo,
  };
}

export async function completarSolicitud(
  id: string,
  valor: string,
): Promise<{ok: true} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; error?: string}>(`/remote-scan/requests/${id}/complete`, {
    body: {valor},
  });
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo completar la solicitud.'};
}

/** El usuario reclamó pero se echó atrás sin escanear (o quiere desistir): cierra la solicitud. */
export async function cancelarSolicitud(
  id: string,
): Promise<{ok: true} | {ok: false; error: string}> {
  const r = await api.post<{ok?: boolean; error?: string}>(`/remote-scan/requests/${id}/cancel`);
  if (r.ok && r.json?.ok) {
    return {ok: true};
  }
  return {ok: false, error: r.json?.error || 'No se pudo cancelar la solicitud.'};
}
