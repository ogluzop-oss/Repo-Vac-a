"""
Integraciones Comerciales · Servicio/registro (Fase WEB-03). CRUD estructural de integraciones por empresa,
con auditoría de eventos ESTRUCTURALES (no de sincronización). Multiempresa estricto (aislado por `id_empresa`).
Sin conexiones reales: sólo gestiona metadatos/estado. Registro en memoria (degradable) — la persistencia real
se añadirá cuando se implementen las integraciones (reutilizando `db/ecommerce.py`, sin secretos en claro).
"""

import logging
import threading

from src.services.comercio_digital.integraciones_comerciales import \
    catalogo as _cat
from src.services.marketplace.integraciones_comerciales import estados as E
from src.services.marketplace.integraciones_comerciales.modelo import Integracion

logger = logging.getLogger("marketplace.integraciones_comerciales")

_LOCK = threading.RLock()
_REGISTRO = {}   # (id_empresa, plataforma) -> Integracion

# Ámbitos de sincronización PREPARADOS (no se ejecuta nada real todavía).
AMBITOS_SYNC = ("productos", "clientes", "pedidos", "reservas", "stock", "precios", "estados",
                "click_collect")


def _clave(id_empresa, plataforma):
    return (str(id_empresa), (plataforma or "").lower())


def _validar_plataforma(plataforma):
    if _cat.obtener(plataforma) is None:
        raise ValueError(f"plataforma no reconocida: {plataforma}")


def crear_integracion(id_empresa, plataforma, *, nombre=None, url=None, credenciales_ref=None,
                      frecuencia=None, observaciones=None, usuario=None) -> dict:
    """Da de alta una integración (sin conectar). Estado inicial CONFIGURADA si hay ref de credenciales,
    NO_CONFIGURADA en otro caso. Audita `INTEGRACION_CREADA`."""
    _validar_plataforma(plataforma)
    meta = _cat.obtener(plataforma)
    ing = Integracion(id_empresa, plataforma.lower(), nombre=nombre, tipo=meta.get("tipo"), url=url,
                      frecuencia=frecuencia, observaciones=observaciones, credenciales_ref=credenciales_ref)
    with _LOCK:
        _REGISTRO[_clave(id_empresa, plataforma)] = ing
    _audit("INTEGRACION_CREADA", id_empresa, plataforma, usuario)
    return ing.to_dict()


def editar_integracion(id_empresa, plataforma, *, usuario=None, **campos) -> dict:
    """Edita metadatos (nombre/url/frecuencia/observaciones/credenciales_ref). Audita `INTEGRACION_EDITADA`."""
    with _LOCK:
        ing = _REGISTRO.get(_clave(id_empresa, plataforma))
        if not ing:
            return {"ok": False, "error": "integración inexistente"}
        for k in ("nombre", "url", "version", "frecuencia", "observaciones", "credenciales_ref"):
            if k in campos and campos[k] is not None:
                setattr(ing, k, campos[k])
        if ing.estado == E.NO_CONFIGURADA and ing.credenciales_ref:
            ing.estado = E.CONFIGURADA
    _audit("INTEGRACION_EDITADA", id_empresa, plataforma, usuario)
    return {"ok": True, "integracion": ing.to_dict()}


def eliminar_integracion(id_empresa, plataforma, *, usuario=None) -> dict:
    with _LOCK:
        existe = _REGISTRO.pop(_clave(id_empresa, plataforma), None) is not None
    if existe:
        _audit("INTEGRACION_ELIMINADA", id_empresa, plataforma, usuario)
    return {"ok": existe}


def habilitar(id_empresa, plataforma, *, usuario=None) -> dict:
    return _set_habilitada(id_empresa, plataforma, True, usuario)


def deshabilitar(id_empresa, plataforma, *, usuario=None) -> dict:
    return _set_habilitada(id_empresa, plataforma, False, usuario)


def _set_habilitada(id_empresa, plataforma, valor, usuario):
    with _LOCK:
        ing = _REGISTRO.get(_clave(id_empresa, plataforma))
        if not ing:
            return {"ok": False, "error": "integración inexistente"}
        ing.habilitada = valor
        if not valor:
            ing.estado = E.DESHABILITADA
        elif ing.estado == E.DESHABILITADA:
            ing.estado = E.CONFIGURADA if ing.credenciales_ref else E.NO_CONFIGURADA
    _audit("INTEGRACION_HABILITADA" if valor else "INTEGRACION_DESHABILITADA", id_empresa, plataforma, usuario)
    return {"ok": True, "integracion": ing.to_dict()}


