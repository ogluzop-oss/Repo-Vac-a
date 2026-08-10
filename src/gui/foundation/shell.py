"""
Enterprise Shell (Foundation) — contenedor único del que hereda toda pantalla Enterprise.

Desacoplado del framework: la capa `Base*` define el CONTRATO (anatomía, registro de pestañas por
factory, ciclo de vida, lazy loading, permisos y eventos) SIN depender de Qt; la capa `Qt*` es la
implementación concreta en PyQt6. El día que exista una versión web/móvil/API visual, solo se añade
otra implementación sin reescribir la arquitectura.

Anatomía de ventana: Header · Toolbar · Sidebar secundaria (opcional) · Tabs · Panel principal ·
Barra de estado · Footer. **Lazy loading obligatorio**: cada pestaña se construye/carga solo en su
primer acceso. La GUI solo orquesta; la lógica vive en `services/`.
"""

import logging

from src.gui.foundation import events as _ev
from src.gui.foundation import icons as _icons
from src.gui.foundation import permissions as _perm
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.foundation.shell")


# ══════════════════════════════════════════════════════════════════════════════
# Capa framework-agnóstica (contratos). NO importa Qt.
# ══════════════════════════════════════════════════════════════════════════════
class BaseEnterprisePanel:
    """Contrato de un panel/pestaña Enterprise. `cargar()` es perezoso (lo invoca el shell en el
    primer acceso). No implementa lógica de negocio: orquesta servicios ya existentes."""

    titulo = "Panel"
    concepto = None          # clave de icono (foundation.icons)
    permiso = None           # permiso RBAC requerido (opcional)
    autoridad = None         # autoridad de Gobierno requerida (opcional)
    destacada = False        # pestaña resaltada (pilar)

    def __init__(self, *, usuario=None, id_empresa=None, main=None):
        self.usuario = usuario
        self.id_empresa = id_empresa
        self.main = main
        self._cargado = False

    # Ciclo de vida (el shell los invoca; sobreescribir `cargar`)
    def cargar(self):
        """Carga perezosa de datos/servicios. Sobreescribir en cada panel."""

    def refrescar(self):
        self.cargar()

    def estado_permiso(self) -> str:
        return _perm.resolver(permiso=self.permiso, autoridad=self.autoridad,
                              usuario=self.usuario, id_empresa=self.id_empresa)


class BaseEnterpriseWindow:
    """Contrato de una ventana contenedora Enterprise: registro de pestañas por factory + lazy."""

    def __init__(self):
        self._pestanas = []   # [(titulo, factory, concepto, destacada)]

    def registrar_pestana(self, titulo, factory, *, concepto=None, destacada=False):
        self._pestanas.append((titulo, factory, concepto, destacada))


# ══════════════════════════════════════════════════════════════════════════════
# Implementación Qt/PyQt6.
# ══════════════════════════════════════════════════════════════════════════════
from PyQt6.QtCore import Qt                                        # noqa: E402
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton,     # noqa: E402
                             QTabWidget, QVBoxLayout, QWidget)


def _titulo_label(texto, acento=T.INFO):
    lbl = QLabel(texto)
    lbl.setStyleSheet(T.qss_titulo(acento))
    return lbl


def _boton_x(slot):
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(46, 40)
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{T.CRITICO};"
                    f"border:2px solid {T.CRITICO};border-radius:9px;font-weight:900;font-size:16px;}}"
                    f"QPushButton:hover{{background:{T.CRITICO};color:{T.BG};}}")
    if slot:
        b.clicked.connect(slot)
    return b


class QtEnterprisePanel(QWidget, BaseEnterprisePanel):
    """Panel Enterprise en Qt: Toolbar · Contenido · Barra de estado. Base de TODOS los paneles nuevos
    (Gemelo, Predicción, Gobierno, Simulador, Autonomía, Automatización, Historial)."""

    def __init__(self, *, usuario=None, id_empresa=None, main=None, parent=None):
        QWidget.__init__(self, parent)
        BaseEnterprisePanel.__init__(self, usuario=usuario, id_empresa=id_empresa, main=main)
        self.setStyleSheet(T.qss_panel())
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(T.SPACING_M, T.SPACING_M, T.SPACING_M, T.SPACING_M)
        self._root.setSpacing(T.SPACING_S)
        # Toolbar
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(T.SPACING_S)
        self._root.addLayout(self.toolbar)
        # Contenido
        self.contenido = QVBoxLayout()
        self.contenido.setSpacing(T.SPACING_S)
        self._root.addLayout(self.contenido, 1)
        # Barra de estado
        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{T.DIM};background:transparent;border:none;font-size:11px;")
        self._root.addWidget(self.status)

    def add_toolbar_widget(self, w):
        self.toolbar.addWidget(w)

    def toolbar_stretch(self):
        self.toolbar.addStretch(1)

    def set_status(self, texto, rol="neutro"):
        self.status.setStyleSheet(f"color:{T.color(rol)};background:transparent;border:none;font-size:11px;")
        self.status.setText(texto or "")

    def cargar_si_necesario(self):
        if self._cargado:
            return
        self._cargado = True
        estado = self.estado_permiso()
        if estado == _perm.OCULTO:
            self.set_status("Sin acceso a esta sección.", "advertencia")
            return
        try:
            self.cargar()
            _ev.publicar_ui(_ev.PANEL_OPENED, panel=self.__class__.__name__,
                            usuario=self.usuario, id_empresa=self.id_empresa)
            _ev.publicar_ui(_ev.DATA_LOADED, panel=self.__class__.__name__,
                            usuario=self.usuario, id_empresa=self.id_empresa)
        except Exception as e:
            logger.error("cargar panel %s: %s", self.__class__.__name__, e)
            self.set_status(f"Error al cargar: {e}", "critico")
        if estado == _perm.SOLO_LECTURA:
            self.set_status("Modo solo lectura (permisos).", "advertencia")


