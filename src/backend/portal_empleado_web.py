"""
Portal Web para Empleados (extranet) — gestión de pedidos online. Sustituye a
`gui/portal_web_home.PortalWebHome` (diálogo Qt nativo, retirado tras esta migración): mismo diseño
visual (fondo oscuro #0E1117, acento cian #00FFC6) que ya tenía la ventana de escritorio, pero servido
como página web real en vez de una ventana nativa — se abre desde el botón "Venta almacén" del TPV.
Mismo patrón que los demás portales de la extranet (`portal_empresa_b2b.py`, `portal_proveedor.py`):
HTML por funciones puras + Flask fino, sesión SIN cookies (token en la URL, revalidado cada petición).

A diferencia de los portales para terceros EXTERNOS (empresa/proveedor, con su propio mecanismo de
sesión `*_sesion_empresa`), este portal es para un EMPLEADO interno: reutiliza directamente el JWT de
acceso ya emitido por el login de escritorio (`src.seguridad.tokens`), sin inventar un segundo sistema
de sesión — el TPV emite el token al pulsar "Venta almacén" y lo pasa en la URL (mismo patrón que
`gui/components/remote_scan.py::_token_desktop`).

Lógica de negocio: delega en `services.tpv.online_orders_service` tal cual (mismo motor que ya
consumía `PortalWebHome` y que ahora también consume el móvil, Fase G del rediseño) — sin duplicar
reglas. El ciclo de estados se simplificó a Preparar→Enviar→Entregar (igual que el móvil), en vez del
selector libre de estados que tenía el diálogo Qt.
"""

import logging
import os

from markupsafe import escape

from src.backend.portal_empresa_b2b import _CSEL_CSS, _CSEL_JS
from src.backend.portal_i18n import idioma_actual, registrar_selector_idioma, selector_idioma_html, t as _t

logger = logging.getLogger("backend.portal_empleado_web")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"

# Flecha del `<select>` nativo, recoloreada a mano en cian — idéntico patrón que ya usan
# `portal_empresa_b2b.py`/`portal_proveedor.py` para que los 3 portales compartan el mismo
# desplegable con borde/flecha propios en vez del `<select>` sin estilo del navegador.
_FLECHA_SVG = ("data:image/svg+xml;utf8,"
              "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E"
              "%3Cpath d='M1 1l5 5 5-5' stroke='%2300FFC6' stroke-width='2' fill='none' "
              "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")

