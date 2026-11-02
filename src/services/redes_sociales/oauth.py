"""
Conexión de cuentas por OAuth REAL (petición explícita: alta "totalmente fluida, intuitiva y sin
fricciones" — el usuario de la empresa inicia sesión en la plataforma en su navegador y la cuenta
queda vinculada automáticamente, sin pegar ningún token a mano). Flujo estándar "loopback redirect"
para apps nativas (RFC 8252): se abre el navegador del sistema hacia la pantalla de login REAL de
cada plataforma con `redirect_uri` apuntando al backend Flask que Smart Manager YA arranca en local
(`src.main._puerto_backend`, puerto 8090 por defecto) — mismo proceso que ya sirve el resto de la
API, sin levantar un servidor nuevo. El callback (`api/routers/redes_sociales_oauth.py`) intercambia
el código por un token real y llama a `cuentas.conectar(...)`.

El diálogo manual de "pegar un access_token" (`gui/redes_sociales_gui.py::_ConectarCuentaDialog`)
NO se retira: sigue disponible como vía alternativa (útil antes de tener una app OAuth aprobada por
la plataforma, o para credenciales de servicio que no pasan por login de usuario).

Degradación honesta: sin credenciales de aplicación OAuth configuradas (variables de entorno, ver
`_CONFIG`), `disponible(plataforma)` es False y la GUI lo informa claramente en vez de ofrecer un
botón que fallaría a mitad de flujo.

IMPORTANTE (corrección de arquitectura): la URL de autorización se construye en el proceso de
ESCRITORIO, pero el callback HTTP llega al proceso del BACKEND FLASK — son dos procesos SEPARADOS
que NO comparten memoria. Por eso el `state`/`code_verifier` de cada flujo en curso se persiste en
MariaDB (`redes_sociales_oauth_estados`, migr. 0326), que SÍ comparten ambos procesos, en vez de en
un diccionario en memoria (que habría hecho fallar silenciosamente cada conexión)."""

import base64
import hashlib
import logging
import os
import secrets

logger = logging.getLogger("redes_sociales.oauth")

_TTL_ESTADO = 600   # 10 min — un state sin completar en ese plazo se considera caducado


def _puerto_backend() -> int:
    return int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))


def redirect_uri(plataforma) -> str:
    return f"http://127.0.0.1:{_puerto_backend()}/api/v1/oauth/redes-sociales/{plataforma}/callback"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


_CONFIG = {
    "instagram": {
        "authorize_url": "https://www.facebook.com/v20.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v20.0/oauth/access_token",
        "id_env": "META_OAUTH_APP_ID", "secret_env": "META_OAUTH_APP_SECRET",
        "param_id": "client_id",
        "scope": "pages_show_list,pages_messaging,pages_manage_posts,pages_read_engagement,"
                 "read_insights,instagram_basic,instagram_manage_messages,"
                 "instagram_manage_comments,instagram_content_publish",
    },
    "facebook": {
        "authorize_url": "https://www.facebook.com/v20.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v20.0/oauth/access_token",
        "id_env": "META_OAUTH_APP_ID", "secret_env": "META_OAUTH_APP_SECRET",
        "param_id": "client_id",
        "scope": "pages_show_list,pages_messaging,pages_manage_posts,pages_read_engagement,"
                 "read_insights",
    },
    "tiktok": {
        "authorize_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "id_env": "TIKTOK_OAUTH_CLIENT_KEY", "secret_env": "TIKTOK_OAUTH_CLIENT_SECRET",
        "param_id": "client_key",
        "scope": "user.info.basic,video.publish,video.list,biz.comment.manage",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "id_env": "GOOGLE_OAUTH_CLIENT_ID", "secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "param_id": "client_id",
        "scope": "https://www.googleapis.com/auth/youtube.force-ssl",
        "extra": {"access_type": "offline", "prompt": "consent"},
    },
    "x": {
        "authorize_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.x.com/2/oauth2/token",
        "id_env": "X_OAUTH_CLIENT_ID", "secret_env": "X_OAUTH_CLIENT_SECRET",
        "param_id": "client_id",
        "scope": "tweet.read tweet.write users.read dm.read dm.write offline.access",
        "pkce": True,
    },
}


def plataformas_soportadas() -> list:
    return list(_CONFIG)


