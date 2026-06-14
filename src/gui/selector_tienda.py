"""
Selector de tienda (F1 — acceso remoto multitienda).

Diálogo para cambiar la tienda activa SIN cerrar sesión. ADMINISTRADOR ve solo
las tiendas de su empresa; SUPERADMIN puede elegir empresa y cualquier tienda.
Al seleccionar, cambia el TenantContext y registra CAMBIO_CONTEXTO_TIENDA.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.db import empresa as emp_db
from src.db import tiendas as tiendas_db
from src.db.usuario import sesion_global
from src.utils.i18n import tr

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"


def _nombre_empresa(e: dict) -> str:
    return (e.get("nombre_comercial") or e.get("razon_social")
            or e.get("nombre_empresa") or e.get("codigo_empresa") or "")


class SelectorTiendaDialog(QDialog):
    """Devuelve la tienda seleccionada (dict) en `get_resultado()` o None."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._resultado: dict | None = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(520)
        self._build()
        self._cargar_tiendas()

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("selTienda")
        card.setStyleSheet(f"QFrame#selTienda{{background:{_BG};border:2px solid {_CIAN};"
                           f"border-radius:20px;}}")
        outer.addWidget(card)
        lay = QVBoxLayout(card); lay.setContentsMargins(24, 22, 24, 22); lay.setSpacing(12)

        tit = QLabel("🏪  " + tr("tienda.titulo", default="CAMBIAR DE TIENDA"))
        tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;"
                          f"font-size:17px;background:transparent;")
        lay.addWidget(tit)

        sub = QLabel(tr("tienda.sub", default="Selecciona la tienda que quieres gestionar."))
        sub.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:700;"
                          f"font-size:12px;background:transparent;")
        lay.addWidget(sub)

        # SUPERADMIN: selector de empresa (el resto solo ve su empresa).
        self.cmb_empresa = None
        if sesion_global.es_superadmin():
            lbl_e = QLabel(tr("tienda.empresa", default="Empresa"))
            lbl_e.setStyleSheet(f"color:{_TEXT};font-family:'Segoe UI';font-weight:900;"
                                f"font-size:12px;background:transparent;")
            lay.addWidget(lbl_e)
            self.cmb_empresa = QComboBox(); self.cmb_empresa.setFixedHeight(38)
            self.cmb_empresa.setStyleSheet(
                f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};"
                f"border:2px solid {_BORDE};border-radius:9px;padding:0 12px;font-size:13px;"
                f"font-family:'Segoe UI';}}"
                f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
                f"QComboBox::drop-down{{border:none;width:22px;}}"
                f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};"
                f"border:2px solid {_CIAN};border-radius:8px;selection-background-color:{_CIAN};"
                f"selection-color:#0D1117;}}")
            for e in emp_db.listar_empresas():
                self.cmb_empresa.addItem(f"{e.get('codigo_empresa','')} · {_nombre_empresa(e)}",
                                         e.get("id_empresa"))
            # Empresa activa preseleccionada.
            idx = self.cmb_empresa.findData(emp_db.empresa_actual_id())
            if idx >= 0:
                self.cmb_empresa.setCurrentIndex(idx)
            self.cmb_empresa.currentIndexChanged.connect(self._cargar_tiendas)
            lay.addWidget(self.cmb_empresa)

        # Lista de tiendas (scroll).
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFixedHeight(300)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}"
            f"QScrollBar:vertical{{background:transparent;width:10px;margin:4px;}}"
            f"QScrollBar::handle:vertical{{background:{_CIAN};border-radius:5px;min-height:28px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        self._cont = QWidget(); self._cont.setStyleSheet("background:transparent;")
        self._cont_lay = QVBoxLayout(self._cont)
        self._cont_lay.setContentsMargins(8, 8, 8, 8); self._cont_lay.setSpacing(6)
        self._cont_lay.addStretch()
        scroll.setWidget(self._cont)
        lay.addWidget(scroll)

        fila = QHBoxLayout()
        b_cancel = QPushButton(tr("tienda.cancelar", default="CANCELAR"))
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor); b_cancel.setFixedHeight(42)
        b_cancel.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_DIM};border:2px solid {_BORDE};"
            f"border-radius:10px;font-weight:900;padding:0 18px;}}"
            f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        b_cancel.clicked.connect(self.reject)
        fila.addStretch(); fila.addWidget(b_cancel)
        lay.addLayout(fila)

    def _empresa_filtro(self):
        if self.cmb_empresa is not None:
            return self.cmb_empresa.currentData()
        return sesion_global.empresa_id()

    def _cargar_tiendas(self):
        # Limpiar lista (menos el stretch final).
        while self._cont_lay.count() > 1:
            it = self._cont_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

        actual = emp_db.tienda_actual_id()
        tiendas = tiendas_db.listar_tiendas(self._empresa_filtro())
        if not tiendas:
            vacio = QLabel(tr("tienda.vacio", default="No hay tiendas para esta empresa."))
            vacio.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:12px;"
                                f"background:transparent;padding:14px;")
            self._cont_lay.insertWidget(0, vacio)
            return
        for i, t in enumerate(tiendas):
            self._cont_lay.insertWidget(i, self._fila_tienda(t, es_actual=(t.get("id") == actual)))

    def _fila_tienda(self, t, es_actual=False) -> QPushButton:
        codigo = t.get("codigo_tienda") or f"TND-{t.get('id')}"
        nombre = t.get("nombre") or ""
        suf = ("   ✓ " + tr("tienda.actual", default="ACTUAL")) if es_actual else ""
        b = QPushButton(f"  🏬   {codigo}   ·   {nombre}{suf}")
        b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(48)
        borde = _CIAN if es_actual else _BORDE
        b.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_TEXT};border:2px solid {borde};"
            f"border-radius:10px;text-align:left;padding:0 14px;font-family:'Segoe UI';"
            f"font-weight:900;font-size:13px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};background:#11312B;}}")
        b.clicked.connect(lambda _c, td=t: self._elegir(td))
        return b

    def _elegir(self, t):
        res = tiendas_db.cambiar_contexto_tienda(t.get("id"))
        if res:
            self._resultado = res
            self.accept()

    def get_resultado(self) -> dict | None:
        return self._resultado
