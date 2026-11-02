"""
Panel web del FUNDADOR (Fase 4). HTML por funciones puras + Flask fino, mismo patrón que
`src.backend.portal_empresa_b2b`/`portal_proveedor` — pero con login real (una única cuenta, ver
`services.licencia_central.panel_fundador`) en vez de un enlace de invitación, así que la sesión
viaja en una cookie HttpOnly (token opaco resuelto contra `panel_fundador_sesiones` en cada
petición) en lugar de en la URL. Sin Flask `session`/`secret_key` — el codebase evita ese mecanismo
en todas sus superficies web (ver `cripto.py`, `b2b_sesion_empresa.py`).

Reutiliza `services.cloud_manager.tenants/licencias_cloud/monitorizacion` (la misma lógica que
tenía `gui/cloud_manager_gui.py`, ahora servida como web): listar empresas, plan, estado, crear,
suspender, reactivar, backup. No se inventa ningún motor de tenants nuevo — este blueprint solo
orquesta esos servicios y, corriendo en el proceso `backend_central` (BD central por variables de
entorno, ver `app.py`), actúan automáticamente sobre la BD central, nunca sobre la de un cliente.

Esta ruta NUNCA se monta en el backend local (`src.backend.app`) ni se empaqueta en el instalador
de escritorio — solo existe en el despliegue separado del servidor central.
"""

import functools
import logging
import os

from markupsafe import escape

logger = logging.getLogger("backend_central.rutas_admin")

_COOKIE = "fundador_sesion"


def _e(x):
    return str(escape(x if x is not None else ""))


def _cookie_segura() -> bool:
    """HTTPS obligatorio salvo en desarrollo explícito (mismo criterio que el resto del proyecto:
    seguro por defecto, degradable solo si se pide expresamente)."""
    return os.getenv("CENTRAL_DEV_HTTP") != "1"


