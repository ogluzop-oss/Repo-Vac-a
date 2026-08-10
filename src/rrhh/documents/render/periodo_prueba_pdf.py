"""
Generador AUTÓNOMO de la CARTA DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA en PDF — diseño limpio B/N,
Segoe UI bold y tablas con esquinas redondeadas (helpers de `estilo_pdf`). Recibe `datos` del
formulario inline. Extinción dentro del período de prueba (art. 14 ET).
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

RECIBI_ESTADOS = ["Recibí", "No conforme", "Negativa a firmar"]
ESTADO_BIEN = ["No aplica", "Devuelto", "Pendiente"]

EMPRESA_CAMPOS = [("razon_social", "Razón social"), ("cif", "CIF"), ("domicilio", "Domicilio")]
TRABAJADOR_CAMPOS = [("nombre", "Nombre"), ("nif", "DNI"), ("puesto", "Puesto")]
CONTRATO_CAMPOS = [
    ("fecha_alta", "Fecha de alta"), ("tipo_contrato", "Tipo de contrato"),
    ("duracion_periodo_prueba", "Duración del período de prueba"),
    ("clausula_contractual", "Cláusula contractual que lo establece"),
    ("convenio", "Convenio colectivo aplicable"),
]
COMUNICACION_CAMPOS = [
    ("fecha_comunicacion", "Fecha de comunicación"), ("fecha_efectos", "Fecha de efectos"),
]
EXPLICACION_CAMPO = ("explicacion", "Explicación (opcional — no obligatoria)")
LIQUIDACION_CAMPOS = [
    ("salarios_pendientes", "Salarios pendientes"),
    ("vacaciones_no_disfrutadas", "Vacaciones no disfrutadas"),
    ("pp_pagas_extra", "Parte proporcional de pagas extraordinarias"),
    ("otras_cantidades", "Otras cantidades devengadas"),
    ("finiquito_info", "Finiquito"), ("fecha_pago", "Fecha de pago"),
]
BIENES_CAMPOS = [
    ("bien_llaves", "Llaves"), ("bien_tarjetas", "Tarjetas de acceso"),
    ("bien_equipos", "Equipos informáticos"), ("bien_movil", "Teléfono móvil"),
    ("bien_vehiculo", "Vehículo"), ("bien_uniformes", "Uniformes"),
    ("bien_herramientas", "Herramientas"), ("bien_documentacion", "Documentación"),
    ("bien_otros", "Otros bienes asignados"),
]
TESTIGOS_CAMPO = ("testigos", "Testigos (opcional)")


def generar_periodo_prueba_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "periodo_prueba")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "PRUEBA"
        ruta = os.path.join(folder, f"PERIODO_PRUEBA_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="No superación período de prueba")
    usable_w = doc.width
    sty = E.estilos()

    nombre = str(datos.get("nombre") or "—")
    convenio = str(datos.get("convenio") or "").strip()
    fecha_ef = str(datos.get("fecha_efectos") or "—")
    fecha_com = str(datos.get("fecha_comunicacion") or datetime.now().strftime("%d/%m/%Y"))

    manifiesto = (
        f"Muy Sr./Sra. <b>{nombre}</b>:<br/><br/>Por medio de la presente le comunicamos que <b>NO HA "
        f"SUPERADO el período de prueba</b> establecido en su contrato de trabajo. En consecuencia, se "
        f"procede a la <b>extinción de la relación laboral con efectos del {fecha_ef}</b>, produciéndose "
        f"dicha extinción <b>dentro del período de prueba vigente</b>, al amparo del <b>artículo 14 del "
        f"Estatuto de los Trabajadores</b>"
        + (f" y del convenio colectivo aplicable ({convenio})" if convenio else "")
        + ".<br/><br/>Conforme a la normativa, la decisión adoptada durante el período de prueba no "
        "requiere motivación."
    )

    story = [
        Paragraph("COMUNICACIÓN DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA", sty["tit"]),
        Paragraph(f"Fecha de comunicación: {fecha_com}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del contrato", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(CONTRATO_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Comunicación", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(COMUNICACION_CAMPOS, datos, usable_w, sty), Spacer(1, 2 * mm),
        Paragraph(manifiesto, sty["just"]), Spacer(1, 2 * mm),
    ]
    if str(datos.get("explicacion") or "").strip():
        story.append(E.grid_datos([EXPLICACION_CAMPO], datos, usable_w, sty, cols=1))
    story.append(Spacer(1, 3 * mm))

    story += [
        E.seccion("Liquidación", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(LIQUIDACION_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Devolución de bienes de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(BIENES_CAMPOS, datos, usable_w, sty), Spacer(1, 5 * mm),
    ]

    recibi = datos.get("recibi_estado") or RECIBI_ESTADOS[0]
    rep = str(datos.get("representante_empresa") or "—")
    cargo = str(datos.get("cargo") or "")
    emp_val = f"{rep}<br/>{cargo}" if cargo else rep
    columnas = [("Por la empresa", emp_val), (f"El/la trabajador/a — {recibi}", nombre)]
    if str(datos.get("testigos") or "").strip():
        columnas.append(("Testigos", str(datos.get("testigos"))))
    story.append(E.firmas_cols(usable_w, sty, columnas))
    doc.build(story)
    return ruta
