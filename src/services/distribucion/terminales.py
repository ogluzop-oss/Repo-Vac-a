"""
Registro de terminales de la organizacion (Fase 2, SUBFASE 2.5/2.10).

REUTILIZA `edge_nodes` (Bloque 7) como registro de terminales (tiendas/central/almacenes):
alta, estado online/offline, reconexion. No duplica infraestructura.
"""

import logging

from src.services.resiliencia import edge_node as _EN

logger = logging.getLogger("distribucion.terminales")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def registrar(id_tienda, *, nombre=None, id_empresa=None) -> dict:
    return _EN.registrar(_emp(id_empresa), int(id_tienda or 0), nombre=nombre)


def listar(id_empresa=None) -> list:
    try:
        return _EN.listar(id_empresa=_emp(id_empresa)) or []
    except Exception as e:
        logger.debug("listar terminales: %s", e)
        return []


def conectadas(id_empresa=None) -> list:
    return [t for t in listar(id_empresa) if (t.get("modo") or "online") == "online"]


def desconectadas(id_empresa=None) -> list:
    return [t for t in listar(id_empresa) if (t.get("modo") or "online") == "offline"]


def entrar_offline(id_tienda, id_empresa=None) -> dict:
    return _EN.entrar_offline(_emp(id_empresa), int(id_tienda or 0))


def reconectar(id_tienda, id_empresa=None) -> dict:
    return _EN.reconectar(_emp(id_empresa), int(id_tienda or 0))


def esta_online(id_tienda, id_empresa=None) -> bool:
    try:
        st = _EN.estado(_emp(id_empresa), int(id_tienda or 0))
        return (st or {}).get("modo", "online") == "online"
    except Exception:
        return True


def central(id_empresa=None) -> dict:
    """Terminal central (id_tienda=0). Si no existe en el registro, se devuelve una sintetica."""
    for t in listar(id_empresa):
        if int(t.get("id_tienda") or 0) == 0:
            return t
    return {"nombre": "central", "id_tienda": 0, "modo": "online"}
