"""
Motor de recomendaciones (SUBFASE 5). La IA SUGIERE acciones; NUNCA las ejecuta. Cada
recomendacion propone el circuito Workflow/BPM adecuado — la ejecucion queda delegada al
Workflow existente y siempre bajo decision humana.
"""

from src.services.ia import adaptadores as A
from src.services.ia import configuracion as C
from src.services.ia.modelos import Recomendacion


def generar(id_empresa=None, *, limite=30) -> list:
    if not C.activo("recomendaciones", id_empresa):
        return []
    rec = []
    # ── Reposicion ──
    for a in A.articulos_bajo_umbral(id_empresa)[:20]:
        rec.append(Recomendacion(
            "Reponer articulo",
            f"{a['codigo']} por debajo del umbral (tienda {a['stock_tienda']}/{a['objetivo']}, "
            f"almacen {a['stock_almacen']})",
            "articulo", str(a["codigo"]), "ALTA", workflow="compras_pedido", datos=a))
    # ── Exceso de stock ──
    for a in A.articulos_exceso(id_empresa)[:10]:
        rec.append(Recomendacion(
            "Reducir / mover stock", f"{a['codigo']} en exceso (+{a['exceso']} sobre objetivo)",
            "articulo", str(a["codigo"]), "MEDIA", datos=a))
    # ── Facturas pendientes ──
    fp = A.facturas_pendientes(id_empresa)
    if fp:
        rec.append(Recomendacion("Revisar cobro de facturas",
                                 f"{len(fp)} facturas pendientes de cobro", "facturacion", "",
                                 "ALTA", workflow="tesoreria_pago"))
    # ── Contratos por vencer ──
    cv = A.contratos_por_vencer(id_empresa)
    if cv:
        rec.append(Recomendacion("Revisar contratos por vencer",
                                 f"{len(cv)} contratos vencen en 30 dias", "rrhh", "", "MEDIA",
                                 workflow="rrhh_vacaciones"))
    # ── Sincronizaciones fallidas → resync ──
    sync = A.sincronizacion(id_empresa)
    if int(sync.get("global", {}).get("errores") or 0) > 0:
        rec.append(Recomendacion("Reintentar sincronizacion",
                                 "Hay sincronizaciones con error", "sincronizacion", "", "MEDIA"))
    return rec[:limite]
