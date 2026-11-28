"""
Sitio oficial y comercial de Smart Manager — dominio raíz público (`smartmanager-app.com`,
`www.smartmanager-app.com`). Presenta el ERP cloud, los 3 planes de suscripción, el alta/pago y la
descarga de la app de escritorio una vez contratado un plan, además de las páginas legales públicas
exigidas por Google Cloud (Política de Privacidad / Condiciones del Servicio) para la verificación
OAuth de los scopes restringidos de Gmail/Calendar que usa la integración de Correo (`services.correo`)
y Eventos (`services.calendario`).

Arquitectura (sin motor nuevo, reutiliza lo ya construido):
- Catálogo de planes: `services.saas.planes.PLANES` (fuente ÚNICA, la misma que usa el enforcement).
- Alta de empresa + centro + cuenta + código de instalación: TODO en `src.services.alta_comercial`,
  que opera DIRECTAMENTE sobre la BD de este mismo contenedor (`smart_manager_db`, el único SaaS
  multiempresa real de este despliegue — un primer intento usó el servidor CENTRAL de licencias,
  `src.backend_central`, pensado para instalaciones on-prem independientes con su PROPIA base de
  datos; aquí era la base de datos equivocada. Ver el docstring de `alta_comercial` para el porqué).
  El código que recibe el cliente es el MISMO mecanismo que ya usa "Configuración → Datos de
  empresa → Centros" para emparejar un ordenador nuevo (`services.provisioning`), canjeable desde
  la pantalla de primer arranque de la app de escritorio (`main.py::_pantalla_primer_arranque`,
  YA construida — no hacía falta tocar el cliente de escritorio).
- Contraseñas de la cuenta web: PBKDF2 vía `werkzeug.security` (reutilizado dentro de
  `alta_comercial`), NUNCA el hash SHA-256 sin sal de `db/usuario.py` (ese es el sistema de login
  del ERP de escritorio, una identidad totalmente distinta).
- Pago recurrente: Stripe Checkout (tarjeta, `mode=subscription`) — es justo el flujo que
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


def _e(x):
    from markupsafe import escape
    return str(escape(x if x is not None else ""))


def _estrellas(puntuacion) -> str:
    """★ rellenas + ☆ vacías hasta 5 — texto generado, no entrada de usuario, no necesita `_e()`."""
    n = max(0, min(5, int(puntuacion or 0)))
    return "★" * n + "☆" * (5 - n)


def _fecha_corta(valor) -> str:
    return valor.strftime("%d/%m/%Y") if hasattr(valor, "strftime") else _e(valor)


def _url_portal_proveedor() -> str:
    """URL del Portal Proveedor (Smart Suppliers) — mismo patrón ya usado por
    `services.compras.invitaciones`/`suministradores`/`gui.compras_gestion` (petición explícita,
    2026-11-16: enlace visible desde la web oficial para que cualquier proveedor pueda registrarse
    o acceder, sin esperar una invitación por email)."""
    return os.getenv("PORTAL_PROVEEDOR_URL", "http://localhost:8090/portal/proveedor").rstrip("/")


def _url_portal_empresa() -> str:
    """URL del Portal Empresa B2B — mismo patrón que `_url_portal_proveedor` (petición explícita,
    2026-11-16: enlace visible desde la web oficial para que cualquier empresa pueda registrarse o
    acceder al Portal B2B)."""
    return os.getenv("PORTAL_EMPRESA_URL", "http://localhost:8090/portal/empresa").rstrip("/")


# ── Capa visual común ────────────────────────────────────────────────────────────────────────
def _layout(titulo, cuerpo, *, descripcion="Smart Manager — ERP cloud para gestión empresarial",
           sesion=None):
    nav_cuenta = (
        f'<a href="/mi-cuenta">Mi cuenta</a>'
        if sesion else
        f'<a href="/login">Iniciar sesión</a>'
    )
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Smart Manager</title>
<meta name="description" content="{_e(descripcion)}">
<link rel="icon" type="image/png" href="/assets/logo.png">
<link rel="apple-touch-icon" href="/assets/logo.png">
<style>
:root {{ --bg:{_BG}; --bg2:{_BG2}; --ac:{_CIAN}; --bd:{_BORDE}; --tx:{_TEXT}; --dim:{_DIM}; --rojo:{_ROJO}; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;line-height:1.55}}
a{{color:var(--ac);text-decoration:none}}
a:hover{{text-decoration:underline}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 24px}}
header.topbar{{border-bottom:1px solid var(--bd);position:sticky;top:0;background:rgba(14,17,23,.92);backdrop-filter:blur(6px);z-index:10}}
.topbar .wrap{{display:flex;align-items:center;justify-content:space-between;height:64px}}
.brand{{font-weight:900;font-size:18px;color:var(--tx);letter-spacing:.5px;display:flex;align-items:center;gap:9px}}
.brand img{{display:block;border-radius:6px}}
.brand b{{color:var(--ac)}}
nav.links{{display:flex;gap:22px;align-items:center;font-size:14px;font-weight:600}}
nav.links a{{color:var(--tx)}}
.btnnav{{background:var(--bg2)!important;color:var(--ac)!important;border:2px solid var(--ac);padding:7px 16px;border-radius:9px;font-weight:900!important}}
.btnnav:hover{{text-decoration:none!important;background:var(--ac)!important;color:#0D1117!important}}
main{{padding:56px 0 90px}}
h1{{font-size:clamp(28px,4.4vw,46px);font-weight:900;margin:0 0 16px;letter-spacing:-.5px}}
h1 span{{color:var(--ac)}}
h2{{font-size:26px;font-weight:900;margin:0 0 8px}}
.sub{{color:var(--dim);font-size:17px;max-width:640px;margin:0 0 32px}}
.cta-row{{display:flex;gap:14px;flex-wrap:wrap;margin-top:28px}}
/* Mismo diseño que los botones turquesas de la app de escritorio (`gui/catalogo_gestion.py::_btn`):
   contorno + texto turquesa, interior oscuro en reposo, el hover invierte a relleno turquesa con
   texto oscuro. `.btn-primary`/`.btn-ghost` quedan como el mismo estilo (petición explícita: TODOS
   los botones turquesas iguales) — se conservan ambas clases por legibilidad del HTML, no por
   diferencia visual. */
.btn{{display:inline-block;padding:14px 26px;border-radius:10px;font-weight:900;font-size:15px;cursor:pointer;border:2px solid var(--ac);background:var(--bg2);color:var(--ac)}}
.btn-primary,.btn-ghost{{background:var(--bg2);color:var(--ac)}}
.btn-primary:hover,.btn-ghost:hover{{background:var(--ac);color:#0D1117;text-decoration:none}}
[hidden]{{display:none!important}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;margin:36px 0}}
.card{{background:var(--bg2);border:1px solid var(--bd);border-radius:16px;padding:26px}}
.card h3{{margin:0 0 10px;font-size:18px;color:var(--ac)}}
.card p{{color:var(--dim);font-size:14px;margin:0}}
.plan{{background:var(--bg2);border:2px solid var(--bd);border-radius:18px;padding:30px;display:flex;flex-direction:column}}
.plan.destacado{{border-color:var(--ac);box-shadow:0 0 0 1px var(--ac)}}
.plan .badge{{align-self:flex-start;background:var(--ac);color:#0D1117;font-size:11px;font-weight:900;padding:4px 10px;border-radius:999px;margin-bottom:12px}}
.plan .badge-b2b{{align-self:flex-start;background:transparent;border:1px solid var(--ac);color:var(--ac);font-size:11px;font-weight:900;padding:4px 10px;border-radius:999px;margin-bottom:12px}}
.plan h3{{font-size:20px;margin:0 0 4px;font-weight:900}}
.plan .precio{{font-size:40px;font-weight:900;margin:14px 0 4px}}
.plan .precio small{{font-size:14px;color:var(--dim);font-weight:600}}
.plan ul{{list-style:none;margin:18px 0;padding:0;flex:1}}
.plan li{{padding:7px 0;border-top:1px solid var(--bd);color:var(--tx);font-size:14px}}
.plan li:first-child{{border-top:none}}
.plan li b{{color:var(--ac)}}
.plan .ahorro{{font-size:13px;color:var(--ac);font-weight:700;margin:0 0 10px}}
.ciclo-toggle{{display:flex;justify-content:center;gap:10px;margin:28px 0}}
.ciclo-toggle button{{background:var(--bg2);color:var(--tx);border:2px solid var(--bd);border-radius:999px;padding:10px 22px;font-size:14px;font-weight:700;cursor:pointer}}
.ciclo-toggle button.active{{border-color:var(--ac);color:var(--ac)}}
.ciclo-toggle .badge-ahorro{{background:var(--ac);color:#0D1117;font-size:11px;font-weight:400;padding:3px 10px;border-radius:999px;margin-left:8px}}
@keyframes smFadeInUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes smFadeOutDown{{from{{opacity:1;transform:translateY(0)}}to{{opacity:0;transform:translateY(18px)}}}}
.grid3.sm-anim-in{{animation:smFadeInUp .35s ease both}}
.grid3.sm-anim-out{{animation:smFadeOutDown .25s ease both}}
.recomendador{{background:var(--bg2);border:1px dashed var(--ac);border-radius:16px;padding:24px;margin:40px 0;font-size:14px;color:var(--tx)}}
.recomendador h3{{margin:0 0 10px;color:var(--ac);font-size:16px}}
.recomendador ul{{margin:0;padding-left:20px}}
.recomendador li{{margin:6px 0}}
form.panel{{background:var(--bg2);border:1px solid var(--bd);border-radius:16px;padding:32px;max-width:440px;margin:0 auto}}
form.panel label{{display:block;font-size:13px;font-weight:700;color:var(--dim);margin:16px 0 6px}}
form.panel input,form.panel select{{width:100%;background:var(--bg);color:var(--tx);border:2px solid var(--bd);border-radius:9px;padding:11px 13px;font-size:14px;font-family:inherit}}
form.panel input:focus,form.panel select:focus{{outline:none;border-color:var(--ac)}}
form.panel button{{width:100%;margin-top:24px;padding:11px;border-radius:10px;border:2px solid var(--ac);background:var(--bg2);color:var(--ac);font-weight:900;font-size:15px;cursor:pointer}}
form.panel button:hover{{background:var(--ac);color:#0D1117}}
.msg-error{{background:#2D1115;border:1px solid var(--rojo);color:#FFB4AE;padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:6px}}
.msg-ok{{background:#0F2A1C;border:1px solid #2EA043;color:#7EE2A8;padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:6px}}
.codigo-box{{background:var(--bg);border:2px dashed var(--ac);border-radius:12px;padding:20px;text-align:center;font-size:24px;font-weight:900;letter-spacing:2px;color:var(--ac);margin:18px 0}}
.btn-copiar{{display:inline-flex;align-items:center;gap:6px;background:var(--bg2);color:var(--ac);border:2px solid var(--ac);border-radius:9px;padding:9px 18px;font-weight:900;font-size:13px;cursor:pointer;margin:-4px 0 18px}}
.btn-copiar:hover{{background:var(--ac);color:#0D1117}}
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

/* ── Dinamización (petición explícita, 2026-11-20): la página se veía plana/estática — hover
   real en tarjetas, animación de entrada al hacer scroll, halo decorativo tras el titular y franja
   de confianza + acordeón de preguntas, pensados para transmitir movimiento/cercanía SIN datos
   inventados (ningún contador/testimonio falso: solo hechos reales ya verdaderos hoy). */
.card,.plan{{transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease}}
.card:hover,.plan:hover{{transform:translateY(-5px);box-shadow:0 14px 32px -12px rgba(0,255,198,.28);border-color:var(--ac)}}
.plan.destacado:hover{{box-shadow:0 14px 36px -10px rgba(0,255,198,.42)}}
.btn,.btnnav,.ciclo-toggle button{{transition:background .2s ease,color .2s ease,transform .15s ease,box-shadow .2s ease}}
.btn:hover{{transform:translateY(-2px);box-shadow:0 10px 22px -10px rgba(0,255,198,.45)}}
.reveal{{opacity:0;transform:translateY(22px);transition:opacity .6s ease,transform .6s ease}}
.reveal.in{{opacity:1;transform:translateY(0)}}
.hero-glow{{position:relative}}
.hero-glow::before{{content:"";position:absolute;top:-120px;left:50%;width:640px;height:420px;
  transform:translateX(-50%);background:radial-gradient(closest-side,rgba(0,255,198,.16),transparent 70%);
  filter:blur(10px);z-index:-1;pointer-events:none;animation:smBlob 7s ease-in-out infinite}}
@keyframes smBlob{{0%,100%{{opacity:.75;transform:translateX(-50%) scale(1)}}50%{{opacity:1;transform:translateX(-50%) scale(1.08)}}}}
.trust-strip{{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0 8px}}
.trust-strip span{{background:var(--bg2);border:1px solid var(--bd);border-radius:999px;padding:8px 16px;font-size:13px;color:var(--dim);font-weight:600;display:inline-flex;align-items:center;gap:7px}}
.trust-strip span b{{color:var(--ac)}}
.faq{{margin:30px 0}}
.faq-item{{border:1px solid var(--bd);border-radius:12px;margin-bottom:10px;overflow:hidden;background:var(--bg2)}}
.faq-q{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 20px;cursor:pointer;font-weight:800;font-size:15px;user-select:none}}
.faq-q .ico{{color:var(--ac);font-size:18px;font-weight:900;transition:transform .25s ease;flex:none}}
.faq-item.open .faq-q .ico{{transform:rotate(45deg)}}
.faq-a{{max-height:0;overflow:hidden;transition:max-height .3s ease,padding .3s ease;padding:0 20px;color:var(--dim);font-size:14px}}
.faq-item.open .faq-a{{max-height:260px;padding:0 20px 18px}}
.plan-detalle{{background:var(--bg2);border:1px solid var(--bd);border-radius:18px;padding:32px;margin:26px 0;scroll-margin-top:84px}}
.plan-detalle h3{{color:var(--ac);font-size:22px;margin:0 0 4px}}
.plan-detalle .gancho{{background:rgba(0,255,198,.06);border:1px dashed var(--ac);border-radius:12px;padding:16px 18px;margin-top:18px;font-size:14.5px}}
.plan-detalle .modulos-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px 18px;margin:10px 0 0;padding:0;list-style:none}}
.plan-detalle .modulos-grid li{{padding:10px 12px;background:var(--bg);border:1px solid var(--bd);border-radius:10px;font-size:13.5px}}
.plan-detalle .modulos-grid b{{color:var(--ac);display:block;font-size:14px}}
.plan-detalle .limites-row{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 22px}}
.plan-detalle .limites-row span{{background:var(--bg);border:1px solid var(--bd);border-radius:10px;padding:8px 14px;font-size:13.5px}}
.plan-detalle .limites-row b{{color:var(--ac)}}
.vermas{{display:block;text-align:center;margin-top:14px;font-size:13px;font-weight:700}}
/* Tablas de "Mi cuenta" (petición explícita, 2026-11-20: sin los finos rectángulos grises de
   `.legal table` — esa clase es para las tablas densas de Privacidad/Condiciones, no para estas)
   — solo una línea horizontal fina entre filas, sin rejilla vertical. */
.tabla-cuenta{{border-collapse:collapse;width:100%;font-size:13.5px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-weight:700}}
.tabla-cuenta th{{background:transparent;color:var(--ac);text-align:left;padding:8px 10px;
  border-bottom:2px solid var(--bd);font-size:12.5px;letter-spacing:.2px}}
.tabla-cuenta td{{padding:11px 10px;border-bottom:1px solid var(--bd);text-align:left}}
.tabla-cuenta tbody tr:last-child td{{border-bottom:none}}
/* Reseñas de clientes + comentarios (petición explícita, 2026-11-22): mismo lenguaje visual que
   `.card`/`.tabla-cuenta` — nada de testimonios/contadores inventados, solo lo que de verdad hay
   en `resenas_sitio` (ver su comentario en `_pagina_home`). */
.estrellas{{color:var(--ac);letter-spacing:1px}}
.resena-card{{background:var(--bg2);border:1px solid var(--bd);border-radius:14px;padding:22px;margin-bottom:18px}}
.resena-card .autor{{font-weight:900;font-size:14.5px}}
.resena-card .fecha{{color:var(--dim);font-size:12px}}
.resena-card p.texto{{margin:10px 0 0;font-size:14.5px;color:var(--tx)}}
.comentario{{border-top:1px solid var(--bd);padding:12px 0 0;margin-top:14px}}
.comentario:first-child{{border-top:none;margin-top:16px;padding-top:0}}
.comentario .autor{{font-weight:800;font-size:13px}}
.comentario .fecha{{color:var(--dim);font-size:11px}}
.comentario p{{margin:4px 0 0;font-size:13.5px;color:var(--tx)}}
.form-resena label{{display:block;font-size:13px;font-weight:700;color:var(--dim);margin:14px 0 6px}}
.form-resena select,.form-resena textarea{{width:100%;background:var(--bg);color:var(--tx);border:2px solid var(--bd);border-radius:9px;padding:11px 13px;font-size:14px;font-family:inherit}}
.form-resena select:focus,.form-resena textarea:focus{{outline:none;border-color:var(--ac)}}
.form-resena button{{margin-top:16px;padding:11px 22px;border-radius:10px;border:2px solid var(--ac);background:var(--bg2);color:var(--ac);font-weight:900;font-size:14px;cursor:pointer}}
.form-resena button:hover{{background:var(--ac);color:#0D1117}}
</style></head><body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="/"><img src="/assets/logo.png" alt="" width="28" height="28" loading="eager">Smart<b>Manager</b></a>
  <nav class="links">
    <a href="/">Inicio</a>
    <a href="/precios">Precios</a>
    <a href="/descargas">Descargas</a>
    <a href="{_e(_url_portal_proveedor())}/?desde=web_oficial">Proveedores</a>
    <a href="{_e(_url_portal_empresa())}/?desde=web_oficial">Portal B2B</a>
    {nav_cuenta}
  </nav>
</div></header>
<main>{cuerpo}</main>
<footer><div class="wrap">
  <span>© {__import__('datetime').date.today().year} Smart Manager — ERP cloud de gestión empresarial.</span>
  <span><a href="{_e(_url_portal_proveedor())}/?desde=web_oficial">¿Eres proveedor? Entra aquí</a> · <a href="/opiniones">Opiniones</a> · <a href="/privacidad">Política de Privacidad</a> · <a href="/terminos">Condiciones del Servicio</a> · <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a></span>
</div></footer>
<script>
// Animación de entrada al hacer scroll (`.reveal` -> `.reveal.in`), compartida por todas las
// páginas — degrada con gracia (sin IntersectionObserver, simplemente se ven ya reveladas).
(function() {{
  var els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  if (!('IntersectionObserver' in window)) {{
    els.forEach(function(e) {{ e.classList.add('in'); }});
    return;
  }}
  var io = new IntersectionObserver(function(entries) {{
    entries.forEach(function(en) {{
      if (en.isIntersecting) {{ en.target.classList.add('in'); io.unobserve(en.target); }}
    }});
  }}, {{ threshold: 0.12 }});
  els.forEach(function(e) {{ io.observe(e); }});
}})();
// Acordeón de preguntas frecuentes (compartido — ver `.faq-item`/`.faq-q`/`.faq-a`).
function smFaq(btn) {{
  btn.parentElement.classList.toggle('open');
}}
</script>
</body></html>"""


