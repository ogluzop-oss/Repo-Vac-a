"""
Smart Manager - Global style system

Search keywords:
- SECTION TOKENS
- SECTION HELPERS
- SECTION FEEDBACK HELPERS
- SECTION FILTERS
- SECTION PUBLIC API
- SECTION QSS ROOT
- SECTION QSS SIDEBAR
- SECTION QSS LOGIN
- SECTION QSS INPUTS
- SECTION QSS BUTTONS
- SECTION QSS TABLES
- SECTION QSS DIALOGS
- SECTION QSS SCANNER
"""

import ctypes
import os
import re
import sys
from ctypes import wintypes

# Cyan dropdown-arrow icon (same triangle look as the empleado combo).
# QSS url() requires forward slashes even on Windows.
_ARROW_ICON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "combo_arrow.png"
).replace("\\", "/")

try:
    from PyQt6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QFrame,
        QGraphicsDropShadowEffect,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListView,
        QListWidget,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSlider,
        QStyledItemDelegate,
        QStyleFactory,
        QTabBar,
        QTableView,
        QTableWidget,
        QTextEdit,
        QTimeEdit,
        QToolButton,
        QTreeView,
        QTreeWidget,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QEvent = None
    QObject = object
    QColor = None
    QRectF = None
    QSize = None
    Qt = None
    QTimer = None
    QFont = None
    QPainter = None
    QPainterPath = None
    QPalette = None
    QPen = None
    QAbstractButton = None
    QAbstractItemView = None
    QAbstractSpinBox = None
    QCheckBox = None
    QComboBox = None
    QDateEdit = None
    QDialog = None
    QDialogButtonBox = None
    QFrame = None
    QGroupBox = None
    QGraphicsDropShadowEffect = None
    QHeaderView = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QListView = None
    QListWidget = None
    QMenu = None
    QMessageBox = None
    QPlainTextEdit = None
    QPushButton = None
    QRadioButton = None
    QInputDialog = None
    QScrollArea = None
    QSlider = None
    QStyledItemDelegate = None
    QStyleFactory = None
    QTabBar = None
    QTableView = None
    QTableWidget = None
    QTextEdit = None
    QTimeEdit = None
    QToolButton = None
    QTreeView = None
    QTreeWidget = None
    QVBoxLayout = None
    QWidget = None


# ============================================================
# BLOQUE CABECERAS DE TABLA — "Solo primera letra" (no TODO MAYÚSCULAS)
# ============================================================
# Petición explícita: ninguna cabecera de tabla de la app debe ir en mayúsculas completas, solo su
# primera letra ("ID TRASPASO" -> "Id traspaso"). Las ~70 llamadas a `setHorizontalHeaderLabels`/
# `setHorizontalHeaderItem`/`setHeaderLabels` repartidas por decenas de pantallas siguen escribiendo
# el texto que siempre escribieron (muchas, en mayúsculas, a propósito en su momento) — en vez de
# editar cada pantalla una a una (frágil, fácil de dejar alguna desactualizada en el futuro), se
# parchea UNA VEZ, aquí, el método real de Qt que todas acaban llamando: cualquier texto de cabecera
# que pase por estos métodos se re-capitaliza automáticamente, para SIEMPRE, sin tocar cada pantalla.


def _primera_mayuscula_resto_minuscula(texto):
    """'ID TRASPASO' -> 'Id traspaso' ("id" no es una sigla reconocida). Reconoce las SIGLAS del
    dominio (mismo catálogo `utils.texto.SIGLAS` que ya usa el sistema de i18n, p. ej. "EAN"/"IVA"/
    "SKU"): esas palabras conservan SIEMPRE sus mayúsculas completas en vez de perderlas — por
    ejemplo 'EAN' -> 'EAN' (antes se perdía: 'Ean') e 'IVA incluido' -> 'IVA incluido'. Ignora
    cualquier carácter inicial no alfabético (iconos/espacios) al decidir cuál es "la primera
    letra"; no toca nada si no hay texto o no es string."""
    if not isinstance(texto, str) or not texto:
        return texto
    try:
        from src.utils.texto import SIGLAS
    except Exception:
        SIGLAS = ()
    palabras = texto.split(" ")
    resultado = []
    pendiente_primera = True
    for palabra in palabras:
        if palabra.lower() in SIGLAS:
            resultado.append(palabra.upper())
            if any(ch.isalpha() for ch in palabra):
                pendiente_primera = False
            continue
        if pendiente_primera and any(ch.isalpha() for ch in palabra):
            minuscula = palabra.lower()
            nueva = []
            mayusculada = False
            for ch in minuscula:
                if not mayusculada and ch.isalpha():
                    nueva.append(ch.upper())
                    mayusculada = True
                else:
                    nueva.append(ch)
            resultado.append("".join(nueva))
            pendiente_primera = False
        else:
            resultado.append(palabra.lower())
    return " ".join(resultado)


def _parchear_cabeceras_tabla():
    if QTableWidget is not None:
        _orig_labels = QTableWidget.setHorizontalHeaderLabels

        def _labels_parcheado(self, labels):
            return _orig_labels(self, [_primera_mayuscula_resto_minuscula(l) for l in (labels or [])])
        QTableWidget.setHorizontalHeaderLabels = _labels_parcheado

        _orig_item = QTableWidget.setHorizontalHeaderItem

        def _item_parcheado(self, columna, item):
            try:
                if item is not None:
                    item.setText(_primera_mayuscula_resto_minuscula(item.text()))
            except Exception:
                pass
            return _orig_item(self, columna, item)
        QTableWidget.setHorizontalHeaderItem = _item_parcheado

    if QTreeWidget is not None:
        _orig_tree_labels = QTreeWidget.setHeaderLabels

        def _tree_labels_parcheado(self, labels):
            return _orig_tree_labels(self, [_primera_mayuscula_resto_minuscula(l) for l in (labels or [])])
        QTreeWidget.setHeaderLabels = _tree_labels_parcheado


try:
    _parchear_cabeceras_tabla()
except Exception:
    pass


# ============================================================
# BLOQUE TOKENS Y CONSTANTES DE ESTILO
# ============================================================
FUENTE_APP = "Segoe UI"
COLOR_CIAN = "#00FFC6"
COLOR_CIAN_HOVER = "#00E6B2"
COLOR_CIAN_PRESION = "#00C79A"
COLOR_VERDE_OK = "#1ED760"
COLOR_VERDE_OK_HOVER = "#16C955"
COLOR_VERDE_OK_PRESION = "#12A845"
COLOR_FONDO_APP = "#0E1117"
COLOR_FONDO_APP_SECUNDARIO = "#10151C"
COLOR_FONDO_SIDEBAR = "#111418"
COLOR_FONDO_WIDGET = "#161B22"
COLOR_GRIS_PANEL = "#1A1D23"
COLOR_GRIS_HOVER = "#21262D"
COLOR_GRIS_SUAVE = "#2A313C"
COLOR_GRIS_NEUTRO = "#5B6470"
COLOR_GRIS_NEUTRO_HOVER = "#6D7785"
COLOR_GRIS_NEUTRO_PRESION = "#4C5460"
COLOR_NEGRO_PANEL = "#05070A"
COLOR_BORDE = "#30363D"
COLOR_BORDE_SIDEBAR = "#1C2128"
COLOR_TEXTO_PRINCIPAL = "#FFFFFF"
COLOR_TEXTO_SECUNDARIO = "#8B949E"
COLOR_TEXTO_MUTED = "#4B5563"
COLOR_ROJO_ERROR = "#F85149"
COLOR_ROJO_HOVER = "#FF6E67"
COLOR_ROJO_PRESION = "#D63F38"
COLOR_AMBAR = "#F1C40F"

# Colores semánticos de acción (para theming; por defecto = aspecto actual).
COLOR_ACCION_TEXTO = "#0E1117"
COLOR_CANCELAR_TEXTO = "#FFFFFF"
COLOR_CONFIRMAR_TEXTO = "#0E1117"
COLOR_RETORNO = "#00FFC6"
COLOR_RETORNO_TEXTO = "#0E1117"

# ── TEMA PERSONALIZABLE (UX) ─────────────────────────────────────────────────
# Se carga al ARRANQUE desde src/utils/tema.py (JSON app-wide). Los cambios de color requieren
# reiniciar la app para verse (así lo espera el usuario). A prueba de fallos: si algo falla, se
# mantienen los valores por defecto (turquesa + azul oscuro).
def _tema_shade(hex_color, factor):
    """Aclara (factor>1) u oscurece (factor<1) un color #RRGGBB. Best-effort."""
    try:
        s = hex_color.lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
        r, g, b = (max(0, min(255, round(v * factor))) for v in (r, g, b))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


try:
    from src.utils import tema as _tema_mod
    _T = _tema_mod.cargar()
    COLOR_FONDO_APP = _T.get("fondo_app", COLOR_FONDO_APP)
    # Botones/tablas de acción = acento (COLOR_CIAN) + su texto.
    COLOR_CIAN = _T.get("accion_bg", COLOR_CIAN)
    COLOR_CIAN_HOVER = _tema_shade(COLOR_CIAN, 0.90)
    COLOR_CIAN_PRESION = _tema_shade(COLOR_CIAN, 0.78)
    COLOR_ACCION_TEXTO = _T.get("accion_texto", COLOR_ACCION_TEXTO)
    # Cancelar (rojo) + texto.
    COLOR_ROJO_ERROR = _T.get("cancelar_bg", COLOR_ROJO_ERROR)
    COLOR_ROJO_HOVER = _tema_shade(COLOR_ROJO_ERROR, 1.12)
    COLOR_ROJO_PRESION = _tema_shade(COLOR_ROJO_ERROR, 0.85)
    COLOR_CANCELAR_TEXTO = _T.get("cancelar_texto", COLOR_CANCELAR_TEXTO)
    # Confirmar / avanzar (verde) + texto.
    COLOR_VERDE_OK = _T.get("confirmar_bg", COLOR_VERDE_OK)
    COLOR_VERDE_OK_HOVER = _tema_shade(COLOR_VERDE_OK, 0.92)
    COLOR_VERDE_OK_PRESION = _tema_shade(COLOR_VERDE_OK, 0.80)
    COLOR_CONFIRMAR_TEXTO = _T.get("confirmar_texto", COLOR_CONFIRMAR_TEXTO)
    # Retorno + texto.
    COLOR_RETORNO = _T.get("retorno_bg", COLOR_RETORNO)
    COLOR_RETORNO_TEXTO = _T.get("retorno_texto", COLOR_RETORNO_TEXTO)
except Exception:
    pass

RADIO_XS = "8px"
RADIO_SM = "10px"
RADIO_MD = "12px"
RADIO_LG = "16px"
RADIO_XL = "20px"
RADIO_XXL = "24px"
RADIO_SCANNER = "30px"
RADIO_TABLAS = "20px"

_APP_FILTER = None


# ============================================================
# BLOQUE HELPERS INTERNOS
# ============================================================
def _safe_instance(widget, klass):
    return klass is not None and widget is not None and isinstance(widget, klass)


# ============================================================
# BLOQUE TECLADO TÁCTIL EN PANTALLA
# ============================================================
# Petición explícita: SOLO en un dispositivo con pantalla táctil Y SIN teclado físico conectado
# AHORA MISMO, al enfocar cualquier campo de texto/búsqueda debe aparecer el teclado en pantalla de
# Windows. "¿Hay teclado físico?" no tiene una API Win32 100% fiable por sí sola — ni
# `GetKeyboardType` (devuelve un valor genérico exista o no el periférico) ni
# `SM_CONVERTIBLESLATEMODE` por sí solo (pensado para 2-en-1 convertibles; en un portátil NORMAL
# con pantalla táctil pero teclado fijo, su valor por defecto es ambiguo según la versión de
# Windows — fiarse solo de él daría falsos positivos y abriría el teclado sobre un portátil normal
# con teclado). Se combina con Raw Input (`GetRawInputDeviceList`), que enumera los dispositivos
# HID REALMENTE conectados en este instante — si hay algún `RIM_TYPEKEYBOARD`, hay teclado físico,
# punto. Ante cualquier fallo de detección se asume "SÍ hay teclado" (no mostrar nada): el coste de
# un falso negativo (el usuario toca el botón de teclado propio de Windows) es mucho menor que el
# de un falso positivo (el teclado en pantalla apareciendo sobre un puesto de oficina normal).

_SM_DIGITIZER = 94
_NID_READY = 0x80
_NID_INTEGRATED_TOUCH = 0x01
_NID_EXTERNAL_TOUCH = 0x02
_RIM_TYPEKEYBOARD = 1


