"""
Adaptadores de LECTURA de la IA (SUBFASE 12: solo lee, nunca escribe).

Punto unico desde el que la IA obtiene informacion, SIEMPRE reutilizando la infraestructura
existente (Event Bus, Centro de Actividad, distribucion/sync, BI y BD). No duplica datos ni
crea tablas. Cada adaptador es best-effort: si una fuente no esta, devuelve vacio sin romper.
"""

import logging

logger = logging.getLogger("ia.adaptadores")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _q(sql, params=(), id_empresa=None):
    """Consulta de solo lectura contra la BD existente. Devuelve lista de dicts (best-effort)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("consulta ia: %s", e)
        return []


# ── Event Bus / Centro de Actividad (Fases 1-3) ───────────────────────────────
def resumen_eventos(id_empresa=None, *, dias=1, usuario=None, perfil=None) -> list:
    try:
        from src.services.actividad import timeline
        return timeline.resumen_por_tipo(usuario, perfil, id_empresa, dias=dias)
    except Exception as e:
        logger.debug("resumen_eventos: %s", e)
        return []


def timeline(id_empresa=None, *, usuario=None, perfil=None, limite=50, prioridad=None) -> list:
    try:
        from src.services.actividad import timeline as _tl
        return _tl.feed(usuario, perfil, id_empresa, prioridad=prioridad, limite=limite)
    except Exception as e:
        logger.debug("timeline: %s", e)
        return []


def badges(id_empresa=None, *, usuario=None, perfil=None) -> dict:
    try:
        from src.services import actividad
        return actividad.contar(usuario=usuario, perfil=perfil, id_empresa=id_empresa)
    except Exception:
        return {}


def eventos_por_tipo(tipo, id_empresa=None, *, dias=7, limite=500) -> list:
    try:
        from src.services import eventos as EV
        return [e for e in EV.buscar(id_empresa=id_empresa, tipo=tipo, limite=limite)]
    except Exception:
        return []


# ── Sincronizacion / infraestructura (Fases 2-4) ──────────────────────────────
def sincronizacion(id_empresa=None) -> dict:
    try:
        from src.services.actividad import sincronizacion as _s
        return _s.infraestructura(id_empresa)
    except Exception:
        return {"terminales": [], "global": {}}


def sync_sesiones(id_empresa=None, limite=50) -> list:
    try:
        from src.services.actividad import sincronizacion as _s
        return _s.sesiones(id_empresa, limite)
    except Exception:
        return []


# ── Business Intelligence (KPIs) ──────────────────────────────────────────────
def kpis(id_empresa=None, *, periodo="mes") -> dict:
    try:
        from src.services.bi import dashboard as _D
        return _D.panel(_emp(id_empresa), periodo=periodo, con_forecast=False) or {}
    except Exception as e:
        logger.debug("kpis: %s", e)
        return {}


# ── Inventario / stock (BD existente, solo lectura) ───────────────────────────
def articulos_bajo_umbral(id_empresa=None) -> list:
    """Articulos por debajo del umbral de reposicion con stock en almacen (misma condicion que
    el Informe de Reposicion)."""
    filas = _q("SELECT codigo, nombre, COALESCE(Stock_total,0) alm, COALESCE(Stock_tienda,0) tie, "
               "COALESCE(Stock_esperado,0) esp FROM articulos", id_empresa=id_empresa)
    out = []
    for f in filas:
        alm, tie, esp = int(f.get("alm") or 0), int(f.get("tie") or 0), int(f.get("esp") or 0)
        if esp > 0 and tie < esp * 0.7 and alm > 0:
            out.append({"codigo": f.get("codigo"), "nombre": f.get("nombre"),
                        "stock_tienda": tie, "stock_almacen": alm, "objetivo": esp,
                        "faltan": max(esp - tie, 0)})
    return out


def articulos_exceso(id_empresa=None) -> list:
    """Articulos con exceso claro sobre el objetivo (riesgo de sobre-stock)."""
    filas = _q("SELECT codigo, nombre, COALESCE(Stock_tienda,0) tie, COALESCE(Stock_esperado,0) esp "
               "FROM articulos", id_empresa=id_empresa)
    out = []
    for f in filas:
        tie, esp = int(f.get("tie") or 0), int(f.get("esp") or 0)
        if esp > 0 and tie > esp * 1.5:
            out.append({"codigo": f.get("codigo"), "nombre": f.get("nombre"),
                        "stock_tienda": tie, "objetivo": esp, "exceso": tie - esp})
    return out


# ── Ventas (para anomalias/predicciones) ──────────────────────────────────────
def ventas_por_dia(id_empresa=None, *, dias=30) -> list:
    emp = _emp(id_empresa)
    return _q("SELECT DATE(fecha) d, COALESCE(SUM(total),0) total, COUNT(*) tickets FROM ventas "
              "WHERE id_empresa=%s AND fecha >= (NOW() - INTERVAL %s DAY) GROUP BY DATE(fecha) "
              "ORDER BY d", (emp, int(dias)), id_empresa=emp)


def mermas_recientes(id_empresa=None, *, dias=30) -> list:
    emp = _emp(id_empresa)
    return _q("SELECT DATE(fecha) d, COALESCE(SUM(cantidad),0) cant, COUNT(*) n FROM mermas "
              "WHERE id_empresa=%s AND fecha >= (NOW() - INTERVAL %s DAY) GROUP BY DATE(fecha)",
              (emp, int(dias)), id_empresa=emp)


# ── Documentos / facturacion / RRHH / licencias (best-effort) ─────────────────
def facturas_pendientes(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    return _q("SELECT * FROM facturas_cliente WHERE id_empresa=%s "
              "AND estado IN ('pendiente','emitida','impagada') LIMIT 200", (emp,), id_empresa=emp)


def contratos_por_vencer(id_empresa=None, *, dias=30) -> list:
    emp = _emp(id_empresa)
    return _q("SELECT * FROM rrhh_contratos WHERE id_empresa=%s "
              "AND fecha_fin IS NOT NULL AND fecha_fin BETWEEN CURDATE() AND (CURDATE() + INTERVAL %s DAY)",
              (emp, int(dias)), id_empresa=emp)


def licencia(id_empresa=None) -> dict:
    try:
        from src.services.saas import licensing as _L
        return _L.licencia_activa(_emp(id_empresa)) or {}
    except Exception:
        return {}
