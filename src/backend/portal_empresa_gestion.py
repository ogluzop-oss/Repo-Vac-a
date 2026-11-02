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

import json
import logging

from src.backend.portal_empresa_b2b import _e, _layout, _nav_html, _pagina_error
from src.backend.portal_i18n import t as _t

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


def _volver_gestion(token):
    """Enlace "Volver a Gestión" en la esquina superior derecha, compartido por TODAS las sub-páginas
    de Gestión — un único helper reutilizado, en vez de duplicar el HTML en cada página."""
    return (f'<div style="text-align:right;margin-bottom:10px">'
           f'<a href="/portal/empresa/{_e(token)}/gestion" class="btn btn-ghost" '
           f'style="font-size:12px;padding:6px 12px">◀ {_t("portal_gest.volver_gestion", "Volver a Gestión")}</a></div>')


# ── Alta artículo (migrada desde "Info artículo" del escritorio, petición explícita) ────────────
# Reutiliza OBLIGATORIAMENTE los motores ya existentes: generador de EAN-13 único
# (`src/utils/ean.py::generar`, el MISMO que usaba la antigua pestaña "Alta artículo" del
# escritorio, ya retirada de `gui/info_articulo.py` tras esta migración) y el
# alta real (`src/db/articulos.py::crear_articulo`). La novedad de esta página es la referencia de
# proveedor opcional, que crea una equivalencia (`src/db/equivalencias_proveedor.py`, migr. 0316)
# — sin la cual el proveedor nunca podría identificarse en recepción con su propio código de barras.
def _bloque_equivalencias_fila_html(equivalencias):
    """Lista en línea de TODAS las equivalencias activas de un artículo (petición explícita: ya
    no se muestran como filas de "Proveedor" sueltas en la búsqueda) — la más reciente (primera,
    `listar_equivalencias_de_articulo` ya devuelve orden DESC por fecha) resaltada en bold; el
    resto se lista igual de apta para seguir usándose, solo que sin el resalte."""
    if not equivalencias:
        return ""
    partes = []
    for i, eq in enumerate(equivalencias):
        ref = _e(eq.get("referencia_proveedor"))
        nombre_prov = eq.get("nombre_proveedor")
        txt = f"{ref} ({_e(nombre_prov)})" if nombre_prov else ref
        partes.append(f"<b>{txt}</b>" if i == 0 else txt)
    return (f'<div class="sub" style="margin-top:4px">'
           f'{_t("portal_gest.equivalencias_lbl", "Referencias de proveedor:")} ' + ", ".join(partes) + "</div>")


def _bloque_buscar_unificado_html(token, busqueda, resultados):
    """Búsqueda "Buscar artículo" (revisada, petición explícita): SOLO artículos del catálogo
    INTERNO de la empresa — ya no se listan filas de "Proveedor" sueltas. Cada artículo muestra,
    en su lugar, TODAS sus equivalencias de proveedor activas (si tiene dos o más), con la más
    reciente resaltada en bold — todas igualmente aptas para seguir usándose."""
    base = f"/portal/empresa/{token}/gestion/alta_articulo"

    def _toggle_flag_si_no(codigo, campo, activo):
        """Celda "Sí"/"No" (petición explícita) que es a la vez el toggle: un clic cambia el
        valor — mismo mecanismo que antes, ahora expresado como el indicador Sí/No pedido en vez
        de un botón "Marcar..."."""
        nuevo = "0" if activo else "1"
        clase = "badge badge-ok" if activo else "badge"
        texto = _t("portal_gest.si", "Sí") if activo else _t("portal_gest.no", "No")
        return (f'<form method="post" action="{base}/{_e(codigo)}/flag" class="inline">'
               f'<input type="hidden" name="campo" value="{campo}">'
               f'<input type="hidden" name="valor" value="{nuevo}">'
               f'<input type="hidden" name="buscar" value="{_e(busqueda or "")}">'
               f'<button type="submit" class="{clase}" style="border:none;cursor:pointer" '
               f'title="{_t("portal_gest.click_para_cambiar", "Clic para cambiar")}">{texto}</button></form>')

    filas = ""
    for r in resultados or []:
        atributos = " / ".join(filter(None, [r.get("talla"), r.get("marca"), r.get("color")]))
        gestionar = (f'<a class="btn btn-ghost" style="font-size:11px;padding:4px 8px" '
                    f'href="{base}/equivalencias/{_e(r.get("codigo"))}">'
                    f'{_t("portal_gest.gestionar_equiv_btn", "Equivalencias")}</a>')
        equiv_html = _bloque_equivalencias_fila_html(r.get("equivalencias"))
        filas += (f'<tr><td>{_e(r.get("codigo"))}</td>'
                 f'<td>{_e(r.get("nombre"))}{equiv_html}</td>'
                 f'<td>{_e(atributos) or "—"}</td><td>{_e(r.get("precio"))} €</td>'
                 f'<td>{_toggle_flag_si_no(r.get("codigo"), "es_complementario", bool(r.get("es_complementario")))}</td>'
                 f'<td>{_toggle_flag_si_no(r.get("codigo"), "es_promocional", bool(r.get("es_promocional")))}</td>'
                 f'<td>{gestionar}</td></tr>')
    tabla = (f'<table><tr><th>{_t("portal_gest.col_codigo", "Código")}</th>'
            f'<th>{_t("portal_gest.col_nombre", "Nombre")}</th>'
            f'<th>{_t("portal_gest.col_talla_marca_color", "Talla/Marca/Color")}</th>'
            f'<th>{_t("portal_gest.col_precio", "Precio")}</th>'
            f'<th>{_t("portal_gest.col_complementario", "Complementario")}</th>'
            f'<th>{_t("portal_gest.col_promocional", "Promocional")}</th>'
            f'<th></th></tr>{filas}</table>' if resultados else
            (f'<p>{_t("portal_gest.sin_coincidencias", "Sin coincidencias para «{q}».", q=_e(busqueda))}</p>' if busqueda else ""))
    return f"""<div class="card"><h2>{_t("portal_gest.buscar_articulo_h2", "Buscar artículo")}</h2>
<p>{_t("portal_gest.buscar_articulo_desc2",
      "Comprueba antes de crear uno nuevo: busca por código o nombre en tu catálogo interno. Si "
      "un artículo tiene varias equivalencias de proveedor, se listan todas, con la más reciente "
      "en negrita.")}</p>
<form method="get" action="{base}">
<input type="text" name="buscar" value="{_e(busqueda or '')}" placeholder="{_t("portal_gest.codigo_nombre_ph", "Código o nombre...")}">
<button type="submit">{_t("portal_gest.buscar_btn", "Buscar")}</button>
</form>
{tabla}
</div>"""


def _bloque_impresora_etiquetas_html(token):
    """Configuración de la impresora de etiquetas de ESTA máquina (petición explícita): dato de
    máquina, no de empresa — reutiliza tal cual `services.etiquetas.impresion.obtener_
    impresora_configurada/configurar_impresora_etiquetas` (antes sin ninguna superficie de UI)."""
    base = f"/portal/empresa/{token}/gestion/alta_articulo"
    from src.services.etiquetas import impresion as _IMPR
    actual = _IMPR.obtener_impresora_configurada()
    estado = (_t("portal_gest.impresora_configurada_como", "Configurada como: «{n}»", n=_e(actual))
             if actual else
             _t("portal_gest.impresora_predeterminada_sistema", "Usando la impresora predeterminada del sistema."))
    return f"""<div class="card"><h2>{_t("portal_gest.impresora_etiquetas_h2", "Impresora de etiquetas de este equipo")}</h2>
<p class="sub">{estado}</p>
<form method="post" action="{base}/impresora" class="inline">
<input type="text" name="nombre_impresora" value="{_e(actual or '')}"
placeholder="{_t("portal_gest.nombre_impresora_ph", "Nombre exacto de la impresora (vacío = predeterminada)")}">
<button type="submit" class="btn btn-ghost">{_t("portal_gest.guardar_btn2", "Guardar")}</button>
</form>
</div>"""


def pagina_alta_articulo(token, *, mensaje=None, error=None, resultado=None, proveedores=None,
                         vincular=None, busqueda=None, resultados_busqueda=None):
    """`resultado` (tras crear con éxito): dict con codigo/nombre/etiqueta_generada/equivalencia
    para mostrar el EAN generado y, si aplica, la confirmación de la etiqueta impresa.

    `vincular` (llegada desde la detección de duplicados del pedido a proveedor, petición
    explícita — "Sí -> redirigir a Alta artículos para crear la equivalencia"): dict con
    codigo_existente/nombre_existente/id_proveedor/referencia_proveedor — en vez del formulario de
    alta completo, se muestra un bloque de confirmación de UNA sola acción (vincular la referencia
    del proveedor al artículo YA EXISTENTE, sin crear ningún artículo nuevo)."""
    base = f"/portal/empresa/{token}/gestion/alta_articulo"
    opts_prov = "".join(f'<option value="{p["id_proveedor"]}">{_e(p["razon_social"])}</option>'
                        for p in (proveedores or []))
    titulo_alta = _t("portal_gest.alta_articulo_titulo", "Alta artículo")
    if vincular:
        return _layout(titulo_alta, f"""
{_volver_gestion(token)}
{_aviso_html(mensaje, error)}
<div class="card"><h1>{_t("portal_gest.vincular_ref_proveedor_h1", "Vincular referencia de proveedor")}</h1>
<p>{_t("portal_gest.vas_a_vincular", "Vas a vincular la referencia {r} del proveedor al artículo YA EXISTENTE en tu catálogo interno:", r=f"<b>{_e(vincular.get('referencia_proveedor'))}</b>")}</p>
<p><b>{_e(vincular.get('nombre_existente'))}</b> ({_t("portal_gest.codigo_lbl", "código {c}", c=_e(vincular.get('codigo_existente')))})</p>
<p>{_t("portal_gest.no_se_creara_articulo",
      "No se creará ningún artículo nuevo — solo la equivalencia, para que al recibir mercancía "
      "de este proveedor escaneando su propio código de barras, el sistema lo reconozca como "
      "este artículo.")}</p>
<form method="post" action="{base}/vincular">
<input type="hidden" name="codigo_existente" value="{_e(vincular.get('codigo_existente'))}">
<input type="hidden" name="id_proveedor" value="{_e(vincular.get('id_proveedor') or '')}">
<input type="hidden" name="id_suministrador" value="{_e(vincular.get('id_suministrador') or '')}">
<input type="hidden" name="nombre_proveedor" value="{_e(vincular.get('nombre_proveedor') or '')}">
<input type="hidden" name="referencia_proveedor" value="{_e(vincular.get('referencia_proveedor'))}">
<button type="submit" class="btn btn-primary">{_t("portal_gest.confirmar_vinculacion_btn", "Confirmar vinculación")}</button>
</form>
</div>""", nav=_nav_html(token, "gestion"))
    bloque_resultado = ""
    if resultado:
        bloque_resultado = f"""<div class="card" style="border:2px solid var(--ac)">
<h2>✔ {_t("portal_gest.articulo_creado_h2", "Artículo creado")}</h2>
<p><b>{_t("portal_gest.codigo_interno_ean_lbl", "Código interno (EAN-13):")}</b> {_e(resultado.get('codigo'))}</p>
<p><b>{_t("portal_gest.nombre_lbl", "Nombre:")}</b> {_e(resultado.get('nombre'))}</p>
{f"<p class='ok'>{_t('portal_gest.equivalencia_registrada', 'Equivalencia con la referencia del proveedor registrada correctamente.')}</p>"
 if resultado.get('equivalencia_creada') else ""}
{f"<p class='ok'>{_t('portal_gest.etiqueta_generada_impresa', 'Etiqueta generada (ref. interna + PVP + sección) y enviada a la impresora configurada.')}</p>" if resultado.get('etiqueta_impresa') else
 f"<p class='sub'>{_t('portal_gest.etiqueta_sin_impresora', 'No se pudo enviar la etiqueta a ninguna impresora configurada — el PDF de la etiqueta sigue disponible en el Centro Documental.')}</p>" if resultado.get('etiqueta_generada')
 else ""}
<p><a class="btn btn-ghost" href="{base}/equivalencias/{_e(resultado.get('codigo'))}">
{_t("portal_gest.gestionar_equivalencias_articulo", "Gestionar equivalencias de este artículo")}</a></p>
</div>"""
    return _layout(titulo_alta, f"""
{_volver_gestion(token)}
{_aviso_html(mensaje, error)}
{bloque_resultado}
{_bloque_buscar_unificado_html(token, busqueda, resultados_busqueda)}
{_bloque_impresora_etiquetas_html(token)}
<div class="card"><h1>{_t("portal_gest.alta_de_articulo_h1", "Alta de artículo")}</h1>
<p>{_t("portal_gest.codigo_generado_automatico",
      "El código de artículo (EAN-13) se genera automáticamente al guardar — reutiliza el mismo "
      "generador que la aplicación de escritorio, nunca se teclea a mano.")}</p>
<form method="post" action="{base}/crear">
<label>{_t("portal_gest.nombre_req_lbl", "Nombre *")}</label>
<input type="text" name="nombre" required>
<label>{_t("portal_gest.precio_ref_lbl", "Precio de referencia (€) *")}</label>
<input type="text" name="precio" required placeholder="0,00">
<label>{_t("portal_gest.seccion_lbl", "Sección")}</label>
<input type="text" name="seccion" placeholder="{_t("portal_gest.seccion_ph", "p. ej. TEXTIL, ALIMENTACIÓN...")}">
<label>{_t("portal_gest.marca_equiv_lbl", "Marca (o equivalente del sector: variedad, calibre…)")}</label>
<input type="text" name="marca">
<label>{_t("portal_gest.talla_si_aplica_lbl", "Talla (si aplica)")}</label>
<input type="text" name="talla">
<label>{_t("portal_gest.color_si_aplica_lbl", "Color (si aplica)")}</label>
<input type="text" name="color">
<label style="font-weight:400"><input type="checkbox" name="es_complementario"
style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
{_t("portal_gest.es_complementario_lbl", "Artículo complementario (cuenta como «venta cruzada» al venderse por TPV)")}</label>
<label style="font-weight:400"><input type="checkbox" name="es_promocional"
style="width:auto;padding:0;margin:0 6px 0 0;vertical-align:middle">
{_t("portal_gest.es_promocional_lbl", "Artículo promocional (cuenta como «venta promocional» al venderse por TPV)")}</label>
<hr>
<p><b>{_t("portal_gest.vincular_ref_opcional", "Vincular a una referencia de proveedor (opcional)")}</b> — {_t("portal_gest.permite_que_al_recibir",
      "permite que, al recibir mercancía de este proveedor escaneando SU propio código de "
      "barras, el sistema lo reconozca automáticamente como este artículo interno.")}</p>
<label>{_t("portal_gest.proveedor_lbl", "Proveedor")}</label>
<select name="id_proveedor"><option value="">{_t("portal_gest.ninguno_opt", "— Ninguno —")}</option>{opts_prov}</select>
<label>{_t("portal_gest.ref_proveedor_lbl", "Referencia del proveedor")}</label>
<input type="text" name="referencia_proveedor" placeholder="{_t("portal_gest.ref_proveedor_ph", "Código/SKU que usa el proveedor")}">
<button type="submit" class="btn btn-primary" style="margin-top:14px">{_t("portal_gest.crear_articulo_btn", "Crear artículo")}</button>
</form>
</div>""", nav=_nav_html(token, "gestion"))

