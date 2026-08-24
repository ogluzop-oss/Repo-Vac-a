/**
 * Resolución de conflictos de sincronización (lógica PURA, sin dependencias nativas).
 * Port 1:1 de `resolver_conflicto` / `ESTRATEGIAS` de `src/services/mobile/sync.py`.
 * Aislado aquí para poder testearlo en Node sin cargar SQLite ni la red.
 */
export const ESTRATEGIAS = [
  'ultimo_gana',
  'servidor_gana',
  'cliente_gana',
  'manual',
] as const;
export type Estrategia = (typeof ESTRATEGIAS)[number];

export function resolverConflicto<T extends Record<string, any>>(
  local: T,
  remoto: T,
  estrategia: Estrategia = 'ultimo_gana',
): T | {_conflicto: true; local: T; remoto: T} {
  if (estrategia === 'servidor_gana') {
    return remoto;
  }
  if (estrategia === 'cliente_gana') {
    return local;
  }
  if (estrategia === 'manual') {
    return {_conflicto: true, local, remoto};
  }
  // ultimo_gana: mayor versión; a igualdad, mayor timestamp.
  const vl = Number(local.version ?? 0);
  const vr = Number(remoto.version ?? 0);
  if (vl !== vr) {
    return vl > vr ? local : remoto;
  }
  return Number(local.ts ?? 0) >= Number(remoto.ts ?? 0) ? local : remoto;
}