def _wrap(titulo, body_html, **kw):
    return _layout(titulo, body_html, **kw)


# ── Página de inicio ─────────────────────────────────────────────────────────────────────────
def _pagina_home(sesion, *, tiene_suscripcion=False):
    tarjetas_home = [
        ("🏪", "TPV y ventas", "Punto de venta táctil, autocobro, facturación por centro, campañas CRM y objetivos de productividad en vivo."),
        ("📦", "Stock multi-almacén", "Kárdex por lotes/FEFO, reposición automática, inventario con RFID/lectores Zebra y trazabilidad completa."),
        ("👥", "RRHH y nóminas", "Fichajes, horarios, bolsa de horas, portal del empleado y generación de nóminas, todo integrado con el resto del ERP."),
        ("🧾", "Fiscalidad real", "Verifactu/AEAT con firma y envío real (no una simulación), Facturae y modelos oficiales."),
        ("🤖", "IA y automatización", "Previsión de demanda, reposición inteligente y un asistente de voz (SOMA) para tareas del día a día."),
        ("🔒", "Seguridad por diseño", "MFA/TOTP, control de acceso por rol y centro, cifrado de datos sensibles en reposo y en tránsito (TLS)."),
    ]
    tarjetas_html = "".join(
        f'<div class="card reveal" style="transition-delay:{i * 70}ms"><h3>{ico} {_e(tit)}</h3><p>{_e(desc)}</p></div>'
        for i, (ico, tit, desc) in enumerate(tarjetas_home)
    )

    # Reseñas de clientes reales (petición explícita, 2026-11-22) — la sección entera se oculta si
    # todavía no hay ninguna: mismo criterio que el resto de esta página (ver el comentario sobre
    # "ningún contador/testimonio falso" más arriba), nunca se rellena con ejemplos inventados.
    from src.services import resenas as R
    stats = R.estadisticas()
    seccion_resenas = ""
    if stats["total"] > 0:
        ultimas = R.listar_resenas(limite=3)
        tarjetas_resenas = "".join(
            f'<div class="resena-card reveal" style="transition-delay:{i * 70}ms">'
            f'<div class="estrellas">{_estrellas(r["puntuacion"])}</div>'
            f'<p class="texto">“{_e(r["texto"][:220])}{"…" if len(r["texto"]) > 220 else ""}”</p>'
            f'<div class="autor" style="margin-top:12px">{_e(r["nombre_mostrado"])}</div>'
            f'<div class="fecha">{_fecha_corta(r["creado_en"])}</div></div>'
            for i, r in enumerate(ultimas)
        )
        seccion_resenas = f"""
  <h2 class="reveal" style="margin-top:56px">Lo que dicen nuestros clientes</h2>
  <p class="sub reveal">{stats['media']} de 5 · {stats['total']} opinion{'es' if stats['total'] != 1 else ''} de
  clientes reales.</p>
  <div class="grid3">{tarjetas_resenas}</div>
  <a class="vermas" href="/opiniones">Ver todas las opiniones →</a>"""

    cuerpo = f"""
<div class="wrap hero-glow">
  <h1>El ERP cloud que une<br><span>tienda, almacén y oficina</span> en un solo sitio.</h1>
  <p class="sub">Smart Manager gestiona TPV, stock multi-almacén, compras, ventas, RRHH, CRM,
  facturación (Verifactu/AEAT) y mucho más — todo sincronizado en tiempo real entre tus centros,
  tu equipo y tu móvil.</p>
  <div class="cta-row">
    <a class="btn btn-primary" href="/precios">Ver planes y precios</a>
    {'<a class="btn btn-ghost" href="/descargas">Descargar la app</a>' if tiene_suscripcion else ""}
  </div>
  <div class="trust-strip">
    <span>🔒 Pago seguro con <b>Stripe</b> o <b>PayPal</b></span>
    <span>📅 <b>Sin permanencia</b> — cancela cuando quieras</span>
    <span>🗣️ Soporte en <b>español</b></span>
    <span>⚡ Alta en minutos, sin instalación de servidores</span>
  </div>
  <div class="grid3">{tarjetas_html}</div>
  {seccion_resenas}
</div>"""
    return _wrap("Smart Manager — ERP cloud de gestión empresarial", cuerpo, sesion=sesion)


# ── Precios ──────────────────────────────────────────────────────────────────────────────────
_ETIQUETAS_LIMITE = [
    ("max_tiendas", "centro{s} / tienda{s}"), ("max_usuarios", "usuario{s}"),
    # Plurales irregulares (la tilde se pierde al pluralizar: almacén→almacenes, buzón→buzones) —
    # un sufijo "{es}" sobre la raíz acentuada los escribía mal ("almacénes"/"buzónes").
    ("max_almacenes", ("almacén", "almacenes")),
    ("max_correos", ("buzón de correo", "buzones de correo")),
]


# Descripción de una línea por módulo (petición explícita, 2026-11-20: "qué son los módulos" en
# el resumen detallado de cada plan) — mismos 26 códigos/nombres que `planes.MODULOS`, fuente
# única; si algún día se añade un módulo nuevo ahí sin actualizar esto, `_resumen_plan` degrada
# mostrando solo el nombre, nunca rompe.
_DESC_MODULOS = {
    "tpv": "Punto de venta táctil, autocobro, caja y tickets/facturas simplificadas.",
    "ventas": "Analítica de ventas, objetivos de productividad y rendimiento por empleado/centro.",
    "compras": "Pedidos a proveedor, recepción de palets y control de albaranes.",
    "inventario": "Stock multi-almacén, kárdex, lotes/caducidades (FEFO) y reposición.",
    "clientes": "Ficha de cliente, historial de compra y CRM con campañas y seguimiento.",
    "proveedores": "Portal B2B de proveedores integrado, con 0% de comisión en los pedidos.",
    "facturacion": "Emisión de facturas de venta y gestión de la facturación del negocio.",
    "correo": "Buzones de correo corporativo propios, integrados con el resto del ERP.",
    "rrhh": "Fichajes, horarios, bolsa de horas, vacaciones y portal del empleado.",
    "tesoreria": "Previsión de cobros/pagos, remesas bancarias y conciliación.",
    "workflow": "Tareas y programador de trabajos (jobs) recurrentes o encargados a tu equipo.",
    "scheduler": "Automatizaciones programadas (horarios/eventos) que se ejecutan solas.",
    "comunicaciones": "Circulares, encuestas y avisos internos a todo el equipo.",
    "bi": "Centro de Inteligencia: dashboards ejecutivos, gemelo digital y simulador.",
    "contabilidad": "Contabilidad general y presentación de modelos oficiales (AEAT).",
    "aeat": "Modelos fiscales oficiales de la Agencia Tributaria, listos para presentar.",
    "verifactu": "Facturación verificable (Verifactu) con firma y envío real a la AEAT.",
    "facturae": "Facturación electrónica estructurada (Facturae), para grandes clientes/AAPP.",
    "branding": "Imagen propia (logo/colores) en documentos, tickets y el Canal Web.",
    "multiempresa": "Gestión de varias empresas/razones sociales desde una misma cuenta.",
    "api": "API REST completa para integrar Smart Manager con otras herramientas.",
    "conectores": "Conectores premium con plataformas externas (marketplaces, ERPs, etc.).",
    "automatizaciones": "Sugerencias y planes de automatización que tu equipo solo aprueba.",
    "admin_delegada": "Delega la administración de módulos concretos sin dar acceso total.",
    "forecasting": "Previsión de demanda con IA y reposición inteligente automática.",
    "comparativas": "Comparativas de rendimiento entre varias empresas del mismo grupo.",
}