def disponible(plataforma) -> bool:
    cfg = _CONFIG.get(plataforma)
    if not cfg:
        return False
    from src.services.seguridad import secret_manager as sm
    return bool(sm.obtener_secreto(cfg["id_env"]) and sm.obtener_secreto(cfg["secret_env"]))


def _limpiar_estados_caducados(cur) -> None:
    cur.execute("DELETE FROM redes_sociales_oauth_estados WHERE creado < "
               "DATE_SUB(NOW(), INTERVAL %s SECOND)", (_TTL_ESTADO,))


def _guardar_estado(state, *, plataforma, id_empresa, usuario, code_verifier) -> None:
    from src.db.conexion import transaccion
    with transaccion() as conn, conn.cursor() as cur:
        _limpiar_estados_caducados(cur)
        cur.execute(
            "INSERT INTO redes_sociales_oauth_estados (state, id_empresa, plataforma, "
            "code_verifier, usuario) VALUES (%s,%s,%s,%s,%s)",
            (state, id_empresa, plataforma, code_verifier, usuario))


def _tomar_estado(state) -> dict | None:
    """Lee y consume (de un solo uso) el estado guardado por `_guardar_estado` — funciona entre
    procesos porque ambos comparten la misma MariaDB (ver docstring del módulo)."""
    from src.db.conexion import transaccion
    with transaccion() as conn, conn.cursor() as cur:
        _limpiar_estados_caducados(cur)
        cur.execute("SELECT id_empresa, plataforma, code_verifier, usuario FROM "
                   "redes_sociales_oauth_estados WHERE state=%s", (state,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("DELETE FROM redes_sociales_oauth_estados WHERE state=%s", (state,))
    return {"id_empresa": row[0], "plataforma": row[1], "code_verifier": row[2], "usuario": row[3]}


def construir_url_autorizacion(plataforma, *, id_empresa=None, usuario=None) -> dict:
    """`{"ok": True, "url": "..."}` lista para abrir en el navegador del sistema, o un degradado
    honesto `{"ok": False, "estado": "no_configurado"}` si faltan credenciales de app OAuth."""
    cfg = _CONFIG.get(plataforma)
    if not cfg:
        return {"ok": False, "estado": "plataforma_no_soportada"}
    if not disponible(plataforma):
        return {"ok": False, "estado": "no_configurado",
                "detalle": f"Faltan {cfg['id_env']}/{cfg['secret_env']} (credenciales de la "
                           f"aplicación OAuth registrada en la plataforma)."}
    from src.services.seguridad import secret_manager as sm
    state = secrets.token_urlsafe(24)
    params = {cfg["param_id"]: sm.obtener_secreto(cfg["id_env"]),
             "redirect_uri": redirect_uri(plataforma), "response_type": "code",
             "scope": cfg["scope"], "state": state}
    params.update(cfg.get("extra") or {})
    code_verifier = None
    if cfg.get("pkce"):
        code_verifier = secrets.token_urlsafe(64)[:128]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    try:
        _guardar_estado(state, plataforma=plataforma, id_empresa=_emp(id_empresa), usuario=usuario,
                        code_verifier=code_verifier)
    except Exception as e:
        logger.error("construir_url_autorizacion: no se pudo guardar el estado: %s", e)
        return {"ok": False, "estado": "error_interno"}
    import urllib.parse
    url = cfg["authorize_url"] + "?" + urllib.parse.urlencode(params)
    return {"ok": True, "url": url, "state": state}


def _intercambiar_codigo(plataforma, code, *, code_verifier=None) -> dict:
    cfg = _CONFIG[plataforma]
    from src.services.redes_sociales.transporte import get_transporte
    from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
    from src.services.seguridad import secret_manager as sm
    client_id = sm.obtener_secreto(cfg["id_env"])
    client_secret = sm.obtener_secreto(cfg["secret_env"])
    body = {cfg["param_id"]: client_id, "client_secret": client_secret, "code": code,
           "grant_type": "authorization_code", "redirect_uri": redirect_uri(plataforma)}
    headers = None
    if cfg.get("pkce"):
        body["code_verifier"] = code_verifier
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"}
        del body["client_secret"]
    try:
        data = get_transporte().request("POST", cfg["token_url"], data=body, headers=headers,
                                        plataforma=plataforma)
    except IntegracionError as e:
        return {"ok": False, "estado": "error_intercambio", "detalle": e.to_dict()}
    token = data.get("access_token")
    if not token:
        return {"ok": False, "estado": "error_intercambio", "detalle": data}
    return {"ok": True, "access_token": token, "refresh_token": data.get("refresh_token"),
           "expires_in": data.get("expires_in")}


def _resolver_cuenta(plataforma, access_token) -> dict:
    """Identifica la página/canal/cuenta real a vincular (id_externo + nombre) tras el login —
    cada plataforma expone esta información de forma distinta."""
    from src.services.redes_sociales.transporte import get_transporte
    from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
    try:
        if plataforma in ("instagram", "facebook"):
            data = get_transporte().request(
                "GET", "https://graph.facebook.com/v20.0/me/accounts", token=access_token,
                params={"fields": "id,name,access_token,instagram_business_account"},
                plataforma=plataforma)
            paginas = data.get("data") or []
            if not paginas:
                return {"ok": False, "estado": "sin_paginas_gestionadas"}
            pagina = paginas[0]   # primera página gestionada; varias cuentas se gestionan
                                  # repitiendo el flujo de conexión, no hay límite de cuentas.
            if plataforma == "instagram":
                ig = pagina.get("instagram_business_account")
                if not ig:
                    return {"ok": False, "estado": "pagina_sin_instagram_business_vinculado"}
                return {"ok": True, "id_externo": ig["id"], "nombre": pagina.get("name"),
                       "token_cuenta": pagina.get("access_token") or access_token}
            return {"ok": True, "id_externo": pagina["id"], "nombre": pagina.get("name"),
                   "token_cuenta": pagina.get("access_token") or access_token}
        if plataforma == "tiktok":
            data = get_transporte().request(
                "GET", "https://open.tiktokapis.com/v2/user/info/", token=access_token,
                params={"fields": "open_id,display_name"}, plataforma=plataforma)
            info = (data.get("data") or {}).get("user") or {}
            return {"ok": True, "id_externo": info.get("open_id"),
                   "nombre": info.get("display_name"), "token_cuenta": access_token}
        if plataforma == "youtube":
            data = get_transporte().request(
                "GET", "https://www.googleapis.com/youtube/v3/channels", token=access_token,
                params={"part": "snippet", "mine": "true"}, plataforma=plataforma)
            items = data.get("items") or []
            if not items:
                return {"ok": False, "estado": "sin_canal_youtube"}
            canal = items[0]
            return {"ok": True, "id_externo": canal["id"],
                   "nombre": (canal.get("snippet") or {}).get("title"), "token_cuenta": access_token}
        if plataforma == "x":
            data = get_transporte().request(
                "GET", "https://api.x.com/2/users/me", token=access_token, plataforma=plataforma)
            u = data.get("data") or {}
            return {"ok": True, "id_externo": u.get("id"), "nombre": u.get("username"),
                   "token_cuenta": access_token}
    except IntegracionError as e:
        return {"ok": False, "estado": "error_resolviendo_cuenta", "detalle": e.to_dict()}
    return {"ok": False, "estado": "plataforma_no_soportada"}


def completar_conexion(state, code) -> dict:
    """Punto de entrada del callback HTTP (`api/routers/redes_sociales_oauth.py`): intercambia el
    código por un token real, identifica la cuenta y la deja conectada en
    `redes_sociales_cuentas` — exactamente la misma función que usa el alta manual
    (`cuentas.conectar`), así ambas vías quedan siempre consistentes."""
    entrada = _tomar_estado(state)
    if not entrada:
        return {"ok": False, "estado": "state_invalido_o_caducado"}
    plataforma = entrada["plataforma"]
    r_token = _intercambiar_codigo(plataforma, code, code_verifier=entrada.get("code_verifier"))
    if not r_token.get("ok"):
        return r_token
    r_cuenta = _resolver_cuenta(plataforma, r_token["access_token"])
    if not r_cuenta.get("ok"):
        return r_cuenta
    from src.services.redes_sociales import cuentas as _cuentas
    try:
        r = _cuentas.conectar(
            plataforma, id_externo=r_cuenta["id_externo"], access_token=r_cuenta["token_cuenta"],
            refresh_token=r_token.get("refresh_token"), nombre_cuenta=r_cuenta.get("nombre"),
            conectado_por=entrada.get("usuario"), id_empresa=entrada.get("id_empresa"))
    except _cuentas.CuentaError as e:
        return {"ok": False, "estado": "error_guardando_cuenta", "detalle": str(e)}
    return {"ok": True, "plataforma": plataforma, "nombre": r_cuenta.get("nombre"), "id": r.get("id")}
