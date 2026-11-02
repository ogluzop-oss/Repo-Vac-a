"""
Exportación a PDF del resultado de la Calculadora Fiscal (Contabilidad). Reutiliza EXACTAMENTE el
helper de estilo de los generadores RRHH (`rrhh.documents.render.estilo_pdf`, B/N, Segoe UI,
esquinas redondeadas) — mismo patrón que `rrhh/documents/render/cert_laboral_pdf.py`, sin motor de
PDF paralelo. Ruta de guardado con la convención de `services/` (PyInstaller-safe):
`utils.recursos.ruta_datos(...)`, igual que `services/fiscal/evidencias.py`.
"""

import logging
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

logger = logging.getLogger("contab.calculadora_fiscal_pdf")

_CAMPOS_PERFIL = [("tipo_entidad", "Tipo de entidad"), ("ccaa", "Comunidad Autónoma"),
                  ("anio", "Ejercicio"), ("num_empleados_total", "Nº empleados")]


def generar_pdf(resultado: dict, contexto: dict = None, ruta: str = None) -> str:
    """`resultado`: el dict devuelto por `calculadora_fiscal.simular()`. `contexto`: datos de
    cabecera opcionales (empresa, tipo_entidad, ccaa, anio). Devuelve la ruta del PDF generado."""
    resultado = resultado or {}
    contexto = contexto or {}

    if not ruta:
        from src.utils import recursos
        folder = recursos.ruta_datos("calculadora_fiscal")
        os.makedirs(folder, exist_ok=True)
        emp = str(contexto.get("empresa") or "IS").replace(" ", "_")[:40]
        ruta = os.path.join(folder, f"IS_{emp}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Calculadora Fiscal — Impuesto de Sociedades")
    usable_w = doc.width
    sty = E.estilos()

    datos_perfil = {
        "tipo_entidad": contexto.get("tipo_entidad") or "—",
        "ccaa": contexto.get("ccaa") or "—",
        "anio": contexto.get("anio") or datetime.now().year,
        "num_empleados_total": resultado.get("num_empleados_total", 0),
    }

    filas_deducciones = [
        ("Deducción por empleo (contratación indefinida/bonificada)", resultado.get("deduccion_empleo", 0)),
        ("Deducción por inversión en I+D", resultado.get("deduccion_id", 0)),
        ("Deducción por inversión en digitalización", resultado.get("deduccion_digitalizacion", 0)),
    ]

    story = [
        Paragraph("CALCULADORA FISCAL — IMPUESTO DE SOCIEDADES (ESTIMACIÓN)", sty["tit"]),
        Paragraph(f"Simulación generada el {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Perfil de la simulación", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(_CAMPOS_PERFIL, datos_perfil, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Base y cuota", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos([("base_imponible", "Base imponible"),
                     ("cuota_integra", f"Cuota íntegra ({resultado.get('tipo_general_pct', 0):.0f}%)")],
                    {"base_imponible": f"{resultado.get('base_imponible', 0):,.2f} €",
                     "cuota_integra": f"{resultado.get('cuota_integra', 0):,.2f} €"}, usable_w, sty),
        Spacer(1, 3 * mm),
        E.seccion("Deducciones aplicadas", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_importes("Concepto", filas_deducciones, "TOTAL DEDUCCIONES",
                         resultado.get("total_deducciones", 0), usable_w, sty),
        Spacer(1, 3 * mm),
        E.seccion("Resultado", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_importes("Concepto", [("Ahorro fiscal estimado", resultado.get("ahorro_fiscal_estimado", 0))],
                         "IMPUESTO FINAL ESTIMADO", resultado.get("impuesto_final", 0), usable_w, sty),
        Spacer(1, 5 * mm),
        Paragraph(resultado.get("nota_legal") or
                 "Estimación orientativa, sujeta a validación de un asesor fiscal.", sty["sub"]),
    ]
    doc.build(story)
    logger.info("PDF de Calculadora Fiscal generado: %s", ruta)
    return ruta
