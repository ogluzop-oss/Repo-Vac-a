"""
Conectores Enterprise (Etapa E · Fase E2) — registro/fachada.

Catálogo de conectores oficiales (SAP/Salesforce/WooCommerce/PrestaShop/Magento/Business Central/
Dynamics 365) construidos sobre infraestructura EXISTENTE (Reglas 6/7/10):

  · Adapter Pattern: cada conector es una subclase de `RestChannelAdapter` (provider-agnostic).
  · Credenciales: se resuelven en runtime vía `comercio_digital.conexiones` (cifradas con el Secret
    Manager Enterprise). NUNCA en código; multiempresa/multitienda estricto.
  · Auto-registro: al importar este paquete se registran los 7 conectores en este registry y su
    Service Contract en `platform.registry` (degradable).
  · Sin tocar el dominio: solo traduce y transporta. Degradable: sin endpoint/credenciales no llama.

No crea un framework paralelo: es un catálogo de adaptadores sobre el framework de conectores existente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("integraciones.enterprise")

FASE = "E2"

# codigo → {"factory": clase_adapter, "categoria": str, "descripcion": str}
_CONECTORES: dict = {}


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("integraciones", accion, "integraciones_enterprise", (detalle or "")[:255])
    except Exception:
        pass


def registrar_conector(codigo, factory, *, categoria="externo", descripcion="") -> bool:
    """Registra un conector (código → factory de adaptador). Extensible: terceros pueden añadir los
    suyos con el mismo contrato. También publica su Service Contract en `platform.registry`."""
    _CONECTORES[codigo] = {"factory": factory, "categoria": categoria, "descripcion": descripcion}
    _registrar_en_plataforma(factory)
    return True


def _registrar_en_plataforma(factory):
    """Publica el ServiceContract del adaptador en el Service Registry Enterprise (degradable)."""
    try:
        from src.platform import registry
        registry.registrar(factory().contrato())
    except Exception as e:
        logger.debug("registro en platform.registry: %s", e)


def disponibles() -> dict:
    """Catálogo de conectores registrados (sin credenciales): código → {categoria, descripcion}."""
    return {c: {"categoria": v["categoria"], "descripcion": v["descripcion"]}
            for c, v in _CONECTORES.items()}


def sincronizar_platform() -> int:
    """Re-publica los Service Contracts de todos los conectores en `platform.registry` (idempotente).
    Útil si el registry se reinicia en runtime. Devuelve el nº de conectores publicados."""
    for entrada in _CONECTORES.values():
        _registrar_en_plataforma(entrada["factory"])
    return len(_CONECTORES)


def adaptador(codigo, *, transporte=None):
    """Instancia el adaptador de un conector (o None si no existe). `transporte` inyectable (pruebas)."""
    entrada = _CONECTORES.get(codigo)
    if not entrada:
        return None
    return entrada["factory"](transporte=transporte)


def _contexto(codigo, id_empresa, nombre, correlation_id=None):
    """Resuelve el AdapterContext (endpoint+credenciales cifradas) reutilizando `conexiones`."""
    from src.services.comercio_digital import conexiones
    return conexiones.contexto(codigo, nombre=nombre, id_empresa=id_empresa,
                               correlation_id=correlation_id)


def registrar_conexion(codigo, *, id_empresa=None, nombre="default", endpoint_base=None,
                       tipo_auth=None, credenciales=None, secret_ref=None, config=None, actor=None):
    """Da de alta la conexión (endpoint + credenciales CIFRADAS) de un conector, reutilizando el
    registro seguro de `conexiones` (Secret Manager). El tipo de auth por defecto lo aporta el
    conector. Nunca persiste secretos en claro."""
    if codigo not in _CONECTORES:
        return False
    from src.services.comercio_digital import conexiones
    ta = tipo_auth or getattr(_CONECTORES[codigo]["factory"], "tipo_auth_defecto", "apikey")
    ok = conexiones.registrar(codigo, nombre=nombre, id_empresa=id_empresa, tipo_auth=ta,
                              endpoint_base=endpoint_base, config=config, credenciales=credenciales,
                              secret_ref=secret_ref, actor=actor)
    if ok:
        _audit("CONECTOR_CONEXION", f"{codigo}/{nombre}")
    return ok


def probar(codigo, *, id_empresa=None, nombre="default") -> dict:
    """Prueba de conexión degradable (valida config+credenciales resolubles) vía `conexiones.probar`."""
    if codigo not in _CONECTORES:
        return {"ok": False, "motivo": "conector desconocido"}
    from src.services.comercio_digital import conexiones
    return conexiones.probar(codigo, nombre=nombre, id_empresa=id_empresa)


def enviar(codigo, mensaje, *, id_empresa=None, nombre="default", transporte=None,
           correlation_id=None) -> dict:
    """Traduce y envía un mensaje neutro del dominio a la plataforma externa. Degradable: si no hay
    conexión configurada, el adaptador devuelve `{ok:False, degradado:True}` sin llamar a la red."""
    ad = adaptador(codigo, transporte=transporte)
    if ad is None:
        return {"ok": False, "estado": "desconocido", "conector": codigo}
    ctx = _contexto(codigo, id_empresa, nombre, correlation_id)
    res = ad.enviar(ad.traducir_saliente(mensaje or {}), contexto=ctx)
    _audit("CONECTOR_ENVIAR", f"{codigo}/{nombre} → {res.get('ok')}")
    return res


def recibir(codigo, *, id_empresa=None, nombre="default", transporte=None) -> list:
    """Recibe y traduce los mensajes entrantes de la plataforma externa a la forma neutra del dominio.
    Degradable: sin endpoint devuelve []. El adaptador NUNCA invoca al dominio (traducción pura)."""
    ad = adaptador(codigo, transporte=transporte)
    if ad is None:
        return []
    ctx = _contexto(codigo, id_empresa, nombre)
    return [ad.traducir_entrante(x) for x in (ad.recibir(contexto=ctx) or [])]


def descriptor() -> dict:
    return {"servicio": "integraciones.enterprise", "etapa": "E", "fase": FASE,
            "estado": "implementado", "conectores": sorted(_CONECTORES.keys()),
            "reutiliza": ["RestChannelAdapter (Adapter Pattern)", "comercio_digital.conexiones",
                          "secret_manager", "platform.registry", "capabilities"],
            "provider_agnostic": True, "degradable": True, "multiempresa": True,
            "secretos_en_claro": False, "motor_nuevo": False, "modifica_dominio": False}


def _registrar_por_defecto():
    """Auto-registro de los 7 conectores oficiales (idempotente)."""
    if "woocommerce" in _CONECTORES:
        return
    from src.services.integraciones.enterprise import adaptadores as A
    for cls, categoria, descripcion in A.CATALOGO:
        registrar_conector(cls.canal, cls, categoria=categoria, descripcion=descripcion)


_registrar_por_defecto()

__all__ = ["FASE", "registrar_conector", "disponibles", "sincronizar_platform", "adaptador",
           "registrar_conexion", "probar", "enviar", "recibir", "descriptor"]