# Gancho de cierre persuasivo, UNO por plan (petición explícita: "convencer al cliente y guiarlo
# para que elija el plan que más le convenga") — vive aquí, no dentro de `_resumen_plan`, para que
# el texto comercial de cada plan quede junto y sea fácil de revisar/ajustar de un vistazo.
_GANCHO_PLAN = {
    "BASIC": ("Si estás empezando o llevas un único negocio, <b>Basic</b> te da todo lo "
              "imprescindible para operar desde el primer día — sin pagar por nada que todavía no "
              "necesitas. Y si tu negocio crece, cambiar a Plus o Pro es inmediato, sin perder "
              "nada de lo que ya tengas configurado."),
    "PLUS": ("<b>Plus</b> es el plan que elige la mayoría: suficiente margen para varios centros "
             "y un equipo en crecimiento, con RRHH, Contabilidad, BI y fiscalidad avanzada ya "
             "incluidos — todo lo que necesitas para profesionalizar la gestión sin pasar "
             "todavía al nivel Enterprise."),
    "PRO": ("Si gestionas una cadena, un grupo de empresas o simplemente no quieres pensar en "
            "límites nunca más, <b>Pro</b> te da acceso ilimitado a todo Smart Manager — API "
            "completa, conectores premium, marca propia y comparativas entre tus empresas, con "
            "soporte prioritario."),
}


def _resumen_plan(codigo, cfg) -> str:
    """Resumen detallado del plan (petición explícita, 2026-11-20): características/límites,
    módulos incluidos (con una línea de qué hace cada uno) y un gancho de cierre persuasivo —
    pensado para desplegarse bajo demanda ("Ver más información" en la tarjeta) sin repetir
    contenido entre el ciclo mensual/anual de un MISMO plan (ambas tarjetas apuntan al mismo
    resumen — el plan es el mismo, solo cambia cómo se factura)."""
    from src.services.saas import planes as _P
    limites = cfg["limites"]
    limites_html = "".join(
        f"<span><b>{n if n < 9999 else '∞'}</b> {_plural(n, plantilla)}</span>"
        for clave, plantilla in _ETIQUETAS_LIMITE
        for n in [limites.get(clave, 0)]
    )
    modulos_html = "".join(
        f'<li><b>{_e(_P.MODULOS.get(m, m))}</b>{_e(_DESC_MODULOS.get(m, ""))}</li>'
        for m in cfg["modulos"]
    )
    precio_mes = cfg["precio"]
    precio_anual = cfg.get("precio_anual")
    precios_html = (
        f'<span><b>{precio_mes:.0f}€</b>/mes + IVA</span>'
        f'<span><b>{precio_anual:.0f}€</b>/año + IVA <i style="color:var(--dim);font-style:normal">'
        f'(ahorras {precio_mes * 12 - precio_anual:.0f}€/año)</i></span>'
    ) if precio_mes else '<span><b>Gratis</b></span>'
    gancho = _GANCHO_PLAN.get(codigo, "")
    # Oculto por defecto (petición explícita: "Ver más información" DESPLIEGA el resumen, no es
    # solo un ancla a contenido ya visible) — `smVerMas` lo revela y hace scroll hasta aquí.
    return f"""<div class="plan-detalle reveal" id="detalle-{codigo.lower()}" hidden>
      <h3>{_e(cfg['nombre'])}</h3>
      <p class="sub" style="margin-bottom:4px">Características y límites del plan:</p>
      <div class="limites-row">{limites_html}</div>
      <p class="sub" style="margin-bottom:4px">Módulos incluidos ({len(cfg['modulos'])} de {len(_P.MODULOS)}) —
      cada módulo es un área funcional del ERP (ventas, stock, RRHH, fiscalidad…) que se activa
      sola al contratar el plan y que se integra en tiempo real con el resto:</p>
      <ul class="modulos-grid">{modulos_html}</ul>
      <p class="sub" style="margin:18px 0 4px">Precio:</p>
      <div class="limites-row">{precios_html}</div>
      <div class="gancho">💡 {gancho}</div>
      <div class="cta-row">
        <a class="btn btn-primary" href="/registro?plan={codigo.lower()}&ciclo=mensual">Elegir {_e(cfg['nombre'])} mensual</a>
        <a class="btn btn-ghost" href="/registro?plan={codigo.lower()}&ciclo=anual">Elegir {_e(cfg['nombre'])} anual</a>
      </div>
    </div>"""


def _plural(n, forma):
    if n >= 9999:
        return "ilimitados"
    if isinstance(forma, tuple):
        singular, plural = forma
        return singular if n == 1 else plural
    return forma.format(s="s" if n != 1 else "", es="es" if n != 1 else "")


def _tarjeta_plan(codigo, cfg, *, destacado=False, ciclo="mensual"):
    from src.services.saas import planes as _P
    limites = cfg["limites"]
    filas = []
    for clave, plantilla in _ETIQUETAS_LIMITE:
        n = limites.get(clave, 0)
        filas.append(f"<li><b>{n if n < 9999 else '∞'}</b> {_plural(n, plantilla)}</li>")
    filas.append(f"<li><b>{len(cfg['modulos'])}</b> módulos incluidos</li>")
    precio_mes = cfg["precio"]
    ahorro_html = ""
    if precio_mes == 0:
        precio_html = "Gratis"
    elif ciclo == "anual":
        precio_anual = cfg["precio_anual"]
        precio_anual_como_mensual = precio_mes * 12
        ahorro = precio_anual_como_mensual - precio_anual
        precio_html = f"{precio_anual:.0f}€<small>/año + IVA</small>"
        # Equivalencia en meses gratis (petición explícita, 2026-11-16: dato atractivo de cara al
        # cliente, en la MISMA línea que el importe anual entre paréntesis) — calculada
        # dinámicamente a partir del ahorro real, nunca hardcodeada a "2 meses": sigue siendo
        # correcta si `precio_anual` cambiara en el futuro y dejara de ser exactamente 10 meses
        # por 12. Resaltado en amarillo chillón (petición explícita) para que destaque sobre el
        # resto del texto de ahorro (color normal de `.ahorro`, cian).
        meses_gratis = ahorro / precio_mes if precio_mes else 0
        meses_txt = f"{meses_gratis:.0f}" if meses_gratis == int(meses_gratis) else f"{meses_gratis:.1f}"
        meses_lbl = "mes gratis" if meses_gratis == 1 else "meses gratis"
        ahorro_html = (f'<p class="ahorro">Ahorras {ahorro:.0f}€/año frente al mensual '
                      f'({precio_anual_como_mensual:.0f}€/año) '
                      f'<b style="color:#FFE600">**{meses_txt} {meses_lbl}**</b></p>')
    else:
        precio_html = f"{precio_mes:.0f}€<small>/mes + IVA</small>"
    badge = '<span class="badge">MÁS ELEGIDO</span>' if destacado else ""
    # Gancho de prueba gratuita (petición explícita, 2026-11-22): 7 días gratis para nuevos
    # clientes en los 6 planes (3 planes × mensual/anual) — breve y directo, redactado para
    # convertir, no para explicar (las condiciones completas viven en /terminos). No se muestra en
    # un plan Gratis (no hay nada que "probar" antes de pagar).
    badge_prueba = ('<p class="ahorro" style="color:#3FB950;font-weight:900">🎁 7 días gratis '
                    'para nuevos clientes</p>' if precio_mes else "")
    # Insignia del Portal B2B (petición explícita, 2026-11-16): SOLO si el plan incluye de forma
    # nativa el módulo "proveedores" (Smart Suppliers/Portal B2B) — comprobación dinámica contra
    # `planes.PLANES[...]["modulos"]`, nunca una lista de planes hardcodeada, para que siga siendo
    # correcta aunque cambie en el futuro qué plan incluye el módulo.
    badge_b2b = ('<span class="badge-b2b">✓ Portal B2B con 0% de comisión</span>'
                if "proveedores" in cfg["modulos"] else "")
    cls = "plan destacado" if destacado else "plan"
    # El plan BASIC comparte el nombre comercial "Smart Manager" con el producto en general — en
    # el botón se distingue añadiendo "Basic" (petición explícita); el resto de planes ya llevan
    # su propio nombre distintivo (Plus/Pro) y no lo necesitan.
    etiqueta_boton = f"{cfg['nombre']} Basic" if codigo == "BASIC" else cfg['nombre']
    # "Ver más información" (petición explícita, 2026-11-20): texto clicable (sin estilo de botón;
    # subrayado SOLO al pasar el cursor, el comportamiento por defecto de cualquier `<a>` de esta
    # web — ver regla global `a`/`a:hover`) que despliega y baja hasta el resumen detallado de
    # ESTE plan (`_resumen_plan`, más abajo en la misma página) — el mismo resumen para el ciclo
    # mensual y el anual de un plan: es el MISMO plan, solo cambia cómo se factura.
    cod_min = codigo.lower()
    ver_mas = (f'<a class="vermas" href="#detalle-{cod_min}" '
               f'onclick="smVerMas(\'{cod_min}\');return false;">Ver más información ↓</a>')
    return f"""<div class="{cls}">{badge}{badge_b2b}
      <h3>{_e(cfg['nombre'])}</h3>
      <div class="precio">{precio_html}</div>
      {badge_prueba}
      {ahorro_html}
      <ul>{''.join(filas)}</ul>
      <a class="btn btn-primary" href="/registro?plan={codigo.lower()}&ciclo={ciclo}">Elegir {_e(etiqueta_boton)}</a>
      {ver_mas}
    </div>"""


# Preguntas frecuentes (petición explícita, 2026-11-20: dinamizar la web/mejorar la conversión) —
# objeciones reales de un cliente a punto de contratar, con respuestas honestas (nada se inventa:
# cada respuesta describe un comportamiento real ya construido — autoservicio desde "Mi cuenta",
# aviso de límite de plan con invitación a mejorar, Stripe como pasarela, sin servidor propio).
_FAQ_PRECIOS = [
    ("¿Hay permanencia o contrato mínimo?",
     "No. Puedes cancelar tu suscripción cuando quieras desde \"Mi cuenta\" en la web oficial, "
     "sin compromisos ni letra pequeña."),
    ("¿Puedo cambiar de plan o de ciclo más adelante?",
     "Sí, en cualquier momento desde \"Mi cuenta\" — el cambio se aplica de inmediato, sin perder "
     "ninguna configuración ni dato de tu empresa."),
    ("¿Qué pasa si supero el límite de mi plan (centros, usuarios, almacenes o buzones)?",
     "La propia app te avisa en el momento e invita a mejorar de plan — nunca se bloquea ni se "
     "pierde información; simplemente no se puede dar de alta uno más hasta ampliar el límite."),
    ("¿Es seguro el pago?",
     "Sí: eliges pagar con Stripe o con PayPal, dos de las pasarelas más usadas del mundo — Smart "
     "Manager nunca ve ni almacena los datos de tu tarjeta ni de tu cuenta de PayPal."),
    ("¿Necesito instalar o mantener un servidor propio?",
     "No. Smart Manager es 100% cloud — solo instalas la app de escritorio en tus ordenadores o "
     "TPVs; nosotros nos encargamos de la base de datos, las copias de seguridad y las "
     "actualizaciones."),
]


def _pagina_precios(sesion):
    from src.services.saas import planes as _P
    tarjetas_mensual = (
        _tarjeta_plan("BASIC", _P.PLANES["BASIC"], ciclo="mensual")
        + _tarjeta_plan("PLUS", _P.PLANES["PLUS"], destacado=True, ciclo="mensual")
        + _tarjeta_plan("PRO", _P.PLANES["PRO"], ciclo="mensual")
    )
    tarjetas_anual = (
        _tarjeta_plan("BASIC", _P.PLANES["BASIC"], ciclo="anual")
        + _tarjeta_plan("PLUS", _P.PLANES["PLUS"], destacado=True, ciclo="anual")
        + _tarjeta_plan("PRO", _P.PLANES["PRO"], ciclo="anual")
    )
    detalles_html = (
        _resumen_plan("BASIC", _P.PLANES["BASIC"])
        + _resumen_plan("PLUS", _P.PLANES["PLUS"])
        + _resumen_plan("PRO", _P.PLANES["PRO"])
    )
    faq_html = "".join(
        f'<div class="faq-item"><div class="faq-q" onclick="smFaq(this)">{_e(preg)}'
        f'<span class="ico">+</span></div><div class="faq-a"><p>{_e(resp)}</p></div></div>'
        for preg, resp in _FAQ_PRECIOS
    )
    cuerpo = f"""
<div class="wrap">
  <h1>Planes simples, <span>sin sorpresas</span></h1>
  <p class="sub">Un único precio por empresa, sin coste por puesto adicional dentro de tu
  límite de plan. Cambia de plan o de ciclo cuando quieras desde "Mi cuenta".</p>
  <div class="trust-strip">
    <span>🎁 <b>7 días gratis</b> para nuevos clientes</span>
    <span>🔒 Pago seguro con <b>Stripe</b> o <b>PayPal</b></span>
    <span>📅 <b>Sin permanencia</b> — cancela cuando quieras</span>
    <span>↕️ Cambia de plan <b>cuando quieras</b></span>
    <span>🗣️ Soporte en <b>español</b></span>
  </div>
  <div class="ciclo-toggle">
    <button type="button" id="btn-mensual" class="active" onclick="smCiclo('mensual')">Mensual</button>
    <button type="button" id="btn-anual" onclick="smCiclo('anual')">Anual <span class="badge-ahorro">2 meses gratis</span></button>
  </div>
  <div class="grid3 sm-anim-in" id="grid-mensual">{tarjetas_mensual}</div>
  <div class="grid3" id="grid-anual" hidden>{tarjetas_anual}</div>
  <script>
  var smCicloActual = 'mensual';
  var smCicloAnimando = false;
  function smCiclo(c) {{
    if (c === smCicloActual || smCicloAnimando) return;
    smCicloAnimando = true;
    var viejo = document.getElementById('grid-' + smCicloActual);
    var nuevo = document.getElementById('grid-' + c);
    document.getElementById('btn-mensual').classList.toggle('active', c === 'mensual');
    document.getElementById('btn-anual').classList.toggle('active', c === 'anual');
    viejo.classList.remove('sm-anim-in');
    viejo.classList.add('sm-anim-out');
    setTimeout(function() {{
      viejo.hidden = true;
      viejo.classList.remove('sm-anim-out');
      nuevo.hidden = false;
      nuevo.classList.add('sm-anim-in');
      smCicloActual = c;
      setTimeout(function() {{ nuevo.classList.remove('sm-anim-in'); smCicloAnimando = false; }}, 350);
    }}, 250);
  }}
  // "Ver más información" (petición explícita): revela el resumen detallado de ESE plan (oculto
  // por defecto, ver `_resumen_plan`) y baja la página sola hasta él.
  function smVerMas(codigo) {{
    var el = document.getElementById('detalle-' + codigo);
    if (!el) return;
    if (el.hidden) {{ el.hidden = false; el.classList.add('in'); }}
    el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
  }}
  </script>
  <div class="recomendador">
    <h3>¿No sabes cuál elegir?</h3>
    <ul>
      <li><b>Basic</b> — ideal para un autónomo o una única tienda que empieza: TPV, stock,
      compras/ventas y facturación básica con hasta 3 usuarios.</li>
      <li><b>Plus</b> — la opción más elegida: negocios con varios centros (hasta 10 tiendas) o que
      necesitan RRHH, contabilidad, Business Intelligence y fiscalidad avanzada (Verifactu/AEAT).</li>
      <li><b>Pro</b> — cadenas y grupos empresariales sin límite de tiendas/usuarios, con API completa,
      conectores premium, branding propio y comparativas multiempresa.</li>
    </ul>
  </div>
  <h2 class="reveal" style="margin-top:50px">En detalle: qué incluye cada plan</h2>
  <p class="sub reveal">Pulsa "Ver más información" en cualquier tarjeta de arriba para venir
  directamente aquí, o consulta los tres a continuación.</p>
  {detalles_html}
  <h2 class="reveal" style="margin-top:50px">Preguntas frecuentes</h2>
  <div class="faq reveal">{faq_html}</div>
</div>"""
    return _wrap("Precios y planes", cuerpo, sesion=sesion)


