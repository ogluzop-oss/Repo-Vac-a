"""
Tienda online propia (Escenario B) — storefront dinámico servido por el backend.

Consume el catálogo EN VIVO (`src.services.catalogo`, vista pública) por lo que
SIEMPRE está sincronizada con Smart Manager AI: no hay export que regenerar. Es
multi-tenant (la empresa va en la URL) y se personaliza con `web_config`
(nombre/color/logo/moneda).

El HTML se genera con funciones puras (sin Flask) → testeables sin servidor. Flask
solo se usa para enrutar (import perezoso en `crear_blueprint`).
"""

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


def _layout(cfg, eid, titulo, contenido):
    color = cfg.get("color") or "#00FFC6"
    nombre = _e(cfg.get("nombre") or "Tienda")
    base = f"/tienda/{_e(eid)}"
    logo = (f'<img src="{_e(cfg["logo_url"])}" alt="{nombre}" style="height:40px">'
            if cfg.get("logo_url") else f'<span class="logo">{nombre}</span>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · {nombre}</title><style>
:root{{--ac:{color};}}
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


# ── Páginas (funciones puras, testeables sin Flask) ──────────────────────────
def pagina_home(eid, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
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
    info += "</div>"
    c = (_nav(cfg, eid, cats) + '<main><div class="detalle">'
         f'<div class="img" {img}></div>{info}</div>' + (galeria and f"<div>{galeria}</div>") + "</main>")
    return _layout(cfg, eid, p.get("nombre") or "Producto", c), 200


def pagina_buscar(eid, q, cfg=None):
    cfg = cfg or web_tienda.obtener_config(eid)
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    prods = cat_svc.buscar(q, interno=False, id_empresa=eid) if q else []
    c = (_nav(cfg, eid, cats) + f"<main><h1>Resultados: {_e(q)}</h1>"
         + _grid(prods, eid, cfg.get("moneda")) + "</main>")
    return _layout(cfg, eid, f"Buscar {q}", c)


def _no_disponible(cfg, eid):
    return _layout(cfg, eid, "Tienda no disponible",
                   "<main><h1>Tienda no disponible</h1>"
                   "<p>Esta tienda online no está activa.</p></main>")


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, abort, request

    bp = Blueprint("storefront", __name__)

    def _cfg_o_404(eid):
        cfg = web_tienda.obtener_config(eid)
        if not cfg.get("activa"):
            abort(404)
        return cfg

    @bp.get("/tienda/<id_empresa>")
    def home(id_empresa):
        cfg = web_tienda.obtener_config(id_empresa)
        if not cfg.get("activa"):
            return _no_disponible(cfg, id_empresa), 404
        return pagina_home(id_empresa, cfg)

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

    return bp
