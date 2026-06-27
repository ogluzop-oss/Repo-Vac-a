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

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QToolButton, QWidget

logger = logging.getLogger("gui.sidebar_colapsable")

_CIAN = "#22F4E6"
_ANCHO_RAIL = 46


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

        btn = QToolButton(sidebar)            # ¡hijo de la SIDEBAR, no de la ventana!
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCheckable(True)
        btn.setFixedSize(34, 34)
        btn.setToolTip("Ocultar / mostrar panel lateral")
        btn.setText("⮜")
        btn.setStyleSheet(
            "QToolButton{background:rgba(13,17,23,0.85);color:%s;border:2px solid %s;"
            "border-radius:9px;font-size:15px;font-weight:900;}"
            "QToolButton:hover{background:%s;color:#0B1118;}"
            "QToolButton:checked{background:%s;color:#0B1118;}" % (_CIAN, _CIAN, _CIAN, _CIAN)
        )

        estado = {"colapsado": False}

        def _hijos_contenido():
            # Widgets de contenido directos de la sidebar (todos menos el propio botón).
            return [c for c in sidebar.findChildren(
                QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly) if c is not btn]

        def _aplicar(colapsado, persistir=True):
            estado["colapsado"] = bool(colapsado)
            try:
                for c in _hijos_contenido():
                    c.setVisible(not colapsado)
                sidebar.setFixedWidth(_ANCHO_RAIL if colapsado else ancho_orig)
            except Exception:
                return
            btn.setChecked(colapsado)
            btn.setText("☰" if colapsado else "⮜")
            btn.setToolTip("Mostrar panel lateral" if colapsado else "Ocultar panel lateral")
            try:
                repos.reposicionar()
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
        _aplicar(colapsado_ini, persistir=False)

        ventana._sidebar_toggle_btn = btn
        ventana._sidebar_toggle_repos = repos
        btn.show()
        return btn
    except Exception as e:
        logger.debug("instalar_sidebar_colapsable: %s", e)
        return None
