"""
Distribución mayorista B2B (R8·it3, función BASE). La ventana SOLO orquesta `services.expediciones`
(pedido → picking → expedición → salida de stock oficial). Se muestra en las versiones donde
`verticales.visible("distribucion.expedicion")` (comercio general con almacén). Compatible con el menú.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.gui.foundation import tokens as T
from src.services import expediciones as _S

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.distribucion")


def _btn(txt, cb, *, primary=False, rojo=False, h=36):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(h)
    col = T.CRITICO if rojo else T.INFO
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{col};color:{T.BG};border:2px solid {col};border-radius:8px;"
                        f"font-weight:800;padding:6px 14px;}}QPushButton:hover{{background:transparent;color:{col};}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:2px solid {col};border-radius:8px;"
                        f"font-weight:800;padding:6px 14px;}}QPushButton:hover{{background:{col};color:{T.BG};}}")
    if cb:
        b.clicked.connect(cb)
    return b


def _inp(ph=""):
    e = QLineEdit(); e.setPlaceholderText(ph); e.setFixedHeight(34)
    e.setStyleSheet(f"QLineEdit{{background:{T.BG};color:{T.TEXT};border:2px solid #30363D;border-radius:8px;"
                    f"padding:0 10px;}}QLineEdit:focus{{border-color:{T.INFO};}}")
    return e


def _tabla(cols):
    t = QTableWidget(0, len(cols)); t.setHorizontalHeaderLabels(cols)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.horizontalHeader().setHighlightSections(False)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setFrameShape(QTableWidget.Shape.NoFrame)
    t.setStyleSheet(_ss_tabla_neon())
    t._round = _RoundTableCorners(t, radius=10)
    return t


def _aviso(parent, titulo, msg, tipo="info"):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, msg, tipo)


class DistribucionWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        self._cargar()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        cab = QHBoxLayout()
        tit = QLabel("📦  DISTRIBUCIÓN · PEDIDOS Y EXPEDICIONES")
        tit.setStyleSheet(f"color:{T.INFO};font-size:20px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            cab.addWidget(_btn("✕", self._volver, rojo=True))
        root.addLayout(cab)

        barra = QHBoxLayout()
        barra.addWidget(_btn("＋  Nuevo pedido", self._nuevo, primary=True))
        barra.addWidget(_btn("📋  Preparar (picking)", self._preparar))
        barra.addWidget(_btn("🧭  Ver ruta", self._ver_ruta))
        barra.addWidget(_btn("🚚  Expedir", self._expedir))
        barra.addStretch()
        barra.addWidget(_btn("🔄  Actualizar", self._cargar))
        root.addLayout(barra)

        self._tbl = _tabla(["ID", "Cliente", "Fecha", "Estado"])
        root.addWidget(self._tbl, 1)
        self._picking_de = {}   # id_pedido -> id_picking (de esta sesión)

    def _cargar(self):
        self._tbl.setRowCount(0)
        for p in _S.listar_pedidos(id_empresa=self._emp()):
            r = self._tbl.rowCount(); self._tbl.insertRow(r)
            for c, val in enumerate((p.get("id"), p.get("cliente_nombre") or p.get("id_cliente") or "—",
                                     p.get("fecha") or "—", p.get("estado"))):
                self._tbl.setItem(r, c, QTableWidgetItem(str(val)))

    def _sel(self):
        r = self._tbl.currentRow()
        if r < 0:
            _aviso(self, "Distribución", "Selecciona un pedido.", "warning"); return None
        try:
            return int(self._tbl.item(r, 0).text())
        except Exception:
            return None

    def _nuevo(self):
        if _NuevoPedidoDialog(self._emp(), self).exec() == QDialog.DialogCode.Accepted:
            self._cargar()

    def _preparar(self):
        pid = self._sel()
        if pid is None:
            return
        pick = _S.preparar(pid, id_empresa=self._emp())
        if pick:
            self._picking_de[pid] = pick
            _aviso(self, "Preparación", f"Picking #{pick} creado para el pedido #{pid}.", "success")
        else:
            _aviso(self, "Preparación", "No se pudo crear el picking.", "error")

    def _ver_ruta(self):
        pid = self._sel()
        if pid is None:
            return
        pick = self._picking_de.get(pid)
        if not pick:
            return _aviso(self, "Ruta", "Prepara primero el picking del pedido.", "warning")
        ordenadas, met = _S.ruta_optima(pick, id_empresa=self._emp())
        _RutaDialog(pick, ordenadas, met, self).exec()

    def _expedir(self):
        pid = self._sel()
        if pid is None:
            return
        if _ExpedirDialog(pid, self._emp(), self).exec() == QDialog.DialogCode.Accepted:
            self._cargar()


class _NuevoPedidoDialog(QDialog):
    """Nuevo pedido mayorista: cliente (buscar/crear) + líneas (código + cantidad, precio mayorista)."""

    def __init__(self, id_empresa, parent=None):
        super().__init__(parent)
        self._emp = id_empresa
        self._lineas = []
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True); self.setMinimumWidth(560)
        self._build()

    def showEvent(self, e):
        # Ventana COMPLETA: el diálogo ocupa toda la ventana padre para que la tabla tenga altura y no
        # se vea aplastada (misma sensación que la ventana de Distribución).
        super().showEvent(e)
        try:
            w = self.parent().window() if self.parent() is not None else None
            if w is not None:
                self.setGeometry(w.geometry())
        except Exception:
            pass

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("dlg_card")
        card.setStyleSheet(f"QFrame#dlg_card{{background:{T.BG};border:2px solid {T.INFO};border-radius:16px;}}")
        root.addWidget(card)
        v = QVBoxLayout(card); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        cab = QHBoxLayout(); tit = QLabel("＋  NUEVO PEDIDO MAYORISTA")
        tit.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch(); cab.addWidget(_btn("✕", self.reject, rojo=True, h=30))
        v.addLayout(cab)

        cf = QHBoxLayout()
        self._cli = _inp("Cliente (empresa) *"); self._nif = _inp("NIF")
        cf.addWidget(self._cli); cf.addWidget(self._nif)
        v.addLayout(cf)

        lf = QHBoxLayout()
        self._cod = _inp("Código artículo"); self._cant = QSpinBox(); self._cant.setRange(1, 1000000)
        self._cant.setFixedHeight(34)
        lf.addWidget(self._cod); lf.addWidget(self._cant); lf.addWidget(_btn("＋ Línea", self._add_linea))
        v.addLayout(lf)
        self._tbl = _tabla(["Artículo", "Cantidad", "Precio (mayorista)"])
        v.addWidget(self._tbl, 1)

        acc = QHBoxLayout(); acc.addStretch(); acc.addWidget(_btn("Crear pedido", self._crear, primary=True))
        v.addLayout(acc)

    def _add_linea(self):
        cod = self._cod.text().strip()
        if not cod:
            return _aviso(self, "Pedido", "Indica el código del artículo.", "warning")
        precio = _S.precio_mayorista(cod, id_empresa=self._emp)
        self._lineas.append({"codigo": cod, "cantidad": self._cant.value()})
        r = self._tbl.rowCount(); self._tbl.insertRow(r)
        for c, val in enumerate((cod, self._cant.value(), f"{precio:.2f}" if precio is not None else "base")):
            self._tbl.setItem(r, c, QTableWidgetItem(str(val)))
        self._cod.clear(); self._cant.setValue(1)

    def _resolver_cliente(self):
        nombre = self._cli.text().strip()
        if not nombre:
            return None
        try:
            from src.db.clientes import buscar_clientes, crear_cliente
            existentes = buscar_clientes(nombre, id_empresa=self._emp) or []
            for c in existentes:
                if str(c.get("nombre", "")).strip().lower() == nombre.lower():
                    return c.get("id")
            return crear_cliente(nombre, nif=self._nif.text().strip() or None, id_empresa=self._emp)
        except Exception as e:
            logger.error("_resolver_cliente: %s", e)
            return None

    def _crear(self):
        if not self._lineas:
            return _aviso(self, "Pedido", "Añade al menos una línea.", "warning")
        cli = self._resolver_cliente()
        if not cli:
            return _aviso(self, "Pedido", "Indica un cliente válido.", "warning")
        pid = _S.crear_pedido(cli, self._lineas, id_empresa=self._emp)
        if pid:
            _aviso(self, "Pedido", f"Pedido #{pid} creado.", "success")
            self.accept()
        else:
            _aviso(self, "Pedido", "No se pudo crear el pedido.", "error")


class _ExpedirDialog(QDialog):
    """Expide un pedido: transportista + dirección → salida de stock oficial + expedición."""

    def __init__(self, id_pedido, id_empresa, parent=None):
        super().__init__(parent)
        self._pid = id_pedido; self._emp = id_empresa
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True); self.setMinimumWidth(460)
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("dlg_card")
        card.setStyleSheet(f"QFrame#dlg_card{{background:{T.BG};border:2px solid {T.INFO};border-radius:16px;}}")
        root.addWidget(card)
        v = QVBoxLayout(card); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        cab = QHBoxLayout(); tit = QLabel(f"🚚  EXPEDIR PEDIDO #{self._pid}")
        tit.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch(); cab.addWidget(_btn("✕", self.reject, rojo=True, h=30))
        v.addLayout(cab)
        v.addWidget(QLabel("Al expedir se descuenta el stock por el motor oficial y se registra la expedición."))
        self._transp = QComboBox(); self._transp.setFixedHeight(34)
        self._transp.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:2px solid #30363D;"
                                   f"border-radius:8px;padding:0 10px;}}")
        self._transp.addItem("— Sin transportista —", None)
        for t in _S.listar_transportistas(id_empresa=self._emp):
            self._transp.addItem(t.get("nombre") or "—", t.get("id"))
        self._dir = _inp("Dirección de entrega")
        v.addWidget(self._transp); v.addWidget(self._dir)
        acc = QHBoxLayout(); acc.addStretch(); acc.addWidget(_btn("Expedir y descontar stock", self._ok, primary=True))
        v.addLayout(acc)

    def _ok(self):
        r = _S.expedir(self._pid, id_transportista=self._transp.currentData(),
                       direccion=self._dir.text().strip() or None, id_empresa=self._emp)
        if r.get("ok"):
            _aviso(self, "Expedición", f"Pedido expedido (venta #{r.get('venta_id')}).", "success")
            self.accept()
        else:
            _aviso(self, "Expedición", r.get("error", "No se pudo expedir."), "error")


class _RutaDialog(QDialog):
    """Muestra la ruta óptima de picking (serpentín)."""

    def __init__(self, id_picking, ordenadas, metricas, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True); self.setMinimumWidth(520)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("dlg_card")
        card.setStyleSheet(f"QFrame#dlg_card{{background:{T.BG};border:2px solid {T.INFO};border-radius:16px;}}")
        root.addWidget(card)
        v = QVBoxLayout(card); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        cab = QHBoxLayout(); tit = QLabel(f"🧭  RUTA DE PICKING · #{id_picking}")
        tit.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch(); cab.addWidget(_btn("✕", self.accept, rojo=True, h=30))
        v.addLayout(cab)
        tbl = _tabla(["Orden", "Artículo", "Cantidad", "Ubicación"])
        for i, ln in enumerate(ordenadas or [], start=1):
            r = tbl.rowCount(); tbl.insertRow(r)
            for c, val in enumerate((i, ln.get("codigo_articulo") or ln.get("codigo") or "—",
                                     ln.get("cantidad") or "—", ln.get("ubicacion") or "—")):
                tbl.setItem(r, c, QTableWidgetItem(str(val)))
        v.addWidget(tbl, 1)
