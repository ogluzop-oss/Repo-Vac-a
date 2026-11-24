"""
Integraciones Comerciales · Servicio/registro (Fase WEB-03). CRUD estructural de integraciones por empresa,
con auditoría de eventos ESTRUCTURALES (no de sincronización). Multiempresa estricto (aislado por `id_empresa`).

Persistencia real (petición explícita, 2026-11-24 — ver migración 0362/`db/ic_integraciones.py`): antes de
esto, cada integración vivía en un diccionario Python en memoria (`_REGISTRO`), perdido en cada reinicio del
backend. Ahora `db.ic_integraciones` es el origen de verdad; este módulo sigue devolviendo exactamente la
misma forma de siempre (`Integracion.to_dict()`), así que la GUI y los 12 adaptadores de canal no cambian.
"""

import logging

from src.db import ic_integraciones as _DB
from src.services.comercio_digital.integraciones_comerciales import \
    catalogo as _cat
from src.services.marketplace.integraciones_comerciales import estados as E
from src.services.marketplace.integraciones_comerciales.modelo import Integracion

logger = logging.getLogger("marketplace.integraciones_comerciales")

# Ámbitos de sincronización PREPARADOS (no se ejecuta nada real todavía).
AMBITOS_SYNC = ("productos", "clientes", "pedidos", "reservas", "stock", "precios", "estados",
                "click_collect")


def _validar_plataforma(plataforma):
    if _cat.obtener(plataforma) is None:
        raise ValueError(f"plataforma no reconocida: {plataforma}")


def _desde_fila(fila: dict) -> Integracion:
    """Reconstruye el objeto de valor `Integracion` (modelo.py, sin tocar) a partir de una fila de
    `ic_integraciones` — único punto donde se traduce BD → objeto en memoria."""
    ing = Integracion(fila["id_empresa"], fila["plataforma"], nombre=fila.get("nombre"),
                      tipo=fila.get("tipo"), url=fila.get("url"), version=fila.get("version"),
                      frecuencia=fila.get("frecuencia"), observaciones=fila.get("observaciones"),
                      credenciales_ref=fila.get("credenciales_ref"), estado=fila.get("estado"))
    ing.habilitada = bool(fila.get("habilitada", True))
    us = fila.get("ultima_sync")
    ing.ultima_sync = us.timestamp() if hasattr(us, "timestamp") else us
    creado = fila.get("creado")
    if hasattr(creado, "timestamp"):
        ing.creado = creado.timestamp()
    elif creado is not None:
        ing.creado = creado
    return ing


def crear_integracion(id_empresa, plataforma, *, nombre=None, url=None, credenciales_ref=None,
                      frecuencia=None, observaciones=None, usuario=None) -> dict:
    """Da de alta una integración (sin conectar). Estado inicial CONFIGURADA si hay ref de credenciales,
    NO_CONFIGURADA en otro caso. Audita `INTEGRACION_CREADA`."""
    _validar_plataforma(plataforma)
    meta = _cat.obtener(plataforma)
    ing = Integracion(id_empresa, plataforma.lower(), nombre=nombre, tipo=meta.get("tipo"), url=url,
                      frecuencia=frecuencia, observaciones=observaciones, credenciales_ref=credenciales_ref)
    _DB.guardar(ing.to_dict())
    _audit("INTEGRACION_CREADA", id_empresa, plataforma, usuario)
    return ing.to_dict()


def editar_integracion(id_empresa, plataforma, *, usuario=None, **campos) -> dict:
    """Edita metadatos (nombre/url/frecuencia/observaciones/credenciales_ref). Audita `INTEGRACION_EDITADA`."""
    fila = _DB.obtener(id_empresa, plataforma)
    if not fila:
        return {"ok": False, "error": "integración inexistente"}
    ing = _desde_fila(fila)
    for k in ("nombre", "url", "version", "frecuencia", "observaciones", "credenciales_ref"):
        if k in campos and campos[k] is not None:
            setattr(ing, k, campos[k])
    if ing.estado == E.NO_CONFIGURADA and ing.credenciales_ref:
        ing.estado = E.CONFIGURADA
    _DB.guardar(ing.to_dict())
    _audit("INTEGRACION_EDITADA", id_empresa, plataforma, usuario)
    return {"ok": True, "integracion": ing.to_dict()}


