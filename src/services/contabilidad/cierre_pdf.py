"""
PDF del cierre formal de ejercicio (Contabilidad · pestaña Cierres). Reutiliza EXACTAMENTE el
mismo patrón que `calculadora_fiscal_pdf.py` (helpers `rrhh.documents.render.estilo_pdf`, B/N,
esquinas redondeadas) — sin motor de PDF paralelo. Antes de esto, "Cerrar Ejercicio" no generaba
ningún documento (bug real, confirmado): esta es la pieza que faltaba.
"""

import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

logger = logging.getLogger("contab.cierre_pdf")


def _dir_cierres() -> str:
    # cierre_pdf.py está en src/services/contabilidad/ (3 niveles bajo la raíz del proyecto) —
    # 4 `dirname` para llegar a la raíz, no 3 (error real detectado y corregido en pruebas: con 3
    # dirnames la ruta resultante caía dentro de src/, no en la raíz).
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    base = os.path.join(raiz, "documentos", "Cierres")
    os.makedirs(base, exist_ok=True)
    return base


def generar_pdf_cierre(anio, id_empresa=None, resultado=None, datos_empresa=None) -> str | None:
    """Genera el PDF de cierre del ejercicio `anio`: cabecera de empresa, balance de situación y
    pérdidas y ganancias reales (`informes.balance_situacion`/`perdidas_ganancias`), y la fecha de
    cierre. Devuelve la ruta, o None si falla."""
    try:
        from src.services.contabilidad import informes as I

        resultado = resultado or {}
        datos_empresa = datos_empresa or {}
        anio = int(anio)
        ruta = os.path.join(_dir_cierres(), f"CIERRE-{anio}.pdf")

        bs = I.balance_situacion(id_empresa=id_empresa, anio=anio)
        pyg = I.perdidas_ganancias(id_empresa=id_empresa, anio=anio)

        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                                topMargin=14 * mm, bottomMargin=14 * mm,
                                title=f"Cierre del ejercicio {anio}")
        usable_w = doc.width
        sty = E.estilos()

        emp_nombre = datos_empresa.get("nombre") or ""
        emp_cif = datos_empresa.get("cif") or ""
        emp_dir = datos_empresa.get("dir") or ""
        fecha_cierre = datetime.now().strftime("%d/%m/%Y %H:%M")

        story = [
            Paragraph(f"CIERRE DEL EJERCICIO {anio}", sty["tit"]),
            Paragraph(f"{emp_nombre}" + (f" · CIF {emp_cif}" if emp_cif else "") +
                     (f" · {emp_dir}" if emp_dir else ""), sty["sub"]),
            Paragraph(f"Fecha de cierre: {fecha_cierre}", sty["sub"]),
            Spacer(1, 4 * mm),
            E.seccion("Balance de situación", usable_w, sty), Spacer(1, 1.5 * mm),
            E.grid_datos(
                [("activo", "Activo"), ("pasivo", "Pasivo"),
                 ("patrimonio_neto", "Patrimonio neto"), ("cuadra", "Cuadra")],
                {"activo": f"{bs.get('activo', 0):,.2f} €", "pasivo": f"{bs.get('pasivo', 0):,.2f} €",
                 "patrimonio_neto": f"{bs.get('patrimonio_neto', 0):,.2f} €",
                 "cuadra": "Sí" if bs.get("cuadra") else "NO"},
                usable_w, sty),
            Spacer(1, 3 * mm),
            E.seccion("Pérdidas y ganancias", usable_w, sty), Spacer(1, 1.5 * mm),
            E.grid_datos(
                [("ingresos", "Ingresos"), ("gastos", "Gastos"), ("resultado", "Resultado")],
                {"ingresos": f"{pyg.get('ingresos', 0):,.2f} €", "gastos": f"{pyg.get('gastos', 0):,.2f} €",
                 "resultado": f"{pyg.get('resultado', 0):,.2f} €"},
                usable_w, sty),
            Spacer(1, 5 * mm),
            Paragraph(f"Regularización y asiento de cierre {'generados' if resultado.get('cierre') else 'no generados (sin movimientos)'}"
                     + (f"; apertura {anio + 1} generada." if resultado.get("apertura") else "."),
                     sty["sub"]),
        ]
        pie = sty["sub"].clone("pie"); pie.fontSize = 7; pie.textColor = colors.HexColor("#888888")
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            f"Documento generado por Smart Manager · CIERRE-{anio} · {fecha_cierre}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_cierre(%s): %s", anio, e)
        return None
