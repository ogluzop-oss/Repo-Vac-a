"""
Tienda online propia (Escenario B) — storefront dinámico servido por el backend.

Consume el catálogo EN VIVO (`src.services.catalogo`, vista pública) por lo que
SIEMPRE está sincronizada con Smart Manager AI: no hay export que regenerar. Es
multi-tenant (la empresa va en la URL) y se personaliza con `web_config`
(nombre/color/logo/moneda).

El HTML se genera con funciones puras (sin Flask) → testeables sin servidor. Flask
solo se usa para enrutar (import perezoso en `crear_blueprint`).
"""

import json
import logging

from markupsafe import escape

from src.db import web_tienda
from src.services import catalogo as cat_svc

logger = logging.getLogger("backend.storefront")

_SIMBOLOS = {"EUR": "€", "USD": "$", "GBP": "£", "MXN": "$", "ARS": "$"}


def _sym(moneda):
    return _SIMBOLOS.get((moneda or "EUR").upper(), (moneda or "").upper() + " ")


def _precio(p, moneda):
    return f"{float(p or 0):.2f} {_sym(moneda)}"


def _e(x):
    return str(escape(x if x is not None else ""))


# Chat de soporte (Fase 6 e-commerce): widget JS plano, sin dependencias externas — en una cadena
# PROPIA (no un f-string) para no tener que escapar cada `{`/`}` de JavaScript dentro del f-string
# de `_layout`. `__EID__` es el único punto de sustitución (vía `.replace`, nunca interpolación de
# texto NO escapado del visitante — los mensajes solo viajan por `fetch`, nunca se inyectan en el
# HTML server-side).
_CHAT_WIDGET_HTML = """
<div id="smchat" style="position:fixed;bottom:20px;right:20px;z-index:999;font-family:'Segoe UI',system-ui,sans-serif">
  <button id="smchat-btn" aria-label="Chat de soporte" style="width:56px;height:56px;border-radius:50%;
    background:var(--ac);color:#0E1117;border:none;font-size:24px;cursor:pointer;
    box-shadow:0 2px 10px rgba(0,0,0,.4)">💬</button>
  <div id="smchat-panel" style="display:none;flex-direction:column;position:fixed;bottom:84px;right:20px;
    width:320px;max-height:440px;background:#161B22;border:1px solid #30363D;border-radius:12px;overflow:hidden">
    <div style="background:var(--ac);color:#0E1117;padding:10px 14px;font-weight:900;font-size:13px">
      Atención al cliente</div>
    <div id="smchat-msgs" style="flex:1;overflow-y:auto;padding:10px;font-size:13px;color:#E6EDF3"></div>
    <form id="smchat-form" style="display:flex;border-top:1px solid #30363D">
      <input id="smchat-inp" placeholder="Escribe tu mensaje…" autocomplete="off" style="flex:1;
        background:#0D1117;color:#E6EDF3;border:none;padding:10px;font-size:13px;outline:none">
      <button type="submit" style="background:var(--ac);color:#0E1117;border:none;padding:0 14px;
        font-weight:900;cursor:pointer">➤</button>
    </form>
  </div>
</div>
<script>
(function(){
  var eid = "__EID__";
  var clave = "smchat_token_" + eid;
  var token = "";
  try { token = localStorage.getItem(clave) || ""; } catch (e) {}
  var btn = document.getElementById('smchat-btn');
  var panel = document.getElementById('smchat-panel');
  var msgsEl = document.getElementById('smchat-msgs');
  var form = document.getElementById('smchat-form');
  var inp = document.getElementById('smchat-inp');
  var poll = null;

  function render(mensajes) {
    msgsEl.innerHTML = '';
    (mensajes || []).forEach(function (m) {
      var b = document.createElement('div');
      var esVisitante = m.remitente === 'visitante';
      b.style.cssText = 'margin:6px 0;padding:8px 10px;border-radius:10px;max-width:85%;word-wrap:break-word;'
        + (esVisitante ? 'background:var(--ac);color:#0E1117;margin-left:auto'
                       : 'background:#0D1117;color:#E6EDF3');
      b.textContent = m.texto;
      msgsEl.appendChild(b);
    });
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  function refrescar() {
    if (!token) return;
    fetch('/tienda/' + eid + '/soporte/hilo?token=' + encodeURIComponent(token))
      .then(function (r) { return r.json(); })
      .then(function (d) { render(d.mensajes); })
      .catch(function () {});
  }

  btn.onclick = function () {
    var abierto = panel.style.display === 'flex';
    panel.style.display = abierto ? 'none' : 'flex';
    if (!abierto) {
      refrescar();
      if (!poll) poll = setInterval(refrescar, 8000);
    }
  };

  form.onsubmit = function (e) {
    e.preventDefault();
    var texto = inp.value.trim();
    if (!texto) return;
    inp.value = '';
    fetch('/tienda/' + eid + '/soporte/mensaje', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: texto, token: token })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.token) {
        token = d.token;
        try { localStorage.setItem(clave, token); } catch (e) {}
      }
      render(d.mensajes);
    }).catch(function () {});
  };
})();
</script>"""


def _widget_chat(eid) -> str:
    return _CHAT_WIDGET_HTML.replace("__EID__", _e(eid))


# Carrito flotante (Motor de Alta Conversión e-Commerce — Drawer Cart): mismo criterio exacto que
# el chat (cadena PROPIA, no un f-string, para no escapar cada `{`/`}` de JS; `__EID__` es el único
# punto de sustitución, vía `.replace`). Vanilla JS, sin dependencias — reutiliza el patrón ya
# establecido (`fetch`, sin framework) del propio chat. `window.__smAddToCart` es el punto de
# entrada público que usan los botones "Añadir al carrito"/"Comprar ahora" de la ficha de producto.
_CART_WIDGET_HTML = """
<div id="smcart-fab" style="position:fixed;bottom:20px;right:92px;z-index:999;font-family:'Segoe UI',system-ui,sans-serif">
  <button id="smcart-btn" aria-label="Carrito" style="position:relative;width:56px;height:56px;border-radius:50%;
    background:var(--ac);color:#0E1117;border:none;font-size:24px;cursor:pointer;
    box-shadow:0 2px 10px rgba(0,0,0,.4)">🛒
    <span id="smcart-badge" style="display:none;position:absolute;top:-4px;right:-4px;background:#F85149;
      color:#fff;border-radius:50%;min-width:20px;height:20px;font-size:11px;font-weight:900;
      line-height:20px;text-align:center;padding:0 4px">0</span>
  </button>
</div>
<div id="smcart-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000"></div>
<div id="smcart-drawer" style="display:none;flex-direction:column;position:fixed;top:0;right:0;bottom:0;
  width:380px;max-width:92vw;background:#161B22;border-left:1px solid #30363D;z-index:1001;
  box-shadow:-4px 0 20px rgba(0,0,0,.4);font-family:'Segoe UI',system-ui,sans-serif">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:16px;
    border-bottom:1px solid #30363D">
    <b style="font-size:16px;color:#E6EDF3">Tu carrito</b>
    <button id="smcart-cerrar" aria-label="Cerrar" style="background:transparent;border:none;color:#8B949E;
      font-size:22px;cursor:pointer;line-height:1">×</button>
  </div>
  <div id="smcart-envio-bar" style="padding:12px 16px;display:none">
    <div id="smcart-envio-txt" style="font-size:12px;color:#E6EDF3;margin-bottom:6px"></div>
    <div style="height:8px;border-radius:999px;background:#0D1117;border:1px solid #30363D;overflow:hidden">
      <div id="smcart-envio-fill" style="height:100%;width:0%;background:var(--ac);transition:width .25s"></div>
    </div>
  </div>
  <div id="smcart-lineas" style="flex:1;overflow-y:auto;padding:0 16px"></div>
  <div style="padding:14px 16px;border-top:1px solid #30363D">
    <div style="display:flex;gap:8px;margin-bottom:6px">
      <input id="smcart-cupon" placeholder="Código promocional" style="flex:1;background:#0D1117;
        color:#E6EDF3;border:1px solid #30363D;border-radius:8px;padding:8px 10px;font-size:13px">
      <button id="smcart-aplicar-cupon" style="background:transparent;border:1px solid var(--ac);
        color:var(--ac);border-radius:8px;padding:0 12px;font-weight:900;cursor:pointer">Aplicar</button>
    </div>
    <div id="smcart-cupon-msg" style="font-size:11px;margin-bottom:8px"></div>
    <div style="display:flex;justify-content:space-between;font-size:13px;color:#8B949E;margin-bottom:4px">
      <span>Subtotal</span><span id="smcart-subtotal">—</span>
    </div>
    <div id="smcart-desc-row" style="display:none;justify-content:space-between;font-size:13px;color:#3FB950;margin-bottom:4px">
      <span>Descuento</span><span id="smcart-descuento">—</span>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:13px;color:#8B949E;margin-bottom:8px">
      <span>Envío</span><span id="smcart-envio-coste">—</span>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:18px;font-weight:900;color:var(--ac);
      margin-bottom:14px">
      <span>Total</span><span id="smcart-total">—</span>
    </div>
    <a id="smcart-checkout-btn" href="/tienda/__EID__/checkout" style="display:block;text-align:center;
      background:var(--ac);color:#0E1117;border-radius:10px;padding:12px;font-weight:900;
      text-decoration:none;font-size:14px">Finalizar compra</a>
  </div>
</div>
<script>
(function(){
  var eid = "__EID__";
  var moneda = "€";
  var qty = {};
  var cuponActivo = "";

  function fmt(n){ return (Math.round((n||0)*100)/100).toFixed(2).replace(".", ",") + " " + moneda; }

  var btn = document.getElementById('smcart-btn');
  var drawer = document.getElementById('smcart-drawer');
  var backdrop = document.getElementById('smcart-backdrop');
  var cerrar = document.getElementById('smcart-cerrar');
  var cuponInp = document.getElementById('smcart-cupon');
  var cuponBtn = document.getElementById('smcart-aplicar-cupon');
  var cuponMsg = document.getElementById('smcart-cupon-msg');

  function abrir(){ drawer.style.display='flex'; backdrop.style.display='block'; }
  function ocultar(){ drawer.style.display='none'; backdrop.style.display='none'; }
  btn.onclick = function(){ abrir(); cargar(); };
  cerrar.onclick = ocultar;
  backdrop.onclick = ocultar;

  function render(d){
    var badge = document.getElementById('smcart-badge');
    if (d.n_articulos > 0) { badge.style.display='block'; badge.textContent = d.n_articulos; }
    else { badge.style.display='none'; }
    if (d.moneda === 'USD') moneda = '$'; else if (d.moneda === 'GBP') moneda = '£'; else moneda = '€';
    qty = {};
    var cont = document.getElementById('smcart-lineas');
    cont.innerHTML = '';
    if (!d.lineas.length) {
      cont.innerHTML = '<p style="color:#8B949E;font-size:13px;padding:20px 0">Tu carrito está vacío.</p>';
    }
    d.lineas.forEach(function(l){
      qty[l.id] = l.cantidad;
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:10px;padding:12px 0;border-bottom:1px solid #21262D';
      var img = l.imagen ? "background-image:url('" + l.imagen + "')" : '';
      row.innerHTML =
        '<div style="width:56px;height:56px;border-radius:8px;flex:0 0 auto;background:#0D1117 center/cover no-repeat;' + img + '"></div>' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-size:13px;font-weight:700;color:#E6EDF3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + l.nombre + '</div>' +
          '<div style="font-size:12px;color:#8B949E;margin:4px 0">' + fmt(l.precio_unitario) + ' / ud.</div>' +
          '<div style="display:flex;align-items:center;gap:6px">' +
            '<button data-menos="' + l.id + '" style="width:22px;height:22px;border-radius:5px;border:1px solid #30363D;background:#0D1117;color:#E6EDF3;cursor:pointer">−</button>' +
            '<span style="font-size:13px;min-width:18px;text-align:center;color:#E6EDF3">' + l.cantidad + '</span>' +
            '<button data-mas="' + l.id + '" style="width:22px;height:22px;border-radius:5px;border:1px solid #30363D;background:#0D1117;color:#E6EDF3;cursor:pointer">+</button>' +
            '<button data-quitar="' + l.id + '" style="margin-left:auto;background:transparent;border:none;color:#F85149;cursor:pointer;font-size:12px">Quitar</button>' +
          '</div>' +
        '</div>';
      cont.appendChild(row);
    });
    Array.prototype.forEach.call(cont.querySelectorAll('[data-menos]'), function(b){
      b.onclick = function(){ cambiarCantidad(b.getAttribute('data-menos'), -1); }; });
    Array.prototype.forEach.call(cont.querySelectorAll('[data-mas]'), function(b){
      b.onclick = function(){ cambiarCantidad(b.getAttribute('data-mas'), 1); }; });
    Array.prototype.forEach.call(cont.querySelectorAll('[data-quitar]'), function(b){
      b.onclick = function(){ quitar(b.getAttribute('data-quitar')); }; });

    document.getElementById('smcart-subtotal').textContent = fmt(d.subtotal);
    var descRow = document.getElementById('smcart-desc-row');
    if (d.descuento_total > 0) {
      descRow.style.display = 'flex';
      document.getElementById('smcart-descuento').textContent = '−' + fmt(d.descuento_total);
    } else { descRow.style.display = 'none'; }
    document.getElementById('smcart-envio-coste').textContent = d.envio.gratis ? 'Gratis' : fmt(d.envio.coste);
    document.getElementById('smcart-total').textContent = fmt(d.total);

    var envioBar = document.getElementById('smcart-envio-bar');
    var envioTxt = document.getElementById('smcart-envio-txt');
    var envioFill = document.getElementById('smcart-envio-fill');
    if (d.envio.umbral_envio_gratis) {
      envioBar.style.display = 'block';
      if (d.envio.falta_para_envio_gratis > 0) {
        envioTxt.textContent = '¡Solo te faltan ' + fmt(d.envio.falta_para_envio_gratis) + ' para tener Envío Gratuito!';
        var pct = Math.min(100, Math.round((d.subtotal / d.envio.umbral_envio_gratis) * 100));
        envioFill.style.width = pct + '%';
      } else {
        envioTxt.textContent = '✓ ¡Tienes Envío Gratuito!';
        envioFill.style.width = '100%';
      }
    } else { envioBar.style.display = 'none'; }

    if (d.cupon) {
      if (d.cupon.valido === false) {
        cuponMsg.style.color = '#F85149'; cuponMsg.textContent = 'Código no válido.';
      } else {
        cuponMsg.style.color = '#3FB950'; cuponMsg.textContent = '✓ Código "' + d.cupon.codigo + '" aplicado.';
      }
    } else { cuponMsg.textContent = ''; }
  }

  function cargar(){
    var q = cuponActivo ? ('?cupon=' + encodeURIComponent(cuponActivo)) : '';
    fetch('/tienda/' + eid + '/carrito/resumen' + q, {credentials:'same-origin'})
      .then(function(r){ return r.json(); }).then(render).catch(function(){});
  }

  function cambiarCantidad(idLinea, delta){
    var nueva = (qty[idLinea] || 0) + delta;
    fetch('/tienda/' + eid + '/carrito/actualizar', {
      method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id_linea: idLinea, cantidad: nueva, cupon: cuponActivo})
    }).then(function(r){ return r.json(); }).then(render).catch(function(){});
  }

  function quitar(idLinea){
    fetch('/tienda/' + eid + '/carrito/quitar', {
      method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id_linea: idLinea, cupon: cuponActivo})
    }).then(function(r){ return r.json(); }).then(render).catch(function(){});
  }

  cuponBtn.onclick = function(){ cuponActivo = cuponInp.value.trim(); cargar(); };

  // `identificador`: {codigo:"..."} (variante concreta) o {id_producto:N} (producto base, sin
  // variante elegida) — el backend acepta cualquiera de los dos (ver `carrito_storefront.anadir`).
  window.__smAddToCart = function(identificador, cantidad, opts){
    opts = opts || {};
    var body = {cantidad: cantidad || 1, cupon: cuponActivo};
    if (identificador && identificador.codigo) body.codigo = identificador.codigo;
    if (identificador && identificador.id_producto) body.id_producto = identificador.id_producto;
    return fetch('/tienda/' + eid + '/carrito/anadir', {
      method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    }).then(function(r){ return r.json(); }).then(function(d){
      render(d);
      if (!opts.silencioso) abrir();
      return d;
    });
  };

  document.addEventListener('DOMContentLoaded', cargar);
  if (document.readyState !== 'loading') cargar();
})();
</script>"""


