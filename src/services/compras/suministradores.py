"""
Identidad del proveedor en la plataforma (Smart Suppliers · Fase A). `suministradores` es el registro
ÚNICO de cada proveedor (login propio del Portal Web), independiente de cualquier empresa compradora —
distinto de `proveedores`, que sigue siendo el registro POR EMPRESA (homologación, condiciones,
incidencias, evaluación no cambian). `proveedores.id_suministrador` es el puente entre ambos.

Login con email + contraseña (`verificar_login`): sustituye al antiguo acceso sin contraseña
(enlace mágico reenviado automáticamente en cada cierre de sesión/pestaña, retirado por completo).
Hashing reutilizado tal cual de `src.seguridad.passwords` (Argon2id) — el mismo motor que ya usan los
usuarios de escritorio vía `src.db.usuario` — sin motor paralelo. La sesión, una vez autenticado, sigue
usando el mismo mecanismo de siempre: token opaco en `suministrador_sesiones` (`crear_sesion`/
`resolver_sesion`, sin cambios), con el token viajando en la URL (sin cookies).
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.suministradores")

ESTADOS_KYB = ("pendiente", "en_revision", "verificado", "rechazado")
# 30 días de sesión: con login real de email+contraseña (ya no un enlace de un solo uso), una
# ventana larga simplemente evita que el proveedor tenga que volver a autenticarse a diario — no
# hay ningún enlace de reentrada que sincronizar con este valor (ese mecanismo se retiró por
# completo, ver `verificar_login`).
MINUTOS_SESION = 60 * 24 * 30


def texto_validez() -> str:
    """Texto legible de la validez de `MINUTOS_SESION`, por si alguna página necesita informar al
    proveedor de cuánto dura su sesión sin imprimir minutos en bruto."""
    dias = MINUTOS_SESION // (60 * 24)
    if dias >= 1:
        return f"{dias} día" if dias == 1 else f"{dias} días"
    horas = MINUTOS_SESION // 60
    if horas >= 1:
        return f"{horas} hora" if horas == 1 else f"{horas} horas"
    return f"{MINUTOS_SESION} minutos"


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
                         email_login: str | None = None, password: str | None = None,
                         confirmar_password: str | None = None) -> dict:
    """Completa el alta de un proveedor invitado: crea (o reutiliza, si el CIF ya existe en la
    plataforma — el mismo proveedor puede servir a varias empresas) la identidad `suministradores`, y
    la vincula al registro `proveedores` de la empresa que invitó. Requiere sector, email de acceso
    (identificador de login, ya obligatorio) y contraseña (obligatorios).

    El enlace de invitación es PERMANENTE y reutilizable (`invitaciones.resolver_token` ya no caduca
    ni se bloquea tras usarse, ver ese módulo) — así que esta función puede recibir el MISMO token una
    segunda vez si el proveedor vuelve a pulsar el enlace de alta después de haberse registrado ya. En
    ese caso NO se crea una segunda fila `suministradores` (duplicaría la identidad): se detecta que
    `proveedores.id_suministrador` de esta invitación ya está fijado y se devuelve
    `error="ya_registrado"` para que el llamante redirija al login en vez de reintentar el alta."""
    from src.services.compras import invitaciones
    inv = invitaciones.resolver_token(token_invitacion)
    if not inv:
        return {"ok": False, "error": "invitacion_invalida"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_suministrador FROM proveedores WHERE id_proveedor=%s",
                       (inv["id_proveedor"],))
            row = cur.fetchone()
            ya_vinculado = (row[0] if not isinstance(row, dict) else row["id_suministrador"]) if row else None
    except Exception as e:
        logger.error("completar_onboarding (comprobación ya_registrado): %s", e)
        ya_vinculado = None
    if ya_vinculado:
        return {"ok": False, "error": "ya_registrado"}
    if not (razon_social or "").strip() or not (cif or "").strip() or not sector_id:
        return {"ok": False, "error": "razon_social_cif_y_sector_son_obligatorios"}
    email_login = (email_login or "").strip().lower()
    if not email_login or "@" not in email_login:
        return {"ok": False, "error": "el_email_de_acceso_es_obligatorio"}
    if not password or password != confirmar_password:
        return {"ok": False, "error": "las_contrasenas_no_coinciden"}
    from src.seguridad import politica
    ok_pol, motivo = politica.validar(password, longitud_minima=8)
    if not ok_pol:
        return {"ok": False, "error": motivo}
    from src.seguridad.passwords import hash_password
    password_hash = hash_password(password)
    cif_n = cif.strip().upper()
    try:
        ensure_schema()
        existente = obtener_por_cif(cif_n)
        with obtener_conexion() as conn, conn.cursor() as cur:
            if existente:
                id_sum = existente["id"]
                # Identidades creadas antes de que existiera el login con contraseña (o que por
                # cualquier motivo aún no tengan una) se completan aquí — nunca se sobreescribe una
                # contraseña ya establecida por una re-invitación posterior de otra empresa.
                if not (existente.get("password") or "").strip():
                    cur.execute("UPDATE suministradores SET password=%s, email_login=%s WHERE id=%s",
                               (password_hash, email_login, id_sum))
            else:
                cur.execute(
                    "INSERT INTO suministradores (razon_social, cif, sector_id, email_login, "
                    "contacto, telefono, estado_kyb, password) VALUES (%s,%s,%s,%s,%s,%s,'pendiente',%s)",
                    (razon_social.strip(), cif_n, sector_id, email_login, contacto, telefono,
                     password_hash))
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


def validar_password_proveedor(password: str, confirmar_password: str) -> dict:
    """Valida contraseña+confirmación SIN tocar la base de datos — extraído de `registrar_publico`
    (petición explícita, 2026-11-22: el paso de verificación de email por código necesita validar
    la contraseña y HASHEARLA antes de guardar nada en la cookie de sesión entre el envío del
    formulario y la confirmación del código, para no guardar la contraseña en claro ni un
    instante). Devuelve {ok} o {ok: False, error}."""
    if not password or password != confirmar_password:
        return {"ok": False, "error": "las_contrasenas_no_coinciden"}
    from src.seguridad import politica
    ok_pol, motivo = politica.validar(password, longitud_minima=8)
    if not ok_pol:
        return {"ok": False, "error": motivo}
    return {"ok": True}


def registrar_publico(*, razon_social: str, cif: str, sector_id: int,
                      contacto: str | None = None, telefono: str | None = None,
                      email_login: str, password: str = "", confirmar_password: str = "",
                      password_hash: str | None = None) -> dict:
    """Alta pública SIN invitación (petición explícita, 2026-11-16): el Portal Proveedor pasa a
    tener registro abierto, COEXISTIENDO con el flujo de invitación por email (`completar_onboarding`),
    que sigue intacto para cuando una empresa concreta invita a un proveedor ya conocido. Esta vía
    crea (o reutiliza, por CIF, igual que `completar_onboarding`) la identidad `suministradores` SIN
    vincularla a ningún `proveedores` de empresa — esa vinculación concreta por empresa se sigue
    haciendo aparte (homologación), cuando una empresa decide trabajar con este proveedor. Mismas
    validaciones y mismo hashing (Argon2id) que el alta por invitación.

    `password_hash` (petición explícita, 2026-11-22): si se pasa, ya viene validado y hasheado por
    el llamador (verificación de email por código — ver `validar_password_proveedor`) y se ignoran
    `password`/`confirmar_password`. Si no, se valida y hashea aquí (retrocompatible)."""
    if not (razon_social or "").strip() or not (cif or "").strip() or not sector_id:
        return {"ok": False, "error": "razon_social_cif_y_sector_son_obligatorios"}
    email_login = (email_login or "").strip().lower()
    if not email_login or "@" not in email_login:
        return {"ok": False, "error": "el_email_de_acceso_es_obligatorio"}
    if password_hash is None:
        r_val = validar_password_proveedor(password, confirmar_password)
        if not r_val.get("ok"):
            return r_val
    cif_n = cif.strip().upper()
    try:
        ensure_schema()
        existente = obtener_por_cif(cif_n)
        if existente and (existente.get("password") or "").strip():
            # Ya hay una identidad de plataforma activa con ese CIF (con contraseña ya fijada,
            # por invitación o por un registro público anterior) — no se duplica ni se pisa.
            return {"ok": False, "error": "cif_ya_registrado"}
        if password_hash is None:
            from src.seguridad.passwords import hash_password
            password_hash = hash_password(password)
        with obtener_conexion() as conn, conn.cursor() as cur:
            if existente:
                cur.execute("UPDATE suministradores SET password=%s, email_login=%s WHERE id=%s",
                           (password_hash, email_login, existente["id"]))
                id_sum = existente["id"]
            else:
                cur.execute(
                    "INSERT INTO suministradores (razon_social, cif, sector_id, email_login, "
                    "contacto, telefono, estado_kyb, password) VALUES (%s,%s,%s,%s,%s,%s,'pendiente',%s)",
                    (razon_social.strip(), cif_n, sector_id, email_login, contacto, telefono,
                     password_hash))
                id_sum = cur.lastrowid
            conn.commit()
        logger.info("Registro público de proveedor: id_suministrador=%s cif=%s", id_sum, cif_n)
        return {"ok": True, "id_suministrador": id_sum}
    except Exception as e:
        logger.error("registrar_publico: %s", e)
        return {"ok": False, "error": "error_interno"}


# ── Onboarding Stripe Connect (requisito previo a activar comisiones reales, 2026-11-16) ────────
# El riel de cobro con comisión (`compras.b2b_escrow` + `tpv.pagos.connect_stripe`) ya estaba
# construido, pero NINGÚN proveedor tenía forma de vincular su cuenta de Stripe — sin esto, activar
# `B2B_PASARELA_PROVEEDOR=stripe_connect` haría fallar el 100% de los pedidos ("Falta la cuenta
# conectada del vendedor"). Usa SIEMPRE Stripe Connect real (nunca la pasarela simulada): generar un
# enlace de onboarding sin credenciales reales no tiene sentido.
def _pasarela_connect(token=None):
    """`token` opcional (sesión del proveedor en curso): si se da, el enlace de onboarding de
    Stripe vuelve a SU panel real al terminar, en vez del placeholder `smartmanager.local` por
    defecto de `connect_stripe.py`."""
    import os
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        return None
    from src.services.tpv.pagos.registry import clase_de
    clase = clase_de("stripe_connect")
    if not clase:
        return None
    config = {"api_key": api_key}
    if token:
        base = os.getenv("PORTAL_PROVEEDOR_URL", "http://localhost:8090/portal/proveedor")
        config["return_url"] = f"{base}/{token}/dashboard"
        config["refresh_url"] = f"{base}/{token}/stripe/conectar"
    return clase(config)


def iniciar_onboarding_stripe(id_suministrador, *, token=None) -> dict:
    """Inicia (o retoma) el onboarding KYB de Stripe Connect: crea la cuenta conectada si no existe
    todavía, o genera un enlace de onboarding nuevo si ya existe (p. ej. el anterior caducó antes de
    completarse). Devuelve {ok, onboarding_url} o {ok: False, error}.

    Un proveedor elige UNA sola pasarela de cobro (petición explícita, 2026-11-22 — PayPal como
    alternativa: el escrow de un pedido tiene que liquidar por una única vía, nunca las dos a la
    vez) — si ya había empezado (o completado) el onboarding de PayPal, se rechaza aquí."""
    sup = obtener(id_suministrador)
    if not sup:
        return {"ok": False, "error": "proveedor_no_encontrado"}
    if sup.get("pasarela_cobro") == "paypal":
        return {"ok": False, "error": "ya_tienes_paypal_como_pasarela_de_cobro"}
    pasarela = _pasarela_connect(token)
    if not pasarela:
        return {"ok": False, "error": "stripe_no_configurado"}
    if sup.get("cuenta_conectada_id"):
        link = pasarela.link_onboarding(sup["cuenta_conectada_id"])
        if not link.get("ok"):
            return {"ok": False, "error": link.get("mensaje", "error_stripe")}
        return {"ok": True, "onboarding_url": link["onboarding_url"]}
    res = pasarela.crear_cuenta_conectada(tipo_parte="proveedor", id_parte=id_suministrador,
                                          email=sup.get("email_login"))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "error_stripe")}
    fijar_cuenta_conectada(id_suministrador, res["account_id"])
    logger.info("Onboarding Stripe Connect iniciado: id_suministrador=%s account=%s",
               id_suministrador, res["account_id"])
    return {"ok": True, "onboarding_url": res["onboarding_url"]}


def _cachear_verificado(id_suministrador, verificado: bool):
    """Guarda `stripe_verificado` (migr. 0342) — caché LOCAL del último `payouts_enabled` conocido,
    consultada por `esta_verificado()` en los puntos calientes (publicar catálogo, tramitar
    pedidos) para no llamar a la API de Stripe en cada uno."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET stripe_verificado=%s WHERE id=%s",
                       (int(bool(verificado)), id_suministrador))
            conn.commit()
    except Exception as e:
        logger.error("_cachear_verificado(%s): %s", id_suministrador, e)


