"""
Adaptador CRM ↔ IOC (Bloque III.1) — punto oficial por el que el CRM resuelve identidad a través de
la `IdentityAPI`, en lugar de resolver empresa por su cuenta. Patrón Strangler: se adopta de forma
incremental y **behavior-preserving** (devuelve el mismo `id_empresa` que antes, con *fallback*).

Reglas:
- El CRM NO accede a SQL/Repository/tablas IOC para identidad: usa este adaptador.
- Dirección de dependencia correcta: CRM → IOC (este módulo importa IOC; IOC nunca importa CRM).
- Multiempresa: siempre se resuelve `id_empresa`; sin fugas entre empresas.
- Eventos/telemetría: en las resoluciones SIGNIFICATIVAS (no en el camino caliente `empresa_id`).
"""

import logging
import threading

logger = logging.getLogger("crm.identidad")

# Telemetría ligera propia del adaptador (complementa la de IdentityAPI).
_LOCK = threading.RLock()
_MET = {"empresa_id": 0, "contexto": 0, "identidad_cliente": 0, "errores": 0}


def _api():
    from src.services.identidad.api import api
    return api()


# ── Resolución de empresa (camino caliente; sustituye al _emp del CRM) ────────
def empresa_id(id_empresa=None):
    """Resuelve la empresa activa a través de la capa de identidad IOC. Comportamiento IDÉNTICO al
    `_emp` histórico (`id_empresa or empresa_actual_id()`), con *fallback* a prueba de fallos.
    Camino caliente: no publica eventos (solo telemetría)."""
    with _LOCK:
        _MET["empresa_id"] += 1
    try:
        from src.services.identidad import _base as B
        return B.emp(id_empresa)
    except Exception:
        # Fallback: comportamiento histórico exacto (nunca romper el CRM).
        try:
            from src.db.empresa import empresa_actual_id
            return id_empresa or empresa_actual_id()
        except Exception:
            return id_empresa


# ── Resoluciones significativas (publican eventos + telemetría IdentityAPI) ──
def contexto(*, id_empresa=None, id_centro=None, id_terminal=None, usuario=None) -> dict:
    """Devuelve el IdentityContext (dict) del ámbito indicado, vía IdentityAPI. Uso: cuando el CRM
    necesita el contexto completo (empresa/grupo/centro/…) para un documento/actividad."""
    with _LOCK:
        _MET["contexto"] += 1
    try:
        return _api().obtener_contexto(id_empresa=id_empresa, id_centro=id_centro,
                                       id_terminal=id_terminal, usuario=usuario)
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("contexto: %s", e)
        return {"id_empresa": empresa_id(id_empresa)}


def identidad_cliente(id_cliente=None, *, id_empresa=None):
    """Resuelve la identidad (contexto de empresa) asociada a una operación de cliente del CRM.
    Operación 'relevante': publica `crm.identidad.resuelta` y cuenta en telemetría."""
    with _LOCK:
        _MET["identidad_cliente"] += 1
    eid = empresa_id(id_empresa)
    try:
        res = _api().resolver_por_empresa(id_empresa=eid)
        try:
            from src.services import eventos
            eventos.publicar("crm.identidad.resuelta", id_empresa=eid, ref_entidad="cliente",
                             ref_id=id_cliente, payload={"origen": "crm"})
        except Exception:
            pass
        return res
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("identidad_cliente: %s", e)
        return None


def resolver(**kw):
    """Passthrough a IdentityAPI.resolver (para cuando el CRM necesite resolver por terminal/tienda…)."""
    return _api().resolver(**kw)


def telemetria() -> dict:
    """Telemetría combinada: contadores del adaptador CRM + snapshot de IdentityAPI."""
    with _LOCK:
        propio = dict(_MET)
    try:
        return {"crm_adaptador": propio, "identity_api": _api().telemetria()}
    except Exception:
        return {"crm_adaptador": propio}
