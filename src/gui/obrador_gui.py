"""
Obrador / producción diaria (edición Bakery). SOLO orquesta `services.obrador` (que produce el terminado y
consume ingredientes por los motores de stock oficiales). Ventana compatible con el menú. El acceso se gatea con
`verticales.visible("bakery.obrador")`.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui._neon_ui import _RoundTableCorners, _RoundWidgetCorners, _ss_lista_neon, _ss_tabla_neon
from src.gui.foundation import tokens as T
from src.services import obrador as _O

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.obrador")


class ObradorWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        self._cargar_partes()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _btn(self, txt, cb, *, primary=False, rojo=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(36)
        col = T.CRITICO if rojo else T.INFO
        if primary:
            # Relleno; al pasar el ratón se invierte a contorno (hover swap).
            b.setStyleSheet(
                f"QPushButton{{background:{col};color:{T.BG};border:2px solid {col};border-radius:8px;"
                f"font-weight:800;padding:6px 14px;}}"
                f"QPushButton:hover{{background:transparent;color:{col};}}")
        else:
            # Contorno; al pasar el ratón se rellena (hover swap).
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{col};border:2px solid {col};border-radius:8px;"
                f"font-weight:800;padding:6px 14px;}}"
                f"QPushButton:hover{{background:{col};color:{T.BG};}}")
        b.clicked.connect(cb)
        return b

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        cab = QHBoxLayout()
        tit = QLabel("🥖  OBRADOR · PRODUCCIÓN DIARIA")
        tit.setStyleSheet(f"color:{T.INFO};font-size:20px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            cab.addWidget(self._btn("✕", self._volver, rojo=True))
        root.addLayout(cab)

        cuerpo = QHBoxLayout(); cuerpo.setSpacing(16)
        izq = QVBoxLayout()
        izq.addWidget(QLabel("Parte de producción"))
        fila_t = QHBoxLayout()
        self.in_turno = QLineEdit(); self.in_turno.setPlaceholderText("Turno (mañana/tarde)")
        self.in_resp = QLineEdit(); self.in_resp.setPlaceholderText("Responsable")
        for w in (self.in_turno, self.in_resp):
            w.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                            "border-radius:8px;padding:6px;}")
        fila_t.addWidget(self.in_turno); fila_t.addWidget(self.in_resp)
        izq.addLayout(fila_t)
        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Producto (código)", "Cantidad"])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)          # ambas columnas del MISMO ancho
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)            # cabeceras centradas
        hh.setHighlightSections(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        self.tabla.setStyleSheet(_ss_tabla_neon())                     # contorno neón + cabeceras redondeadas + hover swap
        self._mask_tabla = _RoundTableCorners(self.tabla, radius=10)
        izq.addWidget(self.tabla, 1)
        add = QHBoxLayout()
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código producto")
        self.in_cant = QSpinBox(); self.in_cant.setRange(1, 100000); self.in_cant.setValue(1)
        self.in_cod.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                                  "border-radius:8px;padding:5px;}")
        add.addWidget(self.in_cod, 2); add.addWidget(self.in_cant); add.addWidget(self._btn("＋", self._add_linea))
        izq.addLayout(add)
        izq.addWidget(self._btn("Registrar producción", self._registrar, primary=True))
        cuerpo.addLayout(izq, 1)

        der = QVBoxLayout()
        der.addWidget(QLabel("Partes recientes"))
        self.lst = QListWidget()
        self.lst.setFrameShape(QListWidget.Shape.NoFrame)
        self.lst.setStyleSheet(_ss_lista_neon())
        self._mask_lst = _RoundWidgetCorners(self.lst, radius=10)
        der.addWidget(self.lst, 1)
        cuerpo.addLayout(der, 1)
        root.addLayout(cuerpo, 1)

    def _add_linea(self, cod=None, cant=None):
        cod = (self.in_cod.text() if cod is None or cod is False else cod).strip()
        if not cod:
            return
        cant = self.in_cant.value() if cant is None else int(cant)
        r = self.tabla.rowCount(); self.tabla.insertRow(r)
        for c, val in ((0, cod), (1, str(cant))):
            it = QTableWidgetItem(val)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)          # contenido centrado (como las cabeceras)
            self.tabla.setItem(r, c, it)
        self.in_cod.clear(); self.in_cant.setValue(1)

    def _items(self):
        out = []
        for r in range(self.tabla.rowCount()):
            cod = (self.tabla.item(r, 0).text() if self.tabla.item(r, 0) else "").strip()
            try:
                cant = int(self.tabla.item(r, 1).text())
            except Exception:
                cant = 0
            if cod and cant > 0:
                out.append({"codigo": cod, "cantidad": cant})
        return out

    def _registrar(self):
        items = self._items()
        if not items:
            self._aviso("Añade al menos un producto.")
            return
        res = _O.registrar_produccion_diaria(items, turno=self.in_turno.text().strip() or None,
                                             responsable=self.in_resp.text().strip() or None,
                                             id_empresa=self._emp(),
                                             usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        if res.get("ok"):
            self.ultima_parte = res["parte"]
            self.tabla.setRowCount(0)
            self._cargar_partes()
            self._aviso(f"Parte #{res['parte']}: {res['producidos']} uds producidas.", "info")
        else:
            self._aviso(res.get("error", "No se pudo registrar la producción."), "error")

    def _cargar_partes(self):
        self.lst.clear()
        try:
            for p in _O.listar_partes(id_empresa=self._emp()):
                it = QListWidgetItem(f"#{p['id']} · {p.get('fecha')} · {p.get('turno') or ''} "
                                     f"· {p.get('responsable') or ''}")
                it.setData(Qt.ItemDataRole.UserRole, p["id"])
                self.lst.addItem(it)
        except Exception as e:
            logger.debug("cargar partes: %s", e)

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Obrador", msg, tipo)
        else:  # pragma: no cover
            logger.info("obrador: %s", msg)
