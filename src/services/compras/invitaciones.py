"""
Invitación de proveedores por email (Smart Suppliers · Fase A). Sustituye el registro manual de
proveedores: la empresa invita por correo con un token de un solo uso; el proveedor completa su alta
(razón social/CIF/sector/contacto/datos bancarios) en el Portal Web (Fase A, `portal_proveedor`).

Reimplementación adaptada del patrón que existía en `services/compras/portal/invitaciones.py`
(retirado en el desmontaje del 21-ago-2026, `git show 408548b~1:...` para el original): mismo esquema
de token (`secrets.token_urlsafe`) y mismo canal de envío (CCP), pero sobre las tablas nuevas de Fase A
en vez de `portal_invitaciones`.
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.invitaciones")

DIAS_VALIDEZ = 14


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def invitar_proveedor(id_empresa, email: str, *, usuario=None) -> dict:
    """Crea (o reutiliza) el registro `proveedores` en estado 'invitado' + un token de invitación, y
    envía el email vía CCP. Idempotente: reinvitar al mismo email regenera el token en vez de duplicar
    la invitación."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_invalido"}
    try:
        ensure_schema()
        from src.db import proveedores as P
        # Reutiliza el proveedor si ya se invitó antes a este email en esta empresa.
        existentes = P.listar_proveedores(id_empresa=id_empresa, texto=email, limite=1)
        id_proveedor = existentes[0]["id_proveedor"] if existentes else None
        if not id_proveedor:
            id_proveedor = P.crear_proveedor(f"(Invitación pendiente) {email}", email=email,
                                             id_empresa=id_empresa)
            if not id_proveedor:
                return {"ok": False, "error": "no_se_pudo_crear_proveedor"}
            P.actualizar_proveedor(id_proveedor, id_empresa=id_empresa, estado="invitado")

        token = secrets.token_urlsafe(32)
        expira = datetime.now() + timedelta(days=DIAS_VALIDEZ)
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Revoca invitaciones pendientes previas del mismo proveedor antes de crear la nueva
            # (evita que un token viejo siga siendo válido tras reinvitar).
            cur.execute("UPDATE invitaciones_proveedor SET estado='revocado' "
                        "WHERE id_proveedor=%s AND estado='pendiente'", (id_proveedor,))
            cur.execute(
                "INSERT INTO invitaciones_proveedor (id_empresa, id_proveedor, email, token, "
                "estado, expira) VALUES (%s,%s,%s,%s,'pendiente',%s)",
                (id_empresa, id_proveedor, email, token, expira))
            conn.commit()

        _enviar_email_invitacion(id_empresa, email, token, usuario=usuario)
        return {"ok": True, "id_proveedor": id_proveedor, "token": token, "expira": expira.isoformat()}
    except Exception as e:
        logger.error("invitar_proveedor(%s): %s", email, e)
        return {"ok": False, "error": "error_interno"}


def _enviar_email_invitacion(id_empresa, email, token, *, usuario=None):
    """Best-effort: si el canal de email no está configurado, la invitación queda creada igualmente
    (el token es válido) — no bloquea el flujo de negocio. `enviar_comunicacion` no lanza excepción
    cuando falla (p. ej. sin buzón corporativo activo en Correo), solo devuelve `ok=False`: se
    registra en WARNING para que el fallo sea diagnosticable en logs en vez de desaparecer en
    silencio (antes solo se capturaban excepciones, nunca un resultado `ok=False`)."""
    try:
        from src.services import ccp
        import os
        base = os.getenv("PORTAL_PROVEEDOR_URL", "http://localhost:8090/portal/proveedor")
        # Apunta al login (con contexto de la invitación), no directo al alta: el enlace es
        # PERMANENTE y siempre debe llevar al login, tanto la primera vez (donde el login ofrece
        # el enlace a completar el alta) como en visitas posteriores (donde ya solo sirve para
        # entrar con email+contraseña) — ver `resolver_token` y `portal_proveedor.pagina_acceso`.
        enlace = f"{base}/acceso/{token}"
        r = ccp.enviar_comunicacion(
            id_empresa=id_empresa, destinatario=email,
            asunto="Invitación al Portal de Proveedores de Smart Manager",
            cuerpo=(f"Has sido invitado a darte de alta como proveedor.\n\n"
                   f"Accede aquí: {enlace}\n\n"
                   f"Este enlace no caduca: puedes usarlo cuando quieras, tanto para completar tu "
                   f"registro como, más adelante, para iniciar sesión."),
            contexto="compras.invitacion_proveedor", usuario=usuario)
        if not getattr(r, "ok", True):
            logger.warning("_enviar_email_invitacion(%s): no se pudo enviar (%s) — la invitación "
                           "sigue siendo válida, comparte el enlace manualmente.", email,
                           getattr(r, "mensaje", "motivo desconocido"))
    except Exception as e:
        logger.debug("_enviar_email_invitacion(%s): %s", email, e)


def resolver_token(token: str) -> dict | None:
    """Devuelve la invitación si el token existe. El enlace es PERMANENTE y reutilizable: no caduca
    (`expira` deja de comprobarse) y resuelve sin importar el `estado` (pendiente/usado/revocado) —
    `estado`/`usado_en` (ver `marcar_usado`) quedan como registro histórico para el panel de la
    empresa, nunca como motivo de rechazo aquí; el rechazo solo ocurre si el token no existe. None en
    ese caso — nunca distingue el motivo exacto en la respuesta pública (no dar pistas de
    enumeración)."""
    if not token:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM invitaciones_proveedor WHERE token=%s", (token,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("resolver_token: %s", e)
        return None


def marcar_usado(token: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE invitaciones_proveedor SET estado='usado', usado_en=NOW() "
                        "WHERE token=%s AND estado='pendiente'", (token,))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("marcar_usado: %s", e)
        return False


def listar_pendientes(id_empresa) -> list[dict]:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM invitaciones_proveedor WHERE id_empresa=%s AND estado='pendiente' "
                        "ORDER BY creado_en DESC", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_pendientes: %s", e)
        return []
