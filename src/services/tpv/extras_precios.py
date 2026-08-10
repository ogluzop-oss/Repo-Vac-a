"""
Precios editables de los extras del TPV (bolsas / sobres de regalo).

Fuente de precio para los botones rápidos del TPV. Lee de `tpv_extras_precios`; si no hay fila para un
código, devuelve el precio por defecto del catálogo `gui.tpv._EXTRAS_TPV`. Degradable (sin BD → defecto).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("tpv.extras_precios")

# Códigos gestionados (los 4 con precio fijo; la tarjeta regalo tiene importe variable, no va aquí).
CODIGOS = ("BOLSA_GRANDE", "BOLSA_PEQUENA", "SOBRE_REGALO_PEQUENO", "SOBRE_REGALO_GRANDE")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _defecto(codigo):
    try:
        from src.gui.tpv import _EXTRAS_TPV
        ic, nombre, precio, iva = _EXTRAS_TPV[codigo]
        return nombre, float(precio)
    except Exception:
        return codigo.replace("_", " ").title(), 0.0


def obtener(codigo) -> float:
    """Precio del extra: el guardado en BD o, si no hay, el valor por defecto del catálogo."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT precio FROM tpv_extras_precios WHERE codigo=%s", (codigo,))
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except Exception as e:
        logger.debug(f"obtener precio extra degradado: {e}")
    return _defecto(codigo)[1]


def listar() -> list[dict]:
    """Los 4 extras con su nombre y precio actual: [{codigo, nombre, precio}]."""
    guardados = {}
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, precio FROM tpv_extras_precios")
            for cod, nom, pre in cur.fetchall():
                guardados[cod] = (nom, float(pre) if pre is not None else None)
    except Exception as e:
        logger.debug(f"listar precios extra degradado: {e}")
    salida = []
    for cod in CODIGOS:
        nom_def, pre_def = _defecto(cod)
        nom, pre = guardados.get(cod, (None, None))
        salida.append({"codigo": cod, "nombre": nom or nom_def,
                       "precio": pre if pre is not None else pre_def})
    return salida


def guardar(cambios: dict) -> tuple[bool, str]:
    """Guarda nuevos precios. `cambios` = {codigo: precio}. Devuelve (ok, mensaje)."""
    validos = {c: p for c, p in (cambios or {}).items() if c in CODIGOS}
    if not validos:
        return False, "No hay cambios que guardar."
    try:
        with _conn() as conn, conn.cursor() as cur:
            for cod, precio in validos.items():
                try:
                    precio = round(float(str(precio).replace(",", ".")), 2)
                except (TypeError, ValueError):
                    continue
                if precio < 0:
                    continue
                nom_def, _ = _defecto(cod)
                cur.execute(
                    "INSERT INTO tpv_extras_precios (codigo, nombre, precio) VALUES (%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE precio=VALUES(precio)", (cod, nom_def, precio))
            conn.commit()
        return True, "Precios actualizados."
    except Exception as e:
        logger.error(f"guardar precios extra: {e}")
        return False, f"Error al guardar: {e}"
