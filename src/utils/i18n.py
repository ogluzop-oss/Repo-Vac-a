"""
Sistema de internacionalización (i18n) global de Smart Manager AI.

Arquitectura híbrida:

  Nivel 1 — Traducción local (este módulo):
      Textos fijos de la interfaz almacenados en archivos JSON por idioma
      (assets/lang/<codigo>.json). Acceso instantáneo vía `tr("clave.anidada")`.

  Nivel 2 — Traducción inteligente (IA):
      Contenido dinámico (contratos, nóminas, facturas, respuestas de SOMA,
      observaciones...) se traduce con `ai_translate(texto, idioma, dominio)`.
      El proveedor de IA es enchufable (`set_ai_provider`) y se cachea; si no
      hay proveedor configurado, devuelve el texto original (degradación
      elegante, sin romper nada).

Características:
  - Cambio de idioma EN CALIENTE: al cambiar de idioma se emite la señal
    `gestor.idioma_cambiado`; cada ventana se reconecta y se re-traduce sin
    reiniciar la app.
  - Persistencia: el idioma se guarda en disco y se recupera al arrancar.
  - Soporte RTL (árabe, etc.) vía `is_rtl()`.
  - Metadatos por idioma: nombre nativo, bandera, voz TTS y código STT para
    que SOMA (reconocimiento + síntesis de voz) se adapte automáticamente.
"""

import json
import logging
import os

try:
    from PyQt6.QtCore import QObject, pyqtSignal
except Exception:  # pragma: no cover - permite importar sin Qt (tests/CLI)
    QObject = object

    def pyqtSignal(*_a, **_k):  # type: ignore
        return None

logger = logging.getLogger("i18n")

# ============================================================
# RUTAS
# ============================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))  # src/utils -> raíz
_LANG_DIR = os.path.join(_PROJECT_ROOT, "assets", "lang")
_SETTINGS_PATH = os.path.join(_PROJECT_ROOT, "documentos", "app_settings.json")

_DEFAULT_LANG = "es"
_FALLBACK_LANG = "en"


# ============================================================
# IDIOMAS SOPORTADOS (los 20 más hablados; ampliable sin tocar la lógica)
# code -> {native, flag, rtl, tts (locale voz), stt (locale reconocimiento)}
# ============================================================
LANGUAGES = {
    "es": {"native": "Español",     "flag": "🇪🇸", "rtl": False, "tts": "es-ES", "stt": "es-ES"},
    "en": {"native": "English",     "flag": "🇬🇧", "rtl": False, "tts": "en-US", "stt": "en-US"},
    "zh": {"native": "中文",         "flag": "🇨🇳", "rtl": False, "tts": "zh-CN", "stt": "zh-CN"},
    "hi": {"native": "हिन्दी",        "flag": "🇮🇳", "rtl": False, "tts": "hi-IN", "stt": "hi-IN"},
    "ar": {"native": "العربية",      "flag": "🇸🇦", "rtl": True,  "tts": "ar-SA", "stt": "ar-SA"},
    "pt": {"native": "Português",    "flag": "🇵🇹", "rtl": False, "tts": "pt-PT", "stt": "pt-PT"},
    "fr": {"native": "Français",     "flag": "🇫🇷", "rtl": False, "tts": "fr-FR", "stt": "fr-FR"},
    "ru": {"native": "Русский",      "flag": "🇷🇺", "rtl": False, "tts": "ru-RU", "stt": "ru-RU"},
    "ja": {"native": "日本語",       "flag": "🇯🇵", "rtl": False, "tts": "ja-JP", "stt": "ja-JP"},
    "de": {"native": "Deutsch",      "flag": "🇩🇪", "rtl": False, "tts": "de-DE", "stt": "de-DE"},
    "it": {"native": "Italiano",     "flag": "🇮🇹", "rtl": False, "tts": "it-IT", "stt": "it-IT"},
    "ko": {"native": "한국어",       "flag": "🇰🇷", "rtl": False, "tts": "ko-KR", "stt": "ko-KR"},
    "tr": {"native": "Türkçe",       "flag": "🇹🇷", "rtl": False, "tts": "tr-TR", "stt": "tr-TR"},
    "nl": {"native": "Nederlands",   "flag": "🇳🇱", "rtl": False, "tts": "nl-NL", "stt": "nl-NL"},
    "pl": {"native": "Polski",       "flag": "🇵🇱", "rtl": False, "tts": "pl-PL", "stt": "pl-PL"},
    "uk": {"native": "Українська",   "flag": "🇺🇦", "rtl": False, "tts": "uk-UA", "stt": "uk-UA"},
    "id": {"native": "Indonesia",    "flag": "🇮🇩", "rtl": False, "tts": "id-ID", "stt": "id-ID"},
    "vi": {"native": "Tiếng Việt",   "flag": "🇻🇳", "rtl": False, "tts": "vi-VN", "stt": "vi-VN"},
    "th": {"native": "ไทย",          "flag": "🇹🇭", "rtl": False, "tts": "th-TH", "stt": "th-TH"},
    "sv": {"native": "Svenska",      "flag": "🇸🇪", "rtl": False, "tts": "sv-SE", "stt": "sv-SE"},
}


