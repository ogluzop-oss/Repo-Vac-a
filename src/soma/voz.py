"""
Adaptador de voz de SOMA (Fase 1 — núcleo). ENVUELVE los sistemas de voz ya existentes
(`SomaWorker` = wake-word + STT; `SomaTTS` = voz) que crea `SmartManagerApp`. NO crea hilos ni
motores paralelos: solo referencia los existentes y ofrece una interfaz estable y enchufable para
el kernel.

En esta fase NO hay voz interactiva (eso es de una fase posterior): aquí solo se prepara el puente.
"""

import logging
import re

logger = logging.getLogger("soma.voz")

# ── Limpieza de Markdown para TTS ───────────────────────────────────────────────
# Las respuestas de SOMA (motor LLM) pueden venir en Markdown (negrita, listas,
# títulos, enlaces, código). El panel de texto lo renderiza (`conversacion.py`,
# QLabel en MarkdownText), pero la voz NO debe "leer" los símbolos literalmente
# (asterisco asterisco, guion, etc.). Estas expresiones son deliberadamente
# conservadoras: solo tocan sintaxis Markdown real, nunca guiones de palabras
# compuestas (bien-conocido), guiones bajos dentro de identificadores
# (variable_nombre) ni asteriscos sueltos de una multiplicación (2 * 3).
_RE_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
_RE_HEADER = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_RE_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_RE_HR = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)
_RE_LIST_BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", re.MULTILINE)
_RE_BOLD_STAR = re.compile(r"\*\*(\S(?:[^\n]*?\S)?)\*\*")
_RE_BOLD_UNDER = re.compile(r"__(\S(?:[^\n]*?\S)?)__")
_RE_ITALIC_STAR = re.compile(r"(?<!\*)\*(?!\*)(\S(?:[^*\n]*?\S)?)\*(?!\*)")
_RE_ITALIC_UNDER = re.compile(r"(?<!\w)_(?!_)(\S(?:[^_\n]*?\S)?)_(?!_)(?!\w)")


def strip_markdown_para_voz(texto: str) -> str:
    """Convierte texto en Markdown a texto plano apto para TTS: quita **negrita**,
    _cursiva_, encabezados `#`, código ```bloques```/`inline`, enlaces
    `[texto](url)` (se queda solo con el texto) y viñetas de lista (`- `/`* `/`1. `),
    sustituyendo los saltos de línea restantes por una pausa hablada (". ").
    No toca puntuación normal del texto (guiones de palabras compuestas, guiones
    bajos de identificadores, asteriscos de una multiplicación). Solo afecta al
    audio: la copia visual del mensaje en el panel de chat no pasa por aquí."""
    if not texto:
        return texto
    t = texto
    t = _RE_CODE_FENCE.sub(lambda m: m.group(1), t)
    t = _RE_INLINE_CODE.sub(lambda m: m.group(1), t)
    t = _RE_LINK.sub(lambda m: m.group(1), t)
    t = _RE_HEADER.sub("", t)
    t = _RE_BLOCKQUOTE.sub("", t)
    t = _RE_HR.sub("", t)
    t = _RE_LIST_BULLET.sub("", t)
    t = _RE_BOLD_STAR.sub(lambda m: m.group(1), t)
    t = _RE_BOLD_UNDER.sub(lambda m: m.group(1), t)
    t = _RE_ITALIC_STAR.sub(lambda m: m.group(1), t)
    t = _RE_ITALIC_UNDER.sub(lambda m: m.group(1), t)
    t = re.sub(r"[ \t]*\n[ \t]*", ". ", t)
    t = re.sub(r"\.(?:\s*\.)+", ".", t)
    t = re.sub(r"([,:;!?])\.", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"^[ \t.]+", "", t)
    return t.strip()


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
            tts.decir(strip_markdown_para_voz(texto))
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
