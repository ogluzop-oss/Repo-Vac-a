"""
Adaptador Compras ↔ IOC (Bloque III.3) — punto oficial por el que Compras resuelve identidad a través
de la `IdentityAPI`. Patrón Strangler, behavior-preserving. Compras opera con empresa, tienda y almacén
(dato de dominio), por lo que el adaptador ofrece las tres resoluciones y el `IdentityContext` completo.

Reglas:
- Compras NO accede a SQL/Repository/Cache/tablas IOC para identidad: usa este adaptador.
- Dirección de dependencia: Compras → IdentityAPI → Service → Repository → Cache → IOC.
- Multiempresa: siempre se resuelve `id_empresa`; sin fugas entre empresas.
- Eventos/telemetría: solo en resoluciones SIGNIFICATIVAS (nunca en el camino caliente empresa/tienda).
- NO modifica ninguna lógica de Compras.
"""

import logging
import threading

logger = logging.getLogger("compras.identidad")

_LOCK = threading.RLock()
_MET = {"empresa_id": 0, "tienda_actual": 0, "almacen_actual": 0, "contexto": 0,
        "identidad_proveedor": 0, "identidad_pedido": 0, "errores": 0}


def _api():
    from src.services.identidad.api import api
    return api()


# ── Resolución de empresa (camino caliente; sustituye a los _emp de compras) ──
def empresa_id(id_empresa=None):
    """Empresa activa vía la capa de identidad IOC. Comportamiento IDÉNTICO al seam histórico
    (`fuentes.emp`), con *fallback* exacto. Camino caliente: sin eventos."""
    with _LOCK:
        _MET["empresa_id"] += 1
    try:
        from src.services.identidad import _base as B
        eid = B.emp(id_empresa)
        if eid:
            return eid
    except Exception:
        pass
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


# ── Tienda / almacén activos (contexto; behavior-preserving) ──────────────────
def tienda_actual():
    with _LOCK:
        _MET["tienda_actual"] += 1
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def almacen_actual():
    """Almacén activo de contexto, si el ERP lo expone; None si no hay resolución de contexto."""
    with _LOCK:
        _MET["almacen_actual"] += 1
    try:
        from src.db.empresa import almacen_actual_id  # opcional según versión del ERP
        return almacen_actual_id()
    except Exception:
        return None


def empresa_tienda_almacen(id_empresa=None):
    """(empresa, tienda, almacén) para operaciones de compra que necesiten el trío."""
    return empresa_id(id_empresa), tienda_actual(), almacen_actual()


# ── Resoluciones significativas (IdentityContext + eventos) ───────────────────
def contexto(*, id_empresa=None, id_centro=None, id_tienda=None, id_almacen=None) -> dict:
    """IdentityContext completo (empresa/grupo/centro/tienda/almacén) vía IdentityAPI."""
    with _LOCK:
        _MET["contexto"] += 1
    try:
        return _api().obtener_contexto(id_empresa=id_empresa, id_centro=id_centro,
                                       id_tienda=id_tienda, id_almacen=id_almacen)
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("contexto: %s", e)
        return {"id_empresa": empresa_id(id_empresa), "id_tienda": id_tienda, "id_almacen": id_almacen}


def _resolver_significativo(ref_entidad, ref_id, *, id_tienda=None, id_almacen=None, id_empresa=None):
    eid = empresa_id(id_empresa)
    try:
        res = _api().resolver(id_empresa=eid, id_tienda=id_tienda, id_almacen=id_almacen)
        try:
            from src.services import eventos
            eventos.publicar("compras.identidad.resuelta", id_empresa=eid, ref_entidad=ref_entidad,
                             ref_id=ref_id, payload={"id_tienda": id_tienda, "id_almacen": id_almacen,
                                                     "origen": "compras"})
        except Exception:
            pass
        return res
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("_resolver_significativo(%s): %s", ref_entidad, e)
        return None


def identidad_proveedor(id_proveedor=None, *, id_empresa=None):
    """Resuelve la identidad (contexto de empresa) de una operación con proveedor. Publica evento."""
    with _LOCK:
        _MET["identidad_proveedor"] += 1
    return _resolver_significativo("proveedor", id_proveedor, id_empresa=id_empresa)


def identidad_pedido(id_pedido=None, *, id_tienda=None, id_almacen=None, id_empresa=None):
    """Resuelve la identidad (empresa/tienda/almacén) de un pedido de compra. Publica evento."""
    with _LOCK:
        _MET["identidad_pedido"] += 1
    return _resolver_significativo("pedido_compra", id_pedido, id_tienda=id_tienda,
                                   id_almacen=id_almacen, id_empresa=id_empresa)


def telemetria() -> dict:
    """Telemetría combinada: contadores del adaptador Compras + snapshot de IdentityAPI."""
    with _LOCK:
        propio = dict(_MET)
    try:
        return {"compras_adaptador": propio, "identity_api": _api().telemetria()}
    except Exception:
        return {"compras_adaptador": propio}
