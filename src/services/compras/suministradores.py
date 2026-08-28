"""
Identidad del proveedor en la plataforma (Smart Suppliers · Fase A). `suministradores` es el registro
ÚNICO de cada proveedor (login propio del Portal Web), independiente de cualquier empresa compradora —
distinto de `proveedores`, que sigue siendo el registro POR EMPRESA (homologación, condiciones,
incidencias, evaluación no cambian). `proveedores.id_suministrador` es el puente entre ambos.

Sesión sin contraseña (magic-link): un proveedor externo no debería tener que gestionar una contraseña
más. El acceso es siempre por un token de un solo uso enviado por email (igual que la invitación).
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.suministradores")

ESTADOS_KYB = ("pendiente", "en_revision", "verificado", "rechazado")
MINUTOS_SESION = 60


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def obtener(id_suministrador) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM suministradores WHERE id=%s", (id_suministrador,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener(%s): %s", id_suministrador, e)
        return None


def obtener_por_cif(cif: str) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM suministradores WHERE cif=%s", (cif.strip().upper(),))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener_por_cif: %s", e)
        return None


def completar_onboarding(token_invitacion: str, *, razon_social: str, cif: str, sector_id: int,
                         contacto: str | None = None, telefono: str | None = None,
                         email_login: str | None = None) -> dict:
    """Completa el alta de un proveedor invitado: crea (o reutiliza, si el CIF ya existe en la
    plataforma — el mismo proveedor puede servir a varias empresas) la identidad `suministradores`, y
    la vincula al registro `proveedores` de la empresa que invitó. Requiere sector (obligatorio)."""
    from src.services.compras import invitaciones
    inv = invitaciones.resolver_token(token_invitacion)
    if not inv:
        return {"ok": False, "error": "invitacion_invalida_o_caducada"}
    if not (razon_social or "").strip() or not (cif or "").strip() or not sector_id:
        return {"ok": False, "error": "razon_social_cif_y_sector_son_obligatorios"}
    cif_n = cif.strip().upper()
    email_login = (email_login or inv["email"]).strip().lower()
    try:
        ensure_schema()
        existente = obtener_por_cif(cif_n)
        with obtener_conexion() as conn, conn.cursor() as cur:
            if existente:
                id_sum = existente["id"]
            else:
                cur.execute(
                    "INSERT INTO suministradores (razon_social, cif, sector_id, email_login, "
                    "contacto, telefono, estado_kyb) VALUES (%s,%s,%s,%s,%s,%s,'pendiente')",
                    (razon_social.strip(), cif_n, sector_id, email_login, contacto, telefono))
                id_sum = cur.lastrowid
            conn.commit()
        # Vincula el proveedor de ESTA empresa (creado en la invitación) a la identidad de plataforma.
        from src.db import proveedores as P
        P.actualizar_proveedor(inv["id_proveedor"], id_empresa=inv["id_empresa"],
                               razon_social=razon_social.strip(), cif_nif=cif_n,
                               persona_contacto=contacto, telefono=telefono, estado="activo")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE proveedores SET id_suministrador=%s, sector_id=%s WHERE id_proveedor=%s",
                        (id_sum, sector_id, inv["id_proveedor"]))
            conn.commit()
        invitaciones.marcar_usado(token_invitacion)
        return {"ok": True, "id_suministrador": id_sum}
    except Exception as e:
        logger.error("completar_onboarding: %s", e)
        return {"ok": False, "error": "error_interno"}


def fijar_cuenta_conectada(id_suministrador, cuenta_conectada_id: str) -> bool:
    """Guarda el identificador OPACO devuelto por el PSP (Stripe Connect u otro) para poder liberar
    fondos al proveedor. Nunca se recibe ni se persiste aquí un IBAN u otro dato bancario en claro."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET cuenta_conectada_id=%s WHERE id=%s",
                        (cuenta_conectada_id, id_suministrador))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("fijar_cuenta_conectada(%s): %s", id_suministrador, e)
        return False


