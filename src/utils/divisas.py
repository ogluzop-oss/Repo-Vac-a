"""
Sistema multidivisa global de Smart Manager AI.

La divisa es INDEPENDIENTE del idioma: se configura aparte (DIVISA EMPRESA) y se
guarda en la configuración global de la empresa (configuraciones.moneda).

Todo es CONFIGURABLE (assets/currencies/registry.json): para añadir una divisa
basta con (1) crear assets/currencies/<CODE>/coins y /banknotes, (2) poner las
imágenes (nombre = valor: 0.01.png, 0.5.png, 2.png, 100.png...), y (3) añadir su
entrada al registro. NO hay que tocar esta lógica.

API principal:
    from src.utils import divisas
    divisas.divisa_actual()            -> 'EUR'
    divisas.formatear(1234.5)          -> '1,234.50 €'
    divisas.denominaciones()           -> [{'tipo','valor','etiqueta','imagen'}, ...] (desc.)
    divisas.ruta_imagen('EUR','coins',2)  -> ruta o None (con fallback + log)
    divisas.set_divisa('USD')          -> persiste y emite señal de cambio en caliente
    divisas.senal().divisa_cambiada.connect(slot)   # rebuild de UI sin reiniciar
"""

import json
import logging
import os

logger = logging.getLogger("divisas")

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))


def _dir_currencies():
    """Carpeta assets/currencies (compatible con .exe vía recursos)."""
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "currencies")
    except Exception:
        return os.path.join(_ROOT, "assets", "currencies")


# ── Registro (config) ───────────────────────────────────────────────────────────
_registro_cache = None
_DEFECTO = "EUR"


def _registro():
    global _registro_cache
    if _registro_cache is not None:
        return _registro_cache
    data = {}
    try:
        with open(os.path.join(_dir_currencies(), "registry.json"), encoding="utf-8") as f:
            data = (json.load(f) or {}).get("monedas", {})
    except Exception as e:
        logger.error("No se pudo leer el registro de divisas: %s", e)
    _registro_cache = data
    return data


def monedas_soportadas():
    """Lista de códigos soportados (los del registro)."""
    return list(_registro().keys())


def info(code=None):
    """Metadatos de la divisa (símbolo, decimales, posición, denominaciones)."""
    code = (code or divisa_actual()).upper()
    reg = _registro()
    d = reg.get(code) or reg.get(_DEFECTO) or {}
    return {
        "code": code if code in reg else _DEFECTO,
        "nombre": d.get("nombre", code),
        "simbolo": d.get("simbolo", code),
        "decimales": int(d.get("decimales", 2)),
        "simbolo_pos": d.get("simbolo_pos", "antes"),
        "coins": list(d.get("coins", [])),
        "banknotes": list(d.get("banknotes", [])),
    }


def simbolo(code=None):
    return info(code)["simbolo"]


# ── Divisa activa (config de empresa) ────────────────────────────────────────────
_cache_divisa = None


def divisa_actual():
    """Código de la divisa de la empresa (cacheado). Defecto EUR."""
    global _cache_divisa
    if _cache_divisa:
        return _cache_divisa
    code = _DEFECTO
    try:
        from src.db.conexion import obtener_configuracion
        code = (obtener_configuracion().get("moneda") or _DEFECTO).upper()
    except Exception as e:
        logger.debug("No se pudo leer la divisa de la BD: %s", e)
    if code not in _registro():
        code = _DEFECTO
    _cache_divisa = code
    return code


def set_divisa(code):
    """Cambia la divisa de la empresa: persiste en BD, refresca caché y emite señal
    para que la UI se reconstruya en caliente (sin reiniciar)."""
    code = (code or "").upper()
    if code not in _registro():
        raise ValueError(f"Divisa no soportada: {code}")
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE configuraciones SET moneda=%s", (code,))
                if cur.rowcount == 0:
                    cur.execute(
                        "INSERT INTO configuraciones (nombre_empresa, moneda) "
                        "VALUES ('SMART MANAGER', %s)", (code,)
                    )
            conn.commit()
    except Exception as e:
        logger.error("No se pudo guardar la divisa: %s", e)
        raise
    global _cache_divisa
    _cache_divisa = code
    logger.info("Divisa de empresa cambiada a %s.", code)
    _emitir(code)
    return code


