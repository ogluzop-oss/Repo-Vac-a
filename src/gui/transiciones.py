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

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect
from PyQt6.QtWidgets import QLabel

logger = logging.getLogger("gui.transiciones")

_DUR = 240  # ms


def _animar_salida(container, old_widget, geom: QRect, duracion: int):
    """Superpone un snapshot de `old_widget` sobre `container` y lo desliza a la derecha."""
    try:
        if old_widget is None or geom.width() <= 0 or geom.height() <= 0:
            return
        pm = old_widget.grab()
        if pm.isNull():
            return
        ov = QLabel(container)
        ov.setPixmap(pm)
        ov.setGeometry(geom)
        ov.raise_()
        ov.show()
        anim = QPropertyAnimation(ov, b"pos", ov)
        anim.setDuration(int(duracion))
        anim.setStartValue(geom.topLeft())
        anim.setEndValue(QPoint(geom.x() + container.width(), geom.y()))
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.finished.connect(ov.deleteLater)
        anim.start()
        ov._anim = anim   # conserva la referencia mientras dura la animación
    except Exception as e:
        logger.debug("_animar_salida: %s", e)


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
            if old is None or old is nuevo:
                return
            try:
                geom = QRect(old.mapTo(tabs, QPoint(0, 0)), old.size())
            except Exception:
                geom = tabs.rect()
            _animar_salida(tabs, old, geom, duracion)

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
            if old is None or old is nuevo:
                return
            _animar_salida(stack, old, QRect(0, 0, stack.width(), stack.height()), duracion)

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