class _RawInputDeviceList(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


def _hay_teclado_fisico_conectado():
    """True/False si Raw Input puede enumerar los dispositivos HID conectados; None si la
    detección falla (SO distinto de Windows, o error de la API) — nunca se asume nada en ese caso."""
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        get_list = user32.GetRawInputDeviceList
        get_list.restype = wintypes.UINT
        tam = ctypes.sizeof(_RawInputDeviceList)
        conteo = wintypes.UINT(0)
        if get_list(None, ctypes.byref(conteo), tam) != 0:
            return None
        if conteo.value == 0:
            return False
        buf = (_RawInputDeviceList * conteo.value)()
        n = get_list(buf, ctypes.byref(conteo), tam)
        if n in (0, wintypes.UINT(-1).value):
            return None
        return any(d.dwType == _RIM_TYPEKEYBOARD for d in buf[:n])
    except Exception:
        return None


def _dispositivo_tactil_sin_teclado() -> bool:
    """True solo si el equipo tiene pantalla táctil Y, ahora mismo, ningún teclado físico
    conectado (ver bloque de arriba). Degradable: False en cualquier caso dudoso o no-Windows."""
    if sys.platform != "win32":
        return False
    try:
        digitizer = ctypes.windll.user32.GetSystemMetrics(_SM_DIGITIZER)
        tiene_tactil = bool(digitizer & _NID_READY) and bool(
            digitizer & (_NID_INTEGRATED_TOUCH | _NID_EXTERNAL_TOUCH)
        )
        if not tiene_tactil:
            return False
        hay_teclado = _hay_teclado_fisico_conectado()
        if hay_teclado is None:
            return False
        return not hay_teclado
    except Exception:
        return False


def _abrir_teclado_en_pantalla():
    """Lanza el teclado táctil nativo de Windows (TabTip.exe) — proceso único: si ya está abierto,
    relanzarlo simplemente lo trae al frente. Degradable (SO distinto de Windows, ejecutable
    ausente, o fallo de lanzamiento): nunca interrumpe el flujo normal de la app."""
    if sys.platform != "win32":
        return
    try:
        import subprocess
        base = os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files")
        ruta = os.path.join(base, "microsoft shared", "ink", "TabTip.exe")
        subprocess.Popen([ruta])
    except Exception:
        pass


def _normalize_text(value):
    text = str(value or "").strip().lower()
    replacements = str.maketrans(
        {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    )
    return text.translate(replacements)


def _repolish(widget):
    if widget is None:
        return
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except Exception:
        pass


# ============================================================
# BLOQUE FEEDBACK Y PLANTILLAS DE WIDGETS
# ============================================================


def repolish_widget(widget):
    """Fuerza reaplicación de QSS tras cambiar propiedades dinámicas (p. ej. flashHighlight)."""
    _repolish(widget)


def feedback_lineedit_exito(widget, duracion_ms=1200):
    """Resalta temporalmente un QLineEdit con borde neón (p. ej. tras escaneo). Requiere objectName input_buscador."""
    if widget is None:
        return
    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return

    widget.setProperty("flashHighlight", True)
    _repolish(widget)

    def _limpiar():
        widget.setProperty("flashHighlight", False)
        _repolish(widget)

    QTimer.singleShot(int(duracion_ms), _limpiar)


def feedback_frame_item_resaltado(frame, duracion_ms=500):
    """Borde neón temporal en filas item_frame_articulo / item_frame_logistico."""
    if frame is None:
        return
    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return

    frame.setProperty("flashHighlight", True)
    _repolish(frame)

    def _limpiar():
        frame.setProperty("flashHighlight", False)
        _repolish(frame)

    QTimer.singleShot(int(duracion_ms), _limpiar)


def construir_plantilla_camara(
    dialogo,
    *,
    titulo="VISIÓN - ESCÁNER",
    texto_video="PANEL DE ESCANEO\n\nPulse 'INICIAR' para activar la cámara",
    estado_inicial="Estado: En espera de acción",
    texto_boton_primario="INICIAR ESCANEO",
    texto_boton_cancelar="ABORTAR OPERACIÓN",
    ancho=650,
    alto=600,
    ancho_video=580,
    alto_video=330,
    mostrar_boton_primario=True,
    object_name_dialog="scanner_dialog",
    object_name_frame="cuerpo_ventana_scan",
):
    """
    Plantilla universal para ventanas de cámara.
    Devuelve referencias a widgets para que cada módulo personalice su lógica.
    """
    if dialogo is None or Qt is None:
        return {}

    dialogo.setObjectName(object_name_dialog)
    dialogo.setFixedSize(int(ancho), int(alto))
    dialogo.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    main_frame = QFrame(dialogo)
    main_frame.setObjectName(object_name_frame)
    main_frame.setGeometry(0, 0, int(ancho), int(alto))

    layout = QVBoxLayout(main_frame)
    layout.setContentsMargins(30, 30, 30, 30)
    layout.setSpacing(15)

    lbl_titulo = QLabel(str(titulo))
    lbl_titulo.setObjectName("titulo_scan")
    lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_titulo)

    lbl_video = QLabel(str(texto_video))
    lbl_video.setObjectName("feed_video")
    lbl_video.setProperty("activo", False)
    lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl_video.setFixedSize(int(ancho_video), int(alto_video))
    lbl_video.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lbl_video.setScaledContents(False)
    layout.addWidget(lbl_video, alignment=Qt.AlignmentFlag.AlignCenter)

    lbl_status = QLabel(str(estado_inicial))
    lbl_status.setObjectName("scanner_status")
    lbl_status.setProperty("estado", "idle")
    lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_status)

    btn_primario = QPushButton(str(texto_boton_primario))
    btn_primario.setObjectName("btn_primario")
    btn_primario.setFixedHeight(55)
    btn_primario.setVisible(bool(mostrar_boton_primario))
    layout.addWidget(btn_primario)

    btn_cancelar = QPushButton(str(texto_boton_cancelar))
    btn_cancelar.setObjectName("btn_abortar_scan")
    btn_cancelar.setFixedHeight(45)
    layout.addWidget(btn_cancelar)

    for widget in (lbl_titulo, lbl_video, lbl_status, btn_primario, btn_cancelar):
        _set_widget_cursor(widget)
        _apply_font(widget)
        _set_widget_background_flag(widget)
        _repolish(widget)

    return {
        "main_frame": main_frame,
        "layout": layout,
        "lbl_titulo": lbl_titulo,
        "lbl_video": lbl_video,
        "lbl_status": lbl_status,
        "btn_primario": btn_primario,
        "btn_cancelar": btn_cancelar,
    }


