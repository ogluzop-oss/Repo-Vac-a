"""Jobs del Portal de proveedor (Scheduler existente, opt-in).

`portal_invitaciones_pendientes`: avisa de las invitaciones que el proveedor aún NO ha aceptado (cuenta en
estado 'invitado', sin primera conexión). Reutiliza el Scheduler y las notificaciones; no crea motores
nuevos. Idempotente y best-effort.
"""

from ._common import _conn, _emp, _filas, _notificar, logger

CODIGO_JOB = "portal_invitaciones_pendientes"


def invitaciones_pendientes(id_empresa=None, dias_min=0) -> list:
    """Cuentas invitadas que el proveedor no ha aceptado todavía (estado 'invitado', sin conexión).
    `dias_min` filtra las invitadas hace al menos N días (0 = todas)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT pc.id_proveedor, "
                "COALESCE(p.razon_social, CONCAT('Proveedor ', pc.id_proveedor)) AS proveedor, "
                "pc.email, pc.creado_en FROM portal_proveedor_cuentas pc "
                "LEFT JOIN proveedores p ON p.id_proveedor = pc.id_proveedor "
                "WHERE pc.id_empresa=%s AND pc.estado='invitado' AND pc.ultima_conexion IS NULL "
                "AND pc.creado_en <= (NOW() - INTERVAL %s DAY) ORDER BY pc.creado_en",
                (emp, int(dias_min)))
            return _filas(cur)
    except Exception as e:
        logger.error("invitaciones_pendientes: %s", e)
        return []


def _job_avisar_invitaciones(id_empresa=None) -> str:
    """Job: avisa (una notificación) si hay invitaciones sin aceptar. Devuelve un resumen textual."""
    emp = _emp(id_empresa)
    pend = invitaciones_pendientes(id_empresa=emp)
    if pend:
        nombres = ", ".join(str(x.get("proveedor")) for x in pend[:8])
        if len(pend) > 8:
            nombres += "…"
        _notificar("portal_invitaciones_pendientes",
                   f"Portal de proveedor: {len(pend)} invitación(es) sin aceptar",
                   f"Proveedores que aún no han entrado al portal: {nombres}.",
                   id_empresa=emp, prioridad="normal")
    return f"invitaciones_pendientes={len(pend)}"


def registrar_jobs_portal(id_empresa=None):
    """Registra el job de invitaciones pendientes en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar(CODIGO_JOB, _job_avisar_invitaciones)
        scheduler.registrar_job(CODIGO_JOB, intervalo_horas=24,
                                descripcion="Portal de proveedor: aviso de invitaciones sin aceptar",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_portal: %s", e)
