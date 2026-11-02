"""
Informe Anual de Empresa (GUI) — diálogo Enterprise sobre `services.contabilidad.informe_anual`.

Solo orquesta: toda la agregación de cifras vive en el servicio (`generar_informe_anual`), este
módulo únicamente renderiza el dict resultante con la librería Enterprise (`gui/components`) sobre
un panel Enterprise (`gui/foundation/shell`) — nada de tablas/tarjetas ad-hoc, conforme a las reglas
de arquitectura de la UI (CLAUDE.md). El export Excel reutiliza el exportador ÚNICO
(`foundation.export.exportar_excel`); el PDF reutiliza el motor reportlab/`estilo_pdf` ya usado por
`contabilidad/cierre_pdf.py` (ver `informe_anual_pdf.py`).
"""

import logging
import os

from PyQt6.QtWidgets import QDialog, QLabel, QScrollArea

from src.gui.catalogo_gestion import _dialogo_frameless
from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid, EnterpriseTable,
                                EnterpriseToolbar)
from src.gui.components.enterprise import EnterpriseInlineBanner  # no reexportado en __init__
from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterprisePanel

logger = logging.getLogger("gui.informe_anual")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _eur(v):
    try:
        from src.utils import divisas
        return divisas.formatear(v)
    except Exception:  # pragma: no cover
        try:
            return f"{float(v or 0):,.2f} €"
        except Exception:
            return str(v)


def _delta_pct(actual, anterior) -> str:
    """% de variación interanual, honesto: 'N/D' (nunca un porcentaje fabricado) si no hay valor
    numérico o el año anterior es cero (división por cero)."""
    try:
        a = float(actual)
        b = float(anterior)
    except (TypeError, ValueError):
        return "N/D"
    if not b:
        return "N/D"
    return f"{(a - b) / abs(b) * 100:+.1f}%"


