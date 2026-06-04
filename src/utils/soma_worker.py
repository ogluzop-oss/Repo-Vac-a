"""
SOMA Voice Worker — Smart Manager AI
Continuously listens for the wake phrase "Ey SOMA" and routes commands.

Design notes (latency + reliability):
  * PERSISTENT microphone: the mic stream is opened ONCE and reused across
    cycles. Reopening per-cycle cost ~300-500 ms on Windows AND clipped the
    start of the user's speech (a major cause of missed "Ey SOMA"). The TTS
    now plays through pygame (separate output device), so it no longer resets
    the SR input stream — making a persistent mic safe.
  * FUZZY wake-word: Google STT routinely mis-transcribes "SOMA" (zona, goma,
    toma, soa...). We match the first tokens against a set of accepted variants
    using difflib ratio, so detection no longer depends on a perfect transcript.
  * Fast end-of-speech: pause_threshold lowered to 0.45 s so a short "Ey SOMA"
    is finalised quickly instead of waiting ~0.8 s of silence.
"""

from __future__ import annotations

import difflib
import logging
import time

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("soma.worker")

# ── States ────────────────────────────────────────────────────────────────────
ESTADO_INACTIVO   = "inactivo"
ESTADO_ESCUCHANDO = "escuchando"
ESTADO_ACTIVADO   = "activado"
ESTADO_PROCESANDO = "procesando"
ESTADO_ERROR      = "error"

# ── Wake word ──────────────────────────────────────────────────────────────────
# Greeting prefixes that may precede the name ("Ey SOMA", "Oye SOMA"...).
# Añadidos EL/E/EX a partir de transcripciones reales: Google STT convierte el
# "Ey" de "Ey SOMA" en "EL", "E" o "EX" con frecuencia.
_PREFIJOS = ("EY", "HEY", "OYE", "EI", "OK", "HOLA", "VALE", "OYES", "EH",
             "EL", "E", "EX")

# STRICT name set: a bare token equal to one of these counts as the wake word
# on its own. Kept tight so common Spanish words never cause false activations.
_NOMBRE_ESTRICTO = frozenset((
    "SOMA", "SOMMA", "SOMAA", "SOMAH", "SOA", "SOMÁ",
))

# LOOSE name set: common mis-transcriptions of "SOMA". Only accepted when
# immediately preceded by a greeting prefix (so "Ey zona" wakes, but a bare
# "toma"/"suma"/"coma"/"zona" said during normal work does NOT).
_NOMBRE_LAXO = frozenset((
    "ZONA", "GOMA", "TOMA", "COMA", "SUMA", "SOPA", "SOMO",
    "SONA", "SONIA", "ROMA", "SOLA", "ESOMA", "SOBA",
    # Fragmentos reales en los que Google parte "SOMA" al transcribir "Ey SOMA":
    # "EL SO", "HEY SO", "E HIZO", "E ISO"... Solo cuentan precedidos de prefijo,
    # así que un "so"/"hizo" sueltos en una frase normal NO activan a SOMA.
    "SO", "HIZO", "ISO", "HISO", "SOMABA", "SOMI",
))
# Strict fuzzy threshold vs "SOMA"/"SOMMA" only (SOMMA=0.80, SUMA=0.75<thr).
_FUZZY_ESTRICTO = 0.80


# Seconds to wait, after a bare wake word, for SOMA's greeting to finish
# playing before re-opening the mic (prevents SOMA hearing its own voice).
_TTS_GREETING_GUARD_S = 1.6

# Ventana para decir el SEGUNDO comando tras "Ey SOMA" (el primero). Si en este
# tiempo el usuario no dice nada, SOMA responde solo al primero (el saludo).
_VENTANA_SEGUNDO_COMANDO_S = 2.5


def _norm(s: str) -> str:
    return s.upper().strip().replace(",", " ").replace(".", " ")


def _es_nombre_estricto(tok: str) -> bool:
    """Bare-token name match: exact strict set OR very-close fuzzy to SOMA."""
    if not tok:
        return False
    if tok in _NOMBRE_ESTRICTO:
        return True
    best = max(
        difflib.SequenceMatcher(None, tok, v).ratio() for v in ("SOMA", "SOMMA")
    )
    return best >= _FUZZY_ESTRICTO


def _es_nombre_laxo(tok: str) -> bool:
    """Loose name match — only valid right after a greeting prefix."""
    return tok in _NOMBRE_LAXO or _es_nombre_estricto(tok)


