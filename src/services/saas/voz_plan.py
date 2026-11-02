"""
Administración del uso/tarifa de voz (ElevenLabs/SOMA) — Fase C (panel de administración) del
control de uso/coste/reventa de voz. Construida ENCIMA de la fundación de Fase A
(`services/voz_control_uso.py`): reutiliza su mismo límite de mes UTC (`_inicio_mes_utc`, vía
`ia_control_uso`) y su mismo esquema (`empresas.voice_monthly_limit_chars` +
`voice_billing_config` + `voice_usage_logs`) — no reimplementa ni un segundo cálculo de fechas ni
una segunda fuente de coste.

Mitad self-service / mitad plataforma, EXACTAMENTE con la frontera de seguridad que ya documenta
`gui/saas_admin.py` (líneas ~96-102): SUPERADMIN es un rol interno de CADA empresa cliente, no una
identidad de plataforma, así que las funciones de aquí se dividen en dos grupos nítidos:

- **Self-service** (consumidas por `saas_admin.py`, SIEMPRE con `id_empresa` explícito de la
  empresa activa, nunca cross-tenant — mismo criterio que `saas/ia_plan.py`):
  `resumen_uso_voz(id_empresa)`, `cambiar_limite_voz(id_empresa, nuevo_limite)`.
- **Plataforma** (consumidas SOLO por `backend_central/rutas_admin.py`, el Panel del Fundador —
  cuenta única sin relación con ningún tenant, igual que `services/saas/metricas.py::resumen()`):
  `resumen_global_voz()` (sin filtro de empresa, a propósito) y
  `actualizar_tarifa_global(...)` (única función que escribe `voice_billing_config`).

REGLA PERMANENTE: `resumen_uso_voz` jamás debe devolver ni agregar datos de otra empresa que la
pedida; `resumen_global_voz` es la ÚNICA función de este módulo sin ese filtro, y por eso nunca se
expone desde `saas_admin.py` ni desde ningún endpoint de tenant.
"""

import logging

from src.db.conexion import obtener_conexion
from src.services.ia_control_uso import _inicio_mes_utc

logger = logging.getLogger("saas.voz_plan")


