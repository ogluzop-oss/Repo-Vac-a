# src/gui/autocobro.py
"""
Autocobro — Terminal de autoservicio INDEPENDIENTE (Smart Manager AI).

Diseñado para correr como proceso separado (ver src/autocobro_app.py), en otro
monitor / pantalla táctil. Comparte la MISMA base de datos MariaDB, stock,
ventas y servicios que el TPV del cajero, pero con su propia interfaz pensada
para el cliente final.

Características:
  * Doble plataforma de peso (izquierda sin escanear / derecha escaneada) con
    control antifraude vía services.tpv.self_checkout_service.BaggingAreaController.
  * Sin botón de cierre: el cliente sólo escanea, paga, cancela o pide ayuda.
  * Báscula simulada por defecto (scale_service); driver listo para hardware.
"""
from __future__ import annotations
from src.utils import divisas
from src.utils.i18n import tr

import datetime
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db.conexion import obtener_articulo, obtener_conexion, stock_signals

logger = logging.getLogger("autocobro")

# ── Estilo (coherente con el resto de la app) ──────────────────────────────────
_BG    = "#0E1117"
_BG2   = "#161B22"
_CIAN  = "#00FFC6"
_ROJO  = "#FF4C4C"
_VERDE = "#3FB950"
_AMBAR = "#F1C40F"
_BORDE = "#30363D"
_TEXT  = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT  = "Segoe UI"


def _lbl(text, bold=False, size=12, color=_TEXT):
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;"
    )
    return lb


