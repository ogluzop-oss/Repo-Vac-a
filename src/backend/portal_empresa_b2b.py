"""
Extranet B2B de la Empresa (Smart Suppliers · Fase B) — servido por el backend, mismo patrón que
`storefront.py`/`portal_proveedor.py`: HTML por funciones puras + Flask fino. Sesión sin cookies: el
token (emitido por `b2b_sesion_empresa.crear_sesion`, futuro botón "Entrar al portal B2B" del
escritorio — Fase E) viaja en la URL y se revalida en cada petición.

"Actualizar Ofertas B2B" no es una sincronización que haya que disparar: `b2b_catalogo.buscar_para_empresa`
consulta la tabla en vivo en cada petición, así que el botón simplemente vuelve a cargar la página con
los datos más recientes — no hay caché ni copia local que refrescar (nunca se finge una sincronización
que no ocurre).
"""

import logging

from markupsafe import escape

logger = logging.getLogger("backend.portal_empresa_b2b")

_ETIQUETA_UNIDAD = {"kg": "Kilos", "unidad": "Unidades", "pale": "Palés", "caja": "Cajas"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _nav_html(token, activo, *, no_leidos=0):
    base = f"/portal/empresa/{token}"
    badge = f' <span class="badge-alerta">{no_leidos}</span>' if no_leidos else ""
    enlaces = (("dashboard", f"{base}/dashboard", "Inicio"),
              ("catalogo", f"{base}/catalogo", "Catálogo B2B"),
              ("reposicion", f"{base}/reposicion", "Desde reposición"),
              ("carrito", f"{base}/carrito", "Carrito"),
              ("plantillas", f"{base}/plantillas", "Plantillas"),
              ("pedidos", f"{base}/pedidos", f"Mis pedidos{badge}"),
              ("gestion", f"{base}/gestion", "Gestión"))
    return "".join(f'<a href="{href}"{" class=\"on\"" if activo == key else ""}>{label}</a>'
                   for key, href, label in enlaces)


_FLECHA_SVG = ("data:image/svg+xml;utf8,"
              "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E"
              "%3Cpath d='M1 1l5 5 5-5' stroke='%2300FFC6' stroke-width='2' fill='none' "
              "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")

# Un <select> nativo solo se puede restilizar en su estado CERRADO — el popup de opciones lo pinta
# el navegador y ignora casi todo el CSS (colores fijos del SO, sin border-radius/hover propio). Para
# que el desplegado se parezca de verdad al QComboBox del escritorio (fondo oscuro, contorno cian,
# fila resaltada en cian al pasar el ratón), se sustituye la interacción por un popup propio en HTML:
# el <select> original se queda oculto pero sigue existiendo (su valor viaja igual en el formulario),
# así que si este script no llegara a ejecutarse el desplegable nativo seguiría siendo usable.
_CSEL_CSS = """
.csel-wrap{display:block;width:100%;position:relative}
.csel-trigger{padding:9px 10px;border-radius:10px;border:2px solid var(--ac);background:#0D1117;
color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px}
.csel-arrow{width:12px;height:8px;flex:none;background-repeat:no-repeat;background-size:contain}
.csel-pop{display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:50;
background:#0D1117;border:2px solid var(--ac);border-radius:10px;max-height:240px;
overflow-y:auto;padding:4px}
.csel-pop.open{display:block}
.csel-opt{padding:8px 12px;border-radius:6px;color:#E6EDF3;cursor:pointer;font-weight:700;
font-size:14px}
.csel-opt:hover,.csel-opt.sel{background:var(--ac);color:#0D1117}
"""
_CSEL_JS = f"""
document.addEventListener('DOMContentLoaded',function(){{
 document.querySelectorAll('select').forEach(function(sel){{
  var wrap=document.createElement('div');wrap.className='csel-wrap';
  sel.parentNode.insertBefore(wrap,sel);wrap.appendChild(sel);
  var trig=document.createElement('div');trig.className='csel-trigger';trig.tabIndex=0;
  var lbl=document.createElement('span');
  var arw=document.createElement('span');arw.className='csel-arrow';
  arw.style.backgroundImage=`url("{_FLECHA_SVG}")`;
  trig.appendChild(lbl);trig.appendChild(arw);
  var pop=document.createElement('div');pop.className='csel-pop';
  function refrescar(){{var o=sel.options[sel.selectedIndex];lbl.textContent=o?o.textContent:'';}}
  refrescar();
  Array.prototype.forEach.call(sel.options,function(opt,i){{
   var row=document.createElement('div');
   row.className='csel-opt'+(i===sel.selectedIndex?' sel':'');
   row.textContent=opt.textContent;
   row.addEventListener('click',function(){{
    sel.selectedIndex=i;refrescar();
    pop.querySelectorAll('.csel-opt').forEach(function(r){{r.classList.remove('sel');}});
    row.classList.add('sel');pop.classList.remove('open');
    sel.dispatchEvent(new Event('change',{{bubbles:true}}));
   }});
   pop.appendChild(row);
  }});
  trig.addEventListener('click',function(e){{
   e.stopPropagation();
   document.querySelectorAll('.csel-pop.open').forEach(function(p){{if(p!==pop)p.classList.remove('open');}});
   pop.classList.toggle('open');
  }});
  wrap.appendChild(trig);wrap.appendChild(pop);
  sel.style.display='none';
 }});
 document.addEventListener('click',function(){{
  document.querySelectorAll('.csel-pop.open').forEach(function(p){{p.classList.remove('open');}});
 }});
}});
"""

# El botón nativo de <input type=file> (::file-selector-button) y el texto "Ningún archivo
# seleccionado" que lo acompaña son parte del control del sistema operativo: su alto y su
# separación del resto no se pueden ajustar con fiabilidad entre navegadores (de ahí que quedara
# pegado al botón "Importar" con una altura ligeramente distinta). Se sustituye por el mismo patrón
# que el desplegable: un disparador propio con el mismo alto/tipografía que el resto de botones +
# el nombre del archivo en un <span> aparte, con espaciado explícito — el <input> original se
# mantiene oculto pero funcional (el archivo se sigue enviando igual en el formulario).
_CFILE_CSS = """
.cfile-wrap{display:flex;align-items:center;flex-wrap:wrap;gap:14px;margin-top:14px}
.cfile-trigger{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;font-family:'Segoe UI',system-ui,sans-serif;
font-size:13px}
.cfile-trigger:hover{background:var(--ac);color:#0D1117}
.cfile-name{color:#8B949E;font-weight:700;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif}
"""
_CFILE_JS = """
document.addEventListener('DOMContentLoaded',function(){
 document.querySelectorAll('input[type=file]').forEach(function(inp){
  var wrap=document.createElement('div');wrap.className='cfile-wrap';
  inp.parentNode.insertBefore(wrap,inp);wrap.appendChild(inp);
  var trig=document.createElement('div');trig.className='cfile-trigger';trig.tabIndex=0;
  trig.textContent='Seleccionar archivo';
  var name=document.createElement('span');name.className='cfile-name';
  name.textContent='Ningún archivo seleccionado';
  trig.addEventListener('click',function(){inp.click();});
  inp.addEventListener('change',function(){
   name.textContent=(inp.files&&inp.files.length)?inp.files[0].name:'Ningún archivo seleccionado';
  });
  wrap.appendChild(trig);wrap.appendChild(name);
  inp.style.display='none';
 });
});
"""


def _layout(titulo, contenido, nav=""):
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Extranet B2B</title><style>
:root{{--ac:#00FFC6;}}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:#0D1117;color:#E6EDF3}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 24px;background:#0D1117;border-bottom:1px solid #21262D}}
nav a{{color:#8B949E;text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;
border-radius:8px}}nav a.on,nav a:hover{{color:#0D1117;background:var(--ac)}}
main{{max-width:1000px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:#161B22;border:1px solid #30363D;border-radius:12px;padding:18px;margin-bottom:16px}}
label{{display:block;font-size:14px;color:#8B949E;margin:10px 0 4px;font-weight:700}}
input,select{{padding:9px 10px;border-radius:8px;border:1px solid #30363D;
background:#0D1117;color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;
font-weight:700}}
select{{appearance:none;-webkit-appearance:none;border:2px solid var(--ac);border-radius:10px;
background-color:#0D1117;background-image:url("{_FLECHA_SVG}");background-repeat:no-repeat;
background-position:right 12px center;background-size:12px 8px;padding-right:32px;cursor:pointer}}
select:focus{{outline:none;border-color:var(--ac)}}
button,.btn{{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;text-decoration:none;display:inline-block;
font-size:13px;font-family:'Segoe UI',system-ui,sans-serif}}
button:hover,.btn:hover{{background:var(--ac);color:#0D1117}}
.btn-ghost{{background:transparent;color:#8B949E;border:2px solid #30363D}}
.btn-ghost:hover{{background:#8B949E;color:#0D1117;border-color:#8B949E}}
.btn-danger{{background:transparent;color:#F85149;border:2px solid #F85149}}
.btn-danger:hover{{background:#F85149;color:#0D1117}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px;vertical-align:middle}}
th{{color:#8B949E}}
.badge{{display:inline-block;background:#21262D;color:var(--ac);border-radius:6px;padding:2px 8px;
font-size:11px;font-weight:700}}
.badge-ok{{background:#3FB950;color:#0D1117}}
.error{{color:#F85149;font-weight:700}}.ok{{color:#3FB950;font-weight:700}}
.total{{font-size:20px;font-weight:900;color:var(--ac)}}
form.inline{{display:flex;gap:8px;align-items:center}}
form.inline input[type=number]{{width:70px}}
a.gestion-card{{display:block;margin-bottom:10px;padding:14px 16px;text-align:left;
background:transparent;border:2px solid var(--ac);border-radius:10px;text-decoration:none}}
a.gestion-card b{{color:var(--ac)}}
a.gestion-card span{{color:#8B949E;font-size:14px;font-weight:700;
font-family:'Segoe UI',system-ui,sans-serif}}
a.gestion-card:hover{{background:var(--ac)}}
a.gestion-card:hover b,a.gestion-card:hover span{{color:#0D1117}}
.badge-alerta{{display:inline-block;min-width:16px;padding:1px 6px;border-radius:999px;
background:#F85149;color:#fff;font-size:11px;font-weight:900;text-align:center}}
.progreso{{width:100%;height:14px;border-radius:999px;background:#0D1117;border:1px solid #30363D;
overflow:hidden;margin-top:8px}}
.progreso-barra{{height:100%;border-radius:999px;transition:width .2s}}
.chat{{display:flex;flex-direction:column;gap:10px;max-height:420px;overflow-y:auto;margin-bottom:12px}}
.msg{{max-width:75%;padding:8px 12px;border-radius:12px;background:#0D1117;border:1px solid #30363D}}
.msg-propio{{align-self:flex-end;border-color:var(--ac)}}
.msg-otro{{align-self:flex-start}}
.msg-autor{{font-size:11px;color:var(--ac);font-weight:900;margin-bottom:2px}}
.msg-cuerpo{{font-size:14px;color:#E6EDF3;white-space:pre-wrap;word-break:break-word}}
.msg-fecha{{font-size:10px;color:#8B949E;margin-top:4px}}
textarea{{width:100%;padding:9px 10px;border-radius:8px;border:1px solid #30363D;background:#0D1117;
color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;resize:vertical}}
{_CSEL_CSS}
</style></head><body>
<header><span class="logo">🏢 Extranet B2B</span></header>
<nav>{nav}</nav>
<main>{contenido}</main>
<script>{_CSEL_JS}</script>
</body></html>"""


def _pagina_error(titulo, mensaje, codigo=200):
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p></div>")


# ── Dashboard ──────────────────────────────────────────────────────────────────
def pagina_dashboard(token, sesion, *, n_carrito=0, limite_actual=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    valor_limite = f'value="{limite_actual}"' if limite_actual is not None else ""
    return _layout("Inicio", f"""
<div class="card">
<h1>Bienvenido, {_e(sesion.get('nombre_usuario') or 'usuario')}</h1>
<p>Tienda conectada: <span class="badge">#{_e(sesion.get('id_tienda'))}</span>
· Sector: <span class="badge">{_e(sesion.get('sector_id'))}</span></p>
<p>Para reponer una tienda distinta, vuelve a Smart Manager, conéctate remotamente a ella y entra de
nuevo al portal.</p>
<p>Artículos en tu carrito: <span class="badge">{n_carrito}</span></p>
</div>
<div class="card"><h2>Límite de gasto mensual (B2B)</h2>
<p>Aviso visual (no bloqueante) en el carrito cuando el gasto validado del mes más el carrito actual
supere este límite. Déjalo vacío para desactivarlo.</p>
<form class="inline" method="post" action="{base}/dashboard/limite-gasto">
<input type="number" name="limite" step="0.01" min="0" placeholder="Sin límite" {valor_limite}>
<span>€ / mes</span>
<button type="submit">Guardar</button>
</form></div>""", nav=_nav_html(token, "dashboard", no_leidos=no_leidos))


# ── Catálogo B2B ───────────────────────────────────────────────────────────────
def pagina_catalogo(token, articulos, *, texto="", mensaje=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    filas = "".join(f"""<tr>
<td>{_e(a['nombre'])}<br><span class="badge">{_e(a['proveedor_nombre'])}</span></td>
<td>{_ETIQUETA_UNIDAD.get(a['unidad_medida'], a['unidad_medida'])}</td>
<td>{a['moq']}</td><td>{a['precio_unitario']} €</td>
<td><form class="inline" method="post" action="{base}/catalogo/anadir">
<input type="hidden" name="id_catalogo" value="{a['id']}">
<input type="number" name="cantidad" min="{a['moq']}" value="{a['moq']}">
<button type="submit">Añadir</button></form></td></tr>""" for a in articulos)
    tabla = (f"<table><tr><th>Artículo</th><th>Unidad</th><th>MOQ</th><th>Precio</th><th></th></tr>"
            f"{filas}</table>") if articulos else "<p>No hay ofertas disponibles para tu sector ahora mismo.</p>"
    return _layout("Catálogo B2B", f"""
<div class="card">
<h1>Catálogo B2B de tu sector</h1>
<form method="get" action="{base}/catalogo">
<input type="text" name="q" placeholder="Buscar artículo…" value="{_e(texto)}">
<button type="submit" class="btn-ghost">Buscar</button>
<button type="submit" name="actualizar" value="1">🔄 Actualizar Ofertas B2B</button>
</form>
{aviso}{tabla}
</div>""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos))


# ── Desde reposición ─────────────────────────────────────────────────────────
def pagina_reposicion(token, propuestas, *, no_leidos=0):
    base = f"/portal/empresa/{token}"
    filas = []
    for p in propuestas:
        anadido = p["estado"] in ("en_carrito", "tramitada")
        accion = (f'<span class="badge badge-ok">Añadido</span>' if anadido else
                 f'''<form method="post" action="{base}/reposicion/anadir/{p['id']}">
<button type="submit">Añadir al carrito</button></form>''')
        filas.append(f"""<tr><td>{_e(p['nombre'])}</td><td>{p['stock_actual']}</td>
<td>{p['stock_objetivo']}</td><td><b>{p['cantidad']}</b></td>
<td>{accion}</td></tr>""")
    tabla = (f"<table><tr><th>Artículo</th><th>Stock actual</th>"
            f"<th>Objetivo</th><th>Sugerido</th><th></th></tr>{''.join(filas)}</table>"
            if propuestas else "<p>No hay artículos bajo mínimos en tu tienda ahora mismo.</p>")
    return _layout("Desde reposición", f"""
<div class="card">
<h1>Sugerencias de reposición — tu tienda</h1>
<p>Solo se muestran artículos de la tienda con la que estás conectado. Los artículos que no añadas al
carrito seguirán apareciendo aquí; los añadidos se marcan "Añadido" pero no desaparecen hasta que
tramites el pedido.</p>
{tabla}
</div>""", nav=_nav_html(token, "reposicion", no_leidos=no_leidos))


_ORIGEN_ETIQUETA = {"reposicion": "Desde reposición", "plantilla": "Plantilla"}


def _badge_origen(origen):
    return _ORIGEN_ETIQUETA.get(origen, "Catálogo")


def _barra_presupuesto_html(resumen):
    if resumen["limite"] is None:
        return ""
    pct_barra = min(resumen["pct"], 100)
    color = "#F85149" if resumen["excedido"] else "var(--ac)"
    aviso = (f'<p class="error">⚠ El gasto proyectado de este mes ({resumen["proyectado"]} €) supera tu '
            f'límite de {resumen["limite"]} €. Puedes seguir tramitando el pedido si lo necesitas.</p>'
            if resumen["excedido"] else "")
    return f"""<div class="card"><h2>Gasto mensual B2B</h2>
<p>Gasto validado este mes: {resumen['gasto_mes']} € · Carrito actual: {resumen['total_carrito']} € ·
Proyectado: <b>{resumen['proyectado']} €</b> / {resumen['limite']} € ({resumen['pct']}%)</p>
<div class="progreso"><div class="progreso-barra" style="width:{pct_barra}%;background:{color}"></div></div>
{aviso}</div>"""


# ── Carrito ────────────────────────────────────────────────────────────────────
def pagina_carrito(token, lineas, total, *, mensaje=None, error=None, resumen_presupuesto=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (f'<p class="error">{_e(error)}</p>' if error else "")
    filas = "".join(f"""<tr><td>{_e(l['nombre'])}
<br><span class="badge">{_badge_origen(l['origen'])}</span></td>
<td>{l['cantidad']} {_ETIQUETA_UNIDAD.get(l['unidad_medida'], l['unidad_medida'] or '')}</td>
<td>{l['precio_unitario']} €</td>
<td>{round(float(l['cantidad'])*float(l['precio_unitario']), 2)} €</td>
<td><form method="post" action="{base}/carrito/quitar/{l['id']}">
<button type="submit" class="btn-danger">Quitar</button></form></td></tr>""" for l in lineas)
    tabla = (f"<table><tr><th>Artículo</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th>"
            f"<th></th></tr>{filas}</table>") if lineas else "<p>Tu carrito está vacío.</p>"
    acciones = ""
    if lineas:
        acciones = f"""<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
<form method="post" action="{base}/carrito/tramitar"><button type="submit">Tramitar pedido(s)</button></form>
<form class="inline" method="post" action="{base}/carrito/guardar-plantilla">
<input type="text" name="nombre" placeholder="Nombre de la plantilla" required>
<button type="submit" class="btn-ghost">Guardar como plantilla</button></form>
</div>"""
    barra = _barra_presupuesto_html(resumen_presupuesto) if resumen_presupuesto else ""
    return _layout("Carrito", f"""
<div class="card"><h1>Tu carrito</h1>{aviso}{tabla}
<p class="total">Total: {total} €</p>
{acciones}
</div>
{barra}""", nav=_nav_html(token, "carrito", no_leidos=no_leidos))


def pagina_pedido_confirmado(token, pedidos, *, no_leidos=0):
    filas = "".join(f"<li>Pedido <code>{_e(p['id_tx'])}</code> — proveedor #{_e(p['id_suministrador'])} "
                    f"({p['transicion'].get('hasta', '?')})</li>" for p in pedidos)
    return _layout("Pedido tramitado", f"""
<div class="card"><h1 class="ok">✓ Pedido(s) tramitado(s)</h1>
<p>Se ha generado un pedido por cada proveedor de tu carrito:</p>
<ul>{filas}</ul>
<p><a href="/portal/empresa/{_e(token)}/catalogo" style="color:var(--ac);font-weight:700">
Seguir comprando →</a> · <a href="/portal/empresa/{_e(token)}/pedidos" style="color:var(--ac);font-weight:700">
Ver mis pedidos →</a></p>
</div>""", nav=_nav_html(token, "carrito", no_leidos=no_leidos))


# ── Plantillas de aprovisionamiento ───────────────────────────────────────────
def pagina_plantillas(token, plantillas, *, mensaje=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    filas = "".join(f"""<tr><td>{_e(p['nombre'])}</td><td>{p['n_lineas']}</td>
<td>{p['creado_en']}</td>
<td style="display:flex;gap:8px">
<form method="post" action="{base}/plantillas/{p['id']}/enviar">
<button type="submit">Enviar al carrito</button></form>
<form method="post" action="{base}/plantillas/{p['id']}/eliminar">
<button type="submit" class="btn-danger">Eliminar</button></form>
</td></tr>""" for p in plantillas)
    tabla = (f"<table><tr><th>Nombre</th><th>Artículos</th><th>Creada</th><th></th></tr>{filas}</table>"
            if plantillas else "<p>Aún no has guardado ninguna plantilla. Desde el carrito, guarda tus "
            "compras recurrentes con un nombre para reutilizarlas con un clic.</p>")
    return _layout("Plantillas", f"""
<div class="card"><h1>Plantillas de aprovisionamiento</h1>{aviso}{tabla}</div>""",
        nav=_nav_html(token, "plantillas", no_leidos=no_leidos))


# ── Mis pedidos + detalle (chat) ───────────────────────────────────────────────
_ETIQUETA_ESTADO = {"BORRADOR": "Borrador", "CONFIRMADA": "Confirmado", "PAGADA": "Pagado",
                    "PREPARANDO": "Preparando", "ENVIADA": "Enviado", "ENTREGADA": "Entregado",
                    "FACTURADA": "Facturado", "DEVUELTA": "Devuelto", "ABONADA": "Abonado",
                    "CANCELADA": "Cancelado", "EXPIRADA": "Expirado"}


def pagina_mis_pedidos(token, pedidos, *, no_leidos=0):
    base = f"/portal/empresa/{token}"
    filas = "".join(f"""<tr><td><code>{_e(p['id_tx'])}</code></td>
<td>{_e(_ETIQUETA_ESTADO.get(p['estado'], p['estado']))}</td>
<td>{p['total']} €</td><td>{p['creada']}</td>
<td><a class="btn" href="{base}/pedido/{p['id_tx']}">Ver / chat</a></td></tr>""" for p in pedidos)
    tabla = (f"<table><tr><th>Pedido</th><th>Estado</th><th>Total</th><th>Fecha</th>"
            f"<th></th></tr>{filas}</table>") if pedidos else "<p>Aún no has tramitado ningún pedido B2B.</p>"
    return _layout("Mis pedidos", f"""<div class="card"><h1>Mis pedidos</h1>{tabla}</div>""",
        nav=_nav_html(token, "pedidos", no_leidos=no_leidos))


def _burbujas_chat_html(mensajes, lado):
    if not mensajes:
        return "<p>Aún no hay mensajes en este pedido.</p>"
    burbujas = []
    for m in mensajes:
        propio = m["autor_tipo"] == lado
        clase = "msg-propio" if propio else "msg-otro"
        burbujas.append(f"""<div class="msg {clase}">
<div class="msg-autor">{_e(m.get('autor_nombre') or m['autor_tipo'].capitalize())}</div>
<div class="msg-cuerpo">{_e(m['cuerpo'])}</div>
<div class="msg-fecha">{m['creado_en']}</div></div>""")
    return f'<div class="chat">{"".join(burbujas)}</div>'


def pagina_pedido_detalle(token, tx, lineas, mensajes, *, lado="empresa", no_leidos=0):
    base = f"/portal/empresa/{token}"
    filas_lineas = "".join(f"<tr><td>{_e(l['nombre'])}</td><td>{l['cantidad']}</td>"
                           f"<td>{l['precio_unitario']} €</td></tr>" for l in lineas)
    chat = _burbujas_chat_html(mensajes, lado)
    return _layout(f"Pedido {tx['id_tx'][:8]}", f"""
<div class="card"><h1>Pedido <code>{_e(tx['id_tx'])}</code></h1>
<p>Estado: <span class="badge">{_e(_ETIQUETA_ESTADO.get(tx['estado'], tx['estado']))}</span> ·
Total: <b>{tx['total']} €</b> · Fecha: {tx['creada']}</p>
<table><tr><th>Artículo</th><th>Cantidad</th><th>Precio</th></tr>{filas_lineas}</table>
</div>
<div class="card"><h2>Comunicación sobre este pedido</h2>
{chat}
<form method="post" action="{base}/pedido/{tx['id_tx']}/mensaje" style="margin-top:12px">
<textarea name="cuerpo" rows="3" placeholder="Escribe un mensaje…" required></textarea>
<button type="submit" style="margin-top:8px">Enviar</button>
</form></div>""", nav=_nav_html(token, "pedidos", no_leidos=no_leidos))


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_empresa_b2b", __name__, url_prefix="/portal/empresa")

    def _sesion_o_error(token):
        from src.services.compras import b2b_sesion_empresa as SES
        ses = SES.resolver_sesion(token)
        if not ses:
            return None, (_pagina_error("Sesión no válida",
                          "Tu sesión ha caducado. Vuelve a entrar desde Smart Manager."), 401)
        return ses, None

    def _no_leidos(ses):
        try:
            from src.services.compras import b2b_chat as CHAT
            return CHAT.no_leidos_totales_empresa(ses["id_empresa"])
        except Exception:
            return 0

    @bp.get("/<token>/dashboard")
    def dashboard(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_presupuesto as PRES
        return pagina_dashboard(token, ses, n_carrito=len(CART.listar(token)),
                               limite_actual=PRES.obtener_limite(ses["id_empresa"]),
                               no_leidos=_no_leidos(ses))

    @bp.post("/<token>/dashboard/limite-gasto")
    def dashboard_limite_gasto(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_presupuesto as PRES
        PRES.guardar_limite(ses["id_empresa"], request.form.get("limite", ""))
        return redirect(f"/portal/empresa/{token}/dashboard")

    @bp.get("/<token>/catalogo")
    def catalogo(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, sectores
        texto = request.args.get("q", "").strip()
        sector_ids = sectores.compatibles_de(ses["sector_id"])
        arts = CAT.buscar_para_empresa(sector_ids, texto=texto or None)
        for a in arts:
            CAT.registrar_evento(a["id"], ses["id_empresa"], "vista")
        mensaje = "Catálogo actualizado." if request.args.get("actualizar") else None
        return pagina_catalogo(token, arts, texto=texto, mensaje=mensaje, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/catalogo/anadir")
    def catalogo_anadir(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, b2b_carrito as CART, sectores
        id_catalogo = request.form.get("id_catalogo")
        cantidad = request.form.get("cantidad", 1)
        arts = CAT.buscar_para_empresa(sectores.compatibles_de(ses["sector_id"]))
        art = next((a for a in arts if str(a["id"]) == str(id_catalogo)), None)
        if not art:
            return redirect(f"/portal/empresa/{token}/catalogo")
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            cantidad = art["moq"]
        if cantidad < art["moq"]:
            return pagina_catalogo(token, arts, mensaje=None, no_leidos=_no_leidos(ses)), 400
        CAT.registrar_evento(art["id"], ses["id_empresa"], "click")
        CART.anadir(token, id_suministrador=art["id_suministrador"], codigo=art["codigo"],
                   nombre=art["nombre"], unidad_medida=art["unidad_medida"], cantidad=cantidad,
                   precio_unitario=CAT.precio_para_cantidad(art, cantidad), origen="catalogo")
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.get("/<token>/reposicion")
    def reposicion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import reabastecimiento as R
        R.generar_propuestas_tienda(ses["id_tienda"], ses["id_empresa"])
        props = R.listar_propuestas_tienda(ses["id_tienda"],
                                           estados=("pendiente", "en_carrito"),
                                           id_empresa=ses["id_empresa"])
        return pagina_reposicion(token, props, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/reposicion/anadir/<int:id_propuesta>")
    def reposicion_anadir(token, id_propuesta):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import reabastecimiento as R
        from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, sectores
        prop = R.obtener_propuesta(id_propuesta)
        if not prop:
            return redirect(f"/portal/empresa/{token}/reposicion")
        # La sugerencia es de STOCK (umbral/objetivo), no de catálogo B2B: hace falta localizar QUÉ
        # proveedor del catálogo ofrece ese código antes de poder tramitarlo como pedido. Si hay
        # varios, se toma el más barato (criterio simple y explícito, no oculto).
        candidatos = [a for a in CAT.buscar_para_empresa(sectores.compatibles_de(ses["sector_id"]))
                     if a["codigo"] == prop["codigo"]]
        if not candidatos:
            props = R.listar_propuestas_tienda(ses["id_tienda"], estados=("pendiente", "en_carrito"),
                                               id_empresa=ses["id_empresa"])
            return pagina_reposicion(token, props, no_leidos=_no_leidos(ses)), 400
        mejor = min(candidatos, key=lambda a: float(a["precio_unitario"]))
        cantidad = max(prop["cantidad"], mejor["moq"])
        CART.anadir(token, id_suministrador=mejor["id_suministrador"], codigo=prop["codigo"],
                   nombre=prop["nombre"], unidad_medida=mejor["unidad_medida"], cantidad=cantidad,
                   precio_unitario=CAT.precio_para_cantidad(mejor, cantidad), origen="reposicion",
                   id_reab_propuesta=id_propuesta)
        return redirect(f"/portal/empresa/{token}/reposicion")

    @bp.get("/<token>/carrito")
    def carrito(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_presupuesto as PRES
        total = CART.total(token)
        resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
        return pagina_carrito(token, CART.listar(token), total, resumen_presupuesto=resumen,
                              no_leidos=_no_leidos(ses))

    @bp.post("/<token>/carrito/quitar/<int:id_linea>")
    def carrito_quitar(token, id_linea):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART
        CART.quitar_linea(token, id_linea)
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.post("/<token>/carrito/guardar-plantilla")
    def carrito_guardar_plantilla(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_presupuesto as PRES, b2b_plantillas as PLANT
        r = PLANT.guardar_desde_carrito(ses["id_empresa"], request.form.get("nombre", ""), token)
        total = CART.total(token)
        resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
        if not r.get("ok"):
            return pagina_carrito(token, CART.listar(token), total, error=r.get("error"),
                                  resumen_presupuesto=resumen, no_leidos=_no_leidos(ses)), 400
        return pagina_carrito(token, CART.listar(token), total, mensaje="Plantilla guardada.",
                              resumen_presupuesto=resumen, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/carrito/tramitar")
    def carrito_tramitar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_pedidos as PED, b2b_presupuesto as PRES
        r = PED.tramitar(token)
        if not r.get("ok"):
            total = CART.total(token)
            resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
            return pagina_carrito(token, CART.listar(token), total, error=r.get("error"),
                                  resumen_presupuesto=resumen, no_leidos=_no_leidos(ses)), 400
        return pagina_pedido_confirmado(token, r["pedidos"], no_leidos=_no_leidos(ses))

    @bp.get("/<token>/plantillas")
    def plantillas(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        return pagina_plantillas(token, PLANT.listar(ses["id_empresa"]), no_leidos=_no_leidos(ses))

    @bp.post("/<token>/plantillas/<int:id_plantilla>/enviar")
    def plantillas_enviar(token, id_plantilla):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        r = PLANT.enviar_a_carrito(token, ses["id_empresa"], id_plantilla)
        if r.get("ok") and r.get("omitidas"):
            mensaje = (f"{r['anadidas']} artículo(s) añadidos al carrito. Omitidos (ya no disponibles "
                      f"en el catálogo): {', '.join(r['omitidas'])}.")
            return pagina_plantillas(token, PLANT.listar(ses["id_empresa"]), mensaje=mensaje,
                                     no_leidos=_no_leidos(ses))
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.post("/<token>/plantillas/<int:id_plantilla>/eliminar")
    def plantillas_eliminar(token, id_plantilla):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        PLANT.eliminar(ses["id_empresa"], id_plantilla)
        return redirect(f"/portal/empresa/{token}/plantillas")

    @bp.get("/<token>/pedidos")
    def pedidos(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        peds = TX.listar(id_empresa=ses["id_empresa"], id_tienda=None, origen="b2b")
        return pagina_mis_pedidos(token, peds, no_leidos=_no_leidos(ses))

    @bp.get("/<token>/pedido/<id_tx>")
    def pedido_detalle(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        from src.services.compras import b2b_chat as CHAT
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error("Pedido no encontrado", "Ese pedido no existe o no es tuyo."), 404
        CHAT.marcar_leido(id_tx, "empresa")
        return pagina_pedido_detalle(token, tx, tx["lineas"], CHAT.listar_mensajes(id_tx),
                                     lado="empresa", no_leidos=_no_leidos(ses))

    @bp.post("/<token>/pedido/<id_tx>/mensaje")
    def pedido_mensaje(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        from src.services.compras import b2b_chat as CHAT
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error("Pedido no encontrado", "Ese pedido no existe o no es tuyo."), 404
        CHAT.enviar_mensaje(id_tx, "empresa", ses.get("nombre_usuario"), request.form.get("cuerpo", ""))
        return redirect(f"/portal/empresa/{token}/pedido/{id_tx}")

    return bp