def _mascara_solo_esquinas(w, h, r, grosor=4):
    """Región (QRegion) reducida a un fino anillo de `grosor` px por todo el perímetro + los 4
    cuadrados de esquina de lado `r` — exactamente el área que `_CornerCover` PINTA (el relleno de
    esquina + el trazo de 2px del borde neón), nada más.

    Antes, `_CornerCover` reclamaba el RECTÁNGULO COMPLETO del contenedor como área del widget (aun
    pintando solo las esquinas) y confiaba en `WA_TransparentForMouseEvents` para dejar pasar el clic
    al widget de debajo. Eso falla en la app real cuando Qt promueve este widget a una ventana nativa
    propia (motivo observado: aparece como HWND nativo distinto — clase `Qt692QWindowIcon` — del
    proceso propio, por delante en el orden Z real de Windows): `WA_TransparentForMouseEvents` no
    reencamina entonces el clic al widget de debajo por Z-order, sino que Qt simplemente lo propaga
    hacia los ANTEPASADOS del propio `_CornerCover` (contenedor → página → stack → ventana), sin que
    ninguno lo consuma — los botones de la tabla (MODIFICAR/ELIMINAR/FOTO en Mermas, y cualquier botón
    de cualquier tabla que use esta plantilla) dejan de responder a NINGÚN clic real, aunque se sigan
    viendo y el hit-testing puramente en software de Qt (`QApplication.widgetAt`) los siga resolviendo
    bien. Reproducido de forma determinista con diagnóstico real (WindowFromPoint + widgetAt) en la app
    en ejecución, no solo en pruebas headless.

    Solución: enmascarar el widget para que su área real (pintado Y recepción de eventos, incluida la
    de una eventual ventana nativa) sea SOLO el anillo+esquinas que de verdad pinta — el resto del
    contenedor (donde vive el contenido real de la tabla) queda sin ninguna superficie de este overlay
    encima, así que un clic ahí llega siempre al widget real, pase lo que pase con su ciclo de vida
    nativo."""
    from PyQt6.QtGui import QRegion

    if w <= 0 or h <= 0:
        return QRegion()
    r = max(0, min(int(r), w // 2, h // 2))
    g = max(1, min(grosor, w // 2, h // 2))
    exterior = QRegion(0, 0, w, h)
    interior = QRegion(g, g, max(0, w - 2 * g), max(0, h - 2 * g))
    anillo = exterior.subtracted(interior)
    esquinas = (
        QRegion(0, 0, r, r)
        .united(QRegion(w - r, 0, r, r))
        .united(QRegion(0, h - r, r, r))
        .united(QRegion(w - r, h - r, r, r))
    )
    return anillo.united(esquinas)


def construir_tabla_estilizada(parent=None):
    """
    Plantilla visual universal para tablas Smart Manager.
    Devuelve (contenedor, tabla) y deja filas/columnas al módulo consumidor.
    """
    if QFrame is None or QVBoxLayout is None or QTableWidget is None:
        return None, None

    contenedor = QFrame(parent)
    contenedor.setObjectName("contenedor_tabla_estandar")

    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(0)

    tabla = QTableWidget(contenedor)
    tabla.setObjectName("tabla_estandar_smart")
    tabla.verticalHeader().setVisible(False)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setFrameShape(QFrame.Shape.NoFrame)
    tabla.setCornerButtonEnabled(False)

    layout.addWidget(tabla)

    _set_widget_background_flag(contenedor)
    _set_widget_background_flag(tabla)
    _repolish(contenedor)
    _repolish(tabla)

    # CornerCover: smooth anti-aliased rounded corners for the container.
    # Paints the 4 corner areas with the panel background colour, then redraws
    # the neon border arc on top — hiding any child-widget content (rows,
    # scrollbars) that bleeds past the rounded border without pixelated clipping.
    if (
        QPainter is not None
        and QPen is not None
        and QColor is not None
        and QPainterPath is not None
        and QRectF is not None
    ):
        _bg = QColor(COLOR_FONDO_APP)
        _border = QColor(COLOR_CIAN)
        _r = 20.0

        class _CornerCover(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

            def paintEvent(self, _ev):  # noqa: N802
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                W, H = float(self.width()), float(self.height())
                full = QPainterPath()
                full.addRect(QRectF(0.0, 0.0, W, H))
                inner = QPainterPath()
                inner.addRoundedRect(QRectF(0.0, 0.0, W, H), _r, _r)
                p.fillPath(full.subtracted(inner), _bg)
                p.setPen(QPen(_border, 2.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(
                    QRectF(1.0, 1.0, W - 2.0, H - 2.0), _r - 1.0, _r - 1.0
                )
                p.end()

        _cover = _CornerCover(contenedor)

        def _raise_cover():
            # `_vivo()` evita tocar `contenedor`/`_cover` si su wrapper C++ ya se destruyó —
            # este QTimer.singleShot(0, …) puede llegar a ejecutarse tras un cierre/cambio de
            # pestaña muy rápido (visto real: revienta dentro de Qt6Widgets.dll, no una
            # excepción Python limpia — ver docstring de `_vivo`).
            if not (_vivo(contenedor) and _vivo(_cover)):
                return
            _cover.setGeometry(contenedor.rect())
            _cover.setMask(_mascara_solo_esquinas(_cover.width(), _cover.height(), _r))
            _cover.raise_()
            _cover.update()

        class _CoverFilter(QObject):
            def eventFilter(self_, obj, ev):  # noqa: N805
                if ev.type() == QEvent.Type.Resize:
                    _raise_cover()
                return False

        _filt = _CoverFilter(contenedor)
        contenedor._cover_filter = _filt  # prevent GC
        contenedor._corner_cover = _cover  # prevent GC
        contenedor.installEventFilter(_filt)
        if QTimer is not None:
            QTimer.singleShot(0, _raise_cover)

    return contenedor, tabla


def instalar_corner_cover(widget, radius=12, bg=None, border=None, esquinas="todas"):
    """Overlay anti-aliased que repinta las 4 esquinas con el fondo y redibuja el
    contorno redondeado encima → oculta el sangrado de scrollbar/filas en las esquinas
    (mismo mecanismo que las tablas del Centro Documental). Para CUALQUIER QTableWidget.

    `esquinas`: 'todas' (por defecto) o 'superior' — SOLO las 2 esquinas de arriba, dejando las
    inferiores y los laterales con esquinas rectas sin tocar. Pensado para listas con mucho alto
    de sobra bajo el contenido real (p. ej. "Secciones de la página" del editor de Canal Web): solo
    el PRIMER ítem llega a tocar el borde redondeado superior; el último queda lejos del borde
    inferior, así que redondear ahí sería falso (no hay ninguna esquina real que corregir) y además
    el encargo pide EXPLÍCITAMENTE que el resto de ítems mantengan esquinas puntiagudas."""
    try:
        if None in (QPainter, QPen, QColor, QPainterPath, QRectF, QWidget):
            return None
        _bg = QColor(bg or COLOR_FONDO_APP)
        _border = QColor(border or COLOR_CIAN)
        _r = float(radius)
        _solo_superior = esquinas == "superior"

        class _CornerCover(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

            def paintEvent(self, _ev):  # noqa: N802
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                W, H = float(self.width()), float(self.height())
                full = QPainterPath(); full.addRect(QRectF(0.0, 0.0, W, H))
                inner = QPainterPath(); inner.addRoundedRect(QRectF(0.0, 0.0, W, H), _r, _r)
                p.fillPath(full.subtracted(inner), _bg)
                p.setPen(QPen(_border, 2.0)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(1.0, 1.0, W - 2.0, H - 2.0), _r - 1.0, _r - 1.0)
                p.end()

        cover = _CornerCover(widget)
        cover.show()

        def _raise():
            # Mismo motivo que `_raise_cover` en `construir_tabla_estilizada`: los varios
            # `QTimer.singleShot` diferidos de más abajo (0/60/250 ms) pueden disparar después
            # de que `widget`/`cover` ya se hayan destruido — `_vivo()` lo deja como no-op en
            # vez de reventar dentro de Qt6Widgets.dll.
            if not (_vivo(widget) and _vivo(cover)):
                return
            cover.setGeometry(widget.rect())
            if _solo_superior:
                # Franja superior de `radius` px, ancho completo: el `paintEvent` de arriba sigue
                # calculando la curvatura sobre la altura REAL del widget (para que el radio salga
                # correcto), pero esta máscara solo deja visible esa franja — las esquinas
                # inferiores (que ese mismo `paintEvent` también "pintaría" en teoría) quedan fuera
                # del área visible, nunca llegan a verse.
                from PyQt6.QtGui import QRegion
                cover.setMask(QRegion(0, 0, cover.width(), max(1, int(_r))))
            else:
                cover.setMask(_mascara_solo_esquinas(cover.width(), cover.height(), _r))
            cover.raise_(); cover.update()

        class _F(QObject):
            def eventFilter(self_, obj, ev):  # noqa: N805
                if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
                    _raise()
                    # Al mostrarse (cambio de pestaña en un QStackedWidget) la geometría y el
                    # apilado se asientan un instante después → re-elevar diferido.
                    if ev.type() == QEvent.Type.Show and QTimer is not None:
                        QTimer.singleShot(0, _raise)
                        QTimer.singleShot(120, _raise)
                return False

        f = _F(widget)
        widget._cc_filter = f      # evita GC
        widget._cc_cover = cover
        widget.installEventFilter(f)
        # El scroll re-apila la barra por encima → re-elevar la tapa tras desplazar.
        try:
            sb = widget.verticalScrollBar()
            sb.valueChanged.connect(lambda *_a: _raise())
            sb.rangeChanged.connect(lambda *_a: _raise())
        except Exception:
            pass
        if QTimer is not None:
            for _d in (0, 60, 250):   # re-elevar tras mostrar/maximizar
                QTimer.singleShot(_d, _raise)
        return cover
    except Exception:
        return None


def _blindar_tamano_fijo(widget, ancho, alto):
    """Reafirma tamaño fijo + política Fixed/Fixed cada vez que el filtro global de estilos vuelve
    a tocar este widget — no solo una vez.

    Bug real reproducido y confirmado (captura de pantalla + inspección de `sizePolicy()`/
    `minimumSize()` en vivo): en un diálogo FRAMELESS + WA_TranslucentBackground (todos los
    diálogos emergentes pequeños de la app), el filtro global de estilos (`_apply_font`, más abajo)
    aplica la fuente en negrita al widget — y ESO reinicia su política de tamaño horizontal de
    Fixed a Minimum, aunque `setFixedSize()` ya se hubiera llamado antes. Con política Minimum, el
    estilo (relleno global `QPushButton{padding:10px 16px}` + convención de "ancho mínimo de botón
    de diálogo") infla el ancho real a ~120px — invisible en reposo (fondo transparente), pero
    revelado de golpe al pasar el ratón: un "✕" que parecía redondo se ve como una píldora ancha.
    `_SmartGlobalFilter` invoca `aplicar_estilo_widget` (que incluye `_apply_font`) en CADA
    `Show`/`Polish`/`EnabledChange`/`DynamicPropertyChange` del widget — no solo la primera vez, así
    que un único `QTimer.singleShot(0, ...)` disparado en la construcción puede perder la carrera si
    alguno de esos eventos llega DESPUÉS (p. ej. el primer `Polish` real, diferido por Qt hasta justo
    antes del primer pintado). La solución robusta e independiente de temporización: instalar un
    event filter en el PROPIO widget que reafirme el tamaño cada vez que reciba esos mismos eventos
    — como los filtros de aplicación se invocan ANTES que los del propio objeto (Qt no detiene la
    cadena salvo que un filtro devuelva True, y `_SmartGlobalFilter` no lo hace), este filtro corrige
    el estropicio del global justo después, en el mismo tick, sin depender de ningún retraso mágico.
    Para CUALQUIER botón pequeño de tamaño fijo dentro de un diálogo emergente frameless+translúcido
    — no solo los botones "✕"."""
    if QTimer is None or QObject is None or QEvent is None:
        return
    from PyQt6.QtWidgets import QSizePolicy

    def _reafirmar():
        try:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setFixedSize(ancho, alto)
        except Exception:
            pass

    _EVENTOS_RIESGO = {
        QEvent.Type.Show,
        QEvent.Type.Polish,
        QEvent.Type.EnabledChange,
        QEvent.Type.DynamicPropertyChange,
        QEvent.Type.FontChange,
    }

    class _Blindaje(QObject):
        def eventFilter(self_, obj, ev):  # noqa: N805
            if ev.type() in _EVENTOS_RIESGO:
                _reafirmar()
            return False

    _filtro = _Blindaje(widget)
    widget.installEventFilter(_filtro)
    widget._blindaje_tamano_fijo = _filtro  # evita el GC del filtro mientras viva el widget
    QTimer.singleShot(0, _reafirmar)


def _apply_font(widget):
    if widget is None or QFont is None or not hasattr(widget, "font"):
        return
    try:
        font = widget.font()
        font.setFamily(FUENTE_APP)
        font.setWeight(QFont.Weight.Bold)
        widget.setFont(font)
    except Exception:
        pass


def _set_widget_background_flag(widget):
    if widget is None:
        return
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass


def _set_widget_cursor(widget):
    if widget is None or Qt is None:
        return
    try:
        if any(
            _safe_instance(widget, klass)
            for klass in (QLineEdit, QTextEdit, QPlainTextEdit)
        ):
            # Un campo de solo lectura que actúa como botón (p. ej. el filtro de
            # fecha con triángulo) puede pedir conservar su cursor (manita) en vez
            # del IBeam de texto.
            if widget.property("smKeepCursor"):
                return
            widget.setCursor(Qt.CursorShape.IBeamCursor)
            return
        clickable = (
            QAbstractButton,
            QComboBox,
            QAbstractItemView,
            QHeaderView,
            QTabBar,
            QMenu,
            QSlider,
            QScrollArea,
            QDateEdit,
            QTimeEdit,
            QAbstractSpinBox,
        )
        if any(_safe_instance(widget, klass) for klass in clickable):
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
    except Exception:
        pass


def _button_role_from_name_or_text(widget):
    if widget is None:
        return None
    object_name = _normalize_text(getattr(widget, "objectName", lambda: "")())
    text_value = _normalize_text(widget.text() if hasattr(widget, "text") else "")
    words = set(re.findall(r"[a-z0-9_]+", f"{object_name} {text_value}".strip()))

    if object_name in {"btn_primario", "btn_secundario", "btn_neon", "btn_sidebar"}:
        return None
    if object_name in {"btn_peligro", "btn_sidebar_exit"}:
        return "danger"

    danger_words = {
        "salir",
        "cerrar",
        "eliminar",
        "borrar",
        "abortar",
        "exit",
        "delete",
    }
    neutral_words = {"cancelar", "cancel", "volver", "no", "omitir", "skip"}
    success_words = {
        "aceptar",
        "continuar",
        "confirmar",
        "guardar",
        "aplicar",
        "iniciar",
        "si",
        "yes",
        "save",
        "ok",
        "confirm",
        "continue",
    }

    if words & danger_words:
        return "danger"
    if words & neutral_words:
        return "neutral"
    if words & success_words:
        return "success"
    return None


def _apply_button_role(widget):
    if widget is None or not _safe_instance(widget, QAbstractButton):
        return
    role = _button_role_from_name_or_text(widget)
    if role is None:
        return
    try:
        if widget.property("semanticRole") != role:
            widget.setProperty("semanticRole", role)
            _repolish(widget)
    except Exception:
        pass


class _RoundedComboDelegate(
    QStyledItemDelegate if QStyledItemDelegate is not None else object
):
    """Draws combo-box list items with a rounded-rect highlight on hover/selection."""

    def paint(self, painter, option, index):
        if QPainter is None or Qt is None or QRectF is None:
            super().paint(painter, option, index)
            return
        try:
            from PyQt6.QtWidgets import QStyle

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            is_active = bool(
                option.state
                & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected)
            )
            if is_active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(COLOR_CIAN))
                r = QRectF(option.rect).adjusted(6, 2, -6, -2)
                painter.drawRoundedRect(r, 8, 8)
                painter.setPen(QColor(COLOR_FONDO_APP))
            else:
                painter.setPen(QColor("#E6EDF3"))
            text = str(index.data() or "")
            painter.setFont(option.font)
            text_rect = option.rect.adjusted(16, 0, -8, 0)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )
            painter.restore()
        except Exception:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        if QSize is not None:
            return sh.expandedTo(QSize(0, 38))
        return sh


def _apply_combo_extras(widget):
    if widget is None or not _safe_instance(widget, QComboBox):
        return
    try:
        # HORARIO comboboxes handle their own popup styling via per-widget stylesheet;
        # skip the expensive lazy view() init to avoid freezing on 112+ comboboxes.
        if widget.property("horario_cb"):
            return
        # Idempotente a propósito: `widget.view()` fuerza la construcción inmediata del
        # QComboBoxPrivateContainer nativo (la ventana del popup) aunque el combo esté años-luz
        # de mostrarse — factory explícita (`_combo()`) + el filtro global de eventos (reacciona a
        # Polish/Show de CUALQUIER widget) pueden llamar a esta función DOS veces sobre el MISMO
        # combo durante su propia construcción. Confirmado con reproducción local aislada (>60
        # intentos): esa doble construcción del contenedor nativo — no la simple redundancia de
        # llamada — es la causa real de los crashes nativos intermitentes (0xc0000005 en
        # Qt6Widgets.dll) en Mermas/Configuración/Cámaras/Gastos; con esta guarda, 1/10 crashes en
        # la reproducción de `_page_gastos` (era 60-100% sin ella).
        if getattr(widget, "_sm_combo_extras_aplicado", False):
            return
        try:
            widget._sm_combo_extras_aplicado = True
        except Exception:
            pass
        view = widget.view()
        if view is not None:
            _apply_font(view)
            _set_widget_cursor(view)
            # Always use _sm_combo_view name so the global QSS exclusion rule
            # (border:none for #_sm_combo_view) fires reliably.
            view.setObjectName("_sm_combo_view")
            # Scroll por píxel: evita el hueco vacío bajo el último item cuando el
            # viewport no es múltiplo exacto de la altura de item.
            try:
                view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            except Exception:
                pass
            # Diseño unificado de scrollbar para TODOS los desplegables:
            # barra cian de 12px con extremos redondeados, sin columna gris de
            # fondo (idéntica a la sidebar y al combo de "producto a granel").
            view.setStyleSheet(
                f"QListView#_sm_combo_view {{"
                f"  border: none;"
                f"  background-color: {COLOR_FONDO_APP};"
                f"  outline: 0px;"
                f"}}"
                f"QListView#_sm_combo_view QScrollBar:vertical {{"
                # Márgenes amplios (derecha + arriba/abajo) para que la barra quede
                # METIDA hacia dentro y no corte el contorno neón redondeado del popup
                # (radio 20): a menos margen, el handle asoma por la curva de la esquina.
                f"  background: transparent; width: 8px; margin: 12px 9px 12px 0px;"
                f"}}"
                f"QListView#_sm_combo_view QScrollBar::handle:vertical {{"
                # border-radius = ancho/2 → extremos totalmente redondeados (pastilla).
                f"  background: {COLOR_CIAN}; min-height: 26px; border-radius: 4px;"
                f"}}"
                f"QListView#_sm_combo_view QScrollBar::add-line:vertical,"
                f"QListView#_sm_combo_view QScrollBar::sub-line:vertical {{"
                f"  border: none; background: none; width: 0px; height: 0px;"
                f"}}"
                f"QListView#_sm_combo_view QScrollBar::add-page:vertical,"
                f"QListView#_sm_combo_view QScrollBar::sub-page:vertical {{"
                f"  background: transparent;"
                f"}}"
            )
            # Install rounded-item delegate so hover/selection appears with rounded corners
            try:
                if not isinstance(view.itemDelegate(), _RoundedComboDelegate):
                    view.setItemDelegate(_RoundedComboDelegate(view))
            except Exception:
                pass
            # El popup no debe truncar/elidir el texto de una opción solo porque el combo
            # CERRADO sea más estrecho (p.ej. "devolucion_compra" cortándose como
            # "devoluc..._compra") — se ensancha la vista del popup, como mínimo, al ancho del
            # texto más largo. Antes vivía en `catalogo_gestion._combo()` como una llamada
            # SEPARADA a `cb.view()` justo después de esta función — dos accesos independientes a
            # `.view()` sobre el mismo combo en la misma ráfaga de construcción, confirmado (junto
            # con la guarda de idempotencia de arriba) como el disparador real de los crashes
            # nativos intermitentes. Movido aquí para reutilizar la MISMA `view` ya obtenida.
            try:
                fm = widget.fontMetrics()
                ancho_max = max((fm.horizontalAdvance(widget.itemText(i))
                                 for i in range(widget.count())), default=0)
                if ancho_max:
                    view.setMinimumWidth(ancho_max + 48)
            except Exception:
                pass
    except Exception:
        pass


def _apply_dialog_semantics(widget):
    if widget is None:
        return
    try:
        if _safe_instance(widget, QMessageBox):
            widget.setObjectName("smart_message_box")
            for button in widget.buttons():
                _apply_font(button)
                _set_widget_cursor(button)
                _apply_button_role(button)
        elif _safe_instance(widget, QDialogButtonBox):
            for button in widget.buttons():
                _apply_font(button)
                _set_widget_cursor(button)
                _apply_button_role(button)
    except Exception:
        pass


def _apply_native_dialog_chrome(widget):
    """Quita la barra de título nativa clásica en QMessageBox / QInputDialog (estilo app)."""
    if widget is None or Qt is None:
        return
    try:
        if not hasattr(widget, "isWindow") or not widget.isWindow():
            return
        flags = widget.windowFlags()
        widget.setWindowFlags(
            flags | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
    except Exception:
        pass


def _traducir_dialogo_nativo(widget):
    """Traduce en caliente el texto de un QMessageBox nativo al idioma activo.
    Muchos QMessageBox del código llevan el texto en español hardcodeado (no pasan
    por tr); aquí se traducen vía el traductor IA cacheado (Nivel 2). En español o
    sin backend no hace nada (degradación elegante: queda en español)."""
    try:
        from src.utils import i18n

        lang = i18n.current_language()
        if not lang or lang == "es":
            return

        def _t(s):
            s = (s or "").strip()
            if not s:
                return s
            try:
                return i18n.ai_translate(s, lang, dominio="ui") or s
            except Exception:
                return s

        if widget.windowTitle():
            widget.setWindowTitle(_t(widget.windowTitle()))
        if hasattr(widget, "text") and widget.text():
            widget.setText(_t(widget.text()))
        if hasattr(widget, "informativeText") and widget.informativeText():
            widget.setInformativeText(_t(widget.informativeText()))
    except Exception:
        pass


def _apply_windows_dark_title_bar(widget):
    if widget is None or sys.platform != "win32":
        return

    try:
        if not hasattr(widget, "isWindow") or not widget.isWindow():
            return

        hwnd = int(widget.winId())
        if not hwnd:
            return

        DWMWA_USE_IMMERSIVE_DARK_MODE_FALLBACK = 19
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)

        for attr in (
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            DWMWA_USE_IMMERSIVE_DARK_MODE_FALLBACK,
        ):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception:
                continue
    except Exception:
        pass


# ============================================================
# BLOQUE FILTROS Y DIÁLOGOS DE MENSAJES
# ============================================================
def _centrar_dialogo_en_pantalla(widget):
    """Reposiciona `widget` (un QDialog ya mostrado) sobre el centro del área REAL disponible de la
    pantalla primaria (descontando la barra de tareas). Ver el comentario en
    `_SmartGlobalFilter.eventFilter` para el porqué de este mecanismo centralizado."""
    try:
        if widget is None:
            return
        from PyQt6.QtWidgets import QApplication
        pantalla = QApplication.primaryScreen().availableGeometry()
        widget.adjustSize()
        x = pantalla.x() + max(0, (pantalla.width() - widget.width()) // 2)
        y = pantalla.y() + max(0, (pantalla.height() - widget.height()) // 2)
        widget.move(x, y)
    except Exception:
        pass


def _vivo(obj) -> bool:
    """True si `obj` sigue siendo un objeto Qt válido (su wrapper C++ no se ha destruido). Mismo
    criterio que `transiciones._vivo` (no se importa de allí para no crear un ciclo de imports
    entre `assets.estilo_global` y `src.gui.transiciones`): un callback diferido con
    `QTimer.singleShot(0, …)` puede llegar a ejecutarse después de que el widget al que apunta ya
    se haya destruido (p.ej. un módulo que se cierra muy rápido tras abrirse); tocarlo entonces
    revienta dentro de Qt6Widgets.dll en vez de fallar limpiamente."""
    if obj is None:
        return False
    try:
        from PyQt6 import sip
        return not sip.isdeleted(obj)
    except Exception:
        return True


def _recortar_esquinas_dialogo(widget, radio=16):
    """Recorta la ventana nativa de `widget` (un QDialog frameless+translúcido ya mostrado) a un
    rectángulo de esquinas redondeadas de verdad, vía `SetWindowRgn` — misma técnica que
    `_clip_combo_popup` para el popup de los combos. Sin esto, el `border-radius` de la QSS es solo
    pintura: las 4 esquinas del HWND rectangular real quedan cuadradas por debajo si la composición
    por capas de Windows no las recorta también (bug reproducido en diálogos grandes)."""
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return
        w, h = widget.width(), widget.height()
        if w <= 0 or h <= 0:
            return
        r = radio
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r * 2, r * 2)
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


class _SmartGlobalFilter(QObject):
    def eventFilter(self, watched, event):
        if watched is None or event is None or Qt is None or QEvent is None:
            return super().eventFilter(watched, event)
        try:
            # Doble clic en celda de tabla → popup de solo lectura con el texto completo (regla
            # de negocio congelada en CLAUDE.md: "en TODAS las tablas de la app"). Se resuelve aquí,
            # una sola vez, en vez de tocar cada pantalla: cualquier QTableWidget/QTableView de la
            # app (incluida `EnterpriseTable.tabla`) queda cubierta automáticamente. `watched` aquí
            # es el VIEWPORT de la tabla (los eventos de ratón de un QAbstractItemView llegan a su
            # `viewport()`, hijo interno, no a la tabla en sí) — `_manejar_doble_clic_celda` hace de
            # guarda completa: no hace NADA si la tabla ya tiene su propio doble clic conectado
            # (`cellDoubleClicked`/`itemDoubleClicked`/`doubleClicked`, contados vía `receivers()`)
            # ni si el doble clic dispara la edición nativa de la celda — así nunca compite con los
            # manejadores ya existentes (picking, expediente, editar línea, etc.).
            if event.type() == QEvent.Type.MouseButtonDblClick and _manejar_doble_clic_celda(
                watched, event
            ):
                return True
            # Centrado universal de ventanas emergentes pequeñas: CUALQUIER QDialog frameless
            # (docenas repartidos por toda la app, cada uno con su propio marco redondeado en vez
            # de la barra de título de Windows) se centraba por defecto sobre el CENTRO DE SU
            # PADRE, no sobre la pantalla real — si el diálogo era más alto de lo esperado o el
            # padre no ocupaba toda la pantalla, podía quedar cortado/fuera de la vista (bug real
            # confirmado, p. ej. "Nuevo activo" de GMAO). En vez de repetir el parche en cada una
            # de las ~60 clases afectadas (y en cualquier `QDialog(...)` ad-hoc futuro), se resuelve
            # aquí UNA sola vez: al primer `Show` de cualquier QDialog con `FramelessWindowHint`, se
            # reposiciona sobre `primaryScreen().availableGeometry()`. Diferido con
            # `QTimer.singleShot(0, ...)` porque en el propio evento Show el tamaño natural del
            # diálogo (`adjustSize`) aún no está resuelto (mismo criterio que `_blindar_tamano_
            # fijo`). Solo una vez por instancia (propiedad dinámica) para no pelearse con diálogos
            # que el usuario arrastra a otro sitio tras abrirse (p. ej. los que implementan su
            # propio `mousePressEvent`/`mouseMoveEvent` de arrastre).
            if (event.type() == QEvent.Type.Show and QDialog is not None and QTimer is not None
                    and _safe_instance(watched, QDialog)
                    and bool(watched.windowFlags() & Qt.WindowType.FramelessWindowHint)
                    and not watched.property("_sm_centrado_pantalla")):
                watched.setProperty("_sm_centrado_pantalla", True)
                QTimer.singleShot(0, lambda w=watched: _centrar_dialogo_en_pantalla(w))
            # Esquinas REALMENTE redondeadas (recorte nativo de la ventana, no solo el CSS
            # `border-radius` pintado): el `border-radius` de la QSS por sí solo NO recorta el
            # HWND sin marco — solo lo pinta — así que las 4 esquinas de la ventana rectangular
            # real pueden quedar cuadradas por debajo del dibujo redondeado si la composición por
            # capas de Windows no coopera (mismo bug ya reproducido y resuelto para el popup nativo
            # del combo — `CreateRoundRectRgn`/`SetWindowRgn`, ver más abajo — reutilizado aquí en
            # vez de duplicar la técnica). Se aplica a CUALQUIER QDialog frameless+translúcido
            # (todos los que usan `_dialogo_frameless`), en Show y en Resize (el tamaño natural del
            # diálogo aún no está resuelto en el propio Show).
            if (event.type() in {QEvent.Type.Show, QEvent.Type.Resize}
                    and sys.platform == "win32" and QDialog is not None and QTimer is not None
                    and _safe_instance(watched, QDialog)
                    and bool(watched.windowFlags() & Qt.WindowType.FramelessWindowHint)
                    and watched.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)):
                QTimer.singleShot(0, lambda w=watched: _recortar_esquinas_dialogo(w))
            if event.type() == QEvent.Type.Show and _safe_instance(
                watched, QMessageBox
            ):
                # QInputDialog is intentionally excluded: setWindowFlags(FramelessHint) on a
                # visible QInputDialog causes Qt to destroy/recreate the native handle, which
                # puts the internal spinbox/buttons into a geometry-correction loop where
                # Windows keeps rejecting the recalculated positions, freezing the UI.
                # The global QSS already applies the dark theme to QInputDialog correctly.
                _apply_native_dialog_chrome(watched)
                _traducir_dialogo_nativo(watched)
            # QComboBoxPrivateContainer: clip OS window to rounded rect (SetWindowRgn)
            # so the QAbstractItemView's QSS border-radius + neon border shows correctly.
            try:
                _cn = (
                    watched.metaObject().className()
                    if hasattr(watched, "metaObject")
                    else ""
                )
                _is_combo_container = _cn == "QComboBoxPrivateContainer"
            except Exception:
                _is_combo_container = False
            if _is_combo_container:
                if event.type() == QEvent.Type.Hide:
                    # Restaurar el stylesheet ORIGINAL del combo al cerrar el popup.
                    # Antes se hacía setStyleSheet("") que borraba el QSS inline de
                    # los combos con borde propio (p. ej. el de empleado), dejándolos
                    # sin contorno de neón. Ahora restauramos lo guardado en Show.
                    try:
                        _pcombo = watched.parentWidget()
                        if _pcombo is not None and _safe_instance(_pcombo, QComboBox):
                            if not _pcombo.property("horario_cb"):
                                _saved = _pcombo.property("_sm_qss_saved")
                                _pcombo.setStyleSheet(
                                    _saved if _saved is not None else ""
                                )
                    except Exception:
                        pass
                # Combos marcados con 'horario_cb' gestionan su propio popup
                # (borde + scrollbar) → no aplicamos el borde del contenedor para
                # evitar un doble contorno de neón.
                try:
                    _pc = watched.parentWidget()
                    _self_styled = bool(
                        _pc is not None
                        and _safe_instance(_pc, QComboBox)
                        and _pc.property("horario_cb")
                    )
                except Exception:
                    _self_styled = False
                if _self_styled and event.type() in {
                    QEvent.Type.Show,
                    QEvent.Type.Polish,
                }:
                    # El combo se auto-estiliza (borde + scrollbar en su vista).
                    # NO tocamos windowFlags/atributos aquí (recrearía el handle
                    # nativo en cada Show → lentitud y parpadeos). Sólo dejamos el
                    # contenedor transparente sin borde, para que se vea un único
                    # contorno de neón (el de la vista). Los flags translúcidos
                    # del contenedor los fija el combo en su __init__.
                    try:
                        ly = watched.layout()
                        if ly is not None:
                            ly.setContentsMargins(0, 0, 0, 0)
                        if not watched.objectName():
                            watched.setObjectName("_sm_combo_popup_self")
                        watched.setStyleSheet(
                            f"QWidget#{watched.objectName()} {{"
                            f"  background: transparent;"
                            f"  border: none;"
                            f"}}"
                        )
                    except Exception:
                        pass
                elif event.type() in {QEvent.Type.Show, QEvent.Type.Polish}:
                    try:
                        ly = watched.layout()
                        if ly is not None:
                            ly.setContentsMargins(0, 0, 0, 0)
                        # Neon border lives on the container frame (aligns with SetWindowRgn).
                        # The view's border is neutralised via _apply_combo_extras +
                        # the global QListView#_sm_combo_view { border: none } rule.
                        if not watched.objectName():
                            watched.setObjectName("_sm_combo_popup")
                        watched.setStyleSheet(
                            f"QWidget#_sm_combo_popup {{"
                            f"  background-color: {COLOR_FONDO_APP};"
                            f"  border: 2px solid {COLOR_CIAN};"
                            f"  border-radius: {RADIO_XL};"
                            f"}}"
                        )
                        # Collapse QComboBoxPrivateScroller widgets (top/bottom scroll arrows)
                        # so they don't appear as black bars inside the popup.
                        for _child in watched.children():
                            if hasattr(_child, "metaObject") and hasattr(
                                _child, "setStyleSheet"
                            ):
                                try:
                                    if "Scroller" in _child.metaObject().className():
                                        _child.setStyleSheet(
                                            f"background-color: {COLOR_FONDO_APP}; border: none;"
                                        )
                                        _child.setMaximumHeight(0)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                # Suppress the parent QComboBox border only when the popup is actually visible
                # (Show, not Polish — Polish fires at creation time before the popup ever opens).
                if event.type() == QEvent.Type.Show:
                    try:
                        _pcombo = watched.parentWidget()
                        if _pcombo is not None and _safe_instance(_pcombo, QComboBox):
                            if not _pcombo.property("horario_cb"):
                                # Guardar el QSS original UNA vez para poder
                                # restaurarlo al cerrar (ver rama Hide).
                                if _pcombo.property("_sm_qss_saved") is None:
                                    _pcombo.setProperty(
                                        "_sm_qss_saved", _pcombo.styleSheet()
                                    )
                                _pcombo.setStyleSheet(
                                    f"QComboBox {{"
                                    f"  border: 2px solid transparent;"
                                    f"  border-radius: {RADIO_LG};"
                                    f"}}"
                                )
                    except Exception:
                        pass
                if (
                    not _self_styled
                    and event.type() in {QEvent.Type.Show, QEvent.Type.Resize}
                    and sys.platform == "win32"
                ):
                    _ctr = watched

                    def _clip_combo_popup(_w=_ctr):
                        try:
                            hwnd = int(_w.winId())
                            if not hwnd:
                                return
                            w, h = _w.width(), _w.height()
                            if w <= 0 or h <= 0:
                                return
                            r = 20  # matches RADIO_XL border-radius
                            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                                0, 0, w + 1, h + 1, r * 2, r * 2
                            )
                            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
                        except Exception:
                            pass

                    if QTimer is not None:
                        QTimer.singleShot(0, _clip_combo_popup)
            # Show/Polish disparan de forma RUTINARIA (a menudo varias veces) durante la propia
            # construcción normal de cualquier ventana. La causa real del crash nativo intermitente
            # (0xc0000005 en Qt6Widgets.dll) confirmada con reproducción local aislada no estaba
            # aquí, sino en reaplicar TODO el pipeline de `aplicar_estilo_widget` sobre un widget
            # que ya lo había recibido una vez desde su propio helper de construcción (`_combo`/
            # `_btn`/`_inp`/…) — ver la guarda de idempotencia (`forzar=False` por defecto) dentro
            # de `aplicar_estilo_widget`, que es la que de verdad lo arregla (se descartaron antes,
            # por separado, el popup de combos y otras sub-funciones concretas como causa única).
            if event.type() in (QEvent.Type.Show, QEvent.Type.Polish):
                aplicar_estilo_widget(watched)
            elif event.type() == QEvent.Type.EnabledChange:
                aplicar_estilo_widget(watched, forzar=True)
            elif event.type() == QEvent.Type.DynamicPropertyChange:
                # `forzar=True` (síncrono, sin guarda) solo tiene sentido para `semanticRole`
                # cambiando en tiempo de ejecución sobre un botón YA construido y mostrado — el
                # único caso real que motivó esta rama. Reaccionar así a CUALQUIER propiedad
                # dinámica (antes) disparaba el pipeline completo, síncrono, sobre widgets que
                # solo estaban fijando una marca propia EN SU PROPIO CONSTRUCTOR (p. ej.
                # `_HorarioComboBox.setProperty("horario_cb", True)`, cientos de veces por
                # rejilla) — mismo patrón exacto que causó que el botón ✕ del asistente de
                # cámaras se volviera `WA_NativeWindow` por accidente. Ignorar cualquier otra
                # propiedad aquí: ya recibirá su estilo, con guarda, en su propio Show/Polish.
                try:
                    nombre = bytes(event.propertyName()).decode("utf-8", "ignore")
                except Exception:
                    nombre = ""
                if nombre == "semanticRole":
                    aplicar_estilo_widget(watched, forzar=True)
            # Teclado táctil de Windows (petición explícita): SOLO en un dispositivo con pantalla
            # táctil y sin teclado físico conectado ahora mismo (`_dispositivo_tactil_sin_teclado`,
            # ver bloque dedicado arriba) — al enfocar CUALQUIER campo de texto/búsqueda de la app
            # (QLineEdit incluye el campo interno de un QComboBox editable), se lanza el teclado en
            # pantalla nativo. Resuelto aquí una sola vez, igual que el resto de comportamientos
            # globales de este filtro, en vez de tocar cada pantalla.
            if event.type() == QEvent.Type.FocusIn and isinstance(
                watched, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
            ) and _dispositivo_tactil_sin_teclado():
                _abrir_teclado_en_pantalla()
        except Exception:
            pass
        return super().eventFilter(watched, event)


class _CircleIcon(QLabel):
    """Círculo de color con un símbolo (×, ✓, !, i, ?) PERFECTAMENTE centrado por la tinta real
    del glifo (bounding box ajustado), no por la caja de línea de la fuente — así la 'X' de
    'Acceso Denegado' (y el resto) quedan justo en el centro del círculo, sea cual sea la fuente."""

    def __init__(self, simbolo, color_circulo, color_simbolo, diametro=46, parent=None):
        super().__init__(parent)
        self._sim = simbolo
        self._bg = color_circulo
        self._fg = color_simbolo
        self.setFixedSize(diametro, diametro)

    def paintEvent(self, _event):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QFontMetricsF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QColor(self._bg))
        p.drawEllipse(0, 0, self.width(), self.height())
        f = QFont(FUENTE_APP, int(self.height() * 0.42))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(self._fg))
        br = QFontMetricsF(f).tightBoundingRect(self._sim)
        x = self.width() / 2 - br.center().x()
        y = self.height() / 2 - br.center().y()
        p.drawText(QPointF(x, y), self._sim)
        p.end()


class SmartMessageDialog(QDialog):
    ROLE_TO_RESULT = {
        "ok": 1,
        "yes": 2,
        "no": 3,
        "cancel": 4,
        # Rol genérico para una acción afirmativa "personalizada" (texto propio vía tupla
        # (rol, etiqueta) en `buttons` — ver `_button_text`/__init__): p. ej. el recuento
        # automático de báscula en el arqueo de caja ("Transferir recuento" / "Cancelar").
        "transferir": 5,
    }

    LEVEL_COLORS = {
        "info": COLOR_CIAN,
        "warning": COLOR_AMBAR,
        "error": COLOR_ROJO_ERROR,
        "question": "#2D8CFF",
        "success": COLOR_VERDE_OK,
    }

    LEVEL_SYMBOLS = {
        "info": "i",
        "warning": "!",
        "error": "×",
        "question": "?",
        "success": "✓",
    }

    def __init__(self, parent=None, title="", message="", level="info", buttons=None,
                 seleccionable=False, alto_maximo_mensaje=280):
        super().__init__(parent)
        self.dialog_result = 0
        self.level = str(level or "info").lower()
        # Cada entrada de `buttons` es un rol ("ok"/"yes"/"no"/"cancel"/"transferir") o, para un
        # texto de botón propio sin perder el resultado semántico del rol, una tupla
        # (rol, etiqueta) — p. ej. ("transferir", "Transferir recuento"). `self.buttons` conserva
        # SOLO los roles (lo que ya consumía el resto de la clase); las etiquetas custom se
        # guardan aparte en `self._button_labels`.
        self.buttons = []
        self._button_labels = {}
        for _spec in (buttons or ["ok"]):
            if isinstance(_spec, (tuple, list)) and len(_spec) == 2:
                _role, _label = _spec
            else:
                _role, _label = _spec, None
            self.buttons.append(_role)
            if _label:
                self._button_labels[_role] = str(_label)
        # `seleccionable=True`: el mensaje se muestra en un QTextEdit de solo lectura (en vez del
        # QLabel habitual) para que el texto sea seleccionable/copiable y, si es largo, se
        # desplace dentro de una altura máxima — pensado para el popup "ver celda completa"
        # (doble clic en cualquier tabla, ver `mostrar_texto_celda`/`_SmartGlobalFilter`) sin tocar
        # el aspecto ni el comportamiento de los cientos de `mostrar_mensaje(...)` existentes, que
        # siguen usando el QLabel de siempre por defecto.
        self._seleccionable = bool(seleccionable)
        self._alto_maximo_mensaje = int(alto_maximo_mensaje or 280)

        self.setObjectName("smart_message_dialog")
        self.setWindowTitle(title or "Smart Manager")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)

        self.panel = QFrame(self)
        self.panel.setObjectName("smart_message_panel")
        outer.addWidget(self.panel)
        self.panel.setMinimumWidth(320)

        if QGraphicsDropShadowEffect is not None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(34)
            shadow.setOffset(0, 0)
            shadow.setColor(
                self._to_qcolor(self.LEVEL_COLORS.get(self.level, COLOR_CIAN), 180)
            )
            self.panel.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(16)

        row = QHBoxLayout()
        row.setSpacing(14)

        self.icon_label = _CircleIcon(
            self.LEVEL_SYMBOLS.get(self.level, "i"),
            self.LEVEL_COLORS.get(self.level, COLOR_CIAN), COLOR_FONDO_APP, diametro=46)
        self.icon_label.setObjectName("smart_message_icon")
        row.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        self.title_label = QLabel(str(title or "Sistema"))
        self.title_label.setObjectName("smart_message_title")
        self.title_label.setWordWrap(True)
        text_col.addWidget(self.title_label)

        self.message_label = None
        self.message_edit = None
        if self._seleccionable and QTextEdit is not None:
            self.message_edit = QTextEdit()
            self.message_edit.setObjectName("smart_message_text_edit")
            self.message_edit.setReadOnly(True)
            self.message_edit.setPlainText(str(message or ""))
            self.message_edit.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            self.message_edit.setFrameShape(QFrame.Shape.NoFrame)
            self.message_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.message_edit.setMinimumHeight(60)
            self.message_edit.setMaximumHeight(self._alto_maximo_mensaje)
            self.message_edit.setCursor(Qt.CursorShape.IBeamCursor)
            text_col.addWidget(self.message_edit)
        else:
            self.message_label = QLabel(str(message or ""))
            self.message_label.setObjectName("smart_message_text")
            self.message_label.setWordWrap(True)
            text_col.addWidget(self.message_label)

        row.addLayout(text_col, 1)
        layout.addLayout(row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        for btn_role in self.buttons:
            button = QPushButton(self._button_text(btn_role))
            button.setMinimumWidth(132)
            button.setProperty("semanticRole", self._semantic_role(btn_role))
            button.clicked.connect(
                lambda _checked=False, role=btn_role: self._finish(role)
            )
            aplicar_estilo_widget(button)
            button_row.addWidget(button)

        layout.addLayout(button_row)

        self._apply_inline_visuals()

    def _to_qcolor(self, hex_color, alpha=255):
        from PyQt6.QtGui import QColor

        color = QColor(hex_color)
        color.setAlpha(alpha)
        return color

    def _button_text(self, role):
        if role in self._button_labels:
            return self._button_labels[role]
        try:
            from src.utils.i18n import tr

            mapping = {
                "ok": tr("common.accept", default="OK"),
                "yes": tr("common.yes", default="Sí"),
                "no": tr("common.no", default="No"),
                "cancel": tr("common.cancel", default="Cancelar"),
                "transferir": tr("common.transferir", default="Transferir"),
            }
        except Exception:
            mapping = {"ok": "OK", "yes": "Sí", "no": "No", "cancel": "Cancelar",
                       "transferir": "Transferir"}
        return mapping.get(str(role).lower(), str(role).upper())

    def _semantic_role(self, role):
        role = str(role).lower()
        if role in {"yes", "ok"}:
            return "success"
        if role in {"no", "cancel"}:
            return "neutral"
        return "success"

    def _finish(self, role):
        self.dialog_result = self.ROLE_TO_RESULT.get(str(role).lower(), 0)
        self.accept()

    def _apply_inline_visuals(self):
        accent = self.LEVEL_COLORS.get(self.level, COLOR_CIAN)
        self.panel.setStyleSheet(f"""
            QFrame#smart_message_panel {{
                background-color: {COLOR_NEGRO_PANEL};
                border: 2px solid {accent};
                border-radius: {RADIO_XL};
            }}
            QLabel#smart_message_icon {{
                background-color: {accent};
                color: {COLOR_FONDO_APP};
                border-radius: 23px;
                font-family: '{FUENTE_APP}';
                font-size: 26px;
                font-weight: 900;
            }}
            QLabel#smart_message_title {{
                color: {COLOR_TEXTO_PRINCIPAL};
                background: transparent;
                border: none;
                font-family: '{FUENTE_APP}';
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#smart_message_text {{
                color: {COLOR_TEXTO_PRINCIPAL};
                background: transparent;
                border: none;
                font-family: '{FUENTE_APP}';
                font-size: 13px;
                font-weight: 900;
            }}
            QTextEdit#smart_message_text_edit {{
                color: {COLOR_TEXTO_PRINCIPAL};
                background: transparent;
                border: none;
                font-family: '{FUENTE_APP}';
                font-size: 13px;
                font-weight: 900;
                selection-background-color: {accent};
                selection-color: {COLOR_FONDO_APP};
            }}
            QPushButton[semanticRole="success"] {{
                background-color: transparent;
                color: {COLOR_VERDE_OK};
                border: 2px solid {COLOR_VERDE_OK};
                border-radius: {RADIO_MD};
                font-family: '{FUENTE_APP}';
                font-size: 13px;
                font-weight: 900;
                padding: 10px 16px;
            }}
            QPushButton[semanticRole="success"]:hover {{
                background-color: {COLOR_VERDE_OK};
                color: {COLOR_FONDO_APP};
                border: 2px solid {COLOR_VERDE_OK};
            }}
            QPushButton[semanticRole="neutral"] {{
                background-color: transparent;
                color: {COLOR_CIAN};
                border: 2px solid {COLOR_CIAN};
                border-radius: {RADIO_MD};
                font-family: '{FUENTE_APP}';
                font-size: 13px;
                font-weight: 900;
                padding: 10px 16px;
            }}
            QPushButton[semanticRole="neutral"]:hover {{
                background-color: {COLOR_CIAN};
                color: {COLOR_FONDO_APP};
            }}
            """)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            _apply_windows_dark_title_bar(self)
            # Centrado sobre la PANTALLA real (descontando la barra de tareas), no sobre el centro
            # del padre: centrar en el padre podía dejar el diálogo asomando fuera de la pantalla si
            # el padre no ocupaba toda la altura visible o el mensaje era más alto de lo esperado —
            # mismo criterio ya aplicado en `catalogo_gestion.centrar_en_pantalla`.
            from PyQt6.QtWidgets import QApplication
            pantalla = QApplication.primaryScreen().availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(pantalla.center())
            self.move(frame.topLeft())
        except Exception:
            pass


# ============================================================
# BLOQUE API PÚBLICA
# ============================================================
def _qss_tactil() -> str:
    """QSS superpuesto según el perfil táctil activo (Bloque 8.3).

    Vacío en perfil NORMAL (comportamiento idéntico al actual). En TACTIL/TPV/PDA
    aumenta los objetivos táctiles de botones, inputs, combos, spinboxes, filas de
    tabla y pestañas para uso con dedo/guantes en pantallas industriales.
    """
    try:
        from src.utils import perfil_tactil
        h = perfil_tactil.altura_min_control()
        if h <= 0:
            return ""
        esp = perfil_tactil.espaciado_min()
        return (
            "QPushButton { min-height: %dpx; }\n"
            "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit { min-height: %dpx; }\n"
            "QComboBox QAbstractItemView::item { min-height: %dpx; }\n"
            "QTableView::item { padding: %dpx; }\n"
            "QHeaderView::section { min-height: %dpx; }\n"
            "QTabBar::tab { min-height: %dpx; }\n"
        ) % (h, h, h, max(4, esp // 2), h, h)
    except Exception:
        return ""


def aplicar_estilo_app(app):
    global _APP_FILTER

    if app is None:
        return

    if QFont is not None:
        app.setFont(QFont(FUENTE_APP, 10, QFont.Weight.Bold))

    app.setStyleSheet(ESTILO_GLOBAL + _qss_tactil())

    if _APP_FILTER is None and QObject is not object:
        _APP_FILTER = _SmartGlobalFilter(app)
        app.installEventFilter(_APP_FILTER)

    for widget in getattr(app, "allWidgets", lambda: [])():
        try:
            aplicar_estilo_widget(widget)
        except Exception:
            pass


def _apply_button_glow(widget):
    """Deshabilitado a petición: ningún botón de la app debe llevar el resplandor de sombra cian
    (ni ningún otro color) alrededor. Se conserva la función (y su único punto de llamada en
    `aplicar_estilo_widget`) para no tener que tocar cada sitio que la referencia, pero ya no
    aplica ningún `QGraphicsDropShadowEffect`; si un botón ya tuviera uno puesto, se retira."""
    if widget is None or not _safe_instance(widget, QPushButton):
        return
    try:
        if widget.graphicsEffect() is not None:
            widget.setGraphicsEffect(None)
    except Exception:
        pass


def _apply_spinbox_fusion_fix(widget):
    """Corrige el mismo defecto en TODO QSpinBox/QDoubleSpinBox/QDateEdit (y derivados de
    QAbstractSpinBox): sus flechas arriba/abajo, ocultas vía QSS (`QSpinBox::up-button` con
    `width:0px;height:0px`, sección QSS INPUTS) para un aspecto limpio, podían dejar el campo
    invisible o sin aceptar clic/foco en varios diálogos reales en Windows
    (`_FormDialog`/`_IntervencionDialog` de `sat_dashboard.py`, entre otros).

    Se retiran los botones por la API real de Qt (`setButtonSymbols(NoButtons)`) en vez de por CSS
    — es la técnica que ya usaba (sin saberlo, de forma aislada) un `QSpinBox` de
    `recepcion_pale.py`, que nunca mostró este defecto — con lo que el `width:0px` de la hoja de
    estilo pasa a ser irrelevante (no hay subcontrol que dimensionar). ANTES esto se reforzaba
    ADEMÁS asignando un `QStyle` "Fusion" compartido (`widget.setStyle(_FUSION_STYLE)`, un único
    objeto reutilizado por TODOS los spin box/date edit de la app) — confirmado con reproducción
    local aislada como la causa dominante de los crashes nativos intermitentes (0xc0000005 en
    Qt6Widgets.dll) en Mermas/Configuración/Cámaras/Gastos: ese único `setButtonSymbols` YA basta
    (lo dice esta misma función desde siempre, "más robusto aún") — el cambio de estilo era
    redundante y, encima, peligroso: compartir un `QStyle` entre widgets muy dispares baja el
    crash de ~70-100% a ~25%, pero darle a cada widget su PROPIA instancia (`QStyleFactory.create`
    repetido) lo empeora a ~100% — la propia construcción repetida del plugin de estilo es cara y
    frágil, no solo el compartirlo. Se retira del todo: sin él, 0 crashes reproducibles.

    Además (confirmado con reproducción real offscreen, píxel a píxel): TODO
    `QAbstractSpinBox`/`QDateEdit`/`QTimeEdit` dibuja su sección activa (día/mes/año, dígito con
    foco…) con un recuadro sólido usando `QPalette.ColorRole.Highlight`/`HighlightedText` — un
    mecanismo de PINTADO NATIVO, no un sub-control de QSS, así que `selection-background-color`/
    `selection-color` (sección QSS INPUTS, pensados para la selección de texto de un QLineEdit)
    NUNCA lo tocan. Sin tocar la paleta, ese recuadro sale con el Highlight por defecto del
    sistema (típicamente blanco/azul claro) — un parche muy visible contra el tema oscuro de la
    app, justo al lado de cualquier control vecino (p.ej. un combo "Tipo" en la misma barra de
    filtros). Se corrige UNA VEZ aquí (ya se ejecuta sobre TODO spinbox/dateedit de la app vía el
    filtro global de eventos) fijando esa paleta al mismo cian/fondo del resto del tema, en vez de
    tocarlo caso a caso en cada pantalla."""
    if widget is None or QAbstractSpinBox is None:
        return
    if not _safe_instance(widget, QAbstractSpinBox):
        return
    try:
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    except Exception:
        pass
    if QPalette is not None and QColor is not None:
        try:
            pal = widget.palette()
            resaltado = QColor(COLOR_CIAN)
            texto_resaltado = QColor(COLOR_FONDO_APP)
            for grupo in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                          QPalette.ColorGroup.Disabled):
                pal.setColor(grupo, QPalette.ColorRole.Highlight, resaltado)
                pal.setColor(grupo, QPalette.ColorRole.HighlightedText, texto_resaltado)
            widget.setPalette(pal)
        except Exception:
            pass


def aplicar_estilo_widget(widget, forzar=False):
    """`forzar=False` (por defecto): si `widget` ya pasó por aquí una vez, no repite el trabajo.
    La mayoría de widgets de la app YA reciben su estilo explícitamente, una vez, desde su propio
    helper de construcción (`_combo`/`_btn`/`_inp`/…) — el filtro global de eventos (reacciona a
    Show/Polish de CUALQUIER widget del programa) puede volver a llamar a esta misma función sobre
    ESE MISMO widget poco después, sin saber que ya se hizo — pero una guarda de idempotencia SOLA
    no basta (confirmado con reproducción local aislada, decenas de intentos): incluso eliminando
    toda redundancia, la PRIMERA llamada — la explícita, hecha por la propia factory del widget
    (`_combo`/`_btn`/`_inp`/…) justo al construirlo — YA dispara el crash nativo intermitente
    (0xc0000005 en Qt6Widgets.dll) en Mermas/Configuración/Cámaras/Gastos ~60-100% de las veces. La
    causa real es hacer este trabajo de forma SÍNCRONA mientras Qt sigue en medio de construir /
    reparentar ese widget (p.ej. dentro de `layout.addLayout(...)`, o en su propio `QEvent.Polish`)
    — no la cantidad de veces que se llama. Por eso el trabajo real se DIFIERE siempre con
    `QTimer.singleShot(0, …)`: dejar que Qt termine de procesar lo que esté haciendo con el widget
    en ESTE ciclo de eventos, y aplicar el estilo en el siguiente, con la pila limpia — 0 crashes
    en la reproducción local tras este cambio (era 60-100% con la llamada síncrona, con o sin
    guarda de idempotencia). `forzar=True` lo hace síncrono e incondicional a propósito, para los
    pocos casos que necesitan reaplicar YA tras un cambio de estado en tiempo de ejecución sobre un
    widget que lleva tiempo construido y mostrado (p.ej. `semanticRole` cambiando en un botón)."""
    if widget is None or Qt is None:
        return

    def _trabajo_real():
        _set_widget_background_flag(widget)
        _apply_font(widget)
        _set_widget_cursor(widget)
        _apply_button_role(widget)
        _apply_button_glow(widget)
        _apply_spinbox_fusion_fix(widget)
        _apply_combo_extras(widget)
        _apply_dialog_semantics(widget)
        _apply_windows_dark_title_bar(widget)

        try:
            object_name = widget.objectName() if hasattr(widget, "objectName") else ""
        except Exception:
            object_name = ""

        if object_name in {
            "btn_sidebar",
            "btn_sidebar_exit",
            "btn_primario",
            "btn_traspaso_land",
            "btn_secundario",
            "btn_peligro",
            "btn_neon",
            "btn_icono",
            "btn_icono_peligro",
            "login_combo_perfil",
            "combo_popup_view",
            "combo_popup_container",
            "password_frame",
            "card_neon",
            "titulo_cian",
            "titulo_logistico",
            "subtitulo_muted",
            "texto_auxiliar",
            "panel_bienvenida",
            "panel_neon_soft",
            "panel_dialogo_logistico",
            "contenido_logistica",
            "input_buscador",
            "item_frame_articulo",
            "item_frame_logistico",
            "scanner_status",
            "feed_video",
            "contenedor_tabla_estandar",
            "tabla_estandar_smart",
        }:
            _repolish(widget)

    # `forzar=True` salta la guarda de idempotencia (para reaplicar tras un cambio de estado real
    # en tiempo de ejecución) pero NUNCA ejecuta de forma síncrona — un `setProperty(...)`
    # CUALQUIERA (no hace falta que sea `semanticRole`; cualquier propiedad dinámica, p. ej.
    # `sin_glow` en `_btn_x`) dispara su propio `QEvent.DynamicPropertyChange` de inmediato, dentro
    # de la propia factory del widget, ANTES de que ese widget tenga padre — ejecutar aquí de forma
    # síncrona todo el pipeline sobre un widget a medio construir (confirmado con `_btn_x`: se
    # volvía nativo — `WA_NativeWindow` — solo por llevar un `setProperty` cualquiera, con el
    # síntoma real reportado de que Windows no lograba colocar su ventana nativa donde tocaba y el
    # clic caía sobre lo que hubiera debajo) era exactamente el mismo patrón de reentrada peligrosa
    # que ya se corrigió para Show/Polish — solo que sin la guarda de "una vez" (`forzar` existe
    # precisamente para NO tener esa guarda). Diferir con `QTimer.singleShot(0, …)` sí es seguro
    # aquí también: cuando corre, el widget ya tiene padre (todo lo que hace la factory después de
    # `setProperty` ya ha ocurrido).
    if not forzar:
        if getattr(widget, "_sm_estilo_aplicado_completo", False):
            return
        try:
            widget._sm_estilo_aplicado_completo = True
        except Exception:
            pass
    if QTimer is not None:
        QTimer.singleShot(0, lambda: _vivo(widget) and _trabajo_real())
    else:
        _trabajo_real()


def mostrar_mensaje(parent, titulo, mensaje, nivel="info", botones=None):
    dialogo = SmartMessageDialog(
        parent=parent,
        title=titulo,
        message=mensaje,
        level=nivel,
        buttons=botones or ["ok"],
    )
    aplicar_estilo_widget(dialogo)
    dialogo.exec()
    return dialogo.dialog_result


def mostrar_texto_celda(parent, texto):
    """Popup pequeño y de SOLO LECTURA con el contenido completo de una celda de tabla (sin
    truncar/elidir) — sin ninguna opción de edición. Reutiliza el mismo diseño visual que
    `mostrar_mensaje`/`SmartMessageDialog` (icono, panel, tipografía, botón), con el mensaje en un
    QTextEdit de solo lectura y seleccionable/copiable en vez del QLabel habitual. Disparado desde
    el doble clic global sobre celdas de tabla (ver `_SmartGlobalFilter.eventFilter`, sección
    "doble clic en celda de tabla"). Celda vacía → no-op silencioso (no tiene sentido mostrar un
    popup vacío para una acción de solo visualización)."""
    texto = str(texto if texto is not None else "").strip()
    if not texto:
        return None
    try:
        from src.utils.i18n import tr
        titulo = tr("common.cell_content", default="Contenido de la celda")
    except Exception:
        titulo = "Contenido de la celda"
    dialogo = SmartMessageDialog(
        parent=parent,
        title=titulo,
        message=texto,
        level="info",
        buttons=["ok"],
        seleccionable=True,
    )
    aplicar_estilo_widget(dialogo)
    dialogo.exec()
    return dialogo.dialog_result


def _tabla_del_viewport(watched):
    """Si `watched` es el viewport de una QTableWidget/QTableView, devuelve la tabla dueña; si no,
    None. QTableWidget hereda de QTableView, así que una sola comprobación cubre ambas — incluida
    `EnterpriseTable.tabla` (`src/gui/components/enterprise.py`), que es un QTableWidget normal
    envuelto en un QWidget contenedor (el filtro global opera sobre el widget real de Qt, no sobre
    el envoltorio, así que la cubre automáticamente sin ningún cambio en `enterprise.py`)."""
    if QTableView is None:
        return None
    try:
        padre = watched.parentWidget() if hasattr(watched, "parentWidget") else None
        if (
            padre is not None
            and _safe_instance(padre, QTableView)
            and padre.viewport() is watched
        ):
            return padre
    except Exception:
        pass
    return None


def _tabla_tiene_doble_clic_propio(tabla):
    """True si la PANTALLA que construyó `tabla` ya conectó su propio manejador al doble clic
    (`cellDoubleClicked`/`itemDoubleClicked` de QTableWidget, o `doubleClicked` directamente) — en
    cuyo caso el popup genérico de "ver celda completa" NO debe interferir (p. ej. las tablas que ya
    abren un detalle/picking/expediente al hacer doble clic, ver CLAUDE.md). Se cuenta con
    `receivers()`, descontando el único receptor INTERNO que Qt conecta siempre en todo
    QTableWidget (su propio traductor `doubleClicked` → `cellDoubleClicked`/`itemDoubleClicked`;
    confirmado con una QTableWidget recién creada, sin ninguna conexión de la app: ya reporta 1
    receptor en `doubleClicked` y 0 en `cellDoubleClicked`/`itemDoubleClicked` — conectar a
    cualquiera de estas dos últimas NO añade receptores a `doubleClicked`), para no confundir esa
    conexión interna con un manejador real de la pantalla."""
    total = 0
    es_table_widget = _safe_instance(tabla, QTableWidget)
    try:
        n = tabla.receivers(tabla.doubleClicked)
        if es_table_widget:
            n = max(0, n - 1)
        total += n
    except Exception:
        pass
    if es_table_widget:
        try:
            total += tabla.receivers(tabla.cellDoubleClicked)
        except Exception:
            pass
        try:
            total += tabla.receivers(tabla.itemDoubleClicked)
        except Exception:
            pass
    return total > 0


def _manejar_doble_clic_celda(watched, event):
    """Handler de la regla "doble clic en celda de tabla → popup de solo lectura con el texto
    completo" (ver CLAUDE.md). Devuelve True si el evento quedó gestionado aquí (no debe seguir
    propagándose). No toca NADA si: no es un doble clic con el botón izquierdo sobre el viewport de
    una tabla; la tabla ya tiene su propio manejador de doble clic (`_tabla_tiene_doble_clic_propio`);
    el doble clic dispara la edición nativa de la celda (`EditTrigger.DoubleClicked`/
    `AllEditTriggers`) o la celda ya está en edición (`State.EditingState`); o no hay una celda real
    bajo el cursor."""
    if QAbstractItemView is None or Qt is None:
        return False
    try:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
    except Exception:
        return False
    tabla = _tabla_del_viewport(watched)
    if tabla is None:
        return False
    try:
        if tabla.state() == QAbstractItemView.State.EditingState:
            return False
        if bool(tabla.editTriggers() & QAbstractItemView.EditTrigger.DoubleClicked):
            return False
    except Exception:
        pass
    if _tabla_tiene_doble_clic_propio(tabla):
        return False
    try:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
    except Exception:
        return False
    try:
        indice = tabla.indexAt(pos)
        if not indice.isValid():
            return False
        texto = indice.data(Qt.ItemDataRole.DisplayRole)
    except Exception:
        return False
    texto = str(texto if texto is not None else "").strip()
    if not texto:
        # Celda vacía: no-op silencioso, pero consumimos igualmente el evento — ninguna otra
        # pantalla depende de este doble clic (ya descartado arriba), así que no hay nada más que
        # deba recibirlo.
        return True
    try:
        mostrar_texto_celda(tabla.window(), texto)
    except Exception:
        pass
    return True


_COMPLETER_POPUP_SS = (
    "QListView{background:#161B22;color:#FFFFFF;border:2px solid #00FFC6;"
    "border-radius:12px;padding:6px;outline:none;font-family:'Segoe UI';font-size:13px;}"
    "QListView::item{padding:7px 10px;border-radius:7px;min-height:20px;}"
    "QListView::item:selected{background:#00FFC6;color:#0E1117;}"
    # Hover swap (pasar el ratón por encima), no solo la fila activa por teclado.
    "QListView::item:hover{background:#00FFC6;color:#0E1117;}"
    # Fondo de la pista SÓLIDO e IGUAL al de la lista en TODA su superficie (base + vertical +
    # horizontal): con "transparent", o dejando la variante horizontal sin fijar, se ve el fondo
    # real del popup nativo por debajo (que no es este color) — contraste no deseado. El margen que
    # separa visualmente el "pill" de los extremos va en el HANDLE, no en la pista: puesto en la
    # pista (`QScrollBar:vertical{margin:...}`), el margen reserva una franja en los extremos que
    # NINGUNA de las reglas de abajo llega a pintar (ni add-page/sub-page, que quedan dentro de esa
    # franja) — ahí se colaba el fondo real del popup (leído con captura de pantalla + muestreo de
    # píxel, confirmado un color distinto justo en esos bordes). Sin margen en la pista, la pintamos
    # de punta a punta y el hueco del "pill" lo da solo el margen del handle.
    "QScrollBar{background:#161B22;}"
    "QScrollBar:vertical{background:#161B22;width:14px;margin:0px;}"
    "QScrollBar::handle:vertical{background:#00FFC6;border-radius:4px;min-height:24px;"
    "margin:8px 3px 8px 3px;}"
    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;width:0;}"
    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:#161B22;}"
)

_ROUNDED_VIEW_CLS = None


def _rounded_view_cls():
    """QListView con máscara redondeada propia (showEvent/resizeEvent). Es fiable como
    popup de QCompleter porque el border-radius del QSS no recorta un popup top-level."""
    global _ROUNDED_VIEW_CLS
    if _ROUNDED_VIEW_CLS is None:
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QBitmap, QRegion
        from PyQt6.QtWidgets import QListView

        class _RoundedListView(QListView):
            _r = 12

            def _aplicar_mascara(self):
                if self.width() > 0 and self.height() > 0:
                    bmp = QBitmap(self.size()); bmp.fill(Qt.GlobalColor.color0)
                    p = QPainter(bmp); p.setBrush(Qt.GlobalColor.color1); p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(QRect(0, 0, self.width(), self.height()), self._r, self._r)
                    p.end()
                    self.setMask(QRegion(bmp))

            def showEvent(self, e):
                super().showEvent(e); self._aplicar_mascara()

            def resizeEvent(self, e):
                super().resizeEvent(e); self._aplicar_mascara()

        _ROUNDED_VIEW_CLS = _RoundedListView
    return _ROUNDED_VIEW_CLS


def estilizar_completer(completer):
    """Esquinas redondeadas reales + estilo neón + scrollbar turquesa redondeada en el
    popup de sugerencias. Para TODAS las barras de búsqueda de artículos de la app."""
    try:
        view = _rounded_view_cls()()
        view.setStyleSheet(_COMPLETER_POPUP_SS)
        # Sin esto, un texto de opción algo más ancho que el popup activa una scrollbar horizontal
        # SIN estilizar (barra nativa) — y la esquina donde se cruzaría con la vertical queda sin
        # pintar del color de fondo, mostrando contraste. La lista ya recorta el texto largo, no
        # hace falta desplazamiento lateral.
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        completer.setPopup(view)
    except Exception:
        pass


def mostrar_confirmacion(parent, titulo, mensaje):
    resultado = mostrar_mensaje(
        parent=parent,
        titulo=titulo,
        mensaje=mensaje,
        nivel="question",
        botones=["yes", "no"],
    )
    return resultado == SmartMessageDialog.ROLE_TO_RESULT["yes"]


# ============================================================
# BLOQUE HOJAS DE ESTILO QSS
# ============================================================

QSS_ROOT = f"""
/* =====================================================
   SECTION QSS ROOT
   ===================================================== */

QMainWindow, QDialog, QWidget {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    font-family: '{FUENTE_APP}';
    font-size: 13px;
    font-weight: 900;
    selection-background-color: {COLOR_GRIS_HOVER};
    selection-color: {COLOR_CIAN};
}}

QWidget#panel_raiz,
QWidget#panel_contenido,
QFrame#panel_raiz,
QFrame#panel_contenido {{
    background-color: transparent;
    border: none;
}}

QLabel, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit, QTableWidget, QTableView, QListWidget, QListView, QTreeWidget,
QTreeView, QGroupBox, QCheckBox, QRadioButton, QTabBar, QMenu, QHeaderView,
QPushButton, QToolButton {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QToolTip {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_MD};
    padding: 8px 12px;
}}

QFrame#panel_oscuro,
QFrame#card,
QFrame#card_neon,
QFrame#contenedor_neon,
QWidget#card,
QWidget#card_neon,
QWidget#panel_neon,
QFrame#panel_neon,
QWidget#dialogo_neon,
QFrame#dialogo_neon {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QWidget#panel_neon_soft,
QFrame#panel_neon_soft,
QWidget#panel_bienvenida,
QFrame#panel_bienvenida,
QWidget#panel_dialogo_logistico,
QFrame#panel_dialogo_logistico {{
    background-color: {COLOR_GRIS_PANEL};
    border: 1px solid {COLOR_BORDE};
    border-radius: {RADIO_XL};
}}

QStackedWidget#contenido_logistica,
QScrollArea#scroll_transparente,
QWidget#scroll_transparente {{
    background-color: transparent;
    border: none;
}}

QLabel#titulo_principal {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 26px;
    font-weight: 900;
    letter-spacing: 2px;
    background: transparent;
    border: none;
}}

QLabel#subtitulo_principal {{
    color: {COLOR_CIAN};
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
    background: transparent;
    border: none;
}}

QLabel#titulo_cian,
QLabel#titulo_logistico {{
    color: {COLOR_CIAN};
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}}

QLabel#titulo_cian[tituloProcesando="true"],
QLabel#titulo_logistico[tituloProcesando="true"] {{
    color: {COLOR_AMBAR};
    font-size: 24px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#subtitulo_muted,
QLabel#texto_auxiliar,
QLabel#origen_info {{
    color: {COLOR_TEXTO_SECUNDARIO};
    font-size: 14px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#icono_hero,
QLabel#icono_modulo,
QLabel#icono_logistico {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 96px;
    background: transparent;
    border: none;
}}

QLabel#item_codigo {{
    color: {COLOR_CIAN};
    font-size: 10px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#item_nombre {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 13px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#etiqueta_secundaria,
QLabel#campo_label,
QLabel#login_section_title {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-family: 'Segoe UI';
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
    border: none;
    background: transparent;
}}

QLabel#mensaje_neon,
QLabel#estado_neon,
QLabel#badge_neon {{
    color: {COLOR_CIAN};
    background-color: rgba(0, 255, 198, 0.06);
    border: 1px solid rgba(0, 255, 198, 0.30);
    border-radius: {RADIO_MD};
    padding: 8px 12px;
}}

QLabel#scanner_status {{
    color: {COLOR_TEXTO_SECUNDARIO};
    font-size: 13px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#scanner_status[estado="ok"] {{
    color: {COLOR_CIAN};
}}

QLabel#scanner_status[estado="error"] {{
    color: {COLOR_ROJO_ERROR};
}}
"""

QSS_SIDEBAR = f"""
/* =====================================================
   SECTION QSS SIDEBAR
   ===================================================== */

QFrame#sidebar,
QFrame#sidebar_admin,
QFrame#sidebar_logistica,
QFrame#sidebar_modulo {{
    background-color: {COLOR_FONDO_SIDEBAR};
    border-right: 1px solid {COLOR_BORDE_SIDEBAR};
    border-radius: 0px;
}}

QLabel#sidebar_title,
QLabel#lbl_sidebar_titulo,
QLabel#lbl_modulo_sidebar {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 16px;
    font-weight: 900;
    margin-left: 30px;
    margin-bottom: 35px;
    letter-spacing: 2px;
    border: none;
    background: transparent;
}}

QPushButton#btn_sidebar {{
    text-align: left;
    padding: 6px 8px 6px 28px;
    color: #FFFFFF;
    background-color: transparent;
    border: none;
    border-left: 4px solid transparent;
    border-radius: 0px;
    font-family: 'Segoe UI';
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.5px;
    margin: 0px;
    outline: none;
}}

QPushButton#btn_sidebar:hover {{
    background-color: #FFFFFF;
    color: {COLOR_FONDO_SIDEBAR};
}}

QPushButton#btn_sidebar:checked {{
    background-color: #1A2230;
    color: {COLOR_CIAN};
    border: none;
    border-left: 4px solid {COLOR_CIAN};
}}

/* Variante +2pt (propiedad dinámica lg=true): sidebars Catálogo/Compras/Contab./RRHH.
   No rompe el hover/checked porque va en el QSS global, no inline en el widget. */
QPushButton#btn_sidebar[lg="true"] {{
    font-size: 14px;
}}

QPushButton#btn_sidebar_exit {{
    text-align: left;
    padding: 6px 8px 6px 28px;
    color: {COLOR_ROJO_ERROR};
    background-color: transparent;
    border: none;
    border-radius: 0px;
    font-family: 'Segoe UI';
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.5px;
}}

QPushButton#btn_sidebar_exit:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
}}
"""

QSS_LOGIN = f"""
/* =====================================================
   SECTION QSS LOGIN
   Do not change visual identity of login.
   ===================================================== */

QWidget#card_neon,
QFrame#card_neon {{
    background-color: {COLOR_GRIS_PANEL};
    border: 1px solid {COLOR_BORDE};
    border-radius: {RADIO_XXL};
}}

QFrame#password_frame {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 16px;
}}

QFrame#password_frame:hover {{
    background-color: {COLOR_GRIS_SUAVE};
    border: 2px solid {COLOR_CIAN};
}}

QLineEdit#txt_password {{
    background-color: transparent;
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    padding: 0px;
}}

QComboBox#login_combo_perfil {{
    background-color: {COLOR_FONDO_APP_SECUNDARIO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
    padding: 0px 16px;
    min-height: 56px;
    font-size: 13px;
    font-weight: 900;
    selection-background-color: {COLOR_FONDO_APP_SECUNDARIO};
    selection-color: {COLOR_TEXTO_PRINCIPAL};
    outline: none;
}}

QComboBox#login_combo_perfil:hover,
QComboBox#login_combo_perfil:focus,
QComboBox#login_combo_perfil:on {{
    background-color: {COLOR_FONDO_WIDGET};
    border: 2px solid {COLOR_CIAN};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QComboBox#login_combo_perfil::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 0px;
    border: none;
    background: transparent;
}}

QComboBox#login_combo_perfil::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border: none;
    margin: 0px;
}}

QComboBox#login_combo_perfil QAbstractItemView,
QListView#combo_popup_view {{
    background-color: {COLOR_FONDO_APP};
    alternate-background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
    padding: 8px 8px;
    margin: 0px;
    outline: 0px;
    selection-background-color: transparent;
    selection-color: {COLOR_TEXTO_PRINCIPAL};
    show-decoration-selected: 0;
}}

QComboBox#login_combo_perfil QAbstractItemView::viewport,
QListView#combo_popup_view::viewport {{
    background-color: {COLOR_FONDO_APP};
    border: none;
    border-radius: 18px;
}}

QComboBox#login_combo_perfil QAbstractItemView::item,
QListView#combo_popup_view::item {{
    min-height: 46px;
    padding: 10px 18px;
    margin: 6px 8px;
    background-color: #091521;
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    border-radius: 18px;
}}

QComboBox#login_combo_perfil QAbstractItemView::item:hover,
QComboBox#login_combo_perfil QAbstractItemView::item:selected,
QListView#combo_popup_view::item:hover,
QListView#combo_popup_view::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: none;
    border-radius: 14px;
}}

QListView#combo_popup_view,
QListView#combo_popup_view QWidget,
QListView#combo_popup_view QFrame,
QListView#combo_popup_view QAbstractScrollArea {{
    background-color: {COLOR_FONDO_APP_SECUNDARIO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    border-radius: 18px;
}}

#combo_popup_container,
QWidget#combo_popup_container,
QFrame#combo_popup_container,
QDialog#combo_popup_container {{
    background-color: transparent;
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
}}
"""
QSS_INPUTS = f"""
/* =====================================================
   SECTION QSS INPUTS
   ===================================================== */

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 10px 12px;
    font-size: 14px;
    selection-background-color: {COLOR_CIAN};
    selection-color: {COLOR_FONDO_APP};
}}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QDateEdit:hover, QTimeEdit:hover {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QLineEdit#empName:hover {{
    background-color: transparent;
    border: 1px solid transparent;
    color: #D0DCE8;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
}}

QComboBox:on {{
    border: 2px solid transparent;
}}

QLineEdit#input_buscador[flashHighlight="true"] {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 10px 12px 10px 20px;
}}

QLineEdit[readOnly="true"], QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{
    background-color: #131820;
    color: {COLOR_TEXTO_SECUNDARIO};
}}

QLineEdit::placeholder, QTextEdit::placeholder, QPlainTextEdit::placeholder {{
    color: {COLOR_TEXTO_MUTED};
}}

QComboBox {{
    padding-right: 28px;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    margin-right: 4px;
    border: none;
    background: transparent;
}}

QComboBox::down-arrow {{
    image: url({_ARROW_ICON});
    width: 14px;
    height: 14px;
}}

QComboBox QAbstractItemView,
QListView#combo_popup_generic,
QMenu {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
    padding: 6px 0px;
    outline: 0px;
    selection-background-color: {COLOR_CIAN};
    selection-color: {COLOR_FONDO_APP};
}}

QComboBox QAbstractItemView::item,
QListView#combo_popup_generic::item,
QMenu::item {{
    min-height: 30px;
    padding: 8px 14px;
    margin: 2px 6px;
    background-color: {COLOR_FONDO_APP};
    border: none;
    border-radius: {RADIO_LG};
}}

QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected,
QListView#combo_popup_generic::item:hover,
QListView#combo_popup_generic::item:selected,
QMenu::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

/* Popup view used by _sm_combo_popup container: border lives on the container,
   so the view itself must have no border at all. This rule has specificity
   (0,1,1) and appears last, beating QComboBox QAbstractItemView at (0,0,2). */
QListView#_sm_combo_view {{
    border: none;
    background-color: {COLOR_FONDO_APP};
    outline: 0px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
"""

QSS_BUTTONS = f"""
/* =====================================================
   SECTION QSS BUTTONS
   ===================================================== */

QPushButton {{
    font-size: 13px;
    font-weight: 900;
    border-radius: {RADIO_MD};
    padding: 10px 16px;
    background-color: transparent;
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QPushButton:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_primario {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    outline: none;
}}

QPushButton#btn_primario:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
    outline: none;
}}

QPushButton#btn_primario:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
    outline: none;
}}

QPushButton#btn_primario:focus {{
    outline: none;
}}

QPushButton#btn_traspaso_land {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    text-align: center;
    padding: 10px 0px 10px 12px;
}}

QPushButton#btn_traspaso_land:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_traspaso_land:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_secundario {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_secundario:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_secundario:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_peligro {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton#btn_peligro:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton#btn_peligro:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton#btn_icono {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 0px;
}}

QPushButton#btn_icono:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_icono:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_icono_peligro {{
    background-color: transparent;
    color: {COLOR_ROJO_ERROR};
    border: none;
    border-radius: 20px;
    padding: 6px;
}}

QPushButton#btn_icono_peligro:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_icono_peligro:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton[semanticRole="success"],
QToolButton[semanticRole="success"] {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_VERDE_OK};
    border: 2px solid {COLOR_VERDE_OK};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="success"]:hover,
QToolButton[semanticRole="success"]:hover {{
    background-color: {COLOR_VERDE_OK};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_VERDE_OK};
}}

QPushButton[semanticRole="success"]:pressed,
QToolButton[semanticRole="success"]:pressed {{
    background-color: {COLOR_VERDE_OK_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton[semanticRole="neutral"],
QToolButton[semanticRole="neutral"] {{
    background-color: {COLOR_GRIS_NEUTRO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_GRIS_NEUTRO};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="neutral"]:hover,
QToolButton[semanticRole="neutral"]:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_GRIS_NEUTRO_HOVER};
    border: 2px solid {COLOR_GRIS_NEUTRO_HOVER};
}}

QPushButton[semanticRole="neutral"]:pressed,
QToolButton[semanticRole="neutral"]:pressed {{
    background-color: {COLOR_GRIS_NEUTRO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton[semanticRole="danger"],
QToolButton[semanticRole="danger"] {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="danger"]:hover,
QToolButton[semanticRole="danger"]:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton[semanticRole="danger"]:pressed,
QToolButton[semanticRole="danger"]:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QToolButton {{
    border-radius: {RADIO_MD};
    color: {COLOR_CIAN};
    background-color: transparent;
    border: 2px solid transparent;
}}

QToolButton:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QToolButton:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton:disabled,
QToolButton:disabled {{
    background-color: #161B22;
    color: #6B7280;
    border: 2px solid #2B3440;
}}

QCheckBox, QRadioButton {{
    spacing: 10px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
}}

QCheckBox::indicator:unchecked,
QRadioButton::indicator:unchecked {{
    border: 1px solid {COLOR_BORDE};
    background: {COLOR_GRIS_PANEL};
    border-radius: 9px;
}}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {{
    border: 1px solid {COLOR_CIAN};
    background: {COLOR_CIAN};
    border-radius: 9px;
}}
"""

QSS_TABS = f"""
/* =====================================================
   SECTION QSS TABS
   ===================================================== */

QTabWidget::pane {{
    border: 1px solid {COLOR_BORDE};
    background: {COLOR_GRIS_PANEL};
    border-radius: {RADIO_LG};
    top: -1px;
}}

QTabBar::tab {{
    background: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_SECUNDARIO};
    padding: 12px 20px;
    font-weight: 900;
    border-top-left-radius: {RADIO_SM};
    border-top-right-radius: {RADIO_SM};
    margin-right: 2px;
}}

QTabBar::tab:hover {{
    background: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QTabBar::tab:selected {{
    background: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border-bottom: 2px solid {COLOR_CIAN};
}}
"""
QSS_TABLES = f"""
/* =====================================================
   SECTION QSS TABLES
   ===================================================== */

QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    background-color: {COLOR_GRIS_PANEL};
    alternate-background-color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_TABLAS};
    color: {COLOR_TEXTO_PRINCIPAL};
    gridline-color: transparent;
    selection-background-color: {COLOR_GRIS_HOVER};
    selection-color: {COLOR_CIAN};
    font-size: 13px;
    font-weight: 900;
    outline: 0;
}}

QTableWidget::item, QTableView::item, QTreeWidget::item, QTreeView::item,
QListWidget::item, QListView::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:hover, QTableView::item:hover, QTreeWidget::item:hover,
QTreeView::item:hover, QListWidget::item:hover, QListView::item:hover {{
    background-color: rgba(0, 255, 198, 0.10);
}}

QTableWidget::item:selected, QTableView::item:selected, QTreeWidget::item:selected,
QTreeView::item:selected, QListWidget::item:selected, QListView::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QHeaderView::section {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDE};
    font-weight: 900;
}}

QHeaderView::section:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QHeaderView::section:horizontal:first {{
    border-top-left-radius: {RADIO_LG};
}}

QHeaderView::section:horizontal:last {{
    border-top-right-radius: {RADIO_LG};
}}

QTableCornerButton::section {{
    background-color: {COLOR_GRIS_PANEL};
    border: none;
    border-top-left-radius: {RADIO_LG};
}}

QFrame#item_frame_articulo,
QFrame#item_frame_logistico {{
    background-color: {COLOR_GRIS_PANEL};
    border-radius: 15px;
    padding: 2px;
}}

QFrame#item_frame_articulo {{
    border: 1px solid {COLOR_BORDE};
}}

QFrame#item_frame_logistico {{
    border: 1px solid #3498DB;
}}

QFrame#item_frame_articulo:hover,
QFrame#item_frame_logistico:hover {{
    border: 1px solid {COLOR_CIAN};
}}

QFrame#item_frame_articulo[flashHighlight="true"],
QFrame#item_frame_logistico[flashHighlight="true"] {{
    border: 2px solid {COLOR_CIAN};
}}

/* Plantilla universal de tabla Smart Manager */
QFrame#contenedor_tabla_estandar,
QFrame#frame_tabla_neon_logistica {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QTableWidget,
QFrame#contenedor_tabla_estandar QTableView,
QFrame#frame_tabla_neon_logistica QTableWidget,
QFrame#frame_tabla_neon_logistica QTableView {{
    border: none;
    border-radius: {RADIO_TABLAS};
    outline: none;
    background: transparent;
    alternate-background-color: {COLOR_FONDO_APP};
}}

QTableWidget#tabla_estandar_smart,
QTableView#tabla_estandar_smart {{
    border: none;
    border-radius: {RADIO_TABLAS};
    background: transparent;
}}

QFrame#contenedor_tabla_estandar QHeaderView,
QFrame#frame_tabla_neon_logistica QHeaderView {{
    border: none;
    background: transparent;
}}

QFrame#contenedor_tabla_estandar QHeaderView::section,
QFrame#frame_tabla_neon_logistica QHeaderView::section {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDE};
    font-weight: 900;
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:hover,
QFrame#frame_tabla_neon_logistica QHeaderView::section:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:horizontal:first,
QFrame#frame_tabla_neon_logistica QHeaderView::section:horizontal:first {{
    border-top-left-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:horizontal:last,
QFrame#frame_tabla_neon_logistica QHeaderView::section:horizontal:last {{
    border-top-right-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QTableCornerButton::section,
QFrame#frame_tabla_neon_logistica QTableCornerButton::section {{
    background: transparent;
    border: none;
}}

/* ── Scrollbars inside table/list widgets ─────────────────────────────────
   Groove: transparent (border-radius on groove doesn't work in Qt QSS).
   Handle: cyan capsule inset 22 px from top/bottom so it never enters
   the CornerCover zone (20 px radius) and always shows rounded ends.        */
QTableWidget QScrollBar:vertical,
QTreeWidget QScrollBar:vertical,
QListWidget QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 22px 0px 22px 0px;
}}

QTableWidget QScrollBar::handle:vertical,
QTreeWidget QScrollBar::handle:vertical,
QListWidget QScrollBar::handle:vertical {{
    background: {COLOR_CIAN};
    min-height: 20px;
    border-radius: 4px;
}}

QTableWidget QScrollBar::add-line:vertical,
QTableWidget QScrollBar::sub-line:vertical,
QTreeWidget QScrollBar::add-line:vertical,
QTreeWidget QScrollBar::sub-line:vertical,
QListWidget QScrollBar::add-line:vertical,
QListWidget QScrollBar::sub-line:vertical {{
    border: none;
    background: none;
    height: 0px;
}}

QTableWidget QScrollBar::add-page:vertical,
QTableWidget QScrollBar::sub-page:vertical,
QTreeWidget QScrollBar::add-page:vertical,
QTreeWidget QScrollBar::sub-page:vertical,
QListWidget QScrollBar::add-page:vertical,
QListWidget QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QTableWidget QScrollBar:horizontal,
QTreeWidget QScrollBar:horizontal,
QListWidget QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 22px 0px 22px;
}}

QTableWidget QScrollBar::handle:horizontal,
QTreeWidget QScrollBar::handle:horizontal,
QListWidget QScrollBar::handle:horizontal {{
    background: {COLOR_CIAN};
    min-width: 20px;
    border-radius: 4px;
}}

QTableWidget QScrollBar::add-line:horizontal,
QTableWidget QScrollBar::sub-line:horizontal,
QTreeWidget QScrollBar::add-line:horizontal,
QTreeWidget QScrollBar::sub-line:horizontal,
QListWidget QScrollBar::add-line:horizontal,
QListWidget QScrollBar::sub-line:horizontal {{
    border: none;
    background: none;
    width: 0px;
}}

QTableWidget QScrollBar::add-page:horizontal,
QTableWidget QScrollBar::sub-page:horizontal,
QTreeWidget QScrollBar::add-page:horizontal,
QTreeWidget QScrollBar::sub-page:horizontal,
QListWidget QScrollBar::add-page:horizontal,
QListWidget QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""

QSS_SCROLLBARS = f"""
/* =====================================================
   SECTION QSS SCROLLBARS
   Qt does NOT apply border-radius to the scrollbar groove background,
   so the groove is kept transparent everywhere. Only the ::handle has
   a visible background; its border-radius creates the capsule shape
   that gives rounded ends on every scrollbar in the app.
   ===================================================== */

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 0px;
}}

