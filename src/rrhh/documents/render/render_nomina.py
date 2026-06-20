"""
Render del RECIBO OFICIAL DE SALARIOS (F4.8, inspirado en Orden ESS/2098/2014).

YA NO CALCULA: invoca el motor único (`nomina_servicio.calcular_desde_datos`) y solo
FORMATEA el `NominaResultado`. Bloques: encabezado (empresa/trabajador/período),
devengos (salariales / no salariales), deducciones (SS por contingencia / IRPF / otras),
determinación de bases, aportación empresarial (informativa), resumen (líquido destacado)
y recibí. El epílogo del wizard añade firmas/nota/hash (compartido). Nombres libres
resueltos desde `ctx` (scope del wizard) vía `contexto.ejecutar`.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        # Definidos DENTRO de _impl: el cuerpo se ejecuta con ctx como globals (los
        # nombres de módulo no son visibles), así que las tablas de contingencias
        # deben ser locales.
        _SS_TRAB = [("comunes", "Contingencias comunes"), ("desempleo", "Desempleo"),
                    ("fp", "Formación profesional"), ("mei", "MEI"), ("horas_extra", "Horas extra")]
        _SS_EMP = [("comunes", "Contingencias comunes"), ("desempleo", "Desempleo"),
                   ("fp", "Formación profesional"), ("fogasa", "FOGASA"), ("at_ep", "AT/EP"),
                   ("mei", "MEI"), ("horas_extra", "Horas extra")]
        from src.rrhh.nomina_servicio import calcular_desde_datos
        res = calcular_desde_datos(self._datos)
        eur = divisas.formatear

        th = _st("th", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
        thc = _st("thc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)
        cell = _st("cell", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10)
        cellr = _st("cellr", fontName=_FN, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_RIGHT)
        bold = _st("boldc", fontName=_FB, fontSize=8.5, textColor=NEGRO, leading=11)
        boldr = _st("boldr", fontName=_FB, fontSize=8.5, textColor=NEGRO, leading=11, alignment=TA_RIGHT)

        def _tbl_conceptos(titulo, filas, total_lbl, total_val):
            data = [[Paragraph(self._pdf_tr(titulo), th), Paragraph(self._pdf_tr("IMPORTE"), thc)]]
            for concepto, importe in filas:
                data.append([Paragraph(self._pdf_tr(concepto), cell), Paragraph(eur(importe), cellr)])
            data.append([Paragraph("<b>" + self._pdf_tr(total_lbl) + "</b>", bold),
                         Paragraph("<b>" + eur(total_val) + "</b>", boldr)])
            t = Table(data, colWidths=[usable_w * 0.70, usable_w * 0.30])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLR),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDE_OSC),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [BLANCO, HexColor("#F7F7F7")]),
                ("BACKGROUND", (0, -1), (-1, -1), GRIS_CLR),
                ("LINEABOVE", (0, -1), (-1, -1), 1.0, BORDE_OSC),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            return t

        # ── 1) ENCABEZADO ──────────────────────────────────────────────────────
        story.append(_sec_header("RECIBO INDIVIDUAL JUSTIFICATIVO DEL PAGO DE SALARIOS"))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(_data_val_row(("DOMICILIO", emp_dir), ("C.C.C.", emp_ccc or "—")))
        story.append(_data_val_row(("TRABAJADOR/A", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(("Nº SEG. SOCIAL", ss or "—"),
                                   ("CATEGORÍA/GRUPO", f"{puesto or '—'} / {grupo_prof or '—'}")))
        story.append(_data_val_row(("PERÍODO DE LIQUIDACIÓN", fecha), ("Nº PAGAS", num_pagas),
                                   ("EMISIÓN", now.strftime("%d/%m/%Y"))))
        story.append(Spacer(1, 2 * mm))

        # ── 2) DEVENGOS (salariales / no salariales) ────────────────────────────
        salariales = [(d["concepto"], d["importe"]) for d in res.devengos
                      if d.get("clase") == "DEVENGO_SALARIAL"]
        no_sal = [(d["concepto"], d["importe"]) for d in res.devengos
                  if d.get("clase") == "DEVENGO_NO_SALARIAL"]
        story.append(_tbl_conceptos("I. DEVENGOS SALARIALES", salariales,
                                    "Subtotal salariales", round(sum(i for _, i in salariales), 2)))
        story.append(Spacer(1, 1 * mm))
        if no_sal:
            story.append(_tbl_conceptos("DEVENGOS NO SALARIALES", no_sal,
                                        "Subtotal no salariales", round(sum(i for _, i in no_sal), 2)))
            story.append(Spacer(1, 1 * mm))
        story.append(_tbl_conceptos("TOTAL DEVENGADO", [], "A. TOTAL DEVENGADO", res.total_devengado))
        story.append(Spacer(1, 2 * mm))

        # ── 3) DEDUCCIONES (SS por contingencia / IRPF / otras) ─────────────────
        ss_filas = [(et, res.ss_trabajador.get(k, 0.0)) for k, et in _SS_TRAB
                    if res.ss_trabajador.get(k, 0.0)]
        story.append(_tbl_conceptos("II. APORTACIONES DEL TRABAJADOR A LA S.S.", ss_filas,
                                    "Subtotal S.S. trabajador", res.ss_trabajador.get("total", 0.0)))
        story.append(Spacer(1, 1 * mm))
        story.append(_tbl_conceptos(f"RETENCIÓN IRPF ({res.irpf_tipo:.1f}%)", [],
                                    "IRPF", res.irpf_importe))
        otras = [(d["concepto"], d["importe"]) for d in res.deducciones
                 if d["concepto"] in ("Anticipos", "Embargos")]
        if otras:
            story.append(Spacer(1, 1 * mm))
            story.append(_tbl_conceptos("OTRAS DEDUCCIONES", otras,
                                        "Subtotal otras", round(sum(i for _, i in otras), 2)))
        story.append(Spacer(1, 1 * mm))
        story.append(_tbl_conceptos("TOTAL A DEDUCIR", [], "B. TOTAL DEDUCCIONES", res.total_deducciones))
        story.append(Spacer(1, 2 * mm))

        # ── 4) DETERMINACIÓN DE BASES ───────────────────────────────────────────
        story.append(_sec_header("DETERMINACIÓN DE LAS BASES DE COTIZACIÓN Y DE RETENCIÓN"))
        story.append(_data_val_row(("BASE C.C. (BCCC)", eur(res.bccc)),
                                   ("BASE C.P. y H.E. (BCCP)", eur(res.bccp))))
        story.append(_data_val_row(("BASE AT/EP", eur(res.base_at_ep)),
                                   ("BASE SUJETA A IRPF", eur(res.base_irpf))))
        story.append(Spacer(1, 2 * mm))

        # ── 5) APORTACIÓN EMPRESARIAL (informativa) ─────────────────────────────
        emp_filas = [(et, res.ss_empresa.get(k, 0.0)) for k, et in _SS_EMP
                     if res.ss_empresa.get(k, 0.0)]
        story.append(_tbl_conceptos("APORTACIÓN DE LA EMPRESA A LA S.S. (informativa)", emp_filas,
                                    "TOTAL COTIZACIÓN EMPRESA", res.ss_empresa.get("total", 0.0)))
        story.append(Spacer(1, 2 * mm))

        # ── 6) RESUMEN / LÍQUIDO (bloque destacado) ─────────────────────────────
        liq_data = [
            [Paragraph("<b>" + self._pdf_tr("A. TOTAL DEVENGADO") + "</b>", bold),
             Paragraph("<b>" + eur(res.total_devengado) + "</b>", boldr)],
            [Paragraph("<b>" + self._pdf_tr("B. TOTAL A DEDUCIR") + "</b>", bold),
             Paragraph("<b>" + eur(res.total_deducciones) + "</b>", boldr)],
            [Paragraph("<b>" + self._pdf_tr("LÍQUIDO TOTAL A PERCIBIR (A − B)") + "</b>",
                       _st("liq", fontName=_FB, fontSize=11, textColor=AZUL, leading=14)),
             Paragraph("<b>" + eur(res.liquido) + "</b>",
                       _st("liqr", fontName=_FB, fontSize=11, textColor=AZUL, leading=14, alignment=TA_RIGHT))],
        ]
        liq = Table(liq_data, colWidths=[usable_w * 0.70, usable_w * 0.30])
        liq.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.2, AZUL),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("BACKGROUND", (0, -1), (-1, -1), AZUL_CLR),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(liq)
        story.append(Spacer(1, 4 * mm))

        # ── 7) RECIBÍ ───────────────────────────────────────────────────────────
        story.append(_sec_header("RECIBÍ"))
        recibi = [
            [Paragraph(self._pdf_tr("El/La trabajador/a (Recibí)"), cell),
             Paragraph(self._pdf_tr("La Empresa"), cell)],
            [Spacer(1, 1.6 * cm), Spacer(1, 1.6 * cm)],
            [Paragraph(f"<b>{trab}</b><br/>{nif}", cell),
             Paragraph(f"<b>{emp_nombre}</b><br/>{emp_cif}", cell)],
        ]
        rt = Table(recibi, colWidths=[usable_w / 2] * 2)
        rt.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, BORDE_OSC),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(rt)
        story.append(Spacer(1, 2 * mm))
        story.append(_P(
            f"IBAN: {emp_iban or '—'}  ·  Convenio: {convenio or '—'}  ·  "
            f"Recibo emitido el {now.strftime('%d/%m/%Y')}",
            st_center))


def render_nomina(ctx):
    ejecutar(_impl, ctx)