def pagina_equivalencias_articulo(token, codigo_articulo, nombre_articulo, equivalencias, *,
                                  mensaje=None, error=None):
    """Lista TODAS las equivalencias (activas y deshechas) de un artículo interno, con un botón de
    Deshacer/Reactivar por fila (petición explícita — "mecanismo de reversibilidad... en cualquier
    punto del proceso"). Reutiliza `db.equivalencias_proveedor.listar_equivalencias_de_articulo`
    (antes sin ninguna superficie de UI) y `deshacer_equivalencia`/`reactivar_equivalencia` — nunca
    se borra una fila, solo cambia su `estado`."""
    base = f"/portal/empresa/{token}/gestion/alta_articulo/equivalencias/{codigo_articulo}"
    filas = ""
    for e in equivalencias or []:
        activa = e.get("estado") == "activa"
        # El texto del confirm() es SIEMPRE estático (nunca interpola `referencia_proveedor`, dato
        # controlado por el usuario): interpolarlo dentro de un literal JS de un atributo onclick
        # sería una vía de inyección si la referencia trajera una comilla simple.
        accion = (f'<form method="post" action="{base}/{e["id"]}/deshacer" class="inline">'
                 f'<button type="submit" class="btn-ghost" onclick="return confirm(\'{_t("portal_gest.confirmar_deshacer_js", "¿Deshacer esta equivalencia? Dejará de reconocerse en recepción y en la búsqueda; podrás reactivarla después.")}\')">'
                 f'{_t("portal_gest.deshacer_btn", "Deshacer")}</button></form>'
                 if activa else
                 f'<form method="post" action="{base}/{e["id"]}/reactivar" class="inline">'
                 f'<button type="submit" class="btn-ghost" onclick="return confirm(\'{_t("portal_gest.confirmar_reactivar_js", "¿Reactivar esta equivalencia?")}\')">'
                 f'{_t("portal_gest.reactivar_btn", "Reactivar")}</button></form>')
        estilo_fila = "" if activa else ' style="opacity:.55"'
        filas += (f'<tr{estilo_fila}>'
                 f'<td>{_e(e.get("referencia_proveedor"))}</td>'
                 f'<td>{_e(e.get("nombre_proveedor") or "—")}</td>'
                 f'<td>{_e(e.get("origen_proveedor"))}</td>'
                 f'<td><span class="badge{" badge-ok" if activa else ""}">{_e(e.get("estado"))}</span></td>'
                 f'<td>{_e(e.get("fecha_creacion") or "—")}</td><td>{accion}</td></tr>')
    tabla = (f'<table><tr><th>{_t("portal_gest.col_ref_proveedor", "Referencia proveedor")}</th>'
            f'<th>{_t("portal_gest.col_proveedor", "Proveedor")}</th>'
            f'<th>{_t("portal_gest.col_origen", "Origen")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th>'
            f'<th>{_t("portal_gest.col_creada", "Creada")}</th><th></th></tr>{filas}</table>'
            if equivalencias else f'<p>{_t("portal_gest.sin_equivalencias", "Este artículo no tiene ninguna equivalencia de proveedor todavía.")}</p>')
    return _layout(_t("portal_gest.equivalencias_titulo", "Equivalencias"), f"""
{_volver_gestion(token)}
{_aviso_html(mensaje, error)}
<div class="card"><h1>{_t("portal_gest.equivalencias_de_h1", "Equivalencias de «{n}»", n=_e(nombre_articulo))}</h1>
<p class="sub">{_t("portal_gest.codigo_interno_lbl", "Código interno: {c}", c=_e(codigo_articulo))}</p>
<p>{_t("portal_gest.equivalencias_desc",
      "Cada fila vincula una referencia de proveedor con este artículo interno. «Deshacer» NO "
      "borra el histórico — solo deja de reconocerse en recepción y en la búsqueda; puedes "
      "reactivarla después si fue un error.")}</p>
{tabla}
</div>
<p><a class="btn btn-ghost" href="/portal/empresa/{_e(token)}/gestion/alta_articulo">
◀ {_t("portal_gest.volver_alta_articulo", "Volver a Alta artículo")}</a></p>""",
                  nav=_nav_html(token, "gestion"))


# ── Índice de Gestión ────────────────────────────────────────────────────────
_SECCIONES = (
    ("alta_articulo", "➕", "Alta artículo",
     "Crear un artículo nuevo en el catálogo interno (EAN-13 automático) y, opcionalmente, "
     "vincularlo a una referencia de proveedor."),
    ("homologacion", "🏷️", "Homologar Proveedor", "Aprobar, suspender o bloquear proveedores."),
    ("devoluciones", "↩️", "Devoluciones", "Registrar y consultar devoluciones a proveedor."),
    ("incidencias", "⚠️", "Incidencias", "Dañado, faltante, exceso, rechazo… y su resolución."),
    ("evaluacion", "⭐", "Evaluación", "KPIs de proveedor y evaluaciones periódicas."),
    ("recepciones", "📥", "Recepciones pendientes",
     "Pedidos pendientes por recibir o parcialmente recibidos."),
    ("facturas", "🧾", "Facturas", "Registrar y validar facturas de proveedor."),
    ("contratos", "📄", "Contratos", "Alta, renovación y próximos vencimientos."),
    ("informes", "📊", "Informes", "Gasto por proveedor, por periodo y por artículo."),
    ("calidad", "🔬", "Calidad", "Resumen de inspecciones, no conformidades y CAPA."),
    ("compras_pro", "🔁", "Pedidos recurrentes",
     "Pedidos recurrentes, órdenes abiertas, comparativa de proveedores y aprobación de pedidos."),
    ("rappels", "💰", "Rappels", "Tramos de rebate acumulado por proveedor y liquidación."),
    ("licitaciones", "🏆", "Licitaciones", "Subastas inversas (RFQ): pide precio a tus proveedores y "
     "adjudica la mejor oferta."),
)


def pagina_gestion_index(token):
    # `_SECCIONES` es una constante de MÓDULO (evaluada al importar, sin contexto de petición
    # Flask) — el texto en español ahí es solo la fuente/default; la traducción real ocurre aquí
    # dentro, por petición, con `_t(f"portal_gest.sec_{sid}_titulo"/..._desc", ...)`.
    base = f"/portal/empresa/{token}/gestion"
    tarjetas = "".join(f"""<a href="{base}/{sid}" class="gestion-card">
<b>{ic}  {_e(_t(f"portal_gest.sec_{sid}_titulo", titulo))}</b><br>
<span>{_e(_t(f"portal_gest.sec_{sid}_desc", desc))}</span></a>"""
                        for sid, ic, titulo, desc in _SECCIONES)
    return _layout(_t("portal_gest.gestion_titulo", "Gestión"), f"""
<div class="card"><h1>{_t("portal_gest.gestion_compras_h1", "Gestión de Compras")}</h1>
<p>{_t("portal_gest.gestion_compras_desc",
      "Back-office de proveedores: homologación, incidencias, devoluciones, recepciones, "
      "facturas, contratos, informes y el resumen de Calidad.")}</p>
{tarjetas}
</div>""", nav=_nav_html(token, "gestion"))


# ── Homologar Proveedor ──────────────────────────────────────────────────────
_ESTADOS_HOMOLOG = ("pendiente", "aprobado", "suspendido", "bloqueado")
_ESTADOS_KYB = ("pendiente", "en_revision", "verificado", "rechazado")


def pagina_homologacion(token, proveedores, *, estados_kyb=None, mensaje=None, id_proveedor=None,
                        contactos=None, direcciones=None, certificaciones=None, acuerdos=None,
                        tarifas=None):
    """`estados_kyb`: {id_suministrador: estado_kyb} — la verificación de identidad del proveedor en
    la PLATAFORMA (`suministradores.estado_kyb`, compartida entre todas las empresas que trabajan con
    él), distinta de `homologacion_estado` (la aprobación comercial de ESTA empresa en concreto). Solo
    aplica a proveedores que completaron su alta en el Portal Proveedor (tienen `id_suministrador`).
    `id_proveedor`/`contactos`/`direcciones`/`certificaciones`/`acuerdos`/`tarifas`: ficha completa del
    proveedor elegido (`db.proveedores.agregar_contacto/agregar_direccion` + `services.compras.
    proveedores_pro` — sin ninguna superficie hasta esta auditoría)."""
    estados_kyb = estados_kyb or {}
    base = f"/portal/empresa/{token}/gestion/homologacion"
    filas = []
    for p in proveedores:
        estado = p.get("homologacion_estado") or "pendiente"
        id_p = p["id_proveedor"]
        # Un único <select> por fila (en vez de los 4 botones anteriores) que se auto-envía a la
        # MISMA ruta POST /<id_proveedor>/<estado> que ya usaban los botones — no cambia el backend,
        # solo cómo se elige el estado destino. Preseleccionado con el estado actual de la fila.
        opts_estado = "".join(f'<option value="{est}"{" selected" if est == estado else ""}>{est}</option>'
                              for est in _ESTADOS_HOMOLOG)
        selector_estado = f"""<form method="post" action="{base}/{id_p}/{estado}" id="frm-hom-{id_p}">
<select name="estado_comercial" onchange="document.getElementById('frm-hom-{id_p}').action='{base}/{id_p}/'+this.value;document.getElementById('frm-hom-{id_p}').submit()">{opts_estado}</select></form>"""
        id_sum = p.get("id_suministrador")
        if id_sum:
            estado_kyb = estados_kyb.get(id_sum, "pendiente")
            opts_kyb = "".join(f'<option value="{est}"{" selected" if est == estado_kyb else ""}>{est}</option>'
                               for est in _ESTADOS_KYB)
            celda_kyb = f"""<form method="post" action="{base}/kyb/{id_sum}/{estado_kyb}" id="frm-kyb-{id_sum}">
<select name="estado_kyb" onchange="document.getElementById('frm-kyb-{id_sum}').action='{base}/kyb/{id_sum}/'+this.value;document.getElementById('frm-kyb-{id_sum}').submit()">{opts_kyb}</select></form>"""
        else:
            celda_kyb = f'<span class="badge">{_t("portal_gest.no_completo_alta", "— (no completó el alta en el Portal Proveedor)")}</span>'
        filas.append(f"""<tr><td>{_e(p['razon_social'])}<br>
<span class="badge">{_e(p.get('cif_nif') or 's/CIF')}</span></td>
<td>{selector_estado}</td>
<td>{celda_kyb}</td></tr>""")
    tabla = (f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th>'
            f'<th>{_t("portal_gest.col_sel_estado_comercial", "Seleccionar estado comercial")}</th>'
            f'<th>{_t("portal_gest.col_verif_kyb", "Verificación de identidad (KYB)")}</th></tr>{"".join(filas)}</table>'
            if proveedores else f'<p>{_t("portal_gest.sin_proveedores", "No hay proveedores dados de alta todavía.")}</p>')
    base_ficha = f"/portal/empresa/{token}/gestion/homologacion"
    ficha = ""
    if id_proveedor:
        filas_c = "".join(f"""<tr><td>{_e(c.get('nombre'))}</td><td>{_e(c.get('cargo') or '—')}</td>
<td>{_e(c.get('email') or '—')}</td><td>{_e(c.get('telefono') or '—')}</td></tr>"""
                          for c in (contactos or []))
        tabla_c = (f'<table><tr><th>{_t("portal_gest.col_nombre", "Nombre")}</th>'
                  f'<th>{_t("portal_gest.col_cargo", "Cargo")}</th>'
                  f'<th>{_t("portal_gest.col_email", "Email")}</th>'
                  f'<th>{_t("portal_gest.col_telefono", "Teléfono")}</th></tr>'
                  f"{filas_c}</table>" if contactos else f'<p>{_t("portal_gest.sin_contactos", "Sin contactos registrados.")}</p>')
        filas_d = "".join(f"""<tr><td>{_e(d.get('tipo'))}</td><td>{_e(d.get('direccion') or '—')}</td>
<td>{_e(d.get('cp') or '—')}</td><td>{_e(d.get('municipio') or '—')}</td>
<td>{_e(d.get('provincia') or '—')}</td><td>{_e(d.get('pais') or '—')}</td></tr>"""
                          for d in (direcciones or []))
        tabla_d = (f'<table><tr><th>{_t("portal_gest.col_tipo", "Tipo")}</th>'
                  f'<th>{_t("portal_gest.col_direccion", "Dirección")}</th>'
                  f'<th>{_t("portal_gest.col_cp", "CP")}</th>'
                  f'<th>{_t("portal_gest.col_municipio", "Municipio")}</th>'
                  f'<th>{_t("portal_gest.col_provincia", "Provincia")}</th>'
                  f'<th>{_t("portal_gest.col_pais", "País")}</th></tr>{filas_d}</table>'
                  if direcciones else f'<p>{_t("portal_gest.sin_direcciones", "Sin direcciones registradas.")}</p>')
        filas_cert = "".join(f"""<tr><td>{_e(c.get('tipo'))}</td><td>{_e(c.get('numero') or '—')}</td>
<td>{_e(c.get('emisor') or '—')}</td><td>{_e(c.get('fecha_caducidad') or '—')}</td>
<td><span class="badge{' badge-ok' if c.get('estado') == 'vigente' else ''}">{_e(c.get('estado') or 'vigente')}</span>
</td></tr>""" for c in (certificaciones or []))
        tabla_cert = (f'<table><tr><th>{_t("portal_gest.col_tipo", "Tipo")}</th>'
                     f'<th>{_t("portal_gest.col_numero", "Número")}</th>'
                     f'<th>{_t("portal_gest.col_emisor", "Emisor")}</th>'
                     f'<th>{_t("portal_gest.col_caduca", "Caduca")}</th>'
                     f'<th>{_t("portal_gest.col_estado", "Estado")}</th></tr>{filas_cert}</table>' if certificaciones
                     else f'<p>{_t("portal_gest.sin_certificaciones", "Sin certificaciones registradas.")}</p>')
        filas_ac = "".join(f"""<tr><td>{_e(a.get('referencia') or a['id'])}</td>
<td>{_e(a.get('fecha_inicio') or '—')}</td><td>{_e(a.get('fecha_fin') or '—')}</td>
<td>{a.get('importe_comprometido') or 0} €</td>
<td><span class="badge{' badge-ok' if a.get('estado') == 'vigente' else ''}">{_e(a.get('estado') or 'vigente')}</span>
</td></tr>""" for a in (acuerdos or []))
        tabla_ac = (f'<table><tr><th>{_t("portal_gest.col_referencia", "Referencia")}</th>'
                   f'<th>{_t("portal_gest.col_inicio", "Inicio")}</th>'
                   f'<th>{_t("portal_gest.col_fin", "Fin")}</th>'
                   f'<th>{_t("portal_gest.col_importe", "Importe")}</th>'
                   f'<th>{_t("portal_gest.col_estado", "Estado")}</th></tr>{filas_ac}</table>' if acuerdos
                   else f'<p>{_t("portal_gest.sin_acuerdos", "Sin acuerdos marco registrados.")}</p>')
        eliminar_btn = _t("portal_gest.eliminar_btn", "Eliminar")
        filas_tar = "".join(f"""<tr><td>{_e(t.get('codigo'))}</td><td>{_e(t.get('descripcion') or '—')}</td>
<td>{t.get('precio_neto')} {_e(t.get('divisa') or 'EUR')}</td><td>{_e(t.get('unidad_medida'))}</td>
<td><form method="post" action="{base_ficha}/{id_proveedor}/tarifas/{t['id']}/eliminar" style="display:inline">
<button type="submit" class="btn-ghost">{eliminar_btn}</button></form></td></tr>""" for t in (tarifas or []))
        tabla_tar = (f'<table><tr><th>{_t("portal_gest.col_articulo", "Artículo")}</th>'
                    f'<th>{_t("portal_gest.col_descripcion", "Descripción")}</th>'
                    f'<th>{_t("portal_gest.col_precio_neto", "Precio neto")}</th>'
                    f'<th>{_t("portal_gest.col_unidad", "Unidad")}</th>'
                    f"<th></th></tr>{filas_tar}</table>" if tarifas else f'<p>{_t("portal_gest.sin_tarifas", "Sin tarifas registradas.")}</p>')
        ficha = f"""
<div class="card"><h2>{_t("portal_gest.contactos_h2", "Contactos")}</h2>{tabla_c}
<form method="post" action="{base_ficha}/{id_proveedor}/contactos/agregar">
<input type="text" name="nombre" placeholder="{_t("portal_gest.nombre_ph", "Nombre")}" required>
<input type="text" name="cargo" placeholder="{_t("portal_gest.cargo_ph", "Cargo")}">
<input type="email" name="email" placeholder="{_t("portal_gest.email_ph", "Email")}">
<input type="text" name="telefono" placeholder="{_t("portal_gest.telefono_ph", "Teléfono")}">
<button type="submit">{_t("portal_gest.anadir_contacto_btn", "Añadir contacto")}</button></form></div>
<div class="card"><h2>{_t("portal_gest.direcciones_h2", "Direcciones")}</h2>{tabla_d}
<form method="post" action="{base_ficha}/{id_proveedor}/direcciones/agregar">
{_select('tipo', [('fiscal', _t('portal_gest.fiscal_opt', 'Fiscal')), ('entrega', _t('portal_gest.entrega_opt', 'Entrega')), ('facturacion', _t('portal_gest.facturacion_opt', 'Facturación'))])}
<input type="text" name="direccion" placeholder="{_t("portal_gest.direccion_ph", "Dirección")}">
<input type="text" name="cp" placeholder="{_t("portal_gest.cp_ph", "CP")}">
<input type="text" name="municipio" placeholder="{_t("portal_gest.municipio_ph", "Municipio")}">
<input type="text" name="provincia" placeholder="{_t("portal_gest.provincia_ph", "Provincia")}">
<input type="text" name="pais" placeholder="{_t("portal_gest.pais_ph", "País")}" value="España">
<button type="submit">{_t("portal_gest.anadir_direccion_btn", "Añadir dirección")}</button></form></div>
<div class="card"><h2>{_t("portal_gest.certificaciones_h2", "Certificaciones")}</h2>{tabla_cert}
<form method="post" action="{base_ficha}/{id_proveedor}/certificaciones/agregar">
<input type="text" name="tipo" placeholder="{_t("portal_gest.tipo_iso_ph", "Tipo (p. ej. ISO 9001)")}" required>
<input type="text" name="numero" placeholder="{_t("portal_gest.numero_ph", "Número")}">
<input type="text" name="emisor" placeholder="{_t("portal_gest.emisor_ph", "Emisor")}">
<label>{_t("portal_gest.caduca_lbl", "Caduca")}</label><input type="text" name="fecha_caducidad" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<button type="submit">{_t("portal_gest.anadir_certificacion_btn", "Añadir certificación")}</button></form></div>
<div class="card"><h2>{_t("portal_gest.acuerdos_marco_h2", "Acuerdos marco")}</h2>{tabla_ac}
<form method="post" action="{base_ficha}/{id_proveedor}/acuerdos/agregar">
<input type="text" name="referencia" placeholder="{_t("portal_gest.referencia_ph", "Referencia")}">
<label>{_t("portal_gest.inicio_lbl", "Inicio")}</label><input type="text" name="fecha_inicio" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.fin_lbl", "Fin")}</label><input type="text" name="fecha_fin" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<input type="number" step="0.01" name="importe_comprometido" placeholder="{_t("portal_gest.importe_comprometido_ph", "Importe comprometido (€)")}">
<button type="submit">{_t("portal_gest.crear_acuerdo_btn", "Crear acuerdo")}</button></form></div>
<div class="card"><h2>{_t("portal_gest.tarifas_negociadas_h2", "Tarifas negociadas")}</h2>{tabla_tar}
<form method="post" action="{base_ficha}/{id_proveedor}/tarifas/agregar">
<input type="text" name="codigo" placeholder="{_t("portal_gest.codigo_articulo_ph", "Código de artículo")}" required>
<input type="number" step="0.01" name="precio" placeholder="{_t("portal_gest.precio_ph", "Precio")}" required>
<input type="number" step="0.01" name="descuento" placeholder="{_t("portal_gest.descuento_pct_ph", "Descuento %")}" value="0">
{_select('unidad_medida', [(u, u) for u in ('unidad', 'caja', 'pale', 'kg')])}
<button type="submit">{_t("portal_gest.anadir_tarifa_btn", "Añadir tarifa")}</button></form>
<form method="post" action="{base_ficha}/{id_proveedor}/tarifas/importar" enctype="multipart/form-data" style="margin-top:8px">
<input type="file" name="archivo" accept=".csv,.xlsx,.xls" required>
<button type="submit">{_t("portal_gest.importar_tarifas_btn", "Importar tarifas (CSV/Excel)")}</button></form></div>"""
    titulo_homolog = _t("portal_gest.homologar_proveedor_titulo", "Homologar Proveedor")
    return _layout(titulo_homolog, f"""
{_volver_gestion(token)}
<div class="card"><h1>{titulo_homolog}</h1>
<p>{_t("portal_gest.homologar_desc",
      'El "estado comercial" es tu aprobación como empresa (descuentos/condiciones/bloqueo). La '
      '"verificación de identidad (KYB)" es la comprobación de la razón social/CIF del proveedor '
      "en la plataforma — se comparte con el resto de empresas que trabajen con él.")}</p>
{_aviso_html(mensaje)}{tabla}
</div>
<div class="card"><h2>{_t("portal_gest.ficha_proveedor_h2", "Ficha del proveedor (contactos y direcciones)")}</h2>
<form method="get" action="{base_ficha}">
{_select('id_proveedor', _opts_proveedores(proveedores), seleccionado=id_proveedor, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<button type="submit">{_t("portal_gest.ver_ficha_btn", "Ver ficha")}</button></form></div>
{ficha}""", nav=_nav_html(token, "gestion"))


