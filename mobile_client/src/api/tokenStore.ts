/**
 * Almacén de tokens JWT (access + refresh).
 *
 * Para el MVP se persiste en AsyncStorage con una caché en memoria para lecturas síncronas
 * rápidas desde el cliente HTTP. En producción se recomienda migrar a almacenamiento seguro
 * (react-native-keychain / EncryptedSharedPreferences / Keychain de iOS) — ver README.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const K_ACCESS = 'sm.auth.access';
const K_REFRESH = 'sm.auth.refresh';

export interface TokenPair {
  access: string | null;
  refresh: string | null;
}

let _cache: TokenPair = {access: null, refresh: null};

/** Carga los tokens persistidos a la caché en memoria (llamar al arrancar la app). */
export async function loadTokens(): Promise<TokenPair> {
  const [access, refresh] = await Promise.all([
    AsyncStorage.getItem(K_ACCESS),
    AsyncStorage.getItem(K_REFRESH),
  ]);
  _cache = {access, refresh};
  return _cache;
}

/** Persiste (o borra) el par de tokens y actualiza la caché. */
export async function setTokens(tokens: Partial<TokenPair>): Promise<void> {
  if (tokens.access !== undefined) {
    _cache.access = tokens.access;
    if (tokens.access) {
      await AsyncStorage.setItem(K_ACCESS, tokens.access);
    } else {
      await AsyncStorage.removeItem(K_ACCESS);
    }
  }
  if (tokens.refresh !== undefined) {
    _cache.refresh = tokens.refresh;
    if (tokens.refresh) {
      await AsyncStorage.setItem(K_REFRESH, tokens.refresh);
    } else {
      await AsyncStorage.removeItem(K_REFRESH);
    }
  }
}

/** Borra ambos tokens (logout). */
export async function clearTokens(): Promise<void> {
  _cache = {access: null, refresh: null};
  await AsyncStorage.multiRemove([K_ACCESS, K_REFRESH]);
}

/** Lectura síncrona de la caché (usada por el cliente HTTP para las cabeceras). */
export function getAccessToken(): string | null {
  return _cache.access;
}

export function getRefreshToken(): string | null {
  return _cache.refresh;
}
