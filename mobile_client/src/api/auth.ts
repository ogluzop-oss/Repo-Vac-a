/**
 * Ciclo de autenticación del cliente móvil.
 *
 * Espejo de `src/services/mobile/auth.py` + el router real `src/api/routers/auth.py`:
 *   POST /auth/login  {usuario, password, id_empresa?}
 *        -> 200 {access, refresh, empresa, usuario, mfa_enrollment_required?}
 *        -> 200 {mfa_required:true, mfa_token, usuario}   (2º factor ACTIVO)
 *        -> 401 {error:"invalid_credentials"}
 *   POST /auth/mfa    {mfa_token, codigo}  -> 200 {access, refresh, ...} | 401 {error}
 *   POST /auth/refresh {refresh}           -> 200 {access}               (lo gestiona client.ts)
 *
 * No crea un segundo sistema de auth: envuelve el oficial (JWT + refresh + MFA/TOTP).
 */
import {api} from './client';
import {clearTokens, setTokens} from './tokenStore';

export interface LoginTokens {
  access: string;
  refresh: string;
  empresa?: number | string | null;
  usuario?: string;
  mfa_enrollment_required?: boolean;
}

export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
  usuario?: string;
}

export type LoginResult =
  | {kind: 'ok'; data: LoginTokens}
  | {kind: 'mfa'; data: MfaChallenge}
  | {kind: 'error'; status: number; error: string};

type LoginBody = Partial<LoginTokens> & Partial<MfaChallenge> & {error?: string};

/** Login con usuario + contraseña (+ empresa opcional para multi-tenant). */
export async function login(
  usuario: string,
  password: string,
  idEmpresa?: number | string,
): Promise<LoginResult> {
  const r = await api.post<LoginBody>('/auth/login', {
    auth: false,
    body: {usuario, password, id_empresa: idEmpresa},
  });
  const j = r.json;

  if (r.status === 401 || !j) {
    return {kind: 'error', status: r.status, error: j?.error ?? 'invalid_credentials'};
  }
  if (j.mfa_required && j.mfa_token) {
    return {kind: 'mfa', data: {mfa_required: true, mfa_token: j.mfa_token, usuario: j.usuario}};
  }
  if (j.access && j.refresh) {
    await setTokens({access: j.access, refresh: j.refresh});
    return {kind: 'ok', data: j as LoginTokens};
  }
  return {kind: 'error', status: r.status, error: j.error ?? 'unexpected_response'};
}

/** Completa el reto MFA (TOTP o recovery code) con el `mfa_token` recibido en el login. */
export async function verifyMfa(
  mfaToken: string,
  codigo: string,
): Promise<LoginResult> {
  const r = await api.post<LoginBody>('/auth/mfa', {
    auth: false,
    body: {mfa_token: mfaToken, codigo},
  });
  const j = r.json;
  if (r.ok && j?.access && j?.refresh) {
    await setTokens({access: j.access, refresh: j.refresh});
    return {kind: 'ok', data: j as LoginTokens};
  }
  return {kind: 'error', status: r.status, error: j?.error ?? 'invalid_mfa'};
}

/** Cierra la sesión local (borra tokens). La revocación remota es un endpoint aparte. */
export async function logout(): Promise<void> {
  await clearTokens();
}
