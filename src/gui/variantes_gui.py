"""
Gestión de VARIANTES por talla/color (edición Textil). Despliega un producto "modelo" en SKUs (talla × color) y
muestra la rejilla de stock. SOLO orquesta `services.variantes` (que reutiliza el modelo de artículos/stock).
Autocontenido y testeable offscreen. La entrada a este diálogo se gatea con `verticales.visible("productos.tallas")`.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from src.gui.foundation import tokens as T
from src.services import variantes as _V

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.variantes")


class VariantesDialog(QDialog):
    def __init__(self, codigo_padre=None, usuario=None, parent=None):
        super().__init__(parent)
        self.codigo_padre = (codigo_padre or "").strip()
        self.usuario = usuario or {}
        self.setWindowTitle(f"Variantes (talla/color) · {self.codigo_padre or 'modelo'}")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        if self.codigo_padre:
            self._cargar_matriz()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _btn(self, txt, cb, *, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            b.setStyleSheet(f"QPushButton{{background:{T.INFO};color:{T.BG};border:none;border-radius:8px;"
                            "font-weight:800;padding:7px 14px;}")
        else:
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{T.INFO};border:1px solid {T.INFO};"
                            "border-radius:8px;padding:7px 14px;}")
        b.clicked.connect(cb)
        return b

    def _build(self):
        ly = QVBoxLayout(self); ly.setContentsMargins(16, 16, 16, 16); ly.setSpacing(10)
        if not self.codigo_padre:
            fila0 = QHBoxLayout(); fila0.addWidget(QLabel("Modelo (código):"))
            self.in_padre = QLineEdit(); self.in_padre.setPlaceholderText("Código del producto modelo")
            fila0.addWidget(self.in_padre, 1); ly.addLayout(fila0)
        fila = QHBoxLayout()
        self.in_tallas = QLineEdit(); self.in_tallas.setPlaceholderText("Tallas (S,M,L,XL)")
        self.in_colores = QLineEdit(); self.in_colores.setPlaceholderText("Colores (Rojo,Azul,Negro)")
        self.in_precio = QDoubleSpinBox(); self.in_precio.setRange(0, 1000000); self.in_precio.setDecimals(2)
        self.in_precio.setPrefix("€ ")
        for w in (self.in_tallas, self.in_colores):
            w.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                            "border-radius:8px;padding:6px;}")
        fila.addWidget(self.in_tallas, 2); fila.addWidget(self.in_colores, 2); fila.addWidget(self.in_precio)
        ly.addLayout(fila)
        ly.addWidget(self._btn("Generar variantes", self._generar, primary=True))
        self.tabla = QTableWidget(0, 0)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setStyleSheet("QTableWidget{background:#0E1117;color:#E6EDF3;gridline-color:#30363D;}"
                                 "QHeaderView::section{background:#161B22;color:#00FFC6;border:0;padding:5px;}")
        ly.addWidget(self.tabla, 1)
        self.lbl_total = QLabel("—"); self.lbl_total.setStyleSheet(f"color:{T.DIM};")
        ly.addWidget(self.lbl_total)

    def _padre(self):
        return self.codigo_padre or (self.in_padre.text().strip() if hasattr(self, "in_padre") else "")

    def _generar(self):
        padre = self._padre()
        tallas = [t.strip() for t in self.in_tallas.text().split(",") if t.strip()]
        colores = [c.strip() for c in self.in_colores.text().split(",") if c.strip()]
        if not padre or not tallas or not colores:
            self._aviso("Indica modelo, tallas y colores.")
            return
        precio = self.in_precio.value() or None
        res = _V.crear_variantes(padre, tallas=tallas, colores=colores, id_empresa=self._emp(), precio=precio)
        if not res.get("ok"):
            self._aviso(res.get("error", "No se pudieron crear las variantes."), "error")
            return
        self.codigo_padre = padre
        self._cargar_matriz()
        self._aviso(f"{res['variantes']} variante(s) generadas.", "info")

    def _cargar_matriz(self):
        m = _V.matriz(self.codigo_padre, self._emp())
        tallas, colores = m["tallas"], m["colores"]
        stock = {(c["talla"], c["color"]): c["stock"] for c in m["celdas"]}
        self.tabla.clear()
        self.tabla.setRowCount(len(tallas)); self.tabla.setColumnCount(len(colores))
        self.tabla.setVerticalHeaderLabels([str(t) for t in tallas])
        self.tabla.setHorizontalHeaderLabels([str(c) for c in colores])
        for i, t in enumerate(tallas):
            for j, c in enumerate(colores):
                self.tabla.setItem(i, j, QTableWidgetItem(str(stock.get((t, c), 0))))
        self.lbl_total.setText(f"Stock total: {m['stock_total']} · {len(m['celdas'])} SKU(s)")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Variantes", msg, tipo)
        else:  # pragma: no cover
            logger.info("variantes: %s", msg)
