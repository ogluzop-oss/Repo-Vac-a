"""
Editor visual del storefront (Fase 4 e-commerce, Catálogo Web / Canal Web) — secciones/bloques
reordenables que componen la página de inicio de la tienda propia.

Sigue el patrón Strangler de CLAUDE.md (prohibido reescribir `storefront.py` completo):
`pagina_home` (en `storefront.py`) sigue generando el layout fijo de SIEMPRE si la tienda no tiene
`tema_json` guardado (comportamiento idéntico, cero regresión — ninguna tienda existente cambia);
cuando SÍ hay un tema guardado, delega en `renderizar_home_con_tema` de este módulo. Los bloques
reutilizan `_nav`/`_card`/_grid`/`_e` de `storefront.py` tal cual (mismo HTML/CSS, cero motor de
render paralelo) — este fichero solo añade la composición por secciones ENCIMA de esas funciones.

Cada bloque es `{"id": str, "tipo": str, "config": dict}`; `config` solo admite texto plano
(nunca HTML sin escapar: los bloques los edita el dueño de la tienda pero el HTML resultante lo ve
cualquier visitante público, así que todo texto pasa por `_e()` igual que el resto del storefront).
"""

from __future__ import annotations

# Registro de tipos de bloque disponibles — única fuente que consume tanto el render (este fichero)
# como el editor visual (`gui/tema_editor_dialog.py`, selector "Añadir sección"), para que ambos
# lados queden siempre sincronizados sin mantener la lista dos veces.
BLOQUES_DISPONIBLES = {
    "hero": {
        "etiqueta": "Hero / Portada",
        "campos": [("titulo", "Título", True), ("subtitulo", "Subtítulo", True),
                  ("texto_boton", "Texto del botón (opcional)", False),
                  ("enlace_boton", "Enlace del botón (opcional, ruta relativa)", False)],
    },
    "texto": {
        "etiqueta": "Bloque de texto",
        "campos": [("titulo", "Título (opcional)", False), ("texto", "Texto", True)],
    },
    "banner": {
        "etiqueta": "Banner con imagen",
        "campos": [("imagen_url", "URL de la imagen", True), ("texto", "Texto (opcional)", False),
                  ("enlace", "Enlace (opcional, ruta relativa)", False)],
    },
    "grid_destacados": {"etiqueta": "Productos destacados", "campos": []},
    "grid_recomendados": {"etiqueta": "Productos recomendados", "campos": []},
    "grid_catalogo": {"etiqueta": "Catálogo completo", "campos": []},
    "separador": {"etiqueta": "Separador", "campos": []},
}


def bloque_por_defecto(tipo: str) -> dict:
    meta = BLOQUES_DISPONIBLES.get(tipo)
    if meta is None:
        raise ValueError(f"Tipo de bloque desconocido: {tipo!r}")
    import uuid
    return {"id": uuid.uuid4().hex[:10], "tipo": tipo,
            "config": {campo: "" for campo, _etq, _req in meta["campos"]}}


def _render_hero(cfg_bloque, ctx):
    from src.backend.storefront import _e
    titulo = _e(cfg_bloque.get("titulo") or "")
    subtitulo = _e(cfg_bloque.get("subtitulo") or "")
    boton = ""
    if cfg_bloque.get("texto_boton"):
        href = _e(cfg_bloque.get("enlace_boton") or f"/tienda/{_e(ctx['eid'])}")
        boton = (f'<p><a href="{href}" style="display:inline-block;margin-top:10px;'
                f'background:var(--ac);color:#0E1117;font-weight:900;padding:10px 20px;'
                f'border-radius:8px;text-decoration:none">{_e(cfg_bloque["texto_boton"])}</a></p>')
    return f'<section style="padding:20px 0"><h1>{titulo}</h1><p>{subtitulo}</p>{boton}</section>'


