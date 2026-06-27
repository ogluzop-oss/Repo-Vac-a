"""
MRP-A — Listas de materiales (BOM). Simples, multinivel, versiones, alternativos/sustituciones.
Multiempresa, auditado. La explosion multinivel resuelve BOM de componentes que a su vez son fabricados.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("mrp.bom")
ESTADOS = ("borrador", "activa", "obsoleta")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_bom(articulo_final, *, version="1", nombre=None, cantidad_base=1, lineas=None,
              estado="activa", id_empresa=None) -> int | None:
    """Crea una BOM con sus lineas. `lineas`: [{componente, cantidad, merma_pct?, es_alternativo?, sustituye_a?}]."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bom (id_empresa, articulo_final, version, nombre, cantidad_base, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "cantidad_base=VALUES(cantidad_base), estado=VALUES(estado)",
                        (eid, articulo_final, str(version), nombre, cantidad_base,
                         estado if estado in ESTADOS else "borrador"))
            cur.execute("SELECT id FROM bom WHERE id_empresa=%s AND articulo_final=%s AND version=%s",
                        (eid, articulo_final, str(version)))
            bid = cur.fetchone()
            bid = bid[0] if not isinstance(bid, dict) else list(bid.values())[0]
            cur.execute("DELETE FROM bom_lineas WHERE id_bom=%s", (bid,))
            for i, ln in enumerate(lineas or []):
                cur.execute("INSERT INTO bom_lineas (id_empresa, id_bom, componente, cantidad, merma_pct, "
                            "es_alternativo, sustituye_a, orden) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (eid, bid, ln["componente"], ln.get("cantidad", 1), ln.get("merma_pct", 0),
                             1 if ln.get("es_alternativo") else 0, ln.get("sustituye_a"), ln.get("orden", i)))
            conn.commit()
        log_auditoria("mrp", "MRP_BOM_CREATED", "bom", f"bom={bid} {articulo_final} v{version}")
        return bid
    except Exception as e:
        logger.error("crear_bom: %s", e)
        return None


def bom_activa(articulo_final, *, id_empresa=None) -> dict | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM bom WHERE id_empresa=%s AND articulo_final=%s AND estado='activa' "
                        "ORDER BY version DESC LIMIT 1", (eid, articulo_final))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("bom_activa: %s", e)
        return None


def lineas_bom(id_bom, *, incluir_alternativos=False) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM bom_lineas WHERE id_bom=%s"
            if not incluir_alternativos:
                q += " AND es_alternativo=0"
            q += " ORDER BY orden"
            cur.execute(q, (id_bom,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("lineas_bom: %s", e)
        return []


def explosionar(articulo_final, cantidad=1, *, id_empresa=None, _nivel=0, _visto=None) -> list:
    """Explosion multinivel: devuelve necesidades netas de componentes hoja.
    [{componente, cantidad, nivel, fabricado}]. Evita ciclos. cantidad escala por la BOM."""
    eid = _emp(id_empresa)
    _visto = _visto or set()
    if _nivel > 20 or articulo_final in _visto:
        return []
    bom = bom_activa(articulo_final, id_empresa=eid)
    if not bom:
        return []
    _visto = _visto | {articulo_final}
    base = float(bom.get("cantidad_base") or 1) or 1
    factor = cantidad / base
    out = []
    for ln in lineas_bom(bom["id"]):
        comp = ln["componente"]
        neto = float(ln["cantidad"]) * factor * (1 + float(ln.get("merma_pct") or 0) / 100)
        sub = bom_activa(comp, id_empresa=eid)
        if sub:                                  # componente fabricado -> sigue explosionando
            out.append({"componente": comp, "cantidad": round(neto, 4), "nivel": _nivel + 1, "fabricado": True})
            out.extend(explosionar(comp, neto, id_empresa=eid, _nivel=_nivel + 1, _visto=_visto))
        else:                                    # componente hoja (comprado)
            out.append({"componente": comp, "cantidad": round(neto, 4), "nivel": _nivel + 1, "fabricado": False})
    return out
