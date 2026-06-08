"""
Smart Manager - Módulo de Stock
Vista lateral (sidebar) con 6 pestañas:
  0 · Stock Tienda
  1 · Stock Almacén Central
  2 · Editar Stock
  3 · Importar Stock
  4 · Exportar Stock
  5 · Inventario
"""

import os
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import (
    aplicar_estilo_widget,
    construir_tabla_estilizada,
    repolish_widget,
)
from src.db.conexion import (
    ensure_schema,
    modificar_stock_completo,
    obtener_conexion,
)
from src.utils import i18n
from src.utils.i18n import tr

# ---------------------------------------------------------------------------
# Module-level signals (backward-compat: imported by src.db.conexion)
# ---------------------------------------------------------------------------


class StockSignals(QObject):
    stock_actualizado = pyqtSignal(str)


stock_signals = StockSignals()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_GRIS_PANEL = "#1A1D23"
_BORDE = "#30363D"

# Neon input
_NEON_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_CIAN};
    border-radius: 12px;
    padding: 8px 14px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""

# Cyan action button (no focus rect, no shadow — add shadow manually only on main page buttons)
_BTN_CIAN_SS = f"""
QPushButton {{
    background-color: #0E1117;
    color: {_CIAN};
    font-weight: bold;
    border-radius: 14px;
    padding: 12px 24px;
    font-size: 13px;
    font-family: 'Segoe UI';
    border: 2px solid {_CIAN};
    outline: none;
}}
QPushButton:hover {{
    background-color: {_CIAN};
    color: #0E1117;
    border: 2px solid {_CIAN};
}}
QPushButton:pressed {{
    background-color: #00C79A;
    color: #0E1117;
}}
QPushButton:focus {{
    outline: none;
}}
"""

# Green save button
_BTN_VERDE_SS = """
QPushButton {
    background-color: #2EA043;
    color: #000000;
    font-weight: bold;
    border-radius: 12px;
    padding: 10px 28px;
    font-size: 13px;
    font-family: 'Segoe UI';
    border: none;
    outline: none;
}
QPushButton:hover {
    background-color: #FFFFFF;
    color: #000000;
}
QPushButton:pressed {
    background-color: #238636;
    color: #000000;
}
QPushButton:focus {
    outline: none;
}
"""

# Red cancel button (no focus rect)
_BTN_ROJO_SS = """
QPushButton {
    background-color: #0E1117;
    color: #FF4B4B;
    font-weight: bold;
    border-radius: 14px;
    padding: 10px 20px;
    font-size: 12px;
    font-family: 'Segoe UI';
    border: 2px solid #FF4B4B;
    outline: none;
}
QPushButton:hover {
    background-color: #FF4B4B;
    color: #0E1117;
    border: 2px solid #FF4B4B;
}
QPushButton:focus {
    outline: none;
}
"""

# Shared description panel background
_DESC_SS = (
    f"color: #8B949E; font-size: 13px; "
    f"background-color: {_PANEL_BG}; border-radius: 12px; padding: 14px; "
    f"border: 1px solid {_BORDE};"
)

# Textos descriptivos por defecto (fallback si falta la clave i18n).
_IMPORT_DESC_DEFAULT = (
    "Importa artículos y niveles de stock desde un fichero Excel (.xlsx) o CSV/TXT. "
    "Las columnas del fichero deben coincidir con los campos de la base de datos. "
    "Columnas requeridas:\n"
    "  • codigo          → Código del artículo (obligatorio, clave única)\n"
    "  • nombre          → Nombre del artículo\n"
    "  • Stock_tienda    → Stock lineal (expuesto en tienda)\n"
    "  • Stock_total     → Stock almacén tienda\n"
    "  • Stock_central   → Stock almacén central\n"
    "  • Stock_esperado  → Stock mínimo esperado en el lineal\n\n"
    "Columnas opcionales: descripcion, categoria, seccion, precio"
)
_EXPORT_DESC_DEFAULT = (
    "Genera un informe Excel con todos los niveles de stock actuales. "
    "El fichero se guarda automáticamente en documentos/stocks/. "
    "El informe incluye: Código, Nombre, Stock Lineal, Stock Almacén,\n"
    "Stock Almacén Central y Stock Esperado de cada artículo."
)
_INVENTORY_DESC_DEFAULT = (
    "Accede a la carpeta compartida de inventario en Google Drive "
    "para ver y gestionar los documentos de inventario. "
    "Se abrirá tu navegador predeterminado con la carpeta de\n"
    "Google Drive configurada para este negocio."
)


