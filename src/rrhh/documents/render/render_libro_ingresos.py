"""
Render documental fiscal `render_libro_ingresos` — Libro de Ingresos (Contabilidad · pestaña
"Libro de Ingresos"). Consulta facturas de cliente REALES
(`src.db.facturas_cliente.listar_facturas`) del período indicado — antes caía en
`render_generico` (una línea estática, sin consulta alguna). Si no hay facturas en el rango, se
muestra ese hecho tal cual (dato real, no se inventa contenido).

Segunda sección (Smart Suppliers B2B): rappels/rebates retroactivos de proveedor ya LIQUIDADOS
(`services.compras.b2b_rappels.listar_liquidaciones`), filtrados por `fecha_liquidacion` (momento
real del abono, no la ventana de acumulación `fecha_inicio`/`fecha_fin`, que puede ser todo el
ejercicio). Honestidad: un rappel de COMPRAS es, por el PGC, una reducción de gasto (contra-cuenta
600), NO un ingreso de cliente — se muestra en sección PROPIA, con etiqueta explícita, y JAMÁS se
suma al total de facturas de cliente de arriba. Se incluye aquí porque así lo pide el producto
(dinero que vuelve a la empresa en el período), no porque sea técnicamente "ingreso".
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
    import datetime as _dt

    from src.db import clientes as _CLI
    from src.db import facturas_cliente as _FC

    id_empresa = self._datos.get("id_empresa")
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

    facturas = [f for f in (_FC.listar_facturas(id_empresa=id_empresa, limite=1000) or [])
               if _en_rango(f.get("fecha_emision"))]

    story.append(_sec_header(f"LIBRO DE INGRESOS — período {periodo_ini or '(inicio)'} a "
                             f"{periodo_fin or '(hoy)'}"))
    story.append(Spacer(1, 2 * mm))
    if not facturas:
        story.append(_P("No se han encontrado facturas emitidas en el período indicado.", st_body))
    else:
        _nombres = {}
        filas = [["Nº factura", "Fecha", "Cliente", "Base", "IVA", "Total"]]
        tb = tiva = tt = 0.0
        for f in facturas:
            fe = f.get("fecha_emision")
            fe_s = fe.strftime("%d/%m/%Y") if hasattr(fe, "strftime") else str(fe or "")
            idc = f.get("id_cliente")
            if idc not in _nombres:
                try:
                    _nombres[idc] = (_CLI.obtener_cliente(idc) or {}).get("nombre") or f"#{idc}"
                except Exception:
                    _nombres[idc] = f"#{idc}" if idc else "—"
            base = float(f.get("base") or 0)
            iva = float(f.get("iva") or 0)
            tot = float(f.get("total") or 0)
            tb += base; tiva += iva; tt += tot
            filas.append([str(f.get("numero") or ""), fe_s, _nombres[idc],
                         f"{base:.2f}", f"{iva:.2f}", f"{tot:.2f}"])
        filas.append(["", "", "TOTAL", f"{tb:.2f}", f"{tiva:.2f}", f"{tt:.2f}"])
        t = Table(filas, colWidths=[usable_w * 0.16, usable_w * 0.14, usable_w * 0.30,
                                    usable_w * 0.16, usable_w * 0.12, usable_w * 0.12])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLR),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDE_OSC),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
            ("FONTNAME", (0, -1), (-1, -1), _FB),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)

    # ── Rappels de proveedores liquidados (rebates retroactivos B2B) ────────────────────────
    from src.services.compras import b2b_rappels as _RAP

    def _fmt_fecha(d):
        try:
            return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d or "")
        except Exception:
            return str(d or "")

    liquidaciones = [r for r in (_RAP.listar_liquidaciones(id_empresa=id_empresa, limite=1000) or [])
                     if float(r.get("importe_rebate") or 0) > 0 and _en_rango(r.get("fecha_liquidacion"))]

    story.append(Spacer(1, 5 * mm))
    story.append(_sec_header("RAPPELS DE PROVEEDORES LIQUIDADOS (rebates retroactivos B2B) — "
                             "reducción de gasto de compras, NO ingreso de cliente"))
    story.append(Spacer(1, 2 * mm))
    if not liquidaciones:
        story.append(_P("No se han liquidado rappels de proveedores en el período indicado.", st_body))
    else:
        from src.services.compras import suministradores as _SUM
        _nombres_sum = {}
        filas_r = [["Suministrador", "Periodo acumulado", "Fecha liquidación",
                   "Gasto base", "% rebate", "Importe rebate"]]
        tr = 0.0
        for r in liquidaciones:
            idsum = r.get("id_suministrador")
            if idsum not in _nombres_sum:
                try:
                    _nombres_sum[idsum] = (_SUM.obtener(idsum) or {}).get("razon_social") or f"#{idsum}"
                except Exception:
                    _nombres_sum[idsum] = f"#{idsum}" if idsum else "—"
            importe = float(r.get("importe_rebate") or 0)
            tr += importe
            filas_r.append([
                _nombres_sum[idsum],
                f"{_fmt_fecha(r.get('fecha_inicio'))} a {_fmt_fecha(r.get('fecha_fin'))}",
                _fmt_fecha(r.get("fecha_liquidacion")),
                f"{float(r.get('gasto_total') or 0):.2f}",
                f"{float(r.get('pct_aplicado') or 0):.2f}%",
                f"{importe:.2f}",
            ])
        filas_r.append(["", "", "", "", "TOTAL RAPPELS", f"{tr:.2f}"])
        t_rap = Table(filas_r, colWidths=[usable_w * 0.22, usable_w * 0.24, usable_w * 0.16,
                                          usable_w * 0.14, usable_w * 0.10, usable_w * 0.14])
        t_rap.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLR),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDE_OSC),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
            ("FONTNAME", (0, -1), (-1, -1), _FB),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t_rap)

    if obs:
        story.append(Spacer(1, 3 * mm))
        story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))


def render_libro_ingresos(ctx):
    ejecutar(_impl, ctx)
