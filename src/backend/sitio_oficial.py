"""
Sitio oficial y comercial de Smart Manager — dominio raíz público (`smartmanager-app.com`,
`www.smartmanager-app.com`). Presenta el ERP cloud, los 3 planes de suscripción, el alta/pago y la
descarga de la app de escritorio una vez contratado un plan, además de las páginas legales públicas
exigidas por Google Cloud (Política de Privacidad / Condiciones del Servicio) para la verificación
OAuth de los scopes restringidos de Gmail/Calendar que usa la integración de Correo (`services.correo`)
y Eventos (`services.calendario`).

Arquitectura (sin motor nuevo, reutiliza lo ya construido):
- Catálogo de planes: `services.saas.planes.PLANES` (fuente ÚNICA, la misma que usa el enforcement).
- Alta de empresa + cuenta + código de activación: vive en la BD CENTRAL
  (`src.backend_central`, contenedor/proceso DISTINTO) — este blueprint corre en el contenedor
  `backend` (conectado a la BD local/multiempresa), así que cruza por HTTP interno a
  `backend_central:8091` (ver `_central`), nunca accede a esa BD directamente.
- Contraseñas de la cuenta web: PBKDF2 vía `werkzeug.security` (igual que el resto de Flask/
  `backend_central.rutas_sitio_web`), NUNCA el hash SHA-256 sin sal de `db/usuario.py` (ese es el
  sistema de login del ERP de escritorio, una identidad totalmente distinta).
- Pago recurrente: Stripe Checkout (tarjeta, `mode=subscription`) — NUEVO, es justo el flujo que
  `services.saas.billing.stripe_gateway` decía (en su propio docstring) que faltaba por no existir
  "un flujo web de alta". Requiere `STRIPE_SECRET_KEY` + `STRIPE_PRICE_ID_BASIC`/`_PLUS`/`_PRO` en el
  entorno de ESTE contenedor (los 3 planes son de pago); sin ellos, degrada con un aviso honesto
  (nunca finge un pago). El alta SIN pago (`/registro` cuando `precio==0`) queda lista por si algún
  plan vuelve a ser gratuito en el futuro, pero hoy no se usa.
- HTML generado con funciones puras (f-strings + `_e()` de escape), mismo patrón que
  `src.backend.storefront` — sin motor de plantillas nuevo.
"""

import logging
import os

logger = logging.getLogger("backend.sitio_oficial")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"

_CENTRAL_BASE = os.environ.get("CENTRAL_BASE_URL", "http://backend_central:8091")
_CENTRAL_TIMEOUT = 10


def _e(x):
    from markupsafe import escape
    return str(escape(x if x is not None else ""))


def _central(path, payload=None, method="POST", timeout=_CENTRAL_TIMEOUT):
    """Llamada interna a `backend_central` (red privada de Docker), protegida con el secreto
    compartido `CENTRAL_INTERNAL_SECRET`. Nunca propaga la excepción cruda: cualquier fallo de red
    se traduce en `{"ok": False, "error": ...}`, igual que un error de negocio normal."""
    import requests
    secreto = os.environ.get("CENTRAL_INTERNAL_SECRET", "")
    try:
        r = requests.request(
            method, f"{_CENTRAL_BASE}{path}", json=payload or {},
            headers={"X-Internal-Secret": secreto}, timeout=timeout,
        )
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400 and "error" not in data:
            data = {**data, "error": f"Error del servidor central (HTTP {r.status_code})."}
        data.setdefault("ok", r.status_code < 400)
        return data
    except requests.RequestException as ex:
        logger.error("_central(%s): %s", path, ex)
        return {"ok": False, "error": "El servicio de altas no está disponible ahora mismo. "
                                      "Inténtalo de nuevo en unos minutos."}


