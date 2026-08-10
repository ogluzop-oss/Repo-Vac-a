"""
Corporate Communication Platform (CCP) — fachada / API PÚBLICA estable (Parte M).

Punto ÚNICO de comunicaciones corporativas de Smart Manager AI. Cualquier módulo o canal debe usar
esta API; ningún módulo se comunica directamente con los canales ni consulta datos por su cuenta.

    from src.services import ccp
    ccp.enviar_comunicacion(id_empresa=..., pistas={"nif": "B123"}, contexto="facturacion",
                            plantilla="factura", variables={...})

Solo el canal Email es operativo en esta fase; el resto quedan preparados. Las firmas son estables y
ampliables sin romper compatibilidad (parámetros por palabra clave con valores por defecto).
"""

# Servicio central + Communication ID.
from src.services.ccp.servicio import (  # noqa: F401
    enviar_comunicacion, historial_comunicaciones,
)
# Corporate Identity Resolver (única vía de localización de entidades).
from src.services.ccp.identidad import (  # noqa: F401
    resolver_identidad, resolver_destinatarios, resolver_documento, resolver_organizacion,
)
# Intelligent Recipient Engine (reglas por documento).
from src.services.ccp.motor import (  # noqa: F401
    resolver_documento as resolver_documento_inteligente,
    registrar_regla as registrar_regla_documento, ReglaDocumento,
)
# Registro de canales / política / cola.
from src.services.ccp import canales as canales  # noqa: F401
from src.services.ccp import templates as templates  # noqa: F401  (B1 Templates Manager)
from src.services.ccp import timeline as timeline  # noqa: F401  (B4 Timeline)
from src.services.ccp import conversaciones as conversaciones  # noqa: F401  (B4 Conversation)
from src.services.ccp import campanas as campanas  # noqa: F401  (B3 Campaign Manager)
from src.services.ccp import cola as cola  # noqa: F401  (B3 Outgoing Queue)
from src.services.ccp import analitica as analitica  # noqa: F401  (B5 Analytics)
from src.services.ccp import notificaciones_centro as notificaciones_centro  # noqa: F401  (B6)
from src.services.ccp import gobierno_comunicaciones as gobierno  # noqa: F401  (B10 Governance)
from src.services.ccp import workflows as workflows  # noqa: F401  (B2 Workflow Engine)
from src.services.ccp import contactos_crm as contactos_crm  # noqa: F401  (B7 Contacts CRM)
from src.services.ccp import ia_asistente as ia_asistente  # noqa: F401  (B9 IA Assistant)
from src.services.ccp.modelo import Comunicacion, Resultado  # noqa: F401


# ── Reexports de aprendizaje (delegan en el Servicio de Resolución de Destinatarios) ──
def buscar_destinatarios(id_empresa=None, texto="", *, contexto=None, usuario=None, limite=25):
    from src.services import destinatarios as _dest
    return _dest.buscar_destinatarios(id_empresa, texto, contexto=contexto, usuario=usuario,
                                      limite=limite)


def registrar_envio(correo, nombre=None, *, id_empresa=None, usuario=None, contexto=None):
    from src.services import destinatarios as _dest
    return _dest.registrar_envio(correo, nombre, id_empresa=id_empresa, usuario=usuario,
                                 contexto=contexto)


def registrar_favorito(correo, nombre=None, tipo=None, *, id_empresa=None, usuario=None):
    from src.services import destinatarios as _dest
    return _dest.marcar_favorito(correo, nombre, tipo, id_empresa=id_empresa, usuario=usuario)


def registrar_evento(tipo, *, id_empresa=None, com_id=None, canal=None, estado=None,
                     destinatario=None, usuario=None):
    from src.services.ccp import telemetria as _tel
    return _tel.evento(tipo, id_empresa=id_empresa, com_id=com_id, canal=canal, estado=estado,
                       destinatario=destinatario, usuario=usuario)


__all__ = [
    "enviar_comunicacion", "historial_comunicaciones",
    "resolver_identidad", "resolver_destinatarios", "resolver_documento", "resolver_organizacion",
    "resolver_documento_inteligente", "registrar_regla_documento", "ReglaDocumento",
    "buscar_destinatarios", "registrar_envio", "registrar_favorito", "registrar_evento",
    "canales", "Comunicacion", "Resultado",
]
