/**
 * Badges de notificación del Dashboard (círculo rojo + número, igual que el menú de escritorio).
 *
 * Espejo de `src/api/routers/activity.py`:
 *   GET /activity/badges -> {logistica, pedidos, etiquetas}
 *
 * Solo las 3 capacidades con un concepto real de "trabajo pendiente" (Stock/Ubicación/Escanear
 * artículo son acciones bajo demanda, sin bandeja que contar). "pedidos" cuenta solo los pedidos B2B
 * sin expedir (mismo criterio de siempre); la clave se renombró de "distribucion" al fusionar la
 * pantalla móvil con el ciclo de pedidos online.
 */
import {api} from './client';

export interface Badges {
  logistica: number;
  pedidos: number;
  etiquetas: number;
}

const VACIO: Badges = {
  logistica: 0,
  pedidos: 0,
  etiquetas: 0,
};

export async function obtenerBadges(): Promise<Badges> {
  try {
    const r = await api.get<Badges>('/activity/badges');
    if (!r.ok || !r.json) {
      return VACIO;
    }
    return {
      logistica: Number(r.json.logistica) || 0,
      pedidos: Number(r.json.pedidos) || 0,
      etiquetas: Number(r.json.etiquetas) || 0,
    };
  } catch {
    return VACIO;
  }
}

/**
 * Granularidad de PESTAÑA dentro de un módulo (motor general de eventos,
 * `services.actividad.badges.contar_subtabs`) — espejo de `GET /activity/subtab-badges`.
 * Devuelve `{slug_pestaña: nº pendiente}`; una pestaña ausente del resultado no tiene badge.
 */
export async function obtenerBadgesSubtab(modulo: string): Promise<Record<string, number>> {
  try {
    const r = await api.get<Record<string, number>>('/activity/subtab-badges', {params: {modulo}});
    if (!r.ok || !r.json) {
      return {};
    }
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(r.json)) {
      out[k] = Number(v) || 0;
    }
    return out;
  } catch {
    return {};
  }
}

/** Marca una pestaña (o, sin `subtab`, el módulo entero) como vista — pone su badge a cero. */
export async function marcarVistoSubtab(modulo: string, subtab?: string): Promise<boolean> {
  try {
    const r = await api.post<{ok: boolean}>('/activity/seen', {body: {modulo, subtab}});
    return !!r.json?.ok;
  } catch {
    return false;
  }
}
