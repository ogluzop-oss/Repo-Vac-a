"""
Proveedor de traducción por IA (Nivel 2) para Smart Manager AI.

Traduce el contenido DINÁMICO del sistema (contratos, nóminas, facturas,
certificados, correos, observaciones, motivos, respuestas de SOMA...) al idioma
activo, manteniendo el contexto y la terminología del DOMINIO (fiscal, laboral,
jurídico, logístico, TPV, SOMA...).

Diseño:
  - Caché persistente en disco + memoria  → cada frase se traduce UNA vez; las
    repeticiones son instantáneas y gratis.
  - Prompt orientado por dominio           → terminología empresarial correcta.
  - Backend LLM enchufable; se incluye un backend Claude (Anthropic) opcional
    que se activa si está el paquete `anthropic` y la variable de entorno
    ANTHROPIC_API_KEY. Si no hay backend, degrada con elegancia (texto original).
  - Traducción por LOTES (`traducir_lote`) → un documento entero en una llamada.

Uso:
    from src.utils import ai_translator
    ai_translator.registrar_proveedor()          # lo enchufa en i18n
    # ...y ya: i18n.ai_translate(...) y SOMA/documentos quedan multiidioma.
"""

import hashlib
import json
import logging
import os
import re
import threading

logger = logging.getLogger("ai.translator")

# Marcadores de formato {asi}. NUNCA deben traducirse (rompen .format()).
_PH = re.compile(r"\{[^{}]*\}")


def _preservar_placeholders(origen, trad):
    """Si la traducción alteró los {placeholders} (la IA a veces los traduce:
    {nombre}->{nazwa}), los restaura por posición desde el original."""
    if not trad or "{" not in (origen or ""):
        return trad
    src = _PH.findall(origen)
    if not src:
        return trad
    cur = _PH.findall(trad)
    if cur == src or len(cur) != len(src):
        return trad
    it = iter(src)
    return _PH.sub(lambda m: next(it), trad)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
_CACHE_PATH = os.path.join(_PROJECT_ROOT, "documentos", "ai_translate_cache.json")

_MODEL = os.getenv("SMART_MANAGER_TRANSLATE_MODEL", "claude-haiku-4-5-20251001")

# Nombre en inglés de cada idioma (para el prompt).
_LANG_NAMES = {
    "es": "Spanish", "en": "English", "zh": "Simplified Chinese", "hi": "Hindi",
    "ar": "Arabic", "pt": "Portuguese", "fr": "French", "ru": "Russian",
    "ja": "Japanese", "de": "German", "it": "Italian", "ko": "Korean",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian",
    "id": "Indonesian", "vi": "Vietnamese", "th": "Thai", "sv": "Swedish",
    "ca": "Catalan",
}

# Pista de terminología por dominio.
_DOMAIN_HINTS = {
    "fiscal":    "tax/accounting documents; use precise fiscal and accounting terminology.",
    "laboral":   "HR/labour documents (contracts, payslips); use correct employment-law terminology.",
    "juridico":  "legal documents; use formal legal terminology and register.",
    "logistico": "warehouse/logistics (pallets, receptions, transfers, stock).",
    "tpv":       "point-of-sale / retail checkout terminology (tickets, invoices, change).",
    "soma":      "short, natural spoken assistant phrases for a voice assistant.",
    "ui":        "concise software user-interface labels (buttons, menus, messages).",
}

_lock = threading.Lock()
_mem_cache = None  # dict cargado de disco


# ============================================================
# CACHÉ PERSISTENTE
# ============================================================
def _cargar_cache():
    global _mem_cache
    if _mem_cache is not None:
        return _mem_cache
    data = {}
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f) or {}
    except Exception as e:
        logger.debug("No se pudo leer la caché de traducción: %s", e)
    _mem_cache = data
    return _mem_cache


def _guardar_cache():
    if _mem_cache is None:
        return
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_mem_cache, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("No se pudo guardar la caché de traducción: %s", e)


def _clave(texto, idioma, dominio):
    base = f"{idioma} {dominio or ''} {texto}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


# ============================================================
# BACKEND LLM (enchufable). Backend por defecto: Claude (Anthropic).
# Una función backend recibe (system_prompt, user_text) y devuelve el texto.
# ============================================================
_backend = None
_backend_intentado = False


def set_backend(fn):
    """Registra un backend LLM personalizado: fn(system_prompt, user_text)->str."""
    global _backend
    _backend = fn