# estado de pedidos_online mostrado en cada pestaña -> (acción del formulario, etiqueta del botón)
# "PENDIENTE" (sin acción, solo lectura) es el pedido/encargo recién creado pero AÚN SIN COBRAR —
# antes no tenía ninguna pestaña, así que un encargo entre tiendas/almacenes (o un pedido web
# esperando confirmación de pago) era invisible para el centro que debe suministrarlo hasta que
# alguien lo cobraba; ahora se ve desde el primer momento (sin botón de acción: no hay nada que
# hacer todavía, solo informar de que viene en camino).
_ESTADO_A_ACCION = {
    "PENDIENTE": (None, None),
    "PAGADO": ("prepare", "Marcar preparado"),
    "PREPARANDO": ("ship", "Marcar enviado"),
    "ENVIADO": ("deliver", "Marcar entregado"),
}
_ESTADO_A_PESTANA = {"PENDIENTE": "Pendientes", "PAGADO": "Preparar", "PREPARANDO": "Enviar",
                    "ENVIADO": "Entregar"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _layout(titulo, contenido, *, token=None, activo=None, id_empresa=None):
    from src.backend import portal_theming as _tema
    if id_empresa is None:
        try:
            from flask import g
            id_empresa = getattr(g, "id_empresa", None)
        except Exception:
            pass
    idioma = idioma_actual()
    nav = ""
    if token:
        base = f"/portal/empleado/{token}"
        # "Nuevo encargo" (construcción, F2) primero — es la acción PRIMARIA que trae aquí al
        # cajero desde el botón "Venta almacén" del TPV; Pendientes/Preparar/Enviar/Entregar es el
        # tablero de seguimiento de almacén, secundario. "Recogidas" (Click&Collect) es un motor
        # de datos DISTINTO (`comercio_digital.transacciones`, no `pedidos_online`) que antes no
        # tenía ninguna pantalla en este portal — solo se veía como un número en el badge del TPV.
        enlaces = (("encargo", f"{base}/encargo", _t("portal_emp.nav_encargo", "Nuevo pedido")),
                  ("PENDIENTE", f"{base}/pedidos?estado=PENDIENTE", _t("portal_emp.nav_pendientes", "Pendientes")),
                  ("PAGADO", f"{base}/pedidos?estado=PAGADO", _t("portal_emp.nav_preparar", "Preparar")),
                  ("PREPARANDO", f"{base}/pedidos?estado=PREPARANDO", _t("portal_emp.nav_enviar", "Enviar")),
                  ("ENVIADO", f"{base}/pedidos?estado=ENVIADO", _t("portal_emp.nav_entregar", "Entregar")),
                  ("recogidas", f"{base}/recogidas", _t("portal_emp.nav_recogidas", "Recogidas")),
                  ("colores", f"{base}/colores", _t("portal_emp.nav_personalizacion", "Personalización")))
        nav = "<nav>" + "".join(
            f'<a href="{href}"{" class=\"on\"" if activo == e else ""}>{l}</a>'
            for e, href, l in enlaces) + selector_idioma_html(
                accion="/portal/empleado/idioma") + "</nav>"
    _tv = _tema.obtener_tema(id_empresa)
    return f"""<!doctype html><html lang="{_e(idioma)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · {_t("portal_emp.titulo_marca", "Portal del Empleado")}</title><style>
:root{_tema.bloque_css_variables(id_empresa)}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:var(--bg);color:var(--text)}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 24px;background:var(--bg);border-bottom:1px solid #21262D}}
nav a{{color:var(--text2);text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;border-radius:8px}}
nav a.on,nav a:hover{{color:var(--bg);background:var(--ac)}}
main{{max-width:900px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:var(--bg2);border:1px solid var(--borde);border-radius:12px;padding:18px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px;vertical-align:middle}}
th{{color:var(--text2)}}
.sub{{color:var(--text2);margin-top:2px;font-size:14px}}
form.inline{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
button,.btn{{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;text-decoration:none;display:inline-block;font-size:13px;
font-family:'Segoe UI',system-ui,sans-serif}}
button:hover,.btn:hover{{background:var(--ac);color:var(--bg)}}
.btn-ghost{{background:transparent;color:var(--text2);border:2px solid var(--borde)}}
.btn-ghost:hover{{background:var(--text2);color:var(--bg);border-color:var(--text2)}}
.btn-danger{{background:transparent;color:var(--err);border:2px solid var(--err)}}
.btn-danger:hover{{background:var(--err);color:var(--bg)}}
.total{{font-size:20px;font-weight:900;color:var(--ac)}}
input,select{{padding:9px 10px;border-radius:8px;border:1px solid var(--borde);background:var(--bg);color:var(--text);
font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;margin:0 10px 10px 0}}
input[type=color]{{height:42px;padding:4px;cursor:pointer}}
select{{appearance:none;-webkit-appearance:none;border:2px solid var(--ac);border-radius:10px;
background-color:var(--bg);background-image:url("{_FLECHA_SVG}");background-repeat:no-repeat;
background-position:right 12px center;background-size:12px 8px;padding-right:32px;cursor:pointer}}
select:focus{{outline:none;border-color:var(--ac)}}
.error{{color:var(--err);font-weight:700}}.ok{{color:var(--ok);font-weight:700}}
.sel-idioma{{margin-left:auto}}.sel-idioma select{{padding:5px 24px 5px 8px;font-size:12px;margin:0}}
{_CSEL_CSS}
{_tema.CSS_POLISH}
</style></head><body>
<header><span class="logo">{_t("portal_emp.titulo_marca", "Portal del Empleado").upper()}</span></header>
{nav}
<main>{contenido}</main>
<script>{_CSEL_JS}</script>
</body></html>"""


def _pagina_error(titulo, mensaje):
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p></div>")


def pagina_pedidos(token, estado, pedidos, *, mensaje=None, id_tienda_empleado=None, id_empresa=None):
    """``id_tienda_empleado`` (opcional): tienda INT del empleado en sesión (resuelta de su
    `centro_codigo`). Si un pedido de la lista tiene una tienda de DESTINO distinta (es decir,
    lo está viendo porque su ALMACÉN es el origen del encargo, no porque sea su tienda), se
    etiqueta con una nota "Encargo solicitado por: <tienda>" para que el personal de almacén
    entienda que ese pedido sale hacia otra tienda, no es un cliente local."""
    base = f"/portal/empleado/{token}"
    accion, etiqueta = _ESTADO_A_ACCION.get(estado, (None, None))
    if etiqueta:
        etiqueta = _t(f"portal_emp.accion_{accion}", etiqueta)
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    if estado == "PENDIENTE":
        aviso += f'<p class="sub">{_t("portal_emp.aviso_pendiente", "Pedidos ya registrados pero TODAVÍA SIN COBRAR — un pedido web/marketplace a la espera de confirmación de pago, o un encargo entre tiendas/almacenes que el cliente aún no ha pagado en caja. Nada que hacer todavía: pasan a Preparar en cuanto se confirme el cobro.")}</p>'
    if not pedidos:
        cuerpo = f'<p>{_t("portal_emp.sin_pedidos", "No hay pedidos en este estado.")}</p>'
    else:
        cache_tiendas = {}

        def _nombre_tienda(id_tienda):
            if id_tienda not in cache_tiendas:
                try:
                    from src.db.tiendas import obtener_tienda
                    t = obtener_tienda(id_tienda) or {}
                    cache_tiendas[id_tienda] = (
                        t.get("nombre") or t.get("codigo_tienda")
                        or _t("portal_emp.tienda_generica", "tienda #{id}", id=id_tienda))
                except Exception:
                    cache_tiendas[id_tienda] = _t("portal_emp.tienda_generica", "tienda #{id}",
                                                  id=id_tienda)
            return cache_tiendas[id_tienda]

        filas = []
        for p in pedidos:
            accion_html = ""
            if accion == "prepare":
                # Confirmación MANUAL y OBLIGATORIA de cuánto puede suministrar REALMENTE esta
                # tienda de cada artículo (nunca se asume automáticamente a partir del stock
                # teórico) — si queda por debajo de lo pedido, el sistema crea solo un pedido de
                # continuación hacia la siguiente tienda más cercana con stock.
                from src.services.tpv import online_orders_service as _OS_items
                ped_completo = _OS_items.obtener_pedido(p["id_pedido"]) or {}
                items_html = "".join(
                    f'<div style="margin:4px 0">{_e(it.get("nombre") or it.get("codigo_articulo"))} '
                    f'({_t("portal_emp.pedido_cantidad", "pedido: {c}", c=it.get("cantidad"))}) '
                    f'<input type="number" name="cant_{_e(it.get("codigo_articulo"))}" '
                    f'value="{_e(it.get("cantidad"))}" min="0" max="{_e(it.get("cantidad"))}" '
                    f'required style="width:70px"></div>'
                    for it in (ped_completo.get("items") or []))
                accion_html = (
                    f'<form class="inline" method="post" '
                    f'action="{base}/pedidos/{_e(p["id_pedido"])}/prepare" '
                    f'style="flex-direction:column;align-items:flex-start">{items_html}'
                    f'<button type="submit" style="margin-top:6px">{_e(etiqueta)}</button></form>')
            elif accion == "ship":
                confirmar_envio = _t("portal_emp.confirmar_envio",
                                    "¿Confirmar el envío de este pedido? El stock se descontará "
                                    "de esta tienda/almacén.")
                accion_html = (
                    f'<form class="inline" method="post" action="{base}/pedidos/{_e(p["id_pedido"])}/ship" '
                    f'onsubmit="return confirm(\'{confirmar_envio}\');">'
                    f'<input type="text" name="transportista" '
                    f'placeholder="{_t("portal_emp.transportista_ph", "Transportista")}" required>'
                    f'<input type="text" name="seguimiento" '
                    f'placeholder="{_t("portal_emp.seguimiento_ph", "Nº seguimiento")}">'
                    f'<button type="submit">{_e(etiqueta)}</button></form>')
            elif accion:
                accion_html = (
                    f'<form method="post" action="{base}/pedidos/{_e(p["id_pedido"])}/{accion}">'
                    f'<button type="submit">{_e(etiqueta)}</button></form>')
            destino_tid = p.get("id_tienda")
            nota_encargo = ""
            if (id_tienda_empleado is not None and destino_tid is not None
                    and destino_tid != id_tienda_empleado):
                nota_encargo = (f'<div class="sub" style="color:{_CIAN}">'
                                f'{_t("portal_emp.pedido_solicitado_por", "Pedido solicitado por: {t}", t=_e(_nombre_tienda(destino_tid)))}</div>')
            filas.append(f"""<tr>
<td>{_e(p.get("cliente_nombre") or _t("portal_emp.cliente_generico", "Cliente"))}<div class="sub">{_e(str(p["id_pedido"])[:8])}</div>{nota_encargo}</td>
<td>{_e(p.get("cliente_telefono") or "—")}</td>
<td>{_e(p.get("total"))} €</td>
<td>{accion_html}</td></tr>""")
        cuerpo = (f'<table><tr><th>{_t("portal_emp.col_cliente", "Cliente")}</th>'
                 f'<th>{_t("portal_emp.col_telefono", "Teléfono")}</th>'
                 f'<th>{_t("portal_emp.col_total", "Total")}</th><th></th></tr>'
                 f"{''.join(filas)}</table>")
    titulo = _t(f"portal_emp.pestana_{estado}", _ESTADO_A_PESTANA.get(estado, "Pedidos"))
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1>{aviso}{cuerpo}</div>",
                   token=token, activo=estado, id_empresa=id_empresa)