# ── Devoluciones ─────────────────────────────────────────────────────────────
def pagina_devoluciones(token, devoluciones, proveedores, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/devoluciones"
    filas = "".join(f"""<tr><td>{d['id_devolucion']}</td><td>{_e(d.get('proveedor') or d['id_proveedor'])}</td>
<td>{d.get('motivo') or '—'}</td><td>{d['total']} €</td><td><span class="badge">{_e(d['estado'])}</span></td>
<td>{_e(d['fecha'])}</td></tr>""" for d in devoluciones)
    tabla = (f'<table><tr><th>ID</th><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th>'
            f'<th>{_t("portal_gest.col_motivo", "Motivo")}</th><th>{_t("portal_gest.col_total", "Total")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th>'
            f'<th>{_t("portal_gest.col_fecha", "Fecha")}</th></tr>{filas}</table>') if devoluciones else f'<p>{_t("portal_gest.sin_devoluciones", "Sin devoluciones registradas.")}</p>'
    titulo_dev = _t("portal_gest.devoluciones_titulo", "Devoluciones")
    return _layout(titulo_dev, f"""
{_volver_gestion(token)}
<div class="card"><h2>{_t("portal_gest.registrar_devolucion_h2", "Registrar devolución")}</h2>
<form method="post" action="{base}/crear">
<label>{_t("portal_gest.proveedor_lbl", "Proveedor")}</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.codigo_articulo_lbl", "Código de artículo")}</label><input type="text" name="codigo" required>
<label>{_t("portal_gest.cantidad_lbl", "Cantidad")}</label><input type="number" name="cantidad" min="1" value="1" required>
<label>{_t("portal_gest.lote_opcional_lbl", "Lote (opcional)")}</label><input type="text" name="lote">
<label>{_t("portal_gest.motivo_lbl", "Motivo")}</label><input type="text" name="motivo" placeholder="{_t("portal_gest.motivo_devol_ph", "Producto dañado, caducado…")}">
<p><button type="submit">{_t("portal_gest.registrar_devolucion_btn", "Registrar devolución")}</button></p>
</form>{_aviso_html(mensaje, error)}
</div>
<div class="card"><h2>{_t("portal_gest.historial_h2", "Historial")}</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Incidencias ──────────────────────────────────────────────────────────────
_TIPOS_INCIDENCIA = ("danado", "faltante", "exceso", "rechazo", "error_prov", "otros")
# Solo corrige la ETIQUETA visible ("Dañado", con tilde); el valor almacenado sigue siendo "danado"
# (ya existen filas con ese valor en BD y `db.compras.registrar_incidencia` lo compara literalmente).
_ETIQUETA_TIPO_INCIDENCIA = {"danado": "Dañado"}


def pagina_incidencias(token, incidencias, proveedores, *, mensaje=None):
    base = f"/portal/empresa/{token}/gestion/incidencias"
    resolver_btn = _t("portal_gest.resolver_btn", "Resolver")
    filas = []
    for i in incidencias:
        resolver = (f'<form method="post" action="{base}/{i["id"]}/resolver" style="display:inline">'
                   f'<button type="submit">{resolver_btn}</button></form>' if i["estado"] != "resuelta" else "")
        filas.append(f"""<tr><td>{i['id']}</td>
<td>{_e(_t(f"portal_gest.tipo_incidencia_{i['tipo']}", _ETIQUETA_TIPO_INCIDENCIA.get(i['tipo'], i['tipo'])))}</td>
<td>{_e(i.get('codigo_articulo') or '—')}</td><td>{i.get('cantidad') or 0}</td>
<td>{_e(i.get('descripcion') or '—')}</td>
<td><span class="badge{' badge-ok' if i['estado'] == 'resuelta' else ''}">{_e(i['estado'])}</span></td>
<td>{_e(i['fecha'])}</td><td>{resolver}</td></tr>""")
    tabla = (f'<table><tr><th>ID</th><th>{_t("portal_gest.col_tipo", "Tipo")}</th>'
            f'<th>{_t("portal_gest.col_articulo", "Artículo")}</th><th>{_t("portal_gest.col_cantidad", "Cantidad")}</th>'
            f'<th>{_t("portal_gest.col_descripcion", "Descripción")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th><th>{_t("portal_gest.col_fecha", "Fecha")}</th><th></th></tr>{"".join(filas)}</table>'
            if incidencias else f'<p>{_t("portal_gest.sin_incidencias", "Sin incidencias registradas.")}</p>')
    titulo_inc = _t("portal_gest.incidencias_titulo", "Incidencias")
    return _layout(titulo_inc, f"""
{_volver_gestion(token)}
<div class="card"><h2>{_t("portal_gest.registrar_incidencia_h2", "Registrar incidencia")}</h2>
<form method="post" action="{base}/crear">
<label>{_t("portal_gest.tipo_lbl", "Tipo")}</label>{_select('tipo', [(t, _t(f"portal_gest.tipo_incidencia_{t}", _ETIQUETA_TIPO_INCIDENCIA.get(t, t))) for t in _TIPOS_INCIDENCIA])}
<label>{_t("portal_gest.proveedor_opcional_lbl", "Proveedor (opcional)")}</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio='—')}
<label>{_t("portal_gest.codigo_articulo_opcional_lbl", "Código de artículo (opcional)")}</label><input type="text" name="codigo">
<label>{_t("portal_gest.cantidad_lbl", "Cantidad")}</label><input type="number" name="cantidad" min="0" value="1">
<label>{_t("portal_gest.descripcion_lbl", "Descripción")}</label><input type="text" name="descripcion">
<p><button type="submit">{_t("portal_gest.registrar_incidencia_btn", "Registrar incidencia")}</button></p>
</form>{_aviso_html(mensaje)}
</div>
<div class="card"><h2>{_t("portal_gest.historial_h2", "Historial")}</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


# ── Evaluación ───────────────────────────────────────────────────────────────
def pagina_evaluacion(token, proveedores, *, id_proveedor=None, kpis=None, historial=None, mensaje=None):
    base = f"/portal/empresa/{token}/gestion/evaluacion"
    resultado = ""
    if kpis is not None:
        filas_h = "".join(f"""<tr><td>{_e(h.get('periodo') or '—')}</td><td>{h['valoracion_global']}</td>
<td>{h['incidencias']}</td><td>{h['rechazos']}</td><td>{h['devoluciones']}</td>
<td>{_e(h['fecha'])}</td></tr>""" for h in (historial or []))
        tabla_h = (f'<table><tr><th>{_t("portal_gest.col_periodo", "Periodo")}</th>'
                  f'<th>{_t("portal_gest.col_valoracion", "Valoración")}</th>'
                  f'<th>{_t("portal_gest.col_incidencias", "Incidencias")}</th>'
                  f'<th>{_t("portal_gest.col_rechazos", "Rechazos")}</th>'
                  f'<th>{_t("portal_gest.col_devoluciones", "Devoluciones")}</th>'
                  f'<th>{_t("portal_gest.col_fecha", "Fecha")}</th></tr>{filas_h}</table>'
                  if historial else f'<p>{_t("portal_gest.sin_evaluaciones", "Sin evaluaciones registradas todavía.")}</p>')
        resultado = f"""<div class="card"><h2>{_t("portal_gest.kpis_actuales_h2", "KPIs actuales")}</h2>
<p>{_t("portal_gest.valoracion_global_lbl", "Valoración global:")} <span class="badge badge-ok">{kpis['valoracion_global']}</span>
· {_t("portal_gest.incidencias_lbl", "Incidencias:")} <span class="badge">{kpis['incidencias']}</span>
· {_t("portal_gest.rechazos_lbl", "Rechazos:")} <span class="badge">{kpis['rechazos']}</span>
· {_t("portal_gest.devoluciones_lbl", "Devoluciones:")} <span class="badge">{kpis['devoluciones']}</span>
· {_t("portal_gest.pedidos_recibidos_lbl", "Pedidos recibidos:")} <span class="badge">{kpis['pedidos_recibidos']}</span></p>
<form method="post" action="{base}/registrar">
<input type="hidden" name="id_proveedor" value="{id_proveedor}">
<button type="submit">{_t("portal_gest.registrar_evaluacion_btn", "Registrar esta evaluación")}</button></form>
{_aviso_html(mensaje)}
</div>
<div class="card"><h2>{_t("portal_gest.historial_evaluaciones_h2", "Historial de evaluaciones")}</h2>{tabla_h}</div>"""
    return _layout(_t("portal_gest.evaluacion_titulo", "Evaluación"), f"""
{_volver_gestion(token)}
<div class="card"><h2>{_t("portal_gest.evaluar_proveedor_h2", "Evaluar proveedor")}</h2>
<form method="get" action="{base}">
{_select('id_proveedor', _opts_proveedores(proveedores), seleccionado=id_proveedor, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<button type="submit">{_t("portal_gest.ver_kpis_btn", "Ver KPIs")}</button>
</form>
</div>{resultado}""", nav=_nav_html(token, "gestion"))


# ── Recepciones ──────────────────────────────────────────────────────────────
def pagina_recepciones(token, pedidos, nombres_proveedor):
    base = f"/portal/empresa/{token}/gestion/recepciones"
    recepcionar_btn = _t("portal_gest.recepcionar_btn", "Recepcionar")
    filas = "".join(f"""<tr><td>{p['id_pedido']}</td><td>{_e(p.get('numero') or '—')}</td>
<td>{_e(nombres_proveedor.get(p['id_proveedor'], p['id_proveedor']))}</td>
<td><span class="badge">{_e(p['estado'])}</span></td><td>{p['total']} €</td>
<td><a class="btn" href="{base}/{p['id_pedido']}">{recepcionar_btn}</a></td></tr>""" for p in pedidos)
    tabla = (f'<table><tr><th>{_t("portal_gest.col_pedido", "Pedido")}</th>'
            f'<th>{_t("portal_gest.col_numero", "Nº")}</th>'
            f'<th>{_t("portal_gest.col_proveedor", "Proveedor")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th>'
            f'<th>{_t("portal_gest.col_total", "Total")}</th>'
            f"<th></th></tr>{filas}</table>"
            if pedidos else f'<p>{_t("portal_gest.sin_pedidos_recepcion", "No hay pedidos pendientes de recepción (enviados o parciales).")}</p>')
    return _layout(_t("portal_gest.recepciones_pendientes_titulo", "Recepciones pendientes"), f"""
{_volver_gestion(token)}
<div class="card"><h1>{_t("portal_gest.pedidos_pendientes_recepcion_h1", "Pedidos pendientes de recepción")}</h1>{tabla}</div>""",
                  nav=_nav_html(token, "gestion"))


def _tabla_landed_html(landed):
    """Tabla de desglose de coste landed por línea (Fase B) — reutilizada por la recepción de
    compra y por el pedido B2B (mismo formato, misma función `db.compras.resumen_costes_landed`)."""
    if not landed:
        return f'<p>{_t("portal_gest.sin_costes_landed", "Sin costes extra prorrateados todavía sobre estas líneas.")}</p>'
    filas = "".join(f"""<tr><td>{_e(r['codigo_articulo'])}</td><td>{r['cantidad']}</td>
<td>{r['coste_base_unitario']} €</td><td>{r['coste_unitario_indirecto']} €</td>
<td><b>{r['coste_unitario_landed']} €</b></td>
<td>{_e(', '.join(f"{c['tipo']} ({c['importe_asignado']} €)" for c in r['componentes']))}</td></tr>"""
                    for r in landed)
    return (f'<table><tr><th>{_t("portal_gest.col_articulo", "Artículo")}</th>'
           f'<th>{_t("portal_gest.col_cantidad", "Cantidad")}</th>'
           f'<th>{_t("portal_gest.col_coste_base_ud", "Coste base/ud")}</th>'
           f'<th>{_t("portal_gest.col_coste_indirecto_ud", "Coste indirecto/ud")}</th>'
           f'<th>{_t("portal_gest.col_coste_landed_ud", "Coste landed/ud")}</th>'
           f'<th>{_t("portal_gest.col_componentes", "Componentes")}</th></tr>{filas}</table>')


