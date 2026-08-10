"""
Generador AUTÓNOMO del CERTIFICADO DE EMPRESA (SEPE) en PDF — sigue prácticamente el modelo oficial.
Diseño limpio B/N, Segoe UI bold y tablas con esquinas redondeadas (helpers de `estilo_pdf`). Incluye
la relación MENSUAL de bases de cotización (tabla de varias filas). Recibe `datos` del formulario inline.
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

# Causas de cese oficiales (SEPE) — código: descripción.
CAUSAS_CESE = [
    "01 · Despido", "02 · Despido procedente", "03 · Despido improcedente",
    "04 · Fin de contrato temporal", "05 · Baja voluntaria", "06 · Despido colectivo (ERE)",
    "07 · Fin período de prueba", "08 · Jubilación", "09 · Incapacidad", "10 · Fallecimiento",
    "11 · Excedencia", "12 · Otras causas",
]
MOTIVOS_BAJA = ["Fin de contrato", "Despido", "Baja voluntaria", "Jubilación", "Incapacidad",
                "Fallecimiento", "Excedencia", "Otras"]

EMPRESA_CAMPOS = [
    ("razon_social", "Razón social"), ("cif", "CIF"), ("ccc", "CCC"),
    ("cnae", "CNAE"), ("domicilio", "Domicilio"),
]
TRABAJADOR_CAMPOS = [
    ("nombre", "Nombre"), ("nif", "DNI"), ("num_ss", "NSS"),
    ("fecha_nacimiento", "Fecha de nacimiento"),
]
RELACION_CAMPOS = [
    ("fecha_alta", "Fecha de alta"), ("fecha_baja", "Fecha de baja"),
    ("motivo_baja", "Motivo de baja"), ("tipo_contrato", "Tipo de contrato"),
    ("codigo_contrato", "Código de contrato"), ("ocupacion", "Ocupación"),
    ("grupo_cotizacion", "Grupo de cotización"), ("jornada", "Jornada"),
]
# Tabla mensual de bases de cotización.
BASES_COLUMNAS = [
    ("mes", "Mes / Año"), ("base_cc", "Base contingencias"),
    ("horas_extra", "Horas extras"), ("dias", "Días cotizados"),
]
VACACIONES_CAMPOS = [
    ("vac_pendientes", "Vacaciones pendientes"), ("vac_disfrutadas", "Vacaciones disfrutadas"),
    ("vac_retribuidas_tras_baja", "Retribuidas tras la baja"),
]
CAUSA_CESE_CAMPO = ("causa_cese", "Causa del cese (código oficial)")


def generar_certificado_empresa_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "certificados_empresa")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "CERTEMP"
        ruta = os.path.join(folder, f"CERT_EMPRESA_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Certificado de empresa (SEPE)")
    usable_w = doc.width
    sty = E.estilos()
    bases = datos.get("bases_mensuales") or []

    story = [
        Paragraph("CERTIFICADO DE EMPRESA", sty["tit"]),
        Paragraph("Servicio Público de Empleo Estatal (SEPE)"
                  f"  ·  Emitido el {datetime.now().strftime('%d/%m/%Y')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Relación laboral", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(RELACION_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Bases de cotización (relación mensual)", usable_w, sty), Spacer(1, 1.5 * mm),
        E.tabla_columnas(BASES_COLUMNAS, bases, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Vacaciones", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(VACACIONES_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Causa del cese", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos([CAUSA_CESE_CAMPO], datos, usable_w, sty, cols=1), Spacer(1, 5 * mm),
        E.firmas_cols(usable_w, sty, [("Firma y sello de la empresa",
                                       str(datos.get("razon_social") or "—"))]),
    ]
    doc.build(story)
    return ruta
