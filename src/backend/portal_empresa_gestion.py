"""
Extranet B2B de la Empresa · Gestión (Smart Suppliers · migración de las 9 pestañas del antiguo
escritorio de Compras — Homologar Proveedor, Devoluciones, Incidencias, Evaluación, Recepciones,
Facturas, Contratos, Informes, Calidad). Mismo patrón que `portal_empresa_b2b.py` (HTML por
funciones puras + Flask fino, sesión sin cookies) y REUTILIZA sus helpers de layout (`_layout`,
`_nav_html`, `_e`, `_pagina_error`) — no se duplica el CSS ni la navegación.

Ninguna de estas páginas contiene lógica de negocio nueva: todas orquestan las funciones YA
EXISTENTES de `src/db/compras.py` (probadas en E2.1-E2.7), `src/services/contratos/contratos_pro.py`
y `src/services/calidad/analitica.py` — las mismas que respaldaban las pestañas del escritorio antes
de retirarse (Fase E). Calidad expone solo un RESUMEN de solo lectura (`analitica.kpis`); el módulo
completo de Calidad sigue viviendo en su propia ventana de escritorio (`gui/calidad_dashboard.py`,
v_id "calidad") — no se reescribe aquí.
"""

import logging

from src.backend.portal_empresa_b2b import _e, _layout, _nav_html, _pagina_error

logger = logging.getLogger("backend.portal_empresa_gestion")


def _select(nombre, opciones, seleccionado=None, *, vacio=None):
    """`opciones`: [(valor, etiqueta)]. `vacio`: etiqueta de una opción sin valor al principio."""
    partes = []
    if vacio is not None:
        partes.append(f'<option value="">{_e(vacio)}</option>')
    for val, lab in opciones:
        sel = " selected" if str(val) == str(seleccionado) else ""
        partes.append(f'<option value="{_e(val)}"{sel}>{_e(lab)}</option>')
    return f'<select name="{_e(nombre)}">{"".join(partes)}</select>'


def _opts_proveedores(proveedores):
    return [(p["id_proveedor"], f"{p['razon_social']} ({p.get('cif_nif') or 's/CIF'})")
           for p in proveedores]


def _aviso_html(mensaje=None, error=None):
    if error:
        return f'<p class="error">{_e(error)}</p>'
    if mensaje:
        return f'<p class="ok">{_e(mensaje)}</p>'
    return ""


# ── Índice de Gestión ────────────────────────────────────────────────────────
_SECCIONES = (
    ("homologacion", "🏷️", "Homologar Proveedor", "Aprobar, suspender o bloquear proveedores."),
    ("devoluciones", "↩️", "Devoluciones", "Registrar y consultar devoluciones a proveedor."),
    ("incidencias", "⚠️", "Incidencias", "Dañado, faltante, exceso, rechazo… y su resolución."),
    ("evaluacion", "⭐", "Evaluación", "KPIs de proveedor y evaluaciones periódicas."),
    ("recepciones", "📥", "Recepciones", "Recepcionar pedidos enviados o parcialmente recibidos."),
    ("facturas", "🧾", "Facturas", "Registrar y validar facturas de proveedor."),
    ("contratos", "📄", "Contratos", "Alta, renovación y próximos vencimientos."),
    ("informes", "📊", "Informes", "Gasto por proveedor, por periodo y por artículo."),
    ("calidad", "🔬", "Calidad", "Resumen de inspecciones, no conformidades y CAPA."),
)


def pagina_gestion_index(token):
    base = f"/portal/empresa/{token}/gestion"
    tarjetas = "".join(f"""<a href="{base}/{sid}" class="btn" style="display:block;margin-bottom:10px;
text-align:left;background:#161B22;color:#E6EDF3;border:1px solid #30363D">
<b style="color:var(--ac)">{ic}  {_e(titulo)}</b><br>
<span style="color:#8B949E;font-size:12px">{_e(desc)}</span></a>"""
                        for sid, ic, titulo, desc in _SECCIONES)
    return _layout("Gestión", f"""
<div class="card"><h1>Gestión de Compras</h1>
<p>Back-office de proveedores: homologación, incidencias, devoluciones, recepciones, facturas,
contratos, informes y el resumen de Calidad.</p>
{tarjetas}
</div>""", nav=_nav_html(token, "gestion"))


# ── Homologar Proveedor ──────────────────────────────────────────────────────
_ESTADOS_HOMOLOG = ("pendiente", "aprobado", "suspendido", "bloqueado")
_ESTADOS_KYB = ("pendiente", "en_revision", "verificado", "rechazado")


