"""
Render documental fiscal `render_informe_auditoria` — Informe de Auditoría (Contabilidad ·
pestaña "Informe Auditoría"). Consulta eventos REALES de `auditoria_logs`
(`src.db.auditoria.listar_por_tabla`) del período y ámbito (subtipo) elegidos — antes caía en
`render_generico` (una línea estática, sin consulta alguna).

No existe hoy una taxonomía oficial CAJA/RRHH/ACCESOS/MOVIMIENTOS/DOCUMENTOS en `tabla_afectada`
— el mapeo de abajo es de MEJOR ESFUERZO, basado en las tablas realmente usadas por `log_auditoria`
en el resto de la app (no es una clasificación oficial). Si un ámbito no tiene eventos reales en el
período, la tabla sale vacía con un aviso — dato real, no se inventa contenido.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
    import datetime as _dt

    from src.db import auditoria as _AUD

    # LOCAL a `_impl` a propósito (no a nivel de módulo): `contexto.ejecutar` reconstruye esta
    # función con un `__globals__` distinto (el `ctx` capturado del wizard) — una constante a nivel
    # de módulo de ESTE archivo no sería visible desde dentro (confirmado en pruebas reales).
    mapeo_subtipo = {
        "CAJA": (["tpv", "stock"], "ABRIR_STOCK%"),
        "RRHH": (["rrhh"], "RRHH%"),
        "ACCESOS": (["mfa", "sesiones", "incidentes_seguridad", "rgpd_solicitudes"], "LOGIN%"),
        "MOVIMIENTOS": (["tesoreria", "conciliaciones", "pagos_proveedor", "remesas_sepa",
                        "workflow"], None),
        "DOCUMENTOS": (["storage", "facturas_cliente"], None),
    }

    id_empresa = self._datos.get("id_empresa")
    periodo_ini = (self._datos.get("periodo_ini") or "").strip()
    periodo_fin = (self._datos.get("periodo_fin") or "").strip()
    ambito = (self._datos.get("subtipo") or "").strip().upper()

    def _iso(txt):
        try:
            return _dt.datetime.strptime(txt, "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            return None

    tablas, accion_like = mapeo_subtipo.get(ambito, ([], None))
    eventos = _AUD.listar_por_tabla(tablas, desde=_iso(periodo_ini), hasta=_iso(periodo_fin),
                                    accion_like=accion_like, id_empresa=id_empresa, limite=500)

    story.append(_sec_header(f"INFORME DE AUDITORÍA — ámbito {ambito or '(general)'} — período "
                             f"{periodo_ini or '(inicio)'} a {periodo_fin or '(hoy)'}"))
    story.append(Spacer(1, 2 * mm))
    if not eventos:
        story.append(_P("No se han registrado eventos de auditoría en este ámbito y período.",
                        st_body))
    else:
        filas = [["Fecha", "Usuario", "Acción", "Detalles"]]
        for e in eventos:
            fe = e.get("fecha")
            fe_s = fe.strftime("%d/%m/%Y %H:%M") if hasattr(fe, "strftime") else str(fe or "")
            filas.append([fe_s, str(e.get("usuario") or ""), str(e.get("accion") or ""),
                         str(e.get("detalles") or "")[:80]])
        t = Table(filas, colWidths=[usable_w * 0.16, usable_w * 0.16, usable_w * 0.22, usable_w * 0.46])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLR),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDE_OSC),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ]))
        story.append(t)
    if obs:
        story.append(Spacer(1, 3 * mm))
        story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))


def render_informe_auditoria(ctx):
    ejecutar(_impl, ctx)