def _widget_carrito(eid) -> str:
    return _CART_WIDGET_HTML.replace("__EID__", _e(eid))


# Badges de confianza (Fase conversión — ficha de producto): estáticos, sin lógica de negocio,
# bajo el botón principal de compra.
_BADGES_CONFIANZA_HTML = (
    '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;padding-top:14px;'
    'border-top:1px solid #21262D;color:#8B949E;font-size:11px">'
    '<span>🔒 Conexión segura SSL 256-bit</span>'
    '<span>↩️ Garantía de devolución</span>'
    '<span>💳 Visa · Mastercard</span>'
    '<span>🅿️ PayPal</span>'
    '<span>📱 Bizum / Redsys</span>'
    '</div>'
)


def _estimador_entrega_html(eid, pais_destino="ES") -> str:
    """Estimador de entrega dinámico: calcula un rango de 2-4 días hábiles desde HOY (zona horaria
    del servidor) según exista o no una zona de envío configurada para el destino — degradación
    honesta: sin ninguna zona activa, no se inventa una fecha (no se muestra nada)."""
    try:
        from src.services.comercio_digital.envios import zonas as _zonas
        info = _zonas.calcular_envio(pais_destino, 0.0, 0.0, id_empresa=eid)
        if info.get("motivo") == "sin_zonas_configuradas":
            return ""
    except Exception:
        return ""
    import datetime as _dt
    hoy = _dt.date.today()
    dias_min, dias_max = [], []
    d = hoy
    while len(dias_min) < 2:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            dias_min.append(d)
    d = hoy
    while len(dias_max) < 4:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            dias_max.append(d)
    _MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre")
    _DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    desde, hasta = dias_min[-1], dias_max[-1]
    txt = (f"{_DIAS[desde.weekday()]} {desde.day} de {_MESES[desde.month - 1]}"
           if desde != hasta else "")
    txt_hasta = f"{_DIAS[hasta.weekday()]} {hasta.day} de {_MESES[hasta.month - 1]}"
    frase = f"Recíbelo entre el {txt} y el {txt_hasta}" if txt else f"Recíbelo el {txt_hasta}"
    return (f'<p style="color:#8B949E;font-size:13px;margin:10px 0">🚚 {_e(frase)}'
            f'{" (" + _e(info["zona"]) + ")" if info.get("zona") else ""}</p>')


def _tema_guardado(cfg):
    """Fase 4 (editor visual): `web_config.tema_json` vacío/ausente/corrupto → `None` (la home
    sigue generándose con el layout fijo de siempre, degradación honesta — nunca una página rota
    por un JSON mal formado). Solo un tema con ALGUNA sección activa el renderizado por bloques."""
    crudo = (cfg or {}).get("tema_json")
    if not crudo:
        return None
    try:
        import json
        tema = json.loads(crudo)
        if tema.get("secciones"):
            return tema
    except Exception:
        logger.warning("tema_json inválido para la tienda, se usa el layout por defecto")
    return None