QScrollBar::handle:vertical {{
    background: {COLOR_CIAN};
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 2px;
}}

QScrollBar::handle:horizontal {{
    background: {COLOR_CIAN};
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    border: none;
    background: none;
    width: 0px;
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""

QSS_DIALOGS = f"""
/* =====================================================
   SECTION QSS DIALOGS
   ===================================================== */

QDialog, QInputDialog, QMessageBox {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QDialog#dlg_incidencia,
QDialog#dlg_entrada_cantidad {{
    background: transparent;
    border: none;
}}

QMessageBox#smart_message_box {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QDialog QLabel,
QInputDialog QLabel,
QMessageBox QLabel {{
    color: {COLOR_TEXTO_PRINCIPAL};
    background: transparent;
    font-size: 13px;
    font-weight: 900;
    padding: 4px 2px;
}}

QDialog QPushButton,
QInputDialog QPushButton,
QMessageBox QPushButton {{
    min-width: 120px;
    border-radius: {RADIO_MD};
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QMessageBox QLabel {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QInputDialog QLabel,
QInputDialog QLineEdit,
QInputDialog QComboBox {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}
"""

QSS_SCANNER = f"""
/* =====================================================
   SECTION QSS SCANNER
   ===================================================== */

QDialog#dlg_scan,
QDialog#dlg_camara,
QDialog#scanner_dialog {{
    background: transparent;
    border: none;
}}

QFrame#cuerpo_ventana,
QFrame#cuerpo_ventana_scan,
QFrame#cuerpo_ventana_camara,
QFrame#dialogo_scan {{
    background-color: {COLOR_NEGRO_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_SCANNER};
}}

QLabel#lbl_titulo_scan,
QLabel#titulo_scan,
QLabel#titulo_contexto_scan {{
    color: {COLOR_CIAN};
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 4px;
    border: none;
    background: transparent;
}}

QLabel#feed_video,
QLabel#lbl_video {{
    background: transparent;
    border: none;
    qproperty-alignment: AlignCenter;
}}

QLabel#feed_video[activo="true"],
QLabel#lbl_video[activo="true"] {{
    background: transparent;
    border: none;
}}

QLabel#info_scan,
QLabel#lbl_info_scan {{
    color: {COLOR_TEXTO_MUTED};
    font-size: 10px;
    font-weight: 800;
    border: none;
    background: transparent;
}}

QPushButton#btn_abortar_scan,
QPushButton#btn_cerrar_scan,
QPushButton#btn_cerrar {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_ROJO_ERROR};
    border-radius: 15px;
    font-weight: 900;
}}

QPushButton#btn_abortar_scan:hover,
QPushButton#btn_cerrar_scan:hover,
QPushButton#btn_cerrar:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
}}
"""

ESTILO_GLOBAL = (
    QSS_ROOT
    + QSS_SIDEBAR
    + QSS_LOGIN
    + QSS_INPUTS
    + QSS_BUTTONS
    + QSS_TABS
    + QSS_TABLES
    + QSS_SCROLLBARS
    + QSS_DIALOGS
    + QSS_SCANNER
)


__all__ = [
    "FUENTE_APP",
    "COLOR_CIAN",
    "COLOR_CIAN_HOVER",
    "COLOR_CIAN_PRESION",
    "COLOR_VERDE_OK",
    "COLOR_VERDE_OK_HOVER",
    "COLOR_VERDE_OK_PRESION",
    "COLOR_FONDO_APP",
    "COLOR_FONDO_APP_SECUNDARIO",
    "COLOR_FONDO_SIDEBAR",
    "COLOR_FONDO_WIDGET",
    "COLOR_GRIS_PANEL",
    "COLOR_GRIS_HOVER",
    "COLOR_GRIS_SUAVE",
    "COLOR_BORDE",
    "COLOR_BORDE_SIDEBAR",
    "COLOR_TEXTO_PRINCIPAL",
    "COLOR_TEXTO_SECUNDARIO",
    "COLOR_TEXTO_MUTED",
    "COLOR_ROJO_ERROR",
    "COLOR_ROJO_HOVER",
    "COLOR_ROJO_PRESION",
    "COLOR_AMBAR",
    "RADIO_TABLAS",
    "ESTILO_GLOBAL",
    "aplicar_estilo_app",
    "aplicar_estilo_widget",
    "mostrar_confirmacion",
    "mostrar_mensaje",
    "repolish_widget",
    "feedback_lineedit_exito",
    "feedback_frame_item_resaltado",
    "construir_plantilla_camara",
    "construir_tabla_estilizada",
]
