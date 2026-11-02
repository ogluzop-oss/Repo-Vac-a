"""
Administración del PLAN de consumo de IA (Anthropic) por empresa — Fase C (panel de
administración) del control de uso/coste de IA. Construida ENCIMA de la fundación de Fase A
(`services/ia_control_uso.py`): reutiliza sus mismos límites de día/mes UTC (`_inicio_dia_utc`/
`_inicio_mes_utc`) y su mismo esquema (`empresas.ai_*` + `ai_usage_logs`) — no reimplementa ni un
segundo cálculo de fechas ni una segunda fuente de coste.

Mismo alcance/disciplina que `services/saas/suscripciones.py` (self-service de la empresa activa,
nunca cross-tenant): estas funciones reciben `id_empresa` explícito y NO lo resuelven ellas mismas
de la sesión — el llamador (GUI vía `_empresa()`, API vía el contexto autenticado del token/clave)
es quien decide a qué empresa aplican, siguiendo exactamente la misma regla que ya documenta
`api/security.py` ("el id_empresa sale SIEMPRE del token/clave, nunca del cuerpo").
"""

import logging

from src.db.conexion import obtener_conexion
from src.services.ia_control_uso import _inicio_dia_utc, _inicio_mes_utc

logger = logging.getLogger("saas.ia_plan")

PLANES_IA = ("LIMITED", "PAY_AS_YOU_GO")


def _fila_empresa(cur, id_empresa):
    cur.execute(
        "SELECT ai_plan_type, ai_daily_cost_limit_usd, ai_status FROM empresas WHERE id_empresa=%s",
        (id_empresa,),
    )
    return cur.fetchone()


def resumen_uso_ia(id_empresa) -> dict:
    """Resumen de plan/estado/gasto de IA de `id_empresa` para el panel de administración
    (escritorio y API):

    {plan_type, ai_status, gasto_hoy_usd, gasto_mes_usd, limite_diario_usd,
     porcentaje_limite_usado}

    `gasto_hoy_usd`/`gasto_mes_usd` sobre `ai_usage_logs.estimated_cost_usd` con los MISMOS
    límites UTC (día/mes) que `ia_control_uso.verificar_acceso_ia` usa para decidir el bloqueo —
    así el panel nunca muestra un porcentaje que no cuadre con la razón real de un bloqueo.
    `porcentaje_limite_usado` se calcula siempre (aunque el plan sea PAY_AS_YOU_GO, con el límite
    configurado aunque no se aplique) para que la GUI pueda mostrarlo también si el usuario cambia
    de opinión y vuelve a LIMITED; queda en 0.0 si no hay empresa o el límite es 0.
    """
    with obtener_conexion() as conn, conn.cursor() as cur:
        fila = _fila_empresa(cur, id_empresa)
        if not fila:
            logger.warning("resumen_uso_ia: empresa '%s' no encontrada.", id_empresa)
            return {
                "plan_type": None, "ai_status": None,
                "gasto_hoy_usd": 0.0, "gasto_mes_usd": 0.0,
                "limite_diario_usd": 0.0, "porcentaje_limite_usado": 0.0,
            }
        plan, limite, estado = fila[0], float(fila[1] or 0), fila[2]

        cur.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM ai_usage_logs "
            "WHERE id_empresa=%s AND creado >= %s",
            (id_empresa, _inicio_dia_utc()),
        )
        gasto_hoy = float(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM ai_usage_logs "
            "WHERE id_empresa=%s AND creado >= %s",
            (id_empresa, _inicio_mes_utc()),
        )
        gasto_mes = float(cur.fetchone()[0] or 0)

    pct = round((gasto_hoy / limite) * 100, 2) if limite > 0 else 0.0
    return {
        "plan_type": plan,
        "ai_status": estado,
        "gasto_hoy_usd": round(gasto_hoy, 2),
        "gasto_mes_usd": round(gasto_mes, 2),
        "limite_diario_usd": round(limite, 2),
        "porcentaje_limite_usado": pct,
    }


def cambiar_plan_ia(id_empresa, nuevo_plan) -> dict:
    """Cambia la modalidad de consumo de IA de `id_empresa` a `nuevo_plan`
    (`LIMITED`/`PAY_AS_YOU_GO`, valida estrictamente contra `PLANES_IA`).

    Al pasar a `PAY_AS_YOU_GO` se resetea `ai_status='ACTIVE'` INMEDIATAMENTE — una empresa que
    estuviera `BLOCKED_DAILY_LIMIT` queda desbloqueada en el acto (no hace falta esperar a la
    siguiente llamada de `verificar_acceso_ia`, que de todos modos también se auto-sana, pero solo
    la PRÓXIMA vez que alguien intente usar la IA; aquí se hace ya para que el panel refleje el
    desbloqueo sin una llamada de IA de por medio).

    Devuelve el resumen actualizado (`resumen_uso_ia`), para que el llamador (GUI/API) pueda
    refrescar su vista con un único round-trip.
    """
    nuevo_plan = (nuevo_plan or "").strip().upper()
    if nuevo_plan not in PLANES_IA:
        raise ValueError(f"plan de IA inválido: {nuevo_plan!r} (válidos: {PLANES_IA})")

    with obtener_conexion() as conn, conn.cursor() as cur:
        if nuevo_plan == "PAY_AS_YOU_GO":
            cur.execute(
                "UPDATE empresas SET ai_plan_type=%s, ai_status='ACTIVE' WHERE id_empresa=%s",
                (nuevo_plan, id_empresa),
            )
        else:
            cur.execute(
                "UPDATE empresas SET ai_plan_type=%s WHERE id_empresa=%s",
                (nuevo_plan, id_empresa),
            )
        conn.commit()

    _audit("AI_PLAN_CAMBIADO", id_empresa, f"nuevo_plan={nuevo_plan}")
    return resumen_uso_ia(id_empresa)


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "ia_plan", f"{id_empresa}: {detalle}")
    except Exception:
        pass
