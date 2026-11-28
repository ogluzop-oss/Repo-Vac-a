"""
Verificación de email por código de 6 dígitos (petición explícita, 2026-11-22). Paso OBLIGATORIO
compartido por los 3 formularios de registro públicos (web oficial `/registro`, Portal Empresa B2B
`/portal/empresa/registro`, Portal Proveedor `/portal/proveedor/registro`): antes de completar el
alta, se envía un código al email introducido y hay que confirmarlo — un solo servicio reutilizado
por los tres, nunca tres implementaciones paralelas (migración 0354, tabla `verificaciones_email`).

Envío por SMTP DIRECTO (mismo patrón que `backend.sitio_oficial._enviar_codigo_por_email` — el
código de instalación): variables `SMTP_HOST`/`SMTP_PORT`/`SMTP_FROM`/`SMTP_USER`/`SMTP_PASSWORD`.
A diferencia de aquel código (que SÍ se muestra en pantalla como respaldo porque no es un secreto
de identidad, solo un dato de aprovisionamiento), este código es la PRUEBA de que el email es
tuyo — si SMTP no está configurado, el alta queda honestamente BLOQUEADA (nunca se muestra el
código en pantalla ni se finge una verificación que no ha ocurrido de verdad).
"""

import logging
import os
import random

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("verificacion_email")

MINUTOS_VALIDEZ = 15
MAX_INTENTOS = 5


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _generar_codigo() -> str:
    return f"{random.randint(0, 999999):06d}"


def smtp_configurado() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _enviar_codigo(email, codigo):
    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.warning("SMTP no configurado: no se puede enviar el código de verificación a %s "
                       "(código generado, pero NO se muestra en pantalla — el alta queda "
                       "bloqueada honestamente hasta que haya un SMTP real configurado).", email)
        return
    try:
        import smtplib
        from email.mime.text import MIMEText

        remitente = os.environ.get("SMTP_FROM", "smart.manager.enterprises@gmail.com")
        msg = MIMEText(
            f"Tu código de verificación de Smart Manager es: {codigo}\n\n"
            f"Introdúcelo en la página donde te lo ha pedido para completar tu registro. "
            f"Caduca en {MINUTOS_VALIDEZ} minutos.\n\n"
            f"Si no has solicitado este código, puedes ignorar este mensaje.\n", "plain", "utf-8")
        msg["Subject"] = "Tu código de verificación de Smart Manager"
        msg["From"] = remitente
        msg["To"] = email

        puerto = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, puerto, timeout=10) as s:
            s.starttls()
            usuario_smtp = os.environ.get("SMTP_USER")
            password_smtp = os.environ.get("SMTP_PASSWORD")
            if usuario_smtp and password_smtp:
                s.login(usuario_smtp, password_smtp)
            s.sendmail(remitente, [email], msg.as_string())
    except Exception as ex:
        logger.warning("No se pudo enviar el código de verificación a %s: %s", email, ex)


def generar_y_enviar(email) -> dict:
    """Genera un código de 6 dígitos, invalida cualquier código previo SIN verificar de ese
    email (evita que queden varios códigos válidos a la vez) y lo envía por correo. Devuelve
    {ok} o {ok: False, error: 'email_invalido'|'smtp_no_configurado'|'error_interno'}.

    `expira` se calcula EN SQL (`NOW() + INTERVAL ... MINUTE`), nunca en Python — hallazgo real
    (2026-11-22): el reloj del proceso de la app y el del servidor de MariaDB pueden no coincidir
    (zona horaria distinta entre host y contenedor de BD, confirmado en este mismo entorno: hasta 1
    hora de diferencia), así que comparar un `datetime.now()` de Python contra una columna rellenada
    por defecto con `CURRENT_TIMESTAMP` de SQL puede dar caducidades/ventanas incorrectas. Todas las
    comparaciones de tiempo de este módulo usan el reloj de SQL para los dos lados a la vez."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_invalido"}
    if not smtp_configurado():
        return {"ok": False, "error": "smtp_no_configurado"}
    codigo = _generar_codigo()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM verificaciones_email WHERE email=%s AND verificado=0", (email,))
            cur.execute(
                "INSERT INTO verificaciones_email (email, codigo, expira) "
                "VALUES (%s,%s, NOW() + INTERVAL %s MINUTE)", (email, codigo, MINUTOS_VALIDEZ))
            conn.commit()
    except Exception as e:
        logger.error("generar_y_enviar(%s): %s", email, e)
        return {"ok": False, "error": "error_interno"}
    _enviar_codigo(email, codigo)
    return {"ok": True}


def verificar(email, codigo) -> dict:
    """Confirma el código introducido contra el último pendiente de ese email. Devuelve {ok} o
    {ok: False, error: 'sin_codigo_pendiente'|'demasiados_intentos'|'codigo_caducado'|
    'codigo_incorrecto'}. Cada intento fallido cuenta (`MAX_INTENTOS`, defensa frente a fuerza
    bruta de un código de solo 6 dígitos). La caducidad se resuelve EN SQL (`expira < NOW()`,
    ambos lados en el reloj de la base de datos — ver `generar_y_enviar`)."""
    email = (email or "").strip().lower()
    codigo = (codigo or "").strip()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, codigo, intentos, (expira < NOW()) AS caducado "
                "FROM verificaciones_email WHERE email=%s AND verificado=0 "
                "ORDER BY id DESC LIMIT 1", (email,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "sin_codigo_pendiente"}
            fila = _fila(cur, row)
            if fila["intentos"] >= MAX_INTENTOS:
                return {"ok": False, "error": "demasiados_intentos"}
            if fila["caducado"]:
                return {"ok": False, "error": "codigo_caducado"}
            if codigo != fila["codigo"]:
                cur.execute("UPDATE verificaciones_email SET intentos=intentos+1 WHERE id=%s",
                           (fila["id"],))
                conn.commit()
                return {"ok": False, "error": "codigo_incorrecto"}
            cur.execute("UPDATE verificaciones_email SET verificado=1 WHERE id=%s", (fila["id"],))
            conn.commit()
            return {"ok": True}
    except Exception as e:
        logger.error("verificar(%s): %s", email, e)
        return {"ok": False, "error": "error_interno"}


def email_verificado_recientemente(email) -> bool:
    """¿Este email completó una verificación hace POCO (misma sesión de registro, dentro de la
    misma ventana de validez que un código)? Se comprueba justo ANTES de completar cualquier alta
    — nunca se confía en que el cliente simplemente afirme "ya lo verifiqué": si no hay una fila
    `verificado=1` reciente, el alta se rechaza. Ventana resuelta EN SQL (ver `generar_y_enviar`)."""
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM verificaciones_email WHERE email=%s AND verificado=1 "
                "AND creado_en > NOW() - INTERVAL %s MINUTE LIMIT 1",
                (email, MINUTOS_VALIDEZ * 2))
            return bool(cur.fetchone())
    except Exception as e:
        logger.error("email_verificado_recientemente(%s): %s", email, e)
        return False