# Click & Collect: pestaña del motor PAGADA→PREPARANDO→(recogida) — DISTINTO de `pedidos_online`
# (ver `services.comercio_digital.pickup`/`transacciones`), antes sin ninguna pantalla en este
# portal (solo se contaba, sin detalle, en el badge rojo del TPV).
_RECOGIDA_A_ACCION = {"PAGADA": ("preparar", "Marcar preparado"),
                      "PREPARANDO": ("entregar", "Marcar recogido")}
_RECOGIDA_A_PESTANA = {"PAGADA": "Recogidas — por preparar", "PREPARANDO": "Recogidas — listas"}


def pagina_recogidas(token, estado, recogidas, *, mensaje=None, id_empresa=None):
    """Recogidas en tienda (Click&Collect) PAGADA (por preparar) o PREPARANDO (ya lista, a la
    espera de que el cliente pase a recogerla) — siempre de la tienda del empleado: un
    almacén puro nunca gestiona recogidas (el punto de recogida es SIEMPRE una tienda, nunca un
    almacén — `comercio_digital.pickup.reservar` exige `id_tienda`, nunca un `id_almacen`)."""
    base = f"/portal/empleado/{token}/recogidas"
    accion, etiqueta = _RECOGIDA_A_ACCION.get(estado, (None, None))
    if etiqueta:
        etiqueta = _t(f"portal_emp.recogida_accion_{accion}", etiqueta)
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    if not recogidas:
        cuerpo = f'<p>{_t("portal_emp.sin_recogidas", "No hay recogidas en este estado.")}</p>'
    else:
        filas = []
        for tx in recogidas:
            accion_html = ""
            if accion:
                accion_html = (
                    f'<form method="post" action="{base}/{_e(tx["id_tx"])}/{accion}">'
                    f'<button type="submit">{_e(etiqueta)}</button></form>')
            filas.append(f"""<tr>
<td>{_e(tx.get("cliente_nombre") or _t("portal_emp.cliente_generico", "Cliente"))}<div class="sub">{_e(str(tx["id_tx"])[:8])}</div></td>
<td>{_e(tx.get("cliente_telefono") or "—")}</td>
<td>{_e(tx.get("total"))} €</td>
<td>{accion_html}</td></tr>""")
        cuerpo = (f'<table><tr><th>{_t("portal_emp.col_cliente", "Cliente")}</th>'
                 f'<th>{_t("portal_emp.col_telefono", "Teléfono")}</th>'
                 f'<th>{_t("portal_emp.col_total", "Total")}</th><th></th></tr>'
                 f"{''.join(filas)}</table>")
    nav_estados = (f'<p class="sub">'
                  f'<a class="btn" href="{base}?estado=PAGADA">{_t("portal_emp.recogida_por_preparar", "Por preparar")}</a>&nbsp;'
                  f'<a class="btn" href="{base}?estado=PREPARANDO">{_t("portal_emp.recogida_listas", "Listas para recoger")}</a>'
                  f'</p>')
    titulo = _t(f"portal_emp.recogida_pestana_{estado}", _RECOGIDA_A_PESTANA.get(estado, "Recogidas"))
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1>{nav_estados}{aviso}{cuerpo}</div>",
                   token=token, activo="recogidas", id_empresa=id_empresa)


