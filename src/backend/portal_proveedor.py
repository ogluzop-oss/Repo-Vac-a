"""
Portal Web del Proveedor (Smart Suppliers · Fase A) — servido por el backend, mismo patrón que
`storefront.py`: el HTML se genera con funciones puras (sin Flask) → testeables sin servidor; Flask
solo enruta (import perezoso en `crear_blueprint`).

Identidad de sesión: en vez de cookies/Flask-session, el token de acceso viaja en la URL (igual que
`id_empresa` en `/tienda/<id_empresa>/...`) y se revalida en cada petición contra
`suministradores.resolver_sesion` — sin estado nuevo en la app Flask compartida (sin `secret_key`
adicional que gestionar). El token expira solo (`MINUTOS_SESION` en `suministradores.py`).
"""

import logging

from markupsafe import escape

from src.backend.portal_empresa_b2b import _CSEL_CSS, _CSEL_JS

logger = logging.getLogger("backend.portal_proveedor")

_ETIQUETA_UNIDAD = {"kg": "Kilos", "unidad": "Unidades", "pale": "Palés", "caja": "Cajas"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _nav_html(token, activo):
    """Nav del panel (Panel/Catálogo/Cerrar sesión), construida sin estado global — cada página pasa
    su propio `token` de sesión y cuál de los enlaces está activo."""
    base = f"/portal/proveedor/{token}"
    enlaces = (("dashboard", f"{base}/dashboard", "Panel"), ("catalogo", f"{base}/catalogo", "Catálogo"))
    links = "".join(f'<a href="{href}"{" class=\"on\"" if activo == key else ""}>{label}</a>'
                    for key, href, label in enlaces)
    logout = (f'<form method="post" action="{base}/logout" style="margin-left:auto">'
             f'<button type="submit" class="nav-logout">Cerrar sesión</button></form>')
    return links + logout


_FLECHA_SVG = ("data:image/svg+xml;utf8,"
              "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E"
              "%3Cpath d='M1 1l5 5 5-5' stroke='%2300FFC6' stroke-width='2' fill='none' "
              "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")


def _layout(titulo, contenido, nav="", *, token=None):
    """`token`: si se pasa (páginas con sesión activa: panel/catálogo), inyecta el script que avisa
    al servidor cuando el proveedor cierra la pestaña (`pagehide`, vía `sendBeacon`) para que le
    llegue un enlace de acceso nuevo sin tener que pedirlo — único flujo de reentrada del portal (ver
    `suministradores.notificar_reentrada`). El aviso se SUPRIME si el cierre de página viene de un
    clic interno (navegar entre Panel/Catálogo, enviar un formulario): solo se dispara ante un cierre
    real de la pestaña/navegador, no en cada clic dentro del propio portal."""
    script = f"<script>{_CSEL_JS}</script>"
    if token:
        script += f"""<script>(function(){{
var interno=false;
document.addEventListener('click',function(){{interno=true;}},true);
document.addEventListener('submit',function(){{interno=true;}},true);
window.addEventListener('pagehide',function(){{
  if(!interno){{navigator.sendBeacon('/portal/proveedor/{_e(token)}/cerrar');}}
}});
}})();</script>"""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Portal de Proveedores</title><style>
:root{{--ac:#00FFC6;}}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:#0D1117;color:#E6EDF3}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;align-items:center;gap:8px;padding:12px 24px;background:#0D1117;
border-bottom:1px solid #21262D}}
nav a{{color:#8B949E;text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;
border-radius:8px}}nav a.on,nav a:hover{{color:#0D1117;background:var(--ac)}}
nav .nav-logout{{background:transparent;color:#F85149;border:2px solid #F85149;border-radius:8px;
font-weight:700;font-size:13px;padding:6px 10px;cursor:pointer;margin-top:0;
font-family:'Segoe UI',system-ui,sans-serif}}
nav .nav-logout:hover{{background:#F85149;color:#0D1117}}
main{{max-width:900px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:#161B22;border:1px solid #30363D;border-radius:12px;padding:18px;margin-bottom:16px}}
label{{display:block;font-size:14px;color:#8B949E;margin:10px 0 4px;font-weight:700}}
input,select,textarea{{width:100%;padding:10px 12px;border-radius:8px;border:1px solid #30363D;
background:#0D1117;color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;
font-weight:700}}
select{{appearance:none;-webkit-appearance:none;border:2px solid var(--ac);border-radius:10px;
background-color:#0D1117;background-image:url("{_FLECHA_SVG}");background-repeat:no-repeat;
background-position:right 14px center;background-size:12px 8px;padding-right:36px;cursor:pointer}}
select:focus{{outline:none;border-color:var(--ac)}}
input[type=file]{{border:none;background:transparent;padding:0;width:auto;margin-right:14px;
vertical-align:middle}}
input[type=file]::file-selector-button{{background:transparent;color:var(--ac);
border:2px solid var(--ac);border-radius:8px;padding:9px 16px;font-weight:900;
font-family:'Segoe UI',system-ui,sans-serif;cursor:pointer;margin-right:10px}}
input[type=file]::file-selector-button:hover{{background:var(--ac);color:#0D1117}}
button{{margin-top:14px;padding:9px 16px;border-radius:8px;border:2px solid var(--ac);
background:transparent;color:var(--ac);font-weight:900;cursor:pointer;vertical-align:middle;
font-family:'Segoe UI',system-ui,sans-serif}}
button:hover{{background:var(--ac);color:#0D1117}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px}}
th{{color:#8B949E}}
.badge{{display:inline-block;background:#21262D;color:var(--ac);border-radius:6px;padding:2px 8px;
font-size:11px;font-weight:700}}
.error{{color:#F85149;font-weight:700}}.ok{{color:#3FB950;font-weight:700}}
a.enlace{{color:var(--ac);font-weight:700;text-decoration:none}}
{_CSEL_CSS}
</style></head><body>
<header><span class="logo">📦 Portal de Proveedores</span></header>
<nav>{nav}</nav>
<main>{contenido}</main>
{script}
</body></html>"""


def _pagina_error(titulo, mensaje):
    return _layout(titulo, f"""<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p>
<p>Cada vez que cierras tu portal (o pulsas "Cerrar sesión"), te enviamos automáticamente un enlace
de acceso nuevo a tu email — revisa tu bandeja de entrada.</p></div>""")


# ── Onboarding (desde el enlace de invitación) ───────────────────────────────
def pagina_onboarding(token, *, sectores, error=None):
    opciones = "".join(f'<option value="{s["id"]}">{_e(s["nombre"])}</option>' for s in sectores)
    aviso = f'<p class="error">{_e(error)}</p>' if error else ""
    return _layout("Alta de proveedor", f"""
<div class="card">
<h1>Completa tu alta como proveedor</h1>
<p>Rellena estos datos para acceder al catálogo B2B. El sector es obligatorio: determina qué empresas
podrán ver tus ofertas.</p>
{aviso}
<form method="post" action="/portal/proveedor/onboarding/{_e(token)}">
<label>Razón social *</label><input name="razon_social" required>
<label>CIF *</label><input name="cif" required>
<label>Sector comercial *</label><select name="sector_id" required>
<option value="">Selecciona un sector…</option>{opciones}</select>
<label>Persona de contacto</label><input name="contacto">
<label>Teléfono</label><input name="telefono">
<label>Email de acceso (para futuros inicios de sesión)</label><input name="email_login" type="email">
<button type="submit">Completar alta</button>
</form>
</div>""")


def pagina_onboarding_completado(url_dashboard):
    return _layout("Alta completada", f"""
<div class="card"><h1 class="ok">✓ Alta completada</h1>
<p>Ya puedes acceder a tu panel de proveedor.</p>
<p><a class="enlace" href="{_e(url_dashboard)}">Entrar al panel →</a></p>
<p>No hace falta que guardes este enlace: cada vez que cierres tu portal (o pulses "Cerrar
sesión"), te enviaremos automáticamente uno nuevo a tu email.</p>
</div>""")


# ── Acceso (magic-link) ───────────────────────────────────────────────────────
def pagina_acceso(*, enviado=False):
    if enviado:
        cuerpo = ("<h1>Revisa tu correo</h1><p>Si el email está registrado, te hemos enviado un "
                 "enlace de acceso válido durante 60 minutos.</p>")
    else:
        cuerpo = """<h1>Acceder a tu panel</h1>
<form method="post" action="/portal/proveedor/acceso">
<label>Email de acceso</label><input name="email" type="email" required>
<button type="submit">Enviarme un enlace de acceso</button>
</form>"""
    return _layout("Acceso proveedor", f'<div class="card">{cuerpo}</div>')


def pagina_sesion_cerrada():
    return _layout("Sesión cerrada", """
<div class="card"><h1 class="ok">✓ Sesión cerrada</h1>
<p>Te hemos enviado un enlace de acceso nuevo a tu email. Úsalo la próxima vez que quieras entrar a
tu portal — no hace falta que la empresa te vuelva a invitar.</p>
</div>""")


# ── Panel del proveedor ───────────────────────────────────────────────────────
def pagina_dashboard(token, suministrador):
    estado = suministrador.get("estado_kyb", "pendiente")
    return _layout("Panel", f"""
<div class="card">
<h1>{_e(suministrador.get('razon_social'))}</h1>
<p>CIF: {_e(suministrador.get('cif'))} · Estado de verificación:
<span class="badge">{_e(estado)}</span></p>
<p>Contacto: {_e(suministrador.get('contacto') or '—')} · Tel: {_e(suministrador.get('telefono') or '—')}</p>
</div>""", nav=_nav_html(token, "dashboard"), token=token)


def pagina_catalogo(token, articulos, *, mensaje=None, resultado_import=None):
    filas = "".join(f"""<tr><td>{_e(a['codigo'])}</td><td>{_e(a['nombre'])}</td>
<td>{_ETIQUETA_UNIDAD.get(a['unidad_medida'], a['unidad_medida'])}</td>
<td>{a['moq']}</td><td>{a['precio_unitario']} €</td></tr>""" for a in articulos)
    tabla = (f"<table><tr><th>Código</th><th>Nombre</th><th>Unidad</th><th>MOQ</th>"
            f"<th>Precio</th></tr>{filas}</table>") if articulos else "<p>Aún no has publicado artículos.</p>"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    resumen_import = ""
    if resultado_import:
        errs = "".join(f"<li>Fila {e['fila']} ({_e(e['codigo'])}): {_e(e['error'])}</li>"
                       for e in resultado_import.get("errores", []))
        resumen_import = f"""<p class="ok">Importadas {resultado_import['filas_ok']} filas.</p>
{f'<p class="error">{resultado_import["filas_error"]} filas con error:</p><ul>{errs}</ul>' if errs else ''}"""
    opciones_unidad = "".join(f'<option value="{k}">{v}</option>' for k, v in _ETIQUETA_UNIDAD.items())
    base = f"/portal/proveedor/{token}"
    return _layout("Catálogo", f"""
<div class="card"><h1>Tu catálogo B2B</h1>{aviso}{tabla}</div>
<div class="card"><h2>Añadir artículo</h2>
<form method="post" action="{base}/catalogo/nuevo">
<label>Código *</label><input name="codigo" required>
<label>Nombre *</label><input name="nombre" required>
<label>Unidad de Medida Mayorista *</label><select name="unidad_medida" required>{opciones_unidad}</select>
<label>Cantidad Mínima de Pedido (MOQ) *</label><input name="moq" type="number" min="1" value="1" required>
<label>Precio unitario (€) *</label><input name="precio_unitario" type="number" step="0.01" min="0" required>
<label>Descripción</label><textarea name="descripcion" rows="2"></textarea>
<button type="submit">Publicar artículo</button>
</form></div>
<div class="card"><h2>Subir catálogo (CSV/Excel)</h2>
<p>Columnas esperadas: <code>codigo, nombre, unidad_medida, moq, precio_unitario, descripcion</code>
(unidad_medida: kg/unidad/pale/caja).</p>
{resumen_import}
<form method="post" action="{base}/catalogo/importar" enctype="multipart/form-data">
<input type="file" name="archivo" accept=".csv,.xlsx,.xls" required>
<button type="submit">Importar</button>
</form></div>""", nav=_nav_html(token, "catalogo"), token=token)


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_proveedor", __name__, url_prefix="/portal/proveedor")

    def _suministrador_o_error(token):
        from src.services.compras import suministradores as S
        sup = S.resolver_sesion(token)
        if not sup:
            return None, (_pagina_error("Sesión no válida",
                          "Tu enlace de acceso ha caducado o no es válido."), 401)
        return sup, None

    @bp.get("/onboarding/<token>")
    def onboarding(token):
        from src.services.compras import invitaciones, sectores
        if not invitaciones.resolver_token(token):
            return _pagina_error("Invitación no válida",
                                 "Este enlace de invitación ha caducado o ya se usó."), 404
        return pagina_onboarding(token, sectores=sectores.listar())

    @bp.post("/onboarding/<token>")
    def onboarding_post(token):
        from src.services.compras import sectores, suministradores as S
        d = request.form
        r = S.completar_onboarding(
            token, razon_social=d.get("razon_social", ""), cif=d.get("cif", ""),
            sector_id=d.get("sector_id") or None, contacto=d.get("contacto") or None,
            telefono=d.get("telefono") or None, email_login=d.get("email_login") or None)
        if not r.get("ok"):
            return pagina_onboarding(token, sectores=sectores.listar(), error=r.get("error")), 400
        sesion = S.crear_sesion(r["id_suministrador"])
        return pagina_onboarding_completado(f"/portal/proveedor/{sesion}/dashboard")

    @bp.get("/acceso")
    def acceso():
        return pagina_acceso()

    @bp.post("/acceso")
    def acceso_post():
        from src.services.compras import suministradores as S
        S.solicitar_acceso(request.form.get("email", ""))
        return pagina_acceso(enviado=True)

    @bp.post("/<token>/cerrar")
    def cerrar_beacon(token):
        """Objetivo del `navigator.sendBeacon` disparado por el script de `_layout` en `pagehide`
        (cierre real de pestaña, no navegación interna): reenvía un enlace nuevo sin invalidar el
        token actual (por si el cierre era solo la pestaña en segundo plano, la sesión sigue
        sirviendo mientras no caduque). Responde 204 sin cuerpo — sendBeacon no lee la respuesta."""
        from src.services.compras import suministradores as S
        sup = S.resolver_sesion(token)
        if sup:
            S.notificar_reentrada(sup["id"])
        return ("", 204)

    @bp.post("/<token>/logout")
    def logout(token):
        """Cierre EXPLÍCITO de sesión (botón "Cerrar sesión"): invalida el token actual y envía el
        siguiente sin esperar al pagehide — único flujo de reentrada del portal."""
        from src.services.compras import suministradores as S
        S.cerrar_sesion(token)
        return pagina_sesion_cerrada()

    @bp.get("/<token>/dashboard")
    def dashboard(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        return pagina_dashboard(token, sup)

    @bp.get("/<token>/catalogo")
    def catalogo(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]))

    @bp.post("/<token>/catalogo/nuevo")
    def catalogo_nuevo(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        d = request.form
        r = C.crear_articulo(
            sup["id"], d.get("codigo", ""), d.get("nombre", ""),
            unidad_medida=d.get("unidad_medida", ""), moq=d.get("moq", 1),
            precio_unitario=d.get("precio_unitario", 0), descripcion=d.get("descripcion") or None,
            sector_id=sup.get("sector_id"))
        arts = C.listar_por_suministrador(sup["id"])
        if not r.get("ok"):
            return pagina_catalogo(token, arts, mensaje=None), 400
        return redirect(f"/portal/proveedor/{token}/catalogo")

    @bp.post("/<token>/catalogo/importar")
    def catalogo_importar(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        f = request.files.get("archivo")
        if not f or not f.filename:
            return pagina_catalogo(token, C.listar_por_suministrador(sup["id"])), 400
        try:
            import pandas as pd
            df = pd.read_csv(f) if f.filename.lower().endswith(".csv") else pd.read_excel(f)
            filas = df.fillna("").to_dict(orient="records")
        except Exception as e:
            logger.warning("catalogo_importar parseo(%s): %s", f.filename, e)
            return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]),
                                   mensaje=None), 400
        resultado = C.importar_lote(sup["id"], filas, archivo_nombre=f.filename)
        return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]), resultado_import=resultado)

    return bp
