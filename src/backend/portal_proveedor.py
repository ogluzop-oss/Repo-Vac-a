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
from src.backend.portal_i18n import (FLAG_ICONS_LINK, idioma_actual, layout_publico,
                                     marcar_origen_web, registrar_selector_idioma,
                                     selector_idioma_html, t as _t, url_sitio_oficial,
                                     viene_de_web_oficial)
from src.backend.portal_theming import PALETA_PROVEEDOR as _PALETA_PROV

logger = logging.getLogger("backend.portal_proveedor")

_ETIQUETA_UNIDAD = {"kg": "Kilos", "unidad": "Unidades", "pale": "Palés", "caja": "Cajas"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _nav_html(token, activo, *, no_leidos=0):
    """Nav del panel (Panel/Catálogo/Pedidos/…), construida sin estado global — cada página pasa
    su propio `token` de sesión y cuál de los enlaces está activo. Devuelve SOLO los enlaces de
    navegación — "Cerrar sesión"/"Volver a la web oficial"/selector de idioma los añade `_layout`
    (grupo inferior único, también presente en páginas SIN sesión — ver su docstring)."""
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
              ("rma", f"{base}/rma", _t("portal_prov.nav_rma", "RMA pendientes")),
              ("plan", f"{base}/plan", _t("portal_prov.nav_plan", "Plan")))
    return "".join(f'<a href="{href}"{" class=\"on\"" if activo == key else ""}>{label}</a>'
                   for key, href, label in enlaces)


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
    (eso es cosa de la propia empresa, en el Portal Empleado o el Portal Empresa B2B). Usa la
    paleta FIJA propia de este portal (`portal_theming.PALETA_PROVEEDOR` — petición explícita,
    2026-11-21: cada portal con su propio color de acento, distinto de la web oficial y del Portal
    Empresa B2B), nunca la compartida/personalizable por empresa.

    "Cerrar sesión"/"Volver a la web oficial"/selector de idioma (petición explícita, 2026-11-16;
    reubicados a esquinas fijas 2026-11-22 — ver `portal_theming.CSS_TOPNAV_SHELL`, antes le
    quitaban sitio a las pestañas de la topbar y las empujaba a una segunda línea): "Cerrar sesión"
    (si hay `token`) a la esquina inferior DERECHA, "Volver a la web oficial" (SOLO si
    `portal_i18n.viene_de_web_oficial`) a la esquina inferior IZQUIERDA — visibles en TODAS las
    pestañas por ser `position:fixed`. El selector de idioma se queda en la topbar."""
    from src.backend import portal_theming as _tema
    base = f"/portal/proveedor/{token}" if token else None
    logout_fixed = (f'<div class="sm-corner-logout"><form method="post" action="{base}/logout">'
                    f'<button type="submit" class="nav-logout">'
                    f'{_t("portal_prov.cerrar_sesion", "Cerrar sesión")}</button></form></div>'
                   if token else "")
    volver_fixed = (
        f'<div class="sm-corner-volver"><a href="{_e(url_sitio_oficial())}" class="nav-volver-web">'
        f'{_t("portal_prov.volver_web_oficial", "← Volver a la web")}</a></div>'
        if viene_de_web_oficial() else "")
    idioma_html = selector_idioma_html(accion="/portal/proveedor/idioma") if token else ""
    grupo_wrap = f'<div class="toplinks-grupo">{idioma_html}</div>' if idioma_html else ""
    script = f"<script>{_CSEL_JS}</script><script>{_CFILE_JS}</script><script>{_CDATE_JS}</script>"
    return f"""<!doctype html><html lang="{_e(idioma_actual())}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Portal de Proveedores</title>
{FLAG_ICONS_LINK}
<style>
:root{_tema.bloque_css_variables_fijo(_tema.PALETA_PROVEEDOR)}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:var(--bg);color:var(--text)}}
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
{_tema.CSS_POLISH}
{_tema.CSS_SHELL_PRO}
{_tema.CSS_TOPNAV_SHELL}
</style></head><body>
<header class="sm-topbar"><div class="wrap">
<a class="brand" href="{base + '/dashboard' if base else '/portal/proveedor/'}">{_t("portal_prov.titulo_marca", "Portal de Proveedores")}</a>
<nav class="toplinks">{nav}</nav>
{grupo_wrap}
</div></header>
<main class="sm-contenido">{contenido}</main>
{logout_fixed}
{volver_fixed}
{script}
</body></html>"""


def _mensaje_error_catalogo(error):
    """Traduce códigos de error de `b2b_catalogo.crear_articulo` a texto legible — en particular
    `proveedor_sin_stripe_verificado` (petición explícita, 2026-11-15: sin Stripe Connect
    verificado no se puede publicar catálogo), que sin esto se mostraría como el código en crudo."""
    if error == "proveedor_sin_stripe_verificado":
        return _t("portal_prov.sin_stripe_verificado",
                  "Antes de publicar catálogo, tienes que vincular y verificar tu cuenta de "
                  "Stripe para poder cobrar tus pedidos — hazlo desde tu Panel.")
    return error


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


# Nombre de marca del portal — PLANO, sin pasar por `_t()` (mismo criterio que `sitio_oficial.py`,
# que tampoco traduce "Smart Manager": `_frase()` normaliza TODO texto traducido a frase
# — primera letra mayúscula, resto minúscula, salvo SIGLAS de `utils.texto.SIGLAS` — y un nombre
# propio de marca no es un texto "traducible" al uso, es un literal que debe conservar su
# capitalización exacta siempre, igual que ya ocurre en la web oficial).
_MARCA_PORTAL = "Portal de Proveedores"


# ── Página de inicio (home) ──────────────────────────────────────────────────
def pagina_home_proveedor():
    """Página de inicio PÚBLICA del Portal Proveedor (petición explícita, 2026-11-21): antes, el
    enlace "Proveedores" de la web oficial llevaba DIRECTAMENTE al formulario de registro — sin
    ninguna presentación ni la opción de iniciar sesión primero. Mismo lenguaje visual que la web
    oficial (`layout_publico`): titular + CTA de "Iniciar sesión"/"Registrarme", franja de
    confianza y tarjetas de beneficios con animación de entrada al hacer scroll.

    "Smart Manager"/"B2B" se pasan como PARÁMETROS de formato (`{marca}`/`{b2b}`), nunca
    incrustados en el texto por defecto: `_frase()` (ver `utils.i18n`) normaliza a frase CUALQUIER
    texto que pase por `_t()`, excepto el contenido de los marcadores `{...}` — sin esto, el titular
    se mostraba con la marca en minúsculas ("smart manager")."""
    tarjetas = [
        ("🛒", _t("portal_prov.home_card1_t", "Vende a toda la plataforma"),
         _t("portal_prov.home_card1_d",
            "Publica tu catálogo mayorista y llega a todas las empresas clientes de {marca} "
            "sin coste de entrada.", marca="Smart Manager")),
        ("💳", _t("portal_prov.home_card2_t", "0% de comisión, siempre"),
         _t("portal_prov.home_card2_d",
            "Cobra directamente a través de tu propia cuenta de {stripe}, sin ninguna comisión de "
            "plataforma — tengas o no una suscripción activa a {marca}.",
            stripe="Stripe", marca="Smart Manager")),
        ("📦", _t("portal_prov.home_card3_t", "Pedidos, rappels y RMA en un solo sitio"),
         _t("portal_prov.home_card3_d",
            "Gestiona pedidos, precios por volumen, packs, consignación y devoluciones desde un "
            "panel pensado para proveedores {b2b}.", b2b="B2B")),
    ]
    tarjetas_html = "".join(
        f'<div class="card reveal" style="transition-delay:{i * 70}ms"><h3>{ico} {_e(tit)}</h3><p>{_e(desc)}</p></div>'
        for i, (ico, tit, desc) in enumerate(tarjetas)
    )
    cuerpo = f"""
