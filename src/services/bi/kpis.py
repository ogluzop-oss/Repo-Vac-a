"""
Motor único de KPIs (FASE BI-2).

Registra definiciones, calcula valores reutilizando los calculadores por dominio, los persiste
(idempotente) en bi_kpi_valores, y ofrece serie histórica, comparación de periodos y composición
de dashboard. Multiempresa y auditado. No duplica lógica: delega en los servicios existentes.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.services.bi import calculadores as _C

logger = logging.getLogger("bi.kpis")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def sincronizar_definiciones() -> int:
    """Inserta (idempotente) las definiciones de KPI de todos los dominios. Devuelve nº total."""
    ensure_schema()
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for dom, (_fn, defs) in _C.DOMINIOS.items():
                for (codigo, nombre, unidad, sentido) in defs:
                    cur.execute("INSERT IGNORE INTO bi_kpi_def (codigo, dominio, nombre, unidad, sentido) "
                                "VALUES (%s,%s,%s,%s,%s)", (codigo, dom, nombre, unidad, sentido))
                    n += 1
            conn.commit()
    except Exception as e:
        logger.error("sincronizar_definiciones: %s", e)
    return n


def registrar_kpi(codigo, dominio, nombre, *, unidad=None, objetivo=None, sentido="mayor",
                  descripcion=None) -> bool:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bi_kpi_def (codigo, dominio, nombre, unidad, objetivo, sentido, "
                        "descripcion) VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "nombre=VALUES(nombre), unidad=VALUES(unidad), objetivo=VALUES(objetivo), "
                        "sentido=VALUES(sentido)", (codigo, dominio, nombre, unidad, objetivo, sentido, descripcion))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_kpi: %s", e)
        return False


def guardar_valor(codigo, valor, *, periodo, fecha, id_empresa=None, id_tienda=None,
                  id_almacen=None) -> bool:
    """Persiste (upsert idempotente) el valor de un KPI para un periodo/fecha."""
    id_empresa = _emp(id_empresa)
    # La clave UNIQUE incluye id_tienda/id_almacen; en MySQL NULL≠NULL rompería la idempotencia,
    # por eso se normalizan a 0 (dimensión "empresa global") cuando no aplican.
    id_tienda = 0 if id_tienda is None else id_tienda
    id_almacen = 0 if id_almacen is None else id_almacen
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bi_kpi_valores (id_empresa, id_tienda, id_almacen, codigo, valor, "
                        "periodo, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE valor=VALUES(valor)",
                        (id_empresa, id_tienda, id_almacen, codigo, round(float(valor), 4), periodo, fecha))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_valor: %s", e)
        return False


def _rango(periodo, fecha):
    """(desde, hasta) para un periodo terminado en `fecha` (date)."""
    f = fecha if isinstance(fecha, _dt.date) else _dt.datetime.strptime(str(fecha)[:10], "%Y-%m-%d").date()
    if periodo == "dia":
        return f, f
    if periodo == "semana":
        return f - _dt.timedelta(days=f.weekday()), f
    if periodo == "anio":
        return f.replace(month=1, day=1), f
    return f.replace(day=1), f          # mes (defecto)


def calcular_kpi(dominio, *, periodo="mes", fecha=None, id_empresa=None, persistir=True) -> dict:
    """Calcula (y opcionalmente persiste) los KPIs de un dominio para el periodo. Devuelve dict."""
    id_empresa = _emp(id_empresa)
    fecha = fecha or _dt.date.today()
    if isinstance(fecha, str):
        fecha = _dt.datetime.strptime(fecha[:10], "%Y-%m-%d").date()
    desde, hasta = _rango(periodo, fecha)
    fn = _C.DOMINIOS.get(dominio, (None,))[0]
    if not fn:
        return {}
    valores = fn(id_empresa, desde.isoformat(), hasta.isoformat())
    if persistir:
        for codigo, valor in valores.items():
            guardar_valor(codigo, valor, periodo=periodo, fecha=fecha.isoformat(), id_empresa=id_empresa)
        _audit("BI_KPI_CALCULADO", f"{dominio} {periodo} {fecha} ({len(valores)} kpis)")
    return valores


def calcular_todos(*, periodo="mes", fecha=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    out = {}
    for dom in _C.DOMINIOS:
        out.update(calcular_kpi(dom, periodo=periodo, fecha=fecha, id_empresa=id_empresa))
    return out


def serie_historica(codigo, *, periodo=None, id_empresa=None, limite=120) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT fecha, valor, periodo FROM bi_kpi_valores WHERE id_empresa=%s AND codigo=%s"
    p = [id_empresa, codigo]
    if periodo:
        q += " AND periodo=%s"; p.append(periodo)
    q += " ORDER BY fecha LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("serie_historica: %s", e)
        return []


def comparar_periodos(codigo, fecha_a, fecha_b, *, periodo="mes", id_empresa=None) -> dict:
    """Compara el valor del KPI en dos fechas; devuelve {a, b, variacion, variacion_pct}."""
    id_empresa = _emp(id_empresa)

    def _val(f):
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT valor FROM bi_kpi_valores WHERE id_empresa=%s AND codigo=%s AND "
                            "periodo=%s AND fecha=%s", (id_empresa, codigo, periodo, f))
                r = cur.fetchone()
                return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0.0
        except Exception:
            return 0.0
    a, b = _val(fecha_a), _val(fecha_b)
    var = round(b - a, 4)
    pct = round((var / a * 100), 2) if a else None
    return {"codigo": codigo, "a": a, "b": b, "variacion": var, "variacion_pct": pct}


def obtener_dashboard(id_empresa=None, *, periodo="mes", fecha=None) -> dict:
    """Compone el dashboard: último valor por KPI agrupado por dominio (calcula al vuelo)."""
    id_empresa = _emp(id_empresa)
    valores = calcular_todos(periodo=periodo, fecha=fecha, id_empresa=id_empresa)
    secciones = {}
    for dom, (_fn, defs) in _C.DOMINIOS.items():
        secciones[dom] = [{"codigo": c, "nombre": nom, "unidad": u, "valor": valores.get(c, 0.0)}
                          for (c, nom, u, _s) in defs]
    return {"id_empresa": id_empresa, "periodo": periodo, "secciones": secciones}


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bi", accion, "bi_kpi_valores", detalle)
    except Exception:
        pass
