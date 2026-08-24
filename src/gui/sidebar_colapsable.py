"""
P3 — Sidebar colapsable global (UX-TPV-01).

Helper ADITIVO y reutilizable: añade a CUALQUIER ventana con barra lateral un botón en la
ESQUINA SUPERIOR DERECHA DENTRO de la propia sidebar que la colapsa/expande, con persistencia
por usuario (preferencias_usuario).

Al colapsar, la sidebar NO se oculta del todo: se reduce a un "rail" estrecho que sigue
mostrando el botón (para poder re-expandirla). El contenido interno se oculta/restaura.
Tolerante a fallos: si algo falla, la ventana sigue funcionando igual.

Uso:
    from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
    instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="logistica")
"""

import logging

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PyQt6.QtWidgets import QToolButton, QWidget

logger = logging.getLogger("gui.sidebar_colapsable")

_CIAN = "#22F4E6"
_ANCHO_RAIL = 46
# Ensanche universal: deja sitio al botón de colapso para que no tape el título
# de la sidebar (se aplica a TODAS las sidebars que usan este helper).
_EXTRA_ANCHO = 28


class _Reposicionador(QObject):
    """Mantiene el botón pegado a la esquina superior derecha DENTRO de la sidebar."""

    def __init__(self, sidebar, boton, estado, margen=8):
        super().__init__(sidebar)
        self._sidebar = sidebar
        self._boton = boton
        self._estado = estado
        self._margen = margen
        sidebar.installEventFilter(self)
        self.reposicionar()

    def reposicionar(self):
        try:
            b, s = self._boton, self._sidebar
            # En rail centramos; expandida, esquina superior derecha con margen.
            margen = 3 if self._estado.get("colapsado") else self._margen
            b.move(max(0, s.width() - b.width() - margen), self._margen)
            b.raise_()
        except Exception:
            pass

    def eventFilter(self, obj, ev):
        if obj is self._sidebar and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.reposicionar()
        return False


