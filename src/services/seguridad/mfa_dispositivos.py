"""
Dispositivos de confianza MFA (Gobernanza MFA · Fase 4). Capa de confianza sobre la identidad de
terminal existente (`ioc_terminales` / `terminal_rol.codigo_terminal`). Reutiliza el motor MFA y la
auditoría; NO crea un sistema de dispositivos paralelo. Ver migración 0161.

Invariantes de seguridad:
  · La confianza es por (usuario + empresa + terminal); NUNCA un bypass universal.
  · Un dispositivo de confianza solo evita RE-pedir el 2º factor en el LOGIN de ESE terminal; no
    elimina el step-up de acciones críticas (Fase 7) ni permite cambiar roles / desactivar MFA.
  · Es revocable y caduca (`confianza_hasta`). El factor sigue siendo del usuario.
"""

import datetime as _dt
import logging

logger = logging.getLogger("seguridad.mfa_dispositivos")

CONFIANZA_DIAS = 30


def _emp(id_empresa=None):
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        return id_empresa


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def registrar_confianza(id_usuario, codigo_terminal, id_empresa=None, *, dias=CONFIANZA_DIAS,
                        nombre=None, actor=None) -> dict:
    """Marca (usuario, empresa, terminal) como de confianza durante `dias`. Se llama tras superar el 2º
    factor en el login de ese terminal. Emite TRUSTED_DEVICE_ADDED."""
    if not id_usuario or not codigo_terminal:
        return {"ok": False, "error": "faltan_datos"}
    emp = _emp(id_empresa)
    hasta = _dt.datetime.now() + _dt.timedelta(days=int(dias))
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO mfa_dispositivos_confianza "
                "(id_usuario, id_empresa, codigo_terminal, nombre, confianza_hasta, revocado) "
                "VALUES (%s,%s,%s,%s,%s,0) ON DUPLICATE KEY UPDATE "
                "confianza_hasta=VALUES(confianza_hasta), revocado=0, "
                "nombre=COALESCE(VALUES(nombre), nombre), ultima_confianza=NOW()",
                (str(id_usuario), emp, codigo_terminal, nombre, hasta))
            c.commit()
        _evento("TRUSTED_DEVICE_ADDED", id_usuario, emp, codigo_terminal, actor)
        return {"ok": True, "confianza_hasta": hasta.isoformat()}
    except Exception as e:
        logger.error("registrar_confianza: %s", e)
        return {"ok": False, "error": str(e)}


def es_de_confianza(id_usuario, codigo_terminal, id_empresa=None) -> bool:
    """True si el terminal es de confianza para el usuario en esa empresa (no revocado, no caducado)."""
    if not id_usuario or not codigo_terminal:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT confianza_hasta FROM mfa_dispositivos_confianza "
                "WHERE id_usuario=%s AND id_empresa<=>%s AND codigo_terminal=%s AND revocado=0 LIMIT 1",
                (str(id_usuario), emp, codigo_terminal))
            r = cur.fetchone()
        if not r:
            return False
        hasta = r[0] if not isinstance(r, dict) else r.get("confianza_hasta")
        if hasta is None:
            return True
        if isinstance(hasta, str):
            hasta = _dt.datetime.fromisoformat(hasta)
        return _dt.datetime.now() < hasta
    except Exception as e:
        logger.debug("es_de_confianza: %s", e)
        return False


def listar(id_usuario=None, id_empresa=None) -> list:
    """Dispositivos de confianza (no revocados) de un usuario o de una empresa."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if id_usuario is not None:
                cur.execute("SELECT * FROM mfa_dispositivos_confianza WHERE id_usuario=%s AND "
                            "revocado=0 ORDER BY ultima_confianza DESC", (str(id_usuario),))
            else:
                cur.execute("SELECT * FROM mfa_dispositivos_confianza WHERE id_empresa<=>%s AND "
                            "revocado=0 ORDER BY ultima_confianza DESC", (emp,))
            return _filas(cur)
    except Exception as e:
        logger.debug("listar dispositivos: %s", e)
        return []


def revocar(id_dispositivo, *, actor=None) -> dict:
    """Revoca (marca revocado=1) un dispositivo de confianza. Emite TRUSTED_DEVICE_REVOKED."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_usuario, id_empresa, codigo_terminal FROM "
                        "mfa_dispositivos_confianza WHERE id=%s", (id_dispositivo,))
            r = cur.fetchone()
            cur.execute("UPDATE mfa_dispositivos_confianza SET revocado=1 WHERE id=%s", (id_dispositivo,))
            c.commit()
        if r:
            d = r if isinstance(r, dict) else {"id_usuario": r[0], "id_empresa": r[1], "codigo_terminal": r[2]}
            _evento("TRUSTED_DEVICE_REVOKED", d.get("id_usuario"), d.get("id_empresa"),
                    d.get("codigo_terminal"), actor)
        return {"ok": True}
    except Exception as e:
        logger.error("revocar dispositivo: %s", e)
        return {"ok": False, "error": str(e)}


def _evento(tipo, id_usuario, id_empresa, codigo_terminal, actor):
    try:
        from src.services.seguridad import mfa_eventos
        mfa_eventos.emitir(tipo, id_usuario=id_usuario, id_empresa=id_empresa, actor=actor,
                           detalle=f"terminal={codigo_terminal}")
    except Exception:
        pass
