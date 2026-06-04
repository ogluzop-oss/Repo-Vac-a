"""
SOMA TTS — Neural Text-to-Speech for Smart Manager AI.

Voice engine: Microsoft Edge TTS (es-ES-ElviraNeural)
  – Same neural model as Azure Cognitive Services / Microsoft Edge browser.
  – Sounds genuinely human; no API key required; requires internet.
  – Falls back to pyttsx3 SAPI5 if edge-tts or pygame are unavailable.

Playback: pygame.mixer
  – Handles MP3 natively on Windows without extra codecs.
  – stop() works reliably mid-playback (used for click-to-cancel).

Threading model: ONE persistent background thread ("SomaTTSThread") owns
  both the asyncio event loop and pygame.mixer.  Text is sent via queue.
  This avoids COM STA threading issues that break pyttsx3 on second calls.
"""

import logging
import os
import queue
import random
import tempfile
import threading

logger = logging.getLogger("soma.tts")

# ── Neural voice configuration ─────────────────────────────────────────────────
_VOICE        = "es-ES-ElviraNeural"   # Spain Spanish, female, natural (defecto)
_RATE         = "-8%"                  # slightly slower → more natural pacing
_PITCH        = "+0Hz"
_VOLUME       = "+0%"

# Voz neuronal edge-tts por idioma → SOMA habla con una voz adecuada al idioma
# activo. Si el idioma no está en el mapa, se usa _VOICE (español).
_VOICES_EDGE = {
    "es": "es-ES-ElviraNeural",
    "en": "en-US-AriaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "hi": "hi-IN-SwaraNeural",
    "ar": "ar-SA-ZariyahNeural",
    "pt": "pt-PT-RaquelNeural",
    "fr": "fr-FR-DeniseNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "ko": "ko-KR-SunHiNeural",
    "tr": "tr-TR-EmelNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-ZofiaNeural",
    "uk": "uk-UA-PolinaNeural",
    "id": "id-ID-GadisNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "th": "th-TH-PremwadeeNeural",
    "sv": "sv-SE-SofieNeural",
}


def _voz_actual():
    """Devuelve la voz neuronal edge-tts del idioma activo de la aplicación."""
    try:
        from src.utils import i18n
        return _VOICES_EDGE.get(i18n.current_language(), _VOICE)
    except Exception:
        return _VOICE

# ── Confirmation phrases ───────────────────────────────────────────────────────
FRASES_ACTIVACION = [
    "¿Qué necesitas?",
    "¿En qué puedo ayudarte?",
    "Dime.",
    "Te escucho.",
    "A tus órdenes.",
    "¿Qué puedo hacer por ti?",
    "Aquí estoy.",
    "¿Cómo puedo ayudarte?",
    "Dígame.",
    "Listo, ¿qué necesitas?",
    "¿En qué te ayudo?",
    "A tu disposición.",
    "Adelante.",
    "¿Qué quieres abrir?",
    "Estoy contigo.",
    "¿Sí?",
    "Soy todo oídos.",
    "¿Qué necesitas gestionar?",
]

_STOP_SENTINEL = object()


