import logging
import os
import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
import qrcode
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Pre-importar reportlab con alias para el generador de PDF de reabastecimiento
try:
    from reportlab.lib import colors as _RL_COLORS
    from reportlab.lib.pagesizes import A4 as _RL_A4
    from reportlab.lib.styles import ParagraphStyle as _RL_PARASTYLE
    from reportlab.lib.styles import getSampleStyleSheet as _RL_STYLES
    from reportlab.lib.units import cm as _RL_CM
    from reportlab.platypus import (
        Paragraph as _RL_PARA,
    )
    from reportlab.platypus import (
        SimpleDocTemplate as _RL_DOC,
    )
    from reportlab.platypus import (
        Spacer as _RL_SPACER,
    )
    from reportlab.platypus import (
        Table as _RL_TABLE,
    )
    from reportlab.platypus import (
        TableStyle as _RL_TABLESTYLE,
    )
    _REPORTLAB_REAB_OK = True
except ImportError:
    _REPORTLAB_REAB_OK = False
from src.utils.i18n import tr
from src.db.conexion import (
    formatear_nombre_centro,
    obtener_articulo,
    obtener_conexion,
    obtener_configuracion,
    obtener_destinos_traspaso,
)
from src.db.logistica import (
    obtener_items_pale_traspaso,
)
from src.gui.components.completer_articulos import instalar_sugerencias_articulo
from src.gui.components.completer_centros import instalar_sugerencias_centro, resolver_id_centro

try:
    from src.db.reabastecimiento import (
        cargar_schedule as _reab_cargar_schedule,
    )
    from src.db.reabastecimiento import (
        eliminar_config as _reab_eliminar_config,
    )
    from src.db.reabastecimiento import (
        guardar_schedule as _reab_guardar_schedule,
    )
    from src.db.reabastecimiento import (
        marcar_articulos_recibidos as _reab_marcar_articulos_recibidos,
    )
    from src.db.reabastecimiento import (
        marcar_envio_hoy as _reab_marcar_envio_hoy,
    )
    from src.db.reabastecimiento import (
        upsert_config as _reab_upsert_config,
    )
    _REAB_DB_OK = True
except ImportError:
    _REAB_DB_OK = False
    def _reab_upsert_config(*a, **kw): pass
    def _reab_eliminar_config(*a): pass
    def _reab_marcar_articulos_recibidos(*a): return 0
    def _reab_cargar_schedule(): return {}
    def _reab_guardar_schedule(*a): return False
    def _reab_marcar_envio_hoy(): pass
from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRectF,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegion,
)
from reportlab.graphics.barcode import code128

# Clase SidebarButton: garantiza hover-swap mediante eventos de entrada/salida
try:
    from assets.estilo_global import (
        COLOR_CIAN,
        COLOR_FONDO_APP,
        COLOR_FONDO_SIDEBAR,
        COLOR_ROJO_ERROR,
        _blindar_tamano_fijo,
        aplicar_estilo_widget,
        construir_tabla_estilizada,
        estilizar_completer,
        feedback_frame_item_resaltado,
        feedback_lineedit_exito,
        mostrar_confirmacion,
        mostrar_mensaje,
        repolish_widget,
    )
except Exception:
    COLOR_FONDO_SIDEBAR = "#111418"
    COLOR_CIAN = "#00FFC6"
    COLOR_FONDO_APP = "#0E1117"
    COLOR_ROJO_ERROR = "#F85149"
    _blindar_tamano_fijo = None
    aplicar_estilo_widget = None
    construir_tabla_estilizada = None
    estilizar_completer = None
    feedback_frame_item_resaltado = None
    feedback_lineedit_exito = None
    mostrar_confirmacion = None
    mostrar_mensaje = None
    repolish_widget = None


# ============================================================
# BLOQUE UTILIDADES DE INTERFAZ
# ============================================================

def _mensaje_ui(parent, titulo, texto, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, texto, nivel=nivel)
    elif nivel == "error":
        QMessageBox.critical(parent, titulo, texto)
    elif nivel == "warning":
        QMessageBox.warning(parent, titulo, texto)
    else:
        QMessageBox.information(parent, titulo, texto)


def _confirmar_ui(parent, titulo, texto):
    if mostrar_confirmacion is not None:
        return mostrar_confirmacion(parent, titulo, texto)
    ret = QMessageBox.question(
        parent,
        titulo,
        texto,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes


class SidebarButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("btn_sidebar")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.setMouseTracking(True)
        except Exception:
            pass
        try:
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self)
        except Exception:
            pass


class _SidebarFrameFilter(QObject):
    def eventFilter(self, watched, event):
        return super().eventFilter(watched, event)


def abrir_pdf(ruta_pdf):
    """Abre un archivo PDF con el visor predeterminado de forma multiplataforma."""
    import os

    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return False

    try:
        from src.utils import plataforma
        plataforma.abrir_archivo(ruta_pdf)
        return True
    except Exception as e:
        print(f"Error al abrir PDF: {e}")
        return False


# ============================================================
# BLOQUE SELECCIÓN LOGÍSTICA
# ============================================================

class SelectorLogisticoExtras(QDialog):
    """Ventana emergente con botones toggle para añadir bultos extra al traspaso (multi-select)."""

    items_confirmados = pyqtSignal(list)  # Lista de nombres confirmados

    _BULTOS = [
        ("BASE PALÉ",       "🪵"),
        ("JAULA REMONTADA", "🔼"),
        ("JAULA PLÁSTICO",  "🧺"),
        ("JAULA CARTÓN",    "📦"),
        ("JAULA METÁLICA",  "⚙️"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.anadir_equipamiento_logistic", default="Añadir Equipamiento Logístico"))
        self.setObjectName("dlg_incidencia")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(460)
        self._drag_pos = None
        self._seleccionados: set = set()
        self._btns: dict = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(18)

        titulo = QLabel(tr("recep.anadir_bulto_extra_al_traspa", default="¿AÑADIR BULTO EXTRA AL TRASPASO?"))
        titulo.setObjectName("titulo_cian")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(titulo)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, (nombre, icono) in enumerate(self._BULTOS):
            btn = QPushButton(f"{icono}\n{nombre}")
            btn.setObjectName("btn_secundario")
            btn.setFixedSize(160, 80)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=nombre: self._toggle(n))
            self._btns[nombre] = btn
            grid.addWidget(btn, idx // 3, idx % 3)

        ly.addLayout(grid)

        h_btns = QHBoxLayout()
        h_btns.setSpacing(12)

        self.btn_skip = QPushButton(tr("recep.seguir_sin_bultos_extra", default="SEGUIR SIN BULTOS EXTRA"))
        self.btn_skip.setObjectName("btn_secundario")
        self.btn_skip.setFixedHeight(46)
        self.btn_skip.setStyleSheet(
            "QPushButton#btn_secundario { color: #4FC3F7; border-color: #4FC3F7; }"
            "QPushButton#btn_secundario:hover { background-color: rgba(79,195,247,0.15); }"
        )
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self.reject)

        self.btn_aceptar = QPushButton(tr("recep.aceptar", default="ACEPTAR"))
        self.btn_aceptar.setObjectName("btn_primario")
        self.btn_aceptar.setFixedHeight(46)
        self.btn_aceptar.setEnabled(False)
        self.btn_aceptar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_aceptar.clicked.connect(self._confirmar)

        h_btns.addWidget(self.btn_skip, 3)
        h_btns.addWidget(self.btn_aceptar, 2)
        ly.addLayout(h_btns)

    def _toggle(self, nombre):
        if nombre in self._seleccionados:
            self._seleccionados.discard(nombre)
            self._btns[nombre].setChecked(False)
            self._btns[nombre].setStyleSheet("")
        else:
            self._seleccionados.add(nombre)
            self._btns[nombre].setChecked(True)
            self._btns[nombre].setStyleSheet(
                "QPushButton { border-color: #00FFC6; color: #00FFC6;"
                "  background-color: rgba(0,255,198,0.12); }"
            )
        self.btn_aceptar.setEnabled(bool(self._seleccionados))

    def _confirmar(self):
        self.items_confirmados.emit(sorted(self._seleccionados))
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# BLOQUE RECEPCIÓN BULTO A BULTO (albarán → palé → ¿bultos?)
# ============================================================

class _SeleccionarPaleDialog(QDialog):
    """Paso obligatorio tras escanear el ALBARÁN: el operario elige uno de sus palés y debe
    ESCANEAR físicamente su código para confirmarlo (no basta con hacer clic — evita recepcionar
    el palé equivocado por error de selección en pantalla)."""

    def __init__(self, documento, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.seleccionar_pale_titulo", default="Elige un palé"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(620)
        self._drag_pos = None
        self.id_pale_confirmado = None
        self._pales = documento.get("pales") or []
        self._id_pale_sel = None
        self._build_ui(documento)

    def _build_ui(self, documento):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(); frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(14)

        titulo = QLabel(tr("recep.seleccionar_pale_lbl", default="ALBARÁN {doc} — ELIGE UN PALÉ",
                           doc=documento.get("id_documento", "")))
        titulo.setObjectName("titulo_cian")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(titulo)

        sub = QLabel(tr("recep.seleccionar_pale_sub",
                        default="Selecciona el palé en la tabla y escanea su etiqueta física para confirmarlo."))
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8B949E;font-size:11px;")
        ly.addWidget(sub)

        self._tabla = QTableWidget(len(self._pales), 4)
        self._tabla.setHorizontalHeaderLabels([
            tr("recep.col_pale", default="Palé"), tr("recep.col_estado", default="Estado"),
            tr("recep.col_articulos", default="Artículos"), tr("recep.col_unidades", default="Unidades"),
        ])
        self._tabla.horizontalHeader().setStretchLastSection(True)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, pale in enumerate(self._pales):
            self._tabla.setItem(row, 0, QTableWidgetItem(str(pale.get("id_visual") or "")))
            estado = str(pale.get("estado") or "")
            it_estado = QTableWidgetItem("✔ RECIBIDO" if estado == "RECIBIDO" else estado)
            self._tabla.setItem(row, 1, it_estado)
            self._tabla.setItem(row, 2, QTableWidgetItem(str(pale.get("num_lineas") or 0)))
            self._tabla.setItem(row, 3, QTableWidgetItem(str(pale.get("total_unidades") or 0)))
        self._tabla.setMinimumHeight(min(60 + 36 * max(len(self._pales), 1), 360))
        self._tabla.itemSelectionChanged.connect(self._on_seleccion)
        ly.addWidget(self._tabla)

        self._lbl_estado = QLabel("")
        self._lbl_estado.setWordWrap(True)
        self._lbl_estado.setStyleSheet("color:#F85149;font-size:11px;font-weight:bold;")
        ly.addWidget(self._lbl_estado)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("recep.cancelar", default="CANCELAR"))
        bc.setObjectName("btn_secundario"); bc.setFixedHeight(44)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.clicked.connect(self.reject)
        self.btn_escanear = QPushButton(tr("recep.escanear_pale_btn", default="📱 ESCANEAR PALÉ SELECCIONADO"))
        self.btn_escanear.setObjectName("btn_primario"); self.btn_escanear.setFixedHeight(44)
        self.btn_escanear.setEnabled(False)
        self.btn_escanear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_escanear.clicked.connect(self._escanear)
        br.addWidget(bc); br.addStretch(1); br.addWidget(self.btn_escanear)
        ly.addLayout(br)

    def _on_seleccion(self):
        filas = self._tabla.selectionModel().selectedRows()
        if not filas:
            self._id_pale_sel = None
            self.btn_escanear.setEnabled(False)
            return
        self._id_pale_sel = self._pales[filas[0].row()].get("id_pale")
        self.btn_escanear.setEnabled(True)
        self._lbl_estado.setText("")

    def _escanear(self):
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(self, on_result=self._verificar_escaneo, contexto="recepcion.pale")

    def _verificar_escaneo(self, codigo):
        from src.db.logistica import resolver_codigo_escaneado
        info = resolver_codigo_escaneado(codigo)
        pale = info.get("pale") if info.get("tipo") == "PALE" else None
        if not pale or pale.get("id_pale") != self._id_pale_sel:
            self._lbl_estado.setText(
                tr("recep.pale_no_coincide",
                   default="El código escaneado no coincide con el palé seleccionado."))
            return
        self.id_pale_confirmado = self._id_pale_sel
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _RevisionBultoDialog(QDialog):
    """Lista editable de los artículos ESPERADOS en un bulto (reparto proporcional al declarar los
    bultos del palé) — el operario corrige la cantidad si encuentra alguna discrepancia real antes
    de confirmar; esa cantidad (no la esperada) es la que se suma al stock."""

    def __init__(self, id_bulto, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.revision_bulto_titulo", default="Revisar bulto"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(560)
        self._drag_pos = None
        self.resultado = None
        self._filas = []  # (codigo, inp_cantidad)
        self._build_ui(id_bulto, items or [])

    def _build_ui(self, id_bulto, items):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(); frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(14)

        titulo = QLabel(tr("recep.revision_bulto_lbl", default="CONTENIDO ESPERADO DE {bulto}",
                           bulto=id_bulto))
        titulo.setObjectName("titulo_cian")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(titulo)

        sub = QLabel(tr("recep.revision_bulto_sub",
                        default="Corrige la cantidad si lo que hay en la caja no coincide con lo esperado."))
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8B949E;font-size:11px;")
        ly.addWidget(sub)

        tabla = QTableWidget(len(items), 3)
        tabla.setHorizontalHeaderLabels([
            tr("recep.col_codigo", default="Código"), tr("recep.col_nombre", default="Nombre"),
            tr("recep.col_cantidad_recibida", default="Cantidad recibida"),
        ])
        tabla.horizontalHeader().setStretchLastSection(True)
        tabla.verticalHeader().setVisible(False)
        for row, item in enumerate(items):
            codigo = str(item.get("codigo") or "")
            nombre = str(item.get("nombre") or codigo)
            cantidad = int(item.get("cantidad") or 0)
            it_cod = QTableWidgetItem(codigo); it_cod.setFlags(it_cod.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabla.setItem(row, 0, it_cod)
            it_nom = QTableWidgetItem(nombre); it_nom.setFlags(it_nom.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabla.setItem(row, 1, it_nom)
            inp = QSpinBox(); inp.setRange(0, 999999); inp.setValue(cantidad)
            tabla.setCellWidget(row, 2, inp)
            self._filas.append((codigo, inp))
        tabla.setMinimumHeight(min(60 + 40 * max(len(items), 1), 420))
        ly.addWidget(tabla)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("recep.cancelar", default="CANCELAR"))
        bc.setObjectName("btn_secundario"); bc.setFixedHeight(44)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.clicked.connect(self.reject)
        self.btn_ok = QPushButton(tr("recep.confirmar_bulto_btn", default="✔ CONFIRMAR RECEPCIÓN DEL BULTO"))
        self.btn_ok.setObjectName("btn_primario"); self.btn_ok.setFixedHeight(44)
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.clicked.connect(self._confirmar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(self.btn_ok)
        ly.addLayout(br)

    def _confirmar(self):
        self.resultado = [{"codigo": codigo, "cantidad": inp.value()} for codigo, inp in self._filas]
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _ListaBultosPaleDialog(QDialog):
    """Pantalla "bulto a bulto" de un palé: lista de bultos + su estado, botón para escanear el
    siguiente bulto pendiente (abre `_RevisionBultoDialog` y confirma la recepción real vía
    `db.logistica.confirmar_recepcion_bulto`) y botón para (re)imprimir sus etiquetas. Se cierra
    sola (Accepted) en cuanto el último bulto queda RECIBIDO — el palé completo pasa a RECIBIDO
    automáticamente en ese momento."""

    def __init__(self, id_pale, centro_receptor, usuario, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.lista_bultos_titulo", default="Recepción por bultos"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(560)
        self._drag_pos = None
        self.id_pale = id_pale
        self.centro_receptor = centro_receptor
        self.usuario = usuario
        self._build_ui()
        self._recargar()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(); frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(14)

        titulo = QLabel(tr("recep.lista_bultos_lbl", default="BULTOS DEL PALÉ {pale}", pale=self.id_pale))
        titulo.setObjectName("titulo_cian")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(titulo)

        self._tabla = QTableWidget(0, 2)
        self._tabla.setHorizontalHeaderLabels([
            tr("recep.col_bulto", default="Bulto"), tr("recep.col_estado", default="Estado"),
        ])
        self._tabla.horizontalHeader().setStretchLastSection(True)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self._tabla)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("recep.cerrar", default="CERRAR"))
        bc.setObjectName("btn_secundario"); bc.setFixedHeight(44)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.clicked.connect(self.reject)
        btn_imprimir = QPushButton(tr("recep.imprimir_etiquetas_btn", default="🖨️ IMPRIMIR ETIQUETAS"))
        btn_imprimir.setObjectName("btn_secundario"); btn_imprimir.setFixedHeight(44)
        btn_imprimir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_imprimir.clicked.connect(self._imprimir_etiquetas)
        self.btn_escanear = QPushButton(tr("recep.escanear_bulto_btn", default="📱 ESCANEAR SIGUIENTE BULTO"))
        self.btn_escanear.setObjectName("btn_primario"); self.btn_escanear.setFixedHeight(44)
        self.btn_escanear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_escanear.clicked.connect(self._escanear)
        br.addWidget(bc); br.addWidget(btn_imprimir); br.addStretch(1); br.addWidget(self.btn_escanear)
        ly.addLayout(br)

    def _recargar(self):
        from src.db.logistica import obtener_bultos_pale
        self._bultos = obtener_bultos_pale(self.id_pale)
        self._tabla.setRowCount(len(self._bultos))
        for row, b in enumerate(self._bultos):
            self._tabla.setItem(row, 0, QTableWidgetItem(str(b.get("id_visual") or "")))
            estado = str(b.get("estado") or "")
            self._tabla.setItem(row, 1, QTableWidgetItem("✔ RECIBIDO" if estado == "RECIBIDO" else estado))
        self._tabla.setMinimumHeight(min(60 + 36 * max(len(self._bultos), 1), 320))

    def _imprimir_etiquetas(self):
        from src.services.logistics import bulto_label_service
        try:
            ruta = bulto_label_service.generar_etiquetas_bultos(self._bultos, self.id_pale)
            abrir_pdf(ruta)
        except Exception as e:
            _mensaje_ui(self, "Error", f"No se pudieron generar las etiquetas: {e}", "error")

    def _escanear(self):
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(self, on_result=self._procesar_escaneo, contexto="recepcion.bulto")

    def _procesar_escaneo(self, codigo):
        from src.db.logistica import confirmar_recepcion_bulto, obtener_items_bulto, resolver_codigo_escaneado
        info = resolver_codigo_escaneado(codigo)
        bulto = info.get("bulto") if info.get("tipo") == "BULTO" else None
        if not bulto or bulto.get("id_pale") != self.id_pale:
            _mensaje_ui(self, "No coincide",
                       "Este bulto no pertenece al palé que estás recepcionando.", "warning")
            return
        if str(bulto.get("estado") or "").upper() == "RECIBIDO":
            _mensaje_ui(self, "Ya recibido", "Este bulto ya había sido recibido.", "warning")
            return
        id_bulto = bulto["id_bulto"]
        items = obtener_items_bulto(id_bulto)
        dlg = _RevisionBultoDialog(id_bulto, items, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.resultado is None:
            return
        res = confirmar_recepcion_bulto(id_bulto, self.centro_receptor, self.usuario, dlg.resultado)
        if not res.get("ok"):
            _mensaje_ui(self, "Error", f"No se pudo confirmar el bulto: {res.get('motivo')}", "error")
            return
        self._recargar()
        if res.get("pale_completo"):
            _mensaje_ui(self, "Palé recibido",
                       "Todos los bultos de este palé han sido recibidos. Stock actualizado.", "success")
            self.accept()
        else:
            _mensaje_ui(self, "Bulto recibido", "Stock actualizado correctamente.", "success")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# BLOQUE GENERACIÓN DE DOCUMENTOS PDF
# ============================================================


class PdfWorker(QObject):
    """
    Coordina la generación de documentos (Albaranes y Etiquetas).
    Versión unificada y autónoma con soporte para Recepciones y Traspasos.
    """

    finished = pyqtSignal(tuple)  # (ruta_albaran, [rutas_etiquetas], id_traspaso)
    error = pyqtSignal(str)

    def __init__(self):
        """
        Constructor limpio para evitar errores de argumentos posicionales.
        Se inicializan los atributos vacíos para ser llenados con configurar().
        """
        super().__init__()
        self.pale_items = []
        self.origen = ""
        self.destino = ""
        self.observaciones = ""
        self.agencia_transporte = ""
        self.usuario = ""
        self.datos_logisticos = {}
        self.id_traspaso = ""
        self.tipo_operacion = "traspaso"
        self._pdf_generado = False

    def configurar(
        self,
        pale_items,
        origen,
        destino,
        observaciones,
        agencia_transporte,
        usuario,
        id_traspaso,
        datos_logisticos=None,
        tipo_operacion="traspaso",
    ):
        """Asigna los datos necesarios justo antes de ejecutar la generación."""
        self.pale_items = pale_items
        self.origen = origen
        self.destino = destino
        self.observaciones = observaciones
        self.agencia_transporte = agencia_transporte
        self.usuario = usuario
        self.id_traspaso = id_traspaso
        self.datos_logisticos = datos_logisticos or {}
        self.tipo_operacion = tipo_operacion.lower()
        self._pdf_generado = False

    def _get_terminos(self):
        """Devuelve los términos correctos según el tipo de operación para el PDF."""
        if self.tipo_operacion == "recepcion":
            return {
                "titulo": "ALBARÁN DE RECEPCIÓN",
                "id_label": "ID RECEPCIÓN:",
                "firma_emisor": "FIRMA PROVEEDOR / SALIDA",
                "firma_receptor": "FIRMA RECEPCIÓN TIENDA",
                "subfolder": "albaranes",
                "prefijo_archivo": "REC",
            }
        else:
            return {
                "titulo": "ALBARÁN DE TRASPASO",
                "id_label": "ID TRASPASO:",
                "firma_emisor": "FIRMA EMISIÓN TIENDA",
                "firma_receptor": "FIRMA RECEPTOR / AGENCIA",
                "subfolder": "albaranes",
                "prefijo_archivo": "ALB",
            }

    def run(self):
        """Ejecuta el proceso de generación — delega en los servicios enterprise."""
        if self._pdf_generado:
            return
        self._pdf_generado = True

        try:
            from src.services.logistics.logistics_pdf_service import generar_albaran_traspaso
            from src.services.logistics.pallet_label_service import generar_etiquetas_pales

            data = self._construir_data_agrupada()

            # Albarán enterprise
            ruta_albaran = generar_albaran_traspaso(data)

            # Etiquetas de palés (solo en traspasos)
            rutas_etiquetas = []
            if self.tipo_operacion == "traspaso" and data.get("pales"):
                ruta_etq = generar_etiquetas_pales(
                    lista_pales=data["pales"],
                    origen=self.origen,
                    destino=self.destino,
                    id_traspaso=self.id_traspaso,
                )
                rutas_etiquetas.append(ruta_etq)

            self.finished.emit((str(ruta_albaran), rutas_etiquetas, self.id_traspaso))

        except Exception as e:
            import traceback
            print(f"DEBUG PDF ERROR: {traceback.format_exc()}")
            self.error.emit(f"Error en el proceso de documentación: {str(e)}")

    def _construir_data_agrupada(self) -> dict:
        """
        Organiza los artículos por palé, calcula pesos totales y
        gestiona los valores nulos/pendientes para el PDF.
        """

        pales_dict = {}
        # Recuperamos pesos desde datos_logisticos
        pesos_pales = self.datos_logisticos.get("peso_bulto", {})
        peso_total_acumulado = 0.0
        total_referencias = 0

        for it in self.pale_items:
            # Identificación de estructura de datos (Dict o List)
            if isinstance(it, dict):
                pale_id_full = it.get("pale_codigo") or it.get("id_visual_pale")
                codigo = it.get("codigo", "LOGISTICA")
                nombre = it.get("nombre", "Sin nombre")
                cantidad = it.get("cantidad", 0)
                es_logistico = it.get("es_logistico", False)
            else:
                pale_id_full = "PAL-GENERAL"
                codigo, nombre, cantidad = it[0], it[1], it[2]
                es_logistico = False

            if not pale_id_full:
                continue

            # Si es la primera vez que vemos este palé, inicializamos su entrada
            if pale_id_full not in pales_dict:
                peso_raw = pesos_pales.get(pale_id_full)

                # Gestión de pesos opcionales (Punto 2)
                if peso_raw in [None, "", "None", 0, 0.0]:
                    peso_v = None  # Se imprimirá como "___ KG"
                else:
                    try:
                        peso_v = float(str(peso_raw).replace(",", "."))
                        peso_total_acumulado += peso_v
                    except (ValueError, TypeError):
                        peso_v = None

                pales_dict[pale_id_full] = {
                    "pale_codigo": pale_id_full,
                    "id_visual": pale_id_full,
                    "peso_pale": peso_v,
                    "articulos": [],
                }

            # Añadimos el artículo al palé correspondiente
            pales_dict[pale_id_full]["articulos"].append(
                {
                    "codigo": codigo,
                    "nombre": nombre,
                    "cantidad": int(cantidad),
                    "es_logistico": es_logistico,
                }
            )
            total_referencias += 1

        return {
            "id_traspaso": self.id_traspaso,
            "tipo_documento": self._get_terminos()["titulo"],
            "origen": self.origen,
            "destino": self.destino,
            "observaciones": self.observaciones,
            "agencia_transporte": self.agencia_transporte,
            "usuario": self.usuario,
            "fecha_envio": self.datos_logisticos.get(
                "fecha_envio", datetime.now().strftime("%d/%m/%Y")
            ),
            "pales": list(pales_dict.values()),
            "peso_total": (
                f"{peso_total_acumulado:.2f}" if peso_total_acumulado > 0 else "Pte."
            ),
            "total_referencias": total_referencias,
            "terminos": self._get_terminos(),
        }

    def generar_pdf_traspaso(self, *, traspaso_data: dict):
        """
        Genera el PDF del Albarán con soporte para pesos opcionales
        y distinción visual de artículos logísticos.
        """

        id_doc = traspaso_data.get("id_traspaso", "TRA-000")
        ruta_pdf = os.path.join(
            os.getcwd(), "documentos", "albaranes", f"ALB_{id_doc}.pdf"
        )
        os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)

        # --- i18n: etiquetas fijas (tr) + nombres de artículo por IA (lote) ---
        from src.utils import ai_translator, i18n
        lang = i18n.current_language()

        def L(clave, defecto):
            return i18n.tr(f"albaran.{clave}", default=defecto)

        # Nivel 2: traducir TODOS los nombres de artículo en UNA sola llamada
        # (dominio logístico), respetando el orden de ideración de la tabla.
        _nombres_raw = [
            a.get("nombre", "")
            for p in traspaso_data.get("pales", [])
            for a in p.get("articulos", [])
        ]
        try:
            _nombres_tr = ai_translator.traducir_lote(_nombres_raw, lang, dominio="logistico")
        except Exception:
            _nombres_tr = _nombres_raw
        _nombres_iter = iter(_nombres_tr)

        styles = getSampleStyleSheet()
        style_n = ParagraphStyle("Normal", fontName="Helvetica", fontSize=8, leading=10)
        style_b = ParagraphStyle(
            "Bold", fontName="Helvetica-Bold", fontSize=8, leading=10
        )
        style_log = ParagraphStyle(
            "Logistico", fontName="Helvetica-Bold", fontSize=8, textColor=colors.grey
        )

        story = []

        # --- CABECERA Y QR ---
        qr = qrcode.make(id_doc)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            qr.save(tmp.name)
            qr_path = tmp.name

        head_data = [
            [
                Paragraph("<b>Smart Manager</b>", styles["Heading1"]),
                "",
                Image(qr_path, 20 * mm, 20 * mm),
            ]
        ]
        head_tab = Table(head_data, colWidths=[10 * cm, 4 * cm, 5 * cm])
        story.append(head_tab)
        story.append(Paragraph(f"<b>{L('doc_title', 'ALBARÁN DE TRASPASO')}</b>", style_b))
        story.append(Spacer(1, 10))

        # --- TABLA DE CONTENIDO ---
        data_table = [
            [
                Paragraph(f"<b>{L('col_pale', 'PALÉ')}</b>", style_b),
                Paragraph(f"<b>{L('col_code', 'CÓDIGO')}</b>", style_b),
                Paragraph(f"<b>{L('col_article', 'ARTÍCULO')}</b>", style_b),
                Paragraph(f"<b>{L('col_units', 'UDS')}</b>", style_b),
            ]
        ]

        for p in traspaso_data.get("pales", []):
            arts = p.get("articulos", [])
            peso_val = p.get("peso_pale")
            texto_peso = f"{peso_val} KG" if peso_val is not None else "_______ KG"

            for i, a in enumerate(arts):
                # Punto 4: Resaltado de Jaulas y Logística
                # Nombre traducido por IA (mismo orden que el lote).
                nombre = next(_nombres_iter, a.get("nombre", ""))
                current_style = style_n
                if a.get("es_logistico"):
                    nombre = f"[LOG] {nombre}"
                    current_style = style_log

                data_table.append(
                    [
                        Paragraph(p.get("pale_codigo", "")) if i == 0 else "",
                        Paragraph(str(a.get("codigo", ""))),
                        Paragraph(nombre, current_style),
                        Paragraph(str(a.get("cantidad", 0))),
                    ]
                )

            # Fila de resumen de bulto (Punto 2)
            data_table.append(
                [
                    "",
                    "",
                    Paragraph(f"<b>{L('declared_weight', 'Peso declarado:')}</b>", style_n),
                    Paragraph(f"<b>{texto_peso}</b>", style_n),
                ]
            )
            data_table.append(
                [
                    "",
                    "",
                    Paragraph(L("total_units", "Total unidades bulto:"), style_n),
                    Paragraph(str(sum(x["cantidad"] for x in arts))),
                ]
            )

        table_art = Table(
            data_table, colWidths=[3.5 * cm, 3.5 * cm, 9.5 * cm, 2.5 * cm]
        )
        table_art.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            )
        )
        story.append(table_art)

        # Generación final
        doc = SimpleDocTemplate(ruta_pdf, pagesize=A4)
        doc.build(story)
        if os.path.exists(qr_path):
            os.remove(qr_path)
        return ruta_pdf

    def generar_etiqueta_pdf(
        self, lista_pales, origen, destino, secuencial_traspaso
    ) -> str:
        """
        Genera etiquetas de palés (4 por A4) EXACTAMENTE iguales al modelo.
        Formato ID: PAL-[Sigla]-[Secuencial]-[Origen]
        Nomenclatura Archivo: ETIS_[Origen]_[Secuencial]_[Destino]_[Año].pdf
        """

        # 1. Configuración de Identificadores
        anio = datetime.now().year
        # Limpiamos el secuencial para que solo sea el número (ej: 001)
        sec_str = str(secuencial_traspaso).split("-")[-1].zfill(3)
        orig_clean = str(origen).strip().upper().replace(" ", "_").replace("/", "-")
        dest_clean = str(destino).strip().upper().replace(" ", "_").replace("/", "-")

        # ID Maestro del Traspaso para referencia
        id_maestro = f"TRA-{orig_clean}-{sec_str}-{anio}"
        nombre_archivo = f"ETIS_{orig_clean}_{sec_str}_{dest_clean}_{anio}.pdf"

        # Gestión de rutas absoluta para robustez en Windows
        base_path = Path(os.getcwd())
        out_dir = base_path / "documentos" / "etiquetas_pales"
        out_dir.mkdir(parents=True, exist_ok=True)
        ruta_pdf = str(out_dir / nombre_archivo)

        c = canvas.Canvas(ruta_pdf, pagesize=A4)
        width_a4, height_a4 = A4

        # Coordenadas para 4 etiquetas por página
        posiciones = [
            (0, height_a4 / 2),  # Superior Izquierda
            (width_a4 / 2, height_a4 / 2),  # Superior Derecha
            (0, 0),  # Inferior Izquierda
            (width_a4 / 2, 0),  # Inferior Derecha
        ]

        def dibujar_etiqueta(canv, x_off, y_off, pale_data):
            w_eti = width_a4 / 2
            h_eti = height_a4 / 2

            # --- MARCO PERIMETRAL ---
            canv.setStrokeColorRGB(0, 0, 0)
            canv.setLineWidth(0.2)
            canv.rect(x_off + 5 * mm, y_off + 5 * mm, w_eti - 10 * mm, h_eti - 10 * mm)

            # --- 1. CÓDIGO DE BARRAS (Superior) ---
            sigla = str(pale_data.get("id_visual", "PAL")).upper().replace(" ", "")
            # ID según modelo: PAL-PALE1-001-TRA-ORIGEN
            id_etiqueta = f"PAL-{sigla}-{sec_str}-TRA-{orig_clean}"

            # Generación de código de barras Code128
            barcode = code128.Code128(id_etiqueta, barHeight=25 * mm, barWidth=1.2)
            barcode.drawOn(
                canv, x_off + (w_eti - barcode.width) / 2, y_off + h_eti - 35 * mm
            )

            # --- 2. RUTA ---
            canv.setFont("Helvetica-Bold", 16)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + h_eti - 45 * mm,
                f"{orig_clean} >> {dest_clean}",
            )

            # --- 3. ID DE ETIQUETA Y PESO ---
            canv.setFont("Helvetica-Bold", 14)
            canv.drawCentredString(
                x_off + w_eti / 2, y_off + h_eti - 55 * mm, id_etiqueta
            )

            # Recuadro para el Peso (Destacado)
            peso_val = f"{pale_data.get('peso', 0.0)} KG"
            canv.setFont("Helvetica-Bold", 20)
            canv.rect(
                x_off + w_eti / 2 - 30 * mm,
                y_off + 35 * mm,
                60 * mm,
                12 * mm,
                stroke=1,
                fill=0,
            )
            canv.drawCentredString(x_off + w_eti / 2, y_off + 38 * mm, peso_val)

            # --- 4. REFERENCIA MAESTRA Y SISTEMA ---
            canv.setFont("Helvetica", 9)
            canv.drawCentredString(
                x_off + w_eti / 2, y_off + 25 * mm, f"REF ALBARÁN: {id_maestro}"
            )

            canv.setFont("Helvetica-Bold", 8)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + 15 * mm,
                "SISTEMA LOGÍSTICO - SMART MANAGER",
            )

            canv.setFont("Helvetica", 7)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + 10 * mm,
                f"GEN: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            )

        # Generar las etiquetas solicitadas
        for i, pale in enumerate(lista_pales):
            dibujar_etiqueta(c, posiciones[i % 4][0], posiciones[i % 4][1], pale)
            # Si llenamos una página (4 etiquetas) y hay más, creamos página nueva
            if (i + 1) % 4 == 0 and (i + 1) < len(lista_pales):
                c.showPage()

        c.save()
        return ruta_pdf