def pagina_recepcion_detalle(token, pedido, nombre_proveedor, *, mensaje=None, error=None,
                             recepciones=None, landed_por_recepcion=None):
    """`recepciones`: recepciones YA confirmadas de este pedido (`db.compras.listar_recepciones`) —
    sobre ellas se registran costes extra y se prorratean (`registrar_coste_extra`/
    `prorratear_costes_recepcion`). `landed_por_recepcion` (Fase B — Landed Cost):
    {id_recepcion: resumen de `db.compras.resumen_costes_landed`} con el desglose auditable ya
    prorrateado, si lo hay."""
    base = f"/portal/empresa/{token}/gestion/recepciones/{pedido['id_pedido']}"
    filas = []
    for ln in pedido.get("lineas", []):
        pendiente = int(ln.get("cantidad") or 0) - int(ln.get("cantidad_recibida") or 0)
        if pendiente <= 0:
            continue
        filas.append(f"""<tr><td>{_e(ln.get('codigo_articulo'))}</td>
<td>{_e(ln.get('descripcion') or '—')}</td><td>{pendiente}</td>
<td><input type="number" name="cant_{ln['id']}" min="0" max="{pendiente}" value="{pendiente}"></td>
<td><input type="text" name="lote_{ln['id']}" placeholder="{_t("portal_gest.lote_opc_ph", "Lote (opc.)")}"></td>
<td><input type="text" name="cad_{ln['id']}" data-cdate-tipo="date" placeholder="dd/mm/aaaa"></td></tr>""")
    tabla = (f'<form method=\'post\' action=\'{base}/recibir\'><table><tr><th>{_t("portal_gest.col_articulo", "Artículo")}</th>'
            f'<th>{_t("portal_gest.col_descripcion", "Descripción")}</th><th>{_t("portal_gest.col_pendiente", "Pendiente")}</th>'
            f'<th>{_t("portal_gest.col_recibir_ahora", "Recibir ahora")}</th><th>{_t("portal_gest.col_lote", "Lote")}</th>'
            f'<th>{_t("portal_gest.col_caducidad", "Caducidad")}</th></tr>{"".join(filas)}</table>'
            f'<p><button type=\'submit\'>{_t("portal_gest.confirmar_recepcion_btn", "Confirmar recepción")}</button></p></form>'
            if filas else f'<p>{_t("portal_gest.sin_lineas_pendientes_recibir", "No quedan líneas pendientes de recibir en este pedido.")}</p>')
    costes = ""
    recepciones = recepciones or []
    landed_por_recepcion = landed_por_recepcion or {}
    if recepciones:
        opts_rec = [(r["id_recepcion"], _t("portal_gest.recepcion_numero", "Recepción #{n} · {f}",
                                           n=r['id_recepcion'], f=r.get('fecha') or ''))
                   for r in recepciones]
        desglose_html = "".join(f"""<div class="card"><h3>{_t("portal_gest.desglose_landed_recepcion", "Desglose landed · Recepción #{n}", n=r['id_recepcion'])}</h3>
{_tabla_landed_html(landed_por_recepcion.get(r['id_recepcion']))}</div>""" for r in recepciones)
        costes = f"""
<div class="card"><h2>{_t("portal_gest.costes_extra_recepcion_h2", "Costes extra de la recepción (transporte, aduanas, seguro…)")}</h2>
<p>{_t("portal_gest.costes_prorrateo_desc",
      "Se prorratean sobre el coste medio de los artículos de la recepción elegida, según el "
      "método de reparto elegido (por cantidad, por valor o por peso).")}</p>
<form method="post" action="{base}/costes_extra">
{_select('id_recepcion', opts_rec, vacio=_t('portal_gest.selecciona_recepcion_ph', 'Selecciona la recepción…'))}
{_select('tipo', _opts_tipo_coste_extra())}
<input type="number" step="0.01" name="importe" placeholder="{_t("portal_gest.importe_eur_ph", "Importe (€)")}" required>
{_select('metodo_prorrateo', _opts_metodo_prorrateo())}
<input type="text" name="descripcion" placeholder="{_t("portal_gest.descripcion_opcional_ph", "Descripción (opcional)")}">
<button type="submit">{_t("portal_gest.registrar_coste_btn", "Registrar coste")}</button></form>
<form method="post" action="{base}/prorratear" style="margin-top:8px">
{_select('id_recepcion', opts_rec, vacio=_t('portal_gest.selecciona_recepcion_ph', 'Selecciona la recepción…'))}
<button type="submit">{_t("portal_gest.prorratear_costes_btn", "Prorratear costes pendientes")}</button></form>
</div>
{desglose_html}"""
    return _layout(_t("portal_gest.recepcion_titulo", "Recepción"), f"""
<div class="card"><h1>{_t("portal_gest.pedido_num_h1", "Pedido #{n} · {p}", n=pedido['id_pedido'], p=_e(nombre_proveedor))}</h1>
<p>{_t("portal_gest.estado_lbl", "Estado:")} <span class="badge">{_e(pedido['estado'])}</span> · {_t("portal_gest.total_lbl3", "Total: {t} €", t=pedido['total'])}</p>
{_aviso_html(mensaje, error)}{tabla}
<p><a href="/portal/empresa/{_e(token)}/gestion/recepciones" style="color:var(--ac);font-weight:700">
{_t("portal_gest.volver_recepciones", "← Volver a recepciones")}</a></p>
</div>{costes}""", nav=_nav_html(token, "gestion"))


def _opts_tipo_coste_extra():
    return [('transporte', _t('portal_gest.tipo_transporte', 'Transporte')),
           ('aduanas', _t('portal_gest.tipo_aduanas', 'Aduanas')),
           ('importacion', _t('portal_gest.tipo_importacion', 'Importación')),
           ('seguro', _t('portal_gest.tipo_seguro', 'Seguro')),
           ('manipulacion', _t('portal_gest.tipo_manipulacion', 'Manipulación')),
           ('otros', _t('portal_gest.tipo_otros', 'Otros'))]


def _opts_metodo_prorrateo():
    return [('cantidad', _t('portal_gest.metodo_por_cantidad', 'Por cantidad')),
           ('valor', _t('portal_gest.metodo_por_valor', 'Por valor')),
           ('peso', _t('portal_gest.metodo_por_peso', 'Por peso'))]


# ── Costes extra B2B (Landed Cost, Fase B, punto 5-6) ─────────────────────────
# Pedido B2B (Smart Suppliers) ya recibido: mismo patrón que `pagina_recepcion_detalle` pero
# sobre `transaccion_lineas`/`id_tx` en vez de `compras_recepciones_lineas`/`id_recepcion` — las
# mismas funciones de `db.compras` (`registrar_coste_extra`/`prorratear_costes_recepcion`/
# `resumen_costes_landed`), solo cambia qué tabla de líneas leen internamente.
def pagina_costes_extra_b2b(token, tx, nombre_proveedor, landed, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/b2b/{tx['id_tx']}"
    filas_lineas = "".join(f"""<tr><td>{_e(ln.get('codigo_articulo'))}</td><td>{ln['cantidad']}</td>
<td>{ln['precio_unitario']} €</td></tr>""" for ln in tx.get("lineas", []))
    tabla_lineas = (f'<table><tr><th>{_t("portal_gest.col_articulo", "Artículo")}</th>'
                    f'<th>{_t("portal_gest.col_cantidad", "Cantidad")}</th>'
                    f'<th>{_t("portal_gest.col_precio_base", "Precio base")}</th></tr>'
                    f"{filas_lineas}</table>" if filas_lineas else f'<p>{_t("portal_gest.pedido_sin_lineas", "Este pedido no tiene líneas.")}</p>')
    recibido = bool(tx.get("stock_recibido_en"))
    aviso_recepcion = ("" if recibido else
                       f'<p style="color:#FFB86C;font-weight:700">⚠️ {_t("portal_gest.aviso_sin_recepcion",
                       "Este pedido aún no tiene mercancía recibida en almacén (se recibe desde "
                       "Logística). El coste landed se puede registrar igualmente, pero solo se "
                       "reflejará en el coste medio del artículo una vez recibida la mercancía.")}</p>')
    return _layout(_t("portal_gest.coste_landed_b2b_titulo", "Coste landed B2B"), f"""
{_volver_gestion(token)}
<div class="card"><h1>{_t("portal_gest.pedido_b2b_h1", "Pedido B2B")} <code>{_e(tx['id_tx'])}</code> · {_e(nombre_proveedor)}</h1>
<p>{_t("portal_gest.estado_lbl", "Estado:")} <span class="badge">{_e(tx.get('estado'))}</span> · {_t("portal_gest.total_lbl3", "Total: {t} €", t=tx.get('total'))}</p>
{aviso_recepcion}
{_aviso_html(mensaje, error)}{tabla_lineas}</div>
<div class="card"><h2>{_t("portal_gest.costes_extra_h2", "Costes extra (transporte, aduanas, seguro…)")}</h2>
<p>{_t("portal_gest.costes_prorrateo_b2b_desc",
      "Se prorratean sobre el coste medio de los artículos de este pedido B2B, según el método "
      "de reparto elegido (por cantidad, por valor o por peso).")}</p>
<form method="post" action="{base}/costes_extra">
{_select('tipo', _opts_tipo_coste_extra())}
<input type="number" step="0.01" name="importe" placeholder="{_t("portal_gest.importe_eur_ph", "Importe (€)")}" required>
{_select('metodo_prorrateo', _opts_metodo_prorrateo())}
<input type="text" name="descripcion" placeholder="{_t("portal_gest.descripcion_opcional_ph", "Descripción (opcional)")}">
<button type="submit">{_t("portal_gest.registrar_coste_btn", "Registrar coste")}</button></form>
<form method="post" action="{base}/prorratear" style="margin-top:8px">
<button type="submit">{_t("portal_gest.prorratear_costes_btn", "Prorratear costes pendientes")}</button></form>
</div>
<div class="card"><h2>{_t("portal_gest.desglose_landed_h2", "Desglose landed")}</h2>{_tabla_landed_html(landed)}</div>""",
                  nav=_nav_html(token, "gestion"))


# ── Facturas ─────────────────────────────────────────────────────────────────
def pagina_facturas(token, facturas, nombres_proveedor, proveedores, pedidos, *, saldos=None):
    base = f"/portal/empresa/{token}/gestion/facturas"
    saldos = saldos or {}
    filas = []
    for f in facturas:
        validar = (f'<form method="post" action="{base}/{f["id_factura"]}/validar" style="display:inline">'
                  f'<button type="submit" class="btn-ghost">{_t("portal_gest.validar_btn", "Validar")}</button></form>'
                  if f["estado"] == "registrada" else "")
        # Pagar (pagos_proveedor.registrar_pago): solo tiene sentido con la factura ya validada y
        # con saldo pendiente — antes no existía ningún punto (ni escritorio ni portal) desde el que
        # pagar una factura de proveedor ya registrada (huella de la auditoría app-wide).
        pendiente = saldos.get(f["id_factura"])
        pagar = ""
        if f["estado"] == "validada" and pendiente and pendiente > 0:
            pagar = (f'<form method="post" action="{base}/{f["id_factura"]}/pagar" style="display:inline">'
                    f'<input type="hidden" name="id_proveedor" value="{f["id_proveedor"]}">'
                    f'<select name="metodo"><option value="transferencia">{_t("portal_gest.metodo_transferencia", "Transferencia")}</option>'
                    f'<option value="domiciliacion">{_t("portal_gest.metodo_domiciliacion", "Domiciliación")}</option>'
                    f'<option value="confirming">{_t("portal_gest.metodo_confirming", "Confirming")}</option>'
                    f'<option value="tarjeta">{_t("portal_gest.metodo_tarjeta", "Tarjeta")}</option><option value="efectivo">{_t("portal_gest.metodo_efectivo", "Efectivo")}</option>'
                    f'<option value="otros">{_t("portal_gest.tipo_otros", "Otros")}</option></select> '
                    f'<input type="number" step="0.01" name="importe" value="{pendiente}" '
                    f'min="0.01" max="{pendiente}" style="width:90px"> '
                    f'<button type="submit" class="btn-ghost">{_t("portal_gest.pagar_btn", "Pagar")}</button></form>')
        estado_pago = ((" · " + _t("portal_gest.pendiente_importe", "pendiente {p} €", p=pendiente)) if pendiente
                      else ((" · " + _t("portal_gest.pagada_lbl", "pagada")) if f["estado"] == "validada" else ""))
        filas.append(f"""<tr><td>{f['id_factura']}</td><td>{_e(f.get('numero_factura') or '—')}</td>
<td>{_e(nombres_proveedor.get(f['id_proveedor'], f['id_proveedor']))}</td>
<td>{_e(f.get('tipo_documento') or 'factura')}</td><td>{f['total']} €{estado_pago}</td>
<td><span class="badge{' badge-ok' if f['estado'] == 'validada' else ''}">{_e(f['estado'])}</span></td>
<td>{validar} {pagar}</td></tr>""")
    tabla = (f'<table><tr><th>ID</th><th>{_t("portal_gest.col_num_factura", "Nº factura")}</th>'
            f'<th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_tipo", "Tipo")}</th>'
            f'<th>{_t("portal_gest.col_total", "Total")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th><th></th></tr>{"".join(filas)}</table>'
            if facturas else f'<p>{_t("portal_gest.sin_facturas", "Sin facturas registradas.")}</p>')
    opts_pedidos = [(p["id_pedido"], f"#{p['id_pedido']} · {p.get('numero') or ''} "
                                     f"({p['total']} €)") for p in pedidos]
    opts_facturas = [(f["id_factura"], f"#{f['id_factura']} · {f.get('numero_factura') or ''} "
                                        f"({f['total']} €)") for f in facturas]
    return _layout(_t("portal_gest.facturas_titulo", "Facturas"), f"""
{_volver_gestion(token)}
<div class="card"><h2>{_t("portal_gest.registrar_factura_h2", "Registrar factura")}</h2>
<form method="post" action="{base}/crear">
<label>{_t("portal_gest.col_proveedor", "Proveedor")}</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.pedido_vinculado_opc_lbl", "Pedido vinculado (opcional)")}</label>{_select('id_pedido', opts_pedidos, vacio=_t('portal_gest.sin_vincular_opt', '— sin vincular —'))}
<label>{_t("portal_gest.num_factura_lbl", "Nº de factura")}</label><input type="text" name="numero_factura" required>
<label>{_t("portal_gest.fecha_lbl", "Fecha")}</label><input type="text" name="fecha_factura" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.base_eur_lbl", "Base (€)")}</label><input type="number" step="0.01" name="base" placeholder="{_t("portal_gest.base_calcula_ph", "se calcula si se deja vacío y hay pedido")}">
<label>{_t("portal_gest.iva_eur_lbl", "IVA (€)")}</label><input type="number" step="0.01" name="iva" value="0">
<p><button type="submit">{_t("portal_gest.registrar_factura_btn", "Registrar factura")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.facturas_registradas_h2", "Facturas registradas")}</h2>{tabla}</div>
<div class="card"><h2>{_t("portal_gest.registrar_abono_h2", "Registrar abono / rectificativa")}</h2>
<p>{_t("portal_gest.abono_desc",
      "Un abono anula (total o parcialmente) el importe de una factura ya registrada; una "
      "rectificativa la corrige. Se contabiliza como documento propio (`db.compras.registrar_abono`).")}</p>
<form method="post" action="{base}/abono">
<label>{_t("portal_gest.col_proveedor", "Proveedor")}</label>{_select('id_proveedor', _opts_proveedores(proveedores), vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.factura_rectifica_opc_lbl", "Factura que rectifica (opcional)")}</label>{_select('id_factura_rectificada', opts_facturas, vacio=_t('portal_gest.nuevo_abono_opt', '— nuevo abono —'))}
<label>{_t("portal_gest.num_documento_lbl", "Nº de documento")}</label><input type="text" name="numero_factura" required>
<label>{_t("portal_gest.fecha_lbl", "Fecha")}</label><input type="text" name="fecha_factura" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.base_eur_lbl", "Base (€)")}</label><input type="number" step="0.01" name="base" required>
<label>{_t("portal_gest.iva_eur_lbl", "IVA (€)")}</label><input type="number" step="0.01" name="iva" value="0">
<p><button type="submit">{_t("portal_gest.registrar_abono_btn", "Registrar abono")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.asociar_recepcion_h2", "Asociar recepción a factura (conciliación)")}</h2>
<p>{_t("portal_gest.asociar_recepcion_desc",
      "Vincula una recepción de mercancía a una factura, con el importe correspondiente "
      "(`db.compras.asociar_recepcion_factura`) — para facturas que agrupan varias recepciones.")}</p>
<form method="post" action="{base}/asociar_recepcion">
<label>{_t("portal_gest.factura_lbl", "Factura")}</label>{_select('id_factura', opts_facturas, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.id_recepcion_lbl", "ID de recepción")}</label><input type="number" name="id_recepcion" required>
<label>{_t("portal_gest.importe_eur_lbl", "Importe (€)")}</label><input type="number" step="0.01" name="importe" required>
<p><button type="submit">{_t("portal_gest.asociar_btn", "Asociar")}</button></p>
</form></div>""", nav=_nav_html(token, "gestion"))


