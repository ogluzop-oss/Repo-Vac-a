"""
Subfamilias (apartados) de cada familia a granel — editable por el superadministrador.

Antes vivían como lista fija en `services.tpv.familias_granel` (solo Panes/Bollería). Ahora están
en la tabla `familias_granel_subfamilias` (migración 0308) para que el superadministrador pueda
crear apartados nuevos en cualquier familia (p. ej. Carnicería/Pescadería) desde la propia ventana
de alta/edición de un producto a granel, sin tocar código. `familias_granel.subfamilias()` es
quien consume este módulo — el resto de la app sigue llamando a esa única fuente de verdad.
"""

import logging
import re
import unicodedata

logger = logging.getLogger("tpv.familias_granel_subfamilias")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


# Caché en memoria por familia: `listar()` se llama una vez POR PRODUCTO al agrupar la rejilla de
# una familia (`_cargar_productos`/`normalizar_subfamilia`, decenas de veces por apertura) — sin
# caché, cada llamada abre una conexión nueva del pool (con su propio ping) solo para releer los
# mismos 2-5 apartados que ya se habían leído un instante antes, multiplicando el tiempo de
# construcción de la ventana (medido: ~250 llamadas → ~500 idas y vueltas a BD → cientos de ms,
# competían por CPU con la animación de entrada y se veían como un parpadeo). Se invalida la
# entrada de una familia en cuanto `crear()` le añade un apartado nuevo — nunca sirve datos
# obsoletos, solo evita repetir lo ya leído.
_cache_listar: dict[str, list[dict]] = {}


def listar(codigo_familia: str) -> list[dict]:
    """[{codigo, etiqueta}] de los apartados de una familia, en orden; [] si no tiene ninguno
    (degradable: también [] si la BD no está disponible, nunca lanza)."""
    clave = (codigo_familia or "").upper()
    if clave in _cache_listar:
        return _cache_listar[clave]
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, etiqueta FROM familias_granel_subfamilias "
                "WHERE codigo_familia=%s ORDER BY orden, etiqueta",
                (clave,))
            filas = cur.fetchall()
            out = []
            for f in filas:
                if isinstance(f, dict):
                    out.append({"codigo": f.get("codigo"), "etiqueta": f.get("etiqueta")})
                else:
                    out.append({"codigo": f[0], "etiqueta": f[1]})
            _cache_listar[clave] = out
            return out
    except Exception as e:
        logger.error("listar(%s): %s", codigo_familia, e)
        return []


def _slug(etiqueta: str) -> str:
    """'Pescado blanco' -> 'PESCADO_BLANCO' (sin acentos, mayúsculas, separado por '_')."""
    sin_acentos = unicodedata.normalize("NFKD", etiqueta).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", sin_acentos)).strip("_").upper()


def crear(codigo_familia: str, etiqueta: str) -> dict | None:
    """Crea un apartado nuevo dentro de una familia. Devuelve {codigo, etiqueta} o None si falla
    (nombre vacío, familia vacía, o error de BD)."""
    codigo_familia = (codigo_familia or "").upper().strip()
    etiqueta = (etiqueta or "").strip()
    if not codigo_familia or not etiqueta:
        return None
    base = _slug(etiqueta) or "APARTADO"
    try:
        with _conn() as conn, conn.cursor() as cur:
            existentes = {s["codigo"] for s in listar(codigo_familia)}
            codigo = base
            n = 2
            while codigo in existentes:
                codigo = f"{base}_{n}"
                n += 1
            cur.execute(
                "SELECT COALESCE(MAX(orden), 0) FROM familias_granel_subfamilias "
                "WHERE codigo_familia=%s", (codigo_familia,))
            r = cur.fetchone()
            orden = (list(r.values())[0] if isinstance(r, dict) else r[0]) or 0
            cur.execute(
                "INSERT INTO familias_granel_subfamilias (codigo_familia, codigo, etiqueta, orden) "
                "VALUES (%s, %s, %s, %s)",
                (codigo_familia, codigo, etiqueta, orden + 1))
            conn.commit()
        _cache_listar.pop(codigo_familia, None)
        return {"codigo": codigo, "etiqueta": etiqueta}
    except Exception as e:
        logger.error("crear(%s, %s): %s", codigo_familia, etiqueta, e)
        return None
