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
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db.conexion import obtener_articulo, stock_signals

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
        self._cliente: dict = {}               # cuenta de cliente asociada a la compra (opcional)
        self._asist_clicks: list[float] = []   # zona de asistencia oculta (triple toque en la esquina)
        # ── Métricas de seguridad de la sesión (Capa 3) ──
        self._sec_inicio = time.monotonic()
        self._sec_intervenciones = 0
        self._sec_anulaciones = 0
        self._sec_autorizador = None
        self._ultimo_articulo = None

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

    def keyPressEvent(self, e):
        # Salida de personal (Esc): cierra el terminal. Útil como salida de staff en modo kiosco a
        # pantalla completa (el terminal arranca por rol; no hay botón que lo abra desde el TPV).
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    # ── ZONA DE ASISTENCIA OCULTA (triple toque en la esquina superior derecha) ──────────────────
    # El kiosco NUNCA se transforma en el TPV del cajero. Para intervenciones puntuales (desbloquear
    # peso, anular una línea, cerrar el terminal), el personal hace 3 toques rápidos en la esquina
    # superior derecha y se autoriza con credenciales de un responsable (GERENTE/ADMIN).
    def mousePressEvent(self, e):
        try:
            import time
            pos = e.position().toPoint()
            if pos.x() >= self.width() - 90 and pos.y() <= 90:
                ahora = time.monotonic()
                self._asist_clicks = [t for t in self._asist_clicks if ahora - t <= 1.5]
                self._asist_clicks.append(ahora)
                if len(self._asist_clicks) >= 3:
                    self._asist_clicks = []
                    self._abrir_asistencia()
        except Exception:
            pass
        super().mousePressEvent(e)

    def _abrir_asistencia(self):
        """Pide autorización de un responsable y, si procede, abre el menú de asistencia de personal."""
        try:
            from src.gui.tpv import _AutorizacionDialog
            dlg = _AutorizacionDialog(self)
            if not (dlg.exec() and getattr(dlg, "autorizador", None)):
                return
            autorizador = dlg.autorizador
        except Exception as ex:
            logger.error(f"asistencia (auth): {ex}")
            return
        # Guarda quién autorizó (Capa 3: approved_by_staff).
        self._sec_autorizador = (autorizador.get("nombre") if isinstance(autorizador, dict)
                                 else str(autorizador))
        self._menu_asistencia(autorizador)

    def _menu_asistencia(self, autorizador):
        """Menú flotante de asistencia (no es el TPV): desbloquear peso · anular línea · vaciar · cerrar."""
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        dlg.setStyleSheet(f"QDialog{{background:{_BG};}}")
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setObjectName("asist")
        cont.setStyleSheet(f"QFrame#asist{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        outer.addWidget(cont)
        v = QVBoxLayout(cont)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        nombre = autorizador.get("nombre", "—") if isinstance(autorizador, dict) else str(autorizador)
        v.addWidget(_lbl(tr("autocobro.asist_title", default="🔧  ASISTENCIA DE PERSONAL"),
                         bold=True, size=20, color=_CIAN))
        v.addWidget(_lbl(tr("autocobro.asist_auth", default="Autorizado por: {n}", n=nombre),
                         size=12, color=_TEXT2))
        v.addSpacing(6)

        def _accion(txt, color, slot):
            b = QPushButton(txt)
            b.setFixedHeight(60)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{color};border:2px solid {color};"
                f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:18px;padding:0 18px;}}"
                f"QPushButton:hover{{background:{color};color:#0D1117;}}")
            b.clicked.connect(lambda _=False: (slot(), dlg.accept()))
            v.addWidget(b)

        _accion(tr("autocobro.asist_unlock", default="⚖  Desbloquear peso"), _CIAN,
                self._asist_desbloquear_peso)
        _accion(tr("autocobro.asist_void", default="🗑  Anular línea seleccionada"), _AMBAR,
                lambda: self._asist_anular_linea(autorizador))
        _accion(tr("autocobro.asist_clear", default="✖  Vaciar compra"), _AMBAR, self._asist_vaciar)
        _accion(tr("autocobro.asist_close", default="⏻  Cerrar terminal"), _ROJO, self.close)
        v.addSpacing(4)
        b_cerrar = QPushButton(tr("autocobro.asist_dismiss", default="Cerrar menú"))
        b_cerrar.setFixedHeight(48)
        b_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_TEXT2};border:1px solid {_BORDE};"
            f"border-radius:12px;font-family:'{_FONT}';font-weight:700;font-size:15px;}}"
            f"QPushButton:hover{{border-color:{_TEXT};color:{_TEXT};}}")
        b_cerrar.clicked.connect(dlg.reject)
        v.addWidget(b_cerrar)
        dlg.exec()
        self.inp_scan.setFocus()

    def _asist_desbloquear_peso(self):
        """Desbloquea la zona de embolsado (reutiliza BaggingAreaController.desbloquear del motor)."""
        try:
            self._bagging.desbloquear()
        except Exception:
            pass
        # Capa 3: intervención de peso de personal + incidencia por artículo (señal de merma/packaging).
        self._sec_intervenciones += 1
        art = self._ultimo_articulo or {}
        try:
            from src.services.tpv import autocobro_seguridad as SEC
            SEC.registrar_incidencia(self._id_caja, art.get("codigo"), art.get("nombre"),
                                     SEC.TIPO_BLOQUEO_PESO)
        except Exception:
            pass
        self.lbl_estado.hide()
        self.btn_pagar.setEnabled(self._total() > 0.005)

    def _asist_anular_linea(self, autorizador):
        """Anula la línea SELECCIONADA (override de personal, sin confirmación del cliente)."""
        row = self.lista.currentRow()
        if row is None or row < 0 or row >= len(self._lineas):
            self.lbl_estado.setText(tr("autocobro.asist_sel",
                                       default="Selecciona la línea a anular y repite el gesto."))
            self.lbl_estado.show()
            return
        linea = self._lineas[row]
        try:
            self._bagging.al_eliminar(linea)
            from src.services.tpv import self_checkout_service as SC
            SC.registrar_solicitud_ayuda(
                self._id_caja,
                f"ANULACION LINEA '{linea.get('nombre','?')}' por {autorizador.get('nombre', autorizador) if isinstance(autorizador, dict) else autorizador}")
            # Capa 3: incidencia de anulación por artículo.
            from src.services.tpv import autocobro_seguridad as SEC
            SEC.registrar_incidencia(self._id_caja, linea.get("codigo"), linea.get("nombre"),
                                     SEC.TIPO_ANULACION)
        except Exception:
            pass
        self._sec_anulaciones += 1
        self._lineas.pop(row)
        self._refrescar()

    def _asist_vaciar(self):
        """Vacía la compra completa (override de personal)."""
        self._lineas = []
        try:
            self._bagging.reset()
        except Exception:
            pass
        self.lbl_estado.hide()
        self._cliente = {}
        self._refrescar_cliente_ui()
        self._reset_seguridad_sesion()
        self._refrescar()

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

        # Compra a granel (báscula): mismas 9 familias que el TPV, sin editar precios ni gestión.
        self.btn_granel = QPushButton("⚖  " + tr("autocobro.granel", default="COMPRAR A GRANEL"))
        self.btn_granel.setFixedHeight(58)
        self.btn_granel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_granel.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:3px solid {_CIAN};border-radius:14px;"
            f"font-family:'{_FONT}';font-weight:900;font-size:20px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        self.btn_granel.clicked.connect(self._abrir_granel)
        izq.addWidget(self.btn_granel)

        self.lista = QTableWidget()
        self.lista.setColumnCount(4)
        self.lista.setHorizontalHeaderLabels(["Producto", "Cant.", "Importe", "Acciones"])
        self.lista.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lista.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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

        # ── Asociar la compra a la cuenta de cliente (siempre disponible) ──
        self.btn_cliente = QPushButton()
        self.btn_cliente.setFixedHeight(64)
        self.btn_cliente.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cliente.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:16px;font-family:'{_FONT}';font-weight:900;font-size:18px;padding:0 16px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        self.btn_cliente.clicked.connect(self._asociar_cliente)
        der.addWidget(self.btn_cliente)
        self._refrescar_cliente_ui()

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
        self._ultimo_articulo = articulo   # para la auditoría de seguridad por artículo (Capa 3)
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

    # ── Compra a granel (báscula) ────────────────────────────────────────────
    def _abrir_granel(self):
        """Abre la báscula de granel del TPV (9 familias) SIN gestión ni edición de precios; la línea
        pesada/por unidades se añade a la compra del cliente."""
        try:
            from src.gui.tpv import _BasculaDialog
            dlg = _BasculaDialog(caja_id=self._id_caja, cajero="AUTOCOBRO", parent=self,
                                 mostrar_gestion=False)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                linea = dlg.get_linea()
                if linea:
                    self._add_linea_granel(linea)
        except Exception as e:
            logger.error(f"abrir granel autocobro: {e}")
            self._aviso("No se pudo abrir la venta a granel.")
        self.inp_scan.setFocus()

    def _add_linea_granel(self, linea: dict):
        """Añade al carrito una línea de granel (peso o unidades) y actualiza el antifraude de peso."""
        l = dict(linea)
        # El carrito/registro del autocobro usa 'peso_vendido'; la báscula devuelve 'peso'.
        if l.get("peso") is not None and l.get("peso_vendido") is None:
            l["peso_vendido"] = l.get("peso")
        self._lineas.append(l)
        self._ultimo_articulo = {"codigo": l.get("codigo"), "nombre": l.get("nombre")}
        # Antifraude: el peso esperado sube por el peso pesado (para producto por peso).
        try:
            peso = float(l.get("peso") or 0)
            if peso > 0:
                self._bagging.al_escanear({"peso": peso})
        except Exception:
            pass
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
        # El autocobro SOLO admite pago con TARJETA (crédito/débito). Nunca efectivo.
        if not self._lineas:
            return
        total = self._total()
        box = QMessageBox(self)
        box.setWindowTitle(tr("autocobro.pago_tarjeta", default="Pago con tarjeta"))
        box.setText(tr("autocobro.pago_tarjeta_msg",
                       default="Total: {t}\n\nInserta o acerca tu tarjeta de crédito o débito.",
                       t=divisas.formatear(total)))
        b_pagar = box.addButton(tr("autocobro.pagar_tarjeta", default="PAGAR CON TARJETA"),
                                QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("autocobro.cancelar", default="CANCELAR"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() != b_pagar:
            return
        from src.services.tpv.card_terminal_service import get_terminal
        res = get_terminal().cobrar(total)
        if not res.ok:
            self._aviso(f"Pago rechazado: {res.mensaje}")
            return
        self._finalizar(total, "tarjeta")

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
                cliente=(self._cliente or None),   # compra asociada a la cuenta del cliente (si la hay)
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
        # Capa 3: registra los metadatos de seguridad de la venta (el "security_logs" del ticket).
        try:
            from src.services.tpv import autocobro_seguridad as SEC
            SEC.registrar_venta_seguridad(
                self._id_caja, venta_id,
                intervenciones=self._sec_intervenciones, anulaciones=self._sec_anulaciones,
                autorizado_por=self._sec_autorizador,
                duracion_seg=int(time.monotonic() - self._sec_inicio),
                items=len(self._lineas), total=total,
                id_empresa=empresa_actual_id(), id_tienda=tienda_actual_id())
        except Exception as e:
            logger.debug(f"security_logs no registrado: {e}")
        QMessageBox.information(self, "¡Gracias por tu compra!",
                               f"Compra #{venta_id} completada.\nTotal: {divisas.formatear(total)}")
        self._lineas = []
        self._bagging.reset()
        self.lbl_estado.hide()
        self._cliente = {}
        self._refrescar_cliente_ui()
        self._reset_seguridad_sesion()
        self._refrescar()
        self.inp_scan.setFocus()

    def _reset_seguridad_sesion(self):
        """Reinicia los contadores de seguridad para la siguiente compra."""
        self._sec_inicio = time.monotonic()
        self._sec_intervenciones = 0
        self._sec_anulaciones = 0
        self._sec_autorizador = None
        self._ultimo_articulo = None

    # ── Asociación de cuenta de cliente ──────────────────────────────────────
    def _refrescar_cliente_ui(self):
        if self._cliente and self._cliente.get("id"):
            self.btn_cliente.setText("👤  " + tr("autocobro.cuenta_asociada",
                                                 default="{n}  ✓  (tocar para cambiar)",
                                                 n=self._cliente.get("nombre", "Cliente")))
        else:
            self.btn_cliente.setText(tr("autocobro.asociar_cuenta",
                                        default="👤  ASOCIAR A MI CUENTA"))

    def _asociar_cliente(self):
        dlg = _AsociarClienteDialog(self, ya_asociado=bool(self._cliente.get("id")))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cliente = dlg.cliente or {}     # dlg.cliente = {} → desasociar
            self._refrescar_cliente_ui()
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
        self._cliente = {}
        self._refrescar_cliente_ui()
        self._reset_seguridad_sesion()
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

class _AsociarClienteDialog(QDialog):
    """Asocia la compra del autocobro a una cuenta de cliente: escaneando el código de barras / QR de la
    tarjeta de cliente, o buscando por teléfono o email. Devuelve el cliente en `self.cliente`
    (o {} si el cliente decide desasociar)."""

    def __init__(self, parent=None, ya_asociado=False):
        super().__init__(parent)
        self.cliente = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        try:
            g = self.screen().availableGeometry()
            self.resize(min(720, int(g.width() * 0.6)), min(680, int(g.height() * 0.8)))
        except Exception:
            self.resize(680, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("acbody")
        body.setStyleSheet(f"QFrame#acbody{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(14)

        cab = QHBoxLayout()
        cab.addWidget(_lbl("👤  " + tr("autocobro.asociar_title", default="ASOCIAR A MI CUENTA"),
                           bold=True, size=22, color=_CIAN))
        cab.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(44, 44)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                         f"border-radius:10px;font-weight:900;font-size:18px;}}"
                         f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx.clicked.connect(self.reject)
        cab.addWidget(bx)
        v.addLayout(cab)

        # Opción 1: escanear la tarjeta de cliente.
        v.addWidget(_lbl(tr("autocobro.asociar_scan", default="Escanea el código de tu tarjeta de cliente"),
                         bold=True, size=15, color=_TEXT))
        self.inp_scan_cli = QLineEdit()
        self.inp_scan_cli.setPlaceholderText(tr("autocobro.asociar_scan_ph",
                                                default="Pasa la tarjeta por el escáner…"))
        self.inp_scan_cli.setFixedHeight(54)
        self.inp_scan_cli.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:3px solid {_BORDE};border-radius:14px;"
            f"padding:0 18px;font-size:20px;font-family:'{_FONT}';}}QLineEdit:focus{{border-color:{_CIAN};}}")
        self.inp_scan_cli.returnPressed.connect(self._resolver_scan)
        v.addWidget(self.inp_scan_cli)

        v.addWidget(_lbl(tr("autocobro.asociar_o", default="—  o  —"), size=13, color=_TEXT2))

        # Opción 2: buscar por teléfono o email.
        v.addWidget(_lbl(tr("autocobro.asociar_buscar", default="Busca tu perfil por teléfono o email"),
                         bold=True, size=15, color=_TEXT))
        fila = QHBoxLayout()
        self.inp_busca = QLineEdit()
        self.inp_busca.setPlaceholderText(tr("autocobro.asociar_buscar_ph",
                                             default="Teléfono o correo electrónico…"))
        self.inp_busca.setFixedHeight(54)
        self.inp_busca.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:3px solid {_BORDE};border-radius:14px;"
            f"padding:0 18px;font-size:20px;font-family:'{_FONT}';}}QLineEdit:focus{{border-color:{_CIAN};}}")
        self.inp_busca.returnPressed.connect(self._buscar)
        fila.addWidget(self.inp_busca, 1)
        b_busca = QPushButton("🔎  " + tr("autocobro.asociar_buscar_btn", default="BUSCAR"))
        b_busca.setFixedHeight(54)
        b_busca.setCursor(Qt.CursorShape.PointingHandCursor)
        b_busca.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:3px solid {_CIAN};border-radius:14px;"
            f"font-family:'{_FONT}';font-weight:900;font-size:18px;padding:0 22px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}")
        b_busca.clicked.connect(self._buscar)
        fila.addWidget(b_busca)
        v.addLayout(fila)

        # Resultados de la búsqueda.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        self._res_lay = QVBoxLayout(cont)
        self._res_lay.setContentsMargins(0, 0, 6, 0)
        self._res_lay.setSpacing(8)
        self._res_lay.addStretch()
        scroll.setWidget(cont)
        v.addWidget(scroll, 1)

        self.lbl_status = _lbl("", bold=True, size=14, color=_AMBAR)
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)

        pie = QHBoxLayout()
        if ya_asociado:
            b_quitar = QPushButton(tr("autocobro.asociar_quitar", default="QUITAR ASOCIACIÓN"))
            b_quitar.setFixedHeight(52)
            b_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
            b_quitar.setStyleSheet(
                f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:16px;padding:0 18px;}}"
                f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}")
            b_quitar.clicked.connect(self._quitar)
            pie.addWidget(b_quitar)
        pie.addStretch()
        b_cancel = QPushButton(tr("autocobro.asociar_cancelar", default="CANCELAR"))
        b_cancel.setFixedHeight(52)
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cancel.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_TEXT2};border:2px solid {_BORDE};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:16px;padding:0 22px;}}"
            f"QPushButton:hover{{border-color:{_TEXT};color:{_TEXT};}}")
        b_cancel.clicked.connect(self.reject)
        pie.addWidget(b_cancel)
        v.addLayout(pie)

        QTimer.singleShot(0, self.inp_scan_cli.setFocus)

    def _resolver_scan(self):
        cod = self.inp_scan_cli.text().strip()
        self.inp_scan_cli.clear()
        if not cod:
            return
        try:
            from src.db.clientes import buscar_cliente_por_codigo
            c = buscar_cliente_por_codigo(cod)
        except Exception:
            c = None
        if c:
            self._seleccionar(c)
        else:
            self.lbl_status.setText(tr("autocobro.asociar_scan_no",
                                       default="⚠  Tarjeta no reconocida. Prueba a buscar por teléfono o email."))

    def _buscar(self):
        texto = self.inp_busca.text().strip()
        if not texto:
            return
        try:
            from src.db.clientes import buscar_clientes
            res = buscar_clientes(texto, limite=8)
        except Exception:
            res = []
        while self._res_lay.count() > 1:
            it = self._res_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not res:
            self.lbl_status.setText(tr("autocobro.asociar_sin_res",
                                       default="Sin resultados. Revisa el teléfono o el email."))
            return
        self.lbl_status.setText("")
        for c in res:
            contacto = c.get("telefono") or c.get("email") or c.get("nif") or ""
            b = QPushButton(f"👤  {c.get('nombre','—')}    ·    {contacto}")
            b.setFixedHeight(56)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:12px;"
                f"font-family:'{_FONT}';font-weight:900;font-size:17px;padding:0 16px;text-align:left;}}"
                f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}")
            b.clicked.connect(lambda _=False, cli=c: self._seleccionar(cli))
            self._res_lay.insertWidget(self._res_lay.count() - 1, b)

    def _seleccionar(self, c):
        self.cliente = c
        self.accept()

    def _quitar(self):
        self.cliente = {}
        self.accept()
