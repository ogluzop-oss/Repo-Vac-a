"""
Corporate Identity Resolver — punto ÚNICO por el que la CCP localiza CUALQUIER entidad corporativa
(empresa, tienda, almacén, departamento, centro, usuario, empleado, cliente, proveedor…).

La CCP NO consulta tablas ni módulos de datos directamente: siempre pasa por este resolver, que
coordina los servicios especializados y la Identidad Operativa (IOC). Así la plataforma queda
desacoplada de la estructura física del ERP.

    Corporate Identity Resolver
        ├── Recipient Resolution Service   (src.services.destinatarios — personas/correos)
        ├── Smart Organization Resolver    (ccp.organizacion — organizaciones→departamentos/correos)
        └── IOC                            (src.services.identidad — identidad operativa de centros)

Multiempresa estricto: toda resolución exige `id_empresa`.
"""

import logging

logger = logging.getLogger("ccp.identidad")


def _empresa(id_empresa):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


# ── Personas / correos (Recipient Resolution Service) ─────────────────────────
def resolver_destinatarios(id_empresa=None, texto="", *, contexto=None, usuario=None, limite=25):
    """Delegación al Servicio de Resolución de Destinatarios (personas/correos)."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return []
    from src.services import destinatarios as _dest
    return _dest.buscar_destinatarios(id_empresa, texto, contexto=contexto, usuario=usuario,
                                      limite=limite)


def resolver_documento(*, id_empresa=None, contexto=None, correo=None, nombre=None, nif=None,
                       tipo=None, usuario=None):
    """Resolución documental (delegada). El Intelligent Recipient Engine (ccp.motor) puede envolver
    esto con reglas por tipo de documento."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return None
    from src.services import destinatarios as _dest
    return _dest.resolver_para_documento(id_empresa=id_empresa, contexto=contexto, correo=correo,
                                         nombre=nombre, nif=nif, tipo=tipo, usuario=usuario)


# ── Organizaciones (Smart Organization Resolver) ──────────────────────────────
def resolver_organizacion(id_empresa=None, texto="", *, tipo=None, nif=None, id_origen=None):
    """Delegación al Smart Organization Resolver (creado en la fase siguiente; import diferido)."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return None
    try:
        from src.services.ccp import organizacion as _org
        return _org.resolver_organizacion(id_empresa, texto, tipo=tipo, nif=nif, id_origen=id_origen)
    except Exception as e:
        logger.debug("resolver_organizacion no disponible: %s", e)
        return None


# ── IOC (identidad operativa de centros) ──────────────────────────────────────
def identidad_centro(id_centro, id_empresa=None):
    """Identidad operativa de un centro vía IOC (si está disponible)."""
    id_empresa = _empresa(id_empresa)
    try:
        from src.services.identidad import identidad as _ioc
        return _ioc.identidad_documento(id_centro, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("IOC identidad_centro: %s", e)
        return None


# ── Resolución umbrella ───────────────────────────────────────────────────────
def resolver_identidad(id_empresa=None, *, texto="", tipo=None, correo=None, nif=None, nombre=None,
                       contexto=None, usuario=None):
    """Resuelve una entidad corporativa cualquiera. Si `tipo` es organizativo (empresa/cliente/
    proveedor/tienda/almacén/centro/departamento) intenta el Organization Resolver; en otro caso (o si
    no hay organización) devuelve el mejor destinatario. Objeto enriquecido, nunca cadena."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return None
    tipos_org = {"empresa", "cliente", "proveedor", "tienda", "almacen", "centro", "departamento",
                 "organizacion", "delegacion", "sucursal"}
    if tipo in tipos_org:
        org = resolver_organizacion(id_empresa, texto or nombre or nif or "", tipo=tipo, nif=nif)
        if org is not None:
            return org
    if correo or nif or nombre:
        return resolver_documento(id_empresa=id_empresa, contexto=contexto, correo=correo,
                                  nombre=nombre, nif=nif, tipo=tipo, usuario=usuario)
    res = resolver_destinatarios(id_empresa, texto, contexto=contexto, usuario=usuario, limite=1)
    return res[0] if res else None
