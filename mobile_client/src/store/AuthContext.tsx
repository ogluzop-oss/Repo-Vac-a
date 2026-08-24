/**
 * Estado global de autenticación. Carga los tokens al arrancar, expone el usuario activo y las
 * acciones de login / MFA / logout. Usa el módulo `api/auth` (contrato oficial del servidor).
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import * as auth from '@/api/auth';
import {getAccessToken, loadTokens} from '@/api/tokenStore';

type Status = 'loading' | 'signedOut' | 'mfaRequired' | 'signedIn';

interface AuthState {
  status: Status;
  usuario: string | null;
  empresa: number | string | null;
  mfaToken: string | null;
}

interface AuthContextValue extends AuthState {
  signIn: (
    usuario: string,
    password: string,
    idEmpresa?: number | string,
  ) => Promise<auth.LoginResult>;
  submitMfa: (codigo: string) => Promise<auth.LoginResult>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({children}: {children: React.ReactNode}) {
  const [state, setState] = useState<AuthState>({
    status: 'loading',
    usuario: null,
    empresa: null,
    mfaToken: null,
  });

  // Rehidratación: si hay un access token persistido, entramos directamente.
  useEffect(() => {
    (async () => {
      await loadTokens();
      setState(s => ({
        ...s,
        status: getAccessToken() ? 'signedIn' : 'signedOut',
      }));
    })();
  }, []);

  const signIn = useCallback(
    async (usuario: string, password: string, idEmpresa?: number | string) => {
      const res = await auth.login(usuario, password, idEmpresa);
      if (res.kind === 'ok') {
        setState({
          status: 'signedIn',
          usuario: res.data.usuario ?? usuario,
          empresa: res.data.empresa ?? null,
          mfaToken: null,
        });
      } else if (res.kind === 'mfa') {
        setState(s => ({
          ...s,
          status: 'mfaRequired',
          usuario: res.data.usuario ?? usuario,
          mfaToken: res.data.mfa_token,
        }));
      }
      return res;
    },
    [],
  );

  const submitMfa = useCallback(
    async (codigo: string) => {
      const token = state.mfaToken;
      if (!token) {
        return {kind: 'error', status: 400, error: 'no_mfa_token'} as auth.LoginResult;
      }
      const res = await auth.verifyMfa(token, codigo);
      if (res.kind === 'ok') {
        setState({
          status: 'signedIn',
          usuario: res.data.usuario ?? state.usuario,
          empresa: res.data.empresa ?? null,
          mfaToken: null,
        });
      }
      return res;
    },
    [state.mfaToken, state.usuario],
  );

  const signOut = useCallback(async () => {
    await auth.logout();
    setState({status: 'signedOut', usuario: null, empresa: null, mfaToken: null});
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({...state, signIn, submitMfa, signOut}),
    [state, signIn, submitMfa, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  }
  return ctx;
}
