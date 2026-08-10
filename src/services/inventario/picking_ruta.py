"""
Optimización de rutas de picking (WMS, sin coste externo).

Ordena las líneas de un picking en recorrido SERPENTÍN (S-shape) sobre las ubicaciones pasillo-estantería-
balda para minimizar el desplazamiento del operario (evita ir y volver por el mismo pasillo). Solo cálculo
sobre datos existentes (`almacen_picking_lineas`); no requiere mapas ni servicios de pago. Read-only.
"""

import logging
import re

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("inventario.picking_ruta")


def _num(parte):
    """Componente numérico de un tramo de ubicación ('P12'→12, 'A'→código, ''→0)."""
    m = re.search(r"\d+", str(parte or ""))
    if m:
        return int(m.group())
    letras = "".join(ch for ch in str(parte or "").upper() if ch.isalpha())
    return sum(ord(c) - 64 for c in letras) if letras else 0


def parsear_ubicacion(s):
    """'P1-E2-B3' / '1-2-3' / 'A-05-3' → (pasillo, estantería, balda) numéricos. Vacío → muy al fondo."""
    if not s:
        return (9999, 9999, 9999)
    partes = re.split(r"[-_/\s]+", str(s).strip())
    vals = [_num(p) for p in partes[:3]]
    while len(vals) < 3:
        vals.append(0)
    return tuple(vals[:3])


def optimizar_ruta(lineas):
    """Ordena `lineas` (dicts con 'ubicacion') en serpentín. Devuelve (ordenadas, metricas).

    Serpentín: pasillos en orden ascendente; dentro de cada pasillo la estantería sube en los pasillos
    pares y baja en los impares (así al cambiar de pasillo se sigue por el extremo más cercano); balda asc.
    """
    enr = []
    for ln in lineas or []:
        p, e, b = parsear_ubicacion(ln.get("ubicacion"))
        enr.append((p, e, b, ln))
    enr.sort(key=lambda t: (t[0], t[1] if t[0] % 2 == 0 else -t[1], t[2]))
    ordenadas = [{**t[3], "orden": i + 1, "_pasillo": t[0]} for i, t in enumerate(enr)]
    pasillos = sorted({t[0] for t in enr if t[0] != 9999})
    return ordenadas, {"lineas": len(ordenadas), "pasillos": len(pasillos)}


def ruta_picking(id_picking, id_empresa=None):
    """Lee las líneas de un picking y devuelve su recorrido óptimo (ordenadas, metricas). Read-only."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM almacen_picking_lineas WHERE id_picking=%s", (id_picking,))
            lineas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("ruta_picking: %s", e)
        return [], {"lineas": 0, "pasillos": 0}
    return optimizar_ruta(lineas)