def _layout(cfg, eid, titulo, contenido, chat=True, carrito=True):
    color = cfg.get("color") or "#00FFC6"
    color2 = cfg.get("color_secundario") or "#161B22"
    nombre = _e(cfg.get("nombre") or "Tienda")
    base = f"/tienda/{_e(eid)}"
    logo = (f'<img src="{_e(cfg["logo_url"])}" alt="{nombre}" style="height:40px">'
            if cfg.get("logo_url") else f'<span class="logo">{nombre}</span>')
    widget = (_widget_chat(eid) if chat else "") + (_widget_carrito(eid) if carrito else "")
    # PWA (Generador de Apps Móviles, Fase 1): manifest + Service Worker + metas de instalación,
    # generados dinámicamente por empresa a partir de la MISMA `web_config` (nombre/color/logo) —
    # ver `pagina_manifest`/`pagina_service_worker` más abajo. `theme-color` = color primario (barra
    # del navegador/status-bar); el manifest usa además `color_secundario` como `background_color`.
    icono = cfg.get("logo_url") or ""
    pwa_tags = f"""
<link rel="manifest" href="{base}/manifest.webmanifest">
<meta name="theme-color" content="{_e(color)}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{nombre}">""" + (
        f'\n<link rel="apple-touch-icon" href="{_e(icono)}">' if icono else "") + """
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('""" + base + """/sw.js').catch(function () {});
  });
}
</script>"""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · {nombre}</title>{pwa_tags}<style>
:root{{--ac:{color};--ac2:{color2};}}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;
background:#0E1117;color:#E6EDF3}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac);position:sticky;top:0;z-index:9}}
.logo{{font-weight:900;font-size:22px;color:var(--ac)}}
header form{{margin-left:auto}}header input{{padding:8px 12px;border-radius:8px;border:1px solid #30363D;
background:#161B22;color:#E6EDF3;min-width:220px}}
nav{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 24px;background:#0D1117;border-bottom:1px solid #21262D}}
nav a{{color:#8B949E;text-decoration:none;font-weight:700;font-size:13px;padding:4px 8px}}
nav a:hover{{color:var(--ac)}}
main{{max-width:1100px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac)}}h2{{border-bottom:1px solid #21262D;padding-bottom:6px;margin-top:32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}}
.card{{background:#161B22;border:1px solid #30363D;border-radius:12px;overflow:hidden;
transition:.15s}}.card:hover{{border-color:var(--ac);transform:translateY(-2px)}}
.card a{{color:inherit;text-decoration:none;display:block}}
.card .ph{{height:150px;background:#0D1117 center/cover no-repeat;display:flex;align-items:center;
justify-content:center;color:#30363D;font-size:40px}}
.card .body{{padding:12px}}.card .nom{{font-weight:700;font-size:14px;min-height:38px}}
.card .pr{{color:var(--ac);font-weight:900;font-size:16px;margin-top:6px}}
.badge{{display:inline-block;background:var(--ac);color:#0E1117;border-radius:6px;
padding:1px 7px;font-size:11px;font-weight:900;margin-right:4px}}
.no{{color:#F85149;font-weight:700}}
.detalle{{display:flex;gap:24px;flex-wrap:wrap}}.detalle .img{{flex:1 1 320px;min-height:280px;
background:#161B22 center/contain no-repeat;border:1px solid #30363D;border-radius:12px}}
.detalle .info{{flex:1 1 320px}}
footer{{text-align:center;color:#8B949E;padding:28px;font-size:12px;border-top:1px solid #21262D;margin-top:40px}}
</style></head><body>
<header>{logo}<form action="{base}/buscar"><input name="q" placeholder="Buscar…"></form></header>
{contenido}
<footer>{nombre} · Generado por Smart Manager AI</footer>
{widget}
</body></html>"""


def _nav(cfg, eid, categorias):
    base = f"/tienda/{_e(eid)}"
    links = [f'<a href="{base}">Inicio</a>']
    for c in categorias:
        links.append(f'<a href="{base}/categoria/{_e(c.get("slug") or c["id"])}">{_e(c["nombre"])}</a>')
    return "<nav>" + "".join(links) + "</nav>"


def _card(p, eid, moneda):
    base = f"/tienda/{_e(eid)}"
    img = (f'style="background-image:url(\'{_e(p["imagen"])}\')"' if p.get("imagen") else "")
    ph = "" if p.get("imagen") else "🛍"
    badges = ""
    if p.get("destacado"):
        badges += '<span class="badge">Destacado</span>'
    precio = (_precio(p.get("precio"), moneda) if p.get("disponible")
              else '<span class="no">No disponible</span>')
    return (f'<div class="card"><a href="{base}/producto/{_e(p.get("slug") or p["id"])}">'
            f'<div class="ph" {img}>{ph}</div><div class="body">'
            f'<div class="nom">{badges}{_e(p.get("nombre"))}</div>'
            f'<div class="pr">{precio}</div></div></a></div>')


def _grid(prods, eid, moneda):
    if not prods:
        return '<p style="color:#8B949E">No hay productos.</p>'
    return '<div class="grid">' + "".join(_card(p, eid, moneda) for p in prods) + "</div>"


# ── PWA (Generador de Apps Móviles, Fase 1) — manifest + Service Worker ──────
# Funciones puras (testeables sin Flask), mismo criterio que el resto de `pagina_*`: generan el
# CONTENIDO a partir de la MISMA `web_config` que ya sirve la tienda — ninguna tabla/motor nuevo.
def manifest_pwa(eid, cfg=None) -> dict:
    """Contenido JSON del manifest.webmanifest de la app instalable de esta empresa. Degradación
    honesta: sin `logo_url` configurado, `icons` queda vacío (nunca se inventa un icono)."""
    cfg = cfg or web_tienda.obtener_config(eid)
    nombre = (cfg.get("nombre") or "Tienda").strip()
    color = cfg.get("color") or "#00FFC6"
    color2 = cfg.get("color_secundario") or color
    icono = (cfg.get("logo_url") or "").strip()
    manifest = {
        "name": nombre,
        "short_name": nombre[:12] or "Tienda",
        "description": (cfg.get("descripcion") or f"App de {nombre}").strip(),
        "start_url": f"/tienda/{eid}?fuente=pwa",
        "scope": f"/tienda/{eid}/",
        "id": f"/tienda/{eid}/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": color2,
        "theme_color": color,
        "lang": "es",
        "icons": [],
    }
    if icono:
        manifest["icons"] = [
            {"src": icono, "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": icono, "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]
    return manifest


def service_worker_js(eid) -> str:
    """Service Worker de la app: precachea el "app shell" (home + manifest) en la instalación y
    sirve red-primero/respaldo-en-caché para TODA petición GET del MISMO origen bajo
    `/tienda/<eid>/` — base de "Soporte Offline Básico". Esto cubre, sin lista explícita, las
    páginas de fidelización (Fase 3: tarjeta/QR, puntos, perfil, historial de tickets, recogidas):
    en cuanto el cliente las visita una vez con red, quedan cacheadas para verlas offline después
    (el `fetch` handler de abajo las guarda en caché en cada visita con éxito, no solo el shell)."""
    base = f"/tienda/{eid}"
    cache = f"sm-pwa-{eid}-v1"
    urls_shell = [base, f"{base}/manifest.webmanifest"]
    urls_js = json.dumps(urls_shell)
    return f"""const CACHE = {json.dumps(cache)};
const APP_SHELL = {urls_js};

self.addEventListener('install', function (ev) {{
  self.skipWaiting();
  ev.waitUntil(
    caches.open(CACHE).then(function (c) {{ return c.addAll(APP_SHELL).catch(function () {{}}); }})
  );
}});

self.addEventListener('activate', function (ev) {{
  ev.waitUntil(
    caches.keys().then(function (claves) {{
      return Promise.all(claves.filter(function (k) {{ return k !== CACHE; }})
                              .map(function (k) {{ return caches.delete(k); }}));
    }}).then(function () {{ return self.clients.claim(); }})
  );
}});

// Red-primero con respaldo en caché: el visitante ve siempre el contenido más fresco posible: si
// no hay red (dentro de la tienda sin cobertura), cae a lo último cacheado — nunca una pantalla en
// blanco. Solo intercepta peticiones GET del MISMO origen bajo esta tienda.
self.addEventListener('fetch', function (ev) {{
  var req = ev.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (req.url.indexOf({json.dumps(base)}) === -1) return;
  ev.respondWith(
    fetch(req).then(function (resp) {{
      var copia = resp.clone();
      caches.open(CACHE).then(function (c) {{ c.put(req, copia); }});
      return resp;
    }}).catch(function () {{ return caches.match(req); }})
  );
}});
"""


# ── Páginas (funciones puras, testeables sin Flask) ──────────────────────────
def pagina_home(eid, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
    tema = _tema_guardado(cfg)
    if tema is not None:
        from src.backend.storefront_bloques import renderizar_home_con_tema
        return renderizar_home_con_tema(eid, cfg, tema)
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    moneda = cfg.get("moneda")
    dest = cat_svc.destacados(interno=False, id_empresa=eid)
    reco = cat_svc.recomendados(interno=False, id_empresa=eid)
    todos = cat_svc.listar_productos(interno=False, id_empresa=eid)
    c = _nav(cfg, eid, cats) + "<main>"
    if cfg.get("descripcion"):
        c += f"<h1>{_e(cfg.get('nombre'))}</h1><p>{_e(cfg['descripcion'])}</p>"
    if dest:
        c += "<h2>Destacados</h2>" + _grid(dest, eid, moneda)
    if reco:
        c += "<h2>Recomendados</h2>" + _grid(reco, eid, moneda)
    c += "<h2>Catálogo</h2>" + _grid(todos, eid, moneda) + "</main>"
    return _layout(cfg, eid, cfg.get("nombre") or "Tienda", c)


def pagina_categoria(eid, slug, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    cobj = next((c for c in cats if str(c.get("slug")) == str(slug) or str(c["id"]) == str(slug)), None)
    if not cobj:
        return _layout(cfg, eid, "Categoría", _nav(cfg, eid, cats) + "<main><h1>Categoría no encontrada</h1></main>"), 404
    prods = cat_svc.listar_productos(interno=False, categoria=cobj["id"], id_empresa=eid)
    c = _nav(cfg, eid, cats) + f"<main><h1>{_e(cobj['nombre'])}</h1>" + _grid(prods, eid, cfg.get("moneda")) + "</main>"
    return _layout(cfg, eid, cobj["nombre"], c), 200


def _selector_variantes_html(eid, slug, variantes, moneda) -> str:
    """Selector de variantes (talla/color/formato…) con actualización de precio/disponibilidad EN
    VIVO, sin recargar la página — AJAX a `/producto/<slug>/variante?sku=...` (`fetch`, vanilla JS,
    mismo patrón ya usado por el carrito/chat). Solo se renderiza si el producto tiene variantes."""
    visibles = [v for v in (variantes or []) if v.get("visible", 1)]
    if not visibles:
        return ""
    opciones = "".join(
        f'<option value="{_e(v.get("sku"))}" data-codigo="{_e(v.get("codigo_articulo") or "")}">'
        f'{_e(" · ".join(f"{k}: {val}" for k, val in (v.get("atributos") or {}).items()) or v.get("sku"))}'
        "</option>" for v in visibles)
    return f"""
<div style="margin:14px 0">
  <label for="sm-variante" style="display:block;font-size:12px;color:#8B949E;margin-bottom:6px">
    Elige una opción:</label>
  <select id="sm-variante" style="width:100%;max-width:320px;padding:9px 10px;border-radius:8px;
    border:1px solid #30363D;background:#161B22;color:#E6EDF3;font-size:13px">
    {opciones}
  </select>
  <p id="sm-variante-stock" style="font-size:12px;color:#8B949E;margin:6px 0 0"></p>
</div>
<script>
(function(){{
  var sel = document.getElementById('sm-variante');
  var eid = "{_e(eid)}", slug = "{_e(slug)}";
  var precioEl = document.querySelector('.pr');
  var stockEl = document.getElementById('sm-variante-stock');
  var addBtn = document.getElementById('sm-add-cart');
  var buyBtn = document.getElementById('sm-buy-now');

  function actualizar(){{
    var sku = sel.value;
    fetch('/tienda/' + eid + '/producto/' + slug + '/variante?sku=' + encodeURIComponent(sku), {{credentials:'same-origin'}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        if (!d.ok) return;
        precioEl.textContent = (Math.round(d.precio*100)/100).toFixed(2).replace('.', ',') + ' {_sym(moneda)}';
        if (d.disponible) {{
          stockEl.textContent = (d.stock != null) ? ('Disponible (' + d.stock + ' uds.)') : 'Disponible';
          stockEl.style.color = '#3FB950';
          if (addBtn) addBtn.removeAttribute('disabled');
          if (buyBtn) buyBtn.removeAttribute('disabled');
        }} else {{
          stockEl.textContent = 'Sin stock para esta opción';
          stockEl.style.color = '#F85149';
          if (addBtn) addBtn.setAttribute('disabled', 'disabled');
          if (buyBtn) buyBtn.setAttribute('disabled', 'disabled');
        }}
        var opt = sel.options[sel.selectedIndex];
        window.__smVarianteCodigo = opt.getAttribute('data-codigo') || null;
      }}).catch(function(){{}});
  }}
  sel.addEventListener('change', actualizar);
  actualizar();
}})();
</script>"""


def pagina_producto(eid, slug, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    p = cat_svc.producto(slug=slug, interno=False, id_empresa=eid)
    if not p:
        return _layout(cfg, eid, "Producto", _nav(cfg, eid, cats) + "<main><h1>Producto no encontrado</h1></main>"), 404
    moneda = cfg.get("moneda")
    img = (f'style="background-image:url(\'{_e(p["imagen"])}\')"' if p.get("imagen") else "")
    precio = (_precio(p.get("precio"), moneda) if p.get("disponible")
              else '<span class="no">No disponible</span>')
    galeria = "".join(f'<img src="{_e(u)}" style="height:64px;border-radius:8px;margin:4px;border:1px solid #30363D">'
                      for u in (p.get("galeria") or []) if u)
    info = (f'<div class="info"><h1>{_e(p.get("nombre"))}</h1>'
            f'<p style="font-size:22px" class="pr">{precio}</p>'
            f'<p>{_e(p.get("descripcion"))}</p>')
    if p.get("marca"):
        info += f'<p><b>Marca:</b> {_e(p.get("marca"))}</p>'
    if p.get("atributos"):
        info += "<ul>" + "".join(f'<li>{_e(a.get("nombre"))}: {_e(a.get("valor"))}</li>'
                                 for a in p["atributos"]) + "</ul>"
    info += _selector_variantes_html(eid, slug, p.get("variantes"), moneda)
    info += _estimador_entrega_html(eid)
    disabled = "" if p.get("disponible") else " disabled"
    info += f"""
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
  <button id="sm-add-cart" type="button"{disabled} style="flex:1;min-width:180px;padding:13px 18px;
    border-radius:10px;border:2px solid var(--ac);background:transparent;color:var(--ac);
    font-weight:900;font-size:14px;cursor:pointer">🛒 Añadir al carrito</button>
  <button id="sm-buy-now" type="button"{disabled} style="flex:1;min-width:180px;padding:13px 18px;
    border-radius:10px;border:none;background:var(--ac);color:#0E1117;font-weight:900;
    font-size:14px;cursor:pointer">⚡ Comprar ahora</button>
</div>
<p id="sm-add-msg" style="font-size:12px;margin-top:8px"></p>
{_BADGES_CONFIANZA_HTML}
<script>
(function(){{
  var idProducto = {int(p["id"])};
  var addBtn = document.getElementById('sm-add-cart');
  var buyBtn = document.getElementById('sm-buy-now');
  var msg = document.getElementById('sm-add-msg');
  function payload(){{
    var cod = window.__smVarianteCodigo;
    return cod ? {{codigo: cod}} : {{id_producto: idProducto}};
  }}
  addBtn.onclick = function(){{
    window.__smAddToCart(payload(), 1, {{}}).catch(function(){{}});
  }};
  buyBtn.onclick = function(){{
    msg.style.color = '#8B949E'; msg.textContent = 'Preparando tu pedido…';
    window.__smAddToCart(payload(), 1, {{silencioso:true}}).then(function(){{
      window.location.href = '/tienda/{_e(eid)}/checkout';
    }}).catch(function(){{ msg.style.color = '#F85149'; msg.textContent = 'No se pudo continuar.'; }});
  }};
}})();
</script>"""
    info += "</div>"
    c = (_nav(cfg, eid, cats) + '<main><div class="detalle">'
         f'<div class="img" {img}></div>{info}</div>' + (galeria and f"<div>{galeria}</div>") + "</main>")
    return _layout(cfg, eid, p.get("nombre") or "Producto", c), 200


_PAISES_CHECKOUT = (("ES", "España"), ("PT", "Portugal"), ("FR", "Francia"), ("IT", "Italia"),
                    ("DE", "Alemania"), ("GB", "Reino Unido"), ("US", "Estados Unidos"),
                    ("MX", "México"))


def pagina_checkout(eid, cfg=None) -> str:
    """One-Page Checkout: 1 sola pantalla, sin recargas — contacto → dirección → pago a la
    izquierda, resumen de pedido FIJO a la derecha (re-cotizado en vivo vía `/carrito/resumen`, el
    mismo endpoint que alimenta el Drawer Cart — una sola fuente de verdad para el total)."""
    cfg = cfg or web_tienda.obtener_config(eid)
    from src.db import pagos as pagos_db
    from src.services.tpv.pagos.registry import clase_de
    cfg_pago = pagos_db.obtener_config(eid)
    gateways = []
    proveedor_cfg = (cfg_pago.get("proveedor") or "").strip()
    if proveedor_cfg:
        clase = clase_de(proveedor_cfg)
        if clase is not None:
            try:
                configurado = clase(cfg_pago).configurado()
            except Exception:
                configurado = False
            if configurado:
                gateways.append((proveedor_cfg, proveedor_cfg.capitalize()))
    if not gateways:
        gateways = [("simulado", "Pago de prueba (sin pasarela configurada)")]
    opciones_pago = "".join(
        f'<label style="display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #30363D;'
        f'border-radius:8px;margin-bottom:8px;cursor:pointer">'
        f'<input type="radio" name="pago" value="{_e(cod)}"{" checked" if i == 0 else ""}> '
        f'{_e(nombre)}{" — PayPal Express (pago rápido)" if cod == "paypal" else ""}</label>'
        for i, (cod, nombre) in enumerate(gateways))
    opciones_pais = "".join(
        f'<option value="{_e(c)}"{" selected" if c == "ES" else ""}>{_e(n)}</option>'
        for c, n in _PAISES_CHECKOUT)
    contenido = f"""
<main style="max-width:1100px">
<h1>Finalizar compra</h1>
<div style="display:flex;gap:28px;flex-wrap:wrap-reverse;align-items:flex-start">
  <div style="flex:1 1 420px">
    <h2 style="margin-top:0">1 · Contacto</h2>
    <input id="co-email" type="email" placeholder="Email" required style="width:100%;padding:10px;
      border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin-bottom:14px">
    <h2>2 · Entrega</h2>
    <div style="display:flex;gap:10px;margin-bottom:12px">
      <label style="flex:1;display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #30363D;
        border-radius:8px;cursor:pointer"><input type="radio" name="co-modo" value="envio" checked>
        Envío a domicilio</label>
      <label style="flex:1;display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #30363D;
        border-radius:8px;cursor:pointer"><input type="radio" name="co-modo" value="pickup">
        Recoger en tienda</label>
    </div>
    <div id="co-bloque-envio">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      <input id="co-nombre" placeholder="Nombre y apellidos" required style="flex:1 1 100%;padding:10px;
        border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3">
    </div>
    <input id="co-direccion" placeholder="Dirección (calle, número, piso)" required
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #30363D;background:#161B22;
      color:#E6EDF3;margin-bottom:10px">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      <input id="co-ciudad" placeholder="Ciudad" required style="flex:1 1 140px;padding:10px;
        border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3">
      <input id="co-cp" placeholder="Código postal" required style="flex:1 1 100px;padding:10px;
        border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3">
      <select id="co-pais" style="flex:1 1 140px;padding:10px;border-radius:8px;border:1px solid #30363D;
        background:#161B22;color:#E6EDF3">{opciones_pais}</select>
    </div>
    <input id="co-telefono" placeholder="Teléfono (opcional)" style="width:100%;padding:10px;
      border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin-bottom:14px">
    </div>
    <div id="co-bloque-pickup" style="display:none;margin-bottom:14px">
      <input id="co-nombre-pickup" placeholder="Nombre y apellidos" required style="width:100%;padding:10px;
        border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin-bottom:10px">
      <select id="co-tienda" style="width:100%;padding:10px;border-radius:8px;border:1px solid #30363D;
        background:#161B22;color:#E6EDF3">
        <option value="">Elige la tienda donde recoger…</option>
      </select>
      <p style="font-size:12px;color:#8B949E;margin-top:8px">Tendrás 24 horas para recoger tu pedido
        desde que se confirme el pago. Si no lo recoges, se cancela y se te reembolsa.</p>
    </div>
    <h2>3 · Método de pago</h2>
    <div id="co-pagos">{opciones_pago}</div>
    {_BADGES_CONFIANZA_HTML}
    <p id="co-error" style="color:#F85149;font-size:13px;margin-top:10px"></p>
    <button id="co-pagar" type="button" style="width:100%;margin-top:14px;padding:15px;border-radius:10px;
      border:none;background:var(--ac);color:#0E1117;font-weight:900;font-size:16px;cursor:pointer">
      Pagar <span id="co-pagar-total">—</span></button>
  </div>
  <div style="flex:0 1 340px;position:sticky;top:90px;background:#161B22;border:1px solid #30363D;
    border-radius:12px;padding:16px">
    <h2 style="margin-top:0;border:none;padding:0">Resumen del pedido</h2>
    <div id="co-lineas"></div>
    <div style="display:flex;gap:8px;margin:10px 0">
      <input id="co-cupon" placeholder="Código promocional" style="flex:1;background:#0D1117;
        color:#E6EDF3;border:1px solid #30363D;border-radius:8px;padding:8px 10px;font-size:13px">
      <button id="co-aplicar-cupon" style="background:transparent;border:1px solid var(--ac);
        color:var(--ac);border-radius:8px;padding:0 12px;font-weight:900;cursor:pointer">Aplicar</button>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:13px;color:#8B949E">
      <span>Subtotal</span><span id="co-subtotal">—</span></div>
    <div style="display:flex;justify-content:space-between;font-size:13px;color:#8B949E;margin:4px 0">
      <span>Envío</span><span id="co-envio">—</span></div>
    <div style="display:flex;justify-content:space-between;font-size:19px;font-weight:900;color:var(--ac);
      margin-top:10px;padding-top:10px;border-top:1px solid #30363D">
      <span>Total</span><span id="co-total">—</span></div>
  </div>
</div>
</main>
<script>
(function(){{
  var eid = "{_e(eid)}";
  var cupon = "";
  var emailCapturado = false;

  function pais(){{ return document.getElementById('co-pais').value; }}

  function render(d){{
    document.getElementById('co-subtotal').textContent = fmt(d.subtotal, d.moneda);
    document.getElementById('co-envio').textContent = d.envio.gratis ? 'Gratis' : fmt(d.envio.coste, d.moneda);
    document.getElementById('co-total').textContent = fmt(d.total, d.moneda);
    document.getElementById('co-pagar-total').textContent = fmt(d.total, d.moneda);
    var cont = document.getElementById('co-lineas');
    cont.innerHTML = d.lineas.map(function(l){{
      return '<div style="display:flex;justify-content:space-between;font-size:13px;color:#E6EDF3;' +
        'padding:6px 0;border-bottom:1px solid #21262D"><span>' + l.cantidad + '× ' + l.nombre +
        '</span><span>' + fmt(l.subtotal, d.moneda) + '</span></div>';
    }}).join('') || '<p style="color:#8B949E;font-size:13px">Tu carrito está vacío.</p>';
  }}
  function fmt(n, moneda){{
    var s = (moneda === 'USD') ? '$' : (moneda === 'GBP' ? '£' : '€');
    return (Math.round((n||0)*100)/100).toFixed(2).replace('.', ',') + ' ' + s;
  }}
  function cargar(){{
    var q = '?pais_destino=' + encodeURIComponent(pais()) + (cupon ? '&cupon=' + encodeURIComponent(cupon) : '');
    fetch('/tienda/' + eid + '/carrito/resumen' + q, {{credentials:'same-origin'}})
      .then(function(r){{ return r.json(); }}).then(render).catch(function(){{}});
  }}
  document.getElementById('co-pais').addEventListener('change', cargar);
  document.getElementById('co-aplicar-cupon').onclick = function(){{
    cupon = document.getElementById('co-cupon').value.trim(); cargar();
  }};

  // Click & Collect (Fase 4): alterna entre envío a domicilio y recogida en tienda.
  var tiendasCargadas = false;
  document.querySelectorAll('input[name="co-modo"]').forEach(function(r){{
    r.addEventListener('change', function(){{
      var pickup = this.value === 'pickup';
      document.getElementById('co-bloque-envio').style.display = pickup ? 'none' : '';
      document.getElementById('co-bloque-pickup').style.display = pickup ? '' : 'none';
      if (pickup && !tiendasCargadas) {{
        tiendasCargadas = true;
        fetch('/tienda/' + eid + '/tiendas', {{credentials:'same-origin'}})
          .then(function(r){{ return r.json(); }}).then(function(ts){{
            var sel = document.getElementById('co-tienda');
            (ts || []).forEach(function(t){{
              var o = document.createElement('option'); o.value = t.id; o.textContent = t.nombre;
              sel.appendChild(o);
            }});
          }}).catch(function(){{}});
      }}
    }});
  }});

  // Captura temprana de leads: en cuanto el comprador escribe su email (antes de pagar).
  document.getElementById('co-email').addEventListener('blur', function(){{
    var email = this.value.trim();
    if (!email || emailCapturado) return;
    emailCapturado = true;
    fetch('/tienda/' + eid + '/checkout/email', {{
      method:'POST', credentials:'same-origin', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{email: email}})
    }}).catch(function(){{}});
  }});

  document.getElementById('co-pagar').onclick = function(){{
    var err = document.getElementById('co-error');
    err.textContent = '';
    var modo = (document.querySelector('input[name="co-modo"]:checked') || {{}}).value || 'envio';
    var datos = {{
      email: document.getElementById('co-email').value.trim(),
      modo_entrega: modo,
      cupon: cupon,
      pasarela: (document.querySelector('input[name="pago"]:checked') || {{}}).value
    }};
    if (modo === 'pickup') {{
      datos.nombre = document.getElementById('co-nombre-pickup').value.trim();
      datos.id_tienda = document.getElementById('co-tienda').value;
      if (!datos.email || !datos.nombre || !datos.id_tienda) {{
        err.textContent = 'Completa tu nombre y elige la tienda de recogida antes de pagar.';
        return;
      }}
    }} else {{
      datos.nombre = document.getElementById('co-nombre').value.trim();
      datos.direccion = document.getElementById('co-direccion').value.trim();
      datos.ciudad = document.getElementById('co-ciudad').value.trim();
      datos.cp = document.getElementById('co-cp').value.trim();
      datos.pais = pais();
      datos.telefono = document.getElementById('co-telefono').value.trim();
      if (!datos.email || !datos.nombre || !datos.direccion || !datos.ciudad || !datos.cp) {{
        err.textContent = 'Completa los datos de contacto y envío antes de pagar.';
        return;
      }}
    }}
    var btn = this; btn.setAttribute('disabled', 'disabled'); btn.textContent = 'Procesando…';
    fetch('/tienda/' + eid + '/checkout/confirmar', {{
      method:'POST', credentials:'same-origin', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify(datos)
    }}).then(function(r){{ return r.json(); }}).then(function(d){{
      if (d.ok && d.url) {{ window.location.href = d.url; return; }}
      err.textContent = d.mensaje || 'No se pudo completar el pedido. Inténtalo de nuevo.';
      btn.removeAttribute('disabled'); btn.textContent = 'Pagar';
    }}).catch(function(){{
      err.textContent = 'No se pudo completar el pedido. Inténtalo de nuevo.';
      btn.removeAttribute('disabled'); btn.textContent = 'Pagar';
    }});
  }};

  cargar();
}})();
</script>"""
    return _layout(cfg, eid, "Finalizar compra", contenido, chat=False, carrito=False)


def pagina_confirmacion(eid, pedido, cfg=None) -> str:
    cfg = cfg or web_tienda.obtener_config(eid)
    estado = pedido.get("estado")
    if estado == "PAGADO":
        cab = '<h1 style="color:#3FB950">✓ ¡Gracias por tu compra!</h1><p>Hemos confirmado tu pago.</p>'
    elif estado == "CANCELADO":
        cab = '<h1 class="no">Pedido cancelado</h1>'
    else:
        cab = ("<h1>Pedido recibido</h1>"
               "<p>Estamos confirmando tu pago — te avisaremos por email en cuanto se complete.</p>")
    filas = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #21262D">'
        f'<span>{it["cantidad"]}× {_e(it.get("nombre") or it.get("codigo_articulo"))}</span>'
        f'<span>{_precio(it.get("subtotal"), cfg.get("moneda"))}</span></div>'
        for it in pedido.get("items", []))
    contenido = (
        f'<main><div style="max-width:560px;margin:0 auto">{cab}'
        f'<p style="color:#8B949E">Nº de pedido: <b style="color:#E6EDF3">{_e(str(pedido["id_pedido"])[:8])}</b></p>'
        f'<div style="background:#161B22;border:1px solid #30363D;border-radius:12px;padding:16px;margin-top:16px">'
        f'{filas}<div style="display:flex;justify-content:space-between;font-weight:900;font-size:17px;'
        f'color:var(--ac);padding-top:10px;margin-top:6px;border-top:1px solid #30363D">'
        f'<span>Total</span><span>{_precio(pedido.get("total"), cfg.get("moneda"))}</span></div></div></div></main>'
    )
    return _layout(cfg, eid, "Pedido confirmado", contenido, chat=False, carrito=False)


def pagina_confirmacion_pickup(eid, tx, cfg=None) -> str:
    """Confirmación de una reserva Click & Collect (Fase 4) — misma estructura visual que
    `pagina_confirmacion`, datos de la Transacción Comercial omnicanal en vez del pedido online."""
    cfg = cfg or web_tienda.obtener_config(eid)
    estado = tx.get("estado")
    meta = tx.get("metadata") or {}
    if isinstance(meta, str):
        import json as _json
        try:
            meta = _json.loads(meta)
        except Exception:
            meta = {}
    if estado == "PAGADA":
        limite = meta.get("recogida_limite", "")
        cab = (f'<h1 style="color:#3FB950">✓ ¡Reserva confirmada!</h1>'
              f'<p>Tienes hasta <b>{_e(str(limite)[:16].replace("T", " "))}</b> para recogerla '
              f'en tienda (24 horas).</p>')
    elif estado == "CANCELADA":
        cab = '<h1 class="no">Reserva cancelada</h1>'
    elif estado == "EXPIRADA":
        cab = '<h1 class="no">Reserva caducada</h1><p>No se recogió a tiempo; se ha reembolsado.</p>'
    else:
        cab = ("<h1>Reserva recibida</h1>"
              "<p>Estamos confirmando tu pago — te avisaremos por email en cuanto se complete.</p>")
    filas = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #21262D">'
        f'<span>{it["cantidad"]}× {_e(it.get("nombre") or it.get("codigo_articulo"))}</span>'
        f'<span>{_precio(it.get("subtotal"), cfg.get("moneda"))}</span></div>'
        for it in tx.get("lineas", []))
    contenido = (
        f'<main><div style="max-width:560px;margin:0 auto">{cab}'
        f'<p style="color:#8B949E">Nº de reserva: <b style="color:#E6EDF3">{_e(str(tx["id_tx"])[:8])}</b></p>'
        f'<div style="background:#161B22;border:1px solid #30363D;border-radius:12px;padding:16px;margin-top:16px">'
        f'{filas}<div style="display:flex;justify-content:space-between;font-weight:900;font-size:17px;'
        f'color:var(--ac);padding-top:10px;margin-top:6px;border-top:1px solid #30363D">'
        f'<span>Total</span><span>{_precio(tx.get("total"), cfg.get("moneda"))}</span></div></div></div></main>'
    )
    return _layout(cfg, eid, "Reserva de recogida", contenido, chat=False, carrito=False)


def pagina_buscar(eid, q, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    prods = cat_svc.buscar(q, interno=False, id_empresa=eid) if q else []
    c = (_nav(cfg, eid, cats) + f"<main><h1>Resultados: {_e(q)}</h1>"
         + _grid(prods, eid, cfg.get("moneda")) + "</main>")
    return _layout(cfg, eid, f"Buscar {q}", c)


# ── Cuenta del cliente (Generador de Apps Móviles PWA, Fase 2) — login passwordless + perfil ────
def pagina_cuenta_entrar(eid, cfg=None, *, mensaje=None, error=None) -> str:
    """Pantalla de acceso: Magic Link (email) +, si `py_webauthn` está instalado, un botón de
    acceso rápido por biometría (WebAuthn) — degradación honesta: sin la librería, el botón
    simplemente no aparece, el Magic Link sigue siendo 100% funcional por sí solo."""
    cfg = cfg or web_tienda.obtener_config(eid)
    from src.services.comercio_digital.clientes_auth import webauthn_disponible
    aviso = ""
    if mensaje:
        aviso = f'<p style="color:#3FB950;background:#0D1117;border:1px solid #3FB950;border-radius:8px;padding:12px">{_e(mensaje)}</p>'
    elif error:
        aviso = f'<p class="no" style="background:#0D1117;border:1px solid #F85149;border-radius:8px;padding:12px">{_e(error)}</p>'
    bloque_webauthn = ""
    if webauthn_disponible():
        bloque_webauthn = """
<div style="margin-top:18px;padding-top:18px;border-top:1px solid #21262D">
  <button id="wa-login-btn" type="button" style="width:100%;padding:13px;border-radius:10px;
    border:2px solid var(--ac);background:transparent;color:var(--ac);font-weight:900;
    font-size:14px;cursor:pointer">🔐 Entrar con FaceID / Huella</button>
  <p id="wa-login-msg" style="font-size:12px;margin-top:8px;text-align:center"></p>
</div>"""
    contenido = f"""
<main><div style="max-width:420px;margin:0 auto">
<h1>Accede a tu cuenta</h1>
<p style="color:#8B949E">Sin contraseñas: te enviamos un enlace de acceso de un solo clic a tu email.</p>
{aviso}
<form method="post" action="/tienda/{_e(eid)}/cuenta/entrar">
  <input name="email" type="email" required placeholder="Tu email" style="width:100%;padding:12px;
    border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin-bottom:12px">
  <button type="submit" style="width:100%;padding:13px;border-radius:10px;border:none;
    background:var(--ac);color:#0E1117;font-weight:900;font-size:14px;cursor:pointer">
    Enviarme el enlace de acceso</button>
</form>
{bloque_webauthn}
</div></main>
<script>
(function(){{
  var btn = document.getElementById('wa-login-btn');
  if (!btn || !window.PublicKeyCredential) return;
  function b64uADec(s){{ s=s.replace(/-/g,'+').replace(/_/g,'/'); while(s.length%4)s+='=';
    var bin=atob(s), b=new Uint8Array(bin.length); for(var i=0;i<bin.length;i++)b[i]=bin.charCodeAt(i); return b.buffer; }}
  function decBuf(o){{ o.challenge=b64uADec(o.challenge);
    (o.allowCredentials||[]).forEach(function(c){{c.id=b64uADec(c.id);}}); return o; }}
  function encBuf(b){{ var bytes=new Uint8Array(b); var bin=''; for(var i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''); }}
  btn.onclick = function(){{
    var msg = document.getElementById('wa-login-msg');
    var email = document.querySelector('input[name=email]').value.trim();
    if (!email) {{ msg.textContent = 'Escribe tu email arriba primero.'; msg.style.color='#F85149'; return; }}
    msg.textContent = 'Comprobando…'; msg.style.color = '#8B949E';
    fetch('/tienda/{_e(eid)}/cuenta/webauthn/login/iniciar', {{method:'POST',
      headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{email: email}})}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        if (!d.ok) {{ msg.textContent = 'No se pudo iniciar el acceso rápido.'; msg.style.color='#F85149'; return; }}
        var opts = decBuf(JSON.parse(d.options).publicKey ? JSON.parse(d.options).publicKey : JSON.parse(d.options));
        return navigator.credentials.get({{publicKey: opts}}).then(function(cred){{
          var body = {{email: email, reto: d.reto, respuesta: {{
            id: cred.id, rawId: encBuf(cred.rawId), type: cred.type,
            response: {{
              authenticatorData: encBuf(cred.response.authenticatorData),
              clientDataJSON: encBuf(cred.response.clientDataJSON),
              signature: encBuf(cred.response.signature),
              userHandle: cred.response.userHandle ? encBuf(cred.response.userHandle) : null
            }}}}}};
          return fetch('/tienda/{_e(eid)}/cuenta/webauthn/login/confirmar', {{method:'POST',
            headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body)}}).then(function(r2){{return r2.json();}});
        }});
      }})
      .then(function(d2){{
        if (d2 && d2.ok) {{ window.location.href = '/tienda/{_e(eid)}/cuenta'; }}
        else {{ msg.textContent = 'No se pudo verificar tu huella/FaceID.'; msg.style.color='#F85149'; }}
      }})
      .catch(function(){{ msg.textContent = 'No se pudo completar el acceso rápido.'; msg.style.color='#F85149'; }});
  }};
}})();
</script>"""
    return _layout(cfg, eid, "Acceder", contenido, chat=False, carrito=False)


def pagina_cuenta(eid, cliente, cfg=None, *, mensaje=None) -> str:
    """Perfil editable del cliente — nombre/teléfono/email/dirección, autónomo (sin pasar por un
    empleado). Mismo motor `db.clientes` que ya usa el TPV, nunca una tabla de perfil paralela."""
    cfg = cfg or web_tienda.obtener_config(eid)
    aviso = (f'<p style="color:#3FB950;background:#0D1117;border:1px solid #3FB950;'
            f'border-radius:8px;padding:12px">{_e(mensaje)}</p>') if mensaje else ""
    from src.services.comercio_digital.clientes_auth import webauthn_disponible
    bloque_webauthn = ""
    if webauthn_disponible():
        bloque_webauthn = """
<div style="margin-top:18px;padding-top:18px;border-top:1px solid #21262D">
  <button id="wa-reg-btn" type="button" style="width:100%;padding:12px;border-radius:10px;
    border:2px solid var(--ac);background:transparent;color:var(--ac);font-weight:900;
    font-size:13px;cursor:pointer">🔐 Activar acceso rápido (FaceID / Huella) en este dispositivo</button>
  <p id="wa-reg-msg" style="font-size:12px;margin-top:8px;text-align:center"></p>
</div>"""
    # Tarjeta de fidelización (Fase 3): QR dinámico (el mismo id de cliente que YA resuelve
    # `db.clientes.buscar_cliente_por_codigo`, cero cambios en el lado que escanea) + saldo de
    # puntos real (`db.fidelizacion`, motor ya existente, ahora alimentado de verdad por las
    # ventas). Pantalla PRINCIPAL de la app, arriba del todo — "Tarjeta Digital y Código QR
    # Dinámico" + "Catálogo de Puntos".
    from src.db import fidelizacion as _fid
    puntos = _fid.saldo_puntos(cliente["id"], id_empresa=eid)
    filas_tiers = ""
    for p_req, valor in _fid.TIERS_CANJE:
        puede = puntos >= p_req
        if puede:
            filas_tiers += f"""
  <form method="post" action="/tienda/{_e(eid)}/cuenta/canjear" style="margin:6px 0">
    <input type="hidden" name="puntos" value="{p_req}">
    <button type="submit" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--ac);
      background:transparent;color:var(--ac);font-weight:800;font-size:13px;cursor:pointer">
      Canjear {p_req} puntos → cupón de {valor:g}€</button>
  </form>"""
        else:
            filas_tiers += f"""
  <div style="margin:6px 0;padding:10px;border-radius:10px;border:1px solid #30363D;
    color:#8B949E;font-size:13px;text-align:center">{p_req} puntos → cupón de {valor:g}€</div>"""
    tarjeta = f"""
<div style="background:linear-gradient(135deg,var(--ac2),#0D1117);border:1px solid var(--ac);
  border-radius:16px;padding:20px;margin-bottom:20px;text-align:center">
  <p style="margin:0 0 4px;font-size:12px;color:#8B949E;letter-spacing:1px">TARJETA DE FIDELIZACIÓN</p>
  <p style="margin:0 0 14px;font-size:18px;font-weight:900">{_e(cliente.get('nombre') or 'Cliente')}</p>
  <img src="/tienda/{_e(eid)}/cuenta/tarjeta.png" alt="Código QR de tu tarjeta" width="160" height="160"
    style="background:white;border-radius:12px;padding:8px">
  <p style="margin:14px 0 0;font-size:28px;font-weight:900;color:var(--ac)">{puntos} <span
    style="font-size:13px;color:#8B949E;font-weight:700">puntos</span></p>
  <p style="margin:4px 0 0;font-size:11px;color:#8B949E">Muéstralo en caja para acumular y canjear</p>
</div>
<div style="margin-bottom:20px">
  <p style="margin:0 0 8px;font-size:13px;font-weight:800;color:#8B949E">CATÁLOGO DE PUNTOS</p>
  {filas_tiers}
</div>
<a href="/tienda/{_e(eid)}/cuenta/tickets" style="display:block;text-align:center;margin-bottom:12px;
  padding:12px;border-radius:10px;border:1px solid #30363D;color:#E6EDF3;text-decoration:none;
  font-size:13px;font-weight:700">🧾 Historial de tickets</a>
<a href="/tienda/{_e(eid)}/cuenta/recogidas" style="display:block;text-align:center;margin-bottom:20px;
  padding:12px;border-radius:10px;border:1px solid #30363D;color:#E6EDF3;text-decoration:none;
  font-size:13px;font-weight:700">🏬 Mis recogidas en tienda</a>"""
    contenido = f"""
<main><div style="max-width:480px;margin:0 auto">
<h1>Mi cuenta</h1>
{tarjeta}
{aviso}
<form method="post" action="/tienda/{_e(eid)}/cuenta">
  <label style="font-size:12px;color:#8B949E">Nombre</label>
  <input name="nombre" value="{_e(cliente.get('nombre') or '')}" style="width:100%;padding:11px;
    border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin:4px 0 12px">
  <label style="font-size:12px;color:#8B949E">Email</label>
  <input name="email" type="email" value="{_e(cliente.get('email') or '')}" style="width:100%;padding:11px;
    border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin:4px 0 12px">
  <label style="font-size:12px;color:#8B949E">Teléfono</label>
  <input name="telefono" value="{_e(cliente.get('telefono') or '')}" style="width:100%;padding:11px;
    border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin:4px 0 12px">
  <label style="font-size:12px;color:#8B949E">Dirección de envío</label>
  <input name="direccion" value="{_e(cliente.get('direccion') or '')}" style="width:100%;padding:11px;
    border-radius:8px;border:1px solid #30363D;background:#161B22;color:#E6EDF3;margin:4px 0 16px">
  <button type="submit" style="width:100%;padding:13px;border-radius:10px;border:none;
    background:var(--ac);color:#0E1117;font-weight:900;font-size:14px;cursor:pointer">Guardar cambios</button>
</form>
{bloque_webauthn}
<div id="push-permiso" style="display:none;margin-top:18px;padding:16px;border-radius:12px;
  border:1px solid #30363D;background:#161B22">
  <p style="margin:0 0 10px;font-size:13px">🔔 Activa los avisos para saber al instante cuándo tu
    pedido está listo, o si hay una oferta especial para ti.</p>
  <button id="push-permiso-btn" type="button" style="width:100%;padding:11px;border-radius:10px;
    border:2px solid var(--ac);background:transparent;color:var(--ac);font-weight:900;
    font-size:13px;cursor:pointer">Activar notificaciones</button>
</div>
<form method="post" action="/tienda/{_e(eid)}/cuenta/salir" style="margin-top:18px">
  <button type="submit" style="width:100%;padding:11px;border-radius:10px;border:1px solid #F85149;
    background:transparent;color:#F85149;font-weight:900;font-size:13px;cursor:pointer">Cerrar sesión</button>
</form>
</div></main>
<script>
(function(){{
  // Gestión de permisos (momento de ALTO VALOR, nunca al cargar la página): solo se muestra la
  // tarjeta si el navegador soporta notificaciones Y el usuario no ha decidido ya (ni concedido ni
  // bloqueado) — evita el bloqueo automático típico de pedir el permiso nada más entrar.
  if (!('Notification' in window) || Notification.permission !== 'default') return;
  var caja = document.getElementById('push-permiso');
  if (!caja) return;
  caja.style.display = 'block';
  document.getElementById('push-permiso-btn').onclick = function(){{
    Notification.requestPermission().then(function(estado){{
      caja.style.display = 'none';
    }});
  }};
}})();
(function(){{
  var btn = document.getElementById('wa-reg-btn');
  if (!btn || !window.PublicKeyCredential) return;
  function b64uADec(s){{ s=s.replace(/-/g,'+').replace(/_/g,'/'); while(s.length%4)s+='=';
    var bin=atob(s), b=new Uint8Array(bin.length); for(var i=0;i<bin.length;i++)b[i]=bin.charCodeAt(i); return b.buffer; }}
  function decBuf(o){{ o.challenge=b64uADec(o.challenge); o.user.id=b64uADec(o.user.id);
    (o.excludeCredentials||[]).forEach(function(c){{c.id=b64uADec(c.id);}}); return o; }}
  function encBuf(b){{ var bytes=new Uint8Array(b); var bin=''; for(var i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''); }}
  btn.onclick = function(){{
    var msg = document.getElementById('wa-reg-msg');
    msg.textContent = 'Comprobando…'; msg.style.color = '#8B949E';
    fetch('/tienda/{_e(eid)}/cuenta/webauthn/registro/iniciar', {{method:'POST'}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        if (!d.ok) {{ msg.textContent = 'No se pudo iniciar el registro.'; msg.style.color='#F85149'; return; }}
        var opts = decBuf(JSON.parse(d.options).publicKey ? JSON.parse(d.options).publicKey : JSON.parse(d.options));
        return navigator.credentials.create({{publicKey: opts}}).then(function(cred){{
          var body = {{reto: d.reto, respuesta: {{
            id: cred.id, rawId: encBuf(cred.rawId), type: cred.type,
            response: {{
              attestationObject: encBuf(cred.response.attestationObject),
              clientDataJSON: encBuf(cred.response.clientDataJSON)
            }}}}}};
          return fetch('/tienda/{_e(eid)}/cuenta/webauthn/registro/confirmar', {{method:'POST',
            headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body)}}).then(function(r2){{return r2.json();}});
        }});
      }})
      .then(function(d2){{
        if (d2 && d2.ok) {{ msg.textContent = '✓ Acceso rápido activado.'; msg.style.color='#3FB950'; }}
        else {{ msg.textContent = 'No se pudo activar el acceso rápido.'; msg.style.color='#F85149'; }}
      }})
      .catch(function(){{ msg.textContent = 'No se pudo completar el registro.'; msg.style.color='#F85149'; }});
  }};
}})();
</script>"""
    return _layout(cfg, eid, "Mi cuenta", contenido, chat=False, carrito=True)


def pagina_tickets(eid, cliente, cfg=None) -> str:
    """Historial de tickets del cliente (Fase 3) — reutiliza `ventas_busqueda.buscar_ventas`
    (motor de búsqueda de ventas ya existente), filtrado por `cliente_id` + `id_empresa`
    explícitos (nunca el tenant ambiente: esta ruta la sirve un proceso Flask sin sesión de
    escritorio)."""
    cfg = cfg or web_tienda.obtener_config(eid)
    from src.db.ventas_busqueda import buscar_ventas
    ventas = buscar_ventas(cliente_id=cliente["id"], id_empresa=eid, limite=100)
    if ventas:
        filas = "".join(f"""
  <a href="/tienda/{_e(eid)}/cuenta/tickets/{v['id']}.pdf" style="display:block;text-decoration:none;
    color:inherit;padding:14px;margin-bottom:8px;border-radius:10px;border:1px solid #30363D;
    background:#161B22">
    <div style="display:flex;justify-content:space-between">
      <span style="font-weight:800">{_e(str(v.get('fecha') or ''))[:16]}</span>
      <span style="font-weight:900;color:var(--ac)">{float(v.get('total') or 0):.2f}€</span>
    </div>
    <div style="font-size:12px;color:#8B949E;margin-top:4px">{v.get('n_items') or 0} artículo(s)
      · descargar ticket 📄</div>
  </a>""" for v in ventas)
    else:
        filas = '<p style="color:#8B949E;text-align:center">Todavía no tienes compras registradas.</p>'
    contenido = f"""
<main><div style="max-width:480px;margin:0 auto">
<h1>Mis tickets</h1>
{filas}
<a href="/tienda/{_e(eid)}/cuenta" style="display:block;text-align:center;margin-top:12px;
  color:#8B949E;font-size:13px;text-decoration:none">← Volver a mi cuenta</a>
</div></main>"""
    return _layout(cfg, eid, "Mis tickets", contenido, chat=False, carrito=True)


_ESTADOS_RECOGIDA = {
    "CONFIRMADA": ("Pendiente de pago", "#8B949E"),
    "PAGADA": ("Lista para recoger", "#3FB950"),
    "PREPARANDO": ("Preparando tu pedido", "#D29922"),
    "CANCELADA": ("Cancelada", "#8B949E"),
    "EXPIRADA": ("Caducada (reembolsada)", "#8B949E"),
    "ENTREGADA": ("Recogida", "#3FB950"),
    "FACTURADA": ("Recogida", "#3FB950"),
}


def pagina_recogidas(eid, cliente, cfg=None) -> str:
    """Mis reservas de recogida en tienda (Fase 4 — Click & Collect) — lista + cancelación
    voluntaria con reembolso inmediato (motor `comercio_digital.pickup`, ya existente)."""
    cfg = cfg or web_tienda.obtener_config(eid)
    import json as _json
    from src.services.comercio_digital import transacciones as _tx_svc
    txs = []
    for t in _tx_svc.listar(id_empresa=eid, id_tienda=None, limite=100, cliente_id=cliente["id"]):
        meta = t.get("metadata")
        meta = _json.loads(meta) if isinstance(meta, str) else (meta or {})
        if meta.get("cumplimiento") == "PICKUP_STORE":
            txs.append(t)
    if txs:
        filas = ""
        for t in txs:
            etiqueta, color = _ESTADOS_RECOGIDA.get(t.get("estado"), (t.get("estado"), "#8B949E"))
            cancelable = t.get("estado") in ("CONFIRMADA", "PAGADA", "PREPARANDO")
            boton = f"""
    <form method="post" action="/tienda/{_e(eid)}/cuenta/recogidas/{_e(t['id_tx'])}/cancelar"
      onsubmit="return confirm('¿Cancelar esta reserva? Si ya estaba pagada, se reembolsa al momento.')">
      <button type="submit" style="margin-top:8px;padding:8px 14px;border-radius:8px;border:1px solid #F85149;
        background:transparent;color:#F85149;font-weight:800;font-size:12px;cursor:pointer">Cancelar</button>
    </form>""" if cancelable else ""
            filas += f"""
  <div style="padding:14px;margin-bottom:8px;border-radius:10px;border:1px solid #30363D;background:#161B22">
    <div style="display:flex;justify-content:space-between">
      <span style="font-weight:800;color:{color}">{_e(etiqueta)}</span>
      <span style="font-weight:900;color:var(--ac)">{float(t.get('total') or 0):.2f}€</span>
    </div>
    <div style="font-size:12px;color:#8B949E;margin-top:4px">Reserva {_e(str(t['id_tx'])[:8])}</div>
    {boton}
  </div>"""
    else:
        filas = '<p style="color:#8B949E;text-align:center">Todavía no tienes ninguna recogida en tienda.</p>'
    contenido = f"""
<main><div style="max-width:480px;margin:0 auto">
<h1>Mis recogidas</h1>
{filas}
<a href="/tienda/{_e(eid)}/cuenta" style="display:block;text-align:center;margin-top:12px;
  color:#8B949E;font-size:13px;text-decoration:none">← Volver a mi cuenta</a>
</div></main>"""
    return _layout(cfg, eid, "Mis recogidas", contenido, chat=False, carrito=True)


def _no_disponible(cfg, eid):
    return _layout(cfg, eid, "Tienda no disponible",
                   "<main><h1>Tienda no disponible</h1>"
                   "<p>Esta tienda online no está activa.</p></main>", chat=False, carrito=False)


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, Response, abort, request

    bp = Blueprint("storefront", __name__)

    def _cfg_o_404(eid):
        cfg = web_tienda.obtener_config(eid)
        if not cfg.get("activa"):
            abort(404)
        return cfg

    def _credencial_borrador_ok(cfg):
        from src.seguridad.passwords import verificar
        auth = request.authorization
        if not auth or not auth.password:
            return False
        ok, _rehash = verificar(auth.password, cfg["password_hash"])
        return ok

    # ── Carrito (cookie opaca por tienda, 30 días) ───────────────────────────
    def _cookie_carrito(id_empresa):
        return f"sm_cart_{id_empresa}"

    def _token_carrito(id_empresa):
        """Token de sesión del carrito (comprador anónimo, sin login): lee la cookie existente o
        genera una nueva. Devuelve (token, es_nuevo) — el caller fija la cookie en la respuesta
        SOLO si es_nuevo (evita reescribirla en cada petición)."""
        import uuid
        existente = request.cookies.get(_cookie_carrito(id_empresa))
        if existente:
            return existente, False
        return uuid.uuid4().hex, True

    def _con_cookie_carrito(resp, id_empresa, token):
        resp.set_cookie(_cookie_carrito(id_empresa), token, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite="Lax")
        return resp

    # ── Sesión del CLIENTE (Generador de Apps Móviles PWA, Fase 2) ──────────
    def _cookie_cliente(id_empresa):
        return f"sm_cliente_{id_empresa}"

    def _cliente_sesion_actual(id_empresa):
        """Cliente autenticado para la cookie de ESTA petición, o None (sin login todavía) — nunca
        lanza; las rutas que requieren login redirigen a `/cuenta/entrar` si devuelve None."""
        token = request.cookies.get(_cookie_cliente(id_empresa))
        if not token:
            return None
        from src.services.comercio_digital.clientes_auth import sesion_actual
        return sesion_actual(token)

    def _con_cookie_cliente(resp, id_empresa, token_sesion):
        from src.db.clientes_sesiones import DIAS_SESION_DEFECTO
        resp.set_cookie(_cookie_cliente(id_empresa), token_sesion,
                        max_age=60 * 60 * 24 * DIAS_SESION_DEFECTO, httponly=True, samesite="Lax")
        return resp

    @bp.before_request
    def _gate_borrador():
        # Fase 5 (borrador con contraseña): `activa=0` sigue dando 404 normal (gestionado por cada
        # ruta, sin cambios). `borrador=1` + `password_hash` deja la tienda RESPONDER pero exige
        # HTTP Basic antes de servir cualquier página — gate único, no se repite en cada vista.
        eid = (request.view_args or {}).get("id_empresa")
        if not eid:
            return None
        cfg = web_tienda.obtener_config(eid)
        if not cfg.get("activa") or not cfg.get("borrador") or not cfg.get("password_hash"):
            return None
        if _credencial_borrador_ok(cfg):
            return None
        resp = Response(status=401)
        resp.headers["WWW-Authenticate"] = 'Basic realm="Tienda en borrador"'
        return resp

    @bp.get("/tienda/<id_empresa>")
    def home(id_empresa):
        cfg = web_tienda.obtener_config(id_empresa)
        if not cfg.get("activa"):
            return _no_disponible(cfg, id_empresa), 404
        return pagina_home(id_empresa, cfg)

    @bp.get("/tienda/<id_empresa>/manifest.webmanifest")
    def manifest(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        from flask import jsonify
        resp = jsonify(manifest_pwa(id_empresa, cfg))
        resp.headers["Content-Type"] = "application/manifest+json"
        return resp

    @bp.get("/tienda/<id_empresa>/sw.js")
    def service_worker(id_empresa):
        _cfg_o_404(id_empresa)
        from flask import Response as _Resp
        resp = _Resp(service_worker_js(id_empresa), mimetype="application/javascript")
        # Alcance explícito (si no, el navegador lo restringiría al directorio de `sw.js`, que ya
        # coincide, pero se deja explícito por claridad/robustez ante un futuro cambio de ruta).
        resp.headers["Service-Worker-Allowed"] = f"/tienda/{id_empresa}/"
        return resp

    @bp.get("/tienda/<id_empresa>/categoria/<slug>")
    def categoria(id_empresa, slug):
        cfg = _cfg_o_404(id_empresa)
        html, code = pagina_categoria(id_empresa, slug, cfg)
        return html, code

    @bp.get("/tienda/<id_empresa>/producto/<slug>")
    def producto(id_empresa, slug):
        cfg = _cfg_o_404(id_empresa)
        html, code = pagina_producto(id_empresa, slug, cfg)
        return html, code

    @bp.get("/tienda/<id_empresa>/buscar")
    def buscar(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        return pagina_buscar(id_empresa, request.args.get("q", "").strip(), cfg)

    # Chat de soporte (Fase 6 e-commerce): primer endpoint de ESCRITURA del storefront (hasta ahora
    # solo lectura del catálogo). El gate de borrador (`_gate_borrador`, arriba) ya cubre estas dos
    # rutas igual que el resto — sin duplicar la comprobación.
    @bp.post("/tienda/<id_empresa>/soporte/mensaje")
    def soporte_mensaje(id_empresa):
        _cfg_o_404(id_empresa)
        datos = request.get_json(silent=True) or {}
        texto = (datos.get("texto") or "").strip()
        token = (datos.get("token") or "").strip() or None
        if not texto:
            return {"error": "texto_vacio"}, 400
        from src.services.comercio_digital.canal_web import soporte_chat
        return soporte_chat.enviar_mensaje(id_empresa, token, texto)

    @bp.get("/tienda/<id_empresa>/soporte/hilo")
    def soporte_hilo(id_empresa):
        _cfg_o_404(id_empresa)
        token = (request.args.get("token") or "").strip()
        if not token:
            return {"error": "token_requerido"}, 400
        from src.services.comercio_digital.canal_web import soporte_chat
        return soporte_chat.obtener_hilo(id_empresa, token)

    # ── Carrito (Motor de Alta Conversión e-Commerce — Drawer Cart) ──────────
    def _json_resumen(id_empresa, token, es_nuevo):
        from src.services.comercio_digital import carrito_storefront as _carr
        cupon = (request.values.get("cupon") or "").strip() or None
        pais = (request.values.get("pais_destino") or "ES").strip() or "ES"
        datos = _carr.resumen(token, id_empresa, cupon=cupon, pais_destino=pais)
        from flask import jsonify
        resp = jsonify(datos)
        if es_nuevo:
            resp = _con_cookie_carrito(resp, id_empresa, token)
        return resp

    @bp.get("/tienda/<id_empresa>/carrito/resumen")
    def carrito_resumen(id_empresa):
        _cfg_o_404(id_empresa)
        token, nuevo = _token_carrito(id_empresa)
        return _json_resumen(id_empresa, token, nuevo)

    @bp.post("/tienda/<id_empresa>/carrito/anadir")
    def carrito_anadir(id_empresa):
        _cfg_o_404(id_empresa)
        token, nuevo = _token_carrito(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital import carrito_storefront as _carr
        r = _carr.anadir(token, id_empresa, id_producto=datos.get("id_producto"),
                         codigo=datos.get("codigo"), cantidad=datos.get("cantidad") or 1)
        if not r.get("ok"):
            from flask import jsonify
            resp = jsonify({"error": r.get("error")})
            if nuevo:
                resp = _con_cookie_carrito(resp, id_empresa, token)
            return resp, 400
        return _json_resumen(id_empresa, token, nuevo)

    @bp.post("/tienda/<id_empresa>/carrito/actualizar")
    def carrito_actualizar(id_empresa):
        _cfg_o_404(id_empresa)
        token, nuevo = _token_carrito(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital import carrito_storefront as _carr
        _carr.actualizar_cantidad(token, datos.get("id_linea"), datos.get("cantidad") or 0)
        return _json_resumen(id_empresa, token, nuevo)

    @bp.post("/tienda/<id_empresa>/carrito/quitar")
    def carrito_quitar(id_empresa):
        _cfg_o_404(id_empresa)
        token, nuevo = _token_carrito(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital import carrito_storefront as _carr
        _carr.quitar_linea(token, datos.get("id_linea"))
        return _json_resumen(id_empresa, token, nuevo)

    @bp.get("/tienda/<id_empresa>/carrito/restaurar")
    def carrito_restaurar(id_empresa):
        """1 clic desde el correo de recuperación: fija la cookie al `token_sesion` del carrito
        abandonado (las líneas ya están ahí, no se reconstruye nada) y lleva directo al checkout."""
        _cfg_o_404(id_empresa)
        from flask import redirect
        token = (request.args.get("t") or "").strip()
        resp = redirect(f"/tienda/{id_empresa}/checkout" if token else f"/tienda/{id_empresa}")
        if token:
            resp = _con_cookie_carrito(resp, id_empresa, token)
        return resp

    # ── Variantes (selector en vivo de la ficha de producto) ─────────────────
    @bp.get("/tienda/<id_empresa>/producto/<slug>/variante")
    def producto_variante(id_empresa, slug):
        _cfg_o_404(id_empresa)
        sku = (request.args.get("sku") or "").strip()
        p = cat_svc.producto(slug=slug, interno=False, id_empresa=id_empresa)
        if not p:
            return {"ok": False}, 404
        v = next((x for x in (p.get("variantes") or []) if x.get("sku") == sku), None)
        if not v:
            return {"ok": False}, 404
        precio = float(p.get("precio") or 0) + float(v.get("precio_dif") or 0)
        stock = v.get("stock")
        disponible = p.get("disponible") and (stock is None or float(stock) > 0)
        return {"ok": True, "precio": round(precio, 2), "disponible": bool(disponible),
                "stock": stock, "atributos": v.get("atributos")}

    # ── One-Page Checkout ─────────────────────────────────────────────────────
    @bp.get("/tienda/<id_empresa>/checkout")
    def checkout(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        return pagina_checkout(id_empresa, cfg)

    @bp.get("/tienda/<id_empresa>/tiendas")
    def tiendas_recogida(id_empresa):
        # Click & Collect (Fase 4): selector de tienda para recogida — reutiliza
        # `db.tiendas.listar_tiendas` (motor ya existente), tenant-filtrado explícitamente.
        from flask import jsonify
        _cfg_o_404(id_empresa)
        from src.db.tiendas import listar_tiendas
        return jsonify([{"id": t["id"], "nombre": t.get("nombre") or t.get("codigo_tienda")}
                       for t in listar_tiendas(id_empresa=id_empresa)])

    @bp.post("/tienda/<id_empresa>/checkout/email")
    def checkout_email(id_empresa):
        """Captura temprana de leads (pedido explícito): se llama en cuanto el comprador escribe
        su email, ANTES de pagar — para que el carrito sea recuperable aunque abandone aquí mismo."""
        _cfg_o_404(id_empresa)
        token, nuevo = _token_carrito(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital import carrito_storefront as _carr
        ok = _carr.capturar_email(token, id_empresa, datos.get("email") or "")
        from flask import jsonify
        resp = jsonify({"ok": ok})
        if nuevo:
            resp = _con_cookie_carrito(resp, id_empresa, token)
        return resp

    def _checkout_confirmar_pickup(id_empresa, token, datos, email, nombre):
        """Click & Collect (Fase 4): mismo carrito/cotización que el checkout normal, pero
        reutilizando el motor omnicanal `comercio_digital.pickup` (reserva → pago, 24h de plazo,
        auto-expiración/reembolso ya cableados en el Scheduler) en vez de `online_orders_service`
        — NO es un segundo checkout paralelo, es la modalidad PICKUP_STORE del mismo ecosistema."""
        from flask import jsonify
        id_tienda = str(datos.get("id_tienda") or "").strip()
        if not (email and nombre and id_tienda):
            return jsonify({"ok": False, "mensaje": "Completa tu nombre y elige la tienda de recogida."}), 400
        try:
            id_tienda = int(id_tienda)
        except ValueError:
            return jsonify({"ok": False, "mensaje": "Tienda no válida."}), 400

        from src.services.comercio_digital import carrito_storefront as _carr
        lineas_carrito = _carr.listar(token)
        if not lineas_carrito:
            return jsonify({"ok": False, "mensaje": "Tu carrito está vacío."}), 400
        _carr.capturar_email(token, id_empresa, email)

        cliente_sesion = _cliente_sesion_actual(id_empresa)
        cliente = {"id": (cliente_sesion or {}).get("id"), "nombre": nombre, "email": email}
        lineas = [{"codigo": l["codigo"], "cantidad": int(l["cantidad"]),
                  "precio_unitario": float(l["precio_unitario"])} for l in lineas_carrito]

        from src.services.comercio_digital import pickup as _pk
        res = _pk.reservar(id_empresa=id_empresa, id_tienda=id_tienda, cliente=cliente,
                           lineas=lineas, canal="web_propia")
        if not res.get("ok"):
            return jsonify({"ok": False, "mensaje": res.get("motivo") or "No hay disponibilidad "
                            "en esa tienda para alguno de los artículos."}), 400
        id_tx = res["id_tx"]
        proveedor = (datos.get("pasarela") or "").strip() or None
        pago = _pk.pagar(id_tx, id_empresa=id_empresa, proveedor=proveedor)
        base_absoluta = request.url_root.rstrip("/")
        url_confirmacion = f"{base_absoluta}/tienda/{id_empresa}/pickup/confirmacion/{id_tx}"
        if not pago.get("ok"):
            # La reserva queda creada (CONFIRMADA) pero sin cobrar — el cliente puede reintentar el
            # pago desde la propia página de confirmación en vez de perder la reserva.
            resp = jsonify({"ok": True, "url": url_confirmacion})
        elif pago.get("pendiente"):
            resp = jsonify({"ok": True, "url": pago.get("url") or url_confirmacion})
        else:
            _carr.vaciar(token)
            resp = jsonify({"ok": True, "url": url_confirmacion})
        return _con_cookie_carrito(resp, id_empresa, token)

    @bp.post("/tienda/<id_empresa>/checkout/confirmar")
    def checkout_confirmar(id_empresa):
        """Confirma el pedido: re-cotiza SIEMPRE en el servidor (nunca se confía en un total
        calculado por el cliente), crea el pedido online (motor YA existente,
        `tpv.online_orders_service.crear_pedido_online`) e inicia el cobro con la pasarela
        configurada de ESTA empresa (`crear_cobro`, ya corregido para resolverla por el pedido, no
        por un contexto ambiente de escritorio que este proceso Flask no tiene)."""
        from flask import jsonify
        _cfg_o_404(id_empresa)
        token, _nuevo = _token_carrito(id_empresa)
        datos = request.get_json(silent=True) or {}
        email = (datos.get("email") or "").strip()
        nombre = (datos.get("nombre") or "").strip()

        if (datos.get("modo_entrega") or "envio") == "pickup":
            return _checkout_confirmar_pickup(id_empresa, token, datos, email, nombre)

        direccion = (datos.get("direccion") or "").strip()
        ciudad = (datos.get("ciudad") or "").strip()
        cp = (datos.get("cp") or "").strip()
        pais = (datos.get("pais") or "ES").strip() or "ES"
        if not (email and nombre and direccion and ciudad and cp):
            return jsonify({"ok": False, "mensaje": "Faltan datos de contacto o envío."}), 400

        from src.services.comercio_digital import carrito_storefront as _carr
        lineas_carrito = _carr.listar(token)
        if not lineas_carrito:
            return jsonify({"ok": False, "mensaje": "Tu carrito está vacío."}), 400
        _carr.capturar_email(token, id_empresa, email)

        cupon = (datos.get("cupon") or "").strip() or None
        from src.services.comercio_digital.comercial import cotizar
        lineas_cotizar = [{"codigo": l["codigo"], "cantidad": int(l["cantidad"]),
                           "precio_unitario": float(l["precio_unitario"])} for l in lineas_carrito]
        q = cotizar(lineas_cotizar, cupon=cupon, pais_destino=pais, id_empresa=id_empresa)
        por_codigo = {d["codigo"]: d for d in q["lineas"]}
        lineas_pedido = [{"codigo": l["codigo"], "nombre": l.get("nombre"),
                          "cantidad": int(l["cantidad"]),
                          "precio": por_codigo.get(l["codigo"], {}).get("precio_unitario",
                                                                        float(l["precio_unitario"])),
                          "subtotal": por_codigo.get(l["codigo"], {}).get("neto")}
                         for l in lineas_carrito]
        if q["envio"]["coste"]:
            lineas_pedido.append({"codigo": "ENVIO", "nombre": "Gastos de envío", "cantidad": 1,
                                  "precio": q["envio"]["coste"], "subtotal": q["envio"]["coste"]})
        direccion_envio = f"{direccion}, {ciudad} {cp}, {pais}"

        from src.services.tpv import online_orders_service as _onl
        id_pedido = _onl.crear_pedido_canal_externo(
            {"nombre": nombre, "email": email, "telefono": datos.get("telefono")},
            lineas_pedido, direccion_envio=direccion_envio, plataforma="web_propia",
            cp_cliente=cp, id_empresa=id_empresa)
        if not id_pedido:
            return jsonify({"ok": False, "mensaje": "No se pudo registrar el pedido."}), 500
        if cupon and (q.get("cupon") or {}).get("valido"):
            from src.services.comercio_digital.comercial import redimir_cupon as _redimir
            # `id_venta` se deja en None a propósito (mismo criterio ya establecido en
            # `comercio_digital.checkout.confirmar`): `cupones.id_venta_uso` es BIGINT (pensado
            # para el `id` numérico de la venta TPV/VTA heredada) — `id_pedido` aquí es un UUID,
            # incompatible. `importe_pedido` replica el mismo cálculo que usa `cotizar` para
            # validar el mínimo de pedido (subtotal post-promociones, antes del cupón).
            _redimir(cupon, importe_pedido=q["subtotal"] - q["descuento_promociones"],
                    id_empresa=id_empresa)

        res_cobro = _onl.crear_cobro(id_pedido)
        base_absoluta = request.url_root.rstrip("/")
        url_confirmacion = f"{base_absoluta}/tienda/{id_empresa}/checkout/confirmacion/{id_pedido}"
        proveedor = (datos.get("pasarela") or "").strip()
        if not res_cobro.get("ok") or proveedor == "simulado":
            # Sin pasarela real configurada (o modo de pruebas explícito): el pedido queda
            # registrado igualmente — nunca se marca PAGADO sin una confirmación real de cobro
            # (degradación honesta); la página de confirmación muestra el estado PENDIENTE tal cual.
            _carr.vaciar(token)
            resp = jsonify({"ok": True, "url": url_confirmacion})
        else:
            resp = jsonify({"ok": True, "url": res_cobro["url"]})
        return _con_cookie_carrito(resp, id_empresa, token)

    @bp.get("/tienda/<id_empresa>/checkout/confirmacion/<id_pedido>")
    def checkout_confirmacion(id_empresa, id_pedido):
        """Página de agradecimiento — también sirve de URL de retorno para pasarelas redirect-based
        (Stripe/PayPal/Redsys hosted): sincroniza el estado real con la pasarela antes de mostrarlo,
        nunca confía en que el simple retorno del navegador signifique pago confirmado."""
        cfg = _cfg_o_404(id_empresa)
        from src.services.tpv import online_orders_service as _onl
        pedido = _onl.obtener_pedido(id_pedido)
        if not pedido or pedido.get("id_empresa") != id_empresa:
            from flask import abort as _abort
            _abort(404)
        if pedido.get("estado") == "PENDIENTE" and pedido.get("referencia_pago"):
            _onl.verificar_pago(id_pedido)
            pedido = _onl.obtener_pedido(id_pedido)
        token, _nuevo = _token_carrito(id_empresa)
        from src.services.comercio_digital import carrito_storefront as _carr
        _carr.vaciar(token)
        return pagina_confirmacion(id_empresa, pedido, cfg)

    @bp.get("/tienda/<id_empresa>/pickup/confirmacion/<id_tx>")
    def pickup_confirmacion(id_empresa, id_tx):
        cfg = _cfg_o_404(id_empresa)
        from src.services.comercio_digital import transacciones as _tx_svc
        tx = _tx_svc.obtener(id_tx, id_empresa)
        import json as _json
        meta = tx.get("metadata") if tx else None
        meta = _json.loads(meta) if isinstance(meta, str) else (meta or {})
        if not tx or meta.get("cumplimiento") != "PICKUP_STORE":
            from flask import abort as _abort
            _abort(404)
        tx["metadata"] = meta
        return pagina_confirmacion_pickup(id_empresa, tx, cfg)

    # ── Cuenta del cliente (Generador de Apps Móviles PWA, Fase 2) ───────────
    @bp.get("/tienda/<id_empresa>/cuenta/entrar")
    def cuenta_entrar(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        if _cliente_sesion_actual(id_empresa):
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta")
        return pagina_cuenta_entrar(id_empresa, cfg)

    @bp.post("/tienda/<id_empresa>/cuenta/entrar")
    def cuenta_solicitar_entrada(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        email = (request.form.get("email") or "").strip()
        from src.services.comercio_digital.clientes_auth import solicitar_magic_link
        r = solicitar_magic_link(id_empresa, email, base_url=request.url_root.rstrip("/"))
        if r.get("ok"):
            return pagina_cuenta_entrar(
                id_empresa, cfg,
                mensaje="✉️ Te hemos enviado un enlace de acceso. Revisa tu email (puede tardar "
                       "unos minutos, y caduca en 15 minutos).")
        _MOTIVOS = {
            "email_invalido": "Introduce un email válido.",
            "sin_buzon_activo": "Esta tienda no tiene el correo configurado todavía — contacta con ella directamente.",
        }
        return pagina_cuenta_entrar(
            id_empresa, cfg, error=_MOTIVOS.get(r.get("motivo"), "No se pudo enviar el enlace. Inténtalo de nuevo."))

    @bp.get("/tienda/<id_empresa>/cuenta/entrar/confirmar")
    def cuenta_confirmar_entrada(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        token = (request.args.get("t") or "").strip()
        from src.services.comercio_digital.clientes_auth import confirmar_magic_link
        r = confirmar_magic_link(token) if token else {"ok": False}
        if not r.get("ok") or str(r.get("id_empresa")) != str(id_empresa):
            return pagina_cuenta_entrar(
                id_empresa, cfg, error="Este enlace no es válido o ha caducado. Solicita uno nuevo.")
        from flask import redirect
        resp = redirect(f"/tienda/{id_empresa}/cuenta")
        return _con_cookie_cliente(resp, id_empresa, r["token_sesion"])

    @bp.get("/tienda/<id_empresa>/cuenta")
    def cuenta(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        return pagina_cuenta(id_empresa, cliente, cfg)

    @bp.post("/tienda/<id_empresa>/cuenta")
    def cuenta_actualizar(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        from src.db import clientes as cli_db
        cli_db.actualizar_cliente(
            cliente["id"], id_empresa=id_empresa,
            nombre=(request.form.get("nombre") or "").strip() or cliente.get("nombre"),
            email=(request.form.get("email") or "").strip() or cliente.get("email"),
            telefono=(request.form.get("telefono") or "").strip(),
            direccion=(request.form.get("direccion") or "").strip())
        cliente = cli_db.obtener_cliente(cliente["id"])
        return pagina_cuenta(id_empresa, cliente, cfg, mensaje="✓ Datos actualizados.")

    @bp.post("/tienda/<id_empresa>/cuenta/canjear")
    def cuenta_canjear(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        from src.db import fidelizacion as _fid
        try:
            puntos = int(request.form.get("puntos") or 0)
        except ValueError:
            puntos = 0
        r = _fid.canjear_por_cupon(cliente["id"], puntos, id_empresa=id_empresa)
        if r.get("ok"):
            mensaje = f"✓ Cupón generado: {r['codigo']} ({r['valor']:g}€, válido hasta {r['caduca']})."
        else:
            mensaje = None
        from src.db import clientes as cli_db
        cliente = cli_db.obtener_cliente(cliente["id"])
        html = pagina_cuenta(id_empresa, cliente, cfg, mensaje=mensaje)
        if not r.get("ok"):
            html = html.replace(
                "<h1>Mi cuenta</h1>",
                '<h1>Mi cuenta</h1><p style="color:#F85149;background:#0D1117;border:1px solid '
                '#F85149;border-radius:8px;padding:12px">No se pudo canjear: saldo insuficiente o '
                'tramo no válido.</p>', 1)
        return html

    @bp.get("/tienda/<id_empresa>/cuenta/recogidas")
    def cuenta_recogidas(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        return pagina_recogidas(id_empresa, cliente, cfg)

    @bp.post("/tienda/<id_empresa>/cuenta/recogidas/<id_tx>/cancelar")
    def cuenta_recogida_cancelar(id_empresa, id_tx):
        _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        from src.services.comercio_digital import transacciones as _tx_svc
        tx = _tx_svc.obtener(id_tx, id_empresa)
        # Propiedad: solo el cliente dueño de la reserva puede cancelarla — nunca basta con el
        # id_tx de la URL (podría pertenecer a otro cliente de la misma tienda).
        if tx and str(tx.get("cliente_id")) == str(cliente["id"]):
            from src.services.comercio_digital import pickup as _pk
            _pk.cancelar(id_tx, id_empresa=id_empresa, motivo="cancelada por el cliente desde la app")
        from flask import redirect
        return redirect(f"/tienda/{id_empresa}/cuenta/recogidas")

    @bp.get("/tienda/<id_empresa>/cuenta/tickets")
    def cuenta_tickets(id_empresa):
        cfg = _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            from flask import redirect
            return redirect(f"/tienda/{id_empresa}/cuenta/entrar")
        return pagina_tickets(id_empresa, cliente, cfg)

    @bp.get("/tienda/<id_empresa>/cuenta/tickets/<int:venta_id>.pdf")
    def cuenta_ticket_pdf(id_empresa, venta_id):
        from flask import abort as _abort, send_file
        _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            _abort(401)
        from src.db.ventas_busqueda import obtener_venta_completa
        v = obtener_venta_completa(venta_id)
        # Doble verificación de propiedad: la venta debe pertenecer a ESTE cliente Y a ESTA
        # empresa — nunca basta con el venta_id de la URL (podría pertenecer a otro tenant u
        # otro cliente).
        if not v or str(v.get("cliente_id")) != str(cliente["id"]) \
                or str(v.get("id_empresa")) != str(id_empresa):
            _abort(404)
        from src.db.empresa import contexto_tenant
        from src.utils.ticket_data import reimprimir_ticket
        with contexto_tenant(id_empresa):
            ruta = reimprimir_ticket(venta_id)
        if not ruta:
            _abort(404)
        return send_file(ruta, mimetype="application/pdf", as_attachment=False,
                         download_name=f"ticket_{venta_id}.pdf")

    @bp.get("/tienda/<id_empresa>/cuenta/tarjeta.png")
    def cuenta_tarjeta_qr(id_empresa):
        # QR dinámico de la tarjeta de fidelización: codifica el id numérico de cliente, que
        # `db.clientes.buscar_cliente_por_codigo` YA resuelve como primera estrategia de
        # búsqueda (confirmado en la auditoría) — cero cambios en el lado que escanea en TPV/
        # autocobro, solo se genera y sirve la imagen aquí.
        from flask import Response, abort
        _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            abort(401)
        import io
        import qrcode
        buf = io.BytesIO()
        qrcode.make(str(cliente["id"])).save(buf, format="PNG")
        return Response(buf.getvalue(), mimetype="image/png",
                        headers={"Cache-Control": "no-store"})

    @bp.post("/tienda/<id_empresa>/cuenta/salir")
    def cuenta_salir(id_empresa):
        _cfg_o_404(id_empresa)
        from flask import redirect
        token = request.cookies.get(_cookie_cliente(id_empresa))
        if token:
            from src.services.comercio_digital.clientes_auth import cerrar_sesion
            cerrar_sesion(token)
        resp = redirect(f"/tienda/{id_empresa}")
        resp.delete_cookie(_cookie_cliente(id_empresa))
        return resp

    # ── WebAuthn (passkey) del cliente — JSON, consumido por el JS de las páginas de arriba ──
    @bp.post("/tienda/<id_empresa>/cuenta/webauthn/registro/iniciar")
    def cuenta_webauthn_registro_iniciar(id_empresa):
        from flask import jsonify
        _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            return jsonify({"ok": False, "error": "sin_sesion"}), 401
        from src.services.comercio_digital.clientes_auth import webauthn_iniciar_registro
        return jsonify(webauthn_iniciar_registro(id_empresa, cliente["id"]))

    @bp.post("/tienda/<id_empresa>/cuenta/webauthn/registro/confirmar")
    def cuenta_webauthn_registro_confirmar(id_empresa):
        from flask import jsonify
        _cfg_o_404(id_empresa)
        cliente = _cliente_sesion_actual(id_empresa)
        if not cliente:
            return jsonify({"ok": False, "error": "sin_sesion"}), 401
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital.clientes_auth import webauthn_confirmar_registro
        return jsonify(webauthn_confirmar_registro(
            id_empresa, cliente["id"], datos.get("reto"), datos.get("respuesta")))

    @bp.post("/tienda/<id_empresa>/cuenta/webauthn/login/iniciar")
    def cuenta_webauthn_login_iniciar(id_empresa):
        from flask import jsonify
        _cfg_o_404(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital.clientes_auth import webauthn_iniciar_login
        return jsonify(webauthn_iniciar_login(id_empresa, (datos.get("email") or "").strip()))

    @bp.post("/tienda/<id_empresa>/cuenta/webauthn/login/confirmar")
    def cuenta_webauthn_login_confirmar(id_empresa):
        from flask import jsonify
        _cfg_o_404(id_empresa)
        datos = request.get_json(silent=True) or {}
        from src.services.comercio_digital.clientes_auth import webauthn_confirmar_login
        r = webauthn_confirmar_login(id_empresa, (datos.get("email") or "").strip(),
                                     datos.get("reto"), datos.get("respuesta"))
        resp = jsonify(r)
        if r.get("ok"):
            resp = _con_cookie_cliente(resp, id_empresa, r["token_sesion"])
        return resp

    return bp
