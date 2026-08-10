"""
Centros de coste / contabilidad analítica dimensional (Módulo 11, enriquecimiento de Finanzas).
Genuinamente ausente hasta ahora. Permite definir centros de coste jerárquicos e imputar gastos/
ingresos a ellos (manual o desde cualquier origen: nómina, compra, amortización…) y obtener el
resultado analítico por centro y periodo. Multiempresa, auditado. No duplica el PGC contable:
es la dimensión analítica transversal.
"""

import logging

logger = logging.getLogger("finanzas.centros_coste")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.finanzas.identidad_finanzas import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="centros_coste"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("analitica", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def crear_centro(codigo, nombre, *, id_padre=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO centros_coste (id_empresa, codigo, nombre, id_padre) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "id_padre=VALUES(id_padre), activo=1",
                        (emp, codigo[:40], nombre[:160], id_padre))
            cid = cur.lastrowid
            if not cid:
                cur.execute("SELECT id FROM centros_coste WHERE id_empresa<=>%s AND codigo=%s", (emp, codigo))
                r = cur.fetchone()
                cid = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            c.commit()
        _audit("CENTRO_ALTA", f"{cid}:{codigo}")
        return cid
    except Exception as e:
        logger.error("crear_centro: %s", e)
        return None


def listar_centros(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM centros_coste WHERE id_empresa<=>%s AND activo=1 ORDER BY codigo", (emp,))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_centros: %s", e)
        return []


def imputar(id_centro_coste, importe, *, concepto=None, signo="gasto", periodo=None,
            origen_tipo="manual", origen_id=None, id_empresa=None) -> int | None:
    """Imputa un gasto (signo='gasto') o ingreso (signo='ingreso') a un centro de coste."""
    emp = _emp(id_empresa)
    if signo not in ("gasto", "ingreso"):
        signo = "gasto"
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO imputaciones_analiticas (id_empresa, id_centro_coste, origen_tipo, "
                        "origen_id, concepto, importe, signo, periodo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_centro_coste, origen_tipo,
                         str(origen_id) if origen_id is not None else None, concepto,
                         round(float(importe or 0), 2), signo, periodo))
            iid = cur.lastrowid
            c.commit()
        _audit("IMPUTACION", f"centro{id_centro_coste} {signo} {importe}€", "imputaciones_analiticas")
        return iid
    except Exception as e:
        logger.error("imputar: %s", e)
        return None


def resultado_por_centro(id_empresa=None, *, periodo=None, id_centro_coste=None) -> list:
    """Resultado analítico (ingresos - gastos) agrupado por centro de coste."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT ia.id_centro_coste, cc.codigo, cc.nombre, "
                 "COALESCE(SUM(CASE WHEN ia.signo='ingreso' THEN ia.importe ELSE 0 END),0) AS ingresos, "
                 "COALESCE(SUM(CASE WHEN ia.signo='gasto' THEN ia.importe ELSE 0 END),0) AS gastos "
                 "FROM imputaciones_analiticas ia "
                 "LEFT JOIN centros_coste cc ON cc.id=ia.id_centro_coste "
                 "WHERE ia.id_empresa<=>%s")
            p = [emp]
            if periodo:
                q += " AND ia.periodo=%s"; p.append(periodo)
            if id_centro_coste:
                q += " AND ia.id_centro_coste=%s"; p.append(id_centro_coste)
            q += " GROUP BY ia.id_centro_coste, cc.codigo, cc.nombre ORDER BY cc.codigo"
            cur.execute(q, p)
            filas = _filas(cur)
        for f in filas:
            f["resultado"] = round(float(f.get("ingresos") or 0) - float(f.get("gastos") or 0), 2)
        return filas
    except Exception as e:
        logger.error("resultado_por_centro: %s", e)
        return []