<div class="wrap hero-glow">
  <h1>{_t("portal_prov.home_h1_1", "El portal {b2b} para", b2b="B2B")}<br>
  <span>{_t("portal_prov.home_h1_2", "proveedores de {marca}", marca="Smart Manager")}</span></h1>
  <p class="sub">{_t("portal_prov.home_sub",
      "Publica tu catálogo, recibe pedidos y cobra sin intermediarios — conectado en tiempo real "
      "con todas las empresas que usan {marca}.", marca="Smart Manager")}</p>
  <div class="trust-strip">
    <span>🔒 {_t("portal_prov.home_trust1", "Cobros vía")} <b>Stripe</b></span>
    <span>📦 <b>{_t("portal_prov.home_trust2", "Sin permanencia")}</b></span>
    <span>🌍 {_t("portal_prov.home_trust3", "Disponible en varios idiomas")}</span>
  </div>
  <div class="grid3">{tarjetas_html}</div>
</div>"""
    return layout_publico(_MARCA_PORTAL, cuerpo, marca=_MARCA_PORTAL, icono="📦",
                          url_home="/portal/proveedor/", paleta=_PALETA_PROV)


def pagina_registro_publico(*, sectores, error=None):
    """Alta PÚBLICA sin invitación (petición explícita, 2026-11-16): mismo formulario que
    `pagina_onboarding`, pero sin token — coexiste con el alta por invitación, que sigue intacta
    para cuando una empresa concreta invita a un proveedor ya conocido. Petición explícita,
    2026-11-21: layout PÚBLICO (`layout_publico`, mismo lenguaje visual que la web oficial) en vez
    del shell de sidebar interno — esta página se ve ANTES de tener sesión, igual que `/registro`
    de `sitio_oficial.py`."""
    opciones = "".join(f'<option value="{s["id"]}">{_e(s["nombre"])}</option>' for s in sectores)
    aviso = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2>{_t("portal_prov.registro_h1", "Date de alta como proveedor")}</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
  {_t("portal_prov.registro_desc",
      "Regístrate libremente, sin necesidad de invitación, para ofrecer tu catálogo a las empresas "
      "de la plataforma. El sector es obligatorio: determina qué empresas podrán ver tus ofertas.")}</p>
  <form class="panel" method="post" action="/portal/proveedor/registro">
    {aviso}
    <label>{_t("portal_prov.razon_social_lbl", "Razón social *")}</label><input name="razon_social" required>
    <label>{_t("portal_prov.cif_lbl", "CIF *")}</label><input name="cif" required>
    <label>{_t("portal_prov.sector_lbl", "Sector comercial *")}</label><select name="sector_id" required>
    <option value="">{_t("portal_prov.selecciona_sector_ph", "Selecciona un sector…")}</option>{opciones}</select>
    <label>{_t("portal_prov.contacto_lbl", "Persona de contacto")}</label><input name="contacto">
    <label>{_t("portal_prov.telefono_lbl", "Teléfono")}</label><input name="telefono">
    <label>{_t("portal_prov.email_acceso_lbl", "Email de acceso *")}</label><input name="email_login" type="email" required>
    <label>{_t("portal_prov.password_lbl", "Contraseña *")}</label><input name="password" type="password" minlength="8" required>
    <label>{_t("portal_prov.confirmar_password_lbl", "Confirmar contraseña *")}</label><input name="confirmar_password" type="password" minlength="8" required>
    <button type="submit">{_t("portal_prov.registrarme_btn", "Registrarme")}</button>
  </form>
  <p class="vinculo-sec">{_t("portal_prov.ya_tienes_cuenta", "¿Ya tienes cuenta?")}
  <a href="/portal/proveedor/acceso">{_t("portal_prov.inicia_sesion", "Inicia sesión")}</a>.</p>
</div>"""
    return layout_publico(_t("portal_prov.registro_titulo", "Registro de proveedor"), cuerpo,
                          marca=_MARCA_PORTAL, icono="📦",
                          url_home="/portal/proveedor/", paleta=_PALETA_PROV)


def pagina_verificar_email_proveedor(*, email, error=None):
    """Paso OBLIGATORIO antes de completar el alta pública (petición explícita, 2026-11-22): se
    envía un código de 6 dígitos al email introducido y hay que confirmarlo aquí. Los datos ya
    validados (y la contraseña YA hasheada, nunca en claro) viajan en la cookie de sesión firmada
    de Flask (`session["pendiente_prov_registro"]`) hasta que se confirme."""
    aviso = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2>{_t("portal_prov.verifica_tu_email_h1", "Verifica tu email")}</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
  {_t("portal_prov.verifica_tu_email_desc", "Te hemos enviado un código de 6 dígitos a {email}. Introdúcelo para completar tu registro.", email=f"<b>{_e(email)}</b>")}</p>
  <form class="panel" method="post" action="/portal/proveedor/registro/verificar-email">
    {aviso}
    <label>{_t("portal_prov.codigo_verificacion_lbl", "Código de verificación")}</label>
    <input name="codigo" required maxlength="6" minlength="6" inputmode="numeric" pattern="[0-9]{{6}}"
      autocomplete="one-time-code" placeholder="123456" autofocus>
    <button type="submit">{_t("portal_prov.verificar_y_continuar_btn", "Verificar y continuar")}</button>
  </form>
  <form method="post" action="/portal/proveedor/registro/reenviar-codigo" style="text-align:center;margin-top:14px">
    <button type="submit" class="btn btn-ghost" style="padding:8px 18px;font-size:13px">{_t("portal_prov.reenviar_codigo_btn", "Reenviar código")}</button>
  </form>
