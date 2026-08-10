"""
Fuentes del Gemelo Digital (Paquete Enterprise 8) — capa UNICA de LECTURA.

El Digital Twin NUNCA consulta la BD ni los modulos por su cuenta: obtiene TODO desde aqui, y
este modulo reutiliza integramente la infraestructura Enterprise ya existente (Event Bus, Centro
de Actividad, BI, PredictionService, Gobierno Corporativo, adaptadores de IA, servicios de
tesoreria/actividad). Cada fuente es best-effort: si un servicio no esta disponible, devuelve un
valor vacio sin romper. Solo lectura; no duplica datos ni crea tablas.
"""

import logging

logger = logging.getLogger("gemelo.fuentes")


def emp(id_empresa=None):
    """[DEPRECATED — IOC v3] Resolución de empresa activa. Se conserva como SHIM de compatibilidad.

    A partir de IOC v3 (Bloque V), la resolución de identidad debe hacerse mediante IOC:
      · Capa de servicios: `src.services.<mod>.identidad_<mod>.empresa_id()` o `IdentityAPI`.
      · Capa de datos:    `src.db.identidad_contexto.empresa_id()`.
    Esta función sigue funcionando EXACTAMENTE igual (mismo valor devuelto) para no romper el código
    existente que aún la usa; no debe emplearse en desarrollos nuevos. Ver `DOCUMENTACION_IOC.md`.
    """
    # NOTA: comportamiento intacto (shim). No se emite DeprecationWarning en runtime para no alterar
    # el comportamiento observable; la deprecación es documental hasta la retirada final (Fase L4).
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


def _q(sql, params=()):
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("consulta gemelo: %s", e)
        return []


def _scalar(sql, params=(), defecto=0):
    r = _q(sql, params)
    if not r:
        return defecto
    try:
        return list(r[0].values())[0] or defecto
    except Exception:
        return defecto


# ── Organigrama / Gobierno Corporativo (Enterprise 7) ─────────────────────────
def organigrama(id_empresa=None) -> list:
    try:
        from src.services.gobierno import organigrama as _O
        return _O.mapa(id_empresa)
    except Exception:
        return []


def gobierno_dashboard(id_empresa=None) -> dict:
    try:
        from src.services import gobierno
        return gobierno.servicio().dashboard(id_empresa)
    except Exception:
        return {}


def delegaciones_activas(id_empresa=None) -> list:
    try:
        from src.services import gobierno
        return gobierno.servicio().delegaciones_activas(id_empresa)
    except Exception:
        return []


# ── Centro de Actividad / Event Bus / Sincronizacion (Fases 1-4) ──────────────
def infraestructura(id_empresa=None) -> dict:
    try:
        from src.services.actividad import sincronizacion as _s
        return _s.infraestructura(id_empresa)
    except Exception:
        return {"terminales": [], "global": {}}


def sync_panel(id_empresa=None) -> list:
    try:
        from src.services.actividad import sincronizacion as _s
        return _s.panel(id_empresa)
    except Exception:
        return []


def eventos_metricas(id_empresa=None) -> dict:
    try:
        from src.services import eventos as EV
        return EV.metricas(id_empresa=id_empresa)
    except Exception:
        return {}


def eventos_recientes(id_empresa=None, *, tipo=None, limite=200) -> list:
    try:
        from src.services import eventos as EV
        return EV.buscar(id_empresa=id_empresa, tipo=tipo, limite=limite)
    except Exception:
        return []


# ── Automatizacion (Enterprise 4) ─────────────────────────────────────────────
def automatizacion_panel(id_empresa=None) -> dict:
    try:
        from src.services import automatizacion
        return automatizacion.panel.resumen(id_empresa)
    except Exception:
        return {}


def pendientes_automatizacion(id_empresa=None) -> int:
    return int(_scalar("SELECT COUNT(*) FROM automatizaciones_ejecuciones "
                       "WHERE id_empresa=%s AND estado='PENDIENTE'", (emp(id_empresa),)))


# ── PredictionService (Enterprise 3) — riesgo por dominio ─────────────────────
def prediccion():
    from src.services import prediccion as _p
    return _p.servicio()


def riesgos(id_empresa=None) -> list:
    try:
        return prediccion().riesgos(id_empresa)
    except Exception:
        return []


# ── BI (KPIs) ─────────────────────────────────────────────────────────────────
def kpis(id_empresa=None, *, periodo="mes") -> dict:
    try:
        from src.services.bi import dashboard as _D
        return _D.panel(emp(id_empresa), periodo=periodo, con_forecast=False) or {}
    except Exception:
        return {}


# ── Tesoreria (posicion de liquidez) ──────────────────────────────────────────
def posicion_tesoreria(id_empresa=None) -> dict:
    try:
        from src.services.tesoreria import posicion as _P
        return _P.posicion(emp(id_empresa)) or {}
    except Exception:
        return {}


# ── Consultas de solo lectura sobre entidades operativas ──────────────────────
def contar(sql, params=()) -> int:
    return int(_scalar(sql, params))


def filas(sql, params=()) -> list:
    return _q(sql, params)