def pagina_homologacion(token, proveedores, *, estados_kyb=None, mensaje=None):
    """`estados_kyb`: {id_suministrador: estado_kyb} — la verificación de identidad del proveedor en
    la PLATAFORMA (`suministradores.estado_kyb`, compartida entre todas las empresas que trabajan con
    él), distinta de `homologacion_estado` (la aprobación comercial de ESTA empresa en concreto). Solo
    aplica a proveedores que completaron su alta en el Portal Proveedor (tienen `id_suministrador`)."""
    estados_kyb = estados_kyb or {}
    base = f"/portal/empresa/{token}/gestion/homologacion"
    filas = []
    for p in proveedores:
        estado = p.get("homologacion_estado") or "pendiente"
        acciones = "".join(
            f'<form method="post" action="{base}/{p["id_proveedor"]}/{est}" style="display:inline">'
            f'<button type="submit" class="{"btn-ghost" if est == estado else ""}">{est}</button></form> '
            for est in _ESTADOS_HOMOLOG)
        id_sum = p.get("id_suministrador")
        if id_sum:
            estado_kyb = estados_kyb.get(id_sum, "pendiente")
            acciones_kyb = "".join(
                f'<form method="post" action="{base}/kyb/{id_sum}/{est}" style="display:inline">'
                f'<button type="submit" class="{"btn-ghost" if est == estado_kyb else ""}">'
                f'{est}</button></form> ' for est in _ESTADOS_KYB)
            celda_kyb = (f'<span class="badge{" badge-ok" if estado_kyb == "verificado" else ""}">'
                        f'{_e(estado_kyb)}</span><br>{acciones_kyb}')
        else:
            celda_kyb = '<span class="badge">— (no completó el alta en el Portal Proveedor)</span>'
        filas.append(f"""<tr><td>{_e(p['razon_social'])}<br>
<span class="badge">{_e(p.get('cif_nif') or 's/CIF')}</span></td>
<td><span class="badge{' badge-ok' if estado == 'aprobado' else ''}">{_e(estado)}</span></td>
<td>{acciones}</td>
<td>{celda_kyb}</td></tr>""")
    tabla = (f"<table><tr><th>Proveedor</th><th>Estado comercial</th><th>Cambiar a</th>"
            f"<th>Verificación de identidad (KYB)</th></tr>{''.join(filas)}</table>"
            if proveedores else "<p>No hay proveedores dados de alta todavía.</p>")
    return _layout("Homologar Proveedor", f"""
<div class="card"><h1>Homologar Proveedor</h1>
<p>El "estado comercial" es tu aprobación como empresa (descuentos/condiciones/bloqueo). La
"verificación de identidad (KYB)" es la comprobación de la razón social/CIF del proveedor en la
plataforma — se comparte con el resto de empresas que trabajen con él.</p>
{_aviso_html(mensaje)}{tabla}
</div>""", nav=_nav_html(token, "gestion"))