# ============================================================
# BLOQUE RECEPCIÓN DE MERCANCÍA
# ============================================================

class RecepcionStockPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        # Punto 3: Unificación de variable de usuario
        self.usuario = usuario
        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz principal de recepción con estilo GitHub Dark."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("panel_contenido")

        # --- PANEL DE BIENVENIDA (ÚNICA VISTA) ---
        self.vista_inicio = QFrame()
        layout_inicio = QVBoxLayout(self.vista_inicio)
        layout_inicio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_inicio.setSpacing(20)

        # Contenedor Central Estilizado (Siguiendo estilo_global.py)
        container = QFrame()
        container.setObjectName("panel_bienvenida")
        # Responsive (P2): se adapta a pantallas estrechas; tope visual en pantallas anchas.
        container.setMaximumWidth(550)
        container.setMinimumWidth(320)  # Ligeramente más ancho para mejor legibilidad
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(15)

        # Icono distintivo de Recepción
        self.lbl_icono = QLabel("📥")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_titulo = QLabel(tr("recep.centro_de_recepcion_logistic", default="CENTRO DE RECEPCIÓN LOGÍSTICA"))
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            tr("recep.presione_el_boton_para_abrir", default="Presione el botón para abrir el escáner y\nvalidar la entrada de palés o artículos.")
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central de Acción (Estilo Global Neón)
        self.btn_iniciar = QPushButton(tr("recep.iniciar_escaneo_2", default="🚀  INICIAR ESCANEO"))
        self.btn_iniciar.setObjectName("btn_primario")
        self.btn_iniciar.setFixedWidth(320)
        self.btn_iniciar.setFixedHeight(60)
        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)

        # Mantenemos tu conexión lógica intacta
        self.btn_iniciar.clicked.connect(self.abrir_flujo_recepcion)

        # Montaje de la UI
        container_layout.addWidget(self.lbl_icono)
        container_layout.addWidget(self.lbl_titulo)
        container_layout.addWidget(self.lbl_info)
        container_layout.addSpacing(25)
        container_layout.addWidget(self.btn_iniciar)

        layout_inicio.addWidget(container)
        self.main_layout.addWidget(self.vista_inicio)

    def abrir_flujo_recepcion(self):
        """Abre el escaneo remoto (móvil) y procesa el resultado."""
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(
            self, on_result=self.procesar_codigo_escaneado, contexto="recepcion.flujo_recepcion")

    def procesar_codigo_escaneado(self, codigo):
        """
        Busca el Palé Impersonal en MariaDB y recupera su contenido.
        """
        codigo = str(codigo).strip().upper()
        if not codigo:
            return

        # 1. SI ES UN PALÉ (ID Impersonal: PAL-XXX-YYY-TRP-...)
        if codigo.startswith("PAL"):

            # Esta función debe buscar en 'traspasos_detalle' filtrando por id_pale
            items = obtener_items_pale_traspaso(codigo)

            if items:
                # 'items' será una lista de diccionarios con: codigo, nombre, cantidad, origen, etc.
                # Lanzamos el diálogo de confirmación que mostrará el contenido del palé
                self.abrir_confirmacion_recepcion(codigo, items)
            else:
                _mensaje_ui(
                    self,
                    "No Encontrado",
                    f"El palé {codigo} no existe, ya fue recibido o no está asignado a este centro.",
                    "warning",
                )

        # 2. SI ES UN ARTÍCULO INDIVIDUAL (EAN/REF)
        else:

            art = obtener_articulo(codigo)

            if art:
                self.procesar_entrada_individual(art)
            else:
                _mensaje_ui(
                    self,
                    "Error",
                    f"El artículo {codigo} no está registrado en el maestro.",
                    "error",
                )

    def procesar_entrada_individual(self, art):
        """
        Procesa el artículo obtenido de la DB y lo añade a la tabla de la interfaz.
        'art' es un diccionario devuelto por MariaDB (DictCursor).
        """

        if not art:
            _mensaje_ui(
                self, "Error", "El artículo no existe en la base de datos.", "warning"
            )
            return

        # Extraemos los datos del diccionario (Claves exactas de MariaDB)
        codigo = str(art.get("codigo", "---"))
        nombre = str(art.get("nombre", "Artículo Desconocido"))

        # Priorizamos 'Stock_central' que es la columna que acabamos de crear
        stock_actual = art.get("Stock_central", art.get("Stock_total", 0))

        # Buscamos si el artículo ya está en la tabla para sumar cantidad
        encontrado = False
        # self.tabla_items debe estar definida en tu setup_ui o clase
        for row in range(self.tabla_items.rowCount()):
            item_codigo_tabla = self.tabla_items.item(row, 0)
            if item_codigo_tabla and item_codigo_tabla.text() == codigo:
                # Si ya existe, sumamos 1 a la cantidad (Columna 2)
                item_cant = self.tabla_items.item(row, 2)
                if item_cant:
                    nueva_cant = int(item_cant.text()) + 1
                    item_cant.setText(str(nueva_cant))
                encontrado = True
                break

        if not encontrado:
            # Si es nuevo, añadimos una fila nueva a la tabla
            row_pos = self.tabla_items.rowCount()
            self.tabla_items.insertRow(row_pos)

            self.tabla_items.setItem(row_pos, 0, QTableWidgetItem(codigo))
            self.tabla_items.setItem(row_pos, 1, QTableWidgetItem(nombre))
            self.tabla_items.setItem(
                row_pos, 2, QTableWidgetItem("1")
            )  # Cantidad inicial
            self.tabla_items.setItem(row_pos, 3, QTableWidgetItem(str(stock_actual)))

        # Limpiamos el campo de entrada (Ajustado a tu nombre de widget: input_codigo_manual)
        if hasattr(self, "input_codigo_manual"):
            self.input_codigo_manual.clear()
            self.input_codigo_manual.setFocus()
        elif hasattr(self, "input_codigo"):
            self.input_codigo.clear()
            self.input_codigo.setFocus()

    def procesar_entrada_manual(self):
        """Maneja el texto escrito en el QLineEdit y pulsado Enter."""
        codigo = self.input_manual.text().strip().upper()
        if codigo:
            self.procesar_codigo_escaneado(codigo)
            self.input_manual.clear()

    def setup_interfaz_camara(self):
        """Crea los widgets necesarios para ver la cámara y el input manual."""
        layout_cam = QVBoxLayout(self.vista_scanner)
        layout_cam.setContentsMargins(20, 20, 20, 20)
        layout_cam.setSpacing(15)

        # Contenedor del Feed de Vídeo — con parent explícito para evitar ventana flotante
        self.lbl_video = QLabel(self.vista_scanner)
        self.lbl_video.setObjectName("feed_video")
        self.lbl_video.setProperty("activo", True)
        self.lbl_video.setFixedSize(640, 480)
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Input Manual (Debajo de la cámara, como en tus capturas)
        self.input_manual = QLineEdit()
        self.input_manual.setObjectName("input_buscador")
        self.input_manual.setPlaceholderText(
            tr("recep.o_escriba_el_codigo_manualme", default="O escriba el código manualmente y pulse Enter...")
        )
        self.input_manual.setFixedHeight(45)
        self.input_manual.returnPressed.connect(self.procesar_entrada_manual)

        # Botón Volver/Cancelar
        self.btn_cancelar_cam = QPushButton(tr("recep.cancelar_y_volver", default="⬅ CANCELAR Y VOLVER"))
        self.btn_cancelar_cam.setObjectName("btn_peligro")
        self.btn_cancelar_cam.setFixedWidth(200)
        self.btn_cancelar_cam.clicked.connect(self.detener_camara)

        # Organizar en el layout
        layout_cam.addWidget(self.lbl_video, 0, Qt.AlignmentFlag.AlignCenter)
        layout_cam.addWidget(self.input_manual)
        layout_cam.addWidget(self.btn_cancelar_cam, 0, Qt.AlignmentFlag.AlignCenter)

    def actualizar_frame(self, image):
        """Dibuja cada frame de la cámara en el QLabel."""
        self.lbl_video.setPixmap(QPixmap.fromImage(image))

    def detener_camara(self):
        """Detiene el hilo y vuelve al panel de inicio."""
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
        self.stack.setCurrentIndex(0)


# ============================================================
# BLOQUE UTILIDADES PDF
# ============================================================

class NumberedCanvasWithLastPage(canvas.Canvas):
    """
    Añade numeración 'Página X de Y' y firmas solo en la última página.
    """

    def __init__(self, *args, on_last_page=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._on_last_page = on_last_page

    def showPage(self):
        self._saved_page_states.append(self.__dict__.copy())
        super().showPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for page_num, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self.saveState()

            # Pie de página corporativo
            self.setFont("Helvetica-Oblique", 8)
            self.setFillColor(colors.grey)
            self.drawCentredString(
                A4[0] / 2, 1.2 * cm, "SMART MANAGER - SISTEMA DE GESTIÓN LOGÍSTICA"
            )

            # Numeración
            self.setFont("Helvetica", 8)
            self.drawRightString(
                A4[0] - 1.5 * cm, 1.2 * cm, f"Página {page_num} de {total_pages}"
            )

            # Firmas en la última página
            if page_num == total_pages and callable(self._on_last_page):
                self._on_last_page(self)

            self.restoreState()
            super().showPage()
        super().save()


# ============================================================
# BLOQUE HISTORIAL DE TRASPASOS
# ============================================================

class HistorialTraspasosPage(QWidget):

    def __init__(self, usuario, codigo_local="ALMC"):
        super().__init__()
        self.codigo_local = codigo_local
        # Punto 3: Unificación de variable de usuario
        self.usuario = usuario
        self.setup_ui()
        self.cargar_datos()

    def setup_ui(self):
        """Configura la interfaz visual completa con estilo GitHub Dark."""
        self.setObjectName("panel_contenido")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # --- CABECERA ---
        header = QHBoxLayout()
        title_container = QVBoxLayout()

        title = QLabel(tr("recep.historial_de_traspasos", default="Historial de Traspasos"))
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title.setObjectName("titulo_cian")

        subtitle = QLabel(tr("recep.consulta_trazabilidad_y_gest", default="Consulta, trazabilidad y gestión de envíos realizados."))
        subtitle.setObjectName("subtitulo_muted")

        title_container.addWidget(title)
        title_container.addWidget(subtitle)

        # Punto 4: Unificado a self.btn_actualizar con estilo corporativo
        self.btn_actualizar = QPushButton(tr("recep.actualizar", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)

        header.addLayout(title_container)
        header.addStretch()
        header.addWidget(self.btn_actualizar)
        layout.addLayout(header)

        # --- BUSCADOR HÍBRIDO ---
        h_buscador_layout = QHBoxLayout()
        h_buscador_layout.setSpacing(10)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_pale_articulo", default="🔍 Filtrar por ID, Palé, Artículo, EAN, Destino o Fecha...")
        )
        self.input_busqueda.setFixedHeight(50)

        # ELIMINAR SUGERENCIAS LOGÍSTICAS (QCompleter)
        self.input_busqueda.setCompleter(None)

        self.input_busqueda.textChanged.connect(self.cargar_datos)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self.aplicar_filtro_escaneado, contexto="recepcion.historial_traspasos")

        self.btn_buscar = QPushButton("🔍")
        self.btn_buscar.setObjectName("btn_icono")
        self.btn_buscar.setFixedSize(48, 48)
        self.btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar.clicked.connect(self.cargar_datos)

        h_buscador_layout.addWidget(self.input_busqueda)
        h_buscador_layout.addWidget(self.btn_buscar)
        h_buscador_layout.addWidget(btn_escaneo_movil)
        layout.addLayout(h_buscador_layout)

        # --- TABLA (plantilla visual global reutilizable) ---
        if construir_tabla_estilizada is not None:
            wrap_tabla, self.tabla = construir_tabla_estilizada()
        else:
            wrap_tabla = QFrame()
            wrap_tabla.setObjectName("contenedor_tabla_estandar")
            wrap_layout = QVBoxLayout(wrap_tabla)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.setSpacing(0)
            self.tabla = QTableWidget()
            wrap_layout.addWidget(self.tabla)
        self.setup_tabla_estilo()
        layout.addWidget(wrap_tabla)

    def setup_tabla_estilo(self):
        columnas = ["ID TRASPASO", "FECHA ENVÍO", "DESTINO", "ESTADO", "ACCIONES"]
        self.tabla.setColumnCount(len(columnas))
        self.tabla.setHorizontalHeaderLabels(columnas)
        self.tabla.verticalHeader().setVisible(False)
        # Altura de fila suficiente para que el botón de ACCIONES (32px + glow
        # de neón) no se vea cortado; cada traspaso tiene su espacio vital.
        self.tabla.verticalHeader().setDefaultSectionSize(60)
        # Sin padding vertical en las celdas: el padding global (8px) empujaba el
        # cell widget hacia abajo y descentraba el botón. Se mantiene el padding
        # horizontal para el texto de las columnas.
        self.tabla.setStyleSheet("QTableWidget::item { padding: 0px 8px; }")
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def cargar_datos(self):
        """Consulta la DB y renderiza los traspasos del origen local con feedback visual."""

        busqueda_texto = self.input_busqueda.text().strip()
        busqueda_param = f"%{busqueda_texto}%"

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT DISTINCT h.id_documento, h.fecha_envio, h.destino, h.estado 
                        FROM documentos_logisticos h
                        LEFT JOIN documentos_logisticos_lineas d ON h.id_documento = d.id_documento
                        WHERE (h.origen = %s OR h.origen LIKE %s)
                          AND (h.id_documento LIKE %s OR h.destino LIKE %s OR h.fecha_envio LIKE %s 
                               OR d.nombre_articulo LIKE %s OR d.codigo_articulo LIKE %s OR d.id_pale LIKE %s)
                        ORDER BY h.fecha_envio DESC
                    """
                    params = (
                        self.codigo_local,
                        f"%{self.codigo_local}%",
                        *(busqueda_param,) * 6,
                    )
                    cur.execute(query, params)

                    # Convertimos a lista de diccionarios para compatibilidad total
                    columnas = [desc[0] for desc in cur.description]
                    rows = [dict(zip(columnas, row, strict=False)) for row in cur.fetchall()]

                    self.tabla.setRowCount(0)

                    for i, row in enumerate(rows):
                        self.tabla.insertRow(i)
                        id_doc = str(row["id_documento"])

                        # Celdas básicas
                        self.tabla.setItem(i, 0, QTableWidgetItem(id_doc))
                        self.tabla.setItem(
                            i, 1, QTableWidgetItem(str(row["fecha_envio"] or "-"))
                        )
                        self.tabla.setItem(
                            i, 2, QTableWidgetItem(str(row["destino"] or "N/D"))
                        )

                        # Estado con colores neón
                        texto_estado = str(row["estado"] or "DESCONOCIDO").upper()
                        item_estado = QTableWidgetItem(texto_estado)
                        item_estado.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        item_estado.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

                        # Lógica de colores unificada
                        if texto_estado in [
                            "FINALIZADO",
                            "RECIBIDO",
                            "ENTREGADO",
                            "PROCESADO",
                        ]:
                            color = "#00FFC6"  # Cian Neón
                        elif texto_estado in ["PENDIENTE", "EN TRANSITO", "EN CAMINO"]:
                            color = "#F1C40F"  # Amarillo
                        else:
                            color = "#FF4B4B"  # Rojo/Error

                        item_estado.setForeground(QColor(color))
                        self.tabla.setItem(i, 3, item_estado)

                        # Método para añadir el botón de PDF en la fila
                        if hasattr(self, "agregar_boton_pdf"):
                            self.agregar_boton_pdf(i, id_doc)

        except Exception as e:
            import logging

            logging.error(f"Error cargando historial de traspasos: {e}")

            _mensaje_ui(
                self, "Error de Carga", f"No se pudo obtener el historial:\n{e}", "warning"
            )

        finally:
            # 2. Cerrar aviso siempre
            QApplication.restoreOverrideCursor()

    def ver_pdf(self, id_documento):
        """Abre el PDF existente o inicia la regeneración si falta."""

        base_path = os.getcwd()
        ruta_carpeta = os.path.join(base_path, "documentos", "albaranes")

        # Probar variantes de nombre
        rutas = [
            os.path.join(ruta_carpeta, f"ALB_{id_documento}.pdf"),
            os.path.join(ruta_carpeta, f"{id_documento}.pdf"),
        ]

        for ruta in rutas:
            if os.path.exists(ruta):
                abrir_pdf(ruta)
                return

        # Fallback: Regenerar
        if _confirmar_ui(
            self,
            "Documento no encontrado",
            f"¿Desea regenerar el PDF de {id_documento} desde la DB?",
        ):
            self.regenerar_pdf_desde_historial(id_documento)

    def agregar_boton_pdf(self, fila, id_doc):
        btn = QPushButton(tr("recep.ver_albaran", default="📄 VER ALBARÁN"))
        btn.setObjectName("btn_secundario")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Altura 44px: el QSS añade padding 10px + borde 2px (24px de chrome
        # vertical); con 32px el texto quedaba cortado.
        btn.setFixedSize(150, 44)
        # Hover swap explícito: relleno cian + texto oscuro al pasar el cursor.
        btn.setStyleSheet(
            "QPushButton{background:#161B22;color:#E6EDF3;border:2px solid #00FFC6;"
            "border-radius:10px;font-family:'Segoe UI';font-weight:700;font-size:13px;}"
            "QPushButton:hover{background:#00FFC6;color:#0D1117;}"
            "QPushButton:pressed{background:#00E0AE;color:#0D1117;}"
        )
        btn.clicked.connect(lambda: self.ver_pdf(id_doc))

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        # El contenedor debe llenar la fila para no recortar el glow del botón
        # (si no, queda en su sizeHint ~44px y corta el botón por abajo).
        container.setMinimumHeight(60)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        # AlignHCenter|AlignVCenter centra el botón exactamente en la celda.
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabla.setCellWidget(fila, 4, container)

    def abrir_camara_filtro(self):
        """
        Lanza el escaneo remoto (móvil) para filtrar el historial.
        Implementa feedback visual en el buscador tras una lectura exitosa.
        """
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(
            self, on_result=self.aplicar_filtro_escaneado, contexto="recepcion.historial_traspasos_filtro")

    def aplicar_filtro_escaneado(self, codigo):
        """
        Slot encargado de recibir el código del escáner y actualizar la UI.
        """
        if codigo:
            codigo_limpio = str(codigo).strip()
            self.input_busqueda.setText(codigo_limpio)

            if feedback_lineedit_exito is not None:
                feedback_lineedit_exito(self.input_busqueda, 1200)

            # Ejecutamos la carga con el nuevo filtro
            self.cargar_datos()

    def regenerar_pdf_desde_historial(self, id_traspaso):
        """Inicia el PdfWorker para reconstruir el documento."""
        try:

            usuario_actual = getattr(self, "usuario", "SISTEMA")

            self.worker = PdfWorker()
            self.worker.configurar(
                pale_items=[],  # El worker buscará el detalle en DB
                origen=self.codigo_local,
                destino="",
                observaciones="",
                agencia_transporte="",
                usuario=usuario_actual,
                id_traspaso=id_traspaso,
                tipo_operacion="traspaso",
            )
            self.hilo_pdf = QThread()
            self.worker.moveToThread(self.hilo_pdf)
            self.hilo_pdf.started.connect(self.worker.run)
            self.worker.finished.connect(self.hilo_pdf.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.hilo_pdf.finished.connect(self.hilo_pdf.deleteLater)
            self.worker.finished.connect(self.on_pdf_regenerado)
            self.worker.error.connect(
                lambda e: _mensaje_ui(self, "Error", str(e), "error")
            )

            self.btn_actualizar.setText(tr("recep.generando", default="⏳ Generando..."))
            self.btn_actualizar.setEnabled(False)
            self.hilo_pdf.start()
        except Exception as e:
            _mensaje_ui(self, "Error", f"Fallo al iniciar regeneración: {e}", "error")

    def on_pdf_regenerado(self, resultado):
        """Callback tras finalizar el PdfWorker."""

        ruta_albaran, _, _ = resultado
        self.finalizar_carga()
        abrir_pdf(ruta_albaran)
        _mensaje_ui(self, "Éxito", "Documento regenerado correctamente.", "success")

    def ejecutar_actualizacion(self):
        """
        Inicia la animación de sincronización con el icono de carga y
        actualiza los datos de la base de datos.
        """
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.cargando", default="⌛ CARGANDO..."))
        QApplication.processEvents()
        QTimer.singleShot(300, self.finalizar_carga)

    def finalizar_carga(self):
        self.cargar_datos()
        self.btn_actualizar.setEnabled(True)
        self.btn_actualizar.setText(tr("recep.actualizar_2", default="🔄 ACTUALIZAR"))


# ============================================================
# BLOQUE PANTALLA DE INICIO
# ============================================================

class LandingScannerPage(QWidget):
    """Página de inicio para la sección de Scanner con estilo moderno."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Aplicamos el fondo general para asegurar consistencia
        self.setObjectName("panel_contenido")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Icono de Recepción Logística (📥) - Estilo limpio
        self.lbl_icono = QLabel("📥")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Texto Informativo - Neón Corporativo
        self.lbl_info = QLabel(tr("recep.recepcion_de_mercancia", default="RECEPCIÓN DE MERCANCÍA"))
        self.lbl_info.setObjectName("titulo_cian")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central - Estilo Global Neón
        self.btn_iniciar = QPushButton(tr("recep.abrir_escaner_de_entrada", default="📦  ESCANEAR ALBARÁN"))
        self.btn_iniciar.setObjectName("btn_primario")
        self.btn_iniciar.setFixedSize(
            320, 65
        )  # Ligeramente más grande para mejor impacto
        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addStretch()
        layout.addWidget(self.lbl_icono)
        layout.addWidget(self.lbl_info)
        layout.addSpacing(15)
        layout.addWidget(self.btn_iniciar, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()


# ============================================================
# BLOQUE REABASTECIMIENTO — constantes, helpers y clases
# ============================================================

_REAB_CIAN = "#00FFC6"
_REAB_FONDO = "#0E1117"
_REAB_PANEL_BG = "#161B22"
_REAB_GRIS_PANEL = "#1A1D23"
_REAB_BORDE = "#30363D"

_SPIN_SS = f"""
QSpinBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
    border: none;
    background: #1A2230;
}}
"""

_COMBO_SS = f"""
QComboBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QComboBox QAbstractItemView {{
    background-color: #161B22;
    color: #FFFFFF;
    selection-background-color: {_REAB_CIAN};
    selection-color: #0E1117;
    border: 1px solid {_REAB_CIAN};
}}
"""

_CFG_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 4px 8px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""

_REAB_NEON_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
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

_REAB_BTN_CIAN_SS = f"""
QPushButton {{
    background-color: #0E1117;
    color: {_REAB_CIAN};
    font-weight: bold;
    border-radius: 14px;
    padding: 12px 24px;
    font-size: 13px;
    font-family: 'Segoe UI';
    border: 2px solid {_REAB_CIAN};
    outline: none;
}}
QPushButton:hover {{
    background-color: {_REAB_CIAN};
    color: #0E1117;
    border: 2px solid {_REAB_CIAN};
}}
QPushButton:pressed {{
    background-color: #00C79A;
    color: #0E1117;
}}
QPushButton:focus {{
    outline: none;
}}
"""

_REAB_BTN_ROJO_SS = """
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

_TAB_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: {_REAB_CIAN};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 20px;
    outline: none;
}}
QPushButton:hover {{
    background-color: rgba(0,255,198,0.12);
    border: 2px solid {_REAB_CIAN};
}}
"""

_TAB_BTN_ACTIVO_SS = f"""
QPushButton {{
    background-color: {_REAB_CIAN};
    color: {_REAB_FONDO};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 20px;
    outline: none;
}}
QPushButton:hover {{
    background-color: #00E6B2;
    border: 2px solid #00E6B2;
}}
"""

_ACT_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: {_REAB_CIAN};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 22px;
    outline: none;
}}
QPushButton:hover {{
    background-color: {_REAB_CIAN};
    color: {_REAB_FONDO};
}}
QPushButton:pressed {{
    background-color: #00C79A;
    color: {_REAB_FONDO};
}}
"""

_DIA_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: #8B949E;
    border: 2px solid #8B949E;
    border-radius: 10px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 6px 0px;
    outline: none;
}}
QPushButton:hover {{
    border-color: {_REAB_CIAN};
    color: {_REAB_CIAN};
}}
QPushButton:checked {{
    background-color: {_REAB_CIAN};
    color: #0E1117;
    border: 2px solid {_REAB_CIAN};
}}
"""

_CMB_HORA_SS = f"""
QComboBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    outline: none;
}}
"""

_SAVE_BTN_SS = """
QPushButton {
    background-color: #0E1117;
    color: #1ED760;
    border: 2px solid #1ED760;
    border-radius: 10px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 26px;
    outline: none;
}
QPushButton:hover {
    background-color: #1ED760;
    color: #0E1117;
    border: 2px solid #1ED760;
}
QPushButton:pressed {
    background-color: #12A845;
    color: #0E1117;
    border: 2px solid #12A845;
}
"""

_EMAIL_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""



def _sombra_cian_reab(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(22)
    fx.setColor(QColor(_REAB_CIAN))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


def _crear_tabla_reab(parent, cols):
    cont, tabla = construir_tabla_estilizada(parent)
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
            color: {_REAB_CIAN};
            border: none;
        }}
        QHeaderView::section:hover {{
            background-color: {_REAB_CIAN};
            color: #0E1117;
        }}
        QHeaderView::section:first {{
            border-top-left-radius: 18px;
        }}
        QHeaderView::section:last {{
            border-top-right-radius: 18px;
        }}
    """)
    cont.layout().setContentsMargins(2, 2, 2, 2)
    tabla.setColumnCount(len(cols))
    tabla.setHorizontalHeaderLabels(cols)
    tabla.horizontalHeader().setStretchLastSection(True)
    tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return cont, tabla


def _reab_buscar_articulos(query: str):
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


def _reab_get_todos_articulos():
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo, nombre FROM articulos ORDER BY nombre ASC")
                return cur.fetchall()
    except Exception:
        return []


def _reab_get_articulo_stock(codigo: str):
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


def _reab_obtener_info_empresa() -> dict:
    # Fuente única de datos corporativos (FASE 2c).
    try:
        from src.db.empresa import info_documento
        info = info_documento()
        return {
            "nombre": info.get("nombre") or "SMART MANAGER",
            "codigo": info.get("centro_codigo") or "",
            "cif": info.get("cif") or "",
            "direccion": info.get("direccion_completa") or "",
        }
    except Exception:
        pass
    return {"nombre": "SMART MANAGER", "codigo": ""}


class _ReabItemDelegateReab(QStyledItemDelegate):
    """Rounded-corner item delegate for _ReabComboBoxReab popups."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_sel   = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = QRectF(option.rect).adjusted(4, 2, -4, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        if is_sel or is_hover:
            painter.fillPath(path, QColor(_REAB_CIAN))
        txt_color = QColor("#0E1117") if (is_sel or is_hover) else QColor("#FFFFFF")
        painter.setPen(txt_color)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            option.rect.adjusted(14, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data() or "",
        )
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(38)
        return sh