def fijar_estado_kyb(id_suministrador, estado: str) -> bool:
    if estado not in ESTADOS_KYB:
        raise ValueError(f"estado_kyb inválido: {estado}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET estado_kyb=%s WHERE id=%s", (estado, id_suministrador))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("fijar_estado_kyb(%s): %s", id_suministrador, e)
        return False


# ── Sesión sin contraseña (magic-link) ────────────────────────────────────────
def solicitar_acceso(email_login: str) -> dict:
    """Envía (best-effort) un enlace de acceso de un solo uso al email de login del proveedor. No
    confirma en la respuesta si el email existe (evita enumeración de proveedores registrados)."""
    email = (email_login or "").strip().lower()
    sup = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM suministradores WHERE email_login=%s", (email,))
            row = cur.fetchone()
            sup = _fila(cur, row) if row else None
    except Exception as e:
        logger.error("solicitar_acceso: %s", e)
    if sup:
        token = crear_sesion(sup["id"])
        _enviar_email_acceso(sup, token)
    return {"ok": True}  # siempre 200: no revela si el email existe


def _id_empresa_relacionada(id_suministrador):
    """Una empresa con la que este proveedor tiene relación — `suministradores` es una identidad
    COMPARTIDA (sin `id_empresa` propio), pero `enviar_comunicacion` necesita una empresa concreta
    para elegir el buzón corporativo desde el que enviar. No existe el concepto de "empresa dueña"
    del proveedor; se toma cualquiera de las que lo invitaron (normalmente solo hay una)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM proveedores WHERE id_suministrador=%s LIMIT 1",
                       (id_suministrador,))
            row = cur.fetchone()
            return (row[0] if not isinstance(row, dict) else row["id_empresa"]) if row else None
    except Exception as e:
        logger.error("_id_empresa_relacionada(%s): %s", id_suministrador, e)
        return None


def _enviar_email_acceso(suministrador, token_sesion):
    try:
        from src.services import ccp
        import os
        base = os.getenv("PORTAL_PROVEEDOR_URL", "http://localhost:8090/portal/proveedor")
        # Bug corregido: no se pasaba `id_empresa`, así que `enviar_comunicacion` resolvía la
        # empresa por defecto del contexto (casi nunca la que tiene un buzón corporativo
        # configurado) y el envío fallaba en silencio con "No hay buzón corporativo activo" —
        # exactamente el mismo síntoma que ya se había diagnosticado y resuelto para las
        # invitaciones (`invitaciones._enviar_email_invitacion`), pero sin aplicar aquí.
        id_empresa = _id_empresa_relacionada(suministrador["id"])
        # Ruta real del panel: /portal/proveedor/<token>/dashboard (bug corregido — antes apuntaba
        # a /sesion/<token>, una ruta que nunca existió en el blueprint).
        r = ccp.enviar_comunicacion(
            id_empresa=id_empresa,
            destinatario=suministrador["email_login"], asunto="Acceso a tu Portal de Proveedor",
            cuerpo=f"Accede a tu portal: {base}/{token_sesion}/dashboard\n\nEste enlace caduca en "
                  f"{MINUTOS_SESION} minutos.",
            contexto="compras.acceso_proveedor")
        if not getattr(r, "ok", True):
            logger.warning("_enviar_email_acceso(%s): no se pudo enviar (%s)",
                           suministrador.get("email_login"), getattr(r, "mensaje", "motivo desconocido"))
    except Exception as e:
        logger.debug("_enviar_email_acceso: %s", e)


# ── Reentrada automática (sin flujo manual) ────────────────────────────────────
def notificar_reentrada(id_suministrador, *, cooldown_segundos=60) -> dict:
    """Envía (best-effort) un enlace de acceso NUEVO al proveedor sin que tenga que pedirlo: lo
    dispara `backend.portal_proveedor` cuando detecta que cierra la pestaña (beacon en `pagehide`)
    o cuando pulsa "Cerrar sesión". Es el ÚNICO flujo de reentrada del portal — el proveedor nunca
    depende de que la empresa lo vuelva a invitar.

    `cooldown_segundos` evita ráfagas de email si el beacon se dispara varias veces seguidas (varias
    pestañas cerrándose casi a la vez). Se mide contra `ultima_notificacion_reentrada` (escrita SOLO
    aquí) y NO contra la fila más reciente de `suministrador_sesiones` — esa tabla también guarda la
    sesión que el proveedor está usando en ese momento (creada al entrar), así que mirarla haría
    creer que "ya se avisó hace poco" nada más entrar y suprimiría el primer aviso real."""
    sup = obtener(id_suministrador)
    if not sup or not sup.get("email_login"):
        return {"ok": False, "error": "sin_suministrador_o_email_login"}
    ultima = sup.get("ultima_notificacion_reentrada")
    if ultima and cooldown_segundos:
        if isinstance(ultima, str):
            ultima = datetime.fromisoformat(ultima[:19])
        if ultima > datetime.now() - timedelta(seconds=cooldown_segundos):
            return {"ok": True, "omitido": "envio_reciente"}
    # `crear_sesion` gestiona su PROPIA conexión (INSERT + commit) — NO se anida dentro de otro
    # `with obtener_conexion()` aquí: dos conexiones abiertas a la vez en el mismo hilo, una de ellas
    # sin cerrar todavía, es justo el patrón que causó que el UPDATE de más abajo se perdiera en
    # silencio bajo el servidor Flask (aunque el INSERT sí llegaba a persistir) — no reproducible en
    # un script suelto, sí bajo el pool de conexiones real del backend.
    token = crear_sesion(id_suministrador)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET ultima_notificacion_reentrada=NOW() WHERE id=%s",
                       (id_suministrador,))
            conn.commit()
    except Exception as e:
        logger.error("notificar_reentrada(%s): %s", id_suministrador, e)
    _enviar_email_acceso(sup, token)
    return {"ok": True}


def cerrar_sesion(token_sesion: str) -> dict:
    """Cierre EXPLÍCITO de sesión: invalida el token actual (no se puede reutilizar) y dispara de
    inmediato el envío del enlace siguiente, para que el proveedor pueda volver a entrar sin
    depender de la empresa."""
    if not token_sesion:
        return {"ok": False, "error": "sin_token"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_suministrador FROM suministrador_sesiones WHERE token_sesion=%s",
                       (token_sesion,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "sesion_no_encontrada"}
            id_sum = row[0] if not isinstance(row, dict) else row["id_suministrador"]
            cur.execute("DELETE FROM suministrador_sesiones WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
    except Exception as e:
        logger.error("cerrar_sesion: %s", e)
        return {"ok": False, "error": "error_interno"}
    return notificar_reentrada(id_sum, cooldown_segundos=0)   # cierre explícito: sin cooldown


def crear_sesion(id_suministrador, minutos: int = MINUTOS_SESION) -> str:
    token = secrets.token_urlsafe(32)
    expira = datetime.now() + timedelta(minutes=minutos)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO suministrador_sesiones (id_suministrador, token_sesion, expira) "
                        "VALUES (%s,%s,%s)", (id_suministrador, token, expira))
            conn.commit()
    except Exception as e:
        logger.error("crear_sesion(%s): %s", id_suministrador, e)
    return token


def resolver_sesion(token_sesion: str) -> dict | None:
    """Valida el token de sesión y devuelve el suministrador. Reutilizable mientras no caduque
    (`MINUTOS_SESION`) — no es de un solo uso: el mismo token viaja en la URL de cada página del
    panel (Panel/Catálogo), así que debe seguir siendo válido en cada clic dentro de esa ventana de
    tiempo. Pasado ese plazo, el proveedor pide un enlace nuevo en `/portal/proveedor/acceso`
    (`solicitar_acceso`) tantas veces como necesite — es el mecanismo normal de reentrada, no una
    excepción."""
    if not token_sesion:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM suministrador_sesiones WHERE token_sesion=%s", (token_sesion,))
            row = cur.fetchone()
            ses = _fila(cur, row) if row else None
        if not ses:
            return None
        expira = ses.get("expira")
        if expira and isinstance(expira, str):
            expira = datetime.fromisoformat(expira[:19])
        if expira and expira < datetime.now():
            return None
        return obtener(ses["id_suministrador"])
    except Exception as e:
        logger.error("resolver_sesion: %s", e)
        return None
