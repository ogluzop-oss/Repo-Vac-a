"""
Adaptador de voz de SOMA (Fase 1 — núcleo). ENVUELVE los sistemas de voz ya existentes
(`SomaWorker` = wake-word + STT; `SomaTTS` = voz) que crea `SmartManagerApp`. NO crea hilos ni
motores paralelos: solo referencia los existentes y ofrece una interfaz estable y enchufable para
el kernel.

En esta fase NO hay voz interactiva (eso es de una fase posterior): aquí solo se prepara el puente.
"""

import logging

logger = logging.getLogger("soma.voz")


class AdaptadorVoz:
    def __init__(self):
        self._worker = None            # SomaWorker (propiedad de la app)
        self._worker_getter = None     # callable → SomaWorker | None (lazy/vivo)
        self._tts_getter = None        # callable → SomaTTS | None (lazy)

    def enlazar(self, *, worker=None, worker_getter=None, tts_getter=None) -> None:
        if worker is not None:
            self._worker = worker
        if worker_getter is not None:
            self._worker_getter = worker_getter
        if tts_getter is not None:
            self._tts_getter = tts_getter

    @property
    def worker(self):
        if self._worker is not None:
            return self._worker
        try:
            return self._worker_getter() if self._worker_getter else None
        except Exception:
            return None

    @property
    def tts(self):
        try:
            return self._tts_getter() if self._tts_getter else None
        except Exception:
            return None

    def escucha_disponible(self) -> bool:
        try:
            return bool(self._worker and getattr(self._worker, "disponible", False))
        except Exception:
            return False

    def voz_disponible(self) -> bool:
        t = self.tts
        try:
            return bool(t and t.disponible())
        except Exception:
            return False

    def hablando(self) -> bool:
        t = self.tts
        try:
            return bool(t and t.hablando)
        except Exception:
            return False

    def detener_voz(self) -> None:
        t = self.tts
        try:
            if t:
                t.detener()
        except Exception as e:
            logger.debug("detener_voz: %s", e)

    def interrumpir(self) -> None:
        """Interrumpe el discurso actual (para que el usuario pueda cortar a SOMA)."""
        self.detener_voz()

    def hablar(self, texto: str, *, al_terminar=None) -> None:
        """Reproduce `texto` por TTS y llama a `al_terminar` cuando el discurso finaliza REALMENTE
        (sondeando `SomaTTS.hablando`, ya que no hay señal de fin). Así la pose HABLANDO se mantiene
        hasta que acaba la voz. Si no hay TTS, llama a `al_terminar` de inmediato. A prueba de fallos."""
        tts = self.tts
        if not tts or not (texto or "").strip():
            if callable(al_terminar):
                al_terminar()
            return
        try:
            tts.decir(texto)
        except Exception as e:
            logger.debug("hablar: %s", e)
            if callable(al_terminar):
                al_terminar()
            return
        from PyQt6.QtCore import QTimer
        estado = {"empezo": False, "ticks": 0}

        def _tick():
            estado["ticks"] += 1
            try:
                hablando = bool(tts.hablando)
            except Exception:
                hablando = False
            if hablando:
                estado["empezo"] = True
            elif estado["empezo"] or estado["ticks"] > 24:  # terminó, o ~3,6 s sin arrancar
                if callable(al_terminar):
                    al_terminar()
                return
            if estado["ticks"] < 400:                       # tope de seguridad (~60 s)
                QTimer.singleShot(150, _tick)
        QTimer.singleShot(150, _tick)