# ── Capa visual común ────────────────────────────────────────────────────────────────────────
def _layout(titulo, cuerpo, *, descripcion="Smart Manager — ERP cloud para gestión empresarial",
           sesion=None):
    nav_cuenta = (
        f'<a class="btnnav" href="/mi-cuenta">Mi cuenta</a>'
        if sesion else
        f'<a class="btnnav" href="/login">Iniciar sesión</a>'
    )
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Smart Manager</title>
<meta name="description" content="{_e(descripcion)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22><rect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%230E1117%22/><text x=%2216%22 y=%2222%22 font-size=%2218%22 fill=%22%2300FFC6%22 text-anchor=%22middle%22 font-family=%22sans-serif%22>S</text></svg>">
<style>
:root {{ --bg:{_BG}; --bg2:{_BG2}; --ac:{_CIAN}; --bd:{_BORDE}; --tx:{_TEXT}; --dim:{_DIM}; --rojo:{_ROJO}; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;line-height:1.55}}
a{{color:var(--ac);text-decoration:none}}
a:hover{{text-decoration:underline}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 24px}}
header.topbar{{border-bottom:1px solid var(--bd);position:sticky;top:0;background:rgba(14,17,23,.92);backdrop-filter:blur(6px);z-index:10}}
.topbar .wrap{{display:flex;align-items:center;justify-content:space-between;height:64px}}
.brand{{font-weight:900;font-size:18px;color:var(--tx);letter-spacing:.5px}}
.brand b{{color:var(--ac)}}
nav.links{{display:flex;gap:22px;align-items:center;font-size:14px;font-weight:600}}
nav.links a{{color:var(--tx)}}
.btnnav{{background:var(--ac)!important;color:#0D1117!important;padding:9px 18px;border-radius:9px;font-weight:900!important}}
.btnnav:hover{{text-decoration:none!important;opacity:.88}}
main{{padding:56px 0 90px}}
h1{{font-size:clamp(28px,4.4vw,46px);font-weight:900;margin:0 0 16px;letter-spacing:-.5px}}
h1 span{{color:var(--ac)}}
h2{{font-size:26px;font-weight:900;margin:0 0 8px}}
.sub{{color:var(--dim);font-size:17px;max-width:640px;margin:0 0 32px}}
.cta-row{{display:flex;gap:14px;flex-wrap:wrap;margin-top:28px}}
.btn{{display:inline-block;padding:14px 26px;border-radius:10px;font-weight:900;font-size:15px;cursor:pointer;border:2px solid var(--ac)}}
.btn-primary{{background:var(--ac);color:#0D1117}}
.btn-primary:hover{{opacity:.88;text-decoration:none}}
.btn-ghost{{background:transparent;color:var(--ac)}}
.btn-ghost:hover{{background:var(--ac);color:#0D1117;text-decoration:none}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;margin:36px 0}}
.card{{background:var(--bg2);border:1px solid var(--bd);border-radius:16px;padding:26px}}
.card h3{{margin:0 0 10px;font-size:18px;color:var(--ac)}}
.card p{{color:var(--dim);font-size:14px;margin:0}}
.plan{{background:var(--bg2);border:2px solid var(--bd);border-radius:18px;padding:30px;display:flex;flex-direction:column}}
.plan.destacado{{border-color:var(--ac);box-shadow:0 0 0 1px var(--ac)}}
.plan .badge{{align-self:flex-start;background:var(--ac);color:#0D1117;font-size:11px;font-weight:900;padding:4px 10px;border-radius:999px;margin-bottom:12px}}
.plan h3{{font-size:20px;margin:0 0 4px;font-weight:900}}
.plan .precio{{font-size:40px;font-weight:900;margin:14px 0 4px}}
.plan .precio small{{font-size:14px;color:var(--dim);font-weight:600}}
.plan ul{{list-style:none;margin:18px 0;padding:0;flex:1}}
.plan li{{padding:7px 0;border-top:1px solid var(--bd);color:var(--tx);font-size:14px}}
.plan li:first-child{{border-top:none}}
.plan li b{{color:var(--ac)}}
.recomendador{{background:var(--bg2);border:1px dashed var(--ac);border-radius:16px;padding:24px;margin:40px 0;font-size:14px;color:var(--tx)}}
.recomendador h3{{margin:0 0 10px;color:var(--ac);font-size:16px}}
.recomendador ul{{margin:0;padding-left:20px}}
.recomendador li{{margin:6px 0}}
form.panel{{background:var(--bg2);border:1px solid var(--bd);border-radius:16px;padding:32px;max-width:440px;margin:0 auto}}
form.panel label{{display:block;font-size:13px;font-weight:700;color:var(--dim);margin:16px 0 6px}}
form.panel input,form.panel select{{width:100%;background:var(--bg);color:var(--tx);border:2px solid var(--bd);border-radius:9px;padding:11px 13px;font-size:14px;font-family:inherit}}
form.panel input:focus,form.panel select:focus{{outline:none;border-color:var(--ac)}}
form.panel button{{width:100%;margin-top:24px;padding:13px;border-radius:10px;border:none;background:var(--ac);color:#0D1117;font-weight:900;font-size:15px;cursor:pointer}}
form.panel button:hover{{opacity:.88}}
.msg-error{{background:#2D1115;border:1px solid var(--rojo);color:#FFB4AE;padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:6px}}
.msg-ok{{background:#0F2A1C;border:1px solid #2EA043;color:#7EE2A8;padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:6px}}
.codigo-box{{background:var(--bg);border:2px dashed var(--ac);border-radius:12px;padding:20px;text-align:center;font-size:24px;font-weight:900;letter-spacing:2px;color:var(--ac);margin:18px 0}}
footer{{border-top:1px solid var(--bd);padding:30px 0;color:var(--dim);font-size:13px}}
footer .wrap{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px}}
footer a{{color:var(--dim)}}
.legal{{max-width:760px}}
.legal h2{{margin-top:38px;font-size:19px}}
.legal p,.legal li{{color:#C9D1D9;font-size:14.5px}}
.legal table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}}
.legal th,.legal td{{border:1px solid var(--bd);padding:8px 10px;text-align:left}}
.legal th{{background:var(--bg2);color:var(--ac)}}
code.pill{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:1px 6px;font-size:12.5px}}
@media (max-width:640px){{ nav.links{{display:none}} }}
</style></head><body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="/">Smart<b>Manager</b></a>
  <nav class="links">
    <a href="/">Inicio</a>
    <a href="/precios">Precios</a>
    <a href="/descargas">Descargas</a>
    {nav_cuenta}
  </nav>
</div></header>
<main>{cuerpo}</main>
<footer><div class="wrap">
  <span>© {__import__('datetime').date.today().year} Smart Manager — ERP cloud de gestión empresarial.</span>
  <span><a href="/privacidad">Política de Privacidad</a> · <a href="/terminos">Condiciones del Servicio</a> · <a href="mailto:soporte@smartmanager-app.com">soporte@smartmanager-app.com</a></span>
</div></footer>
</body></html>"""


def _wrap(titulo, body_html, **kw):
    return _layout(titulo, body_html, **kw)


# ── Página de inicio ─────────────────────────────────────────────────────────────────────────
def _pagina_home(sesion):
    cuerpo = f"""
<div class="wrap">
  <h1>El ERP cloud que une<br><span>tienda, almacén y oficina</span> en un solo sitio.</h1>
  <p class="sub">Smart Manager gestiona TPV, stock multi-almacén, compras, ventas, RRHH, CRM,
  facturación (Verifactu/AEAT) y mucho más — todo sincronizado en tiempo real entre tus centros,
  tu equipo y tu móvil.</p>
  <div class="cta-row">
    <a class="btn btn-primary" href="/precios">Ver planes y precios</a>
    <a class="btn btn-ghost" href="/descargas">Descargar la app</a>
  </div>
  <div class="grid3">
    <div class="card"><h3>🏪 TPV y ventas</h3><p>Punto de venta táctil, autocobro, facturación por centro, campañas CRM y objetivos de productividad en vivo.</p></div>
    <div class="card"><h3>📦 Stock multi-almacén</h3><p>Kárdex por lotes/FEFO, reposición automática, inventario con RFID/lectores Zebra y trazabilidad completa.</p></div>
    <div class="card"><h3>👥 RRHH y nóminas</h3><p>Fichajes, horarios, bolsa de horas, portal del empleado y generación de nóminas, todo integrado con el resto del ERP.</p></div>
    <div class="card"><h3>🧾 Fiscalidad real</h3><p>Verifactu/AEAT con firma y envío real (no una simulación), Facturae y modelos oficiales.</p></div>
    <div class="card"><h3>🤖 IA y automatización</h3><p>Previsión de demanda, reposición inteligente y un asistente de voz (SOMA) para tareas del día a día.</p></div>
    <div class="card"><h3>🔒 Seguridad por diseño</h3><p>MFA/TOTP, control de acceso por rol y centro, cifrado de datos sensibles en reposo y en tránsito (TLS).</p></div>
  </div>
</div>"""
    return _wrap("Smart Manager — ERP cloud de gestión empresarial", cuerpo, sesion=sesion)


# ── Precios ──────────────────────────────────────────────────────────────────────────────────
_ETIQUETAS_LIMITE = [
    ("max_tiendas", "centro{s} / tienda{s}"), ("max_usuarios", "usuario{s}"),
    ("max_almacenes", "almacén{es}"), ("max_correos", "buzón{es} de correo"),
]


def _plural(n, singular_plantilla):
    if n >= 9999:
        return "ilimitados"
    return singular_plantilla.format(s="s" if n != 1 else "", es="es" if n != 1 else "")


def _tarjeta_plan(codigo, cfg, *, destacado=False):
    from src.services.saas import planes as _P
    limites = cfg["limites"]
    filas = []
    for clave, plantilla in _ETIQUETAS_LIMITE:
        n = limites.get(clave, 0)
        filas.append(f"<li><b>{n if n < 9999 else '∞'}</b> {_plural(n, plantilla)}</li>")
    filas.append(f"<li><b>{len(cfg['modulos'])}</b> módulos incluidos</li>")
    precio = cfg["precio"]
    precio_html = "Gratis" if precio == 0 else f"{precio:.0f}€<small>/mes</small>"
    badge = '<span class="badge">MÁS ELEGIDO</span>' if destacado else ""
    cls = "plan destacado" if destacado else "plan"
    return f"""<div class="{cls}">{badge}
      <h3>{_e(cfg['nombre'])}</h3>
      <div class="precio">{precio_html}</div>
      <ul>{''.join(filas)}</ul>
      <a class="btn btn-primary" href="/registro?plan={codigo.lower()}">Elegir {_e(cfg['nombre'])}</a>
    </div>"""


def _pagina_precios(sesion):
    from src.services.saas import planes as _P
    tarjetas = (
        _tarjeta_plan("BASIC", _P.PLANES["BASIC"])
        + _tarjeta_plan("PLUS", _P.PLANES["PLUS"], destacado=True)
        + _tarjeta_plan("PRO", _P.PLANES["PRO"])
    )
    cuerpo = f"""
<div class="wrap">
  <h1>Planes simples, <span>sin sorpresas</span></h1>
  <p class="sub">Un único precio mensual por empresa, sin coste por puesto adicional dentro de tu
  límite de plan. Cambia de plan cuando quieras desde "Mi cuenta".</p>
  <div class="grid3">{tarjetas}</div>
  <div class="recomendador">
    <h3>¿No sabes cuál elegir?</h3>
    <ul>
      <li><b>Básico ({_P.PLANES['BASIC']['precio']:.0f}€/mes)</b> — ideal para un autónomo o una única
      tienda que empieza: TPV, stock, compras/ventas y facturación básica con hasta 3 usuarios.</li>
      <li><b>Plus</b> — la opción más elegida: negocios con varios centros (hasta 10 tiendas) o que
      necesitan RRHH, contabilidad, Business Intelligence y fiscalidad avanzada (Verifactu/AEAT).</li>
      <li><b>Pro</b> — cadenas y grupos empresariales sin límite de tiendas/usuarios, con API completa,
      conectores premium, branding propio y comparativas multiempresa.</li>
    </ul>
  </div>
</div>"""
    return _wrap("Precios y planes", cuerpo, sesion=sesion)


# ── Registro / alta ──────────────────────────────────────────────────────────────────────────
def _pagina_registro(plan, error=None):
    from src.services.saas import planes as _P
    cfg = _P.PLANES.get(plan.upper())
    if not cfg:
        plan, cfg = "BASIC", _P.PLANES["BASIC"]
    es_gratis = cfg["precio"] == 0
    aviso_pago = "" if es_gratis else (
        f'<p style="color:var(--dim);font-size:13px;margin-top:-4px">Tras enviar este formulario te '
        f'llevaremos a la pasarela de pago segura de Stripe para domiciliar la cuota mensual '
        f'({cfg["precio"]:.0f}€/mes). No se te cobra nada hasta confirmar el pago.</p>'
    )
    error_html = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2 style="text-align:center">Crear cuenta — plan {_e(cfg['nombre'])}</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
    <a href="/precios">← Cambiar de plan</a></p>
  <form class="panel" method="post" action="/registro">
    <input type="hidden" name="plan" value="{_e(plan.lower())}">
    {error_html}
    <label>Nombre de la empresa</label>
    <input name="nombre_empresa" required maxlength="255" placeholder="Mi Empresa S.L.">
    <label>Email</label>
    <input type="email" name="email" required maxlength="255" placeholder="tu@empresa.com">
    <label>Contraseña</label>
    <input type="password" name="password" required minlength="8" placeholder="Mínimo 8 caracteres">
    {aviso_pago}
    <button type="submit">{"Crear cuenta gratis" if es_gratis else "Continuar al pago"}</button>
  </form>
  <p style="text-align:center;color:var(--dim);font-size:13px;margin-top:18px">
    Al continuar aceptas las <a href="/terminos">Condiciones del Servicio</a> y la
    <a href="/privacidad">Política de Privacidad</a>. ¿Ya tienes cuenta? <a href="/login">Inicia sesión</a>.</p>
</div>"""
    return _wrap(f"Crear cuenta · {cfg['nombre']}", cuerpo)


def _pagina_resultado_alta(codigo, plan, *, nuevo=True):
    nota = "" if nuevo else '<p style="color:var(--dim);font-size:13px">(Este Checkout ya se había confirmado antes — aquí tienes tu código de nuevo.)</p>'
    cuerpo = f"""
<div class="wrap" style="max-width:540px;text-align:center">
  <h2>🎉 ¡Todo listo!</h2>
  <p class="sub" style="margin:0 auto 10px">Tu plan <b>{_e(plan)}</b> está activo. Este es tu código
  de activación — pégalo la primera vez que abras la app de escritorio:</p>
  <div class="codigo-box">{_e(codigo)}</div>
  {nota}
  <p style="color:var(--dim);font-size:13px">También te lo hemos enviado por email, por si lo necesitas más tarde.</p>
  <div class="cta-row" style="justify-content:center">
    <a class="btn btn-primary" href="/descargas">Descargar la app ahora</a>
    <a class="btn btn-ghost" href="/mi-cuenta">Ir a Mi cuenta</a>
  </div>
</div>"""
    return _wrap("Cuenta creada", cuerpo)


def _pagina_pago_no_disponible():
    cuerpo = f"""
<div class="wrap" style="max-width:520px;text-align:center">
  <h2>Pago no disponible todavía</h2>
  <p class="sub" style="margin:0 auto">
    Estamos terminando de activar el cobro con tarjeta para este plan. Escríbenos a
    <a href="mailto:ventas@smartmanager-app.com">ventas@smartmanager-app.com</a> y te damos de alta
    manualmente mientras tanto.</p>
</div>"""
    return _wrap("Pago no disponible", cuerpo)


# ── Login / cuenta ───────────────────────────────────────────────────────────────────────────
def _pagina_login(error=None):
    error_html = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2 style="text-align:center">Iniciar sesión</h2>
  <form class="panel" method="post" action="/login">
    {error_html}
    <label>Email</label>
    <input type="email" name="email" required>
    <label>Contraseña</label>
    <input type="password" name="password" required>
    <button type="submit">Entrar</button>
  </form>
  <p style="text-align:center;color:var(--dim);font-size:13px;margin-top:18px">
    ¿Todavía no tienes cuenta? <a href="/precios">Ver planes</a>.</p>
</div>"""
    return _wrap("Iniciar sesión", cuerpo)


def _pagina_mi_cuenta(info, id_empresa_central):
    sus = info.get("suscripcion") or {}
    codigos = info.get("codigos") or []
    filas_codigos = "".join(
        f"<tr><td>{_e(c.get('plan'))}</td><td><code class='pill'>{_e(c.get('codigo'))}</code></td>"
        f"<td>{'Usado' if c.get('usado') else 'Sin usar'}</td><td>{_e(c.get('generado_en'))}</td></tr>"
        for c in codigos
    ) or "<tr><td colspan='4' style='color:var(--dim)'>Todavía no tienes códigos de activación.</td></tr>"
    estado_sus = _e(sus.get("estado") or "—")
    plan_sus = _e(sus.get("codigo_plan") or "—")
    cuerpo = f"""
<div class="wrap">
  <h2>Mi cuenta</h2>
  <p class="sub">Plan actual: <b style="color:var(--ac)">{plan_sus}</b> · Estado de la suscripción:
  <b>{estado_sus}</b></p>
  <div class="card" style="margin-bottom:28px">
    <h3>Tus códigos de activación</h3>
    <table class="legal" style="width:100%"><thead><tr><th>Plan</th><th>Código</th><th>Estado</th><th>Generado</th></tr></thead>
    <tbody>{filas_codigos}</tbody></table>
  </div>
  <div class="cta-row">
    <a class="btn btn-primary" href="/descargas">Descargar la app de escritorio</a>
    <a class="btn btn-ghost" href="/logout">Cerrar sesión</a>
  </div>
</div>"""
    return _wrap("Mi cuenta", cuerpo, sesion=True)


# ── Descargas ────────────────────────────────────────────────────────────────────────────────
_DIR_INSTALADORES = "/app/instaladores"
_INSTALADOR_WINDOWS = "SmartManagerSetup.exe"


def _pagina_descargas(sesion):
    import os as _os
    disponible = _os.path.exists(_os.path.join(_DIR_INSTALADORES, _INSTALADOR_WINDOWS))
    if sesion and disponible:
        boton = f'<a class="btn btn-primary" href="/descargas/windows">⬇ Descargar para Windows</a>'
    elif sesion:
        boton = ('<p class="msg-error" style="display:inline-block">El instalador está en preparación. '
                 'Te avisaremos por email en cuanto esté disponible.</p>')
    else:
        boton = '<a class="btn btn-primary" href="/precios">Ver planes para empezar</a>'
    cuerpo = f"""
<div class="wrap" style="text-align:center;max-width:560px">
  <h2>Descarga Smart Manager</h2>
  <p class="sub" style="margin:0 auto">La app de escritorio funciona en Windows 10/11 y se conecta
  automáticamente a tu empresa con el código de activación que recibiste al darte de alta.</p>
  {boton}
</div>"""
    return _wrap("Descargas", cuerpo, sesion=sesion)


def _servir_instalador():
    from flask import send_from_directory
    return send_from_directory(_DIR_INSTALADORES, _INSTALADOR_WINDOWS, as_attachment=True)


# ── Legal: Privacidad ────────────────────────────────────────────────────────────────────────
def _pagina_privacidad():
    cuerpo = f"""
<div class="wrap legal">
  <h1 style="font-size:30px">Política de Privacidad</h1>
  <p style="color:var(--dim)">Última actualización: {__import__('datetime').date.today().strftime('%d/%m/%Y')}</p>

  <p>Esta Política de Privacidad describe cómo <b>Smart Manager</b> ("nosotros", "la Plataforma")
  recoge, utiliza, almacena y protege los datos personales de los usuarios de su sitio web
  (<code class="pill">smartmanager-app.com</code>) y de su aplicación de escritorio ERP
  ("el Servicio"), en cumplimiento del Reglamento (UE) 2016/679 (RGPD) y la LOPDGDD.</p>

  <h2>1. Responsable del tratamiento</h2>
  <p>Smart Manager es responsable del tratamiento de los datos descritos en esta política. Para
  cualquier consulta sobre privacidad puedes escribir a
  <a href="mailto:privacidad@smartmanager-app.com">privacidad@smartmanager-app.com</a>.</p>

  <h2>2. Qué datos tratamos</h2>
  <table><tr><th>Categoría</th><th>Ejemplos</th><th>Origen</th></tr>
  <tr><td>Datos de cuenta</td><td>Nombre de empresa, email, contraseña (cifrada, nunca en claro)</td><td>Formulario de alta web</td></tr>
  <tr><td>Datos de facturación</td><td>Datos de la tarjeta de pago (gestionados ÍNTEGRAMENTE por Stripe, nunca almacenados por nosotros)</td><td>Pasarela de pago Stripe</td></tr>
  <tr><td>Datos operativos del ERP</td><td>Clientes, proveedores, ventas, stock, empleados de tu empresa</td><td>Introducidos por ti al usar el Servicio</td></tr>
  <tr><td>Datos de integraciones de terceros</td><td>Mensajes de correo (Gmail) y eventos de calendario (Google Calendar) que tú conectes</td><td>APIs de Google, solo si activas la integración</td></tr>
  <tr><td>Datos técnicos</td><td>IP, tipo de navegador, registros de actividad (auditoría)</td><td>Uso del Servicio</td></tr>
  </table>

  <h2>3. Uso de las APIs de Google (Gmail y Calendar)</h2>
  <p>Smart Manager ofrece, de forma OPCIONAL y solo si el usuario lo activa expresamente desde el
  módulo "Correo" y "Eventos", una integración con cuentas de Google mediante OAuth 2.0. Esta
  integración solicita los siguientes permisos (scopes) y se usa EXCLUSIVAMENTE para lo indicado:</p>
  <ul>
    <li><b>Gmail (scope de modificación, <code class="pill">gmail.modify</code>)</b>: permite a Smart
    Manager leer, enviar y organizar (marcar como leído, etiquetar) los correos de la cuenta conectada
    DENTRO del módulo de Correo corporativo del ERP — p. ej. para que el buzón del cliente y el buzón
    visible en Smart Manager estén sincronizados. Smart Manager NUNCA elimina correos de forma
    permanente ni accede a la cuenta fuera de las acciones que el propio usuario realiza desde la
    interfaz del módulo de Correo.</li>
    <li><b>Google Calendar (scope de eventos)</b>: permite importar, en modo lectura, los eventos del
    calendario conectado hacia la agenda interna de Smart Manager (módulo "Eventos"), para mostrar
    citas y recordatorios dentro del ERP sin tener que consultar dos calendarios por separado.</li>
  </ul>
  <p>El uso que Smart Manager hace de los datos obtenidos de las APIs de Google cumple la
  <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener">
  Política de Datos de Usuario de los Servicios de API de Google</a>, incluidos los requisitos de Uso
  Limitado: estos datos se usan ÚNICAMENTE para proporcionar o mejorar las funciones del módulo de
  Correo/Eventos visibles al usuario, nunca se usan con fines publicitarios, nunca se venden ni se
  comparten con terceros para fines ajenos al Servicio, y solo acceden a ellos personas autorizadas
  cuando es estrictamente necesario para dar soporte técnico al propio usuario.</p>
  <p>El usuario puede revocar el acceso en cualquier momento desde la configuración de su cuenta de
  Google (<a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener">
  myaccount.google.com/permissions</a>) o desde el propio módulo de Correo/Eventos de Smart Manager,
  sin que ello afecte al resto de funciones del ERP.</p>

  <h2>4. Cifrado y seguridad de los datos</h2>
  <ul>
    <li><b>En tránsito</b>: todas las comunicaciones entre el navegador, la app de escritorio y
    nuestros servidores viajan cifradas mediante TLS 1.2+ (HTTPS), incluidas las llamadas a las APIs
    de Google y a la pasarela de pago Stripe.</li>
    <li><b>En reposo</b>: los secretos sensibles (tokens OAuth, credenciales de terceros, IBAN) se
    almacenan cifrados en la base de datos mediante cifrado simétrico (Fernet/AES) gestionado por
    nuestro propio módulo de secretos; las contraseñas de las cuentas nunca se almacenan en claro,
    solo su resumen criptográfico (hash con sal, PBKDF2).</li>
    <li><b>Aislamiento multiempresa</b>: los datos de cada empresa cliente están lógicamente
    aislados y nunca son accesibles desde la cuenta de otra empresa.</li>
  </ul>

  <h2>5. Conservación de los datos</h2>
  <p>Conservamos los datos de la cuenta mientras la suscripción esté activa y durante el plazo
  adicional exigido por la normativa fiscal/mercantil aplicable tras su cancelación. El usuario puede
  solicitar la supresión anticipada de sus datos personales (no operativos/fiscales) escribiendo a
  <a href="mailto:privacidad@smartmanager-app.com">privacidad@smartmanager-app.com</a>.</p>

  <h2>6. Derechos del usuario</h2>
  <p>Puedes ejercer tus derechos de acceso, rectificación, supresión, oposición, limitación y
  portabilidad escribiendo a <a href="mailto:privacidad@smartmanager-app.com">privacidad@smartmanager-app.com</a>.
  También puedes presentar una reclamación ante la Agencia Española de Protección de Datos (AEPD).</p>

  <h2>7. Terceros que procesan datos en nuestro nombre</h2>
  <table><tr><th>Proveedor</th><th>Finalidad</th></tr>
  <tr><td>Stripe, Inc.</td><td>Procesamiento de pagos y domiciliación de cuotas (PCI-DSS Nivel 1)</td></tr>
  <tr><td>Google LLC</td><td>Integración OAuth de Gmail/Calendar, solo si el usuario la activa</td></tr>
  <tr><td>Hetzner Online GmbH</td><td>Alojamiento de los servidores (Unión Europea)</td></tr>
  </table>

  <h2>8. Cambios en esta política</h2>
  <p>Podemos actualizar esta política para reflejar cambios legales o del Servicio; la fecha de
  "última actualización" al inicio de esta página indica la versión vigente.</p>
</div>"""
    return _wrap("Política de Privacidad",
                 cuerpo.replace("\n</div>", "\n</div>"),
                 descripcion="Política de Privacidad de Smart Manager: tratamiento de datos, uso de "
                             "las APIs de Google (Gmail/Calendar) y cifrado en tránsito y en reposo.")


# ── Legal: Términos ──────────────────────────────────────────────────────────────────────────
def _pagina_terminos():
    cuerpo = f"""
<div class="wrap legal">
  <h1 style="font-size:30px">Condiciones del Servicio</h1>
  <p style="color:var(--dim)">Última actualización: {__import__('datetime').date.today().strftime('%d/%m/%Y')}</p>

  <p>Estas Condiciones del Servicio ("Condiciones") regulan el acceso y uso de Smart Manager, un
  software de gestión empresarial (ERP) ofrecido como servicio por suscripción ("el Servicio"). Al
  crear una cuenta o usar el Servicio, aceptas estas Condiciones.</p>

  <h2>1. Descripción del Servicio</h2>
  <p>Smart Manager proporciona una aplicación de escritorio y servicios en la nube para la gestión de
  punto de venta, inventario, compras, ventas, recursos humanos, contabilidad, CRM y funciones
  relacionadas, organizada en los planes <b>Básico</b>, <b>Plus</b> y <b>Pro</b> descritos en
  <a href="/precios">/precios</a>.</p>

  <h2>2. Cuenta y registro</h2>
  <p>Para contratar el Servicio debes proporcionar información veraz sobre tu empresa y mantener la
  confidencialidad de tu contraseña. Eres responsable de toda actividad realizada desde tu cuenta.</p>

  <h2>3. Planes, precios y facturación</h2>
  <ul>
    <li>Los tres planes (Básico, Plus y Pro) se facturan mensualmente por adelantado mediante
    domiciliación de pago con tarjeta a través de Stripe, sujetos a los límites indicados en la
    página de precios; el cobro se renueva automáticamente cada mes salvo cancelación.</li>
    <li>Puedes cambiar de plan o cancelar tu suscripción en cualquier momento desde "Mi cuenta"; la
    cancelación surte efecto al final del periodo ya pagado, sin reembolso de la parte proporcional
    salvo que la ley aplicable disponga lo contrario.</li>
    <li>Nos reservamos el derecho a modificar los precios, avisando con al menos 30 días de antelación
    a los clientes con suscripción activa.</li>
  </ul>

  <h2>4. Uso aceptable</h2>
  <p>Te comprometes a no utilizar el Servicio para actividades ilícitas, a no intentar vulnerar su
  seguridad y a cumplir la normativa aplicable a tu negocio (incluida la fiscal) al introducir datos
  en el ERP, especialmente en los módulos de facturación y Verifactu/AEAT.</p>

  <h2>5. Propiedad intelectual</h2>
  <p>Smart Manager y su código, marca y diseño son propiedad de sus titulares. Tú conservas la
  titularidad de todos los datos que introduzcas en el Servicio ("tus datos").</p>

  <h2>6. Integraciones de terceros (Google y otras)</h2>
  <p>Las integraciones opcionales con servicios de terceros (p. ej. Gmail, Google Calendar, pasarelas
  de pago de tu propia tienda online) están sujetas además a los términos del propio tercero. Puedes
  desactivarlas en cualquier momento desde la configuración del ERP sin afectar al resto del Servicio.
  Ver también el apartado 3 de la <a href="/privacidad">Política de Privacidad</a>.</p>

  <h2>7. Disponibilidad y soporte</h2>
  <p>Trabajamos para mantener el Servicio disponible de forma continua, pero no garantizamos un
  funcionamiento ininterrumpido o libre de errores. Puedes contactar con soporte en
  <a href="mailto:soporte@smartmanager-app.com">soporte@smartmanager-app.com</a>.</p>

  <h2>8. Limitación de responsabilidad</h2>
  <p>En la medida permitida por la ley, Smart Manager no será responsable de daños indirectos,
  lucro cesante o pérdida de datos derivados del uso del Servicio, salvo negligencia grave o dolo.</p>

  <h2>9. Suspensión y cancelación por incumplimiento</h2>
  <p>Podemos suspender o cancelar el acceso al Servicio en caso de impago, uso fraudulento o
  incumplimiento grave de estas Condiciones, notificándolo previamente cuando sea razonablemente
  posible.</p>

  <h2>10. Legislación aplicable</h2>
  <p>Estas Condiciones se rigen por la legislación española. Cualquier controversia se someterá a los
  juzgados y tribunales competentes, sin perjuicio de los derechos que asistan al consumidor conforme
  a la normativa de protección de consumidores y usuarios.</p>

  <h2>11. Contacto</h2>
  <p><a href="mailto:legal@smartmanager-app.com">legal@smartmanager-app.com</a></p>
</div>"""
    return _wrap("Condiciones del Servicio", cuerpo,
                 descripcion="Condiciones del Servicio de Smart Manager: planes, facturación, uso "
                             "aceptable e integraciones de terceros.")


# ── Blueprint ────────────────────────────────────────────────────────────────────────────────
def crear_blueprint():
    from flask import (Blueprint, redirect, request, session, url_for)

    bp = Blueprint("sitio_oficial", __name__)

    @bp.get("/")
    def home():
        return _pagina_home(session.get("cuenta"))

    @bp.get("/precios")
    def precios():
        return _pagina_precios(session.get("cuenta"))

    @bp.get("/privacidad")
    def privacidad():
        return _pagina_privacidad()

    @bp.get("/terminos")
    def terminos():
        return _pagina_terminos()

    @bp.get("/descargas")
    def descargas():
        return _pagina_descargas(session.get("cuenta"))

    @bp.get("/descargas/windows")
    def descargas_windows():
        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        import os as _os
        if not _os.path.exists(_os.path.join(_DIR_INSTALADORES, _INSTALADOR_WINDOWS)):
            return _pagina_descargas(session.get("cuenta"))
        return _servir_instalador()

    # ── Registro ────────────────────────────────────────────────────────────────────────────
    @bp.get("/registro")
    def registro_form():
        plan = (request.args.get("plan") or "basic").lower()
        return _pagina_registro(plan)

    @bp.post("/registro")
    def registro_submit():
        from werkzeug.security import generate_password_hash

        from src.services.saas import planes as _P

        plan = (request.form.get("plan") or "basic").upper()
        nombre_empresa = (request.form.get("nombre_empresa") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        cfg = _P.PLANES.get(plan)
        if not cfg or not nombre_empresa or not email or len(password) < 8:
            return _pagina_registro(plan.lower(),
                                    error="Revisa los datos: la contraseña debe tener al menos 8 "
                                         "caracteres y todos los campos son obligatorios."), 400

        password_hash = generate_password_hash(password)

        if cfg["precio"] == 0:
            r = _central("/central/sitio/registrar_gratis", {
                "nombre_empresa": nombre_empresa, "email": email, "password_hash": password_hash,
            })
            if not r.get("ok"):
                return _pagina_registro(plan.lower(), error=r.get("error") or "No se pudo crear la cuenta."), 400
            _enviar_codigo_por_email(email, r["codigo"], r["plan"])
            session["cuenta"] = {"email": email}
            session["id_empresa_central"] = r.get("id_empresa_central")
            return _pagina_resultado_alta(r["codigo"], r["plan"])

        # Planes de pago: valida que el email no exista YA antes de ir a Stripe (evita checkouts
        # que luego no se pueden confirmar), y guarda los datos del alta en la sesión (cookie
        # firmada del propio navegador) para recuperarlos al volver del pago — la contraseña viaja
        # ya hasheada, nunca en claro, y NUNCA se envía a Stripe.
        pre = _central("/central/sitio/preregistrar", {"email": email})
        if not pre.get("ok"):
            return _pagina_registro(plan.lower(), error=pre.get("error") or "No se pudo validar el email."), 400

        secreto = os.environ.get("STRIPE_SECRET_KEY")
        price_id = os.environ.get(f"STRIPE_PRICE_ID_{plan}")
        if not secreto or not price_id:
            logger.warning("Checkout Stripe no configurado (falta STRIPE_SECRET_KEY o "
                          "STRIPE_PRICE_ID_%s) — alta de pago bloqueada honestamente.", plan)
            return _pagina_pago_no_disponible()

        try:
            import stripe
            stripe.api_key = secreto
            checkout = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=email,
                success_url=url_for("sitio_oficial.checkout_exito", _external=True)
                + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("sitio_oficial.checkout_cancelado", _external=True),
                metadata={"plan": plan, "email": email, "nombre_empresa": nombre_empresa},
            )
        except Exception as ex:
            logger.error("Creando Stripe Checkout Session: %s", ex)
            return _pagina_registro(plan.lower(),
                                    error="No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."), 502

        session["pendiente_checkout"] = {
            "plan": plan, "email": email, "nombre_empresa": nombre_empresa,
            "password_hash": password_hash,
        }
        return redirect(checkout.url, code=303)

    @bp.get("/checkout/exito")
    def checkout_exito():
        session_id = request.args.get("session_id")
        pendiente = session.get("pendiente_checkout")
        if not session_id or not pendiente:
            return redirect(url_for("sitio_oficial.precios"))

        secreto = os.environ.get("STRIPE_SECRET_KEY")
        if not secreto:
            return _pagina_pago_no_disponible()
        try:
            import stripe
            stripe.api_key = secreto
            chk = stripe.checkout.Session.retrieve(session_id)
        except Exception as ex:
            logger.error("Recuperando Checkout Session %s: %s", session_id, ex)
            return _pagina_pago_no_disponible()

        if chk.get("payment_status") != "paid":
            return _pagina_registro(pendiente["plan"].lower(),
                                    error="El pago no se ha completado todavía."), 400

        r = _central("/central/sitio/confirmar_pago", {
            "session_id": session_id, "plan": pendiente["plan"], "email": pendiente["email"],
            "nombre_empresa": pendiente["nombre_empresa"], "password_hash": pendiente["password_hash"],
            "stripe_customer_id": chk.get("customer"),
        })
        session.pop("pendiente_checkout", None)
        if not r.get("ok"):
            logger.error("confirmar_pago tras Stripe OK pero el alta central falló: %s", r.get("error"))
            return _pagina_registro(pendiente["plan"].lower(),
                                    error="El pago se completó pero no pudimos terminar el alta. "
                                         "Escríbenos a soporte@smartmanager-app.com con tu email de "
                                         "compra y lo resolvemos manualmente."), 502

        _enviar_codigo_por_email(pendiente["email"], r["codigo"], r["plan"])
        session["cuenta"] = {"email": pendiente["email"]}
        return _pagina_resultado_alta(r["codigo"], r["plan"], nuevo=not r.get("ya_existia"))

    @bp.get("/checkout/cancelado")
    def checkout_cancelado():
        session.pop("pendiente_checkout", None)
        return _wrap("Pago cancelado", """
<div class="wrap" style="text-align:center;max-width:480px">
  <h2>Pago cancelado</h2>
  <p class="sub" style="margin:0 auto">No se ha realizado ningún cargo. Puedes volver a intentarlo
  cuando quieras.</p>
  <a class="btn btn-primary" href="/precios">Volver a los planes</a>
</div>""")

    # ── Login / sesión ──────────────────────────────────────────────────────────────────────
    @bp.get("/login")
    def login():
        return _pagina_login()

    @bp.post("/login")
    def login_submit():
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        r = _central("/central/sitio/login", {"email": email, "password": password})
        if not r.get("ok"):
            return _pagina_login(error=r.get("error") or "No se pudo iniciar sesión."), 401
        session["cuenta"] = {"email": email}
        session["id_empresa_central"] = r.get("id_empresa_central")
        return redirect(url_for("sitio_oficial.mi_cuenta"))

    @bp.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("sitio_oficial.home"))

    @bp.get("/mi-cuenta")
    def mi_cuenta():
        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        info = _central(f"/central/sitio/mi_cuenta/{id_empresa_central}", method="GET")
        if not info.get("ok"):
            return _pagina_login(error="No se pudo cargar tu cuenta. Inicia sesión de nuevo."), 502
        return _pagina_mi_cuenta(info, id_empresa_central)

    return bp


def _enviar_codigo_por_email(email, codigo, plan):
    """Envío DIRECTO por SMTP (no `services.ccp`): el CCP es multiempresa, pensado para que una
    empresa YA DADA DE ALTA se comunique con SUS clientes — aquí quien envía es Smart Manager (el
    propio vendedor) a un prospecto que normalmente todavía no tiene `id_empresa` en absoluto. Usa
    el buzón propio de la empresa (`SMTP_*`); sin configurar, degrada con un aviso (mejor esfuerzo:
    nunca bloquea el alta — el código ya se muestra en pantalla igualmente)."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.info("SMTP no configurado: no se envía email de activación a %s (código ya mostrado "
                   "en pantalla).", email)
        return
    try:
        import smtplib
        from email.mime.text import MIMEText

        remitente = os.environ.get("SMTP_FROM", "noreply@smartmanager-app.com")
        msg = MIMEText(
            f"¡Gracias por registrarte en Smart Manager!\n\n"
            f"Plan contratado: {plan}\n"
            f"Código de activación: {codigo}\n\n"
            f"Introduce este código la primera vez que abras la app de escritorio para vincularla "
            f"a tu empresa.\n\n"
            f"Descarga la app: https://smartmanager-app.com/descargas\n", "plain", "utf-8")
        msg["Subject"] = "Tu código de activación de Smart Manager"
        msg["From"] = remitente
        msg["To"] = email

        puerto = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, puerto, timeout=10) as s:
            s.starttls()
            usuario_smtp = os.environ.get("SMTP_USER")
            password_smtp = os.environ.get("SMTP_PASSWORD")
            if usuario_smtp and password_smtp:
                s.login(usuario_smtp, password_smtp)
            s.sendmail(remitente, [email], msg.as_string())
    except Exception as ex:
        logger.warning("No se pudo enviar el email de activación a %s: %s", email, ex)
