"""
Generador AUTÓNOMO del FINIQUITO (liquidación de saldo y finiquito) en PDF — diseño limpio B/N,
Segoe UI bold y tablas con esquinas redondeadas (helpers de `estilo_pdf`). Recibe `datos` (campos del
formulario inline). Calcula el total bruto (Σ conceptos), las retenciones (IRPF sobre la parte
salarial; la indemnización legal se considera exenta) y el total líquido.
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

MOTIVOS = ["Despido", "Baja voluntaria", "Fin de contrato", "Jubilación", "Fallecimiento", "Incapacidad"]
TIPOS_DESPIDO = ["—", "Disciplinario", "Objetivo", "Improcedente", "Colectivo (ERE)"]
DECLARACION = ["Recibí y conformidad", "No conforme"]

EMPRESA_CAMPOS = [("razon_social", "Razón social"), ("cif", "CIF"), ("domicilio", "Domicilio")]
TRABAJADOR_CAMPOS = [
    ("nombre", "Nombre"), ("nif", "DNI"), ("num_ss", "NSS"),
    ("categoria", "Categoría"), ("antiguedad", "Antigüedad"),
]
EXTINCION_CAMPOS = [
    ("fecha_baja", "Fecha de baja"), ("fecha_efectos", "Fecha de efectos"),
    ("motivo_extincion", "Motivo de extinción"), ("tipo_despido", "Tipo de despido"),
]
# Detalle informativo de los conceptos (días/unidades).
DETALLE_CAMPOS = [
    ("dias_trabajados", "Días trabajados"), ("vac_generadas", "Vacaciones generadas"),
    ("vac_disfrutadas", "Vacaciones disfrutadas"), ("vac_pendientes", "Vacaciones pendientes"),
    ("pagas_devengadas", "Pagas devengadas"), ("pagas_prorrateadas", "Pagas prorrateadas"),
    ("pagas_pendientes", "Pagas pendientes"), ("dias_indemnizacion", "Días de indemnización"),
    ("salario_regulador", "Salario regulador"), ("base_calculo", "Base de cálculo"),
]
# Importes de cada concepto (para el cálculo del total).
CONCEPTOS_IMPORTE = [
    ("imp_salario_pendiente", "Salario pendiente"), ("imp_vacaciones", "Vacaciones pendientes"),
    ("imp_pagas", "Pagas extraordinarias pendientes"), ("imp_horas_extras", "Horas extraordinarias"),
    ("imp_bonus", "Bonus"), ("imp_incentivos", "Incentivos"), ("imp_comisiones", "Comisiones"),
    ("imp_indemnizacion", "Indemnización"),
]
DESCUENTOS_IMPORTE = [
    ("desc_anticipos", "Anticipos"), ("desc_embargos", "Embargos"), ("desc_otros", "Otros"),
]
RETENCION_CAMPO = ("retencion_pct", "Retención IRPF (%)")
TESTIGOS_CAMPO = ("testigos", "Testigos (opcional)")


def _n(datos, clave):
    from src.rrhh.nomina_servicio import num
    return num(datos.get(clave))


def generar_finiquito_pdf(datos: dict, ruta: str = None) -> str:
    datos = datos or {}
    if not ruta:
        folder = os.path.join(os.getcwd(), "documentos", "finiquitos")
        os.makedirs(folder, exist_ok=True)
        cod = datos.get("nif") or "FINIQUITO"
        ruta = os.path.join(folder, f"FINIQUITO_{cod}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="Finiquito")
    usable_w = doc.width
    sty = E.estilos()

    conceptos = [(et, _n(datos, k)) for k, et in CONCEPTOS_IMPORTE if _n(datos, k)]
    total_bruto = round(sum(v for _, v in conceptos), 2)
    imp_indem = _n(datos, "imp_indemnizacion")
    base_ret = max(0.0, total_bruto - imp_indem)                 # indemnización legal exenta
    ret_pct = _n(datos, "retencion_pct")
    retenciones = round(base_ret * ret_pct / 100.0, 2)
    descuentos = [(et, _n(datos, k)) for k, et in DESCUENTOS_IMPORTE if _n(datos, k)]
    total_desc = round(sum(v for _, v in descuentos), 2)
    total_liquido = round(total_bruto - retenciones - total_desc, 2)

    story = [
        Paragraph("RECIBO DE FINIQUITO Y LIQUIDACIÓN DE SALDO", sty["tit"]),
        Paragraph(f"Emitido el {datetime.now().strftime('%d/%m/%Y')}", sty["sub"]),
        Spacer(1, 4 * mm),
        E.seccion("Datos de la empresa", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EMPRESA_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Datos del trabajador/a", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(TRABAJADOR_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Extinción de la relación laboral", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(EXTINCION_CAMPOS, datos, usable_w, sty), Spacer(1, 3 * mm),
        E.seccion("Conceptos de la liquidación", usable_w, sty), Spacer(1, 1.5 * mm),
        E.grid_datos(DETALLE_CAMPOS, datos, usable_w, sty), Spacer(1, 2 * mm),
        E.tabla_importes("CONCEPTOS DEVENGADOS", conceptos, "A · TOTAL BRUTO", total_bruto, usable_w, sty),
        Spacer(1, 3 * mm),
        E.seccion("Deducciones", usable_w, sty), Spacer(1, 1.5 * mm),
    ]
    if descuentos:
        story.append(E.tabla_importes("DESCUENTOS", descuentos, "Subtotal descuentos", total_desc,
                                      usable_w, sty))
        story.append(Spacer(1, 2 * mm))
    story.append(E.total_row(f"Retención IRPF ({ret_pct:.1f}%)", retenciones, usable_w, sty, fuerte=False))
    story.append(Spacer(1, 2 * mm))
    story.append(E.total_row("B · TOTAL DEDUCCIONES", round(retenciones + total_desc, 2), usable_w, sty))
    story.append(Spacer(1, 3 * mm))
    story.append(E.liquido_box("TOTAL LÍQUIDO A PERCIBIR (A − B)", total_liquido, usable_w, sty))
    story.append(Spacer(1, 4 * mm))

    # Declaración.
    decl = datos.get("declaracion") or DECLARACION[0]
    story.append(E.seccion("Declaración", usable_w, sty)); story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        f"El/la trabajador/a manifiesta: <b>{decl}</b>. Con la firma del presente recibo, y salvo "
        f"indicación en contra, las partes declaran saldada y finiquitada la relación laboral, sin "
        f"nada más que reclamarse por ningún concepto derivado de la misma.", sty["just"]))
    story.append(Spacer(1, 4 * mm))

    columnas = [("Firma de la empresa", str(datos.get("razon_social") or "—")),
                ("Firma del trabajador/a", str(datos.get("nombre") or "—"))]
    if str(datos.get("testigos") or "").strip():
        columnas.append(("Testigos", str(datos.get("testigos"))))
    story.append(E.firmas_cols(usable_w, sty, columnas))
    doc.build(story)
    return ruta
