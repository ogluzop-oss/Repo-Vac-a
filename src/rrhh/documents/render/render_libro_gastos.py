"""
Render documental fiscal `render_libro_gastos` — Libro de Gastos (Contabilidad · pestaña "Libro de
Gastos"). Consulta el gasto REAL COMPLETO del período indicado vía
`src.services.contabilidad.posting.listar_gastos_completo` (FASE B): une las altas manuales de la
pestaña "Gastos" (origen='manual') CON las facturas de compra reales de `compras_facturas`
(origen='compra') — antes solo mostraba las primeras (`listar_gastos`), dejando fuera el grueso del
gasto real de la empresa. Cada fila indica su origen para que no haya confusión sobre su procedencia.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
    import datetime as _dt

    from src.services.contabilidad import posting as _Pg

    id_empresa = self._datos.get("id_empresa")
    anio = self._datos.get("anio")
    periodo_ini = (self._datos.get("periodo_ini") or "").strip()
    periodo_fin = (self._datos.get("periodo_fin") or "").strip()

    def _en_rango(f):
        if not f:
            return False
        try:
            fd = f if hasattr(f, "year") else _dt.datetime.strptime(str(f), "%Y-%m-%d")
            di = _dt.datetime.strptime(periodo_ini, "%d/%m/%Y") if periodo_ini else None
            dfin = _dt.datetime.strptime(periodo_fin, "%d/%m/%Y") if periodo_fin else None
            if di and fd.date() < di.date():
                return False
            if dfin and fd.date() > dfin.date():
                return False
            return True
        except Exception:
            return True

    gastos = [g for g in (_Pg.listar_gastos_completo(anio=anio, id_empresa=id_empresa) or [])
             if _en_rango(g.get("fecha"))]

    story.append(_sec_header(f"LIBRO DE GASTOS — período {periodo_ini or '(inicio)'} a "
                             f"{periodo_fin or '(hoy)'}"))
    story.append(Spacer(1, 2 * mm))
    if not gastos:
        story.append(_P("No se han encontrado gastos registrados en el período indicado.", st_body))
    else:
        _ORIGEN_ETIQUETA = {"manual": "Manual", "compra": "Fra. proveedor"}
        filas = [["Nº", "Fecha", "Concepto", "Importe", "Estado", "Origen"]]
        total = 0.0
        for g in gastos:
            fe = g.get("fecha")
            fe_s = fe.strftime("%d/%m/%Y") if hasattr(fe, "strftime") else str(fe or "")
            imp = float(g.get("importe") if g.get("importe") is not None else g.get("total_debe") or 0)
            total += imp
            filas.append([str(g.get("numero") or ""), fe_s, str(g.get("concepto") or ""),
                         f"{imp:.2f}", str(g.get("estado") or ""),
                         _ORIGEN_ETIQUETA.get(g.get("origen"), g.get("origen") or "")])
        filas.append(["", "", "TOTAL", f"{total:.2f}", "", ""])
        t = Table(filas, colWidths=[usable_w * 0.10, usable_w * 0.12, usable_w * 0.36,
                                    usable_w * 0.14, usable_w * 0.14, usable_w * 0.14])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLR),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDE_OSC),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
            ("FONTNAME", (0, -1), (-1, -1), _FB),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
    if obs:
        story.append(Spacer(1, 3 * mm))
        story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))


def render_libro_gastos(ctx):
    ejecutar(_impl, ctx)