class _ReabComboBoxReab(QComboBox):
    """QComboBox styled for the RESPONSABLE LOGÍSTICA page."""

    _fusion_style = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_ready = False
        if _ReabComboBoxReab._fusion_style is None:
            _ReabComboBoxReab._fusion_style = QStyleFactory.create("Fusion")
        self.setStyle(_ReabComboBoxReab._fusion_style)
        self.setMaxVisibleItems(5)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(2, 2, self.width() - 4, self.height() - 4), 8, 8)
        p.setClipPath(clip)
        p.fillRect(self.width() - 30, 2, 28, self.height() - 4, QColor("#161B22"))
        p.end()

    def showPopup(self):
        if not self._popup_ready:
            self._popup_ready = True
            view = self.view()
            vp = view.viewport()
            vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            vp.setStyleSheet("background:#1A1D23;")
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.setItemDelegate(_ReabItemDelegateReab(self))
            container = view.parent()
            if isinstance(container, QWidget) and container is not self:
                container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                container.setWindowFlags(
                    container.windowFlags()
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
        super().showPopup()
        _v = self.view()
        if _v is not None:
            _p = _v.window()
            if _p is not self:
                _p.setWindowOpacity(0.0)
        QTimer.singleShot(0, self._fix_popup)

    def _fix_popup(self):
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if popup is self:
            return
        if hasattr(popup, "setFrameShape"):
            popup.setFrameShape(QFrame.Shape.NoFrame)
            popup.setLineWidth(0)
            popup.setMidLineWidth(0)
        popup.setAutoFillBackground(False)
        popup.setStyleSheet("background: transparent;")
        popup.setContentsMargins(0, 0, 0, 0)
        if popup.layout() is not None:
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)
        for _child in popup.children():
            if isinstance(_child, QWidget) and _child is not view:
                _child.setFixedSize(0, 0)
                _child.hide()
        view.setStyleSheet(
            f"QAbstractItemView{{background:#1A1D23;border:2px solid {_REAB_CIAN};"
            f"border-radius:10px;outline:none;}}"
            f"QScrollBar:vertical{{background:transparent;width:12px;margin:2px 0px;}}"
            f"QScrollBar::handle:vertical{{background:{_REAB_CIAN};min-height:24px;border-radius:6px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{"
            f"border:none;background:none;width:0px;height:0px;}}"
            f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}"
        )
        view.setAutoScroll(False)
        _item_h = view.sizeHintForRow(0) if self.count() > 0 else 38
        _max_view_h = 5 * _item_h + 4
        if view.height() > _max_view_h or self.count() > 5:
            view.setFixedHeight(_max_view_h)
            popup.resize(popup.width(), _max_view_h)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Scroll por píxel: sin hueco vacío bajo el último item.
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        sb = view.verticalScrollBar()
        if sb is not None:
            sb.show()
        global_bottom = self.mapToGlobal(QPoint(0, self.height()))
        popup.move(global_bottom.x(), global_bottom.y())
        sz = popup.size()
        if sz.width() > 0 and sz.height() > 0:
            _ = popup.winId()
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, sz.width(), sz.height()), 10, 10)
            popup.setMask(QRegion(path.toFillPolygon().toPolygon()))
        popup.setWindowOpacity(1.0)


