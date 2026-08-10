"""
DR · Backup operacional (Etapa F · Fase F4).

Fachada que COMPONE las capacidades de backup/DR YA EXISTENTES en una superficie operacional única, sin
crear un sistema nuevo (Reglas 6/7):

  · Planificación  → `db.backup.backup_si_corresponde` (+ jobs de `scheduler` y `dr_drills`).
  · Verificación   → `db.backup.verificar_backup` (+ `dr_drills.verify_diario`).
  · Restauración   → total/por tenant/por empresa (`saas.backup_tenant.restaurar_empresa`) y PARCIAL
                     por subconjunto de tablas (`saas.backup_tenant.restaurar_parcial`).
  · Simulacros     → `dr_drills.restore_test_semanal` / `verify_diario` / `consistency_mensual`.
  · Estado         → edad del último backup, RPO/RTO (`dr_pitr`) y últimos simulacros.

Solo delega; degradable; multiempresa. Aditivo y reversible.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("dr.backup_operacional")

FASE = "F4"


# ── Planificación automática ──────────────────────────────────────────────────
def planificar(intervalo_horas: int = 24, *, motivo: str = "programado") -> dict:
    """Crea un backup solo si el último supera `intervalo_horas` (reutiliza `backup_si_corresponde`)."""
    try:
        from src.db import backup
        r = backup.backup_si_corresponde(intervalo_horas=intervalo_horas, motivo=motivo)
        return {"ok": True, "creado": bool(r), "backup": r}
    except Exception as e:
        logger.debug("planificar: %s", e)
        return {"ok": False, "error": str(e)}


def registrar_jobs(id_empresa=None) -> dict:
    """Asegura que los jobs de backup y de simulacros DR están registrados (reutiliza el Scheduler y
    `dr_drills.registrar_jobs_dr`). Degradable."""
    hecho = {}
    try:
        from src.services import scheduler
        if hasattr(scheduler, "registrar_jobs_por_defecto"):
            scheduler.registrar_jobs_por_defecto(id_empresa=id_empresa)
            hecho["scheduler"] = True
    except Exception as e:
        logger.debug("registrar_jobs scheduler: %s", e)
    try:
        from src.services.dr import dr_drills
        dr_drills.registrar_jobs_dr(id_empresa)
        hecho["dr_drills"] = True
    except Exception as e:
        logger.debug("registrar_jobs dr: %s", e)
    return hecho


# ── Verificación automática ───────────────────────────────────────────────────
def verificar(ruta: str | None = None) -> dict:
    """Verifica un backup (o el último). Reutiliza `db.backup.verificar_backup`."""
    try:
        from src.db import backup
        return backup.verificar_backup(ruta)
    except Exception as e:
        logger.debug("verificar: %s", e)
        return {"ok": False, "error": str(e)}


# ── Restauración (total / por tenant-empresa / parcial) ───────────────────────
def restaurar_tenant(ruta, id_empresa=None) -> dict:
    """Restauración COMPLETA por tenant/empresa (reutiliza `backup_tenant.restaurar_empresa`)."""
    from src.services.saas import backup_tenant
    return backup_tenant.restaurar_empresa(ruta, id_empresa=id_empresa)


def restaurar_parcial(ruta, tablas, *, id_empresa=None, reemplazar=True) -> dict:
    """Restauración PARCIAL por subconjunto de tablas (reutiliza `backup_tenant.restaurar_parcial`)."""
    from src.services.saas import backup_tenant
    return backup_tenant.restaurar_parcial(ruta, tablas, id_empresa=id_empresa, reemplazar=reemplazar)


def exportar_tenant(id_empresa=None, *, tablas=None) -> dict:
    """Exporta el tenant (opcionalmente un subconjunto de tablas). Reutiliza `exportar_empresa`."""
    from src.services.saas import backup_tenant
    return backup_tenant.exportar_empresa(id_empresa=id_empresa, tablas=tablas)


# ── Simulacros ────────────────────────────────────────────────────────────────
def simulacro(tipo: str = "restore") -> dict:
    """Ejecuta un simulacro DR: `restore` (restore_test), `verify` (verify_diario) o `consistency`
    (consistency_mensual). Reutiliza `dr_drills`."""
    from src.services.dr import dr_drills
    if tipo == "verify":
        return dr_drills.verify_diario()
    if tipo == "consistency":
        return dr_drills.consistency_mensual()
    return dr_drills.restore_test_semanal()


# ── Estado operacional de backup/DR ───────────────────────────────────────────
def estado(id_empresa=None) -> dict:
    """Foto operacional: edad del último backup, nº de backups, RPO/RTO y últimos simulacros."""
    out = {}
    try:
        from src.db import backup
        out["edad_ultimo_backup_h"] = backup.edad_ultimo_backup_horas()
        out["backups"] = len(backup.listar_backups() or [])
    except Exception as e:
        logger.debug("estado backup: %s", e)
    try:
        from src.services.dr import dr_pitr
        out["rpo"] = dr_pitr.calcular_rpo()
        out["rto"] = dr_pitr.calcular_rto()
    except Exception as e:
        logger.debug("estado rpo/rto: %s", e)
    try:
        from src.services.dr import dr_drills
        out["simulacros_recientes"] = dr_drills.ultimos(limite=10)
    except Exception as e:
        logger.debug("estado drills: %s", e)
    return out


def descriptor() -> dict:
    return {"servicio": "dr.backup_operacional", "etapa": "F", "fase": FASE,
            "estado": "implementado", "motor_nuevo": False,
            "reutiliza": ["db.backup", "saas.backup_tenant", "dr_pitr", "dr_drills", "scheduler"],
            "operaciones": ["planificar", "registrar_jobs", "verificar", "restaurar_tenant",
                            "restaurar_parcial", "exportar_tenant", "simulacro", "estado"]}


__all__ = ["FASE", "planificar", "registrar_jobs", "verificar", "restaurar_tenant",
           "restaurar_parcial", "exportar_tenant", "simulacro", "estado", "descriptor"]