class QtEnterpriseWindow(QWidget, BaseEnterpriseWindow):
    """Ventana contenedora Enterprise: Header + Tabs (lazy) + Footer. Firma COMPATIBLE con el
    contrato de navegación del menú: (callback_vuelta, usuario, main, parent)."""

    titulo_ventana = "Enterprise"
    concepto = None

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        QWidget.__init__(self, parent)
        BaseEnterpriseWindow.__init__(self)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{T.BG};")
        self._construido = {}   # index -> bool (lazy)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACING_M, T.SPACING_M, T.SPACING_M, T.SPACING_M)
        root.setSpacing(T.SPACING_S)

        # Header
        header = QHBoxLayout()
        titulo = _icons.etiqueta(self.concepto, self.titulo_ventana) if self.concepto else self.titulo_ventana
        header.addWidget(_titulo_label(titulo))
        header.addStretch(1)
        self.header_tools = QHBoxLayout()
        header.addLayout(self.header_tools)
        if callback_vuelta:
            header.addWidget(_boton_x(callback_vuelta))
        root.addLayout(header)

        # Tabs (lazy)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # Footer / estado
        self.footer = QLabel("")
        self.footer.setStyleSheet(f"color:{T.DIM};background:transparent;border:none;font-size:11px;")
        root.addWidget(self.footer)

        self._crear_pestanas()      # subclase registra pestañas
        self._montar_placeholders()

    # ── API para subclases ──
    def _crear_pestanas(self):
        """Sobreescribir: llamar a `self.registrar_pestana(titulo, factory, concepto, destacada)`."""

    def _montar_placeholders(self):
        for i, (titulo, _factory, concepto, destacada) in enumerate(self._pestanas):
            cont = QWidget()
            lay = QVBoxLayout(cont)
            lay.setContentsMargins(0, 0, 0, 0)
            etiqueta = _icons.etiqueta(concepto, titulo) if concepto else titulo
            # IMPORTANTE: marcar como NO construida ANTES de `addTab`. Al añadir la 1ª pestaña, `addTab`
            # fija el índice 0 y dispara `currentChanged(0)` → `_on_tab_changed(0)` la construye; si el flag
            # se pusiera DESPUÉS, se reseteaba a False y la llamada explícita de abajo la construía OTRA VEZ
            # (sección duplicada en la 1ª pestaña).
            self._construido[i] = False
            self.tabs.addTab(cont, etiqueta)
            if destacada:
                # Pilar resaltado: acento cian en el texto de la pestaña (sin tooltip flotante).
                try:
                    from PyQt6.QtGui import QColor
                    self.tabs.tabBar().setTabTextColor(i, QColor(T.INFO))
                except Exception:
                    pass
        if self._pestanas:
            # Construye/mide la primera pestaña de inmediato (ya es la visible).
            self._on_tab_changed(0)

    def _on_tab_changed(self, index):
        if index < 0 or index >= len(self._pestanas) or self._construido.get(index):
            return
        titulo, factory, _concepto, _destacada = self._pestanas[index]
        try:
            widget = factory()
            cont = self.tabs.widget(index)
            # Scroll de PÁGINA COMPLETA: si el contenido no cabe, aparece barra vertical (las tablas
            # dejan de ir apretadas). Reutiliza el estilo de scrollbar neón de la app.
            from PyQt6.QtWidgets import QScrollArea
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
            scroll.setWidget(widget)
            cont.layout().addWidget(scroll)
            self._construido[index] = True
            if isinstance(widget, QtEnterprisePanel):
                widget.cargar_si_necesario()
            self.footer.setText(f"{titulo} cargado.")
        except Exception as e:
            logger.error("construir pestaña '%s': %s", titulo, e)
            cont = self.tabs.widget(index)
            err = QLabel(f"No se pudo cargar «{titulo}»: {e}")
            err.setStyleSheet(f"color:{T.CRITICO};")
            cont.layout().addWidget(err)
            self._construido[index] = True