class _ReabastecimientoPage(QWidget):
    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self._engine = engine
        try:
            # Solo refresco EN VIVO del stock de la tabla monitorizada (sin propuestas ni webhook: el
            # reabastecimiento es informativo por Correo y el stock se ajusta al recepcionar palés).
            from src.db.conexion import stock_signals as _db_signals
            _db_signals.stock_actualizado.connect(self._on_stock_cambio)
            _db_signals.propuestas_actualizadas.connect(self._cargar_config)
        except Exception:
            pass
        self._build_ui()
        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(60_000)
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start()

    def _act_btn_loading(self, label, fn):
        btn = QPushButton(label)
        btn.setStyleSheet(_ACT_BTN_SS)
        btn.setFixedHeight(44)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(lambda: self._with_loading(btn, fn))
        return btn

    def _with_loading(self, btn: QPushButton, fn):
        if not btn.isEnabled():
            return
        from PyQt6.QtWidgets import QApplication
        original = btn.text()
        btn.setText(tr("recep.cargando_2", default="⟳  Cargando..."))
        btn.setEnabled(False)
        QApplication.processEvents()
        try:
            fn()
        finally:
            btn.setText(original)
            btn.setEnabled(True)

    def _ir_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setStyleSheet(_TAB_BTN_ACTIVO_SS if i == idx else _TAB_BTN_SS)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(14)

        lbl = QLabel(tr("recep.reabastecimiento", default="Reabastecimiento"))
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_REAB_CIAN};")
        root.addWidget(lbl)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)
        nav_row.setContentsMargins(0, 0, 0, 0)

        tab_labels = [
            "ARTÍCULOS MONITORIZADOS",
            "RESPONSABLES LOGÍSTICA",
        ]
        self._tab_btns = []
        for i, label in enumerate(tab_labels):
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, idx=i: self._ir_tab(idx))
            nav_row.addWidget(btn)
            self._tab_btns.append(btn)

        root.addLayout(nav_row)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {_REAB_FONDO};")

        # Page 0: ARTÍCULOS MONITORIZADOS
        page0 = QWidget()
        page0.setStyleSheet(f"background: {_REAB_FONDO};")
        p0_ly = QVBoxLayout(page0)
        p0_ly.setContentsMargins(0, 8, 0, 0)
        p0_ly.setSpacing(8)

        p0_hdr = QHBoxLayout()
        btn_guardar_cfg = QPushButton(tr("recep.guardar_2", default="Guardar"))
        btn_guardar_cfg.setStyleSheet(_SAVE_BTN_SS)
        btn_guardar_cfg.setFixedHeight(46)
        btn_guardar_cfg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_guardar_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar_cfg.clicked.connect(self._guardar_config)
        p0_hdr.addWidget(btn_guardar_cfg)
        p0_hdr.addStretch()
        p0_hdr.addWidget(self._act_btn_loading("🔄  ACTUALIZAR", self._cargar_config))
        p0_ly.addLayout(p0_hdr)

        cols_cfg = ["EAN", "ARTÍCULO", "STOCK TIENDA", "STOCK CENTRAL", "UMBRAL MÍN", "STOCK OBJETIVO"]
        self._cont_cfg, self._tbl_cfg = _crear_tabla_reab(self, cols_cfg)
        hh = self._tbl_cfg.horizontalHeader()
        hh.setStretchLastSection(False)
        for i in range(len(cols_cfg)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self._tbl_cfg.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_cfg.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl_cfg.verticalHeader().setVisible(False)
        p0_ly.addWidget(self._cont_cfg)
        self._stack.addWidget(page0)

        # Page 1: RESPONSABLES LOGÍSTICA (selección de perfiles → Correo interno)
        page3 = QWidget()
        page3.setStyleSheet(f"background: {_REAB_FONDO};")
        p3_ly = QVBoxLayout(page3)
        p3_ly.setContentsMargins(32, 20, 32, 20)
        p3_ly.setSpacing(0)

        lbl_sec1 = QLabel("Responsables de logística (perfiles de Smart Manager)")
        lbl_sec1.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec1.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 4px;")
        p3_ly.addWidget(lbl_sec1)

        lbl_sec1_desc = QLabel(
            "Selecciona hasta 6 perfiles. Recibiran la solicitud de reabastecimiento en su MODULO DE "
            "CORREO (bandeja interna), solo cuando haya articulos por debajo del umbral minimo. Es "
            "informativa: no modifica el stock (se ajusta al recepcionar los pales)."
        )
        lbl_sec1_desc.setWordWrap(True)
        lbl_sec1_desc.setStyleSheet("color: #8B949E; font-size: 11px; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec1_desc)

        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        self._lst_perfiles = QListWidget()
        self._lst_perfiles.setFixedHeight(210)
        self._lst_perfiles.setStyleSheet(
            f"QListWidget {{ background: #0E1117; color: #E6EDF3; border: 2px solid {_REAB_CIAN};"
            f" border-radius: 10px; padding: 6px; font-size: 13px; outline: none; }}"
            f"QListWidget::item {{ padding: 7px 8px; }}"
            f"QListWidget::item:selected {{ background: #1A2230; color: {_REAB_CIAN}; }}"
        )
        try:
            from src.db.usuario import listar_usuarios_empresa as _lu_reab
            for _u in (_lu_reab() or []):
                _id = _u.get("id")
                _nom = _u.get("nombre") or _u.get("usuario") or str(_id)
                _rol = _u.get("perfil") or _u.get("rol") or ""
                _it = QListWidgetItem(f"{_nom}" + (f"   -   {_rol}" if _rol else ""))
                _it.setData(Qt.ItemDataRole.UserRole, str(_id))
                _it.setFlags(_it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                _it.setCheckState(Qt.CheckState.Unchecked)
                self._lst_perfiles.addItem(_it)
        except Exception:
            pass
        self._lst_perfiles.itemChanged.connect(self._limitar_perfiles)
        p3_ly.addWidget(self._lst_perfiles)

        p3_ly.addSpacing(16)

        lbl_sec2 = QLabel(tr("recep.dias_de_envio_puede_seleccio", default="Días de envío (puede seleccionar varios)"))
        lbl_sec2.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec2.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec2)

        dias_row = QHBoxLayout()
        dias_row.setSpacing(10)
        dias_row.setContentsMargins(0, 0, 0, 0)
        dias_nombres = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
        self._dia_btns = []
        for nombre in dias_nombres:
            btn = QPushButton(nombre)
            btn.setCheckable(True)
            btn.setFixedSize(66, 46)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(_DIA_BTN_SS)
            dias_row.addWidget(btn)
            self._dia_btns.append(btn)
        dias_row.addStretch()
        p3_ly.addLayout(dias_row)

        p3_ly.addSpacing(24)

        lbl_sec3 = QLabel(tr("recep.hora_de_envio", default="Hora de envío"))
        lbl_sec3.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec3.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec3)

        hora_row = QHBoxLayout()
        hora_row.setSpacing(8)
        hora_row.setContentsMargins(0, 0, 0, 0)

        self._cmb_hora = _ReabComboBoxReab()
        for h in range(24):
            self._cmb_hora.addItem(f"{h:02d}h")
        self._cmb_hora.setFixedWidth(100)
        self._cmb_hora.setFixedHeight(46)
        self._cmb_hora.setStyleSheet(_CMB_HORA_SS)
        hora_row.addWidget(self._cmb_hora)

        lbl_sep_hora = QLabel(":")
        lbl_sep_hora.setStyleSheet(f"color: {_REAB_CIAN}; font-size: 22px; font-weight: bold;")
        lbl_sep_hora.setFixedWidth(18)
        hora_row.addWidget(lbl_sep_hora)

        self._cmb_min = _ReabComboBoxReab()
        for m in range(0, 60, 5):
            self._cmb_min.addItem(f"{m:02d}min")
        self._cmb_min.setFixedWidth(110)
        self._cmb_min.setFixedHeight(46)
        self._cmb_min.setStyleSheet(_CMB_HORA_SS)
        hora_row.addWidget(self._cmb_min)
        hora_row.addStretch()
        p3_ly.addLayout(hora_row)

        p3_ly.addStretch()

        self._lbl_save_ok = QLabel("")
        self._lbl_save_ok.setStyleSheet(
            "color: #1ED760; font-size: 13px; font-weight: bold; background: transparent;"
        )
        self._lbl_save_ok.setVisible(False)

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._lbl_save_ok)
        save_row.addSpacing(20)
        btn_test = QPushButton(tr("recep.enviar_ahora", default="📨  ENVIAR AHORA"))
        btn_test.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_REAB_CIAN}; border: 2px solid {_REAB_CIAN};"
            f" border-radius: 10px; font-size: 13px; font-weight: bold; padding: 0 18px; outline: none; }}"
            f"QPushButton:hover {{ background: {_REAB_CIAN}; color: #0E1117; }}"
        )
        btn_test.setFixedHeight(46)
        btn_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_test.clicked.connect(self._probar_envio)
        save_row.addWidget(btn_test)
        save_row.addSpacing(12)
        btn_save = QPushButton(tr("recep.guardar_3", default="Guardar"))
        btn_save.setStyleSheet(_SAVE_BTN_SS)
        btn_save.setFixedHeight(46)
        btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save.clicked.connect(self._guardar_schedule_ui)
        save_row.addWidget(btn_save)
        p3_ly.addLayout(save_row)

        self._stack.addWidget(page3)

        root.addWidget(self._stack)
        self._ir_tab(0)
        self.cargar()

    def cargar(self):
        self._cargar_config()
        self._cargar_schedule_ui()

    def _cargar_config(self):
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT a.codigo, a.nombre,
                               COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0),
                               COALESCE(a.Stock_central, 0),
                               rc.umbral_min, rc.stock_objetivo
                        FROM articulos a
                        LEFT JOIN reab_config rc ON rc.codigo = a.codigo
                        ORDER BY a.nombre ASC
                    """)
                    rows = cur.fetchall()
        except Exception:
            rows = []

        self._tbl_cfg.setRowCount(len(rows))
        for r, row in enumerate(rows):
            codigo = row[0]
            nombre = row[1]
            st_tienda = row[2]
            st_central = row[3]
            tiene_cfg = row[4] is not None
            umbral = int(row[4]) if tiene_cfg else 5
            objetivo = int(row[5]) if tiene_cfg else 20

            self._tbl_cfg.setRowHeight(r, 48)

            ean_item = QTableWidgetItem(codigo)
            ean_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ean_item.setFlags(ean_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not tiene_cfg:
                ean_item.setForeground(QColor("#8B949E"))
            self._tbl_cfg.setItem(r, 0, ean_item)

            art_item = QTableWidgetItem(nombre)
            art_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            art_item.setFlags(art_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not tiene_cfg:
                art_item.setForeground(QColor("#8B949E"))
            self._tbl_cfg.setItem(r, 1, art_item)

            for ci, val in enumerate([st_tienda, st_central], start=2):
                it = QTableWidgetItem(str(val))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._tbl_cfg.setItem(r, ci, it)

            inp_u = QLineEdit(str(umbral))
            inp_u.setStyleSheet(_CFG_INPUT_SS)
            inp_u.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp_u.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            w_u = QWidget()
            w_u.setStyleSheet("background: transparent;")
            ly_u = QHBoxLayout(w_u)
            ly_u.setContentsMargins(4, 2, 4, 2)
            ly_u.addWidget(inp_u)
            self._tbl_cfg.setCellWidget(r, 4, w_u)

            inp_o = QLineEdit(str(objetivo))
            inp_o.setStyleSheet(_CFG_INPUT_SS)
            inp_o.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp_o.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            w_o = QWidget()
            w_o.setStyleSheet("background: transparent;")
            ly_o = QHBoxLayout(w_o)
            ly_o.setContentsMargins(4, 2, 4, 2)
            ly_o.addWidget(inp_o)
            self._tbl_cfg.setCellWidget(r, 5, w_o)

            inp_u.editingFinished.connect(
                lambda c=codigo, iu=inp_u, io=inp_o: self._auto_guardar_cfg(c, iu, io)
            )
            inp_o.editingFinished.connect(
                lambda c=codigo, iu=inp_u, io=inp_o: self._auto_guardar_cfg(c, iu, io)
            )

    def _guardar_config(self):
        """Guarda umbral mínimo + stock objetivo de los artículos monitorizados (sin crear propuestas)."""
        for r in range(self._tbl_cfg.rowCount()):
            ean_item = self._tbl_cfg.item(r, 0)
            if not ean_item:
                continue
            codigo = ean_item.text().strip()
            if not codigo:
                continue
            w_u = self._tbl_cfg.cellWidget(r, 4)
            w_o = self._tbl_cfg.cellWidget(r, 5)
            if w_u is None or w_o is None:
                continue
            inp_u = w_u.layout().itemAt(0).widget()
            inp_o = w_o.layout().itemAt(0).widget()
            try:
                umbral = max(0, int(inp_u.text().strip() or "0"))
                objetivo = max(0, int(inp_o.text().strip() or "0"))
            except ValueError:
                continue
            _reab_upsert_config(codigo, umbral, objetivo)
            inp_u.deselect()
            inp_o.deselect()
        self._tbl_cfg.clearSelection()
        self._tbl_cfg.setFocus()

    def _on_stock_cambio(self, codigo: str):
        # Solo refresca el stock en vivo de la tabla monitorizada (informativo; no crea propuestas
        # ni toca stock: el reabastecimiento se comunica por Correo y el stock se ajusta al recepcionar).
        self._actualizar_stock_en_cfg(codigo)

    def _eliminar_config(self, codigo: str):
        _reab_eliminar_config(codigo)
        self._cargar_config()

    def _perfiles_seleccionados(self):
        """IDs de los perfiles marcados en la lista de responsables."""
        ids = []
        if hasattr(self, "_lst_perfiles"):
            for i in range(self._lst_perfiles.count()):
                it = self._lst_perfiles.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    ids.append(it.data(Qt.ItemDataRole.UserRole))
        return ids

    def _limitar_perfiles(self, item):
        """Máximo 6 perfiles: si se marca uno de más, se revierte."""
        if item.checkState() != Qt.CheckState.Checked:
            return
        if len(self._perfiles_seleccionados()) > 6:
            self._lst_perfiles.blockSignals(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._lst_perfiles.blockSignals(False)
            self._lbl_save_ok.setText("⚠ Máximo 6 perfiles responsables")
            self._lbl_save_ok.setStyleSheet(
                "color: #E3B341; font-size: 12px; font-weight: bold; background: transparent;")
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(3000, self._hide_save_ok)

    def _cargar_schedule_ui(self):
        cfg = _reab_cargar_schedule()
        perfiles = set(str(p) for p in cfg.get("perfiles", []))
        if hasattr(self, "_lst_perfiles"):
            self._lst_perfiles.blockSignals(True)
            for i in range(self._lst_perfiles.count()):
                it = self._lst_perfiles.item(i)
                pid = str(it.data(Qt.ItemDataRole.UserRole))
                it.setCheckState(Qt.CheckState.Checked if pid in perfiles else Qt.CheckState.Unchecked)
            self._lst_perfiles.blockSignals(False)
        dias_activos = set(cfg.get("dias", "").split(",")) if cfg.get("dias") else set()
        for i, btn in enumerate(self._dia_btns):
            btn.setChecked(str(i) in dias_activos)
        hora = cfg.get("hora", 8)
        minuto = cfg.get("minuto", 0)
        self._cmb_hora.setCurrentIndex(max(0, min(hora, 23)))
        closest = min(range(0, 60, 5), key=lambda m: abs(m - minuto))
        self._cmb_min.setCurrentIndex(closest // 5)

    def _guardar_schedule_ui(self):
        perfiles = self._perfiles_seleccionados()
        dias_str = ",".join(str(i) for i, btn in enumerate(self._dia_btns) if btn.isChecked())
        hora = int(self._cmb_hora.currentText().replace("h", "").strip())
        minuto = int(self._cmb_min.currentText().replace("min", "").strip())
        if _reab_guardar_schedule(dias_str, hora, minuto, perfiles):
            self._lbl_save_ok.setText("✓ Configuración guardada correctamente")
            self._lbl_save_ok.setStyleSheet(
                "color: #1ED760; font-size: 13px; font-weight: bold; background: transparent;")
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(3000, self._hide_save_ok)
        else:
            self._lbl_save_ok.setText("✕ Error al guardar la configuración")
            self._lbl_save_ok.setStyleSheet(
                "color: #FF4B4B; font-size: 13px; font-weight: bold; background: transparent;")
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(4000, self._hide_save_ok)

    def _probar_envio(self):
        """ENVIAR AHORA: entrega la solicitud (artículos bajo umbral) al Correo de los perfiles marcados."""
        perfiles = self._perfiles_seleccionados()
        if not perfiles:
            self._lbl_save_ok.setText("✕ Selecciona al menos un perfil responsable")
            self._lbl_save_ok.setStyleSheet(
                "color: #FF4B4B; font-size: 12px; font-weight: bold; background: transparent;")
            self._lbl_save_ok.setVisible(True); QTimer.singleShot(4000, self._hide_save_ok); return
        try:
            from src.db.reabastecimiento import enviar_reabastecimiento_a_perfiles as _envp
            res = _envp(perfiles)
        except Exception:
            res = {"enviados": 0, "articulos": 0, "sin_articulos": True}
        if res.get("sin_articulos"):
            self._lbl_save_ok.setText("⚠ No hay artículos por debajo del umbral ahora mismo")
            self._lbl_save_ok.setStyleSheet(
                "color: #E3B341; font-size: 12px; font-weight: bold; background: transparent;")
        elif res.get("enviados"):
            self._lbl_save_ok.setText(f"✓ Solicitud enviada al Correo de {res['enviados']} perfil(es) "
                                      f"({res['articulos']} artículo/s)")
            self._lbl_save_ok.setStyleSheet(
                "color: #1ED760; font-size: 12px; font-weight: bold; background: transparent;")
        else:
            self._lbl_save_ok.setText("✕ No se pudo entregar (los perfiles no tienen buzón de Correo)")
            self._lbl_save_ok.setStyleSheet(
                "color: #FF4B4B; font-size: 11px; font-weight: bold; background: transparent;")
        self._lbl_save_ok.setVisible(True); QTimer.singleShot(6000, self._hide_save_ok)

    def _hide_save_ok(self):
        try:
            self._lbl_save_ok.setVisible(False)
        except RuntimeError:
            pass

    def _check_schedule(self):
        """En el día/hora programados, entrega UNA solicitud (artículos bajo umbral) al Correo interno de
        los perfiles responsables. Informativo; no modifica stock. Una vez al día (ultima_envio)."""
        from datetime import date as _date
        cfg = _reab_cargar_schedule()
        perfiles = cfg.get("perfiles", [])
        if not perfiles or not cfg.get("dias"):
            return
        now = datetime.now()
        dias = [int(d) for d in cfg["dias"].split(",") if d.strip().isdigit()]
        if now.weekday() not in dias:
            return
        target_mins = cfg["hora"] * 60 + cfg["minuto"]
        current_mins = now.hour * 60 + now.minute
        if abs(current_mins - target_mins) > 1:
            return
        if cfg.get("ultima_envio") == _date.today():
            return
        try:
            from src.db.reabastecimiento import enviar_reabastecimiento_a_perfiles as _envp
            res = _envp(perfiles)
            if res.get("enviados"):
                _reab_marcar_envio_hoy()
        except Exception as e:
            logger.debug("check_schedule reab: %s", e)


# ============================================================
# CONSTANTES ENTERPRISE — ESTADOS LOGÍSTICOS
# ============================================================

_ESTADO_COLORES_LOG = {
    "PENDIENTE":          "#F59E0B",
    "EN PREPARACIÓN":     "#3B82F6",
    "EN PREPARACION":     "#3B82F6",
    "PREPARADO":          "#00FFC6",
    "EXPEDIDO":           "#8B5CF6",
    "EN TRÁNSITO":        "#60A5FA",
    "EN TRANSITO":        "#60A5FA",
    "RECEPCIÓN PARCIAL":  "#F97316",
    "RECEPCION PARCIAL":  "#F97316",
    "RECIBIDO":           "#22C55E",
    "INCIDENCIA":         "#EF4444",
    "CANCELADO":          "#6B7280",
    "ABIERTA":            "#EF4444",
    "CERRADA":            "#22C55E",
}


def _color_estado_log(estado: str) -> str:
    return _ESTADO_COLORES_LOG.get((estado or "").upper().strip(), "#6B7280")


def _tabla_item_centrado(texto):
    it = QTableWidgetItem(str(texto) if texto is not None else "—")
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


class _PickingDialog(QDialog):
    """Aviso de picking de un documento EN PREPARACION — SOLO informativo. El picking en sí (marcar
    líneas recogidas, confirmar y expedir) es trabajo físico de caminar el almacén con el artículo en
    la mano: se hace desde la app móvil (Logística → Preparación), nunca desde el PC — mismo criterio
    que Recepción (rediseño móvil Grupo A, a petición explícita del usuario: escritorio redirige, no
    duplica la interacción). Este diálogo solo muestra el progreso (de solo lectura, útil para un
    supervisor) y el aviso de dónde completarlo."""

    def __init__(self, id_documento, usuario=None, parent=None):
        super().__init__(parent)
        self.id_documento = id_documento
        self.setWindowTitle(tr("recep.picking_titulo", default="Picking del traspaso"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(480)
        self._drag_pos = None
        self._build_ui()
        self._cargar()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(14)

        lbl = QLabel(tr("recep.picking_de", default="PICKING — {doc}", doc=self.id_documento))
        lbl.setObjectName("titulo_cian")
        ly.addWidget(lbl)

        self._lbl_progreso = QLabel("")
        self._lbl_progreso.setObjectName("subtitulo_muted")
        ly.addWidget(self._lbl_progreso)

        aviso = QLabel(tr(
            "recep.picking_ve_al_movil",
            default="Este paso se realiza desde la app móvil: abre Logística → Preparación en tu "
                    "dispositivo para marcar las líneas recogidas y expedir el traspaso."))
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color:{_REAB_CIAN};font-size:13px;font-weight:bold;border:none;")
        ly.addWidget(aviso)

        btn_cerrar = QPushButton(tr("recep.cerrar", default="CERRAR"))
        btn_cerrar.setObjectName("btn_primario")
        btn_cerrar.setFixedHeight(45)
        btn_cerrar.clicked.connect(self.reject)
        ly.addWidget(btn_cerrar)

    def _cargar(self):
        from src.db.logistica import obtener_documento_logistico_completo
        _maestro, lineas = obtener_documento_logistico_completo(self.id_documento)
        total = len(lineas or [])
        hechas = sum(1 for lin in (lineas or []) if lin.get("picking_completo"))
        self._lbl_progreso.setText(
            tr("recep.picking_progreso", default="{h} de {t} líneas recogidas", h=hechas, t=total))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# PÁGINA PREPARACIÓN
# ============================================================

class PreparacionPage(QWidget):
    """Documentos logísticos en estado EN PREPARACIÓN (picking pendiente, aún no expedidos)."""

    _ESTADO = "EN PREPARACION"

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.preparacion_de_envios", default="Preparación de Envíos"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.documentos_en_preparacion_ac", default="Documentos en preparación activa y listos para expedir"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_actualizar = QPushButton(tr("recep.actualizar_3", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_origen_destin", default="🔍 Filtrar por ID, Origen, Destino o Estado...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC. `setText()` ya
        # dispara `_filtrar` sola (vía `textChanged`), no hace falta llamarla aparte.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self.input_busqueda.setText, contexto="recepcion.preparacion")

        self.btn_buscar = QPushButton("🔍")
        self.btn_buscar.setObjectName("btn_icono")
        self.btn_buscar.setFixedSize(48, 48)
        self.btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar.clicked.connect(self._filtrar)

        h_buscador = QHBoxLayout()
        h_buscador.addWidget(self.input_busqueda)
        h_buscador.addWidget(self.btn_buscar)
        h_buscador.addWidget(btn_escaneo_movil)
        ly.addLayout(h_buscador)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = ["ID", "TIPO", "ORIGEN", "DESTINO", "ESTADO", "EMISOR", "FECHA CREACIÓN"]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._abrir_picking)
        lbl_hint = QLabel(tr("recep.doble_clic_picking", default="Doble clic sobre un documento para gestionar su picking."))
        lbl_hint.setObjectName("subtitulo_muted")
        ly.addWidget(self._cont)
        ly.addWidget(lbl_hint)

    def cargar_datos(self):
        from src.db.logistica import obtener_historial_traspasos
        self._datos = obtener_historial_traspasos(estado_filtro=self._ESTADO)
        self._filtrar()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_4", default="🔄 ACTUALIZAR"))

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            self.tabla.setItem(i, 0, _tabla_item_centrado(d["id_documento"]))
            self.tabla.setItem(i, 1, _tabla_item_centrado(d["tipo"]))
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["origen"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["destino"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 4, ei)
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["emisor"]))
            fc = d["fecha_creacion"]
            self.tabla.setItem(i, 6, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()

    def _abrir_picking(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self._datos):
            return
        id_documento = self._datos[fila]["id_documento"]
        dlg = _PickingDialog(id_documento, usuario=self.usuario, parent=self)
        dlg.exec()
        self.cargar_datos()


# ============================================================
# PÁGINA EXPEDICIONES
# ============================================================

class ExpedicionesPage(QWidget):
    """Documentos logísticos ya expedidos (picking confirmado), en tránsito o parcialmente recibidos."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.expediciones_y_transito", default="Expediciones y Tránsito"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.seguimiento_de_envios_expedi", default="Seguimiento de envíos expedidos y en tránsito hacia destino"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_actualizar = QPushButton(tr("recep.actualizar_5", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_origen_destin_2", default="🔍 Filtrar por ID, Origen, Destino o Estado...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self.input_busqueda.setText, contexto="recepcion.expediciones")

        self.btn_buscar = QPushButton("🔍")
        self.btn_buscar.setObjectName("btn_icono")
        self.btn_buscar.setFixedSize(48, 48)
        self.btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar.clicked.connect(self._filtrar)

        h_buscador = QHBoxLayout()
        h_buscador.addWidget(self.input_busqueda)
        h_buscador.addWidget(self.btn_buscar)
        h_buscador.addWidget(btn_escaneo_movil)
        ly.addLayout(h_buscador)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = ["ID", "TIPO", "ORIGEN", "DESTINO", "ESTADO", "EMISOR", "FECHA CREACIÓN"]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self._cont)

    def cargar_datos(self):
        from src.db.logistica import obtener_historial_traspasos
        self._datos = obtener_historial_traspasos(estado_filtro="ABIERTOS")
        self._filtrar()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando_2", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_6", default="🔄 ACTUALIZAR"))

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            self.tabla.setItem(i, 0, _tabla_item_centrado(d["id_documento"]))
            self.tabla.setItem(i, 1, _tabla_item_centrado(d["tipo"]))
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["origen"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["destino"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 4, ei)
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["emisor"]))
            fc = d["fecha_creacion"]
            self.tabla.setItem(i, 6, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()


# ============================================================
# PÁGINA INCIDENCIAS
# ============================================================

_TIPOS_INCIDENCIA = [
    "ROTURA", "FALTANTE", "EXCESO", "MERCANCÍA INCORRECTA",
    "PALÉ DAÑADO", "CAJA DAÑADA", "HUMEDAD", "ERROR ETIQUETADO",
]


class _NuevaIncidenciaDialog(QDialog):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        if isinstance(usuario, dict):
            self._usuario_str = usuario.get("nombre", "Usuario")
        else:
            self._usuario_str = str(usuario or "Usuario")
        self.setWindowTitle(tr("recep.registrar_incidencia_logisti", default="Registrar Incidencia Logística"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_incidencia")
        self.setMinimumWidth(500)
        self._drag_pos = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        # objectName propio (NO "cuerpo_ventana", compartido con diálogos de escáner/cámara vía QSS
        # global en `assets/estilo_global.py`, cuyo fondo es COLOR_NEGRO_PANEL "#05070A" — mucho más
        # oscuro que el tono estándar de diálogo de la app, COLOR_FONDO_APP "#0E1117", usado por
        # `selector_tienda.py`/`fichajes_gui.py`/`horarios_gui.py`). Se fija aquí en línea para no
        # tocar esa regla global compartida.
        frame.setObjectName("cuerpo_incidencia")
        frame.setStyleSheet(
            f"QFrame#cuerpo_incidencia{{background-color:{COLOR_FONDO_APP};"
            f"border:2px solid {COLOR_CIAN};border-radius:20px;}}")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(30, 25, 30, 25)
        ly.setSpacing(16)

        cab = QHBoxLayout()
        lbl = QLabel(tr("recep.nueva_incidencia_logistica", default="NUEVA INCIDENCIA LOGÍSTICA"))
        lbl.setObjectName("titulo_cian")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cab.addWidget(lbl, 1)
        btn_x = QPushButton("✕")
        btn_x.setObjectName("btn_icono_peligro")
        btn_x.setFixedSize(40, 40)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setProperty("sin_glow", True)
        if _blindar_tamano_fijo is not None:
            _blindar_tamano_fijo(btn_x, 40, 40)
        btn_x.clicked.connect(self.reject)
        cab.addWidget(btn_x)
        ly.addLayout(cab)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.inp_doc = QLineEdit()
        self.inp_doc.setObjectName("input_buscador")
        self.inp_doc.setPlaceholderText(tr("recep.ej_doc_2024_001", default="ej. DOC-2024-001"))
        form.addRow("ID Documento *:", self.inp_doc)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(_TIPOS_INCIDENCIA)
        form.addRow("Tipo *:", self.cmb_tipo)

        self.inp_pale = QLineEdit()
        self.inp_pale.setObjectName("input_buscador")
        self.inp_pale.setPlaceholderText(tr("recep.opcional", default="Opcional"))
        form.addRow("ID Palé:", self.inp_pale)

        self.inp_codigo = QLineEdit()
        self.inp_codigo.setObjectName("input_buscador")
        self.inp_codigo.setPlaceholderText(tr("recep.opcional_2", default="Opcional"))
        instalar_sugerencias_articulo(self.inp_codigo)
        form.addRow("Código Artículo:", self.inp_codigo)

        self.spin_cant = QSpinBox()
        self.spin_cant.setRange(0, 9999)
        form.addRow("Cantidad Afectada:", self.spin_cant)

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(tr("recep.descripcion_detallada_de_la_", default="Descripción detallada de la incidencia..."))
        self.txt_desc.setFixedHeight(90)
        form.addRow("Descripción:", self.txt_desc)

        ly.addLayout(form)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btn_ok = QPushButton(tr("recep.registrar", default="✅  REGISTRAR"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(45)
        btn_ok.clicked.connect(self._registrar)
        btns.addWidget(btn_ok)
        ly.addLayout(btns)

    def _registrar(self):
        id_doc = self.inp_doc.text().strip()
        tipo = self.cmb_tipo.currentText()
        desc = self.txt_desc.toPlainText().strip()
        if not id_doc:
            _mensaje_ui(
                self, "Campo obligatorio",
                "Debes indicar el ID del documento.", "warning"
            )
            return
        codigo_art = self.inp_codigo.text().strip()
        if "–" in codigo_art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            codigo_art = codigo_art.split("–")[0].strip()
        from src.db.logistica import registrar_incidencia
        iid = registrar_incidencia(
            id_documento=id_doc,
            tipo=tipo,
            descripcion=desc,
            usuario=self._usuario_str,
            id_pale=self.inp_pale.text().strip() or None,
            codigo=codigo_art or None,
            cantidad=self.spin_cant.value(),
        )
        if iid:
            self.accept()
        else:
            _mensaje_ui(self, "Error", "No se pudo registrar la incidencia.", "error")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _IncidenciasTablaPage(QWidget):
    """Tabla + filtros de incidencias logísticas — parametrizada por la función de listado
    (`listar_incidencias_recepcion`/`listar_incidencias_traspaso` de `db/logistica.py`). Sub-página
    interna de `IncidenciasPage`: sin cabecera propia (título/NUEVA INCIDENCIA/ACTUALIZAR viven en
    el contenedor, igual patrón que `HistorialUnificadoPage` con
    `HistorialRecepcionesPage`/`HistorialTraspasosPage`)."""

    def __init__(self, listar_fn, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self._listar_fn = listar_fn
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(16)

        fil = QHBoxLayout()
        fil.setSpacing(12)
        lbl_f = QLabel(tr("recep.estado", default="Estado:"))
        lbl_f.setObjectName("label_campo")
        self.cmb_estado = QComboBox()
        self.cmb_estado.addItems(["TODAS", "ABIERTA", "CERRADA"])
        self.cmb_estado.setFixedWidth(160)
        self.cmb_estado.currentTextChanged.connect(self.cargar_datos)
        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_documento_tip", default="🔍 Filtrar por ID, Documento, Tipo o Usuario...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self.input_busqueda.setText, contexto="recepcion.incidencias")

        self.btn_buscar = QPushButton("🔍")
        self.btn_buscar.setObjectName("btn_icono")
        self.btn_buscar.setFixedSize(48, 48)
        self.btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar.clicked.connect(self._filtrar)

        fil.addWidget(lbl_f)
        fil.addWidget(self.cmb_estado)
        fil.addWidget(self.input_busqueda)
        fil.addWidget(self.btn_buscar)
        fil.addWidget(btn_escaneo_movil)
        ly.addLayout(fil)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = [
            "ID", "TIPO", "DESCRIPCIÓN",
            "PALÉ", "ARTÍCULO", "CANT.", "USUARIO", "ESTADO", "FECHA",
        ]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._accion_cerrar)
        ly.addWidget(self._cont)

        hint = QLabel(tr("recep.doble_clic_sobre_una_inciden", default="Doble clic sobre una incidencia ABIERTA para cerrarla."))
        hint.setObjectName("subtitulo_muted")
        ly.addWidget(hint)

    def cargar_datos(self):
        filtro = (
            self.cmb_estado.currentText()
            if hasattr(self, "cmb_estado") else "TODAS"
        )
        self._datos = self._listar_fn(self.codigo_local, None if filtro == "TODAS" else filtro)
        self._filtrar()

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            # Col 0: ID DOC. — shows document reference, UserRole holds incidence id for close action
            item_id = _tabla_item_centrado(str(d["id_documento"] or "—"))
            item_id.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.tabla.setItem(i, 0, item_id)
            it_tipo = _tabla_item_centrado(d["tipo"])
            it_tipo.setForeground(QColor("#F97316"))
            it_tipo.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 1, it_tipo)
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["descripcion"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["id_pale"]))
            self.tabla.setItem(i, 4, _tabla_item_centrado(d["codigo"]))
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["cantidad"]))
            self.tabla.setItem(i, 6, _tabla_item_centrado(d["usuario"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 7, ei)
            fc = d["fecha_creacion"]
            self.tabla.setItem(i, 8, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()

    def _accion_cerrar(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            return
        estado_item = self.tabla.item(fila, 7)  # ESTADO is now col 7
        if not estado_item or estado_item.text() != "ABIERTA":
            return
        id_item = self.tabla.item(fila, 0)
        if not id_item:
            return
        try:
            inc_id = id_item.data(Qt.ItemDataRole.UserRole)  # incidence id stored in UserRole
            if inc_id is None:
                return
            inc_id = int(inc_id)
        except (ValueError, TypeError):
            return
        if not _confirmar_ui(
            self, "Cerrar incidencia",
            f"¿Confirmas el cierre de la incidencia #{inc_id}?"
        ):
            return
        from src.db.logistica import cerrar_incidencia
        if cerrar_incidencia(inc_id):
            self.cargar_datos()
        else:
            _mensaje_ui(self, "Error", "No se pudo cerrar la incidencia.", "error")


class IncidenciasPage(QWidget):
    """Gestión de incidencias logísticas — contenedor con selector pill Recepción/Traspaso (mismo
    patrón visual y de slide que `HistorialUnificadoPage`). Las incidencias nunca se mezclan entre
    ambos lados: cada sub-página usa el mismo criterio origen/destino=codigo_local que ya separa
    `HistorialTraspasosPage` (origen) de `HistorialRecepcionesPage` (destino)."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._setup_ui()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.incidencias_logisticas", default="Incidencias Logísticas"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.registro_y_seguimiento_de_in", default="Registro y seguimiento de incidencias durante el proceso logístico"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        btn_nueva = QPushButton(tr("recep.nueva_incidencia", default="⚠️  NUEVA INCIDENCIA"))
        btn_nueva.setObjectName("btn_primario")
        btn_nueva.setFixedHeight(45)
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.clicked.connect(self._abrir_nueva)
        hdr.addWidget(btn_nueva)
        hdr.addSpacing(8)
        self.btn_actualizar = QPushButton(tr("recep.actualizar_7", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_secundario")
        self.btn_actualizar.setFixedSize(150, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        # Pill segmented switch — mismas constantes de estilo que HistorialUnificadoPage
        # (_SS_PILL_*), reutilizadas verbatim para no duplicar QSS.
        pill_row = QHBoxLayout()
        pill_row.setSpacing(0)

        self.btn_recepcion = QPushButton(tr("recep.incidencias_recepcion", default="📥  INCIDENCIAS RECEPCIÓN"))
        self.btn_recepcion.setFixedHeight(44)
        self.btn_recepcion.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recepcion.clicked.connect(lambda: self._cambiar(0))

        div = QFrame()
        div.setFixedWidth(1)
        div.setFixedHeight(44)
        div.setStyleSheet("background-color: #00FFC6;")

        self.btn_traspaso = QPushButton(tr("recep.incidencias_traspaso", default="🚚  INCIDENCIAS TRASPASO"))
        self.btn_traspaso.setFixedHeight(44)
        self.btn_traspaso.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_traspaso.clicked.connect(lambda: self._cambiar(1))

        pill_row.addStretch()
        pill_row.addWidget(self.btn_recepcion)
        pill_row.addWidget(div)
        pill_row.addWidget(self.btn_traspaso)
        pill_row.addStretch()
        ly.addLayout(pill_row)

        from src.db.logistica import listar_incidencias_recepcion, listar_incidencias_traspaso

        self._stack = QStackedWidget()
        self.pag_recepcion = _IncidenciasTablaPage(
            listar_incidencias_recepcion, usuario=self.usuario, codigo_local=self.codigo_local,
        )
        self.pag_traspaso = _IncidenciasTablaPage(
            listar_incidencias_traspaso, usuario=self.usuario, codigo_local=self.codigo_local,
        )
        self._stack.addWidget(self.pag_recepcion)  # index 0
        self._stack.addWidget(self.pag_traspaso)   # index 1
        ly.addWidget(self._stack)

        # Animación de deslizamiento al cambiar entre Recepción/Traspaso — mismo motivo/patrón
        # que en `HistorialUnificadoPage._setup_ui` (stack interno creado de forma perezosa).
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self._stack)
        except Exception:
            pass

        self._aplicar_estilos_pill(0)

        hint = QLabel(tr("recep.doble_clic_sobre_una_inciden", default="Doble clic sobre una incidencia ABIERTA para cerrarla."))
        hint.setObjectName("subtitulo_muted")
        ly.addWidget(hint)

    def _aplicar_estilos_pill(self, idx: int):
        if idx == 0:
            self.btn_recepcion.setStyleSheet(HistorialUnificadoPage._SS_PILL_IZQUIERDO_ACTIVE)
            self.btn_traspaso.setStyleSheet(HistorialUnificadoPage._SS_PILL_DERECHO_INACTIVE)
        else:
            self.btn_recepcion.setStyleSheet(HistorialUnificadoPage._SS_PILL_IZQUIERDO_INACTIVE)
            self.btn_traspaso.setStyleSheet(HistorialUnificadoPage._SS_PILL_DERECHO_ACTIVE)

    def _cambiar(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._aplicar_estilos_pill(idx)
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()

    def cargar_datos(self):
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando_3", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_8", default="🔄 ACTUALIZAR"))

    def _abrir_nueva(self):
        dlg = _NuevaIncidenciaDialog(self.usuario, parent=self)
        if dlg.exec():
            self.cargar_datos()
            _mensaje_ui(
                self, "Registrada",
                "La incidencia ha sido registrada correctamente.", "info"
            )


# ============================================================
# HISTORIAL UNIFICADO (switch Recepciones / Traspasos)
# ============================================================

class HistorialUnificadoPage(QWidget):
    """Pestaña HISTORIAL con selector entre Recepciones y Traspasos."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._setup_ui()

    # Inline stylesheets for the pill segmented switch
    _SS_PILL_ACTIVE = (
        "QPushButton {"
        "  background-color: #00FFC6;"
        "  color: #0D1117;"
        "  border: 1px solid #00FFC6;"
        "  font-family: 'Segoe UI';"
        "  font-size: 13px;"
        "  font-weight: 700;"
        "  padding: 0 20px;"
        "}"
        "QPushButton:hover {"
        "  background-color: #00E5B3;"
        "}"
    )
    _SS_PILL_IZQUIERDO_ACTIVE = (
        _SS_PILL_ACTIVE
        + "QPushButton { border-top-left-radius: 22px; border-bottom-left-radius: 22px;"
        "  border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none; }"
    )
    _SS_PILL_DERECHO_ACTIVE = (
        _SS_PILL_ACTIVE
        + "QPushButton { border-top-right-radius: 22px; border-bottom-right-radius: 22px;"
        "  border-top-left-radius: 0px; border-bottom-left-radius: 0px; border-left: none; }"
    )
    _SS_PILL_INACTIVE = (
        "QPushButton {"
        "  background-color: transparent;"
        "  color: #00FFC6;"
        "  border: 1px solid #00FFC6;"
        "  font-family: 'Segoe UI';"
        "  font-size: 14px;"
        "  font-weight: 700;"
        "  padding: 0 20px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(0, 255, 198, 0.12);"
        "}"
    )
    _SS_PILL_IZQUIERDO_INACTIVE = (
        _SS_PILL_INACTIVE
        + "QPushButton { border-top-left-radius: 22px; border-bottom-left-radius: 22px;"
        "  border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none; }"
    )
    _SS_PILL_DERECHO_INACTIVE = (
        _SS_PILL_INACTIVE
        + "QPushButton { border-top-right-radius: 22px; border-bottom-right-radius: 22px;"
        "  border-top-left-radius: 0px; border-bottom-left-radius: 0px; border-left: none; }"
    )
    # Tercera pestaña "Bultos" (sin esquinas redondeadas, va en el centro) — reutiliza los colores
    # base de _SS_PILL_ACTIVE/_SS_PILL_INACTIVE, solo cambia el radio de esquina.
    _SS_PILL_CENTRO_ACTIVE = (
        _SS_PILL_ACTIVE + "QPushButton { border-radius: 0px; border-left: none; }"
    )
    _SS_PILL_CENTRO_INACTIVE = (
        _SS_PILL_INACTIVE + "QPushButton { border-radius: 0px; border-left: none; }"
    )

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        # Header row: title/subtitle left, refresh button right
        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.historial_logistico", default="Historial Logístico"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.consulta_el_historial_de_rec", default="Consulta el historial de recepciones de palés y traspasos de stock"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_refresh = QPushButton(tr("recep.actualizar_9", default="🔄 ACTUALIZAR"))
        self.btn_refresh.setObjectName("btn_primario")
        self.btn_refresh.setFixedSize(180, 45)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._actualizar)
        hdr.addWidget(self.btn_refresh)
        ly.addLayout(hdr)

        # Pill segmented switch — inline, no wrapper frame
        pill_row = QHBoxLayout()
        pill_row.setSpacing(0)

        self.btn_rec = QPushButton(tr("recep.historial_recepciones", default="📥  HISTORIAL RECEPCIONES"))
        self.btn_rec.setFixedHeight(44)
        self.btn_rec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rec.clicked.connect(lambda: self._cambiar(0))

        # Divider pixel — 1 px separator between the two halves
        div = QFrame()
        div.setFixedWidth(1)
        div.setFixedHeight(44)
        div.setStyleSheet("background-color: #00FFC6;")

        self.btn_tras = QPushButton(tr("recep.historial_traspasos", default="🚚  HISTORIAL TRASPASOS"))
        self.btn_tras.setFixedHeight(44)
        self.btn_tras.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tras.clicked.connect(lambda: self._cambiar(1))

        div2 = QFrame()
        div2.setFixedWidth(1)
        div2.setFixedHeight(44)
        div2.setStyleSheet("background-color: #00FFC6;")

        self.btn_bultos = QPushButton(tr("recep.historial_bultos", default="📦  HISTORIAL BULTOS"))
        self.btn_bultos.setFixedHeight(44)
        self.btn_bultos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bultos.clicked.connect(lambda: self._cambiar(2))

        pill_row.addStretch()
        pill_row.addWidget(self.btn_rec)
        pill_row.addWidget(div)
        pill_row.addWidget(self.btn_tras)
        pill_row.addWidget(div2)
        pill_row.addWidget(self.btn_bultos)
        pill_row.addStretch()
        ly.addLayout(pill_row)

        # Sub-pages embedded directly
        self._stack = QStackedWidget()
        self.pag_recepciones = HistorialRecepcionesPage(
            codigo_local=self.codigo_local, usuario=self.usuario
        )
        self.pag_traspasos = HistorialTraspasosPage(
            usuario=self.usuario, codigo_local=self.codigo_local
        )
        self.pag_bultos = HistorialBultosPage(
            codigo_local=self.codigo_local, usuario=self.usuario
        )
        self._stack.addWidget(self.pag_recepciones)  # index 0
        self._stack.addWidget(self.pag_traspasos)    # index 1
        self._stack.addWidget(self.pag_bultos)       # index 2
        ly.addWidget(self._stack)

        # Animación de deslizamiento al cambiar entre Recepciones/Traspasos. Se instala aquí (no
        # basta con `instalar_transiciones_en` a nivel de ventana): esta página se crea de forma
        # perezosa (al visitar por primera vez la pestaña "Historial"), después de que el resto de
        # la ventana ya haya propagado la transición — este `_stack` interno aún no existía entonces.
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self._stack)
        except Exception:
            pass

        # Hide sub-page internal headers (would duplicate our own title/refresh)
        self._ocultar_cabecera_subpagina(self.pag_recepciones)
        self._ocultar_cabecera_subpagina(self.pag_traspasos)
        self._ocultar_cabecera_subpagina(self.pag_bultos)

        # Set initial active state
        self._aplicar_estilos_pill(0)

    def _ocultar_cabecera_subpagina(self, pag):
        # HistorialRecepcionesPage wraps content in page_widget; HistorialTraspasosPage uses self directly
        target_widget = getattr(pag, 'page_widget', pag)
        target_ly = target_widget.layout() if target_widget is not None else None
        if target_ly is None:
            return
        if target_ly.count() > 0:
            target_ly.takeAt(0)
            target_ly.setContentsMargins(0, 0, 0, 0)
        # Hide any label children that were orphaned from the removed layout item
        try:
            for lbl in target_widget.findChildren(QLabel):
                if lbl.objectName() in ("titulo_cian", "subtitulo_muted"):
                    lbl.hide()
        except Exception:
            pass
        # Hide known header buttons that remain as self attributes (camera/search buttons stay visible)
        for attr in ("btn_refresh", "btn_back_level", "btn_actualizar"):
            w = getattr(pag, attr, None)
            if w is not None:
                w.hide()

    def _aplicar_estilos_pill(self, idx: int):
        self.btn_rec.setStyleSheet(
            self._SS_PILL_IZQUIERDO_ACTIVE if idx == 0 else self._SS_PILL_IZQUIERDO_INACTIVE)
        self.btn_tras.setStyleSheet(
            self._SS_PILL_CENTRO_ACTIVE if idx == 1 else self._SS_PILL_CENTRO_INACTIVE)
        self.btn_bultos.setStyleSheet(
            self._SS_PILL_DERECHO_ACTIVE if idx == 2 else self._SS_PILL_DERECHO_INACTIVE)

    def _cambiar(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._aplicar_estilos_pill(idx)
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()

    def _actualizar(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText(tr("recep.actualizando_4", default="⌛ ACTUALIZANDO..."))
        self.btn_refresh.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText(tr("recep.actualizar_10", default="🔄 ACTUALIZAR"))

    def cargar_datos(self):
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()


class HistorialBultosPage(QWidget):
    """Historial de BULTOS recepcionados individualmente (sub-pestaña de Historial Logístico).

    MISMA estructura/columnas/lógica que `HistorialRecepcionesPage` (buscador con escaneo remoto,
    tabla estilizada, 3 niveles con botones de ACCIONES, colores de estado, PDF del albarán) —
    adaptada a bultos: Nivel 1 = Documentos CON algún bulto declarado (mismas 5 columnas que
    Recepciones); Nivel 2 = Bultos de ese documento (en vez de "palés" — mismo formato de 4
    columnas, con el palé de origen de cada bulto); Nivel 3 = Artículos de ese bulto, con cantidad
    ESPERADA y RECIBIDA por separado (a diferencia de Recepciones, aquí sí pueden diferir — es
    justo lo que el operario necesita poder revisar)."""

    def __init__(self, codigo_local="ALMC", usuario=None, parent=None):
        super().__init__(parent)
        self.codigo_local = codigo_local
        self.usuario = usuario
        self.nivel_actual = 1  # 1: Documentos, 2: Bultos del documento, 3: Artículos del bulto
        self.filtro_id_documento = None
        self.filtro_id_bulto = None
        self.setObjectName("panel_contenido")
        (self.page_widget, self.tabla, self.input_busqueda, self.btn_refresh,
         self.btn_back_level) = self.setup_ui_historial(
            tr("recep.historial_bultos_titulo", default="Historial de Bultos"),
            tr("recep.historial_bultos_sub",
               default="Consulta y trazabilidad de recepciones bulto a bulto"))
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.page_widget)

        self.btn_refresh.clicked.connect(self.cargar_datos)
        self.btn_back_level.clicked.connect(self.retroceder_nivel)
        self.input_busqueda.textChanged.connect(self.cargar_datos)

        self.cargar_datos()

    def setup_ui_historial(self, titulo_texto, subtitulo_texto):
        page = QWidget()
        page.setObjectName("panel_contenido")
        ly_principal = QVBoxLayout(page)
        ly_principal.setContentsMargins(30, 30, 30, 30)
        ly_principal.setSpacing(25)

        header_layout = QHBoxLayout()
        title_container = QVBoxLayout()
        self.lbl_titulo = QLabel(titulo_texto)
        self.lbl_titulo.setObjectName("titulo_cian")
        lbl_subtitulo = QLabel(subtitulo_texto)
        lbl_subtitulo.setObjectName("subtitulo_muted")
        title_container.addWidget(self.lbl_titulo)
        title_container.addWidget(lbl_subtitulo)
        header_layout.addLayout(title_container)
        header_layout.addStretch()

        btn_back_level = QPushButton(tr("recep.volver", default="⬅ VOLVER"))
        btn_back_level.setObjectName("btn_secundario")
        btn_back_level.setFixedSize(130, 45)
        btn_back_level.setVisible(False)
        btn_back_level.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_refresh = QPushButton(tr("recep.actualizar_13", default="🔄 ACTUALIZAR"))
        btn_refresh.setObjectName("btn_primario")
        btn_refresh.setFixedSize(180, 45)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(btn_back_level)
        header_layout.addSpacing(10)
        header_layout.addWidget(btn_refresh)
        ly_principal.addLayout(header_layout)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        input_busqueda = QLineEdit()
        input_busqueda.setObjectName("input_buscador")
        input_busqueda.setPlaceholderText(
            tr("recep.filtrar_bultos", default="🔍 Filtrar por ID, Bulto, Artículo, EAN u Origen..."))
        input_busqueda.setFixedHeight(50)

        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=input_busqueda.setText, contexto="recepcion.historial_bultos")

        btn_buscar = QPushButton("🔍")
        btn_buscar.setObjectName("btn_icono")
        btn_buscar.setFixedSize(48, 48)
        btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_buscar.clicked.connect(self.cargar_datos)

        search_layout.addWidget(input_busqueda)
        search_layout.addWidget(btn_buscar)
        search_layout.addWidget(btn_escaneo_movil)
        ly_principal.addLayout(search_layout)

        if construir_tabla_estilizada is not None:
            wrap_tabla, tabla = construir_tabla_estilizada()
        else:
            wrap_tabla = QFrame()
            wrap_tabla.setObjectName("contenedor_tabla_estandar")
            wrap_layout = QVBoxLayout(wrap_tabla)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.setSpacing(0)
            tabla = QTableWidget()
            wrap_layout.addWidget(tabla)

        header = tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabla.verticalHeader().setDefaultSectionSize(60)
        tabla.setStyleSheet("QTableWidget::item { padding: 0px 8px; }")
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly_principal.addWidget(wrap_tabla)

        return page, tabla, input_busqueda, btn_refresh, btn_back_level

    def configurar_tabla_nivel_1(self):
        self.btn_back_level.setVisible(False)
        self.lbl_titulo.setText(tr("recep.historial_bultos_titulo", default="Historial de Bultos"))
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(["ID DOCUMENTO", "FECHA ENVÍO", "ORIGEN", "ESTADO", "ACCIONES"])
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(4, 150)

    def configurar_tabla_nivel_2(self):
        self.btn_back_level.setVisible(True)
        self.lbl_titulo.setText(
            f"Bultos en Documento: <span style='color:#00FFC6;'>{self.filtro_id_documento}</span>")
        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels(["CÓDIGO BULTO", "PALÉ DE ORIGEN", "FECHA RECEPCIÓN", "ACCIONES"])
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(3, 150)

    def configurar_tabla_nivel_3(self):
        self.btn_back_level.setVisible(True)
        self.lbl_titulo.setText(
            f"Contenido Bulto: <span style='color:#00FFC6;'>{self.filtro_id_bulto}</span>")
        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels(
            ["EAN / CÓDIGO", "DESCRIPCIÓN ARTÍCULO", "CANTIDAD ESPERADA", "CANTIDAD RECIBIDA"])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    def cargar_datos(self):
        busqueda_texto = self.input_busqueda.text().strip()
        busqueda_param = f"%{busqueda_texto}%"
        local_ref = str(self.codigo_local)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    if self.nivel_actual == 1:
                        self.configurar_tabla_nivel_1()
                        cursor.execute(
                            """
                            SELECT DISTINCT d.id_documento, d.fecha_envio, d.origen, d.estado
                            FROM documentos_logisticos d
                            JOIN documentos_logisticos_bultos b ON b.id_documento = d.id_documento
                            WHERE d.destino = %s
                              AND (d.id_documento LIKE %s OR d.origen LIKE %s OR d.estado LIKE %s)
                            ORDER BY d.fecha_envio DESC
                            """,
                            (local_ref, busqueda_param, busqueda_param, busqueda_param),
                        )
                    elif self.nivel_actual == 2:
                        self.configurar_tabla_nivel_2()
                        cursor.execute(
                            """
                            SELECT b.id_bulto, b.id_visual, b.id_pale, b.estado, b.fecha_recepcion,
                                   p.id_visual AS pale_visual
                            FROM documentos_logisticos_bultos b
                            LEFT JOIN documentos_logisticos_pales p ON p.id_pale = b.id_pale
                            WHERE b.id_documento = %s AND (b.id_bulto LIKE %s OR p.id_visual LIKE %s)
                            ORDER BY b.id_visual ASC
                            """,
                            (self.filtro_id_documento, busqueda_param, busqueda_param),
                        )
                    else:
                        self.configurar_tabla_nivel_3()
                        cursor.execute(
                            """
                            SELECT codigo_articulo AS codigo, nombre_articulo AS nombre,
                                   cantidad_enviada AS cantidad, cantidad_recibida
                            FROM documentos_logisticos_bultos_lineas
                            WHERE id_bulto = %s AND (nombre_articulo LIKE %s OR codigo_articulo LIKE %s)
                            """,
                            (self.filtro_id_bulto, busqueda_param, busqueda_param),
                        )

                    if cursor.description:
                        columnas = [desc[0] for desc in cursor.description]
                        resultados = [dict(zip(columnas, row, strict=False)) for row in cursor.fetchall()]
                        self.renderizar_filas(resultados)
                    else:
                        self.tabla.setRowCount(0)
        except Exception as e:
            logger.error(f"Error cargando historial de bultos: {e}")
            _mensaje_ui(self, "Error de Conexión",
                       f"No se pudo sincronizar con el servidor.\n\nDetalle: {e}", "error")
        finally:
            QApplication.restoreOverrideCursor()

    def renderizar_filas(self, rows):
        self.tabla.setRowCount(0)
        if not rows:
            return
        self.tabla.setRowCount(len(rows))

        for i, row in enumerate(rows):
            if self.nivel_actual == 1:
                vals = [row["id_documento"], str(row["fecha_envio"]), row["origen"], str(row["estado"]).upper()]
                self.agregar_botones_nivel_1(i, row["id_documento"])
            elif self.nivel_actual == 2:
                vals = [row["id_bulto"], row.get("pale_visual") or row.get("id_pale"),
                        str(row["fecha_recepcion"]) if row.get("fecha_recepcion") else "—"]
                self.agregar_botones_nivel_2(i, row["id_bulto"])
            else:
                recibida = row.get("cantidad_recibida")
                vals = [row["codigo"], row["nombre"], str(row["cantidad"]),
                        str(recibida) if recibida is not None else "—"]

            for j, val in enumerate(vals):
                item = QTableWidgetItem(str(val) if val else "-")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if self.nivel_actual == 1 and j == 3:
                    estado = str(val).upper()
                    if estado == "RECIBIDO":
                        color = "#00FFC6"
                    elif estado in ("PENDIENTE", "PARCIAL"):
                        color = "#F1C40F"
                    elif "ERROR" in estado or "CANCELADO" in estado:
                        color = "#FF6B6B"
                    else:
                        color = "#8B949E"
                    item.setForeground(QColor(color))
                    item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                elif j == 0:
                    item.setForeground(QColor("#58A6FF"))

                self.tabla.setItem(i, j, item)

    def agregar_botones_nivel_1(self, fila, id_doc):
        id_doc_str = str(id_doc)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_ver = self.crear_boton_estilizado("🔍 DETALLES", "#21262D", "#00FFC6")
        btn_pdf = self.crear_boton_estilizado("📄 PDF", "#21262D", "#F0A500")
        btn_ver.clicked.connect(lambda: self.ir_a_nivel_2(id_doc_str))
        btn_pdf.clicked.connect(lambda: self.abrir_albaran(id_doc_str))

        lay.addWidget(btn_ver, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(btn_pdf, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tabla.setCellWidget(fila, 4, container)

    def agregar_botones_nivel_2(self, fila, id_bulto):
        id_bulto_str = str(id_bulto)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)

        btn_items = self.crear_boton_estilizado("📦 VER CONTENIDO", "#21262D", "#00FFC6")
        btn_items.clicked.connect(lambda: self.ir_a_nivel_3(id_bulto_str))

        lay.addWidget(btn_items, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabla.setCellWidget(fila, 3, container)

    def crear_boton_estilizado(self, texto, bg, color_neon):
        btn = QPushButton(texto)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(44)
        btn.setStyleSheet(
            f"QPushButton{{background:{bg};color:{color_neon};"
            f"border:2px solid {color_neon};border-radius:10px;"
            f"font-family:'Segoe UI';font-weight:700;font-size:12px;padding:0px 14px;}}"
            f"QPushButton:hover{{background:{color_neon};color:#0D1117;}}"
            f"QPushButton:pressed{{background:{color_neon};color:#0D1117;}}"
        )
        return btn

    def abrir_albaran(self, id_documento):
        """Abre el MISMO PDF de albarán que Historial de Recepciones (documento → bultos comparte
        documento padre) — si todavía no se generó, pide generarlo desde Recepciones en vez de
        duplicar aquí esa lógica de reconstrucción (ya existe en `HistorialRecepcionesPage`)."""
        ruta_pdf = os.path.abspath(os.path.join("documentos", "albaranes", f"ALB_{id_documento}.pdf"))
        if os.path.exists(ruta_pdf):
            abrir_pdf(ruta_pdf)
        else:
            _mensaje_ui(self, "Albarán no generado",
                       "Genera primero el albarán desde la pestaña Historial Recepciones.", "warning")

    def ir_a_nivel_2(self, id_doc):
        self.filtro_id_documento = id_doc
        self.nivel_actual = 2
        self.input_busqueda.clear()
        self.tabla.scrollToTop()
        self.cargar_datos()

    def ir_a_nivel_3(self, id_bulto):
        self.filtro_id_bulto = id_bulto
        self.nivel_actual = 3
        self.input_busqueda.clear()
        self.tabla.scrollToTop()
        self.cargar_datos()

    def retroceder_nivel(self):
        if self.nivel_actual == 3:
            self.nivel_actual = 2
            self.filtro_id_bulto = None
        elif self.nivel_actual == 2:
            self.nivel_actual = 1
            self.filtro_id_documento = None
        self.input_busqueda.clear()
        self.cargar_datos()


class CrossDockingPage(QWidget):
    """Pestaña CROSS-DOCKING (Fase D): KPI del dominio BI `logistica` (Fase A) + listado de los
    movimientos de kárdex `tipo_movimiento='CROSS_DOCKING'` más recientes. Misma estructura que las
    páginas hermanas (`IncidenciasPage`/`ExpedicionesPage`): sin lógica de negocio propia, solo
    orquesta datos ya calculados por `services.bi.calculadores`/`db.conexion`."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.cross_docking_titulo", default="Envío Directo"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.cross_docking_sub",
                      default="Recepciones enrutadas directamente hacia un pedido de salida "
                              "pendiente, sin permanencia en almacén."))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_actualizar = QPushButton(tr("recep.actualizar_xdock", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.cargar_datos)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        from src.gui.components.enterprise import EnterpriseCard
        self.card_operaciones = EnterpriseCard(
            tr("recep.xdock_kpi_operaciones", default="Operaciones Cross-Docking (30 días)"), "0",
            modo="kpi", concepto="logistica")
        self.card_unidades = EnterpriseCard(
            tr("recep.xdock_kpi_unidades", default="Unidades cross-dockeadas (30 días)"), "0",
            modo="kpi", concepto="logistica")
        kpis.addWidget(self.card_operaciones)
        kpis.addWidget(self.card_unidades)
        kpis.addStretch()
        ly.addLayout(kpis)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = [tr("recep.col_fecha", default="Fecha"), tr("recep.col_codigo", default="Código"),
                tr("recep.col_cantidad", default="Cantidad"), tr("recep.col_origen", default="Origen"),
                tr("recep.col_destino", default="Destino"),
                tr("recep.col_documento", default="Documento"),
                tr("recep.col_usuario", default="Usuario")]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self._cont)

        # ── Cross-docking a RUTAS DE REPARTO (petición explícita) ──────────────────────────────
        # Mercancía de Producción/Traspasos enlazada automáticamente a un camión/ruta ya abierto,
        # con el cierre de un solo clic (validar albarán + stock en tránsito + cerrar expedición).
        t2 = QLabel(tr("recep.xdock_rutas_titulo", default="Enlazado a rutas de reparto"))
        t2.setObjectName("titulo_cian")
        ly.addWidget(t2)

        self.tabla_rutas = QTableWidget(self)
        cols_r = [tr("recep.col_documento", default="Documento"), tr("recep.col_tipo", default="Tipo"),
                 tr("recep.col_destino", default="Destino"), tr("recep.xdock_ruta", default="Ruta"),
                 tr("recep.xdock_vehiculo", default="Vehículo"), tr("recep.xdock_conductor", default="Conductor"),
                 tr("recep.col_estado", default="Estado"), tr("recep.xdock_validado", default="Validado")]
        self.tabla_rutas.setColumnCount(len(cols_r))
        self.tabla_rutas.setHorizontalHeaderLabels(cols_r)
        self.tabla_rutas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla_rutas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_rutas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        ly.addWidget(self.tabla_rutas)

        acc_rutas = QHBoxLayout(); acc_rutas.addStretch()
        self.btn_validar_cerrar = QPushButton(
            tr("recep.xdock_validar_cerrar_btn", default="✔ VALIDAR Y CERRAR EXPEDICIÓN"))
        self.btn_validar_cerrar.setObjectName("btn_primario")
        self.btn_validar_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_validar_cerrar.setFixedHeight(40)
        self.btn_validar_cerrar.clicked.connect(self._validar_cerrar_seleccionado)
        acc_rutas.addWidget(self.btn_validar_cerrar)
        ly.addLayout(acc_rutas)

        # Pendientes de ruta: mercancía con centro destino fijado pero sin camión disponible todavía.
        t3 = QLabel(tr("recep.xdock_pendientes_titulo", default="Pendientes de ruta disponible"))
        t3.setObjectName("subtitulo_muted")
        ly.addWidget(t3)
        self.tabla_pendientes = QTableWidget(self)
        cols_p = [tr("recep.col_documento", default="Documento"), tr("recep.col_tipo", default="Tipo"),
                 tr("recep.col_origen", default="Origen"), tr("recep.col_destino", default="Destino"),
                 tr("recep.col_estado", default="Estado"), tr("recep.col_fecha", default="Fecha")]
        self.tabla_pendientes.setColumnCount(len(cols_p))
        self.tabla_pendientes.setHorizontalHeaderLabels(cols_p)
        self.tabla_pendientes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla_pendientes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self.tabla_pendientes)

    def _validar_cerrar_seleccionado(self):
        fila = self.tabla_rutas.currentRow()
        if fila < 0:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("recep.xdock_validar_cerrar_btn", default="Validar y cerrar expedición"),
                                tr("recep.xdock_sin_seleccion", default="Selecciona primero una fila de la tabla."),
                                nivel="warning")
            return
        id_documento = self.tabla_rutas.item(fila, 0).text()
        from src.services.logistica import cross_docking_rutas as XD
        from src.db.usuario import sesion_global
        usuario = (sesion_global.usuario_actual or {}).get("nombre") if sesion_global.usuario_actual else None
        r = XD.validar_y_cerrar_expedicion(id_documento, usuario=usuario)
        if mostrar_mensaje:
            if r.get("ok"):
                mostrar_mensaje(self, tr("recep.xdock_validar_cerrar_btn", default="Validar y cerrar expedición"),
                                tr("recep.xdock_validado_ok", default="Expedición {d} validada y cerrada.",
                                   d=id_documento),
                                nivel="success")
            else:
                mostrar_mensaje(self, tr("recep.xdock_validar_cerrar_btn", default="Validar y cerrar expedición"),
                                str(r.get("error") or "Error"), nivel="warning")
        self.cargar_datos()

    def cargar_datos(self):
        from datetime import date, timedelta
        from src.db.empresa import empresa_actual_id
        id_empresa = empresa_actual_id()
        hoy = date.today()
        desde = hoy - timedelta(days=30)
        try:
            from src.services.bi import calculadores
            kpi = calculadores.logistica(id_empresa, desde.isoformat(), hoy.isoformat())
        except Exception as e:
            logger.warning("CrossDockingPage.cargar_datos (BI): %s", e)
            kpi = {}
        self.card_operaciones.set_valor(kpi.get("logistica.cross_docking_operaciones", 0))
        self.card_unidades.set_valor(kpi.get("logistica.cross_docking_unidades", 0))

        movimientos = []
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT codigo_articulo, cantidad, origen, destino, id_documento, usuario, "
                    "fecha_movimiento FROM movimientos_stock WHERE id_empresa=%s "
                    "AND tipo_movimiento='CROSS_DOCKING' ORDER BY fecha_movimiento DESC LIMIT 200",
                    (id_empresa,))
                cols = [d[0] for d in cur.description]
                movimientos = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning("CrossDockingPage.cargar_datos (movimientos): %s", e)

        self.tabla.setRowCount(len(movimientos))
        for row, m in enumerate(movimientos):
            valores = [str(m.get("fecha_movimiento") or ""), str(m.get("codigo_articulo") or ""),
                      str(m.get("cantidad") or 0), str(m.get("origen") or ""),
                      str(m.get("destino") or ""), str(m.get("id_documento") or ""),
                      str(m.get("usuario") or "")]
            for col, val in enumerate(valores):
                self.tabla.setItem(row, col, QTableWidgetItem(val))

        try:
            from src.services.logistica import cross_docking_rutas as XD
            datos_xd = XD.documentos_cross_docking(id_empresa)
        except Exception as e:
            logger.warning("CrossDockingPage.cargar_datos (rutas): %s", e)
            datos_xd = {"cross_dockeados": [], "pendientes": []}

        enlazados = datos_xd.get("cross_dockeados") or []
        self.tabla_rutas.setRowCount(len(enlazados))
        for row, d in enumerate(enlazados):
            validado = "✔" if d.get("validado") else "—"
            valores = [str(d.get("id_documento") or ""), str(d.get("tipo_documento") or ""),
                      str(d.get("destino") or ""), str(d.get("id_ruta") or ""),
                      str(d.get("matricula") or "—"), str(d.get("conductor") or "—"),
                      str(d.get("estado") or ""), validado]
            for col, val in enumerate(valores):
                self.tabla_rutas.setItem(row, col, QTableWidgetItem(val))

        pendientes = datos_xd.get("pendientes") or []
        self.tabla_pendientes.setRowCount(len(pendientes))
        for row, d in enumerate(pendientes):
            valores = [str(d.get("id_documento") or ""), str(d.get("tipo_documento") or ""),
                      str(d.get("origen") or ""), str(d.get("destino") or ""),
                      str(d.get("estado") or ""), str(d.get("fecha_creacion") or "")]
            for col, val in enumerate(valores):
                self.tabla_pendientes.setItem(row, col, QTableWidgetItem(val))


# ============================================================
# BLOQUE REVISIÓN DE LOTE/CADUCIDAD EN RECEPCIÓN (Punto 3 · INV.3/FEFO)
# ============================================================

_RE_FECHA_LOTE = None  # compilado perezosamente (evita importar `re` a nivel de módulo)


def _fecha_lote_valida(txt: str) -> bool:
    """Valida el formato AAAA-MM-DD (mismo criterio de texto libre que `lotes_caducidades.py`,
    sin introducir un widget de fecha nuevo en la app)."""
    import re
    global _RE_FECHA_LOTE
    if _RE_FECHA_LOTE is None:
        _RE_FECHA_LOTE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    return bool(_RE_FECHA_LOTE.match((txt or "").strip()))


class _RevisionLotesRecepcionDialog(QDialog):
    """Revisión de líneas antes de confirmar la recepción de un documento (palé de traspaso interno
    O pedido B2B — Punto de unificación de recepciones): permite introducir lote/caducidad por
    artículo. El motor oficial de recepción de traspasos (`db.logistica.procesar_recepcion_logistica`)
    tiene el gancho de alta de lote (best-effort, `origen="recepcion"`); el de pedidos B2B
    (`b2b_pedidos.recibir_mercancia`) lo tiene vía `lineas_override`. Si el artículo tiene
    `articulos.requiere_lote=1`, el lote y la caducidad pasan de opcionales a OBLIGATORIOS (bloquea
    la confirmación con un mensaje claro); si no, se mantiene el mismo espíritu "opc." que ya usa
    el formulario de Recepciones del Portal Empresa.

    `es_b2b=True` (Punto 3 bis, rediseño del flujo lote/caducidad): las líneas de un pedido B2B ya
    declararon su lote/caducidad — el proveedor lo fijó en su catálogo B2B y viajó con el pedido
    (`transaccion_lineas.lote/fecha_caducidad`, calculado por `b2b_pedidos._fijar_suministrador_y_
    unidades`). Cuando una línea trae ese dato, se muestra de forma READ-ONLY (idéntico criterio que
    usaba el antiguo "Confirmar recepción de mercancía" del Portal Empresa, ahora retirado — la
    recepción física se hace SOLO desde aquí): el operario solo la confirma, nunca la reescribe. La
    entrada manual (editable, y obligatoria si `requiere_lote`) sigue siendo el FALLBACK exclusivo de
    líneas sin dato declarado por el proveedor. Para traspasos internos (`es_b2b=False`, por defecto)
    el comportamiento es EXACTAMENTE el de siempre: nunca hay dato declarado, entrada manual completa."""

    def __init__(self, items, parent=None, *, es_b2b=False, demanda=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.revision_lotes_titulo", default="Revisión de recepción — Lote/Caducidad"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_revision_lotes")
        self.setMinimumWidth(760)
        self._drag_pos = None
        self.resultado = None
        self.es_b2b = es_b2b
        self._filas = []  # (codigo, nombre, cantidad, requiere_lote, inp_lote, inp_caducidad, id_linea)
        # Cross-Docking (Fase D): `demanda` = {codigo: [entradas de demanda_pendiente_por_articulo]}
        # ya acotado a los códigos de ESTE documento escaneado. `cross_dock_seleccionado` guarda lo que
        # el usuario decidió aplicar (se lee DESPUÉS de aceptar el diálogo, una vez la recepción normal
        # ya está confirmada — el cross-dock mueve stock DESDE el almacén de recepción, que solo existe
        # de verdad una vez la recepción se ha comprometido).
        self._demanda = demanda or {}
        self.cross_dock_seleccionado = {}
        self._banners_xdock = {}
        self._build_ui(items or [])

    def _build_ui(self, items):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(30, 25, 30, 25)
        ly.setSpacing(14)

        lbl = QLabel(tr("recep.revision_lotes_lbl", default="REVISA LOTE Y CADUCIDAD ANTES DE CONFIRMAR"))
        lbl.setObjectName("titulo_cian")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl)

        sub = QLabel(tr("recep.revision_lotes_sub",
                        default="Los artículos marcados con ⚠ exigen lote y caducidad (AAAA-MM-DD) "
                                "para poder recibirse."))
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8B949E;font-size:11px;")
        ly.addWidget(sub)

        tabla = QTableWidget(len(items), 5)
        tabla.setHorizontalHeaderLabels([
            tr("recep.col_codigo", default="Código"), tr("recep.col_nombre", default="Nombre"),
            tr("recep.col_cantidad", default="Cantidad"), tr("recep.col_lote", default="Lote"),
            tr("recep.col_caducidad", default="Caducidad (AAAA-MM-DD)"),
        ])
        tabla.horizontalHeader().setStretchLastSection(True)
        tabla.verticalHeader().setVisible(False)
        from src.db.conexion import obtener_articulo as _obt_art
        for row, item in enumerate(items):
            id_linea = None
            lote_declarado = None
            cad_declarada = None
            if isinstance(item, dict):
                codigo = str(item.get("codigo") or "")
                nombre = str(item.get("nombre") or codigo)
                cantidad = int(item.get("cantidad") or 0)
                id_linea = item.get("id")
                lote_declarado = item.get("lote")
                cad_declarada = item.get("fecha_caducidad")
            else:
                codigo = str(item[0] or "")
                nombre = str(item[1] or codigo)
                cantidad = int(item[2] or 0)
            requiere_lote = False
            try:
                art = _obt_art(codigo)
                requiere_lote = bool(art and art.get("requiere_lote"))
            except Exception:
                pass
            # Ya declarado por el proveedor (solo pedidos B2B, Punto 3 bis): se muestra read-only en
            # vez de pedir entrada manual — independientemente de `requiere_lote` (si el proveedor lo
            # declaró, es el dato correcto a usar).
            declarado = self.es_b2b and bool(str(lote_declarado or "").strip())
            codigo_txt = codigo + ("  ✔" if declarado else ("  ⚠" if requiere_lote else ""))
            tabla.setItem(row, 0, QTableWidgetItem(codigo_txt))
            tabla.setItem(row, 1, QTableWidgetItem(nombre))
            it_cant = QTableWidgetItem(str(cantidad))
            it_cant.setFlags(it_cant.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabla.setItem(row, 2, it_cant)
            inp_lote = QLineEdit()
            inp_cad = QLineEdit()
            if declarado:
                cad_txt = (cad_declarada.isoformat() if hasattr(cad_declarada, "isoformat")
                          else str(cad_declarada or ""))
                inp_lote.setText(str(lote_declarado))
                inp_lote.setReadOnly(True)
                inp_cad.setText(cad_txt)
                inp_cad.setReadOnly(True)
                for inp in (inp_lote, inp_cad):
                    inp.setStyleSheet("background-color:#161B22;color:#8B949E;")
                    inp.setToolTip(tr("recep.lote_ya_declarado",
                                      default="Ya declarado por el proveedor."))
            else:
                inp_lote.setPlaceholderText(tr("recep.lote_obligatorio", default="Obligatorio")
                                            if requiere_lote else tr("recep.opcional_3", default="Opcional"))
                inp_cad.setPlaceholderText("AAAA-MM-DD" + ("" if requiere_lote
                                           else " (" + tr("recep.opcional_4", default="opcional") + ")"))
            tabla.setCellWidget(row, 3, inp_lote)
            tabla.setCellWidget(row, 4, inp_cad)
            self._filas.append((codigo, nombre, cantidad, requiere_lote, inp_lote, inp_cad, id_linea))
        tabla.setMinimumHeight(min(60 + 40 * max(len(items), 1), 420))
        ly.addWidget(tabla)
        self._tabla = tabla

        # Cross-Docking (Fase D): un banner informativo por artículo con demanda de salida pendiente
        # coincidente. Puramente opcional — si el usuario no pulsa "Aplicar Cross-Docking" la recepción
        # sigue EXACTAMENTE igual que hoy (self.cross_dock_seleccionado queda vacío).
        if self._demanda:
            try:
                from src.gui.components.enterprise import EnterpriseInlineBanner
                vistos = set()
                for codigo, _nombre, cantidad, *_resto in [(f[0], f[1], f[2]) for f in self._filas]:
                    if codigo in vistos:
                        continue
                    matches = self._demanda.get(codigo)
                    if not matches:
                        continue
                    vistos.add(codigo)
                    match = matches[0]
                    cant_match = min(int(cantidad or 0), int(match.get("cantidad_pendiente") or 0))
                    if cant_match <= 0:
                        continue
                    mensaje = tr("recep.xdock_banner",
                                default="{cant} ud. de «{cod}» coinciden con un pedido de salida "
                                        "pendiente ({fuente} #{ref}) — ¿Cross-docking?",
                                cant=cant_match, cod=codigo, fuente=match.get("fuente"),
                                ref=match.get("id_pedido_o_tx"))
                    banner = EnterpriseInlineBanner(
                        mensaje, rol="advertencia",
                        texto_accion=tr("recep.xdock_aplicar", default="Aplicar Cross-Docking"),
                        concepto="cross_docking")
                    banner.accion_pulsada.connect(
                        lambda c=codigo, m=match, q=cant_match, b=banner:
                        self._marcar_cross_dock(c, m, q, b))
                    ly.addWidget(banner)
                    self._banners_xdock[codigo] = banner
            except Exception as e:
                logger.warning("_RevisionLotesRecepcionDialog: banner cross-docking: %s", e)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color:#F85149;font-size:12px;font-weight:700;")
        self.lbl_error.setWordWrap(True)
        ly.addWidget(self.lbl_error)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btn_cancel = QPushButton(tr("recep.cancelar_4", default="CANCELAR"))
        btn_cancel.setObjectName("btn_secundario")
        btn_cancel.setFixedHeight(45)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("recep.confirmar_recepcion", default="✅  CONFIRMAR RECEPCIÓN"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(45)
        btn_ok.clicked.connect(self._confirmar)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        ly.addLayout(btns)

    def _confirmar(self):
        salida = []
        for codigo, nombre, cantidad, requiere_lote, inp_lote, inp_cad, id_linea in self._filas:
            lote = inp_lote.text().strip()
            cad = inp_cad.text().strip()
            if requiere_lote and not lote:
                self.lbl_error.setText(
                    tr("recep.err_lote_obligatorio",
                       default="«{c}» exige lote de trazabilidad: indica el lote antes de continuar.",
                       c=codigo))
                return
            if requiere_lote and not cad:
                self.lbl_error.setText(
                    tr("recep.err_caducidad_obligatoria",
                       default="«{c}» exige caducidad: indícala en formato AAAA-MM-DD antes de continuar.",
                       c=codigo))
                return
            if cad and not _fecha_lote_valida(cad):
                self.lbl_error.setText(
                    tr("recep.err_fecha_formato",
                       default="Caducidad de «{c}» no válida: usa el formato AAAA-MM-DD.", c=codigo))
                return
            fila = {
                "codigo": codigo, "nombre": nombre, "cantidad": cantidad,
                "lote": lote or None, "caducidad": cad or None,
            }
            if id_linea is not None:
                fila["id"] = id_linea
            salida.append(fila)
        self.resultado = salida
        self.accept()

    def _marcar_cross_dock(self, codigo, match, cantidad, banner):
        """Marca (toggle) la aplicación de cross-docking para `codigo`. No mueve stock aquí — eso
        ocurre DESPUÉS de confirmar la recepción normal (`RecepcionPaleWindow` lee
        `cross_dock_seleccionado` tras el commit de la recepción)."""
        if codigo in self.cross_dock_seleccionado:
            del self.cross_dock_seleccionado[codigo]
            banner.set_mensaje(tr("recep.xdock_banner_pendiente",
                                  default="{cant} ud. de «{cod}» coinciden con un pedido de salida "
                                          "pendiente ({fuente} #{ref}) — ¿Cross-docking?",
                                  cant=cantidad, cod=codigo, fuente=match.get("fuente"),
                                  ref=match.get("id_pedido_o_tx")))
        else:
            self.cross_dock_seleccionado[codigo] = {**match, "cantidad_aplicada": cantidad}
            banner.set_mensaje(tr("recep.xdock_banner_aplicado",
                                  default="✔ Cross-Docking aplicado: {cant} ud. de «{cod}» irán a "
                                          "{fuente} #{ref} al confirmar.",
                                  cant=cantidad, cod=codigo, fuente=match.get("fuente"),
                                  ref=match.get("id_pedido_o_tx")))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# BLOQUE VENTANA PRINCIPAL DE RECEPCIÓN
# ============================================================

class RecepcionPaleWindow(QWidget):

    def __init__(self, usuario, callback_vuelta=None, codigo_local="T001", **kwargs):
        super().__init__()
        # Normalizamos el nombre del usuario (Punto 3 de coherencia)
        self.usuario = usuario
        self.callback_vuelta = callback_vuelta
        self.codigo_local = codigo_local

        self.datos_pale_actual = None
        self.hilo_pdf = None

        self.setWindowTitle(
            f"Smart Manager - Gestión Logística [{self.codigo_local}]"
        )
        self.setMinimumSize(1200, 800)

        # Atributo crítico para la limpieza de memoria
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # (Reabastecimiento —y su motor— se han migrado al módulo de Reposición.)

        self.setup_ui()
        self.conectar_eventos_paginas()
        # NO se auto-muestra aquí: quien abre el módulo (menu_principal.manejar_apertura) lo muestra a
        # pantalla completa (frameless + opacidad 0 → revelado tras la animación de deslizamiento). Un
        # showMaximized() propio en __init__ haría aparecer la ventana DURANTE la construcción (antes de
        # poder ocultarla) → parpadeo al entrar al módulo.

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="logistica")
        except Exception:
            pass

    def setup_ui(self):
        # Layout Principal Horizontal
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar_logistica")
        self.sidebar.setFixedWidth(280)

        side_ly = QVBoxLayout(self.sidebar)
        side_ly.setContentsMargins(0, 40, 0, 20)
        side_ly.setSpacing(0)

        lbl_m = QLabel("SMART LOGISTICS")   # título de marca de la sidebar (igual en todos los idiomas)
        lbl_m.setObjectName("sidebar_title")
        side_ly.addWidget(lbl_m)

        # Botones de navegación — 7 pestañas enterprise
        self.btn_nav_scan      = self.crear_boton_nav("Recepción", True)
        self.btn_nav_traspasar = self.crear_boton_nav("Traspasos")
        self.btn_nav_prep      = self.crear_boton_nav("Preparación")
        self.btn_nav_expedir   = self.crear_boton_nav("Expediciones")
        self.btn_nav_incid     = self.crear_boton_nav("Incidencias")
        self.btn_nav_historial = self.crear_boton_nav("Historial")
        self.btn_nav_xdock     = self.crear_boton_nav("Envío Directo")
        # 'Reabastecimiento' se migró al módulo de Reposición; 'Pedir a Central' se retiró (duplicaba
        # Reabastecimiento). Ambas dejan de ser secciones de Logística.

        self.lista_botones_nav = [
            self.btn_nav_scan,
            self.btn_nav_traspasar,
            self.btn_nav_prep,
            self.btn_nav_expedir,
            self.btn_nav_incid,
            self.btn_nav_historial,
            self.btn_nav_xdock,
        ]

        # OPERARIO: solo Recepción (índice 0) — Traspasos/Preparación/Expediciones/Incidencias/
        # Historial son de gestión, restringidas a ADMINISTRADOR/SUPERADMIN. Traspasos (índice 1) pasa
        # por RBAC (`logistica.traspasos`, antes un check ad-hoc de perfil) para que una concesión
        # individual desbloquee la pestaña igual en escritorio y en el móvil; el resto sigue con el
        # mismo criterio de siempre (no se pidió extenderles el permiso fino).
        from src.services import autorizacion
        _perfil_log = str((self.usuario or {}).get("perfil", "")).upper()
        _solo_recepcion = _perfil_log == "OPERARIO"
        _puede_traspasos = autorizacion.puede(self.usuario, "logistica.traspasos")
        for i, btn in enumerate(self.lista_botones_nav):
            btn.setFixedHeight(55)
            try:
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
            except Exception:
                pass
            if _solo_recepcion and i != 0 and not (i == 1 and _puede_traspasos):
                btn.setVisible(False)
                continue
            side_ly.addWidget(btn)

        side_ly.addStretch()

        # Botón salir
        self.btn_sidebar_exit_widget = SidebarButton(tr("recep.exit", default="SALIR").upper())
        self.btn_sidebar_exit_widget.setObjectName("btn_sidebar_exit")
        self.btn_sidebar_exit_widget.setFixedHeight(55)
        self.btn_sidebar_exit_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sidebar_exit_widget.clicked.connect(self.ejecutar_volver)
        try:
            self.btn_sidebar_exit_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        except Exception:
            pass
        side_ly.addWidget(self.btn_sidebar_exit_widget)

        self.main_layout.addWidget(self.sidebar)

        # --- ÁREA DE CONTENIDO (QStackedWidget) — 7 páginas enterprise ---
        # Lazy load: construir las 7 sub-páginas en el __init__ hacía la apertura
        # lenta (~850 ms; cada página hace consultas y construye UI pesada). Ahora
        # solo se construye la inicial (RECEPCIÓN, ligera); el resto se crean la
        # primera vez que se visitan.
        self.vistas = QStackedWidget()
        self.vistas.setObjectName("contenido_logistica")

        self.vista_landing_scanner = LandingScannerPage()                       # 0 RECEPCIÓN (eager)
        self.vistas.addWidget(self.vista_landing_scanner)

        self._vista_factories = {
            1: lambda: TraspasoStockPage(usuario=self.usuario, codigo_local=self.codigo_local),
            2: lambda: PreparacionPage(usuario=self.usuario, codigo_local=self.codigo_local),
            3: lambda: ExpedicionesPage(usuario=self.usuario, codigo_local=self.codigo_local),
            4: lambda: IncidenciasPage(usuario=self.usuario, codigo_local=self.codigo_local),
            5: lambda: HistorialUnificadoPage(usuario=self.usuario, codigo_local=self.codigo_local),
            6: lambda: CrossDockingPage(usuario=self.usuario, codigo_local=self.codigo_local),
        }
        self._vista_attr = {
            1: "vista_traspaso", 2: "vista_preparacion", 3: "vista_expediciones",
            4: "vista_incidencias", 5: "vista_historial", 6: "vista_xdock",
        }
        self._vista_built = {0: True}
        # Placeholders (y atributos a None) para las sub-páginas restantes (1..6).
        for i in range(1, 7):
            setattr(self, self._vista_attr[i], None)
            self.vistas.addWidget(QWidget())

        self.main_layout.addWidget(self.vistas)

    def _ensure_vista(self, index):
        """Construye la sub-página `index` la primera vez que se visita."""
        if self._vista_built.get(index):
            return
        factory = self._vista_factories.get(index)
        if factory is None:
            return
        page = factory()
        old = self.vistas.widget(index)
        self.vistas.insertWidget(index, page)
        self.vistas.removeWidget(old)
        old.deleteLater()
        setattr(self, self._vista_attr[index], page)
        self._vista_built[index] = True
        self._wire_vista(index, page)

    def _wire_vista(self, index, page):
        """Conecta las señales propias de cada sub-página al construirla (lazy)."""
        if index == 1 and hasattr(page, "btn_lanzar_dialogo"):
            try:
                page.btn_lanzar_dialogo.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            page.btn_lanzar_dialogo.clicked.connect(self.abrir_dialogo_traspaso_final)

    def crear_boton_nav(self, txt, active=False):
        """Crea botones de sidebar ocupando todo el ancho usando el estilo global."""
        btn = SidebarButton(txt.upper())
        btn.setObjectName("btn_sidebar")
        btn.setFixedHeight(55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setChecked(bool(active))
        btn.setAutoExclusive(True)
        btn.setFlat(True)

        try:
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.setMouseTracking(True)
        except Exception:
            pass

        try:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        try:
            btn.setMinimumWidth(0)
        except Exception:
            pass

        try:
            from assets.estilo_global import aplicar_estilo_widget

            aplicar_estilo_widget(btn)
        except Exception:
            pass

        return btn

    def conectar_eventos_paginas(self):
        """
        Conecta clics de botones y eventos de las sub-páginas y diálogos.
        Implementa desconexión de seguridad para evitar duplicidad de ventanas.
        """
        # 1. Botones de la Sidebar — 7 pestañas enterprise
        self.btn_nav_scan.clicked.connect(
            lambda: self.cambiar_vista(0, self.btn_nav_scan)
        )
        self.btn_nav_traspasar.clicked.connect(
            lambda: self.cambiar_vista(1, self.btn_nav_traspasar)
        )
        self.btn_nav_prep.clicked.connect(
            lambda: self.cambiar_vista(2, self.btn_nav_prep)
        )
        self.btn_nav_expedir.clicked.connect(
            lambda: self.cambiar_vista(3, self.btn_nav_expedir)
        )
        self.btn_nav_incid.clicked.connect(
            lambda: self.cambiar_vista(4, self.btn_nav_incid)
        )
        self.btn_nav_historial.clicked.connect(
            lambda: self.cambiar_vista(5, self.btn_nav_historial)
        )
        self.btn_nav_xdock.clicked.connect(
            lambda: self.cambiar_vista(6, self.btn_nav_xdock)
        )

        # 2. Acción del botón central de la Landing Page
        if hasattr(self.vista_landing_scanner, "btn_iniciar"):
            try:
                self.vista_landing_scanner.btn_iniciar.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.vista_landing_scanner.btn_iniciar.clicked.connect(
                self.abrir_escaner_recepcion
            )

        # 3. PUENTE CRÍTICO ("Ventana Doble"): la página de Traspasos ahora se
        # construye de forma diferida (lazy), así que su señal btn_lanzar_dialogo
        # se conecta en _wire_vista(1) cuando la página se crea por primera vez.

    def abrir_dialogo_traspaso_final(self):
        """Lanza el TraspasoDialog de forma modal, controlada y sin duplicidad."""

        # 1. Seguro de reentrada: Evita abrir si ya hay uno intentando abrirse
        if hasattr(self, "_bloqueo_dialogo") and self._bloqueo_dialogo:
            return

        self._bloqueo_dialogo = True

        try:
            # 2. Instanciamos el diálogo
            dialogo = TraspasoDialog(parent=self, tienda_id=self.codigo_local)

            # 3. Ejecución modal (bloquea el resto de la app), con la MISMA animación de
            # deslizamiento que el resto de ventanas a pantalla completa.
            from src.gui.transiciones import abrir_dialogo_deslizante
            resultado = abrir_dialogo_deslizante(dialogo, self)

            # 4. Al cerrar, evaluamos el resultado
            if resultado:
                # Si el diálogo terminó en éxito, refrescamos el historial (solo
                # si ya se ha construido — es lazy).
                hist = getattr(self, "vista_historial", None)
                if hist is not None and hasattr(hist, "cargar_datos"):
                    hist.cargar_datos()

            # 5. Limpieza explícita del objeto en memoria
            dialogo.deleteLater()

        except Exception as e:
            import logging

            logging.error(f"Error al abrir el diálogo de traspaso: {e}")

        finally:
            # 6. Liberamos el bloqueo siempre, pase lo que pase
            self._bloqueo_dialogo = False

    def abrir_escaner_recepcion(self):
        """Lanza el escaneo remoto (móvil) para iniciar la recepción. Flujo obligatorio: ALBARÁN
        completo primero — ya no se admite escanear un palé (o un bulto) directamente aquí, para
        garantizar que el operario siempre vea antes la lista completa de palés del pedido."""
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(
            self, on_result=self._procesar_codigo_inicial_escaneado, contexto="recepcion.escaner_recepcion")

    def _procesar_codigo_inicial_escaneado(self, codigo):
        """Clasifica el PRIMER código escaneado del flujo de recepción (`db.logistica.
        resolver_codigo_escaneado`) y exige que sea el ALBARÁN completo — escanear directamente un
        palé o un bulto en este punto se rechaza con un mensaje claro en vez de procesarse."""
        from src.db.logistica import resolver_codigo_escaneado
        info = resolver_codigo_escaneado(codigo)
        tipo = info.get("tipo")
        if tipo == "DOCUMENTO":
            self._abrir_seleccion_pale(info["documento"]["id_documento"])
        elif tipo == "PALE":
            _mensaje_ui(self, "Escanea primero el albarán",
                       "Antes de escanear un palé, escanea el código del ALBARÁN completo del pedido.",
                       "warning")
        elif tipo == "BULTO":
            _mensaje_ui(self, "Código no esperado aquí",
                       "Este es el código de un bulto. Escanea primero el albarán y elige su palé.",
                       "warning")
        else:
            _mensaje_ui(self, "No Encontrado", "CÓDIGO NO RECONOCIDO", "warning")

    def _abrir_seleccion_pale(self, id_documento):
        """Segundo paso: el albarán se cargó con TODOS sus palés — el operario elige uno y debe
        escanearlo físicamente para confirmarlo (`_SeleccionarPaleDialog`)."""
        from src.db.logistica import obtener_documento_con_pales
        doc = obtener_documento_con_pales(id_documento)
        if not doc or not doc.get("pales"):
            _mensaje_ui(self, "Sin palés", "Este albarán no tiene palés registrados.", "warning")
            return
        dlg = _SeleccionarPaleDialog(doc, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.id_pale_confirmado:
            self._pale_confirmado(dlg.id_pale_confirmado)

    def _pale_confirmado(self, id_pale):
        """Tercer paso: palé confirmado por escaneo. Un pedido B2B (palé sintético único, sin
        concepto de bultos por diseño — ver `registrar_documento_b2b`) se recepciona SIEMPRE entero;
        un traspaso interno pregunta "¿Desea revisar los bultos?" antes de decidir cómo."""
        from src.db.logistica import obtener_tipo_documento_por_pale
        info_doc = obtener_tipo_documento_por_pale(id_pale)
        if not info_doc:
            _mensaje_ui(self, "No Encontrado", "PALÉ SIN STOCK O NO EXISTE", "warning")
            return

        if str(info_doc.get("tipo_documento") or "").upper() == "B2B":
            self._procesar_documento_b2b_escaneado(id_pale, info_doc)
            return

        from assets.estilo_global import SmartMessageDialog, mostrar_mensaje
        resultado = mostrar_mensaje(
            self, "¿Desea revisar los bultos?",
            "Puedes recepcionar este palé entero de una vez, o revisarlo bulto a bulto.",
            nivel="question",
            botones=[("yes", "Sí, revisar"), ("no", "No, recepcionar todo el palé")])
        if resultado == SmartMessageDialog.ROLE_TO_RESULT["yes"]:
            self._iniciar_revision_bultos(id_pale)
        else:
            self._recepcionar_pale_completo_traspaso(id_pale)

    def _iniciar_revision_bultos(self, id_pale):
        """Si el palé todavía no tiene bultos declarados, pide cuántos lo componen y los genera
        (reparto proporcional, editable al confirmar cada uno); si ya los tiene (se dejó a medias en
        una sesión anterior), continúa directamente desde donde se quedó."""
        from PyQt6.QtWidgets import QInputDialog
        from src.db.logistica import generar_bultos_para_pale, obtener_bultos_pale
        if not obtener_bultos_pale(id_pale):
            numero, ok = QInputDialog.getInt(
                self, "Número de bultos", "¿Cuántos bultos componen este palé?", 1, 1, 200, 1)
            if not ok:
                return
            res = generar_bultos_para_pale(id_pale, numero)
            if not res.get("ok"):
                _mensaje_ui(self, "Error", res.get("motivo") or "No se pudieron generar los bultos.", "error")
                return
        dlg = _ListaBultosPaleDialog(id_pale, self.codigo_local, self._nombre_usuario_actual(), parent=self)
        completado = dlg.exec() == QDialog.DialogCode.Accepted
        if completado:
            self.cambiar_vista(5, self.btn_nav_historial)

    def _recepcionar_pale_completo_traspaso(self, id_pale):
        """Recepción de TODO el palé de una vez (comportamiento de siempre, extraído de la antigua
        `_procesar_pale_escaneado_movil` para poder invocarse también tras elegir "No" en "¿Desea
        revisar los bultos?")."""
        from src.db.logistica import obtener_items_pale_traspaso
        try:
            items_recuperados = obtener_items_pale_traspaso(id_pale)
        except Exception as e:
            logger.error(f"Error consultando documentos_logisticos_lineas para {id_pale}: {e}")
            _mensaje_ui(self, "Error de Base de Datos", f"Fallo crítico: {e}", "error")
            return

        if not items_recuperados:
            _mensaje_ui(self, "No Encontrado", "PALÉ SIN STOCK O NO EXISTE", "warning")
            return

        # Punto 3 (INV.3/FEFO): revisión de lote/caducidad antes de confirmar — obligatorio para
        # artículos con `articulos.requiere_lote=1`, opcional para el resto (mismo espíritu que el
        # formulario de Recepciones del Portal Empresa). Alimenta el gancho best-effort que YA existe
        # en `db.logistica.procesar_recepcion_logistica` (origen="recepcion").
        #
        # Cross-Docking (Fase D): se consulta la demanda de salida pendiente ANTES de confirmar (las
        # líneas del documento ya se conocen aquí, la recepción todavía no se ha comprometido) para
        # que el diálogo pueda ofrecer el aviso — puramente informativo/opcional (ver
        # `_RevisionLotesRecepcionDialog`).
        demanda = self._demanda_cross_docking(items_recuperados)
        dlg = _RevisionLotesRecepcionDialog(items_recuperados, parent=self, demanda=demanda)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.resultado is None:
            return

        if self.procesar_confirmacion_recepcion(id_pale, dlg.resultado):
            self._ejecutar_cross_docking_seleccionado(dlg.cross_dock_seleccionado,
                                                       codigo_local=self.codigo_local)

    def _nombre_usuario_actual(self) -> str:
        """Nombre de usuario legible para trazabilidad (actor/usuario_receptor). `self.usuario` es el
        diccionario de sesión completo (`sesion_global.usuario_actual`), no un texto plano — evita
        guardar el `repr()` del diccionario en columnas VARCHAR de trazabilidad."""
        u = self.usuario
        if isinstance(u, dict):
            return str(u.get("nombre_usuario") or u.get("usuario") or u.get("nombre") or "Usuario")
        return str(u or "Usuario")

    def _procesar_documento_b2b_escaneado(self, id_pale, info_doc):
        """Rama B2B de la recepción unificada (Punto de rediseño): el documento escaneado es el
        albarán de un pedido B2B (`db.logistica.registrar_documento_b2b`) — las líneas a revisar
        vienen de `transaccion_lineas` (con el lote/caducidad YA declarado por el proveedor, Punto 3
        bis), no de `documentos_logisticos_lineas`. El COMMIT final, más abajo, delega en el motor
        oficial de Smart Suppliers (`b2b_pedidos.recibir_mercancia`) — nunca en
        `procesar_recepcion_logistica` (motor de stock de traspasos internos)."""
        id_tx = info_doc.get("id_tx")
        from src.services.comercio_digital import transacciones as TX
        from src.db.empresa import empresa_actual_id
        id_empresa_activa = empresa_actual_id()
        tx = TX.obtener(id_tx, id_empresa=id_empresa_activa)
        if not tx or not tx.get("lineas"):
            _mensaje_ui(self, "No Encontrado", "El pedido B2B de este documento no existe o no "
                       "pertenece a esta empresa.", "warning")
            return
        if tx.get("stock_recibido_en"):
            _mensaje_ui(self, "Pedido ya recibido",
                       "Este pedido B2B ya había sido recibido anteriormente.", "warning")
            return

        items_recuperados = [{
            "id": ln.get("id"), "codigo": ln.get("codigo_articulo"), "nombre": ln.get("nombre"),
            "cantidad": ln.get("cantidad"), "lote": ln.get("lote"),
            "fecha_caducidad": ln.get("fecha_caducidad"),
        } for ln in tx["lineas"]]

        # Cross-Docking (Fase D): mismo punto de enganche que la vía de traspaso interno — las líneas
        # del documento ya se conocen, la recepción B2B todavía no se ha comprometido.
        demanda = self._demanda_cross_docking(items_recuperados)
        dlg = _RevisionLotesRecepcionDialog(items_recuperados, parent=self, es_b2b=True, demanda=demanda)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.resultado is None:
            return

        # Guardia de destino: `recibir_mercancia` da de alta el stock en el almacén de la tienda del
        # PEDIDO (`transaccion_comercial.id_tienda_destino`), sin conocer desde qué centro escanea el
        # operario — se replica aquí la misma protección "destino_incorrecto" que ya tiene
        # `procesar_recepcion_logistica` para los traspasos, para no recibir en el centro equivocado.
        destino_doc = str(info_doc.get("destino") or "").upper().strip()
        if destino_doc and destino_doc != str(self.codigo_local or "").upper().strip():
            _mensaje_ui(self, "Destino Incorrecto",
                       f"Este pedido B2B está destinado a {info_doc.get('destino')}. "
                       f"No puede recibirlo en {self.codigo_local}.", "error")
            return

        lineas_override = {}
        for item in dlg.resultado:
            id_linea = item.get("id")
            if id_linea is None:
                continue
            lote = item.get("lote")
            caducidad = item.get("caducidad")
            if lote or caducidad:
                lineas_override[str(id_linea)] = {"lote": lote, "fecha_caducidad": caducidad}

        from src.services.compras import b2b_pedidos
        actor = self._nombre_usuario_actual()
        res = b2b_pedidos.recibir_mercancia(
            id_tx, actor=actor, id_empresa=id_empresa_activa, lineas_override=lineas_override)

        if not res.get("ok"):
            _mensaje_ui(self, "Error", f"No se pudo procesar la recepción: {res.get('error')}", "error")
            return

        from src.db.logistica import marcar_documento_b2b_recibido
        marcar_documento_b2b_recibido(info_doc["id_documento"], actor)

        if res.get("idempotente"):
            _mensaje_ui(self, "Pedido ya recibido",
                       "Este pedido B2B ya había sido recibido anteriormente.", "warning")
        else:
            # Cross-Docking (Fase D): el almacén de recepción es el que `recibir_mercancia` acaba de
            # usar de verdad (`res["id_almacen"]`) — no hace falta resolverlo de nuevo desde
            # `codigo_local`, y así se evita cualquier discrepancia entre ambos.
            self._ejecutar_cross_docking_seleccionado(dlg.cross_dock_seleccionado,
                                                       almacen_recepcion=res.get("id_almacen"))
            _mensaje_ui(self, "Recepción Exitosa",
                       f"Pedido B2B recibido. Stock actualizado: {res.get('lineas', 0)} línea(s).",
                       "success")

        self.cambiar_vista(5, self.btn_nav_historial)

    def cambiar_vista(self, index, boton_activo):
        """
        Gestiona el cambio de página en el QStackedWidget y
        actualiza visualmente el botón seleccionado con feedback inmediato.
        """
        # Acceso restringido: OPERARIO solo puede ver Recepción (índice 0), salvo Traspasos (índice 1)
        # si tiene concedido el permiso `logistica.traspasos` (RBAC, ver constructor).
        if index != 0 and str((self.usuario or {}).get("perfil", "")).upper() == "OPERARIO":
            from src.services import autorizacion
            if not (index == 1 and autorizacion.puede(self.usuario, "logistica.traspasos")):
                return
        # 1. Construir la sub-página si aún no existe (lazy) y cambiar el índice
        self._ensure_vista(index)
        self.vistas.setCurrentIndex(index)

        # 2. Resetear el estado checked de todos los botones (delegar estilo al CSS global)
        for btn in self.lista_botones_nav:
            try:
                btn.setChecked(False)
            except Exception:
                pass

        # 3. Marcar el botón activo para que el selector CSS `:checked` lo pinte
        try:
            boton_activo.setChecked(True)
        except Exception:
            pass

        # 4. Refresco automático y Gestión de estado "En blanco"
        pagina_actual = self.vistas.currentWidget()

        if hasattr(pagina_actual, "cargar_datos"):
            # Si la página tiene buscador, limpiamos el filtro para mostrar todo al entrar
            if hasattr(pagina_actual, "input_busqueda"):
                pagina_actual.input_busqueda.clear()

            # Forzamos la carga de datos
            pagina_actual.cargar_datos()

        # 5. Foco automático: Si es la página de traspaso o scanner, ponemos el foco en el input
        # para que el usuario pueda empezar a disparar con el lector láser de inmediato.
        if hasattr(pagina_actual, "input_codigo_manual"):
            pagina_actual.input_codigo_manual.setFocus()

    def ejecutar_volver(self):
        """Regresa al menú principal despertando la ventana anterior y limpiando la actual."""
        try:
            # Buscamos la ruta de retorno
            callback = getattr(self, "callback_vuelta", None)

            if callback:
                # 1. Ocultamos primero para dar sensación de velocidad
                self.hide()

                # 2. Ejecutamos el retorno al padre (MenuPrincipal.mostrar_menu_principal)
                callback()

                # 3. Forzamos limpieza de la cola de eventos para evitar el WARNING de navegación

                QApplication.processEvents()

                # 4. Cerramos definitivamente (el callback puede haber eliminado ya esta ventana del stack
                #    → el objeto C++ estaría destruido; el cierre es seguro).
                self._cerrar_seguro()
            else:
                logger.warning(
                    "Navegación: No se detectó callback_vuelta. Forzando cierre seguro."
                )
                self._cerrar_seguro()

        except RuntimeError:
            # La ventana ya fue destruida por el callback (retorno normal por stack): nada más que cerrar.
            pass
        except Exception as e:
            logger.error(f"Error crítico en navegación de retorno: {e}")
            self._cerrar_seguro()

    def _cerrar_seguro(self):
        """Cierra la ventana sin fallar si el objeto C++ ya fue destruido (RuntimeError de SIP)."""
        try:
            self.close()
        except RuntimeError:
            pass

    def procesar_confirmacion_recepcion(self, id_pale_escaneado, items_a_recibir):
        """
        Procesa la entrada de mercancía de un palé escaneado delegando en el MOTOR OFICIAL de
        recepción (`db.logistica.procesar_recepcion_logistica`): recepción transaccional con alta de
        stock, kárdex `ENTRADA_TRASPASO`, líneas, registro de recepción, incidencias e idempotencia.

        FIX de bug real (cliente fino, Fase 3): esta pantalla tenía una copia INLINE y ROTA de la
        recepción — por una indentación incorrecta, el alta de stock quedaba como código muerto tras un
        `continue`, así que la recepción NUNCA sumaba stock y TODO artículo salía como "no encontrado".
        Se elimina ese motor paralelo y se reutiliza el oficial (N7). La GUI SOLO orquesta el resultado.
        """
        if not id_pale_escaneado or not items_a_recibir:
            _mensaje_ui(self, "Error", "No hay datos válidos para recibir.", "warning")
            return

        # Validación básica del formato de etiqueta (PAL-SIGLA-ORIGEN-SEC-DESTINO). El motor localiza el
        # palé por su id en documentos_logisticos_pales (no hace falta reconstruir el documento maestro).
        if len(id_pale_escaneado.split("-")) < 5:
            _mensaje_ui(self, "Error", "Formato de etiqueta de palé no reconocido.", "error")
            return

        from src.db.logistica import procesar_recepcion_logistica
        try:
            res = procesar_recepcion_logistica(
                id_pale_escaneado, self.codigo_local, self.usuario, items_a_recibir
            )
        except Exception as e:
            _mensaje_ui(self, "Error de Base de Datos", f"Fallo crítico: {e}", "error")
            return

        if not res.get("ok"):
            motivo = res.get("motivo")
            if motivo == "destino_incorrecto":
                _mensaje_ui(self, "Destino Incorrecto",
                            f"Este palé está destinado a {res.get('destino')}. No puede recibirlo en {self.codigo_local}.",
                            "error")
            elif motivo == "pale_ya_recibido":
                _mensaje_ui(self, "Palé ya recibido",
                            "Este palé ya había sido recibido anteriormente.", "warning")
            else:
                _mensaje_ui(self, "Error", f"No se pudo procesar la recepción: {motivo}", "error")
            return

        count_actualizados = res.get("count_actualizados", 0)
        articulos_no_encontrados = res.get("articulos_no_encontrados", [])

        # Marcar propuestas activas de los artículos realmente recibidos como RECIBIDO.
        # `items_a_recibir` admite dict (con lote/caducidad, Punto 3) o lista/tupla legacy [cod,nombre,cant]
        # — mismo criterio de aceptación dual que ya usa `procesar_recepcion_logistica`.
        def _cod_item(item):
            return str((item.get("codigo") if isinstance(item, dict) else item[0]) or "").strip().upper()
        no_enc = {str(a.get("ean", "")).upper() for a in articulos_no_encontrados}
        codigos_recibidos = [
            _cod_item(item)
            for item in items_a_recibir
            if _cod_item(item) not in no_enc
            and not any(x in _cod_item(item)
                        for x in ("LOGISTICA", "PALE", "CARTON", "PLASTICO", "VACIO", "BULTO"))
        ]
        if codigos_recibidos:
            _reab_marcar_articulos_recibidos(codigos_recibidos)
            try:
                from src.db.conexion import stock_signals as _db_signals
                _db_signals.propuestas_actualizadas.emit()
            except Exception:
                pass

        # Feedback final. Mensaje de Logística ESPECÍFICO (petición explícita, distinto del
        # mensaje genérico "Este código de artículo no existe en el sistema" que usa el resto de
        # la app): aquí ya se intentó resolver por la tabla de equivalencias de proveedor
        # (`db.equivalencias_proveedor`) antes de llegar a esta lista, así que si sigue apareciendo
        # es una referencia GENUINAMENTE no registrada en ningún sitio.
        resumen = f"Stock actualizado: {count_actualizados} productos."
        if articulos_no_encontrados:
            resumen += (f"\n\nSe detectó un artículo con una referencia no registrada. "
                       f"Por favor, notifíquelo a un superior. "
                       f"({len(articulos_no_encontrados)} referencia(s) sin resolver.)")
        _mensaje_ui(self, "Recepción Exitosa", resumen, "success")

        # Si hay artículos nuevos, abrir diálogo de creación rápida.
        if articulos_no_encontrados:
            dialogo = DialogoNuevosArticulos(articulos_no_encontrados, self)
            dialogo.exec()

        # Redirigir automáticamente al Historial (Vista Index 5).
        self.cambiar_vista(5, self.btn_nav_historial)
        return True  # Cross-Docking (Fase D): el llamador solo aplica cross-dock si la recepción fue bien.

    # ── Cross-Docking (Fase D) — helpers compartidos por ambas vías de recepción ──
    def _demanda_cross_docking(self, items) -> dict:
        """Consulta `expediciones.demanda_pendiente_por_articulo` acotada a los códigos de ESTE
        documento escaneado (traspaso interno o B2B). Best-effort: nunca bloquea la recepción."""
        codigos = []
        for item in items or []:
            cod = str((item.get("codigo") if isinstance(item, dict) else item[0]) or "").strip()
            if cod:
                codigos.append(cod)
        if not codigos:
            return {}
        try:
            from src.services import expediciones as EXP
            from src.db.empresa import empresa_actual_id
            return EXP.demanda_pendiente_por_articulo(empresa_actual_id(), codigos=codigos)
        except Exception as e:
            logger.warning("_demanda_cross_docking: %s", e)
            return {}

    def _ejecutar_cross_docking_seleccionado(self, seleccion, almacen_recepcion=None,
                                             codigo_local=None) -> None:
        """Ejecuta `expediciones.aplicar_cross_docking` para cada artículo que el usuario marcó en el
        banner del diálogo de revisión (`_RevisionLotesRecepcionDialog.cross_dock_seleccionado`). Se
        invoca DESPUÉS de confirmar la recepción normal (el stock cross-dockeado sale del almacén de
        recepción, que solo tiene existencias reales una vez la recepción está comprometida). Nunca
        bloquea ni revierte la recepción ya confirmada si un cross-dock puntual falla — solo informa."""
        if not seleccion:
            return
        try:
            from src.services import expediciones as EXP
            from src.db.empresa import empresa_actual_id
        except Exception as e:
            logger.warning("_ejecutar_cross_docking_seleccionado: %s", e)
            return
        id_empresa = empresa_actual_id()
        if almacen_recepcion is None and codigo_local is not None:
            try:
                from src.db import stock_almacen as SA
                # `almacen_de_codigo_centro` ya resuelve exactamente este código de centro (tienda O
                # almacén no-tienda) — se reutiliza en vez de duplicar esa lógica; central como
                # último fallback si el código no resuelve a nada (nunca se inventa un almacén).
                almacen_recepcion = (SA.almacen_de_codigo_centro(codigo_local, id_empresa)
                                     or SA.almacen_central(id_empresa))
            except Exception as e:
                logger.warning("_ejecutar_cross_docking_seleccionado: resolver almacén(%s): %s",
                               codigo_local, e)
        if not almacen_recepcion:
            logger.warning("_ejecutar_cross_docking_seleccionado: sin almacén de recepción resuelto")
            return
        actor = self._nombre_usuario_actual()
        aplicados, fallidos = [], []
        for codigo, match in seleccion.items():
            cantidad = int(match.get("cantidad_aplicada") or 0)
            if cantidad <= 0:
                continue
            res = EXP.aplicar_cross_docking(
                codigo, cantidad, match, almacen_recepcion=almacen_recepcion, id_empresa=id_empresa,
                usuario=actor, id_documento=f"XDOCK-{match.get('fuente')}-{match.get('id_pedido_o_tx')}")
            (aplicados if res.get("ok") else fallidos).append((codigo, res))
        if aplicados:
            _mensaje_ui(self, "Cross-Docking aplicado",
                       f"{len(aplicados)} artículo(s) cross-dockeados hacia su pedido de salida.",
                       "success")
        if fallidos:
            detalle = "; ".join(f"{c}: {r.get('error')}" for c, r in fallidos)
            _mensaje_ui(self, "Cross-Docking incompleto",
                       f"No se pudo aplicar para {len(fallidos)} artículo(s): {detalle}", "warning")


# ============================================================
# BLOQUE DIÁLOGOS DE GESTIÓN DE ARTÍCULOS
# ============================================================

class DialogoNuevosArticulos(QDialog):

    def __init__(self, items_nuevos, parent=None):
        """
        items_nuevos: Lista de diccionarios [{'ean':..., 'nombre':..., 'cantidad':...}]
        """
        super().__init__(parent)
        self.items_nuevos = items_nuevos

        self.setWindowTitle(tr("recep.gestion_de_articulos_nuevos", default="Gestión de Artículos Nuevos"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumSize(700, 500)

        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Encabezado informativo con acento neón
        lbl = QLabel(tr("recep.se_han_detectado_codigos_ean", default="⚠️ Se han detectado códigos EAN no registrados"))
        lbl.setObjectName("titulo_cian")
        layout.addWidget(lbl)

        sub_lbl = QLabel(
            tr("recep.los_articulos_listados_a_con", default="Los artículos listados a continuación se darán de alta con stock inicial.")
        )
        sub_lbl.setObjectName("subtitulo_muted")
        layout.addWidget(sub_lbl)

        # Configuración de la Tabla (Estilo Global)
        self.tabla = QTableWidget(len(self.items_nuevos), 3)
        self.tabla.setHorizontalHeaderLabels(
            ["CÓDIGO EAN", "DESCRIPCIÓN SUGERIDA", "CANTIDAD RECIBIDA"]
        )

        # Estética de la tabla (Sincronizada con el resto de módulos)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)  # Estilo más limpio

        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Llenado de datos (Lógica original intacta)
        for i, item in enumerate(self.items_nuevos):
            # EAN
            it_ean = QTableWidgetItem(str(item["ean"]))
            it_ean.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(i, 0, it_ean)

            # NOMBRE
            it_nombre = QTableWidgetItem(str(item["nombre"]))
            self.tabla.setItem(i, 1, it_nombre)

            # CANTIDAD
            it_cant = QTableWidgetItem(str(item["cantidad"]))
            it_cant.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(i, 2, it_cant)

        layout.addWidget(self.tabla)

        # Botonera
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(15)

        self.btn_cancelar = QPushButton(tr("recep.cancelar_registro", default="❌ Cancelar Registro"))
        self.btn_cancelar.setObjectName("btn_peligro")
        self.btn_cancelar.setFixedHeight(45)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)

        self.btn_confirmar = QPushButton(tr("recep.registrar_y_finalizar", default="✅ Registrar y Finalizar"))
        self.btn_confirmar.setObjectName("btn_primario")
        self.btn_confirmar.setFixedHeight(45)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.clicked.connect(self.procesar_altas_db)

        btns_layout.addWidget(self.btn_cancelar)
        btns_layout.addWidget(self.btn_confirmar)
        layout.addLayout(btns_layout)

    def procesar_altas_db(self):
        """Inserta los artículos nuevos en la base de datos."""
        exitos = 0
        try:

            with obtener_conexion() as conn:
                cursor = conn.cursor()
                for item in self.items_nuevos:
                    # Insertamos en la tabla maestra 'articulos'
                    # Se asume que precio=0.0 y estado='activo' para nuevos registros logísticos
                    cursor.execute(
                        """
                        INSERT INTO articulos (codigo, nombre, stock_total, stock_tienda, precio, estado)
                        VALUES (?, ?, ?, ?, 0.0, 'activo')
                        """,
                        (
                            item["ean"],
                            item["nombre"],
                            item["cantidad"],
                            item["cantidad"],
                        ),
                    )
                    exitos += 1
                conn.commit()

            _mensaje_ui(
                self,
                "Éxito",
                f"Se han registrado {exitos} nuevos productos correctamente.",
                "success",
            )
            self.accept()

        except Exception as e:
            _mensaje_ui(
                self, "Error", f"No se pudieron registrar los artículos: {str(e)}", "error"
            )


# ============================================================
# BLOQUE DIÁLOGO DE TRASPASO
# ============================================================


class _PesoDialog(QDialog):
    """Diálogo frameless para capturar el peso de un bulto (texto libre)."""

    def __init__(self, titulo: str, texto: str, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumWidth(400)
        self._drag_pos = None
        self._valor: str = ""
        self._build_ui(titulo, texto)

    def _build_ui(self, titulo, texto):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)

        lbl_titulo = QLabel(titulo.upper())
        lbl_titulo.setObjectName("titulo_cian")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_titulo)

        lbl_texto = QLabel(texto)
        lbl_texto.setWordWrap(True)
        ly.addWidget(lbl_texto)

        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("recep.ej_18_5", default="Ej: 18.5"))
        self.input.setFixedHeight(46)
        self.input.returnPressed.connect(self._aceptar)
        ly.addWidget(self.input)

        h = QHBoxLayout()
        h.setSpacing(12)
        btn_skip = QPushButton(tr("recep.dejar_pendiente", default="DEJAR PENDIENTE"))
        btn_skip.setObjectName("btn_secundario")
        btn_skip.setFixedHeight(44)
        btn_skip.clicked.connect(self.accept)
        btn_ok = QPushButton(tr("recep.guardar_peso", default="GUARDAR PESO"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(44)
        btn_ok.clicked.connect(self._aceptar)
        h.addWidget(btn_skip)
        h.addWidget(btn_ok)
        ly.addLayout(h)

    def _aceptar(self):
        self._valor = self.input.text().strip()
        self.accept()

    def get_value(self) -> str:
        return self._valor

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _EntradaCantidadDialog(QDialog):
    """Frameless quantity-input dialog replacing QInputDialog.getInt."""

    def __init__(self, titulo, texto, valor_min=1, valor_max=9999, valor_defecto=1, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumWidth(380)
        self._drag_pos = None
        self._valor = valor_defecto
        self._build_ui(titulo, texto, valor_min, valor_max, valor_defecto)

    def _build_ui(self, titulo, texto, valor_min, valor_max, valor_defecto):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)

        lbl_titulo = QLabel(titulo.upper())
        lbl_titulo.setObjectName("titulo_cian")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_titulo)

        lbl_texto = QLabel(texto)
        lbl_texto.setWordWrap(True)
        ly.addWidget(lbl_texto)

        self.spin = QSpinBox()
        self.spin.setRange(valor_min, valor_max)
        self.spin.setValue(valor_defecto)
        self.spin.setFixedHeight(46)
        ly.addWidget(self.spin)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btn_cancel = QPushButton(tr("recep.cancelar_4", default="CANCELAR"))
        btn_cancel.setObjectName("btn_secundario")
        btn_cancel.setFixedHeight(44)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("recep.aceptar_2", default="ACEPTAR"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(44)
        btn_ok.clicked.connect(self._aceptar)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        ly.addLayout(btns)

    def _aceptar(self):
        self._valor = self.spin.value()
        self.accept()

    def get_value(self):
        return self._valor

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class TraspasoDialog(QDialog):

    def __init__(
        self,
        usuario=None,
        tipo: str = "enviar",
        codigo_local="ALMC",
        payload_items: list[dict] | None = None,
        pale_codigo: str | None = None,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent)

        # 1. ATRIBUTOS DE SESIÓN Y ESTADO (Punto 3: Normalización)
        self.usuario = usuario
        self.nombre_usuario = usuario
        # Si recibimos 'tienda_id' vía kwargs, lo priorizamos sobre codigo_local
        self.codigo_local = kwargs.get("tienda_id", codigo_local)
        self.tipo = tipo
        self.payload_items = payload_items or []
        self.pale_codigo = pale_codigo

        # 2. TRABAJO EN SEGUNDO PLANO
        try:
            self.pdf_worker = PdfWorker()
        except Exception:
            self.pdf_worker = None

        # 3. CONFIGURACIÓN DE VENTANA (Look PDA)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Esta ventana ocupa toda la geometría del padre (ver más abajo, "AJUSTE DE GEOMETRÍA
        # SEGURO") — sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`,
        # estilo_global.py).
        self.setObjectName("dlg_traspaso")
        self.setStyleSheet("#dlg_traspaso { border: none; }")

        # 4. VARIABLES DE FLUJO
        self.origen_final = ""
        self.destino_final = ""
        self.agencia_final = ""
        self.observaciones_final = ""
        self.items_widgets: list[dict] = []
        self.peso_bulto = {}
        self.lista_pales_final = []

        self.opciones_especiales = [
            "PALÉ VACÍO (LOGÍSTICO)",
            "PALÉ REMONTADO",
            "PALÉ CARTÓN",
            "PALÉ PLÁSTICO",
            "JAULA METÁLICA (JAU)",
            "CONTENEDOR METÁLICO",
        ]

        # 5. CONFIGURACIÓN DE SEDE (Punto 5: Imports movidos a cabecera en el archivo final)
        try:

            config = obtener_configuracion()
            tienda_cfg = (
                self.codigo_local
                if self.codigo_local
                else config.get("tienda_codigo", "ALMC")
            )
            self.tienda_id_formateado = formatear_nombre_centro(str(tienda_cfg))
            self.tienda_codigo = str(tienda_cfg)
        except Exception:
            self.tienda_id_formateado = "ALMACÉN CENTRAL"
            self.tienda_codigo = "ALMC"

        # 6. INICIALIZAR INTERFAZ
        self.setup_ui()

        # AJUSTE DE GEOMETRÍA SEGURO
        if parent:
            self.setGeometry(parent.geometry())
        else:
            self.setMinimumSize(1200, 800)

        # 7. CARGA DE ITEMS PREVIOS
        if self.payload_items:
            for item in self.payload_items:
                if hasattr(self, "procesar_insercion_item"):
                    self.procesar_insercion_item(
                        item.get("codigo"),
                        item.get("cantidad", 1),
                        es_logistico=False,
                    )

    def setup_ui(self):
        """Configura la interfaz de Salida Logística con estética GitHub Dark."""
        # Contenedor principal para permitir bordes redondeados en Frameless
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("panel_dialogo_logistico")

        main_layout_container = QVBoxLayout(self)
        main_layout_container.setContentsMargins(0, 0, 0, 0)
        main_layout_container.addWidget(self.main_frame)

        layout_principal = QVBoxLayout(self.main_frame)
        layout_principal.setContentsMargins(30, 30, 30, 30)
        layout_principal.setSpacing(20)

        # --- CABECERA ---
        header = QHBoxLayout()
        lbl_titulo = QLabel(tr("recep.salida_logistica", default="SALIDA LOGÍSTICA"))
        lbl_titulo.setObjectName("titulo_cian")

        self.btn_back = QPushButton("✕")
        self.btn_back.setObjectName("btn_icono_peligro")
        self.btn_back.setFixedSize(40, 40)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setProperty("sin_glow", True)
        if _blindar_tamano_fijo is not None:
            _blindar_tamano_fijo(self.btn_back, 40, 40)
        self.btn_back.clicked.connect(self.ejecutar_volver)

        header.addWidget(lbl_titulo)
        header.addStretch()
        header.addWidget(self.btn_back)
        layout_principal.addLayout(header)

        # --- SECCIÓN DE ENTRADA ---
        input_group = QVBoxLayout()
        lbl_origen_info = QLabel(f"ORIGEN: {self.tienda_id_formateado}")
        lbl_origen_info.setObjectName("origen_info")

        h_input = QHBoxLayout()
        h_input.setSpacing(10)

        self.input_codigo_manual = QLineEdit()
        self.input_codigo_manual.setObjectName("input_buscador")
        self.input_codigo_manual.setPlaceholderText(
            tr("recep.escanee_ean_o_codigo_de_arti", default="Escanee EAN o Código de Artículo...")
        )
        self.input_codigo_manual.setFixedHeight(55)
        # Sugerencias de artículos: helper compartido, ver gui/components/completer_articulos.py
        self.completer_articulos = instalar_sugerencias_articulo(self.input_codigo_manual)
        self.input_codigo_manual.returnPressed.connect(self.agregar_articulo_manual)

        self.btn_add_manual = QPushButton(tr("recep.anadir_2", default="AÑADIR"))
        self.btn_add_manual.setObjectName("btn_primario")
        self.btn_add_manual.setFixedSize(110, 55)
        self.btn_add_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_manual.clicked.connect(self.agregar_articulo_manual)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=lambda v: (self.input_codigo_manual.setText(v), self.agregar_articulo_manual()),
            contexto="recepcion.traspaso_manual")

        h_input.addWidget(self.input_codigo_manual)
        h_input.addWidget(btn_escaneo_movil)
        h_input.addWidget(self.btn_add_manual)
        input_group.addWidget(lbl_origen_info)
        input_group.addLayout(h_input)
        layout_principal.addLayout(input_group)

        # --- SELECTOR DE PALÉ ---
        h_asignar = QHBoxLayout()
        h_asignar.setSpacing(10)

        _OPCIONES_PALE = [f"PALÉ {i:02d}" for i in range(1, 21)]
        self._opciones_pale = _OPCIONES_PALE

        from src.gui.tpv import _ScrollCombo
        self.global_pale_selector = _ScrollCombo(maxvis=5)
        self.global_pale_selector.addItems(_OPCIONES_PALE)
        # Responsive (P2): ancho flexible, alto táctil (antes fijo 220x46).
        self.global_pale_selector.setMinimumWidth(160)
        self.global_pale_selector.setMaximumWidth(300)
        self.global_pale_selector.setFixedHeight(46)

        lbl_cargar = QLabel(tr("recep.cargar_en", default="CARGAR EN:"))
        lbl_cargar.setObjectName("etiqueta_secundaria")
        lbl_cargar.setStyleSheet("font-size: 12px; font-weight: 900;")

        h_asignar.addWidget(lbl_cargar)
        h_asignar.addWidget(self.global_pale_selector)
        h_asignar.addStretch()
        layout_principal.addLayout(h_asignar)

        # --- ÁREA DE LISTADO ---
        self.scroll_container = QWidget()
        self.scroll_container.setObjectName("scroll_transparente")
        self.scroll_layout = QVBoxLayout(self.scroll_container)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("scroll_transparente")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.scroll_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout_principal.addWidget(scroll)

        # --- BOTÓN DE VALIDACIÓN (Paso 1) ---
        self.btn_confirmar = QPushButton(tr("recep.paso_1_validar_articulos", default="PASO 1: VALIDAR ARTÍCULOS"))
        self.btn_confirmar.setObjectName("btn_secundario")
        self.btn_confirmar.setFixedHeight(65)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.clicked.connect(self.gestionar_confirmacion_final)
        layout_principal.addWidget(self.btn_confirmar)

    def procesar_insercion_item(
        self, codigo, cantidad, nombre=None, stock_max=999, es_logistico=False
    ):
        """
        Procesa la lógica de añadir un ítem.
        Busca duplicados en el palé actual para sumar cantidades o crea una fila nueva.
        """
        codigo_str = str(codigo).strip().upper()
        nombre_str = str(nombre if nombre else codigo).strip()

        # Seguridad: Si el selector no existe o no tiene texto, usamos un valor por defecto
        pale_actual = "PALÉ 01"
        if hasattr(self, "global_pale_selector"):
            pale_actual = self.global_pale_selector.currentText()

        # 1. Verificar si el artículo ya existe en el MISMO palé para sumar cantidad
        for item in self.items_widgets:
            if (
                item["codigo"] == codigo_str
                and item["pale"].currentText() == pale_actual
            ):
                try:
                    cant_int = int(cantidad)
                    nueva_cantidad = item["spinbox"].value() + cant_int
                    item["spinbox"].setValue(min(nueva_cantidad, stock_max))

                    if feedback_frame_item_resaltado is not None:
                        feedback_frame_item_resaltado(item["frame"], 500)

                    self._limpiar_buscador_tras_accion()
                    return
                except ValueError:
                    continue

        # 2. Si es un ítem nuevo, crear la fila visual
        try:
            # Aseguramos que cantidad sea entero antes de pasar a la UI
            cant_final = int(cantidad)

            self._agregar_item_a_layout(
                codigo_str,
                nombre_str,
                stock_max,
                cant_final,
                pale_actual,
                es_logistico,
            )

            # Matamos cualquier rastro de autocompletado fantasma
            self._limpiar_buscador_tras_accion()

        except Exception as e:
            import logging

            logging.error(f"Error al insertar item {codigo_str}: {e}")

            _mensaje_ui(
                self, "Error de Inserción", f"No se pudo añadir el artículo: {e}", "warning"
            )

    def _limpiar_buscador_tras_accion(self):
        """
        Método de soporte para asegurar que el buscador queda limpio tras añadir un artículo.
        El autocompletado se conserva (es una función permanente, no algo a desactivar).
        """
        self.input_codigo_manual.clear()

        # Rompe el foco y lo recupera para resetear el estado del input en el SO
        self.input_codigo_manual.clearFocus()
        self.input_codigo_manual.setFocus()

        # Feedback visual opcional en el placeholder
        self.input_codigo_manual.setPlaceholderText(tr("recep.listo_para_siguiente_escaneo", default="Listo para siguiente escaneo..."))

    def eliminar_widget(self, frame_item, codigo):
        """
        Elimina un artículo de la lista visual y del registro interno.
        Asegura la limpieza de memoria y actualiza el estado del botón principal.
        """
        try:
            # 1. Filtrar la lista interna de control
            # Usamos una lista nueva para evitar problemas de mutación durante la iteración
            self.items_widgets = [
                i for i in self.items_widgets if i["frame"] != frame_item
            ]

            # 2. Borrado físico del widget
            if frame_item:
                frame_item.setParent(None)
                frame_item.deleteLater()

            # 3. Gestión del estado del botón de confirmación
            if not self.items_widgets:
                # Si no hay ítems, el botón vuelve a su estado inicial de "Paso 1"
                self.btn_confirmar.setText(tr("recep.paso_1_validar_articulos_2", default="PASO 1: VALIDAR ARTÍCULOS"))
                self.btn_confirmar.setEnabled(True)
                self.btn_confirmar.setStyleSheet("")
                if aplicar_estilo_widget is not None:
                    aplicar_estilo_widget(self.btn_confirmar)

                # Limpieza de variables de pesaje acumulado
                if hasattr(self, "peso_bulto"):
                    self.peso_bulto = {}

            # 4. Mantenimiento del flujo: Devolver foco al buscador principal
            # Esto es vital para que el usuario pueda seguir escaneando sin tocar la pantalla
            if hasattr(self, "input_codigo_manual"):
                self.input_codigo_manual.setFocus()
                self.input_codigo_manual.selectAll()

        except Exception as e:
            import logging

            logging.error(f"Error al eliminar widget del artículo {codigo}: {e}")

    def solicitar_pesos_pales(self):
        """
        PUNTO 2: Captura de pesos opcionales.
        Si se deja vacío, se asume peso pendiente (None).
        """

        # Identificar bultos únicos (Palés o Jaulas)
        pales_usados = sorted(
            list(
                set(
                    iw["pale"].currentText().strip().upper().replace(" ", "")
                    for iw in self.items_widgets
                    if iw["pale"].currentText().strip()
                )
            )
        )

        self.peso_bulto = {}

        for pale in pales_usados:
            # Personalizamos el mensaje según si es una Jaula o un Palé
            tipo_bulto = "la JAULA" if "JAU" in pale or "JAULA" in pale else "el PALÉ"

            dlg_peso = _PesoDialog(
                f"PESAJE: {pale}",
                f"Peso para {tipo_bulto} {pale}\n(Dejar vacío si no se puede pesar ahora):",
                parent=self,
            )
            dlg_peso.exec()
            peso_str = dlg_peso.get_value()

            if not peso_str:
                self.peso_bulto[pale] = None
            else:
                try:
                    valor = float(peso_str.replace(",", "."))
                    self.peso_bulto[pale] = round(valor, 2)
                except ValueError:
                    _mensaje_ui(
                        self,
                        "Error",
                        f"Formato inválido en {pale}. Se marcará como pendiente.",
                        "warning",
                    )
                    self.peso_bulto[pale] = None
        return True

    def gestionar_confirmacion_final(self):
        """
        Flujo de Cierre:
        1. Selección de Extras (Jaulas/Palés vacíos).
        2. Solicitar Pesos (Opcionales).
        3. Configurar Ruta y Guardar.
        """

        # --- VALIDACIÓN INICIAL ---
        if not self.items_widgets:
            _mensaje_ui(self, "Aviso", "No hay artículos ni bultos en la lista.", "warning")
            return

        # --- PASO 0: SELECCIÓN LOGÍSTICA EXTRA (Puntos 4 y 5) ---
        # Permite añadir Jaulas o Palés vacíos antes de pedir pesos
        self.abrir_seleccion_logistica()

        # --- PASO 1: SOLICITAR PESOS ---
        if not self.solicitar_pesos_pales():
            return

        # --- PASO 2: DIÁLOGO DE CONFIGURACIÓN DE ENVÍO ---
        diag = QDialog(self)
        diag.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        diag.setObjectName("dlg_entrada_cantidad")
        diag.setWindowTitle(tr("recep.finalizar_envio_logistico", default="FINALIZAR ENVÍO LOGÍSTICO"))
        diag.setFixedWidth(480)
        _diag_outer = QVBoxLayout(diag)
        _diag_outer.setContentsMargins(0, 0, 0, 0)
        _diag_frame = QFrame()
        _diag_frame.setObjectName("cuerpo_ventana")
        _diag_outer.addWidget(_diag_frame)

        ly = QVBoxLayout(_diag_frame)
        ly.setSpacing(12)
        ly.setContentsMargins(30, 20, 30, 20)

        # ORIGEN (Solo lectura)
        ly.addWidget(QLabel(tr("recep.centro_origen", default="CENTRO ORIGEN")))
        self.combo_origen_diag = QComboBox()
        nombre_origen = getattr(self, "tienda_id_formateado", "ALMC")
        self.combo_origen_diag.addItem(nombre_origen)
        self.combo_origen_diag.setEnabled(False)
        self.combo_origen_diag.setFixedHeight(40)
        ly.addWidget(self.combo_origen_diag)

        # DESTINO — buscador en tiempo real sobre CUALQUIER centro registrado de la empresa
        # (petición explícita: "barra de búsqueda en tiempo real" / "cualquier centro registrado,
        # independientemente de si es un centro logístico, un almacén secundario, una tienda física
        # u otra sucursal"). `combo_destino_diag` se conserva (editable, mismo origen de datos de
        # siempre) como respaldo honesto si el texto buscado no coincide con ningún centro
        # registrado — el traspaso sigue funcionando igual que antes, solo sin cross-docking
        # automático por falta de `id_centro_destino`.
        ly.addWidget(QLabel(tr("recep.centro_destino", default="CENTRO DESTINO")))
        self.combo_destino_diag = QComboBox()
        self.combo_destino_diag.setEditable(True)
        self.combo_destino_diag.setFixedHeight(40)
        instalar_sugerencias_centro(self.combo_destino_diag.lineEdit())

        try:
            destinos = obtener_destinos_traspaso()
            self.combo_destino_diag.addItems(
                [d for d in destinos if d != nombre_origen]
            )
        except:
            self.combo_destino_diag.addItems(["ALMACEN CENTRAL", "KIK VIC", "KIK TONA"])
        ly.addWidget(self.combo_destino_diag)

        # AGENCIA
        ly.addWidget(QLabel("AGENCIA / TRANSPORTE"))
        self.combo_agencia_diag = QComboBox()
        self.combo_agencia_diag.setEditable(True)
        self.combo_agencia_diag.addItems(["TXERPA LOGÍSTICA", "INTERNO", "DHL", "SEUR"])
        self.combo_agencia_diag.setFixedHeight(40)
        ly.addWidget(self.combo_agencia_diag)

        # OBSERVACIONES
        ly.addWidget(QLabel(tr("recep.observaciones", default="OBSERVACIONES")))
        self.input_obs_diag = QTextEdit()
        self.input_obs_diag.setPlaceholderText(tr("recep.notas_sobre_la_carga", default="Notas sobre la carga..."))
        self.input_obs_diag.setFixedHeight(70)
        ly.addWidget(self.input_obs_diag)

        btn_final = QPushButton(tr("recep.registrar_y_generar_document", default="REGISTRAR Y GENERAR DOCUMENTACIÓN"))
        btn_final.setObjectName("btn_primario")
        btn_final.setFixedHeight(50)
        btn_final.clicked.connect(diag.accept)
        ly.addWidget(btn_final)

        if aplicar_estilo_widget is not None:
            aplicar_estilo_widget(diag)

        # Centrar y habilitar arrastre
        diag.adjustSize()
        _ref = self.window().frameGeometry()
        diag.move(
            _ref.x() + (_ref.width() - diag.width()) // 2,
            _ref.y() + (_ref.height() - diag.height()) // 2,
        )
        _diag_drag: list = [None]

        def _diag_mouse_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                _diag_drag[0] = ev.globalPosition().toPoint() - diag.pos()

        def _diag_mouse_move(ev):
            if ev.buttons() == Qt.MouseButton.LeftButton and _diag_drag[0] is not None:
                diag.move(ev.globalPosition().toPoint() - _diag_drag[0])

        def _diag_mouse_release(ev):
            _diag_drag[0] = None

        diag.mousePressEvent = _diag_mouse_press
        diag.mouseMoveEvent = _diag_mouse_move
        diag.mouseReleaseEvent = _diag_mouse_release

        # --- PROCESAR RESULTADO Y GENERAR PDF ---
        if diag.exec() == QDialog.DialogCode.Accepted:
            self.destino_final = self.combo_destino_diag.currentText().strip().upper()
            # Cross-docking automático (petición explícita): solo se puede evaluar si el texto
            # tecleado coincide EXACTAMENTE con un centro registrado — si no coincide (destino
            # libre, p. ej. una agencia externa), el traspaso sigue su curso normal sin romper nada.
            self.id_centro_destino_final = resolver_id_centro(self.combo_destino_diag.currentText())
            self.agencia_final = self.combo_agencia_diag.currentText().strip().upper()
            self.observaciones_final = self.input_obs_diag.toPlainText().strip()

            if self.confirmar_traspaso():
                try:
                    # Mapeo de items para el Worker
                    items_para_worker = []
                    for iw in self.items_widgets:
                        items_para_worker.append(
                            {
                                "codigo": iw["codigo"],
                                "nombre": iw["nombre"],
                                "cantidad": iw["spinbox"].value(),
                                "pale_codigo": iw["pale"]
                                .currentText()
                                .upper()
                                .replace(" ", ""),
                                "es_logistico": iw.get("es_logistico", False),
                            }
                        )

                    # Lanzar el Worker
                    self.pdf_worker.configurar(
                        pale_items=items_para_worker,
                        origen=nombre_origen,
                        destino=self.destino_final,
                        observaciones=self.observaciones_final,
                        agencia_transporte=self.agencia_final,
                        usuario=getattr(self, "nombre_usuario", "Usuario"),
                        id_traspaso=getattr(self, "ultimo_id_doc", "TRA-ERR"),
                        datos_logisticos={"peso_bulto": self.peso_bulto},
                    )
                    self.pdf_worker.run()

                    # Abrir PDFs automáticamente
                    id_doc = getattr(self, "ultimo_id_doc", "")
                    ruta_alb = os.path.join(
                        os.getcwd(), "documentos", "albaranes", f"ALB_{id_doc}.pdf"
                    )
                    from src.utils import plataforma
                    if os.path.exists(ruta_alb):
                        plataforma.abrir_archivo(ruta_alb)

                    # Abrir etiquetas de palés si se generaron
                    from pathlib import Path as _Path
                    etiq_dir = _Path(os.getcwd()) / "documentos" / "etiquetas_pales"
                    if etiq_dir.exists():
                        etiq_files = sorted(etiq_dir.glob("ETIQ_*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
                        if etiq_files:
                            plataforma.abrir_archivo(str(etiq_files[0]))

                    _mensaje_ui(
                        self, "Éxito", f"Traspaso {id_doc} finalizado.", "success"
                    )
                    self.accept()

                except Exception as e:
                    _mensaje_ui(self, "Error", f"Error al generar documentos: {e}", "error")

    def abrir_seleccion_logistica(self):
        """Muestra el selector de ítems logísticos y los añade al traspaso."""
        dialogo = SelectorLogisticoExtras(self)

        def al_confirmar(nombres: list):
            for nombre_item in nombres:
                match = next(
                    (s for s in self.opciones_especiales if nombre_item in s), nombre_item
                )
                self.procesar_insercion_item(codigo=match, cantidad=1, es_logistico=True)

        dialogo.items_confirmados.connect(al_confirmar)
        dialogo.exec()

    def confirmar_traspaso(self) -> bool:
        """
        Registra el traspaso vía `db.logistica.guardar_traspaso_logistico` (motor oficial,
        transaccional, ya tenant-safe) — antes este método duplicaba el INSERT a mano y, al no crear
        fila en `documentos_logisticos_pales`, dejaba el traspaso sin poder recibirse nunca. El
        documento nace en EN PREPARACION (picking pendiente), no directo en EN TRANSITO.
        """
        try:
            origen = str(getattr(self, "tienda_id_formateado", "ALMC"))
            destino = str(getattr(self, "destino_final", "DEST"))
            user_ref = str(getattr(self, "nombre_usuario", "Usuario"))
            agencia = str(getattr(self, "agencia_final", "PROPIA"))
            obs = str(getattr(self, "observaciones_final", ""))

            info_pales_agrupados = {}
            for iw in self.items_widgets:
                id_v = iw["pale"].currentText().upper().replace(" ", "").strip()
                if id_v not in info_pales_agrupados:
                    peso_p = getattr(self, "peso_bulto", {}).get(id_v)
                    info_pales_agrupados[id_v] = {
                        "id_visual": id_v,
                        "peso": peso_p,
                        "articulos": [],
                    }
                cant = int(iw["spinbox"].value())
                cod = str(iw["codigo"]).strip()
                nom = str(iw["nombre"]).strip()
                info_pales_agrupados[id_v]["articulos"].append(
                    {"codigo": cod, "nombre": nom, "cantidad": cant}
                )

            from src.db.logistica import guardar_traspaso_logistico
            id_centro_destino = getattr(self, "id_centro_destino_final", None)
            resultado = guardar_traspaso_logistico(
                origen, destino, user_ref, agencia, obs, info_pales_agrupados,
                id_centro_destino=id_centro_destino,
            )
            self.ultimo_id_doc = resultado["id_documento"]

            # Cross-docking automático a una ruta de reparto ya abierta hacia el centro destino
            # (petición explícita) — best-effort: si no hay centro resuelto o no hay ruta
            # disponible, el traspaso queda exactamente como antes de esta función.
            if id_centro_destino:
                try:
                    from src.services.logistica import cross_docking_rutas as XD
                    xd = XD.evaluar_cross_docking_automatico(
                        resultado["id_documento"], usuario=user_ref)
                    if xd.get("cross_dockeado"):
                        ruta = xd.get("ruta") or {}
                        _mensaje_ui(
                            self, "Cross-docking automático",
                            f"Mercancía enlazada a la ruta #{ruta.get('id_ruta')} "
                            f"({ruta.get('fecha') or '—'}) — sin pasar por almacén.",
                            "success")
                except Exception as e:
                    logger.warning("confirmar_traspaso cross-docking: %s", e)
            return True

        except Exception as e:
            print(f"CRITICAL DB ERROR: {e}")
            _mensaje_ui(
                self, "Error de Grabación", f"No se pudo guardar: {str(e)}", "error"
            )
            return False


    def agregar_articulo_manual(self):
        """
        PUNTO 1: Filtro de exclusión.
        Evita que el usuario añada palés como productos de traspaso.
        """

        codigo = self.input_codigo_manual.text().strip().upper()
        # Extrae el código del formato "CÓDIGO – NOMBRE" que ofrece el autocompletado.
        if "–" in codigo:
            codigo = codigo.split("–")[0].strip()
        if not codigo:
            return

        self.input_codigo_manual.setAttribute(
            Qt.WidgetAttribute.WA_InputMethodEnabled, False
        )  # Bloquea predicción del SO
        self.input_codigo_manual.clearFocus()  # Rompe el foco actual para resetear el popup
        self.input_codigo_manual.setFocus()  # Devuelve el foco limpio

        try:
            # --- FILTRO DE SEGURIDAD LOGÍSTICA ---
            opciones_log_clean = [
                opt.upper() for opt in getattr(self, "opciones_especiales", [])
            ]

            # Detecta si es un código de transporte (PAL-, JAULA, etc.)
            es_logistico = any(
                opt in codigo for opt in opciones_log_clean
            ) or codigo.startswith("PAL-")

            if es_logistico:
                _mensaje_ui(
                    self,
                    "Uso Incorrecto",
                    f"El código '{codigo}' es un elemento de transporte (Jaula/Palé).\n\n"
                    "Para añadir bultos vacíos, use el botón de 'Validar Artículos' al finalizar.",
                    "warning",
                )
                return

            # --- BÚSQUEDA EN CATÁLOGO COMERCIAL ---
            art = obtener_articulo(codigo)

            if not art:
                _mensaje_ui(
                    self,
                    "No Encontrado",
                    f"El código [{codigo}] no existe en el catálogo comercial.",
                    "error",
                )
                return

            nombre = art.get("descripcion", art.get("nombre", "Artículo"))

            # Buscamos stock en las posibles columnas de la DB
            stock_disp = 0
            for col in ["stock_central", "stock_actual", "Stock_total"]:
                if art.get(col) is not None:
                    stock_disp = int(art[col])
                    break

            # Solicitar cantidad con diálogo personalizado (evita QInputDialog.getInt
            # que causa un bucle de geometría con FramelessWindowHint en Qt/Windows).
            dlg_cant = _EntradaCantidadDialog(
                "Entrada Manual",
                f"Producto: {nombre}\nStock disponible: {stock_disp}\n\nCantidad a traspasar:",
                1, 9999, 1, parent=self,
            )
            if dlg_cant.exec() == QDialog.DialogCode.Accepted:
                self.procesar_insercion_item(
                    codigo, dlg_cant.get_value(), nombre=nombre, es_logistico=False
                )

        except Exception as e:
            print(f"Error al procesar entrada manual: {e}")

        finally:
            # Aseguramos que el campo quede limpio y listo para el siguiente escaneo/búsqueda.
            self.input_codigo_manual.blockSignals(False)
            self.input_codigo_manual.clear()
            self.input_codigo_manual.setFocus()

    def _agregar_item_a_layout(
        self, codigo, nombre, stock_max, value, pale_def, es_logistico
    ):
        """Crea la fila visual con bordes redondeados, sin autocompletado y gestión de eventos limpia."""

        frame = QFrame()
        frame.setObjectName(
            "item_frame_logistico" if es_logistico else "item_frame_articulo"
        )

        ly = QHBoxLayout(frame)
        ly.setContentsMargins(15, 8, 15, 8)

        # 1. Info del Producto
        v_info = QVBoxLayout()
        lbl_cod = QLabel(f"{' [LOG] ' if es_logistico else ''}{codigo}")
        lbl_cod.setObjectName("item_codigo")

        # Truncado de nombre más seguro
        nombre_display = (nombre[:47] + "...") if len(nombre) > 50 else nombre
        lbl_nom = QLabel(nombre_display)
        lbl_nom.setObjectName("item_nombre")

        v_info.addWidget(lbl_cod)
        v_info.addWidget(lbl_nom)
        ly.addLayout(v_info, 4)

        # 2. Selector de Bulto (sin completer — es un desplegable cerrado, no un buscador)
        from src.gui.tpv import _ScrollCombo
        cb_p = _ScrollCombo(maxvis=5)
        _opciones_bulto = getattr(self, "_opciones_pale", None) or (
            [f"PALÉ {i:02d}" for i in range(1, 21)]
            + ["BASE PALÉ", "JAULA REMONTADA", "JAULA CARTÓN", "JAULA PLÁSTICO"]
        )
        cb_p.addItems(_opciones_bulto)
        cb_p.setCompleter(None)
        cb_p.setEditable(False)
        cb_p.setCurrentText(pale_def)
        cb_p.setFixedWidth(175)
        cb_p.setCursor(Qt.CursorShape.PointingHandCursor)
        ly.addWidget(cb_p)

        # 3. Cantidad (SpinBox)
        sp = QSpinBox()
        sp.setRange(1, 9999)
        sp.setValue(value)
        sp.setFixedWidth(75)
        sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp.setButtonSymbols(
            QSpinBox.ButtonSymbols.NoButtons
        )  # Opcional: más limpio para PDA
        ly.addWidget(sp)

        # 4. Botón Borrar (Usando clausura de variable explícita)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_icono_peligro")
        btn_del.setFixedSize(32, 32)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)

        # El truco f=frame, c=codigo asegura que la lambda capture los valores actuales de la iteración
        btn_del.clicked.connect(
            lambda checked, f=frame, c=codigo: self.eliminar_widget(f, c)
        )
        ly.addWidget(btn_del)

        # Insertamos al principio para que lo último escaneado aparezca arriba
        self.scroll_layout.insertWidget(0, frame)

        # Registro en la lista de control
        self.items_widgets.append(
            {
                "frame": frame,
                "codigo": codigo,
                "nombre": nombre,
                "spinbox": sp,
                "pale": cb_p,
                "es_logistico": es_logistico,
            }
        )

    def _lanzar_pdf_worker(self, seleccionados, id_traspaso, pesos, datos_maestro=None):
        """Inicia el hilo secundario para generar PDF y etiquetas."""

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        # 2. Preparación de Metadatos
        if datos_maestro:
            # Flujo de regeneración (datos de base de datos)
            orig = datos_maestro.get("origen", "ALMC")
            dest = datos_maestro.get("destino", "N/D")
            obs = datos_maestro.get("observaciones", "")
            agencia = datos_maestro.get("agencia", "PROPIA")
            user_doc = datos_maestro.get("usuario", "Sistema")
        else:
            # Flujo de Traspaso Nuevo (datos de la UI confirmada)
            orig = str(getattr(self, "tienda_id_formateado", "ALMC"))
            dest = str(getattr(self, "destino_final", "DESTINO"))
            obs = str(getattr(self, "observaciones_final", ""))
            agencia = str(getattr(self, "agencia_final", "PROPIA"))
            user_doc = str(getattr(self, "nombre_usuario", "Usuario"))

        # 3. Inicialización del Worker y el Thread
        self.pdf_thread = QThread()
        self.pdf_worker = PdfWorker()
        self.pdf_worker.configurar(
            pale_items=seleccionados,
            origen=orig,
            destino=dest,
            observaciones=obs,
            agencia_transporte=agencia,
            usuario=user_doc,
            datos_logisticos={"peso_bulto": pesos},
            id_traspaso=str(id_traspaso),
        )

        self.pdf_worker.moveToThread(self.pdf_thread)

        # Conexiones lógicas
        self.pdf_thread.started.connect(self.pdf_worker.run)
        self.pdf_worker.finished.connect(self.pdf_thread.quit)
        self.pdf_worker.finished.connect(self.pdf_worker.deleteLater)
        self.pdf_thread.finished.connect(self.pdf_thread.deleteLater)

        # Conexiones de UI: restaurar cursor al terminar/error
        self.pdf_worker.finished.connect(QApplication.restoreOverrideCursor)
        self.pdf_worker.error.connect(QApplication.restoreOverrideCursor)

        # Callback de éxito/error (asegúrate de tener estos métodos definidos)
        if hasattr(self, "_on_pdf_ok"):
            self.pdf_worker.finished.connect(self._on_pdf_ok)
        if hasattr(self, "_on_pdf_error"):
            self.pdf_worker.error.connect(self._on_pdf_error)

        self.pdf_thread.start()

    def _on_pdf_ok(self, result):
        """Maneja el éxito de la generación del PDF."""
        QApplication.restoreOverrideCursor()

        # Intentamos abrir el PDF generado automáticamente para que el usuario lo imprima
        if result and isinstance(result, str) and os.path.exists(result):

            abrir_pdf(result)

        _mensaje_ui(
            self,
            "Traspaso Exitoso",
            "El registro se ha guardado en la base de datos y la documentación está lista.",
            "success",
        )
        self.accept()

    def _on_pdf_error(self, msg):
        """Maneja fallos en el hilo del PDF sin perder los datos guardados en DB."""
        QApplication.restoreOverrideCursor()

        if hasattr(self, "btn_confirmar"):
            self.btn_confirmar.setEnabled(True)

        _mensaje_ui(
            self,
            "Error de Documentación",
            f"Los datos se guardaron correctamente, pero no se pudo generar el PDF:\n{msg}\n\n"
            "Puede intentar regenerarlo desde el Historial Logístico.",
            "warning",
        )

    def abrir_escaner_camara(self):
        """
        Lanza el escaneo remoto (móvil) y procesa el código detectado.
        """
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(
            self, on_result=self._on_codigo_escaneado_movil, contexto="recepcion.traspaso_dialog")

    def _on_codigo_escaneado_movil(self, codigo):
        """Callback del escaneo remoto: mismo efecto que la antigua detección por webcam."""
        codigo_limpio = str(codigo).strip().upper()

        if codigo_limpio:
            # Insertamos en el campo visual y disparamos la búsqueda
            self.input_codigo_manual.setText(codigo_limpio)
            self.agregar_articulo_manual()

            # Feedback visual en el placeholder por si añade más
            self.input_codigo_manual.setPlaceholderText(
                tr("recep.codigo_anadido_escanee_otro", default="Código añadido. Escanee otro...")
            )
        else:
            self.input_codigo_manual.setPlaceholderText(
                tr("recep.no_se_detecto_contenido", default="No se detectó contenido.")
            )

        self.input_codigo_manual.setFocus()

    def ejecutar_volver(self):
        """
        Cierra el diálogo de traspaso y vuelve a la pantalla de escaneo.
        Utiliza reject() para notificar la navegación de retorno al controlador principal.
        """

        try:
            # Si hay artículos cargados, prevenimos el cierre accidental
            if hasattr(self, "items_widgets") and self.items_widgets:
                if not _confirmar_ui(
                    self,
                    "Confirmar Salida",
                    "Hay artículos en la lista. ¿Seguro que desea volver?\nLos cambios se perderán.",
                ):
                    return

            # REJECT es la clave: cierra el diálogo y devuelve QDialog.DialogCode.Rejected (0)
            # Esto permite que el controlador de navegación detecte la ruta de retorno.
            self.reject()

        except Exception as e:
            print(f"Error al cerrar diálogo: {e}")
            # Fallback de seguridad en caso de error crítico
            self.reject()


# ============================================================
# BLOQUE TRASPASO DE STOCK
# ============================================================

class TraspasoStockPage(QWidget):

    def __init__(self, usuario=None, codigo_local="ALMC"):
        super().__init__()
        # Punto 3: Unificación de referencia de usuario
        self.usuario = usuario
        self.codigo_local = codigo_local

        # Configuración de interfaz
        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz visual con el diseño de bienvenida centralizado estilo GitHub Dark."""

        # Layout principal de la página
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("panel_contenido")

        # --- PANEL DE BIENVENIDA ---
        self.vista_inicio = QFrame()
        layout_inicio = QVBoxLayout(self.vista_inicio)
        layout_inicio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Contenedor Central Estilizado (Siguiendo estilo_global.py)
        container = QFrame()
        container.setObjectName("panel_bienvenida")
        # Responsive (P2): se adapta a pantallas estrechas; tope visual en pantallas anchas.
        container.setMaximumWidth(550)
        container.setMinimumWidth(320)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(5)

        # Icono, Título e Info
        self.lbl_icono = QLabel("🚚")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_titulo = QLabel(tr("recep.gestion_de_traspasos", default="GESTIÓN DE TRASPASOS"))
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            f"Sede actual: {self.codigo_local}\n\nInicie un nuevo envío de stock entre almacenes."
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # BOTÓN CRÍTICO: neón + texto e icono centrados (btn_traspaso_land en estilo_global)
        self.btn_lanzar_dialogo = QPushButton(tr("recep.iniciar_traspaso", default="🚀 INICIAR TRASPASO"))
        self.btn_lanzar_dialogo.setObjectName("btn_traspaso_land")
        # Responsive (P2): ancho flexible con tope, alto táctil (antes fijo 320x60).
        self.btn_lanzar_dialogo.setMinimumSize(220, 60)
        self.btn_lanzar_dialogo.setMaximumWidth(360)
        self.btn_lanzar_dialogo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_lanzar_dialogo.setCursor(Qt.CursorShape.PointingHandCursor)

        # Conexión lógica
        self.btn_lanzar_dialogo.clicked.connect(self.abrir_flujo_traspaso)

        # Montaje de widgets en el contenedor
        container_layout.addWidget(self.lbl_icono)
        container_layout.addWidget(self.lbl_titulo)
        container_layout.addWidget(self.lbl_info)
        container_layout.addSpacing(10)
        container_layout.addWidget(self.btn_lanzar_dialogo)

        layout_inicio.addWidget(container)
        self.main_layout.addWidget(self.vista_inicio)

    def abrir_flujo_traspaso(self):
        """
        Lanza el diálogo de trabajo de traspaso.
        Nota: Este método es llamado si el botón es presionado directamente.
        """
        try:

            # Creamos el diálogo
            # Usamos self.window() para asegurar que el parent sea la ventana principal (RecepcionPaleWindow)
            dialogo = TraspasoDialog(
                usuario=self.usuario, tienda_id=self.codigo_local, parent=self.window()
            )

            # Ejecución modal, con la animación de deslizamiento estándar.
            from src.gui.transiciones import abrir_dialogo_deslizante
            resultado = abrir_dialogo_deslizante(dialogo, self.window())

            if resultado:
                # Si se completó el traspaso, intentamos refrescar el historial
                # buscando la página vecina en el QStackedWidget
                padre = self.parentWidget()  # QStackedWidget
                if padre and hasattr(padre, "widget"):
                    historial = padre.widget(5)  # Índice 5 es HistorialUnificadoPage
                    if hasattr(historial, "cargar_datos"):
                        historial.cargar_datos()

            dialogo.deleteLater()

        except Exception as e:
            import logging

            logging.error(f"Error en TraspasoStockPage: {e}", exc_info=True)

            _mensaje_ui(self, "Error", f"No se pudo iniciar el flujo: {e}", "error")


# ============================================================
# BLOQUE HISTORIAL DE RECEPCIONES
# ============================================================


class HistorialRecepcionesPage(QWidget):

    def __init__(self, codigo_local="ALMC", usuario=None):
        super().__init__()
        self.codigo_local = codigo_local

        # 1. Gestión de identidad de usuario (Punto 3: Normalización)
        if isinstance(usuario, dict):
            self.usuario = usuario.get("nombre", "Usuario")
        else:
            self.usuario = usuario or "Usuario"

        # Mantenemos nombre_usuario por compatibilidad con métodos existentes
        self.nombre_usuario = self.usuario

        self.nivel_actual = 1  # 1: Documentos, 2: Palés, 3: Artículos
        self.filtro_id_documento = None
        self.filtro_id_pale = None

        # 2. UI Initialization
        (
            self.page_widget,
            self.tabla,
            self.input_busqueda,
            self.btn_refresh,
            self.btn_back_level,
        ) = self.setup_ui_historial(
            "Historial de Recepciones",
            "Consulta y trazabilidad de entradas de mercancía",
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.page_widget)

        # 3. Conexiones
        self.btn_refresh.clicked.connect(self.ejecutar_actualizacion)
        self.btn_back_level.clicked.connect(self.retroceder_nivel)
        self.input_busqueda.textChanged.connect(self.cargar_datos)

        self.cargar_datos()

    # MÉTODO 1: Configuración de Interfaz Principal
    def setup_ui_historial(self, titulo_texto, subtitulo_texto):
        page = QWidget()
        page.setObjectName("panel_contenido")
        ly_principal = QVBoxLayout(page)
        ly_principal.setContentsMargins(30, 30, 30, 30)
        ly_principal.setSpacing(25)

        # --- CABECERA ---
        header_layout = QHBoxLayout()
        title_container = QVBoxLayout()

        self.lbl_titulo = QLabel(titulo_texto)
        self.lbl_titulo.setObjectName("titulo_cian")

        lbl_subtitulo = QLabel(subtitulo_texto)
        lbl_subtitulo.setObjectName("subtitulo_muted")

        title_container.addWidget(self.lbl_titulo)
        title_container.addWidget(lbl_subtitulo)

        header_layout.addLayout(title_container)
        header_layout.addStretch()

        # Botón Volver de nivel
        self.btn_back_level = QPushButton(tr("recep.volver", default="⬅ VOLVER"))
        self.btn_back_level.setObjectName("btn_secundario")
        self.btn_back_level.setFixedSize(130, 45)
        self.btn_back_level.setVisible(False)
        self.btn_back_level.setCursor(Qt.CursorShape.PointingHandCursor)

        # BOTÓN ACTUALIZAR: Unificado con el resto del sistema
        btn_refresh = QPushButton(tr("recep.actualizar_11", default="🔄 ACTUALIZAR"))
        btn_refresh.setObjectName("btn_primario")
        btn_refresh.setFixedSize(180, 45)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(self.btn_back_level)
        header_layout.addSpacing(10)
        header_layout.addWidget(btn_refresh)
        ly_principal.addLayout(header_layout)

        # --- BUSCADOR ---
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_pale_articulo_2", default="🔍 Filtrar por ID, Palé, Artículo, EAN, Origen o Fecha...")
        )
        self.input_busqueda.setFixedHeight(50)

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC. `setText()` ya
        # dispara `cargar_datos` sola (conectada a `textChanged` en `__init__`).
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=self.input_busqueda.setText, contexto="recepcion.historial_recepciones")

        self.btn_buscar = QPushButton("🔍")
        self.btn_buscar.setObjectName("btn_icono")
        self.btn_buscar.setFixedSize(48, 48)
        self.btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_buscar.clicked.connect(self.cargar_datos)

        search_layout.addWidget(self.input_busqueda)
        search_layout.addWidget(self.btn_buscar)
        search_layout.addWidget(btn_escaneo_movil)
        ly_principal.addLayout(search_layout)

        # --- TABLA (plantilla visual global reutilizable) ---
        if construir_tabla_estilizada is not None:
            wrap_tabla, self.tabla = construir_tabla_estilizada()
        else:
            wrap_tabla = QFrame()
            wrap_tabla.setObjectName("contenedor_tabla_estandar")
            wrap_layout = QVBoxLayout(wrap_tabla)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.setSpacing(0)
            self.tabla = QTableWidget()
            wrap_layout.addWidget(self.tabla)

        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Altura de fila suficiente para que los botones de ACCIONES (32px + glow
        # de neón) no se vean cortados; cada recepción tiene su espacio vital.
        self.tabla.verticalHeader().setDefaultSectionSize(60)
        # Sin padding vertical en las celdas (el global de 8px descentraba los
        # cell widgets hacia abajo); se mantiene el horizontal para el texto.
        self.tabla.setStyleSheet("QTableWidget::item { padding: 0px 8px; }")

        ly_principal.addWidget(wrap_tabla)

        return page, self.tabla, self.input_busqueda, btn_refresh, self.btn_back_level

    # MÉTODO 2: Apertura de Escáner
    def abrir_camara_filtro(self):
        """
        Lanza el escaneo remoto (móvil) para filtrar el historial mediante códigos de barras o QR.
        """
        from src.gui.components.remote_scan import iniciar_escaneo_movil
        iniciar_escaneo_movil(
            self, on_result=self._on_codigo_escaneado_movil_filtro,
            contexto="recepcion.historial_recepciones_filtro")

    def _on_codigo_escaneado_movil_filtro(self, codigo):
        if codigo:
            # Limpiamos el código por seguridad y lo aplicamos al filtro
            codigo_limpio = str(codigo).strip()
            self.input_busqueda.setText(codigo_limpio)

            if feedback_lineedit_exito is not None:
                feedback_lineedit_exito(self.input_busqueda, 1500)

            # Forzamos la recarga de datos con el nuevo filtro
            self.cargar_datos()

    # MÉTODO 3: Gestión de Refresco
    def ejecutar_actualizacion(self):
        """
        Inicia el proceso de recarga de datos con retroalimentación visual inmediata.
        """
        # Deshabilitamos para evitar colisiones de hilos o múltiples clics
        self.btn_refresh.setEnabled(False)

        # Estado visual de carga (Look industrial: fondo oscuro, borde neón)
        self.btn_refresh.setText(tr("recep.cargando_3", default="⌛ CARGANDO..."))

        # Forzamos a Qt a procesar el cambio de estilo antes de la carga pesada
        QApplication.processEvents()

        try:
            # Ejecutamos la lógica de consulta a la base de datos
            self.cargar_datos()
        except Exception as e:
            logging.error(f"Error en recarga de historial: {e}")

        # Pequeño delay de cortesía visual antes de restaurar el botón
        QTimer.singleShot(600, self.restaurar_boton_refresh)

    def restaurar_boton_refresh(self):
        """
        Devuelve el botón de actualización a su estado original neón.
        """
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText(tr("recep.actualizar_12", default="🔄 ACTUALIZAR"))

    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos)
    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos de Traspaso)
    def configurar_tabla_nivel_1(self):
        """Prepara la vista principal de documentos de recepción."""
        self.btn_back_level.setVisible(False)
        self.lbl_titulo.setText(tr("recep.historial_de_recepciones", default="Historial de Recepciones"))

        # Estética de cabecera para nivel raíz
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            ["ID TRASPASO", "FECHA ENVÍO", "ORIGEN", "ESTADO", "ACCIONES"]
        )

        # Ajuste de ancho específico para acciones
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.tabla.setColumnWidth(4, 150)

    # MÉTODO 6: Configuración Tabla Nivel 2 (Palés dentro de un traspaso)
    def configurar_tabla_nivel_2(self):
        """Prepara la vista detallada de palés para un documento específico."""
        self.btn_back_level.setVisible(True)
        # Usamos un color neón para resaltar el ID en el título
        self.lbl_titulo.setText(
            f"Palés en Traspaso: <span style='color:#00FFC6;'>{self.filtro_id_documento}</span>"
        )

        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels(
            ["CÓDIGO PALÉ", "TIPO / ORIGEN", "FECHA RECEPCIÓN", "ACCIONES"]
        )

        self.tabla.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Fixed
        )
        self.tabla.setColumnWidth(3, 120)

    # MÉTODO 7: Configuración Tabla Nivel 3 (Artículos dentro de un palé)
    def configurar_tabla_nivel_3(self):
        """Prepara la vista final de artículos y cantidades."""
        self.btn_back_level.setVisible(True)
        self.lbl_titulo.setText(
            f"Contenido Palé: <span style='color:#00FFC6;'>{self.filtro_id_pale}</span>"
        )

        self.tabla.setColumnCount(3)
        self.tabla.setHorizontalHeaderLabels(
            ["EAN / CÓDIGO", "DESCRIPCIÓN ARTÍCULO", "CANTIDAD"]
        )

        # En nivel 3, la descripción suele ser larga, le damos prioridad de stretch
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    # MÉTODO 8: Carga de Datos (Lógica Principal de DB)
    def cargar_datos(self):
        """
        Carga los datos del historial con gestión de niveles y estética GitHub Dark.
        """

        busqueda_texto = self.input_busqueda.text().strip()
        busqueda_param = f"%{busqueda_texto}%"
        local_ref = str(self.codigo_local)

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # NIVEL 1: Lista de Documentos
                    if self.nivel_actual == 1:
                        self.configurar_tabla_nivel_1()
                        query = """
                            SELECT id_documento, fecha_envio, origen, estado 
                            FROM documentos_logisticos 
                            WHERE destino = %s 
                              AND (id_documento LIKE %s OR origen LIKE %s OR estado LIKE %s)
                            ORDER BY fecha_envio DESC
                        """
                        cursor.execute(
                            query,
                            (local_ref, busqueda_param, busqueda_param, busqueda_param),
                        )

                    # NIVEL 2: Palés del Documento
                    elif self.nivel_actual == 2:
                        self.configurar_tabla_nivel_2()
                        query = """
                            SELECT DISTINCT d.id_pale, h.origen, h.fecha_envio
                            FROM documentos_logisticos_lineas d
                            JOIN documentos_logisticos h ON d.id_documento = h.id_documento
                            WHERE d.id_documento = %s AND (d.id_pale LIKE %s)
                            ORDER BY d.id_pale ASC
                        """
                        cursor.execute(
                            query, (self.filtro_id_documento, busqueda_param)
                        )

                    # NIVEL 3: Contenido del Palé
                    elif self.nivel_actual == 3:
                        self.configurar_tabla_nivel_3()
                        query = """
                            SELECT codigo_articulo AS codigo, nombre_articulo AS nombre, cantidad_enviada AS cantidad
                            FROM documentos_logisticos_lineas
                            WHERE id_pale = %s AND (nombre_articulo LIKE %s OR codigo_articulo LIKE %s)
                        """
                        cursor.execute(
                            query, (self.filtro_id_pale, busqueda_param, busqueda_param)
                        )

                    # PROCESAMIENTO
                    if cursor.description:
                        columnas = [desc[0] for desc in cursor.description]
                        resultados = [
                            dict(zip(columnas, row, strict=False)) for row in cursor.fetchall()
                        ]
                        self.renderizar_filas(resultados)
                    else:
                        self.tabla.setRowCount(0)

        except Exception as e:
            import logging

            logging.error(f"Error crítico en carga de datos: {e}")
            _mensaje_ui(
                self,
                "Error de Conexión",
                f"No se pudo sincronizar con el servidor.\n\nDetalle: {e}",
                "error",
            )

        finally:
            QApplication.restoreOverrideCursor()

    # MÉTODO 9: Renderizado de Filas con Estilo Semántico
    def renderizar_filas(self, rows):

        self.tabla.setRowCount(0)
        if not rows:
            return
        self.tabla.setRowCount(len(rows))

        for i, row in enumerate(rows):
            if self.nivel_actual == 1:
                vals = [
                    row["id_documento"],
                    str(row["fecha_envio"]),
                    row["origen"],
                    row["estado"].upper(),
                ]
                self.agregar_botones_nivel_1(i, row["id_documento"])
            elif self.nivel_actual == 2:
                vals = [row["id_pale"], row["origen"], str(row["fecha_envio"])]
                self.agregar_botones_nivel_2(i, row["id_pale"])
            else:
                vals = [row["codigo"], row["nombre"], str(row["cantidad"])]

            for j, val in enumerate(vals):
                item = QTableWidgetItem(str(val) if val else "-")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # --- LÓGICA DE COLORES DE ESTADO (Nivel 1) ---
                if self.nivel_actual == 1 and j == 3:
                    estado = str(val).upper()
                    # Paleta GitHub: Neón (Éxito), Ámbar (Pendiente), Coral (Error)
                    if estado == "RECIBIDO":
                        color = "#00FFC6"
                    elif estado == "PENDIENTE":
                        color = "#F1C40F"
                    elif "ERROR" in estado or "CANCELADO" in estado:
                        color = "#FF6B6B"
                    else:
                        color = "#8B949E"

                    item.setForeground(QColor(color))
                    font = QFont("Segoe UI", 9, QFont.Weight.Bold)
                    item.setFont(font)

                # Colores suaves para códigos en Nivel 2 y 3
                elif j == 0:
                    item.setForeground(QColor("#58A6FF"))  # Azul suave GitHub para IDs

                self.tabla.setItem(i, j, item)

    # MÉTODO 10: Botones Nivel 1 (Ver Palés / PDF)
    # MÉTODO 10: Botones Nivel 1 (Navegación y PDF)
    def agregar_botones_nivel_1(self, fila, id_doc):
        """Inserta botones de visualización y exportación para cada documento."""

        id_doc_str = str(id_doc)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)  # llenar la fila → no recortar el glow
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón para profundizar al Nivel 2 (Palés)
        btn_ver = self.crear_boton_estilizado("🔍 DETALLES", "#21262D", "#00FFC6")
        # Botón para abrir el albarán (PDF)
        btn_pdf = self.crear_boton_estilizado("📄 PDF", "#21262D", "#F0A500")

        # Conexiones con clausura para evitar errores de referencia en bucles
        btn_ver.clicked.connect(lambda: self.ir_a_nivel_2(id_doc_str))
        btn_pdf.clicked.connect(lambda: self.abrir_albaran_existente(id_doc_str))

        lay.addWidget(btn_ver, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(btn_pdf, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tabla.setCellWidget(fila, 4, container)

    # MÉTODO 11: Botones Nivel 2 (Ver Contenido de Palé)
    def agregar_botones_nivel_2(self, fila, id_pale):
        """Inserta botón para ver los artículos dentro de un palé específico."""

        id_pale_str = str(id_pale)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)  # llenar la fila → no recortar el glow
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)

        btn_items = self.crear_boton_estilizado(
            "📦 VER CONTENIDO", "#21262D", "#00FFC6"
        )
        btn_items.clicked.connect(lambda: self.ir_a_nivel_3(id_pale_str))

        lay.addWidget(btn_items, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabla.setCellWidget(fila, 3, container)

    # MÉTODO 12: Generador de Botones Estilizados (GitHub Dark Style)
    def crear_boton_estilizado(self, texto, bg, color_neon):
        """Crea un QPushButton con bordes redondeados y efecto hover industrial."""

        btn = QPushButton(texto)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Altura 44px: el QSS añade 24px de chrome vertical (padding+borde); con
        # 32px el texto quedaba cortado.
        btn.setFixedHeight(44)
        # Hover swap por color: relleno del color del botón + texto oscuro.
        btn.setStyleSheet(
            f"QPushButton{{background:{bg};color:{color_neon};"
            f"border:2px solid {color_neon};border-radius:10px;"
            f"font-family:'Segoe UI';font-weight:700;font-size:12px;padding:0px 14px;}}"
            f"QPushButton:hover{{background:{color_neon};color:#0D1117;}}"
            f"QPushButton:pressed{{background:{color_neon};color:#0D1117;}}"
        )
        return btn

    # MÉTODO 13: Apertura de PDF Albarán
    def abrir_albaran_existente(self, id_documento):
        """Localiza el archivo PDF en el servidor local o lo regenera si falta."""

        nombre_archivo = f"ALB_{id_documento}.pdf"
        ruta_pdf = os.path.abspath(
            os.path.join("documentos", "albaranes", nombre_archivo)
        )

        if os.path.exists(ruta_pdf):
            abrir_pdf(ruta_pdf)
        else:
            # Notificación visual de proceso de reconstrucción
            original_title = self.lbl_titulo.text()
            self.lbl_titulo.setText(tr("recep.reconstruyendo_pdf", default="⌛ RECONSTRUYENDO PDF..."))
            self.lbl_titulo.setProperty("tituloProcesando", True)
            if repolish_widget is not None:
                repolish_widget(self.lbl_titulo)

            # Llamamos a la lógica de generación (proceso pesado)
            QApplication.processEvents()
            self.generar_albaran_recepcion(id_documento)

            def _restaurar_titulo():
                self.lbl_titulo.setText(original_title)
                self.lbl_titulo.setProperty("tituloProcesando", False)
                if repolish_widget is not None:
                    repolish_widget(self.lbl_titulo)

            QTimer.singleShot(2000, _restaurar_titulo)

    # MÉTODO 14: Lógica de Reconstrucción de Albarán (Nube -> PDF)
    def generar_albaran_recepcion(self, id_documento):
        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM documentos_logisticos WHERE id_documento = %s",
                        (id_documento,),
                    )
                    maestro = cur.fetchone()
                    cur.execute(
                        "SELECT * FROM documentos_logisticos_lineas WHERE id_documento = %s",
                        (id_documento,),
                    )
                    detalles = cur.fetchall()

            if not maestro or not detalles:
                _mensaje_ui(
                    self, "Error", "No hay datos en la nube para este documento.", "warning"
                )
                return

            items_formateados = []
            pesos_pales = {}
            for d in detalles:
                id_v = (
                    d["id_pale"].split("-")[-1] if "-" in d["id_pale"] else d["id_pale"]
                )
                pesos_pales[id_v] = float(d["peso_bulto"] or 0.0)
                items_formateados.append(
                    {
                        "codigo": d["codigo"],
                        "nombre": d["nombre"],
                        "cantidad": d["cantidad"],
                        "id_visual_pale": id_v,
                    }
                )

            self._lanzar_pdf_worker(
                items_formateados, id_documento, pesos_pales, maestro
            )
        except Exception as e:
            _mensaje_ui(self, "Error", f"Error al procesar: {str(e)}", "error")

    # MÉTODO 15: Lanzador de Worker PDF (Asíncrono)
    def _lanzar_pdf_worker(self, seleccionados, id_traspaso, pesos, datos_maestro):
        self.worker = PdfWorker()
        self.worker.configurar(
            pale_items=seleccionados,
            origen=datos_maestro.get("origen", "ALMC"),
            destino=datos_maestro.get("destino", "N/D"),
            observaciones=datos_maestro.get("observaciones", ""),
            agencia_transporte=datos_maestro.get("agencia", "PROPIA"),
            usuario=self.nombre_usuario,
            id_traspaso=id_traspaso,
            datos_logisticos={"peso_bulto": pesos},
            tipo_operacion="recepcion",
        )
        self.hilo_pdf = QThread()
        self.worker.moveToThread(self.hilo_pdf)
        self.hilo_pdf.started.connect(self.worker.run)
        self.worker.finished.connect(self.hilo_pdf.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.hilo_pdf.finished.connect(self.hilo_pdf.deleteLater)
        self.worker.finished.connect(self.on_pdf_recepcion_listo)
        self.hilo_pdf.start()

    # MÉTODO 16: Callback PDF Listo
    def on_pdf_recepcion_listo(self, resultado):
        ruta_pdf = resultado[0]
        self.restaurar_boton_refresh()
        abrir_pdf(ruta_pdf)

    # MÉTODO 17: Navegación Nivel 2
    # MÉTODO 17: Navegación a Nivel 2 (Vista de Palés)
    def ir_a_nivel_2(self, id_doc):
        """
        Filtra la vista para mostrar exclusivamente los palés asociados
        a un documento de traspaso.
        """
        self.filtro_id_documento = id_doc
        self.nivel_actual = 2

        # Limpiamos el buscador para que el operario pueda buscar palés específicos
        self.input_busqueda.clear()

        # Reiniciamos el scroll al principio de la tabla
        self.tabla.scrollToTop()

        # Recargamos con la configuración de nivel 2
        self.cargar_datos()

    # MÉTODO 18: Navegación a Nivel 3 (Vista de Artículos)
    def ir_a_nivel_3(self, id_pale):
        """
        Filtra la vista para mostrar el contenido detallado (SKUs)
        de un palé seleccionado.
        """
        self.filtro_id_pale = id_pale
        self.nivel_actual = 3

        self.input_busqueda.clear()
        self.tabla.scrollToTop()

        # Recargamos con la configuración de nivel 3
        self.cargar_datos()

    # MÉTODO 19: Lógica de Retroceso (Navegación Breadcrumbs)
    def retroceder_nivel(self):
        """
        Gestiona el retorno a la vista anterior en la jerarquía logística.
        """
        if self.nivel_actual == 3:
            # Si estamos viendo artículos, volvemos a la lista de palés del documento
            self.nivel_actual = 2
            self.filtro_id_pale = None
        elif self.nivel_actual == 2:
            # Si estamos en palés, volvemos al historial general
            self.nivel_actual = 1
            self.filtro_id_documento = None

        # Limpiamos filtros de búsqueda al cambiar de contexto
        self.input_busqueda.clear()

        # Forzamos la actualización de la UI
        self.cargar_datos()

