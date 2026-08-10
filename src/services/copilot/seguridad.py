"""
Seguridad del Copiloto por rol (Paquete Enterprise 5, SUBFASE 5.12). Un cajero (OPERARIO) no
puede consultar tesoreria, nominas, RRHH ni beneficios globales. Solo se responde lo autorizado
por el rol. Reutiliza el concepto de perfiles del ERP (no crea un RBAC nuevo).
"""

_ROLES_GLOBALES = {"ADMINISTRADOR", "GERENTE", "SUPERADMIN"}

# Dominios sensibles vetados a roles no directivos.
DOMINIOS_SENSIBLES = {"tesoreria", "rrhh", "nominas", "beneficios", "contabilidad",
                      "facturacion", "fiscal", "financiero", "auditoria"}


def es_global(rol) -> bool:
    return str(rol or "").upper() in _ROLES_GLOBALES


def permite(dominio, rol) -> bool:
    if es_global(rol):
        return True
    return str(dominio or "general").lower() not in DOMINIOS_SENSIBLES


def dominios_permitidos(rol) -> list:
    if es_global(rol):
        return ["*"]
    return ["ventas", "stock", "reposicion", "compras", "actividad", "crm", "general"]
