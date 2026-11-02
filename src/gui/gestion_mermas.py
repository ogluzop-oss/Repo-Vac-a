import logging
import os
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.transiciones import StackedActual

from assets.estilo_global import (
    construir_tabla_estilizada,
    mostrar_confirmacion,
    mostrar_mensaje,
)
from src.db.conexion import _ajustar_stock_articulo_por_tipo, obtener_articulo
from src.gui.components.completer_articulos import (
    instalar_sugerencias_articulo,
    refrescar_sugerencias_articulo,
)
from src.db.mermas import (
    eliminar_merma,
    marcar_mermas_exportadas,
    modificar_merma,
    obtener_mermas,
    obtener_mermas_pendientes,
    registrar_merma,
)
from src.utils import i18n
from src.utils.i18n import tr

logger = logging.getLogger("gui.gestion_mermas")

# Valores lógicos del origen de stock (NO se traducen; son claves internas).
_TIPO_LINEAL = "STOCK LINEAL"
_TIPO_ALMACEN = "STOCK ALMACÉN"


def _tipo_stock_label(tipo):
    """Etiqueta visible (traducida) para un valor lógico de origen de stock."""
    if tipo == _TIPO_LINEAL:
        return tr("merma.stock_shelf", default="STOCK LINEAL")
    return tr("merma.stock_warehouse", default="STOCK ALMACÉN")

# ---------------------------------------------------------------------------
# CONSTANTES Y ESTILOS NEÓN
# ---------------------------------------------------------------------------
_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"

_NEON_BUTTON_INPUT_SS = f"""
QPushButton {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_CIAN};
    border-radius: 12px;
    padding: 12px 20px;
    font-size: 16px;
    font-family: 'Segoe UI';
    font-weight: bold;
}}
QPushButton:hover {{
    border: 2px solid #FFFFFF;
    background-color: #1A2230;
}}
QPushButton:pressed {{
    background-color: {_CIAN};
    color: #0E1117;
    border: 2px solid {_CIAN};
}}
"""
_NEON_INPUT_SS = f"""
QLineEdit, QSpinBox, QComboBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_CIAN};
    border-radius: 12px;
    padding: 12px 20px;
    font-size: 16px;
    font-family: 'Segoe UI';
    font-weight: bold;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 2px solid {_CIAN};
    background-color: #1A2230;
}}
"""

_BTN_CIAN_SS = f"""
QPushButton {{
    background-color: #0E1117;
    color: {_CIAN};
    font-weight: bold;
    border-radius: 14px;
    padding: 15px 30px;
    font-size: 14px;
    font-family: 'Segoe UI';
    border: 2px solid {_CIAN};
}}
QPushButton:hover {{
    background-color: {_CIAN};
    color: #0E1117;
    border: 2px solid {_CIAN};
}}
"""

# ---------------------------------------------------------------------------
# COMPONENTES AUXILIARES
# ---------------------------------------------------------------------------


