"""
Tema de interfaz + ajustes de SOMA (personalización por el usuario).

Almacén ligero en un JSON app-wide (NO requiere BD; se puede cargar en el import de
`assets/estilo_global.py`). Los cambios de color se aplican al ARRANQUE de la app (hay que reiniciar
para verlos), por eso el almacenamiento es un fichero simple y estable.

Colores por defecto = los actuales de Smart Manager (turquesa + azul oscuro).
Tolerante a fallos: si el fichero no existe o está corrupto, devuelve los valores por defecto.
"""

import json
import logging
import os

logger = logging.getLogger("utils.tema")

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA = os.path.join(_RAIZ, "config_ui_soma.json")

# ── Valores por defecto (idénticos al aspecto actual: turquesa #00FFC6 + azul oscuro #0E1117) ──
DEFECTOS = {
    # 1) Fondo de todas las ventanas de la app.
    "fondo_app": "#0E1117",
    # 2) Tablas y botones que INICIAN una acción (mismo color) + su texto (hover-swap).
    "accion_bg": "#00FFC6",
    "accion_texto": "#0E1117",
    # 3) Botones que CANCELAN una acción + su texto.
    "cancelar_bg": "#F85149",
    "cancelar_texto": "#FFFFFF",
    # 4) Botones que CONFIRMAN / avanzan la acción + su texto.
    "confirmar_bg": "#1ED760",
    "confirmar_texto": "#0E1117",
    # 5) Botones de RETORNO a la pantalla anterior + su texto.
    "retorno_bg": "#00FFC6",
    "retorno_texto": "#0E1117",
    # SOMA
    "soma_color": "#00FFC6",     # color de tintado del personaje (sprites blancos → este color)
    "soma_activo": True,          # SOMA habilitado por completo
    "soma_voz": True,             # voz de SOMA (escuchar + hablar). Si False → solo chat de texto
}

_CLAVES_COLOR = ("fondo_app", "accion_bg", "accion_texto", "cancelar_bg", "cancelar_texto",
                 "confirmar_bg", "confirmar_texto", "retorno_bg", "retorno_texto", "soma_color")


def _valida_color(v, defecto):
    """Acepta solo '#RGB' o '#RRGGBB'. Si no, devuelve el defecto (a prueba de corrupción)."""
    try:
        s = str(v).strip()
        if s.startswith("#") and len(s) in (4, 7):
            int(s[1:], 16)
            return s.upper()
    except Exception:
        pass
    return defecto


def cargar() -> dict:
    """Devuelve el tema (defaults + overrides del JSON). Nunca lanza."""
    datos = dict(DEFECTOS)
    try:
        if os.path.exists(RUTA):
            with open(RUTA, encoding="utf-8") as f:
                guardado = json.load(f) or {}
            for k in _CLAVES_COLOR:
                if k in guardado:
                    datos[k] = _valida_color(guardado[k], DEFECTOS[k])
            for k in ("soma_activo", "soma_voz"):
                if k in guardado:
                    datos[k] = bool(guardado[k])
    except Exception as e:
        logger.debug("cargar tema: %s", e)
    return datos


def guardar(cambios: dict) -> bool:
    """Fusiona `cambios` sobre el tema actual y lo persiste. Nunca lanza."""
    try:
        actual = cargar()
        for k, v in (cambios or {}).items():
            if k in _CLAVES_COLOR:
                actual[k] = _valida_color(v, actual.get(k, DEFECTOS.get(k)))
            elif k in ("soma_activo", "soma_voz"):
                actual[k] = bool(v)
        with open(RUTA, "w", encoding="utf-8") as f:
            json.dump(actual, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("guardar tema: %s", e)
        return False


def restablecer() -> bool:
    """Restablece los colores/ajustes por defecto (turquesa + azul oscuro)."""
    try:
        if os.path.exists(RUTA):
            os.remove(RUTA)
        return True
    except Exception as e:
        logger.error("restablecer tema: %s", e)
        return False


def color(clave) -> str:
    return cargar().get(clave, DEFECTOS.get(clave, "#00FFC6"))