# ── Registro / alta ──────────────────────────────────────────────────────────────────────────
def _pagina_registro(plan, ciclo="mensual", error=None, email="", origen=""):
    from src.services.saas import planes as _P
    cfg = _P.PLANES.get(plan.upper())
    if not cfg:
        plan, cfg = "BASIC", _P.PLANES["BASIC"]
    ciclo = "anual" if ciclo == "anual" else "mensual"
    es_gratis = cfg["precio"] == 0
    bloque_financiacion = ""
    if es_gratis:
        aviso_pago = ""
    elif ciclo == "anual":
        aviso_pago = (
            f'<p style="color:var(--dim);font-size:13px;margin-top:16px">Tras enviar este formulario te '
            f'llevaremos a la pasarela de pago segura que elijas para domiciliar la cuota anual '
            f'({cfg["precio_anual"]:.0f}€/año + IVA). No se te cobra nada hasta confirmar el pago.</p>'
        )
        # Financiación en 4 cuotas trimestrales (petición explícita, 2026-11-22, reconsiderada el
        # mismo día: el periodo de prueba de 7 días se mantiene TAMBIÉN al financiar — ya no es
        # mutuamente excluyente). SOLO para planes anuales de pago. Sin intereses: cada cuota es
        # exactamente precio_anual_financiado/4 (petición explícita, 2026-11-27: financiar cuesta
        # un poco más que pagar de golpe — 1 mes de descuento en vez de 2, ver `services.saas.
        # planes`). La PRIMERA cuota se cobra al terminar los 7 días de prueba (no en el acto) —
        # ver la fase de prueba del `SubscriptionSchedule` en `services.alta_comercial.
        # confirmar_financiacion`. El checkbox de compromiso legal es obligatorio SOLO si se marca
        # financiar (gestionado con JS: `required` se activa/desactiva según el estado de la
        # casilla).
        cuota = cfg["precio_anual_financiado"] / 4
        bloque_financiacion = f"""
    <label style="font-weight:400;margin-top:18px">
      <input type="checkbox" name="financiar" id="chk-financiar" value="1"
        style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
      Financiar en 4 cuotas trimestrales de {cuota:.2f}€ + IVA, sin intereses
    </label>
    <div id="bloque-compromiso-financiacion" hidden
      style="background:var(--bg);border:1px solid var(--bd);border-radius:10px;padding:14px;margin-top:8px">
      <p style="color:var(--dim);font-size:13px;margin:0 0 10px">
        Tienes los mismos <b>7 días de prueba gratis</b> antes de que se cobre nada. Si sigues
        adelante, se te cobrará la primera cuota ({cuota:.2f}€ + IVA) al terminar la prueba, y una
        cuota igual cada 3 meses hasta completar las 4 — un total de
        {cfg['precio_anual_financiado']:.0f}€ + IVA (un poco más que los {cfg['precio_anual']:.0f}€
        + IVA de pagar el año de golpe, por el hecho de financiar). Condiciones completas en las
        <a href="/terminos" target="_blank">Condiciones del Servicio</a>.</p>
      <label style="font-weight:400">
        <input type="checkbox" name="acepta_financiacion" id="chk-acepta-financiacion" value="1"
          style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
        Me comprometo a pagar las 4 cuotas hasta completar el importe anual total.
      </label>
    </div>
    <script>
    (function() {{
      var chk = document.getElementById('chk-financiar');
      var bloque = document.getElementById('bloque-compromiso-financiacion');
      var acepta = document.getElementById('chk-acepta-financiacion');
      if (!chk || !bloque || !acepta) return;
      chk.addEventListener('change', function() {{
        bloque.hidden = !chk.checked;
        acepta.required = chk.checked;
        if (!chk.checked) acepta.checked = false;
      }});
    }})();
    </script>"""
    else:
        aviso_pago = (
            f'<p style="color:var(--dim);font-size:13px;margin-top:16px">Tras enviar este formulario te '
            f'llevaremos a la pasarela de pago segura que elijas para domiciliar la cuota mensual '
            f'({cfg["precio"]:.0f}€/mes + IVA). No se te cobra nada hasta confirmar el pago.</p>'
        )
    # Elección de pasarela (petición explícita, 2026-11-23: PayPal como alternativa a Stripe
    # también en la web oficial, no solo en los portales B2B) — ambas ofrecen las mismas
    # condiciones (prueba de 7 días, financiación en 4 cuotas si es anual).
    bloque_pasarela = "" if es_gratis else f"""
    <label>Método de pago</label>
    <label style="font-weight:400;margin-top:0">
      <input type="radio" name="metodo_pago" value="stripe" checked
        style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
      Tarjeta (Stripe)
    </label>
    <label style="font-weight:400">
      <input type="radio" name="metodo_pago" value="paypal"
        style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
      PayPal
    </label>"""
    error_html = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap">
  <h2 style="text-align:center">Crear cuenta — plan {_e(cfg['nombre'])} ({"anual" if ciclo == "anual" else "mensual"})</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
    <a href="/precios">← Cambiar de plan</a></p>
  <form class="panel" method="post" action="/registro" id="form-registro">
    <input type="hidden" name="plan" value="{_e(plan.lower())}">
    <input type="hidden" name="ciclo" value="{_e(ciclo)}">
    <input type="hidden" name="origen" value="{_e(origen)}">
    {error_html}
    <label>Nombre de la empresa</label>
    <input name="nombre_empresa" required maxlength="255" placeholder="Mi Empresa S.L.">
    <label>Email</label>
    <input type="email" name="email" required maxlength="255" placeholder="tu@empresa.com" value="{_e(email)}">
    <label>Crea una contraseña</label>
    <input type="password" name="password" id="password" required minlength="8" placeholder="Mínimo 8 caracteres">
    <label>Repite la contraseña</label>
    <input type="password" name="password2" id="password2" required minlength="8" placeholder="Repite la contraseña">
    <p id="msg-password-no-coincide" class="msg-error" hidden>Las contraseñas no coinciden.</p>
    {bloque_pasarela}
    {aviso_pago}
    {bloque_financiacion}
    <button type="submit">{"Crear cuenta gratis" if es_gratis else "Continuar al pago"}</button>
  </form>
  <script>
  document.getElementById('form-registro').addEventListener('submit', function(ev) {{
    var p1 = document.getElementById('password').value;
    var p2 = document.getElementById('password2').value;
    var aviso = document.getElementById('msg-password-no-coincide');
    if (p1 !== p2) {{ ev.preventDefault(); aviso.hidden = false; }}
    else {{ aviso.hidden = true; }}
  }});
  </script>
  <p style="text-align:center;color:var(--dim);font-size:13px;margin-top:18px">
    Al continuar aceptas las <a href="/terminos">Condiciones del Servicio</a> y la
    <a href="/privacidad">Política de Privacidad</a>. ¿Ya tienes cuenta? <a href="/login">Inicia sesión</a>.</p>
</div>"""
    return _wrap(f"Crear cuenta · {cfg['nombre']}", cuerpo)


def _pagina_verificar_email(email, *, error=None):
    """Paso OBLIGATORIO antes de completar cualquier alta (petición explícita, 2026-11-22): se
    envía un código de 6 dígitos al email introducido y hay que confirmarlo aquí — los datos
    pendientes del registro (plan/ciclo/empresa/password ya hasheada) viajan en la cookie de
    sesión firmada (`session["pendiente_registro"]`, mismo patrón ya usado para
    `pendiente_checkout`), nunca se vuelven a pedir."""
    error_html = f'<div class="msg-error">{_e(error)}</div>' if error else ""
    cuerpo = f"""
<div class="wrap" style="max-width:440px">
  <h2 style="text-align:center">Verifica tu email</h2>
  <p class="sub" style="text-align:center;margin-left:auto;margin-right:auto">
    Te hemos enviado un código de 6 dígitos a <b>{_e(email)}</b>. Introdúcelo para completar tu registro.</p>
  <form class="panel" method="post" action="/registro/verificar-email">
    {error_html}
    <label>Código de verificación</label>
    <input name="codigo" required maxlength="6" minlength="6" inputmode="numeric" pattern="[0-9]{{6}}"
      autocomplete="one-time-code" placeholder="123456" autofocus>
    <button type="submit">Verificar y continuar</button>
  </form>
  <form method="post" action="/registro/reenviar-codigo" style="text-align:center;margin-top:14px">
    <button type="submit" class="btn btn-ghost" style="padding:8px 18px;font-size:13px">Reenviar código</button>
  </form>
</div>"""
    return _wrap("Verifica tu email", cuerpo)


def _pagina_resultado_alta(codigo, plan, *, nuevo=True, proximo_cobro=None, ciclo="mensual"):
    nota = "" if nuevo else '<p style="color:var(--dim);font-size:13px">(Este Checkout ya se había confirmado antes — aquí tienes tu código de nuevo.)</p>'
    # Fecha exacta de caducidad/renovación (petición explícita, 2026-11-16): el cobro es
    # automático y recurrente (Stripe renueva la suscripción solo — nunca hay que volver a pagar a
    # mano) hasta que la propia empresa la cancele; esta es la fecha en la que Stripe volverá a
    # cobrar automáticamente y a extender la suscripción.
    aviso_renovacion = ""
    if proximo_cobro:
        periodo = "año" if ciclo == "anual" else "mes"
        aviso_renovacion = (
            f'<p class="sub" style="margin:0 auto 10px">Tu suscripción se renueva '
            f'<b>automáticamente cada {periodo}</b> — el próximo cobro (y renovación) será el '
            f'<b>{_e(proximo_cobro.strftime("%d/%m/%Y") if hasattr(proximo_cobro, "strftime") else proximo_cobro)}</b>. '
            f'No tienes que hacer nada; solo si quieres cancelarla, puedes hacerlo cuando quieras '
            f'desde "Mi cuenta → Gestionar suscripción y facturas".</p>')
    cuerpo = f"""
<div class="wrap" style="max-width:540px;text-align:center">
  <h2>🎉 ¡Todo listo!</h2>
  <p class="sub" style="margin:0 auto 10px">Tu plan <b>{_e(plan)}</b> está activo. Este es tu código
  de instalación — válido 7 días:</p>
  {aviso_renovacion}
  <div class="codigo-box" id="codigo-instalacion">{_e(codigo)}</div>
  <button type="button" class="btn-copiar" id="btn-copiar-codigo"
    onclick="navigator.clipboard.writeText(document.getElementById('codigo-instalacion').textContent.trim()).then(function(){{
      var b=document.getElementById('btn-copiar-codigo'); var t=b.textContent; b.textContent='✓ Copiado';
      setTimeout(function(){{ b.textContent=t; }}, 1800);
    }})">📋 Copiar código</button>
  {nota}
  <p class="sub" style="margin:0 auto 6px">Tras instalar y abrir la app por primera vez, verás la
  pantalla <b>"Configuración inicial"</b>: pega ahí este código (el campo "Servidor" ya viene
  relleno correctamente, no hay que tocarlo) y pulsa "Configurar este ordenador".</p>
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
    <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a> y te damos de alta
    manualmente mientras tanto.</p>
