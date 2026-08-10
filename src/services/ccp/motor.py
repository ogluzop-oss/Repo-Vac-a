"""
Intelligent Recipient Engine (Parte D) — no solo encontrar destinatarios, sino el CORRECTO.

Basado en REGLAS (no IA). Cada tipo documental define su regla: tipo de destinatario, departamento
preferido, correo preferido, canal, idioma, plantilla y prioridad. `resolver_documento(...)` usa la
regla + el Corporate Identity Resolver para devolver el destinatario adecuado (p. ej. Factura → cliente
→ correo de facturación, NO el comercial). Registro extensible: añadir un tipo = registrar una regla.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("ccp.motor")


@dataclass
class ReglaDocumento:
    tipo_documento: str
    tipo_destinatario: str | None = None      # cliente/proveedor/empleado/…
    departamento_preferido: str | None = None  # contexto/departamento afín (compras, facturacion…)
    correo_preferido: str | None = None        # sobrescribe si se conoce
    canal: str | None = None                   # canal preferido (hoy la Channel Policy usa email)
    idioma: str | None = None
    plantilla: str | None = None
    prioridad: str = "normal"


_REGLAS: dict = {}


def registrar_regla(regla: ReglaDocumento):
    """Registra (o reemplaza) la regla de un tipo documental. Punto de extensión oficial."""
    _REGLAS[regla.tipo_documento] = regla
    return regla


def regla(tipo_documento) -> ReglaDocumento | None:
    return _REGLAS.get(tipo_documento)


def reglas() -> dict:
    return dict(_REGLAS)


def resolver_documento(tipo_documento, *, id_empresa=None, correo=None, nombre=None, nif=None,
                       contexto=None, usuario=None) -> dict:
    """Resuelve el destinatario CORRECTO para un tipo documental, aplicando su regla. Devuelve un dict
    con `destinatario` (Destinatario o None) + canal/plantilla/idioma/prioridad/departamento sugeridos.
    Toda la localización pasa por el Corporate Identity Resolver."""
    r = _REGLAS.get(tipo_documento)
    ctx = contexto or (r.departamento_preferido if r else None)
    tipo_dest = r.tipo_destinatario if r else None
    correo_pref = correo or (r.correo_preferido if r else None)

    from src.services.ccp import identidad as _identidad
    dest = _identidad.resolver_documento(id_empresa=id_empresa, contexto=ctx, correo=correo_pref,
                                         nombre=nombre, nif=nif, tipo=tipo_dest, usuario=usuario)
    return {
        "destinatario": dest,
        "canal": (r.canal if r else None),
        "plantilla": (r.plantilla if r else None),
        "idioma": (r.idioma if r else None),
        "prioridad": (r.prioridad if r else "normal"),
        "departamento": ctx,
        "tipo_destinatario": tipo_dest,
    }


# ── Reglas SEMILLA (extensibles con una línea) ────────────────────────────────
def _sembrar():
    registrar_regla(ReglaDocumento("factura", tipo_destinatario="cliente",
                                   departamento_preferido="facturacion", plantilla="facturas"))
    registrar_regla(ReglaDocumento("pedido", tipo_destinatario="proveedor",
                                   departamento_preferido="compras", plantilla="pedidos"))
    registrar_regla(ReglaDocumento("albaran", tipo_destinatario="cliente",
                                   departamento_preferido="logistica"))
    registrar_regla(ReglaDocumento("presupuesto", tipo_destinatario="cliente",
                                   departamento_preferido="ventas"))
    registrar_regla(ReglaDocumento("nomina", tipo_destinatario="empleado",
                                   departamento_preferido="rrhh", plantilla="nominas"))
    registrar_regla(ReglaDocumento("contrato", tipo_destinatario="empleado",
                                   departamento_preferido="rrhh", plantilla="contratos"))
    registrar_regla(ReglaDocumento("certificado", tipo_destinatario="empleado",
                                   departamento_preferido="rrhh"))
    registrar_regla(ReglaDocumento("informe", tipo_destinatario="cliente",
                                   departamento_preferido="administracion"))


_sembrar()
