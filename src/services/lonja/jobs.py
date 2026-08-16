"""Jobs de la Lonja (Scheduler existente).

`lonja_cierre_subastas`: cierra las subastas cuya `fecha_limite` ya pasó — adjudica a la mejor puja (que
crea el pedido de la ganadora y avisa) o, si no hubo pujas, marca el listado 'cerrado'. Idempotente y
seguro (la adjudicación usa bloqueo de fila). Se registra como job LIGERO (activo por defecto).
"""

from ._common import _conn, _filas, logger
from . import transacciones as _t

CODIGO_JOB = "lonja_cierre_subastas"


def subastas_vencidas() -> list:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id FROM lonja_listados WHERE estado='activo' AND permite_puja=1 "
                        "AND fecha_limite IS NOT NULL AND fecha_limite < NOW()")
            return [r["id"] for r in _filas(cur)]
    except Exception as e:
        logger.error("subastas_vencidas: %s", e)
        return []


def cerrar_subastas_vencidas() -> dict:
    adjudicadas = cerradas = 0
    for lid in subastas_vencidas():
        try:
            if _t.mejor_puja(lid):
                if _t.adjudicar(lid).get("ok"):
                    adjudicadas += 1
            else:
                with _conn() as c, c.cursor() as cur:
                    cur.execute("UPDATE lonja_listados SET estado='cerrado' WHERE id=%s AND estado='activo'",
                                (lid,))
                    cerradas += 1 if cur.rowcount > 0 else 0
                    c.commit()
        except Exception as e:
            logger.debug("cerrar subasta %s: %s", lid, e)
    return {"adjudicadas": adjudicadas, "cerradas": cerradas}


def _job_cierre_subastas(id_empresa=None) -> str:
    r = cerrar_subastas_vencidas()
    return f"adjudicadas={r['adjudicadas']} cerradas={r['cerradas']}"


def registrar_jobs_lonja(id_empresa=None):
    """Registra el job de cierre de subastas en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar(CODIGO_JOB, _job_cierre_subastas)
        scheduler.registrar_job(CODIGO_JOB, intervalo_horas=1,
                                descripcion="Lonja: cierre de subastas vencidas", id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_lonja: %s", e)
