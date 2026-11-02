"""
Autenticación PASSWORDLESS del cliente final del storefront (Generador de Apps Móviles PWA,
Fase 2) — Magic Link (email) + WebAuthn/Passkey (FaceID/huella). Reutiliza estrictamente motores
existentes, cero duplicidad:
  - `src.db.clientes` para el alta/búsqueda del cliente (la MISMA tabla que ya usa el TPV).
  - `src.services.correo.servicio.enviar_documento` + `src.db.correo.listar_correos` para el envío
    del enlace — EXACTO mismo patrón ya probado en `comercio_digital.carrito_abandono.
    enviar_recuperacion` (buzón corporativo activo de la empresa, nunca un SMTP propio nuevo).
  - `src.services.seguridad.mfa_webauthn` para la ceremonia WebAuthn real (py_webauthn) — las
    credenciales de CLIENTE conviven en la MISMA tabla `mfa_webauthn_credenciales` que las de
    empleado, distinguidas por el prefijo `cli:<id>` en `id_usuario` (campo ya libre, sin FK a
    `usuarios`) — nunca una tabla de passkeys de cliente aparte.
  - `src.db.clientes_sesiones` para la sesión ya autenticada (token opaco DB-backed, revocable).

El TOKEN del Magic Link reutiliza la firma HMAC+TTL YA IMPLEMENTADA en `mfa_webauthn._firmar_reto`/
`_verificar_reto` (genérica: firma CUALQUIER payload de bytes con caducidad, no es específica de
WebAuthn pese a vivir en ese módulo) — en vez de reimplementar el mismo HMAC una segunda vez."""

import logging

logger = logging.getLogger("comercio_digital.clientes_auth")

TTL_MAGIC_LINK_SEG = 900  # 15 minutos


def _prefijo_webauthn(id_cliente) -> str:
    return f"cli:{id_cliente}"


def _resolver_base_url(id_empresa) -> str:
    # Mismo resolutor que `carrito_abandono._resolver_base_url` (dominio publicado de Canal Web, o
    # el backend local en desarrollo) — se importa en vez de duplicarlo.
    from src.services.comercio_digital.carrito_abandono import _resolver_base_url as _r
    return _r(id_empresa)


def _buzon_activo(id_empresa):
    from src.db import correo as correo_db
    try:
        activos = [b for b in correo_db.listar_correos(id_empresa) if b.get("estado") == "activo"]
        return activos[0].get("id_correo") if activos else None
    except Exception as e:
        logger.debug("_buzon_activo(%s): %s", id_empresa, e)
        return None


def _cliente_por_email(id_empresa, email):
    """Coincidencia EXACTA (no `LIKE`) por email dentro de la empresa — `clientes.buscar_clientes`
    hace LIKE, aquí se filtra al resultado exacto para no autenticar contra el cliente equivocado
    si hay varios con emails parecidos."""
    from src.db import clientes as cli_db
    email = (email or "").strip().lower()
    if not email:
        return None
    for c in cli_db.buscar_clientes(email, id_empresa=id_empresa, limite=10):
        if (c.get("email") or "").strip().lower() == email:
            return c
    return None


def _cliente_o_crear(id_empresa, email):
    """Autocreación en el primer login (cero fricción: el comprador no rellena un alta aparte) —
    reutiliza `clientes.crear_cliente` tal cual, con el nombre provisional derivado del email."""
    from src.db import clientes as cli_db
    existente = _cliente_por_email(id_empresa, email)
    if existente:
        return existente
    nombre_provisional = (email.split("@", 1)[0] or "Cliente").strip().title()
    nuevo_id = cli_db.crear_cliente(nombre_provisional, email=email, id_empresa=id_empresa,
                                    origen_flujo="app_pwa")
    if not nuevo_id:
        return None
    return cli_db.obtener_cliente(nuevo_id)