def instalar_sidebar_colapsable(ventana, sidebar, *, usuario=None, clave=None, margen=8):
    """Instala el botón de colapso DENTRO de `sidebar`. Devuelve el QToolButton (o None)."""
    if ventana is None or sidebar is None:
        return None
    try:
        id_usuario = (usuario or {}).get("id") if isinstance(usuario, dict) else getattr(usuario, "id", None)
        clave_pref = f"sidebar_colapsado:{clave or sidebar.objectName() or 'default'}"

        # Ancho expandido original (las sidebars usan setFixedWidth → maximumWidth lo da).
        ancho_orig = sidebar.maximumWidth()
        if ancho_orig <= 0 or ancho_orig > 2000:
            ancho_orig = sidebar.width() or sidebar.minimumWidth() or 260
        # Ensanche universal para que el botón de colapso no tape el título.
        ancho_orig += _EXTRA_ANCHO

        btn = QToolButton(sidebar)            # ¡hijo de la SIDEBAR, no de la ventana!
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCheckable(True)
        btn.setFixedSize(34, 34)
        btn.setText("⮜")
        btn.setStyleSheet(
            "QToolButton{background:rgba(13,17,23,0.85);color:%s;border:2px solid %s;"
            "border-radius:9px;font-size:15px;font-weight:900;}"
            "QToolButton:hover{background:%s;color:#0B1118;}"
            "QToolButton:checked{background:%s;color:#0B1118;}" % (_CIAN, _CIAN, _CIAN, _CIAN)
        )

        # SCROLL + título bajo la flecha (UNIVERSAL para toda sidebar que use este colapsable):
        #   · El contenido de la sidebar (título + botones) puede DESBORDAR en vertical (módulos con muchas
        #     secciones), cortando el último botón (p. ej. "SALIR AL MENÚ"). Se envuelve TODO el contenido
        #     en un QScrollArea con la scrollbar ESTÁNDAR del software (turquesa, extremos redondeados) para
        #     que nada quede cortado.
        #   · La flecha de colapso ocupa la esquina superior-derecha (y=[margen, margen+34]); se baja el
        #     contenido (título incluido) por debajo subiendo el margen superior del layout interior, para
        #     que la flecha no tape títulos largos (p. ej. "SMART ACCOUNTING").
        try:
            import re
            from PyQt6.QtWidgets import QScrollArea, QVBoxLayout
            from src.gui.foundation.tokens import qss_scrollbar
            _old = sidebar.layout()
            if _old is not None and not getattr(sidebar, "_sb_scroll_hecho", False):
                # Color de fondo REAL de la sidebar (de su stylesheet): el scroll/viewport/content se pintan
                # OPACOS con ese color. NO se usa 'transparent' porque el viewport de un QScrollArea puede
                # ser una ventana NATIVA en Windows y, dentro de una ventana frameless, un viewport
                # translúcido deja ver lo que hay DETRÁS (el menú) → duplicaciones. Con fondo opaco no pasa.
                _mcol = re.search(r"background(?:-color)?\s*:\s*(#[0-9A-Fa-f]{3,8})", sidebar.styleSheet() or "")
                _bgcol = _mcol.group(1) if _mcol else "#0D1117"
                # 1) Mover el layout existente (título + botones) a un widget de CONTENIDO.
                _content = QWidget()
                _content.setObjectName("sb_scroll_content")
                _content.setStyleSheet(f"#sb_scroll_content{{background:{_bgcol};}}")
                _content.setLayout(_old)
                # 2) Bajar el contenido por debajo de la flecha (margen superior del layout interior).
                _m = _old.contentsMargins()
                _hueco = margen + btn.height() + 10
                if _m.top() < _hueco:
                    _old.setContentsMargins(_m.left(), _hueco, _m.right(), _m.bottom())
                # 3) QScrollArea OPACO (mismo color de sidebar). La scrollbar ESTÁNDAR se aplica al PROPIO
                #    scrollbar (no al área) para no cascar estilos sobre los botones.
                _scroll = QScrollArea(sidebar)
                _scroll.setObjectName("sb_scroll")
                _scroll.setWidgetResizable(True)          # el contenido llena el ancho y empuja el stretch
                _scroll.setWidget(_content)
                _scroll.setFrameShape(QScrollArea.Shape.NoFrame)
                _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                _scroll.setStyleSheet(f"QScrollArea#sb_scroll{{background:{_bgcol};border:none;}}")
                _scroll.viewport().setStyleSheet(f"background:{_bgcol};")
                _scroll.verticalScrollBar().setStyleSheet(qss_scrollbar())
                # 4) Nuevo layout en la sidebar con solo el scroll (el hueco del título ya va dentro).
                _outer = QVBoxLayout(sidebar)
                _outer.setContentsMargins(0, 0, 0, 0)
                _outer.setSpacing(0)
                _outer.addWidget(_scroll)
                sidebar._sb_scroll_hecho = True
        except Exception as e:
            logger.debug("scroll sidebar: %s", e)

        estado = {"colapsado": False}

        def _hijos_contenido():
            # Widgets de contenido directos de la sidebar (todos menos el propio botón).
            return [c for c in sidebar.findChildren(
                QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly) if c is not btn]

        anim_holder = {"obj": None}

        def _aplicar(colapsado, persistir=True, animar=True):
            estado["colapsado"] = bool(colapsado)
            destino = _ANCHO_RAIL if colapsado else ancho_orig
            btn.setChecked(colapsado)
            btn.setText("☰" if colapsado else "⮜")
            try:
                for c in _hijos_contenido():
                    c.setVisible(not colapsado)
                if not animar:
                    sidebar.setMinimumWidth(destino); sidebar.setMaximumWidth(destino)
                    repos.reposicionar()
                else:
                    inicio = sidebar.width()
                    anim = QPropertyAnimation(sidebar, b"maximumWidth")
                    anim.setDuration(190)
                    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    anim.setStartValue(inicio); anim.setEndValue(destino)
                    anim.valueChanged.connect(
                        lambda v: (sidebar.setMinimumWidth(int(v)), repos.reposicionar()))
                    anim.finished.connect(
                        lambda: (sidebar.setMinimumWidth(destino),
                                 sidebar.setMaximumWidth(destino), repos.reposicionar()))
                    anim_holder["obj"] = anim  # evita el GC durante la animación
                    anim.start()
            except Exception:
                try:
                    sidebar.setFixedWidth(destino)
                except Exception:
                    pass
            if persistir and id_usuario:
                try:
                    from src.db import preferencias
                    preferencias.guardar(id_usuario, clave_pref, "1" if colapsado else "0")
                except Exception:
                    pass

        btn.clicked.connect(lambda _checked=False: _aplicar(not estado["colapsado"]))

        repos = _Reposicionador(sidebar, btn, estado, margen)

        # Estado inicial desde preferencias (por defecto: expandido).
        colapsado_ini = False
        if id_usuario:
            try:
                from src.db import preferencias
                colapsado_ini = preferencias.obtener_bool(id_usuario, clave_pref, False)
            except Exception:
                colapsado_ini = False
        _aplicar(colapsado_ini, persistir=False, animar=False)

        ventana._sidebar_toggle_btn = btn
        ventana._sidebar_toggle_repos = repos
        btn.show()
        return btn
    except Exception as e:
        logger.debug("instalar_sidebar_colapsable: %s", e)
        return None