# ---------------------------------------------------------------------------
# Sidebar button: calls aplicar_estilo_widget like SidebarButton in recepcion_pale.py
# ---------------------------------------------------------------------------
class _SidebarBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("btn_sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
                color: #FFFFFF;
            }}
            QPushButton:hover {{
                background-color: #FFFFFF;
                color: #0E1117;
            }}
            QPushButton:checked {{
                background-color: #1A2230;
                border-left: 4px solid {_CIAN};
                color: {_CIAN};
            }}
        """)
        try:
            aplicar_estilo_widget(self)
        except Exception:
            pass

    def enterEvent(self, event):
        super().enterEvent(event)
        repolish_widget(self)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        repolish_widget(self)


# ---------------------------------------------------------------------------
# Helper: shadow effect
# ---------------------------------------------------------------------------
def _sombra_cian(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(22)
    fx.setColor(QColor(_CIAN))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


# ---------------------------------------------------------------------------
# Helper: build styled table with top-margin fix for corner cuts
# ---------------------------------------------------------------------------
def _crear_tabla(parent, cols):
    contenedor, tabla = construir_tabla_estilizada(parent)
    tabla.setStyleSheet(f"""
        QTableWidget {{
            border: none;
            background-color: transparent;
            outline: none;
        }}
        QHeaderView {{
            background-color: transparent;
            border: none;
        }}
        QHeaderView::section {{
            background-color: #1A1D23;
            color: {_CIAN};
            border: none;
        }}
        QHeaderView::section:hover {{
            background-color: {_CIAN};
            color: #0E1117;
        }}
        QHeaderView::section:first {{
            border-top-left-radius: 18px;
        }}
        QHeaderView::section:last {{
            border-top-right-radius: 18px;
        }}
    """)
    contenedor.layout().setContentsMargins(2, 2, 2, 2)
    tabla.setColumnCount(len(cols))
    tabla.setHorizontalHeaderLabels(cols)
    tabla.horizontalHeader().setStretchLastSection(True)
    tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return contenedor, tabla


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def _buscar_articulos(query: str):
    try:
        like = f"%{query}%"
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT codigo, nombre,
                           COALESCE(Stock_tienda, 0),
                           COALESCE(Stock_total, 0),
                           COALESCE(Stock_central, 0)
                    FROM articulos
                    WHERE codigo LIKE %s OR nombre LIKE %s
                    ORDER BY nombre ASC
                    LIMIT 200
                    """,
                    (like, like),
                )
                return cur.fetchall()
    except Exception:
        return []


def _get_todos_articulos():
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo, nombre FROM articulos ORDER BY nombre ASC")
                return cur.fetchall()
    except Exception:
        return []


def _get_articulo_stock(codigo: str):
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                    "COALESCE(Stock_central,0), COALESCE(Stock_esperado,0) "
                    "FROM articulos WHERE codigo=%s",
                    (codigo,),
                )
                row = cur.fetchone()
        if row:
            return {
                "nombre": row[0],
                "lineal": row[1],
                "almacen": row[2],
                "central": row[3],
                "esperado": row[4],
            }
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tab pages
# ---------------------------------------------------------------------------


