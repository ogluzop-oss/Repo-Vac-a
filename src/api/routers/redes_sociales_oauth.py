"""
Router /oauth/redes-sociales — callback del flujo OAuth "loopback redirect" (RFC 8252) para
conectar cuentas sociales de forma fluida (petición explícita): el navegador del sistema del
usuario de la empresa vuelve aquí tras el login real en la plataforma, con el servidor Flask que
Smart Manager YA arranca en local (puerto 8090 por defecto). SIN `requiere_auth`: quien llama es el
propio navegador redirigido por la plataforma, no un cliente autenticado de nuestra API — la
seguridad del flujo la da el `state` de un solo uso (`services.redes_sociales.oauth`), no un JWT.
"""

import logging

logger = logging.getLogger("api.redes_sociales_oauth")

_PAGINA = """<!doctype html><html><head><meta charset="utf-8"><title>Smart Manager</title>
<style>body{{font-family:system-ui,sans-serif;background:#0E1117;color:#fff;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
.card{{background:#161B22;border:1px solid #30363D;border-radius:12px;padding:32px 40px;
max-width:420px}}h1{{color:{color};font-size:20px}}p{{color:#8B949E;font-size:14px}}</style>
</head><body><div class="card"><h1>{titulo}</h1><p>{mensaje}</p></div></body></html>"""


def _render(titulo, mensaje, ok=True):
    return _PAGINA.format(color="#00FFC6" if ok else "#F85149", titulo=titulo, mensaje=mensaje)


def registrar(bp):
    @bp.get("/oauth/redes-sociales/<plataforma>/callback")
    def redes_sociales_oauth_callback(plataforma):
        from flask import request
        error = request.args.get("error") or request.args.get("error_description")
        if error:
            return _render("No se pudo conectar", str(error), ok=False), 200
        code = request.args.get("code")
        state = request.args.get("state")
        if not code or not state:
            return _render("Enlace incompleto", "Faltan parámetros en la respuesta de la "
                           "plataforma.", ok=False), 400
        from src.services.redes_sociales import oauth
        r = oauth.completar_conexion(state, code)
        if r.get("ok"):
            return _render(
                "¡Cuenta conectada!",
                f"{r.get('nombre') or 'Tu cuenta'} ya está vinculada a Smart Manager. Puedes "
                "cerrar esta pestaña y volver a la aplicación.", ok=True), 200
        return _render(
            "No se pudo completar la conexión",
            f"Motivo: {r.get('estado') or 'error desconocido'}. Puedes cerrar esta pestaña y "
            "volver a intentarlo desde Smart Manager.", ok=False), 200
