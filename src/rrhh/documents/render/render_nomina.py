"""
Render documental RRHH `render_nomina` (F4.3.4).

YA NO CALCULA: invoca el motor único (`nomina_servicio.calcular_desde_datos`) y solo
FORMATEA el `NominaResultado` (devengos/deducciones/bases/totales). Nombres libres
(story, _sec_header, _data_val_row, divisas, estilos, emp_*, trab…) resueltos desde
`ctx` (scope del wizard) vía `contexto.ejecutar`.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        from src.rrhh.nomina_servicio import calcular_desde_datos
        res = calcular_desde_datos(self._datos)

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
        story.append(_data_val_row(("BASE C.C. (BCCC)", divisas.formatear(res.bccc)),
                                   ("BASE C.P. (BCCP)", divisas.formatear(res.bccp))))
        story.append(Spacer(1, 2*mm))
        story.append(_sec_header("DESGLOSE DE NÓMINA"))
        th = _st("th", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
        th_c = _st("thc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)
        nom_data = [
            [Paragraph(self._pdf_tr("CONCEPTO"), th), Paragraph(self._pdf_tr("DEVENGOS"), th_c),
             Paragraph(self._pdf_tr("DEDUCCIONES"), th_c)],
        ]
        for d in res.devengos:                       # solo formateo (no cálculo)
            nom_data.append([d["concepto"], f"{divisas.formatear(d['importe'])}", ""])
        for d in res.deducciones:
            nom_data.append([d["concepto"], "", f"{divisas.formatear(d['importe'])}"])
        nom_data.append([
            Paragraph("<b>"+self._pdf_tr("TOTAL DEVENGADO / TOTAL DEDUCCIONES")+"</b>",
                      _st("tb", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)),
            Paragraph(f"<b>{divisas.formatear(res.total_devengado)}</b>",
                      _st("tb2", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
            Paragraph(f"<b>{divisas.formatear(res.total_deducciones)}</b>",
                      _st("tb3", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
        ])
        nom_data.append([
            Paragraph("<b>"+self._pdf_tr("LÍQUIDO A PERCIBIR")+"</b>",
                      _st("liq", fontName=_FB, fontSize=10, textColor=AZUL, leading=12)),
            Paragraph(f"<b>{divisas.formatear(res.liquido)}</b>",
                      _st("liq2", fontName=_FB, fontSize=10, textColor=AZUL, leading=12, alignment=TA_CENTER)),
            "",
        ])
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