def _render_texto(cfg_bloque, ctx):
    from src.backend.storefront import _e
    titulo = f"<h2>{_e(cfg_bloque['titulo'])}</h2>" if cfg_bloque.get("titulo") else ""
    texto = _e(cfg_bloque.get("texto") or "")
    return f'<section>{titulo}<p>{texto}</p></section>'


def _render_banner(cfg_bloque, ctx):
    from src.backend.storefront import _e
    img = _e(cfg_bloque.get("imagen_url") or "")
    texto = f'<p>{_e(cfg_bloque["texto"])}</p>' if cfg_bloque.get("texto") else ""
    contenido = (f'<div style="background:#161B22 url(\'{img}\') center/cover no-repeat;'
                f'border:1px solid #30363D;border-radius:12px;min-height:160px;'
                f'display:flex;align-items:flex-end;padding:16px">{texto}</div>')
    if cfg_bloque.get("enlace"):
        contenido = f'<a href="{_e(cfg_bloque["enlace"])}" style="text-decoration:none;color:inherit">{contenido}</a>'
    return f"<section>{contenido}</section>"


def _render_grid_destacados(cfg_bloque, ctx):
    from src.backend.storefront import _grid
    if not ctx["dest"]:
        return ""
    return "<section><h2>Destacados</h2>" + _grid(ctx["dest"], ctx["eid"], ctx["moneda"]) + "</section>"


def _render_grid_recomendados(cfg_bloque, ctx):
    from src.backend.storefront import _grid
    if not ctx["reco"]:
        return ""
    return "<section><h2>Recomendados</h2>" + _grid(ctx["reco"], ctx["eid"], ctx["moneda"]) + "</section>"


def _render_grid_catalogo(cfg_bloque, ctx):
    from src.backend.storefront import _grid
    return "<section><h2>Catálogo</h2>" + _grid(ctx["todos"], ctx["eid"], ctx["moneda"]) + "</section>"


def _render_separador(cfg_bloque, ctx):
    return '<hr style="border:none;border-top:1px solid #21262D;margin:24px 0">'


_RENDERERS = {
    "hero": _render_hero, "texto": _render_texto, "banner": _render_banner,
    "grid_destacados": _render_grid_destacados, "grid_recomendados": _render_grid_recomendados,
    "grid_catalogo": _render_grid_catalogo, "separador": _render_separador,
}


def renderizar_bloque(bloque: dict, ctx: dict) -> str:
    """Nunca lanza por un bloque mal formado (p. ej. un tipo retirado en una versión futura) —
    se omite honestamente en vez de romper la página entera de la tienda."""
    fn = _RENDERERS.get(bloque.get("tipo"))
    if fn is None:
        return ""
    try:
        return fn(bloque.get("config") or {}, ctx)
    except Exception:
        return ""


def renderizar_home_con_tema(eid, cfg, tema: dict) -> str:
    """Compone el `<main>` de la home a partir de `tema["secciones"]` (lista ordenada de bloques).
    Reutiliza exactamente los mismos datos que la home por defecto (destacados/recomendados/
    catálogo/categorías) — mismo origen de datos, solo cambia cómo se ordenan/presentan."""
    from src.backend.storefront import _e, _layout, _nav
    from src.services import catalogo as cat_svc

    moneda = cfg.get("moneda")
    cats = cat_svc.listar_categorias(arbol=False, solo_visibles=True, id_empresa=eid)
    ctx = {
        "eid": eid, "cfg": cfg, "moneda": moneda,
        "dest": cat_svc.destacados(interno=False, id_empresa=eid),
        "reco": cat_svc.recomendados(interno=False, id_empresa=eid),
        "todos": cat_svc.listar_productos(interno=False, id_empresa=eid),
    }
    secciones = tema.get("secciones") or []
    cuerpo = "".join(renderizar_bloque(b, ctx) for b in secciones)
    c = _nav(cfg, eid, cats) + "<main>" + cuerpo + "</main>"
    return _layout(cfg, eid, cfg.get("nombre") or "Tienda", c)