</div>"""
    return layout_publico(_t("portal_prov.verifica_tu_email_titulo", "Verifica tu email"), cuerpo,
                          marca=_MARCA_PORTAL, icono="📦",
                          url_home="/portal/proveedor/", paleta=_PALETA_PROV)


# ── Elección de pasarela de cobro — paso OBLIGATORIO del propio registro ───────────────────────
# (petición explícita, 2026-11-23: antes esta elección quedaba como un aviso dentro del panel,
# alcanzable después de registrarse — ahora es el último paso del alta, antes de poder entrar al
# panel de verdad. PayPal pasa a ser pago DIRECTO sin custodia de Smart Manager (petición explícita,
# 2026-11-27, ver `suministradores.fijar_paypal_credenciales`/el docstring de `tpv.pagos.
# paypal_connect`): el proveedor da su propia app de PayPal (Client ID + Secret, gratis e inmediata
# en developer.paypal.com) para que el cobro se haga directamente en SU cuenta — nunca en la de
# Smart Manager.
def pagina_elegir_pasarela(token):
    cuerpo = f"""
<div class="wrap">
  <h2>{_t("portal_prov.elige_pasarela_h1", "¿Cómo quieres cobrar tus ventas?")}</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
  {_t("portal_prov.elige_pasarela_desc", "Elige una de las dos — es un paso obligatorio antes de poder publicar tu catálogo o recibir pedidos.")}</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;max-width:640px;margin:0 auto">
    <div class="card">
      <h3>Stripe</h3>
      <p>{_t("portal_prov.opcion_stripe_desc", "Cobra directamente en tu cuenta bancaria, con la verificación de identidad de Stripe.")}</p>
      <p><a class="enlace" href="/portal/proveedor/{_e(token)}/stripe/conectar" style="font-weight:900">{_t("portal_prov.elegir_stripe_btn", "Elegir {marca} →", marca="Stripe")}</a></p>
    </div>
    <div class="card">
      <h3>PayPal</h3>
      <p>{_t("portal_prov.opcion_paypal_desc", "Cobra directo en tu propia cuenta de {m} — necesitas el Client ID y Secret de tu propia app de {m} (gratis, la creas tú mismo en developer.paypal.com).", m="PayPal")}</p>
      <p><a class="enlace" href="/portal/proveedor/{_e(token)}/paypal/credenciales" style="font-weight:900">{_t("portal_prov.elegir_paypal_btn", "Elegir {marca} →", marca="PayPal")}</a></p>
    </div>
  </div>
</div>"""
    return _layout(_t("portal_prov.elige_pasarela_titulo", "Elige cómo cobrar"), cuerpo, token=token)


def pagina_paypal_credenciales(token, *, error=None):
    aviso = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2>{_t("portal_prov.paypal_cred_h1", "Tu propia app de {m}", m="PayPal")}</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
  {_t("portal_prov.paypal_cred_desc",
     "Para que el pago llegue directo a tu cuenta (nunca a través de {sm}), necesitamos "
     "el Client ID y Secret de tu propia app de {pp}. La creas gratis e inmediatamente en "
     "developer.paypal.com → Apps & Credentials → Create App, con tu cuenta {pp} Business. "
     "Guardamos tu Secret cifrado, nunca en texto plano.", sm="Smart Manager", pp="PayPal")}</p>
  <form class="panel" method="post" action="/portal/proveedor/{_e(token)}/paypal/credenciales">
    {aviso}
    <label>{_t("portal_prov.paypal_client_id_lbl", "Client {m}", m="ID")}</label>
    <input type="text" name="client_id" required autofocus>
    <label>{_t("portal_prov.paypal_client_secret_lbl", "Secret")}</label>
    <input type="password" name="client_secret" required>
    <button type="submit">{_t("portal_prov.continuar_btn", "Continuar →")}</button>
  </form>
</div>"""
    return _layout(_t("portal_prov.paypal_cred_titulo", "Tu propia app de {m}", m="PayPal"), cuerpo, token=token)


# ── Acceso (login email + contraseña) ─────────────────────────────────────────
def pagina_acceso(*, token=None, error=None, info=None):
    """Login real de email+contraseña (sustituye el antiguo "solo email, te mandamos un enlace").
    `token`: contexto opcional de una invitación — si está presente (visita desde el enlace de
    invitación o desde `/onboarding/<token>`), se muestra el enlace "¿Aún no te has registrado?"
    hacia el alta con ESE MISMO token (permanente, ver `invitaciones.resolver_token`); sin token
    (visita directa/bookmarked a `/acceso`) el formulario se muestra igual pero sin ese enlace, al no
    haber token del que partir hacia el alta. Petición explícita, 2026-11-21: layout PÚBLICO
    (`layout_publico`, mismo lenguaje visual que `/login` de la web oficial), con el texto
    clicable hacia el registro justo debajo del formulario."""
    aviso = f'<div class="msg-error">{_e(error)}</div>' if error else (
        f'<div class="msg-ok">{_e(info)}</div>' if info else "")
    action = f"/portal/proveedor/acceso/{_e(token)}" if token else "/portal/proveedor/acceso"
    enlace_alta = (f'<p class="vinculo-sec">{_t("portal_prov.aun_no_registrado", "¿Aún no te has registrado?")} '
                   f'<a href="/portal/proveedor/onboarding/{_e(token)}">{_t("portal_prov.completa_alta_aqui", "Completa tu alta aquí")}</a>.</p>'
                   if token else
                   f'<p class="vinculo-sec">{_t("portal_prov.aun_no_registrado", "¿Aún no te has registrado?")} '
                   f'<a href="/portal/proveedor/registro">{_t("portal_prov.registrate_aqui", "Regístrate aquí")}</a>.</p>')
    cuerpo = f"""
<div class="wrap">
  <h2>{_t("portal_prov.acceder_panel_h1", "Acceder a tu panel")}</h2>
  <form class="panel" method="post" action="{action}">
    {aviso}
    <label>{_t("portal_prov.email_acceso_lbl2", "Email de acceso")}</label><input name="email" type="email" required>
    <label>{_t("portal_prov.password_lbl2", "Contraseña")}</label><input name="password" type="password" required>
    <button type="submit">{_t("portal_prov.entrar_btn", "Entrar")}</button>
  </form>
  {enlace_alta}
</div>"""
    return layout_publico(_t("portal_prov.acceso_proveedor_titulo", "Acceso proveedor"), cuerpo,
                          marca=_MARCA_PORTAL, icono="📦",
                          url_home="/portal/proveedor/", paleta=_PALETA_PROV)