def eliminar_integracion(id_empresa, plataforma, *, usuario=None) -> dict:
    existe = _DB.eliminar(id_empresa, plataforma)
    if existe:
        _audit("INTEGRACION_ELIMINADA", id_empresa, plataforma, usuario)
    return {"ok": existe}


def habilitar(id_empresa, plataforma, *, usuario=None) -> dict:
    return _set_habilitada(id_empresa, plataforma, True, usuario)


def deshabilitar(id_empresa, plataforma, *, usuario=None) -> dict:
    return _set_habilitada(id_empresa, plataforma, False, usuario)


def _set_habilitada(id_empresa, plataforma, valor, usuario):
    fila = _DB.obtener(id_empresa, plataforma)
    if not fila:
        return {"ok": False, "error": "integración inexistente"}
    ing = _desde_fila(fila)
    ing.habilitada = valor
    if not valor:
        ing.estado = E.DESHABILITADA
    elif ing.estado == E.DESHABILITADA:
        ing.estado = E.CONFIGURADA if ing.credenciales_ref else E.NO_CONFIGURADA
    _DB.guardar(ing.to_dict())
    _audit("INTEGRACION_HABILITADA" if valor else "INTEGRACION_DESHABILITADA", id_empresa, plataforma, usuario)
    return {"ok": True, "integracion": ing.to_dict()}


def validar(id_empresa, plataforma, *, usuario=None) -> dict:
    """Validación de credenciales **SIMULADA** (Fase WEB-12): NO realiza llamadas HTTP/OAuth/API reales.
    Comprueba que exista una REFERENCIA de credenciales (Secret Manager) y transiciona a VALIDADA usando el
    modelo de estados existente. La conexión real se implementará en fases posteriores. Audita `INTEGRACION_VALIDADA`."""
    fila = _DB.obtener(id_empresa, plataforma)
    if not fila:
        return {"ok": False, "error": "integración inexistente"}
    ing = _desde_fila(fila)
    if not ing.credenciales_ref:
        ing.estado = E.ERROR
        _DB.guardar(ing.to_dict())
        _audit("INTEGRACION_VALIDACION_ERROR", id_empresa, plataforma, usuario)
        return {"ok": False, "error": "faltan credenciales (referencia a Secret Manager)",
                "estado": ing.estado}
    ing.estado = E.VALIDADA
    _DB.guardar(ing.to_dict())
    _audit("INTEGRACION_VALIDADA", id_empresa, plataforma, usuario)
    return {"ok": True, "estado": E.VALIDADA, "simulada": True, "integracion": ing.to_dict()}


def sincronizar(id_empresa, plataforma, *, ambitos=None, usuario=None) -> dict:
    """Sincronización **SIMULADA** (Fase WEB-12): NO ejecuta sincronización real (ni API, ni webhooks). Aplica
    las transiciones VALIDADA/SINCRONIZADA → SINCRONIZANDO → SINCRONIZADA y sella `ultima_sync`. Preparada para
    los ámbitos productos/clientes/pedidos/reservas/stock/precios/estados/Click&Collect. Audita `INTEGRACION_SINCRONIZADA`."""
    import time
    fila = _DB.obtener(id_empresa, plataforma)
    if not fila:
        return {"ok": False, "error": "integración inexistente"}
    ing = _desde_fila(fila)
    if ing.estado not in (E.VALIDADA, E.SINCRONIZADA):
        return {"ok": False, "error": "requiere estado VALIDADA", "estado": ing.estado}
    ing.estado = E.SINCRONIZANDO          # (simulado: sin trabajo real)
    ing.ultima_sync = time.time()
    ing.estado = E.SINCRONIZADA
    _DB.guardar(ing.to_dict())
    _audit("INTEGRACION_SINCRONIZADA", id_empresa, plataforma, usuario)
    return {"ok": True, "estado": E.SINCRONIZADA, "simulada": True,
            "ambitos": list(ambitos or AMBITOS_SYNC), "integracion": ing.to_dict()}


def obtener(id_empresa, plataforma) -> dict | None:
    fila = _DB.obtener(id_empresa, plataforma)
    return _desde_fila(fila).to_dict() if fila else None


def listar(id_empresa) -> list:
    """Integraciones de UNA empresa (aislamiento estricto: nunca de otro tenant)."""
    return [_desde_fila(f).to_dict() for f in _DB.listar(id_empresa)]


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
    """SOLO para tests — vacía TODA la tabla (mismo efecto de aislamiento que el
    `_REGISTRO.clear()` en memoria que esto sustituye)."""
    _DB.borrar_todo()
