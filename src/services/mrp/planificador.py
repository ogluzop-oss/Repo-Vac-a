"""
MRP-G — Motor de planificacion MRP.

Explosion de BOM sobre una demanda -> necesidades brutas -> netas (descontando stock global) ->
sugerencias de COMPRA (componentes hoja) y FABRICACION (componentes/articulos fabricados).
Reutiliza inventario (stock_total_global), BOM y compras. Persiste en mrp_sugerencias. Auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("mrp.planificador")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _stock(codigo, eid):
    try:
        from src.db.stock_almacen import stock_total_global
        return float(stock_total_global(codigo, id_empresa=eid) or 0)
    except Exception:
        return 0.0


def calcular_necesidades(demanda, *, id_empresa=None) -> dict:
    """demanda: {articulo_final: cantidad}. Devuelve necesidades netas por componente."""
    eid = _emp(id_empresa)
    from src.services.mrp import bom as _bom
    brutas = {}
    fabricado = {}
    for articulo, cant in (demanda or {}).items():
        for comp in _bom.explosionar(articulo, float(cant), id_empresa=eid):
            brutas[comp["componente"]] = brutas.get(comp["componente"], 0) + comp["cantidad"]
            fabricado[comp["componente"]] = comp["fabricado"]
        # el propio articulo final tambien es fabricado
        fabricado.setdefault(articulo, True)
    netas = {}
    for comp, bruto in brutas.items():
        neto = round(bruto - _stock(comp, eid), 4)
        if neto > 0:
            netas[comp] = {"neto": neto, "bruto": round(bruto, 4), "fabricado": fabricado.get(comp, False)}
    return netas


def generar_sugerencias(demanda, *, persistir=True, id_empresa=None) -> dict:
    """Genera sugerencias de compra (hoja) y fabricacion (fabricados) a partir de la demanda."""
    eid = _emp(id_empresa)
    netas = calcular_necesidades(demanda, id_empresa=eid)
    compras, fabricacion = [], []
    for comp, info in netas.items():
        destino = fabricacion if info["fabricado"] else compras
        destino.append({"articulo": comp, "cantidad": info["neto"]})
    # Articulos finales de la demanda -> sugerencia de fabricacion
    for articulo, cant in (demanda or {}).items():
        fabricacion.append({"articulo": articulo, "cantidad": float(cant)})
    if persistir:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                for tipo, items in (("compra", compras), ("fabricacion", fabricacion)):
                    for it in items:
                        cur.execute("INSERT INTO mrp_sugerencias (id_empresa, tipo, articulo, cantidad, origen) "
                                    "VALUES (%s,%s,%s,%s,'MRP')", (eid, tipo, it["articulo"], it["cantidad"]))
                conn.commit()
        except Exception as e:
            logger.error("persistir sugerencias: %s", e)
    log_auditoria("mrp", "MRP_SUGERENCIAS", "mrp_sugerencias",
                  f"compra={len(compras)} fabricacion={len(fabricacion)}")
    return {"compras": compras, "fabricacion": fabricacion, "necesidades": netas}


def listar_sugerencias(*, tipo=None, estado="pendiente", id_empresa=None) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM mrp_sugerencias WHERE id_empresa=%s"
    p = [eid]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY creado_en DESC LIMIT 500"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_sugerencias: %s", e)
        return []