class _SidebarBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("btn_sidebar")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(55)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #FFFFFF;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px; /* Esquinas puntiagudas */
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
            }}
            QPushButton:hover {{ background-color: #FFFFFF; color: #0E1117; border-radius: 0px; }} /* Hover para el botón de salir */
            QPushButton:checked {{
                background-color: #1A2230;
                border-left: 4px solid {_CIAN};
                color: {_CIAN};
                border-radius: 0px;

            }}
        """)


class _StockSourceDialog(QDialog):
    """Diálogo neón para elegir entre STOCK LINEAL o ALMACÉN."""

    def __init__(self, parent, titulo, mensaje, color="#00FFC6"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resultado = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        # ID en el selector (no el tipo "QFrame" a secas): un selector de TIPO cascada a cualquier
        # descendiente de la MISMA clase — y `QLabel` es subclase de `QFrame` en Qt — así que
        # "QFrame { border: ... }" pintaba el mismo contorno alrededor del título y del mensaje
        # (ambos QLabel) además del contenedor. Con ID, la regla solo afecta a este QFrame concreto.
        container.setObjectName("stock_source_dialog_container")
        container.setStyleSheet(
            f"QFrame#stock_source_dialog_container {{ background-color: #0D1117; "
            f"border: 2px solid {color}; border-radius: 20px; }}"
        )
        layout.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(35, 30, 35, 30)
        inner.setSpacing(20)

        lbl_tit = QLabel(titulo.upper())
        lbl_tit.setStyleSheet(
            f"color: {color}; font-family: 'Segoe UI'; font-weight: 900; font-size: 16px; letter-spacing: 1px;"
        )
        lbl_tit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(lbl_tit)

        lbl_msg = QLabel(mensaje)
        lbl_msg.setStyleSheet(
            "color: white; font-family: 'Segoe UI'; font-weight: 900; font-size: 14px;"
        )
        lbl_msg.setWordWrap(True)
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(lbl_msg)

        self.btn_lineal = QPushButton(tr("merma.stock_shelf", default="STOCK LINEAL"))
        self.btn_almacen = QPushButton(tr("merma.stock_warehouse", default="STOCK ALMACÉN"))
        self.btn_cancelar = QPushButton(tr("merma.cancel_op", default="CANCELAR OPERACIÓN"))

        for btn in [self.btn_lineal, self.btn_almacen]:
            btn.setStyleSheet(_NEON_BUTTON_INPUT_SS)
            btn.setMinimumWidth(200); btn.setMaximumWidth(340)  # responsive (P2)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            inner.addWidget(btn)

        self.btn_cancelar.setStyleSheet(
            "QPushButton { background-color: #8B949E; color: #0E1117; border-radius: 12px; padding: 12px; font-weight: 900; font-size: 13px; }"
            "QPushButton:hover { background-color: #A0A8B0; }"
        )
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)
        inner.addWidget(self.btn_cancelar)

        self.btn_lineal.clicked.connect(lambda: self._finalizar(_TIPO_LINEAL))
        self.btn_almacen.clicked.connect(lambda: self._finalizar(_TIPO_ALMACEN))

    def _finalizar(self, seleccion):
        self.resultado = seleccion
        self.accept()


class _CantidadDialog(QDialog):
    """Diálogo neón (frameless, sin barra de título nativa) para pedir una nueva cantidad —
    sustituye a `QInputDialog.getInt`, que es un diálogo NATIVO de Windows: se ve con la barra de
    título del sistema y sus botones OK/Cancel no heredan bien el estilo oscuro de la app (texto
    invisible sobre fondo claro), rompiendo la coherencia visual con el resto de ventanas."""

    def __init__(self, parent, titulo, mensaje, valor_inicial, minimo=1, maximo=9999):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless

        body = _dialogo_frameless(self, titulo, ancho=320)

        lbl = QLabel(mensaje)
        lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 700; background: transparent;")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(lbl)

        self.spin = QSpinBox()
        self.spin.setRange(minimo, maximo)
        self.spin.setValue(valor_inicial)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setStyleSheet(_NEON_INPUT_SS)
        body.addWidget(self.spin)

        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("merma.cancel", default="CANCELAR"), self.reject))
        fila.addWidget(_btn(tr("merma.accept", default="ACEPTAR"), self.accept, primary=True))
        body.addLayout(fila)

    def valor(self) -> int:
        return self.spin.value()


# ---------------------------------------------------------------------------
# PÁGINAS
# ---------------------------------------------------------------------------


class _RegistrarMermaPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent  # ventana contenedora (para refrescar otras vistas)
        self.articulo_actual = None
        self.tipo_stock_seleccionado = None
        self.cantidad_a_mermar = 0
        self._id_documento_foto = None

        # Permitir que el widget capture eventos de ratón para quitar el foco
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.addStretch(1)

        # Fase 1: Buscador (Centrado)
        self.search_container = QFrame()
        search_ly = QVBoxLayout(self.search_container)

        # Icono de papelera centrado
        self.lbl_papelera = QLabel("🗑️")
        # 72px (antes 140px): un emoji de color a 140px puede pedir mucha más altura real de la
        # reportada aquí — las fuentes de emoji de Windows (Segoe UI Emoji) devuelven métricas de
        # ascenso/descenso desproporcionadas a tamaños grandes, inflando el sizeHint del QLabel muy
        # por encima de lo que se ve en un entorno de pruebas sin esa fuente instalada.
        self.lbl_papelera.setStyleSheet(
            "font-size: 72px; margin-bottom: 20px; background: transparent; border: none;"
        )
        self.lbl_papelera.setFixedHeight(100)
        self.lbl_papelera.setAlignment(Qt.AlignmentFlag.AlignCenter)
        search_ly.addWidget(self.lbl_papelera)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            tr("merma.search_ph", default="🔍 INTRODUCE NOMBRE O CÓDIGO DEL ARTÍCULO...")
        )
        # Fuente 1pt más pequeña (15px) para que quepa el placeholder completo.
        self.search_bar.setStyleSheet(_NEON_INPUT_SS + "QLineEdit{font-size:15px;}")
        # Más ancha para que se vea el texto completo del placeholder.
        self.search_bar.setMinimumWidth(470); self.search_bar.setMaximumWidth(620)
        self.search_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_bar.returnPressed.connect(self._buscar)

        # Sugerencias de artículos: helper compartido, ver gui/components/completer_articulos.py
        # (antes usaba `_get_todos_articulos_para_completer`, que no filtraba por empresa — este
        # helper reutiliza `listar_codigo_nombre`, que sí aísla por tenant).
        self.completer = instalar_sugerencias_articulo(self.search_bar)
        self.search_bar.textChanged.connect(self._on_search_text_changed)

        search_ly.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # Botón BUSCAR justo debajo de la barra de búsqueda.
        self._btn_buscar = QPushButton(tr("merma.search_btn", default="🔍"))
        self._btn_buscar.setStyleSheet(_BTN_CIAN_SS)
        self._btn_buscar.setFixedSize(200, 50)
        self._btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_buscar.clicked.connect(self._buscar)

        # Escaneo remoto (piloto): delega el escaneo del código de artículo al móvil del propio
        # usuario en vez de depender de la webcam del PC. No toca la lógica de búsqueda existente —
        # solo rellena la barra y dispara `_buscar()` con el valor que envíe el móvil.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        self._btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self._on_escaneo_movil, contexto="mermas.buscar_articulo")

        botones_ly = QHBoxLayout()
        botones_ly.addStretch()
        botones_ly.addWidget(self._btn_buscar)
        botones_ly.addSpacing(10)
        botones_ly.addWidget(self._btn_escaneo_movil)
        botones_ly.addStretch()
        search_ly.addSpacing(12)
        search_ly.addLayout(botones_ly)

        layout.addWidget(self.search_container)

        # --- FASE 2: FLUJO DE REGISTRO (QStackedWidget para fases) ---
        self.flow_stacked_widget = QStackedWidget()
        self.flow_stacked_widget.setMinimumWidth(320); self.flow_stacked_widget.setMaximumWidth(600)  # responsive (P2)
        self.flow_stacked_widget.setStyleSheet("background: transparent; border: none;")
        self.flow_stacked_widget.setVisible(False)

        # --- Phase 1: Quantity and Stock Source ---
        self.phase1_widget = QFrame()
        self.phase1_widget.setStyleSheet("background: transparent; border: none;")
        phase1_ly = QVBoxLayout(self.phase1_widget)
        phase1_ly.setSpacing(20)
        phase1_ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_art_info = QLabel("-")
        self.lbl_art_info.setStyleSheet(
            f"color: {_CIAN}; font-size: 22px; font-weight: 900;"
        )
        phase1_ly.addWidget(self.lbl_art_info)

        self._lbl_qty = QLabel(
            tr("merma.qty_label", default="CANTIDAD A MERMAR:"),
            styleSheet="color: white; font-weight: 900;",
        )
        phase1_ly.addWidget(self._lbl_qty)
        self.input_cantidad = QSpinBox()
        self.input_cantidad.setRange(1, 9999)
        self.input_cantidad.setFixedWidth(200)
        self.input_cantidad.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_cantidad.setStyleSheet(_NEON_INPUT_SS)
        phase1_ly.addWidget(self.input_cantidad)

        self._lbl_source = QLabel(
            tr("merma.source_q", default="¿DE DÓNDE DESCONTAR EL STOCK?"),
            styleSheet="color: white; font-weight: bold; font-size: 14px; margin-top: 15px;",
        )
        phase1_ly.addWidget(self._lbl_source)

        self.btn_lineal = QPushButton(tr("merma.stock_shelf", default="STOCK LINEAL"))
        self.btn_almacen = QPushButton(tr("merma.stock_warehouse", default="STOCK ALMACÉN"))
        for btn in (self.btn_lineal, self.btn_almacen):
            btn.setMinimumWidth(240); btn.setMaximumWidth(440)  # responsive (P2)
            btn.setStyleSheet(_NEON_BUTTON_INPUT_SS)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        phase1_ly.addWidget(self.btn_lineal)
        phase1_ly.addWidget(self.btn_almacen)

        self.btn_cancel_phase1 = QPushButton(tr("merma.cancel", default="CANCELAR"))
        self.btn_cancel_phase1.setStyleSheet(
            "QPushButton { background-color: #8B949E; color: #0E1117; border-radius: 12px; padding: 12px; font-weight: 900; font-size: 13px; }"
            "QPushButton:hover { background-color: #A0A8B0; color: #0E1117; }"
        )
        self.btn_cancel_phase1.setFixedWidth(200)
        self.btn_cancel_phase1.clicked.connect(self._reset_flow)
        phase1_ly.addWidget(self.btn_cancel_phase1)

        self.flow_stacked_widget.addWidget(self.phase1_widget)

        # --- Phase 2: Motivo and Register ---
        self.phase2_widget = QFrame()
        self.phase2_widget.setStyleSheet("background: transparent; border: none;")
        phase2_ly = QVBoxLayout(self.phase2_widget)
        phase2_ly.setSpacing(20)
        phase2_ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl_reason = QLabel(
            tr("merma.reason_label", default="MOTIVO DE LA MERMA:"),
            styleSheet="color: white; font-weight: bold; font-size: 14px;",
        )
        phase2_ly.addWidget(self._lbl_reason)
        self.combo_motivo = QComboBox()
        self.combo_motivo.setEditable(True)
        self.combo_motivo.addItems(self._motivos_traducidos())
        self.combo_motivo.setMinimumWidth(240); self.combo_motivo.setMaximumWidth(440)  # responsive (P2)
        self.combo_motivo.setStyleSheet(_NEON_INPUT_SS)
        phase2_ly.addWidget(self.combo_motivo)

        # Foto de evidencia (Rediseño móvil · Grupo B → ahora también desde escritorio, Fase F): OBLIGATORIA
        # para registrar la merma, igual que ya lo es desde el propio móvil. Se pide al móvil del usuario
        # (nunca a la webcam del PC) vía el mismo mecanismo de escaneo remoto, en modo foto.
        self._lbl_foto_estado = QLabel(
            tr("merma.photo_pending", default="📸 Foto de evidencia: pendiente"))
        self._lbl_foto_estado.setStyleSheet("color: #F5A623; font-weight: 900; font-size: 12px;")
        self._lbl_foto_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        phase2_ly.addWidget(self._lbl_foto_estado)

        from src.gui.components.remote_scan import agregar_boton_foto_movil
        self._btn_foto_movil = agregar_boton_foto_movil(
            self, on_result=self._on_foto_movil, contexto="mermas.foto_evidencia")
        phase2_ly.addWidget(self._btn_foto_movil, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_save = QPushButton(tr("merma.save", default="REGISTRAR MERMA"))
        self.btn_save.setStyleSheet(_BTN_CIAN_SS)
        self.btn_save.setMinimumWidth(200); self.btn_save.setMaximumWidth(340)  # responsive (P2)
        self.btn_save.clicked.connect(self._registrar_final)
        phase2_ly.addWidget(self.btn_save)

        self.btn_back_phase2 = QPushButton(tr("merma.back", default="VOLVER"))
        self.btn_back_phase2.setStyleSheet(
            "QPushButton { background-color: #8B949E; color: #0E1117; border-radius: 12px; padding: 12px; font-weight: 900; font-size: 13px; }"
            "QPushButton:hover { background-color: #A0A8B0; color: #0E1117; }"
        )
        self.btn_back_phase2.setFixedWidth(200)
        self.btn_back_phase2.clicked.connect(
            lambda: self.flow_stacked_widget.setCurrentIndex(0)
        )
        phase2_ly.addWidget(self.btn_back_phase2)

        self.flow_stacked_widget.addWidget(self.phase2_widget)

        layout.addWidget(
            self.flow_stacked_widget, alignment=Qt.AlignmentFlag.AlignCenter
        )
        layout.addStretch(1)

        # Connections
        self.btn_lineal.clicked.connect(
            lambda: self._seleccionar_origen(_TIPO_LINEAL)
        )
        self.btn_almacen.clicked.connect(
            lambda: self._seleccionar_origen(_TIPO_ALMACEN)
        )

    @staticmethod
    def _motivos_traducidos():
        return [
            tr("merma.reason_expiry", default="Caducidad"),
            tr("merma.reason_breakage", default="Rotura"),
            tr("merma.reason_theft", default="Robo"),
            tr("merma.reason_sample", default="Muestra"),
            tr("merma.reason_inventory_error", default="Error de Inventario"),
            tr("merma.reason_other", default="Otro"),
        ]

    def _retraducir(self):
        self.search_bar.setPlaceholderText(
            tr("merma.search_ph", default="🔍 INTRODUCE NOMBRE O CÓDIGO DEL ARTÍCULO...")
        )
        self._btn_buscar.setText(tr("merma.search_btn", default="🔍"))
        self._lbl_qty.setText(tr("merma.qty_label", default="CANTIDAD A MERMAR:"))
        self._lbl_source.setText(tr("merma.source_q", default="¿DE DÓNDE DESCONTAR EL STOCK?"))
        self.btn_lineal.setText(tr("merma.stock_shelf", default="STOCK LINEAL"))
        self.btn_almacen.setText(tr("merma.stock_warehouse", default="STOCK ALMACÉN"))
        self.btn_cancel_phase1.setText(tr("merma.cancel", default="CANCELAR"))
        self._lbl_reason.setText(tr("merma.reason_label", default="MOTIVO DE LA MERMA:"))
        actual = self.combo_motivo.currentText()
        self.combo_motivo.clear()
        self.combo_motivo.addItems(self._motivos_traducidos())
        self.combo_motivo.setEditText(actual)
        self.btn_save.setText(tr("merma.save", default="REGISTRAR MERMA"))
        self.btn_back_phase2.setText(tr("merma.back", default="VOLVER"))

    def _on_search_text_changed(self, text):
        if not text.strip():
            self._reset_flow()

    def _on_foto_movil(self, id_documento):
        """Callback del botón "📸 Foto desde el móvil": guarda el id del documento ya subido por el
        móvil (la foto en sí vive en el registro documental, referenciada temporalmente a la propia
        solicitud) — se re-referencia a la merma real en `_registrar_final`, una vez existe su id."""
        self._id_documento_foto = id_documento
        self._lbl_foto_estado.setText(tr("merma.photo_ready", default="📸 Foto de evidencia: recibida ✓"))
        self._lbl_foto_estado.setStyleSheet("color: #2FBF71; font-weight: 900; font-size: 12px;")

    def _on_escaneo_movil(self, valor):
        """Callback del botón "📱 Escanear con el móvil": el móvil ya devuelve el código tal cual
        (sin el formato "CÓDIGO – NOMBRE" del completer), así que `_buscar()` lo usa directamente."""
        self.search_bar.setText(valor)
        self._buscar()

    def _buscar(self):  # Renamed from _buscar_articulo for clarity
        q = self.search_bar.text().strip()
        if not q:
            return

        # Extract code from "CODE – NAME" format if completer is used
        codigo = q.split("–")[0].strip() if "–" in q else q
        art = obtener_articulo(codigo)

        if art:
            self.articulo_actual = art
            self.lbl_art_info.setText(f"{art['nombre'].upper()} ({art['codigo']})")
            self.search_container.setVisible(False)
            self.flow_stacked_widget.setCurrentIndex(0)  # Show Phase 1
            self.flow_stacked_widget.setVisible(True)
            self.input_cantidad.setValue(1)
            # Set max value for spinbox based on available stock
            max_stock = max(
                int(art.get("Stock_tienda", 0)), int(art.get("Stock_total", 0))
            )
            self.input_cantidad.setMaximum(max(1, max_stock))  # Ensure min 1
        else:
            mostrar_mensaje(
                self,
                tr("merma.not_found_title", default="No Encontrado"),
                tr("merma.not_found_msg", default="No se encontró el artículo: {q}", q=q),
                nivel="warning",
            )

    def _seleccionar_origen(self, tipo):
        self.tipo_stock_seleccionado = tipo
        cant = self.input_cantidad.value()
        codigo = self.articulo_actual["codigo"]

        col = "Stock_tienda" if tipo == _TIPO_LINEAL else "Stock_total"
        disponible = int(self.articulo_actual.get(col, 0))

        if cant > disponible:
            mostrar_mensaje(
                self,
                tr("merma.blocked_title", default="Operación Bloqueada"),
                tr("merma.insufficient_msg",
                   default="STOCK INSUFICIENTE EN {tipo}.\nDisponible: {disp}\nSolicitado: {sol}",
                   tipo=_tipo_stock_label(tipo), disp=disponible, sol=cant),
                nivel="error",
            )
            return

        self.cantidad_a_mermar = cant
        self.flow_stacked_widget.setCurrentIndex(1)  # Show Phase 2 (Motivo)

    def _registrar_final(self):
        cant = self.cantidad_a_mermar
        motivo = self.combo_motivo.currentText().strip()
        codigo = self.articulo_actual["codigo"]
        tipo = self.tipo_stock_seleccionado

        if not motivo:
            mostrar_mensaje(
                self,
                tr("merma.error_title", default="Error"),
                tr("merma.empty_reason", default="El motivo de la merma no puede estar vacío."),
                nivel="warning",
            )
            return

        if not self._id_documento_foto:
            mostrar_mensaje(
                self,
                tr("merma.error_title", default="Error"),
                tr("merma.photo_required",
                   default="Haz una foto de evidencia desde el móvil antes de registrar la merma."),
                nivel="warning",
            )
            return

        # A2.3: registro de merma + descuento de stock ATÓMICOS (una transacción).
        _col_merma = "Stock_tienda" if tipo == _TIPO_LINEAL else "Stock_total"
        id_merma = registrar_merma(codigo, cant, self.combo_motivo.currentText(), columna_stock=_col_merma)
        if id_merma:
            # Re-referencia la foto (subida por el móvil con una referencia temporal atada a la propia
            # solicitud de escaneo remoto) a la merma real ya registrada — mismo criterio de "idempotente
            # por ruta" que usa el resto del proyecto para adjuntar evidencias.
            try:
                from src.db.documentos import obtener_documento, registrar_documento
                doc = obtener_documento(self._id_documento_foto)
                if doc and doc.get("ruta"):
                    registrar_documento(
                        doc["ruta"], tipo="merma", nombre=doc.get("nombre"),
                        referencia=f"MERMA:{id_merma}", id_empresa=doc.get("id_empresa"),
                        id_usuario=doc.get("id_usuario"))
            except Exception as e:
                logger.error("re-referenciar foto de merma %s: %s", id_merma, e)
            mostrar_mensaje(
                self,
                tr("merma.success_title", default="Éxito"),
                tr("merma.registered_msg",
                   default="Merma registrada y stock actualizado correctamente."),
                nivel="success",
            )
            self._reset_flow()
            # Optionally refresh other pages if they exist and are visible
            if (
                hasattr(self.main_window, "_page_modificar_eliminar")
                and self.main_window._page_modificar_eliminar.isVisible()
            ):
                self.main_window._page_modificar_eliminar.cargar_datos()

    def _reset_flow(self):
        self.articulo_actual = None
        self.tipo_stock_seleccionado = None
        self.cantidad_a_mermar = 0
        self._id_documento_foto = None
        self._lbl_foto_estado.setText(tr("merma.photo_pending", default="📸 Foto de evidencia: pendiente"))
        self._lbl_foto_estado.setStyleSheet("color: #F5A623; font-weight: 900; font-size: 12px;")
        self.flow_stacked_widget.setVisible(False)
        self.search_container.setVisible(True)
        self.search_bar.clear()
        self.search_bar.setFocus()
        self.flow_stacked_widget.setCurrentIndex(0)  # Reset to first phase

    def mousePressEvent(self, event):
        """Quita la selección de la barra de búsqueda al hacer clic fuera."""
        self.search_bar.clearFocus()
        super().mousePressEvent(event)

    def cargar_datos(self):
        """Refresca el autocompletado al entrar en la pestaña."""
        refrescar_sugerencias_articulo(self.completer)


class _ModificarEliminarMermaPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)

        self._title = title = QLabel(tr("merma.list_title", default="REGISTRO DE MERMAS DEL MES"))
        title.setStyleSheet(
            f"color: {_CIAN}; font-size: 20px; font-weight: 900; letter-spacing: 1px;"
        )
        layout.addWidget(title)

        self.container_tabla, self.tabla = construir_tabla_estilizada(self)
        if self.container_tabla.layout():
            self.container_tabla.layout().setContentsMargins(2, 2, 2, 2)

        # Estética de redondeo superior para no cortar el neón
        self.tabla.horizontalHeader().setStyleSheet(f"""
            QHeaderView {{
                background-color: transparent;
                border: none;
            }}
            QHeaderView::section {{
                background-color: #1A1D23;
                color: {_CIAN};
                border: none;
                padding: 10px;
                font-weight: bold;
            }}
            QHeaderView::section:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
            QHeaderView::section:first {{ border-top-left-radius: 18px; }}
            QHeaderView::section:last {{ border-top-right-radius: 18px; }}
        """)

        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(self._headers())
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.tabla.setColumnWidth(4, 340)
        layout.addWidget(self.container_tabla)

    @staticmethod
    def _headers():
        return [
            tr("merma.col_code", default="CÓDIGO"),
            tr("merma.col_qty", default="CANTIDAD"),
            tr("merma.col_reason", default="MOTIVO"),
            tr("merma.col_date", default="FECHA"),
            tr("merma.col_actions", default="ACCIONES"),
        ]

    def _retraducir(self):
        self._title.setText(tr("merma.list_title", default="REGISTRO DE MERMAS DEL MES"))
        self.tabla.setHorizontalHeaderLabels(self._headers())
        self.cargar_datos()

    def cargar_datos(self):
        self.tabla.setRowCount(0)
        mes_actual = datetime.now().strftime("%Y-%m")
        mermas = obtener_mermas(mes=mes_actual)

        for i, m in enumerate(mermas):
            self.tabla.insertRow(i)
            self.tabla.setRowHeight(i, 66)   # altura suficiente para los botones de acciones
            id_m, cod, cant, mot, fecha, origen = m

            for j, val in enumerate([cod, cant, mot, str(fecha)[:16]]):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    # Origen de stock elegido al REGISTRAR esta merma ("STOCK LINEAL"/"STOCK
                    # ALMACÉN"), guardado en la celda de CÓDIGO (sin columna visible propia) para que
                    # modificar/eliminar lo reutilicen sin volver a preguntar. `None` en mermas
                    # antiguas anteriores a esta migración, o registradas sin descuento de stock.
                    item.setData(Qt.ItemDataRole.UserRole, origen)
                self.tabla.setItem(i, j, item)

            btn_box = QWidget()
            btn_lyt = QHBoxLayout(btn_box)
            btn_lyt.setContentsMargins(5, 2, 5, 2)

            from PyQt6.QtGui import QFont
            _font_acc = QFont("Segoe UI", 13, QFont.Weight.Bold)

            btn_edit = QPushButton(tr("merma.edit_btn", default="MODIFICAR"))
            btn_edit.setFont(_font_acc)
            btn_edit.setStyleSheet(
                "QPushButton { background-color: #0E1117; color: %s; font-family: 'Segoe UI'; "
                "font-weight: bold; font-size: 13px; border-radius: 8px; padding: 6px 12px; "
                "border: 2px solid %s; }"
                "QPushButton:hover { background-color: %s; color: #0E1117; border: 2px solid %s; }"
                % (_CIAN, _CIAN, _CIAN, _CIAN)
            )
            btn_edit.setMinimumHeight(42)
            btn_edit.clicked.connect(lambda _, mid=id_m, r=i: self._modificar(mid, r))

            btn_del = QPushButton(tr("merma.del_btn", default="ELIMINAR"))
            btn_del.setFont(_font_acc)
            btn_del.setStyleSheet(
                "QPushButton { background-color: #0D1117; color: #F85149; font-family: 'Segoe UI'; font-weight: bold; border-radius: 8px; padding: 6px 12px; font-size: 13px; border: 2px solid #F85149; }"
                "QPushButton:hover { background-color: #F85149; color: #0E1117; border: 2px solid #F85149; }"
            )
            btn_del.setMinimumHeight(42)
            btn_del.clicked.connect(lambda _, mid=id_m, r=i: self._eliminar(mid, r))

            btn_lyt.addWidget(btn_edit)
            btn_lyt.addWidget(btn_del)

            # Foto de evidencia (Rediseño móvil · Grupo B): solo la capturan desde el móvil — aquí
            # solo se consulta, de solo lectura, igual que el resto de módulos de este proyecto.
            from src.db.documentos import obtener_por_referencia
            doc_foto = obtener_por_referencia(f"MERMA:{id_m}")
            btn_foto = QPushButton(tr("merma.photo_btn", default="📷 FOTO"))
            btn_foto.setFont(_font_acc)
            btn_foto.setStyleSheet(
                "QPushButton { background-color: #0E1117; color: %s; font-family: 'Segoe UI'; "
                "font-weight: bold; font-size: 13px; border-radius: 8px; padding: 6px 12px; "
                "border: 2px solid %s; }"
                "QPushButton:disabled { color: #4B5563; border: 2px solid #30363D; }"
                "QPushButton:hover:!disabled { background-color: %s; color: #0E1117; }"
                % (_CIAN, _CIAN, _CIAN)
            )
            btn_foto.setMinimumHeight(42)
            btn_foto.setEnabled(bool(doc_foto and doc_foto.get("ruta")))
            if doc_foto and doc_foto.get("ruta"):
                btn_foto.clicked.connect(lambda _, ruta=doc_foto["ruta"]: self._ver_foto(ruta))
            btn_lyt.addWidget(btn_foto)

            self.tabla.setCellWidget(i, 4, btn_box)

    def _ver_foto(self, ruta):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))

    def _modificar(self, id_merma, row):
        codigo = self.tabla.item(row, 0).text()
        cant_antigua = int(self.tabla.item(row, 1).text())
        # Origen de stock elegido al REGISTRAR esta merma (ver `cargar_datos`) — se reutiliza para
        # ajustar el stock sin volver a preguntar; el empleado rara vez recuerda de dónde descontó
        # una merma que ahora está corrigiendo. `None` solo en mermas anteriores a esta migración.
        origen = self.tabla.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg_cant = _CantidadDialog(
            self,
            tr("merma.edit_title", default="Modificar Merma"),
            tr("merma.new_qty_prompt", default="Nueva cantidad para {codigo}:", codigo=codigo),
            cant_antigua,
            1,
            9999,
        )
        if dlg_cant.exec() != QDialog.DialogCode.Accepted:
            return
        nueva_cant = dlg_cant.valor()
        if nueva_cant == cant_antigua:
            return

        art = obtener_articulo(codigo)
        diff = nueva_cant - cant_antigua

        tipo = origen
        if tipo is None:
            # Registro anterior a esta migración: no se guardó su origen, no hay forma fiable de
            # automatizarlo — se sigue preguntando, igual que antes.
            dlg = _StockSourceDialog(
                self,
                tr("merma.increase_title", default="Aumentar Merma") if diff > 0
                else tr("merma.reduce_title", default="Reducir Merma"),
                tr("merma.source_unknown_msg",
                   default="Este registro es anterior y no guarda su origen de stock. "
                           "¿De dónde descontar/sumar?"),
                _CIAN,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            tipo = dlg.resultado

        if diff > 0:
            if diff > int(
                art.get("Stock_tienda" if tipo == _TIPO_LINEAL else "Stock_total", 0)
            ):
                mostrar_mensaje(
                    self,
                    tr("merma.blocked2_title", default="Bloqueado"),
                    tr("merma.db_insufficient", default="Stock insuficiente en la base de datos."),
                    nivel="error",
                )
                return
            adj = -diff
        else:
            adj = abs(diff)

        if modificar_merma(id_merma, nueva_cant):
            _ajustar_stock_articulo_por_tipo(codigo, adj, tipo)
            mostrar_mensaje(
                self,
                tr("merma.success_title", default="Éxito"),
                tr("merma.updated_msg", default="Merma actualizada correctamente."),
                nivel="success",
            )
            self.cargar_datos()

    def _eliminar(self, id_merma, row):
        codigo = self.tabla.item(row, 0).text()
        cantidad = int(self.tabla.item(row, 1).text())
        # Origen elegido al REGISTRAR esta merma (ver `cargar_datos`) — el stock se repone ahí
        # automáticamente, sin volver a preguntar (el empleado ya lo indicó una vez).
        origen = self.tabla.item(row, 0).data(Qt.ItemDataRole.UserRole)

        if origen:
            tipo = origen
            confirmado = mostrar_confirmacion(
                self,
                tr("merma.delete_title", default="Eliminar Registro"),
                tr("merma.delete_confirm",
                   default="¿Seguro que quieres eliminar este registro de merma?\n"
                           "Se repondrán {cant} uds. en {origen}.",
                   cant=cantidad, origen=_tipo_stock_label(origen)),
            )
            if not confirmado:
                return
        else:
            # Registro anterior a esta migración: no se guardó su origen, no hay forma fiable de
            # automatizarlo — se sigue preguntando, igual que antes.
            dlg = _StockSourceDialog(
                self,
                tr("merma.delete_title", default="Eliminar Registro"),
                tr("merma.delete_q", default="Este registro es anterior y no guarda su origen de "
                                              "stock. ¿A dónde desea devolverlo?"),
                _CIAN,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            tipo = dlg.resultado

        if eliminar_merma(id_merma):
            _ajustar_stock_articulo_por_tipo(codigo, cantidad, tipo)
            mostrar_mensaje(
                self,
                tr("merma.success_title", default="Éxito"),
                tr("merma.deleted_msg", default="Registro eliminado y stock repuesto."),
                nivel="success",
            )
            self.cargar_datos()


class _ExportarExcelPage(QWidget):
    """Lista de artículos mermados AÚN NO exportados. Un único botón exporta TODA la
    lista a un Excel, lo registra en Documentos → Exportaciones Excel, y vacía la tabla."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host = parent   # GestionMermasWindow (para navegar a Documentos)
        self._pendientes = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(16)

        # Cabecera: título (izq) + botón "Exportar mermas" (esquina superior derecha).
        cab = QHBoxLayout()
        self._title = title = QLabel(tr("merma.export_pending_title", default="EXPORTAR MERMAS"))
        title.setStyleSheet(
            f"color: {_CIAN}; font-size: 20px; font-weight: 900; letter-spacing: 1px;"
        )
        cab.addWidget(title); cab.addStretch()
        self._btn_export = QPushButton(tr("merma.export_pending_btn", default="EXPORTAR MERMAS"))
        self._btn_export.setStyleSheet(_BTN_CIAN_SS)
        self._btn_export.setMinimumHeight(44)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.clicked.connect(self._exportar_mermas)
        cab.addWidget(self._btn_export)
        layout.addLayout(cab)

        self.container_tabla, self.tabla = construir_tabla_estilizada(self)
        if self.container_tabla.layout():
            self.container_tabla.layout().setContentsMargins(2, 2, 2, 2)

        # Estética de redondeo superior para no cortar el neón
        self.tabla.horizontalHeader().setStyleSheet(f"""
            QHeaderView {{
                background-color: transparent;
                border: none;
            }}
            QHeaderView::section {{
                background-color: #1A1D23;
                color: {_CIAN};
                border: none;
                padding: 10px;
                font-weight: bold;
            }}
            QHeaderView::section:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
            QHeaderView::section:first {{ border-top-left-radius: 18px; }}
            QHeaderView::section:last {{ border-top-right-radius: 18px; }}
        """)

        self.tabla.setColumnCount(2)
        self.tabla.setHorizontalHeaderLabels(self._headers())
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.container_tabla, 1)

        # Mensaje de éxito + "Ver archivo" (oculto hasta exportar).
        self.lbl_msg = QLabel()
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet(f"color: {_CIAN}; font-size: 14px; font-weight: bold;")
        self.lbl_msg.setVisible(False)
        layout.addWidget(self.lbl_msg)

        self.btn_ver = QPushButton(tr("merma.view_file_btn", default="📂 VER ARCHIVO"))
        self.btn_ver.setStyleSheet(_BTN_CIAN_SS)
        self.btn_ver.setMinimumSize(160, 48); self.btn_ver.setMaximumWidth(300)
        self.btn_ver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver.clicked.connect(self._abrir_documentos_exportaciones)
        self.btn_ver.setVisible(False)
        layout.addWidget(self.btn_ver, alignment=Qt.AlignmentFlag.AlignHCenter)

    @staticmethod
    def _headers():
        return [
            tr("merma.col_month", default="MES / AÑO"),
            tr("merma.col_article", default="ARTÍCULO"),
        ]

    def _retraducir(self):
        self._title.setText(tr("merma.export_pending_title", default="EXPORTAR MERMAS"))
        self._btn_export.setText(tr("merma.export_pending_btn", default="EXPORTAR MERMAS"))
        self.btn_ver.setText(tr("merma.view_file_btn", default="📂 VER ARCHIVO"))
        self.tabla.setHorizontalHeaderLabels(self._headers())
        self.cargar_datos()

    def cargar_datos(self):
        self.tabla.setRowCount(0)
        self._pendientes = obtener_mermas_pendientes()
        for i, m in enumerate(self._pendientes):
            self.tabla.insertRow(i)
            fecha = str(m.get("fecha") or "")
            try:
                mes = datetime.strptime(fecha[:7], "%Y-%m").strftime("%m/%Y")
            except Exception:
                mes = fecha[:7]
            articulo = f"{m.get('nombre', '')} ({m.get('codigo', '')})"
            for j, val in enumerate([mes, articulo]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(i, j, item)

    def _exportar_mermas(self):
        pend = self._pendientes or obtener_mermas_pendientes()
        if not pend:
            mostrar_mensaje(
                self,
                tr("merma.export_title", default="Exportación"),
                tr("merma.export_empty", default="No hay mermas pendientes de exportar."),
                nivel="warning",
            )
            return
        try:
            _h = (
                tr("merma.col_code", default="CÓDIGO"),
                tr("merma.col_name", default="ARTÍCULO"),
                tr("merma.col_date", default="FECHA"),
            )
            df = pd.DataFrame([
                {_h[0]: m.get("codigo"), _h[1]: m.get("nombre"),
                 _h[2]: str(m.get("fecha"))[:16]}
                for m in pend
            ])
            ruta_dir = os.path.join(os.getcwd(), "documentos", "mermas")
            os.makedirs(ruta_dir, exist_ok=True)
            name = f"Mermas_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
            path = os.path.join(ruta_dir, name)

            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Mermas")
                ws = writer.sheets["Mermas"]
                from openpyxl.styles import Alignment, Font, PatternFill

                fill = PatternFill(start_color="00FFC6", end_color="00FFC6", fill_type="solid")
                hdr_font = Font(name="Segoe UI", bold=True)
                for cell in ws[1]:
                    cell.fill, cell.font, cell.alignment = (
                        fill, hdr_font, Alignment(horizontal="center"))
                for row in ws.iter_rows(min_row=2):
                    for cell in row:
                        cell.font, cell.alignment = (
                            Font(name="Segoe UI"), Alignment(horizontal="center"))
                for col in ws.columns:
                    max_len = max(len(str(c.value or "")) for c in col)
                    ws.column_dimensions[col[0].column_letter].width = max(16, max_len + 4)

            # Registrar en Documentos → categoría "Exportaciones Excel".
            from src.db.documentos import registrar_documento
            registrar_documento(path, tipo="exportacion", nombre=name, referencia="MERMAS")
            # Marcar como exportadas → la tabla se vaciará al recargar.
            marcar_mermas_exportadas([m.get("id") for m in pend])
        except Exception as e:
            mostrar_mensaje(
                self,
                tr("merma.error_title", default="Error"),
                tr("merma.export_err", default="Fallo al exportar Excel: {e}", e=e),
                nivel="error",
            )
            return

        self.lbl_msg.setText(tr(
            "merma.export_done_msg",
            default=("Las mermas se han exportado correctamente.\n"
                     "Puedes encontrar el archivo en la pestaña «Exportaciones Excel» "
                     "de la función Documentos, donde podrás compartirlo o enviarlo.")))
        self.lbl_msg.setVisible(True)
        self.btn_ver.setVisible(True)
        self.cargar_datos()   # vacía la tabla (ya no hay pendientes)

    def _abrir_documentos_exportaciones(self):
        """Abre Documentos posicionado en la categoría «Exportaciones Excel»."""
        from src.gui.centro_documental import CentroDocumentalWindow
        main = getattr(self._host, "main", None)
        try:
            if main is not None and hasattr(main, "manejar_apertura"):
                main.manejar_apertura(
                    "documentos", CentroDocumentalWindow,
                    callback_vuelta=getattr(main, "mostrar_menu_principal", None),
                    usuario=getattr(self._host, "usuario_actual", None),
                    categoria_inicial="exportacion")
            else:
                self._doc_win = CentroDocumentalWindow(
                    usuario=getattr(self._host, "usuario_actual", None),
                    categoria_inicial="exportacion")
                # Ventana hija abierta fuera de manejar_apertura: sin este flag se ve con la
                # barra de título nativa de Windows (inconsistente con el resto de módulos,
                # todos frameless). Replica el mismo tratamiento + animación de deslizamiento.
                try:
                    self._doc_win.setWindowFlags(
                        self._doc_win.windowFlags() | Qt.WindowType.FramelessWindowHint)
                except Exception:
                    pass
                snap = None
                try:
                    from src.gui.transiciones import capturar_pantalla
                    snap = capturar_pantalla(self._host or self)
                except Exception:
                    pass
                try:
                    from PyQt6.QtWidgets import QApplication
                    self._doc_win.setWindowOpacity(0.0)
                    scr = self._doc_win.screen() or QApplication.primaryScreen()
                    if scr is not None:
                        self._doc_win.setGeometry(scr.availableGeometry())
                except Exception:
                    pass
                self._doc_win.showMaximized()
                try:
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                except Exception:
                    pass
                try:
                    from src.gui.transiciones import deslizar_entrada_modulo
                    deslizar_entrada_modulo(snap, self._doc_win, revelar=self._doc_win)
                except Exception:
                    try:
                        self._doc_win.setWindowOpacity(1.0)
                    except Exception:
                        pass
        except Exception as e:
            mostrar_mensaje(self, tr("merma.error_title", default="Error"),
                            tr("merma.nav_err", default="No se pudo abrir Documentos: {e}", e=e),
                            nivel="error")


class GestionMermasWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        self.main = kwargs.get("main")   # menú principal (para navegar a Documentos)
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")
        self.setWindowTitle(tr("merma.window_title", default="SMART MANAGER - GESTIÓN DE MERMAS"))
        self.resize(1100, 750)
        # Techo explícito de tamaño mínimo: la ventana se abre frameless + maximizada al área
        # disponible de pantalla (menu_principal.manejar_apertura). Sin este límite, Qt calcula el
        # mínimo a partir del árbol de layouts (incluye el emoji de 140px de _RegistrarMermaPage,
        # que con métricas de fuente reales/DPI de Windows puede pedir mucha más altura que en un
        # entorno de pruebas) y, si supera la altura útil real de la pantalla (p. ej. 1366x768 con
        # barra de tareas ≈728px), Windows fuerza la ventana más baja que ese mínimo — Qt no lo
        # gestiona con elegancia: el contenido inferior de la sidebar ("SALIR AL MENÚ") queda fuera
        # del área visible/clicable, y el layout general puede desincronizarse (botones que no
        # responden aunque se vean). Fijar un mínimo bajo, cómodo para cualquier portátil, evita el
        # conflicto de raíz en vez de perseguir la causa exacta en cada resolución/DPI.
        self.setMinimumSize(900, 560)
        self.setStyleSheet(f"background-color: {_FONDO};")

        self.setup_ui()
        i18n.conectar_retraduccion(self, self._retraducir)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        toggle_btn = None
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                toggle_btn = instalar_sidebar_colapsable(
                    self, self.sidebar, usuario=self.usuario_actual, clave="mermas")
        except Exception:
            pass

        # Restricciones por perfil: OPERARIO solo ve "Registrar merma" — "Modificar/Eliminar" y
        # "Exportar mermas" quedan para ADMINISTRADOR/SUPERADMIN (mismo criterio ya aplicado en
        # `mostrar_stock.py`). Se aplica DESPUÉS de `instalar_sidebar_colapsable` porque este, al
        # restaurar el estado expandido/colapsado, vuelve a mostrar todos los botones de la
        # sidebar — y se reconecta al toggle porque cada colapsar/expandir repite ese "mostrar
        # todos".
        if self.perfil == "OPERARIO":
            def _ocultar_restringidas():
                for i in (1, 2):
                    self.nav_btns[i].setVisible(False)
            _ocultar_restringidas()
            if toggle_btn:
                toggle_btn.clicked.connect(_ocultar_restringidas)

    def setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- SIDEBAR ---
        sidebar = QFrame()
        self.sidebar = sidebar  # P3: referencia para el toggle colapsable
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet(
            f"background-color: {_PANEL_BG}; border-right: 1px solid {_BORDE};"
        )
        side_ly = QVBoxLayout(sidebar)
        side_ly.setContentsMargins(0, 40, 0, 20)

        lbl_m = QLabel(tr("merma.smart_losses", default="SMART LOSSES").upper())
        lbl_m.setStyleSheet(  # Sidebar title
            "color: white; font-size: 16px; font-weight: 900; margin-left: 30px; margin-bottom: 35px; letter-spacing: 2px;"
        )
        side_ly.addWidget(lbl_m)

        self._tab_keys = ["merma.tab_register", "merma.tab_edit", "merma.tab_export"]
        _tab_def = ["REGISTRAR MERMA", "MODIFICAR / ELIMINAR", "EXPORTAR MERMAS"]
        self.nav_btns = []
        for idx, key in enumerate(self._tab_keys):
            btn = _SidebarBtn(tr(key, default=_tab_def[idx]).upper())
            btn.clicked.connect(lambda _, i=idx: self._ir_a(i))
            side_ly.addWidget(btn)
            self.nav_btns.append(btn)

        side_ly.addStretch()
        self._btn_exit = btn_exit = _SidebarBtn(tr("merma.exit", default="SALIR AL MENÚ").upper())
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #F85149;
                border: none;
                border-left: 4px solid transparent;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
            }
            QPushButton:hover { /* Hover para el botón de salir */
                background-color: #F85149;
                color: #0E1117;
                border-radius: 0px;
            }
            """)
        btn_exit.clicked.connect(self.volver_menu_principal)
        side_ly.addWidget(btn_exit)
        root.addWidget(sidebar)

        # --- CONTENIDO ---
        # StackedActual (no QStackedWidget "a pelo"): sin esto el ancho mínimo de la ventana
        # reflejaba el máximo de las 3 páginas aunque solo una esté visible, forzando una ventana
        # más ancha que la pantalla real y provocando el fallo nativo de Windows al no poder
        # concederle esa geometría (mismo bug ya resuelto en Contabilidad/RRHH/Cámaras).
        self.vistas = StackedActual()
        self._page_registrar = _RegistrarMermaPage(self)
        self._page_modificar_eliminar = _ModificarEliminarMermaPage(self)
        self._page_exportar = _ExportarExcelPage(self)
        for p in (self._page_registrar, self._page_modificar_eliminar, self._page_exportar):
            self.vistas.addWidget(p)
        root.addWidget(self.vistas)

        self._ir_a(0)

    def _retraducir(self):
        self.setWindowTitle(tr("merma.window_title", default="SMART MANAGER - GESTIÓN DE MERMAS"))
        _tab_def = ["REGISTRAR MERMA", "MODIFICAR / ELIMINAR", "EXPORTAR MERMAS"]
        for i, btn in enumerate(self.nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]).upper())
        self._btn_exit.setText(tr("merma.exit", default="SALIR").upper())
        for page in (self._page_registrar, self._page_modificar_eliminar, self._page_exportar):
            if hasattr(page, "_retraducir"):
                page._retraducir()

    def _ir_a(self, index):
        self.vistas.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        # Refrescar datos de la vista
        widget = self.vistas.widget(index)
        if hasattr(widget, "cargar_datos"):
            widget.cargar_datos()

    def volver_menu_principal(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()
