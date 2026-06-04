#!/usr/bin/env python
"""
Backfill de traducciones i18n para Smart Manager AI.

Rellena, para cada idioma soportado, las claves que falten respecto a la base
española (assets/lang/es.json) usando el traductor IA por dominio
(src/utils/ai_translator). Es:

  • Idempotente: solo añade claves que faltan; nunca sobrescribe las existentes
    (respeta traducciones humanas ya presentes).
  • Seguro: solo escribe una traducción si el motor IA devolvió algo distinto del
    texto original. Si no hay backend (sin ANTHROPIC_API_KEY) no escribe nada y la
    app sigue cayendo a inglés vía la cadena de respaldo current→en→default→key.
  • Eficiente: traduce por lotes (una llamada por sección e idioma) y reutiliza la
    caché en disco de ai_translator (documentos/ai_translate_cache.json).
  • Respeta los marcadores {nombre} y el formato HTML simple del texto.

Uso:
    set ANTHROPIC_API_KEY=sk-...
    pip install anthropic        # si no está instalado
    python backfill_idiomas.py                 # todos los idiomas
    python backfill_idiomas.py fr de it pt     # solo esos
    python backfill_idiomas.py --dry-run       # informe sin escribir

Sin clave API la ejecución es un “no-op” informativo (no rompe nada).
"""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# Carga el .env de la raíz del proyecto (igual que la app vía src/db/conexion.py),
# para que ANTHROPIC_API_KEY definida en .env funcione también al ejecutar el script.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass

from src.utils import ai_translator  # noqa: E402

_LANG_DIR = os.path.join(_ROOT, "assets", "lang")
_BASE = "es"          # idioma fuente (autoridad)
_SKIP = {"es", "en"}  # es es la fuente; en ya está completo

# Dominio de traducción por sección (orienta la terminología del LLM).
_DOMINIO_SECCION = {
    "ticket": "tpv", "tpv": "tpv", "pago": "tpv", "bascula": "tpv", "devol": "tpv",
    "sel_caja": "tpv", "login_tpv": "tpv", "bloq": "tpv", "linea": "tpv",
    "retenidas": "tpv", "ges_granel": "tpv", "ed_granel": "tpv", "autoriz": "tpv",
    "vta": "tpv", "etiq": "tpv",
    "albaran": "logistico", "ubic": "logistico", "stock": "logistico",
    "merma": "logistico", "repo": "logistico", "info": "logistico",
    "cfg": "laboral",   # configuración incluye fiscalidad/laboral; "laboral" es razonable
}
_DOMINIO_DEFECTO = "ui"


def _cargar(code):
    p = os.path.join(_LANG_DIR, "%s.json" % code)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _guardar(code, data):
    p = os.path.join(_LANG_DIR, "%s.json" % code)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _idiomas_soportados():
    try:
        from src.utils import i18n
        return [c for c in i18n.LANGUAGES.keys() if c not in _SKIP]
    except Exception:
        return [os.path.basename(p)[:-5] for p in
                [f for f in os.listdir(_LANG_DIR) if f.endswith(".json")]
                if os.path.basename(p)[:-5] not in _SKIP]


def backfill(idiomas=None, dry_run=False):
    base = _cargar(_BASE)
    objetivos = idiomas or _idiomas_soportados()
    ai_translator._obtener_backend()  # fuerza intento de backend (log informativo)

    total_global = 0
    for code in objetivos:
        try:
            dest = _cargar(code)
        except FileNotFoundError:
            dest = {}
        añadidas = 0
        faltan = 0
        for seccion, claves in base.items():
            if not isinstance(claves, dict):
                continue
            dseccion = dest.setdefault(seccion, {})
            dominio = _DOMINIO_SECCION.get(seccion, _DOMINIO_DEFECTO)
            # Claves que faltan en esta sección/idioma.
            pendientes = [(k, v) for k, v in claves.items()
                          if isinstance(v, str) and k not in dseccion]
            if not pendientes:
                continue
            faltan += len(pendientes)
            textos = [v for _, v in pendientes]
            traducidos = ai_translator.traducir_lote(textos, code, dominio=dominio)
            for (k, original), trad in zip(pendientes, traducidos, strict=False):
                # Solo escribir traducciones reales (distintas del original).
                if trad and trad != original and not dry_run:
                    dseccion[k] = trad
                    añadidas += 1
        if añadidas and not dry_run:
            _guardar(code, dest)
        total_global += añadidas
        estado = "DRY-RUN" if dry_run else "escritas"
        print("  %-3s  faltaban %4d  ·  %s %4d" % (code, faltan, estado, añadidas))

    print("-" * 48)
    if total_global == 0:
        print("No se escribió ninguna traducción.")
        print("Si esperabas traducciones: define ANTHROPIC_API_KEY e instala 'anthropic',")
        print("luego vuelve a ejecutar. (La app ya funciona en 20 idiomas cayendo a inglés.)")
    else:
        print("Total de claves traducidas y escritas: %d" % total_global)
        print("Caché IA: documentos/ai_translate_cache.json")
    return total_global


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    langs = [a for a in args if not a.startswith("--")] or None
    print("== Backfill i18n Smart Manager ==  base=%s  destino=%s%s" % (
        _BASE, langs or "todos", "  (DRY-RUN)" if dry else ""))
    backfill(langs, dry_run=dry)
