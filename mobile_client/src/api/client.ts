/**
 * Cliente HTTP de la plataforma móvil.
 *
 * Espejo en el dispositivo de `src/services/mobile/networking.py`:
 *   - Habla EXCLUSIVAMENTE con la REST API oficial (`/api/v1`), nunca con SQL ni servicios internos.
 *   - Propaga el JWT en `Authorization: Bearer <access>` → aislamiento multiempresa por token.
 *   - `request(metodo, ruta, {params, cuerpo})` devuelve `{status, json}` (mismo contrato que `solicitar`).
 *
 * Añade lo que la app necesita y el modelo servidor delega en el cliente: refresh AUTOMÁTICO del
 * access token ante un 401 (usando el refresh token de `auth.refrescar`), con un único reintento.
 */
import {API_BASE_URL, REQUEST_TIMEOUT_MS} from '@/config/env';
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from './tokenStore';

export interface ApiResponse<T = unknown> {
  status: number;
  json: T | null;
  ok: boolean;
}

export interface RequestOptions {
  params?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  /** Si false, no adjunta Authorization ni intenta refrescar (para /auth/login y /auth/refresh). */
  auth?: boolean;
  /** Cabeceras extra (p. ej. Idempotency-Key para la sincronización). */
  headers?: Record<string, string>;
}

/** Construye la URL absoluta. `ruta` es relativa a /api/v1 (ej. "/auth/login", "/stock"). */
function buildUrl(
  path: string,
  params?: RequestOptions['params'],
): string {
  const base = path.startsWith('http')
    ? path
    : `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  if (!params) {
    return base;
  }
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return qs ? `${base}?${qs}` : base;
}

/** Llamada de red de bajo nivel (sin lógica de refresh). */
async function rawFetch<T>(
  method: string,
  path: string,
  opts: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const {params, body, auth = true, headers = {}} = opts;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  };
  if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
  }
  const token = getAccessToken();
  if (auth && token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  try {
    const resp = await fetch(buildUrl(path, params), {
      method: method.toUpperCase(),
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    let json: T | null = null;
    try {
      json = (await resp.json()) as T;
    } catch {
      json = null; // respuesta sin cuerpo JSON
    }
    return {status: resp.status, json, ok: resp.ok};
  } finally {
    clearTimeout(timeout);
  }
}

export interface ArchivoAdjunto {
  /** URI local del fichero (p. ej. lo que devuelve `takePhoto()` de vision-camera). */
  uri: string;
  name: string;
  type: string;
}

/** Sube un fichero + campos de formulario como `multipart/form-data` (primer uso: foto de evidencia
 * de Mermas). Mismo manejo de Authorization/refresh-en-401 que `request()` — NUNCA usa `JSON.stringify`
 * (dejamos que `fetch` construya el boundary multipart él solo al pasarle un `FormData`). */
export async function requestMultipart<T = unknown>(
  path: string,
  campo: string,
  archivo: ArchivoAdjunto,
  campos: Record<string, string | number>,
): Promise<ApiResponse<T>> {
  const enviar = async (): Promise<ApiResponse<T>> => {
    const form = new FormData();
    Object.entries(campos).forEach(([k, v]) => form.append(k, String(v)));
    // React Native FormData acepta {uri,name,type} para ficheros locales (no un Blob del DOM).
    form.append(campo, {uri: archivo.uri, name: archivo.name, type: archivo.type} as unknown as Blob);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const token = getAccessToken();
    try {
      const resp = await fetch(buildUrl(path), {
        method: 'POST',
        headers: token ? {Authorization: `Bearer ${token}`} : undefined,
        body: form,
        signal: controller.signal,
      });
      let json: T | null = null;
      try {
        json = (await resp.json()) as T;
      } catch {
        json = null;
      }
      return {status: resp.status, json, ok: resp.ok};
    } finally {
      clearTimeout(timeout);
    }
  };

  const first = await enviar();
  if (first.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return enviar();
    }
  }
  return first;
}

/**
 * Renueva el access token con el refresh guardado.
 * Contrato: POST /auth/refresh {refresh} -> {access} (ver src/api/routers/auth.py::refresh).
 */
export async function refreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) {
    return false;
  }
  const r = await rawFetch<{access?: string}>('POST', '/auth/refresh', {
    body: {refresh},
    auth: false,
  });
  if (r.ok && r.json?.access) {
    await setTokens({access: r.json.access});
    return true;
  }
  // Refresh inválido/expirado → sesión muerta.
  await clearTokens();
  return false;
}

/**
 * Petición REST con manejo automático de expiración: ante un 401 intenta refrescar UNA vez y
 * reintenta la llamada original. Devuelve `{status, json, ok}` (paridad con `solicitar`).
 */
export async function request<T = unknown>(
  method: string,
  path: string,
  opts: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const {auth = true} = opts;
  const first = await rawFetch<T>(method, path, opts);

  const isRefreshCall = path.includes('/auth/refresh');
  if (first.status === 401 && auth && !isRefreshCall) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return rawFetch<T>(method, path, opts);
    }
  }
  return first;
}

// ── Azúcar sintáctico ────────────────────────────────────────────────────────
export const api = {
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>('GET', path, opts),
  post: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>('POST', path, opts),
  put: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>('PUT', path, opts),
  del: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>('DELETE', path, opts),
  postMultipart: <T = unknown>(
    path: string,
    campo: string,
    archivo: ArchivoAdjunto,
    campos: Record<string, string | number>,
  ) => requestMultipart<T>(path, campo, archivo, campos),
};
