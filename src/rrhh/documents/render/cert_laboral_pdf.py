"""
Generador AUTÓNOMO del CERTIFICADO LABORAL (certificado de servicios prestados) en PDF — diseño limpio
B/N, Segoe UI bold y tablas con esquinas redondeadas (helpers de `estilo_pdf`). Recibe `datos` del
formulario inline. Documento a petición del trabajador (banco/embajada/administración/…).
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

FINALIDADES = ["Solicitud del trabajador", "Banco", "Embajada", "Administración", "Otra"]

EMPRESA_CAMPOS = [("razon_social", "Razón social"), ("cif", "CIF"), ("domicilio", "Domicilio")]
TRABAJADOR_CAMPOS = [("nombre", "Nombre"), ("nif", "DNI")]
CONTENIDO_CAMPOS = [
    ("fecha_alta", "Fecha de alta"), ("fecha_baja", "Fecha de baja (si existe)"),
    ("antiguedad", "Antigüedad"), ("puesto", "Puesto"), ("categoria", "Categoría"),
    ("departamento", "Departamento"), ("jornada", "Jornada"), ("horario", "Horario"),
    ("tipo_contrato", "Tipo de contrato"), ("salario", "Salario (si procede)"),
    ("convenio", "Convenio colectivo"), ("centro_trabajo", "Centro de trabajo"),
]
FUNCIONES_CAMPO = ("funciones", "Funciones")
EXPEDICION_CAMPOS = [
    ("lugar", "Lugar"), ("fecha_expedicion", "Fecha"),
    ("representante_empresa", "Representante de la empresa"), ("cargo", "Cargo"),
]
FINALIDAD_CAMPO = ("finalidad", "Finalidad del certificado")


def generar_cert_laboral_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "certificados_laborales")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "CERTLAB"
        ruta = os.path.join(folder, f"CERT_LABORAL_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Certificado laboral")
    usable_w = doc.width
    sty = E.estilos()

    razon = str(datos.get("razon_social") or "—")
    nombre = str(datos.get("nombre") or "—")
    finalidad = datos.get("finalidad") or FINALIDADES[0]

    story = [
        Paragraph("CERTIFICADO LABORAL", sty["tit"]),
        Paragraph(f"Emitido el {datetime.now().strftime('%d/%m/%Y')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        Paragraph(f"Por la presente se <b>CERTIFICA</b> que <b>{nombre}</b> presta (o ha prestado) sus "
                  f"servicios en <b>{razon}</b> en las condiciones que se detallan a continuación:",
                  sty["just"]),
        Spacer(1, 3 * mm),
        E.seccion("Datos del certificado", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(CONTENIDO_CAMPOS, datos, usable_w, sty), Spacer(1, 1.5 * mm),
    ]
    if str(datos.get("funciones") or "").strip():
        story.append(E.grid_datos([FUNCIONES_CAMPO], datos, usable_w, sty, cols=1))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f"Y para que así conste y surta los efectos oportunos ante <b>{finalidad}</b>, se expide el "
        f"presente certificado a petición del interesado/a.", sty["just"]))
    story.append(Spacer(1, 3 * mm))

    lugar = str(datos.get("lugar") or "—")
    fecha = str(datos.get("fecha_expedicion") or datetime.now().strftime("%d/%m/%Y"))
    story.append(Paragraph(f"En {lugar}, a {fecha}.", sty["just"]))
    story.append(Spacer(1, 4 * mm))

    rep = str(datos.get("representante_empresa") or "—")
    cargo = str(datos.get("cargo") or "")
    firma_val = f"{rep}<br/>{cargo}<br/>(Firma y sello de la empresa)" if cargo else \
        f"{rep}<br/>(Firma y sello de la empresa)"
    story.append(E.firmas_cols(usable_w, sty, [("Por la empresa", firma_val)]))
    doc.build(story)
    return ruta
