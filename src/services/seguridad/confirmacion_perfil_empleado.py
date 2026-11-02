"""
Confirmación por email (código de 6 dígitos) al generar un perfil nuevo de empleado — "Generar
perfil empleado" (Configuración → Usuarios, `gui/gestion_usuarios.py::ejecutar_creacion_usuario`).

El perfil YA NO se inserta en `usuarios` de forma síncrona: `solicitar(...)` guarda los datos del
alta (nombre/PIN/perfil/centro/email) en la tabla temporal `confirmaciones_perfil_empleado`
(migración 0312) y envía un código de 6 dígitos al email indicado; solo `confirmar(...)`, si el
código coincide y no ha caducado, invoca el `crear_perfil` REAL (`db/usuario.py`) — mismo motor que
ya usaba el alta directa, sin duplicar su lógica de hash/política de PIN/evento `USUARIO_CREADO`.

El PIN se guarda CIFRADO (`utils.cripto.cifrar`, reversible) mientras la confirmación está
pendiente — nunca en claro — y se descarta en cuanto se confirma o caduca. El código en sí se
guarda SOLO hasheado (SHA-256), igual criterio que `mfa_recovery_codes` para sus códigos de
recuperación.

Degradación honesta: si la empresa no tiene ningún buzón de correo corporativo activo
(`correos_corporativos`, ver `db/correo.py`), `solicitar()` devuelve `ok=False` con un motivo
explícito — nunca finge haber enviado un email que no salió, ni crea el perfil sin confirmación.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("seguridad.confirmacion_perfil_empleado")

MINUTOS_VALIDEZ = 10
MAX_INTENTOS = 5


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def _generar_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _buzon_activo(id_empresa):
    try:
        from src.db import correo as correo_db
        buzones = [c for c in correo_db.listar_correos(id_empresa) if c.get("estado") == "activo"]
        return buzones[0] if buzones else None
    except Exception as e:
        logger.debug("_buzon_activo: %s", e)
        return None


def _enviar_codigo(email: str, codigo: str, id_empresa) -> tuple[bool, str]:
    buzon = _buzon_activo(id_empresa)
    if not buzon:
        return False, ("No hay ningún buzón de correo corporativo activo configurado — "
                       "configúralo en Comunicaciones antes de generar perfiles de empleado.")
    try:
        from src.services.correo import servicio as correo_srv
        asunto = "Código de confirmación — nuevo perfil de empleado"
        cuerpo = (f"Se ha solicitado crear tu perfil de empleado en Smart Manager.\n\n"
                 f"Código de confirmación: {codigo}\n\n"
                 f"Facilita este código a la persona que está dando de alta tu perfil. "
                 f"Caduca en {MINUTOS_VALIDEZ} minutos. Si no esperabas este correo, ignóralo.")
        return correo_srv.enviar_documento(buzon.get("id_correo"), email, asunto, cuerpo)
    except Exception as e:
        logger.error("_enviar_codigo: %s", e)
        return False, "No se pudo enviar el email de confirmación."


def solicitar(nombre, password_pin, perfil_tipo="OPERARIO", centro_codigo=None, email=None,
             id_empresa=None, creado_por_id=None) -> dict:
    """Inicia el alta pendiente: guarda los datos + envía el código. Devuelve
    {ok, id_confirmacion, motivo}. No crea el perfil todavía."""
    email = (email or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "motivo": "Email inválido."}
    from src.seguridad import politica
    ok_pol, motivo_pol = politica.validar_pin(password_pin)
    if not ok_pol:
        return {"ok": False, "motivo": motivo_pol or "PIN rechazado por política de seguridad."}
    from src.utils import cripto
    codigo = _generar_codigo()
    ok_envio, motivo_envio = _enviar_codigo(email, codigo, id_empresa)
    if not ok_envio:
        return {"ok": False, "motivo": motivo_envio}
    try:
        ensure_schema()
        expira = datetime.now() + timedelta(minutes=MINUTOS_VALIDEZ)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO confirmaciones_perfil_empleado "
                "(id_empresa, nombre, password_pin_cifrado, perfil_tipo, centro_codigo, email, "
                " codigo_hash, creado_por_id, expira_en) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, nombre.strip().upper(), cripto.cifrar(password_pin), perfil_tipo,
                 centro_codigo, email, _hash_codigo(codigo), creado_por_id, expira))
            id_confirmacion = cur.lastrowid
            conn.commit()
        return {"ok": True, "id_confirmacion": id_confirmacion,
                "motivo": f"Código enviado a {email}."}
    except Exception as e:
        logger.error("solicitar: %s", e)
        return {"ok": False, "motivo": "No se pudo iniciar la confirmación."}


def confirmar(id_confirmacion: int, codigo: str) -> dict:
    """Valida el código introducido; si es correcto, crea el perfil REAL (`db.usuario.crear_perfil`)
    y consume la confirmación. Devuelve {ok, motivo}."""
    codigo = (codigo or "").strip()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT nombre, password_pin_cifrado, perfil_tipo, centro_codigo, email, "
                "codigo_hash, intentos, usado, expira_en "
                "FROM confirmaciones_perfil_empleado WHERE id=%s", (id_confirmacion,))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "motivo": "Confirmación no encontrada."}
            cols = [d[0] for d in cur.description]
            d = fila if isinstance(fila, dict) else dict(zip(cols, fila))
            if int(d.get("usado") or 0):
                return {"ok": False, "motivo": "Este código ya se utilizó."}
            if datetime.now() > d["expira_en"]:
                return {"ok": False, "motivo": "El código ha caducado. Vuelve a iniciar el alta."}
            if int(d.get("intentos") or 0) >= MAX_INTENTOS:
                return {"ok": False, "motivo": "Demasiados intentos fallidos. Vuelve a iniciar el alta."}
            if _hash_codigo(codigo) != d["codigo_hash"]:
                cur.execute("UPDATE confirmaciones_perfil_empleado SET intentos=intentos+1 "
                           "WHERE id=%s", (id_confirmacion,))
                conn.commit()
                restantes = MAX_INTENTOS - int(d.get("intentos") or 0) - 1
                return {"ok": False, "motivo": f"Código incorrecto ({max(restantes, 0)} intentos restantes)."}
            cur.execute("UPDATE confirmaciones_perfil_empleado SET usado=1 WHERE id=%s",
                       (id_confirmacion,))
            conn.commit()
        from src.utils import cripto
        pin = cripto.descifrar(d["password_pin_cifrado"])
        if pin is None:
            return {"ok": False, "motivo": "No se pudo recuperar el PIN de la solicitud. Vuelve a iniciar el alta."}
        from src.db.usuario import crear_perfil
        if crear_perfil(d["nombre"], pin, d["perfil_tipo"], centro_codigo=d.get("centro_codigo"),
                        email=d.get("email")):
            return {"ok": True, "motivo": "Perfil creado correctamente."}
        return {"ok": False, "motivo": "El código era correcto pero no se pudo crear el perfil."}
    except Exception as e:
        logger.error("confirmar: %s", e)
        return {"ok": False, "motivo": "Error al confirmar el código."}


def reenviar(id_confirmacion: int) -> dict:
    """Genera un código nuevo para una confirmación pendiente y lo reenvía (misma expiración
    desde cero, intentos reiniciados)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email, id_empresa, usado FROM confirmaciones_perfil_empleado "
                       "WHERE id=%s", (id_confirmacion,))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "motivo": "Confirmación no encontrada."}
            cols = [d[0] for d in cur.description]
            d = fila if isinstance(fila, dict) else dict(zip(cols, fila))
            if int(d.get("usado") or 0):
                return {"ok": False, "motivo": "Este código ya se utilizó."}
        codigo = _generar_codigo()
        ok_envio, motivo_envio = _enviar_codigo(d["email"], codigo, d.get("id_empresa"))
        if not ok_envio:
            return {"ok": False, "motivo": motivo_envio}
        expira = datetime.now() + timedelta(minutes=MINUTOS_VALIDEZ)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE confirmaciones_perfil_empleado SET codigo_hash=%s, intentos=0, "
                       "expira_en=%s WHERE id=%s", (_hash_codigo(codigo), expira, id_confirmacion))
            conn.commit()
        return {"ok": True, "motivo": f"Código reenviado a {d['email']}."}
    except Exception as e:
        logger.error("reenviar: %s", e)
        return {"ok": False, "motivo": "No se pudo reenviar el código."}
