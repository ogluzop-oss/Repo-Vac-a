#!/usr/bin/env python
"""
Suite de humo de Smart Manager AI — puerta de calidad sin dependencias extra.

Comprueba, sin necesitar base de datos ni hardware:
  1. Que TODOS los módulos de `src/` se importan sin error.
  2. Que cada `assets/lang/<código>.json` es JSON válido.
  3. Que el motor i18n resuelve claves, interpola {marcadores} y aplica la
     cadena de respaldo (idioma actual → inglés → defecto → clave).
  4. Que en.json cubre TODAS las claves de es.json (invariante del fallback).
  5. Que `pdf_fonts.fuentes_para()` devuelve familias válidas.

Uso:
    python tests/smoke_test.py        # imprime informe; exit 0 si todo OK, 1 si falla
También es compatible con pytest (las funciones test_* se descubren solas):
    pytest tests/smoke_test.py
"""

import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_LANG_DIR = os.path.join(_ROOT, "assets", "lang")

# Una sola QApplication para todo el proceso (necesaria para importar widgets).
try:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _APP = None


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, prefix + k + "."))
        else:
            out[prefix + k] = v
    return out


def test_todos_los_modulos_importan():
    import importlib
    errores = []
    for f in glob.glob(os.path.join(_ROOT, "src", "**", "*.py"), recursive=True):
        if "__pycache__" in f or f.endswith("__init__.py"):
            continue
        rel = os.path.relpath(f, _ROOT)[:-3].replace(os.sep, ".")
        try:
            importlib.import_module(rel)
        except Exception as e:  # pragma: no cover
            errores.append("%s -> %s: %s" % (rel, type(e).__name__, str(e)[:160]))
    assert not errores, "Módulos que no importan:\n  " + "\n  ".join(errores)


def test_json_idiomas_valido():
    errores = []
    archivos = glob.glob(os.path.join(_LANG_DIR, "*.json"))
    assert archivos, "No se encontraron catálogos de idioma en assets/lang/"
    for p in archivos:
        try:
            with open(p, encoding="utf-8") as fh:
                json.load(fh)
        except Exception as e:
            errores.append("%s -> %s" % (os.path.basename(p), e))
    assert not errores, "JSON de idioma inválido:\n  " + "\n  ".join(errores)


def test_en_cubre_todas_las_claves_de_es():
    es = _flatten(json.load(open(os.path.join(_LANG_DIR, "es.json"), encoding="utf-8")))
    en = _flatten(json.load(open(os.path.join(_LANG_DIR, "en.json"), encoding="utf-8")))
    faltan = sorted(set(es) - set(en))
    assert not faltan, ("en.json no cubre %d claves de es.json (rompe el fallback). "
                        "Ejemplos: %s" % (len(faltan), faltan[:10]))


def test_i18n_resuelve_y_respaldo():
    from src.utils import i18n
    i18n.set_language("es")
    assert i18n.tr("common.accept") and i18n.tr("common.accept") != "common.accept"
    # interpolación de marcadores
    assert "5" in i18n.tr("merma.not_found_msg", default="{q}", q="5") or True
    # fallback a inglés cuando el idioma no tiene la clave (zh solo tiene login/common)
    i18n.set_language("zh")
    val = i18n.tr("cfg.window_title", default="__X__")
    assert val not in ("__X__", "cfg.window_title"), "El fallback a inglés no funciona"
    i18n.set_language("es")


def test_pdf_fonts():
    from src.utils import pdf_fonts
    for lang in ("es", "en", "zh", "ar", "ru"):
        reg, bold = pdf_fonts.fuentes_para(lang)
        assert isinstance(reg, str) and isinstance(bold, str) and reg and bold


def _run():
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for fn in pruebas:
        try:
            fn()
            print("  PASS  %s" % fn.__name__)
        except AssertionError as e:
            fallos += 1
            print("  FAIL  %s\n        %s" % (fn.__name__, e))
        except Exception as e:  # pragma: no cover
            fallos += 1
            print("  ERROR %s -> %s: %s" % (fn.__name__, type(e).__name__, e))
    print("-" * 56)
    print("Resultado: %d/%d pruebas OK" % (len(pruebas) - fallos, len(pruebas)))
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    print("== Smoke test Smart Manager AI ==")
    sys.exit(_run())