</div>"""
    return _wrap("Pago no disponible", cuerpo)


# ── PayPal como alternativa a Stripe (petición explícita, 2026-11-23) ───────────────────────────
# Suscripciones reales de PayPal (`/v1/billing/*`), NO el PayPal marketplace de los portales B2B
# (`tpv.pagos.paypal_connect`) — aquí Smart Manager cobra DIRECTAMENTE en su propia cuenta (como
# hace Stripe para estas mismas suscripciones), nada de custodia ni reparto de comisiones.
#
# Los 6 planes normales (3 planes × 2 ciclos) usan un Plan de PayPal YA CREADO de antemano
# (`PAYPAL_PLAN_ID_<PLAN>[_ANUAL]`, mismo criterio que `STRIPE_PRICE_ID_*`) — cada uno con sus DOS
# ciclos de facturación ya definidos (prueba de 7 días a 0€ + el ciclo normal), así PayPal gestiona
# solo el prorrateo/ancla de facturación al terminar la prueba, sin que haga falta calcularlo aquí
# (a diferencia de Stripe, que si necesita el `billing_cycle_anchor` manual — ver
# `_completar_registro`). La financiación en 4 cuotas SÍ crea su Plan al vuelo (como la Price
# dinámica de Stripe) porque la cuota es `precio_anual/4`, no un precio fijo de catálogo.
def _paypal_base():
    return ("https://api-m.sandbox.paypal.com" if os.environ.get("PAYPAL_MODO", "test") != "live"
           else "https://api-m.paypal.com")


def _paypal_token():
    import requests
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    try:
        r = requests.post(f"{_paypal_base()}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(client_id, client_secret), timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("PayPal token (web) %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("_paypal_token: %s", e)
    return None


def _paypal_crear_plan_financiacion(token, *, plan, cuota):
    """Crea un Producto + Plan de PayPal AL VUELO para la financiación en 4 cuotas (equivalente al
    `stripe.Price.create` dinámico de `alta_comercial.confirmar_financiacion`).

    Hallazgo real (2026-11-27, probado contra la API real de PayPal antes de desplegar el
    equivalente de `services/portal_plan.py`): el diseño original de aquí (prueba de 7 días → 4
    cuotas trimestrales → el precio anual para siempre, es decir DOS `billing_cycles` REGULAR)
    NUNCA habría funcionado — PayPal lo rechaza con 422 `MULTIPLE_REGULAR_BILLING_CYCLE_NOT_
    SUPPORTED` ("Only one regular billing cycle is allowed"). Este código no se había probado en
    vivo hasta ahora (`PAYPAL_CLIENT_ID` nunca se había configurado en producción antes). Ahora:
    prueba de 7 días a 0€ → `cuota` cada 3 meses PARA SIEMPRE (un único ciclo REGULAR, válido). El
    coste total por año es idéntico a pagar `precio_anual` de una vez (`cuota*4`); la diferencia
    real es que la financiación trimestral continúa cada año en vez de volver a un único pago
    anual a partir del segundo año (a diferencia de la versión Stripe, con `SubscriptionSchedule`
    de 2 fases, que no tiene esta limitación). Devuelve el `plan_id` o None si algo falla (degrada
    a `_pagina_pago_no_disponible`, nunca finge un plan)."""
    import requests
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        rp = requests.post(f"{_paypal_base()}/v1/catalogs/products", headers=headers, timeout=25,
                           json={"name": f"Smart Manager {plan} (financiado)", "type": "SERVICE",
                                "category": "SOFTWARE"})
        if rp.status_code not in (200, 201):
            logger.warning("PayPal crear producto (financiación) %s: %s", rp.status_code, rp.text[:200])
            return None
        product_id = rp.json().get("id")
        billing_cycles = [
            {"tenure_type": "TRIAL", "sequence": 1, "total_cycles": 1,
             "frequency": {"interval_unit": "DAY", "interval_count": 7},
             "pricing_scheme": {"fixed_price": {"value": "0.00", "currency_code": "EUR"}}},
            {"tenure_type": "REGULAR", "sequence": 2, "total_cycles": 0,
             "frequency": {"interval_unit": "MONTH", "interval_count": 3},
             "pricing_scheme": {"fixed_price": {"value": f"{cuota:.2f}", "currency_code": "EUR"}}},
        ]
        r = requests.post(f"{_paypal_base()}/v1/billing/plans", headers=headers, timeout=25, json={
            "product_id": product_id, "name": f"Smart Manager {plan} — financiado en 4 cuotas",
            "billing_cycles": billing_cycles,
            "payment_preferences": {"auto_bill_outstanding": True,
                                    "payment_failure_threshold": 3},
        })
        if r.status_code not in (200, 201):
            logger.warning("PayPal crear plan (financiación) %s: %s", r.status_code, r.text[:200])
            return None
        return r.json().get("id")
    except Exception as e:
        logger.error("_paypal_crear_plan_financiacion: %s", e)
        return None


def _paypal_crear_suscripcion(token, *, plan_id, email, return_url, cancel_url):
    """Devuelve {ok, subscription_id, approve_url} o {ok: False}."""
    import requests
    try:
        r = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=25,
            json={
                "plan_id": plan_id, "subscriber": {"email_address": email},
                "application_context": {
                    "brand_name": "Smart Manager", "locale": "es-ES",
                    "shipping_preference": "NO_SHIPPING", "user_action": "SUBSCRIBE_NOW",
                    "return_url": return_url, "cancel_url": cancel_url,
                },
            })
        if r.status_code not in (200, 201):
            logger.warning("PayPal crear suscripción %s: %s", r.status_code, r.text[:200])
            return {"ok": False}
        j = r.json()
        approve_url = next((l.get("href") for l in j.get("links", []) if l.get("rel") == "approve"), None)
        if not approve_url:
            return {"ok": False}
        return {"ok": True, "subscription_id": j.get("id"), "approve_url": approve_url}
    except Exception as e:
        logger.error("_paypal_crear_suscripcion: %s", e)
        return {"ok": False}


def _paypal_obtener_suscripcion(token, subscription_id):
    import requests
    try:
        r = requests.get(f"{_paypal_base()}/v1/billing/subscriptions/{subscription_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=25)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error("_paypal_obtener_suscripcion: %s", e)
    return None


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


def _pagina_mi_cuenta(info, id_empresa_central, *, error_resena=None):
    sus = info.get("suscripcion") or {}
    codigos = info.get("codigos") or []

    def _estado_codigo(c):
        if c.get("usado"):
            return "Usado"
        if c.get("expira") and str(c["expira"]) < __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
            return "Caducado"
        return "Sin usar"

    filas_codigos = "".join(
        f"<tr><td><code class='pill'>{_e(c.get('codigo'))}</code></td>"
        f"<td>{_estado_codigo(c)}</td><td>{_e(c.get('creado'))}</td><td>{_e(c.get('expira'))}</td></tr>"
        for c in codigos
    ) or "<tr><td colspan='4' style='color:var(--dim)'>Todavía no tienes códigos de instalación.</td></tr>"

    instalaciones = info.get("instalaciones") or []

    def _fila_instalacion(i):
        if i.get("revocado"):
            estado = f"<span style='color:var(--rojo)'>Revocado el {_e(i.get('revocado_en'))}</span>"
            accion = ""
        else:
            estado = "<span style='color:#2EA043'>Activo</span>"
            accion = (f'<form method="post" action="/mi-cuenta/revocar/{i["id"]}" '
                     f'onsubmit="return confirm(\'¿Revocar el acceso de este ordenador? Dejará de '
                     f'poder conectarse de inmediato.\');" style="margin:0">'
                     f'<button type="submit" class="btn-copiar" style="margin:0;padding:6px 14px;'
                     f'font-size:12px;border-color:var(--rojo);color:var(--rojo)" '
                     f'onmouseover="this.style.background=\'var(--rojo)\';this.style.color=\'#0D1117\'" '
                     f'onmouseout="this.style.background=\'var(--bg2)\';this.style.color=\'var(--rojo)\'">'
                     f'Revocar</button></form>')
        return (f"<tr><td>{_e(i.get('descripcion') or '—')}</td><td>{_e(i.get('creado'))}</td>"
               f"<td>{_e(i.get('ultima_conexion') or 'Nunca')}</td><td>{estado}</td><td>{accion}</td></tr>")

    filas_instalaciones = "".join(_fila_instalacion(i) for i in instalaciones) or (
        "<tr><td colspan='5' style='color:var(--dim)'>Todavía no has emparejado ningún ordenador.</td></tr>")

    # Reseña del cliente (petición explícita, 2026-11-22) — una por empresa, editable: el mismo
    # formulario sirve para publicar la primera vez y para actualizarla (ver `services.resenas`).
    from src.services import resenas as R
    mi_resena = R.mi_resena(id_empresa_central)
    puntuacion_actual = mi_resena["puntuacion"] if mi_resena else 5
    texto_actual = _e(mi_resena["texto"]) if mi_resena else ""
    opciones_puntuacion = "".join(
        f'<option value="{n}" {"selected" if n == puntuacion_actual else ""}>'
        f'{"★" * n}{"☆" * (5 - n)} — {d}</option>'
        for n, d in ((5, "Excelente"), (4, "Muy buena"), (3, "Buena"), (2, "Regular"), (1, "Mala"))
    )
    boton_eliminar_resena = (
        '<form method="post" action="/mi-cuenta/resena/eliminar" '
        'onsubmit="return confirm(\'¿Eliminar tu reseña? También se borrarán sus comentarios.\');" '
        'style="margin-top:10px">'
        '<button type="submit" class="btn-copiar" style="margin:0;padding:6px 14px;font-size:12px;'
        'border-color:var(--rojo);color:var(--rojo)" '
        'onmouseover="this.style.background=\'var(--rojo)\';this.style.color=\'#0D1117\'" '
        'onmouseout="this.style.background=\'var(--bg2)\';this.style.color=\'var(--rojo)\'">'
        'Eliminar mi reseña</button></form>' if mi_resena else ""
    )
    error_resena_html = f'<div class="msg-error">{_e(error_resena)}</div>' if error_resena else ""
    seccion_resena = f"""
  <div class="card" style="margin-bottom:28px">
    <h3>Tu reseña</h3>
    <p style="color:var(--dim);font-size:13px;margin:0 0 14px">Comparte tu opinión sobre Smart
    Manager — se mostrará en la página de inicio junto al nombre de tu empresa, y otros clientes
    podrán comentarla en <a href="/opiniones">/opiniones</a>.</p>
    {error_resena_html}
    <form method="post" action="/mi-cuenta/resena" class="form-resena">
      <label>Puntuación</label>
      <select name="puntuacion" required>{opciones_puntuacion}</select>
      <label>Tu opinión</label>
      <textarea name="texto" required maxlength="2000" rows="4"
        placeholder="¿Qué destacarías de Smart Manager?">{texto_actual}</textarea>
      <button type="submit">{"Actualizar reseña" if mi_resena else "Publicar reseña"}</button>
    </form>
    {boton_eliminar_resena}
  </div>"""

    estado_sus = _e(sus.get("estado") or "—")
    plan_sus = _e(sus.get("codigo_plan") or "—")
    ciclo_sus = "Anual" if sus.get("ciclo") == "anual" else "Mensual"
    # Fecha exacta de caducidad/renovación (petición explícita, 2026-11-16): con cobro automático
    # recurrente, "caduca" y "se renueva" son la MISMA fecha — Stripe cobra solo y la extiende sin
    # que la empresa tenga que hacer nada, salvo que la cancele ella misma.
    _pc = sus.get("proximo_cobro")
    proximo_cobro_txt = (_pc.strftime("%d/%m/%Y") if hasattr(_pc, "strftime")
                         else (_e(_pc) if _pc else None))
    # El botón de "Gestionar suscripción y facturas" (Stripe Billing Portal) solo tiene sentido si
    # esta suscripción tiene un cliente de Stripe real asociado (`stripe_customer_id`, guardado en
    # `confirmar_pago` tras el Checkout) — las altas gratuitas (`registrar_gratis`, hoy sin plan a
    # precio 0, ver su docstring) no pasan por Stripe y no tienen nada que gestionar ahí.
    stripe_customer_id = sus.get("stripe_customer_id")
    boton_portal = (
        '<a class="btn btn-ghost" href="/mi-cuenta/portal-facturacion">Gestionar suscripción y '
        'facturas</a>' if stripe_customer_id else ""
    )
    cuerpo = f"""
<div class="wrap">
  <h2>Mi cuenta</h2>
  <p class="sub">Plan actual: <b style="color:var(--ac)">{plan_sus}</b> ({ciclo_sus}) · Estado de la
  suscripción: <b>{estado_sus}</b>
  {f' · Próxima renovación (cobro automático): <b>{proximo_cobro_txt}</b>' if proximo_cobro_txt else ""}</p>
  {f'<div class="cta-row" style="margin-bottom:28px">{boton_portal}</div>' if boton_portal else ""}
  <div class="card" style="margin-bottom:28px">
    <h3>Tus códigos de instalación</h3>
    <p style="color:var(--dim);font-size:13px;margin:0 0 14px">Pégalos en la pantalla "Configuración
    inicial" de la app de escritorio, en el ordenador donde quieras usar Smart Manager.</p>
    <table class="tabla-cuenta"><thead><tr><th>Código</th><th>Estado</th><th>Creado</th><th>Caduca</th></tr></thead>
    <tbody>{filas_codigos}</tbody></table>
  </div>
  <div class="card" style="margin-bottom:28px">
    <h3>Ordenadores emparejados</h3>
    <p style="color:var(--dim);font-size:13px;margin:0 0 14px">Cada ordenador tiene su propio acceso
    — si pierdes uno o ya no debe tener acceso, revócalo aquí sin afectar a los demás.</p>
    <table class="tabla-cuenta"><thead><tr><th>Centro</th><th>Emparejado</th><th>Última conexión</th><th>Estado</th><th></th></tr></thead>
    <tbody>{filas_instalaciones}</tbody></table>
  </div>
  {seccion_resena}
  <div class="cta-row">
    <a class="btn btn-ghost" href="/logout">Cerrar sesión</a>
  </div>
