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


def _nav_html(token, activo):
    base = f"/portal/empresa/{token}"
    enlaces = (("dashboard", f"{base}/dashboard", "Inicio"),
              ("catalogo", f"{base}/catalogo", "Catálogo B2B"),
              ("reposicion", f"{base}/reposicion", "Desde reposición"),
              ("carrito", f"{base}/carrito", "Carrito"),
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
  arw.style.backgroundImage="url('{_FLECHA_SVG}')";
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
a.gestion-card span{{color:#8B949E;font-size:12px}}
a.gestion-card:hover{{background:var(--ac)}}
a.gestion-card:hover b,a.gestion-card:hover span{{color:#0D1117}}
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
def pagina_dashboard(token, sesion, *, n_carrito=0):
    return _layout("Inicio", f"""
<div class="card">
<h1>Bienvenido, {_e(sesion.get('nombre_usuario') or 'usuario')}</h1>
<p>Tienda conectada: <span class="badge">#{_e(sesion.get('id_tienda'))}</span>
· Sector: <span class="badge">{_e(sesion.get('sector_id'))}</span></p>
<p>Para reponer una tienda distinta, vuelve a Smart Manager, conéctate remotamente a ella y entra de
nuevo al portal.</p>
<p>Artículos en tu carrito: <span class="badge">{n_carrito}</span></p>
</div>""", nav=_nav_html(token, "dashboard"))


# ── Catálogo B2B ───────────────────────────────────────────────────────────────
def pagina_catalogo(token, articulos, *, texto="", mensaje=None):
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
</div>""", nav=_nav_html(token, "catalogo"))


# ── Desde reposición ─────────────────────────────────────────────────────────
def pagina_reposicion(token, propuestas):
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
</div>""", nav=_nav_html(token, "reposicion"))


# ── Carrito ────────────────────────────────────────────────────────────────────
def pagina_carrito(token, lineas, total, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (f'<p class="error">{_e(error)}</p>' if error else "")
    filas = "".join(f"""<tr><td>{_e(l['nombre'])}
<br><span class="badge">{'Desde reposición' if l['origen']=='reposicion' else 'Catálogo'}</span></td>
<td>{l['cantidad']} {_ETIQUETA_UNIDAD.get(l['unidad_medida'], l['unidad_medida'] or '')}</td>
<td>{l['precio_unitario']} €</td>
<td>{round(float(l['cantidad'])*float(l['precio_unitario']), 2)} €</td>
<td><form method="post" action="{base}/carrito/quitar/{l['id']}">
<button type="submit" class="btn-danger">Quitar</button></form></td></tr>""" for l in lineas)
    tabla = (f"<table><tr><th>Artículo</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th>"
            f"<th></th></tr>{filas}</table>") if lineas else "<p>Tu carrito está vacío.</p>"
    tramitar = (f'<form method="post" action="{base}/carrito/tramitar" style="margin-top:14px">'
               f'<button type="submit">Tramitar pedido(s)</button></form>') if lineas else ""
    return _layout("Carrito", f"""
<div class="card"><h1>Tu carrito</h1>{aviso}{tabla}
<p class="total">Total: {total} €</p>
{tramitar}
</div>""", nav=_nav_html(token, "carrito"))


def pagina_pedido_confirmado(token, pedidos):
    filas = "".join(f"<li>Pedido <code>{_e(p['id_tx'])}</code> — proveedor #{_e(p['id_suministrador'])} "
                    f"({p['transicion'].get('hasta', '?')})</li>" for p in pedidos)
    return _layout("Pedido tramitado", f"""
<div class="card"><h1 class="ok">✓ Pedido(s) tramitado(s)</h1>
<p>Se ha generado un pedido por cada proveedor de tu carrito:</p>
<ul>{filas}</ul>
<p><a href="/portal/empresa/{_e(token)}/catalogo" style="color:var(--ac);font-weight:700">
Seguir comprando →</a></p>
</div>""", nav=_nav_html(token, "carrito"))


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

    @bp.get("/<token>/dashboard")
    def dashboard(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART
        return pagina_dashboard(token, ses, n_carrito=len(CART.listar(token)))

    @bp.get("/<token>/catalogo")
    def catalogo(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, sectores
        texto = request.args.get("q", "").strip()
        sector_ids = sectores.compatibles_de(ses["sector_id"])
        arts = CAT.buscar_para_empresa(sector_ids, texto=texto or None)
        mensaje = "Catálogo actualizado." if request.args.get("actualizar") else None
        return pagina_catalogo(token, arts, texto=texto, mensaje=mensaje)

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
            return pagina_catalogo(token, arts, mensaje=None), 400
        CART.anadir(token, id_suministrador=art["id_suministrador"], codigo=art["codigo"],
                   nombre=art["nombre"], unidad_medida=art["unidad_medida"], cantidad=cantidad,
                   precio_unitario=float(art["precio_unitario"]), origen="catalogo")
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
        return pagina_reposicion(token, props)

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
            return pagina_reposicion(token, props), 400
        mejor = min(candidatos, key=lambda a: float(a["precio_unitario"]))
        CART.anadir(token, id_suministrador=mejor["id_suministrador"], codigo=prop["codigo"],
                   nombre=prop["nombre"], unidad_medida=mejor["unidad_medida"],
                   cantidad=max(prop["cantidad"], mejor["moq"]),
                   precio_unitario=float(mejor["precio_unitario"]), origen="reposicion",
                   id_reab_propuesta=id_propuesta)
        return redirect(f"/portal/empresa/{token}/reposicion")

    @bp.get("/<token>/carrito")
    def carrito(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART
        return pagina_carrito(token, CART.listar(token), CART.total(token))

    @bp.post("/<token>/carrito/quitar/<int:id_linea>")
    def carrito_quitar(token, id_linea):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART
        CART.quitar_linea(token, id_linea)
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.post("/<token>/carrito/tramitar")
    def carrito_tramitar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_pedidos as PED
        r = PED.tramitar(token)
        if not r.get("ok"):
            return pagina_carrito(token, CART.listar(token), CART.total(token), error=r.get("error")), 400
        return pagina_pedido_confirmado(token, r["pedidos"])

    return bp
