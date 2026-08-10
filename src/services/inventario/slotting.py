"""
Slotting inteligente (WMS, sin coste externo).

Analiza la ROTACIÓN de los productos (clasificación ABC por ventas) y su UBICACIÓN física para detectar
colocaciones mejorables: productos de alta rotación (A/B) en ubicaciones lejanas y productos de baja
rotación (C) ocupando ubicaciones accesibles ("golden zone"). Propone INTERCAMBIOS que acercan los productos
que más se pickean. Solo cálculo sobre datos existentes (`ventas` + `ubicaciones`); no requiere servicios de
pago. Puede aplicarse (intercambio de ubicaciones) o quedarse como recomendación.
"""

import logging
import re

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("inventario.slotting")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _num(s):
    m = re.search(r"\d+", str(s or ""))
    return int(m.group()) if m else 0


def rotacion(id_empresa=None, dias=90):
    """{codigo: unidades vendidas} en los últimos `dias` (scope de la empresa vía articulos)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT v.codigo, COALESCE(SUM(v.cantidad),0) FROM ventas v "
                        "JOIN articulos a ON a.codigo=v.codigo AND a.id_empresa=%s "
                        "WHERE v.fecha >= DATE_SUB(NOW(), INTERVAL %s DAY) GROUP BY v.codigo",
                        (eid, int(dias)))
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    except Exception as e:
        logger.error("rotacion: %s", e)
        return {}


def clasificar_abc(rot):
    """Pareto: A = hasta el 80% acumulado del volumen, B = 80–95%, C = resto (y sin rotación)."""
    total = sum(v for v in rot.values() if v > 0)
    if total <= 0:
        return {k: "C" for k in rot}
    clase, acc = {}, 0.0
    for k, v in sorted(rot.items(), key=lambda kv: kv[1], reverse=True):
        if v <= 0:
            clase[k] = "C"
            continue
        prev = acc / total * 100      # acumulado ANTES del ítem → el top siempre es A
        acc += v
        clase[k] = "A" if prev < 80 else ("B" if prev < 95 else "C")
    return clase


def _ocupadas(eid):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, codigo_articulo, pasillo, estanteria, balda FROM ubicaciones "
                    "WHERE id_empresa<=>%s AND codigo_articulo IS NOT NULL AND codigo_articulo<>''",
                    (eid,))
        return _filas_a_dicts(cur, cur.fetchall())


def _coste(u):
    """Coste de acceso de una ubicación (menor = más accesible / 'golden')."""
    return _num(u.get("pasillo")) * 100 + _num(u.get("estanteria")) * 10 + _num(u.get("balda"))


def _fmt(u):
    return "-".join(str(u.get(k) or "") for k in ("pasillo", "estanteria", "balda"))


def analizar(id_empresa=None, dias=90):
    """Analiza rotación vs ubicación. Devuelve {abc, ubicaciones, recomendaciones:[intercambios]}."""
    eid = _emp(id_empresa)
    rot = rotacion(eid, dias)
    clase = clasificar_abc(rot)
    ubis = _ocupadas(eid)
    if not ubis:
        return {"abc": {"A": 0, "B": 0, "C": 0}, "ubicaciones": 0, "recomendaciones": []}
    for u in ubis:
        u["clase"] = clase.get(u["codigo_articulo"], "C")
        u["rotacion"] = rot.get(u["codigo_articulo"], 0)
        u["coste"] = _coste(u)
    costes = sorted(u["coste"] for u in ubis)
    mediana = costes[len(costes) // 2]
    # Mitad superior de coste (lejanas) para productos de rotación; mitad inferior (golden) para los C.
    lejanas = [u for u in ubis if u["clase"] in ("A", "B") and u["coste"] >= mediana]
    lejanas.sort(key=lambda u: (-u["rotacion"], u["coste"]))
    golden = [u for u in ubis if u["clase"] == "C" and u["coste"] < mediana]
    golden.sort(key=lambda u: u["coste"])
    recs = []
    for a, c in zip(lejanas, golden):
        recs.append({
            "codigo": a["codigo_articulo"], "clase": a["clase"], "rotacion": a["rotacion"],
            "ubicacion_actual": _fmt(a), "id_ubicacion": a["id"],
            "codigo_intercambio": c["codigo_articulo"], "ubicacion_sugerida": _fmt(c),
            "id_ubicacion_sugerida": c["id"],
            "motivo": f"Producto {a['clase']} (rotación {a['rotacion']:.0f}) en ubicación lejana; "
                      f"intercambiar con un producto C en zona accesible.",
        })
    abc = {"A": 0, "B": 0, "C": 0}
    for u in ubis:
        abc[u["clase"]] = abc.get(u["clase"], 0) + 1
    return {"abc": abc, "ubicaciones": len(ubis), "recomendaciones": recs}


def aplicar_intercambio(id_ubicacion_a, id_ubicacion_b, id_empresa=None):
    """Intercambia el producto asignado entre dos ubicaciones (aplica una recomendación de slotting)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, codigo_articulo FROM ubicaciones WHERE id IN (%s,%s)",
                        (id_ubicacion_a, id_ubicacion_b))
            filas = {r[0]: r[1] for r in cur.fetchall()}
            if len(filas) != 2:
                return False
            cur.execute("UPDATE ubicaciones SET codigo_articulo=%s WHERE id=%s",
                        (filas[id_ubicacion_b], id_ubicacion_a))
            cur.execute("UPDATE ubicaciones SET codigo_articulo=%s WHERE id=%s",
                        (filas[id_ubicacion_a], id_ubicacion_b))
            conn.commit()
            return True
    except Exception as e:
        logger.error("aplicar_intercambio: %s", e)
        return False