# ── Devoluciones ─────────────────────────────────────────────────────────────
def pagina_devoluciones(token, devoluciones, proveedores, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/devoluciones"
    filas = "".join(f"""<tr><td>{d['id_devolucion']}</td><td>{_e(d.get('proveedor') or d['id_proveedor'])}</td>
<td>{d.get('motivo') or '—'}</td><td>{d['total']} €</td><td><span class="badge">{_e(d['estado'])}</span></td>
<td>{_e(d['fecha'])}</td></tr>""" for d in devoluciones)
    tabla = (f"<table><tr><th>ID</th><th>Proveedor</th><th>Motivo</th><th>Total</th><th>Estado</th>"
            f"<th>Fecha</th></tr>{filas}</table>") if devoluciones else "<p>Sin devoluciones registradas.</p>"
    return _layout("Devoluciones", f"""
<div class="card"><h2>Registrar devolución</h2>
<form method="post" action="{base}/crear">
<label>Proveedor</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio='Selecciona…')}
<label>Código de artículo</label><input type="text" name="codigo" required>
<label>Cantidad</label><input type="number" name="cantidad" min="1" value="1" required>
<label>Lote (opcional)</label><input type="text" name="lote">
<label>Motivo</label><input type="text" name="motivo" placeholder="Producto dañado, caducado…">
<p><button type="submit">Registrar devolución</button></p>
</form>{_aviso_html(mensaje, error)}
</div>
<div class="card"><h2>Historial</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Incidencias ──────────────────────────────────────────────────────────────
_TIPOS_INCIDENCIA = ("danado", "faltante", "exceso", "rechazo", "error_prov", "otros")


def pagina_incidencias(token, incidencias, proveedores, *, mensaje=None):
    base = f"/portal/empresa/{token}/gestion/incidencias"
    filas = []
    for i in incidencias:
        resolver = (f'<form method="post" action="{base}/{i["id"]}/resolver" style="display:inline">'
                   f'<button type="submit">Resolver</button></form>' if i["estado"] != "resuelta" else "")
        filas.append(f"""<tr><td>{i['id']}</td><td>{_e(i['tipo'])}</td>
<td>{_e(i.get('codigo_articulo') or '—')}</td><td>{i.get('cantidad') or 0}</td>
<td>{_e(i.get('descripcion') or '—')}</td>
<td><span class="badge{' badge-ok' if i['estado'] == 'resuelta' else ''}">{_e(i['estado'])}</span></td>
<td>{_e(i['fecha'])}</td><td>{resolver}</td></tr>""")
    tabla = (f"<table><tr><th>ID</th><th>Tipo</th><th>Artículo</th><th>Cantidad</th><th>Descripción</th>"
            f"<th>Estado</th><th>Fecha</th><th></th></tr>{''.join(filas)}</table>"
            if incidencias else "<p>Sin incidencias registradas.</p>")
    return _layout("Incidencias", f"""
<div class="card"><h2>Registrar incidencia</h2>
<form method="post" action="{base}/crear">
<label>Tipo</label>{_select('tipo', [(t, t) for t in _TIPOS_INCIDENCIA])}
<label>Proveedor (opcional)</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio='—')}
<label>Código de artículo (opcional)</label><input type="text" name="codigo">
<label>Cantidad</label><input type="number" name="cantidad" min="0" value="1">
<label>Descripción</label><input type="text" name="descripcion">
<p><button type="submit">Registrar incidencia</button></p>
</form>{_aviso_html(mensaje)}
</div>
<div class="card"><h2>Historial</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Evaluación ───────────────────────────────────────────────────────────────
def pagina_evaluacion(token, proveedores, *, id_proveedor=None, kpis=None, historial=None, mensaje=None):
    base = f"/portal/empresa/{token}/gestion/evaluacion"
    resultado = ""
    if kpis is not None:
        filas_h = "".join(f"""<tr><td>{_e(h.get('periodo') or '—')}</td><td>{h['valoracion_global']}</td>
<td>{h['incidencias']}</td><td>{h['rechazos']}</td><td>{h['devoluciones']}</td>
<td>{_e(h['fecha'])}</td></tr>""" for h in (historial or []))
        tabla_h = (f"<table><tr><th>Periodo</th><th>Valoración</th><th>Incidencias</th><th>Rechazos</th>"
                  f"<th>Devoluciones</th><th>Fecha</th></tr>{filas_h}</table>"
                  if historial else "<p>Sin evaluaciones registradas todavía.</p>")
        resultado = f"""<div class="card"><h2>KPIs actuales</h2>
<p>Valoración global: <span class="badge badge-ok">{kpis['valoracion_global']}</span>
· Incidencias: <span class="badge">{kpis['incidencias']}</span>
· Rechazos: <span class="badge">{kpis['rechazos']}</span>
· Devoluciones: <span class="badge">{kpis['devoluciones']}</span>
· Pedidos recibidos: <span class="badge">{kpis['pedidos_recibidos']}</span></p>
<form method="post" action="{base}/registrar">
<input type="hidden" name="id_proveedor" value="{id_proveedor}">
<button type="submit">Registrar esta evaluación</button></form>
{_aviso_html(mensaje)}
</div>
<div class="card"><h2>Historial de evaluaciones</h2>{tabla_h}</div>"""
    return _layout("Evaluación", f"""
<div class="card"><h2>Evaluar proveedor</h2>
<form method="get" action="{base}">
{_select('id_proveedor', _opts_proveedores(proveedores), seleccionado=id_proveedor, vacio='Selecciona…')}
<button type="submit">Ver KPIs</button>
</form>
</div>{resultado}""", nav=_nav_html(token, "gestion"))


