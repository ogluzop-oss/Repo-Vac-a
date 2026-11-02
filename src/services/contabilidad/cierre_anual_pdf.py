"""
PDF ÚNICO del Cierre del Ejercicio Anual (Contabilidad · pestaña Cierres). Sustituye a los TRES
documentos que `_cerrar()` generaba antes por separado (`cierre_pdf.generar_pdf_cierre`,
`informe_anual_pdf.generar_pdf_informe_anual`, `cuentas_anuales_pdf.generar_pdf_cuentas_anuales`,
registrados como tipo="cierre_ejercicio"/"informe_anual"/"cuentas_anuales") — decisión de producto:
cerrar el ejercicio debe dejar UN solo documento registrado, no tres, y sin cifras repetidas.

Reutiliza al 100% los helpers de sección ya factorizados en los otros dos módulos — nunca
reescribe una tabla desde cero (mismo criterio "sin motor de PDF paralelo" que el resto de
`services/contabilidad`):
  - `informe_anual_pdf._bloque_ventas/_bloque_mermas_devoluciones/_bloque_plantilla/
    _bloque_empleados_detalle/_bloque_inversion/_bloque_comparacion_interanual`
  - `cuentas_anuales_pdf._tabla_balance/_tabla_ecpn/_tabla_flujos/_bloque_memoria/
    _bloque_informe_gestion/_bloque_propuesta/_parrafo`

Deduplicación deliberada (auditoría de las 3 fuentes antes de este cambio): el "Resultado del
ejercicio"/ingresos/gastos aparecía en tres sitios con grados de detalle distintos:
  1. `cierre_pdf` — grid simple "Balance de situación"/"Pérdidas y ganancias" (vía
     `informes.balance_situacion`/`perdidas_ganancias`, re-consultado de cero, sin desglose).
  2. `informe_anual_pdf` — grid "Pérdidas y ganancias" actual vs. año anterior (vía
     `informes.perdidas_ganancias`, mismo dato que (1) para el año actual).
  3. `cuentas_anuales_pdf` — el Balance de Situación OFICIAL (`balance_situacion.generar_balance`,
     con desglose completo de partidas) y el Informe de Gestión · Evolución del negocio (también
     ingresos/gastos/resultado actual vs. anterior, pero como parte del documento estatutario).
Se queda SOLO (3): es la fuente con desglose real (no un resumen de 3 cifras) y es, además, parte
del documento legal Cuentas Anuales. Las cifras planas de (1) y (2) NO se repiten en el documento
unificado:
  - La sección "Resumen del cierre contable" de aquí se queda SOLO con el texto de
    regularización/cierre/apertura — lo único que (1) aportaba que (3) no cubre ya. Su grid de
    Balance/P&G se omite (duplicaría el Balance de Situación oficial y el Informe de Gestión).
  - La "Operativa del ejercicio" se queda con TODO el contenido de `informe_anual_pdf` EXCEPTO su
    grid de Pérdidas y Ganancias (`_bloque_pyg`, deliberadamente NO importado aquí), que ya cubre
    el Informe de Gestión de la parte de Cuentas Anuales.
  - La "Comparación interanual" de `informe_anual_pdf` SÍ se mantiene íntegra (incluida su fila
    "Resultado P&G" actual/anterior): no es un resumen plano redundante, es la única vista que
    compara ventas físico/online/total + resultado en una misma tabla año-contra-año, y
    `cuentas_anuales_pdf` no tiene equivalente — se deja para el final del documento, tal cual la
    ordenaba `informe_anual_pdf`.

`tipo` de documento registrado: "cierre_anual_completo" (NUEVO, ver `db/documentos.py` TIPOS y
`gui/centro_documental.py` _TIPOS_CONTABILIDAD) — no se reutiliza "cierre_ejercicio" a propósito:
ese tipo etiquetaba el PDF ESTRECHO de 1 página que generaba `cierre_pdf.generar_pdf_cierre`, y
reusarlo para este documento de 6 secciones/decenas de páginas confundiría cualquier búsqueda o
filtro futuro en Documentos Centralizados que asuma la forma antigua. `cierre_ejercicio`/
`informe_anual`/`cuentas_anuales` SIGUEN siendo tipos válidos (documentos históricos ya generados,
y `informe_anual` además lo sigue creando bajo demanda el botón "Generar PDF" del visor interactivo
`gui/informe_anual_gui.py`, un flujo manual DISTINTO del cierre automático — fuera del alcance de
este cambio) — simplemente `_cerrar()` ya no genera NUEVOS documentos de esos tres tipos.
"""

