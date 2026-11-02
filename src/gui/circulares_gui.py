"""
Bandeja interna de la empresa — CIRCULARES y ENCUESTAS entre centros (dentro del módulo de Correo).

Estructura base común y diseño moderno/limpio coherente con la app (dark + turquesa):
  · BandejaComunicacionDialog — recibe todas las circulares y encuestas de la empresa.
  · Compositor y visor de CIRCULAR (confirmación de lectura con perfil + contraseña, comentario y
    adjuntos; imágenes del emisor mostradas en línea).
  · Compositor y visor de ENCUESTA (preguntas ilimitadas de opciones o de texto, opción "Otro" con
    texto, texto introductorio, comentario y adjuntos; imágenes en línea).

Reutiliza los servicios `services.comunicacion_interna` (circulares/encuestas/adjuntos), los usuarios
(perfil+contraseña) y los centros de la empresa. Sin motor nuevo.
"""

from __future__ import annotations

import logging
import os
import re

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import _blindar_tamano_fijo
from src.utils.i18n import tr

logger = logging.getLogger("gui.circulares")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_VERDE = "#3FB950"
_ROJO = "#FF4C4C"
_AMBAR = "#F1C40F"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"

_IMG_EXT = ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp")
_FILTRO = ("Texto e imagen (*.txt *.pdf *.doc *.docx *.csv *.png *.jpg *.jpeg *.gif *.bmp *.webp)")


def _lbl(text, bold=False, size=13, color=_TEXT, wrap=False):
    la = QLabel(text)
    la.setWordWrap(wrap)
    la.setStyleSheet(f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
                     f"font-weight:{'900' if bold else '500'};background:transparent;border:none;")
    return la


def _btn(text, *, fg=_TEXT, border=_BORDE, bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=40):
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:{fg};border:2px solid {border};border-radius:10px;"
        f"font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 16px;}}"
        f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};border-color:{hover_bg};}}")
    return b


def _input(ph="", val=""):
    e = QLineEdit(val)
    e.setPlaceholderText(ph)
    e.setFixedHeight(40)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:0 12px;font-size:14px;font-family:'{_FONT}';}}"
                    f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _textarea(ph="", h=120, val=""):
    t = QTextEdit()
    t.setPlaceholderText(ph)
    if val:
        t.setPlainText(val)
    t.setFixedHeight(h)
    t.setStyleSheet(f"QTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:8px;font-size:14px;font-family:'{_FONT}';}}"
                    f"QTextEdit:focus{{border-color:{_CIAN};}}")
    return t


def _combo(items=None):
    c = QComboBox()
    c.setFixedHeight(40)
    c.setStyleSheet(f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:0 12px;font-size:14px;font-family:'{_FONT}';}}"
                    f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
                    f"QComboBox::drop-down{{border:none;width:24px;}}"
                    f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
                    f"border-radius:10px;outline:0px;selection-background-color:{_CIAN};selection-color:#0D1117;}}")
    for it in (items or []):
        if isinstance(it, (tuple, list)):
            c.addItem(it[0], it[1])
        else:
            c.addItem(it)
    return c


def _scroll_qss():
    try:
        from src.gui.foundation import tokens
        return tokens.qss_scrollbar()
    except Exception:
        return ""


def _fecha(v) -> str:
    try:
        return v.strftime("%d/%m/%Y  %H:%M") if hasattr(v, "strftime") else str(v or "")
    except Exception:
        return str(v or "")


def _empresa_id():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _abrir_archivo(ruta):
    try:
        if ruta and os.path.exists(ruta):
            os.startfile(ruta)   # Windows
    except Exception:
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))
        except Exception:
            pass


class _DialogoBase(QDialog):
    """Diálogo frameless con cabecera (título + ✕), borde neón y área de scroll. Base común de diseño."""

    def __init__(self, titulo, parent=None, ancho=0.62, alto=0.86, icono="📋",
                pantalla_completa: bool = False):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        if pantalla_completa:
            # TERCER INTENTO (los dos anteriores — geometría a mano, luego showFullScreen() solo en
            # showEvent — no se pudieron confirmar como realmente arreglados en la máquina real del
            # usuario). `showFullScreen()` necesita que la ventana sea un top-level "Window" de
            # verdad, no un `Qt.WindowType.Dialog` (el tipo por defecto de QDialog).
            self.setWindowFlag(Qt.WindowType.Window)
            # WA_TranslucentBackground es sospechoso de interferir con la composición de pantalla
            # completa de DWM en Windows (combinación frameless+translúcido+fullscreen conocida por
            # dar problemas) — en pantalla completa no aporta nada visualmente de todos modos (ya se
            # pinta sin borde ni esquinas redondeadas, ver más abajo), así que se omite aquí para
            # eliminar esa variable en vez de seguir conviviendo con ella sin saber si es la causa.
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag = None
        self._pantalla_completa = pantalla_completa
        if pantalla_completa:
            # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`,
            # estilo_global.py): esta ventana es a PANTALLA COMPLETA — el `border:none` puesto
            # más abajo en el QFrame interior ("cbody") NO basta, el contorno lo pinta el propio
            # QDialog (éste, `self`) vía esa regla QSS global por tipo, no por el frame hijo.
            self.setObjectName("dlg_base_pantalla_completa")
            self.setStyleSheet("#dlg_base_pantalla_completa { border: none; }")
        if not pantalla_completa:
            try:
                pantalla = self.screen() or QApplication.primaryScreen()
                g = pantalla.availableGeometry()
                self.resize(int(g.width() * ancho), int(g.height() * alto))
            except Exception:
                self.resize(900, 700)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("cbody")
        if pantalla_completa:
            # Borde/radio con sentido en un diálogo flotante; en pantalla completa, borde a
            # borde, no aportan nada (y un borde "redondeado" a pantalla completa desentona).
            cuerpo.setStyleSheet(f"QFrame#cbody{{background:{_BG};border:none;border-radius:0px;}}")
        else:
            cuerpo.setStyleSheet(f"QFrame#cbody{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        outer.addWidget(cuerpo)
        root = QVBoxLayout(cuerpo)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(12)
        # Cabecera
        hd = QHBoxLayout()
        hd.addWidget(_lbl(f"{icono}  {titulo}", bold=True, size=19, color=_CIAN))
        hd.addStretch()
        self._hd = hd
        bx = QPushButton("✕")
        bx.setFixedSize(38, 38)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:none;border-radius:19px;padding:0;font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 38, 38)
        bx.clicked.connect(self.reject)
        hd.addWidget(bx)
        root.addLayout(hd)
        # Scroll + contenido
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}" + _scroll_qss())
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        self.cuerpo = QVBoxLayout(cont)
        # Margen derecho ampliado (12 -> 24px): la scrollbar (16px de ancho, ver qss_scrollbar())
        # tapaba el borde derecho de los campos de texto de los diálogos de circular/encuesta.
        self.cuerpo.setContentsMargins(4, 4, 24, 4)
        self.cuerpo.setSpacing(12)
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)
        self._root = root

    def _aplicar_pantalla_completa(self, momento: str):
        """QUINTO intento. El log REAL del usuario (cuarto intento, `showMaximized()`) reveló la
        causa de raíz exacta: `isMaximized()`/`windowState()` SÍ reportaban `WindowMaximized` (Qt
        "cree" que pidió maximizar), pero la geometría real en pantalla NO era la de la pantalla
        — y, más revelador aún, el CENTRO X de la ventana era IDÉNTICO (673px) en tres diálogos con
        contenidos y tamaños distintos. Esa es la firma inequívoca de que, DESPUÉS de que este
        método pide pantalla completa, el propio `QDialog` (en su secuencia interna de `show()`,
        que continúa tras `showEvent`) vuelve a ajustar la ventana a su `sizeHint()` y la CENTRA —
        deshaciendo el pedido. Ni `setGeometry` a mano (1er intento) ni `showFullScreen()` (2º/3er)
        ni `showMaximized()` solos (4º) sobreviven a ese reajuste posterior porque todos se piden
        DEMASIADO PRONTO, antes de que Qt termine su propia secuencia de "mostrar diálogo".

        Fix: además de pedirlo ya (por si ayuda), se vuelve a pedir en el SIGUIENTE ciclo de
        eventos (`QTimer.singleShot(0, ...)`), momento en el que la secuencia interna de Qt ya ha
        terminado — así esta llamada es la que tiene la ÚLTIMA palabra, no una que Qt pueda
        sobrescribir después. Combina `showMaximized()` (semántica ya probada en esta app) CON una
        geometría explícita a la pantalla física completa (`screen().geometry()`, no
        `availableGeometry()`) como refuerzo, ya que el log confirmó que el ESTADO puede decir
        "maximizado" sin que la geometría real lo refleje."""
        try:
            pantalla = self.screen() or QApplication.primaryScreen()
            self.showMaximized()
            if pantalla:
                self.setGeometry(pantalla.geometry())
            logger.info(
                "_DialogoBase pantalla_completa [%s]: geometry=%s screen_geometry=%s "
                "isMaximized=%s windowState=%s", momento, self.geometry(),
                pantalla.geometry() if pantalla else None, self.isMaximized(), self.windowState())
        except Exception as e:
            logger.debug("pantalla_completa [%s]: %s", momento, e)

    def exec(self):
        if self._pantalla_completa:
            self._aplicar_pantalla_completa("pre-exec")
        return super().exec()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pantalla_completa:
            self._aplicar_pantalla_completa("showEvent")
            # LA clave de este quinto intento: reaplicar en el siguiente ciclo de eventos, DESPUÉS
            # de que la propia secuencia interna de `QDialog.show()` termine de recentrar/reajustar
            # la ventana a su sizeHint (eso es lo que deshacía los 4 intentos anteriores). Esta
            # llamada diferida es la que de verdad gana la partida.
            QTimer.singleShot(0, lambda: self._aplicar_pantalla_completa("diferido-0ms"))

    # Barra de acciones al pie (opcional).
    def barra_pie(self):
        fila = QHBoxLayout()
        self._root.addLayout(fila)
        return fila

    # Arrastre por la cabecera — NUNCA en pantalla completa (petición explícita: el usuario no
    # debe poder desplazar fuera de sitio un diálogo que ya ocupa toda la pantalla a propósito).
    def mousePressEvent(self, e):
        if (not self._pantalla_completa and e.button() == Qt.MouseButton.LeftButton
                and e.position().y() <= 60):
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)


