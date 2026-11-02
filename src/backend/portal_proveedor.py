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

from src.backend.portal_empresa_b2b import (_CDATE_CSS, _CDATE_JS, _CFILE_CSS, _CFILE_JS,
                                             _CSEL_CSS, _CSEL_JS)
from src.backend.portal_i18n import idioma_actual, registrar_selector_idioma, selector_idioma_html, t as _t

logger = logging.getLogger("backend.portal_proveedor")

_ETIQUETA_UNIDAD = {"kg": "Kilos", "unidad": "Unidades", "pale": "Palés", "caja": "Cajas"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _nav_html(token, activo, *, no_leidos=0):
    """Nav del panel (Panel/Catálogo/Pedidos/Cerrar sesión), construida sin estado global — cada
    página pasa su propio `token` de sesión y cuál de los enlaces está activo."""
    base = f"/portal/proveedor/{token}"
    badge = f' <span class="badge-alerta">{no_leidos}</span>' if no_leidos else ""
    enlaces = (("dashboard", f"{base}/dashboard", _t("portal_prov.nav_panel", "Panel")),
              ("catalogo", f"{base}/catalogo", _t("portal_prov.nav_catalogo", "Catálogo")),
              ("pedidos", f"{base}/pedidos", f'{_t("portal_prov.nav_pedidos", "Pedidos")}{badge}'),
              ("rappels", f"{base}/rappels", _t("portal_prov.nav_rappels", "Rappels")),
              ("consignacion", f"{base}/consignacion", _t("portal_prov.nav_consignacion", "Consignación")),
              ("licitaciones", f"{base}/licitaciones", _t("portal_prov.nav_licitaciones", "Licitaciones")),
              ("abandonados", f"{base}/abandonados",
               _t("portal_prov.nav_abandonados", "Carritos abandonados")),
              ("rma", f"{base}/rma", _t("portal_prov.nav_rma", "RMA pendientes")))
    links = "".join(f'<a href="{href}"{" class=\"on\"" if activo == key else ""}>{label}</a>'
                    for key, href, label in enlaces)
    logout = (f'<form method="post" action="{base}/logout" style="margin-left:auto">'
             f'<button type="submit" class="nav-logout">'
             f'{_t("portal_prov.cerrar_sesion", "Cerrar sesión")}</button></form>')
    return links + logout + selector_idioma_html(accion="/portal/proveedor/idioma")


_FLECHA_SVG = ("data:image/svg+xml;utf8,"
              "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E"
              "%3Cpath d='M1 1l5 5 5-5' stroke='%2300FFC6' stroke-width='2' fill='none' "
              "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")


def _layout(titulo, contenido, nav="", *, token=None):
    """`token`: sesión activa del proveedor (páginas con nav: panel/catálogo/pedidos/…) — el token de
    sesión ya viaja en cada URL del portal (ver docstring del módulo); no se usa aquí para nada más
    (ya no inyecta ningún script de aviso al cerrar la pestaña — ese mecanismo de reentrada
    automática se retiró junto con el login sin contraseña, ver `suministradores.verificar_login`).

    Tema de color: SOLO LECTURA aquí a propósito — el proveedor es un tercero EXTERNO sin acceso a
    una empresa concreta de Smart Manager (su sesión no resuelve a un `id_empresa`, ver
    `suministradores.resolver_sesion`), así que nunca se le ofrece una página para EDITAR el color
    (eso es cosa de la propia empresa, en el Portal Empleado o el Portal Empresa B2B) — solo
    hereda, visualmente, la paleta por defecto/compartida (`portal_theming`, sin `id_empresa`)."""
    from src.backend import portal_theming as _tema
    script = f"<script>{_CSEL_JS}</script><script>{_CFILE_JS}</script><script>{_CDATE_JS}</script>"
    return f"""<!doctype html><html lang="{_e(idioma_actual())}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Portal de Proveedores</title><style>
:root{_tema.bloque_css_variables()}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:var(--bg);color:var(--text)}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;align-items:center;gap:8px;padding:12px 24px;background:var(--bg);
border-bottom:1px solid #21262D}}
nav a{{color:var(--text2);text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;
border-radius:8px}}nav a.on,nav a:hover{{color:var(--bg);background:var(--ac)}}
nav .nav-logout{{background:transparent;color:var(--err);border:2px solid var(--err);border-radius:8px;
font-weight:700;font-size:13px;padding:6px 10px;cursor:pointer;margin-top:0;
font-family:'Segoe UI',system-ui,sans-serif}}
nav .nav-logout:hover{{background:var(--err);color:var(--bg)}}
main{{max-width:900px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:var(--bg2);border:1px solid var(--borde);border-radius:12px;padding:18px;margin-bottom:16px}}
label{{display:block;font-size:14px;color:var(--text2);margin:10px 0 4px;font-weight:700}}
input,select,textarea{{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--borde);
background:var(--bg);color:var(--text);font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;
font-weight:700;margin:0 10px 10px 0}}
select{{appearance:none;-webkit-appearance:none;border:2px solid var(--ac);border-radius:10px;
background-color:var(--bg);background-image:url("{_FLECHA_SVG}");background-repeat:no-repeat;
background-position:right 12px center;background-size:12px 8px;padding-right:32px;cursor:pointer}}
select:focus{{outline:none;border-color:var(--ac)}}
input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{{
-webkit-appearance:none;margin:0}}
input[type=number]{{-moz-appearance:textfield}}
input[type=time],input[data-cdate-tipo]{{background:var(--bg);color:var(--text);
border:1px solid var(--ac);border-radius:8px;color-scheme:dark}}
input[type=time]::-webkit-calendar-picker-indicator{{filter:invert(1) sepia(1) saturate(5)
hue-rotate(120deg);cursor:pointer}}
input[type=file]{{border:none;background:transparent;padding:0;width:auto;margin-right:14px;
vertical-align:middle}}
input[type=file]::file-selector-button{{background:transparent;color:var(--ac);
border:2px solid var(--ac);border-radius:8px;padding:9px 16px;font-weight:900;
font-family:'Segoe UI',system-ui,sans-serif;cursor:pointer;margin-right:10px}}
input[type=file]::file-selector-button:hover{{background:var(--ac);color:var(--bg)}}
button{{margin:14px 10px 10px 0;padding:9px 16px;border-radius:8px;border:2px solid var(--ac);
background:transparent;color:var(--ac);font-weight:900;cursor:pointer;vertical-align:middle;
font-family:'Segoe UI',system-ui,sans-serif}}
button:hover{{background:var(--ac);color:var(--bg)}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px}}
th{{color:var(--text2)}}
.badge{{display:inline-block;background:#21262D;color:var(--ac);border-radius:6px;padding:2px 8px;
font-size:11px;font-weight:700}}
.error{{color:var(--err);font-weight:700}}.ok{{color:var(--ok);font-weight:700}}
a.enlace{{color:var(--ac);font-weight:700;text-decoration:none}}
.badge-alerta{{display:inline-block;min-width:16px;padding:1px 6px;border-radius:999px;
background:var(--err);color:#fff;font-size:11px;font-weight:900;text-align:center}}
.chat{{display:flex;flex-direction:column;gap:10px;max-height:420px;overflow-y:auto;margin-bottom:12px}}
.msg{{max-width:75%;padding:8px 12px;border-radius:12px;background:var(--bg);border:1px solid var(--borde)}}
.msg-propio{{align-self:flex-end;border-color:var(--ac)}}
.msg-otro{{align-self:flex-start}}
.msg-autor{{font-size:11px;color:var(--ac);font-weight:900;margin-bottom:2px}}
.msg-cuerpo{{font-size:14px;color:var(--text);white-space:pre-wrap;word-break:break-word}}
.msg-fecha{{font-size:10px;color:var(--text2);margin-top:4px}}
.escalon-fila{{display:flex;gap:10px;align-items:center;margin-bottom:8px}}
.escalon-fila input{{width:auto;flex:1}}
.progreso{{width:100%;height:14px;border-radius:999px;background:var(--bg);border:1px solid var(--borde);
overflow:hidden;margin-top:8px}}
.progreso-barra{{height:100%;border-radius:999px;transition:width .2s}}
{_CSEL_CSS}
{_CFILE_CSS}
{_CDATE_CSS}
.sel-idioma{{margin-left:auto}}
.sel-idioma select{{padding:5px 24px 5px 8px;font-size:12px;margin:0}}
{_tema.CSS_POLISH}
</style></head><body>
<header><span class="logo">📦 {_t("portal_prov.titulo_marca", "Portal de Proveedores")}</span></header>
<nav>{nav}</nav>
<main>{contenido}</main>
{script}
</body></html>"""


def _pagina_error(titulo, mensaje):
    return _layout(titulo, f"""<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p>
<p><a class="enlace" href="/portal/proveedor/acceso">{_t("portal_prov.volver_iniciar_sesion", "Volver a iniciar sesión")}</a></p></div>""")


# ── Onboarding (desde el enlace de invitación) ───────────────────────────────
def pagina_onboarding(token, *, sectores, error=None):
    opciones = "".join(f'<option value="{s["id"]}">{_e(s["nombre"])}</option>' for s in sectores)
    aviso = f'<p class="error">{_e(error)}</p>' if error else ""
    return _layout(_t("portal_prov.alta_proveedor_titulo", "Alta de proveedor"), f"""
<div class="card">
<h1>{_t("portal_prov.completa_alta_h1", "Completa tu alta como proveedor")}</h1>
<p>{_t("portal_prov.completa_alta_desc",
      "Rellena estos datos para acceder al catálogo B2B. El sector es obligatorio: determina qué "
      "empresas podrán ver tus ofertas. El email y la contraseña serán tus credenciales para "
      "volver a entrar más adelante.")}</p>
{aviso}
<form method="post" action="/portal/proveedor/onboarding/{_e(token)}">
<label>{_t("portal_prov.razon_social_lbl", "Razón social *")}</label><input name="razon_social" required>
<label>{_t("portal_prov.cif_lbl", "CIF *")}</label><input name="cif" required>
<label>{_t("portal_prov.sector_lbl", "Sector comercial *")}</label><select name="sector_id" required>
<option value="">{_t("portal_prov.selecciona_sector_ph", "Selecciona un sector…")}</option>{opciones}</select>
<label>{_t("portal_prov.contacto_lbl", "Persona de contacto")}</label><input name="contacto">
<label>{_t("portal_prov.telefono_lbl", "Teléfono")}</label><input name="telefono">
<label>{_t("portal_prov.email_acceso_lbl", "Email de acceso *")}</label><input name="email_login" type="email" required>
<label>{_t("portal_prov.password_lbl", "Contraseña *")}</label><input name="password" type="password" minlength="8" required>
<label>{_t("portal_prov.confirmar_password_lbl", "Confirmar contraseña *")}</label><input name="confirmar_password" type="password" minlength="8" required>
<button type="submit">{_t("portal_prov.completar_alta_btn", "Completar alta")}</button>
</form>
</div>""")


def pagina_onboarding_completado(url_dashboard):
    return _layout(_t("portal_prov.alta_completada_titulo", "Alta completada"), f"""
<div class="card"><h1 class="ok">✓ {_t("portal_prov.alta_completada_h1", "Alta completada")}</h1>
<p>{_t("portal_prov.ya_puedes_acceder", "Ya puedes acceder a tu panel de proveedor.")}</p>
<p><a class="enlace" href="{_e(url_dashboard)}">{_t("portal_prov.entrar_panel", "Entrar al panel →")}</a></p>
<p>{_t("portal_prov.guarda_credenciales",
      "Guarda tu email y contraseña: los necesitarás la próxima vez que quieras entrar, en")}
<a class="enlace" href="/portal/proveedor/acceso">/portal/proveedor/acceso</a>.</p>
</div>""")


# ── Acceso (login email + contraseña) ─────────────────────────────────────────
def pagina_acceso(*, token=None, error=None, info=None):
    """Login real de email+contraseña (sustituye el antiguo "solo email, te mandamos un enlace").
    `token`: contexto opcional de una invitación — si está presente (visita desde el enlace de
    invitación o desde `/onboarding/<token>`), se muestra el enlace "¿Aún no te has registrado?"
    hacia el alta con ESE MISMO token (permanente, ver `invitaciones.resolver_token`); sin token
    (visita directa/bookmarked a `/acceso`) el formulario se muestra igual pero sin ese enlace, al no
    haber token del que partir hacia el alta."""
    aviso = f'<p class="error">{_e(error)}</p>' if error else (
        f'<p class="ok">{_e(info)}</p>' if info else "")
    action = f"/portal/proveedor/acceso/{_e(token)}" if token else "/portal/proveedor/acceso"
    enlace_alta = (f'<p>{_t("portal_prov.aun_no_registrado", "¿Aún no te has registrado?")} <a class="enlace" '
                   f'href="/portal/proveedor/onboarding/{_e(token)}">{_t("portal_prov.completa_alta_aqui", "Completa tu alta aquí")}</a>.</p>'
                   if token else "")
    cuerpo = f"""<h1>{_t("portal_prov.acceder_panel_h1", "Acceder a tu panel")}</h1>
{aviso}
<form method="post" action="{action}">
<label>{_t("portal_prov.email_acceso_lbl2", "Email de acceso")}</label><input name="email" type="email" required>
<label>{_t("portal_prov.password_lbl2", "Contraseña")}</label><input name="password" type="password" required>
<button type="submit">{_t("portal_prov.entrar_btn", "Entrar")}</button>
</form>
{enlace_alta}"""
    return _layout(_t("portal_prov.acceso_proveedor_titulo", "Acceso proveedor"), f'<div class="card">{cuerpo}</div>')


def pagina_sesion_cerrada():
    return _layout(_t("portal_prov.sesion_cerrada_titulo", "Sesión cerrada"), f"""
<div class="card"><h1 class="ok">✓ {_t("portal_prov.sesion_cerrada_h1", "Sesión cerrada")}</h1>
<p>{_t("portal_prov.sesion_cerrada_desc", "Has cerrado tu sesión correctamente.")}</p>
<p><a class="enlace" href="/portal/proveedor/acceso">{_t("portal_prov.volver_iniciar_sesion", "Volver a iniciar sesión")}</a></p>
</div>""")


# ── Panel del proveedor ───────────────────────────────────────────────────────
def pagina_dashboard(token, suministrador, *, metricas=None, no_leidos=0):
    estado = suministrador.get("estado_kyb", "pendiente")
    panel_metricas = ""
    if metricas:
        filas_met = "".join(f"<tr><td>{_e(m['codigo'])}</td><td>{_e(m['nombre'])}</td>"
                            f"<td>{m['vistas']}</td><td>{m['clics']}</td></tr>" for m in metricas)
        panel_metricas = f"""<div class="card"><h2>{_t("portal_prov.visibilidad_catalogo", "Visibilidad de tu catálogo (últimos 30 días)")}</h2>
<table><tr><th>{_t("portal_prov.col_codigo", "Código")}</th><th>{_t("portal_prov.col_nombre", "Nombre")}</th><th>{_t("portal_prov.col_vistas", "Vistas")}</th><th>{_t("portal_prov.col_clics", "Clics")}</th></tr>{filas_met}</table>
</div>"""
    return _layout(_t("portal_prov.nav_panel", "Panel"), f"""
<div class="card">
<h1>{_e(suministrador.get('razon_social'))}</h1>
<p>{_t("portal_prov.cif_lbl2", "CIF:")} {_e(suministrador.get('cif'))} · {_t("portal_prov.estado_verificacion", "Estado de verificación:")}
<span class="badge">{_e(estado)}</span></p>
<p>{_t("portal_prov.contacto_lbl2", "Contacto:")} {_e(suministrador.get('contacto') or '—')} · {_t("portal_prov.tel_lbl", "Tel:")} {_e(suministrador.get('telefono') or '—')}</p>
</div>
{panel_metricas}""", nav=_nav_html(token, "dashboard", no_leidos=no_leidos), token=token)


def pagina_catalogo(token, articulos, *, mensaje=None, error=None, resultado_import=None, no_leidos=0):
    base_esc = f"/portal/proveedor/{token}/catalogo"

    def _fila_articulo(a):
        perecedero = bool(a.get("es_perecedero"))
        cad = (f"<span class='badge'>{_t('portal_prov.perecedero_badge', 'Perecedero')}</span><br>"
              f"{_t('portal_prov.lote_caduca', 'Lote {l} · Caduca {f}', l=_e(a.get('lote') or '—'), f=_e(a.get('fecha_caducidad') or '—'))}"
              if perecedero else _t("portal_prov.no_perecedero", "No perecedero"))
        consig = (f"<span class='badge badge-ok'>{_t('portal_prov.consignacion_badge', 'Consignación')}</span><br>"
                 f"{_t('portal_prov.comision_lbl', 'Comisión {c} €/ud', c=a.get('comision_unitaria'))}"
                 if a.get("disponible_consignacion") else "—")
        return f"""<tr><td>{_e(a['codigo'])}</td><td>{_e(a['nombre'])}</td>
<td>{_ETIQUETA_UNIDAD.get(a['unidad_medida'], a['unidad_medida'])}</td>
<td>{a['moq']}</td><td>{a['precio_unitario']} €</td><td>{cad}</td><td>{consig}</td>
<td><a class="enlace" href="{base_esc}/{a['id']}/escalones">{_t("portal_prov.precios_volumen", "Precios por volumen")}</a><br>
<a class="enlace" href="{base_esc}/{a['id']}/bundles">{_t("portal_prov.packs", "Packs")}</a></td></tr>"""

    filas = "".join(_fila_articulo(a) for a in articulos)
    tabla = (f'<table><tr><th>{_t("portal_prov.col_codigo", "Código")}</th>'
            f'<th>{_t("portal_prov.col_nombre", "Nombre")}</th>'
            f'<th>{_t("portal_prov.col_unidad", "Unidad")}</th><th>MOQ</th>'
            f'<th>{_t("portal_prov.col_precio", "Precio")}</th>'
            f'<th>{_t("portal_prov.col_trazabilidad", "Trazabilidad")}</th>'
            f'<th>{_t("portal_prov.col_consignacion", "Consignación")}</th><th></th></tr>{filas}</table>'
            if articulos else f'<p>{_t("portal_prov.sin_articulos", "Aún no has publicado artículos.")}</p>')
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (
        f'<p class="error">{_e(error)}</p>' if error else "")
    resumen_import = ""
    if resultado_import:
        errs = "".join(
            f'<li>{_t("portal_prov.fila_error", "Fila {f} ({c}): {e}", f=e["fila"], c=_e(e["codigo"]), e=_e(e["error"]))}</li>'
            for e in resultado_import.get("errores", []))
        resumen_import = f"""<p class="ok">{_t("portal_prov.importadas_filas", "Importadas {n} filas.", n=resultado_import['filas_ok'])}</p>
{f'<p class="error">{_t("portal_prov.filas_con_error", "{n} filas con error:", n=resultado_import["filas_error"])}</p><ul>{errs}</ul>' if errs else ''}"""
    opciones_unidad = "".join(f'<option value="{k}">{v}</option>' for k, v in _ETIQUETA_UNIDAD.items())
    base = f"/portal/proveedor/{token}"
    return _layout(_t("portal_prov.nav_catalogo", "Catálogo"), f"""
<div class="card"><h1>{_t("portal_prov.tu_catalogo_b2b", "Tu catálogo B2B")}</h1>{aviso}{tabla}</div>
<div class="card"><h2>{_t("portal_prov.anadir_articulo_h2", "Añadir artículo")}</h2>
<form method="post" action="{base}/catalogo/nuevo">
<label>{_t("portal_prov.codigo_lbl", "Código *")}</label><input name="codigo" required>
<label>{_t("portal_prov.nombre_lbl", "Nombre *")}</label><input name="nombre" required>
<label>{_t("portal_prov.unidad_mayorista_lbl", "Unidad de Medida Mayorista *")}</label><select name="unidad_medida" required>{opciones_unidad}</select>
<label>{_t("portal_prov.moq_lbl", "Cantidad Mínima de Pedido (MOQ) *")}</label><input name="moq" type="number" min="1" value="1" required>
<label>{_t("portal_prov.precio_unitario_lbl", "Precio unitario (€) *")}</label><input name="precio_unitario" type="number" step="0.01" min="0" required>
<label>{_t("portal_prov.descripcion_lbl", "Descripción")}</label><textarea name="descripcion" rows="2"></textarea>
<label>{_t("portal_prov.talla_req_lbl", "Talla * (o el equivalente de tu sector, p. ej. calibre)")}</label>
<input name="talla" required>
<label>{_t("portal_prov.marca_req_lbl", "Marca * (o el equivalente de tu sector, p. ej. variedad)")}</label>
<input name="marca" required>
<label>{_t("portal_prov.color_req_lbl", "Color *")}</label>
<input name="color" required>
<label>{_t("portal_prov.trazabilidad_lbl", "Trazabilidad *")}</label>
<select name="es_perecedero" id="sel_perecedero" required>
<option value="0">{_t("portal_prov.no_perecedero", "No perecedero")}</option>
<option value="1">{_t("portal_prov.perecedero_badge", "Perecedero")}</option>
</select>
<div id="campos_perecedero" style="display:none">
<label>{_t("portal_prov.lote_lbl", "Lote *")}</label><input name="lote" id="in_lote">
<label>{_t("portal_prov.fecha_caducidad_lbl", "Fecha de caducidad / consumo preferente *")}</label><input name="fecha_caducidad" id="in_caducidad"
type="text" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
</div>
<label>{_t("portal_prov.disponible_consignacion_lbl", "Disponible para consignación")}</label>
<select name="disponible_consignacion" id="sel_consignacion">
<option value="0">{_t("portal_prov.no_opt", "No")}</option>
<option value="1">{_t("portal_prov.si_opt", "Sí")}</option>
</select>
<div id="campos_consignacion" style="display:none">
<label>{_t("portal_prov.comision_unidad_lbl", "Comisión por unidad (€) *")}</label><input name="comision_unitaria" id="in_comision"
type="number" step="0.01" min="0">
</div>
<button type="submit">{_t("portal_prov.publicar_articulo_btn", "Publicar artículo")}</button>
</form>
<script>
(function(){{
 var sel = document.getElementById('sel_perecedero');
 var campos = document.getElementById('campos_perecedero');
 var inLote = document.getElementById('in_lote');
 var inCad = document.getElementById('in_caducidad');
 function sync(){{
   var per = sel.value === '1';
   campos.style.display = per ? 'block' : 'none';
   if (inLote) inLote.required = per;
   if (inCad) inCad.required = per;
 }}
 sel.addEventListener('change', sync);
 sync();
 var selConsig = document.getElementById('sel_consignacion');
 var camposConsig = document.getElementById('campos_consignacion');
 var inComision = document.getElementById('in_comision');
 function syncConsig(){{
   var consig = selConsig.value === '1';
   camposConsig.style.display = consig ? 'block' : 'none';
   if (inComision) inComision.required = consig;
 }}
 selConsig.addEventListener('change', syncConsig);
 syncConsig();
}})();
</script>
</div>
<div class="card"><h2>{_t("portal_prov.subir_catalogo_h2", "Subir catálogo (CSV/Excel)")}</h2>
<p>{_t("portal_prov.columnas_esperadas", "Columnas esperadas:")} <code>codigo, nombre, unidad_medida, moq, precio_unitario, descripcion,
es_perecedero, lote, fecha_caducidad</code> {_t("portal_prov.columnas_nota", "(unidad_medida: kg/unidad/pale/caja; es_perecedero: 1/0 — si es 1, lote y fecha_caducidad son obligatorios en esa fila).")}</p>
{resumen_import}
<form method="post" action="{base}/catalogo/importar" enctype="multipart/form-data">
<input type="file" name="archivo" accept=".csv,.xlsx,.xls" required>
<button type="submit">{_t("portal_prov.importar_btn", "Importar")}</button>
</form></div>""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos), token=token)


# ── Precios escalonados por volumen (rappels) ────────────────────────────────
def pagina_escalones(token, articulo, escalones, *, mensaje=None, no_leidos=0):
    base = f"/portal/proveedor/{token}/catalogo/{articulo['id']}/escalones"
    ph_desde = _t("portal_prov.a_partir_de_ph", "A partir de…")
    ph_precio = _t("portal_prov.precio_eur_ph", "Precio (€)")
    quitar_btn = _t("portal_prov.quitar_btn2", "Quitar")
    filas_js = "".join(f"""<div class="escalon-fila">
<input type="number" name="cantidad_desde" min="1" value="{e['cantidad_desde']}" placeholder="{ph_desde}">
<input type="number" name="precio_unitario" step="0.01" min="0" value="{e['precio_unitario']}" placeholder="{ph_precio}">
<button type="button" class="btn-quitar-escalon" onclick="this.parentElement.remove()">{quitar_btn}</button>
</div>""" for e in escalones)
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    titulo = _t("portal_prov.precios_volumen", "Precios por volumen")
    return _layout(titulo, f"""
<div class="card">
<h1>{titulo} — {_e(articulo['nombre'])}</h1>
<p>{_t("portal_prov.precio_base_desc", "Precio base (desde el MOQ de {moq}):", moq=articulo['moq'])} <b>{articulo['precio_unitario']} €</b>. {_t("portal_prov.anade_escalones_desc", 'Añade escalones "a partir de X unidades → precio Y" para que el carrito de la empresa recalcule el precio automáticamente según la cantidad.')}</p>
{aviso}
<form method="post" action="{base}">
<div id="escalones-filas">{filas_js}</div>
<button type="button" id="btn-anadir-escalon">+ {_t("portal_prov.anadir_escalon_btn", "Añadir escalón")}</button>
<button type="submit">{_t("portal_prov.guardar_precios_vol_btn", "Guardar precios por volumen")}</button>
</form>
</div>
<script>
document.getElementById('btn-anadir-escalon').addEventListener('click', function(){{
 var fila = document.createElement('div'); fila.className = 'escalon-fila';
 fila.innerHTML = '<input type="number" name="cantidad_desde" min="1" placeholder="{ph_desde}">' +
   '<input type="number" name="precio_unitario" step="0.01" min="0" placeholder="{ph_precio}">' +
   '<button type="button" class="btn-quitar-escalon" onclick="this.parentElement.remove()">{quitar_btn}</button>';
 document.getElementById('escalones-filas').appendChild(fila);
}});
</script>""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos), token=token)


