"""
Transiciones globales de DESLIZAMIENTO al cambiar de pantalla (QStackedWidget) o de pestaña
(QTabWidget): la vista SALIENTE se desliza hacia la DERECHA y deja paso a la entrante.

Técnica basada en SNAPSHOT (no reparenta ni mueve los widgets vivos, así no rompe layouts ni foco):
al cambiar, se captura la vista anterior en un QLabel superpuesto y se anima ese overlay saliendo por
la derecha; la nueva vista ya está debajo. A prueba de fallos: cualquier error degrada a un cambio
instantáneo sin animación.

API:
    from src.gui.transiciones import instalar_transicion_tabs, instalar_transicion_stack
    instalar_transicion_tabs(qtabwidget)
    instalar_transicion_stack(qstackedwidget)
"""

import logging

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation
from PyQt6.QtWidgets import QLabel

logger = logging.getLogger("gui.transiciones")

_DUR = 240  # ms


def _deslizar(old_widget, new_widget, duracion: int):
    """Efecto filmstrip: el SALIENTE (snapshot) se va por la derecha y el ENTRANTE (widget vivo) entra
    desde la izquierda, a la vez. El entrante SIEMPRE se anima (garantiza que el efecto se vea, aunque el
    snapshot del saliente falle). Todo relativo al PADRE del entrante (el stack interno del QTabWidget o
    el propio QStackedWidget)."""
    try:
        if new_widget is None:
            return
        cont = new_widget.parentWidget()
        if cont is None:
            return
        w = cont.width()
        if w <= 0 or cont.height() <= 0:
            return
        g = new_widget.geometry()
        # (a) Saliente: snapshot deslizándose a la DERECHA (best-effort).
        try:
            if old_widget is not None:
                pm = old_widget.grab()
                if not pm.isNull():
                    ov = QLabel(cont); ov.setPixmap(pm); ov.setGeometry(g)
                    ov.raise_(); ov.show()
                    a1 = QPropertyAnimation(ov, b"pos", ov)
                    a1.setDuration(int(duracion))
                    a1.setStartValue(g.topLeft())
                    a1.setEndValue(QPoint(g.x() + w, g.y()))
                    a1.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    a1.finished.connect(ov.deleteLater)
                    a1.start(); ov._a = a1
        except Exception:
            pass
        # (b) Entrante: widget vivo entrando desde la IZQUIERDA (garantizado).
        new_widget.raise_()
        a2 = QPropertyAnimation(new_widget, b"pos", new_widget)
        a2.setDuration(int(duracion))
        a2.setStartValue(QPoint(g.x() - w, g.y()))
        a2.setEndValue(g.topLeft())
        a2.setEasingCurve(QEasingCurve.Type.InOutCubic)
        a2.finished.connect(lambda gp=g.topLeft(): new_widget.move(gp))
        a2.start()
        new_widget._a_in = a2
    except Exception as e:
        logger.debug("_deslizar: %s", e)