def estado_stripe(id_suministrador) -> dict:
    """Estado REAL (llamada en vivo a Stripe) de la cuenta Connect del proveedor, para mostrar en
    su panel — y de paso refresca la caché local `stripe_verificado` (ver `_cachear_verificado`).
    Degrada siempre a "sin conectar" ante cualquier fallo — nunca una excepción no controlada."""
    sup = obtener(id_suministrador)
    if not sup or not sup.get("cuenta_conectada_id"):
        return {"conectada": False, "verificada": False}
    pasarela = _pasarela_connect()
    if not pasarela:
        return {"conectada": True, "verificada": False, "error": "stripe_no_configurado"}
    try:
        res = pasarela.estado_cuenta(sup["cuenta_conectada_id"])
    except Exception as e:
        logger.error("estado_stripe(%s): %s", id_suministrador, e)
        return {"conectada": True, "verificada": False}
    if not res.get("ok"):
        _cachear_verificado(id_suministrador, False)
        return {"conectada": True, "verificada": False}
    verificada = bool(res.get("payouts_enabled"))
    _cachear_verificado(id_suministrador, verificada)
    return {"conectada": True, "verificada": verificada, "status": res.get("status")}


def aviso_stripe_ya_mostrado(id_suministrador) -> bool:
    """¿Ya se le mostró al proveedor el aviso "Stripe verificado"? (migr. 0353, petición explícita,
    2026-11-22 — ese aviso debe verse UNA sola vez, justo tras completar la verificación, nunca de
    forma permanente en cada visita al panel)."""
    sup = obtener(id_suministrador)
    return bool(sup and sup.get("stripe_verificado_aviso_mostrado"))


