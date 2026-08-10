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

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.utils.i18n import tr

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

    def __init__(self, titulo, parent=None, ancho=0.62, alto=0.86, icono="📋"):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag = None
        try:
            g = self.screen().availableGeometry()
            self.resize(int(g.width() * ancho), int(g.height() * alto))
        except Exception:
            self.resize(900, 700)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("cbody")
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
        bx.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                         f"border-radius:9px;font-weight:900;font-size:16px;}}"
                         f"QPushButton:hover{{background:{_ROJO};color:{_BG};}}")
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
        self.cuerpo.setContentsMargins(4, 4, 12, 4)
        self.cuerpo.setSpacing(12)
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)
        self._root = root

    # Barra de acciones al pie (opcional).
    def barra_pie(self):
        fila = QHBoxLayout()
        self._root.addLayout(fila)
        return fila

    # Arrastre por la cabecera.
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() <= 60:
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
        x.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;font-weight:900;}}")
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
        b_ok = _btn("✔  " + tr("com.confirmar", default="Confirmar"), fg=_BG, border=_VERDE, bg=_VERDE,
                    hover_bg="#FFF", h=42)
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


# ══════════════════════════════════ CIRCULARES ══════════════════════════════════

class _CircularComposerDialog(_DialogoBase):
    """Compositor de una nueva circular."""

    def __init__(self, parent=None):
        super().__init__(tr("com.circ_nueva", default="NUEVA CIRCULAR"), parent, icono="📢", alto=0.86)
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
        pie = self.barra_pie()
        # "Adjuntar archivo" a la ESQUINA INFERIOR IZQUIERDA del pie, a la misma altura que Cancelar/Publicar.
        pie.addWidget(self.adj.extraer_boton(alto=46))
        pie.addStretch()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), fg=_ROJO, border=_ROJO, hover_bg=_ROJO,
                        hover_fg="#FFF", h=46)
        b_cancel.clicked.connect(self.reject)
        pie.addWidget(b_cancel)
        b_pub = _btn("📢  " + tr("com.publicar_circ", default="PUBLICAR CIRCULAR"), fg=_BG, border=_VERDE,
                     bg=_VERDE, hover_bg="#FFF", h=46)
        b_pub.clicked.connect(self._publicar)
        pie.addWidget(b_pub)

    def _publicar(self):
        from src.services.comunicacion_interna import circulares
        r = circulares.crear_circular(self.inp_titulo.text(), self.txt_cuerpo.toPlainText(),
                                      adjuntos=self.adj.rutas())
        if r.get("ok"):
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


class _CircularViewerDialog(_DialogoBase):
    """Visor de una circular: estructura base + imágenes en línea + confirmación de lectura."""

    def __init__(self, id_circular, parent=None):
        super().__init__(tr("com.circ_titulo", default="CIRCULAR"), parent, icono="📢")
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
        b = _btn("✔  " + tr("com.confirmar_lectura", default="CONFIRMAR LECTURA"), fg=_BG, border=_VERDE,
                 bg=_VERDE, hover_bg="#FFF", h=48)
        b.clicked.connect(self._confirmar)
        pie.addWidget(b)

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
        dlg = _ConfirmarPerfilDialog(self, titulo=tr("com.conf_lectura_t", default="CONFIRMAR LECTURA"))
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
                         f"border-radius:9px;font-weight:900;font-size:22px;padding:0 0 2px 0;}}"
                         f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}")
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
        x.setFixedSize(30, 34)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;font-weight:900;}}")
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

    def datos(self):
        tipo = self.cmb_tipo.currentData() or "OPCIONES"
        opciones = [c._inp.text().strip() for c in self._opciones if c._inp.text().strip()]
        return {"texto": self.inp_texto.text().strip(), "tipo": tipo, "opciones": opciones}


class _EncuestaComposerDialog(_DialogoBase):
    """Compositor de una nueva encuesta (preguntas ilimitadas, tipo por pregunta, texto introductorio)."""

    def __init__(self, parent=None):
        super().__init__(tr("com.enc_nueva", default="NUEVA ENCUESTA"), parent, icono="📊", alto=0.9)
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
        self._add_pregunta()
        pie = self.barra_pie()
        pie.addStretch()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), fg=_ROJO, border=_ROJO, hover_bg=_ROJO,
                        hover_fg="#FFF", h=46)
        b_cancel.clicked.connect(self.reject)
        pie.addWidget(b_cancel)
        b_pub = _btn("📊  " + tr("com.publicar_enc", default="PUBLICAR ENCUESTA"), fg=_BG, border=_VERDE,
                     bg=_VERDE, hover_bg="#FFF", h=46)
        b_pub.clicked.connect(self._publicar)
        pie.addWidget(b_pub)

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

    def _publicar(self):
        preguntas = [p.datos() for p in self._preguntas]
        from src.services.comunicacion_interna import encuestas
        r = encuestas.crear_encuesta(self.inp_titulo.text(), self.txt_intro.toPlainText(), preguntas,
                                     adjuntos=self.adj.rutas())
        if r.get("ok"):
            self.accept()
        else:
            QMessageBox.warning(self, tr("com.error", default="Aviso"), r.get("error", "Error"))


class _EncuestaViewerDialog(_DialogoBase):
    """Visor/relleno de una encuesta: preguntas con casillas u opción de texto + «Otro»."""

    def __init__(self, id_encuesta, parent=None):
        super().__init__(tr("com.enc_titulo", default="ENCUESTA"), parent, icono="📊", alto=0.9)
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
        b = _btn("📨  " + tr("com.enviar_respuesta", default="ENVIAR RESPUESTA"), fg=_BG, border=_VERDE,
                 bg=_VERDE, hover_bg="#FFF", h=48)
        b.clicked.connect(self._enviar)
        pie.addWidget(b)

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

    def _enviar(self):
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
        dlg = _ConfirmarPerfilDialog(self, titulo=tr("com.enviar_resp_t", default="ENVIAR RESPUESTA"))
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
        self._filas = []
        for c in circulares.listar_circulares():
            self._filas.append(("CIRCULAR", c))
        for e in encuestas.listar_encuestas():
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
        tipo, d = self._filas[row]
        dlg = _CircularViewerDialog(d["id"], self) if tipo == "CIRCULAR" else _EncuestaViewerDialog(d["id"], self)
        dlg.exec()
        self.refrescar()

    def _nueva_circular(self):
        if _CircularComposerDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()

    def _nueva_encuesta(self):
        if _EncuestaComposerDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()
