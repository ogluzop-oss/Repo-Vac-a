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
    adjudicadas = cerradas = desiertas = 0
    for lid in subastas_vencidas():
        try:
            if _t.mejor_puja(lid):
                res = _t.adjudicar(lid)
                if res.get("ok"):
                    adjudicadas += 1
                elif res.get("error") == "reserva_no_alcanzada":
                    # Hubo pujas pero ninguna alcanzó el precio de reserva → desierta.
                    with _conn() as c, c.cursor() as cur:
                        cur.execute("UPDATE lonja_listados SET estado='desierta' WHERE id=%s "
                                    "AND estado='activo'", (lid,))
                        desiertas += 1 if cur.rowcount > 0 else 0
                        c.commit()
            else:
                with _conn() as c, c.cursor() as cur:
                    cur.execute("UPDATE lonja_listados SET estado='cerrado' WHERE id=%s AND estado='activo'",
                                (lid,))
                    cerradas += 1 if cur.rowcount > 0 else 0
                    c.commit()
        except Exception as e:
            logger.debug("cerrar subasta %s: %s", lid, e)
    return {"adjudicadas": adjudicadas, "cerradas": cerradas, "desiertas": desiertas}


def subastas_por_vencer(minutos=30) -> list:
    """Subastas ACTIVAS que caducan en los próximos `minutos` (para avisar de "por vencer")."""
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_vendedor, codigo_articulo, fecha_limite FROM lonja_listados "
                        "WHERE estado='activo' AND permite_puja=1 AND fecha_limite IS NOT NULL "
                        "AND fecha_limite > NOW() AND fecha_limite <= (NOW() + INTERVAL %s MINUTE)",
                        (int(minutos),))
            return _filas(cur)
    except Exception as e:
        logger.error("subastas_por_vencer: %s", e)
        return []


def _job_cierre_subastas(id_empresa=None) -> str:
    r = cerrar_subastas_vencidas()
    # Aviso "por vencer" a los vendedores con subastas a punto de caducar.
    try:
        from . import avisos as _av
        for s in subastas_por_vencer(30):
            _av.avisar_vendedor(s["id_vendedor"], "LONJA_POR_VENCER",
                                f"listado={s['id']} caduca={s.get('fecha_limite')}")
    except Exception:
        pass
    return f"adjudicadas={r['adjudicadas']} cerradas={r['cerradas']} desiertas={r['desiertas']}"


def registrar_jobs_lonja(id_empresa=None):
    """Registra el job de cierre de subastas en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar(CODIGO_JOB, _job_cierre_subastas)
        scheduler.registrar_job(CODIGO_JOB, intervalo_horas=1,
                                descripcion="Lonja: cierre de subastas vencidas", id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_lonja: %s", e)