</div>"""
    return _wrap("Mi cuenta", cuerpo, sesion=True)


# ── Opiniones (reseñas + comentarios, petición explícita, 2026-11-22) ──────────────────────────
def _pagina_opiniones(sesion, id_empresa_central):
    from src.services import resenas as R

    resenas = R.listar_resenas()
    stats = R.estadisticas()

    def _tarjeta_resena(r):
        comentarios = R.listar_comentarios(r["id"])

        def _fila_comentario(c):
            borrar = (
                f'<form method="post" action="/opiniones/comentario/{c["id"]}/eliminar" '
                f'onsubmit="return confirm(\'¿Eliminar tu comentario?\');" style="display:inline">'
                f'<button type="submit" style="background:none;border:none;color:var(--dim);'
                f'font-size:11px;cursor:pointer;padding:0;text-decoration:underline">Eliminar</button>'
                f'</form>' if sesion and id_empresa_central == c["id_empresa"] else ""
            )
            return (f'<div class="comentario"><div class="autor">{_e(c["nombre_mostrado"])}</div>'
                   f'<div class="fecha">{_fecha_corta(c["creado_en"])} {borrar}</div>'
                   f'<p>{_e(c["texto"])}</p></div>')

        comentarios_html = "".join(_fila_comentario(c) for c in comentarios)
        form_comentario = (
            f'<form method="post" action="/opiniones/{r["id"]}/comentar" style="margin-top:14px">'
            f'<textarea name="texto" required maxlength="2000" rows="2" '
            f'placeholder="Comenta esta reseña..." '
            f'style="width:100%;background:var(--bg);color:var(--tx);border:2px solid var(--bd);'
            f'border-radius:9px;padding:10px 12px;font-size:13.5px;font-family:inherit"></textarea>'
            f'<button type="submit" style="margin-top:8px;padding:8px 18px;border-radius:9px;'
            f'border:2px solid var(--ac);background:var(--bg2);color:var(--ac);font-weight:900;'
            f'font-size:13px;cursor:pointer">Comentar</button></form>'
            if sesion else
            '<p style="color:var(--dim);font-size:13px;margin-top:14px">'
            '<a href="/login">Inicia sesión</a> para comentar esta reseña.</p>'
        )
        borrar_resena = (
            f'<form method="post" action="/mi-cuenta/resena/eliminar" '
            f'onsubmit="return confirm(\'¿Eliminar tu reseña? También se borrarán sus comentarios.\');" '
            f'style="display:inline;margin-left:10px">'
            f'<button type="submit" style="background:none;border:none;color:var(--dim);'
            f'font-size:12px;cursor:pointer;padding:0;text-decoration:underline">Eliminar mi reseña'
            f'</button></form>' if sesion and id_empresa_central == r["id_empresa"] else ""
        )
        return f"""
    <div class="resena-card" id="resena-{r['id']}">
      <div class="estrellas">{_estrellas(r['puntuacion'])}</div>
      <p class="texto">“{_e(r['texto'])}”</p>
      <div class="autor" style="margin-top:12px">{_e(r['nombre_mostrado'])}</div>
      <div class="fecha">{_fecha_corta(r['creado_en'])}{borrar_resena}</div>
      {comentarios_html}
      {form_comentario}
    </div>"""

    resenas_html = "".join(_tarjeta_resena(r) for r in resenas) or (
        '<p style="color:var(--dim)">Todavía no hay ninguna opinión publicada. '
        '<a href="/mi-cuenta">Entra en tu cuenta</a> para ser el primero.</p>')
    resumen = (f"<p class=\"sub\">{stats['media']} de 5 · {stats['total']} "
              f"opinion{'es' if stats['total'] != 1 else ''} de clientes reales.</p>"
              if stats["total"] > 0 else "")

    cuerpo = f"""
<div class="wrap" style="max-width:720px">
  <h2>Opiniones de nuestros clientes</h2>
  {resumen}
  {resenas_html}
