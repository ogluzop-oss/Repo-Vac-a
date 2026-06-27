"""
B7-K — RPO/RTO operativo. Reutiliza dr_pitr (RPO/RTO de backup) y lo AMPLIA al plano operativo:
RPO/RTO por empresa y por tienda en funcion de eventos/operaciones pendientes de sincronizar
(perdida potencial real si cae el edge). No duplica DR: lo complementa.
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.rpo_rto")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def rpo_rto_empresa(*, id_empresa=None) -> dict:
    """RPO/RTO de backup (DR) + pendientes operativos de toda la empresa."""
    eid = _emp(id_empresa)
    base = {"rpo_backup": None, "rto_backup": None}
    try:
        from src.services.dr import dr_pitr
        base["rpo_backup"] = dr_pitr.calcular_rpo().get("rpo_horas")
        base["rto_backup"] = dr_pitr.calcular_rto().get("rto_min")
    except Exception as e:
        logger.debug("dr_pitr: %s", e)
    from src.services.resiliencia import outbox
    m = outbox.metricas(id_empresa=eid)
    base["eventos_pendientes"] = m.get("pendientes", 0)
    base["conflictos"] = m.get("conflictos_abiertos", 0)
    # Perdida potencial: operaciones aun no confirmadas en central.
    base["perdida_potencial_eventos"] = m.get("pendientes", 0)
    return base


def rpo_rto_tienda(id_tienda, *, id_empresa=None) -> dict:
    """RPO/RTO operativo de una tienda concreta (segun su offline_store sin sincronizar)."""
    eid = _emp(id_empresa)
    from src.services.resiliencia import offline_store
    try:
        pend = offline_store.pendientes_sync(eid, id_tienda=id_tienda)
    except Exception:
        pend = {}
    total = sum(pend.values())
    # RTO estimado: ~0.5s por operacion a sincronizar + 5s de arranque.
    rto_seg = round(5 + total * 0.5, 1)
    return {"id_tienda": id_tienda, "pendientes": pend, "perdida_potencial_eventos": total,
            "rto_estimado_seg": rto_seg, "rpo": "ultimo_evento_sincronizado"}


def resumen(*, id_empresa=None) -> dict:
    """Resumen RPO/RTO empresa + por tienda (para dashboard de resiliencia)."""
    eid = _emp(id_empresa)
    from src.services.resiliencia import edge_node
    tiendas = []
    for nodo in edge_node.listar(id_empresa=eid):
        tiendas.append(rpo_rto_tienda(nodo.get("id_tienda", 0), id_empresa=eid))
    return {"empresa": rpo_rto_empresa(id_empresa=eid), "tiendas": tiendas}