# ── Contratos ────────────────────────────────────────────────────────────────
# "cliente" se excluye SOLO en este desplegable del portal (motor de contratos de compras/proveedores):
# `CT.TIPOS` es el catálogo general compartido con el resto de la app y no se toca.
_TIPOS_CONTRATO_OCULTOS_PORTAL = {"cliente"}


def pagina_contratos(token, contratos, vencimientos, tipos):
    base = f"/portal/empresa/{token}/gestion/contratos"
    tipos_visibles = [t for t in tipos if t not in _TIPOS_CONTRATO_OCULTOS_PORTAL]
    aviso_venc = (f'<p style="color:#FFB86C;font-weight:800">⚠️ {_t("portal_gest.contratos_vencen", "{n} contrato(s) vencen en los próximos 60 días.", n=len(vencimientos))}</p>'
                 if vencimientos else "")
    filas = "".join(f"""<tr><td>{_e(c.get('codigo') or c['id'])}</td><td>{_e(c['tipo'])}</td>
<td>{_e(c.get('contraparte') or '—')}</td><td>{_e(c.get('fecha_inicio') or '—')}</td>
<td>{_e(c.get('fecha_fin') or '—')}</td><td>{c.get('valor') or 0} €</td>
<td><span class="badge">{_e(c['estado'])}</span></td>
<td><form method="post" action="{base}/{c['id']}/renovar" style="display:inline">
<button type="submit" class="btn-ghost">{_t("portal_gest.renovar_12m_btn", "Renovar 12m")}</button></form></td></tr>""" for c in contratos)
    tabla = (f'<table><tr><th>{_t("portal_gest.col_codigo", "Código")}</th><th>{_t("portal_gest.col_tipo", "Tipo")}</th>'
            f'<th>{_t("portal_gest.col_contraparte", "Contraparte")}</th><th>{_t("portal_gest.col_inicio", "Inicio")}</th>'
            f'<th>{_t("portal_gest.col_fin", "Fin")}</th>'
            f'<th>{_t("portal_gest.col_valor", "Valor")}</th><th>{_t("portal_gest.col_estado", "Estado")}</th><th></th></tr>{filas}</table>'
            if contratos else f'<p>{_t("portal_gest.sin_contratos", "Sin contratos registrados.")}</p>')
    return _layout(_t("portal_gest.contratos_titulo", "Contratos"), f"""
{_volver_gestion(token)}
<div class="card"><h2>{_t("portal_gest.nuevo_contrato_h2", "Nuevo contrato")}</h2>
<form method="post" action="{base}/crear">
<label>{_t("portal_gest.codigo_opcional_lbl", "Código (opcional)")}</label><input type="text" name="codigo">
<label>{_t("portal_gest.col_tipo", "Tipo")}</label>{_select('tipo', [(t, t) for t in tipos_visibles])}
<label>{_t("portal_gest.col_contraparte", "Contraparte")}</label><input type="text" name="contraparte">
<label>{_t("portal_gest.fecha_inicio_lbl", "Fecha inicio")}</label><input type="text" name="fecha_inicio" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.fecha_fin_lbl", "Fecha fin")}</label><input type="text" name="fecha_fin" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.valor_eur_lbl", "Valor (€)")}</label><input type="number" step="0.01" name="valor" value="0">
<p><button type="submit">{_t("portal_gest.crear_contrato_btn", "Crear contrato")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.contratos_titulo", "Contratos")}</h2>{aviso_venc}{tabla}</div>""", nav=_nav_html(token, "gestion"))


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
    sin_datos = f'<p>{_t("portal_gest.sin_datos", "Sin datos.")}</p>'
    return _layout(_t("portal_gest.informes_titulo", "Informes"), f"""
{_volver_gestion(token)}
<div class="card"><h1>{_t("portal_gest.informes_compras_h1", "Informes de compras")}</h1>
<form method="get" action="{base}">
<label>{_t("portal_gest.desde_lbl", "Desde")}</label><input type="text" name="desde" value="{_e(desde or '')}" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.hasta_lbl", "Hasta")}</label><input type="text" name="hasta" value="{_e(hasta or '')}" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<button type="submit" class="btn-ghost">{_t("portal_gest.filtrar_btn", "Filtrar")}</button>
</form></div>
<div class="card"><h2>{_t("portal_gest.gasto_por_proveedor_h2", "Gasto por proveedor")}</h2>
{f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_facturas", "Facturas")}</th><th>{_t("portal_gest.col_total", "Total")}</th></tr>{f_prov}</table>' if por_proveedor else sin_datos}
</div>
<div class="card"><h2>{_t("portal_gest.gasto_por_periodo_h2", "Gasto por periodo")}</h2>
{f'<table><tr><th>{_t("portal_gest.col_periodo", "Periodo")}</th><th>{_t("portal_gest.col_facturas", "Facturas")}</th><th>{_t("portal_gest.col_total", "Total")}</th></tr>{f_per}</table>' if por_periodo else sin_datos}
</div>
<div class="card"><h2>{_t("portal_gest.coste_articulo_top30_h2", "Coste por artículo (top 30)")}</h2>
{f'<table><tr><th>{_t("portal_gest.col_articulo", "Artículo")}</th><th>{_t("portal_gest.col_unidades", "Unidades")}</th><th>{_t("portal_gest.col_gasto", "Gasto")}</th><th>{_t("portal_gest.col_precio_medio", "Precio medio")}</th></tr>{f_art}</table>' if por_articulo else sin_datos}
</div>
<div class="card"><h2>{_t("portal_gest.proveedores_mas_usados_h2", "Proveedores más utilizados")}</h2>
{f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_pedidos", "Pedidos")}</th><th>{_t("portal_gest.col_total", "Total")}</th></tr>{f_top}</table>' if top_proveedores else sin_datos}
</div>""", nav=_nav_html(token, "gestion"))


# ── Calidad (resumen) ────────────────────────────────────────────────────────
def pagina_calidad(token, kpis):
    return _layout(_t("portal_gest.calidad_titulo", "Calidad"), f"""
{_volver_gestion(token)}
<div class="card"><h1>{_t("portal_gest.calidad_resumen_h1", "Calidad · Resumen")}</h1>
<p>{_t("portal_gest.calidad_solo_lectura_desc",
      "Vista de solo lectura. El módulo completo de Calidad (inspecciones, no conformidades, "
      "CAPA, auditorías) se gestiona desde Smart Manager escritorio.")}</p>
<p>{_t("portal_gest.unidades_inspeccionadas_lbl", "Unidades inspeccionadas:")} <span class="badge">{kpis['unidades_inspeccionadas']}</span>
· {_t("portal_gest.unidades_rechazadas_lbl", "Unidades rechazadas:")} <span class="badge">{kpis['unidades_rechazadas']}</span>
· {_t("portal_gest.tasa_rechazo_lbl", "Tasa de rechazo:")} <span class="badge">{kpis['tasa_rechazo_pct']} %</span></p>
<p>{_t("portal_gest.nc_abiertas_lbl", "No conformidades abiertas:")} <span class="badge{' badge-ok' if not kpis['nc_abiertas'] else ''}">
{kpis['nc_abiertas']}</span> {_t("portal_gest.de_n_totales", "de {n} totales", n=kpis['nc_total'])}
· {_t("portal_gest.capa_abiertas_lbl", "CAPA abiertas:")} <span class="badge">{kpis['capa_abiertas']}</span>
· {_t("portal_gest.capa_cerradas_lbl", "CAPA cerradas:")} <span class="badge">{kpis['capa_cerradas']}</span></p>
<p>{_t("portal_gest.unidades_merma_calidad_lbl", "Unidades de merma asociadas a calidad:")} <span class="badge">{kpis['unidades_merma']}</span></p>
</div>""", nav=_nav_html(token, "gestion"))


# ── Compras Pro (recurrentes, órdenes abiertas, comparativa, aprobación) ──────
# Motor en `src.services.compras.compras_pro` — existía sin ninguna superficie (ni el job de
# generación de recurrentes tenía datos que procesar) hasta esta auditoría.
def pagina_compras_pro(token, proveedores, recurrentes, ordenes, pedidos, *, comparativa=None,
                       codigo_comparado=None, id_pedido_aprob=None, aprobado=None, mensaje=None):
    base = f"/portal/empresa/{token}/gestion/compras_pro"

    filas_rec = "".join(f"""<tr><td>{r['id']}</td><td>{_e(r.get('nombre') or '—')}</td>
<td>{_t("portal_gest.n_dias", "{n} días", n=r['frecuencia_dias'])}</td><td>{_e(r.get('proximo') or '—')}</td>
<td><span class="badge{' badge-ok' if r.get('activo') else ''}">{_t("portal_gest.activo_lbl", "activo") if r.get('activo') else _t("portal_gest.pausado_lbl", "pausado")}</span>
</td></tr>""" for r in recurrentes)
    tabla_rec = (f'<table><tr><th>ID</th><th>{_t("portal_gest.col_nombre", "Nombre")}</th>'
                f'<th>{_t("portal_gest.col_frecuencia", "Frecuencia")}</th><th>{_t("portal_gest.col_proximo", "Próximo")}</th>'
                f'<th>{_t("portal_gest.col_estado", "Estado")}</th></tr>{filas_rec}</table>' if recurrentes
                else f'<p>{_t("portal_gest.sin_recurrentes", "Sin pedidos recurrentes configurados.")}</p>')

    filas_oa = "".join(f"""<tr><td>{o['id']}</td><td>{_e(o.get('codigo_articulo'))}</td>
<td>{o['cantidad_consumida']} / {o['cantidad_total']}</td><td>{o.get('precio') or 0} €</td>
<td><span class="badge{' badge-ok' if o.get('estado') == 'abierta' else ''}">{_e(o.get('estado'))}</span></td>
<td><form method="post" action="{base}/ordenes_abiertas/{o['id']}/consumir" style="display:inline">
<input type="number" step="0.01" name="cantidad" placeholder="{_t("portal_gest.cantidad_ph", "Cantidad")}" style="min-width:100px" required>
<button type="submit" class="btn-ghost">{_t("portal_gest.consumir_btn", "Consumir")}</button></form></td></tr>""" for o in ordenes)
    tabla_oa = (f'<table><tr><th>ID</th><th>{_t("portal_gest.col_articulo", "Artículo")}</th>'
               f'<th>{_t("portal_gest.col_consumido_total", "Consumido/Total")}</th><th>{_t("portal_gest.col_precio", "Precio")}</th>'
               f'<th>{_t("portal_gest.col_estado", "Estado")}</th><th></th></tr>{filas_oa}</table>' if ordenes
               else f'<p>{_t("portal_gest.sin_ordenes_abiertas", "Sin órdenes abiertas.")}</p>')

    comp_html = ""
    if comparativa is not None:
        filas_c = "".join(f"""<tr><td>{_e(c.get('proveedor') or c['id_proveedor'])}</td>
<td>{c['precio_neto']} €</td><td>{c['valoracion']}</td><td>{c.get('lead_time_dias') or '—'}</td>
<td>{_t("portal_gest.recomendado_lbl", "⭐ recomendado") if c.get('recomendado') else ''}</td></tr>""" for c in comparativa)
        tabla_c = (f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_precio_neto", "Precio neto")}</th><th>{_t("portal_gest.col_valoracion", "Valoración")}</th>'
                  f'<th>{_t("portal_gest.col_lead_time_dias", "Lead time (días)")}</th><th></th></tr>{filas_c}</table>' if comparativa
                  else f'<p>{_t("portal_gest.sin_proveedor_precio_negociado", "Ningún proveedor tiene precio negociado vigente para ese artículo.")}</p>')
        comp_html = f"""<div class="card"><h2>{_t("portal_gest.resultado_para_h2", "Resultado para «{c}»", c=_e(codigo_comparado))}</h2>{tabla_c}</div>"""

    aprob_html = ""
    if id_pedido_aprob is not None:
        estado_aprob = (f'<span class="badge badge-ok">{_t("portal_gest.aprobado_no_requiere", "aprobado / no requiere")}</span>' if aprobado
                        else f'<span class="badge">{_t("portal_gest.pendiente_aprobacion_lbl", "pendiente de aprobación")}</span>')
        aprob_html = f"""<div class="card"><h2>{_t("portal_gest.pedido_num_h2", "Pedido #{n}", n=id_pedido_aprob)}</h2>
<p>{_t("portal_gest.estado_aprobacion_lbl", "Estado de aprobación:")} {estado_aprob}</p>
<form method="post" action="{base}/aprobacion/{id_pedido_aprob}/solicitar">
<button type="submit">{_t("portal_gest.solicitar_aprobacion_btn", "Solicitar aprobación (si supera el umbral configurado)")}</button></form></div>"""

    opts_prov = _opts_proveedores(proveedores)
    opts_ped = [(p["id_pedido"], f"#{p['id_pedido']} · {p.get('numero') or ''} ({p['total']} €)")
               for p in pedidos]
    return _layout(_t("portal_gest.pedidos_recurrentes_titulo", "Pedidos recurrentes"), f"""
{_volver_gestion(token)}
{_aviso_html(mensaje)}
<div class="card"><h2>{_t("portal_gest.nuevo_pedido_recurrente_h2", "Nuevo pedido recurrente")}</h2>
<p>{_t("portal_gest.pedido_recurrente_desc", "Genera automáticamente un pedido cada N días (job de fondo, ya activo).")}</p>
<form method="post" action="{base}/recurrentes/crear">
<label>{_t("portal_gest.col_proveedor", "Proveedor")}</label>{_select('id_proveedor', opts_prov, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.col_nombre", "Nombre")}</label><input type="text" name="nombre" placeholder="{_t("portal_gest.ej_reposicion_semanal_ph", "p. ej. Reposición semanal")}">
<label>{_t("portal_gest.frecuencia_dias_lbl", "Frecuencia (días)")}</label><input type="number" name="frecuencia_dias" value="30" min="1">
<label>{_t("portal_gest.articulo_codigo_lbl", "Artículo (código)")}</label><input type="text" name="codigo" required>
<label>{_t("portal_gest.cantidad_lbl", "Cantidad")}</label><input type="number" step="0.01" name="cantidad" required>
<label>{_t("portal_gest.precio_unitario_eur_lbl", "Precio unitario (€)")}</label><input type="number" step="0.01" name="precio" value="0">
<p><button type="submit">{_t("portal_gest.crear_recurrente_btn", "Crear recurrente")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.pedidos_recurrentes_titulo", "Pedidos recurrentes")}</h2>{tabla_rec}</div>

<div class="card"><h2>{_t("portal_gest.nueva_orden_abierta_h2", "Nueva orden abierta (blanket order)")}</h2>
<p>{_t("portal_gest.orden_abierta_desc", "Cantidad total pactada con el proveedor; se consume (call-off) en pedidos parciales.")}</p>
<form method="post" action="{base}/ordenes_abiertas/crear">
<label>{_t("portal_gest.col_proveedor", "Proveedor")}</label>{_select('id_proveedor', opts_prov, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.articulo_codigo_lbl", "Artículo (código)")}</label><input type="text" name="codigo" required>
<label>{_t("portal_gest.cantidad_total_lbl", "Cantidad total")}</label><input type="number" step="0.01" name="cantidad_total" required>
<label>{_t("portal_gest.precio_unitario_eur_lbl", "Precio unitario (€)")}</label><input type="number" step="0.01" name="precio" value="0">
<label>{_t("portal_gest.fecha_inicio_lbl", "Fecha inicio")}</label><input type="text" name="fecha_inicio" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.fecha_fin_lbl", "Fecha fin")}</label><input type="text" name="fecha_fin" data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.referencia_lbl", "Referencia")}</label><input type="text" name="referencia">
<p><button type="submit">{_t("portal_gest.crear_orden_abierta_btn", "Crear orden abierta")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.ordenes_abiertas_h2", "Órdenes abiertas")}</h2>{tabla_oa}</div>

<div class="card"><h2>{_t("portal_gest.comparativa_proveedores_h2", "Comparativa de proveedores por artículo")}</h2>
<p>{_t("portal_gest.comparativa_desc", "Compara precio negociado, valoración y lead time de los proveedores que ofrecen un artículo.")}</p>
<form method="get" action="{base}">
<input type="hidden" name="ver" value="comparativa">
<input type="text" name="codigo" placeholder="{_t("portal_gest.codigo_articulo_ph", "Código de artículo")}" value="{_e(codigo_comparado or '')}" required>
<button type="submit">{_t("portal_gest.comparar_btn", "Comparar")}</button></form></div>
{comp_html}

<div class="card"><h2>{_t("portal_gest.aprobacion_pedidos_h2", "Aprobación de pedidos")}</h2>
<p>{_t("portal_gest.aprobacion_desc", "Los pedidos que superan el umbral configurado requieren aprobación (circuito de Workflow).")}</p>
<form method="get" action="{base}">
<input type="hidden" name="ver" value="aprobacion">
{_select('id_pedido', opts_ped, vacio=_t('portal_gest.selecciona_pedido_opt', 'Selecciona un pedido…'))}
<button type="submit">{_t("portal_gest.ver_estado_btn", "Ver estado")}</button></form></div>
{aprob_html}""", nav=_nav_html(token, "gestion"))