class AutocobroWindow(QWidget):
    """Ventana principal del terminal de autocobro independiente."""

    def __init__(self, id_caja: str = "AUTO-01", parent=None):
        super().__init__(parent)
        self._id_caja = id_caja
        self._lineas: list[dict] = []

        # Báscula + controlador antifraude de la zona de embolsado
        from src.services.tpv.scale_service import get_scale_manager
        from src.services.tpv.self_checkout_service import BaggingAreaController
        self._scale = get_scale_manager()
        try:
            self._scale.detect_and_connect()
        except Exception:
            pass
        self._bagging = BaggingAreaController()

        self.setWindowTitle(tr("autocobro.autocobro_smart_manager", default="Autocobro — Smart Manager"))
        self.setStyleSheet(f"background:{_BG};")
        self._build_ui()

        # Reloj de cabecera
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabecera (sin botón de cierre)
        cab = QFrame()
        cab.setFixedHeight(88)
        cab.setStyleSheet(f"QFrame{{background:{_BG2};border-bottom:2px solid {_CIAN};}}")
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(40, 0, 40, 0)
        cl.addWidget(_lbl("🛒  AUTOCOBRO", bold=True, size=30, color=_CIAN))
        cl.addStretch()
        self.lbl_reloj = _lbl("", size=14, color=_TEXT2)
        cl.addWidget(self.lbl_reloj)
        root.addWidget(cab)

        body = QHBoxLayout()
        body.setContentsMargins(28, 22, 28, 22)
        body.setSpacing(22)

        # ── Columna izquierda: escaneo + lista ────────────────────────────
        izq = QVBoxLayout()
        izq.setSpacing(12)
        izq.addWidget(_lbl("Escanea tus productos", bold=True, size=22, color=_TEXT))

        self.inp_scan = QLineEdit()
        self.inp_scan.setPlaceholderText(tr("autocobro.pasa_el_codigo_de_barras", default="Pasa el código de barras…"))
        self.inp_scan.setFixedHeight(60)
        self.inp_scan.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:3px solid {_BORDE};"
            f"border-radius:14px;padding:0 20px;font-size:22px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        self.inp_scan.returnPressed.connect(self._escanear)
        izq.addWidget(self.inp_scan)

        self.lista = QTableWidget()
        self.lista.setColumnCount(4)
        self.lista.setHorizontalHeaderLabels(["Producto", "Cant.", "Importe", "Acciones"])
        self.lista.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lista.verticalHeader().setVisible(False)
        self.lista.verticalHeader().setDefaultSectionSize(52)
        # Tabla sin borde propio: el borde neón + esquinas redondeadas los
        # aporta un QFrame contenedor, así el contorno nunca queda cortado.
        self.lista.setStyleSheet(
            f"QTableWidget{{background:transparent;color:{_TEXT};border:none;"
            f"font-family:'{_FONT}';font-size:18px;gridline-color:{_BORDE};}}"
            f"QTableWidget::item{{padding:10px;}}"
            f"QHeaderView::section{{background:{_BG2};color:{_CIAN};border:none;"
            f"border-bottom:2px solid {_CIAN};padding:12px;font-weight:700;font-size:16px;}}"
        )
        self.lista.setFrameShape(QFrame.Shape.NoFrame)
        self.lista.viewport().setStyleSheet("background:transparent;")
        from PyQt6.QtWidgets import QHeaderView
        hh = self.lista.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 90); hh.resizeSection(2, 140); hh.resizeSection(3, 110)

        cont_lista = QFrame()
        cont_lista.setObjectName("cont_lista_autocobro")
        cont_lista.setStyleSheet(
            f"QFrame#cont_lista_autocobro{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:14px;}}"
        )
        _cl = QVBoxLayout(cont_lista)
        _cl.setContentsMargins(6, 6, 6, 6)
        _cl.addWidget(self.lista)
        izq.addWidget(cont_lista, 1)

        # ── Doble plataforma de peso (estado visual) ──────────────────────
        plats = QHBoxLayout()
        plats.setSpacing(14)
        self.card_izq = self._build_plataforma("ZONA SIN ESCANEAR", "Deposita aquí los productos por escanear")
        self.card_der = self._build_plataforma("ZONA ESCANEADA", "Coloca aquí los productos ya escaneados")
        plats.addWidget(self.card_izq)
        plats.addWidget(self.card_der)
        izq.addLayout(plats)
        body.addLayout(izq, 6)

        # ── Columna derecha: total + acciones ─────────────────────────────
        der = QVBoxLayout()
        der.setSpacing(14)

        card_total = QFrame()
        card_total.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_VERDE};border-radius:18px;}}")
        ct = QVBoxLayout(card_total)
        ct.setContentsMargins(24, 18, 24, 18)
        ct.addWidget(_lbl("TOTAL A PAGAR", bold=True, size=18, color=_TEXT2))
        self.lbl_total = _lbl(divisas.formatear(0), bold=True, size=48, color=_VERDE)
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        ct.addWidget(self.lbl_total)
        der.addWidget(card_total)

        # Aviso de estado antifraude
        self.lbl_estado = _lbl("", bold=True, size=15, color=_AMBAR)
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet(
            f"color:{_AMBAR};background:{_BG2};border:1px solid {_AMBAR};"
            f"border-radius:12px;padding:10px;font-family:'{_FONT}';font-weight:900;"
        )
        self.lbl_estado.hide()
        der.addWidget(self.lbl_estado)

        der.addStretch()

        self.btn_pagar = QPushButton(tr("autocobro.pagar", default="PAGAR"))
        self.btn_pagar.setFixedHeight(92)
        self.btn_pagar.setEnabled(False)
        self.btn_pagar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pagar.setStyleSheet(
            f"QPushButton{{background:{_VERDE};color:#0D1117;border:none;border-radius:18px;"
            f"font-family:'{_FONT}';font-weight:900;font-size:32px;}}"
            f"QPushButton:hover{{background:#FFF;}}"
            f"QPushButton:disabled{{background:#1C2128;color:#484F58;}}"
        )
        self.btn_pagar.clicked.connect(self._pagar)
        der.addWidget(self.btn_pagar)

        btn_ayuda = QPushButton(tr("autocobro.solicitar_ayuda", default="🔔  SOLICITAR AYUDA"))
        btn_ayuda.setFixedHeight(78)
        btn_ayuda.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ayuda.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:3px solid {_CIAN};"
            f"border-radius:18px;font-family:'{_FONT}';font-weight:900;font-size:22px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        btn_ayuda.clicked.connect(self._solicitar_ayuda)
        der.addWidget(btn_ayuda)

        btn_cancelar = QPushButton(tr("autocobro.cancelar_compra", default="CANCELAR COMPRA"))
        btn_cancelar.setFixedHeight(60)
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )
        btn_cancelar.clicked.connect(self._cancelar)
        der.addWidget(btn_cancelar)

        body.addLayout(der, 4)
        root.addLayout(body, 1)
        QTimer.singleShot(200, self.inp_scan.setFocus)

    def _build_plataforma(self, titulo: str, sub: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame{{background:{_BG2};border:2px solid {_BORDE};border-radius:14px;}}"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        v.addWidget(_lbl(titulo, bold=True, size=13, color=_CIAN))
        v.addWidget(_lbl(sub, size=10, color=_TEXT2))
        return card

    # ── Lógica de escaneo ────────────────────────────────────────────────────
    def _escanear(self):
        from src.services.tpv import self_checkout_service as SC
        codigo = self.inp_scan.text().strip()
        self.inp_scan.clear()
        if not codigo:
            return
        articulo = obtener_articulo(codigo)
        if not articulo:
            self._aviso("Producto no reconocido. Inténtalo de nuevo o pide ayuda.")
            return
        if SC.es_producto_restringido(articulo):
            if not self._verificar_edad(articulo):
                return

        cod = articulo.get("codigo", codigo)
        precio = float(articulo.get("precio", 0) or 0)
        for l in self._lineas:
            if l["codigo"] == cod:
                l["cantidad"] += 1
                l["subtotal"] = round(l["cantidad"] * l["precio"], 2)
                break
        else:
            self._lineas.append({
                "codigo": cod, "nombre": articulo.get("nombre", "—"),
                "seccion": articulo.get("seccion", ""), "cantidad": 1,
                "precio": precio, "descuento_pct": 0.0, "subtotal": round(precio, 2),
                "peso_unitario": articulo.get("peso_unitario", 0),
            })

        # Antifraude: tras escanear, esperar el depósito en la zona escaneada
        self._bagging.al_escanear(articulo)
        self._refrescar()
        self._verificar_bagging("Coloca el producto en la zona escaneada.")

    def _verificar_bagging(self, msg_espera: str):
        """Comprueba el peso de la zona escaneada. Sin hardware, pasa directo."""
        from src.services.tpv.self_checkout_service import (
            ESTADO_OK,
        )
        if not self._scale.has_hardware:
            # Modo simulado: aceptamos el peso esperado automáticamente.
            self._bagging.verificar(self._bagging.peso_esperado)
            self.lbl_estado.hide()
            self.btn_pagar.setEnabled(self._total() > 0.005)
            return
        peso = self._scale.read_weight() or 0.0
        estado, mensaje = self._bagging.verificar(peso)
        if estado == ESTADO_OK:
            self.lbl_estado.hide()
            self.btn_pagar.setEnabled(self._total() > 0.005)
        else:
            self.btn_pagar.setEnabled(False)
            self.lbl_estado.setText("⚠  " + (mensaje or msg_espera))
            self.lbl_estado.show()

    def _verificar_edad(self, articulo) -> bool:
        from src.services.tpv import self_checkout_service as SC
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("autocobro.producto_restringido", default="Producto restringido"))
        box.setText(tr("autocobro.este_producto_requiere_verif", default="Este producto requiere verificación de edad."))
        box.setInformativeText("Un responsable debe autorizar la venta.")
        box.addButton("CANCELAR", QMessageBox.ButtonRole.RejectRole)
        b_auth = box.addButton("LLAMAR RESPONSABLE", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() != b_auth:
            return False
        try:
            from src.gui.tpv import _AutorizacionDialog
            dlg = _AutorizacionDialog(self)
            if dlg.exec() and getattr(dlg, "autorizador", None):
                SC.registrar_autorizacion_edad(self._id_caja, dlg.autorizador,
                                               articulo.get("nombre", "—"))
                return True
        except Exception as e:
            logger.error(f"verificar_edad: {e}")
        return False

    def _total(self) -> float:
        return round(sum(l["subtotal"] for l in self._lineas), 2)

    def _refrescar(self):
        self.lista.setRowCount(len(self._lineas))
        for row, l in enumerate(self._lineas):
            self.lista.setItem(row, 0, QTableWidgetItem(l["nombre"]))
            it_c = QTableWidgetItem(str(l["cantidad"]))
            it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lista.setItem(row, 1, it_c)
            it_s = QTableWidgetItem(f"{divisas.formatear(l['subtotal'])}")
            it_s.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.lista.setItem(row, 2, it_s)
            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(40, 36)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_ROJO};border:2px solid {_ROJO};"
                f"border-radius:8px;font-size:16px;font-weight:900;}}"
                f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
            )
            btn_del.clicked.connect(lambda _=False, r=row: self._eliminar_linea(r))
            cont = QWidget()
            cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(btn_del)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lista.setCellWidget(row, 3, cont)
        self.lbl_total.setText(f"{divisas.formatear(self._total())}")
        self.btn_pagar.setEnabled(self._total() > 0.005 and not self.lbl_estado.isVisible())

    def _eliminar_linea(self, row: int):
        if not (0 <= row < len(self._lineas)):
            return
        linea = self._lineas[row]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("autocobro.eliminar_articulo", default="Eliminar artículo"))
        box.setText(tr("autocobro.desea_eliminar_este_articulo", default="¿Desea eliminar este artículo de la compra?"))
        box.setInformativeText(linea.get("nombre", ""))
        box.addButton("CANCELAR", QMessageBox.ButtonRole.RejectRole)
        b_del = box.addButton("ELIMINAR", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() != b_del:
            return
        # Antifraude: pedir retirar el artículo de la zona escaneada
        self._bagging.al_eliminar(linea)
        self._lineas.pop(row)
        self._refrescar()
        if self._scale.has_hardware:
            QMessageBox.information(
                self, "Retire el artículo",
                "Retire el artículo de la zona escaneada para continuar.",
            )
            self._verificar_bagging("Retira el artículo eliminado de la zona escaneada.")
        self.inp_scan.setFocus()

    # ── Pago / cancelación / ayuda ─────────────────────────────────────────────
    def _pagar(self):
        if not self._lineas:
            return
        total = self._total()
        box = QMessageBox(self)
        box.setWindowTitle(tr("autocobro.forma_de_pago", default="Forma de pago"))
        box.setText(f"Total: {divisas.formatear(total)}\n\n¿Cómo quieres pagar?")
        b_tarj = box.addButton("TARJETA", QMessageBox.ButtonRole.AcceptRole)
        b_efe = box.addButton("EFECTIVO", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("CANCELAR", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clic = box.clickedButton()
        if clic == b_tarj:
            from src.services.tpv.card_terminal_service import get_terminal
            res = get_terminal().cobrar(total)
            if not res.ok:
                self._aviso(f"Pago rechazado: {res.mensaje}")
                return
            self._finalizar(total, "tarjeta")
        elif clic == b_efe:
            self._aviso("Introduce el efectivo. Un responsable validará el cobro.")
            self._finalizar(total, "efectivo")

    def _finalizar(self, total: float, forma_pago: str):
        fecha = datetime.datetime.now()
        venta_id = None
        try:
            # P0 — RUTA CANÓNICA ÚNICA (igual que el TPV). Persistencia + Verifactu +
            # contabilidad + kárdex + FEFO + stock_almacen + M4 en una sola llamada.
            # Fija el tenant explícitamente (corrige el riesgo de aislamiento del autocobro).
            from src.db.conexion import registrar_venta_con_items
            from src.db.empresa import empresa_actual_id, tienda_actual_id
            items = [{"codigo_articulo": l["codigo"], "nombre": l.get("nombre"),
                      "seccion": l.get("seccion", ""), "cantidad": l["cantidad"],
                      "precio_unitario": l["precio"], "subtotal": l["subtotal"],
                      "peso_vendido": l.get("peso_vendido"), "precio_kg": l.get("precio_kg"),
                      "modo_venta": l.get("modo_venta", "UNIDAD")} for l in self._lineas]
            venta_id = registrar_venta_con_items(
                items, fecha=fecha.strftime("%Y-%m-%d %H:%M:%S"), forma_pago=forma_pago,
                empleado_id="AUTOCOBRO", numero_caja=99, total=total,
                id_empresa=empresa_actual_id(), id_tienda=tienda_actual_id())
            if not venta_id:
                raise RuntimeError("registro de venta no devolvió id")
        except Exception as e:
            self._aviso(f"Error al registrar la compra: {e}")
            return
        for l in self._lineas:
            try:
                stock_signals.stock_actualizado.emit(str(l["codigo"]))
            except Exception:
                pass
        QMessageBox.information(self, "¡Gracias por tu compra!",
                               f"Compra #{venta_id} completada.\nTotal: {divisas.formatear(total)}")
        self._lineas = []
        self._bagging.reset()
        self.lbl_estado.hide()
        self._refrescar()
        self.inp_scan.setFocus()

    def _solicitar_ayuda(self):
        from src.services.tpv import self_checkout_service as SC
        SC.registrar_solicitud_ayuda(self._id_caja, "AYUDA GENERAL")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr("autocobro.ayuda_en_camino", default="Ayuda en camino"))
        box.setText(tr("autocobro.un_responsable_ha_sido_avisa", default="🔔  Un responsable ha sido avisado.\nEspera un momento, por favor."))
        box.exec()

    def _cancelar(self):
        if self._lineas and QMessageBox.question(
            self, "Cancelar compra", "¿Seguro que quieres cancelar la compra?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._lineas = []
        self._bagging.reset()
        self.lbl_estado.hide()
        self._refrescar()
        self.inp_scan.setFocus()

    def _aviso(self, texto: str):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("autocobro.aviso", default="Aviso"))
        box.setText(texto)
        box.exec()
        self.inp_scan.setFocus()

    def _tick(self):
        self.lbl_reloj.setText(datetime.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
