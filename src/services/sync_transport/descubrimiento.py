"""
Descubrimiento automatico de terminales (Fase 4, SUBFASE 4.6). Detecta y da de alta las
terminales de la empresa sin configuracion manual. En entorno local: central + tienda del
contexto. En red real: escaneo LAN/servicio de descubrimiento (mismo contrato). Reutiliza el
registro de terminales (edge_nodes) y el control de versiones.
"""

import logging

from src.services.sync_transport import versiones

logger = logging.getLogger("sync_transport.descubrimiento")


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


def descubrir(id_empresa=None) -> list:
    """Da de alta (idempotente) las terminales detectadas y registra su version. Devuelve la lista."""
    emp = _emp(id_empresa)
    try:
        from src.services.distribucion import terminales
        terminales.registrar(0, nombre="central", id_empresa=emp)   # la central siempre existe
        try:
            from src.db.conexion import tienda_actual_id_int
            t = int(tienda_actual_id_int() or 0)
        except Exception:
            t = 0
        if t:
            terminales.registrar(t, nombre=f"tienda-{t}", id_empresa=emp)
        lista = terminales.listar(emp)
        for term in lista:
            try:
                if versiones.obtener(emp, term.get("id_tienda")) is None:
                    versiones.actualizar(emp, term.get("id_tienda"))
            except Exception:
                pass
        return lista
    except Exception as e:
        logger.error("descubrir: %s", e)
        return []
