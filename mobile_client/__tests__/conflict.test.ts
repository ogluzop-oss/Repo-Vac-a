/**
 * Paridad con `resolver_conflicto` de src/services/mobile/sync.py.
 */
import {resolverConflicto} from '@/db/conflict';

describe('resolverConflicto', () => {
  const local = {id: 1, version: 2, ts: 100, quien: 'local'};
  const remoto = {id: 1, version: 3, ts: 50, quien: 'remoto'};

  it('servidor_gana devuelve el remoto', () => {
    expect(resolverConflicto(local, remoto, 'servidor_gana')).toBe(remoto);
  });

  it('cliente_gana devuelve el local', () => {
    expect(resolverConflicto(local, remoto, 'cliente_gana')).toBe(local);
  });

  it('manual marca el conflicto con ambas versiones', () => {
    expect(resolverConflicto(local, remoto, 'manual')).toEqual({
      _conflicto: true,
      local,
      remoto,
    });
  });

  it('ultimo_gana usa la mayor versión', () => {
    expect(resolverConflicto(local, remoto, 'ultimo_gana')).toBe(remoto);
  });

  it('ultimo_gana desempata por timestamp cuando la versión coincide', () => {
    const a = {version: 1, ts: 200};
    const b = {version: 1, ts: 100};
    expect(resolverConflicto(a, b, 'ultimo_gana')).toBe(a);
  });
});
