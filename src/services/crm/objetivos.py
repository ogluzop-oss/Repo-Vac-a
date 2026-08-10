"""
CRM · Objetivos comerciales (Módulo 1, enriquecimiento). Fija objetivos/cuotas por responsable y
período (ventas, oportunidades ganadas o visitas) y calcula el progreso REAL reutilizando los datos ya
existentes (ventas, crm_oportunidades, crm_actividades). Integra auditoría + BI. No duplica lógica.
"""

import logging

logger = logging.getLogger("crm.objetivos")

TIPOS = ("ventas", "oportunidades", "visitas")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.crm.identidad_crm import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("crm", accion, "crm_objetivos", (detalle or "")[:255])
    except Exception:
        pass


def crear_objetivo(responsable, objetivo_valor, *, tipo="ventas", periodo=None,
                   fecha_inicio=None, fecha_fin=None, id_empresa=None) -> int | None:
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {tipo}")
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO crm_objetivos (id_empresa, responsable, tipo, periodo, "
                        "objetivo_valor, fecha_inicio, fecha_fin) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, responsable, tipo, periodo, float(objetivo_valor or 0),
                         fecha_inicio, fecha_fin))
            oid = cur.lastrowid
            c.commit()
        _audit("OBJETIVO_CREADO", f"{oid}:{responsable}/{tipo}={objetivo_valor}")
        return oid
    except Exception as e:
        logger.error("crear_objetivo: %s", e)
        return None


def _real(tipo, responsable, fi, ff, emp) -> float:
    """Valor REAL logrado en el período, reutilizando las tablas existentes."""
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            if tipo == "ventas":
                cur.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE id_empresa<=>%s "
                            "AND (%s IS NULL OR empleado=%s) AND (%s IS NULL OR fecha>=%s) "
                            "AND (%s IS NULL OR fecha<=%s)",
                            (emp, responsable, responsable, fi, fi, ff, ff))
            elif tipo == "oportunidades":
                cur.execute("SELECT COALESCE(SUM(valor),0) FROM crm_oportunidades WHERE id_empresa<=>%s "
                            "AND estado='ganada' AND (%s IS NULL OR responsable=%s) "
                            "AND (%s IS NULL OR fecha_cierre>=%s) AND (%s IS NULL OR fecha_cierre<=%s)",
                            (emp, responsable, responsable, fi, fi, ff, ff))
            else:  # visitas
                cur.execute("SELECT COUNT(*) FROM crm_actividades WHERE id_empresa<=>%s AND tipo='visita' "
                            "AND (%s IS NULL OR responsable=%s) AND (%s IS NULL OR fecha_creacion>=%s) "
                            "AND (%s IS NULL OR fecha_creacion<=%s)",
                            (emp, responsable, responsable, fi, fi, ff, ff))
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.debug("_real(%s): %s", tipo, e)
        return 0.0


def progreso(id_empresa=None) -> list:
    """Objetivos con su progreso real (objetivo/real/%/cumplido). Reutiliza ventas/oport./actividades."""
    emp = _emp(id_empresa)
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    out = []
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM crm_objetivos WHERE id_empresa<=>%s ORDER BY creada DESC", (emp,))
            objetivos = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("progreso: %s", e)
        return out
    for o in objetivos:
        real = _real(o["tipo"], o.get("responsable"), o.get("fecha_inicio"), o.get("fecha_fin"), emp)
        meta = float(o.get("objetivo_valor") or 0)
        pct = round(real / meta * 100, 1) if meta else None
        out.append({**o, "real": real, "pct": pct, "cumplido": (pct is not None and pct >= 100)})
    return out


def listar(id_empresa=None) -> list:
    return progreso(id_empresa)
