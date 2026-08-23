"""
Anti-hurto / prevención de pérdidas (loss prevention).

Cuando un artículo SALE por la puerta sin haber sido pagado, la antena EAS/RFID dispara la alarma y —en
ese mismo instante— se envía una notificación PUSH al móvil del guardia de seguridad con la ficha del
artículo (nombre, foto, EAN, precio, hora, tienda), tal y como funciona en grandes superficies.

FUNCIÓN INTERNA: NO tiene interfaz en el escritorio de Smart Manager. El único frontend es la app móvil
del guardia (que recibe el push). Degradable: reutiliza `services.mobile.push` (que delega en el Centro de
Notificaciones/CCP) — sin canal paralelo. Si no hay backend de push activo, el aviso queda registrado en
notificaciones para que la app lo sincronice.

La detección física (antena EAS/portal RFID) llama a `alarma_salida_no_pagada(...)`; este módulo resuelve
el artículo, evita falsas alarmas (si se acaba de pagar) y avisa a los guardias registrados.
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("rfid.antihurto")

# Guardias de seguridad por empresa. Sus apps se registran al iniciar sesión (como los tokens FCM):
# es un registro volátil en memoria, coherente con cómo funcionan los tokens push.
_GUARDIAS = {}   # id_empresa -> set(id_usuario)


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def registrar_guardia(id_usuario, token_push=None, *, plataforma="android", id_empresa=None) -> bool:
    """Da de alta a un guardia (y, si se aporta, su token push) para recibir alarmas anti-hurto en el
    móvil. Lo llama la app del guardia al iniciar sesión."""
    if not id_usuario:
        return False
    _GUARDIAS.setdefault(_emp(id_empresa), set()).add(str(id_usuario))
    if token_push:
        try:
            from src.services.mobile import push
            push.registrar_dispositivo(id_usuario, token_push, plataforma=plataforma)
        except Exception:
            pass
    return True


def baja_guardia(id_usuario, *, id_empresa=None) -> bool:
    _GUARDIAS.get(_emp(id_empresa), set()).discard(str(id_usuario))
    return True


def guardias(id_empresa=None) -> list:
    return sorted(_GUARDIAS.get(_emp(id_empresa), set()))


def _articulo(codigo, id_empresa):
    """(nombre, precio, imagen) del artículo por código/EAN, o (None, None, None)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, precio, imagen FROM articulos WHERE codigo=%s "
                        "AND (%s IS NULL OR id_empresa=%s) LIMIT 1", (codigo, id_empresa, id_empresa))
            r = cur.fetchone()
            if not r:
                return (None, None, None)
            r = r if not isinstance(r, dict) else list(r.values())
            return (r[0], r[1], r[2])
    except Exception:
        return (None, None, None)


def _codigo_desde_epc(epc):
    """codigo_articulo asociado a un EPC RFID (tabla ubicaciones), o None."""
    if not epc:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_articulo FROM ubicaciones WHERE epc=%s "
                        "AND codigo_articulo IS NOT NULL AND codigo_articulo<>'' LIMIT 1", (epc,))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception:
        return None


def _pagado_recientemente(codigo, minutos=10) -> bool:
    """True si el artículo se vendió (pagó) en los últimos `minutos` → probablemente NO es hurto
    (evita falsas alarmas de un cliente que acaba de pagar). Best-effort."""
    try:
        desde = (_dt.datetime.now() - _dt.timedelta(minutes=int(minutos))).strftime("%Y-%m-%d %H:%M:%S")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
                        "WHERE vi.codigo_articulo=%s AND v.fecha>=%s LIMIT 1", (codigo, desde))
            return cur.fetchone() is not None
    except Exception:
        return False


def alarma_salida_no_pagada(*, ean=None, epc=None, id_empresa=None, id_tienda=None,
                            guardias=None, verificar_pago=True) -> dict:
    """Manejador INTERNO de la alarma EAS/RFID: un artículo salió sin pagar. Resuelve su ficha y envía un
    PUSH inmediato al móvil de cada guardia. Sin frontend de escritorio.

    Parámetros: `ean` (código de artículo) o `epc` (etiqueta RFID); `guardias` opcional (ids de usuario;
    por defecto, los guardias registrados de la empresa). Devuelve {ok, motivo, articulo, notificados}.
    """
    emp = _emp(id_empresa)
    codigo = (ean or _codigo_desde_epc(epc))
    if not codigo:
        return {"ok": False, "motivo": "articulo_no_identificado", "notificados": 0}

    # Anti falsa-alarma: si se pagó hace un momento, no se dispara la notificación.
    if verificar_pago and _pagado_recientemente(codigo):
        return {"ok": False, "motivo": "pagado_recientemente", "ean": codigo, "notificados": 0}

    nombre, precio, imagen = _articulo(codigo, emp)
    hora = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "evento": "salida_no_pagada", "ean": codigo, "nombre": nombre or codigo,
        "precio": float(precio or 0), "foto": imagen, "epc": epc,
        "id_tienda": id_tienda, "hora": hora,
    }
    titulo = "🚨 Artículo sin pagar en la salida"
    cuerpo = (f"{nombre or codigo} (EAN {codigo})"
              + (f" · {float(precio):.2f} €" if precio else ""))

    destinatarios = [str(g) for g in (guardias if guardias is not None else _GUARDIAS.get(emp, set()))]
    notificados = 0
    for gid in destinatarios:
        # Push al móvil del guardia (canal principal, degradable).
        try:
            from src.services.mobile import push
            push.enviar(gid, titulo, cuerpo, id_empresa=emp, datos=payload)
            notificados += 1
        except Exception as e:
            logger.debug("push guardia %s: %s", gid, e)
        # Registro persistente en el Centro de Notificaciones (para que la app lo sincronice / historial).
        try:
            from src.services import notificaciones
            notificaciones.emitir("antihurto", titulo, cuerpo, prioridad="alta", modulo="seguridad",
                                  usuarios=[gid], id_empresa=emp)
        except Exception:
            pass

    _audit(emp, codigo, notificados)
    return {"ok": True, "articulo": payload, "notificados": notificados}


def _audit(id_empresa, codigo, notificados):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", "ANTIHURTO_ALARMA", "articulos",
                      f"empresa={id_empresa} ean={codigo} guardias_notificados={notificados}")
    except Exception:
        pass


__all__ = ["registrar_guardia", "baja_guardia", "guardias", "alarma_salida_no_pagada"]
