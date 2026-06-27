"""
Replicacion y failover (DR-B) — arquitectura preparada, sin dependencias cloud.

Lee la configuracion de replica desde env (SM_DR_REPLICA_*). Sin replica configurada, informa
'no_configurada' (no rompe). Expone el estado y operaciones manuales; el failover automatico y la
sincronizacion real requieren infraestructura externa (MariaDB replication) documentada en el runbook.
"""

import logging
import os

logger = logging.getLogger("dr.replicacion")


def configurada() -> bool:
    return bool(os.getenv("SM_DR_REPLICA_HOST"))


def estado_replicacion() -> dict:
    if not configurada():
        return {"estado": "no_configurada", "primaria": True, "replica": None}
    return {"estado": "configurada", "primaria": True,
            "replica": os.getenv("SM_DR_REPLICA_HOST"), "modo": os.getenv("SM_DR_REPLICA_MODO", "async")}


def sincronizar_replicas() -> dict:
    """Punto de extension: la sincronizacion real la gestiona MariaDB replication."""
    if not configurada():
        return {"ok": False, "estado": "no_configurada"}
    _audit("DR_REPLICA_SYNC", os.getenv("SM_DR_REPLICA_HOST"))
    return {"ok": True, "estado": "delegado_a_mariadb"}


def promover_replica() -> dict:
    """Failover manual: marca intencion de promocion (la ejecucion la realiza el operador/infra)."""
    if not configurada():
        return {"ok": False, "estado": "no_configurada"}
    _audit("DR_FAILOVER", "promocion_replica_solicitada")
    return {"ok": True, "estado": "promocion_solicitada"}


def validar_consistencia() -> dict:
    """Comprobacion basica (BD accesible). La consistencia entre nodos requiere infra externa."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            ok = cur.fetchone() is not None
        return {"ok": ok, "primaria_accesible": ok}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("dr", accion, "dr_snapshots", detalle)
    except Exception:
        pass
