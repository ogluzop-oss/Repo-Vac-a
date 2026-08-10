"""
Producción PRO (Módulo 14, enriquecimiento). Añade SOLO lo ausente sobre el módulo de fabricación
existente (`services/mrp/ordenes.py|centros.py`): PARTES DE TRABAJO / control de planta (registro de
operaciones ejecutadas con tiempos reales, avance por operación de la ruta) y CRP (carga vs capacidad
de los centros de trabajo, reutilizando `centros.capacidad_diaria`). Multiempresa, auditado. No
duplica el ciclo de la OF ni los centros/rutas.
"""

import datetime as _dt
import logging

logger = logging.getLogger("mrp.produccion_pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.4): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.produccion.identidad_produccion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="partes_trabajo_prod"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("produccion", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Partes de trabajo (control de planta) ────────────────────────────────────
def registrar_parte(id_orden, *, id_centro=None, id_operacion=None, secuencia=None, cantidad=0,
                    tiempo_min=0, operario=None, fecha=None, observaciones=None, id_empresa=None) -> int | None:
    """Registra un parte de trabajo (operación ejecutada) contra una orden de fabricación."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO partes_trabajo_prod (id_empresa, id_orden, id_centro, id_operacion, "
                        "secuencia, cantidad, tiempo_min, operario, fecha, observaciones) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_orden, id_centro, id_operacion, secuencia, float(cantidad or 0),
                         float(tiempo_min or 0), operario, fecha or _dt.date.today().isoformat(),
                         observaciones))
            pid = cur.lastrowid
            c.commit()
        _audit("PARTE_REGISTRADO", f"{pid}:of{id_orden} centro{id_centro} {tiempo_min}min")
        return pid
    except Exception as e:
        logger.error("registrar_parte: %s", e)
        return None


def partes_de_orden(id_orden, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM partes_trabajo_prod WHERE id_empresa<=>%s AND id_orden=%s "
                        "ORDER BY secuencia, id", (emp, id_orden))
            return _filas(cur)
    except Exception as e:
        logger.error("partes_de_orden: %s", e)
        return []


def avance_orden(id_orden, *, id_empresa=None) -> dict:
    """Avance de la OF: nº de operaciones de la ruta con parte registrado vs total de la ruta, y
    cantidad/tiempo acumulados. Reutiliza la ruta del artículo existente."""
    emp = _emp(id_empresa)
    try:
        partes = partes_de_orden(id_orden, id_empresa=emp)
        ops_con_parte = {p.get("id_operacion") for p in partes if p.get("id_operacion")}
        cantidad = round(sum(float(p.get("cantidad") or 0) for p in partes), 3)
        tiempo = round(sum(float(p.get("tiempo_min") or 0) for p in partes), 2)
        total_ops = None
        try:
            from src.services.mrp import ordenes, centros
            of = ordenes.obtener_of(id_orden) or {}
            art = of.get("articulo_final") or of.get("articulo")
            if art:
                ruta = centros.ruta_de_articulo(art, id_empresa=emp)
                if ruta:
                    total_ops = len(centros.operaciones_ruta(ruta.get("id") or ruta.get("id_ruta")))
        except Exception:
            pass
        pct = round(len(ops_con_parte) / total_ops * 100, 1) if total_ops else None
        return {"operaciones_con_parte": len(ops_con_parte), "operaciones_ruta": total_ops,
                "avance_pct": pct, "cantidad_reportada": cantidad, "tiempo_total_min": tiempo}
    except Exception as e:
        logger.error("avance_orden: %s", e)
        return {}


# ── CRP: carga vs capacidad ──────────────────────────────────────────────────
def carga_centro(id_centro, *, desde=None, hasta=None, id_empresa=None) -> dict:
    """Carga (horas de partes de trabajo) frente a la capacidad del centro en el rango. Reutiliza
    `centros.capacidad_diaria` para la capacidad teórica."""
    emp = _emp(id_empresa)
    hoy = _dt.date.today()
    desde = desde or (hoy - _dt.timedelta(days=7)).isoformat()
    hasta = hasta or hoy.isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(tiempo_min),0) FROM partes_trabajo_prod WHERE id_empresa<=>%s "
                        "AND id_centro=%s AND fecha BETWEEN %s AND %s", (emp, id_centro, desde, hasta))
            r = cur.fetchone()
            carga_min = float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
        carga_horas = round(carga_min / 60.0, 2)
        # Capacidad teórica: horas/día * nº días laborables del rango.
        cap_dia_uds = 0.0
        horas_dia = 8.0
        try:
            from src.services.mrp import centros
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("SELECT horas_dia FROM capacidades_prod WHERE id_centro=%s ORDER BY id DESC "
                            "LIMIT 1", (id_centro,))
                rr = cur.fetchone()
                if rr:
                    horas_dia = float((rr[0] if not isinstance(rr, dict) else list(rr.values())[0]) or 8)
            cap_dia_uds = centros.capacidad_diaria(id_centro)
        except Exception:
            pass
        try:
            d0 = _dt.date.fromisoformat(str(desde)[:10]); d1 = _dt.date.fromisoformat(str(hasta)[:10])
            dias = max(1, (d1 - d0).days + 1)
        except Exception:
            dias = 1
        cap_horas = round(horas_dia * dias, 2)
        ocupacion = round(carga_horas / cap_horas * 100, 1) if cap_horas else None
        return {"carga_horas": carga_horas, "capacidad_horas": cap_horas,
                "ocupacion_pct": ocupacion, "sobrecarga": bool(ocupacion and ocupacion > 100),
                "capacidad_uds_dia": cap_dia_uds}
    except Exception as e:
        logger.error("carga_centro: %s", e)
        return {}
