"""
Internacionalización de los portales web (Empleado/Empresa B2B/Gestión/Proveedor).

Los 4 portales (`portal_empleado_web.py`, `portal_empresa_b2b.py`, `portal_empresa_gestion.py`,
`portal_proveedor.py`) generan HTML con funciones puras + Flask fino, 100% en español hardcodeado
(confirmado por auditoría previa) — a diferencia de la app de escritorio, nunca llamaban a
`src.utils.i18n.tr()`. Este módulo es el PUENTE que les permite reutilizar ESE MISMO motor de
traducción (mismos catálogos JSON de `assets/lang/`, mismo `tr()`) sin duplicar nada, resolviendo
el problema concreto de un backend multi-visitante:

  - La app de escritorio tiene UN idioma "activo" por proceso (un solo usuario). Un portal Flask
    atiende peticiones de MUCHOS visitantes a la vez, cada uno con su propio idioma elegido — no
    pueden compartir ese único idioma activo global.
  - Por eso `i18n.tr()` se extendió con un parámetro `lang=` que resuelve contra un idioma
    EXPLÍCITO sin mutar ningún estado global (ver `i18n._GestorI18n.tr`). Este módulo solo añade
    la resolución POR PETICIÓN (cookie de preferencia) y el selector visual reutilizable.

Elección de mecanismo: una cookie `sm_lang` (preferencia de UI, NO de sesión/autenticación — los
portales siguen sin cookies de sesión, el token sigue viajando en la URL exactamente igual que
antes; esto es una cookie no sensible, de solo lectura de preferencia, totalmente ortogonal a la
seguridad del token). Si no hay cookie, se usa español (comportamiento idéntico al de antes de
este cambio — ningún visitante existente nota ninguna diferencia hasta que elige otro idioma).
"""

from markupsafe import escape

from src.utils.i18n import LANGUAGES, tr as _tr

COOKIE_NAME = "sm_lang"
_DEFAULT = "es"

# Los 21 idiomas soportados (petición explícita: el selector del portal debe mostrarlos TODOS,
# no un subconjunto — mismo catálogo que `LANGUAGES`, una sola fuente de verdad).
IDIOMAS_PORTAL = tuple(LANGUAGES)


def _e(x):
    return str(escape(x if x is not None else ""))


def _req(request):
    """Si no se pasa `request` explícito, usa el proxy de contexto de Flask (`flask.request`,
    thread-local — siempre correcto dentro de una petición) para no tener que enhebrar `request`
    por la firma de cada una de las decenas de funciones `pagina_*` de los 4 portales."""
    if request is not None:
        return request
    from flask import request as _flask_request
    return _flask_request


def idioma_actual(request=None) -> str:
    """Idioma elegido por ESTE visitante (cookie `sm_lang`), validado contra los idiomas
    soportados; 'es' si no hay cookie o el valor no es válido (comportamiento de siempre)."""
    try:
        code = (_req(request).cookies.get(COOKIE_NAME) or "").strip()
    except Exception:
        code = ""
    return code if code in LANGUAGES else _DEFAULT


def t(key, default=None, request=None, **kwargs):
    """`tr()` resuelto contra el idioma de ESTE visitante — mismo catálogo que la app de
    escritorio, sin tocar el idioma activo global del proceso."""
    return _tr(key, default=default, lang=idioma_actual(request), **kwargs)


def registrar_selector_idioma(bp, url_prefix):
    """Registra `POST {url_prefix}/idioma` en el blueprint `bp`: guarda la cookie de idioma y
    redirige de vuelta a la página desde la que se pidió el cambio (Referer), o a `url_prefix` si
    no hay Referer. Cada portal llama a esto UNA vez al construir su blueprint."""
    from flask import make_response, redirect, request

    @bp.post(f"{url_prefix}/idioma")
    def _cambiar_idioma_portal():
        code = (request.form.get("idioma") or "").strip()
        destino = request.form.get("volver") or request.referrer or url_prefix
        resp = make_response(redirect(destino))
        if code in LANGUAGES:
            resp.set_cookie(COOKIE_NAME, code, max_age=60 * 60 * 24 * 365, samesite="Lax")
        return resp


def selector_idioma_html(*, accion: str, request=None) -> str:
    """Desplegable de idioma — un único `<select>` que se auto-envía al elegir una opción (mismo
    patrón ya usado en otros selectores de los portales, p. ej. homologación en
    `portal_empresa_gestion.py`). `accion`: URL de `POST {url_prefix}/idioma` de ESTE portal."""
    req = _req(request)
    actual = idioma_actual(req)
    opciones = "".join(
        f'<option value="{cod}"{" selected" if cod == actual else ""}>'
        f'{_e(LANGUAGES[cod]["flag"])} {_e(LANGUAGES[cod]["native"])}</option>'
        for cod in IDIOMAS_PORTAL if cod in LANGUAGES
    )
    try:
        volver = req.full_path if req.full_path and req.full_path != "?" else req.path
    except Exception:
        volver = ""
    return f"""<form method="post" action="{_e(accion)}" class="sel-idioma">
<input type="hidden" name="volver" value="{_e(volver)}">
<select name="idioma" onchange="this.form.submit()" aria-label="Idioma">{opciones}</select>
</form>"""