# ── Rappels acumulados (Smart Suppliers B2B · Punto 1) ────────────────────────
# Motor en `src.services.compras.b2b_rappels`. Rebate RETROACTIVO sobre el gasto acumulado con un
# proveedor en una ventana de fechas — DISTINTO de los "Precios por volumen" (b2b_catalogo_escalones)
# que el proveedor gestiona en su propio catálogo (descuento por cantidad EN el pedido, no un rebate
# periódico sobre el conjunto de pedidos ya facturados). Solo la Empresa configura tramos; el
# Proveedor ve su progreso en modo solo-lectura (Portal Proveedor).
def _barra_rappel_html(prog):
    if not prog.get("tiene_tramos"):
        return f'<p>{_t("portal_gest.sin_tramos_proveedor", "Sin tramos configurados para este proveedor.")}</p>'
    tramo = prog.get("tramo_alcanzado")
    siguiente = prog.get("siguiente_tramo")
    detalle_tramo = (_t("portal_gest.tramo_alcanzado_detalle",
                       "Tramo alcanzado: desde {d} € → {p} % (rebate estimado {r} €, aún no liquidado)",
                       d=tramo['umbral_desde'], p=tramo['pct_rebate'], r=prog['rebate_estimado']) if tramo
                     else _t("portal_gest.ningun_tramo_alcanzado", "Ningún tramo alcanzado todavía."))
    detalle_siguiente = (" · " + _t("portal_gest.proximo_tramo_detalle", "Próximo tramo: desde {d} € → {p} %",
                                    d=siguiente['umbral_desde'], p=siguiente['pct_rebate']) if siguiente else "")
    return f"""<p>{_t("portal_gest.ventana_gasto_validado", "Ventana {ini} → {fin} · Gasto acumulado validado:",
                      ini=_e(prog['fecha_inicio']), fin=_e(prog['fecha_fin']))} <b>{prog['gasto_acumulado']} €</b></p>
<div class="progreso"><div class="progreso-barra" style="width:{prog['pct_barra']}%;background:var(--ac)"></div></div>
<p>{detalle_tramo}{detalle_siguiente}</p>"""