def validar(id_empresa, plataforma, *, usuario=None) -> dict:
    """Validación de credenciales **SIMULADA** (Fase WEB-12): NO realiza llamadas HTTP/OAuth/API reales.
    Comprueba que exista una REFERENCIA de credenciales (Secret Manager) y transiciona a VALIDADA usando el
    modelo de estados existente. La conexión real se implementará en fases posteriores. Audita `INTEGRACION_VALIDADA`."""
    with _LOCK:
        ing = _REGISTRO.get(_clave(id_empresa, plataforma))
        if not ing:
            return {"ok": False, "error": "integración inexistente"}
        if not ing.credenciales_ref:
            ing.estado = E.ERROR
            _audit("INTEGRACION_VALIDACION_ERROR", id_empresa, plataforma, usuario)
            return {"ok": False, "error": "faltan credenciales (referencia a Secret Manager)",
                    "estado": ing.estado}
        ing.estado = E.VALIDADA
    _audit("INTEGRACION_VALIDADA", id_empresa, plataforma, usuario)
    return {"ok": True, "estado": E.VALIDADA, "simulada": True, "integracion": ing.to_dict()}


def sincronizar(id_empresa, plataforma, *, ambitos=None, usuario=None) -> dict:
    """Sincronización **SIMULADA** (Fase WEB-12): NO ejecuta sincronización real (ni API, ni webhooks). Aplica
    las transiciones VALIDADA/SINCRONIZADA → SINCRONIZANDO → SINCRONIZADA y sella `ultima_sync`. Preparada para
    los ámbitos productos/clientes/pedidos/reservas/stock/precios/estados/Click&Collect. Audita `INTEGRACION_SINCRONIZADA`."""
    import time
    with _LOCK:
        ing = _REGISTRO.get(_clave(id_empresa, plataforma))
        if not ing:
            return {"ok": False, "error": "integración inexistente"}
        if ing.estado not in (E.VALIDADA, E.SINCRONIZADA):
            return {"ok": False, "error": "requiere estado VALIDADA", "estado": ing.estado}
        ing.estado = E.SINCRONIZANDO          # (simulado: sin trabajo real)
        ing.ultima_sync = time.time()
        ing.estado = E.SINCRONIZADA
    _audit("INTEGRACION_SINCRONIZADA", id_empresa, plataforma, usuario)
    return {"ok": True, "estado": E.SINCRONIZADA, "simulada": True,
            "ambitos": list(ambitos or AMBITOS_SYNC), "integracion": ing.to_dict()}


def obtener(id_empresa, plataforma) -> dict | None:
    with _LOCK:
        ing = _REGISTRO.get(_clave(id_empresa, plataforma))
        return ing.to_dict() if ing else None


def listar(id_empresa) -> list:
    """Integraciones de UNA empresa (aislamiento estricto: nunca de otro tenant)."""
    emp = str(id_empresa)
    with _LOCK:
        return [ing.to_dict() for (e, _p), ing in _REGISTRO.items() if e == emp]


def estado_integraciones(id_empresa) -> dict:
    """Resumen: plataformas del catálogo + estado de la integración de la empresa (o NO_CONFIGURADA)."""
    conf = {i["plataforma"]: i for i in listar(id_empresa)}
    out = []
    for p in _cat.listar():
        i = conf.get(p["clave"])
        out.append({**p, "estado": i["estado"] if i else E.NO_CONFIGURADA,
                    "habilitada": i["habilitada"] if i else False})
    return {"id_empresa": emp_str(id_empresa), "integraciones": out}


def emp_str(id_empresa):
    return str(id_empresa)


def _audit(evento, id_empresa, plataforma, usuario):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "integraciones_comerciales",
                      f"emp={id_empresa} plataforma={plataforma} por={usuario}")
    except Exception:
        pass


def _reset_para_tests():
    with _LOCK:
        _REGISTRO.clear()
