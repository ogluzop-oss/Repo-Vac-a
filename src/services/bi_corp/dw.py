"""
FASE A — Data Warehouse corporativo + ETL interno.

Fuentes unificadas: dominio -> callable(id_empresa)->{metrica: valor}. Reutiliza los calculadores
del BI existente (ventas/compras/inventario/rrhh/tesoreria/contabilidad/aeat) y las analiticas de
los modulos (crm/mrp/calidad/gmao/sat/finanzas). El ETL escribe en dw_hechos (idempotente por
clave). NO consulta el sistema transaccional fuera de los calculadores ya validados.
"""

import datetime as _dt
import json
import logging

from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.dw")
GRANULARIDADES = ("diaria", "semanal", "mensual", "anual")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _rango(granularidad, fecha):
    """Devuelve (desde, hasta, periodo) para la granularidad/fecha dadas."""
    f = fecha or _dt.date.today()
    if isinstance(f, str):
        f = _dt.datetime.strptime(f[:10], "%Y-%m-%d").date()
    if granularidad == "diaria":
        return f, f, f.strftime("%Y-%m-%d")
    if granularidad == "semanal":
        ini = f - _dt.timedelta(days=f.weekday())
        return ini, ini + _dt.timedelta(days=6), f"{f.isocalendar()[0]}-W{f.isocalendar()[1]:02d}"
    if granularidad == "anual":
        return _dt.date(f.year, 1, 1), _dt.date(f.year, 12, 31), str(f.year)
    return _dt.date(f.year, f.month, 1), f, f"{f.year}-{f.month:02d}"   # mensual


# ── Fuentes de datos (reutilizan calculadores/analiticas existentes) ──────────
def _fuente_bi(dominio):
    def _f(id_empresa, desde, hasta):
        from src.services.bi import calculadores
        fn = calculadores.DOMINIOS.get(dominio, (None,))[0]
        return fn(id_empresa, desde, hasta) if fn else {}
    return _f


def _fuente_modulo(import_path, attr="kpis"):
    def _f(id_empresa, desde, hasta):
        try:
            mod = __import__(import_path, fromlist=["x"])
            return getattr(mod, attr)(id_empresa=id_empresa)
        except Exception as e:
            logger.debug("fuente %s: %s", import_path, e)
            return {}
    return _f


# dominio -> (callable, etiqueta del dominio DW)
FUENTES = {
    "ventas": _fuente_bi("ventas"),
    "compras": _fuente_bi("compras"),
    "stock": _fuente_bi("inventario"),
    "rrhh": _fuente_bi("rrhh"),
    "tesoreria": _fuente_bi("tesoreria"),
    "finanzas": _fuente_modulo("src.services.finanzas.ratios", "calcular"),
    "crm": _fuente_modulo("src.services.crm.analitica"),
    "produccion": _fuente_modulo("src.services.mrp.analitica"),
    "calidad": _fuente_modulo("src.services.calidad.analitica"),
    "gmao": _fuente_modulo("src.services.gmao.analitica"),
    "sat": _fuente_modulo("src.services.sat.analitica"),
}


def _aplana(prefijo, d):
    """Convierte un dict de KPIs (posiblemente anidado) en {metrica: float}. Ignora no numericos."""
    out = {}
    for k, v in (d or {}).items():
        nombre = k.split(".")[-1] if "." in k else k
        if isinstance(v, (int, float)):
            out[nombre] = float(v)
    return out


def guardar_hecho(dominio, metrica, valor, *, granularidad, periodo, fecha, id_empresa=None,
                  id_tienda=0, id_almacen=0, dims=None) -> bool:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO dw_hechos (id_empresa, id_tienda, id_almacen, dominio, metrica, valor, "
                        "granularidad, periodo, fecha, dims) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE valor=VALUES(valor), fecha=VALUES(fecha), dims=VALUES(dims)",
                        (eid, id_tienda or 0, id_almacen or 0, dominio, metrica, round(float(valor), 4),
                         granularidad, periodo, fecha, json.dumps(dims) if dims else None))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_hecho: %s", e)
        return False


def ejecutar_etl(*, dominios=None, granularidad="mensual", fecha=None, id_empresa=None) -> dict:
    """Ejecuta el ETL para los dominios indicados (todos por defecto) y persiste en dw_hechos."""
    eid = _emp(id_empresa)
    desde, hasta, periodo = _rango(granularidad, fecha)
    dominios = dominios or list(FUENTES.keys())
    total = 0
    detalle = {}
    for dom in dominios:
        fuente = FUENTES.get(dom)
        if not fuente:
            continue
        try:
            datos = _aplana(dom, fuente(eid, desde, hasta))
            n = 0
            for metrica, valor in datos.items():
                if guardar_hecho(dom, metrica, valor, granularidad=granularidad, periodo=periodo,
                                 fecha=hasta, id_empresa=eid):
                    n += 1
            detalle[dom] = n
            total += n
        except Exception as e:
            logger.error("ETL %s: %s", dom, e)
            detalle[dom] = f"error: {e}"
    _registrar_etl(eid, ",".join(dominios), granularidad, periodo, total)
    log_auditoria("bi_corp", "DW_ETL", "dw_hechos", f"granularidad={granularidad} filas={total}")
    return {"periodo": periodo, "granularidad": granularidad, "filas": total, "detalle": detalle}


def consultar(*, dominio=None, metrica=None, granularidad=None, periodo=None, id_empresa=None,
              id_tienda=None, id_almacen=None, limite=5000) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM dw_hechos WHERE id_empresa=%s"
    p = [eid]
    for col, val in (("dominio", dominio), ("metrica", metrica), ("granularidad", granularidad),
                     ("periodo", periodo), ("id_tienda", id_tienda), ("id_almacen", id_almacen)):
        if val is not None:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY periodo DESC, dominio LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("consultar: %s", e)
        return []


def _registrar_etl(eid, dominio, granularidad, periodo, filas, estado="ok"):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO dw_etl_ejecuciones (id_empresa, dominio, granularidad, periodo, filas, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (eid, dominio[:20], granularidad, periodo, filas, estado))
            conn.commit()
    except Exception:
        pass


# ── Job Scheduler ──────────────────────────────────────────────────────────────
def _job_etl(id_empresa):
    return f"dw_filas={ejecutar_etl(granularidad='mensual', id_empresa=id_empresa).get('filas')}"


def registrar_jobs_dw(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("bi_corp_etl", _job_etl)
    scheduler.registrar_job("bi_corp_etl", intervalo_horas=24, descripcion="ETL Data Warehouse corporativo",
                            id_empresa=id_empresa)