def _anthropic_backend():
    """Crea el backend Claude si hay paquete `anthropic` y ANTHROPIC_API_KEY.
    Usa caché de prompt en el bloque de sistema (TTL 5 min) para abaratar."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None
    cliente = anthropic.Anthropic(api_key=api_key)

    def _call(system_prompt, user_text):
        msg = cliente.messages.create(
            model=_MODEL,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_text}],
        )
        partes = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        return "".join(partes).strip()

    logger.info("AI translator: backend Claude (%s) activo.", _MODEL)
    return _call


def _obtener_backend():
    global _backend, _backend_intentado
    if _backend is not None:
        return _backend
    if not _backend_intentado:
        _backend_intentado = True
        _backend = _anthropic_backend()
        if _backend is None:
            logger.info(
                "AI translator: sin backend LLM (sin ANTHROPIC_API_KEY o paquete "
                "'anthropic'). La traducción dinámica devuelve el texto original."
            )
    return _backend


# ============================================================
# PROMPTS
# ============================================================
def _system_prompt(idioma, dominio):
    destino = _LANG_NAMES.get(idioma, idioma)
    hint = _DOMAIN_HINTS.get(dominio or "", "general business software content.")
    return (
        f"You are a professional translator for Smart Manager AI, an enterprise "
        f"retail/warehouse management platform. Translate the user's text into "
        f"{destino}. Context: {hint} "
        f"Preserve meaning and tone. CRITICAL: copy any placeholder in curly braces "
        f"(e.g. {{nombre}}, {{modulo}}, {{x}}) VERBATIM — never translate, rename or "
        f"remove what is inside the braces. Keep numbers, codes and proper nouns unchanged. "
        f"Return ONLY the translation, with no quotes, no notes, no explanations."
    )


# ============================================================
# API PÚBLICA
# ============================================================
def traducir(texto, idioma, dominio=None):
    """Traduce `texto` a `idioma` (código ISO) en el `dominio` dado.
    Devuelve la traducción, o el texto original si no hay backend o falla."""
    if not texto or not str(texto).strip():
        return texto
    if idioma in (None, "es"):
        # El contenido base del sistema está en español; no se traduce a sí mismo.
        return texto
    cache = _cargar_cache()
    k = _clave(texto, idioma, dominio)
    if k in cache:
        return cache[k]
    backend = _obtener_backend()
    if backend is None:
        return texto
    try:
        with _lock:
            resultado = backend(_system_prompt(idioma, dominio), texto)
        if resultado:
            resultado = _preservar_placeholders(texto, resultado)
            cache[k] = resultado
            _guardar_cache()
            return resultado
    except Exception as e:
        logger.debug("Traducción IA falló (%s): %s", idioma, e)
    return texto


# Máximo de cadenas por llamada al LLM. Lotes pequeños evitan que la respuesta
# JSON se trunque por max_tokens (la causa de que secciones grandes no se tradujeran).
_LOTE_MAX = 25


def _parse_json_array(raw):
    """Extrae un array JSON de la respuesta del modelo (tolera ```fences``` o texto)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
    a, b = s.find("["), s.rfind("]")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    return json.loads(s)


def traducir_lote(textos, idioma, dominio=None):
    """Traduce una lista de cadenas en sub-lotes pequeños. Devuelve una lista del
    mismo tamaño; usa caché por elemento. Los fallos NO se cachean (se reintentan)."""
    if not textos:
        return []
    if idioma in (None, "es"):
        return list(textos)
    cache = _cargar_cache()
    resultado = [None] * len(textos)
    pendientes, idx_pendientes = [], []
    for i, t in enumerate(textos):
        if not t or not str(t).strip():
            resultado[i] = t
            continue
        k = _clave(t, idioma, dominio)
        if k in cache:
            resultado[i] = cache[k]
        else:
            pendientes.append(t)
            idx_pendientes.append(i)
    if not pendientes:
        return resultado

    backend = _obtener_backend()
    if backend is None:
        for i in idx_pendientes:
            resultado[i] = textos[i]
        return resultado

    sp = _system_prompt(idioma, dominio) + (
        " The user sends a JSON array of strings; return ONLY a JSON array with the "
        "translations in the same order and the SAME length, nothing else."
    )
    algo_nuevo = False
    # Procesa en sub-lotes para que la respuesta nunca se trunque.
    for c0 in range(0, len(pendientes), _LOTE_MAX):
        sub = pendientes[c0:c0 + _LOTE_MAX]
        sub_idx = idx_pendientes[c0:c0 + _LOTE_MAX]
        try:
            with _lock:
                raw = backend(sp, json.dumps(sub, ensure_ascii=False))
            trad = _parse_json_array(raw)
            if not (isinstance(trad, list) and len(trad) == len(sub)):
                raise ValueError(f"tamaño distinto ({len(trad) if isinstance(trad,list) else '?'} vs {len(sub)})")
            for j, i in enumerate(sub_idx):
                val = _preservar_placeholders(textos[i], trad[j])
                resultado[i] = val
                cache[_clave(textos[i], idioma, dominio)] = val
                algo_nuevo = True
        except Exception as e:
            logger.debug("Sub-lote falló (%s): %s", idioma, e)
            for i in sub_idx:
                resultado[i] = textos[i]
    if algo_nuevo:
        _guardar_cache()
    return resultado


def registrar_proveedor():
    """Enchufa este traductor en el sistema i18n (Nivel 2)."""
    try:
        from src.utils import i18n
        i18n.set_ai_provider(traducir)
        logger.info("AI translator registrado en i18n.")
    except Exception as e:
        logger.debug("No se pudo registrar el proveedor de traducción: %s", e)
