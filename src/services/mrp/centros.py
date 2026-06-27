"""
MRP-B/C — Centros de trabajo productivos (capacidad/calendarios/turnos) + rutas y operaciones.
Multiempresa, auditado. NO confundir con centros_trabajo corporativos (RRHH/fiscal): estos son
recursos de produccion (lineas/maquinas/operarios/celulas).
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("mrp.centros")
TIPOS_CENTRO = ("linea", "maquina", "operario", "celula")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


# ── Centros + capacidad ───────────────────────────────────────────────────────
def crear_centro(codigo, nombre, *, tipo="linea", coste_hora=0, horas_dia=8, unidades_hora=0,
                 id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO centros_trabajo_prod (id_empresa, codigo, nombre, tipo, coste_hora) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "tipo=VALUES(tipo), coste_hora=VALUES(coste_hora)",
                        (eid, codigo, nombre, tipo if tipo in TIPOS_CENTRO else "linea", coste_hora))
            cur.execute("SELECT id FROM centros_trabajo_prod WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            cid = cur.fetchone()
            cid = cid[0] if not isinstance(cid, dict) else list(cid.values())[0]
            cur.execute("INSERT INTO capacidades_prod (id_empresa, id_centro, horas_dia, unidades_hora) "
                        "VALUES (%s,%s,%s,%s)", (eid, cid, horas_dia, unidades_hora))
            conn.commit()
        log_auditoria("mrp", "MRP_CENTRO_CREATED", "centros_trabajo_prod", f"centro={cid} {codigo}")
        return cid
    except Exception as e:
        logger.error("crear_centro: %s", e)
        return None


def listar_centros(*, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM centros_trabajo_prod WHERE id_empresa=%s AND activo=1 ORDER BY codigo", (eid,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_centros: %s", e)
        return []


def capacidad_diaria(id_centro) -> float:
    """Unidades/dia que puede producir el centro (horas_dia * unidades_hora)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT horas_dia, unidades_hora FROM capacidades_prod WHERE id_centro=%s "
                        "ORDER BY id DESC LIMIT 1", (id_centro,))
            r = cur.fetchone()
            if not r:
                return 0.0
            r = list(r.values()) if isinstance(r, dict) else r
            return float(r[0] or 0) * float(r[1] or 0)
    except Exception as e:
        logger.error("capacidad_diaria: %s", e)
        return 0.0


def fijar_calendario(id_centro, fecha, *, disponible=True, horas=8, id_empresa=None) -> bool:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO calendarios_prod (id_empresa, id_centro, fecha, disponible, horas) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, id_centro, fecha, 1 if disponible else 0, horas))
            conn.commit()
        return True
    except Exception as e:
        logger.error("fijar_calendario: %s", e)
        return False


# ── Rutas + operaciones ───────────────────────────────────────────────────────
def crear_ruta(articulo_final, codigo, *, nombre=None, operaciones=None, id_empresa=None) -> int | None:
    """operaciones: [{nombre, secuencia?, id_centro?, tiempo_estandar_min?}]."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO rutas_fabricacion (id_empresa, articulo_final, codigo, nombre) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "articulo_final=VALUES(articulo_final)", (eid, articulo_final, codigo, nombre))
            cur.execute("SELECT id FROM rutas_fabricacion WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            rid = cur.fetchone()
            rid = rid[0] if not isinstance(rid, dict) else list(rid.values())[0]
            cur.execute("DELETE FROM operaciones_fabricacion WHERE id_ruta=%s", (rid,))
            for i, op in enumerate(operaciones or []):
                cur.execute("INSERT INTO operaciones_fabricacion (id_empresa, id_ruta, secuencia, nombre, "
                            "id_centro, tiempo_estandar_min) VALUES (%s,%s,%s,%s,%s,%s)",
                            (eid, rid, op.get("secuencia", (i + 1) * 10), op["nombre"],
                             op.get("id_centro"), op.get("tiempo_estandar_min", 0)))
            conn.commit()
        log_auditoria("mrp", "MRP_RUTA_CREATED", "rutas_fabricacion", f"ruta={rid} {codigo}")
        return rid
    except Exception as e:
        logger.error("crear_ruta: %s", e)
        return None


def operaciones_ruta(id_ruta) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM operaciones_fabricacion WHERE id_ruta=%s ORDER BY secuencia", (id_ruta,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("operaciones_ruta: %s", e)
        return []


def ruta_de_articulo(articulo_final, *, id_empresa=None) -> dict | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rutas_fabricacion WHERE id_empresa=%s AND articulo_final=%s "
                        "AND activo=1 ORDER BY id DESC LIMIT 1", (eid, articulo_final))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("ruta_de_articulo: %s", e)
        return None