def detectar_wake(texto: str) -> tuple[bool, str]:
    """
    Detects the wake word anywhere in the transcript.
    Returns (found, comando_inline): comando_inline is whatever follows the
    wake word in the same phrase ('' if only the wake word was said).

    Rules (tuned to avoid false activations in a noisy retail floor):
      * "<prefix> <name>"  → prefix in _PREFIJOS, name in loose set  → wake.
      * "<strict-name>"     → bare strict name anywhere               → wake.
    """
    palabras = _norm(texto).split()
    if not palabras:
        return False, ""

    for i, tok in enumerate(palabras):
        # Form 1: prefix + (loose) name  →  "EY SOMA", "OYE ZONA"
        if tok in _PREFIJOS and i + 1 < len(palabras) and _es_nombre_laxo(palabras[i + 1]):
            return True, " ".join(palabras[i + 2:]).strip()
        # Form 2: bare strict name  →  "SOMA ..."
        if _es_nombre_estricto(tok):
            return True, " ".join(palabras[i + 1:]).strip()
    return False, ""


class SomaWorker(QObject):
    """Core voice recognition loop (runs inside a QThread)."""

    estado_cambiado   = pyqtSignal(str)
    soma_activado     = pyqtSignal(bool)   # True → inline command follows immediately
    comando_detectado = pyqtSignal(str)
    error_ocurrido    = pyqtSignal(str)

    # Energy-threshold band for the dynamic detector. Keeps sensitivity stable
    # over a long session: never so low it triggers on background noise (the
    # "umbral=49" bug), never so high it ignores normal speech.
    # Banda algo más sensible que antes: el síntoma "no responde a Ey SOMA" suele
    # deberse a un umbral demasiado alto que no captura voz normal. Bajamos el mínimo
    # y la base (siguen MUY por encima del valor 49 que provocaba disparos por ruido).
    _ENERGY_MIN  = 130
    _ENERGY_MAX  = 600
    _ENERGY_BASE = 230

    def _clamp_threshold(self, rec):
        try:
            if rec.energy_threshold < self._ENERGY_MIN:
                rec.energy_threshold = self._ENERGY_MIN
            elif rec.energy_threshold > self._ENERGY_MAX:
                rec.energy_threshold = self._ENERGY_MAX
        except Exception:
            pass

    def __init__(self, parent=None):
        super().__init__(parent)
        self._activo     = False
        self._disponible = False
        self._mic        = None
        self._debug      = False
        self._check_deps()

    def _check_deps(self):
        # IMPORTANTE: solo comprobamos DISPONIBILIDAD (find_spec), sin importar de
        # verdad speech_recognition aquí. Este método corre en el hilo PRINCIPAL al
        # crear el worker; importar speech_recognition+pyaudio tarda 1-3 s y
        # CONGELABA el menú nada más hacer login. El import real ocurre en start(),
        # ya dentro del hilo secundario.
        import importlib.util
        if importlib.util.find_spec("speech_recognition") is not None:
            self._disponible = True
            logger.info("SOMA: speech_recognition disponible.")
        else:
            logger.warning("SOMA: speech_recognition no instalado.")

    @property
    def disponible(self) -> bool:
        return self._disponible

    def set_debug(self, on: bool):
        self._debug = bool(on)

    # ── Main loop ─────────────────────────────────────────────────────────────
    def start(self):
        if not self._disponible:
            self.error_ocurrido.emit(
                "SOMA no disponible: instala SpeechRecognition y pyaudio."
            )
            return

        import speech_recognition as sr

        self._activo = True
        rec = sr.Recognizer()
        # DYNAMIC threshold so SOMA keeps adapting to ambient noise across a long
        # work session (a fixed low threshold like 49 caused it to treat rising
        # background noise as speech, flooding the loop with garbage STT calls and
        # missing the real "Ey SOMA"). We clamp it to [_ENERGY_MIN, _ENERGY_MAX]
        # every cycle so it never collapses to a hyper-sensitive value nor climbs
        # so high that quiet speech is ignored.
        rec.dynamic_energy_threshold = True
        rec.energy_threshold         = self._ENERGY_BASE
        rec.pause_threshold          = 0.85    # un poco más alto: da tiempo a oír el comando entero
        rec.non_speaking_duration    = 0.35
        rec.phrase_threshold         = 0.20

        # Open the microphone ONCE and keep it open (low latency, no clipped starts)
        try:
            self._mic = sr.Microphone()
            with self._mic as source:
                logger.info("SOMA: calibrando ruido ambiente...")
                # Calibración más corta → SOMA empieza a escuchar antes (menos
                # "Ey SOMA" perdidos durante el arranque).
                rec.adjust_for_ambient_noise(source, duration=0.6)
                self._clamp_threshold(rec)
        except Exception as e:
            msg = f"No se pudo abrir el micrófono: {e}"
            logger.error(msg)
            self.error_ocurrido.emit(msg)
            self.estado_cambiado.emit(ESTADO_ERROR)
            return

        logger.info(
            f"SOMA activo (umbral={rec.energy_threshold:.0f}). Di 'Ey SOMA'."
        )
        self.estado_cambiado.emit(ESTADO_ESCUCHANDO)

        while self._activo:
            try:
                self._ciclo(rec)
            except Exception as e:
                logger.error(f"SOMA ciclo error: {e}")
                time.sleep(0.3)

        try:
            self._mic = None
        except Exception:
            pass
        logger.info("SOMA: bucle detenido.")
        self.estado_cambiado.emit(ESTADO_INACTIVO)

    def _ciclo(self, rec):
        import speech_recognition as sr

        self.estado_cambiado.emit(ESTADO_ESCUCHANDO)
        t_listen = time.time()
        try:
            with self._mic as source:
                audio = rec.listen(source, timeout=5, phrase_time_limit=7)
        except sr.WaitTimeoutError:
            self._clamp_threshold(rec)  # keep band tight even on idle cycles
            return
        except Exception as e:
            logger.error(f"SOMA mic listen error: {e}")
            time.sleep(0.3)
            return
        # The dynamic detector adjusts energy_threshold after each listen;
        # re-clamp so it can't drift out of the usable band over time.
        self._clamp_threshold(rec)

        self.estado_cambiado.emit(ESTADO_PROCESANDO)
        alternativas = self._transcribir(rec, audio)
        if not alternativas:
            self.estado_cambiado.emit(ESTADO_ESCUCHANDO)
            return

        dt = (time.time() - t_listen) * 1000
        texto = alternativas[0]
        if self._debug:
            logger.info(f"[SOMA-DEBUG] STT={alternativas!r}  ({dt:.0f} ms)")
        else:
            logger.debug(f"STT: {alternativas!r} ({dt:.0f} ms)")

        # Wake word: se busca en TODAS las hipótesis (la correcta puede no ser la
        # primera). Se recopilan los comandos en línea (lo que sigue a la wake) de
        # cada hipótesis que la contenga, para luego elegir el que sea un comando válido.
        found = False
        candidatos_inline: list[str] = []
        for alt in alternativas:
            f, c = detectar_wake(alt)
            if f:
                found = True
                if c:
                    candidatos_inline.append(c)
        if not found:
            # Diagnóstico: deja constancia de lo que oyó cuando NO hubo wake.
            logger.info("SOMA oyó (sin wake): '%s' (%.0f ms)", texto, dt)
            self.estado_cambiado.emit(ESTADO_ESCUCHANDO)
            return

        # Wake word detected
        self.estado_cambiado.emit(ESTADO_ACTIVADO)
        # Solo lo tratamos como "comando en la misma frase" si ese comando es
        # VÁLIDO. Si la voz se cortó y quedó incompleto ("abre" sin módulo,
        # "más abre"...), lo tratamos como wake a secas: SOMA saluda y escucha el
        # comando completo, en vez de responder "no reconozco".
        mejor_inline = self._elegir_mejor_comando(candidatos_inline) if candidatos_inline else ""
        inline_valido = self._es_comando_valido(mejor_inline)
        self.soma_activado.emit(inline_valido)
        if self._debug:
            logger.info(f"[SOMA-DEBUG] WAKE OK  inline_valido={inline_valido}  cands={candidatos_inline!r}")
        else:
            logger.info(f"SOMA activado. inline={inline_valido}")

        if inline_valido:
            # Command in the same phrase → fire immediately (the action message
            # IS the acknowledgement; main.py cancels any greeting TTS).
            self.comando_detectado.emit(mejor_inline)
            return

        # Bare wake word → main.py plays a short greeting ("¿Qué necesitas?").
        # CRITICAL: wait for that greeting to finish before listening, otherwise
        # the mic hears SOMA's own voice through the speakers, transcribes it,
        # and mis-fires as 'ayuda' / 'desconocido'. The greeting is ~1.2 s; we
        # wait a bit more to be safe. The parser also ignores greeting echoes
        # (_es_eco_saludo) as a second line of defence.
        time.sleep(_TTS_GREETING_GUARD_S)

        # Ahora capturamos el comando de seguimiento. Espera hasta 2,5 s a que el
        # usuario empiece a hablar; si no, solo responde al primero (el saludo).
        try:
            with self._mic as source:
                audio2 = rec.listen(
                    source,
                    timeout=_VENTANA_SEGUNDO_COMANDO_S,
                    phrase_time_limit=7,
                )
        except sr.WaitTimeoutError:
            self.estado_cambiado.emit(ESTADO_ESCUCHANDO)
            return
        except Exception:
            self.estado_cambiado.emit(ESTADO_ESCUCHANDO)
            return

        self.estado_cambiado.emit(ESTADO_PROCESANDO)
        alternativas2 = self._transcribir(rec, audio2)
        if alternativas2:
            # Cada hipótesis puede traer otra vez la wake; la quitamos. Después
            # elegimos la que sea un comando válido.
            cands2: list[str] = []
            for alt in alternativas2:
                f2, inner = detectar_wake(alt)
                cands2.append(inner if (f2 and inner) else alt)
            cmd = self._elegir_mejor_comando(cands2)
            if self._debug:
                logger.info(f"[SOMA-DEBUG] FOLLOW-UP cands={cands2!r} -> '{cmd}'")
            self.comando_detectado.emit(cmd)
        else:
            self.estado_cambiado.emit(ESTADO_ESCUCHANDO)

    def stop(self):
        self._activo = False

    # ── STT ───────────────────────────────────────────────────────────────────
    def _idioma_stt(self) -> str:
        """Locale de reconocimiento de voz según el idioma activo de la app."""
        try:
            from src.utils import i18n
            return i18n.gestor().stt_code() or "es-ES"
        except Exception:
            return "es-ES"

    def _transcribir(self, rec, audio) -> list[str]:
        """Devuelve VARIAS hipótesis de Google (no solo la mejor), en orden de
        confianza. Probarlas todas mejora muchísimo el reconocimiento: la frase
        correcta suele estar entre las alternativas aunque la primera sea errónea
        (p. ej. 'abre ubicación' → top 'MAL', alternativa 'ABRE UBICACIÓN')."""
        import speech_recognition as sr
        idioma = self._idioma_stt()
        try:
            res = rec.recognize_google(audio, language=idioma, show_all=True)
            if isinstance(res, dict):
                vistos: set[str] = set()
                out: list[str] = []
                for a in res.get("alternative", []):
                    t = (a.get("transcript") or "").upper().strip()
                    if t and t not in vistos:
                        vistos.add(t)
                        out.append(t)
                return out
            if isinstance(res, str) and res.strip():
                return [res.upper().strip()]
            return []
        except sr.UnknownValueError:
            return []
        except sr.RequestError:
            logger.debug("Google STT no disponible (sin red).")
        try:
            s = rec.recognize_sphinx(audio, language=idioma).upper().strip()
            return [s] if s else []
        except Exception:
            pass
        return []

    def _elegir_mejor_comando(self, candidatos: list[str]) -> str:
        """De varias hipótesis de comando, elige la mejor por PUNTUACIÓN:
          · acción ESPECÍFICA (abrir/cerrar/ayuda-de-módulo/consulta...) > genérica
            (ayuda general 'mostrar_ayuda'),
          · coincidencia EXACTA > DIFUSA.
        Ejemplos: 'comandos tpv' (ayuda de TPV) gana a 'comandos dpv' (ayuda
        general); 'abre ubicación' (exacta) gana a 'ábreme más' (difusa→mermas).
        Si ninguna hipótesis es válida, devuelve la primera (mayor confianza)."""
        candidatos = [c for c in candidatos if c]
        if not candidatos:
            return ""
        try:
            from src.utils.soma_engine import parsear_comando
            mejor_cand, mejor_score = None, 0
            for cand in candidatos:
                try:
                    accion, params = parsear_comando(cand)
                except Exception:
                    continue
                if accion in ("desconocido", "ignorar"):
                    continue
                especifica = accion != "mostrar_ayuda"
                exacta = not params.get("fuzzy")
                score = (4 if especifica else 1) + (1 if exacta else 0)
                if score > mejor_score:   # '>' → ante empate gana la primera (más confianza)
                    mejor_score, mejor_cand = score, cand
            if mejor_cand is not None:
                return mejor_cand
        except Exception:
            pass
        return candidatos[0]

    def _es_comando_valido(self, texto: str) -> bool:
        """True si el texto se reconoce como una acción ejecutable (no 'desconocido')."""
        if not texto:
            return False
        try:
            from src.utils.soma_engine import parsear_comando
            accion, _ = parsear_comando(texto)
            return accion not in ("desconocido", "ignorar")
        except Exception:
            return False
