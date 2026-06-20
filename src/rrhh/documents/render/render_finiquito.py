"""Render documental RRHH `render_finiquito` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_finiquito` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        story.append(_sec_header("LIQUIDACIÓN Y FINIQUITO"))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DEL EMPLEADOR"))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
        story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(("PUESTO", puesto or "—"), ("FECHA EXTINCIÓN", fecha)))
        story.append(Spacer(1, 2*mm))
        story.append(_P(
            f"La empresa <b>{emp_nombre}</b> (CIF: {emp_cif}) y el/la trabajador/a "
            f"<b>{trab}</b> (NIF/NIE: {nif}) acuerdan la extinción definitiva de la relación "
            f"laboral con efectos del <b>{fecha}</b>, procediéndose a la liquidación y finiquito "
            "de los haberes pendientes conforme al siguiente desglose:",
            st_body
        ))
        story.append(Spacer(1, 2*mm))
        fin_th = _st("fth", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
        fin_data = [
            [Paragraph(self._pdf_tr("CONCEPTO"), fin_th), Paragraph(self._pdf_tr("IMPORTE (€)"), _st("fthc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER))],
            [self._pdf_tr("Vacaciones no disfrutadas"), "___________"],
            [self._pdf_tr("Parte proporcional pagas extraordinarias"), "___________"],
            [self._pdf_tr("Salarios pendientes de pago"), "___________"],
            [self._pdf_tr("Indemnización por extinción"), "___________"],
            [self._pdf_tr("Otros conceptos"), "___________"],
            [
                Paragraph("<b>"+self._pdf_tr("TOTAL FINIQUITO")+"</b>", _st("ft", fontName=_FB, fontSize=9, textColor=NEGRO, leading=11)),
                Paragraph("<b>___________</b>", _st("ft2", fontName=_FB, fontSize=9, textColor=NEGRO, leading=11, alignment=TA_CENTER)),
            ],
        ]
        fin_tbl = Table(fin_data, colWidths=[usable_w*0.7, usable_w*0.3])
        fin_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), GRIS_CLR),
            ("FONTNAME", (0,1),(-1,-2), _FN),
            ("FONTSIZE", (0,0),(-1,-1), 8.5),
            ("ALIGN", (1,0),(-1,-1), "CENTER"),
            ("GRID", (0,0),(-1,-1), 0.4, BORDE),
            ("BOX", (0,0),(-1,-1), 0.8, BORDE_OSC),
            ("ROWBACKGROUNDS", (0,1),(-1,-2), [BLANCO, HexColor("#F7F7F7")]),
            ("BACKGROUND", (0,-1),(-1,-1), AZUL_CLR),
            ("LINEABOVE", (0,-1),(-1,-1), 1.5, AZUL),
            ("TOPPADDING", (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING", (0,0),(-1,-1), 6),
            ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ]))
        story.append(fin_tbl)
        if obs:
            story.append(Spacer(1, 3*mm))
            story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))
        story.append(Spacer(1, 3*mm))
        story.append(_P(
            "El/La trabajador/a declara recibir la cantidad total correspondiente al finiquito y, "
            "con su firma, reconoce que no tiene ninguna reclamación adicional pendiente contra "
            "la empresa derivada de la relación laboral extinguida, salvo los derechos que "
            "legalmente no sean renunciables.",
            st_body
        ))



def render_finiquito(ctx):
    ejecutar(_impl, ctx)
