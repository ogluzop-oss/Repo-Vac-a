"""
Portal Web para Empleados (Back Office) · Ventana / navegación (Fases WEB-08/09; reforma WEB-13).

`PortalWebWindow` es el shell del Back Office web: barra lateral de navegación (con el MISMO diseño que el
resto de la app + botón de colapso) + área de contenido con **lazy loading** y scroll. Navegación FLUIDA
dentro de una sola ventana.

Secciones (reforma): **Inicio** (dashboard) · **Buscador global** · **Pedidos online** (`PortalWebHome`).
Las secciones de Reservas/Encargos/Stock/Logística/Clientes/Configuración se retiraron: duplicaban módulos
propios del ERP (Logística/CRM/Mostrar Stock/Canal Web). VISTAS DELGADAS que reutilizan `services/*`/`db/*`.
Autónoma respecto al TPV (el TPV solo la ABRE: router → PortalWebWindow).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _SIDEBAR

try:
    # Mismo tratamiento (fuente/repintado) que las sidebars del resto de la app. Con objectName
    # "btn_sidebar" queda EXCLUIDO del resplandor (glow) y del rol; solo iguala el render.
    from assets.estilo_global import aplicar_estilo_widget
except Exception:
    aplicar_estilo_widget = None

logger = logging.getLogger("gui.portal_web")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"

# Navegación estructural del Portal Web (sin emojis; mismo diseño de sidebar que el resto de la app).
_NAV = (
    ("inicio", "Inicio"),
    ("buscador", "Buscador global"),
    ("pedidos", "Pedidos online"),
)

# Estilos explícitos de los botones del sidebar (mismo aspecto que el resto de la app: fondo transparente =
# color de la sidebar; HOVER SWAP → pestaña blanca + texto oscuro; SELECCIONADA → texto cian + acento izq.
# cian). Tamaño 12px, igual que "SALIR AL TPV".
_SS_OFF = ("QPushButton{{background:transparent;color:#FFFFFF;text-align:left;padding:6px 8px 6px 28px;"
           "border:none;border-left:4px solid transparent;border-radius:0px;font-family:'{f}';"
           "font-weight:900;font-size:12px;outline:none;}}"
           "QPushButton:hover{{background:#FFFFFF;color:{sb};}}").format(f=_FONT, sb=_SIDEBAR)
_SS_ON = ("QPushButton{{background:#1A2230;color:{c};text-align:left;padding:6px 8px 6px 28px;"
          "border:none;border-left:4px solid {c};border-radius:0px;font-family:'{f}';"
          "font-weight:900;font-size:12px;outline:none;}}").format(c=_CIAN, f=_FONT)


class PortalWebWindow(QWidget):
    """Shell del Portal Web para empleados. Firma compatible: `empleado`/`id_caja` (para el núcleo
    `PortalWebHome`) y `id_empresa`/`usuario` (contexto, opcionales; retrocompat WEB-07)."""

    def __init__(self, empleado="—", id_caja="—", id_empresa=None, usuario=None, parent=None):
        super().__init__(parent)
        self._empleado = empleado
        self._id_caja = id_caja
        self._id_empresa = id_empresa
        self._usuario = usuario
        self._cache = {}   # lazy loading: clave -> widget (envuelto en scroll) ya creado
        self.setStyleSheet(f"background:{_BG};color:{_TEXT};")
        # Sidebar a TODA la altura (izquierda) + columna de contenido (derecha), como el resto de la app.
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar(), 0)

        right = QWidget()
        right.setStyleSheet(f"background:{_BG};")
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 16, 24, 16)
        rcol.setSpacing(12)
        # El título va DENTRO del contenido (la sidebar ocupa ya la esquina superior izquierda).
        cab = QHBoxLayout()
        titulo = QLabel("PORTAL WEB · EMPLEADOS")
        titulo.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:900;background:transparent;")
        cab.addWidget(titulo)
        cab.addStretch()
        rcol.addLayout(cab)

        # ── Área de contenido (lazy, con scroll) ──
        self._stack = QStackedWidget()
        rcol.addWidget(self._stack, 1)
        root.addWidget(right, 1)

        self._navegar("inicio")

    # ── Barra lateral: MISMO diseño que el resto de la app (#btn_sidebar) + botón de colapso ──
    def _build_sidebar(self) -> QFrame:
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230)
        self.sidebar = wrap
        wrap.setStyleSheet(f"QFrame#sw{{background:{_SIDEBAR};border:none;border-right:1px solid {_BORDE};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel("PORTAL WEB")   # título de la sidebar en MAYÚSCULAS
        cab.setStyleSheet(f"color:#FFFFFF;font-family:'{_FONT}';font-weight:900;font-size:16px;"
                          f"letter-spacing:2px;background:transparent;border:none;padding:0 0 24px 28px;")
        lay.addWidget(cab)
        self._botones = []
        for clave, texto in _NAV:
            b = QPushButton(texto.upper())   # MAYÚSCULAS, como el resto de sidebars
            # objectName "btn_sidebar": la app excluye estos botones del resplandor global (glow) en varios
            # puntos. El aspecto lo fija _SS_OFF/_SS_ON explícito (la hoja global no llega a esta ventana).
            b.setObjectName("btn_sidebar")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Sin resplandor (glow) en el texto: opt-out del refuerzo global de estilos (los botones de
            # sidebar deben verse planos, como el resto de la app).
            b.setProperty("sin_glow", True)
            b.setStyleSheet(_SS_OFF)
            if aplicar_estilo_widget is not None:
                try:
                    aplicar_estilo_widget(b)   # paridad de render con recepcion_pale (sin glow por objectName)
                except Exception:
                    pass
            b.setGraphicsEffect(None)          # garantiza sin resplandor tras el tratamiento
            b.clicked.connect(lambda _=False, c=clave: self._navegar(c))
            lay.addWidget(b)
            self._botones.append((b, clave))
        lay.addStretch()
        # Salir al TPV (rojo, al fondo del sidebar) — sustituye a la ✕ superior. Mismo estilo que el
        # "SALIR AL MENÚ" del resto de sidebars de la app.
        b_salir = QPushButton("SALIR AL TPV")
        b_salir.setObjectName("btn_sidebar_exit")
        b_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        b_salir.setFixedHeight(55)
        b_salir.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_salir.setStyleSheet(
            "QPushButton{background:transparent;color:#FF4C4C;border:none;border-left:4px solid transparent;"
            f"border-radius:0px;font-size:12px;font-family:'{_FONT}';font-weight:900;text-align:left;"
            "padding-left:28px;}QPushButton:hover{background:#FF4C4C;color:#0E1117;}")
        b_salir.clicked.connect(self._cerrar)
        lay.addWidget(b_salir)
        # Botón de colapso (igual que el resto de sidebars de la app).
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            instalar_sidebar_colapsable(self, wrap, usuario=self._usuario, clave="portal_web")
        except Exception as e:
            logger.debug("sidebar colapsable portal web: %s", e)
        return wrap

    # ── Fábrica de secciones (lazy). Cada sección reutiliza servicios existentes. ──
    def _crear_seccion(self, clave: str) -> QWidget:
        try:
            if clave == "inicio":
                from src.gui.portal_web_ui.inicio import SeccionInicio
                return self._con_scroll(SeccionInicio(empleado=self._empleado))
            if clave == "pedidos":
                from src.gui.portal_web_home import PortalWebHome
                return self._con_scroll(
                    PortalWebHome(empleado=self._empleado, id_caja=self._id_caja, parent=self))
            if clave == "buscador":
                from src.gui.portal_web_ui.buscador_global import \
                    SeccionBuscadorGlobal
                return self._con_scroll(SeccionBuscadorGlobal())
        except Exception as e:
            logger.debug("sección %s no disponible: %s", clave, e)
            return self._pagina_error(clave, e)
        return self._pagina_error(clave, "sección desconocida")

    def _con_scroll(self, widget: QWidget) -> QScrollArea:
        """Envuelve una sección en un área desplazable → el contenido nunca queda cortado (scroll en TODAS
        las secciones de la sidebar)."""
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        sc.setWidget(widget)
        return sc

    def _pagina_error(self, clave, e):
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(24, 24, 24, 24)
        lb = QLabel(f"La sección «{clave}» no está disponible en este entorno.\n{e}")
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{_TEXT2};background:{_BG2};border:1px dashed {_BORDE};"
                         f"border-radius:10px;padding:16px;font-size:12px;")
        ly.addWidget(lb)
        ly.addStretch()
        return w

    def _navegar(self, clave: str, *_ignore):
        """Navegación fluida con lazy loading. (`*_ignore` mantiene compatibilidad de firma.)"""
        for b, c in self._botones:
            sel = (c == clave)
            b.setChecked(sel)
            b.setStyleSheet(_SS_ON if sel else _SS_OFF)   # seleccionada = cian; resto = normal + hover swap
        if clave not in self._cache:
            w = self._crear_seccion(clave)
            self._stack.addWidget(w)
            self._cache[clave] = w
        self._stack.setCurrentWidget(self._cache[clave])

    def seccion_actual(self):
        for c, w in self._cache.items():
            if w is self._stack.currentWidget():
                return c
        return None

    def _cerrar(self):
        try:
            self.close()
        except Exception:
            pass
