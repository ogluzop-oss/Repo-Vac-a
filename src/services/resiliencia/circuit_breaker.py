"""
B7-F — Circuit breakers para dependencias externas (AEAT/Verifactu/SII/correo/SMS/pasarelas/
webhooks/APIs). Estados closed/open/half_open con max_fallos/ventana/cooldown configurables.
Estado persistente (circuit_breakers) para compartir entre procesos. Integra observabilidad/alertas.
"""

import datetime as _dt
import logging
import time
from src.db.conexion import log_auditoria, obtener_conexion

logger = logging.getLogger("resiliencia.circuit_breaker")
ESTADOS = ("closed", "open", "half_open")
_DEFAULTS = {"max_fallos": 5, "ventana_seg": 60, "cooldown_seg": 30}


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _estado_bd(servicio, id_empresa):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM circuit_breakers WHERE servicio=%s AND (id_empresa<=>%s)",
                        (servicio, id_empresa))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception:
        return None


def _asegurar(servicio, id_empresa, cfg):
    if _estado_bd(servicio, id_empresa) is None:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("INSERT IGNORE INTO circuit_breakers (id_empresa, servicio, max_fallos, ventana_seg, "
                            "cooldown_seg) VALUES (%s,%s,%s,%s,%s)",
                            (id_empresa, servicio, cfg["max_fallos"], cfg["ventana_seg"], cfg["cooldown_seg"]))
                conn.commit()
        except Exception as e:
            logger.debug("_asegurar: %s", e)


def permitido(servicio, *, id_empresa=None) -> bool:
    """¿Se permite la llamada? open -> False salvo que haya pasado el cooldown (pasa a half_open)."""
    cfg = dict(_DEFAULTS)
    _asegurar(servicio, id_empresa, cfg)
    est = _estado_bd(servicio, id_empresa)
    if not est:
        return True
    if est["estado"] == "closed":
        return True
    if est["estado"] == "open":
        abierto = est.get("abierto_desde")
        if abierto:
            if isinstance(abierto, str):
                abierto = _dt.datetime.strptime(abierto[:19], "%Y-%m-%d %H:%M:%S")
            if (_dt.datetime.now() - abierto).total_seconds() >= (est.get("cooldown_seg") or 30):
                _set_estado(servicio, id_empresa, "half_open")
                return True
        return False
    return True   # half_open: permite una prueba


def registrar_exito(servicio, *, id_empresa=None):
    """Exito -> cierra el breaker y resetea fallos."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE circuit_breakers SET estado='closed', fallos=0, abierto_desde=NULL, "
                        "actualizado=NOW() WHERE servicio=%s AND (id_empresa<=>%s)", (servicio, id_empresa))
            conn.commit()
    except Exception as e:
        logger.debug("registrar_exito: %s", e)


def registrar_fallo(servicio, *, id_empresa=None) -> str:
    """Fallo -> incrementa contador; si supera max_fallos abre el breaker. Devuelve el estado resultante."""
    cfg = dict(_DEFAULTS)
    _asegurar(servicio, id_empresa, cfg)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE circuit_breakers SET fallos=fallos+1, ultimo_fallo=NOW(), actualizado=NOW() "
                        "WHERE servicio=%s AND (id_empresa<=>%s)", (servicio, id_empresa))
            conn.commit()
        est = _estado_bd(servicio, id_empresa)
        if est and est["fallos"] >= est["max_fallos"] and est["estado"] != "open":
            _set_estado(servicio, id_empresa, "open", abrir=True)
            log_auditoria("resiliencia", "CIRCUIT_OPEN", "circuit_breakers", f"{servicio} fallos={est['fallos']}")
            _alertar(servicio, id_empresa)
            return "open"
        if est and est["estado"] == "half_open":
            _set_estado(servicio, id_empresa, "open", abrir=True)
            return "open"
        return est["estado"] if est else "closed"
    except Exception as e:
        logger.error("registrar_fallo: %s", e)
        return "closed"


def _set_estado(servicio, id_empresa, estado, *, abrir=False):
    with obtener_conexion() as conn, conn.cursor() as cur:
        if abrir:
            cur.execute("UPDATE circuit_breakers SET estado=%s, abierto_desde=NOW(), actualizado=NOW() "
                        "WHERE servicio=%s AND (id_empresa<=>%s)", (estado, servicio, id_empresa))
        else:
            cur.execute("UPDATE circuit_breakers SET estado=%s, actualizado=NOW() WHERE servicio=%s "
                        "AND (id_empresa<=>%s)", (estado, servicio, id_empresa))
        conn.commit()


def llamar(servicio, funcion, *args, id_empresa=None, fallback=None, **kwargs):
    """Ejecuta `funcion` protegida por el breaker. Si esta open -> fallback (o excepcion controlada).
    Marca exito/fallo automaticamente. fail-fast cuando el circuito esta abierto."""
    if not permitido(servicio, id_empresa=id_empresa):
        log_auditoria("resiliencia", "CIRCUIT_FAILFAST", "circuit_breakers", servicio)
        if fallback is not None:
            return fallback() if callable(fallback) else fallback
        raise RuntimeError(f"circuito abierto: {servicio}")
    try:
        r = funcion(*args, **kwargs)
        registrar_exito(servicio, id_empresa=id_empresa)
        return r
    except Exception as e:
        registrar_fallo(servicio, id_empresa=id_empresa)
        if fallback is not None:
            return fallback() if callable(fallback) else fallback
        raise e


def estado(servicio=None, *, id_empresa=None) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if servicio:
                cur.execute("SELECT * FROM circuit_breakers WHERE servicio=%s", (servicio,))
            else:
                cur.execute("SELECT * FROM circuit_breakers ORDER BY servicio")
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("estado: %s", e)
        return []


def abiertos(*, id_empresa=None) -> list:
    return [b for b in estado(id_empresa=id_empresa) if b["estado"] == "open"]


def resetear(servicio, *, id_empresa=None) -> bool:
    try:
        _set_estado(servicio, id_empresa, "closed")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE circuit_breakers SET fallos=0, abierto_desde=NULL WHERE servicio=%s", (servicio,))
            conn.commit()
        return True
    except Exception:
        return False


def _alertar(servicio, id_empresa):
    try:
        from src.services.observabilidad import alertas_tecnicas
        alertas_tecnicas.emitir("circuit_breaker", f"Circuito ABIERTO: {servicio}", severidad="alta",
                                id_empresa=id_empresa, crear_incidente=True)
    except Exception:
        pass
