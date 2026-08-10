"""
Barrido RFID de inventario (PDA/MDE con RFID activo) — API-First, sin PyQt.

El operario recorre la tienda con la PDA/MDE y el lector detecta AUTOMÁTICAMENTE todos los
artículos por sus alarmas (etiqueta adhesiva RFID o tag duro EAS reutilizable). Al terminar
el barrido se obtiene el conteo detectado por artículo y sus DISCREPANCIAS frente al stock
esperado, para localizar errores de stock sin recuento manual ni error humano.

Modo DEGRADABLE (patrón del ERP): si se pasa un `gateway` con lectura de hardware real
(`inventario_conteo()` → {codigo: unidades}) se usa; si no, se simula un barrido físico
realista (tasa de lectura + pequeñas mermas/sobrantes) sobre los artículos de la empresa.
No escribe en la BD: devuelve la lectura para que el llamador registre el recuento donde
corresponda (p. ej. `src.db.inventario_fisico.registrar_recuento`).
"""

import logging
import random

from src.db.conexion import obtener_conexion

logger = logging.getLogger("rfid.inventario")


def _articulos_para_barrido(id_empresa, incluir_sin_stock=False):
    """Devuelve [(codigo, nombre, esperado)] de la empresa. `esperado` = Stock_total+Stock_tienda
    (mismo criterio que inventario_fisico._stock_actual, para que la diferencia sea coherente)."""
    q = ("SELECT codigo, nombre, COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0) AS esperado "
         "FROM articulos WHERE id_empresa=%s")
    if not incluir_sin_stock:
        q += " AND (COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0)) > 0"
    q += " ORDER BY nombre"
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, (id_empresa,))
            for r in cur.fetchall():
                if isinstance(r, dict):
                    out.append((r["codigo"], r.get("nombre"), int(r.get("esperado") or 0)))
                else:
                    out.append((r[0], r[1], int(r[2] or 0)))
    except Exception as e:
        logger.error("_articulos_para_barrido(%s): %s", id_empresa, e)
    return out


def _conteo_por_hardware(gateway):
    """Lectura real del lector: {codigo: unidades}. None si no hay método/hardware."""
    fn = getattr(gateway, "inventario_conteo", None)
    if not callable(fn):
        return None
    try:
        d = fn()
        if isinstance(d, dict):
            return {str(k): int(v) for k, v in d.items() if int(v) >= 0}
    except Exception as e:
        logger.warning("inventario_conteo hardware: %s", e)
    return None


def barrido_inventario(id_empresa, id_tienda=None, *, gateway=None,
                       incluir_sin_stock=False, tasa_lectura=0.99, semilla=None):
    """Realiza un barrido RFID y devuelve el resultado del recuento.

    Retorna dict:
      {
        "modo": "RFID" | "SIMULADO",
        "total_articulos": nº de artículos con lectura,
        "total_unidades":  nº total de unidades detectadas,
        "discrepancias":   nº de artículos con diferencia ≠ 0,
        "detectados": [ {codigo, nombre, detectado, esperado, diferencia}, ... ]
                      (ordenado: primero los que tienen discrepancia)
      }

    - `gateway`: lector físico opcional (degradable). Si expone `inventario_conteo()` se usa.
    - `tasa_lectura`: en simulación, probabilidad de leer cada unidad (RFID no siempre es 100 %).
    - `semilla`: fija la aleatoriedad de la simulación (reproducible en tests).
    """
    articulos = _articulos_para_barrido(id_empresa, incluir_sin_stock)
    esperados = {c: e for c, _n, e in articulos}
    nombres = {c: n for c, n, _e in articulos}

    conteo_hw = _conteo_por_hardware(gateway) if gateway is not None else None

    if conteo_hw is not None:
        modo = "RFID"
        conteo = conteo_hw
        # Los artículos de la tienda no detectados quedan a 0 (posible faltante real).
        for cod in esperados:
            conteo.setdefault(cod, 0)
    else:
        modo = "SIMULADO"
        rnd = random.Random(semilla)
        conteo = {}
        for cod, _nom, esp in articulos:
            # 1) tasa de lectura RFID (algún tag puede no leerse en una sola pasada)
            leido = sum(1 for _ in range(esp) if rnd.random() <= tasa_lectura)
            # 2) merma/sobrante real de ~15 % de las referencias (expone discrepancias)
            if esp > 0 and rnd.random() < 0.15:
                leido = max(0, leido + rnd.choice([-2, -1, 1, 2]))
            conteo[cod] = leido

    filas = []
    total_u = 0
    disc = 0
    # Unión: artículos de la tienda + posibles códigos ajenos leídos por el lector.
    codigos = list(esperados.keys()) + [c for c in conteo if c not in esperados]
    for cod in codigos:
        det = int(conteo.get(cod, 0))
        esp = int(esperados.get(cod, 0))
        dif = det - esp
        total_u += det
        if dif != 0:
            disc += 1
        filas.append({"codigo": cod, "nombre": nombres.get(cod, ""),
                      "detectado": det, "esperado": esp, "diferencia": dif})

    # Primero las discrepancias (por magnitud), luego el resto por nombre.
    filas.sort(key=lambda f: (f["diferencia"] == 0, -abs(f["diferencia"]),
                              (f["nombre"] or f["codigo"] or "")))
    return {"modo": modo, "total_articulos": len(filas), "total_unidades": total_u,
            "discrepancias": disc, "detectados": filas}
