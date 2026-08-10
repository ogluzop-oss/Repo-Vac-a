"""
Política de contraseñas (Módulo 20, enriquecimiento de Seguridad). Añade SOLO lo ausente sobre la
seguridad existente (RBAC, MFA, Argon2id, bloqueo por intentos): política empresarial de complejidad
configurable, caducidad periódica e historial de no-reutilización. Reutiliza `src/seguridad/passwords`
para el hashing/verificación; el bloqueo por intentos fallidos ya existe en `db/usuario.py` y NO se
toca. Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import logging
import re

logger = logging.getLogger("seguridad.password_politica")

_DEFECTO = {"longitud_min": 8, "requiere_mayus": 1, "requiere_minus": 1, "requiere_digito": 1,
            "requiere_simbolo": 0, "dias_caducidad": 0, "historial_n": 3, "activo": 1}


def _emp(id_empresa=None):
    # IOC v3 (Bloque VI): adopción — resolución vía IOC (sin depender del shim deprecado fuentes.emp).
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="seguridad_password_politica"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("seguridad", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def obtener_politica(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM seguridad_password_politica WHERE id_empresa<=>%s LIMIT 1", (emp,))
            filas = _filas(cur)
        if filas:
            return filas[0]
    except Exception as e:
        logger.debug("obtener_politica: %s", e)
    return dict(_DEFECTO)


def guardar_politica(id_empresa=None, **campos) -> dict:
    emp = _emp(id_empresa)
    pol = obtener_politica(emp)
    pol.update({k: v for k, v in campos.items() if k in _DEFECTO})
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO seguridad_password_politica (id_empresa, longitud_min, requiere_mayus, "
                        "requiere_minus, requiere_digito, requiere_simbolo, dias_caducidad, historial_n, "
                        "activo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "longitud_min=VALUES(longitud_min), requiere_mayus=VALUES(requiere_mayus), "
                        "requiere_minus=VALUES(requiere_minus), requiere_digito=VALUES(requiere_digito), "
                        "requiere_simbolo=VALUES(requiere_simbolo), dias_caducidad=VALUES(dias_caducidad), "
                        "historial_n=VALUES(historial_n), activo=VALUES(activo), actualizado=NOW()",
                        (emp, int(pol["longitud_min"]), int(pol["requiere_mayus"]),
                         int(pol["requiere_minus"]), int(pol["requiere_digito"]),
                         int(pol["requiere_simbolo"]), int(pol["dias_caducidad"]),
                         int(pol["historial_n"]), int(pol["activo"])))
            c.commit()
        _audit("POLITICA_GUARDADA", str({k: pol[k] for k in ("longitud_min", "dias_caducidad")}))
        return {"ok": True, "politica": pol}
    except Exception as e:
        logger.error("guardar_politica: %s", e)
        return {"ok": False, "motivo": str(e)}


def validar_complejidad(password, *, id_empresa=None) -> dict:
    """Valida la contraseña contra la política. Devuelve {ok, errores:[...]}."""
    pol = obtener_politica(id_empresa)
    errores = []
    if len(password or "") < int(pol["longitud_min"]):
        errores.append(f"mínimo {pol['longitud_min']} caracteres")
    if int(pol["requiere_mayus"]) and not re.search(r"[A-ZÁÉÍÓÚÑ]", password or ""):
        errores.append("requiere mayúscula")
    if int(pol["requiere_minus"]) and not re.search(r"[a-záéíóúñ]", password or ""):
        errores.append("requiere minúscula")
    if int(pol["requiere_digito"]) and not re.search(r"\d", password or ""):
        errores.append("requiere dígito")
    if int(pol["requiere_simbolo"]) and not re.search(r"[^A-Za-z0-9]", password or ""):
        errores.append("requiere símbolo")
    return {"ok": not errores, "errores": errores}


def reutilizada(id_usuario, password, *, id_empresa=None) -> bool:
    """True si la contraseña coincide con alguna de las últimas `historial_n` (no puede reutilizarse)."""
    emp = _emp(id_empresa)
    pol = obtener_politica(emp)
    n = int(pol.get("historial_n") or 0)
    if n <= 0:
        return False
    try:
        from src.seguridad import passwords as _pw
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT hash FROM seguridad_password_historial WHERE id_usuario=%s "
                        "ORDER BY creado DESC LIMIT %s", (id_usuario, n))
            hashes = [r["hash"] for r in _filas(cur)]
        for h in hashes:
            try:
                ok, _ = _pw.verificar(password, h)
                if ok:
                    return True
            except Exception:
                pass
        return False
    except Exception as e:
        logger.error("reutilizada: %s", e)
        return False


def registrar_cambio(id_usuario, password_hash, *, id_empresa=None) -> dict:
    """Registra el nuevo hash en el historial (recortando a `historial_n`) y sella
    `usuarios.password_changed_at`."""
    emp = _emp(id_empresa)
    pol = obtener_politica(emp)
    n = max(1, int(pol.get("historial_n") or 3))
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO seguridad_password_historial (id_empresa, id_usuario, hash) "
                        "VALUES (%s,%s,%s)", (emp, id_usuario, password_hash))
            # recorta el historial a las N últimas
            cur.execute("SELECT id FROM seguridad_password_historial WHERE id_usuario=%s "
                        "ORDER BY creado DESC", (id_usuario,))
            ids = [r["id"] for r in _filas(cur)]
            sobrantes = ids[n:]
            if sobrantes:
                cur.executemany("DELETE FROM seguridad_password_historial WHERE id=%s",
                                [(i,) for i in sobrantes])
            try:
                cur.execute("UPDATE usuarios SET password_changed_at=NOW() WHERE id=%s", (id_usuario,))
            except Exception:
                pass
            c.commit()
        _audit("PASSWORD_CAMBIO", f"usuario{id_usuario}", "seguridad_password_historial")
        return {"ok": True}
    except Exception as e:
        logger.error("registrar_cambio: %s", e)
        return {"ok": False, "motivo": str(e)}


def password_caducado(id_usuario, *, id_empresa=None) -> dict:
    """Indica si la contraseña del usuario ha superado los `dias_caducidad` de la política."""
    emp = _emp(id_empresa)
    pol = obtener_politica(emp)
    dias = int(pol.get("dias_caducidad") or 0)
    if dias <= 0:
        return {"caducado": False, "dias_caducidad": 0}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT password_changed_at FROM usuarios WHERE id=%s", (id_usuario,))
            r = cur.fetchone()
        cambio = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
        if not cambio:
            return {"caducado": True, "motivo": "sin fecha de cambio registrada"}
        if isinstance(cambio, str):
            cambio = _dt.datetime.fromisoformat(cambio)
        limite = cambio + _dt.timedelta(days=dias)
        caducado = _dt.datetime.now() >= limite
        return {"caducado": caducado, "limite": limite.isoformat(), "dias_caducidad": dias}
    except Exception as e:
        logger.error("password_caducado: %s", e)
        return {"caducado": False, "error": str(e)}
