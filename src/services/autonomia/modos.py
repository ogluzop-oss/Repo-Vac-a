"""
Modo de empresa (Paquete Enterprise 10, SUBFASE 10.13). Configura y consulta el nivel de autonomia
de la empresa: MANUAL / ASISTIDA / SEMIAUTO / AVANZADA. Cada modo limita automaticamente que
acciones puede EJECUTAR el sistema (el resto se propone a un humano). Persistente por empresa.
"""

import logging

from src.services.autonomia import modelo as M

logger = logging.getLogger("autonomia.modos")


def _emp(id_empresa=None):
    # IOC v3 (Bloque VI): adopción — resolución vía IOC (sin depender del shim deprecado fuentes.emp).
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        try:
            from src.services.gemelo import fuentes
            return fuentes.emp(id_empresa)
        except Exception:
            try:
                from src.db.conexion import EMPRESA_DEFAULT_ID
                return id_empresa or EMPRESA_DEFAULT_ID
            except Exception:
                return id_empresa


def obtener(id_empresa=None) -> str:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT modo FROM exec_config WHERE id_empresa=%s", (emp,))
            r = cur.fetchone()
            if r:
                return (r[0] if not isinstance(r, dict) else r["modo"]) or M.MODO_ASISTIDA
    except Exception as e:
        logger.debug("obtener modo: %s", e)
    return M.MODO_ASISTIDA


def establecer(modo, id_empresa=None) -> bool:
    modo = str(modo).upper()
    if modo not in M.MODOS:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO exec_config (id_empresa, modo) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE modo=VALUES(modo)", (emp, modo))
            c.commit()
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("autonomia", "MODO_AUTONOMIA_CAMBIADO", tabla_afectada="exec_config",
                          detalles=f"modo={modo}")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("establecer modo: %s", e)
        return False


def permite_ejecucion(modo, *, critica=False, informativa=False) -> bool:
    """Regla de capacidad por modo (SUBFASE 10.13/10.14):
       MANUAL → nunca ejecuta. ASISTIDA → solo informativas. SEMIAUTO/AVANZADA → reversibles no
       criticas. Las CRITICAS nunca se auto-ejecutan (siempre se proponen)."""
    nivel = M.nivel_modo(modo)
    if critica:
        return False
    if nivel == 0:                       # MANUAL
        return False
    if nivel == 1:                       # ASISTIDA
        return bool(informativa)
    return True                          # SEMIAUTO / AVANZADA (reversibles no criticas)