# ── Magic Link ─────────────────────────────────────────────────────────────
def solicitar_magic_link(id_empresa, email, *, base_url=None) -> dict:
    """Paso 1 del login passwordless: crea/encuentra al cliente por email y le envía un enlace de
    1 clic (caduca en 15 min, firmado HMAC — no hay estado que limpiar si nunca se usa). Degrada
    honesto: sin buzón corporativo activo, no finge haberlo enviado."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "motivo": "email_invalido"}
    cliente = _cliente_o_crear(id_empresa, email)
    if not cliente:
        return {"ok": False, "motivo": "no_se_pudo_registrar_el_cliente"}
    id_correo = _buzon_activo(id_empresa)
    if not id_correo:
        return {"ok": False, "motivo": "sin_buzon_activo"}

    from src.services.seguridad.mfa_webauthn import _firmar_reto
    payload = f"{id_empresa}|{cliente['id']}".encode()
    token = _firmar_reto(payload, ttl=TTL_MAGIC_LINK_SEG)

    try:
        from src.db.empresa import info_documento
        nombre_empresa = (info_documento(id_empresa) or {}).get("nombre") or "la tienda"
    except Exception:
        nombre_empresa = "la tienda"
    base = (base_url or _resolver_base_url(id_empresa)).rstrip("/")
    enlace = f"{base}/tienda/{id_empresa}/cuenta/entrar/confirmar?t={token}"
    asunto = f"Tu enlace de acceso a {nombre_empresa}"
    cuerpo = (f"Hola {cliente.get('nombre') or ''}:\n\nAccede a tu cuenta de {nombre_empresa} con "
             f"un solo clic (caduca en 15 minutos):\n\n{enlace}\n\n"
             f"Si no has solicitado este enlace, puedes ignorar este correo.\n\nUn saludo,\n{nombre_empresa}")
    try:
        from src.services.correo.servicio import enviar_documento
        ok, msg = enviar_documento(id_correo, email, asunto, cuerpo)
    except Exception as e:
        logger.warning("solicitar_magic_link(%s,%s): %s", id_empresa, email, e)
        return {"ok": False, "motivo": "error_envio"}
    return {"ok": ok, "motivo": None if ok else (msg or "error_envio")}


def confirmar_magic_link(token) -> dict:
    """Paso 2: valida el token firmado, abre una sesión real (DB-backed) y la devuelve. Honesto:
    token inválido/caducado → `ok:False`, nunca abre una sesión a medias."""
    from src.services.seguridad.mfa_webauthn import _verificar_reto
    crudo = _verificar_reto(token)
    if not crudo:
        return {"ok": False, "motivo": "enlace_invalido_o_caducado"}
    try:
        id_empresa, id_cliente_str = crudo.decode().split("|", 1)
        id_cliente = int(id_cliente_str)
    except Exception:
        return {"ok": False, "motivo": "enlace_invalido_o_caducado"}

    from src.db import clientes as cli_db
    cliente = cli_db.obtener_cliente(id_cliente)
    # Aislamiento: el cliente resuelto debe pertenecer a la MISMA empresa del enlace — nunca se
    # confía ciegamente en el id_cliente decodificado sin volver a comprobar el tenant real.
    if not cliente or str(cliente.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "motivo": "enlace_invalido_o_caducado"}

    from src.db import clientes_sesiones as ses_db
    token_sesion = ses_db.crear_sesion(id_empresa, id_cliente)
    if not token_sesion:
        return {"ok": False, "motivo": "error_interno"}
    return {"ok": True, "token_sesion": token_sesion, "id_empresa": id_empresa,
            "id_cliente": id_cliente, "cliente": cliente}


# ── Sesión ───────────────────────────────────────────────────────────────────
def sesion_actual(token_sesion):
    """Cliente autenticado para este token de sesión, o None. Ficha completa (`clientes.
    obtener_cliente`), no solo el id — así el llamante no necesita una segunda consulta."""
    from src.db import clientes_sesiones as ses_db
    sesion = ses_db.resolver_sesion(token_sesion)
    if not sesion:
        return None
    from src.db import clientes as cli_db
    cliente = cli_db.obtener_cliente(sesion["id_cliente"])
    if not cliente or str(cliente.get("id_empresa")) != str(sesion["id_empresa"]):
        return None
    return cliente


def cerrar_sesion(token_sesion) -> bool:
    from src.db import clientes_sesiones as ses_db
    return ses_db.cerrar_sesion(token_sesion)


# ── WebAuthn (passkey) — ceremonia real, delegada en `mfa_webauthn` ───────────
def webauthn_disponible() -> bool:
    from src.services.seguridad.mfa_webauthn import disponible
    return disponible()


def webauthn_iniciar_registro(id_empresa, id_cliente) -> dict:
    """El cliente YA debe estar autenticado (Magic Link) para dar de alta una passkey — WebAuthn
    aquí es un factor ADICIONAL de acceso rápido, no el primer alta (necesita verificar el email
    al menos una vez, igual que un empleado activa TOTP/passkey tras loguearse con contraseña)."""
    from src.db import clientes as cli_db
    cliente = cli_db.obtener_cliente(id_cliente)
    if not cliente or str(cliente.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "motivo": "cliente_no_encontrado"}
    from src.services.seguridad.mfa_webauthn import iniciar_registro
    usuario = {"id": _prefijo_webauthn(id_cliente), "nombre": cliente.get("nombre") or "Cliente",
              "id_empresa": id_empresa}
    return iniciar_registro(usuario)


def webauthn_confirmar_registro(id_empresa, id_cliente, reto, respuesta) -> dict:
    from src.services.seguridad.mfa_webauthn import confirmar_registro
    usuario = {"id": _prefijo_webauthn(id_cliente), "id_empresa": id_empresa}
    return confirmar_registro(usuario, reto, respuesta,
                              nombre=f"Passkey de {usuario['id']}")


def webauthn_iniciar_login(id_empresa, email) -> dict:
    cliente = _cliente_por_email(id_empresa, email)
    if not cliente:
        return {"ok": False, "motivo": "cliente_no_encontrado"}
    from src.services.seguridad.mfa_webauthn import iniciar_login
    usuario = {"id": _prefijo_webauthn(cliente["id"]), "id_empresa": id_empresa}
    return iniciar_login(usuario)


def webauthn_confirmar_login(id_empresa, email, reto, respuesta) -> dict:
    cliente = _cliente_por_email(id_empresa, email)
    if not cliente:
        return {"ok": False, "motivo": "cliente_no_encontrado"}
    from src.services.seguridad.mfa_webauthn import confirmar_login
    usuario = {"id": _prefijo_webauthn(cliente["id"]), "id_empresa": id_empresa}
    r = confirmar_login(usuario, reto, respuesta)
    if not r.get("ok"):
        return r
    from src.db import clientes_sesiones as ses_db
    token_sesion = ses_db.crear_sesion(id_empresa, cliente["id"])
    if not token_sesion:
        return {"ok": False, "motivo": "error_interno"}
    return {"ok": True, "token_sesion": token_sesion, "id_empresa": id_empresa,
            "id_cliente": cliente["id"], "cliente": cliente}