def _parse_carrito(raw) -> list[dict]:
    """Deserializa el carrito del encargo en construcción desde el campo oculto `carrito`
    (JSON, reenviado en cada formulario — el portal no usa cookies, ver módulo). Saneado
    defensivo: cualquier línea sin `codigo` o con JSON corrupto se descarta en vez de romper la
    página; NUNCA levanta excepción."""
    import json
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for l in data:
        if not isinstance(l, dict) or not l.get("codigo"):
            continue
        try:
            cant = max(1, int(float(l.get("cantidad") or 1)))
        except (TypeError, ValueError):
            cant = 1
        try:
            precio = float(l.get("precio") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        id_alm = l.get("id_almacen")
        try:
            id_alm = int(id_alm) if id_alm not in (None, "") else None
        except (TypeError, ValueError):
            id_alm = None
        out.append({
            "codigo": str(l.get("codigo"))[:64],
            "nombre": str(l.get("nombre") or l.get("codigo"))[:200],
            "cantidad": cant,
            "precio": round(precio, 2),
            "subtotal": round(cant * precio, 2),
            "id_almacen": id_alm,
            "almacen": str(l.get("almacen") or "")[:120],
        })
    return out


def pagina_encargo(token, carrito, *, articulo=None, almacenes=None, error=None, mensaje=None):
    """Construcción de un ENCARGO A ALMACÉN (F2, movida del TPV aquí): buscar artículo → elegir
    almacén de origen por proximidad con stock (`buscar_almacenes_con_stock`, reutilizado sin
    cambios) → repetir para varios artículos → datos de cliente → crear
    (`crear_encargo_almacen`, nace SIEMPRE en PENDIENTE — el cobro real se completa después en el
    TPV, botón «💳 Cobrar encargo»).

    Sin cookies (mismo criterio que el resto del portal): el carrito viaja como JSON en un campo
    oculto `carrito`, reenviado por cada formulario de esta misma página — cada acción (buscar,
    añadir, quitar, confirmar) es un POST que vuelve a renderizar la página con el carrito
    actualizado, sin depender de sesión de servidor."""
    import json
    base = f"/portal/empleado/{token}/encargo"
    carrito_json = _e(json.dumps(carrito))
    aviso = (f'<p class="error">{_e(error)}</p>' if error
            else (f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""))

    busq = f"""<div class="card"><h2>{_t("portal_emp.buscar_articulo", "Buscar artículo")}</h2>{aviso}
<form class="inline" method="post" action="{base}/buscar">
<input type="hidden" name="carrito" value="{carrito_json}">
<input type="text" name="q" placeholder="{_t("portal_emp.buscar_articulo_ph", "Código o nombre del artículo")}" required>
<button type="submit">{_t("portal_emp.buscar_btn", "Buscar")}</button></form></div>"""

    resultado = ""
    if articulo:
        filas_alm = []
        for a in (almacenes or []):
            if a.get("ubicacion_desconocida"):
                dist = _t("portal_emp.ubicacion_desconocida", "ubicación desconocida")
            else:
                dist = f"{a.get('distancia_km', 0):.1f} km"
            filas_alm.append(f"""<tr>
<td>{_e(a.get('nombre'))}<div class="sub">{_e(a.get('tipo_almacen') or '')}</div></td>
<td>{_e(dist)}</td><td>{_t("portal_emp.ud_abrev", "{n} ud.", n=int(a.get('cantidad') or 0))}</td>
<td><form class="inline" method="post" action="{base}/anadir">
<input type="hidden" name="carrito" value="{carrito_json}">
<input type="hidden" name="codigo" value="{_e(articulo['codigo'])}">
<input type="hidden" name="nombre" value="{_e(articulo['nombre'])}">
<input type="hidden" name="precio" value="{_e(articulo['precio'])}">
<input type="hidden" name="id_almacen" value="{_e(a.get('id_almacen'))}">
<input type="hidden" name="almacen" value="{_e(a.get('nombre'))}">
<input type="number" name="cantidad" value="1" min="1" style="width:70px">
<button type="submit">{_t("portal_emp.anadir_btn", "Añadir")}</button></form></td></tr>""")
        tabla_alm = (f'<table><tr><th>{_t("portal_emp.col_almacen_origen", "Almacén de origen")}</th>'
                    f'<th>{_t("portal_emp.col_distancia", "Distancia")}</th>'
                    f'<th>{_t("portal_emp.col_stock", "Stock")}</th>'
                    f"<th></th></tr>{''.join(filas_alm)}</table>") if filas_alm else ""
        bajo_pedido = f"""<form class="inline" method="post" action="{base}/anadir" style="margin-top:18px">
<input type="hidden" name="carrito" value="{carrito_json}">
<input type="hidden" name="codigo" value="{_e(articulo['codigo'])}">
<input type="hidden" name="nombre" value="{_e(articulo['nombre'])}">
<input type="hidden" name="precio" value="{_e(articulo['precio'])}">
<input type="hidden" name="id_almacen" value="">
<input type="hidden" name="almacen" value="bajo pedido">
<input type="number" name="cantidad" value="1" min="1" style="width:70px">
<button type="submit">{_t("portal_emp.anadir_bajo_pedido", "Añadir bajo pedido (sin almacén de origen)")}</button></form>"""
        # Misma foto que "Información artículo" del escritorio (columna articulos.imagen), servida
        # por /imagen/<codigo> — con MISMO fallback honesto que info_articulo.py ("SIN IMAGEN") en
        # vez de un <img> roto cuando el artículo no tiene foto.
        if articulo.get("tiene_imagen"):
            foto_html = (f'<img src="/portal/empleado/{_e(token)}/imagen/{_e(articulo["codigo"])}" '
                        f'alt="{_e(articulo["nombre"])}" style="width:110px;height:110px;'
                        f'object-fit:cover;border-radius:12px;border:2px solid {_BORDE};'
                        f'float:left;margin-right:16px">')
        else:
            foto_html = (f'<div style="width:110px;height:110px;border-radius:12px;'
                        f'border:2px solid {_BORDE};background:{_BG};color:{_TEXT2};'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'font-size:11px;text-align:center;float:left;margin-right:16px">'
                        f'{_t("portal_emp.sin_imagen", "SIN IMAGEN")}</div>')
        resultado = f"""<div class="card">{foto_html}<h2>{_e(articulo['nombre'])}</h2>
<p class="sub">{_e(articulo['codigo'])} · {articulo['precio']} €</p>
<div style="clear:both">{tabla_alm or f'<p>{_t("portal_emp.sin_stock_fisico", "Sin stock físico en ningún almacén.")}</p>'}
{bajo_pedido}</div></div>"""

    total = round(sum(l["subtotal"] for l in carrito), 2)
    filas_cart = "".join(f"""<tr><td>{_e(l['nombre'])}<div class="sub">{_e(l['codigo'])}</div></td>
<td>{l['cantidad']}</td><td>{l['precio']} €</td><td>{l['subtotal']} €</td>
<td>{_e(l.get('almacen') or '—')}</td>
<td><form method="post" action="{base}/quitar/{i}">
<input type="hidden" name="carrito" value="{carrito_json}">
<button type="submit" class="btn-danger">{_t("portal_emp.quitar_btn", "Quitar")}</button></form></td></tr>"""
        for i, l in enumerate(carrito))
    tabla_cart = (f'<table><tr><th>{_t("portal_emp.col_articulo", "Artículo")}</th>'
                 f'<th>{_t("portal_emp.col_cant", "Cant.")}</th>'
                 f'<th>{_t("portal_emp.col_precio", "Precio")}</th>'
                 f'<th>{_t("portal_emp.col_subtotal", "Subtotal")}</th>'
                 f'<th>{_t("portal_emp.col_almacen", "Almacén")}</th>'
                 f"<th></th></tr>{filas_cart}</table>") if carrito else (
        f'<p>{_t("portal_emp.anade_articulos", "Añade artículos (arriba) para construir el pedido.")}</p>')
    cart_html = f"""<div class="card"><h2>{_t("portal_emp.pedido_construccion", "Pedido en construcción")}</h2>{tabla_cart}
<p class="total">{_t("portal_emp.total_lbl", "Total: {tot} €", tot=total)}</p></div>"""

    cliente_html = ""
    if carrito:
        # Modo de entrega (2 opciones): el cliente está delante del mostrador, así que "recogida
        # en esta tienda" es una opción tan válida como el envío — sin dirección ni gastos de
        # envío en ese caso. El bloque de domicilio (envío + facturación + gastos de envío) se
        # oculta/exige en el cliente con un `onchange` mínimo (nunca cookies/JS pesado, mismo
        # criterio que el resto del portal) Y se revalida en el servidor (`encargo_confirmar`) —
        # el JS solo mejora la experiencia, nunca es la única guardia.
        js_modo = (
            "var dom=document.getElementById('bloque_domicilio');"
            "dom.hidden=(this.value!=='domicilio');"
            "var reqs=dom.querySelectorAll('[data-obligatorio]');"
            "for(var i=0;i<reqs.length;i++){reqs[i].required=!dom.hidden;}"
        )
        cliente_html = f"""<div class="card"><h2>{_t("portal_emp.cliente_entrega", "Cliente y entrega")}</h2>
<form method="post" action="{base}/confirmar">
<input type="hidden" name="carrito" value="{carrito_json}">
<p><input type="text" name="cliente_nombre" placeholder="{_t("portal_emp.nombre_razon_ph", "Nombre / Razón social")}" required
style="width:100%"></p>
<p><input type="text" name="cliente_telefono" placeholder="{_t("portal_emp.telefono_ph", "Teléfono")}" style="width:100%"></p>
<p><input type="text" name="cliente_email" placeholder="{_t("portal_emp.email_ph", "Email")}" style="width:100%"></p>

<p>{_t("portal_emp.como_recibir", "¿Cómo quiere el cliente recibir el pedido?")}<br>
<select name="modo_entrega" onchange="{js_modo}" style="width:100%">
<option value="domicilio">{_t("portal_emp.envio_domicilio", "Envío a domicilio")}</option>
<option value="recogida_tienda">{_t("portal_emp.recogida_tienda", "Recogida en esta tienda")}</option>
</select></p>

<div id="bloque_domicilio">
<h3 style="margin-bottom:4px">{_t("portal_emp.direccion_envio", "Dirección de envío")}</h3>
<p><input type="text" name="envio_direccion" placeholder="{_t("portal_emp.direccion_ph", "Dirección")}" data-obligatorio required
style="width:100%"></p>
<p><input type="text" name="envio_ciudad" placeholder="{_t("portal_emp.ciudad_ph", "Ciudad")}" data-obligatorio required
style="width:48%"> <input type="text" name="envio_cp" placeholder="{_t("portal_emp.cp_ph", "Código postal")}"
data-obligatorio required style="width:48%"></p>
<p><input type="text" name="envio_pais" placeholder="{_t("portal_emp.pais_ph", "País")}" value="ES" style="width:100%"></p>

<h3 style="margin-bottom:4px">{_t("portal_emp.direccion_facturacion", "Dirección de facturación")}
<span class="sub">({_t("portal_emp.direccion_fact_opcional", "opcional — solo si es distinta de la de envío")})</span></h3>
<p><input type="text" name="fact_direccion" placeholder="{_t("portal_emp.direccion_ph", "Dirección")}" style="width:100%"></p>
<p><input type="text" name="fact_ciudad" placeholder="{_t("portal_emp.ciudad_ph", "Ciudad")}" style="width:48%">
<input type="text" name="fact_cp" placeholder="{_t("portal_emp.cp_ph", "Código postal")}" style="width:48%"></p>
<p><input type="text" name="fact_pais" placeholder="{_t("portal_emp.pais_ph", "País")}" style="width:100%"></p>

<p><label><input type="checkbox" name="cobrar_envio" value="1" checked>
{_t("portal_emp.cobrar_envio", "Cobrar los gastos de envío al cliente")}</label></p>
</div>

<button type="submit">{_t("portal_emp.crear_pedido_btn", "Crear pedido")}</button></form></div>"""

    return _layout(_t("portal_emp.nav_encargo", "Nuevo pedido"), busq + resultado + cart_html + cliente_html,
                   token=token, activo="encargo")


def pagina_encargo_creado(token, id_pedido, total):
    """Confirmación tras `crear_encargo_almacen`: referencia corta para relayar al cajero (mismo
    recorte `id_pedido[:8]` que usa `pagina_pedidos`/`listar_pedidos_online(texto=...)` — la
    búsqueda del selector «💳 Cobrar pedido» del TPV hace LIKE sobre `id_pedido`, así que este
    prefijo basta como referencia)."""
    ref = str(id_pedido)[:8]
    return _layout(_t("portal_emp.pedido_creado_titulo", "Pedido creado"), f"""
<div class="card"><h1 class="ok">✓ {_t("portal_emp.pedido_creado_h1", "Pedido #{ref} creado", ref=_e(ref))}</h1>
<p>{_t("portal_emp.pendiente_cobro", "Pendiente de cobro en caja — total {tot} €.", tot=round(float(total or 0), 2))}</p>
<p>{_t("portal_emp.indica_referencia", "Indica esta referencia al cliente: vuelve al TPV y usa el botón «💳 Cobrar pedido» para buscar {ref} y completar el cobro. El pedido NO se sirve hasta que se cobre.", ref=f"<b>{_e(ref)}</b>")}</p>
<p><a class="btn" href="/portal/empleado/{_e(token)}/encargo">{_t("portal_emp.crear_otro_pedido", "Crear otro pedido →")}</a></p>
</div>""", token=token, activo="encargo")


def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_empleado_web", __name__, url_prefix="/portal/empleado")
    registrar_selector_idioma(bp, "")

    def _sesion_o_error(token):
        try:
            from src.seguridad import tokens
            claims = tokens.verificar(token, "access")
        except Exception:
            claims = None
        if not claims or not claims.get("empresa"):
            return None, (_pagina_error(
                _t("portal_emp.sesion_no_valida_titulo", "Sesión no válida"),
                _t("portal_emp.sesion_no_valida_msg",
                   "Tu sesión ha caducado. Vuelve a entrar desde Smart Manager (botón Venta almacén).")), 401)
        # `g.id_empresa`: resuelto UNA vez por request, para que `_layout()` pueda temizar cada
        # página con el color de esta empresa sin tener que enhebrar `id_empresa` por parámetro
        # a través de cada función de página/ruta (hay más de una decena de puntos de llamada).
        try:
            from flask import g
            g.id_empresa = claims.get("empresa")
        except Exception:
            pass
        return {"id_empresa": claims.get("empresa"), "id_usuario": claims.get("sub"),
               "nombre": claims.get("nombre"), "centro_codigo": claims.get("tienda")}, None

    def _pedido_de_la_empresa(id_pedido, id_empresa):
        from src.services.tpv import online_orders_service as OS
        ped = OS.obtener_pedido(id_pedido)
        return ped if ped and ped.get("id_empresa") == id_empresa else None

    @bp.get("/<token>")
    def raiz(token):
        return redirect(f"/portal/empleado/{token}/pedidos?estado=PAGADO")

    @bp.get("/<token>/pedidos")
    def pedidos(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import stock_almacen as _SA
        from src.db import tiendas as _T
        from src.services.tpv import online_orders_service as OS
        estado = request.args.get("estado", "PAGADO")
        if estado not in _ESTADO_A_ACCION:
            estado = "PAGADO"
        # Contexto del empleado: su tienda (destino habitual) y su almacén (origen de encargos
        # que sirve, aunque el destino sea otra tienda) — ambos resueltos del mismo
        # `centro_codigo` que ya lleva el JWT (ver `tienda_de_codigo`/`almacen_de_codigo_centro`).
        id_tienda = _T.tienda_de_codigo(ses["centro_codigo"], ses["id_empresa"])
        id_almacen_origen = _SA.almacen_de_codigo_centro(ses["centro_codigo"], ses["id_empresa"])
        lista = OS.listar_pedidos_online(id_empresa=ses["id_empresa"], id_tienda=id_tienda,
                                         estado=estado, id_almacen_origen=id_almacen_origen)
        return pagina_pedidos(token, estado, lista, id_tienda_empleado=id_tienda,
                              mensaje=request.args.get("mensaje"))

    @bp.post("/<token>/pedidos/<id_pedido>/prepare")
    def pedidos_preparar(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.tpv import online_orders_service as OS
        pedido = _pedido_de_la_empresa(id_pedido, ses["id_empresa"])
        mensaje = None
        if pedido:
            cantidades = {}
            for it in pedido.get("items", []):
                codigo = it.get("codigo_articulo")
                try:
                    cantidades[codigo] = int(request.form.get(f"cant_{codigo}", it.get("cantidad", 0)))
                except (TypeError, ValueError):
                    cantidades[codigo] = int(it.get("cantidad", 0) or 0)
            res = OS.confirmar_cantidad_servida(id_pedido, cantidades, usuario=ses.get("usuario"),
                                                id_empresa=ses["id_empresa"])
            if res.get("ok"):
                OS.cambiar_estado(id_pedido, "PREPARANDO")
                if res.get("id_pedido_continuacion"):
                    ref_cont = str(res["id_pedido_continuacion"])[:8]
                    mensaje = _t("portal_emp.preparado_parcial",
                                "Preparado parcialmente. Se ha creado el pedido de continuación "
                                "#{ref} para la cantidad restante en otra tienda.", ref=ref_cont)
        url = f"/portal/empleado/{token}/pedidos?estado=PAGADO"
        if mensaje:
            from urllib.parse import quote
            url += f"&mensaje={quote(mensaje)}"
        return redirect(url)

    @bp.post("/<token>/pedidos/<id_pedido>/ship")
    def pedidos_enviar(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.tpv import online_orders_service as OS
        mensaje = None
        if _pedido_de_la_empresa(id_pedido, ses["id_empresa"]):
            if OS.cambiar_estado(id_pedido, "ENVIADO"):
                OS.registrar_envio(id_pedido, request.form.get("transportista", ""),
                                   request.form.get("seguimiento", ""))
                # El descuento físico del stock ocurre AQUÍ (ver `registrar_envio` →
                # `_descontar_stock_pedido`) — hasta este clic el stock solo estaba reservado.
                mensaje = _t("portal_emp.pedido_enviado_msg",
                            "Pedido enviado. El stock ya ha sido descontado de esta tienda/almacén.")
        url = f"/portal/empleado/{token}/pedidos?estado=PREPARANDO"
        if mensaje:
            from urllib.parse import quote
            url += f"&mensaje={quote(mensaje)}"
        return redirect(url)

    @bp.post("/<token>/pedidos/<id_pedido>/deliver")
    def pedidos_entregar(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.tpv import online_orders_service as OS
        if _pedido_de_la_empresa(id_pedido, ses["id_empresa"]):
            OS.cambiar_estado(id_pedido, "ENTREGADO")
        return redirect(f"/portal/empleado/{token}/pedidos?estado=ENVIADO")

    # ── Recogidas (Click&Collect) — motor DISTINTO (`comercio_digital.transacciones`/`pickup`,
    # ver docstring de `pagina_recogidas`), antes sin pantalla propia en este portal ──────────
    def _recogidas_de_la_tienda(id_tienda, id_empresa, estado):
        """Transacciones PICKUP_STORE de esta tienda en `estado` — mismo filtrado por
        `metadata.cumplimiento` que ya usaba `contar_pedidos_pendientes_tienda` para el badge del
        TPV (ver `online_orders_service.py`), ahora también con detalle aquí."""
        import json
        from src.services.comercio_digital import pickup as _PK
        from src.services.comercio_digital import transacciones as _TX
        if id_tienda is None:
            return []
        out = []
        for tx in _TX.listar(id_empresa=id_empresa, id_tienda=id_tienda, estado=estado, limite=500):
            meta = tx.get("metadata")
            try:
                meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
            except Exception:
                meta = {}
            if meta.get("cumplimiento") == _PK.CUMPLIMIENTO:
                out.append(tx)
        return out

    @bp.get("/<token>/recogidas")
    def recogidas(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import tiendas as _T
        estado = request.args.get("estado", "PAGADA")
        if estado not in _RECOGIDA_A_ACCION:
            estado = "PAGADA"
        id_tienda = _T.tienda_de_codigo(ses["centro_codigo"], ses["id_empresa"])
        lista = _recogidas_de_la_tienda(id_tienda, ses["id_empresa"], estado)
        return pagina_recogidas(token, estado, lista, mensaje=request.args.get("mensaje"),
                                id_empresa=ses["id_empresa"])

    @bp.post("/<token>/recogidas/<id_tx>/preparar")
    def recogida_preparar(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import pickup as _PK
        _PK.preparar(id_tx, id_empresa=ses["id_empresa"], actor=ses.get("nombre"))
        return redirect(f"/portal/empleado/{token}/recogidas?estado=PAGADA")

    @bp.post("/<token>/recogidas/<id_tx>/entregar")
    def recogida_entregar(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import pickup as _PK
        _PK.recoger(id_tx, id_empresa=ses["id_empresa"], actor=ses.get("nombre"))
        return redirect(f"/portal/empleado/{token}/recogidas?estado=PREPARANDO")

    # ── Foto del artículo (búsqueda del encargo): MISMA fuente que "Información artículo" del
    # escritorio (info_articulo.py) — columna articulos.imagen, ruta absoluta bajo
    # documentos/imagenes_articulos/. Ninguna copia/segundo almacén: se sirve el fichero real vía
    # send_file, detrás de la MISMA revalidación de sesión (token en la URL) que el resto del
    # portal — nunca una ruta anónima. 404 (sin cuerpo) si no hay foto o el fichero no existe.
    @bp.get("/<token>/imagen/<codigo>")
    def imagen_articulo(token, codigo):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from flask import abort, send_file
        from src.db import articulos as _ART
        try:
            ruta = _ART.obtener_imagen(codigo, id_empresa=ses["id_empresa"])
        except Exception:
            ruta = None
        if not ruta or not os.path.exists(ruta):
            abort(404)
        return send_file(ruta)

    # ── Construcción de un ENCARGO A ALMACÉN (F2, movida aquí desde el TPV) ──────────────────
    @bp.get("/<token>/encargo")
    def encargo(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        return pagina_encargo(token, [])

    @bp.post("/<token>/encargo/buscar")
    def encargo_buscar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import articulos as _ART
        from src.db import tiendas as _T
        from src.services.tpv.online_orders_service import buscar_almacenes_con_stock
        carrito = _parse_carrito(request.form.get("carrito"))
        termino = (request.form.get("q") or "").strip()
        if not termino:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.indica_codigo_nombre",
                                          "Indica un código o nombre de artículo."))
        uno = _ART.buscar_uno(termino, ses["id_empresa"])
        if not uno:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.articulo_no_encontrado",
                                          "No se encontró el artículo «{q}».", q=termino))
        codigo, nombre, precio = uno
        # Foto (mismo origen que info_articulo.py: columna articulos.imagen = ruta absoluta en
        # documentos/imagenes_articulos/). No todo artículo tiene foto — se marca aquí para que la
        # plantilla decida <img> vs. placeholder "SIN IMAGEN", sin exponer nunca un <img> roto.
        try:
            ruta_img = _ART.obtener_imagen(codigo, id_empresa=ses["id_empresa"])
        except Exception:
            ruta_img = None
        tiene_imagen = bool(ruta_img and os.path.exists(ruta_img))
        articulo = {"codigo": codigo, "nombre": nombre, "precio": float(precio or 0),
                   "tiene_imagen": tiene_imagen}
        id_tienda = _T.tienda_de_codigo(ses["centro_codigo"], ses["id_empresa"])
        try:
            almacenes = buscar_almacenes_con_stock(codigo, id_tienda, id_empresa=ses["id_empresa"])
        except Exception as e:
            logger.warning("encargo_buscar: buscar_almacenes_con_stock(%s): %s", codigo, e)
            almacenes = []
        return pagina_encargo(token, carrito, articulo=articulo, almacenes=almacenes)

    @bp.post("/<token>/encargo/anadir")
    def encargo_anadir(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        carrito = _parse_carrito(request.form.get("carrito"))
        codigo = (request.form.get("codigo") or "").strip()
        if not codigo:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.selecciona_articulo_antes",
                                          "Selecciona un artículo antes de añadir."))
        try:
            cantidad = max(1, int(float(request.form.get("cantidad") or 1)))
        except (TypeError, ValueError):
            cantidad = 1
        try:
            precio = float(request.form.get("precio") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        id_alm_raw = (request.form.get("id_almacen") or "").strip()
        id_almacen = int(id_alm_raw) if id_alm_raw.isdigit() else None
        nombre = request.form.get("nombre") or codigo
        carrito.append({
            "codigo": codigo, "nombre": nombre, "cantidad": cantidad, "precio": round(precio, 2),
            "subtotal": round(cantidad * precio, 2), "id_almacen": id_almacen,
            "almacen": request.form.get("almacen") or "",
        })
        return pagina_encargo(token, carrito,
                              mensaje=_t("portal_emp.anadido_al_encargo", "«{n}» añadido al encargo.",
                                        n=nombre))

    @bp.post("/<token>/encargo/quitar/<int:idx>")
    def encargo_quitar(token, idx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        carrito = _parse_carrito(request.form.get("carrito"))
        if 0 <= idx < len(carrito):
            carrito.pop(idx)
        return pagina_encargo(token, carrito)

    @bp.post("/<token>/encargo/confirmar")
    def encargo_confirmar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import tiendas as _T
        from src.services.tpv import online_orders_service as OS
        carrito = _parse_carrito(request.form.get("carrito"))
        if not carrito:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.anade_al_menos_un_articulo",
                                          "Añade al menos un artículo.")), 400
        nombre_cli = (request.form.get("cliente_nombre") or "").strip()
        if not nombre_cli:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.indica_nombre_cliente",
                                          "Indica el nombre del cliente.")), 400
        cliente = {"nombre": nombre_cli,
                  "telefono": (request.form.get("cliente_telefono") or "").strip(),
                  "email": (request.form.get("cliente_email") or "").strip()}

        # Modo de entrega (2 opciones): revalidado en el SERVIDOR (el `required` del formulario es
        # solo ayuda al cajero, nunca la única guardia — un cliente sin JS, o manipulado, podría
        # saltárselo). "recogida_tienda" no necesita ni dirección ni gastos de envío.
        modo_entrega = (request.form.get("modo_entrega") or "domicilio").strip()
        if modo_entrega not in ("domicilio", "recogida_tienda"):
            modo_entrega = "domicilio"
        direccion_envio = ""
        direccion_facturacion = ""
        lineas = [{"codigo": l["codigo"], "nombre": l["nombre"], "cantidad": l["cantidad"],
                  "precio": l["precio"], "subtotal": l["subtotal"], "id_almacen": l.get("id_almacen")}
                 for l in carrito]
        if modo_entrega == "domicilio":
            envio_direccion = (request.form.get("envio_direccion") or "").strip()
            envio_ciudad = (request.form.get("envio_ciudad") or "").strip()
            envio_cp = (request.form.get("envio_cp") or "").strip()
            envio_pais = (request.form.get("envio_pais") or "ES").strip() or "ES"
            if not (envio_direccion and envio_ciudad and envio_cp):
                return pagina_encargo(
                    token, carrito,
                    error=_t("portal_emp.indica_direccion_completa",
                            "Indica la dirección, ciudad y código postal de envío del cliente.")), 400
            direccion_envio = ", ".join(x for x in (envio_direccion, f"{envio_ciudad} {envio_cp}",
                                                    envio_pais) if x)
            fact_direccion = (request.form.get("fact_direccion") or "").strip()
            fact_ciudad = (request.form.get("fact_ciudad") or "").strip()
            fact_cp = (request.form.get("fact_cp") or "").strip()
            fact_pais = (request.form.get("fact_pais") or "").strip()
            if fact_direccion or fact_ciudad or fact_cp:
                direccion_facturacion = ", ".join(x for x in (
                    fact_direccion, f"{fact_ciudad} {fact_cp}".strip(), fact_pais) if x)
            # Gastos de envío: según la política de la empresa, el cajero decide si se le cobran
            # al cliente — si se cobran, se calculan con el MISMO motor de zonas/peso que ya usa
            # el checkout de la web propia (`comercio_digital.envios.zonas`), nunca un importe
            # inventado a mano. Degrada a 0 € honestamente si la empresa no tiene zonas
            # configuradas (ver `calcular_envio`) — nunca bloquea la creación del pedido.
            if request.form.get("cobrar_envio"):
                try:
                    from src.services.comercio_digital.envios import zonas as _Z
                    peso = _Z.peso_total_lineas(carrito, id_empresa=ses["id_empresa"])
                    importe = sum(l["subtotal"] for l in carrito)
                    envio = _Z.calcular_envio(envio_pais, peso, importe, id_empresa=ses["id_empresa"])
                    coste = float(envio.get("coste") or 0)
                    if coste > 0:
                        lineas.append({"codigo": "ENVIO",
                                       "nombre": _t("portal_emp.gastos_envio", "Gastos de envío"),
                                       "cantidad": 1, "precio": coste, "subtotal": coste,
                                       "id_almacen": None})
                except Exception as e:
                    logger.debug("calcular_envio encargo: %s", e)

        # Contexto EXPLÍCITO (id_empresa/id_tienda/id_usuario/trabajador): el portal corre en el
        # proceso del backend Flask, SIN sesión de escritorio — `crear_pedido_online`/`_ctx()` no
        # vería a este empleado. Se resuelve del JWT (mismo `centro_codigo` que ya usa la ruta
        # `/pedidos` de arriba para `tienda_de_codigo`/`almacen_de_codigo_centro`).
        id_tienda = _T.tienda_de_codigo(ses["centro_codigo"], ses["id_empresa"])
        contexto = {"id_empresa": ses["id_empresa"], "id_tienda": id_tienda,
                   "id_usuario": ses["id_usuario"], "trabajador": ses["nombre"]}
        id_pedido = OS.crear_encargo_almacen(
            cliente, lineas, direccion_envio=direccion_envio,
            modo_entrega=modo_entrega, direccion_facturacion=direccion_facturacion,
            contexto=contexto)
        if not id_pedido:
            return pagina_encargo(token, carrito,
                                  error=_t("portal_emp.no_se_pudo_crear_encargo",
                                          "No se pudo crear el encargo. Inténtalo de nuevo.")), 500
        total = sum(l["subtotal"] for l in lineas)
        return pagina_encargo_creado(token, id_pedido, total)

    @bp.get("/<token>/colores")
    def colores(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.backend import portal_theming as _tema
        titulo = _t("portal_emp.nav_personalizacion", "Personalización")
        contenido = _tema.pagina_colores_html(
            titulo=titulo, accion_guardar=f"/portal/empleado/{token}/colores/guardar",
            accion_volver=f"/portal/empleado/{token}/pedidos?estado=PAGADO",
            accion_restablecer=f"/portal/empleado/{token}/colores/restablecer",
            id_empresa=ses["id_empresa"], mensaje=request.args.get("mensaje"),
            error=request.args.get("error"))
        return _layout(titulo, contenido, token=token, activo="colores", id_empresa=ses["id_empresa"])

    @bp.post("/<token>/colores/guardar")
    def colores_guardar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from urllib.parse import quote
        from src.backend import portal_theming as _tema
        res = _tema.guardar_tema(ses["id_empresa"],
                                 color_primario=request.form.get("color_primario"),
                                 color_secundario=request.form.get("color_secundario"),
                                 color_terciario=request.form.get("color_terciario"))
        url = f"/portal/empleado/{token}/colores"
        if res["ok"]:
            url += f"?mensaje={quote(_t('portal_emp.colores_guardados', 'Colores guardados.'))}"
        else:
            url += f"?error={quote(_t('portal_emp.colores_no_guardados', 'No se pudieron guardar los colores.'))}"
        return redirect(url)

    @bp.post("/<token>/colores/restablecer")
    def colores_restablecer(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from urllib.parse import quote
        from src.backend import portal_theming as _tema
        ok = _tema.restablecer_tema(ses["id_empresa"])
        url = f"/portal/empleado/{token}/colores"
        url += (f"?mensaje={quote(_t('portal_emp.colores_restablecidos', 'Colores restablecidos.'))}" if ok
               else f"?error={quote(_t('portal_emp.colores_no_restablecidos', 'No se pudo restablecer.'))}")
        return redirect(url)

    return bp
