"""
'Pedir a Central' (LOGÍSTICA) — desde recepción, una tienda solicita mercancía al almacén central y sirve las
solicitudes pendientes. SOLO orquesta `services.logistica.solicitudes` (que mueve el stock por el motor oficial
`traspasar_stock` → kárdex). Autocontenido y testeable offscreen.

`PedidoCentralPanel` es un QWidget EMBEBIBLE (se integra como una pestaña más de la ventana de recepción, sin
ventana emergente). `PedidoCentralDialog` se conserva como envoltura fina (compatibilidad hacia atrás).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui._neon_ui import _RoundTableCorners, _RoundWidgetCorners, _ss_lista_neon, _ss_tabla_neon
from src.gui.foundation import tokens as T
from src.services.logistica import solicitudes as _S

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.pedido_central")


class PedidoCentralPanel(QWidget):
    """Panel embebible de 'Pedir a Central' (se usa como pestaña; también dentro del diálogo de compat)."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        self._cargar_tiendas()
        self._cargar_solicitudes()

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
                            f"border-radius:8px;padding:7px 14px;}}"
                            f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
        b.clicked.connect(cb)
        return b

    def _build(self):
        # Contenido centrado con ancho acotado (se ve limpio al ocupar toda la pestaña maximizada).
        outer = QHBoxLayout(self); outer.setContentsMargins(24, 20, 24, 20); outer.setSpacing(0)
        outer.addStretch(1)
        cont = QWidget(); cont.setMaximumWidth(880)
        ly = QVBoxLayout(cont); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(cont, 5)
        outer.addStretch(1)

        fila = QHBoxLayout(); fila.addWidget(QLabel("Tienda:"))
        self.cb_tienda = QComboBox(); fila.addWidget(self.cb_tienda, 1)
        ly.addLayout(fila)

        # Tabla de artículos a solicitar (contorno neón + cabeceras redondeadas con hover swap + máscara de
        # esquinas para que el contenido y la scrollbar NO sobresalgan del borde al llenarse por 'Sugerir').
        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Código", "Cantidad"])
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.horizontalHeader().setHighlightSections(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        self._mask_tabla = _RoundTableCorners(self.tabla, radius=10)
        self.tabla.setMinimumHeight(150)
        ly.addWidget(self.tabla)

        add = QHBoxLayout()
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código de artículo")
        self.in_cant = QSpinBox(); self.in_cant.setRange(1, 1000000); self.in_cant.setValue(1)
        add.addWidget(self.in_cod, 1); add.addWidget(self.in_cant)
        add.addWidget(self._btn("＋ Añadir", self._add_item))
        add.addWidget(self._btn("✨ Sugerir", self._sugerir))
        ly.addLayout(add)
        ly.addWidget(self._btn("Crear solicitud", self._crear, primary=True))

        ly.addWidget(QLabel("Solicitudes pendientes:"))
        # Lista con contorno neón + filas redondeadas + máscara (la selección/hover no sobresalen con
        # esquinas puntiagudas por fuera del borde).
        self.lst = QListWidget()
        self.lst.setFrameShape(QListWidget.Shape.NoFrame)
        self.lst.setStyleSheet(_ss_lista_neon())
        self._mask_lst = _RoundWidgetCorners(self.lst, radius=10)
        self.lst.setMinimumHeight(140)
        ly.addWidget(self.lst)

        srv = QHBoxLayout(); srv.addStretch()
        srv.addWidget(self._btn("Servir seleccionada", self._servir, primary=True))
        ly.addLayout(srv)

    def _cargar_tiendas(self):
        self.cb_tienda.clear()
        try:
            from src.db.stock_almacen import ensure_almacenes_empresa
            tiendas = ensure_almacenes_empresa(self._emp()).get("tiendas") or {}
            for tid in sorted(tiendas):
                self.cb_tienda.addItem(f"Tienda {tid}", tid)
        except Exception as e:
            logger.debug("cargar tiendas: %s", e)

    def _add_item(self, cod=None, cant=None):
        cod = (self.in_cod.text() if cod is None or cod is False else cod).strip()
        if not cod:
            return
        cant = self.in_cant.value() if cant is None else int(cant)
        r = self.tabla.rowCount(); self.tabla.insertRow(r)
        self.tabla.setItem(r, 0, QTableWidgetItem(cod))
        self.tabla.setItem(r, 1, QTableWidgetItem(str(cant)))
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

    def _sugerir(self):
        tid = self.cb_tienda.currentData()
        if tid is None:
            return
        for it in _S.sugerir_items(tid, id_empresa=self._emp()):
            self._add_item(it["codigo"], it["cantidad"])

    def _crear(self):
        tid = self.cb_tienda.currentData()
        items = self._items()
        if tid is None or not items:
            self._aviso("Selecciona una tienda y añade al menos un artículo.")
            return
        sid = _S.crear_solicitud(tid, items, id_empresa=self._emp(),
                                 usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        if sid:
            self.ultima_sid = sid
            self.tabla.setRowCount(0)
            self._cargar_solicitudes()
            self._aviso(f"Solicitud #{sid} creada.", "info")
        else:
            self._aviso("No se pudo crear la solicitud (revisa tienda/almacenes).", "error")

    def _cargar_solicitudes(self):
        self.lst.clear()
        try:
            for s in _S.listar_solicitudes(id_empresa=self._emp()):
                if s["estado"] in ("PENDIENTE", "PARCIAL"):
                    it = QListWidgetItem(f"#{s['id']} · tienda {s['id_tienda']} · {s['estado']}")
                    it.setData(Qt.ItemDataRole.UserRole, s["id"])
                    self.lst.addItem(it)
        except Exception as e:
            logger.debug("cargar solicitudes: %s", e)

    def _servir(self):
        it = self.lst.currentItem()
        if not it:
            self._aviso("Selecciona una solicitud pendiente.")
            return
        res = _S.servir_solicitud(it.data(Qt.ItemDataRole.UserRole), id_empresa=self._emp(),
                                  usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        self._cargar_solicitudes()
        if res.get("ok"):
            self._aviso(f"Servida ({res['estado']}, {res['movidas']} uds).", "info")
        else:
            self._aviso(res.get("error", "No se pudo servir."), "error")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Pedir a Central", msg, tipo)
        else:  # pragma: no cover
            logger.info("pedido central: %s", msg)


class PedidoCentralDialog(QDialog):
    """Envoltura de compatibilidad: aloja el `PedidoCentralPanel` en un diálogo. La ruta principal (recepción)
    embebe el panel como pestaña; este diálogo se mantiene por retro-compatibilidad de firma."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pedir mercancía al almacén central")
        self.setMinimumWidth(600)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.panel = PedidoCentralPanel(usuario=usuario, parent=self)
        lay.addWidget(self.panel)

    def __getattr__(self, nombre):
        # Delegación: cualquier atributo/método no hallado en el diálogo se busca en el panel (retrocompat).
        panel = self.__dict__.get("panel")
        if panel is not None and hasattr(panel, nombre):
            return getattr(panel, nombre)
        raise AttributeError(nombre)