# ============================================================
# SELF-SERVICE (por empresa — consumido por saas_admin.py)
# ============================================================
def resumen_uso_voz(id_empresa) -> dict:
    """Resumen de uso/coste/facturado de voz de ESTE MES para `id_empresa` (panel de CLIENTE,
    self-service, mismo shape/criterio que `ia_plan.resumen_uso_ia`):

    {caracteres_mes, coste_mes_usd, facturado_mes_usd, limite_mensual_chars,
     porcentaje_limite_usado}

    `limite_mensual_chars` puede ser `None` (sin límite configurado); en ese caso
    `porcentaje_limite_usado` queda en 0.0 (no hay límite contra el que calcular un %)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT voice_monthly_limit_chars FROM empresas WHERE id_empresa=%s",
            (id_empresa,),
        )
        fila = cur.fetchone()
        if not fila:
            logger.warning("resumen_uso_voz: empresa '%s' no encontrada.", id_empresa)
            return {
                "caracteres_mes": 0, "coste_mes_usd": 0.0, "facturado_mes_usd": 0.0,
                "limite_mensual_chars": None, "porcentaje_limite_usado": 0.0,
            }
        limite = fila[0]
        limite = int(limite) if limite is not None else None

        cur.execute(
            "SELECT COALESCE(SUM(character_count), 0), COALESCE(SUM(cost_basis_usd), 0), "
            "COALESCE(SUM(billed_amount_usd), 0) FROM voice_usage_logs "
            "WHERE id_empresa=%s AND creado >= %s",
            (id_empresa, _inicio_mes_utc()),
        )
        caracteres, coste, facturado = cur.fetchone()
        caracteres = int(caracteres or 0)
        coste = float(coste or 0)
        facturado = float(facturado or 0)

    pct = round((caracteres / limite) * 100, 2) if limite else 0.0
    return {
        "caracteres_mes": caracteres,
        "coste_mes_usd": round(coste, 6),
        "facturado_mes_usd": round(facturado, 6),
        "limite_mensual_chars": limite,
        "porcentaje_limite_usado": pct,
    }


def cambiar_limite_voz(id_empresa, nuevo_limite_o_none) -> dict:
    """Ajusta la cuota de SEGURIDAD mensual de caracteres de voz de `id_empresa` (self-service,
    límite propio — NUNCA el precio/margen de reventa, eso es solo de plataforma).
    `nuevo_limite_o_none=None` quita el límite (sin cuota). Devuelve el resumen actualizado
    (`resumen_uso_voz`), mismo criterio que `ia_plan.cambiar_plan_ia`."""
    if nuevo_limite_o_none is not None:
        nuevo_limite_o_none = int(nuevo_limite_o_none)
        if nuevo_limite_o_none < 0:
            raise ValueError("el límite mensual de caracteres no puede ser negativo")

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE empresas SET voice_monthly_limit_chars=%s WHERE id_empresa=%s",
            (nuevo_limite_o_none, id_empresa),
        )
        conn.commit()

    _audit("VOZ_LIMITE_CAMBIADO", id_empresa, f"nuevo_limite={nuevo_limite_o_none}")
    return resumen_uso_voz(id_empresa)


# ============================================================
# PLATAFORMA (global, SIN filtro de empresa — SOLO Panel del Fundador)
# ============================================================
def resumen_global_voz() -> dict:
    """Desglose GLOBAL de coste real vs. facturado (con margen) de voz, de TODAS las empresas —
    SIN filtro, mismo criterio que `services/saas/metricas.py::resumen()`. Solo para el Panel del
    Fundador (`backend_central/rutas_admin.py`); JAMÁS se expone desde `saas_admin.py` ni desde
    ningún endpoint de tenant (ver cabecera del módulo).

    {coste_total_usd, facturado_total_usd, margen_total_usd, por_empresa: [
        {id_empresa, caracteres, coste_usd, facturado_usd}, ...]}"""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(cost_basis_usd),0), COALESCE(SUM(billed_amount_usd),0) "
            "FROM voice_usage_logs"
        )
        coste_total, facturado_total = cur.fetchone()
        coste_total = float(coste_total or 0)
        facturado_total = float(facturado_total or 0)

        cur.execute(
            "SELECT id_empresa, COALESCE(SUM(character_count),0), COALESCE(SUM(cost_basis_usd),0), "
            "COALESCE(SUM(billed_amount_usd),0) FROM voice_usage_logs "
            "GROUP BY id_empresa ORDER BY SUM(billed_amount_usd) DESC"
        )
        filas = cur.fetchall()

    por_empresa = [
        {"id_empresa": r[0], "caracteres": int(r[1] or 0),
         "coste_usd": round(float(r[2] or 0), 6), "facturado_usd": round(float(r[3] or 0), 6)}
        for r in filas
    ]
    return {
        "coste_total_usd": round(coste_total, 6),
        "facturado_total_usd": round(facturado_total, 6),
        "margen_total_usd": round(facturado_total - coste_total, 6),
        "por_empresa": por_empresa,
    }


def actualizar_tarifa_global(cost_basis_per_char_usd, margen_pct, actualizado_por=None) -> dict:
    """ÚNICA función que escribe `voice_billing_config` (la fila global id=1). Solo para el Panel
    del Fundador — la tarifa/margen de reventa es una decisión de PLATAFORMA, nunca self-service
    de una empresa cliente."""
    cost_basis_per_char_usd = float(cost_basis_per_char_usd)
    margen_pct = float(margen_pct)
    if cost_basis_per_char_usd < 0 or margen_pct < 0:
        raise ValueError("coste por carácter y margen deben ser valores no negativos")

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE voice_billing_config SET cost_basis_per_char_usd=%s, margen_pct=%s, "
            "actualizado_por=%s, actualizado_en=UTC_TIMESTAMP() WHERE id=1",
            (cost_basis_per_char_usd, margen_pct, actualizado_por),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO voice_billing_config (id, cost_basis_per_char_usd, margen_pct, "
                "actualizado_por) VALUES (1,%s,%s,%s)",
                (cost_basis_per_char_usd, margen_pct, actualizado_por),
            )
        conn.commit()

    _audit("VOZ_TARIFA_CAMBIADA", None,
           f"coste={cost_basis_per_char_usd} margen={margen_pct}% por={actualizado_por}")
    from src.services.voz_control_uso import tarifa_actual
    coste, margen = tarifa_actual()
    return {"cost_basis_per_char_usd": coste, "margen_pct": margen}


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "voz_plan", f"{id_empresa}: {detalle}")
    except Exception:
        pass
