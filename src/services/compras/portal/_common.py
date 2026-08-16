"""Helpers compartidos del Portal de proveedor (resolución de tenant, conexión, auditoría, token).

Reutiliza la resolución de empresa de `identidad_compras`/`gemelo.fuentes` (misma que `proveedores_pro`)
y los helpers de `db.conexion`; no abre una capa de acceso paralela.
"""

import logging
import secrets

logger = logging.getLogger("compras.portal")

# Estados que el PROVEEDOR puede reportar de un pedido.
ESTADOS_PROVEEDOR = ("pendiente", "aceptado", "en_reparto", "no_disponible", "rechazado")


def _emp(id_empresa=None):
    try:
        from src.services.compras.identidad_compras import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        try:
            from src.services.gemelo import fuentes
            return fuentes.emp(id_empresa)
        except Exception:
            return id_empresa


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def _uno(cur):
    fs = _filas(cur)
    return fs[0] if fs else None


def _audit(accion, detalle, tabla="portal_proveedor_cuentas"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _notificar(tipo, titulo, mensaje, *, id_empresa=None, prioridad="normal"):
    try:
        from src.services import notificaciones
        notificaciones.emitir(tipo, titulo, mensaje, prioridad=prioridad, modulo="compras",
                              roles=["ADMINISTRADOR", "GERENTE"], id_empresa=id_empresa)
    except Exception as e:
        logger.debug("notificar %s: %s", tipo, e)


def _token():
    return secrets.token_urlsafe(32)[:64]