import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E
from src.services.contabilidad.cuentas_anuales_pdf import (
    _bloque_informe_gestion,
    _bloque_memoria,
    _bloque_propuesta,
    _parrafo,
    _tabla_balance,
    _tabla_ecpn,
    _tabla_flujos,
)
from src.services.contabilidad.informe_anual_pdf import (
    _bloque_comparacion_interanual,
    _bloque_empleados_detalle,
    _bloque_inversion,
    _bloque_mermas_devoluciones,
    _bloque_plantilla,
    _bloque_ventas,
)

logger = logging.getLogger("contab.cierre_anual_pdf")


def _dir_cierre_anual() -> str:
    # cierre_anual_pdf.py está en src/services/contabilidad/ (3 niveles bajo la raíz del
    # proyecto) — 4 `dirname` para llegar a la raíz (mismo criterio ya corregido/verificado en
    # cierre_pdf.py/informe_anual_pdf.py/cuentas_anuales_pdf.py).
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    base = os.path.join(raiz, "documentos", "CierreAnual")
    os.makedirs(base, exist_ok=True)
    return base


def _titulo_parte(texto, sty):
    """Divisor de 'parte' del documento unificado — a propósito DISTINTO visualmente de
    `E.seccion` (que ya se usa profusamente DENTRO de cada parte para sus propias sub-secciones).
    Va SIN numerar: la Memoria/Informe de Gestión/Propuesta reutilizados ya traen su propia
    numeración legal 2./3./4. (ver docstring del módulo), así que numerar estos divisores
    colisionaría con esa numeración oficial en vez de aclararla."""
    t = sty["tit"].clone("parte")
    t.fontSize = 12
    return Paragraph(texto, t)