# ============================================================
# GESTOR DE TRADUCCIÓN (singleton)
# ============================================================
class _GestorI18n(QObject):
    # Emitida al cambiar de idioma (con el nuevo código). Cada ventana se
    # conecta a esta señal para re-traducirse en caliente.
    idioma_cambiado = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lang = _DEFAULT_LANG
        self._catalogo = {}
        self._fallback = self._cargar_catalogo(_FALLBACK_LANG)
        self._cache = {_FALLBACK_LANG: self._fallback}
        guardado = self._leer_preferencia()
        self.set_language(guardado or _DEFAULT_LANG, emitir=False)

    # ---- carga de catálogos ----
    def _ruta_catalogo(self, code):
        return os.path.join(_LANG_DIR, f"{code}.json")

    def _cargar_catalogo(self, code):
        if hasattr(self, "_cache") and code in self._cache:
            return self._cache[code]
        data = {}
        ruta = self._ruta_catalogo(code)
        try:
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8") as f:
                    data = json.load(f)
        except Exception as e:
            logger.warning("No se pudo cargar el idioma '%s': %s", code, e)
        return data

    # ---- API pública ----
    def set_language(self, code, emitir=True):
        if code not in LANGUAGES:
            code = _DEFAULT_LANG
        self._lang = code
        if code not in self._cache:
            self._cache[code] = self._cargar_catalogo(code)
        self._catalogo = self._cache[code]
        self._guardar_preferencia(code)
        if emitir:
            try:
                self.idioma_cambiado.emit(code)
            except Exception:
                pass

    @property
    def lang(self):
        return self._lang

    def info(self, code=None):
        return LANGUAGES.get(code or self._lang, {})

    def is_rtl(self, code=None):
        return bool(self.info(code).get("rtl", False))

    def tts_voice(self, code=None):
        return self.info(code).get("tts")

    def stt_code(self, code=None):
        return self.info(code).get("stt")

    def tr(self, key, default=None, **kwargs):
        """Devuelve el texto traducido para `key` (notación con puntos:
        'login.user_label'). Cae a inglés y luego a `default`/`key`.
        Admite formato: tr('saludo', nombre='Ana') con '{nombre}' en el texto."""
        val = self._lookup(self._catalogo, key)
        if val is None:
            val = self._lookup(self._fallback, key)
        if val is None:
            val = default if default is not None else key
        if kwargs and isinstance(val, str):
            try:
                val = val.format(**kwargs)
            except Exception:
                pass
        return val

    @staticmethod
    def _lookup(catalogo, key):
        cur = catalogo
        for parte in key.split("."):
            if isinstance(cur, dict) and parte in cur:
                cur = cur[parte]
            else:
                return None
        return cur if isinstance(cur, str) else None

    # ---- persistencia ----
    def _leer_preferencia(self):
        try:
            if os.path.exists(_SETTINGS_PATH):
                with open(_SETTINGS_PATH, encoding="utf-8") as f:
                    return (json.load(f) or {}).get("idioma")
        except Exception:
            pass
        return None

    def _guardar_preferencia(self, code):
        try:
            data = {}
            if os.path.exists(_SETTINGS_PATH):
                with open(_SETTINGS_PATH, encoding="utf-8") as f:
                    data = json.load(f) or {}
            data["idioma"] = code
            os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
            with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("No se pudo guardar la preferencia de idioma: %s", e)


_gestor = None


def gestor():
    """Devuelve el gestor i18n (singleton)."""
    global _gestor
    if _gestor is None:
        _gestor = _GestorI18n()
    return _gestor


# ---- atajos a nivel de módulo ----
def tr(key, default=None, **kwargs):
    return gestor().tr(key, default, **kwargs)


def set_language(code):
    gestor().set_language(code)


def current_language():
    return gestor().lang


def is_rtl():
    return gestor().is_rtl()


def aplicar_direccion(widget):
    """Aplica al widget la dirección de escritura del idioma activo (RTL/LTR)."""
    try:
        from PyQt6.QtCore import Qt
        widget.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl()
            else Qt.LayoutDirection.LeftToRight
        )
    except Exception:
        pass


def conectar_retraduccion(widget, retraducir_fn):
    """Conecta `widget` al cambio de idioma global: cuando el idioma cambia,
    llama a `retraducir_fn()` (para actualizar textos) y aplica la dirección
    RTL/LTR. También aplica la dirección de inmediato. Devuelve el slot para
    poder desconectarlo si hiciera falta.

    Uso típico en una ventana:
        i18n.conectar_retraduccion(self, self._retraducir)
    """
    def _slot(*_):
        try:
            retraducir_fn()
        except Exception:
            pass
        aplicar_direccion(widget)
    try:
        gestor().idioma_cambiado.connect(_slot)
    except Exception:
        pass
    aplicar_direccion(widget)
    return _slot


# ============================================================
# NIVEL 2 — TRADUCCIÓN POR IA (contenido dinámico)
# ============================================================
_ai_provider = None
_ai_cache = {}


def set_ai_provider(fn):
    """Registra el proveedor de traducción por IA.

    `fn(texto:str, idioma_destino:str, dominio:str|None) -> str`

    `dominio` orienta la terminología: 'fiscal', 'laboral', 'juridico',
    'logistico', 'tpv', 'soma'... El proveedor real (LLM) se enchufa aquí desde
    la capa de integración (p. ej. usando la API de IA del sistema), sin acoplar
    este módulo a ningún servicio concreto.
    """
    global _ai_provider
    _ai_provider = fn


def ai_translate(texto, idioma=None, dominio=None):
    """Traduce contenido dinámico al idioma activo (o al indicado) usando el
    proveedor de IA registrado, manteniendo contexto y terminología del
    `dominio`. Cachea resultados. Si no hay proveedor o el idioma destino es el
    de origen del texto, devuelve el texto original (degradación elegante)."""
    if not texto:
        return texto
    destino = idioma or current_language()
    clave = (destino, dominio or "", texto)
    if clave in _ai_cache:
        return _ai_cache[clave]
    if _ai_provider is None:
        return texto
    try:
        resultado = _ai_provider(texto, destino, dominio)
        if resultado:
            _ai_cache[clave] = resultado
            return resultado
    except Exception as e:
        logger.debug("ai_translate falló (%s); se devuelve original: %s", destino, e)
    return texto
