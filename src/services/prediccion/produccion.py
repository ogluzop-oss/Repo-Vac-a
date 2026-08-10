"""
Predicción de PRODUCCIÓN / fabricación (IA de producción). Para cada artículo con BOM activa, estima la demanda
(rotación reciente como proxy honesto) y, comparándola con el stock, RECOMIENDA fabricar. Explosiona el BOM para
avisar de componentes que faltan. NUNCA crea órdenes de fabricación: delega en MRP/Workflow.

Honestidad IA/ML: es un motor HEURÍSTICO (rotación − stock); etiqueta el origen con `heuristicas.motor_activo()`.
Reutiliza `services/mrp/bom` (BOM/explosión), `prediccion/adaptadores` (rotación) y `db/stock_almacen` (stock). N7.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C
from src.services.prediccion import heuristicas as H


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _fabricables(id_empresa) -> list:
    """Artículos con BOM activa (productos terminados)."""
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT articulo_final FROM bom WHERE id_empresa=%s AND estado='activa'",
                        (id_empresa,))
            return [r[0] if not isinstance(r, dict) else r["articulo_final"] for r in cur.fetchall()]
    except Exception:
        return []


def _stock(codigo, id_empresa) -> int:
    try:
        from src.db import stock_almacen
        return int(stock_almacen.stock_total_global(codigo, id_empresa) or 0)
    except Exception:
        return 0


def _componentes_faltantes(articulo, cantidad, id_empresa) -> list:
    faltan = []
    try:
        from src.services.mrp import bom
        for comp in bom.explosionar(articulo, cantidad, id_empresa=id_empresa):
            ccod = comp.get("componente") or comp.get("codigo")
            nec = int(comp.get("cantidad") or comp.get("necesario") or comp.get("cantidad_neta") or 0)
            if not ccod or nec <= 0:
                continue
            disp = _stock(ccod, id_empresa)
            if disp < nec:
                faltan.append({"componente": ccod, "necesario": nec, "stock": disp})
    except Exception:
        pass
    return faltan


def predecir(id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    if not C.activo("produccion", id_empresa):
        return {"dominio": "produccion", "activo": False, "recomendaciones": [], "alertas": [],
                "motor": H.motor_activo()}
    rot = {r.get("codigo"): int(r.get("uds") or 0) for r in A.rotacion_articulos(id_empresa)}
    recomendaciones = []
    for art in _fabricables(id_empresa)[:50]:
        demanda = rot.get(art, 0)                       # uds/30d (proxy de demanda)
        stock = _stock(art, id_empresa)
        sugerido = max(0, demanda - stock)
        if sugerido <= 0:
            continue
        faltan = _componentes_faltantes(art, sugerido, id_empresa)
        recomendaciones.append({
            "accion": "fabricar", "entidad": "articulo", "entidad_id": art,
            "cantidad_sugerida": sugerido,
            "motivo": f"Demanda {demanda} uds/30d > stock {stock}. Producir {sugerido}.",
            "componentes_faltantes": faltan,
            "prioridad": "ALTA" if faltan else "MEDIA", "workflow": "mrp_orden"})
    alertas = []
    if recomendaciones:
        alertas.append({"tipo": "produccion", "severidad": "media",
                        "mensaje": f"{len(recomendaciones)} producto(s) recomendados para fabricar.",
                        "datos": {"n": len(recomendaciones)}})
    return {"dominio": "produccion", "activo": True, "recomendaciones": recomendaciones,
            "alertas": alertas, "motor": H.motor_activo()}
