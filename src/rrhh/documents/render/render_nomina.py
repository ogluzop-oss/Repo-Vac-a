"""Render documental RRHH `render_nomina` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_nomina` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        try:
            irpf_pct = float(irpf_pct_str.replace(",",".").strip()) if irpf_pct_str else 15.0
        except ValueError:
            irpf_pct = 15.0
        try:
            ss_emp_pct = float(ss_pct_str.replace(",",".").strip()) if ss_pct_str else 6.35
        except ValueError:
            ss_emp_pct = 6.35
        try:
            plus_conv = float(plus_convenio_str.replace(",",".").strip()) if plus_convenio_str else 0.0
        except ValueError:
            plus_conv = 0.0
        try:
            horas_ext = float(horas_extras_str.replace(",",".").strip()) if horas_extras_str else 0.0
        except ValueError:
            horas_ext = 0.0
        sal_base    = salario_mensual if salario_mensual > 0 else salario
        irpf_ret    = round(sal_base * irpf_pct / 100, 2)
        ss_ret      = round(sal_base * ss_emp_pct / 100, 2)
        bruto_total = round(sal_base + plus_conv + horas_ext, 2)
        neto        = round(bruto_total - irpf_ret - ss_ret, 2)

        story.append(_sec_header("DATOS DEL EMPLEADOR"))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(_data_val_row(("DOMICILIO", emp_dir), ("CCC", emp_ccc or "—")))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
        story.append(_data_val_row(("TRABAJADOR/A", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(
            ("Nº SEG. SOCIAL", ss or "—"),
            ("PERÍODO", fecha),
            ("Nº PAGAS", num_pagas),
        ))
        story.append(_data_val_row(("CATEGORÍA/PUESTO", puesto or "—"), ("GRUPO PROF.", grupo_prof or "—")))
        story.append(Spacer(1, 2*mm))
        story.append(_sec_header("DESGLOSE DE NÓMINA"))
        th = _st("th", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
        th_c = _st("thc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)
        nom_data = [
            [Paragraph(self._pdf_tr("CONCEPTO"), th), Paragraph(self._pdf_tr("DEVENGOS"), th_c), Paragraph(self._pdf_tr("DEDUCCIONES"), th_c)],
            ["Salario base", f"{divisas.formatear(sal_base)}", ""],
            ["Plus convenio", f"{divisas.formatear(plus_conv)}" if plus_conv else "—", ""],
            ["Horas extras", f"{divisas.formatear(horas_ext)}" if horas_ext else "—", ""],
            [f"Retención IRPF ({irpf_pct:.1f}%)", "", f"{divisas.formatear(irpf_ret)}"],
            [f"Cuota S.S. trabajador ({ss_emp_pct:.2f}%)", "", f"{divisas.formatear(ss_ret)}"],
            [
                Paragraph("<b>"+self._pdf_tr("TOTAL BRUTO / TOTAL DEDUCCIONES")+"</b>", _st("tb", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)),
                Paragraph(f"<b>{divisas.formatear(bruto_total)}</b>", _st("tb2", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
                Paragraph(f"<b>{divisas.formatear(irpf_ret+ss_ret)}</b>", _st("tb3", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
            ],
            [
                Paragraph("<b>"+self._pdf_tr("LÍQUIDO A PERCIBIR")+"</b>", _st("liq", fontName=_FB, fontSize=10, textColor=AZUL, leading=12)),
                Paragraph(f"<b>{divisas.formatear(neto)}</b>", _st("liq2", fontName=_FB, fontSize=10, textColor=AZUL, leading=12, alignment=TA_CENTER)),
                "",
            ],
        ]
        nom_tbl = Table(nom_data, colWidths=[usable_w*0.55, usable_w*0.225, usable_w*0.225])
        nom_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), GRIS_CLR),
            ("FONTNAME", (0,1),(-1,-3), _FN),
            ("FONTSIZE", (0,1),(-1,-1), 8.5),
            ("ALIGN", (1,0),(-1,-1), "CENTER"),
            ("GRID", (0,0),(-1,-1), 0.4, BORDE),
            ("BOX", (0,0),(-1,-1), 0.8, BORDE_OSC),
            ("ROWBACKGROUNDS", (0,1),(-1,-3), [BLANCO, HexColor("#F7F7F7")]),
            ("BACKGROUND", (0,-2),(-1,-2), GRIS_CLR),
            ("BACKGROUND", (0,-1),(-1,-1), AZUL_CLR),
            ("LINEABOVE", (0,-2),(-1,-2), 1.0, BORDE_OSC),
            ("LINEABOVE", (0,-1),(-1,-1), 1.5, AZUL),
            ("TOPPADDING", (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING", (0,0),(-1,-1), 6),
            ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ]))
        story.append(nom_tbl)
        story.append(Spacer(1, 3*mm))
        story.append(_P(
            f"IBAN: {emp_iban or '—'}  ·  Convenio: {convenio or '—'}  ·  "
            f"Generado: {now.strftime('%d/%m/%Y')}",
            st_center
        ))



def render_nomina(ctx):
    ejecutar(_impl, ctx)
