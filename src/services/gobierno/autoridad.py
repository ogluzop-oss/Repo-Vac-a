"""
Matriz de autoridad (Paquete Enterprise 7, SUBFASE 7.7). Separa claramente quien puede aprobar/
rechazar/delegar/modificar/consultar/certificar/firmar/exportar/eliminar segun su rol organico.
La IA respetara SIEMPRE esta matriz. Matriz por defecto en codigo (ampliable); mapea el perfil
del ERP a un rol organico cuando el usuario no tiene rol explicito en el organigrama.
"""

PERMISOS = ("aprobar", "rechazar", "delegar", "modificar", "consultar", "certificar",
            "firmar", "exportar", "eliminar")

# rol_org → permisos concedidos.
_MATRIZ = {
    "administrador": set(PERMISOS),
    "director": {"aprobar", "rechazar", "delegar", "modificar", "consultar", "certificar",
                 "firmar", "exportar"},
    "supervisor": {"aprobar", "rechazar", "delegar", "modificar", "consultar", "exportar"},
    "principal": {"aprobar", "rechazar", "modificar", "consultar", "exportar"},
    "suplente": {"aprobar", "consultar"},
    "auditor": {"consultar", "certificar", "exportar"},
}

# Perfil del ERP → rol organico por defecto.
_PERFIL_A_ORG = {"SUPERADMIN": "administrador", "ADMINISTRADOR": "administrador",
                 "GERENTE": "director", "OPERARIO": "suplente"}


def rol_org_de_perfil(perfil) -> str:
    return _PERFIL_A_ORG.get(str(perfil or "").upper(), "suplente")


def permisos_de(rol_org) -> set:
    return set(_MATRIZ.get(str(rol_org or "").lower(), set()))


def puede(rol_org, permiso) -> bool:
    return str(permiso) in permisos_de(rol_org)


def puede_perfil(perfil, permiso) -> bool:
    return puede(rol_org_de_perfil(perfil), permiso)
