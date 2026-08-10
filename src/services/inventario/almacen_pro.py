"""
Almacenes PRO (Módulo 5, enriquecimiento). Añade lo ausente: zonas/capacidad/restricciones por
ubicación, picking/packing, cross-docking y consolidación. Reutiliza `ubicaciones` (pasillo/estantería/
nivel ya existentes) y los pedidos existentes. Auditado, multiempresa. No duplica.
"""

import logging

logger = logging.getLogger("inventario.almacen_pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.2): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.stock.identidad_stock import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="almacen_picking"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("inventario", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Zonas / capacidad / restricciones (sobre `ubicaciones`) ─────────────────
def set_atributos_ubicacion(id_ubicacion, *, zona=None, capacidad=None, restriccion=None) -> bool:
    sets, params = [], []
    for col, val in (("zona", zona), ("capacidad", capacidad), ("restriccion", restriccion)):
        if val is not None:
            sets.append(f"{col}=%s"); params.append(val)
    if not sets:
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"UPDATE ubicaciones SET {', '.join(sets)} WHERE id=%s", (*params, id_ubicacion))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_atributos_ubicacion: %s", e)
        return False


def ubicaciones_por_zona(zona, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM ubicaciones WHERE id_empresa<=>%s AND zona=%s", (emp, zona))
            return _filas(cur)
    except Exception as e:
        logger.debug("ubicaciones_por_zona: %s", e)
        return []


# ── Picking / packing ───────────────────────────────────────────────────────
def crear_picking(lineas, *, referencia=None, origen="pedido", id_documento=None, cross_docking=False,
                  responsable=None, id_empresa=None) -> int | None:
    """Crea una lista de picking. `lineas`: [{codigo, cantidad, ubicacion?}]. La ubicación se resuelve
    de `ubicaciones` si no se indica (reutiliza el mapa existente)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO almacen_picking (id_empresa, referencia, origen, id_documento, "
                        "cross_docking, responsable) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, referencia, origen, str(id_documento) if id_documento is not None else None,
                         1 if cross_docking else 0, responsable))
            pid = cur.lastrowid
            for ln in (lineas or []):
                ub = ln.get("ubicacion")
                if not ub and ln.get("codigo"):
                    cur.execute("SELECT CONCAT_WS('-', pasillo, estanteria, balda) u FROM ubicaciones "
                                "WHERE id_empresa<=>%s AND codigo_articulo=%s LIMIT 1", (emp, ln["codigo"]))
                    r = cur.fetchone()
                    ub = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
                cur.execute("INSERT INTO almacen_picking_lineas (id_picking, codigo_articulo, cantidad, "
                            "ubicacion) VALUES (%s,%s,%s,%s)",
                            (pid, ln.get("codigo"), float(ln.get("cantidad") or 0), ub))
            c.commit()
        _audit("PICKING_CREADO", f"{pid}:{len(lineas or [])} líneas cross={cross_docking}")
        return pid
    except Exception as e:
        logger.error("crear_picking: %s", e)
        return None


def confirmar_linea_picking(id_linea, cantidad) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE almacen_picking_lineas SET pickeado=%s, "
                        "estado=CASE WHEN %s>=cantidad THEN 'COMPLETA' ELSE 'PARCIAL' END WHERE id=%s",
                        (float(cantidad), float(cantidad), id_linea))
            c.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("confirmar_linea_picking: %s", e)
        return {"ok": False, "motivo": str(e)}


def cerrar_packing(id_picking, *, id_empresa=None) -> dict:
    """Cierra el picking (packing hecho). Si es cross-docking, deja lista la expedición inmediata."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT cross_docking FROM almacen_picking WHERE id=%s", (id_picking,))
            r = cur.fetchone()
            cross = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
            cur.execute("UPDATE almacen_picking SET estado=%s WHERE id=%s",
                        ("LISTO_EXPEDIR" if cross else "EMPAQUETADO", id_picking))
            c.commit()
        _audit("PACKING_CERRADO", f"{id_picking} cross={cross}")
        return {"ok": True, "cross_docking": bool(cross)}
    except Exception as e:
        logger.error("cerrar_packing: %s", e)
        return {"ok": False, "motivo": str(e)}


def listar_picking(id_empresa=None, *, estado=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM almacen_picking WHERE id_empresa<=>%s"
            p = [emp]
            if estado:
                q += " AND estado=%s"; p.append(estado)
            q += " ORDER BY creada DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("listar_picking: %s", e)
        return []


# ── Cross-docking / consolidación ───────────────────────────────────────────
def cross_docking_desde_recepcion(id_documento, lineas, *, referencia=None, id_empresa=None) -> int | None:
    """Genera un picking marcado como cross-docking a partir de una recepción, para expedir sin
    almacenar. Reutiliza `crear_picking`."""
    return crear_picking(lineas, referencia=referencia, origen="recepcion", id_documento=id_documento,
                         cross_docking=True, id_empresa=id_empresa)


def consolidar_pickings(ids_picking, *, referencia=None, id_empresa=None) -> int | None:
    """Consolida varias listas de picking pendientes en una sola (menos recorridos). Reutiliza las
    líneas existentes."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO almacen_picking (id_empresa, referencia, origen) VALUES (%s,%s,%s)",
                        (emp, referencia or "consolidado", "consolidacion"))
            nuevo = cur.lastrowid
            marcadores = ",".join(["%s"] * len(ids_picking))
            cur.execute(f"UPDATE almacen_picking_lineas SET id_picking=%s WHERE id_picking IN ({marcadores})",
                        (nuevo, *ids_picking))
            cur.execute(f"UPDATE almacen_picking SET estado='CONSOLIDADO' WHERE id IN ({marcadores})",
                        tuple(ids_picking))
            c.commit()
        _audit("PICKING_CONSOLIDADO", f"{nuevo}<-{ids_picking}")
        return nuevo
    except Exception as e:
        logger.error("consolidar_pickings: %s", e)
        return None
