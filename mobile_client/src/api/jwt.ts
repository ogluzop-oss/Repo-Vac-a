/**
 * Decodificador MÍNIMO del payload de un JWT (sin verificar firma — la verificación real la hace
 * siempre el servidor en cada petición; esto es solo para leer claims públicos como `rol` y adaptar la
 * UI). Base64url manual, sin depender de `atob` (no siempre presente en Hermes/RN).
 */

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function base64Decode(input: string): string {
  const clean = input.replace(/[^A-Za-z0-9+/=]/g, '');
  let output = '';
  let buffer = 0;
  let bits = 0;
  for (const char of clean) {
    if (char === '=') {
      break;
    }
    const value = B64_CHARS.indexOf(char);
    if (value === -1) {
      continue;
    }
    buffer = (buffer << 6) | value;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      output += String.fromCharCode((buffer >> bits) & 0xff);
    }
  }
  return output;
}

function base64UrlDecode(input: string): string {
  const padded = input.replace(/-/g, '+').replace(/_/g, '/');
  return base64Decode(padded);
}

export interface JwtClaims {
  sub?: string;
  empresa?: string | number;
  tienda?: number | null;
  rol?: string;
  nombre?: string;
  [key: string]: unknown;
}

/** Decodifica el payload de un JWT. Devuelve `null` si el token no tiene el formato esperado. */
export function decodeJwtPayload(token: string | null | undefined): JwtClaims | null {
  if (!token) {
    return null;
  }
  const partes = token.split('.');
  const payload = partes[1];
  if (partes.length !== 3 || !payload) {
    return null;
  }
  try {
    const json = base64UrlDecode(payload);
    // decodeURIComponent + escape maneja UTF-8 multibyte (nombres con acentos, etc.).
    const utf8 = decodeURIComponent(
      json
        .split('')
        .map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
        .join(''),
    );
    return JSON.parse(utf8) as JwtClaims;
  } catch {
    return null;
  }
}

/** Rol del usuario a partir del access token (o `null` si no se puede determinar). */
export function rolDeToken(token: string | null | undefined): string | null {
  return decodeJwtPayload(token)?.rol ?? null;
}