def recargar():
    """Olvida la caché (releer de BD/registro la próxima vez)."""
    global _cache_divisa, _registro_cache
    _cache_divisa = None
    _registro_cache = None


# ── Formato de importes ──────────────────────────────────────────────────────────
def formatear(monto, code=None, con_simbolo=True):
    """Formatea un importe en la divisa dada: separador de miles y los decimales
    propios de la divisa (JPY/KRW/CLP/COP = 0 decimales), con el símbolo en su
    posición. Ej.: EUR -> '1,234.50 €', USD -> '$1,234.50', JPY -> '¥1,235'."""
    inf = info(code)
    try:
        monto = float(monto or 0)
    except (TypeError, ValueError):
        monto = 0.0
    txt = f"{monto:,.{inf['decimales']}f}"
    if not con_simbolo:
        return txt
    return f"{txt} {inf['simbolo']}" if inf["simbolo_pos"] == "despues" else f"{inf['simbolo']}{txt}"


# ── Denominaciones e imágenes ────────────────────────────────────────────────────
def _slug(valor):
    """Nombre de archivo de una denominación (valor → '0.01', '0.5', '2', '100')."""
    return ("%g" % float(valor))


def etiqueta(valor, code=None):
    """Etiqueta COMPACTA de una denominación: '2 €', '0.5 €', '500 €', '$100', '¥1000'
    (sin decimales innecesarios, a diferencia de formatear() que es para importes)."""
    inf = info(code)
    txt = "%g" % float(valor)
    return f"{txt} {inf['simbolo']}" if inf["simbolo_pos"] == "despues" else f"{inf['simbolo']}{txt}"


def ruta_imagen(code, tipo, valor):
    """Ruta de la imagen de una denominación, o None si no existe (con log).
    tipo: 'coins' | 'banknotes'. Estructura: assets/currencies/<CODE>/<tipo>/<valor>.png"""
    code = (code or divisa_actual()).upper()
    base = os.path.join(_dir_currencies(), code, tipo)
    slug = _slug(valor)
    for nombre in (f"{slug}.png", f"{slug}.jpg", f"{slug}.webp"):
        ruta = os.path.join(base, nombre)
        if os.path.exists(ruta):
            return ruta
    logger.warning("Imagen de divisa no encontrada: %s/%s/%s (se usará icono genérico).",
                   code, tipo, slug)
    return None


def denominaciones(code=None, descendente=True):
    """Lista de denominaciones de la divisa, lista para una tabla de arqueo.
    Cada elemento: {'tipo':'billete'|'moneda', 'valor':float, 'etiqueta':str,
    'imagen':ruta|None}. Ordenadas de mayor a menor por defecto."""
    inf = info(code)
    code = inf["code"]
    items = []
    for v in inf["banknotes"]:
        items.append({"tipo": "billete", "valor": float(v),
                      "etiqueta": etiqueta(v, code),
                      "imagen": ruta_imagen(code, "banknotes", v)})
    for v in inf["coins"]:
        items.append({"tipo": "moneda", "valor": float(v),
                      "etiqueta": etiqueta(v, code),
                      "imagen": ruta_imagen(code, "coins", v)})
    items.sort(key=lambda d: d["valor"], reverse=descendente)
    return items


# ── Señal de cambio en caliente (Qt, opcional) ───────────────────────────────────
_senal_obj = None


def senal():
    """Devuelve un QObject con la señal `divisa_cambiada = pyqtSignal(str)` para que
    la UI se reconstruya al cambiar de divisa. None si Qt no está disponible."""
    global _senal_obj
    if _senal_obj is not None:
        return _senal_obj
    try:
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Senal(QObject):
            divisa_cambiada = pyqtSignal(str)

        _senal_obj = _Senal()
    except Exception:
        _senal_obj = None
    return _senal_obj


def _emitir(code):
    s = senal()
    if s is not None:
        try:
            s.divisa_cambiada.emit(code)
        except Exception:
            pass
