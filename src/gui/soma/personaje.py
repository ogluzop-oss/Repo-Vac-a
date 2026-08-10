"""
SomaCharacter (Fase 2). Widget del personaje: muestra la ilustración del estado actual y aplica
TRANSFORMACIONES suaves (escala/rotación/desplazamiento/opacidad) sobre ella, de forma independiente
del formato del asset. No decide estados (eso es del SomaKernel): solo los representa.

Usa `QGraphicsView` + un item de pixmap para poder transformar la ilustración con fluidez (estilo
Disney/Pixar: microanimaciones sutiles, nunca exageradas).
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from src.gui.soma import character_pack as _cp

logger = logging.getLogger("gui.soma.personaje")


class SomaCharacter(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setStyleSheet("background: transparent; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self._item)

        self._pack = _cp.pack()
        self._recurso = None
        self._recurso_blink = self._pack.parpadeo()
        self._parpadeando = False

        # Componentes de transformación (los combina el controlador de animación)
        self._base_scale = 1.0
        self._breath = 1.0      # factor de respiración (≈1.0)
        self._extra_scale = 1.0  # acentos por estado / rebotes
        self._sway = 0.0        # grados
        self._bob = 0.0         # px verticales
        self._offx = 0.0        # px horizontales
        self._opacity = 1.0

        # Timer para recursos animados (gif/sprite)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._siguiente_frame)

        self.mostrar_estado("DORMIDO")

    # ── Representación de estado (ilustración) ────────────────────────────────
    def mostrar_estado(self, estado: str):
        rec = self._pack.para_estado(estado)
        self._set_recurso(rec)

    def mostrar_pose(self, clave: str):
        """Fuerza una pose concreta por clave (p.ej. 'proponiendo'), independiente del estado."""
        self._set_recurso(self._pack.recurso(clave))

    def _set_recurso(self, rec: _cp.RecursoPersonaje):
        self._recurso = rec
        self._refrescar_pixmap()
        if rec and rec.animado:
            self._frame_timer.start(80)
        else:
            self._frame_timer.stop()

    def _refrescar_pixmap(self):
        if not self._recurso:
            return
        pm = self._recurso.pixmap()
        if pm.isNull():
            return
        self._item.setPixmap(pm)
        self._item.setOffset(-pm.width() / 2, -pm.height() / 2)  # origen en el centro
        self._recolocar()

    def _siguiente_frame(self):
        if self._recurso:
            self._recurso.avanzar()
            self._refrescar_pixmap()

    # ── Parpadeo (superpone brevemente la ilustración de ojos cerrados) ───────
    def parpadear(self):
        if self._parpadeando or not self._recurso_blink:
            return
        estado_actual = self._recurso
        self._parpadeando = True
        self._set_recurso(self._recurso_blink)
        QTimer.singleShot(120, lambda: self._fin_parpadeo(estado_actual))

    def _fin_parpadeo(self, recurso_previo):
        self._parpadeando = False
        if recurso_previo:
            self._set_recurso(recurso_previo)

    # ── Transformaciones (las fija el controlador de animación) ───────────────
    def set_micro(self, *, breath=None, sway=None, bob=None, offx=None):
        if breath is not None:
            self._breath = breath
        if sway is not None:
            self._sway = sway
        if bob is not None:
            self._bob = bob
        if offx is not None:
            self._offx = offx
        self._aplicar()

    def set_extra_scale(self, s):
        self._extra_scale = s
        self._aplicar()

    def set_opacity(self, o):
        self._opacity = max(0.0, min(1.0, o))
        self._item.setOpacity(self._opacity)

    def _aplicar(self):
        self._item.setScale(self._base_scale * self._breath * self._extra_scale)
        self._item.setRotation(self._sway)

    def _recolocar(self):
        r = self.viewport().rect()
        pm = self._item.pixmap()
        if pm.isNull() or r.width() < 2:
            return
        margen = 0.86
        escala = min(r.width() / pm.width(), r.height() / pm.height()) * margen
        self._base_scale = max(0.05, escala)
        cx, cy = r.width() / 2 + self._offx, r.height() / 2 + self._bob
        self._item.setPos(cx, cy)
        self.scene().setSceneRect(0, 0, r.width(), r.height())
        self._aplicar()

    def actualizar_posicion(self):
        """Recalcula posición/escala tras un cambio de bob/offset (microanimación)."""
        r = self.viewport().rect()
        self._item.setPos(r.width() / 2 + self._offx, r.height() / 2 + self._bob)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recolocar()