class SomaTTS:
    """Thread-safe neural TTS with click-to-cancel support."""

    def __init__(self):
        self._disponible   = False
        self._hablando     = False
        self._ultima_frase = ""
        self._stop_flag    = threading.Event()
        self._queue: queue.Queue = queue.Queue(maxsize=2)
        self._running      = True
        self._mixer        = None   # pygame.mixer reference
        self._ready        = threading.Event()

        self._thread = threading.Thread(
            target=self._tts_loop, daemon=True, name="SomaTTSThread"
        )
        self._thread.start()
        # Wait for engine init before first use (max 6s)
        self._ready.wait(timeout=6.0)

    # ── Background thread ─────────────────────────────────────────────────────
    def _tts_loop(self):
        """Persistent thread: owns asyncio loop + pygame, processes the queue."""
        # 1. Try edge-tts + pygame (neural voice)
        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=2048)
            self._mixer = pygame.mixer
            import edge_tts  # noqa — just verify importability
            self._disponible = True
            self._engine_type = "edge-tts"
            logger.info("SOMA TTS: ElviraNeural (edge-tts + pygame) listo.")
        except Exception as e:
            logger.warning(f"SOMA: edge-tts/pygame no disponible ({e}), probando pyttsx3...")
            # 2. Fallback: pyttsx3 SAPI5
            try:
                import pyttsx3
                eng = pyttsx3.init()
                voices = eng.getProperty("voices")
                for v in voices:
                    vid   = (v.id   or "").lower()
                    vname = (v.name or "").lower()
                    if any(k in vid or k in vname
                           for k in ("spanish", "es-", "zira", "helena", "sabina")):
                        eng.setProperty("voice", v.id)
                        break
                eng.setProperty("rate", 165)
                eng.setProperty("volume", 0.88)
                self._pyttsx3_engine = eng
                self._disponible = True
                self._engine_type = "pyttsx3"
                logger.info("SOMA TTS: pyttsx3 SAPI5 (fallback) listo.")
            except Exception as e2:
                logger.warning(f"SOMA TTS no disponible: {e2}")
                self._ready.set()
                return

        self._ready.set()

        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is _STOP_SENTINEL:
                self._queue.task_done()
                break

            # Cada item es (texto, voz). La voz va ligada al idioma real del
            # texto para que nunca una voz extranjera lea texto en español.
            try:
                texto_item, voz_item = item
            except Exception:
                texto_item, voz_item = item, _VOICE

            self._stop_flag.clear()
            self._hablando = True
            try:
                if self._engine_type == "edge-tts":
                    self._hablar_edge(texto_item, voz_item)
                else:
                    self._hablar_pyttsx3(texto_item)
            except Exception as e:
                logger.error(f"TTS loop error: {e}")
            finally:
                self._hablando = False
                self._queue.task_done()

    # ── edge-tts playback ─────────────────────────────────────────────────────
    def _hablar_edge(self, texto: str, voz: str = _VOICE):
        import asyncio

        tmp = tempfile.mktemp(suffix=".mp3")
        try:
            # Generate audio (neural, via Microsoft's endpoint)
            async def _gen():
                import edge_tts
                comm = edge_tts.Communicate(
                    texto, voz, rate=_RATE, pitch=_PITCH, volume=_VOLUME
                )
                await comm.save(tmp)

            asyncio.run(_gen())

            if self._stop_flag.is_set():
                return

            # Play with pygame.mixer
            self._mixer.music.load(tmp)
            self._mixer.music.play()
            while self._mixer.music.get_busy() and not self._stop_flag.is_set():
                import time
                time.sleep(0.04)
            self._mixer.music.stop()
            self._mixer.music.unload()

        except Exception as e:
            logger.error(f"edge-tts speak error: {e}")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    # ── pyttsx3 fallback ──────────────────────────────────────────────────────
    def _hablar_pyttsx3(self, texto: str):
        try:
            self._pyttsx3_engine.say(texto)
            self._pyttsx3_engine.runAndWait()
        except Exception as e:
            logger.error(f"pyttsx3 speak error: {e}")

    # ── Public interface ───────────────────────────────────────────────────────
    @property
    def disponible(self) -> bool:
        return self._disponible

    @property
    def hablando(self) -> bool:
        return self._hablando

    def _localizar(self, texto: str):
        """Traduce el texto de SOMA al idioma activo (vía IA, dominio 'soma') y
        devuelve (texto_final, voz). Si no hay traducción disponible (sin
        proveedor de IA o idioma español), mantiene el texto en español con la
        voz española, evitando que una voz extranjera lea texto en español."""
        try:
            from src.utils import i18n
            lang = i18n.current_language()
            if lang == "es":
                return texto, _VOICES_EDGE.get("es", _VOICE)
            traducido = i18n.ai_translate(texto, lang, dominio="soma")
            if traducido and traducido != texto:
                return traducido, _VOICES_EDGE.get(lang, _VOICE)
            return texto, _VOICES_EDGE.get("es", _VOICE)
        except Exception:
            return texto, _VOICE

    def decir(self, texto: str):
        """Queue text for neural speech. Cancels any in-progress speech first.
        El texto se traduce al idioma activo (Nivel 2) y la voz se ajusta a ese
        idioma; sin traducción disponible, se mantiene en español."""
        if not self._disponible:
            return
        texto_final, voz = self._localizar(texto)
        if self._hablando:
            self.detener()
        # Drain stale queued messages
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        try:
            self._queue.put_nowait((texto_final, voz))
        except queue.Full:
            pass

    def detener(self):
        """Interrupt speech immediately (click-to-cancel)."""
        if not self._disponible:
            return
        self._stop_flag.set()
        try:
            if self._engine_type == "edge-tts" and self._mixer:
                self._mixer.music.stop()
            elif self._engine_type == "pyttsx3":
                self._pyttsx3_engine.stop()
        except Exception as e:
            logger.warning(f"TTS detener: {e}")
        self._hablando = False
        logger.debug("SOMA TTS: detenido.")

    def confirmar_activacion(self):
        """Random, non-repeating confirmation phrase."""
        candidatos = [f for f in FRASES_ACTIVACION if f != self._ultima_frase]
        frase = random.choice(candidatos)
        self._ultima_frase = frase
        self.decir(frase)

    def decir_error(self):
        self.decir(random.choice([
            "No he podido entenderte. Inténtalo de nuevo.",
            "No te he entendido bien. ¿Puedes repetirlo?",
            "No he captado el comando. Dilo de nuevo, por favor.",
        ]))

    def decir_desconocido(self, _texto: str = ""):
        self.decir(random.choice([
            "No reconozco ese comando. Di Ey SOMA ayuda para ver qué puedo hacer.",
            "No he encontrado esa función. Prueba decir Ey SOMA ayuda.",
            "No sé cómo ejecutar eso. Di Ey SOMA ayuda para más opciones.",
        ]))

    def shutdown(self):
        """Clean shutdown — stops the background thread."""
        self._running = False
        self.detener()
        try:
            self._queue.put_nowait(_STOP_SENTINEL)
        except queue.Full:
            pass