class _PanelInformeAnual(QtEnterprisePanel):
    """Contenido del informe (panel Enterprise embebido en `InformeAnualDialog`)."""

    titulo = "Informe Anual"

    def __init__(self, anio, *, usuario=None, id_empresa=None, parent=None):
        super().__init__(usuario=usuario, id_empresa=id_empresa, parent=parent)
        self.anio = int(anio)
        self.datos = None

    # ── Carga (perezosa, vía QtEnterprisePanel.cargar_si_necesario) ──────────
    def cargar(self):
        from src.services.contabilidad.informe_anual import generar_informe_anual

        toolbar = EnterpriseToolbar(f"Informe Anual de Empresa · {self.anio}")
        toolbar.add_action("Exportar a Excel", self._exportar_excel, concepto="exportar", color=T.ANALISIS)
        toolbar.add_action("Generar PDF", self._generar_pdf, concepto="exportar", color=T.INFO)
        self.add_toolbar_widget(toolbar)

        try:
            self.datos = generar_informe_anual(self.anio, self.id_empresa)
        except Exception as e:
            logger.error("generar_informe_anual(%s): %s", self.anio, e)
            self.set_status(f"No se pudo generar el informe: {e}", "critico")
            return
        self._render(self.datos)
        self.set_status(f"Informe {self.anio} generado correctamente.", "ok")

    # ── Render ────────────────────────────────────────────────────────────────
    def _render(self, d):
        self._render_ventas(d["ventas"])
        self._render_mermas_devoluciones(d["mermas"], d["devoluciones"])
        self._render_plantilla(d["plantilla"], d["empleados_detalle"])
        self._render_inversion(d["inversion"])
        self._render_pyg(d["pyg"], d["comparacion_interanual"])

    def _render_ventas(self, ventas):
        self.contenido.addWidget(QLabel("Facturación por tienda"))
        t1 = EnterpriseTable(["Tienda", "Nº ventas", "Total"], con_busqueda=False)
        t1.set_datos([{"Tienda": f["tienda"], "Nº ventas": f["num_ventas"], "Total": _eur(f["total"])}
                     for f in ventas["por_tienda"]])
        self.contenido.addWidget(t1)

        self.contenido.addWidget(QLabel("Facturación por empleado"))
        t2 = EnterpriseTable(["Empleado", "Nº ventas", "Total"], con_busqueda=True, pagina=15,
                             contador_abajo=True)
        t2.set_datos([{"Empleado": f.get("empleado"), "Nº ventas": f["num_ventas"], "Total": _eur(f["total"])}
                     for f in ventas["por_empleado"]])
        self.contenido.addWidget(t2)

        grid = EnterpriseDashboardGrid(columnas=3)
        grid.add_card(EnterpriseCard("Total empresa", _eur(ventas["total_empresa"]), modo="kpi"))
        grid.add_card(EnterpriseCard("Total físico (tienda)", _eur(ventas["total_fisico"]), modo="kpi"))
        grid.add_card(EnterpriseCard("Total online", _eur(ventas["total_online"]), modo="kpi"))
        self.contenido.addWidget(grid)

    def _render_mermas_devoluciones(self, mermas, devoluciones):
        self.contenido.addWidget(QLabel("Mermas y devoluciones del ejercicio"))
        grid = EnterpriseDashboardGrid(columnas=4)
        grid.add_card(EnterpriseCard("Mermas · registros", mermas["registros"],
                                     modo="riesgo", riesgo="advertencia"))
        grid.add_card(EnterpriseCard("Mermas · cantidad", mermas["cantidad_total"],
                                     modo="riesgo", riesgo="advertencia"))
        grid.add_card(EnterpriseCard("Devoluciones · registros", devoluciones["registros"],
                                     modo="riesgo", riesgo="advertencia"))
        grid.add_card(EnterpriseCard("Devoluciones · importe", _eur(devoluciones["total_reembolso"]),
                                     modo="riesgo", riesgo="advertencia"))
        self.contenido.addWidget(grid)

    def _render_plantilla(self, plantilla, detalle):
        self.contenido.addWidget(QLabel("Plantilla"))
        grid = EnterpriseDashboardGrid(columnas=3)
        grid.add_card(EnterpriseCard("Activos actuales", plantilla["activos_actuales"], modo="kpi"))
        grid.add_card(EnterpriseCard("Con expediente (histórico)",
                                     plantilla["total_empleados_con_expediente"], modo="kpi"))
        grid.add_card(EnterpriseCard("Altas nuevas", plantilla["num_altas_nuevas"], modo="kpi"))
        self.contenido.addWidget(grid)

        self.contenido.addWidget(QLabel("Altas nuevas del ejercicio"))
        ta = EnterpriseTable(["Nombre", "Fecha de alta"], con_busqueda=True, contador_abajo=True)
        ta.set_datos([{"Nombre": e["nombre_completo"], "Fecha de alta": e["fecha_alta"]}
                     for e in plantilla["altas_nuevas"]])
        self.contenido.addWidget(ta)

        self.contenido.addWidget(QLabel("Plantilla — detalle por empleado"))
        td = EnterpriseTable(["Nombre", "Horas trabajadas", "Días de baja médica", "Bruto anual",
                              "SS empresa anual"], con_busqueda=True, pagina=15, contador_abajo=True)
        filas = []
        for e in detalle:
            horas = e.get("horas_trabajadas_anio")
            ss = e.get("ss_empresa_anual")
            filas.append({
                "Nombre": e["nombre_completo"],
                "Horas trabajadas": "no disponible" if horas is None else horas,
                "Días de baja médica": e.get("dias_baja_medica_anio"),
                "Bruto anual": _eur(e.get("bruto_anual")),
                # `ss_empresa_anual` puede ser la cadena "no disponible" (nómina sin desglose) o un
                # número: no se fuerza _eur() sobre texto, ni se oculta el texto honesto.
                "SS empresa anual": ss if isinstance(ss, str) else _eur(ss),
            })
        td.set_datos(filas)
        self.contenido.addWidget(td)

    def _render_inversion(self, inv):
        self.contenido.addWidget(QLabel("Inversión por categoría"))
        # `sin_categorizar_historico` se sigue calculando en el servicio (y sigue sumado en
        # "TOTAL (calculado)") — solo se omite su fila aquí por decisión de producto: el usuario no
        # quiere ver una categoría "cajón de sastre" en pantalla. No se pierde el importe: sigue
        # dentro del total mostrado más abajo.
        etiquetas = [
            ("proveedores", "Proveedores"),
            ("rebates_proveedores_liquidados", "Rebates proveedores liquidados (informativo, ya incluido en Proveedores)"),
            ("sueldos", "Sueldos"), ("ss_empresa", "SS empresa"),
            ("maquinaria", "Maquinaria"), ("publicidad", "Publicidad"), ("alquiler", "Alquiler"),
            ("suministros", "Suministros"), ("vehiculos", "Vehículos"), ("impuestos", "Impuestos"),
        ]
        filas = []
        for clave, etiqueta in etiquetas:
            v = inv.get(clave)
            filas.append({"Categoría": etiqueta, "Importe": v if isinstance(v, str) else _eur(v)})
        filas.append({"Categoría": "TOTAL (calculado)", "Importe": _eur(inv.get("total_inversion_calculada"))})
        ti = EnterpriseTable(["Categoría", "Importe"], con_busqueda=False)
        ti.set_datos(filas)
        self.contenido.addWidget(ti)
        if inv.get("ss_empresa_nota"):
            self.contenido.addWidget(EnterpriseInlineBanner(inv["ss_empresa_nota"], rol="advertencia"))

    def _render_pyg(self, pyg, comp):
        self.contenido.addWidget(QLabel("Pérdidas y ganancias"))
        grid = EnterpriseDashboardGrid(columnas=3)
        actual, anterior = pyg["actual"], pyg["anterior"]
        for clave, etiqueta in (("ingresos", "Ingresos"), ("gastos", "Gastos"), ("resultado", "Resultado")):
            grid.add_card(EnterpriseCard(
                f"{etiqueta} {self.anio}", _eur(actual.get(clave)), modo="kpi",
                subtitulo=f"{self.anio - 1}: {_eur(anterior.get(clave))} "
                         f"({_delta_pct(actual.get(clave), anterior.get(clave))})"))
        self.contenido.addWidget(grid)

        self.contenido.addWidget(QLabel("Comparación interanual"))
        grid2 = EnterpriseDashboardGrid(columnas=4)
        for clave, etiqueta in (("ventas_fisico", "Ventas físico"), ("ventas_online", "Ventas online"),
                                ("ventas_total", "Ventas total"), ("resultado_pyg", "Resultado P&G")):
            c = comp[clave]
            grid2.add_card(EnterpriseCard(
                etiqueta, _eur(c["actual"]), modo="kpi",
                subtitulo=f"{comp['anio_anterior']}: {_eur(c['anterior'])} "
                         f"({_delta_pct(c['actual'], c['anterior'])})"))
        self.contenido.addWidget(grid2)

    # ── Export ───────────────────────────────────────────────────────────────
    def _filas_export(self) -> list:
        """Aplana el informe a filas Concepto/Valor para el Excel (el PDF tiene su propio render
        tabular/seccionado, no reutiliza esta lista plana)."""
        d = self.datos
        if not d:
            return []
        filas = [{"Sección": "Ventas", "Concepto": "Total empresa", "Valor": d["ventas"]["total_empresa"]},
                 {"Sección": "Ventas", "Concepto": "Total físico", "Valor": d["ventas"]["total_fisico"]},
                 {"Sección": "Ventas", "Concepto": "Total online", "Valor": d["ventas"]["total_online"]}]
        for f in d["ventas"]["por_tienda"]:
            filas.append({"Sección": "Ventas por tienda", "Concepto": f["tienda"], "Valor": f["total"]})
        for f in d["ventas"]["por_empleado"]:
            filas.append({"Sección": "Ventas por empleado", "Concepto": f.get("empleado"), "Valor": f["total"]})
        filas.append({"Sección": "Mermas", "Concepto": "Registros", "Valor": d["mermas"]["registros"]})
        filas.append({"Sección": "Mermas", "Concepto": "Cantidad", "Valor": d["mermas"]["cantidad_total"]})
        filas.append({"Sección": "Devoluciones", "Concepto": "Registros", "Valor": d["devoluciones"]["registros"]})
        filas.append({"Sección": "Devoluciones", "Concepto": "Importe", "Valor": d["devoluciones"]["total_reembolso"]})
        filas.append({"Sección": "Plantilla", "Concepto": "Activos actuales", "Valor": d["plantilla"]["activos_actuales"]})
        filas.append({"Sección": "Plantilla", "Concepto": "Altas nuevas", "Valor": d["plantilla"]["num_altas_nuevas"]})
        for e in d["empleados_detalle"]:
            filas.append({"Sección": "Plantilla — empleados", "Concepto": e["nombre_completo"],
                         "Valor": f"bruto {e.get('bruto_anual')} · SS {e.get('ss_empresa_anual')} · "
                                 f"horas {e.get('horas_trabajadas_anio')} · bajas {e.get('dias_baja_medica_anio')}"})
        for clave, valor in d["inversion"].items():
            # `sin_categorizar_historico` se excluye también del Excel por el mismo motivo que de
            # la tabla en pantalla (ver `_render_inversion`): no se quiere exponer esa categoría
            # "cajón de sastre" en ninguna vista, aunque sigue sumada en el total.
            if clave in ("ss_empresa_nota", "sin_categorizar_historico"):
                continue
            filas.append({"Sección": "Inversión", "Concepto": clave, "Valor": valor})
        filas.append({"Sección": "P&G", "Concepto": f"Resultado {self.anio}", "Valor": d["pyg"]["actual"].get("resultado")})
        filas.append({"Sección": "P&G", "Concepto": f"Resultado {self.anio - 1}", "Valor": d["pyg"]["anterior"].get("resultado")})
        return filas

    def _exportar_excel(self):
        if not self.datos:
            _aviso(self, "Informe Anual", "Genera el informe antes de exportar.", "warning")
            return
        from src.gui.foundation.export import exportar_excel
        r = exportar_excel(self._filas_export(), f"InformeAnual_{self.anio}",
                           referencia=f"INFORME-ANUAL-{self.anio}")
        if r.get("ok"):
            _aviso(self, "Informe Anual", f"Excel exportado: {r['nombre']}", "success")
        else:
            _aviso(self, "Informe Anual", f"No se pudo exportar: {r.get('error')}", "error")

    def _generar_pdf(self):
        if not self.datos:
            _aviso(self, "Informe Anual", "Genera el informe antes de crear el PDF.", "warning")
            return
        try:
            from src.services.contabilidad.informe_anual_pdf import generar_pdf_informe_anual
            ruta = generar_pdf_informe_anual(self.anio, self.id_empresa, self.datos)
        except Exception as e:
            logger.error("generar_pdf_informe_anual: %s", e)
            _aviso(self, "Informe Anual", f"No se pudo generar el PDF: {e}", "error")
            return
        if ruta and os.path.exists(ruta):
            try:
                from src.db import documentos
                documentos.registrar_documento(
                    ruta, tipo="informe_anual", nombre=os.path.basename(ruta),
                    referencia=f"INFORME-ANUAL-{self.anio}", estado="generado", id_empresa=self.id_empresa)
            except Exception as e:
                logger.debug("registrar_documento informe_anual: %s", e)
            _aviso(self, "Informe Anual", "PDF generado correctamente.", "success")
        else:
            _aviso(self, "Informe Anual", "No se pudo generar el PDF.", "error")


class InformeAnualDialog(QDialog):
    """Diálogo del Informe Anual de Empresa — se abre desde la pestaña Cierres de Contabilidad."""

    def __init__(self, anio, id_empresa=None, usuario=None, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo=f"📊 Informe Anual de Empresa · {anio}", ancho=980)

        self.panel = _PanelInformeAnual(anio, usuario=usuario, id_empresa=id_empresa, parent=self)

        # Scroll de página completa (el panel Enterprise embebido en una ventana con pestañas ya lo
        # obtiene gratis de `QtEnterpriseWindow._on_tab_changed`; aquí se vive dentro de un QDialog
        # suelto, así que se envuelve explícitamente — mismo criterio y mismo estilo de scrollbar).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        scroll.setWidget(self.panel)
        scroll.setMinimumHeight(640)
        v.addWidget(scroll)

        self.panel.cargar_si_necesario()