def generar_pdf_cierre_anual_unificado(anio, id_empresa, resultado_cierre, datos_informe_anual,
                                        datos_cuentas_anuales, datos_empresa=None) -> str | None:
    """Genera el ÚNICO PDF del cierre del ejercicio `anio`: resumen del cierre contable + operativa
    del ejercicio (ventas/mermas/plantilla/inversión) + estados financieros (Balance/ECPN/Estado de
    Flujos) + Memoria/Informe de Gestión/Propuesta de Aplicación del Resultado + comparación
    interanual — ver docstring del módulo para el detalle de qué se fusiona/omite y por qué.

    Recibe los 3 dicts YA calculados (no vuelve a consultar nada):
      - `resultado_cierre`: dict devuelto por `cierre.cerrar_ejercicio_formal`.
      - `datos_informe_anual`: dict devuelto por `informe_anual.generar_informe_anual`.
      - `datos_cuentas_anuales`: dict devuelto por
        `cierre_anual_service.generar_cuentas_anuales_completas`.
    Devuelve la ruta del PDF generado, o None si falla."""
    try:
        anio = int(anio)
        resultado_cierre = resultado_cierre or {}
        datos_informe_anual = datos_informe_anual or {}
        datos_cuentas_anuales = datos_cuentas_anuales or {}
        datos_empresa = datos_empresa or {}
        ruta = os.path.join(_dir_cierre_anual(), f"CIERRE-ANUAL-{anio}.pdf")

        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                                topMargin=14 * mm, bottomMargin=14 * mm,
                                title=f"Cierre del Ejercicio Anual {anio}")
        usable_w = doc.width
        sty = E.estilos()

        emp_nombre = datos_empresa.get("nombre") or ""
        emp_cif = datos_empresa.get("cif") or ""
        emp_dir = datos_empresa.get("dir") or ""
        fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")

        story = [
            Paragraph(f"CIERRE DEL EJERCICIO ANUAL {anio}", sty["tit"]),
            Paragraph(f"{emp_nombre}" + (f" · CIF {emp_cif}" if emp_cif else "") +
                     (f" · {emp_dir}" if emp_dir else ""), sty["sub"]),
            Paragraph(f"Generado: {fecha_gen}", sty["sub"]),
            Spacer(1, 4 * mm),
        ]

        # ── Parte 1: Resumen del cierre contable ─────────────────────────────────────────────
        story.append(_titulo_parte("RESUMEN DEL CIERRE CONTABLE", sty))
        story.append(Spacer(1, 2 * mm))
        story.append(E.seccion("Regularización, cierre y apertura", usable_w, sty))
        story.append(Spacer(1, 1.5 * mm))
        texto_cierre = (
            "Regularización y asiento de cierre "
            + ("generados" if resultado_cierre.get("cierre") else "no generados (sin movimientos)")
            + (f"; apertura {anio + 1} generada." if resultado_cierre.get("apertura") else "."))
        story.append(_parrafo(texto_cierre, sty))
        story.append(Spacer(1, 5 * mm))

        # ── Parte 2: Operativa del ejercicio ─────────────────────────────────────────────────
        # Contenido íntegro de `informe_anual_pdf` EXCEPTO su grid de Pérdidas y Ganancias (ver
        # docstring del módulo): ese dato lo cubre, con más detalle, el Informe de Gestión de la
        # Parte 3. La Comparación Interanual (que sí incluye una fila de resultado P&G) se deja
        # para el final del documento (Parte 4).
        story.append(_titulo_parte("OPERATIVA DEL EJERCICIO", sty))
        story.append(Spacer(1, 2 * mm))
        story += _bloque_ventas(datos_informe_anual.get("ventas", {}), usable_w, sty)
        story += _bloque_mermas_devoluciones(
            datos_informe_anual.get("mermas", {}), datos_informe_anual.get("devoluciones", {}),
            usable_w, sty)
        story += _bloque_plantilla(datos_informe_anual.get("plantilla", {}), usable_w, sty)
        story += _bloque_empleados_detalle(
            datos_informe_anual.get("empleados_detalle", []), usable_w, sty)
        story += _bloque_inversion(datos_informe_anual.get("inversion", {}), usable_w, sty)
        story.append(PageBreak())

        # ── Parte 3: Cuentas Anuales (Estados financieros + Memoria + Gestión + Propuesta) ───
        # Se reutiliza tal cual la numeración legal propia del documento de Cuentas Anuales
        # (`cuentas_anuales_pdf`): 1 = Balance/ECPN/Estado de Flujos, 2 = Memoria, 3 = Informe de
        # Gestión, 4 = Propuesta de Aplicación del Resultado. Es la numeración oficial del
        # documento estatutario — no se renumera aquí.
        story.append(_titulo_parte("CUENTAS ANUALES", sty))
        story.append(Spacer(1, 2 * mm))

        balance = datos_cuentas_anuales.get("balance")
        ecpn = datos_cuentas_anuales.get("ecpn")
        estado_flujos = datos_cuentas_anuales.get("estado_flujos")
        story.append(E.seccion("1. Balance de situación / ECPN / Estado de flujos de efectivo",
                               usable_w, sty))
        story.append(Spacer(1, 1.5 * mm))
        if balance:
            story.append(E.seccion("1.1 Balance de situación", usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_balance(balance, usable_w, sty)
            story.append(PageBreak())
        if ecpn:
            story.append(E.seccion("1.2 Estado de cambios en el patrimonio neto (ECPN)",
                                   usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_ecpn(ecpn, usable_w, sty)
            story.append(Spacer(1, 5 * mm))
        if estado_flujos:
            story.append(E.seccion("1.3 Estado de flujos de efectivo (método indirecto)",
                                   usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_flujos(estado_flujos, usable_w, sty)
            story.append(PageBreak())
        if not (balance or ecpn or estado_flujos):
            story.append(_parrafo("[Sin datos de Balance/ECPN/Estado de Flujos disponibles para "
                                  "este ejercicio.]", sty))
            story.append(Spacer(1, 5 * mm))

        memoria = datos_cuentas_anuales.get("memoria") or {}
        informe_gestion = datos_cuentas_anuales.get("informe_gestion") or {}
        propuesta = datos_cuentas_anuales.get("propuesta") or {}
        story += _bloque_memoria(memoria, usable_w, sty)
        story += _bloque_informe_gestion(informe_gestion, anio, usable_w, sty)
        story += _bloque_propuesta(propuesta, usable_w, sty)

        # ── Parte 4: Comparación interanual ──────────────────────────────────────────────────
        story.append(_titulo_parte("COMPARACIÓN INTERANUAL", sty))
        story.append(Spacer(1, 2 * mm))
        story += _bloque_comparacion_interanual(
            datos_informe_anual.get("comparacion_interanual", {}), anio, usable_w, sty)

        pie = sty["sub"].clone("pie"); pie.fontSize = 7; pie.textColor = colors.HexColor("#888888")
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            f"Documento generado por Smart Manager · CIERRE-ANUAL-{anio} · {fecha_gen}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_cierre_anual_unificado(%s): %s", anio, e)
        return None