def _layout(titulo, contenido, *, autenticado=False):
    nav = ("""<nav><a href="/central/panel/">Empresas</a>
<a href="/central/panel/voz">Voz (ElevenLabs)</a>
<a href="/central/panel/logout">Cerrar sesión</a></nav>""" if autenticado else "")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Panel del Fundador</title><style>
:root{{--ac:#00FFC6;}}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:#0D1117;color:#E6EDF3}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 24px;background:#0D1117;border-bottom:1px solid #21262D}}
nav a{{color:#8B949E;text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;border-radius:8px}}
nav a:hover{{color:#0D1117;background:var(--ac)}}
main{{max-width:1100px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:#161B22;border:1px solid #30363D;border-radius:12px;padding:18px;margin-bottom:16px}}
label{{display:block;font-size:14px;color:#8B949E;margin:10px 0 4px;font-weight:700}}
input,select{{padding:9px 10px;border-radius:8px;border:1px solid #30363D;width:100%;max-width:320px;
background:#0D1117;color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700}}
button,.btn{{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;text-decoration:none;display:inline-block;
font-size:13px;font-family:'Segoe UI',system-ui,sans-serif}}
button:hover,.btn:hover{{background:var(--ac);color:#0D1117}}
.btn-danger{{background:transparent;color:#F85149;border:2px solid #F85149}}
.btn-danger:hover{{background:#F85149;color:#0D1117}}
.btn-ghost{{background:transparent;color:#8B949E;border:2px solid #30363D}}
.btn-ghost:hover{{background:#8B949E;color:#0D1117;border-color:#8B949E}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px;vertical-align:middle}}
th{{color:#8B949E}}
.badge{{display:inline-block;background:#21262D;color:var(--ac);border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}}
.badge-suspendida,.badge-cancelada{{background:#F85149;color:#0D1117}}
.badge-activa,.badge-normal{{background:#3FB950;color:#0D1117}}
.badge-prueba{{background:#D29922;color:#0D1117}}
.error{{color:#F85149;font-weight:700}}.ok{{color:#3FB950;font-weight:700}}
.stats{{display:flex;flex-wrap:wrap;gap:14px}}
.stat{{background:#0D1117;border:1px solid #30363D;border-radius:10px;padding:12px 18px;min-width:140px}}
.stat b{{display:block;font-size:22px;color:var(--ac)}}
.stat span{{font-size:12px;color:#8B949E}}
form.inline{{display:inline;margin:0 4px 0 0}}
.acciones{{display:flex;gap:6px;flex-wrap:wrap}}
</style></head><body>
<header><span class="logo">🔒 Panel del Fundador</span></header>
{nav}
<main>{contenido}</main>
</body></html>"""


def _pagina_login(error=None):
    err_html = f'<p class="error">{_e(error)}</p>' if error else ""
    return _layout("Iniciar sesión", f"""
<div class="card" style="max-width:380px;margin:60px auto 0">
<h1>Panel del Fundador</h1>
{err_html}
<form method="post" action="/central/panel/login">
<label>Usuario</label><input type="text" name="usuario" required autofocus>
<label>Contraseña</label><input type="password" name="password" required>
<div style="margin-top:16px"><button type="submit">Entrar</button></div>
</form>
</div>""")


def _pagina_error(titulo, mensaje, codigo=200):
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p></div>",
                   autenticado=True), codigo


def _requiere_login(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        from flask import make_response, redirect, request
        token = request.cookies.get(_COOKIE)
        from src.services.licencia_central import panel_fundador
        ses = panel_fundador.resolver_sesion(token)
        if not ses:
            resp = make_response(redirect("/central/panel/login"))
            resp.delete_cookie(_COOKIE)
            return resp
        request.fundador_usuario = ses["usuario"]
        return fn(*a, **k)
    return wrapper


def _fila_tenant(t):
    id_empresa = t.get("id") or t.get("id_empresa")
    estado = _e(t.get("estado_operativo") or "—")
    clase = f"badge-{estado.lower()}" if estado and estado != "—" else "badge"
    return f"""<tr>
<td>{_e(t.get('nombre_empresa') or t.get('nombre') or '—')}</td>
<td><span class="badge {clase}">{estado}</span></td>
<td class="acciones">
<form class="inline" method="post" action="/central/panel/tenant/{_e(id_empresa)}/reactivar">
<button type="submit">Reactivar</button></form>
<form class="inline" method="post" action="/central/panel/tenant/{_e(id_empresa)}/suspender">
<button type="submit" class="btn-danger">Suspender</button></form>
<form class="inline" method="post" action="/central/panel/tenant/{_e(id_empresa)}/backup">
<button type="submit" class="btn-ghost">Backup</button></form>
</td></tr>"""


def _pagina_dashboard(mensaje=None, error=None):
    from src.services.cloud_manager import tenants, monitorizacion
    try:
        g = monitorizacion.global_()
    except Exception as e:
        logger.error("monitorizacion.global_: %s", e)
        g = {}
    try:
        lista = tenants.listar()
    except Exception as e:
        logger.error("tenants.listar: %s", e)
        lista = []

    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    if error:
        aviso += f'<p class="error">{_e(error)}</p>'

    filas = "".join(_fila_tenant(t) for t in lista) or \
        '<tr><td colspan="3">No hay empresas registradas todavía.</td></tr>'

    sis = g.get("sistema") or {}
    salud = g.get("salud") or {}

    return _layout("Empresas", f"""
<h1>Empresas registradas</h1>
{aviso}
<div class="card stats">
<div class="stat"><b>{_e(len(lista))}</b><span>Empresas</span></div>
<div class="stat"><b>{_e(sis.get('cpu_pct', '—'))}%</b><span>CPU servidor</span></div>
<div class="stat"><b>{_e(sis.get('ram_pct', '—'))}%</b><span>RAM servidor</span></div>
<div class="stat"><b>{_e(salud.get('status', '—'))}</b><span>Salud</span></div>
</div>
<div class="card">
<h2>Alta de empresa</h2>
<form method="post" action="/central/panel/tenant/crear">
<label>Nombre</label><input type="text" name="nombre" required>
<label>Plan</label>
<select name="plan">
<option value="trial">trial</option>
<option value="basic" selected>basic</option>
<option value="professional">professional</option>
<option value="enterprise">enterprise</option>
</select>
<div style="margin-top:16px"><button type="submit">Crear empresa</button></div>
</form>
</div>
<div class="card">
<h2>Listado</h2>
<table><thead><tr><th>Empresa</th><th>Estado</th><th>Acciones</th></tr></thead>
<tbody>{filas}</tbody></table>
</div>""", autenticado=True)


def _fila_empresa_voz(e):
    return f"""<tr>
<td>{_e(e.get('id_empresa'))}</td>
<td>{_e(f"{e.get('caracteres', 0):,}")}</td>
<td>${_e(f"{e.get('coste_usd', 0):.4f}")}</td>
<td>${_e(f"{e.get('facturado_usd', 0):.4f}")}</td>
</tr>"""


def _pagina_voz(mensaje=None, error=None):
    """Panel GLOBAL (cross-empresa) de coste real vs. facturado de voz (ElevenLabs/SOMA) + editor
    de la tarifa de reventa (coste base + margen). Vive AQUÍ a propósito, nunca en
    `gui/saas_admin.py`: SUPERADMIN es un rol interno de cada empresa cliente, no una identidad de
    plataforma (ver `services/saas/voz_plan.py`, que documenta la misma frontera), así que el
    desglose cruzado entre empresas y el ajuste de la tarifa global solo pueden vivir en esta
    cuenta única del Fundador, sin relación con ningún tenant."""
    from src.services.saas import voz_plan
    from src.services.voz_control_uso import tarifa_actual
    try:
        resumen = voz_plan.resumen_global_voz()
    except Exception as e:
        logger.error("voz_plan.resumen_global_voz: %s", e)
        resumen = {"coste_total_usd": 0, "facturado_total_usd": 0, "margen_total_usd": 0, "por_empresa": []}
    try:
        coste_actual, margen_actual = tarifa_actual()
    except Exception as e:
        logger.error("voz_control_uso.tarifa_actual: %s", e)
        coste_actual, margen_actual = 0.0, 0.0

    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    if error:
        aviso += f'<p class="error">{_e(error)}</p>'

    filas = "".join(_fila_empresa_voz(e) for e in resumen.get("por_empresa") or []) or \
        '<tr><td colspan="4">Todavía no hay uso de voz registrado.</td></tr>'

    return _layout("Voz (ElevenLabs)", f"""
<h1>Voz (ElevenLabs / SOMA) — coste vs. facturación</h1>
{aviso}
<div class="card stats">
<div class="stat"><b>${_e(f"{resumen.get('coste_total_usd', 0):.4f}")}</b><span>Coste real (proveedor)</span></div>
<div class="stat"><b>${_e(f"{resumen.get('facturado_total_usd', 0):.4f}")}</b><span>Facturado (con margen)</span></div>
<div class="stat"><b>${_e(f"{resumen.get('margen_total_usd', 0):.4f}")}</b><span>Margen generado</span></div>
</div>
<div class="card">
<h2>Tarifa de reventa (global)</h2>
<form method="post" action="/central/panel/voz/tarifa">
<label>Coste por carácter (USD) — lo que cobra ElevenLabs</label>
<input type="number" step="0.00000001" min="0" name="cost_basis_per_char_usd" value="{_e(coste_actual)}" required>
<label>Margen de reventa (%)</label>
<input type="number" step="0.01" min="0" name="margen_pct" value="{_e(margen_actual)}" required>
<div style="margin-top:16px"><button type="submit">Actualizar tarifa</button></div>
</form>
</div>
<div class="card">
<h2>Desglose por empresa (todas, sin filtro)</h2>
<table><thead><tr><th>Empresa</th><th>Caracteres</th><th>Coste real</th><th>Facturado</th></tr></thead>
<tbody>{filas}</tbody></table>
</div>""", autenticado=True)


def crear_blueprint():
    from flask import Blueprint, make_response, redirect, request

    bp = Blueprint("panel_fundador", __name__, url_prefix="/central/panel")

    @bp.get("/login")
    def login_form():
        token = request.cookies.get(_COOKIE)
        from src.services.licencia_central import panel_fundador
        if panel_fundador.resolver_sesion(token):
            return redirect("/central/panel/")
        return _pagina_login()

    @bp.post("/login")
    def login_submit():
        from src.seguridad import rate_limit
        clave = f"{request.remote_addr or '?'}:panel_fundador_login"
        if not rate_limit.permitido(clave, 10, 60):
            return _pagina_login("Demasiados intentos. Espera un minuto.")

        usuario = (request.form.get("usuario") or "").strip()
        password = request.form.get("password") or ""
        from src.services.licencia_central import panel_fundador
        if not panel_fundador.verificar_password(usuario, password):
            return _pagina_login("Usuario o contraseña incorrectos.")

        r = panel_fundador.crear_sesion(usuario)
        if not r.get("ok"):
            return _pagina_login("No se pudo iniciar sesión. Inténtalo de nuevo.")
        panel_fundador.registrar_acceso(usuario)

        resp = make_response(redirect("/central/panel/"))
        resp.set_cookie(_COOKIE, r["token"], httponly=True, secure=_cookie_segura(),
                        samesite="Lax", max_age=panel_fundador.MINUTOS_SESION * 60)
        return resp

    @bp.get("/logout")
    def logout():
        token = request.cookies.get(_COOKIE)
        from src.services.licencia_central import panel_fundador
        panel_fundador.cerrar_sesion(token)
        resp = make_response(redirect("/central/panel/login"))
        resp.delete_cookie(_COOKIE)
        return resp

    @bp.get("/")
    @_requiere_login
    def dashboard():
        return _pagina_dashboard()

    @bp.post("/tenant/crear")
    @_requiere_login
    def tenant_crear():
        nombre = (request.form.get("nombre") or "").strip()
        plan = (request.form.get("plan") or "basic").strip()
        if not nombre:
            return _pagina_dashboard(error="Indica el nombre de la empresa.")
        from src.services.cloud_manager import tenants
        r = tenants.crear(nombre, plan=plan, usuario=request.fundador_usuario)
        if not r.get("ok"):
            return _pagina_dashboard(error=r.get("error") or "No se pudo crear la empresa.")
        return _pagina_dashboard(mensaje=f"Empresa «{nombre}» creada.")

    @bp.post("/tenant/<id_empresa>/suspender")
    @_requiere_login
    def tenant_suspender(id_empresa):
        from src.services.cloud_manager import tenants
        r = tenants.suspender(id_empresa, usuario=request.fundador_usuario)
        if not r.get("ok"):
            return _pagina_dashboard(error=r.get("error") or "No se pudo suspender.")
        return _pagina_dashboard(mensaje="Empresa suspendida.")

    @bp.post("/tenant/<id_empresa>/reactivar")
    @_requiere_login
    def tenant_reactivar(id_empresa):
        from src.services.cloud_manager import tenants
        r = tenants.reactivar(id_empresa, usuario=request.fundador_usuario)
        if not r.get("ok"):
            return _pagina_dashboard(error=r.get("error") or "No se pudo reactivar.")
        return _pagina_dashboard(mensaje="Empresa reactivada.")

    @bp.post("/tenant/<id_empresa>/backup")
    @_requiere_login
    def tenant_backup(id_empresa):
        from src.services.cloud_manager import tenants
        r = tenants.backup(id_empresa)
        if not r.get("ok"):
            return _pagina_dashboard(error=r.get("error") or "No se pudo generar el backup.")
        return _pagina_dashboard(mensaje="Backup generado.")

    @bp.get("/voz")
    @_requiere_login
    def voz_dashboard():
        return _pagina_voz()

    @bp.post("/voz/tarifa")
    @_requiere_login
    def voz_tarifa():
        from src.services.saas import voz_plan
        try:
            voz_plan.actualizar_tarifa_global(
                request.form.get("cost_basis_per_char_usd"),
                request.form.get("margen_pct"),
                actualizado_por=request.fundador_usuario,
            )
        except Exception as e:
            return _pagina_voz(error=f"No se pudo actualizar la tarifa: {e}")
        return _pagina_voz(mensaje="Tarifa de voz actualizada.")

    return bp