# ── Packs / bundles (producto A -> descuento en producto B) ─────────────────
# Mismo patrón exacto que "Precios por volumen" arriba: el proveedor configura sus propias reglas
# sobre su propio catálogo, página por artículo (el artículo de la URL es siempre el disparador A).
def pagina_bundles(token, articulo, reglas, otros_articulos, *, mensaje=None, no_leidos=0):
    base = f"/portal/proveedor/{token}/catalogo/{articulo['id']}/bundles"
    opciones_b = "".join(f'<option value="{_e(a["codigo"])}">{_e(a["nombre"])} ({_e(a["codigo"])})</option>'
                         for a in otros_articulos)
    activa_lbl = _t("portal_prov.activa_badge", "Activa")
    inactiva_lbl = _t("portal_prov.inactiva_badge", "Inactiva")
    desactivar_btn = _t("portal_prov.desactivar_btn", "Desactivar")
    filas = "".join(f"""<tr><td>{_e(r['nombre'])}</td>
<td>{_t("portal_prov.ud_de", "{n} ud. de {c}", n=r['cantidad_minima'], c=_e(articulo['codigo']))}</td>
<td>{_e(r['codigo_recompensa'])}</td>
<td>{f"{r['pct_descuento']}%" if r['forma_recompensa'] == 'pct_descuento' else f"{r['precio_pack_fijo']} € (pack)"}</td>
<td>{_e(str(r['fecha_inicio']))} → {_e(str(r['fecha_fin']))}</td>
<td>{f'<span class="badge badge-ok">{activa_lbl}</span>' if r.get('activo') else f'<span class="badge">{inactiva_lbl}</span>'}</td>
<td><form method="post" action="{base}/{r['id']}/desactivar">
<button type="submit" class="btn-danger">{desactivar_btn}</button></form></td></tr>""" for r in reglas)
    tabla = (f'<table><tr><th>{_t("portal_prov.col_nombre", "Nombre")}</th>'
            f'<th>{_t("portal_prov.col_condicion", "Condición")}</th>'
            f'<th>{_t("portal_prov.col_producto_b", "Producto B")}</th>'
            f'<th>{_t("portal_prov.col_recompensa", "Recompensa")}</th>'
            f'<th>{_t("portal_prov.col_vigencia", "Vigencia")}</th>'
            f'<th>{_t("portal_prov.col_estado", "Estado")}</th><th></th></tr>{filas}</table>'
            if reglas else f'<p>{_t("portal_prov.sin_packs", "Sin packs configurados todavía para este artículo.")}</p>')
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    titulo_bundles = _t("portal_prov.packs_bundles_titulo", "Packs / Bundles")
    return _layout(titulo_bundles, f"""
<div class="card"><h1>{_t("portal_prov.packs", "Packs")} — {_e(articulo['nombre'])}</h1>
<p>{_t("portal_prov.define_oferta_desc",
      'Define una oferta "compra N unidades de {c} y obtén un descuento en otro artículo de tu '
      'catálogo" — se aplica sola en el carrito de la empresa en cuanto se cumple la condición.',
      c=f"<code>{_e(articulo['codigo'])}</code>")}</p>
{aviso}{tabla}</div>
<div class="card"><h2>{_t("portal_prov.nuevo_pack_h2", "Nuevo pack")}</h2>
<form method="post" action="{base}">
<label>{_t("portal_prov.nombre_pack_lbl", "Nombre del pack *")}</label><input name="nombre" required placeholder="{_t("portal_prov.nombre_pack_ph", "p.ej. Pack Apertura")}">
<label>{_t("portal_prov.cantidad_minima_lbl", "Cantidad mínima de {c} *", c=_e(articulo['codigo']))}</label>
<input name="cantidad_minima" type="number" min="1" value="1" required>
<label>{_t("portal_prov.producto_b_lbl", "Producto B (recompensa) *")}</label><select name="codigo_recompensa" required>{opciones_b}</select>
<label>{_t("portal_prov.forma_recompensa_lbl", "Forma de la recompensa *")}</label>
<select name="forma_recompensa" id="sel_forma_bundle" required>
<option value="pct_descuento">{_t("portal_prov.pct_descuento_opt", "% de descuento en B")}</option>
<option value="precio_pack_fijo">{_t("portal_prov.precio_fijo_opt", "Precio fijo para el pack (A+B)")}</option>
</select>
<div id="campos_pct">
<label>{_t("portal_prov.pct_descuento_lbl", "% de descuento en B *")}</label>
<input name="pct_descuento" id="in_pct" type="number" step="0.01" min="0.01" max="100">
</div>
<div id="campos_pack" style="display:none">
<label>{_t("portal_prov.precio_fijo_pack_lbl", "Precio fijo del pack (€) *")}</label>
<input name="precio_pack_fijo" id="in_pack" type="number" step="0.01" min="0">
</div>
<label>{_t("portal_prov.vigente_desde_lbl", "Vigente desde *")}</label>
<input name="fecha_inicio" required type="text" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_prov.vigente_hasta_lbl", "Vigente hasta *")}</label>
<input name="fecha_fin" required type="text" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<button type="submit">{_t("portal_prov.crear_pack_btn", "Crear pack")}</button>
</form>
<script>
(function(){{
 var sel = document.getElementById('sel_forma_bundle');
 var cPct = document.getElementById('campos_pct');
 var cPack = document.getElementById('campos_pack');
 var inPct = document.getElementById('in_pct');
 var inPack = document.getElementById('in_pack');
 function sync(){{
  var pct = sel.value === 'pct_descuento';
  cPct.style.display = pct ? 'block' : 'none';
  cPack.style.display = pct ? 'none' : 'block';
  inPct.required = pct; inPack.required = !pct;
 }}
 sel.addEventListener('change', sync); sync();
}})();
</script>
</div>""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos), token=token)


# ── Mis pedidos + detalle (chat) ───────────────────────────────────────────────
_ETIQUETA_ESTADO = {"BORRADOR": "Borrador", "CONFIRMADA": "Confirmado", "PAGADA": "Pagado",
                    "PREPARANDO": "Preparando", "ENVIADA": "Enviado", "ENTREGADA": "Entregado",
                    "FACTURADA": "Facturado", "DEVUELTA": "Devuelto", "ABONADA": "Abonado",
                    "CANCELADA": "Cancelado", "EXPIRADA": "Expirado"}


def _etiqueta_estado_t(estado):
    return _t(f"portal_prov.estado_{estado}", _ETIQUETA_ESTADO.get(estado, estado))


def pagina_mis_pedidos(token, pedidos, *, no_leidos=0):
    base = f"/portal/proveedor/{token}"
    ver_chat = _t("portal_prov.ver_chat", "Ver / chat")
    filas = "".join(f"""<tr><td><code>{_e(p['id_tx'])}</code></td>
<td>{_e(_etiqueta_estado_t(p['estado']))}</td>
<td>{p['total']} €</td><td>{p['creada']}</td>
<td><a class="enlace" href="{base}/pedido/{p['id_tx']}">{ver_chat}</a></td></tr>""" for p in pedidos)
    tabla = (f'<table><tr><th>{_t("portal_prov.col_pedido", "Pedido")}</th>'
            f'<th>{_t("portal_prov.col_estado", "Estado")}</th>'
            f'<th>{_t("portal_prov.col_total", "Total")}</th>'
            f'<th>{_t("portal_prov.col_fecha", "Fecha")}</th>'
            f'<th></th></tr>{filas}</table>') if pedidos else f'<p>{_t("portal_prov.sin_pedidos_b2b", "Aún no has recibido ningún pedido B2B.")}</p>'
    return _layout(_t("portal_prov.nav_pedidos", "Pedidos"),
                   f'<div class="card"><h1>{_t("portal_prov.pedidos_recibidos_h1", "Pedidos recibidos")}</h1>{tabla}</div>',
        nav=_nav_html(token, "pedidos", no_leidos=no_leidos), token=token)


def _burbujas_chat_html(mensajes, lado):
    if not mensajes:
        return f'<p>{_t("portal_prov.sin_mensajes", "Aún no hay mensajes en este pedido.")}</p>'
    burbujas = []
    for m in mensajes:
        propio = m["autor_tipo"] == lado
        clase = "msg-propio" if propio else "msg-otro"
        burbujas.append(f"""<div class="msg {clase}">
<div class="msg-autor">{_e(m.get('autor_nombre') or m['autor_tipo'].capitalize())}</div>
<div class="msg-cuerpo">{_e(m['cuerpo'])}</div>
<div class="msg-fecha">{m['creado_en']}</div></div>""")
    return f'<div class="chat">{"".join(burbujas)}</div>'


def pagina_pedido_detalle(token, tx, lineas, mensajes, *, no_leidos=0, tiene_albaran=False):
    base = f"/portal/proveedor/{token}"
    filas_lineas = "".join(f"<tr><td>{_e(l['nombre'])}</td><td>{l['cantidad']}</td>"
                           f"<td>{l['precio_unitario']} €</td></tr>" for l in lineas)
    chat = _burbujas_chat_html(mensajes, "proveedor")
    albaran_html = (f'<p><a href="{base}/pedido/{tx["id_tx"]}/albaran">📄 {_t("portal_prov.descargar_albaran", "Descargar albarán")}</a></p>'
                   if tiene_albaran else "")
    return _layout(_t("portal_prov.pedido_titulo", "Pedido {ref}", ref=tx['id_tx'][:8]), f"""
<div class="card"><h1>{_t("portal_prov.pedido_h1", "Pedido")} <code>{_e(tx['id_tx'])}</code></h1>
<p>{_t("portal_prov.estado_lbl", "Estado:")} <span class="badge">{_e(_etiqueta_estado_t(tx['estado']))}</span> ·
{_t("portal_prov.total_lbl", "Total:")} <b>{tx['total']} €</b> · {_t("portal_prov.fecha_lbl", "Fecha:")} {tx['creada']}</p>
{albaran_html}
<table><tr><th>{_t("portal_prov.col_articulo", "Artículo")}</th><th>{_t("portal_prov.col_cantidad", "Cantidad")}</th><th>{_t("portal_prov.col_precio", "Precio")}</th></tr>{filas_lineas}</table>
</div>
<div class="card"><h2>{_t("portal_prov.comunicacion_pedido_h2", "Comunicación sobre este pedido")}</h2>
{chat}
<form method="post" action="{base}/pedido/{tx['id_tx']}/mensaje" style="margin-top:12px">
<textarea name="cuerpo" rows="3" placeholder="{_t("portal_prov.escribe_mensaje_ph", "Escribe un mensaje…")}" required></textarea>
<button type="submit" style="margin-top:8px">{_t("portal_prov.enviar_btn", "Enviar")}</button>
</form></div>""", nav=_nav_html(token, "pedidos", no_leidos=no_leidos), token=token)


# ── Rappels (solo lectura) ─────────────────────────────────────────────────────
# Los tramos los configura la Empresa (Portal Empresa · Gestión · Rappels); aquí el proveedor solo
# consulta su propio progreso, por cada empresa que le haya configurado tramos. Rebate RETROACTIVO
# sobre el gasto acumulado en una ventana de fechas — distinto de los "Precios por volumen" (escalones
# por cantidad) que este mismo proveedor gestiona en su Catálogo.
def _barra_rappel_proveedor_html(prog):
    if not prog.get("tiene_tramos"):
        return f'<p>{_t("portal_prov.sin_tramos", "Sin tramos configurados.")}</p>'
    tramo = prog.get("tramo_alcanzado")
    siguiente = prog.get("siguiente_tramo")
    detalle_tramo = (_t("portal_prov.tramo_alcanzado_desc",
                       "Tramo alcanzado: desde {d} € → {p} % (rebate estimado {r} €, pendiente de liquidar)",
                       d=tramo['umbral_desde'], p=tramo['pct_rebate'], r=prog['rebate_estimado']) if tramo
                     else _t("portal_prov.ningun_tramo", "Ningún tramo alcanzado todavía."))
    detalle_siguiente = (_t("portal_prov.proximo_tramo_desc", " · Próximo tramo: desde {d} € → {p} %",
                           d=siguiente['umbral_desde'], p=siguiente['pct_rebate']) if siguiente else "")
    return f"""<p>{_t("portal_prov.ventana_lbl", "Ventana")} {_e(prog['fecha_inicio'])} → {_e(prog['fecha_fin'])} · {_t("portal_prov.gasto_validado_lbl", "Gasto acumulado validado:")}
<b>{prog['gasto_acumulado']} €</b></p>
<div class="progreso"><div class="progreso-barra" style="width:{prog['pct_barra']}%;background:var(--ac)"></div></div>
<p>{detalle_tramo}{detalle_siguiente}</p>"""


# ── RMA pendientes (devoluciones de autoservicio B2B) ────────────────────────
# Revisión del proveedor sobre los RMA que los compradores han solicitado (autoservicio, pedido ya
# ENTREGADA — ver `portal_empresa_b2b.py::_rma_html`). "Autorizar Retorno" dispara
# `b2b_disputas.aprobar_devolucion_autoservicio` (efecto de stock + intento de reembolso real vía
# escrow + orden de recogida); "Rechazar con alegación" solo registra el motivo, sin tocar stock ni
# dinero.
_ETIQUETA_ESTADO_RMA = {"pendiente_aprobacion": "Pendiente de aprobación", "aprobada": "Aprobada",
                       "rechazada": "Rechazada"}


def pagina_rma_proveedor(token, bloques, *, mensaje=None, error=None, no_leidos=0):
    """`bloques`: [(nombre_empresa, [devolucion_dict con 'lineas' y 'fotos'])]."""
    base = f"/portal/proveedor/{token}"
    adjunto_lbl = _t("portal_prov.adjunto_lbl", "📷 adjunto")
    secciones = []
    for nombre_empresa, items in bloques:
        tarjetas = []
        for d in items:
            filas_lineas = "".join(f"<li>{_e(l['codigo_articulo'])} × {l['cantidad']} "
                                   f"({l['precio_unitario']} €/ud)</li>" for l in d.get("lineas", []))
            fotos_html = " ".join(
                f'<a href="{base}/rma/{d["id_devolucion"]}/foto/{doc["id_documento"]}" '
                f'target="_blank">{adjunto_lbl}</a>' for doc in d.get("fotos", []))
            tarjetas.append(f"""<div class="card" style="margin-top:10px">
<h3 style="color:#E6EDF3;font-size:14px;margin:0 0 6px">{_t("portal_prov.rma_titulo", "RMA #{id} · Pedido {ped}…", id=d['id_devolucion'], ped=_e((d.get('id_tx') or '')[:8]))}</h3>
<p>{_t("portal_prov.motivo_comprador_lbl", "Motivo del comprador:")} {_e(d.get('motivo') or '—')}</p>
<ul>{filas_lineas}</ul>
<p>{fotos_html or _t("portal_prov.sin_fotos", "Sin fotos adjuntas.")}</p>
<form method="post" action="{base}/rma/{d['id_devolucion']}/aprobar" style="display:inline">
<button type="submit">{_t("portal_prov.autorizar_retorno_btn", "Autorizar Retorno")}</button></form>
<form method="post" action="{base}/rma/{d['id_devolucion']}/rechazar" style="display:inline-block;
margin-left:8px">
<input type="text" name="motivo" placeholder="{_t("portal_prov.motivo_rechazo_ph", "Motivo del rechazo")}" required style="width:220px">
<button type="submit" class="btn-ghost">{_t("portal_prov.rechazar_alegacion_btn", "Rechazar con alegación")}</button></form>
</div>""")
        secciones.append(f"""<div class="card"><h2>{_e(nombre_empresa)}</h2>
{''.join(tarjetas) or f'<p>{_t("portal_prov.sin_rma_empresa", "Sin RMA pendientes de esta empresa.")}</p>'}</div>""")
    contenido = "".join(secciones) or (
        f'<div class=\'card\'><p>{_t("portal_prov.sin_rma_pendientes", "No tienes ninguna devolución (RMA) pendiente de revisión.")}</p></div>')
    aviso = (f'<p class="ok">{_e(mensaje)}</p>' if mensaje else
            (f'<p class="error">{_e(error)}</p>' if error else ""))
    return _layout(_t("portal_prov.nav_rma", "RMA pendientes"), f"""
<div class="card"><h1>{_t("portal_prov.rma_pendientes_h1", "Devoluciones (RMA) pendientes de aprobación")}</h1>
<p>{_t("portal_prov.rma_desc",
      "Solicitudes de devolución de compradores sobre pedidos ya entregados. Al autorizar: se "
      "aplica el efecto de stock, se intenta el reembolso que corresponda (si los fondos del "
      "pedido ya se habían liberado, queda marcado para conciliación manual en vez de fingir un "
      "reembolso que no ocurrió) y se genera la orden de recogida.")}</p>{aviso}</div>
{contenido}""", nav=_nav_html(token, "rma", no_leidos=no_leidos), token=token)


def pagina_rappels_proveedor(token, bloques, *, no_leidos=0):
    """`bloques`: [(nombre_empresa, progreso_dict, [liquidaciones])]."""
    secciones = []
    for nombre_empresa, prog, liquidaciones in bloques:
        filas_liq = "".join(f"""<tr><td>{_e(l['fecha_inicio'])} → {_e(l['fecha_fin'])}</td>
<td>{l['gasto_total']} €</td><td>{l['pct_aplicado']} %</td><td>{l['importe_rebate']} €</td></tr>"""
                            for l in liquidaciones)
        tabla_liq = (f'<table><tr><th>{_t("portal_prov.col_ventana", "Ventana")}</th>'
                    f'<th>{_t("portal_prov.col_gasto", "Gasto")}</th>'
                    f'<th>{_t("portal_prov.col_pct_aplicado", "% Aplicado")}</th>'
                    f'<th>{_t("portal_prov.col_rebate", "Rebate")}</th>'
                    f'</tr>{filas_liq}</table>' if liquidaciones
                    else f'<p>{_t("portal_prov.sin_liquidaciones", "Sin liquidaciones todavía.")}</p>')
        secciones.append(f"""<div class="card"><h2>{_e(nombre_empresa)}</h2>
{_barra_rappel_proveedor_html(prog)}
<h3 style="color:var(--ac);font-size:14px;margin-top:16px">{_t("portal_prov.liquidaciones_abonadas_h3", "Liquidaciones ya abonadas")}</h3>
{tabla_liq}</div>""")
    contenido = "".join(secciones) or (
        f'<div class=\'card\'><p>{_t("portal_prov.sin_tramos_configurados", "Ninguna empresa te ha configurado tramos de rappel todavía.")}</p></div>')
    return _layout(_t("portal_prov.nav_rappels", "Rappels"), f"""
<div class="card"><h1>{_t("portal_prov.rappels_acumulados_h1", "Rappels acumulados")}</h1>
<p>{_t("portal_prov.rappels_desc",
      'Solo lectura: los tramos de rebate los configura cada empresa compradora sobre tu gasto '
      'acumulado con ella. Esto es distinto de los "Precios por volumen" que gestionas en tu '
      "Catálogo (descuento por cantidad en cada pedido) — aquí ves un rebate periódico sobre el "
      "conjunto de pedidos ya facturados.")}</p>
</div>
{contenido}""", nav=_nav_html(token, "rappels", no_leidos=no_leidos), token=token)


# ── Consignación (Fase C — Stock en Consignación) ────────────────────────────
# Ledger real (`b2b_consignacion_saldo`/`_movimientos`, `services.compras.b2b_pedidos`), NO el escrow
# B2B (`b2b_escrow.py` nunca interviene en un pedido de consignación). Solo lectura desde el lado
# Proveedor — la mercancía sigue siendo suya hasta que la Empresa la consume (evento
# `lotes.consumir_fefo` → auto-factura idempotente); aquí solo ve el progreso, igual que en Rappels.
def _barra_consignacion_html(saldo):
    depositada = int(saldo["cantidad_depositada"])
    consumida = int(saldo["cantidad_consumida"])
    devuelta = int(saldo["cantidad_devuelta"])
    disponible = depositada - consumida - devuelta
    pct_consumida = min(round(consumida / depositada * 100, 1), 100) if depositada else 0.0
    return f"""<div class="progreso"><div class="progreso-barra"
style="width:{pct_consumida}%;background:var(--ac)"></div></div>
<p>Depositado: <b>{depositada}</b> · Consumido (liquidado/facturado): <b>{consumida}</b> ·
Devuelto: <b>{devuelta}</b> · <span class="ok">Disponible: <b>{disponible}</b></span></p>"""


def pagina_consignacion_proveedor(token, bloques, *, mensaje=None, error=None, no_leidos=0):
    """`bloques`: [(nombre_empresa, [saldo_dict, ...])] — un saldo por (pedido de depósito, artículo)."""
    pedido_lbl = _t("portal_prov.pedido_badge", "Pedido {id}…")
    secciones = []
    for nombre_empresa, saldos in bloques:
        filas_saldo = "".join(f"""<div class="card" style="margin-top:10px">
<h3 style="color:#E6EDF3;font-size:14px;margin:0 0 6px">{_e(s['codigo_articulo'])}
<span class="badge">{pedido_lbl.format(id=_e(s['id_tx'][:8]))}</span></h3>
{_barra_consignacion_html(s)}
<p style="color:#8B949E;font-size:12px">{_t("portal_prov.precio_congelado_lbl", "Precio congelado al depósito: {p} €/ud", p=s['precio_unitario'])}</p>
</div>""" for s in saldos)
        secciones.append(f"""<div class="card"><h2>{_e(nombre_empresa)}</h2>
{filas_saldo or f'<p>{_t("portal_prov.sin_depositos", "Sin depósitos de consignación todavía.")}</p>'}</div>""")
    contenido = "".join(secciones) or (
        f'<div class=\'card\'><p>{_t("portal_prov.sin_pedido_consignacion", "Ninguna empresa te ha hecho un pedido en consignación todavía.")}</p></div>')
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (
        f'<p class="error">{_e(error)}</p>' if error else "")
    opciones_unidad = "".join(f'<option value="{k}">{v}</option>' for k, v in _ETIQUETA_UNIDAD.items())
    base = f"/portal/proveedor/{token}"
    return _layout(_t("portal_prov.nav_consignacion", "Consignación"), f"""
<div class="card"><h1>{_t("portal_prov.stock_consignacion_h1", "Stock en consignación")}</h1>
<p>{_t("portal_prov.consignacion_desc",
      'Solo lectura: mercancía que has depositado en la empresa compradora y que sigue siendo '
      'tuya hasta que se vende/consume — el "Consumido" de cada línea es lo que YA se ha '
      'liquidado y facturado automáticamente; "Disponible" es lo que aún no se ha tocado y '
      'podrías retirar.')}</p>
</div>
<div class="card"><h2>{_t("portal_prov.subir_consignacion_h2", "Subir artículo en consignación")}</h2>
<p style="color:#8B949E;font-size:13px">{_t("portal_prov.subir_consignacion_desc",
      "Se publica en tu catálogo B2B marcado como disponible para consignación — visible en el "
      "Catálogo B2B de las empresas de tu mismo sector, y en su pestaña Consignación en cuanto "
      "tramiten un pedido de depósito.")}</p>
{aviso}
<form method="post" action="{base}/consignacion/nuevo">
<label>{_t("portal_prov.nombre_articulo_lbl", "Nombre del artículo *")}</label><input name="nombre" required>
<label>{_t("portal_prov.codigo_articulo_lbl", "Código de artículo *")}</label><input name="codigo" required>
<label>{_t("portal_prov.es_perecedero_lbl", "¿Es perecedero? *")}</label>
<select name="es_perecedero" id="csel_perecedero" required>
<option value="0">{_t("portal_prov.no_perecedero", "No perecedero")}</option>
<option value="1">{_t("portal_prov.perecedero_badge", "Perecedero")}</option>
</select>
<div id="ccampos_perecedero" style="display:none">
<label>{_t("portal_prov.lote_lbl", "Lote *")}</label><input name="lote" id="cin_lote">
<label>{_t("portal_prov.fecha_caducidad_lbl", "Fecha de caducidad / consumo preferente *")}</label><input name="fecha_caducidad" id="cin_caducidad"
type="text" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
</div>
<label>{_t("portal_prov.comision_proveedor_lbl", "Comisión del proveedor por unidad vendida (€) *")}</label>
<input name="comision_unitaria" type="number" step="0.01" min="0" required>
<label>{_t("portal_prov.moq_lbl", "Cantidad Mínima de Pedido (MOQ) *")}</label><input name="moq" type="number" min="1" value="1" required>
<label>{_t("portal_prov.descripcion_lbl", "Descripción")}</label><textarea name="descripcion" rows="2"></textarea>
<label>{_t("portal_prov.unidad_mayorista_lbl", "Unidad de Medida Mayorista *")}</label><select name="unidad_medida" required>{opciones_unidad}</select>
<button type="submit">{_t("portal_prov.publicar_consignacion_btn", "Publicar en consignación")}</button>
</form>
<script>
(function(){{
 var sel = document.getElementById('csel_perecedero');
 var campos = document.getElementById('ccampos_perecedero');
 var inLote = document.getElementById('cin_lote');
 var inCad = document.getElementById('cin_caducidad');
 function sync(){{
   var per = sel.value === '1';
   campos.style.display = per ? 'block' : 'none';
   if (inLote) inLote.required = per;
   if (inCad) inCad.required = per;
 }}
 sel.addEventListener('change', sync);
 sync();
}})();
</script>
</div>
{contenido}""", nav=_nav_html(token, "consignacion", no_leidos=no_leidos), token=token)


# ── Licitaciones (RFQ) — puja a ciegas ────────────────────────────────────────
# Motor en `src.services.compras.b2b_rfq`. Esta vista SOLO usa `rfq_abiertas`/`mi_oferta`/
# `responder_rfq` — nunca `ofertas_de_rfq` (esa es exclusiva del lado Empresa) — así que es
# estructuralmente imposible que esta página muestre el precio de otro proveedor.
def pagina_licitaciones_proveedor(token, bloques, *, mensaje=None, error=None, no_leidos=0):
    """`bloques`: [(rfq_dict, mi_oferta_dict_o_None)]."""
    base = f"/portal/proveedor/{token}/licitaciones"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (
        f'<p class="error">{_e(error)}</p>' if error else "")

    secciones = []
    for rfq, propia in bloques:
        titulo = rfq.get("codigo_articulo") or rfq.get("categoria") or "—"
        estado_propia = (f"""<p class="ok">{_t("portal_prov.tu_puja_actual", "Tu puja actual:")} <b>{propia['precio_unitario']} €</b>
({_t("portal_prov.enviada_lbl", "enviada {f}", f=_e(propia['fecha_oferta']))}) — {_t("portal_prov.puedes_actualizar", "puedes actualizarla enviando el formulario de nuevo.")}</p>"""
                         if propia else f'<p>{_t("portal_prov.aun_no_pujado", "Aún no has pujado en esta licitación.")}</p>')
        secciones.append(f"""<div class="card"><h2>{_e(titulo)}</h2>
<p>{_t("portal_prov.cantidad_solicitada_lbl", "Cantidad solicitada:")} <b>{rfq['cantidad']} {_e(rfq['unidad_medida'])}</b> · {_t("portal_prov.entrega_deseada_lbl", "Entrega deseada:")}
{_e(rfq.get('fecha_limite_entrega') or 's/f')} · {_t("portal_prov.cierre_subasta_lbl", "Cierre de la subasta:")}
<b>{_e(rfq['fecha_cierre_subasta'])}</b></p>
{estado_propia}
<form method="post" action="{base}/{rfq['id_rfq']}/pujar">
<label>{_t("portal_prov.tu_precio_unitario_lbl", "Tu precio unitario (€) *")}</label>
<input type="number" step="0.0001" min="0.0001" name="precio_unitario"
value="{propia['precio_unitario'] if propia else ''}" required>
<label>{_t("portal_prov.moq_oferta_lbl", "MOQ (cantidad mínima de tu oferta)")}</label>
<input type="number" step="0.001" min="0" name="moq" value="{propia.get('moq') if propia else ''}">
<label>{_t("portal_prov.plazo_entrega_lbl", "Plazo de entrega (días)")}</label>
<input type="number" min="0" name="plazo_entrega_dias"
value="{propia.get('plazo_entrega_dias') if propia else ''}">
<button type="submit">{_t("portal_prov.actualizar_puja_btn", "Actualizar mi puja") if propia else _t("portal_prov.enviar_puja_btn", "Enviar puja")}</button>
</form></div>""")
    contenido = "".join(secciones) or (
        f'<div class=\'card\'><p>{_t("portal_prov.sin_licitaciones", "No hay licitaciones abiertas en tu sector ahora mismo.")}</p></div>')
    return _layout(_t("portal_prov.nav_licitaciones", "Licitaciones"), f"""
<div class="card"><h1>{_t("portal_prov.licitaciones_abiertas_h1", "Licitaciones abiertas")}</h1>
<p>{_t("portal_prov.licitaciones_desc_a", "Puja")} <b>{_t("portal_prov.a_ciegas", "a ciegas")}</b>{_t("portal_prov.licitaciones_desc_b", ": nunca ves la oferta de otros proveedores, ni ellos la tuya. Solo puedes tener una puja viva por licitación — enviar el formulario de nuevo actualiza tu oferta anterior. Al cerrar la subasta, si tu oferta es la ganadora, se convierte automáticamente en un Pedido B2B.")}</p>
{aviso}
</div>
{contenido}""", nav=_nav_html(token, "licitaciones", no_leidos=no_leidos), token=token)


# ── Carritos abandonados (cierre de brecha — Smart Suppliers) ───────────────
# Solo lectura + una acción ("enviar oferta especial"): lista los carritos marcados abandonados
# (`services.compras.b2b_carrito_abandono`) que contienen artículos de ESTE proveedor. La "oferta
# especial" es honestamente un mensaje de chat del pedido (`b2b_chat.enviar_mensaje`) — el chat B2B
# está ligado a un `id_tx` (pedido), no a un carrito sin tramitar; si la empresa nunca ha tramitado un
# pedido con este proveedor todavía no existe ningún hilo al que enganchar el mensaje, y la ruta de
# envío lo informa como tal en vez de inventar un canal de mensajería paralelo.
_ETIQUETA_MSG_ABANDONO = {"oferta_enviada": "Oferta especial enviada por chat."}
_ETIQUETA_ERROR_ABANDONO = {
    "carrito_no_encontrado": "Ese carrito abandonado ya no existe o no es de un artículo tuyo.",
    "sin_pedido_previo_para_chatear": ("Esta empresa no tiene todavía ningún pedido contigo — el chat "
                                      "B2B va ligado a un pedido, así que no hay un hilo al que "
                                      "enviar el mensaje hasta que tramite su primer pedido."),
}


def pagina_carritos_abandonados(token, items, *, mensaje=None, error=None, no_leidos=0):
    base = f"/portal/proveedor/{token}/abandonados"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (
        f'<p class="error">{_e(error)}</p>' if error else "")
    ph_mensaje = _t("portal_prov.oferta_especial_ph",
                    "Oferta especial para completar el pedido (opcional — si lo dejas vacío se "
                    "envía un mensaje por defecto)")
    filas = "".join(f"""<div class="card" style="margin-top:10px">
<h3 style="color:#E6EDF3;font-size:14px;margin:0 0 6px">{_e(it.get('nombre_empresa') or it['id_empresa'])}</h3>
<p>{_t("portal_prov.carrito_resumen", "{n} artículo(s) · {t} € · sin actividad desde {f}", n=it['n_lineas'], t=it['total'], f=_e(it['ultima_actividad']))}</p>
<form method="post" action="{base}/{_e(it['token_sesion'])}/oferta">
<textarea name="mensaje" rows="2" placeholder="{ph_mensaje}"></textarea>
<button type="submit">{_t("portal_prov.enviar_oferta_especial_btn", "Enviar oferta especial")}</button>
</form></div>""" for it in items)
    contenido = filas or f'<p>{_t("portal_prov.sin_carritos_abandonados", "No tienes carritos abandonados con artículos tuyos ahora mismo.")}</p>'
    return _layout(_t("portal_prov.nav_abandonados", "Carritos abandonados"), f"""
<div class="card"><h1>{_t("portal_prov.carritos_abandonados_h1", "Carritos abandonados")}</h1>
<p>{_t("portal_prov.carritos_abandonados_desc",
      "Empresas que añadieron artículos tuyos al carrito pero no tramitaron el pedido en más de 2 "
      "horas. Puedes enviarles una oferta especial como mensaje de chat del pedido — si todavía "
      "no has recibido ningún pedido de esa empresa, aún no existe un hilo al que enganchar el "
      "mensaje (te lo avisamos tal cual, en vez de inventar un canal nuevo).")}</p>
{aviso}
{contenido}
</div>""", nav=_nav_html(token, "abandonados", no_leidos=no_leidos), token=token)


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_proveedor", __name__, url_prefix="/portal/proveedor")
    registrar_selector_idioma(bp, "")

    def _suministrador_o_error(token):
        from src.services.compras import suministradores as S
        sup = S.resolver_sesion(token)
        if not sup:
            return None, (_pagina_error(_t("portal_prov.sesion_no_valida_titulo", "Sesión no válida"),
                          _t("portal_prov.enlace_caducado",
                             "Tu enlace de acceso ha caducado o no es válido.")), 401)
        return sup, None

    @bp.get("/onboarding/<token>")
    def onboarding(token):
        from src.services.compras import invitaciones, sectores
        if not invitaciones.resolver_token(token):
            return _pagina_error("Invitación no válida", "Este enlace de invitación no existe."), 404
        return pagina_onboarding(token, sectores=sectores.listar())

    @bp.post("/onboarding/<token>")
    def onboarding_post(token):
        from src.services.compras import sectores, suministradores as S
        d = request.form
        r = S.completar_onboarding(
            token, razon_social=d.get("razon_social", ""), cif=d.get("cif", ""),
            sector_id=d.get("sector_id") or None, contacto=d.get("contacto") or None,
            telefono=d.get("telefono") or None, email_login=d.get("email_login") or None,
            password=d.get("password") or None, confirmar_password=d.get("confirmar_password") or None)
        if not r.get("ok"):
            if r.get("error") == "ya_registrado":
                # El enlace de invitación es permanente y reutilizable: si ya llevó a un alta
                # completada, no se reintenta crear un proveedor duplicado — se manda al login con
                # el mismo token, mostrando un aviso informativo (nunca un error genérico aquí).
                return redirect(f"/portal/proveedor/acceso/{token}?info=ya_registrado")
            return pagina_onboarding(token, sectores=sectores.listar(), error=r.get("error")), 400
        sesion = S.crear_sesion(r["id_suministrador"])
        return pagina_onboarding_completado(f"/portal/proveedor/{sesion}/dashboard")

    _MSG_YA_REGISTRADO = "Ya te has registrado con esa invitación: inicia sesión."

    @bp.get("/acceso")
    @bp.get("/acceso/<token>")
    def acceso(token=None):
        info = _MSG_YA_REGISTRADO if request.args.get("info") == "ya_registrado" else None
        return pagina_acceso(token=token, info=info)

    @bp.post("/acceso")
    @bp.post("/acceso/<token>")
    def acceso_post(token=None):
        from src.services.compras import suministradores as S
        d = request.form
        r = S.verificar_login(d.get("email", ""), d.get("password", ""))
        if not r.get("ok"):
            # Mensaje genérico: no revela si falló el email o la contraseña (misma postura
            # anti-enumeración que ya tenía el antiguo flujo de enlace mágico).
            return pagina_acceso(token=token,
                                 error=_t("portal_prov.email_password_incorrectos",
                                         "Email o contraseña incorrectos.")), 401
        sesion = S.crear_sesion(r["id_suministrador"])
        return redirect(f"/portal/proveedor/{sesion}/dashboard")

    @bp.post("/<token>/logout")
    def logout(token):
        """Cierre EXPLÍCITO de sesión (botón "Cerrar sesión"): invalida el token actual. Solo borra
        la fila de sesión — no dispara ningún envío de email (el reenvío automático de un enlace de
        reentrada se retiró junto con el login sin contraseña)."""
        from src.services.compras import suministradores as S
        S.cerrar_sesion(token)
        return pagina_sesion_cerrada()

    def _no_leidos(sup):
        try:
            from src.services.compras import b2b_chat as CHAT
            return CHAT.no_leidos_totales_proveedor(sup["id"])
        except Exception:
            return 0

    @bp.get("/<token>/dashboard")
    def dashboard(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        return pagina_dashboard(token, sup, metricas=C.metricas_de_suministrador(sup["id"]),
                               no_leidos=_no_leidos(sup))

    @bp.get("/<token>/catalogo")
    def catalogo(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]), no_leidos=_no_leidos(sup))

    @bp.post("/<token>/catalogo/nuevo")
    def catalogo_nuevo(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        d = request.form
        # Talla/Marca/Color obligatorios (petición explícita): son los 3 parámetros estructurados
        # (junto al Nombre) que `db.articulos.detectar_posible_duplicado` usa para la detección
        # preventiva de duplicados antes de confirmar un pedido — un proveedor que los deja en
        # blanco degrada esa detección para TODAS las empresas que le compran, no solo para sí
        # mismo, así que se exigen aquí en el origen en vez de confiar en que el campo llegue
        # relleno. Cada sector usa el campo con su propio significado (p. ej. "calibre"/"variedad"
        # para un proveedor agrícola), nunca literalmente "talla de ropa".
        talla = (d.get("talla") or "").strip()
        marca = (d.get("marca") or "").strip()
        color = (d.get("color") or "").strip()
        if not (talla and marca and color):
            arts = C.listar_por_suministrador(sup["id"])
            return pagina_catalogo(
                token, arts,
                error=_t("portal_prov.talla_marca_color_obligatorios",
                         "Talla, Marca y Color (o sus equivalentes de tu sector) son obligatorios "
                         "para poder detectar duplicados con otros proveedores."),
                no_leidos=_no_leidos(sup)), 400
        r = C.crear_articulo(
            sup["id"], d.get("codigo", ""), d.get("nombre", ""),
            unidad_medida=d.get("unidad_medida", ""), moq=d.get("moq", 1),
            precio_unitario=d.get("precio_unitario", 0), descripcion=d.get("descripcion") or None,
            sector_id=sup.get("sector_id"), es_perecedero=d.get("es_perecedero") == "1",
            lote=d.get("lote"), fecha_caducidad=d.get("fecha_caducidad"),
            disponible_consignacion=d.get("disponible_consignacion") == "1",
            comision_unitaria=d.get("comision_unitaria") or None,
            talla=talla, marca=marca, color=color, exigir_atributos=True)
        arts = C.listar_por_suministrador(sup["id"])
        if not r.get("ok"):
            return pagina_catalogo(token, arts, error=r.get("error"), no_leidos=_no_leidos(sup)), 400
        return redirect(f"/portal/proveedor/{token}/catalogo")

    @bp.get("/<token>/catalogo/<int:id_articulo>/escalones")
    def escalones(token, id_articulo):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        articulo = next((a for a in C.listar_por_suministrador(sup["id"], solo_activos=False)
                        if a["id"] == id_articulo), None)
        if not articulo:
            return _pagina_error(_t("portal_prov.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_prov.articulo_no_tuyo", "Ese artículo no existe o no es tuyo.")), 404
        return pagina_escalones(token, articulo, C.escalones_de(id_articulo), no_leidos=_no_leidos(sup))

    @bp.post("/<token>/catalogo/<int:id_articulo>/escalones")
    def escalones_guardar(token, id_articulo):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        articulo = next((a for a in C.listar_por_suministrador(sup["id"], solo_activos=False)
                        if a["id"] == id_articulo), None)
        if not articulo:
            return _pagina_error(_t("portal_prov.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_prov.articulo_no_tuyo", "Ese artículo no existe o no es tuyo.")), 404
        desdes = request.form.getlist("cantidad_desde")
        precios = request.form.getlist("precio_unitario")
        escalones_form = [{"cantidad_desde": d, "precio_unitario": p}
                          for d, p in zip(desdes, precios) if str(d).strip() and str(p).strip()]
        r = C.guardar_escalones(sup["id"], id_articulo, escalones_form)
        if not r.get("ok"):
            return pagina_escalones(token, articulo, C.escalones_de(id_articulo),
                                    mensaje=_t("portal_prov.error_generico", "Error: {e}", e=r.get('error')),
                                    no_leidos=_no_leidos(sup)), 400
        return pagina_escalones(token, articulo, C.escalones_de(id_articulo),
                                mensaje=_t("portal_prov.precios_vol_guardados", "Precios por volumen guardados."),
                                no_leidos=_no_leidos(sup))

    @bp.get("/<token>/catalogo/<int:id_articulo>/bundles")
    def bundles(token, id_articulo):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C, b2b_bundles as BUN
        articulo = next((a for a in C.listar_por_suministrador(sup["id"], solo_activos=False)
                        if a["id"] == id_articulo), None)
        if not articulo:
            return _pagina_error(_t("portal_prov.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_prov.articulo_no_tuyo", "Ese artículo no existe o no es tuyo.")), 404
        reglas = [r for r in BUN.listar_reglas(sup["id"])
                 if r["codigo_disparador"] == articulo["codigo"]]
        otros = [a for a in C.listar_por_suministrador(sup["id"]) if a["codigo"] != articulo["codigo"]]
        return pagina_bundles(token, articulo, reglas, otros, no_leidos=_no_leidos(sup))

    @bp.post("/<token>/catalogo/<int:id_articulo>/bundles")
    def bundles_crear(token, id_articulo):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C, b2b_bundles as BUN
        articulo = next((a for a in C.listar_por_suministrador(sup["id"], solo_activos=False)
                        if a["id"] == id_articulo), None)
        if not articulo:
            return _pagina_error(_t("portal_prov.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_prov.articulo_no_tuyo", "Ese artículo no existe o no es tuyo.")), 404
        d = request.form
        r = BUN.crear_regla_bundle(
            sup["id"], d.get("nombre", ""), codigo_disparador=articulo["codigo"],
            cantidad_minima=d.get("cantidad_minima", 1), codigo_recompensa=d.get("codigo_recompensa", ""),
            forma_recompensa=d.get("forma_recompensa", "pct_descuento"),
            pct_descuento=d.get("pct_descuento") or None, precio_pack_fijo=d.get("precio_pack_fijo") or None,
            fecha_inicio=d.get("fecha_inicio"), fecha_fin=d.get("fecha_fin"))
        reglas = [x for x in BUN.listar_reglas(sup["id"]) if x["codigo_disparador"] == articulo["codigo"]]
        otros = [a for a in C.listar_por_suministrador(sup["id"]) if a["codigo"] != articulo["codigo"]]
        if not r.get("ok"):
            return pagina_bundles(token, articulo, reglas, otros,
                                  mensaje=_t("portal_prov.error_generico", "Error: {e}", e=r.get('error')),
                                  no_leidos=_no_leidos(sup)), 400
        return pagina_bundles(token, articulo, reglas, otros,
                              mensaje=_t("portal_prov.pack_creado", "Pack creado."),
                              no_leidos=_no_leidos(sup))

    @bp.post("/<token>/catalogo/<int:id_articulo>/bundles/<int:id_regla>/desactivar")
    def bundles_desactivar(token, id_articulo, id_regla):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C, b2b_bundles as BUN
        articulo = next((a for a in C.listar_por_suministrador(sup["id"], solo_activos=False)
                        if a["id"] == id_articulo), None)
        if not articulo:
            return _pagina_error(_t("portal_prov.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_prov.articulo_no_tuyo", "Ese artículo no existe o no es tuyo.")), 404
        BUN.desactivar_regla(sup["id"], id_regla)
        reglas = [x for x in BUN.listar_reglas(sup["id"]) if x["codigo_disparador"] == articulo["codigo"]]
        otros = [a for a in C.listar_por_suministrador(sup["id"]) if a["codigo"] != articulo["codigo"]]
        return pagina_bundles(token, articulo, reglas, otros,
                              mensaje=_t("portal_prov.pack_desactivado", "Pack desactivado."),
                              no_leidos=_no_leidos(sup))

    @bp.get("/<token>/pedidos")
    def pedidos(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_pedidos as PED
        return pagina_mis_pedidos(token, PED.listar_para_suministrador(sup["id"]),
                                  no_leidos=_no_leidos(sup))

    @bp.get("/<token>/pedido/<id_tx>")
    def pedido_detalle(token, id_tx):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_pedidos as PED, b2b_chat as CHAT
        tx = PED.obtener_para_proveedor(id_tx, sup["id"])
        if not tx:
            return _pagina_error("Pedido no encontrado", "Ese pedido no existe o no es tuyo."), 404
        CHAT.marcar_leido(id_tx, "proveedor")
        from src.db.documentos import obtener_por_referencia
        doc = obtener_por_referencia(f"B2B_TX:{id_tx}", id_empresa=tx["id_empresa"])
        return pagina_pedido_detalle(token, tx, tx["lineas"], CHAT.listar_mensajes(id_tx),
                                     no_leidos=_no_leidos(sup), tiene_albaran=bool(doc))

    @bp.get("/<token>/pedido/<id_tx>/albaran")
    def pedido_albaran(token, id_tx):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        import os
        from flask import send_file
        from src.services.compras import b2b_pedidos as PED
        from src.db.documentos import obtener_por_referencia
        tx = PED.obtener_para_proveedor(id_tx, sup["id"])
        if not tx:
            return _pagina_error("Pedido no encontrado", "Ese pedido no existe o no es tuyo."), 404
        doc = obtener_por_referencia(f"B2B_TX:{id_tx}", id_empresa=tx["id_empresa"])
        if not doc or not doc.get("ruta") or not os.path.exists(doc["ruta"]):
            return _pagina_error("Albarán no encontrado",
                                "Ese albarán no existe o no pertenece a este pedido."), 404
        return send_file(doc["ruta"])

    @bp.post("/<token>/pedido/<id_tx>/mensaje")
    def pedido_mensaje(token, id_tx):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_pedidos as PED, b2b_chat as CHAT
        tx = PED.obtener_para_proveedor(id_tx, sup["id"])
        if not tx:
            return _pagina_error("Pedido no encontrado", "Ese pedido no existe o no es tuyo."), 404
        CHAT.enviar_mensaje(id_tx, "proveedor", sup.get("contacto") or sup.get("razon_social"),
                           request.form.get("cuerpo", ""))
        return redirect(f"/portal/proveedor/{token}/pedido/{id_tx}")

    @bp.post("/<token>/catalogo/importar")
    def catalogo_importar(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        f = request.files.get("archivo")
        if not f or not f.filename:
            return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]),
                                   no_leidos=_no_leidos(sup)), 400
        try:
            import pandas as pd
            df = pd.read_csv(f) if f.filename.lower().endswith(".csv") else pd.read_excel(f)
            filas = df.fillna("").to_dict(orient="records")
        except Exception as e:
            logger.warning("catalogo_importar parseo(%s): %s", f.filename, e)
            return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]),
                                   mensaje=None, no_leidos=_no_leidos(sup)), 400
        resultado = C.importar_lote(sup["id"], filas, archivo_nombre=f.filename)
        return pagina_catalogo(token, C.listar_por_suministrador(sup["id"]), resultado_import=resultado,
                               no_leidos=_no_leidos(sup))

    def _nombre_empresa(id_empresa):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT nombre_empresa FROM empresas WHERE id_empresa=%s", (id_empresa,))
                row = cur.fetchone()
                if not row:
                    return id_empresa
                return (row[0] if not isinstance(row, dict) else row["nombre_empresa"]) or id_empresa
        except Exception:
            return id_empresa

    @bp.get("/<token>/rappels")
    def rappels(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rappels as RAP
        tramos = RAP.listar_tramos(id_suministrador=sup["id"])
        por_empresa = {}
        for t in tramos:
            por_empresa.setdefault(t["id_empresa"], []).append(t)
        bloques = []
        for id_empresa, ts in por_empresa.items():
            prog = RAP.progreso_suministrador(id_empresa, sup["id"], tramos=ts)
            liqs = RAP.listar_liquidaciones(id_empresa=id_empresa, id_suministrador=sup["id"], limite=20)
            bloques.append((_nombre_empresa(id_empresa), prog, liqs))
        return pagina_rappels_proveedor(token, bloques, no_leidos=_no_leidos(sup))

    @bp.get("/<token>/consignacion")
    def consignacion(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_consignacion_saldo WHERE id_suministrador=%s "
                       "ORDER BY id_empresa, actualizado DESC", (sup["id"],))
            saldos = [r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
                     for r in cur.fetchall()]
        por_empresa = {}
        for s in saldos:
            por_empresa.setdefault(s["id_empresa"], []).append(s)
        bloques = [(_nombre_empresa(id_empresa), ss) for id_empresa, ss in por_empresa.items()]
        return pagina_consignacion_proveedor(token, bloques, no_leidos=_no_leidos(sup))

    @bp.post("/<token>/consignacion/nuevo")
    def consignacion_nuevo(token):
        """Publica un artículo en el catálogo del proveedor ya marcado como disponible para
        consignación — mismo motor que `catalogo_nuevo` (`b2b_catalogo.crear_articulo`), sin
        duplicar lógica; esta pestaña solo simplifica el formulario a los campos relevantes para
        consignación y fuerza `disponible_consignacion=1` (es el propósito de este formulario, no
        hace falta que el proveedor lo marque aparte)."""
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as C
        d = request.form
        r = C.crear_articulo(
            sup["id"], d.get("codigo", ""), d.get("nombre", ""),
            unidad_medida=d.get("unidad_medida", ""), moq=d.get("moq", 1),
            descripcion=d.get("descripcion") or None, sector_id=sup.get("sector_id"),
            es_perecedero=d.get("es_perecedero") == "1", lote=d.get("lote"),
            fecha_caducidad=d.get("fecha_caducidad"), disponible_consignacion=True,
            comision_unitaria=d.get("comision_unitaria") or None)
        if not r.get("ok"):
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM b2b_consignacion_saldo WHERE id_suministrador=%s "
                           "ORDER BY id_empresa, actualizado DESC", (sup["id"],))
                saldos = [row if isinstance(row, dict) else dict(zip([col[0] for col in cur.description], row))
                         for row in cur.fetchall()]
            por_empresa = {}
            for s in saldos:
                por_empresa.setdefault(s["id_empresa"], []).append(s)
            bloques = [(_nombre_empresa(id_empresa), ss) for id_empresa, ss in por_empresa.items()]
            return pagina_consignacion_proveedor(token, bloques, error=r.get("error"),
                                                 no_leidos=_no_leidos(sup)), 400
        return redirect(f"/portal/proveedor/{token}/consignacion")

    def _bloques_rma(sup):
        from src.services.compras import b2b_disputas as DISP
        from src.db.documentos import listar_documentos
        rmas = DISP.listar_rma_pendientes_proveedor(sup["id"])
        por_empresa = {}
        for d in rmas:
            try:
                from src.db import compras as C
                d["lineas"] = (C.obtener_devolucion(d["id_devolucion"],
                                                     id_empresa=d["id_empresa"]) or {}).get("lineas", [])
            except Exception:
                d["lineas"] = []
            try:
                ref = f"DEVOLUCION:{d['id_devolucion']}"
                # `listar_documentos(referencia=...)` hace LIKE (no exacto) — filtra en Python para
                # no confundir, p. ej., el RMA #5 con el #15/#25 por coincidencia de substring.
                d["fotos"] = [doc for doc in listar_documentos(
                    tipo="devolucion", id_empresa=d["id_empresa"], referencia=ref)
                    if doc.get("referencia") == ref]
            except Exception:
                d["fotos"] = []
            por_empresa.setdefault(d["id_empresa"], []).append(d)
        return [(_nombre_empresa(id_empresa), items) for id_empresa, items in por_empresa.items()]

    @bp.get("/<token>/rma")
    def rma_pendientes(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        msg_code, err_code = request.args.get("mensaje"), request.args.get("error")
        return pagina_rma_proveedor(token, _bloques_rma(sup), mensaje=msg_code, error=err_code,
                                    no_leidos=_no_leidos(sup))

    @bp.get("/<token>/rma/<int:id_devolucion>/foto/<id_documento>")
    def rma_foto(token, id_devolucion, id_documento):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        import os

        from flask import send_file

        from src.db.documentos import obtener_documento
        from src.services.compras import b2b_disputas as DISP
        if not DISP.rma_pertenece_a_suministrador(id_devolucion, sup["id"]):
            return {"error": "No encontrado"}, 404
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("tipo_documento") != "devolucion"
                or doc.get("referencia") != f"DEVOLUCION:{id_devolucion}"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)

    @bp.post("/<token>/rma/<int:id_devolucion>/aprobar")
    def rma_aprobar(token, id_devolucion):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_disputas as DISP
        r = DISP.aprobar_devolucion_autoservicio(id_devolucion, id_suministrador=sup["id"],
                                                 usuario=sup.get("razon_social") or sup.get("email"))
        if not r.get("ok"):
            return redirect(f"/portal/proveedor/{token}/rma?error={r.get('error')}")
        aviso = "aprobado_conciliacion_manual" if r.get("conciliacion_manual") else "aprobado"
        return redirect(f"/portal/proveedor/{token}/rma?mensaje={aviso}")

    @bp.post("/<token>/rma/<int:id_devolucion>/rechazar")
    def rma_rechazar(token, id_devolucion):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_disputas as DISP
        motivo = (request.form.get("motivo") or "").strip()
        r = DISP.rechazar_devolucion_autoservicio(
            id_devolucion, motivo, id_suministrador=sup["id"],
            usuario=sup.get("razon_social") or sup.get("email"))
        if not r.get("ok"):
            return redirect(f"/portal/proveedor/{token}/rma?error={r.get('error')}")
        return redirect(f"/portal/proveedor/{token}/rma?mensaje=rechazado")

    @bp.get("/<token>/abandonados")
    def abandonados(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito_abandono as ABANDONO
        items = ABANDONO.listar_para_proveedor(sup["id"])
        for it in items:
            it["nombre_empresa"] = _nombre_empresa(it["id_empresa"])
        msg_code, err_code = request.args.get("mensaje"), request.args.get("error")
        mensaje = _ETIQUETA_MSG_ABANDONO.get(msg_code, msg_code) if msg_code else None
        error = _ETIQUETA_ERROR_ABANDONO.get(err_code, err_code) if err_code else None
        return pagina_carritos_abandonados(token, items, mensaje=mensaje, error=error,
                                          no_leidos=_no_leidos(sup))

    @bp.post("/<token>/abandonados/<token_carrito>/oferta")
    def abandonados_oferta(token, token_carrito):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito_abandono as ABANDONO, b2b_chat as CHAT
        abandono = ABANDONO.obtener(token_carrito)
        if not abandono or abandono.get("id_suministrador") != sup["id"]:
            return redirect(f"/portal/proveedor/{token}/abandonados?error=carrito_no_encontrado")
        # El chat B2B (`b2b_chat.enviar_mensaje`) va ligado a un `id_tx` (pedido), no a un carrito sin
        # tramitar — se usa el pedido B2B MÁS RECIENTE entre esta empresa y este proveedor como hilo
        # para la oferta. Si nunca ha habido uno, se informa honestamente en vez de inventar un canal.
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_tx FROM transaccion_comercial WHERE id_empresa=%s "
                       "AND id_suministrador=%s AND origen='b2b' ORDER BY creada DESC LIMIT 1",
                       (abandono["id_empresa"], sup["id"]))
            row = cur.fetchone()
        if not row:
            return redirect(f"/portal/proveedor/{token}/abandonados?error=sin_pedido_previo_para_chatear")
        id_tx = row[0] if not isinstance(row, dict) else list(row.values())[0]
        cuerpo = (request.form.get("mensaje") or "").strip() or (
            "Hemos visto que tienes artículos pendientes en tu carrito — ¿te interesa una oferta "
            "especial para completarlo?")
        CHAT.enviar_mensaje(id_tx, "proveedor", sup.get("contacto") or sup.get("razon_social"), cuerpo)
        return redirect(f"/portal/proveedor/{token}/abandonados?mensaje=oferta_enviada")

    @bp.get("/<token>/licitaciones")
    def licitaciones(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rfq as RFQ
        abiertas = RFQ.rfq_abiertas(sup.get("sector_id"))
        bloques = [(rfq, RFQ.mi_oferta(rfq["id_rfq"], sup["id"])) for rfq in abiertas]
        return pagina_licitaciones_proveedor(token, bloques, mensaje=request.args.get("mensaje"),
                                             error=request.args.get("error"), no_leidos=_no_leidos(sup))

    @bp.post("/<token>/licitaciones/<id_rfq>/pujar")
    def licitaciones_pujar(token, id_rfq):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rfq as RFQ
        d = request.form
        r = RFQ.responder_rfq(id_rfq, sup["id"], d.get("precio_unitario") or 0,
                              moq=d.get("moq") or None, plazo_entrega_dias=d.get("plazo_entrega_dias") or None)
        if r.get("ok"):
            return redirect(f"/portal/proveedor/{token}/licitaciones?mensaje=Puja+enviada")
        return redirect(f"/portal/proveedor/{token}/licitaciones?error={r.get('error') or 'error_desconocido'}")

    return bp