def pagina_sesion_cerrada():
    return _layout(_t("portal_prov.sesion_cerrada_titulo", "Sesión cerrada"), f"""
<div class="card"><h1 class="ok">✓ {_t("portal_prov.sesion_cerrada_h1", "Sesión cerrada")}</h1>
<p>{_t("portal_prov.sesion_cerrada_desc", "Has cerrado tu sesión correctamente.")}</p>
<p><a class="enlace" href="/portal/proveedor/acceso">{_t("portal_prov.volver_iniciar_sesion", "Volver a iniciar sesión")}</a></p>
</div>""")


# ── Panel del proveedor ───────────────────────────────────────────────────────
def _banner_limite_portal_html(token, id_suministrador):
    """Aviso preventivo de límite Freemium (petición explícita, 2026-11-27 — ver
    `services/portal_plan.py`): discreto, solo cuando de verdad se acerca/alcanza el límite — con
    ERP o Plan de Pago del Portal esta función ni siquiera consulta nada."""
    from src.services import portal_plan as PP
    catalogo = PP.limite("proveedor", "catalogo_items", "proveedor", id_suministrador)
    if catalogo["tier"] != "freemium":
        return ""
    if not catalogo["ok"]:
        texto = _t("portal_prov.limite_catalogo_agotado_aviso",
                   "Has agotado tus {n} referencias activas del plan Freemium.", n=catalogo["limite"])
    elif catalogo["aviso"]:
        texto = _t("portal_prov.limite_catalogo_cerca_aviso",
                   "Vas por {u} de {n} referencias activas en tu plan Freemium.",
                   u=catalogo["usado"], n=catalogo["limite"])
    else:
        return ""
    return (
        f'<div class="card" style="border:2px solid var(--ac);background:color-mix(in srgb, var(--ac) 10%, var(--bg2))">'
        f'<p style="font-weight:700;margin:0 0 8px 0">⏳ {_e(texto)}</p>'
        f'<p style="margin:0"><a class="enlace" href="/portal/proveedor/{_e(token)}/plan" '
        f'style="font-weight:900">{_t("portal_prov.mejorar_plan_cta", "Mejorar plan →")}</a></p>'
        f'</div>')


def pagina_plan(token, suministrador, *, mensaje=None, error=None, no_leidos=0):
    """Plan Freemium / de Pago del Portal (petición explícita, 2026-11-27 — ver
    `services/portal_plan.py`). Precio SIEMPRE calculado por `portal_plan.precio_mensual_portal`/
    `precio_anual_portal`, nunca un número fijo en la plantilla."""
    from src.services import portal_plan as PP
    id_sup = suministrador.get("id")
    tier = PP.tier_efectivo("proveedor", id_sup)
    base = f"/portal/proveedor/{token}/plan"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (
        f'<p class="error">{_e(error)}</p>' if error else "")
    if tier == "erp":
        cuerpo_tier = (
            f'<div class="card"><h2>★ {_t("portal_prov.plan_ya_erp_h2", "Ya tienes acceso completo")}</h2>'
            f'<p>{_t("portal_prov.plan_ya_erp_desc", "Tu empresa tiene una suscripción activa a Smart Manager ERP: acceso completo al portal, sin límites ni coste adicional.")}</p></div>')
    elif tier == "pago":
        cuerpo_tier = (
            f'<div class="card"><h2>★ {_t("portal_prov.plan_ya_pago_h2", "Plan de Pago del Portal activo")}</h2>'
            f'<p>{_t("portal_prov.plan_ya_pago_desc", "Tienes acceso sin límites al Portal Proveedor. ¿Quieres todavía más? Smart Manager ERP añade TPV, stock, RRHH, facturación y mucho más.")}</p></div>')
    else:
        catalogo = PP.limite("proveedor", "catalogo_items", "proveedor", id_sup)
        cuerpo_tier = (
            f'<div class="card"><h2>{_t("portal_prov.plan_freemium_h2", "Tu plan actual: Freemium")}</h2>'
            f'<p>{_t("portal_prov.plan_freemium_catalogo", "Referencias activas en catálogo:")} '
            f'<b>{catalogo["usado"]}/{catalogo["limite"]}</b></p></div>')
    mensual, anual, cuota = PP.precio_mensual_portal(), PP.precio_anual_portal(), PP.cuota_4_pagos()

    def _par_botones(action, etiqueta, extra_inputs=""):
        return f"""<div style="margin-bottom:10px">
<p style="margin:0 0 6px;font-weight:700">{etiqueta}</p>
<form method="post" action="{action}" style="display:inline-block;margin-right:8px">
{extra_inputs}<input type="hidden" name="metodo_pago" value="stripe">
<button type="submit">{_t("portal_prov.pagar_con_stripe_btn", "Pagar con {m}", m="Stripe")}</button></form>
<form method="post" action="{action}" style="display:inline-block">
{extra_inputs}<input type="hidden" name="metodo_pago" value="paypal">
<button type="submit">{_t("portal_prov.pagar_con_paypal_btn", "Pagar con {m}", m="PayPal")}</button></form>
</div>"""

    oferta_html = "" if tier != "freemium" else f"""
<div class="card">
<h2>{_t("portal_prov.plan_pago_h2", "Plan de Pago del Portal")}</h2>
<p>{_t("portal_prov.plan_pago_desc", "Sin límite de referencias en catálogo, más importación masiva.")}</p>
{_par_botones(f"{base}/checkout", _t("portal_prov.plan_mensual_btn", "{p} €/mes", p=mensual),
             '<input type="hidden" name="ciclo" value="mensual">')}
{_par_botones(f"{base}/checkout", _t("portal_prov.plan_anual_btn", "{p} €/año (ahorra 16,7%)", p=anual),
             '<input type="hidden" name="ciclo" value="anual">')}
{_par_botones(f"{base}/checkout-financiado",
             _t("portal_prov.plan_financiado_btn", "4 cuotas de {c} €/trimestre", c=cuota))}
</div>"""
    return _layout(_t("portal_prov.nav_plan", "Plan"), f"""
{aviso}
{cuerpo_tier}
{oferta_html}
""", nav=_nav_html(token, "plan", no_leidos=no_leidos), token=token)


