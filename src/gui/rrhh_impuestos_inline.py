"""
Formulario INLINE "Impuestos y tasas de empresa" — complemento al Modelo Fiscal Empleados.

Punto de alta MANUAL para tributos de empresa que el flujo de declaraciones AEAT (modelo 303/111/
130…, `services.aeat`) no captura por sí solo: IBI, tasas municipales, cuota de autónomos, licencias…
(el importe REALMENTE ingresado por una declaración AEAT ya presentada se suma aparte y
automáticamente en `informe_anual._impuestos_aeat_pagado` — este formulario es solo el
complemento). Reutiliza el MISMO motor de asientos que "Libro de Gastos" en Contabilidad
(`services.contabilidad.posting.registrar_gasto(tipo="impuestos", ...)`, tipo añadido a
`mapeo.TIPOS_GASTO`) — nunca una tabla/motor paralelo. Lo registrado aquí aparece igual en "Libro
de Gastos" (Contabilidad) y en la categoría "Impuestos" del Informe Anual.

Se coloca en RRHH (pestaña "Modelo Fiscal Empleados") porque esa es la sección ya existente más
afín a obligaciones fiscales/tributarias de la empresa; no se crea una pestaña nueva para esto.
"""

import datetime as _dt
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)
from src.gui.catalogo_gestion import _tabla

logger = logging.getLogger("gui.rrhh.impuestos_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")

_NATURALEZA = [("Extraordinario (IBI, tasas, licencias…)", "extraordinario"),
              ("Fijo mensual (cuota de autónomos…)", "fijo_mensual")]
_FORMAS_PAGO = [("Banco / Tarjeta", "banco"), ("Efectivo", "efectivo"), ("A crédito", "credito")]


def _normalizar_fecha(txt):
    txt = (txt or "").strip()
    if not txt:
        return _dt.date.today().isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return _dt.datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class ImpuestoEmpresaInlineForm(QWidget):
    """Alta manual de un impuesto/tasa de empresa + listado de lo ya registrado este año."""

    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._build()
        self._cargar()

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border:none;"
                f"border-radius:10px;padding:8px 16px;font-family:'Segoe UI';font-weight:bold;font-size:14px;}}"
                f"QPushButton:hover{{background:{COLOR_ACCION_TEXTO};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};}}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 16px;font-family:'Segoe UI';font-weight:bold;font-size:14px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};}}")
        b.clicked.connect(cb); return b

    def _line(self):
        w = QLineEdit(); w.setStyleSheet(f"QLineEdit{{{_INP_SS}}}"); return w

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLOR_BORDE};")
        titulo = QLabel("IMPUESTOS Y TASAS DE EMPRESA")
        titulo.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;"
                             "font-weight:900;letter-spacing:1px;background:transparent;margin-top:8px;")
        root.addWidget(titulo); root.addWidget(line)

        desc = QLabel("Registro complementario para tributos NO capturados por el flujo de "
                      "declaraciones AEAT (IBI, tasas municipales, cuota de autónomos, licencias…). "
                      "El importe realmente ingresado de una declaración AEAT ya presentada se suma "
                      "aparte y automáticamente en el Informe Anual.")
        desc.setWordWrap(True); desc.setStyleSheet("color:#8B98A5;font-size:12px;background:transparent;")
        root.addWidget(desc)

        f1 = QHBoxLayout(); f1.setSpacing(10)
        self.in_concepto = self._line(); self.in_concepto.setPlaceholderText("Concepto (p. ej. IBI local — 1er trimestre)")
        self.in_importe = self._line(); self.in_importe.setPlaceholderText("Importe €"); self.in_importe.setFixedWidth(130)
        self.in_fecha = self._line(); self.in_fecha.setPlaceholderText("AAAA-MM-DD (vacío = hoy)"); self.in_fecha.setFixedWidth(160)
        for et, wd in (("Concepto:", self.in_concepto), ("Importe:", self.in_importe), ("Fecha:", self.in_fecha)):
            f1.addWidget(self._lbl(et)); f1.addWidget(wd)
        root.addLayout(f1)

        f2 = QHBoxLayout(); f2.setSpacing(10)
        self.cb_naturaleza = QComboBox(); self.cb_naturaleza.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for et, val in _NATURALEZA:
            self.cb_naturaleza.addItem(et, val)
        self.cb_pago = QComboBox(); self.cb_pago.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for et, val in _FORMAS_PAGO:
            self.cb_pago.addItem(et, val)
        f2.addWidget(self._lbl("Naturaleza:")); f2.addWidget(self.cb_naturaleza, 1)
        f2.addWidget(self._lbl("Pago:")); f2.addWidget(self.cb_pago)
        f2.addWidget(self._btn("➕  Registrar impuesto", self._registrar, primary=True))
        root.addLayout(f2)

        root.addWidget(self._lbl("IMPUESTOS REGISTRADOS ESTE AÑO (manual, vía esta pantalla o Libro de Gastos)"))
        self.tbl = _tabla(["Nº", "Fecha", "Concepto", "Importe", "Estado"])
        self.tbl.setMinimumHeight(140)
        root.addWidget(self.tbl)

    # ── Datos ─────────────────────────────────────────────────────────────────
    def _cargar(self):
        try:
            from src.services.contabilidad.posting import listar_gastos
            anio = _dt.date.today().year
            todas = listar_gastos(anio=anio, id_empresa=self._id_empresa()) or []
        except Exception as e:
            logger.debug("listar_gastos impuestos: %s", e); todas = []
        filas = [g for g in todas if str(g.get("ref_origen") or "").startswith("gasto:impuestos:")]
        self.tbl.setRowCount(len(filas))
        for i, g in enumerate(filas):
            vals = [g.get("numero"), g.get("fecha"), g.get("concepto"), g.get("total_debe"), g.get("estado")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

    # ── Registro ──────────────────────────────────────────────────────────────
    def _registrar(self):
        concepto = self.in_concepto.text().strip()
        if not concepto:
            mostrar_mensaje(self, "Impuestos de empresa", "Indica un concepto.", "warning")
            return
        try:
            importe = float((self.in_importe.text() or "0").replace(",", ".").strip())
        except ValueError:
            importe = 0.0
        if importe <= 0:
            mostrar_mensaje(self, "Impuestos de empresa", "Introduce un importe válido.", "warning")
            return
        fecha = _normalizar_fecha(self.in_fecha.text())
        if fecha is None:
            mostrar_mensaje(self, "Impuestos de empresa",
                           "Fecha no válida. Usa AAAA-MM-DD o DD/MM/AAAA.", "warning")
            return
        try:
            from src.services.contabilidad.posting import registrar_gasto
            r = registrar_gasto(
                "impuestos", importe, fecha=fecha, forma_pago=self.cb_pago.currentData(),
                concepto=concepto, con_iva=False, naturaleza_gasto=self.cb_naturaleza.currentData(),
                id_empresa=self._id_empresa())
        except Exception as e:
            logger.error("registrar impuesto: %s", e); r = None
        if not r:
            mostrar_mensaje(self, "Impuestos de empresa",
                           "No se pudo registrar (¿contabilidad activada?).", "error")
            return
        mostrar_mensaje(self, "Impuestos de empresa",
                        f"Impuesto «{concepto}» registrado (asiento nº {r.get('numero')}).", "success")
        self.in_concepto.clear(); self.in_importe.clear(); self.in_fecha.clear()
        self._cargar()
