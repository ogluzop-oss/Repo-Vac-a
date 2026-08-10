"""
Plantillas de asiento + asientos recurrentes (Módulo 12, enriquecimiento de Contabilidad).
Genuinamente ausente. Permite definir plantillas de asiento reutilizables y programarlas como
recurrentes/periódicas (alquileres, cuotas, provisiones…). La generación reutiliza
`contabilidad.asientos.crear_asiento` (NO reimplementa la contabilidad) y se dispara por Scheduler.
Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("contab.plantillas")

_PERIODOS = {"mensual": 30, "bimensual": 60, "trimestral": 91, "semestral": 182, "anual": 365}


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="contab_plantillas_asiento"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("contabilidad", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Plantillas ───────────────────────────────────────────────────────────────
def crear_plantilla(codigo, nombre, lineas, *, concepto=None, id_empresa=None) -> int | None:
    """`lineas`: [{cuenta, debe, haber, descripcion}] (debe cuadrar Σdebe=Σhaber)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO contab_plantillas_asiento (id_empresa, codigo, nombre, concepto, "
                        "lineas) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "concepto=VALUES(concepto), lineas=VALUES(lineas), activo=1",
                        (emp, codigo[:40], nombre[:160], concepto,
                         json.dumps(lineas, ensure_ascii=False, default=str)))
            pid = cur.lastrowid
            if not pid:
                cur.execute("SELECT id FROM contab_plantillas_asiento WHERE id_empresa<=>%s AND codigo=%s",
                            (emp, codigo))
                r = cur.fetchone()
                pid = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            c.commit()
        _audit("PLANTILLA_ALTA", f"{pid}:{codigo}")
        return pid
    except Exception as e:
        logger.error("crear_plantilla: %s", e)
        return None


def listar_plantillas(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM contab_plantillas_asiento WHERE id_empresa<=>%s AND activo=1 "
                        "ORDER BY codigo", (emp,))
            filas = _filas(cur)
        for f in filas:
            try:
                f["lineas"] = json.loads(f.get("lineas") or "[]")
            except Exception:
                f["lineas"] = []
        return filas
    except Exception as e:
        logger.error("listar_plantillas: %s", e)
        return []


def generar_desde_plantilla(id_plantilla, fecha, *, concepto=None, contabilizar=True,
                            id_empresa=None) -> dict | None:
    """Crea un asiento real a partir de la plantilla reutilizando `asientos.crear_asiento`."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT nombre, concepto, lineas FROM contab_plantillas_asiento WHERE id=%s "
                        "AND id_empresa<=>%s", (id_plantilla, emp))
            r = cur.fetchone()
        if not r:
            return None
        r = r if not isinstance(r, dict) else list(r.values())
        lineas = json.loads(r[2] or "[]")
        from src.services.contabilidad import asientos
        res = asientos.crear_asiento(fecha, lineas, concepto=concepto or r[1] or r[0],
                                     tipo="normal", origen="plantilla",
                                     ref_origen=f"PLANT{id_plantilla}-{fecha}",
                                     contabilizar=contabilizar, id_empresa=emp, idempotente=True)
        _audit("PLANTILLA_GENERADA", f"{id_plantilla}:{fecha}")
        return res
    except Exception as e:
        logger.error("generar_desde_plantilla: %s", e)
        return None


# ── Asientos recurrentes ─────────────────────────────────────────────────────
def programar_recurrente(id_plantilla, *, periodicidad="mensual", proxima_fecha=None, concepto=None,
                         fecha_fin=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    if periodicidad not in _PERIODOS:
        periodicidad = "mensual"
    proxima_fecha = proxima_fecha or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO contab_asientos_recurrentes (id_empresa, id_plantilla, concepto, "
                        "periodicidad, proxima_fecha, fecha_fin) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, id_plantilla, concepto, periodicidad, proxima_fecha, fecha_fin))
            rid = cur.lastrowid
            c.commit()
        _audit("RECURRENTE_ALTA", f"{rid}:plant{id_plantilla} {periodicidad}",
               "contab_asientos_recurrentes")
        return rid
    except Exception as e:
        logger.error("programar_recurrente: %s", e)
        return None


def _avanzar(fecha_iso, periodicidad):
    dias = _PERIODOS.get(periodicidad, 30)
    try:
        f = _dt.date.fromisoformat(str(fecha_iso)[:10])
    except Exception:
        f = _dt.date.today()
    return (f + _dt.timedelta(days=dias)).isoformat()


def _job_asientos_recurrentes(id_empresa=None) -> dict:
    """Job de scheduler: genera los asientos recurrentes cuya `proxima_fecha` ya venció y avanza la
    programación. Idempotente por `ref_origen` (crear_asiento idempotente)."""
    emp = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    generados = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_plantilla, concepto, periodicidad, proxima_fecha, fecha_fin "
                        "FROM contab_asientos_recurrentes WHERE id_empresa<=>%s AND activo=1 "
                        "AND proxima_fecha<=%s", (emp, hoy))
            pendientes = _filas(cur)
        for rec in pendientes:
            if rec.get("fecha_fin") and str(rec["fecha_fin"]) < str(rec["proxima_fecha"]):
                continue
            res = generar_desde_plantilla(rec["id_plantilla"], rec["proxima_fecha"],
                                          concepto=rec.get("concepto"), id_empresa=emp)
            if res:
                generados += 1
            prox = _avanzar(rec["proxima_fecha"], rec["periodicidad"])
            activo = 0 if (rec.get("fecha_fin") and prox > str(rec["fecha_fin"])) else 1
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE contab_asientos_recurrentes SET proxima_fecha=%s, "
                            "ultima_generacion=%s, activo=%s WHERE id=%s",
                            (prox, rec["proxima_fecha"], activo, rec["id"]))
                c.commit()
        return {"generados": generados}
    except Exception as e:
        logger.error("_job_asientos_recurrentes: %s", e)
        return {"generados": generados, "error": str(e)}


def registrar_jobs_contabilidad(id_empresa=None):
    try:
        from src.services import scheduler
        scheduler.registrar("contab_asientos_recurrentes", _job_asientos_recurrentes)
        scheduler.registrar_job("contab_asientos_recurrentes", intervalo_horas=24,
                                descripcion="Generación de asientos contables recurrentes")
    except Exception as e:
        logger.debug("registrar_jobs_contabilidad: %s", e)
