"""
PDF del Informe Anual de Empresa (Contabilidad · pestaña Cierres). Reutiliza EXACTAMENTE el mismo
patrón que `cierre_pdf.py` (helpers `rrhh.documents.render.estilo_pdf`, B/N, esquinas redondeadas) —
sin motor de PDF paralelo. Recibe el dict YA calculado por `informe_anual.generar_informe_anual`
(no vuelve a consultar nada): el dict es la única fuente de verdad de este documento.
"""

import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

logger = logging.getLogger("contab.informe_anual_pdf")


def _dir_informes_anuales() -> str:
    # informe_anual_pdf.py está en src/services/contabilidad/ (3 niveles bajo la raíz del proyecto) —
    # 4 `dirname` para llegar a la raíz (mismo criterio y mismo error ya corregido en cierre_pdf.py).
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    base = os.path.join(raiz, "documentos", "InformesAnuales")
    os.makedirs(base, exist_ok=True)
    return base


def _eur(v):
    if isinstance(v, str):
        return v
    try:
        from src.utils import divisas
        return divisas.formatear(v)
    except Exception:
        return f"{float(v or 0):,.2f} €"


def _bloque_ventas(ventas, usable_w, sty) -> list:
    """Sección 'Ventas': totales (empresa/físico/online) + desglose por tienda. Factorizado
    (igual que `cuentas_anuales_pdf._tabla_balance`/`_tabla_ecpn`/`_tabla_flujos`) para que
    `cierre_anual_pdf.generar_pdf_cierre_anual_unificado` lo reutilice tal cual: un único punto
    de verdad para el layout de esta sección, sin reescribir la tabla en el documento unificado."""
    ventas = ventas or {}
    return [
        E.seccion("Ventas", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(
            [("total_empresa", "Total empresa"), ("total_fisico", "Total físico"),
             ("total_online", "Total online")],
            {"total_empresa": _eur(ventas.get("total_empresa")),
             "total_fisico": _eur(ventas.get("total_fisico")),
             "total_online": _eur(ventas.get("total_online"))},
            usable_w, sty, cols=3),
        Spacer(1, 2 * mm),
        E.tabla_columnas([("tienda", "Tienda"), ("num_ventas", "Nº ventas"), ("total", "Total")],
                         [{"tienda": f.get("tienda"), "num_ventas": f.get("num_ventas"),
                           "total": _eur(f.get("total"))} for f in ventas.get("por_tienda", [])],
                         usable_w, sty),
        Spacer(1, 5 * mm),
    ]


def _bloque_mermas_devoluciones(mermas, devoluciones, usable_w, sty) -> list:
    """Sección 'Mermas y devoluciones'. Factorizado por el mismo motivo que `_bloque_ventas`."""
    mermas = mermas or {}
    devoluciones = devoluciones or {}
    return [
        E.seccion("Mermas y devoluciones", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(
            [("m_reg", "Mermas · registros"), ("m_cant", "Mermas · cantidad"),
             ("d_reg", "Devoluciones · registros"), ("d_imp", "Devoluciones · importe")],
            {"m_reg": mermas.get("registros"), "m_cant": mermas.get("cantidad_total"),
             "d_reg": devoluciones.get("registros"),
             "d_imp": _eur(devoluciones.get("total_reembolso"))},
            usable_w, sty),
        Spacer(1, 5 * mm),
    ]


def _bloque_plantilla(plantilla, usable_w, sty) -> list:
    """Sección 'Plantilla'. Factorizado por el mismo motivo que `_bloque_ventas`."""
    plantilla = plantilla or {}
    return [
        E.seccion("Plantilla", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(
            [("activos", "Activos actuales"), ("expediente", "Con expediente (histórico)"),
             ("altas", "Altas nuevas")],
            {"activos": plantilla.get("activos_actuales"),
             "expediente": plantilla.get("total_empleados_con_expediente"),
             "altas": plantilla.get("num_altas_nuevas")},
            usable_w, sty, cols=3),
        Spacer(1, 5 * mm),
    ]


def _bloque_empleados_detalle(empleados, usable_w, sty) -> list:
    """Sección 'Detalle por empleado' (omitida si no hay empleados). Factorizado por el mismo
    motivo que `_bloque_ventas`."""
    if not empleados:
        return []
    return [
        E.seccion("Detalle por empleado", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_columnas(
            [("nombre", "Nombre"), ("horas", "Horas"), ("bajas", "Días de baja"),
             ("bruto", "Bruto anual"), ("ss", "SS empresa")],
            [{"nombre": e.get("nombre_completo"),
              "horas": "no disponible" if e.get("horas_trabajadas_anio") is None
                       else e.get("horas_trabajadas_anio"),
              "bajas": e.get("dias_baja_medica_anio"),
              "bruto": _eur(e.get("bruto_anual")),
              "ss": _eur(e.get("ss_empresa_anual"))} for e in empleados],
            usable_w, sty),
        Spacer(1, 5 * mm),
    ]


def _bloque_inversion(inversion, usable_w, sty) -> list:
    """Sección 'Inversión por categoría'. Factorizado por el mismo motivo que `_bloque_ventas`.

    `sin_categorizar_historico` NO se lista aquí (decisión de producto: no mostrar la categoría
    "cajón de sastre" en el PDF) pero SÍ sigue sumada dentro de `total_inversion_calculada` (ver
    `informe_anual._inversion`) — no se pierde el importe, solo se omite su fila. Mismo criterio
    que `informe_anual_gui._render_inversion`."""
    inversion = inversion or {}
    inv_filas = [
        ("Proveedores", inversion.get("proveedores")),
        ("Rebates proveedores liquidados (informativo, ya incluido en Proveedores)",
         inversion.get("rebates_proveedores_liquidados")),
        ("Sueldos", inversion.get("sueldos")),
        ("SS empresa", inversion.get("ss_empresa")), ("Maquinaria", inversion.get("maquinaria")),
        ("Publicidad", inversion.get("publicidad")), ("Alquiler", inversion.get("alquiler")),
        ("Suministros", inversion.get("suministros")), ("Vehículos", inversion.get("vehiculos")),
        ("Impuestos", inversion.get("impuestos")),
    ]
    bloques = [
        E.seccion("Inversión por categoría", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_importes(
            "CATEGORÍA", [(c, _eur(v) if not isinstance(v, str) else v) for c, v in inv_filas],
            "TOTAL (calculado)", inversion.get("total_inversion_calculada"), usable_w, sty),
    ]
    if inversion.get("ss_empresa_nota"):
        bloques.append(Spacer(1, 2 * mm))
        nota = sty["sub"].clone("nota_ss")
        nota.textColor = colors.HexColor("#555555")
        bloques.append(Paragraph(f"Nota: {inversion['ss_empresa_nota']}", nota))
    return bloques


def _bloque_pyg(pyg, anio, usable_w, sty) -> list:
    """Sección 'Pérdidas y ganancias' (actual vs. año anterior). Factorizado por el mismo motivo
    que `_bloque_ventas` — OJO: el documento unificado (`cierre_anual_pdf`) NO reutiliza este
    bloque a propósito (duplicaría el Informe de Gestión · Evolución del negocio de Cuentas
    Anuales, que cubre el mismo dato con más detalle); se mantiene aquí solo para que
    `generar_pdf_informe_anual` (documento standalone, todavía usado por el visor interactivo de
    `informe_anual_gui.py`) siga generando exactamente el mismo contenido que antes."""
    pyg = pyg or {}
    pyg_actual, pyg_anterior = pyg.get("actual", {}), pyg.get("anterior", {})
    return [
        E.seccion("Pérdidas y ganancias", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(
            [("ing_a", f"Ingresos {anio}"), ("gas_a", f"Gastos {anio}"),
             ("res_a", f"Resultado {anio}"),
             ("ing_b", f"Ingresos {anio - 1}"), ("gas_b", f"Gastos {anio - 1}"),
             ("res_b", f"Resultado {anio - 1}")],
            {"ing_a": _eur(pyg_actual.get("ingresos")), "gas_a": _eur(pyg_actual.get("gastos")),
             "res_a": _eur(pyg_actual.get("resultado")), "ing_b": _eur(pyg_anterior.get("ingresos")),
             "gas_b": _eur(pyg_anterior.get("gastos")), "res_b": _eur(pyg_anterior.get("resultado"))},
            usable_w, sty, cols=3),
        Spacer(1, 5 * mm),
    ]


def _bloque_comparacion_interanual(comp, anio, usable_w, sty) -> list:
    """Sección 'Comparación interanual' (ventas físico/online/total + resultado P&G, año actual
    vs. anterior). Factorizado por el mismo motivo que `_bloque_ventas` — este bloque SÍ lo
    reutiliza `cierre_anual_pdf` tal cual (no tiene equivalente en Cuentas Anuales)."""
    comp = comp or {}
    comp_filas = []
    for clave, etiqueta in (("ventas_fisico", "Ventas físico"), ("ventas_online", "Ventas online"),
                            ("ventas_total", "Ventas total"), ("resultado_pyg", "Resultado P&G")):
        c = comp.get(clave, {})
        comp_filas.append({"concepto": etiqueta, "actual": _eur(c.get("actual")),
                           "anterior": _eur(c.get("anterior"))})
    return [
        E.seccion("Comparación interanual", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_columnas(
            [("concepto", "Concepto"), ("actual", f"{anio}"),
             ("anterior", f"{comp.get('anio_anterior', anio - 1)}")],
            comp_filas, usable_w, sty),
    ]


def generar_pdf_informe_anual(anio, id_empresa, datos, datos_empresa=None) -> str | None:
    """Genera el PDF del Informe Anual de Empresa del ejercicio `anio` a partir del dict YA
    calculado por `generar_informe_anual` (`datos`). Devuelve la ruta, o None si falla."""
    try:
        anio = int(anio)
        datos = datos or {}
        datos_empresa = datos_empresa or {}
        ruta = os.path.join(_dir_informes_anuales(), f"INFORME-ANUAL-{anio}.pdf")

        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                                topMargin=14 * mm, bottomMargin=14 * mm,
                                title=f"Informe Anual de Empresa {anio}")
        usable_w = doc.width
        sty = E.estilos()

        emp_nombre = datos_empresa.get("nombre") or ""
        emp_cif = datos_empresa.get("cif") or ""
        emp_dir = datos_empresa.get("dir") or ""
        fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")

        story = [
            Paragraph(f"INFORME ANUAL DE EMPRESA {anio}", sty["tit"]),
            Paragraph(f"{emp_nombre}" + (f" · CIF {emp_cif}" if emp_cif else "") +
                     (f" · {emp_dir}" if emp_dir else ""), sty["sub"]),
            Paragraph(f"Generado: {fecha_gen}", sty["sub"]),
            Spacer(1, 4 * mm),
        ]
        story += _bloque_ventas(datos.get("ventas", {}), usable_w, sty)
        story += _bloque_mermas_devoluciones(
            datos.get("mermas", {}), datos.get("devoluciones", {}), usable_w, sty)
        story += _bloque_plantilla(datos.get("plantilla", {}), usable_w, sty)
        story += _bloque_empleados_detalle(datos.get("empleados_detalle", []), usable_w, sty)
        story += _bloque_inversion(datos.get("inversion", {}), usable_w, sty)
        story.append(PageBreak())
        story += _bloque_pyg(datos.get("pyg", {}), anio, usable_w, sty)
        story += _bloque_comparacion_interanual(
            datos.get("comparacion_interanual", {}), anio, usable_w, sty)

        pie = sty["sub"].clone("pie"); pie.fontSize = 7; pie.textColor = colors.HexColor("#888888")
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            f"Documento generado por Smart Manager · INFORME-ANUAL-{anio} · {fecha_gen}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_informe_anual(%s): %s", anio, e)
        return None
