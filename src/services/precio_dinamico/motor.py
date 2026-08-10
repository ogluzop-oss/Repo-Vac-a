"""
Motor de precio dinámico — evalúa las reglas y recalcula `articulos.precio` a partir de `precio_base`
(no destructivo, idempotente, reversible).

Regla de negocio:
  · Cada artículo tiene un precio de REFERENCIA `precio_base`. Si es NULL y una regla lo toca por primera
    vez, se inicializa con el precio actual.
  · Se evalúan las reglas ACTIVAS de la empresa (y de la tienda o de "todas las tiendas"). Entre las que
    coinciden gana la de mayor `prioridad`; a igualdad, la que deja el precio MÁS BAJO (favorece al cliente).
  · Si ninguna regla coincide y el artículo estaba gestionado (`precio_base` no nulo), el precio VUELVE a
    `precio_base` (p. ej. al terminar la franja de "happy hour").
Después de aplicar, ESL detecta solo los cambios como etiquetas PENDIENTES.
"""

import datetime as _dt
import json
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.precio_dinamico.reglas import listar_reglas

logger = logging.getLogger("precio_dinamico.motor")

_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _en_horario(p, ahora):
    dias = p.get("dias")
    if dias:
        try:
            if ahora.weekday() not in [int(d) for d in dias]:
                return False
        except (TypeError, ValueError):
            pass
    desde, hasta = p.get("desde"), p.get("hasta")
    if not desde or not hasta:
        return True
    t = ahora.strftime("%H:%M")
    if desde <= hasta:
        return desde <= t < hasta
    return t >= desde or t < hasta          # ventana que cruza medianoche


def _coincide(regla, art, ahora):
    tipo = regla["tipo"]
    p = regla.get("_params", {})
    if tipo == "horario":
        return _en_horario(p, ahora)
    if tipo == "stock":
        campo = p.get("campo", "Stock_tienda")
        op = _OPS.get(p.get("op", ">"))
        if op is None:
            return False
        try:
            return op(float(art.get(campo) or 0), float(p.get("umbral", 0)))
        except (TypeError, ValueError):
            return False
    if tipo == "caducidad":
        return art.get("codigo") in regla.get("_caducan", set())
    return False


def _ajustar(base, regla):
    if regla["ajuste_tipo"] == "pct":
        return round(base * (1 + float(regla["ajuste_valor"]) / 100), 2)
    return round(float(regla["ajuste_valor"]), 2)


def _reglas_preparadas(id_empresa, id_tienda):
    """Reglas activas con `_params` parseado y, para caducidad, el conjunto de códigos afectados."""
    reglas = listar_reglas(id_empresa=id_empresa, solo_activas=True, id_tienda=id_tienda)
    for r in reglas:
        try:
            r["_params"] = json.loads(r.get("params") or "{}")
        except Exception:
            r["_params"] = {}
        if r["tipo"] == "caducidad":
            dias = int(r["_params"].get("dias", 7))
            try:
                from src.db.lotes import lotes_por_caducar
                r["_caducan"] = {l.get("codigo_articulo") for l in
                                 lotes_por_caducar(dias=dias, id_empresa=id_empresa)}
            except Exception:
                r["_caducan"] = set()
    return reglas


def _base_de(art):
    b = art.get("precio_base")
    if b in (None, ""):
        return float(art.get("precio") or 0)
    return float(b)


def _mejor(art, reglas, ahora):
    """Devuelve (precio_nuevo, regla) de la regla ganadora, o (base, None) si ninguna coincide."""
    base = _base_de(art)
    mejor = None
    mejor_precio = None
    for r in reglas:
        if not _coincide(r, art, ahora):
            continue
        pr = _ajustar(base, r)
        if (mejor is None or r["prioridad"] > mejor["prioridad"]
                or (r["prioridad"] == mejor["prioridad"] and pr < mejor_precio)):
            mejor, mejor_precio = r, pr
    if mejor is None:
        return base, None
    return mejor_precio, mejor


def _articulos(id_empresa):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo, nombre, precio, precio_base, COALESCE(Stock_tienda,0) AS Stock_tienda, "
                    "COALESCE(Stock_total,0) AS Stock_total, COALESCE(Stock_central,0) AS Stock_central "
                    "FROM articulos WHERE id_empresa=%s", (id_empresa,))
        return _filas_a_dicts(cur, cur.fetchall())


def previsualizar(id_empresa=None, id_tienda=None, ahora=None):
    """Qué haría el motor SIN aplicar: lista de {codigo, nombre, precio_actual, precio_nuevo, regla}
    solo para los artículos cuyo precio cambiaría."""
    e = _empresa(id_empresa)
    ahora = ahora or _dt.datetime.now()
    reglas = _reglas_preparadas(e, id_tienda)
    cambios = []
    for art in _articulos(e):
        nuevo, regla = _mejor(art, reglas, ahora)
        actual = float(art.get("precio") or 0)
        if abs(actual - nuevo) > 1e-4:
            cambios.append({"codigo": art["codigo"], "nombre": art.get("nombre"),
                            "precio_actual": actual, "precio_nuevo": nuevo,
                            "regla": regla["nombre"] if regla else None})
    return cambios


def aplicar(id_empresa=None, id_tienda=None, ahora=None):
    """Recalcula y ESCRIBE `articulos.precio` según las reglas. Devuelve {evaluados, cambiados, reglas}."""
    e = _empresa(id_empresa)
    ahora = ahora or _dt.datetime.now()
    reglas = _reglas_preparadas(e, id_tienda)
    evaluados = cambiados = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for art in _articulos(e):
                evaluados += 1
                actual = float(art.get("precio") or 0)
                tiene_base = art.get("precio_base") not in (None, "")
                nuevo, regla = _mejor(art, reglas, ahora)
                if regla is not None:
                    base = _base_de(art)
                    if not tiene_base or abs(actual - nuevo) > 1e-4:
                        cur.execute("UPDATE articulos SET precio=%s, precio_base=%s WHERE codigo=%s "
                                    "AND id_empresa=%s", (nuevo, base, art["codigo"], e))
                        if abs(actual - nuevo) > 1e-4:
                            cambiados += 1
                elif tiene_base and abs(actual - float(art["precio_base"])) > 1e-4:
                    # ninguna regla coincide → vuelve al precio de referencia
                    cur.execute("UPDATE articulos SET precio=precio_base WHERE codigo=%s AND id_empresa=%s",
                                (art["codigo"], e))
                    cambiados += 1
    except Exception as ex:
        logger.error("aplicar: %s", ex)
    return {"evaluados": evaluados, "cambiados": cambiados, "reglas": len(reglas)}