# ── Recepciones ──────────────────────────────────────────────────────────────
def pagina_recepciones(token, pedidos, nombres_proveedor):
    base = f"/portal/empresa/{token}/gestion/recepciones"
    filas = "".join(f"""<tr><td>{p['id_pedido']}</td><td>{_e(p.get('numero') or '—')}</td>
<td>{_e(nombres_proveedor.get(p['id_proveedor'], p['id_proveedor']))}</td>
<td><span class="badge">{_e(p['estado'])}</span></td><td>{p['total']} €</td>
<td><a class="btn" href="{base}/{p['id_pedido']}">Recepcionar</a></td></tr>""" for p in pedidos)
    tabla = (f"<table><tr><th>Pedido</th><th>Nº</th><th>Proveedor</th><th>Estado</th><th>Total</th>"
            f"<th></th></tr>{filas}</table>"
            if pedidos else "<p>No hay pedidos pendientes de recepción (enviados o parciales).</p>")
    return _layout("Recepciones", f"""
<div class="card"><h1>Pedidos pendientes de recepción</h1>{tabla}</div>""",
                  nav=_nav_html(token, "gestion"))


def pagina_recepcion_detalle(token, pedido, nombre_proveedor, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/recepciones/{pedido['id_pedido']}"
    filas = []
    for ln in pedido.get("lineas", []):
        pendiente = int(ln.get("cantidad") or 0) - int(ln.get("cantidad_recibida") or 0)
        if pendiente <= 0:
            continue
        filas.append(f"""<tr><td>{_e(ln.get('codigo_articulo'))}</td>
<td>{_e(ln.get('descripcion') or '—')}</td><td>{pendiente}</td>
<td><input type="number" name="cant_{ln['id']}" min="0" max="{pendiente}" value="{pendiente}"></td>
<td><input type="text" name="lote_{ln['id']}" placeholder="Lote (opc.)"></td>
<td><input type="date" name="cad_{ln['id']}"></td></tr>""")
    tabla = (f"<form method='post' action='{base}/recibir'><table><tr><th>Artículo</th>"
            f"<th>Descripción</th><th>Pendiente</th><th>Recibir ahora</th><th>Lote</th>"
            f"<th>Caducidad</th></tr>{''.join(filas)}</table>"
            f"<p><button type='submit'>Confirmar recepción</button></p></form>"
            if filas else "<p>No quedan líneas pendientes de recibir en este pedido.</p>")
    return _layout("Recepción", f"""
<div class="card"><h1>Pedido #{pedido['id_pedido']} · {_e(nombre_proveedor)}</h1>
<p>Estado: <span class="badge">{_e(pedido['estado'])}</span> · Total: {pedido['total']} €</p>
{_aviso_html(mensaje, error)}{tabla}
<p><a href="/portal/empresa/{_e(token)}/gestion/recepciones" style="color:var(--ac);font-weight:700">
← Volver a recepciones</a></p>
</div>""", nav=_nav_html(token, "gestion"))


# ── Facturas ─────────────────────────────────────────────────────────────────
def pagina_facturas(token, facturas, nombres_proveedor, proveedores, pedidos):
    base = f"/portal/empresa/{token}/gestion/facturas"
    filas = []
    for f in facturas:
        validar = (f'<form method="post" action="{base}/{f["id_factura"]}/validar" style="display:inline">'
                  f'<button type="submit" class="btn-ghost">Validar</button></form>'
                  if f["estado"] == "registrada" else "")
        filas.append(f"""<tr><td>{f['id_factura']}</td><td>{_e(f.get('numero_factura') or '—')}</td>
<td>{_e(nombres_proveedor.get(f['id_proveedor'], f['id_proveedor']))}</td>
<td>{_e(f.get('tipo_documento') or 'factura')}</td><td>{f['total']} €</td>
<td><span class="badge{' badge-ok' if f['estado'] == 'validada' else ''}">{_e(f['estado'])}</span></td>
<td>{validar}</td></tr>""")
    tabla = (f"<table><tr><th>ID</th><th>Nº factura</th><th>Proveedor</th><th>Tipo</th><th>Total</th>"
            f"<th>Estado</th><th></th></tr>{''.join(filas)}</table>"
            if facturas else "<p>Sin facturas registradas.</p>")
    opts_pedidos = [(p["id_pedido"], f"#{p['id_pedido']} · {p.get('numero') or ''} "
                                     f"({p['total']} €)") for p in pedidos]
    return _layout("Facturas", f"""
<div class="card"><h2>Registrar factura</h2>
<form method="post" action="{base}/crear">
<label>Proveedor</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio='Selecciona…')}
<label>Pedido vinculado (opcional)</label>{_select('id_pedido', opts_pedidos, vacio='— sin vincular —')}
<label>Nº de factura</label><input type="text" name="numero_factura" required>
<label>Fecha</label><input type="date" name="fecha_factura">
<label>Base (€)</label><input type="number" step="0.01" name="base" placeholder="se calcula si se deja vacío y hay pedido">
<label>IVA (€)</label><input type="number" step="0.01" name="iva" value="0">
<p><button type="submit">Registrar factura</button></p>
</form></div>
<div class="card"><h2>Facturas registradas</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Contratos ────────────────────────────────────────────────────────────────
def pagina_contratos(token, contratos, vencimientos, tipos):
    base = f"/portal/empresa/{token}/gestion/contratos"
    aviso_venc = (f'<p style="color:#FFB86C;font-weight:800">⚠️ {len(vencimientos)} contrato(s) '
                 f'vencen en los próximos 60 días.</p>' if vencimientos else "")
    filas = "".join(f"""<tr><td>{_e(c.get('codigo') or c['id'])}</td><td>{_e(c['tipo'])}</td>
<td>{_e(c.get('contraparte') or '—')}</td><td>{_e(c.get('fecha_inicio') or '—')}</td>
<td>{_e(c.get('fecha_fin') or '—')}</td><td>{c.get('valor') or 0} €</td>
<td><span class="badge">{_e(c['estado'])}</span></td>
<td><form method="post" action="{base}/{c['id']}/renovar" style="display:inline">
<button type="submit" class="btn-ghost">Renovar 12m</button></form></td></tr>""" for c in contratos)
    tabla = (f"<table><tr><th>Código</th><th>Tipo</th><th>Contraparte</th><th>Inicio</th><th>Fin</th>"
            f"<th>Valor</th><th>Estado</th><th></th></tr>{filas}</table>"
            if contratos else "<p>Sin contratos registrados.</p>")
    return _layout("Contratos", f"""
<div class="card"><h2>Nuevo contrato</h2>
<form method="post" action="{base}/crear">
<label>Código (opcional)</label><input type="text" name="codigo">
<label>Tipo</label>{_select('tipo', [(t, t) for t in tipos])}
<label>Contraparte</label><input type="text" name="contraparte">
<label>Fecha inicio</label><input type="date" name="fecha_inicio">
<label>Fecha fin</label><input type="date" name="fecha_fin">
<label>Valor (€)</label><input type="number" step="0.01" name="valor" value="0">
<p><button type="submit">Crear contrato</button></p>
</form></div>
<div class="card"><h2>Contratos</h2>{aviso_venc}{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Informes ─────────────────────────────────────────────────────────────────
def pagina_informes(token, *, por_proveedor, por_periodo, por_articulo, top_proveedores, desde, hasta):
    base = f"/portal/empresa/{token}/gestion/informes"
    f_prov = "".join(f"<tr><td>{_e(r['proveedor'])}</td><td>{r['facturas']}</td>"
                     f"<td>{r['total']} €</td></tr>" for r in por_proveedor)
    f_per = "".join(f"<tr><td>{_e(r['periodo'])}</td><td>{r['facturas']}</td>"
                    f"<td>{r['total']} €</td></tr>" for r in por_periodo)
    f_art = "".join(f"<tr><td>{_e(r['codigo_articulo'])}</td><td>{r['unidades']}</td>"
                    f"<td>{r['gasto']} €</td><td>{r['precio_medio']} €</td></tr>" for r in por_articulo[:30])
    f_top = "".join(f"<tr><td>{_e(r['proveedor'])}</td><td>{r['pedidos']}</td>"
                    f"<td>{r['total']} €</td></tr>" for r in top_proveedores)
    return _layout("Informes", f"""
<div class="card"><h1>Informes de compras</h1>
<form method="get" action="{base}">
<label>Desde</label><input type="date" name="desde" value="{_e(desde or '')}">
<label>Hasta</label><input type="date" name="hasta" value="{_e(hasta or '')}">
<button type="submit" class="btn-ghost">Filtrar</button>
</form></div>
<div class="card"><h2>Gasto por proveedor</h2>
{f"<table><tr><th>Proveedor</th><th>Facturas</th><th>Total</th></tr>{f_prov}</table>" if por_proveedor else "<p>Sin datos.</p>"}
</div>
<div class="card"><h2>Gasto por periodo</h2>
{f"<table><tr><th>Periodo</th><th>Facturas</th><th>Total</th></tr>{f_per}</table>" if por_periodo else "<p>Sin datos.</p>"}
</div>
<div class="card"><h2>Coste por artículo (top 30)</h2>
{f"<table><tr><th>Artículo</th><th>Unidades</th><th>Gasto</th><th>Precio medio</th></tr>{f_art}</table>" if por_articulo else "<p>Sin datos.</p>"}
</div>
<div class="card"><h2>Proveedores más utilizados</h2>
{f"<table><tr><th>Proveedor</th><th>Pedidos</th><th>Total</th></tr>{f_top}</table>" if top_proveedores else "<p>Sin datos.</p>"}
</div>""", nav=_nav_html(token, "gestion"))


# ── Calidad (resumen) ────────────────────────────────────────────────────────
def pagina_calidad(token, kpis):
    return _layout("Calidad", f"""
<div class="card"><h1>Calidad · Resumen</h1>
<p>Vista de solo lectura. El módulo completo de Calidad (inspecciones, no conformidades, CAPA,
auditorías) se gestiona desde Smart Manager escritorio.</p>
<p>Unidades inspeccionadas: <span class="badge">{kpis['unidades_inspeccionadas']}</span>
· Unidades rechazadas: <span class="badge">{kpis['unidades_rechazadas']}</span>
· Tasa de rechazo: <span class="badge">{kpis['tasa_rechazo_pct']} %</span></p>
<p>No conformidades abiertas: <span class="badge{' badge-ok' if not kpis['nc_abiertas'] else ''}">
{kpis['nc_abiertas']}</span> de {kpis['nc_total']} totales
· CAPA abiertas: <span class="badge">{kpis['capa_abiertas']}</span>
· CAPA cerradas: <span class="badge">{kpis['capa_cerradas']}</span></p>
<p>Unidades de merma asociadas a calidad: <span class="badge">{kpis['unidades_merma']}</span></p>
</div>""", nav=_nav_html(token, "gestion"))


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_empresa_gestion", __name__, url_prefix="/portal/empresa")

    def _sesion_o_error(token):
        from src.services.compras import b2b_sesion_empresa as SES
        ses = SES.resolver_sesion(token)
        if not ses:
            return None, (_pagina_error("Sesión no válida",
                          "Tu sesión ha caducado. Vuelve a entrar desde Smart Manager."), 401)
        return ses, None

    def _proveedores(ses):
        from src.db import proveedores as P
        return P.listar_proveedores(id_empresa=ses["id_empresa"])

    def _nombres_proveedor(ses):
        return {p["id_proveedor"]: p["razon_social"] for p in _proveedores(ses)}

    @bp.get("/<token>/gestion")
    def gestion_index(token):
        ses, err = _sesion_o_error(token)
        return err or pagina_gestion_index(token)

    # ── Homologación ──
    @bp.get("/<token>/gestion/homologacion")
    def homologacion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        provs = _proveedores(ses)
        from src.services.compras import suministradores as SUM
        estados_kyb = {}
        for p in provs:
            if p.get("id_suministrador"):
                sup = SUM.obtener(p["id_suministrador"])
                if sup:
                    estados_kyb[p["id_suministrador"]] = sup.get("estado_kyb") or "pendiente"
        return pagina_homologacion(token, provs, estados_kyb=estados_kyb)

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/<estado>")
    def homologacion_cambiar(token, id_proveedor, estado):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        if estado not in _ESTADOS_HOMOLOG:
            return redirect(f"/portal/empresa/{token}/gestion/homologacion")
        from src.db import compras as C
        C.set_homologacion_estado(id_proveedor, estado, ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/homologacion")

    @bp.post("/<token>/gestion/homologacion/kyb/<int:id_suministrador>/<estado>")
    def homologacion_kyb_cambiar(token, id_suministrador, estado):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        if estado not in _ESTADOS_KYB:
            return redirect(f"/portal/empresa/{token}/gestion/homologacion")
        from src.db import proveedores as P
        # Guarda: la empresa solo puede verificar/rechazar proveedores CON LOS QUE TIENE relación
        # (no cualquier id_suministrador de la plataforma — es una identidad compartida entre
        # empresas, pero la acción de verificarla se restringe a quien realmente trabaja con él).
        propia = any(p.get("id_suministrador") == id_suministrador
                    for p in P.listar_proveedores(id_empresa=ses["id_empresa"]))
        if propia:
            from src.services.compras import suministradores as SUM
            SUM.fijar_estado_kyb(id_suministrador, estado)
        return redirect(f"/portal/empresa/{token}/gestion/homologacion")

    # ── Devoluciones ──
    @bp.get("/<token>/gestion/devoluciones")
    def devoluciones(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        nombres = _nombres_proveedor(ses)
        devs = C.listar_devoluciones(id_empresa=ses["id_empresa"])
        for d in devs:
            d["proveedor"] = nombres.get(d["id_proveedor"])
        return pagina_devoluciones(token, devs, _proveedores(ses))

    @bp.post("/<token>/gestion/devoluciones/crear")
    def devoluciones_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_proveedor = request.form.get("id_proveedor")
        codigo = (request.form.get("codigo") or "").strip()
        try:
            cantidad = int(request.form.get("cantidad") or 0)
        except ValueError:
            cantidad = 0
        if not id_proveedor or not codigo or cantidad <= 0:
            devs = C.listar_devoluciones(id_empresa=ses["id_empresa"])
            return pagina_devoluciones(token, devs, _proveedores(ses),
                                       error="Proveedor, código y cantidad son obligatorios."), 400
        did = C.crear_devolucion(
            id_proveedor=int(id_proveedor),
            lineas=[{"codigo": codigo, "cantidad": cantidad,
                    "lote": (request.form.get("lote") or "").strip() or None}],
            motivo=(request.form.get("motivo") or "").strip() or None,
            usuario=ses.get("nombre_usuario"), id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/devoluciones") if did else (
            pagina_devoluciones(token, C.listar_devoluciones(id_empresa=ses["id_empresa"]),
                                _proveedores(ses), error="No se pudo registrar la devolución."), 400)

    # ── Incidencias ──
    @bp.get("/<token>/gestion/incidencias")
    def incidencias(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        return pagina_incidencias(token, C.listar_incidencias(id_empresa=ses["id_empresa"]),
                                  _proveedores(ses))

    @bp.post("/<token>/gestion/incidencias/crear")
    def incidencias_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        tipo = request.form.get("tipo") or "otros"
        if tipo not in _TIPOS_INCIDENCIA:
            tipo = "otros"
        id_proveedor = request.form.get("id_proveedor") or None
        try:
            cantidad = int(request.form.get("cantidad") or 0)
        except ValueError:
            cantidad = 0
        C.registrar_incidencia(
            tipo, cantidad=cantidad, id_proveedor=(int(id_proveedor) if id_proveedor else None),
            codigo=(request.form.get("codigo") or "").strip() or None,
            descripcion=(request.form.get("descripcion") or "").strip() or None,
            usuario=ses.get("nombre_usuario"), id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/incidencias")

    @bp.post("/<token>/gestion/incidencias/<int:id_incidencia>/resolver")
    def incidencias_resolver(token, id_incidencia):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        C.resolver_incidencia(id_incidencia, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/incidencias")

    # ── Evaluación ──
    @bp.get("/<token>/gestion/evaluacion")
    def evaluacion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_proveedor = request.args.get("id_proveedor")
        kpis = historial = None
        if id_proveedor:
            id_proveedor = int(id_proveedor)
            kpis = C.calcular_kpis_proveedor(id_proveedor, ses["id_empresa"])
            historial = C.listar_evaluaciones(id_proveedor, ses["id_empresa"])
        return pagina_evaluacion(token, _proveedores(ses), id_proveedor=id_proveedor, kpis=kpis,
                                 historial=historial)

    @bp.post("/<token>/gestion/evaluacion/registrar")
    def evaluacion_registrar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_proveedor = int(request.form.get("id_proveedor"))
        C.registrar_evaluacion(id_proveedor, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/evaluacion?id_proveedor={id_proveedor}")

    # ── Recepciones ──
    @bp.get("/<token>/gestion/recepciones")
    def recepciones(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        pendientes = (C.listar_pedidos(id_empresa=ses["id_empresa"], estado="ENVIADO")
                     + C.listar_pedidos(id_empresa=ses["id_empresa"], estado="PARCIAL"))
        return pagina_recepciones(token, pendientes, _nombres_proveedor(ses))

    @bp.get("/<token>/gestion/recepciones/<int:id_pedido>")
    def recepcion_detalle(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        ped = C.obtener_pedido(id_pedido, ses["id_empresa"])
        if not ped:
            return _pagina_error("Recepción", "Pedido no encontrado."), 404
        nombre = _nombres_proveedor(ses).get(ped["id_proveedor"], str(ped["id_proveedor"]))
        return pagina_recepcion_detalle(token, ped, nombre)

    @bp.post("/<token>/gestion/recepciones/<int:id_pedido>/recibir")
    def recepcion_recibir(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        ped = C.obtener_pedido(id_pedido, ses["id_empresa"])
        if not ped:
            return _pagina_error("Recepción", "Pedido no encontrado."), 404
        lineas_recibidas = []
        for ln in ped.get("lineas", []):
            try:
                cant = int(request.form.get(f"cant_{ln['id']}") or 0)
            except ValueError:
                cant = 0
            if cant > 0:
                lineas_recibidas.append({
                    "id_linea": ln["id"], "cantidad": cant,
                    "lote": (request.form.get(f"lote_{ln['id']}") or "").strip() or None,
                    "fecha_caducidad": (request.form.get(f"cad_{ln['id']}") or "").strip() or None})
        if not lineas_recibidas:
            nombre = _nombres_proveedor(ses).get(ped["id_proveedor"], str(ped["id_proveedor"]))
            return pagina_recepcion_detalle(token, ped, nombre,
                                            error="Indica al menos una cantidad a recibir."), 400
        res = C.recibir(id_pedido, lineas_recibidas, usuario=ses.get("nombre_usuario"),
                        id_empresa=ses["id_empresa"])
        if not res:
            nombre = _nombres_proveedor(ses).get(ped["id_proveedor"], str(ped["id_proveedor"]))
            return pagina_recepcion_detalle(token, ped, nombre,
                                            error="No se pudo registrar la recepción."), 400
        return redirect(f"/portal/empresa/{token}/gestion/recepciones")

    # ── Facturas ──
    @bp.get("/<token>/gestion/facturas")
    def facturas(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        facs = C.listar_facturas(id_empresa=ses["id_empresa"])
        pedidos = C.listar_pedidos(id_empresa=ses["id_empresa"])
        return pagina_facturas(token, facs, _nombres_proveedor(ses), _proveedores(ses), pedidos)

    @bp.post("/<token>/gestion/facturas/crear")
    def facturas_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_proveedor = request.form.get("id_proveedor")
        numero = (request.form.get("numero_factura") or "").strip()
        if not id_proveedor or not numero:
            return redirect(f"/portal/empresa/{token}/gestion/facturas")
        base_txt = (request.form.get("base") or "").strip()
        id_pedido = request.form.get("id_pedido") or None
        C.registrar_factura(
            id_proveedor=int(id_proveedor), numero_factura=numero,
            id_pedido=(int(id_pedido) if id_pedido else None),
            base=(float(base_txt) if base_txt else None),
            iva=float(request.form.get("iva") or 0),
            fecha_factura=(request.form.get("fecha_factura") or "").strip() or None,
            id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/facturas")

    @bp.post("/<token>/gestion/facturas/<int:id_factura>/validar")
    def facturas_validar(token, id_factura):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        C.validar_factura(id_factura, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/facturas")

    # ── Contratos ──
    @bp.get("/<token>/gestion/contratos")
    def contratos(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.contratos import contratos_pro as CT
        return pagina_contratos(token, CT.listar_contratos(ses["id_empresa"]),
                                CT.proximos_vencimientos(ses["id_empresa"], dias=60), CT.TIPOS)

    @bp.post("/<token>/gestion/contratos/crear")
    def contratos_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.contratos import contratos_pro as CT
        CT.crear_contrato(
            codigo=(request.form.get("codigo") or "").strip() or None,
            tipo=request.form.get("tipo") or "servicio",
            contraparte=(request.form.get("contraparte") or "").strip() or None,
            fecha_inicio=(request.form.get("fecha_inicio") or "").strip() or None,
            fecha_fin=(request.form.get("fecha_fin") or "").strip() or None,
            valor=float(request.form.get("valor") or 0), id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/contratos")

    @bp.post("/<token>/gestion/contratos/<int:id_contrato>/renovar")
    def contratos_renovar(token, id_contrato):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.contratos import contratos_pro as CT
        CT.renovar_contrato(id_contrato, meses=12, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/contratos")

    # ── Informes ──
    @bp.get("/<token>/gestion/informes")
    def informes(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        desde = request.args.get("desde") or None
        hasta = request.args.get("hasta") or None
        return pagina_informes(
            token,
            por_proveedor=C.compras_por_proveedor(desde, hasta, ses["id_empresa"]),
            por_periodo=C.compras_por_periodo(desde, hasta, ses["id_empresa"]),
            por_articulo=C.costes_por_articulo(id_empresa=ses["id_empresa"]),
            top_proveedores=C.proveedores_mas_utilizados(id_empresa=ses["id_empresa"]),
            desde=desde, hasta=hasta)

    # ── Calidad (resumen) ──
    @bp.get("/<token>/gestion/calidad")
    def calidad(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.calidad import analitica as CAL
        return pagina_calidad(token, CAL.kpis(id_empresa=ses["id_empresa"]))

    return bp