def deslizar_entrada_modulo(pm_saliente, ventana_entrante, duracion: int = _DUR, revelar=None,
                            al_cubrir=None):
    """Anima la ENTRADA a un módulo desde el menú principal.

    `pm_saliente` es una instantánea (QPixmap) de la pantalla anterior —el menú— capturada ANTES de
    ocultarlo; `ventana_entrante` es la ventana/contenedor del módulo ya mostrado y con geometría. La
    instantánea se superpone sobre él y se desliza hacia la DERECHA, dejándolo ver debajo — mismo lenguaje
    visual que `_deslizar` (el saliente sale por la derecha).

    - `revelar` (opcional): ventana abierta con `windowOpacity(0)` para evitar el destello de la ventana
      nativa; se revela (`opacity=1`) UNA VEZ ya está cubierta por la instantánea (caso: módulo en ventana
      propia). Así el primer fotograma visible es el menú, nunca blanco ni el módulo.
    - `al_cubrir` (opcional): callback que se ejecuta con la instantánea YA puesta encima (p. ej. cambiar la
      página del stack raíz al módulo), de modo que el cambio ocurre DEBAJO del overlay y no se ve
      (caso: TPV embebido en el stack).

    A prueba de fallos: cualquier error degrada a mostrar el módulo (revelar/cubrir) sin animación."""
    def _revelar():
        if revelar is not None:
            try:
                revelar.setWindowOpacity(1.0)
            except Exception:
                pass

    def _cubrir():
        if al_cubrir is not None:
            try:
                al_cubrir()
            except Exception:
                pass
    try:
        ov = None
        if (ventana_entrante is not None and pm_saliente is not None and not pm_saliente.isNull()):
            w, h = ventana_entrante.width(), ventana_entrante.height()
            if w > 0 and h > 0:
                ov = QLabel(ventana_entrante)
                ov.setPixmap(pm_saliente)
                ov.setScaledContents(True)   # la instantánea (tamaño del menú) cubre exactamente el módulo
                ov.setGeometry(0, 0, w, h)
                ov.raise_()
                ov.show()
                ov.repaint()                 # pinta la instantánea YA (antes de cubrir/revelar)
        _cubrir()                            # el cambio de pantalla ocurre DEBAJO del overlay (no se ve)
        _revelar()                           # revelar la ventana ya cubierta: sin destello ni módulo previo
        if ov is None:
            return
        ov.raise_()                          # asegurar que sigue por encima tras el cambio de página
        a = QPropertyAnimation(ov, b"pos", ov)
        a.setDuration(int(duracion))
        a.setStartValue(QPoint(0, 0))
        a.setEndValue(QPoint(ov.width(), 0))
        a.setEasingCurve(QEasingCurve.Type.InOutCubic)
        a.finished.connect(ov.deleteLater)
        a.start()
        ov._a = a                            # evita el GC de la animación
    except Exception as e:
        logger.debug("deslizar_entrada_modulo: %s", e)
        _cubrir()
        _revelar()


def instalar_transicion_tabs(tabs, duracion: int = _DUR):
    """Instala la transición de deslizamiento en un QTabWidget (cambio de sub-pestaña). Idempotente."""
    try:
        if tabs.property("_trans_ok"):
            return tabs
        tabs.setProperty("_trans_ok", True)
        estado = {"w": tabs.currentWidget()}

        def _on_change(_idx):
            old = estado["w"]
            nuevo = tabs.currentWidget()
            estado["w"] = nuevo
            if nuevo is None or old is nuevo:
                return
            _deslizar(old, nuevo, duracion)

        tabs.currentChanged.connect(_on_change)
    except Exception as e:
        logger.debug("instalar_transicion_tabs: %s", e)
    return tabs


def instalar_transicion_stack(stack, duracion: int = _DUR):
    """Instala la transición de deslizamiento en un QStackedWidget (cambio de pantalla/sección). Idempotente."""
    try:
        if stack.property("_trans_ok"):
            return stack
        stack.setProperty("_trans_ok", True)
        estado = {"w": stack.currentWidget()}

        def _on_change(_idx):
            old = estado["w"]
            nuevo = stack.currentWidget()
            estado["w"] = nuevo
            if nuevo is None or old is nuevo:
                return
            _deslizar(old, nuevo, duracion)

        stack.currentChanged.connect(_on_change)
    except Exception as e:
        logger.debug("instalar_transicion_stack: %s", e)
    return stack


def instalar_transiciones_en(widget):
    """Propaga la transición a TODA la navegación de `widget` (una ventana/módulo): todos los QTabWidget
    (cambio de sub-pestaña) y los QStackedWidget de navegación (cambio de sección). Se EXCLUYEN los
    QStackedWidget INTERNOS de un QTabWidget (los gestiona su propio QTabWidget) para no duplicar la
    animación. Idempotente y a prueba de fallos: se puede llamar cada vez que se abre un módulo."""
    try:
        from PyQt6.QtWidgets import QStackedWidget, QTabWidget
        objetivos_tabs = list(widget.findChildren(QTabWidget))
        if isinstance(widget, QTabWidget):
            objetivos_tabs.append(widget)
        for tw in objetivos_tabs:
            instalar_transicion_tabs(tw)
        objetivos_stack = list(widget.findChildren(QStackedWidget))
        if isinstance(widget, QStackedWidget):
            objetivos_stack.append(widget)
        for st in objetivos_stack:
            if isinstance(st.parent(), QTabWidget):   # stack interno de un QTabWidget → NO animar aquí
                continue
            instalar_transicion_stack(st)
    except Exception as e:
        logger.debug("instalar_transiciones_en: %s", e)
    return widget
