"""
Generador AUTÓNOMO de la CARTA DE DESPIDO en PDF — diseño limpio B/N, Segoe UI bold y tablas con
esquinas redondeadas (helpers de `estilo_pdf`). Recibe `datos` del formulario inline. Comunicación de
extinción del contrato con relato de hechos, liquidación, recursos y firmas.
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

TIPOS_DESPIDO = [
    "Disciplinario (art. 54 ET)", "Objetivo (art. 52 ET)", "Colectivo (art. 51 ET)", "Improcedente",
]
RECIBI_ESTADOS = ["Recibí", "No conforme", "Negativa a firmar"]

EMPRESA_CAMPOS = [("razon_social", "Razón social"), ("cif", "CIF"), ("domicilio", "Domicilio")]
TRABAJADOR_CAMPOS = [
    ("nombre", "Nombre"), ("nif", "DNI"), ("puesto", "Puesto"), ("categoria", "Categoría"),
]
ENCABEZADO_CAMPOS = [("lugar", "Lugar"), ("fecha_carta", "Fecha")]
DATOS_LABORALES_CAMPOS = [
    ("fecha_alta", "Fecha de alta"), ("antiguedad", "Antigüedad"),
    ("tipo_contrato", "Tipo de contrato"), ("jornada", "Jornada"),
]
COMUNICACION_CAMPOS = [
    ("fecha_efectos", "Fecha de efectos"), ("tipo_despido", "Tipo de despido"),
    ("fundamento_legal", "Fundamento legal"), ("articulos_et", "Artículos ET aplicables"),
    ("convenio", "Convenio colectivo"),
]
HECHOS_CAMPO = ("hechos", "Relato de los hechos")
LIQUIDACION_CAMPOS = [
    ("indemnizacion", "Indemnización"), ("finiquito", "Finiquito"),
    ("forma_pago", "Forma de pago"), ("disponibilidad", "Disponibilidad"),
]
TESTIGOS_CAMPO = ("testigos", "Testigos (si existen)")


def generar_carta_despido_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "cartas_despido")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "DESPIDO"
        ruta = os.path.join(folder, f"CARTA_DESPIDO_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Carta de despido")
    usable_w = doc.width
    sty = E.estilos()

    nombre = str(datos.get("nombre") or "—")
    tipo_desp = datos.get("tipo_despido") or TIPOS_DESPIDO[0]
    fecha_ef = str(datos.get("fecha_efectos") or "—")
    fundamento = str(datos.get("fundamento_legal") or "").strip()
    arts = str(datos.get("articulos_et") or "").strip()
    lugar = str(datos.get("lugar") or "—")
    fecha_c = str(datos.get("fecha_carta") or datetime.now().strftime("%d/%m/%Y"))

    story = [
        Paragraph("CARTA DE DESPIDO", sty["tit"]),
        Paragraph(f"En {lugar}, a {fecha_c}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos laborales", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(DATOS_LABORALES_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Comunicación de despido", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(COMUNICACION_CAMPOS, datos, usable_w, sty), Spacer(1, 2 * mm),
        Paragraph(
            f"Muy Sr./Sra. <b>{nombre}</b>:<br/><br/>Por medio de la presente le comunicamos la "
            f"decisión de esta empresa de proceder a la <b>extinción de su contrato de trabajo</b> con "
            f"efectos del <b>{fecha_ef}</b>, mediante <b>despido {tipo_desp}</b>"
            + (f", al amparo de {fundamento}" if fundamento else "")
            + (f" ({arts})" if arts else "") + ".", sty["just"]),
        Spacer(1, 3 * mm),
        E.seccion("Hechos", usable_w, sty), Spacer(1, 1.5 * mm),
        Paragraph((str(datos.get("hechos") or "—")).replace("\n", "<br/>"), sty["just"]),
        Spacer(1, 3 * mm),
        E.seccion("Liquidación", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(LIQUIDACION_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Recursos", usable_w, sty), Spacer(1, 1.5 * mm),
        Paragraph(
            "Se informa al trabajador/a de que dispone de un plazo de <b>20 días hábiles</b>, contados "
            "desde la fecha de efectos del despido, para impugnar esta decisión ante el Juzgado de lo "
            "Social, previa presentación de la papeleta de conciliación ante el servicio administrativo "
            "correspondiente (SMAC), conforme a la legislación laboral vigente.", sty["just"]),
        Spacer(1, 5 * mm),
    ]

    recibi = datos.get("recibi_estado") or RECIBI_ESTADOS[0]
    columnas = [("Por la empresa", str(datos.get("razon_social") or "—")),
                (f"El/la trabajador/a — {recibi}", nombre)]
    if str(datos.get("testigos") or "").strip():
        columnas.append(("Testigos", str(datos.get("testigos"))))
    story.append(E.firmas_cols(usable_w, sty, columnas))
    doc.build(story)
    return ruta