def pagina_dashboard(token, suministrador, *, metricas=None, no_leidos=0, stripe=None, paypal=None,
                     pasarela_cobro=None, mostrar_aviso_verificado=False):
    estado = suministrador.get("estado_kyb", "pendiente")
    stripe = stripe or {}
    paypal = paypal or {}
    # Requisito OBLIGATORIO (petición explícita, 2026-11-15, reforzado en visibilidad el
    # 2026-11-16): sin NINGUNA cuenta de cobro verificada (Stripe o PayPal, petición explícita
    # 2026-11-22) no se puede publicar catálogo ni recibir pedidos (ver `b2b_catalogo.
    # crear_articulo`/`b2b_pedidos.tramitar`). Mientras no haya ninguna, se muestra como un BANNER
    # de alerta a todo ancho con AMBAS opciones ("elige una, nunca las dos a la vez" — ver
    # `suministradores.iniciar_onboarding_stripe`/`fijar_paypal_credenciales`); en cuanto se elige
    # una, esta tarjeta deja de mencionar la otra (`pasarela_cobro` ya fijado). Ahora es el propio
    # registro el que obliga a elegir (petición explícita, 2026-11-23, ver `/elegir-pasarela`) —
    # este banner solo se ve si el proveedor abandonó ese paso antes de terminarlo.
    #
    # Una vez verificado, el aviso "Cobros ✓" es TEMPORAL (petición explícita, 2026-11-22): se
    # muestra UNA sola vez — `mostrar_aviso_verificado` lo decide el llamador (ruta `dashboard`,
    # ver `suministradores.aviso_stripe_ya_mostrado`/`marcar_aviso_stripe_mostrado`, y sus gemelas
    # `aviso_paypal_*`) — y nunca más después, para no dejar un recordatorio permanente de algo que
    # ya no hace falta recordar.
    if pasarela_cobro == "paypal":
        if paypal.get("verificada"):
            tarjeta_stripe = (
                f'<div class="card"><h2>{_t("portal_prov.cobros_h2", "Cobros")}</h2>'
                f'<p class="ok">✓ {_t("portal_prov.paypal_verificada", "Tu cuenta de {marca} está verificada — ya puedes recibir pagos de pedidos B2B.", marca="PayPal")}</p></div>'
                if mostrar_aviso_verificado else "")
        else:
            cuerpo_banner = (
                f'<p>{_t("portal_prov.paypal_pendiente", "Todavía te falta un paso para verificar tu cobro por {marca}.", marca="PayPal")}</p>'
                f'<p><a class="enlace" href="/portal/proveedor/{_e(token)}/elegir-pasarela" style="color:var(--err);font-weight:900">{_t("portal_prov.paypal_completar", "Completar verificación de {marca} →", marca="PayPal")}</a></p>')
            tarjeta_stripe = (
                f'<div class="card" style="border:2px solid var(--err);background:color-mix(in srgb, var(--err) 10%, var(--bg2))">'
                f'<h2 style="color:var(--err);font-size:20px">⚠ {_t("portal_prov.requisito_obligatorio_paypal_h2", "REQUISITO OBLIGATORIO: verifica tu cuenta de PayPal")}</h2>'
                f'<p style="font-weight:700">{_t("portal_prov.requisito_obligatorio_desc", "Sin esto, NO podrás publicar ningún artículo en tu catálogo ni recibir ningún pedido B2B.")}</p>'
                f'{cuerpo_banner}</div>')
    elif pasarela_cobro == "stripe":
        if stripe.get("verificada"):
            tarjeta_stripe = (
                f'<div class="card"><h2>{_t("portal_prov.cobros_h2", "Cobros")}</h2>'
                f'<p class="ok">✓ {_t("portal_prov.stripe_verificada", "Tu cuenta de {marca} está verificada — ya puedes recibir pagos de pedidos B2B.", marca="Stripe")}</p></div>'
                if mostrar_aviso_verificado else "")
        else:
            if stripe.get("conectada"):
                cuerpo_banner = (
                    f'<p>{_t("portal_prov.stripe_pendiente", "Tu cuenta de {marca} está creada pero aún no está verificada.", marca="Stripe")}</p>'
                    f'<p><a class="enlace" href="/portal/proveedor/{_e(token)}/stripe/conectar" style="color:var(--err);font-weight:900">{_t("portal_prov.stripe_completar", "Completar verificación de {marca} →", marca="Stripe")}</a></p>')
            else:
                cuerpo_banner = (
                    f'<p>{_t("portal_prov.stripe_sin_conectar", "Todavía no has vinculado tu cuenta bancaria para cobrar tus pedidos B2B.")}</p>'
                    f'<p><a class="enlace" href="/portal/proveedor/{_e(token)}/stripe/conectar" style="color:var(--err);font-weight:900">{_t("portal_prov.stripe_vincular", "Vincular cuenta de {marca} →", marca="Stripe")}</a></p>')
            tarjeta_stripe = (
                f'<div class="card" style="border:2px solid var(--err);background:color-mix(in srgb, var(--err) 10%, var(--bg2))">'
                f'<h2 style="color:var(--err);font-size:20px">⚠ {_t("portal_prov.requisito_obligatorio_h2", "REQUISITO OBLIGATORIO: vincula y verifica tu cuenta de Stripe")}</h2>'
                f'<p style="font-weight:700">{_t("portal_prov.requisito_obligatorio_desc", "Sin esto, NO podrás publicar ningún artículo en tu catálogo ni recibir ningún pedido B2B.")}</p>'
                f'{cuerpo_banner}</div>')
    else:
        # Ninguna pasarela elegida todavía — se ofrecen las DOS, nunca se puede empezar las dos a
        # la vez (lo impone `suministradores.iniciar_onboarding_stripe`/`_paypal`).
        tarjeta_stripe = (
            f'<div class="card" style="border:2px solid var(--err);background:color-mix(in srgb, var(--err) 10%, var(--bg2))">'
            f'<h2 style="color:var(--err);font-size:20px">⚠ {_t("portal_prov.requisito_obligatorio_elige_h2", "REQUISITO OBLIGATORIO: vincula y verifica una cuenta de cobro")}</h2>'
            f'<p style="font-weight:700">{_t("portal_prov.requisito_obligatorio_desc", "Sin esto, NO podrás publicar ningún artículo en tu catálogo ni recibir ningún pedido B2B.")}</p>'
            f'<p><a class="enlace" href="/portal/proveedor/{_e(token)}/elegir-pasarela" style="color:var(--err);font-weight:900">{_t("portal_prov.elegir_pasarela_btn", "Elegir cómo cobrar →")}</a></p>'
            f'</div>')
    panel_metricas = ""
    if metricas:
        filas_met = "".join(f"<tr><td>{_e(m['codigo'])}</td><td>{_e(m['nombre'])}</td>"
                            f"<td>{m['vistas']}</td><td>{m['clics']}</td></tr>" for m in metricas)
        panel_metricas = f"""<div class="card"><h2>{_t("portal_prov.visibilidad_catalogo", "Visibilidad de tu catálogo (últimos 30 días)")}</h2>
<table><tr><th>{_t("portal_prov.col_codigo", "Código")}</th><th>{_t("portal_prov.col_nombre", "Nombre")}</th><th>{_t("portal_prov.col_vistas", "Vistas")}</th><th>{_t("portal_prov.col_clics", "Clics")}</th></tr>{filas_met}</table>
</div>"""
    limite_aviso = _banner_limite_portal_html(token, suministrador.get("id"))
    return _layout(_t("portal_prov.nav_panel", "Panel"), f"""
{limite_aviso}
{tarjeta_stripe}
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
    # Columna "Comisión" retirada (petición explícita, 2026-11-27 — comisión de plataforma a 0%
    # siempre, ver `comisiones_b2b.PCT_SIN_SUSCRIPCION`): mostrar una columna que siempre da "-0 €"
    # no aporta nada y genera dudas; el proveedor ya ve el Total íntegro, que es lo que recibe.
    def _fila_pedido(p):
        return f"""<tr><td><code>{_e(p['id_tx'])}</code></td>
<td>{_e(_etiqueta_estado_t(p['estado']))}</td>
<td>{p['total']} €</td><td>{p['creada']}</td>
<td><a class="enlace" href="{base}/pedido/{p['id_tx']}">{ver_chat}</a></td></tr>"""
    filas = "".join(_fila_pedido(p) for p in pedidos)
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
    # Comisión de plataforma retirada por completo (petición explícita, 2026-11-27 — ver
    # `comisiones_b2b.PCT_SIN_SUSCRIPCION = 0.0`): el proveedor recibe siempre el Total íntegro,
    # sin ningún desglose de deducción que mostrar.
    desglose_html = (
        f'<p>{_t("portal_prov.base_lbl", "Base:")} {tx.get("total")} € · '
        f'{_t("portal_prov.recibiras_lbl", "Recibirás:")} <b>{tx.get("total")} €</b> '
        f'({_t("portal_prov.sin_comision_lbl", "sin comisión de plataforma")})</p>')
    return _layout(_t("portal_prov.pedido_titulo", "Pedido {ref}", ref=tx['id_tx'][:8]), f"""
<div class="card"><h1>{_t("portal_prov.pedido_h1", "Pedido")} <code>{_e(tx['id_tx'])}</code></h1>
<p>{_t("portal_prov.estado_lbl", "Estado:")} <span class="badge">{_e(_etiqueta_estado_t(tx['estado']))}</span> ·
{_t("portal_prov.total_lbl", "Total:")} <b>{tx['total']} €</b> · {_t("portal_prov.fecha_lbl", "Fecha:")} {tx['creada']}</p>
{desglose_html}
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
    from flask import Blueprint, redirect, request, session

    bp = Blueprint("portal_proveedor", __name__, url_prefix="/portal/proveedor")
    registrar_selector_idioma(bp, "")

    @bp.after_request
    def _tras_peticion(response):
        return marcar_origen_web(response)

    def _suministrador_o_error(token):
        from src.services.compras import suministradores as S
        sup = S.resolver_sesion(token)
        if not sup:
            return None, (_pagina_error(_t("portal_prov.sesion_no_valida_titulo", "Sesión no válida"),
                          _t("portal_prov.enlace_caducado",
                             "Tu enlace de acceso ha caducado o no es válido.")), 401)
        return sup, None

    # Página de inicio PÚBLICA (petición explícita, 2026-11-21): antes, visitar el portal llevaba
    # directo a `/registro` — ahora se ve primero esta página (mismo lenguaje visual que la web
    # oficial), con "Iniciar sesión"/"Registrarme" como las dos puertas de entrada reales.
    @bp.get("/")
    def home():
        return pagina_home_proveedor()

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
        # Requisito obligatorio como parte del propio alta (petición explícita, 2026-11-23): antes
        # de esto se aterrizaba directo en el panel y la elección de pasarela quedaba pendiente
        # como un aviso — ahora es el último paso, antes de poder entrar de verdad.
        return redirect(f"/portal/proveedor/{sesion}/elegir-pasarela")

    @bp.get("/registro")
    def registro_publico():
        from src.services.compras import sectores
        return pagina_registro_publico(sectores=sectores.listar())

    @bp.post("/registro")
    def registro_publico_post():
        """Verificación de email OBLIGATORIA (petición explícita, 2026-11-22): antes de crear
        nada, se valida la contraseña y se hashea YA (nunca se guarda en claro en la cookie de
        sesión) y se envía un código de 6 dígitos — los datos pendientes viajan en
        `session["pendiente_prov_registro"]` hasta confirmarse (ver `/registro/verificar-email`)."""
        from src.services.compras import sectores, suministradores as S
        d = request.form
        razon_social = (d.get("razon_social") or "").strip()
        cif = (d.get("cif") or "").strip()
        sector_id = d.get("sector_id") or None
        email_login = (d.get("email_login") or "").strip().lower()
        if not razon_social or not cif or not sector_id:
            return pagina_registro_publico(
                sectores=sectores.listar(), error="razon_social_cif_y_sector_son_obligatorios"), 400
        if not email_login or "@" not in email_login:
            return pagina_registro_publico(
                sectores=sectores.listar(), error="el_email_de_acceso_es_obligatorio"), 400
        r_pass = S.validar_password_proveedor(d.get("password", ""), d.get("confirmar_password", ""))
        if not r_pass.get("ok"):
            return pagina_registro_publico(sectores=sectores.listar(), error=r_pass.get("error")), 400

        from src.seguridad.passwords import hash_password
        from src.services import verificacion_email as VE
        r_envio = VE.generar_y_enviar(email_login)
        if not r_envio.get("ok"):
            return pagina_registro_publico(
                sectores=sectores.listar(),
                error=_t("portal_prov.error_envio_codigo", "No se pudo enviar el código de "
                                                           "verificación. Inténtalo de nuevo en "
                                                           "unos minutos.")), 502
        session["pendiente_prov_registro"] = {
            "razon_social": razon_social, "cif": cif, "sector_id": sector_id,
            "contacto": d.get("contacto") or None, "telefono": d.get("telefono") or None,
            "email_login": email_login, "password_hash": hash_password(d.get("password", "")),
        }
        return pagina_verificar_email_proveedor(email=email_login)

    @bp.post("/registro/verificar-email")
    def registro_verificar_email_post():
        from src.services.compras import suministradores as S
        pendiente = session.get("pendiente_prov_registro")
        if not pendiente:
            return redirect("/portal/proveedor/registro")
        from src.services import verificacion_email as VE
        codigo = (request.form.get("codigo") or "").strip()
        r = VE.verificar(pendiente["email_login"], codigo)
        if not r.get("ok"):
            mensajes = {
                "codigo_incorrecto": _t("portal_prov.codigo_incorrecto_err", "Código incorrecto. Revísalo e inténtalo de nuevo."),
                "codigo_caducado": _t("portal_prov.codigo_caducado_err", "El código ha caducado — pulsa \"Reenviar código\"."),
                "demasiados_intentos": _t("portal_prov.demasiados_intentos_err", "Demasiados intentos — pulsa \"Reenviar código\" para pedir uno nuevo."),
                "sin_codigo_pendiente": _t("portal_prov.sin_codigo_pendiente_err", "No hay ningún código pendiente — pulsa \"Reenviar código\"."),
            }
            return pagina_verificar_email_proveedor(
                email=pendiente["email_login"],
                error=mensajes.get(r.get("error"), "No se pudo verificar el código.")), 400

        r_reg = S.registrar_publico(
            razon_social=pendiente["razon_social"], cif=pendiente["cif"],
            sector_id=pendiente["sector_id"], contacto=pendiente.get("contacto"),
            telefono=pendiente.get("telefono"), email_login=pendiente["email_login"],
            password_hash=pendiente["password_hash"])
        session.pop("pendiente_prov_registro", None)
        if not r_reg.get("ok"):
            if r_reg.get("error") == "cif_ya_registrado":
                return redirect("/portal/proveedor/acceso?info=ya_registrado")
            from src.services.compras import sectores
            return pagina_registro_publico(sectores=sectores.listar(), error=r_reg.get("error")), 400
        sesion = S.crear_sesion(r_reg["id_suministrador"])
        # Requisito obligatorio como parte del propio alta (petición explícita, 2026-11-23): antes
        # de esto se aterrizaba directo en el panel y la elección de pasarela quedaba pendiente
        # como un aviso — ahora es el último paso, antes de poder entrar de verdad.
        return redirect(f"/portal/proveedor/{sesion}/elegir-pasarela")

    @bp.post("/registro/reenviar-codigo")
    def registro_reenviar_codigo_post():
        pendiente = session.get("pendiente_prov_registro")
        if not pendiente:
            return redirect("/portal/proveedor/registro")
        from src.services import verificacion_email as VE
        r = VE.generar_y_enviar(pendiente["email_login"])
        if not r.get("ok"):
            return pagina_verificar_email_proveedor(
                email=pendiente["email_login"],
                error=_t("portal_prov.error_reenvio_codigo", "No se pudo reenviar el código. "
                                                             "Inténtalo de nuevo en unos minutos.")), 502
        return pagina_verificar_email_proveedor(email=pendiente["email_login"])

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
        from src.services.compras import suministradores as S
        pasarela_cobro = sup.get("pasarela_cobro")
        stripe = S.estado_stripe(sup["id"]) if pasarela_cobro != "paypal" else {}
        # PayPal pago directo sin custodia (petición explícita, 2026-11-27): no hay un estado "en
        # vivo" que consultar — `paypal_verificado` se fija en el momento de verificar SUS propias
        # credenciales contra PayPal (`suministradores.fijar_paypal_credenciales`).
        paypal = ({"conectada": bool(sup.get("paypal_client_id")),
                  "verificada": bool(sup.get("paypal_verificado"))}
                 if pasarela_cobro == "paypal" else {})
        mostrar_aviso = False
        if pasarela_cobro == "paypal" and paypal.get("verificada") and not S.aviso_paypal_ya_mostrado(sup["id"]):
            mostrar_aviso = True
            S.marcar_aviso_paypal_mostrado(sup["id"])
        elif pasarela_cobro == "stripe" and stripe.get("verificada") and not S.aviso_stripe_ya_mostrado(sup["id"]):
            mostrar_aviso = True
            S.marcar_aviso_stripe_mostrado(sup["id"])
        return pagina_dashboard(token, sup, metricas=C.metricas_de_suministrador(sup["id"]),
                               no_leidos=_no_leidos(sup), stripe=stripe, paypal=paypal,
                               pasarela_cobro=pasarela_cobro, mostrar_aviso_verificado=mostrar_aviso)

    @bp.get("/<token>/plan")
    def plan(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        return pagina_plan(token, sup, no_leidos=_no_leidos(sup),
                           mensaje=request.args.get("mensaje"), error=request.args.get("error"))

    @bp.post("/<token>/plan/checkout")
    def plan_checkout(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        import os
        from src.services import portal_plan as PP
        ciclo = request.form.get("ciclo")
        metodo_pago = request.form.get("metodo_pago") or "stripe"
        base_web = os.getenv("SITIO_OFICIAL_URL", "http://localhost:8000").rstrip("/")
        success_url = f"{base_web}/portal/proveedor/{token}/plan/exito"
        cancel_url = f"{base_web}/portal/proveedor/{token}/plan"
        if metodo_pago == "paypal":
            r = PP.crear_checkout_session_paypal(
                "proveedor", sup["id"], ciclo=ciclo, email=sup.get("email_login") or "",
                success_url=success_url, cancel_url=cancel_url)
        else:
            r = PP.crear_checkout_session(
                "proveedor", sup["id"], ciclo=ciclo, email=sup.get("email_login") or "",
                success_url=success_url, cancel_url=cancel_url)
        if not r.get("ok"):
            from urllib.parse import quote
            return redirect(f"/portal/proveedor/{token}/plan?error={quote(r.get('error', ''))}")
        return redirect(r["url"], code=303)

    @bp.post("/<token>/plan/checkout-financiado")
    def plan_checkout_financiado(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        import os
        from src.services import portal_plan as PP
        metodo_pago = request.form.get("metodo_pago") or "stripe"
        base_web = os.getenv("SITIO_OFICIAL_URL", "http://localhost:8000").rstrip("/")
        success_url = f"{base_web}/portal/proveedor/{token}/plan/exito"
        cancel_url = f"{base_web}/portal/proveedor/{token}/plan"
        if metodo_pago == "paypal":
            r = PP.crear_checkout_session_financiada_paypal(
                "proveedor", sup["id"], email=sup.get("email_login") or "",
                success_url=success_url, cancel_url=cancel_url)
        else:
            r = PP.crear_checkout_session_financiada(
                "proveedor", sup["id"], email=sup.get("email_login") or "",
                success_url=success_url, cancel_url=cancel_url)
        if not r.get("ok"):
            from urllib.parse import quote
            return redirect(f"/portal/proveedor/{token}/plan?error={quote(r.get('error', ''))}")
        return redirect(r["url"], code=303)

    @bp.get("/<token>/plan/exito")
    def plan_exito(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services import portal_plan as PP
        from urllib.parse import quote
        subscription_id = request.args.get("subscription_id")
        if subscription_id:
            r = PP.confirmar_checkout_paypal(subscription_id)
        else:
            session_id = request.args.get("session_id")
            if not session_id:
                return redirect(f"/portal/proveedor/{token}/plan")
            r = PP.confirmar_checkout_generico(session_id)
        if not r.get("ok"):
            return redirect(f"/portal/proveedor/{token}/plan?error={quote(r.get('error', ''))}")
        return redirect(f"/portal/proveedor/{token}/plan?mensaje="
                        f"{quote('¡Plan de Pago del Portal activado! Ya no tienes ningún límite.')}")

    @bp.get("/<token>/stripe/conectar")
    def stripe_conectar(token):
        """Onboarding KYB de Stripe Connect (requisito previo a cobrar comisiones reales, ver
        `suministradores.iniciar_onboarding_stripe`): redirige al enlace hospedado por Stripe."""
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import suministradores as S
        r = S.iniciar_onboarding_stripe(sup["id"], token=token)
        if not r.get("ok"):
            mensaje = (_t("portal_prov.stripe_no_configurado",
                          "Los cobros con Stripe todavía no están activados en la plataforma. "
                          "Vuelve a intentarlo más tarde.")
                      if r.get("error") == "stripe_no_configurado" else
                      _t("portal_prov.stripe_error_generico",
                        "No se pudo iniciar la conexión con Stripe. Inténtalo de nuevo."))
            return _pagina_error(_t("portal_prov.stripe_error_titulo", "{marca} no disponible", marca="Stripe"),
                                 mensaje), 502
        return redirect(r["onboarding_url"])

    @bp.get("/<token>/elegir-pasarela")
    def elegir_pasarela(token):
        """Reentrada única e idempotente del paso obligatorio de elección de pasarela (petición
        explícita, 2026-11-23) — retoma exactamente donde se quedó el proveedor (nunca le hace
        repetir un paso ya completado), tanto si viene recién registrado como si vuelve más tarde
        desde el panel sin haber terminado."""
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        pasarela = sup.get("pasarela_cobro")
        if pasarela == "paypal":
            if not sup.get("paypal_client_id"):
                return redirect(f"/portal/proveedor/{token}/paypal/credenciales")
            return redirect(f"/portal/proveedor/{token}/dashboard")
        if pasarela == "stripe":
            return redirect(f"/portal/proveedor/{token}/dashboard")
        return pagina_elegir_pasarela(token)

    @bp.get("/<token>/paypal/credenciales")
    def paypal_credenciales_form(token):
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        return pagina_paypal_credenciales(token)

    @bp.post("/<token>/paypal/credenciales")
    def paypal_credenciales_post(token):
        """Pago directo sin custodia (petición explícita, 2026-11-27): el proveedor da SU PROPIA
        app de PayPal — se verifica de verdad contra la API de PayPal antes de guardar nada (ver
        `suministradores.fijar_paypal_credenciales`), nunca se finge un estado verificado."""
        sup, err = _suministrador_o_error(token)
        if err:
            return err
        from src.services.compras import suministradores as S
        r = S.fijar_paypal_credenciales(sup["id"], request.form.get("client_id", ""),
                                        request.form.get("client_secret", ""))
        if not r.get("ok"):
            mensajes = {
                "credenciales_incompletas": _t("portal_prov.paypal_cred_incompletas",
                                              "Introduce el Client {id} y el Secret.", id="ID"),
                "credenciales_rechazadas_por_paypal": _t(
                    "portal_prov.paypal_cred_rechazadas",
                    "{m} no reconoce estas credenciales — revisa que sean correctas.", m="PayPal"),
                "ya_tienes_stripe_como_pasarela_de_cobro": _t(
                    "portal_prov.ya_tienes_stripe", "Ya tienes {m} como pasarela de cobro — no "
                                                    "puedes tener las dos a la vez.", m="Stripe"),
            }
            return pagina_paypal_credenciales(
                token, error=mensajes.get(r.get("error"), "No se pudieron guardar las credenciales.")), 400
        return redirect(f"/portal/proveedor/{token}/dashboard")

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
        # Límite Freemium de referencias de catálogo (petición explícita, 2026-11-27 — ver
        # `services/portal_plan.py`): proveedores sin ERP ni Plan de Pago del Portal tienen un
        # tope de artículos activos en catálogo; con cualquiera de los dos, sin límite.
        from src.services import portal_plan as PPLAN
        info_limite = PPLAN.limite("proveedor", "catalogo_items", "proveedor", sup["id"])
        if not info_limite["ok"]:
            arts = C.listar_por_suministrador(sup["id"])
            return pagina_catalogo(
                token, arts, no_leidos=_no_leidos(sup),
                error=_t("portal_prov.limite_catalogo_error",
                        "Has alcanzado el límite de {n} referencias activas de tu plan Freemium. "
                        "Mejora al Plan de Pago del Portal o contrata Smart Manager ERP para añadir "
                        "sin límite.", n=info_limite["limite"])), 400
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
            return pagina_catalogo(token, arts, error=_mensaje_error_catalogo(r.get("error")),
                                   no_leidos=_no_leidos(sup)), 400
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
        # Importación masiva: función de automatización reservada a Plan de Pago del Portal/ERP
        # (petición explícita, 2026-11-27 — "restringe en Freemium... importación masiva...
        # mostrándolas como ganchos de conversión", ver `services/portal_plan.py`). A diferencia
        # del límite de referencias (que SÍ se aplica en Freemium), aquí el gate es binario: nada
        # de importar en lote sin Plan de Pago del Portal o ERP, sea cual sea el tamaño del lote.
        from src.services import portal_plan as PPLAN
        if PPLAN.tier_efectivo("proveedor", sup["id"]) == "freemium":
            return pagina_catalogo(
                token, C.listar_por_suministrador(sup["id"]), no_leidos=_no_leidos(sup),
                error=_t("portal_prov.importacion_masiva_bloqueada",
                        "La importación masiva de catálogo es una función del Plan de Pago del "
                        "Portal o de Smart Manager ERP. Añade tus artículos manualmente o mejora "
                        "tu plan.")), 400
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
            return pagina_consignacion_proveedor(token, bloques,
                                                 error=_mensaje_error_catalogo(r.get("error")),
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