class _AdjuntosWidget(QWidget):
    """Selector de adjuntos reutilizable: botón + lista de archivos elegidos (texto e imagen)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rutas: list[str] = []
        self.setStyleSheet("background:transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self._v = v
        self.boton = _btn("📎  " + tr("com.adjuntar", default="Adjuntar archivo"), fg=_CIAN, border=_CIAN, h=36)
        self.boton.clicked.connect(self._elegir)
        v.addWidget(self.boton, alignment=Qt.AlignmentFlag.AlignLeft)
        self._lista = QVBoxLayout()
        self._lista.setSpacing(4)
        v.addLayout(self._lista)

    def extraer_boton(self, alto=None):
        """Saca el botón 'Adjuntar archivo' del widget para colocarlo donde convenga (p. ej. en el pie).
        El widget conserva solo la LISTA de adjuntos. Devuelve el botón."""
        self._v.removeWidget(self.boton)
        self.boton.setParent(None)
        if alto:
            self.boton.setFixedHeight(alto)
        return self.boton

    def _elegir(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, tr("com.adjuntar_titulo", default="Adjuntar archivos"), "", _FILTRO)
        for r in rutas:
            if r and r not in self._rutas:
                self._rutas.append(r)
                self._añadir_chip(r)

    def _añadir_chip(self, ruta):
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        icono = "🖼" if os.path.splitext(ruta)[1].lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp") else "📄"
        lb = _lbl(f"{icono}  {os.path.basename(ruta)}", size=12, color=_TEXT2)
        x = QPushButton("✕")
        x.setFixedSize(22, 22)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;padding:0;font-weight:900;}}")
        x.setProperty("sin_glow", True)
        _blindar_tamano_fijo(x, 22, 22)
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        fila.addWidget(lb)
        fila.addStretch()
        fila.addWidget(x)
        cont.setLayout(fila)
        self._lista.addWidget(cont)

        def _quitar():
            if ruta in self._rutas:
                self._rutas.remove(ruta)
            cont.setParent(None)
            cont.deleteLater()
        x.clicked.connect(_quitar)

    def rutas(self):
        return list(self._rutas)


def _bloque_imagenes_inline(adjuntos, ancho_max=520):
    """Devuelve un QWidget con las imágenes (clase='imagen') mostradas en línea. None si no hay."""
    imgs = [a for a in (adjuntos or []) if a.get("clase") == "imagen" and os.path.exists(a.get("ruta") or "")]
    if not imgs:
        return None
    cont = QWidget()
    cont.setStyleSheet("background:transparent;")
    v = QVBoxLayout(cont)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)
    for a in imgs:
        pix = QPixmap(a["ruta"])
        if pix.isNull():
            continue
        if pix.width() > ancho_max:
            pix = pix.scaledToWidth(ancho_max, Qt.TransformationMode.SmoothTransformation)
        lb = QLabel()
        lb.setPixmap(pix)
        lb.setStyleSheet(f"border:1px solid {_BORDE};border-radius:10px;background:{_BG2};padding:4px;")
        v.addWidget(lb, alignment=Qt.AlignmentFlag.AlignLeft)
    return cont


def _bloque_adjuntos_texto(adjuntos):
    """Devuelve un QWidget con los adjuntos de texto (botón para abrir). None si no hay."""
    docs = [a for a in (adjuntos or []) if a.get("clase") != "imagen"]
    if not docs:
        return None
    cont = QWidget()
    cont.setStyleSheet("background:transparent;")
    v = QVBoxLayout(cont)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    for a in docs:
        b = _btn("📄  " + (a.get("nombre") or "documento"), fg=_CIAN, border=_BORDE, h=34)
        b.clicked.connect(lambda _=False, r=a.get("ruta"): _abrir_archivo(r))
        v.addWidget(b, alignment=Qt.AlignmentFlag.AlignLeft)
    return cont


def _usuario_actual():
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or {}
    except Exception:
        return {}


class _FlowLayout(QLayout):
    """Flow layout mínimo (receta estándar de Qt): coloca sus hijos en fila, de izquierda a derecha,
    y envuelve a la siguiente línea cuando no caben más — usado por `_CampoDestinatarios` para que
    los chips de destinatario crezcan hacia abajo sin límite de filas."""

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items: list = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._acomodar(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._acomodar(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _acomodar(self, rect, test_only):
        x, y = rect.x(), rect.y()
        alto_fila = 0
        for item in self._items:
            siguiente_x = x + item.sizeHint().width() + self._spacing
            if siguiente_x - self._spacing > rect.right() and alto_fila > 0:
                x = rect.x()
                y += alto_fila + self._spacing
                siguiente_x = x + item.sizeHint().width() + self._spacing
                alto_fila = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = siguiente_x
            alto_fila = max(alto_fila, item.sizeHint().height())
        return y + alto_fila - rect.y()


class _ChipDestinatario(QFrame):
    """Un destinatario ya resuelto, como "chip" removible con tooltip propio (nombre + centro para
    internos, nota de difusión para centros, aviso de "sin cuenta" para externos). El tooltip se
    estiliza con una regla `QToolTip{...}` en la hoja de estilos DEL PROPIO widget (Qt respeta un
    estilo de tooltip por-widget) — si el motor de estilos nativo de la plataforma no llega a
    redondear la esquina del tooltip pese a esto, es una limitación de renderizado del tooltip
    nativo, no de esta hoja de estilos."""

    def __init__(self, texto, identidad: dict, tooltip: str, on_quitar, *, color=_CIAN, parent=None):
        super().__init__(parent)
        self.identidad = identidad
        self.setStyleSheet(
            f"QFrame{{background:rgba(0,255,198,0.10);border:1px solid {color};"
            f"border-radius:12px;}}"
            f"QToolTip{{background:{_BG2};color:{_TEXT};border:1px solid {color};"
            f"border-radius:8px;padding:6px 10px;font-family:'{_FONT}';font-size:12px;}}")
        self.setToolTip(tooltip)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.setSpacing(6)
        lay.addWidget(_lbl(texto, size=12, color=_TEXT))
        x = QPushButton("✕")
        x.setFixedSize(18, 18)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:none;padding:0;"
            f"font-weight:900;font-size:11px;border-radius:9px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}")
        x.setProperty("sin_glow", True)
        _blindar_tamano_fijo(x, 18, 18)
        x.clicked.connect(lambda: on_quitar(self))
        lay.addWidget(x)


_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _CampoDestinatarios(QWidget):
    """Campo de destinatario (Para/CC/Cco) con autocompletado sobre TRES orígenes tenant-safe
    (`services.comunicacion_interna.usuarios_internos`): 👤 usuarios internos de la empresa (por
    email — un empleado sin email no se sugiere), 🏢 centros de trabajo con email (difunden a TODOS
    sus empleados activos) y ✉️ contactos externos con los que esta empresa YA ha escrito antes
    (histórico, nunca el directorio completo de clientes/proveedores). Nunca mezcla datos ENTRE
    empresas — SÍ permite, deliberadamente, escribir a alguien fuera de la propia empresa (cliente,
    proveedor, centro) cuando corresponde a uno de esos tres orígenes.

    Diseño de "chips": seleccionar una sugerencia (o pulsar Intro sobre la sugerencia resaltada) crea
    un chip removible con su identidad ya resuelta — `{"usuario_id":...}` / `{"centro_codigo":...}` /
    `{"email_externo":...,"nombre":...}` — y limpia el campo de texto. Si se pulsa Intro SIN ninguna
    sugerencia visible y el texto escrito tiene forma de email, se admite igualmente como contacto
    externo nuevo (un contacto nunca puede aparecer en el histórico ANTES de su primer envío real:
    sin esto sería imposible escribirle la primera vez). `.destinatarios()` ya no parsea texto: lee
    los chips directamente."""

    def __init__(self, etiqueta, parent=None, *, excluir_id=None, placeholder=None):
        super().__init__(parent)
        self._excluir_id = excluir_id
        self._chips: list[tuple[dict, _ChipDestinatario]] = []
        self.setStyleSheet("background:transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(_lbl(etiqueta, bold=True, size=12, color=_TEXT2))

        self._chips_widget = QWidget()
        self._chips_widget.setStyleSheet("background:transparent;")
        self._chips_layout = _FlowLayout(self._chips_widget, margin=0, spacing=6)
        v.addWidget(self._chips_widget)

        self.campo = _input(placeholder or tr("com.destinatarios_ph",
                                               default="Nombre, email o centro…"))
        v.addWidget(self.campo)

        self._popup = QListWidget()
        # BUG REAL (freeze de "Para"/"CC"/"Cco"): `Qt.WindowType.Popup` lleva un GRAB de ratón/
        # teclado IMPLÍCITO (mecanismo nativo de Qt para menús/popups que se cierran al pulsar
        # fuera). Anidado dentro de un `QDialog` MODAL (`_DialogoBase`, `setModal(True)`), ese grab
        # implícito entra en conflicto con el propio bucle modal del diálogo: el input dejaba de
        # llegarle al resto del diálogo hasta que una interacción CON el propio popup (que sí lo
        # oculta) liberaba el grab — exactamente el síntoma reportado ("todo se bloquea hasta
        # seleccionar del desplegable"). Fix real: dejar de depender del grab implícito de Popup.
        # `Qt.WindowType.ToolTip` flota por encima del contenido igual, pero NUNCA activa/agarra el
        # foco — el show/hide pasa a controlarse A MANO (ver `eventFilter` — Escape, FocusOut con
        # un pequeño retardo, y selección de item, que ya ocultaba el popup antes de este fix).
        self._popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setMouseTracking(True)
        self._popup.setStyleSheet(
            f"QListWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};border-radius:10px;"
            f"font-family:'{_FONT}';font-size:13px;outline:none;padding:4px;}}"
            "QListWidget::item{padding:7px 10px;border-radius:6px;}"
            f"QListWidget::item:selected{{background:rgba(0,255,198,0.18);color:{_CIAN};}}"
            "QListWidget::item:hover{background:rgba(0,255,198,0.10);}")
        self._popup.itemClicked.connect(self._elegir)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._buscar)
        self.campo.textEdited.connect(lambda _t: self._timer.start())
        self.campo.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.campo and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if self._popup.isVisible():
                if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    fila = self._popup.currentRow()
                    fila += 1 if k == Qt.Key.Key_Down else -1
                    self._popup.setCurrentRow(max(0, min(self._popup.count() - 1, fila)))
                    return True
                if k == Qt.Key.Key_Escape:
                    self._popup.hide()
                    return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._popup.isVisible() and self._popup.count():
                    it = self._popup.currentItem() or self._popup.item(0)
                    self._elegir(it)
                else:
                    texto = self.campo.text().strip()
                    if texto and _RE_EMAIL.match(texto):
                        self._agregar_chip(
                            {"email_externo": texto, "nombre": None}, texto,
                            tr("com.tt_externo",
                               default="Contacto externo (sin cuenta en Smart Manager)"))
                return True
        if obj is self.campo and ev.type() == ev.Type.FocusOut:
            # Ya NO hay grab implícito (`Qt.WindowType.ToolTip`, ver `__init__`) que oculte el
            # popup solo — se oculta A MANO aquí. Retardo corto (no síncrono): si el foco se pierde
            # porque el usuario está pulsando un ITEM del propio popup, ese clic todavía necesita
            # procesarse (`itemClicked` -> `_elegir`) antes de que el popup desaparezca; ocultarlo
            # de inmediato aquí se lo impediría. `False`: no consume el evento, el foco se pierde
            # con normalidad (el bloqueo que había NUNCA venía de este evento, sino del grab).
            QTimer.singleShot(150, self._popup.hide)
        return super().eventFilter(obj, ev)

    def _empresa_actual(self):
        return _empresa_id()

    def _buscar(self):
        texto = self.campo.text().strip()
        if not texto:
            self._popup.hide()
            return
        emp = self._empresa_actual()
        resultados = []
        try:
            from src.services.comunicacion_interna.usuarios_internos import (
                listar_centros_empresa, listar_contactos_externos, listar_usuarios_empresa)
            uid_actual = None
            try:
                from src.db.usuario import sesion_global
                uid_actual = (sesion_global.usuario_actual or {}).get("id")
            except Exception:
                pass
            for u in listar_usuarios_empresa(emp, texto, excluir_id=self._excluir_id):
                resultados.append({
                    "icono": "👤", "texto": u.get("nombre") or u.get("email") or "—",
                    "identidad": {"usuario_id": u.get("id"), "nombre": u.get("nombre")},
                    "tooltip": f"{u.get('nombre') or '—'} · {u.get('centro') or '—'}"})
            for c in listar_centros_empresa(emp, texto):
                resultados.append({
                    "icono": "🏢", "texto": c.get("nombre") or c.get("email") or "—",
                    "identidad": {"centro_codigo": c.get("centro_codigo")},
                    "tooltip": tr("com.tt_centro",
                                 default="Difusión a todos los empleados de este centro")})
            for e in listar_contactos_externos(emp, uid_actual, texto):
                resultados.append({
                    "icono": "✉️", "texto": e.get("nombre") or e.get("email") or "—",
                    "identidad": {"email_externo": e.get("email"), "nombre": e.get("nombre")},
                    "tooltip": tr("com.tt_externo",
                                 default="Contacto externo (sin cuenta en Smart Manager)")})
        except Exception as e:
            logger.debug("_CampoDestinatarios buscar: %s", e)
        if not resultados:
            self._popup.hide()
            return
        self._popup.clear()
        for r in resultados[:20]:
            it = QListWidgetItem(f"{r['icono']}  {r['texto']}")
            it.setData(Qt.ItemDataRole.UserRole, r)
            self._popup.addItem(it)
        self._popup.setCurrentRow(0)
        self._posicionar()
        self._popup.show()

    def _posicionar(self):
        pos = self.campo.mapToGlobal(QPoint(0, self.campo.height() + 2))
        self._popup.setGeometry(pos.x(), pos.y(), max(self.campo.width(), 280),
                                min(self._popup.count(), 8) * 38 + 10)

    def _elegir(self, item):
        r = item.data(Qt.ItemDataRole.UserRole)
        self._popup.hide()
        if not r:
            return
        self._agregar_chip(r["identidad"], r["texto"], r["tooltip"])

    def _agregar_chip(self, identidad: dict, texto: str, tooltip: str):
        clave = tuple(sorted(identidad.items()))
        for ident, _chip in self._chips:
            if tuple(sorted(ident.items())) == clave:
                self.campo.clear()
                return
        chip = _ChipDestinatario(texto, identidad, tooltip, self._quitar_chip)
        self._chips.append((identidad, chip))
        self._chips_layout.addWidget(chip)
        self.campo.clear()
        self.campo.setFocus()

    def _quitar_chip(self, chip):
        self._chips = [(i, c) for (i, c) in self._chips if c is not chip]
        self._chips_layout.removeWidget(chip)
        chip.setParent(None)
        chip.deleteLater()

    def destinatarios(self) -> list[dict]:
        """Lee directamente los chips — sin parseo de texto. Cada chip ya guarda su identidad
        resuelta (`usuario_id` / `centro_codigo` / `email_externo`)."""
        return [dict(identidad) for identidad, _chip in self._chips]


class _ConfirmarPerfilDialog(QDialog):
    """Ventana pequeña: seleccionar el perfil de empleado + contraseña. Devuelve (nombre, password)."""

    def __init__(self, parent=None, titulo="CONFIRMAR IDENTIDAD"):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self.resultado = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("cbody")
        body.setStyleSheet(f"QFrame#cbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        v.addWidget(_lbl("🔒  " + titulo, bold=True, size=16, color=_CIAN))
        v.addWidget(_lbl(tr("com.conf_perfil", default="Perfil de empleado"), bold=True, size=12,
                         color=_TEXT2))
        self.cmb = _combo()
        try:
            from src.db.usuario import listar_usuarios_empresa
            for u in listar_usuarios_empresa(_empresa_id()):
                self.cmb.addItem(u.get("nombre", "—"), u.get("nombre"))
        except Exception:
            pass
        v.addWidget(self.cmb)
        v.addWidget(_lbl(tr("com.conf_pwd", default="Contraseña"), bold=True, size=12, color=_TEXT2))
        self.inp_pwd = _input(tr("com.conf_pwd_ph", default="Contraseña del perfil"))
        self.inp_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pwd.returnPressed.connect(self._aceptar)
        v.addWidget(self.inp_pwd)
        self.lbl_err = _lbl("", bold=True, size=12, color=_ROJO, wrap=True)
        v.addWidget(self.lbl_err)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn(tr("common.cancel", default="Cancelar"), fg=_ROJO, border=_ROJO,
                            hover_bg=_ROJO, hover_fg="#FFF", h=42))
        b_ok = _btn("✔  " + tr("com.confirmar", default="Confirmar"), fg=_VERDE, border=_VERDE, bg=_BG2,
                    hover_bg=_VERDE, hover_fg=_BG, h=42)
        b_ok.clicked.connect(self._aceptar)
        fila.itemAt(1).widget().clicked.connect(self.reject)
        fila.addWidget(b_ok)
        v.addLayout(fila)
        QTimer.singleShot(0, self.inp_pwd.setFocus)

    def error(self, msg):
        self.lbl_err.setText(msg)

    def _aceptar(self):
        nombre = self.cmb.currentData() or self.cmb.currentText()
        pwd = self.inp_pwd.text()
        if not nombre or not pwd:
            self.lbl_err.setText(tr("com.conf_falta", default="Selecciona el perfil e introduce la contraseña."))
            return
        self.resultado = (nombre, pwd)
        self.accept()


class _ReenviarDialog(QDialog):
    """Diálogo pequeño de reenvío: un único campo de destinatario (Para, sin CC/Cco — el reenvío
    no lo necesita) + confirmar. Usado por ambos visores (circular/encuesta)."""

    def __init__(self, parent=None, *, excluir_id=None, titulo="REENVIAR"):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self.resultado = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("cbody")
        body.setStyleSheet(f"QFrame#cbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        v.addWidget(_lbl("↪  " + titulo, bold=True, size=16, color=_CIAN))
        self.campo = _CampoDestinatarios(tr("com.f_para", default="Para"), excluir_id=excluir_id)
        v.addWidget(self.campo)
        fila = QHBoxLayout()
        fila.addStretch()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), fg=_ROJO, border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF", h=42)
        b_cancel.clicked.connect(self.reject)
        fila.addWidget(b_cancel)
        b_ok = _btn("↪  " + tr("com.reenviar", default="Reenviar"), fg=_VERDE, border=_VERDE, bg=_BG2,
                    hover_bg=_VERDE, hover_fg=_BG, h=42)
        b_ok.clicked.connect(self._aceptar)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def _aceptar(self):
        destinatarios = self.campo.destinatarios()
        if not destinatarios:
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_para", default="Debes indicar al menos un "
                                   "destinatario en «Para»."))
            return
        self.resultado = destinatarios
        self.accept()


class _FechaHoraDialog(QDialog):
    """Diálogo pequeño: elegir una fecha/hora FUTURA — reutilizado por «Programar envío»
    (composers) y «Posponer» (bandeja unificada). Mismo patrón visual que `_ConfirmarPerfilDialog`/
    `_ReenviarDialog` (frameless + translúcido + card con borde neón)."""

    def __init__(self, parent=None, *, titulo="ELEGIR FECHA Y HORA"):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self.resultado = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("cbody")
        body.setStyleSheet(f"QFrame#cbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(_lbl("🕒  " + titulo, bold=True, size=16, color=_CIAN))
        from PyQt6.QtCore import QDateTime
        from PyQt6.QtWidgets import QDateTimeEdit
        self.dt = QDateTimeEdit()
        self.dt.setCalendarPopup(True)
        self.dt.setDisplayFormat("dd/MM/yyyy HH:mm")
        minimo = QDateTime.currentDateTime().addSecs(60)
        self.dt.setMinimumDateTime(minimo)
        self.dt.setDateTime(minimo)
        self.dt.setFixedHeight(40)
        self.dt.setStyleSheet(
            f"QDateTimeEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 12px;font-size:14px;font-family:'{_FONT}';}}"
            f"QDateTimeEdit:focus{{border-color:{_CIAN};}}")
        v.addWidget(self.dt)
        fila = QHBoxLayout()
        fila.addStretch()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), fg=_ROJO, border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF", h=42)
        b_cancel.clicked.connect(self.reject)
        fila.addWidget(b_cancel)
        b_ok = _btn("✔  " + tr("com.confirmar", default="Confirmar"), fg=_VERDE, border=_VERDE, bg=_BG2,
                    hover_bg=_VERDE, hover_fg=_BG, h=42)
        b_ok.clicked.connect(self._aceptar)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def _aceptar(self):
        self.resultado = self.dt.dateTime().toPyDateTime()
        self.accept()


# ══════════════════════════════════ CIRCULARES ══════════════════════════════════

class _CircularComposerDialog(_DialogoBase):
    """Compositor de una nueva circular — o de un BORRADOR/PROGRAMADA existente si se pasa
    `id_borrador` (reabrir para seguir editando, publicar o reprogramar; ver `circulares.
    guardar_borrador`/`publicar_borrador`/`programar`)."""

    def __init__(self, parent=None, id_borrador=None):
        super().__init__(tr("com.circ_nueva", default="NUEVO MENSAJE"), parent, icono="✉️", alto=0.86,
                         pantalla_completa=True)
        self._id_borrador = id_borrador
        u = _usuario_actual()
        import datetime
        ahora = datetime.datetime.now().strftime("%d/%m/%Y  %H:%M")
        self.cuerpo.addWidget(_lbl(tr("com.f_titulo", default="Título de la circular"), bold=True,
                                   size=12, color=_TEXT2))
        self.inp_titulo = _input(tr("com.f_titulo_ph", default="Ej.: Nuevo horario de verano"))
        self.cuerpo.addWidget(self.inp_titulo)
        self.cuerpo.addWidget(_lbl(
            tr("com.f_subtitulo_auto", default="Subtítulo (automático): {u} · {f}",
               u=u.get("nombre", "—"), f=ahora), size=11, color=_CIAN))
        _excluir = u.get("id")
        self.dest_para = _CampoDestinatarios(tr("com.f_para", default="Para"), excluir_id=_excluir)
        self.dest_cc = _CampoDestinatarios(tr("com.f_cc", default="CC"), excluir_id=_excluir)
        self.dest_cco = _CampoDestinatarios(tr("com.f_cco", default="Cco"), excluir_id=_excluir)
        self.cuerpo.addWidget(self.dest_para)
        self.cuerpo.addWidget(self.dest_cc)
        self.cuerpo.addWidget(self.dest_cco)
        self.cuerpo.addWidget(_lbl(tr("com.f_cuerpo", default="Cuerpo del mensaje"), bold=True,
                                   size=12, color=_TEXT2))
        self.txt_cuerpo = _textarea(tr("com.f_cuerpo_ph", default="Escribe el mensaje para los centros…"),
                                    h=240)
        self.cuerpo.addWidget(self.txt_cuerpo)
        self.cuerpo.addWidget(_lbl(tr("com.f_adjuntos", default="Adjuntos (texto o imagen)"), bold=True,
                                   size=12, color=_TEXT2))
        self.adj = _AdjuntosWidget()
        self.cuerpo.addWidget(self.adj)
        self.cuerpo.addStretch()
        if id_borrador:
            self._precargar_borrador(id_borrador)
        pie = self.barra_pie()
        # "Adjuntar archivo" a la ESQUINA INFERIOR IZQUIERDA del pie, a la misma altura que Publicar.
        pie.addWidget(self.adj.extraer_boton(alto=46))
        pie.addStretch()
        b_borrador = _btn("📝  " + tr("com.guardar_borrador", default="GUARDAR BORRADOR"), fg=_CIAN,
                          border=_CIAN, bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=46)
        b_borrador.clicked.connect(self._guardar_borrador)
        pie.addWidget(b_borrador)
        b_prog = _btn("🕒  " + tr("com.programar_envio", default="PROGRAMAR ENVÍO"), fg=_AMBAR,
                      border=_AMBAR, bg=_BG2, hover_bg=_AMBAR, hover_fg=_BG, h=46)
        b_prog.clicked.connect(self._programar)
        pie.addWidget(b_prog)
        b_pub = _btn("✉️  " + tr("com.publicar_circ", default="Enviar mensaje"), fg=_VERDE, border=_VERDE,
                     bg=_BG2, hover_bg=_VERDE, hover_fg=_BG, h=46)
        b_pub.clicked.connect(self._publicar)
        pie.addWidget(b_pub)

    def _precargar_borrador(self, id_borrador):
        from src.services.comunicacion_interna import circulares
        d = circulares.obtener_circular(id_borrador) or {}
        self.inp_titulo.setText(d.get("titulo") or "")
        self.txt_cuerpo.setPlainText(d.get("cuerpo") or "")
        for dest in (d.get("destinatarios") or []):
            campo = {"PARA": self.dest_para, "CC": self.dest_cc, "CCO": self.dest_cco}.get(
                (dest.get("tipo") or "PARA").upper(), self.dest_para)
            nombre = dest.get("usuario_nombre") or "—"
            campo._agregar_chip({"usuario_id": dest.get("usuario_id"), "nombre": nombre}, nombre,
                                tr("com.tt_interno", default="Usuario interno"))

    def _destinatarios_combinados(self):
        return (
            [{**d, "tipo": "PARA"} for d in self.dest_para.destinatarios()]
            + [{**d, "tipo": "CC"} for d in self.dest_cc.destinatarios()]
            + [{**d, "tipo": "CCO"} for d in self.dest_cco.destinatarios()])

    def _guardar_borrador(self):
        from src.services.comunicacion_interna import circulares
        r = circulares.guardar_borrador(
            self._id_borrador, titulo=self.inp_titulo.text(), cuerpo=self.txt_cuerpo.toPlainText(),
            adjuntos=self.adj.rutas(), destinatarios=self._destinatarios_combinados())
        if r.get("ok"):
            self._id_borrador = r["id"]
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.borrador_ok", default="Borrador guardado."))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _programar(self):
        destinatarios = self._destinatarios_combinados()
        if not any((d.get("tipo") == "PARA") for d in destinatarios):
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_para", default="Debes indicar al menos un "
                                   "destinatario en «Para»."))
            return
        dlg = _FechaHoraDialog(self, titulo=tr("com.programar_t", default="PROGRAMAR ENVÍO"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        from src.services.comunicacion_interna import circulares
        r = circulares.programar(
            self._id_borrador, titulo=self.inp_titulo.text(), cuerpo=self.txt_cuerpo.toPlainText(),
            fecha_programada=dlg.resultado, destinatarios=destinatarios)
        if r.get("ok"):
            msg = tr("com.programado_ok", default="Envío programado para {f}.",
                    f=dlg.resultado.strftime("%d/%m/%Y %H:%M"))
            if r.get("externos_no_programables"):
                msg += "\n" + tr("com.programado_sin_externos",
                                 default="(los contactos externos no se incluyen en el envío "
                                         "programado: {lst})", lst=", ".join(r["externos_no_programables"]))
            QMessageBox.information(self, tr("com.ok", default="Hecho"), msg)
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _publicar(self):
        para = self.dest_para.destinatarios()
        if not para:
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_para", default="Debes indicar al menos un "
                                   "destinatario en «Para»."))
            return
        destinatarios = self._destinatarios_combinados()
        from src.services.comunicacion_interna import circulares
        if self._id_borrador:
            r = circulares.publicar_borrador(self._id_borrador, destinatarios=destinatarios,
                                             titulo=self.inp_titulo.text(),
                                             cuerpo=self.txt_cuerpo.toPlainText())
        else:
            r = circulares.crear_circular(self.inp_titulo.text(), self.txt_cuerpo.toPlainText(),
                                          adjuntos=self.adj.rutas(), destinatarios=destinatarios)
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.circ_publicada_ok",
                                       default="Mensaje publicado correctamente."))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


class _CircularViewerDialog(_DialogoBase):
    """Visor de una circular: estructura base + imágenes en línea + confirmación de lectura."""

    def __init__(self, id_circular, parent=None):
        super().__init__(tr("com.circ_titulo", default="CIRCULAR"), parent, icono="📢",
                         pantalla_completa=True)
        self._id = id_circular
        from src.services.comunicacion_interna import circulares
        self._svc = circulares
        self._data = circulares.obtener_circular(id_circular) or {}
        self._pintar()

    def _pintar(self):
        d = self._data
        # Título + subtítulo automático (creador + fecha/hora).
        self.cuerpo.addWidget(_lbl(d.get("titulo", "—"), bold=True, size=24, color=_TEXT, wrap=True))
        self.cuerpo.addWidget(_lbl(f"{d.get('creador_nombre','—')}  ·  {_fecha(d.get('creado'))}",
                                   size=13, color=_CIAN))
        sep = QFrame(); sep.setFixedHeight(2); sep.setStyleSheet(f"background:{_BORDE};border:none;")
        self.cuerpo.addWidget(sep)
        # Cuerpo del mensaje.
        self.cuerpo.addWidget(_lbl(d.get("cuerpo", "") or "", size=15, color=_TEXT, wrap=True))
        # Imágenes del emisor en línea + adjuntos de texto.
        img = _bloque_imagenes_inline(d.get("adjuntos"))
        if img:
            self.cuerpo.addWidget(img)
        docs = _bloque_adjuntos_texto(d.get("adjuntos"))
        if docs:
            self.cuerpo.addWidget(_lbl(tr("com.adjuntos_emisor", default="Adjuntos:"), bold=True,
                                       size=12, color=_TEXT2))
            self.cuerpo.addWidget(docs)
        # Confirmaciones existentes.
        confs = d.get("confirmaciones") or []
        if confs:
            self.cuerpo.addWidget(_lbl(tr("com.confirmaciones", default="CONFIRMACIONES DE LECTURA"),
                                       bold=True, size=13, color=_CIAN))
            for cf in confs:
                self.cuerpo.addWidget(self._card_confirmacion(cf))
        # Bloque de confirmación (comentario + adjuntos + botón).
        self.cuerpo.addWidget(_lbl(tr("com.tu_comentario", default="Tu comentario (opcional)"),
                                   bold=True, size=12, color=_TEXT2))
        self.txt_coment = _textarea(tr("com.tu_comentario_ph",
                                       default="Añade un comentario al confirmar la lectura…"), h=90)
        self.cuerpo.addWidget(self.txt_coment)
        self.adj = _AdjuntosWidget()
        self.cuerpo.addWidget(self.adj)
        self.cuerpo.addStretch()
        pie = self.barra_pie()
        pie.addStretch()
        b_fwd = _btn("↪  " + tr("com.reenviar", default="Reenviar"), fg=_CIAN, border=_CIAN,
                    bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=48)
        b_fwd.clicked.connect(self._reenviar)
        pie.addWidget(b_fwd)
        b_resp = _btn("✉️  " + tr("com.responder", default="Responder"), fg=_CIAN, border=_CIAN,
                     bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=48)
        b_resp.clicked.connect(self._responder_directo)
        pie.addWidget(b_resp)
        b = _btn("✔  " + tr("com.confirmar_lectura", default="Confirmar lectura"), fg=_VERDE, border=_VERDE,
                 bg=_BG2, hover_bg=_VERDE, hover_fg=_BG, h=48)
        b.clicked.connect(self._confirmar)
        pie.addWidget(b)

    def _reenviar(self):
        u = _usuario_actual()
        dlg = _ReenviarDialog(self, excluir_id=u.get("id"),
                              titulo=tr("com.reenviar_circ_t", default="REENVIAR CIRCULAR"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        r = self._svc.reenviar_circular(self._id, dlg.resultado)
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.reenviado_ok", default="Mensaje reenviado correctamente."))
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _responder_directo(self):
        """Responde con la identidad YA AUTENTICADA de la sesión de escritorio (sin el popup de
        perfil+contraseña) — reutiliza el MISMO comentario/adjuntos del formulario. «CONFIRMAR
        LECTURA» sigue intacta para el escenario de terminal compartido (reautenticación)."""
        u = _usuario_actual()
        r = self._svc.responder_circular(self._id, usuario=u, comentario=self.txt_coment.toPlainText(),
                                         adjuntos=self.adj.rutas())
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.resp_ok", default="Respuesta enviada por {u}.",
                                       u=r.get("usuario") or u.get("nombre", "—")))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _card_confirmacion(self, cf):
        c = QFrame()
        c.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}")
        v = QVBoxLayout(c)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)
        v.addWidget(_lbl(f"✔  {cf.get('usuario_nombre','—')}  ·  {_fecha(cf.get('creado'))}",
                         bold=True, size=12, color=_VERDE))
        if cf.get("comentario"):
            v.addWidget(_lbl(cf["comentario"], size=13, color=_TEXT, wrap=True))
        img = _bloque_imagenes_inline(cf.get("adjuntos"), ancho_max=360)
        if img:
            v.addWidget(img)
        docs = _bloque_adjuntos_texto(cf.get("adjuntos"))
        if docs:
            v.addWidget(docs)
        return c

    def _confirmar(self):
        dlg = _ConfirmarPerfilDialog(self, titulo=tr("com.conf_lectura_t", default="Confirmar lectura"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        nombre, pwd = dlg.resultado
        r = self._svc.confirmar_lectura(self._id, usuario_nombre=nombre, password=pwd,
                                        comentario=self.txt_coment.toPlainText(),
                                        adjuntos=self.adj.rutas())
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.conf_ok", default="Lectura confirmada por {u}.",
                                       u=r.get("usuario", nombre)))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


# ══════════════════════════════════ ENCUESTAS ══════════════════════════════════

class _PreguntaEditorWidget(QFrame):
    """Editor de UNA pregunta (compositor de encuesta): texto + tipo (opciones/texto) + opciones."""

    def __init__(self, idx, on_eliminar, parent=None):
        super().__init__(parent)
        self._on_eliminar = on_eliminar
        self.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        hd = QHBoxLayout()
        self._lbl_num = _lbl(tr("com.pregunta_n", default="Pregunta {n}", n=idx), bold=True, size=13,
                             color=_CIAN)
        hd.addWidget(self._lbl_num)
        hd.addStretch()
        self.cmb_tipo = _combo([
            ("☑  " + tr("com.tipo_opciones", default="Opciones (casillas)"), "OPCIONES"),
            ("✏️  " + tr("com.tipo_texto", default="Texto libre"), "TEXTO")])
        self.cmb_tipo.setFixedWidth(220)
        self.cmb_tipo.currentIndexChanged.connect(self._toggle_tipo)
        hd.addWidget(self.cmb_tipo)
        bx = QPushButton("🗑")
        bx.setFixedSize(52, 50)   # holgado: el emoji 🗑 se ve completo (antes 44×46 lo cortaba un poco)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                         f"border-radius:9px;font-weight:900;font-size:15px;padding:0;}}"
                         f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}")
        # Este widget vive dentro de `_EncuestaComposerDialog` (hereda de `_DialogoBase`, frameless +
        # translúcido) — mismo riesgo de sizePolicy que los botones "✕": sin esto, el reseteo del
        # filtro global de estilos puede inflar el tamaño real del botón por encima del declarado.
        _blindar_tamano_fijo(bx, 52, 50)
        # Contorno negro alrededor del emoji (sombra negra sin desplazamiento) para que resalte y se vea mejor.
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor as _QColor
        _ef = QGraphicsDropShadowEffect(bx); _ef.setBlurRadius(5); _ef.setColor(_QColor(0, 0, 0)); _ef.setOffset(0, 0)
        bx.setGraphicsEffect(_ef)
        bx.clicked.connect(lambda: self._on_eliminar(self))
        hd.addWidget(bx)
        v.addLayout(hd)
        self.inp_texto = _input(tr("com.pregunta_ph", default="Escribe la pregunta…"))
        v.addWidget(self.inp_texto)
        self.box_opciones = QWidget()
        self.box_opciones.setStyleSheet("background:transparent;")
        self._ov = QVBoxLayout(self.box_opciones)
        self._ov.setContentsMargins(0, 0, 0, 0)
        self._ov.setSpacing(6)
        self._opciones: list[QWidget] = []
        v.addWidget(self.box_opciones)
        b_add = _btn("＋  " + tr("com.add_opcion", default="Añadir opción"), fg=_CIAN, border=_BORDE, h=34)
        b_add.clicked.connect(lambda: self._add_opcion())
        self._b_add = b_add
        v.addWidget(b_add, alignment=Qt.AlignmentFlag.AlignLeft)
        self._add_opcion("")
        self._add_opcion("")
        v.addWidget(_lbl("ℹ  " + tr("com.otro_auto",
                                    default="La opción «Otro» (con texto libre) se añade automáticamente."),
                         size=11, color=_TEXT2))

    def set_numero(self, n):
        self._lbl_num.setText(tr("com.pregunta_n", default="Pregunta {n}", n=n))

    def _add_opcion(self, val=""):
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        inp = _input(tr("com.opcion_ph", default="Opción…"), val)
        inp.setFixedHeight(34)
        x = QPushButton("✕")
        x.setFixedSize(30, 30)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;padding:0;font-weight:900;}}")
        x.setProperty("sin_glow", True)
        _blindar_tamano_fijo(x, 30, 30)
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        cont._inp = inp
        fila.addWidget(inp)
        fila.addWidget(x)
        cont.setLayout(fila)
        self._ov.addWidget(cont)
        self._opciones.append(cont)

        def _quitar():
            if cont in self._opciones:
                self._opciones.remove(cont)
            cont.setParent(None)
            cont.deleteLater()
        x.clicked.connect(_quitar)

    def _toggle_tipo(self):
        es_opciones = self.cmb_tipo.currentData() == "OPCIONES"
        self.box_opciones.setVisible(es_opciones)
        self._b_add.setVisible(es_opciones)

    def cargar_datos(self, p):
        """Prefill desde una pregunta ya existente (reabrir un borrador de encuesta)."""
        self.inp_texto.setText(p.get("texto") or "")
        tipo = (p.get("tipo") or "OPCIONES").upper()
        self.cmb_tipo.setCurrentIndex(0 if tipo == "OPCIONES" else 1)
        self._toggle_tipo()
        if tipo == "OPCIONES":
            for cont in list(self._opciones):
                cont.setParent(None)
                cont.deleteLater()
            self._opciones = []
            opciones = p.get("opciones") or []
            for op in opciones:
                self._add_opcion(op.get("texto") or "")
            if not opciones:
                self._add_opcion("")
                self._add_opcion("")

    def datos(self):
        tipo = self.cmb_tipo.currentData() or "OPCIONES"
        opciones = [c._inp.text().strip() for c in self._opciones if c._inp.text().strip()]
        return {"texto": self.inp_texto.text().strip(), "tipo": tipo, "opciones": opciones}


class _EncuestaComposerDialog(_DialogoBase):
    """Compositor de una nueva encuesta — o de un BORRADOR/PROGRAMADA existente si se pasa
    `id_borrador` (preguntas ilimitadas, tipo por pregunta, texto introductorio)."""

    def __init__(self, parent=None, id_borrador=None):
        super().__init__(tr("com.enc_nueva", default="NUEVA ENCUESTA"), parent, icono="📊", alto=0.9,
                         pantalla_completa=True)
        self._id_borrador = id_borrador
        u = _usuario_actual()
        import datetime
        ahora = datetime.datetime.now().strftime("%d/%m/%Y  %H:%M")
        self.cuerpo.addWidget(_lbl(tr("com.f_titulo_enc", default="Título de la encuesta"), bold=True,
                                   size=12, color=_TEXT2))
        self.inp_titulo = _input(tr("com.f_titulo_enc_ph", default="Ej.: Satisfacción del nuevo horario"))
        self.cuerpo.addWidget(self.inp_titulo)
        self.cuerpo.addWidget(_lbl(
            tr("com.f_subtitulo_auto", default="Subtítulo (automático): {u} · {f}",
               u=u.get("nombre", "—"), f=ahora), size=11, color=_CIAN))
        _excluir = u.get("id")
        self.dest_para = _CampoDestinatarios(tr("com.f_para", default="Para"), excluir_id=_excluir)
        self.dest_cc = _CampoDestinatarios(tr("com.f_cc", default="CC"), excluir_id=_excluir)
        self.dest_cco = _CampoDestinatarios(tr("com.f_cco", default="Cco"), excluir_id=_excluir)
        self.cuerpo.addWidget(self.dest_para)
        self.cuerpo.addWidget(self.dest_cc)
        self.cuerpo.addWidget(self.dest_cco)
        self.cuerpo.addWidget(_lbl(tr("com.f_intro", default="Texto explicativo (antes de la encuesta)"),
                                   bold=True, size=12, color=_TEXT2))
        self.txt_intro = _textarea(tr("com.f_intro_ph",
                                      default="Explica el objetivo de la encuesta a los centros…"), h=90)
        self.cuerpo.addWidget(self.txt_intro)
        self.cuerpo.addWidget(_lbl(tr("com.preguntas", default="PREGUNTAS"), bold=True, size=13,
                                   color=_CIAN))
        self._box_preg = QVBoxLayout()
        self._box_preg.setSpacing(10)
        self.cuerpo.addLayout(self._box_preg)
        self._preguntas: list[_PreguntaEditorWidget] = []
        b_add = _btn("＋  " + tr("com.add_pregunta", default="Añadir pregunta"), fg=_CIAN, border=_CIAN,
                     h=40)
        b_add.clicked.connect(self._add_pregunta)
        self.cuerpo.addWidget(b_add, alignment=Qt.AlignmentFlag.AlignLeft)
        self.cuerpo.addWidget(_lbl(tr("com.f_adjuntos", default="Adjuntos (texto o imagen)"), bold=True,
                                   size=12, color=_TEXT2))
        self.adj = _AdjuntosWidget()
        self.cuerpo.addWidget(self.adj)
        self.cuerpo.addStretch()
        if id_borrador:
            self._precargar_borrador(id_borrador)
        else:
            self._add_pregunta()
        pie = self.barra_pie()
        pie.addStretch()
        b_borrador = _btn("📝  " + tr("com.guardar_borrador", default="GUARDAR BORRADOR"), fg=_CIAN,
                          border=_CIAN, bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=46)
        b_borrador.clicked.connect(self._guardar_borrador)
        pie.addWidget(b_borrador)
        b_prog = _btn("🕒  " + tr("com.programar_envio", default="PROGRAMAR ENVÍO"), fg=_AMBAR,
                      border=_AMBAR, bg=_BG2, hover_bg=_AMBAR, hover_fg=_BG, h=46)
        b_prog.clicked.connect(self._programar)
        pie.addWidget(b_prog)
        b_pub = _btn("📊  " + tr("com.publicar_enc", default="Publicar encuesta"), fg=_VERDE, border=_VERDE,
                     bg=_BG2, hover_bg=_VERDE, hover_fg=_BG, h=46)
        b_pub.clicked.connect(self._publicar)
        pie.addWidget(b_pub)

    def _precargar_borrador(self, id_borrador):
        from src.services.comunicacion_interna import encuestas
        d = encuestas.obtener_encuesta(id_borrador) or {}
        self.inp_titulo.setText(d.get("titulo") or "")
        self.txt_intro.setPlainText(d.get("intro") or "")
        for dest in (d.get("destinatarios") or []):
            campo = {"PARA": self.dest_para, "CC": self.dest_cc, "CCO": self.dest_cco}.get(
                (dest.get("tipo") or "PARA").upper(), self.dest_para)
            nombre = dest.get("usuario_nombre") or "—"
            campo._agregar_chip({"usuario_id": dest.get("usuario_id"), "nombre": nombre}, nombre,
                                tr("com.tt_interno", default="Usuario interno"))
        preguntas = d.get("preguntas") or []
        if preguntas:
            for p in preguntas:
                self._add_pregunta()
                self._preguntas[-1].cargar_datos(p)
        else:
            self._add_pregunta()

    def _add_pregunta(self):
        w = _PreguntaEditorWidget(len(self._preguntas) + 1, self._eliminar_pregunta)
        self._preguntas.append(w)
        self._box_preg.addWidget(w)

    def _eliminar_pregunta(self, w):
        if w in self._preguntas:
            self._preguntas.remove(w)
        w.setParent(None)
        w.deleteLater()
        for i, p in enumerate(self._preguntas):
            p.set_numero(i + 1)

    def _destinatarios_combinados(self):
        return (
            [{**d, "tipo": "PARA"} for d in self.dest_para.destinatarios()]
            + [{**d, "tipo": "CC"} for d in self.dest_cc.destinatarios()]
            + [{**d, "tipo": "CCO"} for d in self.dest_cco.destinatarios()])

    def _guardar_borrador(self):
        from src.services.comunicacion_interna import encuestas
        preguntas = [p.datos() for p in self._preguntas]
        r = encuestas.guardar_borrador(
            self._id_borrador, titulo=self.inp_titulo.text(), intro=self.txt_intro.toPlainText(),
            preguntas=preguntas, adjuntos=self.adj.rutas(),
            destinatarios=self._destinatarios_combinados())
        if r.get("ok"):
            self._id_borrador = r["id"]
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.borrador_ok", default="Borrador guardado."))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _programar(self):
        destinatarios = self._destinatarios_combinados()
        if not any((d.get("tipo") == "PARA") for d in destinatarios):
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_para", default="Debes indicar al menos un "
                                   "destinatario en «Para»."))
            return
        preguntas = [p.datos() for p in self._preguntas]
        if not any((p.get("texto") or "").strip() for p in preguntas):
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_pregunta", default="Añade al menos una pregunta."))
            return
        dlg = _FechaHoraDialog(self, titulo=tr("com.programar_t", default="PROGRAMAR ENVÍO"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        from src.services.comunicacion_interna import encuestas
        r = encuestas.programar(
            self._id_borrador, titulo=self.inp_titulo.text(), intro=self.txt_intro.toPlainText(),
            preguntas=preguntas, fecha_programada=dlg.resultado, destinatarios=destinatarios)
        if r.get("ok"):
            msg = tr("com.programado_ok", default="Envío programado para {f}.",
                    f=dlg.resultado.strftime("%d/%m/%Y %H:%M"))
            if r.get("externos_no_programables"):
                msg += "\n" + tr("com.programado_sin_externos",
                                 default="(los contactos externos no se incluyen en el envío "
                                         "programado: {lst})", lst=", ".join(r["externos_no_programables"]))
            QMessageBox.information(self, tr("com.ok", default="Hecho"), msg)
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _publicar(self):
        para = self.dest_para.destinatarios()
        if not para:
            QMessageBox.warning(self, tr("com.error", default="Aviso"),
                                tr("com.falta_para", default="Debes indicar al menos un "
                                   "destinatario en «Para»."))
            return
        destinatarios = self._destinatarios_combinados()
        preguntas = [p.datos() for p in self._preguntas]
        from src.services.comunicacion_interna import encuestas
        if self._id_borrador:
            r = encuestas.publicar_borrador(self._id_borrador, destinatarios=destinatarios,
                                            titulo=self.inp_titulo.text(),
                                            intro=self.txt_intro.toPlainText(), preguntas=preguntas)
        else:
            r = encuestas.crear_encuesta(self.inp_titulo.text(), self.txt_intro.toPlainText(), preguntas,
                                         adjuntos=self.adj.rutas(), destinatarios=destinatarios)
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.enc_publicada_ok",
                                       default="Encuesta publicada correctamente."))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


class _EncuestaViewerDialog(_DialogoBase):
    """Visor/relleno de una encuesta: preguntas con casillas u opción de texto + «Otro»."""

    def __init__(self, id_encuesta, parent=None):
        super().__init__(tr("com.enc_titulo", default="ENCUESTA"), parent, icono="📊", alto=0.9,
                         pantalla_completa=True)
        self._id = id_encuesta
        from src.services.comunicacion_interna import encuestas
        self._svc = encuestas
        self._data = encuestas.obtener_encuesta(id_encuesta) or {}
        self._controles = {}
        self._pintar()

    def _pintar(self):
        d = self._data
        self.cuerpo.addWidget(_lbl(d.get("titulo", "—"), bold=True, size=24, color=_TEXT, wrap=True))
        self.cuerpo.addWidget(_lbl(f"{d.get('creador_nombre','—')}  ·  {_fecha(d.get('creado'))}",
                                   size=13, color=_CIAN))
        sep = QFrame(); sep.setFixedHeight(2); sep.setStyleSheet(f"background:{_BORDE};border:none;")
        self.cuerpo.addWidget(sep)
        if d.get("intro"):
            self.cuerpo.addWidget(_lbl(d["intro"], size=15, color=_TEXT, wrap=True))
        img = _bloque_imagenes_inline(d.get("adjuntos"))
        if img:
            self.cuerpo.addWidget(img)
        docs = _bloque_adjuntos_texto(d.get("adjuntos"))
        if docs:
            self.cuerpo.addWidget(docs)
        for i, p in enumerate(d.get("preguntas") or []):
            self.cuerpo.addWidget(self._card_pregunta(i + 1, p))
        resp = d.get("respuestas") or []
        if resp:
            self.cuerpo.addWidget(_lbl(tr("com.respuestas_recibidas", default="RESPUESTAS RECIBIDAS ({n})",
                                          n=len(resp)), bold=True, size=13, color=_CIAN))
            for r in resp:
                self.cuerpo.addWidget(self._card_respuesta(r))
        self.cuerpo.addWidget(_lbl(tr("com.tu_comentario", default="Tu comentario (opcional)"), bold=True,
                                   size=12, color=_TEXT2))
        self.txt_coment = _textarea(tr("com.tu_comentario_ph2",
                                       default="Añade un comentario junto a tu respuesta…"), h=90)
        self.cuerpo.addWidget(self.txt_coment)
        self.adj = _AdjuntosWidget()
        self.cuerpo.addWidget(self.adj)
        self.cuerpo.addStretch()
        pie = self.barra_pie()
        pie.addStretch()
        b_fwd = _btn("↪  " + tr("com.reenviar", default="Reenviar"), fg=_CIAN, border=_CIAN,
                    bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=48)
        b_fwd.clicked.connect(self._reenviar)
        pie.addWidget(b_fwd)
        b_resp = _btn("✉️  " + tr("com.responder", default="Responder"), fg=_CIAN, border=_CIAN,
                     bg=_BG2, hover_bg=_CIAN, hover_fg=_BG, h=48)
        b_resp.clicked.connect(self._responder_directo)
        pie.addWidget(b_resp)
        b = _btn("📨  " + tr("com.enviar_respuesta", default="Enviar respuesta"), fg=_VERDE, border=_VERDE,
                 bg=_BG2, hover_bg=_VERDE, hover_fg=_BG, h=48)
        b.clicked.connect(self._enviar)
        pie.addWidget(b)

    def _reenviar(self):
        u = _usuario_actual()
        dlg = _ReenviarDialog(self, excluir_id=u.get("id"),
                              titulo=tr("com.reenviar_enc_t", default="REENVIAR ENCUESTA"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        r = self._svc.reenviar_encuesta(self._id, dlg.resultado)
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.reenviado_ok", default="Mensaje reenviado correctamente."))
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _card_pregunta(self, num, p):
        c = QFrame()
        c.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}")
        v = QVBoxLayout(c)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        v.addWidget(_lbl(f"{num}.  {p.get('texto','')}", bold=True, size=15, color=_TEXT, wrap=True))
        ctrl = {"tipo": p.get("tipo"), "checks": [], "otro_cb": None, "otro_inp": None, "texto": None}
        if p.get("tipo") == "TEXTO":
            inp = _textarea(tr("com.respuesta_ph", default="Escribe tu respuesta…"), h=70)
            v.addWidget(inp)
            ctrl["texto"] = inp
        else:
            for op in (p.get("opciones") or []):
                cb = QCheckBox(op.get("texto", ""))
                cb.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-size:14px;font-family:'{_FONT}';spacing:8px;}}"
                                 f"QCheckBox::indicator{{width:20px;height:20px;border:2px solid {_BORDE};"
                                 f"border-radius:5px;background:{_BG};}}"
                                 f"QCheckBox::indicator:checked{{background:{_CIAN};border-color:{_CIAN};}}")
                v.addWidget(cb)
                ctrl["checks"].append((op.get("id"), cb))
            otro_cb = QCheckBox(tr("com.otro", default="Otro (especificar)"))
            otro_cb.setStyleSheet(f"QCheckBox{{color:{_AMBAR};font-size:14px;font-family:'{_FONT}';spacing:8px;}}"
                                  f"QCheckBox::indicator{{width:20px;height:20px;border:2px solid {_BORDE};"
                                  f"border-radius:5px;background:{_BG};}}"
                                  f"QCheckBox::indicator:checked{{background:{_AMBAR};border-color:{_AMBAR};}}")
            v.addWidget(otro_cb)
            otro_inp = _input(tr("com.otro_ph", default="Escribe tu respuesta…"))
            otro_inp.setVisible(False)
            otro_cb.toggled.connect(otro_inp.setVisible)
            v.addWidget(otro_inp)
            ctrl["otro_cb"] = otro_cb
            ctrl["otro_inp"] = otro_inp
        self._controles[p.get("id")] = ctrl
        return c

    def _card_respuesta(self, r):
        c = QFrame()
        c.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}")
        v = QVBoxLayout(c)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(3)
        v.addWidget(_lbl(f"📨  {r.get('usuario_nombre','—')}  ·  {_fecha(r.get('creado'))}", bold=True,
                         size=12, color=_VERDE))
        opts = self._map_opciones()
        for it in (r.get("items") or []):
            if it.get("id_opcion"):
                txt = opts.get(it["id_opcion"], "—")
            else:
                txt = it.get("texto", "")
            if txt:
                v.addWidget(_lbl(f"• {txt}", size=12, color=_TEXT, wrap=True))
        if r.get("comentario"):
            v.addWidget(_lbl("💬 " + r["comentario"], size=12, color=_TEXT2, wrap=True))
        docs = _bloque_adjuntos_texto(r.get("adjuntos"))
        if docs:
            v.addWidget(docs)
        img = _bloque_imagenes_inline(r.get("adjuntos"), ancho_max=340)
        if img:
            v.addWidget(img)
        return c

    def _map_opciones(self):
        m = {}
        for p in (self._data.get("preguntas") or []):
            for op in (p.get("opciones") or []):
                m[op.get("id")] = op.get("texto")
        return m

    def _recolectar_respuestas(self):
        """Lee los controles de respuesta ya pintados (`_card_pregunta`) — factorizado para que
        tanto «ENVIAR RESPUESTA» (perfil+contraseña) como «Responder» (identidad ya autenticada,
        sin contraseña) reutilicen la MISMA recogida de datos, sin reconstruir la UI dos veces."""
        respuestas = {}
        for pid, ctrl in self._controles.items():
            entry = {"opciones": [], "otro": "", "texto": ""}
            if ctrl["tipo"] == "TEXTO":
                entry["texto"] = ctrl["texto"].toPlainText() if ctrl["texto"] else ""
            else:
                for id_op, cb in ctrl["checks"]:
                    if cb.isChecked():
                        entry["opciones"].append(id_op)
                if ctrl["otro_cb"] and ctrl["otro_cb"].isChecked():
                    entry["otro"] = ctrl["otro_inp"].text() if ctrl["otro_inp"] else ""
            respuestas[pid] = entry
        return respuestas

    def _enviar(self):
        respuestas = self._recolectar_respuestas()
        dlg = _ConfirmarPerfilDialog(self, titulo=tr("com.enviar_resp_t", default="Enviar respuesta"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        nombre, pwd = dlg.resultado
        r = self._svc.responder_encuesta(self._id, usuario_nombre=nombre, password=pwd,
                                         respuestas=respuestas, comentario=self.txt_coment.toPlainText(),
                                         adjuntos=self.adj.rutas())
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.resp_ok", default="Respuesta enviada por {u}.",
                                       u=r.get("usuario", nombre)))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))

    def _responder_directo(self):
        """«Responder»: identidad YA AUTENTICADA de la sesión de escritorio, sin el popup de
        perfil+contraseña — reutiliza EXACTAMENTE la misma recogida de respuestas que «ENVIAR
        RESPUESTA» (`_recolectar_respuestas`), solo cambia a qué función de servicio se enruta."""
        u = _usuario_actual()
        respuestas = self._recolectar_respuestas()
        r = self._svc.responder_encuesta_autenticado(
            self._id, usuario=u, respuestas=respuestas, comentario=self.txt_coment.toPlainText(),
            adjuntos=self.adj.rutas())
        if r.get("ok"):
            QMessageBox.information(self, tr("com.ok", default="Hecho"),
                                    tr("com.resp_ok", default="Respuesta enviada por {u}.",
                                       u=r.get("usuario") or u.get("nombre", "—")))
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


# ══════════════════════════════════ BANDEJA ══════════════════════════════════

class BandejaComunicacionDialog(_DialogoBase):
    """Bandeja principal: recibe todas las circulares y encuestas de la empresa."""

    def __init__(self, parent=None):
        super().__init__(tr("com.bandeja", default="BANDEJA INTERNA · CIRCULARES Y ENCUESTAS"),
                         parent, icono="📥", alto=0.86)
        acc = QHBoxLayout()
        acc.setSpacing(10)
        b1 = _btn("📢  " + tr("com.nueva_circ", default="NUEVA CIRCULAR"), fg=_CIAN, border=_CIAN)
        b1.clicked.connect(self._nueva_circular)
        b2 = _btn("📊  " + tr("com.nueva_enc", default="NUEVA ENCUESTA"), fg=_CIAN, border=_CIAN)
        b2.clicked.connect(self._nueva_encuesta)
        b3 = _btn("🔄  " + tr("com.actualizar", default="ACTUALIZAR"), fg=_TEXT2, border=_BORDE)
        b3.clicked.connect(self.refrescar)
        acc.addWidget(b1); acc.addWidget(b2); acc.addStretch(); acc.addWidget(b3)
        self.cuerpo.addLayout(acc)
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels([
            tr("com.col_tipo", default="TIPO"),
            tr("com.col_titulo", default="TÍTULO"),
            tr("com.col_emisor", default="EMISOR"),
            tr("com.col_fecha", default="FECHA"),
            tr("com.col_respuestas", default="RESP./CONF."),
        ])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(46)
        from PyQt6.QtWidgets import QHeaderView
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 130); hh.resizeSection(2, 160); hh.resizeSection(3, 150); hh.resizeSection(4, 120)
        self.tabla.setStyleSheet(
            f"QTableWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};border-radius:12px;"
            f"gridline-color:{_BORDE};font-family:'{_FONT}';font-size:13px;outline:none;}}"
            f"QTableWidget::item{{padding:6px 8px;}}"
            f"QTableWidget::item:selected{{background:#00FFC622;color:white;}}"
            f"QHeaderView::section{{background:{_BG};color:{_CIAN};border:none;"
            f"border-bottom:2px solid {_BORDE};padding:8px;font-weight:900;font-size:11px;}}"
            f"QHeaderView::section:first{{border-top-left-radius:10px;}}"
            f"QHeaderView::section:last{{border-top-right-radius:10px;}}"
            f"QHeaderView::section:hover{{background:{_CIAN};color:{_BG};}}" + _scroll_qss())
        self.tabla.cellDoubleClicked.connect(self._abrir_fila)
        self.cuerpo.addWidget(self.tabla, 1)
        self.lbl_info = _lbl("", size=11, color=_TEXT2)
        self.cuerpo.addWidget(self.lbl_info)
        self._filas = []
        self.refrescar()

    def refrescar(self):
        from src.services.comunicacion_interna import circulares, encuestas
        u = _usuario_actual()
        uid = u.get("id")
        self._filas = []
        for c in circulares.listar_circulares(usuario_id=uid):
            self._filas.append(("CIRCULAR", c))
        for e in encuestas.listar_encuestas(usuario_id=uid):
            self._filas.append(("ENCUESTA", e))
        self._filas.sort(key=lambda t: str(t[1].get("creado") or ""), reverse=True)
        self.tabla.setRowCount(len(self._filas))
        from PyQt6.QtGui import QColor
        for row, (tipo, d) in enumerate(self._filas):
            icono = "📢  Circular" if tipo == "CIRCULAR" else "📊  Encuesta"
            it_tipo = QTableWidgetItem(icono)
            it_tipo.setForeground(QColor(_CIAN if tipo == "CIRCULAR" else _AMBAR))
            self.tabla.setItem(row, 0, it_tipo)
            self.tabla.setItem(row, 1, QTableWidgetItem(d.get("titulo", "—")))
            self.tabla.setItem(row, 2, QTableWidgetItem(d.get("creador_nombre", "—")))
            self.tabla.setItem(row, 3, QTableWidgetItem(_fecha(d.get("creado"))))
            n = d.get("confirmaciones", d.get("respuestas", 0))
            it_n = QTableWidgetItem(str(n))
            it_n.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 4, it_n)
        self.lbl_info.setText(tr("com.total", default="{n} elementos en la bandeja", n=len(self._filas)))

    def _abrir_fila(self, row, _col):
        if not (0 <= row < len(self._filas)):
            return
        from src.gui.transiciones import abrir_dialogo_deslizante
        tipo, d = self._filas[row]
        dlg = _CircularViewerDialog(d["id"], self) if tipo == "CIRCULAR" else _EncuestaViewerDialog(d["id"], self)
        abrir_dialogo_deslizante(dlg, self)
        self.refrescar()

    def _nueva_circular(self):
        from src.gui.transiciones import abrir_dialogo_deslizante
        if abrir_dialogo_deslizante(_CircularComposerDialog(self), self) == QDialog.DialogCode.Accepted:
            self.refrescar()

    def _nueva_encuesta(self):
        from src.gui.transiciones import abrir_dialogo_deslizante
        if abrir_dialogo_deslizante(_EncuestaComposerDialog(self), self) == QDialog.DialogCode.Accepted:
            self.refrescar()
