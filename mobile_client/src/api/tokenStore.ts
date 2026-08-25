/**
 * Almacén SEGURO de tokens JWT (access + refresh).
 *
 * Persiste en el Keychain nativo (Android Keystore / iOS Keychain) vía `react-native-keychain`, en
 * vez de AsyncStorage en texto plano — cierre de la brecha de seguridad documentada en el README.
 * Mantiene una caché en memoria para las lecturas SÍNCRONAS que necesita el cliente HTTP
 * (`api/client.ts`) al construir la cabecera `Authorization` en cada petición; el Keychain solo se
 * lee/escribe de forma asíncrona en `loadTokens`/`setTokens`/`clearTokens`. Misma API pública que la
 * versión anterior: ningún otro módulo (`client.ts`, `AuthContext.tsx`) necesita cambios.
 */
import * as Keychain from 'react-native-keychain';

/** Namespacing del entry en el Keychain (no es un secreto, solo la clave de búsqueda). */
const SERVICE = 'sm.auth.tokens';

export interface TokenPair {
  access: string | null;
  refresh: string | null;
}

let _cache: TokenPair = {access: null, refresh: null};

/** Carga los tokens persistidos a la caché en memoria (llamar al arrancar la app). */
export async function loadTokens(): Promise<TokenPair> {
  try {
    const cred = await Keychain.getGenericPassword({service: SERVICE});
    _cache = cred ? (JSON.parse(cred.password) as TokenPair) : {access: null, refresh: null};
  } catch {
    // Keychain no disponible (p. ej. módulo nativo aún no enlazado en este build): arranca sin
    // sesión persistida en vez de romper el arranque de la app.
    _cache = {access: null, refresh: null};
  }
  return _cache;
}

/** Persiste (o borra) el par de tokens y actualiza la caché. */
export async function setTokens(tokens: Partial<TokenPair>): Promise<void> {
  if (tokens.access !== undefined) {
    _cache.access = tokens.access;
  }
  if (tokens.refresh !== undefined) {
    _cache.refresh = tokens.refresh;
  }
  try {
    if (_cache.access || _cache.refresh) {
      // El Keychain guarda un único blob por servicio: se persiste el par completo (no hay
      // actualización parcial de campos), igual que antes con las dos claves de AsyncStorage.
      await Keychain.setGenericPassword(SERVICE, JSON.stringify(_cache), {
        service: SERVICE,
        accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED,
      });
    } else {
      await Keychain.resetGenericPassword({service: SERVICE});
    }
  } catch {
    // Degradación: la sesión sigue funcionando en memoria para esta ejecución de la app, aunque no
    // sobreviva a un reinicio si el Keychain no está disponible.
  }
}

/** Borra ambos tokens (logout). */
export async function clearTokens(): Promise<void> {
  _cache = {access: null, refresh: null};
  try {
    await Keychain.resetGenericPassword({service: SERVICE});
  } catch {
    // no-op: si el Keychain no está disponible, ya no había nada seguro que borrar.
  }
}

/** Lectura síncrona de la caché (usada por el cliente HTTP para las cabeceras). */
export function getAccessToken(): string | null {
  return _cache.access;
}

export function getRefreshToken(): string | null {
  return _cache.refresh;
}
