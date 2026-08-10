"""
Generador AUTÓNOMO del ALTA LABORAL en PDF — diseño limpio B/N, Segoe UI bold y tablas con esquinas
redondeadas (helpers de `estilo_pdf`). Recibe `datos` (campos del formulario inline) y produce el PDF.
Documento informativo (sin cálculo): comunicación de alta del trabajador en la Seguridad Social.
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

# ── Grupos de campos (compartidos con el formulario inline) ───────────────────
EMPRESA_CAMPOS = [
    ("razon_social", "Razón social"), ("cif", "CIF"), ("ccc", "CCC"),
    ("domicilio", "Domicilio"), ("cnae", "CNAE"),
]
TRABAJADOR_CAMPOS = [
    ("nombre_completo", "Nombre completo"), ("nif", "DNI/NIE"), ("num_ss", "Nº Seguridad Social"),
    ("fecha_nacimiento", "Fecha de nacimiento"), ("sexo", "Sexo"), ("nacionalidad", "Nacionalidad"),
    ("direccion", "Dirección"), ("municipio", "Municipio"), ("provincia", "Provincia"),
    ("cp", "Código Postal"), ("telefono", "Teléfono"), ("email", "Email"),
]
CONTRATO_CAMPOS = [
    ("fecha_alta", "Fecha de alta"), ("fecha_inicio", "Fecha inicio contrato"),
    ("tipo_contrato", "Tipo de contrato"), ("codigo_contrato", "Código de contrato"),
    ("duracion", "Duración"), ("fecha_fin", "Fecha fin (si existe)"), ("jornada", "Jornada"),
    ("horario", "Horario"), ("horas_semanales", "Horas semanales"),
    ("grupo_cotizacion", "Grupo de cotización"), ("grupo_prof", "Grupo profesional"),
    ("categoria", "Categoría"), ("puesto", "Puesto"), ("centro_trabajo", "Centro de trabajo"),
    ("convenio", "Convenio colectivo"), ("salario_bruto_anual", "Salario bruto anual"),
    ("salario_mensual", "Salario mensual"), ("pagas_extra", "Pagas extras"),
    ("periodo_prueba", "Periodo de prueba"), ("vacaciones", "Vacaciones"),
]
FUNCIONES_CAMPO = ("funciones", "Funciones")
SS_CAMPOS = [
    ("regimen", "Régimen"), ("sistema_especial", "Sistema especial (si existe)"),
    ("ocupacion", "Ocupación"), ("coef_parcialidad", "Coeficiente parcialidad"),
    ("coef_jornada", "Coeficiente jornada"),
]


def generar_alta_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "altas")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "ALTA"
        ruta = os.path.join(folder, f"ALTA_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Alta laboral")
    usable_w = doc.width
    sty = E.estilos()

    story = [
        Paragraph("COMUNICACIÓN DE ALTA LABORAL", sty["tit"]),
        Paragraph(f"Emitido el {datetime.now().strftime('%d/%m/%Y')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del contrato", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(CONTRATO_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
    ]

    # Funciones (texto libre, ancho completo).
    funciones = str(datos.get("funciones") or "").strip()
    if funciones:
        story.append(E.seccion("Funciones", usable_w, sty)); story.append(Spacer(1, 1.5 * mm))
        story.append(E.grid_datos([FUNCIONES_CAMPO], datos, usable_w, sty, cols=1))
        story.append(Spacer(1, 3 * mm))

    story += [
        E.seccion("Seguridad Social", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(SS_CAMPOS, datos, usable_w, sty), Spacer(1, 4 * mm),
        E.firmas(usable_w, sty, "Firma de la empresa", str(datos.get("razon_social") or "—"),
                 "Firma del trabajador/a", str(datos.get("nombre_completo") or "—")),
    ]
    doc.build(story)
    return ruta
