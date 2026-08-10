"""
Generador AUTÓNOMO de la BAJA LABORAL en PDF — diseño limpio B/N, Segoe UI bold y tablas con esquinas
redondeadas (helpers de `estilo_pdf`). Recibe `datos` (campos del formulario inline) y produce el PDF.
Documento informativo: comunicación/registro de la baja del trabajador (IT).
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

TIPOS_BAJA = ["Enfermedad común", "Accidente laboral", "Enfermedad profesional", "Accidente no laboral"]

EMPRESA_CAMPOS = [
    ("razon_social", "Razón social"), ("cif", "CIF"), ("ccc", "CCC"),
]
TRABAJADOR_CAMPOS = [
    ("nombre", "Nombre"), ("nif", "DNI"), ("num_ss", "NSS"),
    ("categoria", "Categoría"), ("puesto", "Puesto"),
]
BAJA_CAMPOS = [
    ("tipo_baja", "Tipo de baja"), ("fecha_baja", "Fecha de baja"),
    ("fecha_efecto", "Fecha de efecto"), ("duracion_estimada", "Duración estimada"),
    ("codigo_diagnostico", "Código diagnóstico (si procede)"), ("medico_emisor", "Médico emisor"),
    ("centro_sanitario", "Centro sanitario"), ("revisiones", "Revisiones"),
    ("fecha_prevista_alta", "Fecha prevista de alta"),
    ("fecha_alta_definitiva", "Fecha alta definitiva"),
]
GESTION_CAMPOS = [
    ("fecha_recepcion", "Fecha de recepción"), ("responsable", "Responsable"),
]
OBSERVACIONES_CAMPO = ("observaciones", "Observaciones")


def generar_baja_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "bajas")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "BAJA"
        ruta = os.path.join(folder, f"BAJA_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Baja laboral")
    usable_w = doc.width
    sty = E.estilos()

    story = [
        Paragraph("COMUNICACIÓN DE BAJA LABORAL", sty["tit"]),
        Paragraph(f"Emitido el {datetime.now().strftime('%d/%m/%Y')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos de la baja", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(BAJA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Gestión de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(GESTION_CAMPOS, datos, usable_w, sty), Spacer(1, 1.5 * mm),
    ]
    if str(datos.get("observaciones") or "").strip():
        story.append(E.grid_datos([OBSERVACIONES_CAMPO], datos, usable_w, sty, cols=1))
    story.append(Spacer(1, 4 * mm))
    story.append(E.firmas(usable_w, sty, "Firma de la empresa", str(datos.get("razon_social") or "—"),
                          "Firma del trabajador/a", str(datos.get("nombre") or "—")))
    doc.build(story)
    return ruta