def pagina_rappels(token, proveedores, tramos_por_sum, progresos, liquidaciones, nombres_sum, *,
                   mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/rappels"
    aviso = _aviso_html(mensaje, error)

    bloques = []
    for sid, prog in progresos.items():
        bloques.append(f"""<div class="card"><h2>{_e(nombres_sum.get(sid, _t('portal_gest.proveedor_numero', 'Proveedor #{n}', n=sid)))}</h2>
{_barra_rappel_html(prog)}
<form method="post" action="{base}/liquidar" class="inline">
<input type="hidden" name="id_suministrador" value="{sid}">
<input type="text" name="fecha_inicio" value="{_e(prog.get('fecha_inicio') or '')}" required
data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<input type="text" name="fecha_fin" value="{_e(prog.get('fecha_fin') or '')}" required
data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<button type="submit" class="btn-ghost">{_t("portal_gest.liquidar_ahora_btn", "Liquidar ahora")}</button>
</form></div>""")
    progreso_html = "".join(bloques) or f'<p>{_t("portal_gest.sin_tramos_rappel_ningun_proveedor", "Ningún proveedor tiene tramos de rappel configurados todavía.")}</p>'

    filas_tramos = []
    for sid, ts in tramos_por_sum.items():
        for t in ts:
            filas_tramos.append(f"""<tr><td>{_e(nombres_sum.get(sid, sid))}</td>
<td>{t['umbral_desde']} €</td><td>{t['pct_rebate']} %</td>
<td>{_e(t['fecha_inicio'])} → {_e(t['fecha_fin'])}</td>
<td><span class="badge{' badge-ok' if t['estado'] == 'activo' else ''}">{_e(t['estado'])}</span></td>
</tr>""")
    tabla_tramos = (f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_umbral_desde", "Umbral desde")}</th><th>{_t("portal_gest.col_pct_rebate", "% Rebate")}</th>'
                    f'<th>{_t("portal_gest.col_vigencia", "Vigencia")}</th><th>{_t("portal_gest.col_estado", "Estado")}</th></tr>{"".join(filas_tramos)}</table>'
                    if filas_tramos else f'<p>{_t("portal_gest.sin_tramos_config", "Sin tramos configurados.")}</p>')

    filas_liq = "".join(f"""<tr><td>{_e(nombres_sum.get(l['id_suministrador'], l['id_suministrador']))}</td>
<td>{_e(l['fecha_inicio'])} → {_e(l['fecha_fin'])}</td><td>{l['gasto_total']} €</td>
<td>{l['pct_aplicado']} %</td><td>{l['importe_rebate']} €</td>
<td>{('#' + str(l['id_factura_abono'])) if l['id_factura_abono'] else '—'}</td></tr>"""
                       for l in liquidaciones)
    tabla_liq = (f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_ventana", "Ventana")}</th><th>{_t("portal_gest.col_gasto", "Gasto")}</th><th>{_t("portal_gest.col_pct_aplicado", "% Aplicado")}</th>'
                f'<th>{_t("portal_gest.col_rebate", "Rebate")}</th><th>{_t("portal_gest.col_abono", "Abono")}</th></tr>{filas_liq}</table>' if liquidaciones
                else f'<p>{_t("portal_gest.sin_liquidaciones", "Sin liquidaciones registradas todavía.")}</p>')

    opts_sum = [(p["id_suministrador"], f"{p['razon_social']} ({p.get('cif_nif') or 's/CIF'})")
               for p in proveedores]

    return _layout(_t("portal_gest.rappels_titulo", "Rappels"), f"""
{_volver_gestion(token)}
<h1>{_t("portal_gest.rappels_acumulados_h1", "Rappels acumulados")}</h1>
{aviso}
<div class="card"><h2>{_t("portal_gest.nuevo_tramo_h2", "Nuevo tramo")}</h2>
<form method="post" action="{base}/tramos/crear">
<label>{_t("portal_gest.proveedor_b2b_lbl", "Proveedor (con acceso B2B)")}</label>{_select('id_suministrador', opts_sum, vacio=_t('portal_gest.selecciona_ph', 'Selecciona…'))}
<label>{_t("portal_gest.umbral_gasto_desde_lbl", "Umbral de gasto acumulado desde (€)")}</label>
<input type="number" step="0.01" name="umbral_desde" min="0.01" required>
<label>{_t("portal_gest.pct_rebate_retroactivo_lbl", "% de rebate retroactivo")}</label>
<input type="number" step="0.01" name="pct_rebate" min="0.01" max="100" required>
<label>{_t("portal_gest.vigencia_desde_lbl", "Vigencia del acuerdo — desde")}</label><input type="text" name="fecha_inicio" required
data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.vigencia_hasta_lbl", "Vigencia del acuerdo — hasta")}</label><input type="text" name="fecha_fin" required
data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<p><button type="submit">{_t("portal_gest.crear_tramo_btn", "Crear tramo")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.progreso_por_proveedor_h2", "Progreso por proveedor")}</h2>{progreso_html}</div>
<div class="card"><h2>{_t("portal_gest.tramos_configurados_h2", "Tramos configurados")}</h2>{tabla_tramos}</div>
<div class="card"><h2>{_t("portal_gest.liquidaciones_h2", "Liquidaciones")}</h2>{tabla_liq}</div>""", nav=_nav_html(token, "gestion"))


def _etiqueta_rfq_t(estado):
    return _t(f"portal_gest.rfq_estado_{estado}", _ETIQUETA_ESTADO_RFQ.get(estado, estado))


# ── Licitaciones / subastas inversas (RFQ) (Smart Suppliers B2B · Punto 2) ────
# Motor en `src.services.compras.b2b_rfq`. La empresa pide precio a sus proveedores homologados; ganan
# la puja más barata; al cierre (manual o por vencimiento del temporizador vía job programado) se
# convierte en un Pedido B2B real por el mismo camino que un pedido tramitado desde el carrito.
_ETIQUETA_ESTADO_RFQ = {"abierta": "Abierta", "cerrada": "Cerrada (sin ofertas)",
                        "adjudicada": "Adjudicada", "cancelada": "Cancelada"}
_UNIDADES_RFQ = (("unidad", "Unidades"), ("kg", "Kilos"), ("pale", "Palés"), ("caja", "Cajas"))


def pagina_licitaciones(token, rfqs, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/licitaciones"
    aviso = _aviso_html(mensaje, error)

    filas = "".join(f"""<tr><td>{_e((r.get('codigo_articulo') or r.get('categoria') or '—'))}</td>
<td>{r['cantidad']} {_e(r['unidad_medida'])}</td>
<td>{_e(r['fecha_cierre_subasta'])}</td>
<td><span class="badge{' badge-ok' if r['estado'] == 'adjudicada' else ''}">
{_e(_etiqueta_rfq_t(r['estado']))}</span></td>
<td><a class="enlace" href="{base}/{r['id_rfq']}">{_t("portal_gest.ver_gestionar_link", "Ver / gestionar")}</a></td></tr>"""
                     for r in rfqs)
    tabla = (f'<table><tr><th>{_t("portal_gest.col_que_se_pide", "Qué se pide")}</th><th>{_t("portal_gest.col_cantidad", "Cantidad")}</th><th>{_t("portal_gest.col_cierre_subasta", "Cierre de la subasta")}</th>'
            f'<th>{_t("portal_gest.col_estado", "Estado")}</th><th></th></tr>{filas}</table>' if rfqs
            else f'<p>{_t("portal_gest.sin_licitaciones", "No hay licitaciones creadas todavía.")}</p>')

    return _layout(_t("portal_gest.licitaciones_titulo", "Licitaciones"), f"""
{_volver_gestion(token)}
<div class="card"><h1>{_t("portal_gest.licitaciones_h1", "Licitaciones (subastas inversas)")}</h1>
<p>{_t("portal_gest.licitaciones_desc",
      "Pide precio a tus proveedores homologados para un artículo o una categoría: cada proveedor "
      "puja <b>a ciegas</b> (nunca ve la oferta de los demás). Al cierre de la subasta —manual "
      "desde aquí, o automático al vencer el plazo— la mejor oferta se convierte en un <b>Pedido "
      "B2B real</b>, con la misma custodia de fondos y ciclo de estados que cualquier otro pedido.")}</p>
{aviso}
</div>
<div class="card"><h2>{_t("portal_gest.nueva_licitacion_h2", "Nueva licitación")}</h2>
<form method="post" action="{base}">
<label>{_t("portal_gest.codigo_articulo_opc_lbl", "Código de artículo (opcional si indicas categoría)")}</label><input name="codigo_articulo">
<label>{_t("portal_gest.categoria_opc_lbl", "Categoría (opcional si indicas artículo)")}</label><input name="categoria">
<label>{_t("portal_gest.cantidad_req_lbl", "Cantidad *")}</label><input type="number" step="0.001" min="0.001" name="cantidad" required>
<label>{_t("portal_gest.unidad_medida_req_lbl", "Unidad de medida *")}</label>{_select('unidad_medida', list(_UNIDADES_RFQ), seleccionado='unidad')}
<label>{_t("portal_gest.fecha_limite_entrega_lbl", "Fecha límite de entrega deseada")}</label><input type="text" name="fecha_limite_entrega"
data-cdate-tipo="date" placeholder="dd/mm/aaaa">
<label>{_t("portal_gest.cierre_subasta_req_lbl", "Cierre de la subasta (fecha y hora) *")}</label>
<input type="text" name="fecha_cierre_subasta" required data-cdate-tipo="datetime-local"
placeholder="dd/mm/aaaa --:--">
<p><button type="submit">{_t("portal_gest.crear_licitacion_btn", "Crear licitación")}</button></p>
</form></div>
<div class="card"><h2>{_t("portal_gest.tus_licitaciones_h2", "Tus licitaciones")}</h2>{tabla}</div>""", nav=_nav_html(token, "gestion"))


def pagina_licitacion_detalle(token, rfq, ofertas, *, mensaje=None, error=None):
    base = f"/portal/empresa/{token}/gestion/licitaciones/{rfq['id_rfq']}"
    aviso = _aviso_html(mensaje, error)
    abierta = rfq["estado"] == "abierta"

    filas = []
    for o in ofertas:
        badge_estado = {"ganadora": " badge-ok", "rechazada": "", "activa": ""}.get(o["estado"], "")
        accion = (f"""<form method="post" action="{base}/adjudicar" class="inline">
<input type="hidden" name="id_suministrador" value="{o['id_suministrador']}">
<button type="submit" onclick="return confirm('{_t("portal_gest.confirmar_adjudicar_js", "¿Adjudicar esta oferta y generar el Pedido B2B?")}')">
{_t("portal_gest.adjudicar_btn", "Adjudicar")}</button></form>""" if abierta and o["estado"] == "activa" else "—")
        valoracion = (f"{o['valoracion_global']}" if o.get("valoracion_global") is not None else "—")
        filas.append(f"""<tr><td>{_e(o['proveedor'])}</td><td>{o['precio_unitario']} €</td>
<td>{o.get('moq') if o.get('moq') is not None else '—'}</td>
<td>{_t("portal_gest.n_dias", "{n} días", n=(o.get('plazo_entrega_dias') or '—'))}</td><td>{valoracion}</td>
<td><span class="badge{badge_estado}">{_e(o['estado'])}</span></td><td>{accion}</td></tr>""")
    tabla = (f'<table><tr><th>{_t("portal_gest.col_proveedor", "Proveedor")}</th><th>{_t("portal_gest.col_precio_unitario", "Precio unitario")}</th><th>MOQ</th><th>{_t("portal_gest.col_plazo_entrega", "Plazo entrega")}</th>'
            f'<th>{_t("portal_gest.col_evaluacion", "Evaluación")}</th><th>{_t("portal_gest.col_estado", "Estado")}</th><th></th></tr>{"".join(filas)}</table>' if ofertas
            else f'<p>{_t("portal_gest.ningun_proveedor_pujado", "Ningún proveedor ha pujado todavía.")}</p>')

    return _layout(_t("portal_gest.licitacion_titulo", "Licitación"), f"""
<div class="card"><h1>{_e(rfq.get('codigo_articulo') or rfq.get('categoria') or '—')}</h1>
<p>{_t("portal_gest.cantidad_lbl2", "Cantidad:")} <b>{rfq['cantidad']} {_e(rfq['unidad_medida'])}</b> · {_t("portal_gest.entrega_deseada_lbl", "Entrega deseada:")}
{_e(rfq.get('fecha_limite_entrega') or 's/f')} · {_t("portal_gest.estado_lbl", "Estado:")}
<span class="badge{' badge-ok' if rfq['estado'] == 'adjudicada' else ''}">
{_e(_etiqueta_rfq_t(rfq['estado']))}</span></p>
<p>{_t("portal_gest.cierre_subasta_lbl", "Cierre de la subasta:")} <b id="rfq-cierre" data-cierre="{_e(rfq['fecha_cierre_subasta'])}">
{_e(rfq['fecha_cierre_subasta'])}</b> — <span id="rfq-cuenta-atras">{_t("portal_gest.calculando_lbl", "calculando…")}</span></p>
{aviso}
</div>
<div class="card"><h2>{_t("portal_gest.ofertas_recibidas_h2", "Ofertas recibidas (ordenadas por precio)")}</h2>{tabla}</div>
<script>
(function(){{
 var el = document.getElementById('rfq-cierre');
 var out = document.getElementById('rfq-cuenta-atras');
 if(!el || !out) return;
 var cierre = new Date(el.getAttribute('data-cierre').replace(' ', 'T'));
 function tick(){{
  var ms = cierre.getTime() - Date.now();
  if(isNaN(ms)){{ out.textContent = ''; return; }}
  if(ms <= 0){{ out.textContent = {json.dumps(_t("portal_gest.subasta_vencida_js", "Subasta vencida — pendiente de cierre automático."))}; return; }}
  var s = Math.floor(ms/1000), d = Math.floor(s/86400), h = Math.floor((s%86400)/3600),
      m = Math.floor((s%3600)/60), sg = s%60;
  out.textContent = {json.dumps(_t("portal_gest.quedan_js", "Quedan "))} + (d ? d + 'd ' : '') + h + 'h ' + m + 'm ' + sg + 's';
  setTimeout(tick, 1000);
 }}
 tick();
}})();
</script>""", nav=_nav_html(token, "gestion"))


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
        # `g.id_empresa`: mismo criterio que `portal_empresa_b2b._sesion_o_error` (comparten
        # `_layout`) — así esta sección también queda temizada por empresa.
        try:
            from flask import g
            g.id_empresa = ses.get("id_empresa")
        except Exception:
            pass
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

    # ── Alta artículo ──
    @bp.get("/<token>/gestion/alta_articulo")
    def alta_articulo(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        resultado = None
        codigo_creado = request.args.get("creado")
        if codigo_creado:
            from src.db.conexion import obtener_articulo
            from src.db import equivalencias_proveedor as EQ
            art = obtener_articulo(codigo_creado, id_empresa=ses["id_empresa"])
            if art:
                equiv = EQ.listar_equivalencias_de_articulo(codigo_creado, id_empresa=ses["id_empresa"])
                resultado = {
                    "codigo": art.get("codigo"), "nombre": art.get("nombre"),
                    "equivalencia_creada": bool(equiv),
                    "etiqueta_generada": request.args.get("etq") in ("1", "2"),
                    "etiqueta_impresa": request.args.get("etq") == "2",
                }
        vincular = None
        if request.args.get("vincular_a"):
            from src.db.conexion import obtener_articulo
            art_existente = obtener_articulo(request.args.get("vincular_a"), id_empresa=ses["id_empresa"])
            vincular = {
                "codigo_existente": request.args.get("vincular_a"),
                "nombre_existente": (art_existente or {}).get("nombre"),
                "id_proveedor": request.args.get("id_proveedor"),
                "id_suministrador": request.args.get("id_suministrador"),
                "nombre_proveedor": request.args.get("nombre_proveedor"),
                "referencia_proveedor": request.args.get("referencia_proveedor"),
            }
        busqueda = request.args.get("buscar")
        resultados_busqueda = None
        if busqueda:
            from src.db import equivalencias_proveedor as EQB
            resultados_busqueda = EQB.buscar_unificado(busqueda, id_empresa=ses["id_empresa"])
        return pagina_alta_articulo(token, mensaje=request.args.get("mensaje"),
                                    error=request.args.get("error"), resultado=resultado,
                                    proveedores=_proveedores(ses), vincular=vincular,
                                    busqueda=busqueda, resultados_busqueda=resultados_busqueda)

    @bp.post("/<token>/gestion/alta_articulo/vincular")
    def alta_articulo_vincular(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        base = f"/portal/empresa/{token}/gestion/alta_articulo"
        codigo_existente = (request.form.get("codigo_existente") or "").strip()
        referencia_proveedor = (request.form.get("referencia_proveedor") or "").strip()
        if not codigo_existente or not referencia_proveedor:
            from urllib.parse import quote
            return redirect(f"{base}?error={quote('Datos incompletos para vincular.')}")
        from src.db import equivalencias_proveedor as EQ
        # Dos universos de proveedor posibles (ver `equivalencias_proveedor.py`): el directorio
        # clásico (`id_proveedor`) o un suministrador de Smart Suppliers B2B (`id_suministrador`,
        # llega aquí cuando la vinculación se originó en la detección de duplicados del Catálogo
        # B2B, ver `portal_empresa_b2b.py::pagina_confirmar_duplicado`).
        id_proveedor = request.form.get("id_proveedor") or None
        id_suministrador = request.form.get("id_suministrador") or None
        if id_suministrador:
            id_prov_final, origen, nombre_prov = int(id_suministrador), "b2b", request.form.get("nombre_proveedor")
        else:
            nombres_prov = _nombres_proveedor(ses)
            id_prov_final = int(id_proveedor) if id_proveedor else None
            origen = "clasico"
            nombre_prov = nombres_prov.get(id_prov_final) if id_prov_final else None
        res_eq = EQ.crear_equivalencia(
            referencia_proveedor, codigo_existente, id_proveedor=id_prov_final,
            origen_proveedor=origen, nombre_proveedor=nombre_prov,
            creado_por=ses.get("usuario"), id_empresa=ses["id_empresa"])
        if not res_eq.get("ok"):
            from urllib.parse import quote
            return redirect(f"{base}?error={quote('No se pudo crear la equivalencia.')}")
        return redirect(f"{base}?creado={codigo_existente}&etq=0")

    @bp.post("/<token>/gestion/alta_articulo/crear")
    def alta_articulo_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        base = f"/portal/empresa/{token}/gestion/alta_articulo"

        def _volver_error(msg):
            from urllib.parse import quote
            return redirect(f"{base}?error={quote(msg)}")

        nombre = (request.form.get("nombre") or "").strip()
        if not nombre:
            return _volver_error("El nombre es obligatorio.")
        try:
            precio = float((request.form.get("precio") or "0").replace(",", "."))
        except ValueError:
            return _volver_error("El precio no es válido.")
        seccion = (request.form.get("seccion") or "").strip() or None
        marca = (request.form.get("marca") or "").strip() or None
        talla = (request.form.get("talla") or "").strip() or None
        color = (request.form.get("color") or "").strip() or None
        id_proveedor = request.form.get("id_proveedor") or None
        referencia_proveedor = (request.form.get("referencia_proveedor") or "").strip() or None
        es_complementario = request.form.get("es_complementario") == "on"
        es_promocional = request.form.get("es_promocional") == "on"

        from src.db import articulos as A
        from src.utils import ean
        id_empresa = ses["id_empresa"]

        # Generador de EAN-13 ÚNICO reutilizado tal cual (petición explícita: "sin crear motores
        # paralelos") — el MISMO motor que usaba la antigua pestaña "Alta artículo" del escritorio.
        codigo = ean.generar(existe_fn=lambda c: A.existe_codigo(c, id_empresa))
        if not codigo:
            return _volver_error("No se pudo generar un código EAN-13 único. Inténtalo de nuevo.")

        ok = A.crear_articulo(codigo, nombre, precio=precio, categoria=seccion, unidad="unidad",
                              marca=marca, seccion=seccion, es_complementario=es_complementario,
                              es_promocional=es_promocional, id_empresa=id_empresa)
        if not ok:
            return _volver_error("No se pudo crear el artículo.")

        if talla or color:
            try:
                from src.db.conexion import obtener_conexion as _oc
                with _oc() as conn, conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO producto_variantes (id_empresa, codigo_padre, codigo_variante, "
                        "talla, color) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, codigo, codigo, talla, color))
                    conn.commit()
            except Exception as e:
                logger.warning(f"alta_articulo_crear: no se pudo registrar talla/color ({codigo}): {e}")

        equivalencia_creada = False
        if id_proveedor and referencia_proveedor:
            from src.db import equivalencias_proveedor as EQ
            nombres_prov = _nombres_proveedor(ses)
            res_eq = EQ.crear_equivalencia(
                referencia_proveedor, codigo, id_proveedor=int(id_proveedor), origen_proveedor="clasico",
                nombre_proveedor=nombres_prov.get(int(id_proveedor)), creado_por=ses.get("usuario"),
                id_empresa=id_empresa)
            equivalencia_creada = bool(res_eq.get("ok"))

        # Reetiquetado automático (ref. interna + PVP + sección) — petición explícita: "el ERP debe
        # conectar con una impresora de etiquetas configurada e imprimir automáticamente". Reutiliza
        # el motor de etiquetas YA EXISTENTE (`services.etiquetas.pdf.GeneradorEtiquetas`), extendido
        # con el campo `seccion` (antes solo tenía codigo/nombre/precio).
        etq_flag = "0"
        try:
            from src.services.etiquetas import impresion as IMPR
            res_impr = IMPR.generar_e_imprimir_etiqueta(codigo, nombre, precio, seccion=seccion,
                                                        id_empresa=id_empresa, id_tienda=ses.get("id_tienda"),
                                                        usuario=ses.get("usuario"))
            if res_impr.get("ok"):
                etq_flag = "2" if res_impr.get("impresa") else "1"
        except Exception as e:
            logger.warning(f"alta_articulo_crear: no se pudo generar/imprimir la etiqueta ({codigo}): {e}")

        return redirect(f"{base}?creado={codigo}&etq={etq_flag}")

    @bp.post("/<token>/gestion/alta_articulo/impresora")
    def alta_articulo_impresora(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        base = f"/portal/empresa/{token}/gestion/alta_articulo"
        from src.services.etiquetas import impresion as IMPR
        IMPR.configurar_impresora_etiquetas(request.form.get("nombre_impresora"))
        from urllib.parse import quote
        return redirect(f"{base}?mensaje={quote('Impresora de etiquetas actualizada.')}")

    @bp.post("/<token>/gestion/alta_articulo/<codigo>/flag")
    def alta_articulo_flag(token, codigo):
        """Marca/desmarca un artículo YA REGISTRADO como complementario/promocional (petición
        explícita: "asignar a los artículos registrados"), desde la propia tabla de resultados de
        «Buscar artículo» — sin crear ninguna pantalla nueva, reutiliza `db.articulos.
        actualizar_articulo` (whitelist ya ampliada con estas dos columnas)."""
        ses, err = _sesion_o_error(token)
        if err:
            return err
        base = f"/portal/empresa/{token}/gestion/alta_articulo"
        campo = request.form.get("campo")
        valor = request.form.get("valor") == "1"
        buscar = request.form.get("buscar") or ""
        from urllib.parse import quote
        if campo not in ("es_complementario", "es_promocional"):
            return redirect(f"{base}?buscar={quote(buscar)}&error={quote('Campo no válido.')}")
        from src.db import articulos as A
        ok = A.actualizar_articulo(codigo, id_empresa=ses["id_empresa"], **{campo: valor})
        if not ok:
            return redirect(f"{base}?buscar={quote(buscar)}&error={quote('No se pudo actualizar el artículo.')}")
        return redirect(f"{base}?buscar={quote(buscar)}")

    # ── Equivalencias de un artículo (reversibilidad, petición explícita) ──
    @bp.get("/<token>/gestion/alta_articulo/equivalencias/<codigo>")
    def alta_articulo_equivalencias(token, codigo):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db.conexion import obtener_articulo
        from src.db import articulos as A
        from src.db import equivalencias_proveedor as EQ
        art = obtener_articulo(codigo, id_empresa=ses["id_empresa"])
        if not art:
            return _pagina_error(
                _t("portal_gest.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                _t("articulos.no_existe_sistema", A.MENSAJE_CODIGO_NO_EXISTE))
        equiv = EQ.listar_equivalencias_de_articulo(codigo, id_empresa=ses["id_empresa"],
                                                     incluir_deshechas=True)
        return pagina_equivalencias_articulo(token, codigo, art.get("nombre"), equiv,
                                             mensaje=request.args.get("mensaje"),
                                             error=request.args.get("error"))

    @bp.post("/<token>/gestion/alta_articulo/equivalencias/<codigo>/<int:id_equiv>/deshacer")
    def alta_articulo_equivalencia_deshacer(token, codigo, id_equiv):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import equivalencias_proveedor as EQ
        from urllib.parse import quote
        base = f"/portal/empresa/{token}/gestion/alta_articulo/equivalencias/{codigo}"
        ok = EQ.deshacer_equivalencia(id_equiv, id_empresa=ses["id_empresa"])
        msg = "mensaje=" + quote("Equivalencia deshecha.") if ok else "error=" + quote("No se pudo deshacer la equivalencia.")
        return redirect(f"{base}?{msg}")

    @bp.post("/<token>/gestion/alta_articulo/equivalencias/<codigo>/<int:id_equiv>/reactivar")
    def alta_articulo_equivalencia_reactivar(token, codigo, id_equiv):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import equivalencias_proveedor as EQ
        from urllib.parse import quote
        base = f"/portal/empresa/{token}/gestion/alta_articulo/equivalencias/{codigo}"
        ok = EQ.reactivar_equivalencia(id_equiv, id_empresa=ses["id_empresa"])
        msg = "mensaje=" + quote("Equivalencia reactivada.") if ok else "error=" + quote("No se pudo reactivar la equivalencia.")
        return redirect(f"{base}?{msg}")

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
        id_proveedor = request.args.get("id_proveedor")
        contactos = direcciones = certificaciones = acuerdos = tarifas = None
        if id_proveedor:
            id_proveedor = int(id_proveedor)
            from src.db import proveedores as P
            from src.services.compras import proveedores_pro as PP
            contactos = P.listar_contactos(id_proveedor)
            direcciones = P.listar_direcciones(id_proveedor)
            certificaciones = PP.certificaciones(id_proveedor, id_empresa=ses["id_empresa"])
            acuerdos = PP.acuerdos_marco(id_proveedor, id_empresa=ses["id_empresa"])
            tarifas = PP.listar_tarifas_proveedor(id_proveedor, id_empresa=ses["id_empresa"])
        return pagina_homologacion(token, provs, estados_kyb=estados_kyb, id_proveedor=id_proveedor,
                                   contactos=contactos, direcciones=direcciones,
                                   certificaciones=certificaciones, acuerdos=acuerdos, tarifas=tarifas)

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/contactos/agregar")
    def homologacion_contacto_agregar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import proveedores as P
        nombre = (request.form.get("nombre") or "").strip()
        if nombre:
            P.agregar_contacto(id_proveedor, nombre, cargo=(request.form.get("cargo") or "").strip() or None,
                               email=(request.form.get("email") or "").strip() or None,
                               telefono=(request.form.get("telefono") or "").strip() or None)
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/direcciones/agregar")
    def homologacion_direccion_agregar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import proveedores as P
        P.agregar_direccion(id_proveedor, direccion=(request.form.get("direccion") or "").strip() or None,
                            tipo=request.form.get("tipo") or "fiscal",
                            cp=(request.form.get("cp") or "").strip() or None,
                            municipio=(request.form.get("municipio") or "").strip() or None,
                            provincia=(request.form.get("provincia") or "").strip() or None,
                            pais=(request.form.get("pais") or "").strip() or "España")
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/certificaciones/agregar")
    def homologacion_certificacion_agregar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import proveedores_pro as PP
        tipo = (request.form.get("tipo") or "").strip()
        if tipo:
            PP.añadir_certificacion(id_proveedor, tipo, numero=(request.form.get("numero") or "").strip() or None,
                                    emisor=(request.form.get("emisor") or "").strip() or None,
                                    fecha_caducidad=(request.form.get("fecha_caducidad") or "").strip() or None,
                                    id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/acuerdos/agregar")
    def homologacion_acuerdo_agregar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import proveedores_pro as PP
        try:
            importe = float(request.form.get("importe_comprometido") or 0)
        except ValueError:
            importe = 0.0
        PP.crear_acuerdo_marco(id_proveedor, referencia=(request.form.get("referencia") or "").strip() or None,
                               fecha_inicio=(request.form.get("fecha_inicio") or "").strip() or None,
                               fecha_fin=(request.form.get("fecha_fin") or "").strip() or None,
                               importe_comprometido=importe, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/tarifas/agregar")
    def homologacion_tarifa_agregar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import proveedores_pro as PP
        codigo = (request.form.get("codigo") or "").strip()
        try:
            precio = float(request.form.get("precio") or 0)
            descuento = float(request.form.get("descuento") or 0)
        except ValueError:
            return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")
        if codigo and precio > 0:
            PP.set_precio_negociado(id_proveedor, codigo, precio, descuento=descuento,
                                    unidad_medida=request.form.get("unidad_medida") or "unidad",
                                    id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/tarifas/<int:id_tarifa>/eliminar")
    def homologacion_tarifa_eliminar(token, id_proveedor, id_tarifa):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import proveedores_pro as PP
        PP.eliminar_tarifa(id_tarifa, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

    @bp.post("/<token>/gestion/homologacion/<int:id_proveedor>/tarifas/importar")
    def homologacion_tarifas_importar(token, id_proveedor):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        f = request.files.get("archivo")
        if not f or not f.filename:
            return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")
        import os
        import tempfile
        from src.services.compras import proveedores_pro as PP
        _, ext = os.path.splitext(f.filename)
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        try:
            f.save(tmp.name)
            tmp.close()
            PP.importar_tarifas_proveedor(id_proveedor, tmp.name, id_empresa=ses["id_empresa"])
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return redirect(f"/portal/empresa/{token}/gestion/homologacion?id_proveedor={id_proveedor}")

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
        recs = C.listar_recepciones(id_pedido, ses["id_empresa"])
        landed_por_recepcion = {r["id_recepcion"]: C.resumen_costes_landed(
            id_recepcion=r["id_recepcion"], id_empresa=ses["id_empresa"]) for r in recs}
        return pagina_recepcion_detalle(token, ped, nombre, recepciones=recs,
                                        landed_por_recepcion=landed_por_recepcion)

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

    @bp.post("/<token>/gestion/recepciones/<int:id_pedido>/costes_extra")
    def recepcion_coste_extra(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_recepcion = request.form.get("id_recepcion") or None
        try:
            importe = float(request.form.get("importe") or 0)
        except ValueError:
            importe = 0.0
        if importe > 0:
            C.registrar_coste_extra(request.form.get("tipo") or "otros", importe,
                                    id_recepcion=(int(id_recepcion) if id_recepcion else None),
                                    id_pedido=id_pedido,
                                    metodo_prorrateo=request.form.get("metodo_prorrateo") or "cantidad",
                                    descripcion=(request.form.get("descripcion") or "").strip() or None,
                                    id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/recepciones/{id_pedido}")

    @bp.post("/<token>/gestion/recepciones/<int:id_pedido>/prorratear")
    def recepcion_prorratear(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_recepcion = request.form.get("id_recepcion")
        if id_recepcion:
            C.prorratear_costes_recepcion(id_recepcion=int(id_recepcion), id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/recepciones/{id_pedido}")

    # ── Costes extra B2B (Landed Cost, Fase B) ──
    @bp.get("/<token>/gestion/b2b/<id_tx>")
    def b2b_costes_extra(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        from src.services.comercio_digital import transacciones as TX
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error("Coste landed B2B", "Pedido B2B no encontrado."), 404
        provs = [p for p in _proveedores(ses) if p.get("id_suministrador")]
        nombres_sum = {p["id_suministrador"]: p["razon_social"] for p in provs}
        nombre = nombres_sum.get(tx.get("id_suministrador"), str(tx.get("id_suministrador")))
        landed = C.resumen_costes_landed(id_tx=id_tx, id_empresa=ses["id_empresa"])
        return pagina_costes_extra_b2b(token, tx, nombre, landed)

    @bp.post("/<token>/gestion/b2b/<id_tx>/costes_extra")
    def b2b_costes_extra_registrar(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        try:
            importe = float(request.form.get("importe") or 0)
        except ValueError:
            importe = 0.0
        if importe > 0:
            C.registrar_coste_extra(request.form.get("tipo") or "otros", importe, id_tx=id_tx,
                                    metodo_prorrateo=request.form.get("metodo_prorrateo") or "cantidad",
                                    descripcion=(request.form.get("descripcion") or "").strip() or None,
                                    id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/b2b/{id_tx}")

    @bp.post("/<token>/gestion/b2b/<id_tx>/prorratear")
    def b2b_costes_extra_prorratear(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        C.prorratear_costes_recepcion(id_tx=id_tx, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/b2b/{id_tx}")

    # ── Facturas ──
    @bp.get("/<token>/gestion/facturas")
    def facturas(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C, pagos_proveedor as PP
        facs = C.listar_facturas(id_empresa=ses["id_empresa"])
        pedidos = C.listar_pedidos(id_empresa=ses["id_empresa"])
        saldos = {f["id_factura"]: PP.saldo_pendiente(f["id_factura"], f["total"], ses["id_empresa"])
                 for f in facs if f["estado"] == "validada"}
        return pagina_facturas(token, facs, _nombres_proveedor(ses), _proveedores(ses), pedidos,
                               saldos=saldos)

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

    @bp.post("/<token>/gestion/facturas/<int:id_factura>/pagar")
    def facturas_pagar(token, id_factura):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import pagos_proveedor as PP
        id_proveedor = request.form.get("id_proveedor") or None
        metodo = request.form.get("metodo") or "otros"
        try:
            importe = float(request.form.get("importe") or 0)
        except ValueError:
            importe = 0.0
        if importe > 0:
            PP.registrar_pago(id_factura, metodo, importe,
                              id_proveedor=(int(id_proveedor) if id_proveedor else None),
                              usuario=ses.get("nombre_usuario"), id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/facturas")

    @bp.post("/<token>/gestion/facturas/abono")
    def facturas_abono(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_proveedor = request.form.get("id_proveedor")
        numero = (request.form.get("numero_factura") or "").strip()
        if not id_proveedor or not numero:
            return redirect(f"/portal/empresa/{token}/gestion/facturas")
        id_rect = request.form.get("id_factura_rectificada") or None
        try:
            base = float(request.form.get("base") or 0)
        except ValueError:
            base = 0.0
        C.registrar_abono(
            id_proveedor=int(id_proveedor), numero_factura=numero, base=base,
            iva=float(request.form.get("iva") or 0),
            id_factura_rectificada=(int(id_rect) if id_rect else None),
            fecha_factura=(request.form.get("fecha_factura") or "").strip() or None,
            id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/facturas")

    @bp.post("/<token>/gestion/facturas/asociar_recepcion")
    def facturas_asociar_recepcion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        id_factura = request.form.get("id_factura")
        try:
            id_recepcion = int(request.form.get("id_recepcion") or 0)
            importe = float(request.form.get("importe") or 0)
        except ValueError:
            return redirect(f"/portal/empresa/{token}/gestion/facturas")
        if id_factura and id_recepcion:
            C.asociar_recepcion_factura(int(id_factura), id_recepcion, importe, ses["id_empresa"])
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

    # ── Compras Pro (recurrentes/órdenes abiertas/comparativa/aprobación) ──
    @bp.get("/<token>/gestion/compras_pro")
    def compras_pro(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        from src.services.compras import compras_pro as CP
        ver = request.args.get("ver")
        comparativa = codigo_comparado = None
        id_pedido_aprob = aprobado = None
        if ver == "comparativa":
            codigo_comparado = (request.args.get("codigo") or "").strip()
            if codigo_comparado:
                comparativa = CP.comparativa_proveedores(codigo_comparado, id_empresa=ses["id_empresa"])
        elif ver == "aprobacion":
            id_pedido_txt = request.args.get("id_pedido")
            if id_pedido_txt:
                id_pedido_aprob = int(id_pedido_txt)
                aprobado = CP.pedido_aprobado(id_pedido_aprob, id_empresa=ses["id_empresa"])
        recurrentes = CP.listar_recurrentes(ses["id_empresa"])
        ordenes = CP.ordenes_abiertas(ses["id_empresa"])
        pedidos = C.listar_pedidos(id_empresa=ses["id_empresa"])
        return pagina_compras_pro(token, _proveedores(ses), recurrentes, ordenes, pedidos,
                                  comparativa=comparativa, codigo_comparado=codigo_comparado,
                                  id_pedido_aprob=id_pedido_aprob, aprobado=aprobado)

    @bp.post("/<token>/gestion/compras_pro/recurrentes/crear")
    def compras_pro_recurrente_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import compras_pro as CP
        id_proveedor = request.form.get("id_proveedor")
        codigo = (request.form.get("codigo") or "").strip()
        try:
            cantidad = float(request.form.get("cantidad") or 0)
            precio = float(request.form.get("precio") or 0)
            frecuencia = int(request.form.get("frecuencia_dias") or 30)
        except ValueError:
            return redirect(f"/portal/empresa/{token}/gestion/compras_pro")
        if id_proveedor and codigo and cantidad > 0:
            lineas = [{"codigo": codigo, "descripcion": codigo, "cantidad": cantidad,
                      "precio_unitario": precio}]
            CP.crear_recurrente(int(id_proveedor), lineas,
                                nombre=(request.form.get("nombre") or "").strip() or None,
                                frecuencia_dias=frecuencia, id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/compras_pro")

    @bp.post("/<token>/gestion/compras_pro/ordenes_abiertas/crear")
    def compras_pro_orden_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import compras_pro as CP
        id_proveedor = request.form.get("id_proveedor")
        codigo = (request.form.get("codigo") or "").strip()
        try:
            cantidad_total = float(request.form.get("cantidad_total") or 0)
            precio = float(request.form.get("precio") or 0)
        except ValueError:
            return redirect(f"/portal/empresa/{token}/gestion/compras_pro")
        if id_proveedor and codigo and cantidad_total > 0:
            CP.crear_orden_abierta(int(id_proveedor), codigo, cantidad_total, precio=precio,
                                   fecha_inicio=(request.form.get("fecha_inicio") or "").strip() or None,
                                   fecha_fin=(request.form.get("fecha_fin") or "").strip() or None,
                                   referencia=(request.form.get("referencia") or "").strip() or None,
                                   id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/compras_pro")

    @bp.post("/<token>/gestion/compras_pro/ordenes_abiertas/<int:id_orden>/consumir")
    def compras_pro_orden_consumir(token, id_orden):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import compras_pro as CP
        try:
            cantidad = float(request.form.get("cantidad") or 0)
        except ValueError:
            cantidad = 0
        if cantidad > 0:
            CP.consumir_orden_abierta(id_orden, cantidad, usuario=ses.get("nombre_usuario"),
                                      id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/compras_pro")

    @bp.post("/<token>/gestion/compras_pro/aprobacion/<int:id_pedido>/solicitar")
    def compras_pro_aprobacion_solicitar(token, id_pedido):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import compras as C
        from src.services.compras import compras_pro as CP
        ped = C.obtener_pedido(id_pedido, ses["id_empresa"])
        if ped:
            CP.solicitar_aprobacion_pedido(id_pedido, ped["total"], actor=ses.get("nombre_usuario"),
                                           id_empresa=ses["id_empresa"])
        return redirect(f"/portal/empresa/{token}/gestion/compras_pro?ver=aprobacion&id_pedido={id_pedido}")

    # ── Rappels acumulados ──
    @bp.get("/<token>/gestion/rappels")
    def rappels(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rappels as RAP
        provs = [p for p in _proveedores(ses) if p.get("id_suministrador")]
        nombres_sum = {p["id_suministrador"]: p["razon_social"] for p in provs}
        tramos = RAP.listar_tramos(id_empresa=ses["id_empresa"])
        tramos_por_sum = {}
        for t in tramos:
            tramos_por_sum.setdefault(t["id_suministrador"], []).append(t)
        progresos = {sid: RAP.progreso_suministrador(ses["id_empresa"], sid, tramos=ts)
                    for sid, ts in tramos_por_sum.items()}
        liquidaciones = RAP.listar_liquidaciones(id_empresa=ses["id_empresa"], limite=50)
        return pagina_rappels(token, provs, tramos_por_sum, progresos, liquidaciones, nombres_sum,
                              mensaje=request.args.get("mensaje"), error=request.args.get("error"))

    @bp.post("/<token>/gestion/rappels/tramos/crear")
    def rappels_tramo_crear(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rappels as RAP
        id_suministrador = request.form.get("id_suministrador")
        fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
        fecha_fin = (request.form.get("fecha_fin") or "").strip()
        try:
            umbral = float(request.form.get("umbral_desde") or 0)
            pct = float(request.form.get("pct_rebate") or 0)
        except ValueError:
            return redirect(f"/portal/empresa/{token}/gestion/rappels?error=datos_invalidos")
        if not (id_suministrador and umbral > 0 and 0 < pct <= 100 and fecha_inicio and fecha_fin):
            return redirect(f"/portal/empresa/{token}/gestion/rappels?error=datos_invalidos")
        RAP.crear_tramo(ses["id_empresa"], int(id_suministrador), umbral, pct, fecha_inicio, fecha_fin,
                        creado_por=ses.get("nombre_usuario"))
        return redirect(f"/portal/empresa/{token}/gestion/rappels?mensaje=Tramo+creado")

    @bp.post("/<token>/gestion/rappels/liquidar")
    def rappels_liquidar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rappels as RAP
        id_suministrador = request.form.get("id_suministrador")
        fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
        fecha_fin = (request.form.get("fecha_fin") or "").strip()
        if not (id_suministrador and fecha_inicio and fecha_fin):
            return redirect(f"/portal/empresa/{token}/gestion/rappels?error=datos_invalidos")
        r = RAP.liquidar_rappel(ses["id_empresa"], int(id_suministrador), fecha_inicio, fecha_fin,
                                usuario=ses.get("nombre_usuario"))
        if r.get("ok"):
            qs = f"mensaje=Liquidado:+{r.get('importe_rebate')}+€+(abono+%23{r.get('id_factura_abono')})"
        else:
            qs = f"error={r.get('motivo') or 'error_desconocido'}"
        return redirect(f"/portal/empresa/{token}/gestion/rappels?{qs}")

    # ── Licitaciones (RFQ) ──
    @bp.route("/<token>/gestion/licitaciones", methods=["GET", "POST"])
    def licitaciones(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rfq as RFQ
        if request.method == "POST":
            d = request.form
            fecha_cierre = (d.get("fecha_cierre_subasta") or "").strip().replace("T", " ")
            id_rfq = RFQ.crear_rfq(
                ses["id_empresa"], d.get("cantidad") or 0, d.get("unidad_medida") or "unidad",
                d.get("fecha_limite_entrega") or None, fecha_cierre or None,
                codigo_articulo=(d.get("codigo_articulo") or "").strip() or None,
                categoria=(d.get("categoria") or "").strip() or None,
                sector_comercial_id=ses.get("sector_id"), creado_por=ses.get("nombre_usuario"))
            if not id_rfq:
                return redirect(f"/portal/empresa/{token}/gestion/licitaciones?error=datos_invalidos")
            return redirect(f"/portal/empresa/{token}/gestion/licitaciones/{id_rfq}?mensaje=Licitacion+creada")
        return pagina_licitaciones(token, RFQ.listar_rfq(ses["id_empresa"]),
                                   mensaje=request.args.get("mensaje"), error=request.args.get("error"))

    @bp.get("/<token>/gestion/licitaciones/<id_rfq>")
    def licitacion_detalle(token, id_rfq):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rfq as RFQ
        rfq = RFQ.obtener_rfq(id_rfq, ses["id_empresa"])
        if not rfq:
            return _pagina_error("Licitación no encontrada", "Esa licitación no existe o no es tuya."), 404
        return pagina_licitacion_detalle(token, rfq, RFQ.ofertas_de_rfq(id_rfq),
                                         mensaje=request.args.get("mensaje"),
                                         error=request.args.get("error"))

    @bp.post("/<token>/gestion/licitaciones/<id_rfq>/adjudicar")
    def licitacion_adjudicar(token, id_rfq):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_rfq as RFQ
        rfq = RFQ.obtener_rfq(id_rfq, ses["id_empresa"])
        if not rfq:
            return _pagina_error("Licitación no encontrada", "Esa licitación no existe o no es tuya."), 404
        id_suministrador = request.form.get("id_suministrador")
        if not id_suministrador:
            return redirect(f"/portal/empresa/{token}/gestion/licitaciones/{id_rfq}?error=datos_invalidos")
        r = RFQ.adjudicar_rfq(id_rfq, int(id_suministrador), usuario=ses.get("nombre_usuario"))
        if r.get("ok"):
            qs = f"mensaje=Adjudicada+·+pedido+{r.get('id_tx')}"
        else:
            qs = f"error={r.get('error') or 'error_desconocido'}"
        return redirect(f"/portal/empresa/{token}/gestion/licitaciones/{id_rfq}?{qs}")

    return bp