class _StockTiendaPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(14)

        self._lbl = lbl = QLabel(tr("stock.title_store", default="Stock Tienda"))
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(tr("stock.search_ph", default="Buscar por código o nombre…"))
        self.buscador.setStyleSheet(_NEON_INPUT_SS)
        self.buscador.setFixedHeight(44)
        self.buscador.textChanged.connect(self._filtrar)
        layout.addWidget(self.buscador)

        contenedor, self.tabla = _crear_tabla(self, self._cols())
        hh = self.tabla.horizontalHeader()
        hh.setStretchLastSection(False)
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(contenedor)
        self.cargar()

    @staticmethod
    def _cols():
        return [
            tr("stock.col_ean", default="EAN"),
            tr("stock.col_item", default="Artículo"),
            tr("stock.col_shelf", default="Stock Lineal"),
            tr("stock.col_warehouse", default="Stock Almacén"),
        ]

    def _retraducir(self):
        self._lbl.setText(tr("stock.title_store", default="Stock Tienda"))
        self.buscador.setPlaceholderText(tr("stock.search_ph", default="Buscar por código o nombre…"))
        self.tabla.setHorizontalHeaderLabels(self._cols())

    def cargar(self):
        self._poblar(_buscar_articulos(""))

    def _filtrar(self, texto):
        self._poblar(_buscar_articulos(texto.strip()))

    def _poblar(self, rows):
        self.tabla.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate([str(row[0]), str(row[1]), str(row[2]), str(row[3])]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(r, c, item)


class _StockCentralPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(14)

        self._lbl = lbl = QLabel(tr("stock.title_central", default="Stock Almacén Central"))
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(tr("stock.search_ph", default="Buscar por código o nombre…"))
        self.buscador.setStyleSheet(_NEON_INPUT_SS)
        self.buscador.setFixedHeight(44)
        self.buscador.textChanged.connect(self._filtrar)
        layout.addWidget(self.buscador)

        contenedor, self.tabla = _crear_tabla(self, self._cols())
        hh = self.tabla.horizontalHeader()
        hh.setStretchLastSection(False)
        for c in range(3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(contenedor)
        self.cargar()

    @staticmethod
    def _cols():
        return [
            tr("stock.col_ean", default="EAN"),
            tr("stock.col_item", default="Artículo"),
            tr("stock.col_central", default="Stock Almacén Central"),
        ]

    def _retraducir(self):
        self._lbl.setText(tr("stock.title_central", default="Stock Almacén Central"))
        self.buscador.setPlaceholderText(tr("stock.search_ph", default="Buscar por código o nombre…"))
        self.tabla.setHorizontalHeaderLabels(self._cols())

    def cargar(self):
        self._poblar(_buscar_articulos(""))

    def _filtrar(self, texto):
        self._poblar(_buscar_articulos(texto.strip()))

    def _poblar(self, rows):
        self.tabla.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate([str(row[0]), str(row[1]), str(row[4])]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(r, c, item)


class _EditChoiceDialog(QDialog):
    CANCELAR = 0
    LINEAL_ALMACEN = 1
    SOLO_LINEAL = 2
    SOLO_ALMACEN = 3

    def __init__(self, nombre_art: str, parent=None):
        super().__init__(parent)
        self.choice = self.CANCELAR
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(400)

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _box = QFrame()
        _box.setObjectName("_editchoicebox")
        _box.setStyleSheet(f"""
            QFrame#_editchoicebox {{
                background-color: #161B22;
                border: 2px solid {_CIAN};
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        _outer.addWidget(_box)

        layout = QVBoxLayout(_box)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        lbl_art = QLabel(nombre_art)
        lbl_art.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_art.setStyleSheet("color: #FFFFFF;")
        lbl_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_art.setWordWrap(True)
        layout.addWidget(lbl_art)

        lbl_q = QLabel(tr("stock.choice_q", default="¿Qué stock deseas editar?"))
        lbl_q.setStyleSheet("color: #8B949E; font-size: 13px;")
        lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_q)

        layout.addSpacing(6)

        _BTN_CHOICE_SS = f"""
            QPushButton {{
                background-color: #0E1117;
                color: {_CIAN};
                font-weight: bold;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                font-family: 'Segoe UI';
                border: 2px solid {_CIAN};
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
            QPushButton:focus {{ outline: none; }}
        """
        _BTN_CANCEL_SS = f"""
            QPushButton {{
                background-color: #0E1117;
                color: {_CIAN};
                font-weight: bold;
                border-radius: 12px;
                padding: 10px 20px;
                font-size: 13px;
                font-family: 'Segoe UI';
                border: 2px solid {_CIAN};
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
            QPushButton:focus {{ outline: none; }}
        """

        for label, choice_val in [
            (tr("stock.choice_both", default="LINEAL Y ALMACÉN"), self.LINEAL_ALMACEN),
            (tr("stock.choice_shelf", default="SOLO LINEAL"), self.SOLO_LINEAL),
            (tr("stock.choice_warehouse", default="SOLO ALMACÉN"), self.SOLO_ALMACEN),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(_BTN_CHOICE_SS)
            btn.setFixedHeight(46)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, cv=choice_val: self._elegir(cv))
            layout.addWidget(btn)

        btn_cancel = QPushButton(tr("stock.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet(_BTN_CANCEL_SS)
        btn_cancel.setFixedHeight(40)
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def _elegir(self, cv):
        self.choice = cv
        self.accept()


class _EditStockDialog(QDialog):
    def __init__(self, nombre_art: str, choice: int, lineal: int, almacen: int, parent=None):
        super().__init__(parent)
        self.new_lineal = None
        self.new_almacen = None

        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(400)

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _box = QFrame()
        _box.setObjectName("_editstockbox")
        _box.setStyleSheet(f"""
            QFrame#_editstockbox {{
                background-color: #161B22;
                border: 2px solid {_CIAN};
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        _outer.addWidget(_box)

        layout = QVBoxLayout(_box)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        lbl_art = QLabel(nombre_art)
        lbl_art.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_art.setStyleSheet("color: #FFFFFF;")
        lbl_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_art.setWordWrap(True)
        layout.addWidget(lbl_art)

        layout.addSpacing(4)

        show_lineal = choice in (_EditChoiceDialog.LINEAL_ALMACEN, _EditChoiceDialog.SOLO_LINEAL)
        show_almacen = choice in (_EditChoiceDialog.LINEAL_ALMACEN, _EditChoiceDialog.SOLO_ALMACEN)

        self._inp_lineal = None
        self._inp_almacen = None

        if show_lineal:
            row_ly = QHBoxLayout()
            lbl = QLabel(tr("stock.lbl_shelf", default="Stock Lineal:"))
            lbl.setStyleSheet("color: #8B949E; font-size: 13px;")
            lbl.setFixedWidth(130)
            self._inp_lineal = QLineEdit(str(lineal))
            self._inp_lineal.setStyleSheet(_NEON_INPUT_SS)
            self._inp_lineal.setFixedHeight(44)
            self._inp_lineal.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_ly.addWidget(lbl)
            row_ly.addWidget(self._inp_lineal)
            layout.addLayout(row_ly)

        if show_almacen:
            row_ly = QHBoxLayout()
            lbl = QLabel(tr("stock.lbl_warehouse", default="Stock Almacén:"))
            lbl.setStyleSheet("color: #8B949E; font-size: 13px;")
            lbl.setFixedWidth(130)
            self._inp_almacen = QLineEdit(str(almacen))
            self._inp_almacen.setStyleSheet(_NEON_INPUT_SS)
            self._inp_almacen.setFixedHeight(44)
            self._inp_almacen.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_ly.addWidget(lbl)
            row_ly.addWidget(self._inp_almacen)
            layout.addLayout(row_ly)

        layout.addSpacing(6)

        btn_guardar = QPushButton(tr("stock.save", default="GUARDAR"))
        btn_guardar.setStyleSheet(_BTN_VERDE_SS)
        btn_guardar.setFixedHeight(46)
        btn_guardar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_guardar.clicked.connect(self._on_guardar)
        layout.addWidget(btn_guardar)

        _BTN_CANCEL_SS = f"""
            QPushButton {{
                background-color: #0E1117;
                color: {_CIAN};
                font-weight: bold;
                border-radius: 12px;
                padding: 10px 20px;
                font-size: 13px;
                font-family: 'Segoe UI';
                border: 2px solid {_CIAN};
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
            QPushButton:focus {{ outline: none; }}
        """
        btn_cancel = QPushButton(tr("stock.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet(_BTN_CANCEL_SS)
        btn_cancel.setFixedHeight(40)
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def _on_guardar(self):
        try:
            if self._inp_lineal is not None:
                self.new_lineal = int(self._inp_lineal.text() or "0")
            if self._inp_almacen is not None:
                self.new_almacen = int(self._inp_almacen.text() or "0")
        except ValueError:
            QMessageBox.warning(
                self,
                tr("stock.err_title", default="Error"),
                tr("stock.err_int_msg", default="Los valores deben ser números enteros."),
            )
            return
        self.accept()


class _EditarStockPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._todos = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(14)

        self._lbl = lbl = QLabel(tr("stock.title_edit", default="Editar Stock"))
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(tr("stock.search_ph_ean", default="Buscar por EAN o nombre…"))
        self.buscador.setStyleSheet(_NEON_INPUT_SS)
        self.buscador.setFixedHeight(44)
        self.buscador.textChanged.connect(self._filtrar)
        layout.addWidget(self.buscador)

        contenedor, self.tabla = _crear_tabla(self, self._cols())
        hh = self.tabla.horizontalHeader()
        hh.setStretchLastSection(False)
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 80)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(contenedor)

        self.cargar()

    @staticmethod
    def _cols():
        return [
            tr("stock.col_ean", default="EAN"),
            tr("stock.col_item", default="Artículo"),
            tr("stock.col_shelf", default="Stock Lineal"),
            tr("stock.col_warehouse", default="Stock Almacén"),
            tr("stock.col_edit", default="Editar"),
        ]

    def _retraducir(self):
        self._lbl.setText(tr("stock.title_edit", default="Editar Stock"))
        self.buscador.setPlaceholderText(tr("stock.search_ph_ean", default="Buscar por EAN o nombre…"))
        self.tabla.setHorizontalHeaderLabels(self._cols())

    def cargar(self):
        self._todos = list(_buscar_articulos(""))
        self._poblar(self._todos)

    def _filtrar(self, texto):
        texto = texto.strip().lower()
        if not texto:
            self._poblar(self._todos)
        else:
            filtrados = [r for r in self._todos
                         if texto in str(r[0]).lower() or texto in str(r[1]).lower()]
            self._poblar(filtrados)

    def _poblar(self, rows):
        self.tabla.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for col_idx, val in enumerate([str(row[0]), str(row[1]), str(row[2]), str(row[3])]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(r, col_idx, item)
            btn_edit = QPushButton("✏")
            btn_edit.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    font-size: 16px;
                    color: {_CIAN};
                    padding: 0;
                }}
                QPushButton:hover {{
                    background-color: #1A2230;
                    border-radius: 6px;
                }}
            """)
            btn_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.clicked.connect(lambda _, ri=r: self._on_edit_click(ri))
            self.tabla.setCellWidget(r, 4, btn_edit)

    def _on_edit_click(self, row_idx):
        item_ean = self.tabla.item(row_idx, 0)
        item_nom = self.tabla.item(row_idx, 1)
        item_lin = self.tabla.item(row_idx, 2)
        item_alm = self.tabla.item(row_idx, 3)
        if not item_ean or not item_nom:
            return

        nombre = f"{item_ean.text()} – {item_nom.text()}"
        try:
            lineal_actual = int(item_lin.text()) if item_lin else 0
        except ValueError:
            lineal_actual = 0
        try:
            almacen_actual = int(item_alm.text()) if item_alm else 0
        except ValueError:
            almacen_actual = 0

        dlg_choice = _EditChoiceDialog(nombre, self)
        if dlg_choice.exec() != QDialog.DialogCode.Accepted:
            return

        dlg_edit = _EditStockDialog(nombre, dlg_choice.choice, lineal_actual, almacen_actual, self)
        if dlg_edit.exec() != QDialog.DialogCode.Accepted:
            return

        codigo = item_ean.text()
        datos = _get_articulo_stock(codigo)
        if not datos:
            QMessageBox.critical(
                self,
                tr("stock.err_title", default="Error"),
                tr("stock.err_get_msg", default="No se pudo obtener el artículo."),
            )
            return

        new_lineal = dlg_edit.new_lineal if dlg_edit.new_lineal is not None else datos["lineal"]
        new_almacen = dlg_edit.new_almacen if dlg_edit.new_almacen is not None else datos["almacen"]

        ok = modificar_stock_completo(codigo, datos["central"], new_almacen, new_lineal)
        if ok:
            stock_signals.stock_actualizado.emit(codigo)
            self.tabla.clearSelection()
            if item_lin:
                item_lin.setText(str(new_lineal))
            if item_alm:
                item_alm.setText(str(new_almacen))
            for i, row in enumerate(self._todos):
                if str(row[0]) == codigo:
                    self._todos[i] = (row[0], row[1], new_lineal, new_almacen) + row[4:]
                    break
        else:
            QMessageBox.critical(
                self,
                tr("stock.err_title", default="Error"),
                tr("stock.err_upd_msg", default="No se pudo actualizar el stock."),
            )


class _ImportarHilo(QThread):
    finalizado = pyqtSignal(str)

    def __init__(self, ruta):
        super().__init__()
        self.ruta = ruta

    def run(self):
        try:
            ext = os.path.splitext(self.ruta)[1].lower()
            if ext == ".xlsx":
                df = pd.read_excel(self.ruta)
            elif ext in (".csv", ".txt"):
                try:
                    df = pd.read_csv(self.ruta, sep="\t")
                except Exception:
                    df = pd.read_csv(self.ruta, sep=",")
            else:
                self.finalizado.emit(
                    tr("stock.fmt_incompatible",
                       default="Formato no compatible. Usa Excel (.xlsx) o CSV/TXT.")
                )
                return
            if df.empty:
                self.finalizado.emit(tr("stock.file_empty", default="El fichero está vacío."))
                return
            df.columns = [c.strip().lower() for c in df.columns]
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='articulos'"
                    )
                    existentes = {r[0].lower() for r in cur.fetchall()}
                    for col in df.columns:
                        if col not in existentes:
                            cur.execute(
                                f"ALTER TABLE articulos ADD COLUMN `{col}` TEXT"
                            )
                            existentes.add(col)
                    for _, row in df.iterrows():
                        cols = list(row.index)
                        values = [row[c] for c in cols]
                        col_names = ", ".join(f"`{c}`" for c in cols)
                        placeholders = ", ".join("%s" for _ in cols)
                        updates = ", ".join(
                            f"`{c}`=VALUES(`{c}`)" for c in cols if c != "codigo"
                        )
                        cur.execute(
                            f"INSERT INTO articulos ({col_names}) VALUES ({placeholders}) "
                            f"ON DUPLICATE KEY UPDATE {updates}",
                            values,
                        )
                conn.commit()
            self.finalizado.emit(
                tr("stock.import_ok", default="Stock importado correctamente desde:\n{ruta}", ruta=self.ruta)
            )
        except Exception as e:
            self.finalizado.emit(tr("stock.import_err", default="Error al importar:\n{e}", e=e))


class _ImportarStockPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._lbl_titulo = lbl_titulo = QLabel(tr("stock.title_import", default="Importar Stock"))
        lbl_titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl_titulo)

        self._lbl_desc = lbl_desc = QLabel(tr("stock.import_desc", default=_IMPORT_DESC_DEFAULT))
        lbl_desc.setStyleSheet(_DESC_SS)
        lbl_desc.setWordWrap(True)
        lbl_desc.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(lbl_desc)

        icon_lbl = QLabel("📦")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 160px; background: transparent; border: none;"
        )
        icon_lbl.setFixedHeight(200)
        layout.addWidget(icon_lbl)

        self._btn = btn = QPushButton(tr("stock.import_btn", default="IMPORTAR STOCK"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(200, 62)
        btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(self._importar)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.lbl_resultado = QLabel()
        self.lbl_resultado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_resultado.setStyleSheet(f"color: {_CIAN}; font-size: 13px;")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.setVisible(False)
        layout.addWidget(self.lbl_resultado)
        layout.addStretch()

    def _retraducir(self):
        self._lbl_titulo.setText(tr("stock.title_import", default="Importar Stock"))
        self._lbl_desc.setText(tr("stock.import_desc", default=_IMPORT_DESC_DEFAULT))
        self._btn.setText(tr("stock.import_btn", default="IMPORTAR STOCK"))

    def _importar(self):
        _all = tr("stock.all_files", default="Todos los archivos")
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            tr("stock.file_dialog_title", default="Selecciona un fichero de stock"),
            "",
            f"Excel (*.xlsx);;CSV/TXT (*.csv *.txt);;{_all} (*)",
        )
        if not ruta:
            return
        self.lbl_resultado.setText(tr("stock.importing", default="Importando…"))
        self.lbl_resultado.setVisible(True)
        self._hilo = _ImportarHilo(ruta)
        self._hilo.finalizado.connect(self._on_finalizado)
        self._hilo.start()

    def _on_finalizado(self, mensaje):
        self.lbl_resultado.setText(mensaje)


class _ExportarStockPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._lbl_titulo = lbl_titulo = QLabel(tr("stock.title_export", default="Exportar Stock"))
        lbl_titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl_titulo)

        self._lbl_desc = lbl_desc = QLabel(tr("stock.export_desc", default=_EXPORT_DESC_DEFAULT))
        lbl_desc.setStyleSheet(_DESC_SS)
        lbl_desc.setWordWrap(True)
        lbl_desc.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(lbl_desc)

        icon_lbl = QLabel("🖨")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 160px; background: transparent; border: none;"
        )
        icon_lbl.setFixedHeight(200)
        layout.addWidget(icon_lbl)

        self._btn = btn = QPushButton(tr("stock.export_btn", default="EXPORTAR STOCK"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(200, 62)
        btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(self._exportar)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.lbl_resultado = QLabel()
        self.lbl_resultado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_resultado.setStyleSheet(f"color: {_CIAN}; font-size: 13px;")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.setVisible(False)
        layout.addWidget(self.lbl_resultado)
        layout.addStretch()

    def _exportar(self):
        try:
            query = (
                "SELECT codigo AS Código, nombre AS Nombre, "
                "COALESCE(Stock_tienda,0) AS 'Stock Lineal', "
                "COALESCE(Stock_total,0) AS 'Stock Almacén', "
                "COALESCE(Stock_central,0) AS 'Stock Almacén Central', "
                "COALESCE(Stock_esperado,0) AS 'Stock Esperado' "
                "FROM articulos ORDER BY nombre ASC"
            )
            with obtener_conexion() as conn:
                df = pd.read_sql_query(query, conn)

            if df.empty:
                self.lbl_resultado.setText(tr("stock.export_empty", default="No hay artículos para exportar."))
                self.lbl_resultado.setVisible(True)
                return

            # Cabeceras del informe en el idioma activo.
            df.columns = [
                tr("stock.exp_code", default="Código"),
                tr("stock.exp_name", default="Nombre"),
                tr("stock.exp_shelf", default="Stock Lineal"),
                tr("stock.exp_warehouse", default="Stock Almacén"),
                tr("stock.exp_central", default="Stock Almacén Central"),
                tr("stock.exp_expected", default="Stock Esperado"),
            ]

            exports_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../documentos/stocks")
            )
            os.makedirs(exports_dir, exist_ok=True)
            ruta = os.path.join(
                exports_dir,
                f"Stock_Completo_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx",
            )

            with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Stock")
                ws = writer.sheets["Stock"]
                try:
                    from openpyxl.styles import Alignment, Font, PatternFill

                    fill = PatternFill("solid", fgColor="00FFC6")
                    font_header = Font(
                        name="Segoe UI", bold=True, color="0E1117", size=11
                    )
                    font_data = Font(name="Segoe UI", size=10)
                    align_center = Alignment(horizontal="center", vertical="center")
                    for cell in ws[1]:
                        cell.fill = fill
                        cell.font = font_header
                        cell.alignment = align_center
                    for row in ws.iter_rows(min_row=2):
                        for cell in row:
                            cell.font = font_data
                            cell.alignment = align_center
                    for col in ws.columns:
                        max_len = max(len(str(c.value or "")) for c in col)
                        ws.column_dimensions[col[0].column_letter].width = max(
                            14, max_len + 4
                        )
                except Exception:
                    pass

            self.lbl_resultado.setText(tr("stock.export_ok", default="Exportado correctamente:\n{ruta}", ruta=ruta))
            self.lbl_resultado.setVisible(True)
        except Exception as e:
            self.lbl_resultado.setText(tr("stock.export_err", default="Error al exportar:\n{e}", e=e))
            self.lbl_resultado.setVisible(True)

    def _retraducir(self):
        self._lbl_titulo.setText(tr("stock.title_export", default="Exportar Stock"))
        self._lbl_desc.setText(tr("stock.export_desc", default=_EXPORT_DESC_DEFAULT))
        self._btn.setText(tr("stock.export_btn", default="EXPORTAR STOCK"))


class _InventarioPage(QWidget):
    _DRIVE_URL = "https://drive.google.com/drive/my-drive"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._lbl_titulo = lbl_titulo = QLabel(tr("stock.title_inventory", default="Inventario"))
        lbl_titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(f"color: {_CIAN};")
        layout.addWidget(lbl_titulo)

        self._lbl_desc = lbl_desc = QLabel(tr("stock.inventory_desc", default=_INVENTORY_DESC_DEFAULT))
        lbl_desc.setStyleSheet(_DESC_SS)
        lbl_desc.setWordWrap(True)
        lbl_desc.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(lbl_desc)

        icon_lbl = QLabel("📋")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 160px; background: transparent; border: none;"
        )
        icon_lbl.setFixedHeight(200)
        layout.addWidget(icon_lbl)

        self._btn = btn = QPushButton(tr("stock.inventory_btn", default="ABRIR INVENTARIO"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(240, 62)
        btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(self._abrir_drive)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def _retraducir(self):
        self._lbl_titulo.setText(tr("stock.title_inventory", default="Inventario"))
        self._lbl_desc.setText(tr("stock.inventory_desc", default=_INVENTORY_DESC_DEFAULT))
        self._btn.setText(tr("stock.inventory_btn", default="ABRIR INVENTARIO"))

    def _abrir_drive(self):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(self._DRIVE_URL))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MostrarStockWindow(QWidget):
    def __init__(
        self, callback_vuelta=None, usuario=None, stock_signals_instance=None, **kwargs
    ):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        ensure_schema()

        self.signals = stock_signals_instance or stock_signals
        self.signals.stock_actualizado.connect(self._on_stock_actualizado)

        self._setup_ui()
        self.setStyleSheet(f"background-color: {_FONDO}; color: white;")
        i18n.conectar_retraduccion(self, self._retraducir)

    def _setup_ui(self):
        self.setWindowTitle(tr("stock.smart_stock", default="Smart Stock"))
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar (uses global QSS objectNames) ----
        sidebar = QFrame()
        sidebar.setObjectName("sidebar_logistica")
        sidebar.setFixedWidth(280)

        side_ly = QVBoxLayout(sidebar)
        side_ly.setContentsMargins(0, 40, 0, 20)
        side_ly.setSpacing(0)

        lbl_titulo = QLabel(tr("stock.smart_stock_2", default="SMART STOCK"))
        lbl_titulo.setObjectName("sidebar_title")
        side_ly.addWidget(lbl_titulo)

        self._tab_keys = [
            "stock.tab_store", "stock.tab_central", "stock.tab_edit",
            "stock.tab_import", "stock.tab_export", "stock.tab_inventory",
        ]
        _tab_def = ["STOCK TIENDA", "STOCK ALMACÉN CENTRAL", "EDITAR STOCK",
                    "IMPORTAR STOCK", "EXPORTAR STOCK", "INVENTARIO"]

        self._nav_btns = []
        for idx, key in enumerate(self._tab_keys):
            btn = _SidebarBtn(tr(key, default=_tab_def[idx]))
            btn.setObjectName("btn_sidebar")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedHeight(55)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _, i=idx: self._ir_a(i))
            side_ly.addWidget(btn)
            self._nav_btns.append(btn)

        side_ly.addStretch()

        self._btn_exit = btn_exit = _SidebarBtn(tr("stock.exit", default="SALIR AL MENÚ"))
        btn_exit.setObjectName("btn_sidebar_exit")
        btn_exit.setFixedHeight(55)
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
                color: #F85149;
            }
            QPushButton:hover {
                background-color: #F85149;
                color: #0E1117;
            }
        """)
        btn_exit.clicked.connect(self.volver_menu_principal)
        side_ly.addWidget(btn_exit)

        root.addWidget(sidebar)

        # ---- Content area ----
        self._vistas = QStackedWidget()
        self._vistas.setObjectName("contenido_logistica")
        self._vistas.setStyleSheet(f"background-color: {_FONDO};")

        self._page_tienda = _StockTiendaPage()
        self._page_central = _StockCentralPage()
        self._page_editar = _EditarStockPage()
        self._page_importar = _ImportarStockPage()
        self._page_exportar = _ExportarStockPage()
        self._page_inventario = _InventarioPage()

        for page in (
            self._page_tienda,
            self._page_central,
            self._page_editar,
            self._page_importar,
            self._page_exportar,
            self._page_inventario,
        ):
            self._vistas.addWidget(page)

        root.addWidget(self._vistas)
        self._ir_a(0)

    def _retraducir(self):
        _tab_def = ["STOCK TIENDA", "STOCK ALMACÉN CENTRAL", "EDITAR STOCK",
                    "IMPORTAR STOCK", "EXPORTAR STOCK", "INVENTARIO"]
        for i, btn in enumerate(self._nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]))
        self._btn_exit.setText(tr("stock.exit", default="SALIR AL MENÚ"))
        for page in (
            self._page_tienda, self._page_central, self._page_editar,
            self._page_importar, self._page_exportar, self._page_inventario,
        ):
            if hasattr(page, "_retraducir"):
                page._retraducir()

    def _ir_a(self, index: int):
        self._vistas.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
            repolish_widget(btn)

    def _on_stock_actualizado(self, codigo: str):
        if hasattr(self._page_tienda, "cargar"):
            self._page_tienda.cargar()
        if hasattr(self._page_central, "cargar"):
            self._page_central.cargar()

    def volver_menu_principal(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()

    # Backward-compat
    def cargar_stock(self):
        self._page_tienda.cargar()
        self._page_central.cargar()

    def actualizar_stock_articulo(self, codigo: str):
        self._on_stock_actualizado(codigo)
