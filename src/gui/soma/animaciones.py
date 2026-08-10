"""
Controlador de animación de SOMA (Fase 2). Combina el CAMBIO DE ILUSTRACIONES (por estado del
Kernel) con TRANSFORMACIONES suaves y MICROANIMACIONES continuas, para que el personaje transmita
vida (estilo Disney/Pixar: sutil, elegante, nunca exagerado). No decide estados: los recibe.

Microanimaciones continuas: respiración (escala), balanceo (rotación), flotación (bob vertical),
parpadeo periódico. Secuencias: aparición (elevación + fundido → mano a la oreja) y desaparición.
"""

import logging
import math
import random

from PyQt6.QtCore import QEasingCurve, QTimer, QVariantAnimation

logger = logging.getLogger("gui.soma.animaciones")

_FPS_MS = 33  # ~30 fps para las microanimaciones


class ControladorAnimacion:
    def __init__(self, personaje):
        self.p = personaje
        self._fase = 0.0
        self._activo = False
        # Amplitudes SUTILES (elegantes)
        self.amp_breath = 0.02     # ±2% de escala
        self.amp_sway = 1.4        # ±1.4° de rotación
        self.amp_bob = 4.0         # ±4 px verticales

        self._micro = QTimer(self.p)
        self._micro.timeout.connect(self._tick_micro)

        self._blink = QTimer(self.p)
        self._blink.timeout.connect(self._parpadeo)

        self._anim_aparicion = None

    # ── Microanimaciones continuas ────────────────────────────────────────────
    def iniciar_microanimaciones(self):
        if not self._micro.isActive():
            self._micro.start(_FPS_MS)
        if not self._blink.isActive():
            self._blink.start(self._proximo_parpadeo())

    def detener_microanimaciones(self):
        self._micro.stop()
        self._blink.stop()

    def _tick_micro(self):
        self._fase += 0.06
        breath = 1.0 + self.amp_breath * math.sin(self._fase)
        sway = self.amp_sway * math.sin(self._fase * 0.5)
        bob = self.amp_bob * math.sin(self._fase * 0.8)
        self.p.set_micro(breath=breath, sway=sway, bob=bob)
        self.p.actualizar_posicion()

    def _proximo_parpadeo(self) -> int:
        return random.randint(2800, 5200)   # ms entre parpadeos (natural)

    def _parpadeo(self):
        self.p.parpadear()
        self._blink.start(self._proximo_parpadeo())

    # ── Acento por estado (además de cambiar la ilustración) ──────────────────
    def aplicar_estado(self, estado: str):
        """Cambia la ilustración y aplica un pequeño acento de transformación por estado."""
        estado = str(estado).upper()
        self.p.mostrar_estado(estado)
        if estado == "CONFIRMACION":
            self._rebote(1.10)
        elif estado == "ERROR":
            self._sacudida()
        elif estado == "HABLANDO":
            self._rebote(1.04)
        elif estado == "PENSANDO":
            self._inclinar(2.0)
        else:
            self.p.set_extra_scale(1.0)

    def _rebote(self, pico=1.08):
        anim = QVariantAnimation(self.p)
        anim.setStartValue(1.0); anim.setKeyValueAt(0.5, pico); anim.setEndValue(1.0)
        anim.setDuration(320); anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.valueChanged.connect(lambda v: self.p.set_extra_scale(float(v)))
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _sacudida(self):
        anim = QVariantAnimation(self.p)
        anim.setDuration(360)
        anim.setStartValue(-6.0); anim.setKeyValueAt(0.25, 6.0)
        anim.setKeyValueAt(0.5, -4.0); anim.setKeyValueAt(0.75, 4.0); anim.setEndValue(0.0)
        anim.valueChanged.connect(lambda v: self.p.set_micro(offx=float(v)))
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _inclinar(self, grados):
        self.p.set_micro(sway=grados)

    # ── Secuencia de APARICIÓN (§9): elevación + fundido (la ilustración la fija el Kernel) ──
    def secuencia_aparicion(self, al_terminar=None):
        self.iniciar_microanimaciones()
        anim = QVariantAnimation(self.p)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(460); anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _paso(v):
            v = float(v)
            self.p.set_opacity(v)
            # Elevación: sube desde +46px hasta su posición; ligero overshoot de escala
            self.p.set_micro(bob=(1.0 - v) * 46.0)
            self.p.actualizar_posicion()
            self.p.set_extra_scale(0.92 + 0.08 * v)

        def _fin():
            self.p.set_extra_scale(1.0)
            if callable(al_terminar):
                al_terminar()

        anim.valueChanged.connect(_paso)
        anim.finished.connect(_fin)
        self._anim_aparicion = anim
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    # ── Secuencia de DESAPARICIÓN (solo transformaciones) ─────────────────────
    def secuencia_desaparicion(self, al_terminar=None):
        anim = QVariantAnimation(self.p)
        anim.setStartValue(1.0); anim.setEndValue(0.0)
        anim.setDuration(320); anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def _paso(v):
            v = float(v)
            self.p.set_opacity(v)
            self.p.set_micro(bob=(1.0 - v) * 24.0)
            self.p.actualizar_posicion()

        def _fin():
            self.detener_microanimaciones()
            self.p.set_opacity(1.0)
            if callable(al_terminar):
                al_terminar()

        anim.valueChanged.connect(_paso)
        anim.finished.connect(_fin)
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
