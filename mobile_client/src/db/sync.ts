/**
 * Sincronización OFFLINE-FIRST del dispositivo.
 *
 * Port fiel de `src/services/mobile/sync.py` (Outbox + resolver_conflicto + ESTRATEGIAS), pero con
 * la cola PERSISTIDA en SQLite (no en memoria): las operaciones creadas sin conexión sobreviven a
 * cierres de app y se envían de forma diferida contra la REST API con idempotencia por `_idem`.
 */
import {exec} from './database';
import {request, type ApiResponse} from '@/api/client';

// La resolución de conflictos vive en un módulo puro (testeable sin nativos) y se re-exporta.
export {ESTRATEGIAS, resolverConflicto, type Estrategia} from './conflict';

export type EstadoItem = 'pendiente' | 'sincronizado' | 'fallido';

export interface OutboxItem {
  id: string;
  entidad: string;
  operacion: string;
  datos: Record<string, unknown>;
  idem: string;
  ts: number;
  estado: EstadoItem;
}

export interface SyncResumen {
  sincronizados: number;
  fallidos: number;
  restantes: number;
}

/** Identificador local (hex) — suficiente para PK/idempotencia; no requiere criptografía. */
function genId(): string {
  const rnd = Math.random().toString(16).slice(2);
  return `${Date.now().toString(16)}${rnd}`.padEnd(32, '0').slice(0, 32);
}

/**
 * Cola de operaciones creadas offline, pendientes de sincronizar (idempotentes por `idem`).
 * Misma API pública que la clase `Outbox` de sync.py: encolar / pendientes / marcar / sincronizar.
 */
export class Outbox {
  /** Encola una operación local. Devuelve el id del item. */
  async encolar(
    entidad: string,
    operacion: string,
    datos: Record<string, unknown>,
    idem?: string,
  ): Promise<string> {
    const item: OutboxItem = {
      id: genId(),
      entidad,
      operacion,
      datos,
      idem: idem ?? genId(),
      ts: Date.now() / 1000,
      estado: 'pendiente',
    };
    await exec(
      `INSERT INTO outbox (id, entidad, operacion, datos, idem, ts, estado)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [item.id, entidad, operacion, JSON.stringify(datos), item.idem, item.ts, item.estado],
    );
    return item.id;
  }

  /** Operaciones aún pendientes de sincronizar. */
  async pendientes(): Promise<OutboxItem[]> {
    const res = await exec(
      `SELECT * FROM outbox WHERE estado = 'pendiente' ORDER BY ts ASC`,
    );
    const out: OutboxItem[] = [];
    for (let i = 0; i < res.rows.length; i++) {
      const row = res.rows.item(i);
      out.push({
        id: row.id,
        entidad: row.entidad,
        operacion: row.operacion,
        datos: JSON.parse(row.datos),
        idem: row.idem,
        ts: row.ts,
        estado: row.estado,
      });
    }
    return out;
  }

  /** Cambia el estado de un item. */
  async marcar(itemId: string, estado: EstadoItem): Promise<boolean> {
    const res = await exec(`UPDATE outbox SET estado = ? WHERE id = ?`, [estado, itemId]);
    return res.rowsAffected > 0;
  }

  /** Cuenta de pendientes (útil para badges de UI). */
  async contarPendientes(): Promise<number> {
    const res = await exec(
      `SELECT COUNT(*) AS n FROM outbox WHERE estado = 'pendiente'`,
    );
    return res.rows.item(0).n as number;
  }

  /**
   * Envía las pendientes por la REST API (idempotencia por `_idem` en el cuerpo + cabecera
   * Idempotency-Key). Devuelve el resumen, igual que sync.py.
   */
  async sincronizar(): Promise<SyncResumen> {
    let ok = 0;
    let fallo = 0;
    const items = await this.pendientes();
    for (const it of items) {
      try {
        const r: ApiResponse = await request('POST', `/${it.entidad}`, {
          body: {...it.datos, _idem: it.idem},
          headers: {'Idempotency-Key': it.idem},
        });
        if (r.ok || r.status < 400) {
          await this.marcar(it.id, 'sincronizado');
          ok += 1;
        } else {
          await this.marcar(it.id, 'fallido');
          fallo += 1;
        }
      } catch {
        fallo += 1; // sin red → sigue pendiente para el próximo intento
      }
    }
    const restantes = await this.contarPendientes();
    return {sincronizados: ok, fallidos: fallo, restantes};
  }
}

/** Instancia compartida. */
export const outbox = new Outbox();