def marcar_aviso_stripe_mostrado(id_suministrador):
    """Marca el aviso como ya mostrado — se llama justo después de pintarlo una vez, para que no
    vuelva a aparecer en ninguna visita posterior al panel."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET stripe_verificado_aviso_mostrado=1 WHERE id=%s",
                       (id_suministrador,))
            conn.commit()
    except Exception as e:
        logger.error("marcar_aviso_stripe_mostrado(%s): %s", id_suministrador, e)


def esta_verificado(id_suministrador) -> bool:
    """Lectura RÁPIDA (sin llamar a Stripe/PayPal) de la caché local — para usar en puntos
    calientes: publicar/activar catálogo (`b2b_catalogo.crear_articulo`) y tramitar pedidos
    (`b2b_pedidos.tramitar`). Requisito obligatorio (petición explícita, 2026-11-15): un proveedor
    sin NINGUNA cuenta de cobro verificada no puede publicar catálogo ni recibir pedidos — petición
    explícita 2026-11-22: ahora vale CUALQUIERA de las dos pasarelas (Stripe o PayPal), nunca hace
    falta tener las dos."""
    sup = obtener(id_suministrador)
    return bool(sup and (sup.get("stripe_verificado") or sup.get("paypal_verificado")))


def actualizar_verificacion_por_cuenta(cuenta_conectada_id: str, verificado: bool) -> bool:
    """Llamado por el webhook `account.updated` de Stripe Connect (`backend/app.py`, petición
    explícita, 2026-11-16): mantiene `stripe_verificado` al día SIN depender de que el proveedor
    vuelva a abrir su panel — antes solo se refrescaba al visitar `/dashboard` (incluida la vuelta
    automática tras completar el onboarding, que sigue funcionando igual). Busca por
    `cuenta_conectada_id` (el webhook solo trae el ID de cuenta de Stripe, no nuestro id interno).
    Devuelve False si ninguna fila coincide (cuenta de Stripe no reconocida — no es un error, se
    ignora silenciosamente igual que el resto de webhooks de pago de la app)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET stripe_verificado=%s WHERE cuenta_conectada_id=%s",
                       (int(bool(verificado)), cuenta_conectada_id))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_verificacion_por_cuenta(%s): %s", cuenta_conectada_id, e)
        return False


