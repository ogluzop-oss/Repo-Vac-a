"""
GESTIÓN DE CATÁLOGO ONLINE — panel operativo interno (Fase 2).

Administra el overlay de catálogo sobre `articulos` (ver src/db/catalogo.py):
productos (alta desde artículos + ficha web), categorías/subcategorías, marcas,
etiquetas, galerías de imágenes, atributos, variantes, destacados/recomendados,
visibilidad web y SEO. Multiempresa/multitienda (usa la `vista_operativa`).

Barra lateral al estilo del resto de la app (Centro Documental / Logística).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QObject, QRect, Qt, QTimer
from PyQt6.QtGui import QBitmap, QIntValidator, QPainter, QRegion
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                             QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from src.db import articulos as art_db
from src.db import catalogo as cat
from src.gui.components.completer_articulos import instalar_sugerencias_articulo
from src.utils.i18n import tr

try:
    from assets.estilo_global import (_blindar_tamano_fijo, aplicar_estilo_widget,
                                      instalar_corner_cover,
                                      mostrar_confirmacion, mostrar_mensaje)
except Exception:  # pragma: no cover
    mostrar_mensaje = mostrar_confirmacion = None
    instalar_corner_cover = None
    aplicar_estilo_widget = None
    _blindar_tamano_fijo = None

logger = logging.getLogger("gui.catalogo")

_BG = "#0E1117"
_BG2 = "#161B22"
_SIDEBAR = "#111418"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"
_VERDE = "#22C55E"
_FONT = "Segoe UI"


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, msg, nivel)


def _confirmar(parent, titulo, msg) -> bool:
    if mostrar_confirmacion:
        return mostrar_confirmacion(parent, titulo, msg)
    return True


def _inp(ph="", w=None) -> QLineEdit:
    e = QLineEdit(); e.setFixedHeight(34); e.setPlaceholderText(ph)
    if w:
        e.setFixedWidth(w)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
                    f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _btn(txt, slot=None, primary=False, danger=False, success=False) -> QPushButton:
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(34)
    # `success` (verde #22C55E, mismo tono que "GUARDAR HORARIOS" en horarios_gui.py) sigue el
    # mismo criterio que `primary`/`danger`: mismo diseño (relleno oscuro, contorno+texto del
    # color, hover invierte a relleno del color), solo cambia el color semántico (acciones de
    # aprobación explícitas, p. ej. "Aprobar" en GestionLaboralDialog).
    c, bg, bd = ((_ROJO, _BG2, _ROJO) if danger else
                 (_VERDE, _BG2, _VERDE) if success else
                 (_CIAN, _BG2, _CIAN) if primary else (_DIM, _BG2, _BORDE))
    # Botones "solo icono" (un único glifo sin texto, p. ej. "🗑"/"✕"/"＋" — usados en tarjetas Kanban y
    # cabeceras de diálogo): sin ancho fijo, el auto-cálculo de Qt para UN SOLO glifo puede dejarlo
    # apretado contra el padding horizontal y recortarlo — mismo bug ya visto y corregido en el botón
    # de escaneo remoto (`remote_scan.py`). Los botones CON texto (con espacio) no se tocan.
    solo_icono = bool(txt) and " " not in txt.strip() and len(txt.strip()) <= 2
    if solo_icono:
        # 34x34 -> 44x44: 34x34 recortaba visualmente el glifo emoji (p. ej. 🔍) contra el padding 0 +
        # borde 2px — mismo bug ya visto y corregido en `components/remote_scan.py` (ahí a 46x46).
        b.setFixedSize(44, 44)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:{c};border:2px solid {bd};border-radius:8px;"
        f"font-weight:900;font-size:{'16px' if solo_icono else '12px'};"
        f"padding:{'0' if solo_icono else '0 14px'};font-family:'{_FONT}';}}"
        f"QPushButton:hover{{background:{c};color:{_BG};border-color:{c};}}"
        # `setEnabled(False)` no tenía NINGÚN efecto visual antes de esto: el QSS explícito de arriba
        # sustituye por completo la paleta "disabled" nativa de Qt, así que un botón deshabilitado se
        # veía exactamente igual que uno activo (mismo color/contorno). Se apaga explícitamente aquí,
        # de forma uniforme para toda la app (p. ej. "Importar" en el modal de extracto bancario, que
        # debe verse apagado hasta que haya fichero elegido).
        f"QPushButton:disabled{{background:{_BG2};color:{_DIM};border-color:{_BORDE};}}")
    if slot:
        b.clicked.connect(slot)
    return b


def _btn_cargando(txt, slot=None, primary=True, danger=False, cargando="⏳  Actualizando…"):
    """Botón que al pulsarse muestra un estado de carga (`⏳  Actualizando…`), se deshabilita, ejecuta
    `slot` y restaura su aspecto. Pensado para los botones de 'Actualizar'."""
    b = _btn(txt, None, primary=primary, danger=danger)

    def _run():
        orig = b.text()
        b.setText(cargando); b.setEnabled(False)
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()   # fuerza el repintado del estado de carga
            if slot:
                slot()
        finally:
            b.setText(orig); b.setEnabled(True)
    b.clicked.connect(_run)
    return b


def _btn_x(slot=None) -> QPushButton:
    """Botón rojo 'X' para cerrar/volver: sin contorno ni fondo en reposo (solo el símbolo);
    al pasar el ratón, hover swap con fondo circular — mismo criterio en TODA la app."""
    b = QPushButton("✕"); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedSize(36, 36)
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;"
                    f"border-radius:18px;padding:0;font-weight:900;font-size:18px;}}"
                    f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
    b.setProperty("sin_glow", True)
    if _blindar_tamano_fijo is not None:
        _blindar_tamano_fijo(b, 36, 36)
    if slot:
        b.clicked.connect(slot)
    return b


def centrar_en_pantalla(widget):
    """Centra `widget` (típicamente un QDialog ya construido) sobre el área REAL disponible de la
    pantalla primaria (descontando la barra de tareas) — no sobre el centro de su padre, que en
    diálogos frameless+translúcidos puede dejarlo asomando fuera de la pantalla si es más alto de lo
    esperado o el padre no ocupa toda la pantalla (bug real confirmado, p. ej. en "Nuevo activo" de
    GMAO, con 8 campos). Se llama vía `QTimer.singleShot(0, ...)` para que el tamaño natural del
    widget (`adjustSize`) ya esté resuelto en el momento de calcular la posición."""
    try:
        from PyQt6.QtWidgets import QApplication
        pantalla = QApplication.primaryScreen().availableGeometry()
        widget.adjustSize()
        x = pantalla.x() + max(0, (pantalla.width() - widget.width()) // 2)
        y = pantalla.y() + max(0, (pantalla.height() - widget.height()) // 2)
        widget.move(x, y)
    except Exception:
        pass


def _dialogo_frameless(dialog, titulo="", ancho=None):
    """Convierte un QDialog en 'frameless' (sin la barra de título nativa de Windows) con esquinas
    redondeadas y fondo translúcido, de modo que el contenido no sobresalga por fuera del contorno.
    Devuelve el QVBoxLayout del CUERPO (dentro del marco redondeado) donde añadir el contenido; si se
    pasa `titulo`, incluye una cabecera con el título + botón rojo ✕ para cerrar. Se centra SIEMPRE
    sobre la pantalla real (ver `centrar_en_pantalla`), nunca sobre el centro de su padre."""
    dialog.setModal(True)
    dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    outer = QVBoxLayout(dialog); outer.setContentsMargins(0, 0, 0, 0)
    cuerpo = QFrame(); cuerpo.setObjectName("dlg")
    cuerpo.setStyleSheet(f"QFrame#dlg{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
    if ancho:
        cuerpo.setMinimumWidth(ancho)
    outer.addWidget(cuerpo)
    v = QVBoxLayout(cuerpo); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
    if titulo:
        hdr = QHBoxLayout()
        t = QLabel(titulo)
        t.setStyleSheet(
            f"color:{_CIAN};background:transparent;font-family:'{_FONT}';font-weight:900;font-size:15px;")
        hdr.addWidget(t); hdr.addStretch()
        hdr.addWidget(_btn_x(dialog.reject))
        v.addLayout(hdr)
    QTimer.singleShot(0, lambda: centrar_en_pantalla(dialog))
    return v


class _InfoDialog(QDialog):
    """Aviso frameless compartido (sustituye a QMessageBox.information/.warning/.critical): sobre una
    ventana anfitriona frameless (todas las ventanas completas de la app), un QMessageBox nativo puede
    quedar sin handle nativo correcto y no llegar a mostrarse — mismo criterio ya aplicado en
    `almacenes_gui.py`/`seguridad_gui.py`, ahora centralizado aquí para que cualquier pantalla lo
    reutilice en vez de duplicar la misma clase."""

    def __init__(self, titulo, mensaje, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{_DIM};font-size:13px;")
        v.addWidget(lbl)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)


def _info(parent, titulo, mensaje):
    _InfoDialog(titulo, mensaje, parent).exec()


def _btn_salir_sidebar(slot=None) -> QPushButton:
    """Botón 'SALIR' rojo para el FONDO de los sidebars (estilo unificado en toda la app).

    `.upper()` es OBLIGATORIO aquí: `i18n._frase()` sentence-casea automáticamente CUALQUIER
    texto que pase por `tr()` (p. ej. "SALIR" -> "Salir") salvo que sea una sigla conocida — bug
    real detectado en auditoría (el botón llevaba meses renderizando "Salir", no "SALIR", en
    todos los módulos que usan este helper)."""
    b = QPushButton(tr("cat.salir", default="SALIR").upper())
    b.setObjectName("btn_sidebar_exit"); b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedHeight(55)   # misma altura que el resto de botones de sidebar
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;"
                    f"border-left:4px solid transparent;border-radius:0px;font-size:12px;"
                    f"font-family:'{_FONT}';font-weight:900;text-align:left;padding-left:28px;}}"
                    f"QPushButton:hover{{background:{_ROJO};color:#0E1117;}}")
    if slot:
        b.clicked.connect(slot)
    return b


def _lbl(txt, dim=True, size=12, bold=True):
    l = QLabel(txt)
    l.setStyleSheet(f"color:{_DIM if dim else _TEXT};font-family:'{_FONT}';"
                    f"font-weight:{'900' if bold else '500'};font-size:{size}px;background:transparent;")
    return l


def _combo(opciones, actual=None, cls=QComboBox) -> QComboBox:
    cb = cls(); cb.setFixedHeight(34)
    # Solo el aspecto CERRADO del combo aquí. El popup nativo de Qt (QComboBoxPrivateContainer,
    # abierto con la flecha) recorta mal sus esquinas derechas y a veces esconde su propia scrollbar
    # en esta app incluso con el filtro global de estilos aplicado (bug reproducido y confirmado
    # pixel a pixel) — así que NO se intenta maquillar aquí con un `QComboBox QAbstractItemView{...}`
    # propio (solo duplicaba el contorno). Los desplegables que necesitan una lista larga y fiable
    # usan `_combo_buscable` en su lugar, que sustituye ese popup nativo por el de un QCompleter
    # (`estilizar_completer`, con máscara redondeada real — el mismo mecanismo ya usado en las
    # barras de búsqueda de artículos de toda la app).
    cb.setStyleSheet(
        f"QComboBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
        f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
        f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
        f"QComboBox::drop-down{{border:none;width:22px;}}")
    for etq, val in opciones:
        cb.addItem(etq, val)
    if actual is not None:
        i = cb.findData(actual)
        if i >= 0:
            cb.setCurrentIndex(i)
    if aplicar_estilo_widget is not None:
        try:
            aplicar_estilo_widget(cb)
        except Exception:
            pass
    # El ensanchado del popup para que no trunque/elida el texto de las opciones más largas
    # vive ahora en `estilo_global._apply_combo_extras` (llamada arriba vía `aplicar_estilo_widget`)
    # — reutiliza la MISMA `.view()` que ya obtiene esa función en vez de acceder a ella otra vez
    # aquí por separado (dos accesos independientes a `.view()` sobre el mismo combo, confirmado
    # como parte del disparador de un crash nativo intermitente).
    return cb


def _chk(txt, val=False) -> QCheckBox:
    c = QCheckBox(txt); c.setChecked(bool(val)); c.setCursor(Qt.CursorShape.PointingHandCursor)
    c.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-family:'{_FONT}';font-size:12px;font-weight:700;}}"
                    f"QCheckBox::indicator{{width:18px;height:18px;}}")
    return c


class _RoundTableCorners(QObject):
    """Redondea con máscara las esquinas exteriores de la tabla y las superiores de la
    cabecera (el QSS por sí solo no redondea la cabecera de forma fiable → se ve un
    pequeño corte en las esquinas superiores)."""

    def __init__(self, table, radius=12):
        super().__init__(table)
        self._r = radius
        self._table = table
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (API Qt)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            if obj is self._table:
                rect = QRect(0, 0, obj.width(), obj.height())
            else:  # cabecera: redondea solo arriba (extiende el rect por abajo)
                rect = QRect(0, 0, obj.width(), obj.height() + self._r)
            bmp = QBitmap(obj.size())
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, self._r, self._r)
            p.end()
            obj.setMask(QRegion(bmp))
        return False


def _tabla(cols) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(40)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    # Diseño estándar de la app: anchura equitativa (ocupa todo el ancho), contorno neón,
    # esquinas redondeadas y hover swap en las cabeceras.
    hh = t.horizontalHeader()
    for c in range(len(cols)):
        hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
    hh.setHighlightSections(False)
    t.setStyleSheet(f"""
        QTableWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};border-radius:12px;
                      gridline-color:{_BORDE};font-family:'{_FONT}';font-size:13px;outline:none;}}
        QHeaderView::section{{background:{_BG};color:{_CIAN};border:none;
                              border-bottom:2px solid {_BORDE};padding:8px;font-weight:900;font-size:11px;}}
        QHeaderView::section:hover{{background:{_CIAN};color:{_BG};}}
        QHeaderView::section:first{{border-top-left-radius:12px;}}
        QHeaderView::section:last{{border-top-right-radius:12px;}}
        QTableWidget::item{{padding:6px;}}
        QTableWidget::item:selected{{background:#00FFC622;color:white;}}
        QScrollBar:vertical{{background:transparent;width:16px;margin:0;}}
        QScrollBar::handle:vertical{{background:{_CIAN};min-height:36px;border-radius:5px;margin:3px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;width:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}""")
    # Esquinas limpias (como Documentos): overlay que repinta esquinas + contorno encima
    # del sangrado de la scrollbar. Fallback a la máscara si el helper no está.
    if instalar_corner_cover is not None:
        instalar_corner_cover(t, 12, bg=_BG)
    else:
        _RoundTableCorners(t, radius=12)
    return t


def _wrap_tabla(t):
    # La tabla (_tabla) ya tiene su propio contorno neón + esquinas redondeadas; no añadimos
    # otro marco (antes se veía doble contorno). Se devuelve la tabla tal cual.
    return t


_MOTIVO_IA_MSG = {
    "sin_api_key": "El asistente IA no está configurado todavía en este equipo.",
    "sin_contexto": "Escribe antes un título de producto para poder generar texto.",
    "limite_ia": "Se alcanzó el límite de uso de IA de hoy para tu empresa.",
    "respuesta_vacia": "El asistente no devolvió texto; prueba de nuevo.",
    "error_inesperado": "No se pudo conectar con el asistente IA ahora mismo.",
}


class _AsistenteIADialog(QDialog):
    """Popover ligero de generación de texto con IA para un campo de la ficha de producto
    (e-commerce Fase 1) — reutiliza `services.catalogo.ia_contenido.generar_texto` (que a su vez
    reutiliza el cliente/modelo de SOMA y el medidor de uso compartido, nunca un motor propio).
    NO bloquea el guardado de la ficha: es una ventana aparte, opcional, de un clic
    ("Aplicar sugerencia") — si la IA degrada, se explica el motivo, nunca se inventa texto."""

    def __init__(self, campo, nombre_producto, atributos=None, parent=None):
        super().__init__(parent)
        self._campo = campo
        self._nombre_producto = nombre_producto
        self._atributos = atributos or {}
        self.texto_generado = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 320)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame(); cuerpo.setObjectName("ia")
        cuerpo.setStyleSheet(f"QFrame#ia{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
        v.addWidget(_lbl("✨  " + tr("cat.ia_generar_t", default="Generar con IA"), dim=False, size=14))
        v.addWidget(_lbl(tr("cat.ia_tono", default="Tono"), size=11))
        self.cmb_tono = _combo([(tr("cat.ia_tono_comercial", default="Comercial"), "comercial"),
                                (tr("cat.ia_tono_elegante", default="Elegante"), "elegante"),
                                (tr("cat.ia_tono_tecnico", default="Técnico"), "tecnico")])
        v.addWidget(self.cmb_tono)
        self.txt_preview = QPlainTextEdit(); self.txt_preview.setReadOnly(True)
        self.txt_preview.setFixedHeight(120)
        self.txt_preview.setPlaceholderText(tr("cat.ia_placeholder", default="La sugerencia aparecerá aquí…"))
        self.txt_preview.setStyleSheet(
            f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px;font-size:12px;font-family:'{_FONT}';}}")
        v.addWidget(self.txt_preview, 1)
        self.lbl_estado = _lbl("", size=10); self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet(f"color:{_ROJO};font-size:10px;")
        v.addWidget(self.lbl_estado)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn(tr("cat.ia_generar", default="Generar"), self._generar, primary=True))
        self.btn_aplicar = _btn(tr("cat.ia_aplicar", default="Aplicar sugerencia"), self._aplicar,
                                success=True)
        self.btn_aplicar.setEnabled(False)
        fila.addWidget(self.btn_aplicar)
        fila.addWidget(_btn(tr("cat.cerrar", default="Cerrar"), self.reject))
        v.addLayout(fila)

    def _generar(self):
        from src.db.empresa import empresa_actual_id
        from src.db.usuario import sesion_global
        from src.services.catalogo import ia_contenido
        usuario = sesion_global.usuario_actual or {}
        r = ia_contenido.generar_texto(self._campo, self._nombre_producto, self._atributos,
                                       self.cmb_tono.currentData(), usuario=usuario,
                                       id_empresa=empresa_actual_id())
        if r.get("ok"):
            self.txt_preview.setPlainText(r["texto"])
            self.btn_aplicar.setEnabled(True)
            self.lbl_estado.setText("")
        else:
            self.txt_preview.setPlainText("")
            self.btn_aplicar.setEnabled(False)
            self.lbl_estado.setText(_MOTIVO_IA_MSG.get(
                r.get("motivo"), tr("cat.ia_error_generico", default="No se pudo generar el texto ahora mismo.")))

    def _aplicar(self):
        self.texto_generado = self.txt_preview.toPlainText()
        self.accept()


def _abrir_asistente_ia(parent, campo, nombre_producto, atributos=None):
    """Abre `_AsistenteIADialog` y devuelve el texto aplicado, o None si se canceló."""
    dlg = _AsistenteIADialog(campo, nombre_producto, atributos, parent)
    return dlg.texto_generado if dlg.exec() == QDialog.DialogCode.Accepted else None


class _MatrizVariantesDialog(QDialog):
    """Generador de combinaciones de variantes (p. ej. 3 Tallas × 2 Colores = 6 filas) — "sin
    abrir modales pesados" (encargo e-commerce Fase 1): UNA tabla editable con el resultado, un
    único botón final que llama a `cat.crear_variantes_bulk` (atómico, reutilizado, no
    reimplementado aquí)."""

    def __init__(self, id_producto, codigo_base, parent=None):
        super().__init__(parent)
        self._pid = id_producto
        self._cod_base = codigo_base
        self._filas_ejes = []
        self._combinaciones_actuales = []
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(640, 560)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame(); cuerpo.setObjectName("mv")
        cuerpo.setStyleSheet(f"QFrame#mv{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
        v.addWidget(_lbl(tr("cat.var_matriz_t", default="Generar combinaciones de variantes"),
                        dim=False, size=14))
        v.addWidget(_lbl(tr("cat.var_matriz_ayuda",
                            default="Define cada eje (p. ej. Talla) y sus valores separados por comas."),
                        size=10))

        self.lay_ejes = QVBoxLayout(); self.lay_ejes.setSpacing(4)
        v.addLayout(self.lay_ejes)
        self._add_eje(tr("cat.var_matriz_eje_ej1", default="Talla"),
                     tr("cat.var_matriz_val_ej1", default="S, M, L"))
        self._add_eje(tr("cat.var_matriz_eje_ej2", default="Color"),
                     tr("cat.var_matriz_val_ej2", default="Rojo, Azul"))

        fila_btns = QHBoxLayout()
        fila_btns.addWidget(_btn(tr("cat.var_matriz_add_eje", default="+ Añadir eje"), self._add_eje_vacio))
        fila_btns.addWidget(_btn(tr("cat.var_matriz_generar", default="Generar matriz"),
                                 self._generar, primary=True))
        fila_btns.addStretch()
        v.addLayout(fila_btns)

        self.tbl_preview = _tabla(["Atributos", "SKU", tr("cat.precio_dif", default="Precio dif.")])
        self.tbl_preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_preview.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                         | QAbstractItemView.EditTrigger.EditKeyPressed)
        v.addWidget(_wrap_tabla(self.tbl_preview), 1)

        self.lbl_estado = _lbl("", size=10); self.lbl_estado.setWordWrap(True)
        v.addWidget(self.lbl_estado)
        filaf = QHBoxLayout(); filaf.addStretch()
        self.btn_crear = _btn(tr("cat.var_matriz_crear", default="Crear variantes"),
                              self._crear, primary=True)
        self.btn_crear.setEnabled(False)
        filaf.addWidget(self.btn_crear)
        filaf.addWidget(_btn(tr("cat.cerrar", default="Cerrar"), self.reject))
        v.addLayout(filaf)

    def _add_eje(self, nombre="", valores=""):
        fila = QHBoxLayout()
        inp_n = _inp(tr("cat.var_matriz_eje", default="Eje (ej. Talla)"), 140); inp_n.setText(nombre)
        inp_v = _inp(tr("cat.var_matriz_valores", default="Valores separados por comas"))
        inp_v.setText(valores)
        fila.addWidget(inp_n); fila.addWidget(inp_v, 1)
        self.lay_ejes.addLayout(fila)
        self._filas_ejes.append((inp_n, inp_v))

    def _add_eje_vacio(self):
        self._add_eje("", "")

    def _generar(self):
        import itertools
        ejes = []
        for inp_n, inp_v in self._filas_ejes:
            nombre = inp_n.text().strip()
            valores = [v.strip() for v in inp_v.text().split(",") if v.strip()]
            if nombre and valores:
                ejes.append((nombre, valores))
        if not ejes:
            self.lbl_estado.setText(tr("cat.var_matriz_sin_ejes",
                                       default="Define al menos un eje con valores."))
            self.btn_crear.setEnabled(False)
            return
        nombres_ejes = [n for n, _ in ejes]
        combinaciones = list(itertools.product(*[vals for _, vals in ejes]))
        self.tbl_preview.setRowCount(0)
        self._combinaciones_actuales = []
        for idx, combo in enumerate(combinaciones):
            atributos = dict(zip(nombres_ejes, combo))
            sku = f"{self._cod_base}-" + "-".join(combo).upper().replace(" ", "")
            self._combinaciones_actuales.append({
                "atributos": atributos, "sku": sku, "nombre": " / ".join(combo),
                "precio_dif": 0.0, "orden": idx})
            r = self.tbl_preview.rowCount(); self.tbl_preview.insertRow(r)
            it_attr = QTableWidgetItem(", ".join(f"{k}: {v}" for k, v in atributos.items()))
            it_attr.setFlags(it_attr.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_preview.setItem(r, 0, it_attr)
            self.tbl_preview.setItem(r, 1, QTableWidgetItem(sku))
            self.tbl_preview.setItem(r, 2, QTableWidgetItem("0.00"))
        self.lbl_estado.setText(tr(
            "cat.var_matriz_generadas",
            default="{n} combinaciones generadas — revisa SKU y precio antes de crear.",
            n=len(combinaciones)))
        self.btn_crear.setEnabled(bool(combinaciones))

    def _crear(self):
        # Vuelca a `_combinaciones_actuales` los valores de la tabla (posiblemente editados a
        # mano: SKU/precio) justo antes de confirmar.
        for r, combo in enumerate(self._combinaciones_actuales):
            it_sku = self.tbl_preview.item(r, 1)
            combo["sku"] = (it_sku.text().strip() if it_sku else "") or combo["sku"]
            it_pd = self.tbl_preview.item(r, 2)
            try:
                combo["precio_dif"] = float((it_pd.text() if it_pd else "0").replace(",", ".") or 0)
            except ValueError:
                combo["precio_dif"] = 0.0
        res = cat.crear_variantes_bulk(self._pid, self._combinaciones_actuales)
        if res.get("ok"):
            self.accept()
        else:
            self.lbl_estado.setText(tr("cat.var_matriz_error",
                                       default="No se pudieron crear las variantes."))


# ════════════════════════════════════════════════════════════════════════════
# Editor de ficha de producto (overlay + galería/atributos/variantes/etiquetas)
# ════════════════════════════════════════════════════════════════════════════
class _ProductoEditor(QDialog):
    def __init__(self, codigo_articulo, nombre_articulo="", parent=None):
        super().__init__(parent)
        self._cod = codigo_articulo
        self._nombre = nombre_articulo
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(760, 720)
        # Garantiza overlay (crea si no existe) y carga la ficha.
        cat.upsert_producto(codigo_articulo)
        self._prod = cat.obtener_producto(codigo_articulo=codigo_articulo)
        self._pid = self._prod["id"]
        self._build()

    def _txtarea(self, val=""):
        t = QPlainTextEdit(); t.setPlainText(val or ""); t.setFixedHeight(70)
        t.setStyleSheet(f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                        f"border-radius:8px;padding:6px;font-size:12px;font-family:'{_FONT}';}}"
                        f"QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        return t

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame(); cuerpo.setObjectName("pe")
        cuerpo.setStyleSheet(f"QFrame#pe{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        hdr = QHBoxLayout()
        hdr.addWidget(_lbl(f"📦  {self._nombre or self._cod}  ·  {self._cod}", dim=False, size=15))
        hdr.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(34, 34); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;"
                         f"border-radius:17px;padding:0;font-weight:900;}}QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx.setProperty("sin_glow", True)
        if _blindar_tamano_fijo is not None:
            _blindar_tamano_fijo(bx, 34, 34)
        bx.clicked.connect(self.reject); hdr.addWidget(bx)
        v.addLayout(hdr)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {_BORDE};border-radius:8px;}}"
            f"QTabBar::tab{{background:{_BG2};color:{_DIM};padding:8px 14px;font-family:'{_FONT}';"
            f"font-weight:900;font-size:11px;border:1px solid {_BORDE};border-bottom:none;}}"
            f"QTabBar::tab:selected{{background:{_CIAN};color:{_BG};}}")
        tabs.addTab(self._tab_ficha(), tr("cat.tab_ficha", default="Ficha"))
        tabs.addTab(self._tab_galeria(), tr("cat.tab_galeria", default="Galería"))
        tabs.addTab(self._tab_atributos(), tr("cat.tab_atributos", default="Atributos"))
        tabs.addTab(self._tab_variantes(), tr("cat.tab_variantes", default="Variantes"))
        v.addWidget(tabs, 1)

        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("cat.eliminar_ficha", default="Quitar del catálogo"), self._eliminar, danger=True))
        fila.addStretch()
        fila.addWidget(_btn(tr("cat.cerrar", default="CERRAR"), self.reject))
        fila.addWidget(_btn(tr("cat.guardar", default="GUARDAR FICHA"), self._guardar, primary=True))
        v.addLayout(fila)

    def _fila_con_ia(self, ly, widget, campo, *, texto_simple=False):
        """Añade `widget` a `ly` con un botón "✨" a la derecha que abre `_AsistenteIADialog` para
        `campo` y, al aplicar, rellena `widget` (QLineEdit si `texto_simple`, QPlainTextEdit si
        no) con el texto generado — reutilizado por título/descripción/SEO, un solo camino."""
        fila = QHBoxLayout(); fila.setSpacing(6)
        fila.addWidget(widget, 1)
        btn_ia = _btn("✨", None)
        btn_ia.setToolTip(tr("cat.ia_tooltip", default="Generar con IA"))

        def _abrir():
            nombre = self.inp_titulo.text().strip() or self._nombre or self._cod
            atributos = {a["nombre"]: a["valor"] for a in cat.listar_atributos_producto(self._pid)}
            texto = _abrir_asistente_ia(self, campo, nombre, atributos)
            if texto is not None:
                widget.setText(texto) if texto_simple else widget.setPlainText(texto)

        btn_ia.clicked.connect(_abrir)
        fila.addWidget(btn_ia)
        ly.addLayout(fila)

    def _actualizar_preview_oferta(self):
        if not self.ck_oferta.isChecked():
            self.lbl_preview_precio.setText("")
            return
        try:
            base = float(self._prod.get("precio") or 0)
            oferta = float(self.inp_precio_oferta.text().replace(",", ".") or 0)
        except ValueError:
            self.lbl_preview_precio.setText("")
            return
        self.lbl_preview_precio.setText(
            f"<span style='color:{_DIM};text-decoration:line-through;'>{base:.2f} €</span>"
            f"&nbsp;&nbsp;<span style='color:{_ROJO};font-weight:900;'>{oferta:.2f} €</span>")

    def _tab_ficha(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(7); ly.setContentsMargins(12, 12, 12, 12)
        p = self._prod
        filat = QHBoxLayout(); filat.setSpacing(10)
        colt = QVBoxLayout(); colt.addWidget(_lbl(tr("cat.titulo_web", default="Título web")))
        self.inp_titulo = _inp(); self.inp_titulo.setText(p.get("titulo_web") or ""); colt.addWidget(self.inp_titulo)
        filat.addLayout(colt, 1)
        cols = QVBoxLayout(); cols.addWidget(_lbl(tr("cat.slug", default="URL amigable (slug)")))
        self.inp_slug = _inp(); self.inp_slug.setText(p.get("slug") or ""); cols.addWidget(self.inp_slug)
        filat.addLayout(cols, 1)
        ly.addLayout(filat)
        ly.addWidget(_lbl(tr("cat.desc_web", default="Descripción web")))
        self.inp_desc = self._txtarea(p.get("descripcion_web") or "")
        self._fila_con_ia(ly, self.inp_desc, "descripcion")

        # "Precio de comparación" del encargo e-commerce: reutiliza `articulos.promo_activa`/
        # `precio_promo` (YA existían, ya los leía `services.catalogo.service._precio_efectivo` —
        # aquí se exponen para poder ESCRIBIRLOS, sin añadir ninguna columna nueva).
        ly.addWidget(_lbl(tr("cat.oferta_t", default="Precio de oferta (comparación)")))
        filo = QHBoxLayout(); filo.setSpacing(8)
        self.ck_oferta = _chk(tr("cat.oferta_activa", default="En oferta"), p.get("promo_activa"))
        self.inp_precio_oferta = _inp(tr("cat.oferta_ph", default="Precio de oferta"), 140)
        if p.get("precio_promo"):
            self.inp_precio_oferta.setText(f"{float(p['precio_promo']):.2f}")
        self.lbl_preview_precio = QLabel(""); self.lbl_preview_precio.setStyleSheet("font-size:13px;")
        self.ck_oferta.toggled.connect(self._actualizar_preview_oferta)
        self.inp_precio_oferta.textChanged.connect(self._actualizar_preview_oferta)
        filo.addWidget(self.ck_oferta); filo.addWidget(self.inp_precio_oferta); filo.addWidget(self.lbl_preview_precio, 1)
        ly.addLayout(filo)
        self._actualizar_preview_oferta()

        fila = QHBoxLayout()
        colc = QVBoxLayout(); colc.addWidget(_lbl(tr("cat.categoria", default="Categoría")))
        cats = [("—", None)] + _cats_planas()
        self.cmb_cat = _combo(cats, p.get("id_categoria")); colc.addWidget(self.cmb_cat); fila.addLayout(colc)
        colm = QVBoxLayout(); colm.addWidget(_lbl(tr("cat.marca", default="Marca")))
        marcas = [("—", None)] + [(m["nombre"], m["id"]) for m in cat.listar_marcas()]
        self.cmb_marca = _combo(marcas, p.get("id_marca")); colm.addWidget(self.cmb_marca); fila.addLayout(colm)
        colo = QVBoxLayout(); colo.addWidget(_lbl(tr("cat.orden", default="Orden")))
        # QLineEdit + validador en vez de QSpinBox: la app oculta sus flechas arriba/abajo vía QSS y
        # eso rompía su foco/clic en varios diálogos (confirmado por el usuario) — mismo criterio ya
        # aplicado en `sat_dashboard._FormDialog`.
        self.sp_orden = QLineEdit(str(int(p.get("orden") or 0)))
        self.sp_orden.setValidator(QIntValidator(0, 99999, self.sp_orden))
        self.sp_orden.setFixedHeight(34)
        self.sp_orden.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                                    f"border-radius:8px;padding:0 8px;font-size:12px;}}")
        colo.addWidget(self.sp_orden); fila.addLayout(colo)
        ly.addLayout(fila)
        filc = QHBoxLayout()
        self.ck_dest = _chk(tr("cat.destacado", default="Destacado"), p.get("destacado"))
        self.ck_reco = _chk(tr("cat.recomendado", default="Recomendado"), p.get("recomendado"))
        self.ck_vis = _chk(tr("cat.visible", default="Visible en la web"), p.get("visible_web"))
        for c in (self.ck_dest, self.ck_reco, self.ck_vis):
            filc.addWidget(c)
        filc.addStretch(); ly.addLayout(filc)
        ly.addWidget(_lbl(tr("cat.seo_title", default="SEO · título")))
        self.inp_seo_t = _inp(); self.inp_seo_t.setText(p.get("seo_title") or "")
        self._fila_con_ia(ly, self.inp_seo_t, "seo_title", texto_simple=True)
        ly.addWidget(_lbl(tr("cat.seo_desc", default="SEO · descripción")))
        self.inp_seo_d = _inp(); self.inp_seo_d.setText(p.get("seo_descripcion") or "")
        self._fila_con_ia(ly, self.inp_seo_d, "seo_descripcion", texto_simple=True)
        ly.addStretch()
        return w

    def _tab_galeria(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_img = _inp(tr("cat.img_url_ph", default="URL de la imagen (https://… o ruta local)"))
        fila.addWidget(self.inp_img, 1)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_imagen, primary=True))
        ly.addLayout(fila)
        self.tbl_img = _tabla([tr("cat.img", default="Imagen"), tr("cat.portada", default="Portada"), ""])
        self.tbl_img.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_img.setColumnWidth(1, 90); self.tbl_img.setColumnWidth(2, 90)
        ly.addWidget(_wrap_tabla(self.tbl_img), 1)
        self._recargar_imagenes()
        return w

    def _recargar_imagenes(self):
        imgs = cat.listar_imagenes(self._pid)
        self.tbl_img.setRowCount(0)
        for im in imgs:
            r = self.tbl_img.rowCount(); self.tbl_img.insertRow(r)
            self.tbl_img.setItem(r, 0, QTableWidgetItem(im.get("url") or ""))
            self.tbl_img.setItem(r, 1, QTableWidgetItem("★" if im.get("es_portada") else ""))
            cont = QWidget(); h = QHBoxLayout(cont); h.setContentsMargins(2, 2, 2, 2); h.setSpacing(4)
            bp = _btn("★", lambda _c, i=im["id"]: self._portada(i)); bp.setFixedWidth(34)
            bd = _btn("🗑", lambda _c, i=im["id"]: self._del_imagen(i), danger=True); bd.setFixedWidth(34)
            h.addWidget(bp); h.addWidget(bd)
            self.tbl_img.setCellWidget(r, 2, cont)

    def _add_imagen(self):
        url = self.inp_img.text().strip()
        if not url:
            return
        cat.anadir_imagen(self._pid, url, es_portada=not cat.listar_imagenes(self._pid))
        self.inp_img.clear(); self._recargar_imagenes()

    def _del_imagen(self, id_img):
        cat.eliminar_imagen(id_img); self._recargar_imagenes()

    def _portada(self, id_img):
        cat.marcar_portada(self._pid, id_img); self._recargar_imagenes()

    def _tab_atributos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_attr_n = _inp(tr("cat.attr_nombre", default="Atributo (ej. Color)"))
        self.inp_attr_v = _inp(tr("cat.attr_valor", default="Valor (ej. Azul)"))
        fila.addWidget(self.inp_attr_n); fila.addWidget(self.inp_attr_v)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_attr, primary=True))
        ly.addLayout(fila)
        self.tbl_attr = _tabla([tr("cat.attr", default="Atributo"), tr("cat.valor", default="Valor"), ""])
        self.tbl_attr.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_attr.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_attr.setColumnWidth(2, 60)
        ly.addWidget(_wrap_tabla(self.tbl_attr), 1)
        self._recargar_attr()
        return w

    def _recargar_attr(self):
        self.tbl_attr.setRowCount(0)
        for a in cat.listar_atributos_producto(self._pid):
            r = self.tbl_attr.rowCount(); self.tbl_attr.insertRow(r)
            self.tbl_attr.setItem(r, 0, QTableWidgetItem(a.get("nombre") or ""))
            self.tbl_attr.setItem(r, 1, QTableWidgetItem(a.get("valor") or ""))
            bd = _btn("🗑", lambda _c, i=a["id"]: (cat.eliminar_atributo_producto(i), self._recargar_attr()), danger=True)
            self.tbl_attr.setCellWidget(r, 2, bd)

    def _add_attr(self):
        n = self.inp_attr_n.text().strip(); val = self.inp_attr_v.text().strip()
        if not n:
            return
        cat.set_atributo_producto(self._pid, n, val)
        self.inp_attr_n.clear(); self.inp_attr_v.clear(); self._recargar_attr()

    def _tab_variantes(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_var_n = _inp(tr("cat.var_nombre", default="Variante (ej. Talla M)"))
        self.inp_var_sku = _inp(tr("cat.var_sku", default="SKU"), 140)
        fila.addWidget(self.inp_var_n); fila.addWidget(self.inp_var_sku)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_var, primary=True))
        fila.addWidget(_btn(tr("cat.var_matriz", default="Generar combinaciones"),
                            self._abrir_matriz_variantes))
        ly.addLayout(fila)
        cols = [tr("cat.variante", default="Variante"), tr("cat.atributos", default="Atributos"),
                "SKU", tr("cat.precio_dif", default="Precio dif."), tr("cat.stock", default="Stock"),
                tr("cat.visible", default="Visible"), ""]
        self.tbl_var = _tabla(cols)
        self.tbl_var.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_var.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c, wdt in ((2, 120), (3, 90), (4, 70), (5, 60), (6, 50)):
            self.tbl_var.setColumnWidth(c, wdt)
        ly.addWidget(_wrap_tabla(self.tbl_var), 1)
        self._recargar_var()
        return w

    def _recargar_var(self):
        self.tbl_var.setRowCount(0)
        for vr in cat.listar_variantes(self._pid):
            r = self.tbl_var.rowCount(); self.tbl_var.insertRow(r)
            vid = vr["id"]
            self.tbl_var.setItem(r, 0, QTableWidgetItem(vr.get("nombre") or ""))
            attrs_txt = ", ".join(f"{k}: {v}" for k, v in (vr.get("atributos") or {}).items())
            self.tbl_var.setItem(r, 1, QTableWidgetItem(attrs_txt))
            self.tbl_var.setItem(r, 2, QTableWidgetItem(vr.get("sku") or ""))

            inp_pd = QLineEdit(f"{float(vr.get('precio_dif') or 0):.2f}")
            inp_pd.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
                                 "border-radius:6px;padding:2px 4px;font-size:11px;}")
            inp_pd.editingFinished.connect(
                lambda i=vid, w_=inp_pd: self._guardar_precio_dif_variante(i, w_))
            self.tbl_var.setCellWidget(r, 3, inp_pd)

            stock = vr.get("stock")
            txt_stock = f"{stock:g}" if stock is not None else "—"
            it_stock = QTableWidgetItem(txt_stock)
            it_stock.setFlags(it_stock.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_var.setItem(r, 4, it_stock)

            ck_vis = QCheckBox(); ck_vis.setChecked(bool(vr.get("visible", 1)))
            ck_vis.toggled.connect(lambda chk, i=vid: cat.actualizar_variante(i, visible=1 if chk else 0))
            cont = QWidget(); hl = QHBoxLayout(cont); hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(ck_vis); hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_var.setCellWidget(r, 5, cont)

            bd = _btn("🗑", lambda _c, i=vid: (cat.eliminar_variante(i), self._recargar_var()), danger=True)
            self.tbl_var.setCellWidget(r, 6, bd)

    def _guardar_precio_dif_variante(self, id_variante, widget):
        try:
            valor = float(widget.text().replace(",", ".") or 0)
        except ValueError:
            valor = 0.0
        cat.actualizar_variante(id_variante, precio_dif=valor)

    def _add_var(self):
        n = self.inp_var_n.text().strip()
        if not n:
            return
        cat.crear_variante(self._pid, sku=self.inp_var_sku.text().strip() or None, nombre=n)
        self.inp_var_n.clear(); self.inp_var_sku.clear(); self._recargar_var()

    def _abrir_matriz_variantes(self):
        dlg = _MatrizVariantesDialog(self._pid, self._cod, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._recargar_var()

    def _guardar(self):
        try:
            orden = int(self.sp_orden.text() or 0)
        except ValueError:
            orden = 0
        cat.upsert_producto(
            self._cod, titulo_web=self.inp_titulo.text().strip(),
            descripcion_web=self.inp_desc.toPlainText().strip(),
            id_categoria=self.cmb_cat.currentData(), id_marca=self.cmb_marca.currentData(),
            destacado=1 if self.ck_dest.isChecked() else 0,
            recomendado=1 if self.ck_reco.isChecked() else 0,
            visible_web=1 if self.ck_vis.isChecked() else 0,
            orden=orden, seo_title=self.inp_seo_t.text().strip(),
            seo_descripcion=self.inp_seo_d.text().strip(),
            slug=self.inp_slug.text().strip())
        # "Precio de comparación": escribe sobre `articulos.promo_activa`/`precio_promo` (overlay
        # de catálogo YA leía estas columnas, ahora también las escribe — ver `_tab_ficha`).
        try:
            precio_oferta = float(self.inp_precio_oferta.text().replace(",", ".") or 0)
        except ValueError:
            precio_oferta = 0.0
        art_db.actualizar_articulo(
            self._cod, promo_activa=1 if self.ck_oferta.isChecked() else 0,
            precio_promo=precio_oferta)
        self.accept()

    def _eliminar(self):
        if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                      tr("cat.conf_quitar", default="¿Quitar este producto del catálogo online?")):
            cat.eliminar_producto(self._pid)
            self.accept()


def _cats_planas():
    """Categorías aplanadas como [(nombre_indentado, id)] para combos jerárquicos."""
    salida = []

    def rec(nodos, nivel):
        for n in nodos:
            salida.append(("   " * nivel + n["nombre"], n["id"]))
            rec(n.get("hijos", []), nivel + 1)
    rec(cat.arbol_categorias(), 0)
    return salida


# ════════════════════════════════════════════════════════════════════════════
# Ventana principal de gestión del catálogo
# ════════════════════════════════════════════════════════════════════════════
class CatalogoWindow(QWidget):
    """Gestión del catálogo online de la empresa activa (panel operativo interno)."""

    _SECCIONES = [("productos", "📦", "Productos"), ("categorias", "🗂", "Categorías"),
                  ("marcas", "🏷", "Marcas"), ("etiquetas", "🔖", "Tags Artículos"),
                  ("descuentos", "🎟", "Descuentos"), ("envios", "🚚", "Envíos"),
                  ("web", "🌐", "Web propia")]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self.usuario = usuario
        self._sec_btns = {}
        self.setWindowTitle("Smart Manager — " + tr("cat.titulo", default="CATÁLOGO"))
        # OJO: no fijar un stylesheet de fondo en la VENTANA — se propaga a los botones
        # del sidebar (fondo ≠ color del sidebar) y rompe el estilo. El fondo lo da el
        # QSS global + el panel derecho/wrap (igual que Contabilidad).
        self._build()
        QTimer.singleShot(0, self._recargar_todo)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="catalogo")
        except Exception:
            pass

    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar(), 0)
        right = QWidget(); right.setStyleSheet(f"background:{_BG};")
        rcol = QVBoxLayout(right); rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._build_header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._panel_productos())
        self.stack.addWidget(self._panel_categorias())
        self.stack.addWidget(self._panel_marcas())
        self.stack.addWidget(self._panel_etiquetas())
        self.stack.addWidget(self._panel_descuentos())
        self.stack.addWidget(self._panel_envios())
        self.stack.addWidget(self._panel_web())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self._seleccionar(0)

    def _build_header(self):
        cab = QHBoxLayout()
        t = QLabel("🛍  " + tr("cat.titulo", default="CATÁLOGO ONLINE"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:22px;background:transparent;")
        cab.addWidget(t); cab.addSpacing(16)
        self.lbl_ctx = _lbl("", size=14); cab.addWidget(self.lbl_ctx)
        cab.addStretch()
        return cab

    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230); self.sidebar = wrap  # P3
        wrap.setStyleSheet(f"QFrame#sw{{background:{_SIDEBAR};border:none;border-right:1px solid {_BORDE};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel("SMART CATALOG")   # título de marca de la sidebar (igual en todos los idiomas)
        cab.setStyleSheet(f"color:#FFFFFF;font-family:'{_FONT}';font-weight:900;font-size:16px;"
                          f"letter-spacing:2px;background:transparent;border:none;padding:0 0 24px 28px;")
        lay.addWidget(cab)
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"   {tr('cat.sec_' + sid, default=defecto).upper()}")   # sin icono — sidebar: mayúsculas
            # Mismo tamaño de texto (12px, base) que el resto de sidebars de la app — consistencia
            # exigida explícitamente; la variante +2pt (`lg="true"`) se retira aquí.
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _c, idx=i: self._seleccionar(idx))
            self._sec_btns[i] = b; lay.addWidget(b)
        lay.addStretch()
        if self._volver:   # SALIR AL MENÚ (rojo) al fondo del sidebar
            lay.addWidget(_btn_salir_sidebar(self._volver_menu))
        return wrap

    # Fondo SIEMPRE transparente (= color del sidebar), incluido el seleccionado.
    # La pestaña activa se marca solo con el acento izquierdo turquesa + texto turquesa.
    _SS_OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;padding:6px 8px 6px 24px;"
               f"border:none;border-left:4px solid transparent;border-radius:0px;font-family:'{_FONT}';"
               f"font-weight:900;font-size:14px;outline:none;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};border-radius:0px;}}")
    _SS_ON = (f"QPushButton{{background:transparent;color:{_CIAN};text-align:left;padding:6px 8px 6px 24px;"
              f"border:none;border-left:4px solid {_CIAN};border-radius:0px;font-family:'{_FONT}';"
              f"font-weight:900;font-size:14px;outline:none;}}")

    def _seleccionar(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in self._sec_btns.items():
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar

    # ── Panel Productos ──────────────────────────────────────────────────────
    def _panel_productos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_busca_prod = _inp(tr("cat.buscar_prod", default="🔍 Buscar artículo por nombre o código…"))
        self.inp_busca_prod.returnPressed.connect(self._recargar_productos)
        # Sugerencias de artículos: helper compartido, ver gui/components/completer_articulos.py
        instalar_sugerencias_articulo(self.inp_busca_prod)
        fila.addWidget(self.inp_busca_prod, 1)
        fila.addWidget(_btn(tr("cat.buscar", default="🔍"), self._recargar_productos, primary=True))
        fila.addWidget(_btn(tr("cat.editar_ficha", default="EDITAR FICHA"), self._editar_producto, primary=True))

        # Escaneo remoto: delega el escaneo al móvil en vez de la webcam del PC.
        from src.gui.components.remote_scan import agregar_boton_escaneo_movil
        btn_escaneo_movil = agregar_boton_escaneo_movil(
            self, on_result=lambda v: (self.inp_busca_prod.setText(v), self._recargar_productos()),
            contexto="catalogo.buscar_producto")
        fila.addWidget(btn_escaneo_movil)

        ly.addLayout(fila)
        self.tbl_prod = _tabla([tr("cat.col_codigo", default="Código"), tr("cat.col_articulo", default="Artículo"),
                                tr("cat.col_encat", default="En catálogo"), tr("cat.col_dest", default="Dest."),
                                tr("cat.col_reco", default="Reco."), tr("cat.col_vis", default="Visible")])
        self.tbl_prod.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4, 5):
            self.tbl_prod.setColumnWidth(c, 110)
        self.tbl_prod.doubleClicked.connect(lambda *_: self._editar_producto())
        ly.addWidget(_wrap_tabla(self.tbl_prod), 1)
        self.lbl_prod = _lbl("", size=11); ly.addWidget(self.lbl_prod)
        return w

    def _recargar_productos(self):
        _txt = self.inp_busca_prod.text().strip()
        if "–" in _txt:   # viene del autocompletado "CÓDIGO – NOMBRE"
            _txt = _txt.split("–")[0].strip()
        arts = cat.articulos_para_catalogo(texto=_txt or None)
        self._arts = arts
        self.tbl_prod.setRowCount(0)
        for a in arts:
            r = self.tbl_prod.rowCount(); self.tbl_prod.insertRow(r)
            vals = [a.get("codigo"), a.get("nombre") or "",
                    "✓" if a.get("id_producto") else "—",
                    "★" if a.get("destacado") else "", "✓" if a.get("recomendado") else "",
                    "✓" if (a.get("visible_web") if a.get("id_producto") else 0) else ""]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c != 1:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_prod.setItem(r, c, it)
        self.lbl_prod.setText(tr("cat.n_articulos", default="{n} artículo(s)", n=len(arts)))

    def _editar_producto(self):
        r = self.tbl_prod.currentRow()
        if r < 0 or not getattr(self, "_arts", None) or r >= len(self._arts):
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_articulo", default="Selecciona un artículo de la tabla."), "warning")
            return
        a = self._arts[r]
        _ProductoEditor(a["codigo"], a.get("nombre") or "", parent=self).exec()
        self._recargar_productos()

    # ── Panel Categorías ─────────────────────────────────────────────────────
    def _panel_categorias(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_cat = _inp(tr("cat.cat_nombre", default="Nombre de categoría"))
        fila.addWidget(self.inp_cat, 1)
        fila.addWidget(_btn(tr("cat.crear_raiz", default="CREAR RAÍZ"), lambda: self._crear_categoria(False), primary=True))
        fila.addWidget(_btn(tr("cat.crear_sub", default="CREAR SUBCATEGORÍA"), lambda: self._crear_categoria(True), primary=True))
        fila.addWidget(_btn(tr("cat.renombrar", default="RENOMBRAR"), self._renombrar_categoria, primary=True))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_categoria, danger=True))
        ly.addLayout(fila)
        self.tree_cat = QTreeWidget(); self.tree_cat.setHeaderHidden(True)
        self.tree_cat.setStyleSheet(
            f"QTreeWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};border-radius:14px;"
            f"font-family:'{_FONT}';font-size:13px;padding:6px;}}"
            f"QTreeWidget::item{{height:30px;}}"
            f"QTreeWidget::item:selected{{background:#00FFC622;color:white;}}")
        # `::item:selected` es un rectángulo recto sin margen/radio propio: en el primer/último nodo
        # sobresale por encima del borde redondeado (14px) del propio árbol — mismo mecanismo que la
        # lista de empleados de "Acceso al TPV" (`tpv.py::_LoginTPVDialog`). `_RoundTableCorners` (más
        # arriba en este mismo módulo) no sirve aquí: usa `.horizontalHeader()`, que QTreeWidget no
        # tiene (solo `.header()`), así que reutilizamos el helper genérico compartido.
        if instalar_corner_cover is not None:
            instalar_corner_cover(self.tree_cat, radius=14, bg=_BG2, border=_CIAN)
        ly.addWidget(self.tree_cat, 1)
        return w

    def _recargar_categorias(self):
        self.tree_cat.clear()

        def add(nodos, parent):
            for n in nodos:
                it = QTreeWidgetItem([n["nombre"]]); it.setData(0, Qt.ItemDataRole.UserRole, n["id"])
                (parent.addChild(it) if parent else self.tree_cat.addTopLevelItem(it))
                add(n.get("hijos", []), it)
        add(cat.arbol_categorias(), None)
        self.tree_cat.expandAll()

    def _cat_sel(self):
        it = self.tree_cat.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _crear_categoria(self, como_sub):
        nombre = self.inp_cat.text().strip()
        if not nombre:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"), tr("cat.falta_nombre", default="Escribe un nombre."), "warning")
            return
        parent = self._cat_sel() if como_sub else None
        if como_sub and not parent:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_padre", default="Selecciona la categoría padre."), "warning")
            return
        cat.crear_categoria(nombre, parent_id=parent)
        self.inp_cat.clear(); self._recargar_categorias()

    def _renombrar_categoria(self):
        cid = self._cat_sel(); nombre = self.inp_cat.text().strip()
        if not cid or not nombre:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_y_nombre", default="Selecciona una categoría y escribe el nuevo nombre."), "warning")
            return
        cat.actualizar_categoria(cid, nombre=nombre); self.inp_cat.clear(); self._recargar_categorias()

    def _eliminar_categoria(self):
        cid = self._cat_sel()
        if not cid:
            return
        if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                      tr("cat.conf_del_cat", default="¿Eliminar la categoría? Sus subcategorías subirán de nivel.")):
            cat.eliminar_categoria(cid); self._recargar_categorias()

    # ── Panel Marcas ─────────────────────────────────────────────────────────
    def _panel_marcas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_marca = _inp(tr("cat.marca_nombre", default="Nombre de marca"))
        fila.addWidget(self.inp_marca, 1)
        fila.addWidget(_btn(tr("cat.crear", default="CREAR"), self._crear_marca, primary=True))
        fila.addWidget(_btn(tr("cat.renombrar", default="RENOMBRAR"), self._renombrar_marca, primary=True))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_marca, danger=True))
        ly.addLayout(fila)
        self.tbl_marca = _tabla([tr("cat.col_marca", default="Marca")])
        self.tbl_marca.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_marca), 1)
        return w

    def _recargar_marcas(self):
        self._marcas = cat.listar_marcas()
        self.tbl_marca.setRowCount(0)
        for m in self._marcas:
            r = self.tbl_marca.rowCount(); self.tbl_marca.insertRow(r)
            self.tbl_marca.setItem(r, 0, QTableWidgetItem(m.get("nombre") or ""))

    def _marca_sel(self):
        r = self.tbl_marca.currentRow()
        return self._marcas[r]["id"] if getattr(self, "_marcas", None) and 0 <= r < len(self._marcas) else None

    def _crear_marca(self):
        n = self.inp_marca.text().strip()
        if n:
            cat.crear_marca(n); self.inp_marca.clear(); self._recargar_marcas()

    def _renombrar_marca(self):
        mid = self._marca_sel(); n = self.inp_marca.text().strip()
        if mid and n:
            cat.actualizar_marca(mid, nombre=n); self.inp_marca.clear(); self._recargar_marcas()

    def _eliminar_marca(self):
        mid = self._marca_sel()
        if mid and _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                              tr("cat.conf_del_marca", default="¿Eliminar la marca?")):
            cat.eliminar_marca(mid); self._recargar_marcas()

    # ── Panel Etiquetas ──────────────────────────────────────────────────────
    def _panel_etiquetas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_etq = _inp(tr("cat.etq_nombre", default="Nombre de etiqueta"))
        fila.addWidget(self.inp_etq, 1)
        fila.addWidget(_btn(tr("cat.crear", default="CREAR"), self._crear_etiqueta, primary=True))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_etiqueta, danger=True))
        ly.addLayout(fila)
        self.tbl_etq = _tabla([tr("cat.col_etq", default="Tags")])
        self.tbl_etq.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_etq), 1)
        return w

    def _recargar_etiquetas(self):
        self._etqs = cat.listar_etiquetas()
        self.tbl_etq.setRowCount(0)
        for e in self._etqs:
            r = self.tbl_etq.rowCount(); self.tbl_etq.insertRow(r)
            self.tbl_etq.setItem(r, 0, QTableWidgetItem(e.get("nombre") or ""))

    def _crear_etiqueta(self):
        n = self.inp_etq.text().strip()
        if n:
            cat.crear_etiqueta(n); self.inp_etq.clear(); self._recargar_etiquetas()

    def _eliminar_etiqueta(self):
        r = self.tbl_etq.currentRow()
        if getattr(self, "_etqs", None) and 0 <= r < len(self._etqs):
            if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                          tr("cat.conf_del_etq", default="¿Eliminar la etiqueta?")):
                cat.eliminar_etiqueta(self._etqs[r]["id"]); self._recargar_etiquetas()

    # ── Panel Descuentos (Fase 2 e-commerce) ─────────────────────────────────
    # Gestión de cupones (`db.fidelizacion` — motor YA existente y YA conectado al checkout de
    # Canal Web vía `comercio_digital.comercial.cotizar`/`checkout.confirmar`; esta pestaña es la
    # PRIMERA pantalla que lo administra, no un motor nuevo). "Carrito completo" del encargo: un
    # cupón no está atado a ningún producto/categoría (a diferencia de `db.promociones`, que SÍ
    # es por línea — motor distinto, ya usado por TPV, no se toca aquí).
    _TIPOS_CUPON_UI = [("% de descuento", "descuento_pct"), ("Importe fijo", "importe_fijo"),
                       ("Envío gratis", "envio_gratis")]

    def _panel_descuentos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(_lbl(tr("cat.desc_nuevo_t", default="Nuevo cupón de descuento"), dim=False, size=14))

        fila1 = QHBoxLayout()
        colc = QVBoxLayout(); colc.addWidget(_lbl(tr("cat.desc_codigo", default="Código")))
        self.inp_cup_cod = _inp(tr("cat.desc_codigo_ph", default="VERANO15"))
        colc.addWidget(self.inp_cup_cod); fila1.addLayout(colc, 1)
        colt = QVBoxLayout(); colt.addWidget(_lbl(tr("cat.desc_tipo", default="Tipo")))
        self.cmb_cup_tipo = _combo(self._TIPOS_CUPON_UI)
        colt.addWidget(self.cmb_cup_tipo); fila1.addLayout(colt, 1)
        colv = QVBoxLayout(); colv.addWidget(_lbl(tr("cat.desc_valor", default="Valor")))
        self.inp_cup_valor = _inp("0", 100)
        colv.addWidget(self.inp_cup_valor); fila1.addLayout(colv)
        ly.addLayout(fila1)

        fila2 = QHBoxLayout()
        for attr, etiqueta, ph in (
                ("inp_cup_inicio", "cat.desc_inicio", "Desde (AAAA-MM-DD, opcional)"),
                ("inp_cup_fin", "cat.desc_fin", "Hasta (AAAA-MM-DD, opcional)"),
                ("inp_cup_uso_max", "cat.desc_uso_max", "Usos totales"),
                ("inp_cup_min", "cat.desc_min", "Pedido mínimo € (opcional)")):
            col = QVBoxLayout(); col.addWidget(_lbl(tr(etiqueta, default=ph.split(" (")[0])))
            inp = _inp(tr(etiqueta + "_ph", default=ph))
            setattr(self, attr, inp)
            col.addWidget(inp); fila2.addLayout(col)
        self.inp_cup_uso_max.setText("1")
        ly.addLayout(fila2)

        for inp in (self.inp_cup_cod, self.inp_cup_valor, self.inp_cup_inicio, self.inp_cup_fin,
                   self.inp_cup_uso_max, self.inp_cup_min):
            inp.textChanged.connect(self._actualizar_resumen_cupon)
        self.cmb_cup_tipo.currentIndexChanged.connect(self._actualizar_resumen_cupon)

        self.lbl_resumen_cupon = QLabel("")
        self.lbl_resumen_cupon.setWordWrap(True)
        self.lbl_resumen_cupon.setStyleSheet(
            f"color:{_CIAN};font-family:'{_FONT}';font-size:13px;font-weight:700;"
            f"background:{_BG2};border:1px solid {_BORDE};border-radius:8px;padding:8px 10px;")
        ly.addWidget(self.lbl_resumen_cupon)
        self._actualizar_resumen_cupon()

        filab = QHBoxLayout(); filab.addStretch()
        filab.addWidget(_btn(tr("cat.desc_crear", default="CREAR CUPÓN"), self._crear_cupon, primary=True))
        ly.addLayout(filab)

        cols = [tr("cat.desc_codigo", default="Código"), tr("cat.desc_tipo", default="Tipo"),
                tr("cat.desc_valor", default="Valor"), tr("cat.desc_usos", default="Usos"),
                tr("cat.desc_vigencia", default="Vigencia"), tr("cat.desc_estado", default="Estado"), ""]
        self.tbl_cup = _tabla(cols)
        self.tbl_cup.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_cup), 1)
        return w

    def _resumen_cupon_texto(self, tipo, valor, fecha_inicio, fecha_fin, uso_maximo, importe_minimo):
        """Traduce la configuración actual del formulario a lenguaje natural (petición explícita
        del anexo UX: "15% de descuento en la colección Verano para compras superiores a 50€") —
        se recalcula en vivo con cada cambio, sin esperar a crear el cupón."""
        if tipo == "envio_gratis":
            frase = tr("cat.resumen_envio_gratis", default="Envío gratis")
        elif tipo == "importe_fijo":
            frase = tr("cat.resumen_importe_fijo", default="{v} € de descuento", v=f"{valor:.2f}")
        else:
            frase = tr("cat.resumen_pct", default="{v}% de descuento", v=f"{valor:g}")
        frase += " " + tr("cat.resumen_carrito", default="en todo el pedido")
        if importe_minimo:
            frase += " " + tr("cat.resumen_minimo", default="para compras superiores a {m} €",
                              m=f"{importe_minimo:.2f}")
        if fecha_inicio or fecha_fin:
            if fecha_inicio and fecha_fin:
                frase += " " + tr("cat.resumen_rango", default="(válido del {a} al {b})",
                                  a=fecha_inicio, b=fecha_fin)
            elif fecha_inicio:
                frase += " " + tr("cat.resumen_desde", default="(válido desde el {a})", a=fecha_inicio)
            else:
                frase += " " + tr("cat.resumen_hasta", default="(válido hasta el {b})", b=fecha_fin)
        if uso_maximo and uso_maximo > 1:
            frase += " — " + tr("cat.resumen_usos", default="máximo {n} usos", n=uso_maximo)
        elif uso_maximo == 1:
            frase += " — " + tr("cat.resumen_un_uso", default="un solo uso")
        return frase[0].upper() + frase[1:] + "."

    def _actualizar_resumen_cupon(self):
        try:
            valor = float((self.inp_cup_valor.text() or "0").replace(",", "."))
        except ValueError:
            valor = 0.0
        try:
            uso_maximo = int(self.inp_cup_uso_max.text() or 1)
        except ValueError:
            uso_maximo = 1
        try:
            importe_minimo = float((self.inp_cup_min.text() or "").replace(",", ".")) \
                if self.inp_cup_min.text().strip() else None
        except ValueError:
            importe_minimo = None
        self.lbl_resumen_cupon.setText(self._resumen_cupon_texto(
            self.cmb_cup_tipo.currentData(), valor, self.inp_cup_inicio.text().strip(),
            self.inp_cup_fin.text().strip(), uso_maximo, importe_minimo))

    def _crear_cupon(self):
        from src.db import fidelizacion as fid
        codigo = self.inp_cup_cod.text().strip().upper()
        if not codigo:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                  tr("cat.desc_sin_codigo", default="Indica un código de cupón."), "warning")
            return
        try:
            valor = float((self.inp_cup_valor.text() or "0").replace(",", "."))
        except ValueError:
            valor = 0.0
        try:
            uso_maximo = int(self.inp_cup_uso_max.text() or 1)
        except ValueError:
            uso_maximo = 1
        importe_minimo = None
        if self.inp_cup_min.text().strip():
            try:
                importe_minimo = float(self.inp_cup_min.text().replace(",", "."))
            except ValueError:
                pass
        id_cupon = fid.emitir_cupon(
            codigo, tipo=self.cmb_cup_tipo.currentData(), valor=valor,
            fecha_inicio=self.inp_cup_inicio.text().strip() or None,
            fecha_caducidad=self.inp_cup_fin.text().strip() or None,
            uso_maximo=uso_maximo, importe_minimo=importe_minimo)
        if id_cupon:
            self.inp_cup_cod.clear(); self.inp_cup_valor.clear()
            self.inp_cup_inicio.clear(); self.inp_cup_fin.clear()
            self.inp_cup_uso_max.setText("1"); self.inp_cup_min.clear()
            self._recargar_descuentos()
        else:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                  tr("cat.desc_error_crear",
                     default="No se pudo crear el cupón (¿código ya existente?)."), "warning")

    def _recargar_descuentos(self):
        from src.db import fidelizacion as fid
        self._cupones = fid.listar_cupones()
        self.tbl_cup.setRowCount(0)
        etiquetas_tipo = dict(self._TIPOS_CUPON_UI)
        etiquetas_tipo = {v: k for k, v in etiquetas_tipo.items()}
        for c in self._cupones:
            r = self.tbl_cup.rowCount(); self.tbl_cup.insertRow(r)
            self.tbl_cup.setItem(r, 0, QTableWidgetItem(c.get("codigo") or ""))
            self.tbl_cup.setItem(r, 1, QTableWidgetItem(etiquetas_tipo.get(c.get("tipo"), c.get("tipo") or "")))
            valor_txt = "—" if c.get("tipo") == "envio_gratis" else f"{float(c.get('valor') or 0):g}"
            self.tbl_cup.setItem(r, 2, QTableWidgetItem(valor_txt))
            usos_txt = f"{int(c.get('usos_actuales') or 0)}/{int(c.get('uso_maximo') or 1)}"
            self.tbl_cup.setItem(r, 3, QTableWidgetItem(usos_txt))
            vig = " → ".join(filter(None, [str(c.get("fecha_inicio") or ""),
                                           str(c.get("fecha_caducidad") or "")])) or "—"
            self.tbl_cup.setItem(r, 4, QTableWidgetItem(vig))
            self.tbl_cup.setItem(r, 5, QTableWidgetItem((c.get("estado") or "").upper()))
            if c.get("estado") == "activo":
                bd = _btn(tr("cat.desc_desactivar", default="Desactivar"),
                         lambda _c, i=c["id"]: (fid.desactivar_cupon(i), self._recargar_descuentos()),
                         danger=True)
                self.tbl_cup.setCellWidget(r, 6, bd)

    # ── Panel Envíos (Fase 3 e-commerce) ─────────────────────────────────────
    # Zonas de envío (`comercio_digital.envios.zonas` — motor YA existente, conectado a
    # `comercial.cotizar`; esta pestaña es la PRIMERA pantalla que lo administra, igual criterio
    # que Descuentos). Una zona sin países = "resto del mundo" (fallback, como mucho una por
    # empresa — se valida al calcular, no aquí).
    def _panel_envios(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(_lbl(tr("cat.env_nueva_t", default="Nueva zona de envío"), dim=False, size=14))

        fila1 = QHBoxLayout()
        coln = QVBoxLayout(); coln.addWidget(_lbl(tr("cat.env_nombre", default="Nombre")))
        self.inp_env_nombre = _inp(tr("cat.env_nombre_ph", default="España peninsular"))
        coln.addWidget(self.inp_env_nombre); fila1.addLayout(coln, 1)
        colp = QVBoxLayout(); colp.addWidget(_lbl(tr("cat.env_paises", default="Países (ISO, coma)")))
        self.inp_env_paises = _inp(tr("cat.env_paises_ph", default="ES,PT (vacío = resto del mundo)"))
        colp.addWidget(self.inp_env_paises); fila1.addLayout(colp, 1)
        ly.addLayout(fila1)

        fila2 = QHBoxLayout()
        for attr, etiqueta, ph in (
                ("inp_env_base", "cat.env_base", "Tarifa base € (0 = sin coste fijo)"),
                ("inp_env_kg", "cat.env_kg", "€/kg (0 = sin coste por peso)"),
                ("inp_env_umbral", "cat.env_umbral", "Gratis desde € (opcional)")):
            col = QVBoxLayout(); col.addWidget(_lbl(tr(etiqueta, default=ph.split(" (")[0])))
            inp = _inp(tr(etiqueta + "_ph", default=ph))
            setattr(self, attr, inp)
            col.addWidget(inp); fila2.addLayout(col)
        self.inp_env_base.setText("0"); self.inp_env_kg.setText("0")
        ly.addLayout(fila2)

        filab = QHBoxLayout(); filab.addStretch()
        filab.addWidget(_btn(tr("cat.env_crear", default="CREAR ZONA"), self._crear_zona_envio, primary=True))
        ly.addLayout(filab)

        cols = [tr("cat.env_nombre", default="Nombre"), tr("cat.env_paises", default="Países"),
                tr("cat.env_base", default="Base €"), tr("cat.env_kg", default="€/kg"),
                tr("cat.env_umbral", default="Gratis desde"), tr("cat.desc_estado", default="Estado"), ""]
        self.tbl_env = _tabla(cols)
        self.tbl_env.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_env), 1)
        return w

    def _crear_zona_envio(self):
        from src.services.comercio_digital.envios import zonas as _zonas
        nombre = self.inp_env_nombre.text().strip()
        if not nombre:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                  tr("cat.env_sin_nombre", default="Indica un nombre para la zona."), "warning")
            return
        try:
            tarifa_base = float((self.inp_env_base.text() or "0").replace(",", "."))
        except ValueError:
            tarifa_base = 0.0
        try:
            tarifa_kg = float((self.inp_env_kg.text() or "0").replace(",", "."))
        except ValueError:
            tarifa_kg = 0.0
        umbral = None
        if self.inp_env_umbral.text().strip():
            try:
                umbral = float(self.inp_env_umbral.text().replace(",", "."))
            except ValueError:
                pass
        id_zona = _zonas.crear_zona(
            nombre, paises=self.inp_env_paises.text().strip() or None, tarifa_base=tarifa_base,
            tarifa_por_kg=tarifa_kg, envio_gratis_desde=umbral)
        if id_zona:
            self.inp_env_nombre.clear(); self.inp_env_paises.clear()
            self.inp_env_base.setText("0"); self.inp_env_kg.setText("0"); self.inp_env_umbral.clear()
            self._recargar_envios()
        else:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                  tr("cat.env_error_crear", default="No se pudo crear la zona de envío."), "warning")

    def _recargar_envios(self):
        from src.services.comercio_digital.envios import zonas as _zonas
        self._zonas_envio = _zonas.listar_zonas()
        self.tbl_env.setRowCount(0)
        for z in self._zonas_envio:
            r = self.tbl_env.rowCount(); self.tbl_env.insertRow(r)
            self.tbl_env.setItem(r, 0, QTableWidgetItem(z.get("nombre") or ""))
            self.tbl_env.setItem(r, 1, QTableWidgetItem(z.get("paises") or
                                                        tr("cat.env_resto_mundo", default="Resto del mundo")))
            self.tbl_env.setItem(r, 2, QTableWidgetItem(f"{float(z.get('tarifa_base') or 0):.2f}"))
            self.tbl_env.setItem(r, 3, QTableWidgetItem(f"{float(z.get('tarifa_por_kg') or 0):.2f}"))
            umbral = z.get("envio_gratis_desde")
            self.tbl_env.setItem(r, 4, QTableWidgetItem(f"{float(umbral):.2f}" if umbral is not None else "—"))
            activa = int(z.get("activa", 1) or 0)
            self.tbl_env.setItem(r, 5, QTableWidgetItem(
                tr("cat.env_activa", default="ACTIVA") if activa else tr("cat.env_inactiva", default="INACTIVA")))
            bd = _btn(tr("cat.env_eliminar", default="Eliminar"),
                     lambda _c, i=z["id"]: (_zonas.eliminar_zona(i), self._recargar_envios()),
                     danger=True)
            self.tbl_env.setCellWidget(r, 6, bd)

    # ── Panel Web propia (Escenario B) ───────────────────────────────────────
    def _panel_web(self):
        # Rearquitectura Comercio Digital · Fase 2: la configuración de la WEB PROPIA (marca/logo/color/
        # moneda/dominio, publicación y sincronización) se administra AHORA ÚNICAMENTE en CANAL WEB. El
        # Catálogo es un PIM (solo producto): esta pestaña queda como PUNTO DE REDIRECCIÓN, sin edición,
        # eliminando la duplicidad de responsabilidades. Fuente/servicio únicos: canal_web + web_config.
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(14); ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(_lbl(tr("cat.web_moved_title",
                             default="La web de la empresa se administra en Canal Web"),
                          dim=False, size=15))
        info = _lbl(tr("cat.web_moved",
                       default="La configuración de la tienda online propia (marca, logo, color, "
                               "moneda, dominio, publicación y sincronización) se gestiona ahora desde "
                               "Canal Web (Comercio Digital). El Catálogo se centra exclusivamente en la "
                               "información del producto."), size=12)
        info.setWordWrap(True)
        ly.addWidget(info)
        fb = QHBoxLayout()
        # ÚNICO botón (automatización UX): `abrir_canal_web` ya decide por sí mismo si hay que
        # mostrar la pregunta inicial o saltar directo a la gestión del canal cuando YA existe
        # (`canal_web.existe`) — un segundo botón "ADMINISTRAR CANAL WEB" sería un acceso
        # redundante que hace exactamente lo mismo, solo que sin pasar por esa decisión.
        fb.addWidget(_btn(tr("cat.web_open_canal", default="ABRIR CANAL WEB"),
                          self._abrir_canal_web, primary=True))
        fb.addStretch()
        ly.addLayout(fb); ly.addStretch()
        return w

    def _abrir_canal_web(self):
        """Punto único de acceso a Canal Web: `abrir_canal_web` decide internamente si mostrar la
        pregunta inicial (WEB-12, canal sin configurar) o saltar directo a la gestión (canal YA
        existente — flujo directo, automatización UX)."""
        try:
            from src.gui.canal_web_gui import abrir_canal_web
            self._canal_web_win = abrir_canal_web(parent=self, usuario=getattr(self, "usuario", None))
        except Exception as e:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.web_open_err", default="No se pudo abrir Canal Web: {e}", e=e), "warning")

    # ── Carga / navegación ───────────────────────────────────────────────────
    def _recargar_todo(self):
        try:
            from src.db.empresa import empresa_actual_id
            from src.db import tiendas as _t
            self.lbl_ctx.setText(tr("cat.contexto", default="Tienda: {t}", t=_t.etiqueta_tienda_actual() or "—"))
        except Exception:
            pass
        self._recargar_productos(); self._recargar_categorias()
        self._recargar_marcas(); self._recargar_etiquetas()
        self._recargar_descuentos(); self._recargar_envios()

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()
        self.close()