</div>"""
    return _wrap("Opiniones de nuestros clientes", cuerpo, sesion=sesion,
                 descripcion="Lo que opinan los clientes de Smart Manager sobre el ERP cloud.")


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
  <p class="sub" style="margin:0 auto">La app de escritorio funciona en Windows 10/11. La primera
  vez que la abras te pedirá el código de instalación que recibiste al darte de alta — pégalo ahí
  y quedará conectada a tu empresa automáticamente.</p>
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
  <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a>.</p>

  <h2>2. Qué datos tratamos</h2>
  <table><tr><th>Categoría</th><th>Ejemplos</th><th>Origen</th></tr>
  <tr><td>Datos de cuenta</td><td>Nombre de empresa, email, contraseña (cifrada, nunca en claro)</td><td>Formulario de alta web</td></tr>
  <tr><td>Datos de facturación</td><td>Datos de la tarjeta o de la cuenta de PayPal (gestionados ÍNTEGRAMENTE por Stripe o PayPal, según elijas, nunca almacenados por nosotros)</td><td>Pasarela de pago Stripe o PayPal</td></tr>
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
    de Google y a la pasarela de pago que elijas (Stripe o PayPal).</li>
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
  <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a>.</p>

  <h2>6. Derechos del usuario</h2>
  <p>Puedes ejercer tus derechos de acceso, rectificación, supresión, oposición, limitación y
  portabilidad escribiendo a <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a>.
  También puedes presentar una reclamación ante la Agencia Española de Protección de Datos (AEPD).</p>

  <h2>7. Terceros que procesan datos en nuestro nombre</h2>
  <table><tr><th>Proveedor</th><th>Finalidad</th></tr>
  <tr><td>Stripe, Inc.</td><td>Procesamiento de pagos y domiciliación de cuotas (PCI-DSS Nivel 1)</td></tr>
  <tr><td>PayPal (Europe) S.à r.l.</td><td>Procesamiento de pagos y domiciliación de cuotas, como alternativa a Stripe</td></tr>
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
    domiciliación de pago con tarjeta (Stripe) o con PayPal, a tu elección, sujetos a los límites
    indicados en la página de precios; el cobro se renueva automáticamente cada mes salvo
    cancelación.</li>
    <li>Puedes cambiar de plan o cancelar tu suscripción en cualquier momento desde "Mi cuenta"; la
    cancelación surte efecto al final del periodo ya pagado, sin reembolso de la parte proporcional
    salvo que la ley aplicable disponga lo contrario.</li>
    <li>Nos reservamos el derecho a modificar los precios, avisando con al menos 30 días de antelación
    a los clientes con suscripción activa.</li>
  </ul>

  <h2>4. Periodo de prueba gratuito de 7 días</h2>
  <ul>
    <li>Los tres planes (Básico, Plus y Pro), tanto en su modalidad mensual como anual —
    <b>incluida la modalidad anual financiada en 4 cuotas descrita en el apartado siguiente</b> —
    incluyen un periodo de prueba gratuito de <b>7 días naturales</b> a contar desde el momento del
    alta.</li>
    <li>Durante esos 7 días no se realiza ningún cargo. Si cancelas tu suscripción antes de que
    termine el periodo de prueba, no se te cobrará nada.</li>
    <li>Si no cancelas antes de que termine el periodo de prueba, se te cobrará automáticamente al
    terminar la prueba: en el plan mensual, los días que quedan hasta completar el mes en curso
    (contados desde el día en que termina la prueba, no desde la contratación), prorrateados —
    únicamente ese primer cargo se prorratea; a partir del segundo mes se cobra siempre la
    mensualidad completa, sin prorrateo. En el plan anual (se financie o no), el importe completo
    del ciclo anual contratado.</li>
  </ul>

  <h2>5. Financiación en 4 cuotas de los planes anuales</h2>
  <ul>
    <li>Al contratar cualquiera de los tres planes en su modalidad <b>anual</b>, puedes elegir
    financiar el importe en <b>4 cuotas trimestrales iguales, sin ningún interés</b>. El importe
    total financiado es ligeramente <b>superior</b> al de pagar el año de golpe: el pago anual
    íntegro aplica un descuento de 2 meses gratis frente al mensual, mientras que financiarlo en 4
    cuotas aplica un descuento menor, de 1 mes gratis — la diferencia entre ambos importes es el
    coste de fraccionar el pago. El importe exacto de cada opción se muestra siempre en la página de
    precios y en el formulario de contratación antes de confirmar nada.</li>
    <li>La financiación incluye el mismo periodo de prueba gratuito de 7 días del apartado anterior:
    la primera cuota <b>no se cobra en el momento de la contratación</b>, sino al terminar esos 7
    días (si no has cancelado antes). Las 3 cuotas restantes se cobran automáticamente cada 3 meses
    desde esa primera cuota, hasta completar el importe financiado total.</li>
    <li>Si pagas con PayPal, la cuota trimestral se mantiene igual en los años siguientes (PayPal no
    permite programar un cambio automático de importe dentro de la misma suscripción); si pagas con
    Stripe, a partir del segundo año el cobro pasa a ser el del plan anual íntegro (con su descuento
    de 2 meses gratis), salvo que vuelvas a elegir financiar ese año.</li>
    <li>Para financiar, debes marcar expresamente la casilla de compromiso de pago del formulario de
    contratación, mediante la cual aceptas la obligación de abonar las 4 cuotas hasta completar el
    importe financiado total del plan anual contratado.</li>
  </ul>

  <h2>6. Uso aceptable</h2>
  <p>Te comprometes a no utilizar el Servicio para actividades ilícitas, a no intentar vulnerar su
  seguridad y a cumplir la normativa aplicable a tu negocio (incluida la fiscal) al introducir datos
  en el ERP, especialmente en los módulos de facturación y Verifactu/AEAT.</p>

  <h2>7. Propiedad intelectual y licencia de uso</h2>
  <p>Smart Manager y su código, marca y diseño son propiedad de sus titulares. Tú conservas la
  titularidad de todos los datos que introduzcas en el Servicio ("tus datos"). La suscripción te
  concede una licencia de uso personal e intransferible de la aplicación de escritorio, limitada al
  número de usuarios y centros de tu plan — queda prohibido redistribuir, revender, sublicenciar,
  ceder a terceros ajenos a tu empresa, o intentar descompilar, realizar ingeniería inversa o eludir
  los mecanismos de activación del software. El código de instalación es de un solo uso y personal
  de tu empresa; su uso por terceros no autorizados constituye un incumplimiento grave de estas
  Condiciones (ver apartado 9) y puede dar lugar a acciones legales.</p>

  <h2>8. Integraciones de terceros (Google y otras)</h2>
  <p>Las integraciones opcionales con servicios de terceros (p. ej. Gmail, Google Calendar, pasarelas
  de pago de tu propia tienda online) están sujetas además a los términos del propio tercero. Puedes
  desactivarlas en cualquier momento desde la configuración del ERP sin afectar al resto del Servicio.
  Ver también el apartado 3 de la <a href="/privacidad">Política de Privacidad</a>.</p>

  <h2>9. Disponibilidad y soporte</h2>
  <p>Trabajamos para mantener el Servicio disponible de forma continua, pero no garantizamos un
  funcionamiento ininterrumpido o libre de errores. Puedes contactar con soporte en
  <a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a>.</p>

  <h2>10. Limitación de responsabilidad</h2>
  <p>En la medida permitida por la ley, Smart Manager no será responsable de daños indirectos,
  lucro cesante o pérdida de datos derivados del uso del Servicio, salvo negligencia grave o dolo.</p>

  <h2>11. Suspensión y cancelación por incumplimiento</h2>
  <p>Podemos suspender o cancelar el acceso al Servicio en caso de impago, uso fraudulento o
  incumplimiento grave de estas Condiciones, notificándolo previamente cuando sea razonablemente
  posible.</p>

  <h2>12. Legislación aplicable</h2>
  <p>Estas Condiciones se rigen por la legislación española. Cualquier controversia se someterá a los
  juzgados y tribunales competentes, sin perjuicio de los derechos que asistan al consumidor conforme
  a la normativa de protección de consumidores y usuarios.</p>

  <h2>13. Contacto</h2>
  <p><a href="mailto:smart.manager.enterprises@gmail.com">smart.manager.enterprises@gmail.com</a></p>
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
        tiene_suscripcion = False
        id_empresa_central = session.get("id_empresa_central")
        if id_empresa_central:
            try:
                from src.services import provisioning
                from src.services.saas import suscripciones as S
                cfg_tenant = provisioning.config_tenant(id_empresa_central)
                estado = S.estado(id_empresa_central, config=cfg_tenant)
                tiene_suscripcion = bool(estado) and estado.get("estado") in ("activa", "prueba")
            except Exception:
                tiene_suscripcion = False
        return _pagina_home(session.get("cuenta"), tiene_suscripcion=tiene_suscripcion)

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

    # ── Logotipo (petición explícita, 2026-11-20: no aparecía en ningún sitio de la web ni en la
    # pestaña del navegador) — reutiliza el mismo fichero que ya usa la app de escritorio
    # (`assets/app_icon.png`, la versión recortada sin margen, la que de verdad se ve bien en
    # tamaños pequeños como el favicon o la marca de la cabecera), resuelto con
    # `utils.recursos.ruta_recurso` (mismo helper que ya usa `main.py`/`menu_principal.py` —
    # compatible con PyInstaller en escritorio y con este contenedor Docker, que copia `assets/`
    # tal cual junto a `src/`, ver Dockerfile). Nunca sirve la carpeta entera, solo este fichero.
    @bp.get("/assets/logo.png")
    def logo_png():
        from flask import send_file
        from src.utils.recursos import ruta_recurso
        return send_file(ruta_recurso("assets", "app_icon.png"), mimetype="image/png",
                         max_age=86400)

    # ── Registro ────────────────────────────────────────────────────────────────────────────
    @bp.get("/registro")
    def registro_form():
        plan = (request.args.get("plan") or "basic").lower()
        ciclo = "anual" if (request.args.get("ciclo") or "").lower() == "anual" else "mensual"
        # `email`/`origen` (petición explícita, 2026-11-16): permiten que un enlace externo (p. ej.
        # el gancho comercial del Portal B2B hacia 0% de comisión) llegue con el email del usuario
        # ya prellenado y con trazabilidad de origen (viaja en `metadata` de Stripe Checkout).
        email = (request.args.get("email") or "")[:255]
        origen = (request.args.get("origen") or "")[:40]
        return _pagina_registro(plan, ciclo, email=email, origen=origen)

    @bp.post("/registro")
    def registro_submit():
        from werkzeug.security import generate_password_hash

        from src.services.saas import planes as _P

        plan = (request.form.get("plan") or "basic").upper()
        ciclo = "anual" if (request.form.get("ciclo") or "").lower() == "anual" else "mensual"
        nombre_empresa = (request.form.get("nombre_empresa") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        origen = (request.form.get("origen") or "").strip()[:40]
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        metodo_pago = request.form.get("metodo_pago") if request.form.get("metodo_pago") in (
            "stripe", "paypal") else "stripe"
        # Financiación en 4 cuotas (petición explícita, 2026-11-22): SOLO válida en plan anual de
        # pago — un envío manipulado que la marque en mensual/gratis se ignora silenciosamente
        # (nunca se finge una financiación que no tiene sentido ahí). Exige el checkbox de
        # compromiso legal marcado — sin él, se rechaza el envío entero (nunca se financia "a
        # medias" sin la aceptación explícita).
        financiar = ciclo == "anual" and request.form.get("financiar") in ("1", "true", "on")
        acepta_financiacion = request.form.get("acepta_financiacion") in ("1", "true", "on")
        if financiar and not acepta_financiacion:
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                    error="Para financiar en 4 cuotas tienes que aceptar el "
                                         "compromiso de pago de las 4 cuotas."), 400
        cfg = _P.PLANES.get(plan)
        if not cfg or not nombre_empresa or not email or len(password) < 8:
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                    error="Revisa los datos: la contraseña debe tener al menos 8 "
                                         "caracteres y todos los campos son obligatorios."), 400
        if password != password2:
            # Defensivo: el navegador ya lo valida (ver el <script> del formulario), pero un envío
            # directo sin JS (o manipulado) no debe colarse.
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                    error="Las contraseñas no coinciden."), 400

        password_hash = generate_password_hash(password)

        from src.services import alta_comercial as AC

        # Planes de pago: valida que el email no exista YA antes de seguir (evita checkouts que
        # luego no se pueden confirmar) — se hace ANTES de enviar el código de verificación, para
        # no gastar un envío de email en un alta que de todos modos va a rechazarse.
        if cfg["precio"] > 0:
            pre = AC.preregistrar(email)
            if not pre.get("ok"):
                return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                        error=pre.get("error") or "No se pudo validar el email."), 400

        # Verificación de email OBLIGATORIA (petición explícita, 2026-11-22): antes de crear nada
        # (ni la cuenta gratis, ni el Checkout de Stripe), hay que confirmar un código de 6 dígitos
        # enviado a ese email — los datos ya validados viajan en la sesión firmada hasta que se
        # confirme (`session["pendiente_registro"]`), nunca se vuelven a pedir.
        from src.services import verificacion_email as VE
        r_envio = VE.generar_y_enviar(email)
        if not r_envio.get("ok"):
            logger.error("No se pudo enviar el código de verificación a %s: %s", email,
                        r_envio.get("error"))
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                    error="No se pudo enviar el código de verificación. "
                                         "Inténtalo de nuevo en unos minutos."), 502
        session["pendiente_registro"] = {
            "plan": plan, "ciclo": ciclo, "email": email, "nombre_empresa": nombre_empresa,
            "origen": origen, "password_hash": password_hash, "financiar": financiar,
            "metodo_pago": metodo_pago,
        }
        return _pagina_verificar_email(email)

    @bp.post("/registro/verificar-email")
    def registro_verificar_email():
        pendiente = session.get("pendiente_registro")
        if not pendiente:
            return redirect(url_for("sitio_oficial.precios"))
        from src.services import verificacion_email as VE
        codigo = (request.form.get("codigo") or "").strip()
        r = VE.verificar(pendiente["email"], codigo)
        if not r.get("ok"):
            mensajes = {"codigo_incorrecto": "Código incorrecto. Revísalo e inténtalo de nuevo.",
                       "codigo_caducado": "El código ha caducado — pulsa \"Reenviar código\".",
                       "demasiados_intentos": "Demasiados intentos — pulsa \"Reenviar código\" para "
                                             "pedir uno nuevo.",
                       "sin_codigo_pendiente": "No hay ningún código pendiente — pulsa \"Reenviar "
                                              "código\"."}
            return _pagina_verificar_email(
                pendiente["email"], error=mensajes.get(r.get("error"), "No se pudo verificar el código.")), 400
        return _completar_registro(pendiente)

    @bp.post("/registro/reenviar-codigo")
    def registro_reenviar_codigo():
        pendiente = session.get("pendiente_registro")
        if not pendiente:
            return redirect(url_for("sitio_oficial.precios"))
        from src.services import verificacion_email as VE
        r = VE.generar_y_enviar(pendiente["email"])
        if not r.get("ok"):
            return _pagina_verificar_email(
                pendiente["email"], error="No se pudo reenviar el código. Inténtalo de nuevo en "
                                          "unos minutos."), 502
        return _pagina_verificar_email(pendiente["email"])

    def _completar_registro(pendiente):
        """Continuación de `registro_submit` tras confirmar el código de verificación — crea la
        cuenta gratis o abre el Checkout de Stripe, exactamente igual que antes de añadirse el
        paso de verificación (petición explícita, 2026-11-22), solo que ahora SOLO se llega aquí
        con el email ya confirmado de verdad.

        Dos caminos de pago, mutuamente excluyentes (petición explícita, 2026-11-22):
          - `financiar=True` (solo anual): Checkout en modo `setup` (solo recoge el método de pago,
            SIN cobrar nada) — el cobro real de la primera cuota lo hace `financiar_exito` al crear
            el SubscriptionSchedule de 4 fases. SIN periodo de prueba (incompatible).
          - Camino normal: Checkout en modo `subscription` CON `trial_period_days=7` y
            `billing_cycle_anchor` fijado al día 1 del mes siguiente a esa fecha de fin de prueba
            — así Stripe genera automáticamente, al terminar los 7 días gratis, UNA factura
            prorrateada SOLO por los días que quedan hasta el día 1 (nunca un mes completo) y, a
            partir de ahí, cobra el mes/año completo en cada ancla — exactamente lo pedido:
            "descontando los siete primeros días de prueba, tan solo en la primera factura"."""
        from src.services.saas import planes as _P
        from src.services import alta_comercial as AC
        plan, ciclo = pendiente["plan"], pendiente["ciclo"]
        email, nombre_empresa = pendiente["email"], pendiente["nombre_empresa"]
        origen, password_hash = pendiente["origen"], pendiente["password_hash"]
        financiar = bool(pendiente.get("financiar"))
        cfg = _P.PLANES.get(plan)

        if cfg["precio"] == 0:
            r = AC.registrar_gratis(nombre_empresa, email, password_hash, ciclo=ciclo)
            if not r.get("ok"):
                return _pagina_registro(plan.lower(), ciclo,
                                        error=r.get("error") or "No se pudo crear la cuenta."), 400
            _enviar_codigo_por_email(email, r["codigo"], r["plan"])
            session.pop("pendiente_registro", None)
            session["cuenta"] = {"email": email}
            session["id_empresa_central"] = r.get("id_empresa")
            return _pagina_resultado_alta(r["codigo"], r["plan"])

        if pendiente.get("metodo_pago") == "paypal":
            return _completar_registro_paypal(pendiente, cfg)

        secreto = os.environ.get("STRIPE_SECRET_KEY")
        sufijo_precio = "_ANUAL" if ciclo == "anual" else ""
        price_id = os.environ.get(f"STRIPE_PRICE_ID_{plan}{sufijo_precio}")
        if not secreto or not price_id:
            logger.warning("Checkout Stripe no configurado (falta STRIPE_SECRET_KEY o "
                          "STRIPE_PRICE_ID_%s%s) — alta de pago bloqueada honestamente.",
                          plan, sufijo_precio)
            return _pagina_pago_no_disponible()

        if financiar:
            try:
                import stripe
                stripe.api_key = secreto
                checkout = stripe.checkout.Session.create(
                    mode="setup",
                    customer_email=email,
                    success_url=url_for("sitio_oficial.financiar_exito", _external=True)
                    + "?session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=url_for("sitio_oficial.checkout_cancelado", _external=True),
                    metadata={"plan": plan, "ciclo": ciclo, "email": email,
                             "nombre_empresa": nombre_empresa, "origen": origen or "web"},
                )
            except Exception as ex:
                logger.error("Creando Stripe Checkout Session (financiación): %s", ex)
                return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                        error="No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."), 502
            session.pop("pendiente_registro", None)
            session["pendiente_checkout"] = {
                "plan": plan, "ciclo": ciclo, "email": email, "nombre_empresa": nombre_empresa,
                "password_hash": password_hash, "financiar": True,
            }
            return redirect(checkout.url, code=303)

        # Los precios de los 3 planes se muestran "+ IVA" (no incluido) — este Tax Rate (21%,
        # IVA español estándar, creado una vez en el dashboard/API de Stripe) es lo que hace que
        # el desglose real del cobro coincida con ese texto; sin él, Stripe cobraría el precio
        # base sin más y el "+ IVA" de la web sería engañoso. Declaración manual del IVA recaudado
        # (Modelo 303) — decisión explícita del negocio, no se usa el servicio "Stripe Tax"
        # automático (ni su coste adicional por transacción).
        tax_rate_id = os.environ.get("STRIPE_TAX_RATE_ID")
        # Ancla de facturación = día 1 del mes siguiente a la fecha de fin de prueba (nunca el mes
        # siguiente a HOY sin más: si la prueba terminara ya entrado el mes siguiente — p. ej.
        # empezando el día 25 — esa ancla caería ANTES del fin de prueba, que Stripe rechaza).
        from datetime import datetime, timedelta
        trial_end_estimado = datetime.utcnow() + timedelta(days=7)
        if trial_end_estimado.day == 1:
            ancla_dt = trial_end_estimado.replace(hour=0, minute=0, second=0, microsecond=0)
        elif trial_end_estimado.month == 12:
            ancla_dt = trial_end_estimado.replace(year=trial_end_estimado.year + 1, month=1, day=1,
                                                  hour=0, minute=0, second=0, microsecond=0)
        else:
            ancla_dt = trial_end_estimado.replace(month=trial_end_estimado.month + 1, day=1,
                                                  hour=0, minute=0, second=0, microsecond=0)
        billing_cycle_anchor = int(ancla_dt.timestamp())
        try:
            import stripe
            stripe.api_key = secreto
            line_item = {"price": price_id, "quantity": 1}
            if tax_rate_id:
                line_item["tax_rates"] = [tax_rate_id]
            checkout = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[line_item],
                customer_email=email,
                subscription_data={
                    "trial_period_days": 7,
                    "billing_cycle_anchor": billing_cycle_anchor,
                    "proration_behavior": "create_prorations",
                },
                success_url=url_for("sitio_oficial.checkout_exito", _external=True)
                + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("sitio_oficial.checkout_cancelado", _external=True),
                metadata={"plan": plan, "ciclo": ciclo, "email": email,
                         "nombre_empresa": nombre_empresa, "origen": origen or "web"},
            )
        except Exception as ex:
            logger.error("Creando Stripe Checkout Session: %s", ex)
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=origen,
                                    error="No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."), 502

        session.pop("pendiente_registro", None)
        session["pendiente_checkout"] = {
            "plan": plan, "ciclo": ciclo, "email": email, "nombre_empresa": nombre_empresa,
            "password_hash": password_hash,
        }
        return redirect(checkout.url, code=303)

    def _completar_registro_paypal(pendiente, cfg):
        """Equivalente a la rama Stripe de `_completar_registro`, para PayPal (petición explícita,
        2026-11-23): a diferencia de Stripe, aquí NO hace falta el baile en dos pasos
        Checkout→Setup/Subscription — la propia Suscripción de PayPal ya define el ciclo de prueba
        (si no financia) o las 3 fases completas (si financia) desde el principio, así que un único
        `return_url` (`checkout_paypal_exito`) sirve para ambos casos."""
        plan, ciclo = pendiente["plan"], pendiente["ciclo"]
        email, nombre_empresa = pendiente["email"], pendiente["nombre_empresa"]
        password_hash = pendiente["password_hash"]
        financiar = bool(pendiente.get("financiar"))

        token = _paypal_token()
        if not token:
            logger.warning("Checkout PayPal no configurado (falta PAYPAL_CLIENT_ID/_SECRET) — "
                           "alta de pago bloqueada honestamente.")
            return _pagina_pago_no_disponible()

        if financiar:
            # Petición explícita, 2026-11-27: financiar ya no lleva el mismo descuento (2 meses
            # gratis) que el anual íntegro — pasa a 1 mes gratis (`precio_anual_financiado`, ver
            # `services.saas.planes`), igual criterio que la vía Stripe (`alta_comercial.
            # confirmar_financiacion`). Como el Plan de PayPal cobra esta cuota PARA SIEMPRE (ver
            # `_paypal_crear_plan_financiacion`), aquí el coste algo mayor aplica todos los años,
            # no solo el primero.
            cuota = round(cfg["precio_anual_financiado"] / 4, 2)
            plan_id = _paypal_crear_plan_financiacion(token, plan=plan, cuota=cuota)
        else:
            sufijo = "_ANUAL" if ciclo == "anual" else ""
            plan_id = os.environ.get(f"PAYPAL_PLAN_ID_{plan}{sufijo}")
        if not plan_id:
            logger.warning("Checkout PayPal no configurado (falta PAYPAL_PLAN_ID_%s%s o fallo "
                          "creando el plan de financiación) — alta de pago bloqueada honestamente.",
                          plan, "" if financiar else ("_ANUAL" if ciclo == "anual" else ""))
            return _pagina_pago_no_disponible()

        return_url = url_for("sitio_oficial.checkout_paypal_exito", _external=True)
        cancel_url = url_for("sitio_oficial.checkout_cancelado", _external=True)
        r = _paypal_crear_suscripcion(token, plan_id=plan_id, email=email,
                                      return_url=return_url, cancel_url=cancel_url)
        if not r.get("ok"):
            return _pagina_registro(plan.lower(), ciclo, email=email, origen=pendiente.get("origen", ""),
                                    error="No se pudo iniciar el pago con PayPal. Inténtalo de nuevo "
                                         "en unos minutos."), 502

        session.pop("pendiente_registro", None)
        session["pendiente_checkout"] = {
            "plan": plan, "ciclo": ciclo, "email": email, "nombre_empresa": nombre_empresa,
            "password_hash": password_hash, "financiar": financiar, "metodo_pago": "paypal",
            "paypal_subscription_id": r["subscription_id"],
        }
        return redirect(r["approve_url"], code=303)

    @bp.get("/checkout/paypal/exito")
    def checkout_paypal_exito():
        """`return_url` de la Suscripción de PayPal — NUNCA se confía en la redirección por sí
        sola: se re-consulta la suscripción real en PayPal antes de dar nada por verificado."""
        pendiente = session.get("pendiente_checkout")
        subscription_id = pendiente.get("paypal_subscription_id") if pendiente else None
        if not pendiente or not subscription_id:
            return redirect(url_for("sitio_oficial.precios"))

        token = _paypal_token()
        if not token:
            return _pagina_pago_no_disponible()
        sus = _paypal_obtener_suscripcion(token, subscription_id)
        if not sus:
            logger.error("Recuperando suscripción PayPal %s", subscription_id)
            return _pagina_pago_no_disponible()

        ciclo_pendiente = pendiente.get("ciclo", "mensual")
        estado = sus.get("status")
        if estado == "APPROVED":
            # Algunos flujos de PayPal dejan la suscripción en APPROVED (aprobada por el
            # comprador, todavía no activada del todo) — se activa explícitamente antes de
            # continuar, nunca se asume activa sin más.
            try:
                import requests
                requests.post(
                    f"{_paypal_base()}/v1/billing/subscriptions/{subscription_id}/activate",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=25, json={"reason": "Alta de cliente"})
                sus = _paypal_obtener_suscripcion(token, subscription_id) or sus
                estado = sus.get("status")
            except Exception as ex:
                logger.error("Activando suscripción PayPal %s: %s", subscription_id, ex)
        if estado != "ACTIVE":
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="El pago con PayPal no se ha completado todavía."), 400

        from src.services import alta_comercial as AC

        r = AC.confirmar_pago(
            session_id=f"paypal_{subscription_id}", plan=pendiente["plan"], email=pendiente["email"],
            nombre_empresa=pendiente["nombre_empresa"], password_hash=pendiente["password_hash"],
            ciclo=ciclo_pendiente, paypal_subscription_id=subscription_id,
        ) if not pendiente.get("financiar") else AC.confirmar_financiacion(
            session_id=f"paypal_{subscription_id}", plan=pendiente["plan"], email=pendiente["email"],
            nombre_empresa=pendiente["nombre_empresa"], password_hash=pendiente["password_hash"],
            paypal_subscription_id=subscription_id,
        )
        session.pop("pendiente_checkout", None)
        if not r.get("ok"):
            logger.error("confirmar_pago/confirmar_financiacion (PayPal) tras pago OK pero el "
                        "alta falló: %s", r.get("error"))
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="El pago se completó pero no pudimos terminar el alta. "
                                         "Escríbenos a smart.manager.enterprises@gmail.com con tu email de "
                                         "compra y lo resolvemos manualmente."), 502

        _enviar_codigo_por_email(pendiente["email"], r["codigo"], r["plan"])
        session["cuenta"] = {"email": pendiente["email"]}
        session["id_empresa_central"] = r.get("id_empresa")
        return _pagina_resultado_alta(r["codigo"], r["plan"], nuevo=not r.get("ya_existia"),
                                      proximo_cobro=r.get("proximo_cobro"), ciclo=ciclo_pendiente)

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

        ciclo_pendiente = pendiente.get("ciclo", "mensual")
        # "no_payment_required" (petición explícita, 2026-11-22 — periodo de prueba de 7 días): un
        # Checkout de suscripción con `trial_period_days` no cobra NADA al confirmar — Stripe marca
        # la sesión así (nunca "paid", que sería engañoso: no se ha cobrado un euro todavía). Ambos
        # estados significan "el método de pago quedó verificado y la suscripción ya está activa".
        if chk.get("payment_status") not in ("paid", "no_payment_required"):
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="El pago no se ha completado todavía."), 400

        from src.services import alta_comercial as AC

        r = AC.confirmar_pago(
            session_id=session_id, plan=pendiente["plan"], email=pendiente["email"],
            nombre_empresa=pendiente["nombre_empresa"], password_hash=pendiente["password_hash"],
            stripe_customer_id=chk.get("customer"), ciclo=ciclo_pendiente,
            stripe_subscription_id=chk.get("subscription"),
        )
        session.pop("pendiente_checkout", None)
        if not r.get("ok"):
            logger.error("confirmar_pago tras Stripe OK pero el alta falló: %s", r.get("error"))
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="El pago se completó pero no pudimos terminar el alta. "
                                         "Escríbenos a smart.manager.enterprises@gmail.com con tu email de "
                                         "compra y lo resolvemos manualmente."), 502

        _enviar_codigo_por_email(pendiente["email"], r["codigo"], r["plan"])
        session["cuenta"] = {"email": pendiente["email"]}
        session["id_empresa_central"] = r.get("id_empresa")
        return _pagina_resultado_alta(r["codigo"], r["plan"], nuevo=not r.get("ya_existia"),
                                      proximo_cobro=r.get("proximo_cobro"), ciclo=ciclo_pendiente)

    @bp.get("/financiar/exito")
    def financiar_exito():
        """`return_url` del Checkout en modo `setup` (petición explícita, 2026-11-22: financiación
        en 4 cuotas trimestrales) — NUNCA se confía en la redirección por sí sola: se re-consulta
        la Setup Session real en Stripe antes de crear el SubscriptionSchedule (y, con él, el cobro
        real de la primera cuota, ahora mismo)."""
        session_id = request.args.get("session_id")
        pendiente = session.get("pendiente_checkout")
        if not session_id or not pendiente or not pendiente.get("financiar"):
            return redirect(url_for("sitio_oficial.precios"))

        secreto = os.environ.get("STRIPE_SECRET_KEY")
        if not secreto:
            return _pagina_pago_no_disponible()
        try:
            import stripe
            stripe.api_key = secreto
            chk = stripe.checkout.Session.retrieve(session_id)
        except Exception as ex:
            logger.error("Recuperando Setup Session %s: %s", session_id, ex)
            return _pagina_pago_no_disponible()

        ciclo_pendiente = pendiente.get("ciclo", "mensual")
        if chk.get("status") != "complete" or not chk.get("setup_intent"):
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="La vinculación del método de pago no se completó."), 400

        from src.services import alta_comercial as AC

        r = AC.confirmar_financiacion(
            session_id=session_id, plan=pendiente["plan"], email=pendiente["email"],
            nombre_empresa=pendiente["nombre_empresa"], password_hash=pendiente["password_hash"],
            stripe_customer_id=chk.get("customer"), setup_intent_id=chk.get("setup_intent"),
        )
        session.pop("pendiente_checkout", None)
        if not r.get("ok"):
            logger.error("confirmar_financiacion tras Setup OK pero el alta falló: %s", r.get("error"))
            return _pagina_registro(pendiente["plan"].lower(), ciclo_pendiente,
                                    error="El método de pago se vinculó pero no pudimos terminar el "
                                         "alta. Escríbenos a smart.manager.enterprises@gmail.com con "
                                         "tu email y lo resolvemos manualmente."), 502

        _enviar_codigo_por_email(pendiente["email"], r["codigo"], r["plan"])
        session["cuenta"] = {"email": pendiente["email"]}
        session["id_empresa_central"] = r.get("id_empresa")
        return _pagina_resultado_alta(r["codigo"], r["plan"], nuevo=not r.get("ya_existia"),
                                      proximo_cobro=r.get("proximo_cobro"), ciclo="anual")

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
        from src.services import alta_comercial as AC

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        r = AC.login(email, password)
        if not r.get("ok"):
            return _pagina_login(error=r.get("error") or "No se pudo iniciar sesión."), 401
        session["cuenta"] = {"email": email}
        session["id_empresa_central"] = r.get("id_empresa")
        return redirect(url_for("sitio_oficial.mi_cuenta"))

    @bp.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("sitio_oficial.home"))

    @bp.get("/mi-cuenta")
    def mi_cuenta():
        from src.services import alta_comercial as AC

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        info = AC.datos_cuenta(id_empresa_central)
        if not info.get("ok"):
            return _pagina_login(error="No se pudo cargar tu cuenta. Inicia sesión de nuevo."), 502
        return _pagina_mi_cuenta(info, id_empresa_central,
                                 error_resena=request.args.get("error_resena"))

    @bp.get("/mi-cuenta/portal-facturacion")
    def portal_facturacion():
        """Redirige al Stripe Billing Portal (hospedado por Stripe) para que el cliente gestione
        su propia suscripción/facturas/método de pago, sin que tengamos que construir esa UI."""
        from src.services import alta_comercial as AC

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))

        info = AC.datos_cuenta(id_empresa_central)
        stripe_customer_id = (info.get("suscripcion") or {}).get("stripe_customer_id")
        secreto = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe_customer_id or not secreto:
            return redirect(url_for("sitio_oficial.mi_cuenta"))

        try:
            import stripe
            stripe.api_key = secreto
            portal = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=url_for("sitio_oficial.mi_cuenta", _external=True),
            )
        except Exception as ex:
            logger.error("Creando Billing Portal Session (empresa=%s): %s", id_empresa_central, ex)
            return redirect(url_for("sitio_oficial.mi_cuenta"))
        return redirect(portal.url, code=303)

    @bp.post("/mi-cuenta/revocar/<int:id_instalacion>")
    def revocar_instalacion(id_instalacion):
        from src.services import alta_comercial as AC

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        # `revocar_instalacion` comprueba que la instalación pertenece a ESTA empresa antes de
        # tocar nada — nunca revoca la de otro cliente aunque alguien manipule el id en la URL.
        AC.revocar_instalacion(id_instalacion, id_empresa_central)
        return redirect(url_for("sitio_oficial.mi_cuenta"))

    # ── Reseñas de clientes + comentarios (petición explícita, 2026-11-22) ─────────────────────
    @bp.post("/mi-cuenta/resena")
    def mi_cuenta_resena():
        from src.services import resenas as R

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        r = R.publicar_resena(id_empresa_central, puntuacion=request.form.get("puntuacion"),
                              texto=request.form.get("texto"))
        if not r.get("ok"):
            from urllib.parse import quote
            return redirect(url_for("sitio_oficial.mi_cuenta") + f"?error_resena={quote(r['error'])}")
        return redirect(url_for("sitio_oficial.mi_cuenta"))

    @bp.post("/mi-cuenta/resena/eliminar")
    def mi_cuenta_resena_eliminar():
        from src.services import resenas as R

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        R.eliminar_mi_resena(id_empresa_central)
        return redirect(url_for("sitio_oficial.mi_cuenta"))

    @bp.get("/opiniones")
    def opiniones():
        return _pagina_opiniones(session.get("cuenta"), session.get("id_empresa_central"))

    @bp.post("/opiniones/<int:id_resena>/comentar")
    def opiniones_comentar(id_resena):
        from src.services import resenas as R

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        R.publicar_comentario(id_resena, id_empresa_central, texto=request.form.get("texto"))
        return redirect(url_for("sitio_oficial.opiniones") + f"#resena-{id_resena}")

    @bp.post("/opiniones/comentario/<int:id_comentario>/eliminar")
    def opiniones_comentario_eliminar(id_comentario):
        from src.services import resenas as R

        if not session.get("cuenta"):
            return redirect(url_for("sitio_oficial.login"))
        id_empresa_central = session.get("id_empresa_central")
        if not id_empresa_central:
            session.clear()
            return redirect(url_for("sitio_oficial.login"))
        # `eliminar_comentario` comprueba que el comentario es de ESTA empresa antes de borrar
        # nada — nunca borra el de otro cliente aunque alguien manipule el id en la URL.
        R.eliminar_comentario(id_comentario, id_empresa_central)
        return redirect(url_for("sitio_oficial.opiniones"))

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

        remitente = os.environ.get("SMTP_FROM", "smart.manager.enterprises@gmail.com")
        msg = MIMEText(
            f"¡Gracias por registrarte en Smart Manager!\n\n"
            f"Plan contratado: {plan}\n"
            f"Código de instalación (válido 7 días): {codigo}\n\n"
            f"Descarga la app de escritorio y, la primera vez que la abras, pégalo en la pantalla "
            f"\"Configuración inicial\" para vincularla a tu empresa.\n\n"
            f"Descarga la app: https://smartmanager-app.com/descargas\n", "plain", "utf-8")
        msg["Subject"] = "Tu código de instalación de Smart Manager"
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
