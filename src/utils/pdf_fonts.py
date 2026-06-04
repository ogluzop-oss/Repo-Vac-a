"""
Fuentes Unicode para documentos PDF (reportlab).

Las fuentes base de reportlab (Helvetica) solo cubren alfabeto latino occidental
(WinAnsi). Para idiomas con escritura no latina —chino, japonés, coreano, árabe,
hindi, tailandés, ruso/ucraniano (cirílico), griego…— hay que incrustar una
fuente TrueType con glifos Unicode.

`fuentes_para(idioma)` devuelve `(regular, negrita)`:
  - Para es/en/fr/de/it/pt (latino occidental) → ("Helvetica", "Helvetica-Bold")
    (comportamiento clásico, cero riesgo).
  - Para el resto → registra la mejor TTF del sistema que cubra esa escritura y
    devuelve sus nombres; si no encuentra ninguna, cae a Helvetica (degradación
    elegante: el PDF se genera igual, aunque los glifos no latinos no se vean).

Diseñado para Windows (usa C:\\Windows\\Fonts), pero admite una carpeta propia
en assets/fonts/ que tiene prioridad si el usuario incrusta su propia fuente.
"""

import logging
import os

logger = logging.getLogger("pdf.fonts")

# Idiomas que se renderizan bien con Helvetica/WinAnsi (latino occidental).
_LATIN_SAFE = {"es", "en", "fr", "de", "it", "pt"}

# Carpeta de fuentes propia del proyecto (prioritaria) y la del sistema.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
_ASSET_FONTS = os.path.join(_PROJECT_ROOT, "assets", "fonts")
_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# Candidatas por familia de escritura, en orden de preferencia.
# (regular, negrita_opcional). Si no hay negrita propia se reutiliza la regular.
_CANDIDATAS = {
    "cjk": [  # chino / japonés / coreano
        ("msyh.ttc", "msyhbd.ttc"), ("simsun.ttc", None), ("malgun.ttf", "malgunbd.ttf"),
        ("YuGothR.ttc", "YuGothB.ttc"), ("msgothic.ttc", None), ("NotoSansCJK-Regular.ttc", None),
    ],
    "arabic": [("arial.ttf", "arialbd.ttf"), ("tahoma.ttf", "tahomabd.ttf"), ("NotoSansArabic-Regular.ttf", None)],
    "thai":   [("tahoma.ttf", "tahomabd.ttf"), ("leelawui.ttf", "leelauib.ttf"), ("NotoSansThai-Regular.ttf", None)],
    "deva":   [("Nirmala.ttf", "NirmalaB.ttf"), ("mangal.ttf", None), ("NotoSansDevanagari-Regular.ttf", None)],
    "latin_ext": [  # cirílico, griego, turco, polaco, vietnamita… (Arial cubre casi todo)
        ("arial.ttf", "arialbd.ttf"), ("arialuni.ttf", None), ("segoeui.ttf", "segoeuib.ttf"),
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ],
}

# Idioma → familia de escritura necesaria.
_ESCRITURA = {
    "zh": "cjk", "ja": "cjk", "ko": "cjk",
    "ar": "arabic",
    "th": "thai",
    "hi": "deva",
    # cirílico/otros latinos extendidos
    "ru": "latin_ext", "uk": "latin_ext", "tr": "latin_ext", "pl": "latin_ext",
    "vi": "latin_ext", "nl": "latin_ext", "sv": "latin_ext", "id": "latin_ext",
}

_HELV = ("Helvetica", "Helvetica-Bold")
_cache = {}  # familia -> (regular, negrita)


def _buscar(nombre):
    """Devuelve la ruta de un archivo de fuente (assets propio o sistema), o None."""
    for base in (_ASSET_FONTS, _WIN_FONTS):
        ruta = os.path.join(base, nombre)
        if os.path.exists(ruta):
            return ruta
    return None


def _registrar_familia(familia):
    """Registra la primera candidata disponible para `familia`. Cachea el resultado."""
    if familia in _cache:
        return _cache[familia]
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception:
        _cache[familia] = _HELV
        return _HELV

    for regular_file, bold_file in _CANDIDATAS.get(familia, []):
        ruta_reg = _buscar(regular_file)
        if not ruta_reg:
            continue
        reg_name = "SM_%s" % familia
        bold_name = "SM_%s_B" % familia
        try:
            # subfontIndex=0 cubre .ttc (colecciones) tomando la primera cara.
            kw = {"subfontIndex": 0} if ruta_reg.lower().endswith(".ttc") else {}
            pdfmetrics.registerFont(TTFont(reg_name, ruta_reg, **kw))
            ruta_bold = _buscar(bold_file) if bold_file else None
            if ruta_bold:
                kwb = {"subfontIndex": 0} if ruta_bold.lower().endswith(".ttc") else {}
                pdfmetrics.registerFont(TTFont(bold_name, ruta_bold, **kwb))
            else:
                bold_name = reg_name  # sin negrita propia → usar la regular
            logger.info("PDF: fuente Unicode '%s' registrada para escritura %s.", regular_file, familia)
            _cache[familia] = (reg_name, bold_name)
            return _cache[familia]
        except Exception as e:
            logger.debug("PDF: no se pudo registrar %s: %s", regular_file, e)
            continue

    logger.info("PDF: sin fuente Unicode para escritura %s; se usa Helvetica (glifos no latinos pueden no verse).", familia)
    _cache[familia] = _HELV
    return _HELV


def fuentes_para(idioma):
    """Devuelve (regular, negrita) para generar un PDF en el idioma dado."""
    if not idioma or idioma in _LATIN_SAFE:
        return _HELV
    familia = _ESCRITURA.get(idioma)
    if not familia:
        return _HELV
    return _registrar_familia(familia)