def fijar_cuenta_conectada(id_suministrador, cuenta_conectada_id: str) -> bool:
    """Guarda el identificador OPACO devuelto por el PSP (Stripe Connect u otro) para poder liberar
    fondos al proveedor. Nunca se recibe ni se persiste aquí un IBAN u otro dato bancario en claro.
    Fija también `pasarela_cobro='stripe'` (petición explícita, 2026-11-22 — PayPal como
    alternativa: un proveedor cobra por UNA sola vía)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET cuenta_conectada_id=%s, pasarela_cobro='stripe' "
                       "WHERE id=%s", (cuenta_conectada_id, id_suministrador))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("fijar_cuenta_conectada(%s): %s", id_suministrador, e)
        return False


# ── PayPal SIN Partner Program NI custodia de Smart Manager (rediseño explícito, 2026-11-27) ───
# El proveedor ya no "conecta" una cuenta vía OAuth/Partner Referrals (eso exigía que PayPal
# aceptara a Smart Manager como partner) NI cobra a través de la cuenta de Smart Manager (el
# modelo "custodia + Payout" del 2026-11-23, que SÍ dependía de que PayPal concediera el permiso
# de Payouts — bloqueado en producción con 403 AUTHORIZATION_ERROR). Ahora el proveedor da SU
# PROPIA app de PayPal (Client ID + Secret de su propio desarrollador — cualquier cuenta Business
# puede crear una gratis e inmediatamente en developer.paypal.com, sin aprobación de PayPal ni de
# Smart Manager): `b2b_escrow.py` crea y captura la Orden con ESAS credenciales, así que el dinero
# nace y vive en la cuenta del proveedor desde el principio — Smart Manager nunca lo toca.
def fijar_paypal_credenciales(id_suministrador, client_id: str, client_secret: str) -> dict:
    """Verificación REAL (nunca se finge un estado verificado): se pide un token OAuth2 a PayPal
    con ESTAS credenciales exactas antes de guardar nada — si PayPal las rechaza, no se marca
    `paypal_verificado`. Cifradas en reposo (Fernet, `utils/cripto.py` — mismo criterio que
    `tpv_datafono_config.api_key`/`api_secret`)."""
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        return {"ok": False, "error": "credenciales_incompletas"}
    sup = obtener(id_suministrador)
    if not sup:
        return {"ok": False, "error": "proveedor_no_encontrado"}
    if sup.get("pasarela_cobro") == "stripe":
        return {"ok": False, "error": "ya_tienes_stripe_como_pasarela_de_cobro"}
    import os
    try:
        import requests
        base = ("https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_MODO", "test") != "live"
               else "https://api-m.paypal.com")
        r = requests.post(f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                          auth=(client_id, client_secret), timeout=20)
        if r.status_code != 200:
            logger.warning("fijar_paypal_credenciales(%s): PayPal %s: %s",
                          id_suministrador, r.status_code, r.text[:200])
            return {"ok": False, "error": "credenciales_rechazadas_por_paypal"}
    except Exception as e:
        logger.error("fijar_paypal_credenciales(%s): %s", id_suministrador, e)
        return {"ok": False, "error": "error_interno"}
    from src.utils import cripto
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE suministradores SET paypal_client_id=%s, paypal_client_secret=%s, "
                "pasarela_cobro='paypal', paypal_verificado=1 WHERE id=%s",
                (cripto.cifrar(client_id), cripto.cifrar(client_secret), id_suministrador))
            conn.commit()
    except Exception as e:
        logger.error("fijar_paypal_credenciales (BD, %s): %s", id_suministrador, e)
        return {"ok": False, "error": "error_interno"}
    return {"ok": True}


def credenciales_paypal_de(id_suministrador) -> dict | None:
    """Credenciales PROPIAS de PayPal del proveedor, descifradas — usadas por `b2b_escrow.py` para
    cobrar directo a su cuenta (nunca a la de Smart Manager). `None` si el proveedor no las tiene
    configuradas."""
    sup = obtener(id_suministrador)
    if not sup or not sup.get("paypal_client_id") or not sup.get("paypal_client_secret"):
        return None
    from src.utils import cripto
    client_id = cripto.descifrar_seguro(sup["paypal_client_id"])
    client_secret = cripto.descifrar_seguro(sup["paypal_client_secret"])
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret}




def aviso_paypal_ya_mostrado(id_suministrador) -> bool:
    sup = obtener(id_suministrador)
    return bool(sup and sup.get("paypal_verificado_aviso_mostrado"))


def marcar_aviso_paypal_mostrado(id_suministrador):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suministradores SET paypal_verificado_aviso_mostrado=1 WHERE id=%s",
                       (id_suministrador,))
            conn.commit()
    except Exception as e:
        logger.error("marcar_aviso_paypal_mostrado(%s): %s", id_suministrador, e)


def pasarela_cobro_de(id_suministrador) -> str | None:
    """'stripe'|'paypal'|None — con cuál de las dos pasarelas cobra este proveedor (nunca las dos a
    la vez). Usado por `b2b_escrow.py` para resolver con qué PSP liquidar cada pedido de este
    proveedor en concreto."""
    sup = obtener(id_suministrador)
    return (sup or {}).get("pasarela_cobro")


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


# ── Login con email + contraseña ──────────────────────────────────────────────
def verificar_login(email_login: str, password: str) -> dict:
    """Verifica credenciales de acceso al Portal Web del proveedor (sustituye por completo al
    antiguo acceso sin contraseña). Nunca distingue en el error si el email no existe o la
    contraseña es incorrecta — misma postura anti-enumeración que ya tenía el flujo anterior. En
    éxito, si `passwords.verificar` señala que el hash conviene regenerarse (migración desde un
    esquema antiguo o parámetros Argon2 desactualizados), lo persiste — mismo patrón que
    `db.usuario._rehash`."""
    email = (email_login or "").strip().lower()
    if not email or not password:
        return {"ok": False, "error": "credenciales_invalidas"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM suministradores WHERE email_login=%s", (email,))
            row = cur.fetchone()
            sup = _fila(cur, row) if row else None
    except Exception as e:
        logger.error("verificar_login: %s", e)
        return {"ok": False, "error": "error_interno"}
    if not sup:
        return {"ok": False, "error": "credenciales_invalidas"}
    from src.seguridad import passwords as _pw
    ok, hash_nuevo = _pw.verificar(password, sup.get("password") or "")
    if not ok:
        return {"ok": False, "error": "credenciales_invalidas"}
    if hash_nuevo:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE suministradores SET password=%s WHERE id=%s",
                           (hash_nuevo, sup["id"]))
                conn.commit()
        except Exception as e:
            logger.debug("verificar_login rehash(id=%s): %s", sup["id"], e)
    return {"ok": True, "id_suministrador": sup["id"]}


def cerrar_sesion(token_sesion: str) -> dict:
    """Cierre EXPLÍCITO de sesión: invalida el token actual (no se puede reutilizar). Solo borra la
    fila de sesión — a diferencia del flujo antiguo, NO dispara ningún envío de email; con login por
    contraseña el proveedor simplemente vuelve a entrar en `/portal/proveedor/acceso` cuando quiera."""
    if not token_sesion:
        return {"ok": False, "error": "sin_token"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_suministrador FROM suministrador_sesiones WHERE token_sesion=%s",
                       (token_sesion,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "sesion_no_encontrada"}
            cur.execute("DELETE FROM suministrador_sesiones WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
    except Exception as e:
        logger.error("cerrar_sesion: %s", e)
        return {"ok": False, "error": "error_interno"}
    return {"ok": True}


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
    tiempo. Pasado ese plazo, el proveedor vuelve a entrar con email+contraseña en
    `/portal/proveedor/acceso` (`verificar_login`) tantas veces como necesite — es el mecanismo
    normal de reentrada, no una excepción."""
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
