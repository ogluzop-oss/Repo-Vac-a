"""
Control de uso, coste, reventa y facturación de voz (ElevenLabs/SOMA) — Fase A+B+C (migración
0285: `empresas.voice_monthly_limit_chars` + `voice_billing_config` + `voice_usage_logs` +
`voz_facturacion_periodos`). Mismo rigor que el resto de la suite SaaS/IA (BD real,
`pytest.mark.db`): NO se mockea la fórmula de margen (`pvp_sugerido`, reutilizada tal cual) — eso
es justo lo que se está verificando.

La prueba de aislamiento (`resumen_uso_voz` filtrado por empresa vs. `resumen_global_voz` SIN
filtro, sembrando 2+ empresas) es la más importante de todo el módulo: verifica la frontera de
seguridad documentada en `gui/saas_admin.py`/`services/saas/voz_plan.py` (SUPERADMIN es un rol por
tenant, no una identidad de plataforma) — el panel de cliente NUNCA debe filtrarse con datos de
otra empresa, y el panel del Fundador sí debe sumarlas todas.

Limpieza: `Fabrica.empresa()` ya borra la fila de `empresas` al terminar, pero todavía no conoce
las tablas nuevas de este módulo — se registra una limpieza adicional (`fab.al_limpiar`) para
`voice_usage_logs`/`voz_facturacion_periodos`/`facturas_saas`/`pagos_saas` de cada empresa de
prueba, mismo criterio que `tests/integration/test_saas.py::_limpia`.
"""

import pytest

from src.db.conexion import obtener_conexion
from src.services import voz_control_uso as VCU
from src.services.compras.precios_dinamicos import pvp_sugerido
from src.services.saas import facturacion_voz as FACT_VOZ
from src.services.saas import voz_plan as VOZ_PLAN

pytestmark = pytest.mark.db


def _limpiar_voz(eid):
    with obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("voz_facturacion_periodos", "voice_usage_logs", "pagos_saas", "facturas_saas"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (eid,))
        conn.commit()


@pytest.fixture
def emp_voz(fab):
    """Empresa de prueba (vía `Fabrica`, con `voice_monthly_limit_chars` NULL por defecto) + la
    limpieza adicional que `Fabrica` todavía no cubre para las tablas de este módulo."""
    eid = fab.empresa("Empresa Voz Test")
    fab.al_limpiar(lambda: _limpiar_voz(eid))
    return eid


# ── Fase A: cálculo de coste real + margen de reventa ────────────────────────
def test_registrar_uso_voz_calcula_coste_y_margen_a_precision_de_ledger(emp_voz):
    """`billed_amount_usd` se calcula a la MISMA precisión que la columna (DECIMAL(12,8)), NO vía
    `pvp_sugerido` directamente — esa función redondea a 2 decimales (pensada para un precio de
    venta al público, p. ej. 19,99€), lo que en una fila de una sola síntesis (fracciones de
    céntimo) dejaría `billed_amount_usd` en 0.00 para cantidades pequeñas. Ver docstring de
    `registrar_uso_voz`. Se verifica con una cantidad GRANDE (donde ambos cálculos coinciden,
    confirma que el margen se aplica) y con una PEQUEÑA/realista (donde solo el cálculo a
    precisión de ledger evita el 0.00 — esa es la regresión real que se está guardando)."""
    coste_per_char, margen_pct = VCU.tarifa_actual()
    character_count = 200_000

    r = VCU.registrar_uso_voz(emp_voz, None, "voice-test-1", character_count)

    coste_esperado = round(character_count * coste_per_char, 8)
    billed_esperado = round(coste_esperado * (1 + margen_pct / 100.0), 8)

    assert r["character_count"] == character_count
    assert r["cost_basis_usd"] == pytest.approx(coste_esperado, abs=1e-8)
    assert r["billed_amount_usd"] == pytest.approx(billed_esperado, abs=1e-8)
    assert r["billed_amount_usd"] > r["cost_basis_usd"], "el margen de reventa debe quedar aplicado"
    # A esta magnitud, el redondeo a 2dp de pvp_sugerido coincide por coincidencia — confirma que
    # la fórmula (coste × margen%) es la MISMA, solo calculada a más precisión.
    assert r["billed_amount_usd"] == pytest.approx(pvp_sugerido(coste_esperado, margen_pct), abs=0.01)

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT character_count, cost_basis_usd, billed_amount_usd FROM voice_usage_logs "
            "WHERE id_empresa=%s ORDER BY id DESC LIMIT 1", (emp_voz,)
        )
        fila = cur.fetchone()
    assert int(fila[0]) == character_count
    assert float(fila[1]) == pytest.approx(coste_esperado, abs=1e-8)
    assert float(fila[2]) == pytest.approx(billed_esperado, abs=1e-8)


def test_registrar_uso_voz_frase_corta_no_se_redondea_a_cero(emp_voz):
    """Regresión: una frase típica de SOMA ('¿Qué necesitas?', 16 caracteres) tiene un coste real
    de fracciones de céntimo — `billed_amount_usd` debe reflejarlo (>0), NUNCA 0.00 por un
    redondeo a 2 decimales aplicado fila a fila (ese redondeo es correcto SOLO al facturar el
    acumulado del periodo, en `facturacion_voz.py`, nunca aquí)."""
    coste_per_char, margen_pct = VCU.tarifa_actual()
    character_count = 16

    r = VCU.registrar_uso_voz(emp_voz, None, "voice-test-corta", character_count)

    coste_esperado = round(character_count * coste_per_char, 8)
    billed_esperado = round(coste_esperado * (1 + margen_pct / 100.0), 8)
    assert coste_esperado > 0, "la tarifa semilla debe producir coste>0 incluso para 16 caracteres"
    assert r["billed_amount_usd"] == pytest.approx(billed_esperado, abs=1e-8)
    assert r["billed_amount_usd"] > 0, (
        "una frase corta real NUNCA debe facturarse a 0.00 — esto perdería ingresos "
        "sistemáticamente para la mayoría de las frases que dice SOMA"
    )


# ── Fase A: control de acceso / cuota mensual ────────────────────────────────
def test_verificar_acceso_voz_bloquea_al_superar_limite_mensual_sembrado(emp_voz):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE empresas SET voice_monthly_limit_chars=%s WHERE id_empresa=%s",
                    (100, emp_voz))
        conn.commit()

    VCU.registrar_uso_voz(emp_voz, None, "voice-test-2", 60)
    VCU.verificar_acceso_voz(emp_voz)   # 60 < 100: todavía no bloquea

    VCU.registrar_uso_voz(emp_voz, None, "voice-test-2", 60)   # acumulado 120 >= 100
    with pytest.raises(VCU.LimiteUsoVozExcedido):
        VCU.verificar_acceso_voz(emp_voz)


def test_verificar_acceso_voz_sin_limite_nunca_bloquea(emp_voz):
    # `voice_monthly_limit_chars` queda NULL por defecto (Fabrica.empresa no lo fija) → sin
    # límite configurado, por mucho que se registre, nunca debe bloquear.
    VCU.registrar_uso_voz(emp_voz, None, "voice-test-3", 50_000_000)
    VCU.verificar_acceso_voz(emp_voz)   # no debe lanzar


# ── Fase B: facturación separada (idempotencia + importe CON margen) ────────
def test_facturar_uso_voz_empresa_idempotente_y_cobra_el_importe_con_margen(emp_voz):
    VCU.registrar_uso_voz(emp_voz, None, "voice-test-4", 500_000)

    r1 = FACT_VOZ.facturar_uso_voz_empresa(emp_voz)
    assert r1["facturado"] is True
    assert r1["importe"] > 0

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(cost_basis_usd),0), COALESCE(SUM(billed_amount_usd),0) "
            "FROM voice_usage_logs WHERE id_empresa=%s", (emp_voz,)
        )
        coste_total, facturado_total = cur.fetchone()
    coste_total, facturado_total = float(coste_total), float(facturado_total)

    # El importe facturado es el FACTURADO (con margen) — no el coste base del proveedor.
    assert facturado_total > coste_total
    assert r1["importe"] == pytest.approx(round(facturado_total, 2), abs=0.01)

    # Segunda corrida INMEDIATA: nada pendiente nuevo desde el período ya facturado →
    # NO se cobra dos veces el mismo uso (idempotencia por `voz_facturacion_periodos`).
    r2 = FACT_VOZ.facturar_uso_voz_empresa(emp_voz)
    assert r2["facturado"] is False

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM facturas_saas WHERE id_empresa=%s AND concepto='voz_uso'",
            (emp_voz,)
        )
        n_facturas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM voz_facturacion_periodos WHERE id_empresa=%s", (emp_voz,))
        n_periodos = cur.fetchone()[0]
    assert n_facturas == 1
    assert n_periodos == 1


# ── Fase C: aislamiento self-service vs. panel global (SIN filtro) ──────────
def test_resumen_uso_voz_aisla_por_empresa_y_resumen_global_suma_todas(fab):
    eid_a = fab.empresa("Empresa Voz A")
    eid_b = fab.empresa("Empresa Voz B")
    fab.al_limpiar(lambda: _limpiar_voz(eid_a))
    fab.al_limpiar(lambda: _limpiar_voz(eid_b))

    VCU.registrar_uso_voz(eid_a, None, "voice-a", 100_000)
    VCU.registrar_uso_voz(eid_b, None, "voice-b", 300_000)

    resumen_a = VOZ_PLAN.resumen_uso_voz(eid_a)
    resumen_b = VOZ_PLAN.resumen_uso_voz(eid_b)

    # AISLAMIENTO: el resumen de A no debe reflejar NADA del consumo de B, y viceversa — esta es
    # la verificación crítica de seguridad del módulo.
    assert resumen_a["caracteres_mes"] == 100_000
    assert resumen_b["caracteres_mes"] == 300_000
    assert resumen_a["facturado_mes_usd"] != resumen_b["facturado_mes_usd"]

    glob = VOZ_PLAN.resumen_global_voz()
    por_empresa = {fila["id_empresa"]: fila for fila in glob["por_empresa"]}

    # El panel GLOBAL (plataforma, sin filtro) sí debe ver a AMBAS empresas correctamente.
    assert por_empresa[eid_a]["caracteres"] == 100_000
    assert por_empresa[eid_b]["caracteres"] == 300_000
    assert glob["coste_total_usd"] >= por_empresa[eid_a]["coste_usd"] + por_empresa[eid_b]["coste_usd"] - 1e-6
    assert glob["margen_total_usd"] == pytest.approx(
        glob["facturado_total_usd"] - glob["coste_total_usd"], abs=1e-6
    )


def test_actualizar_tarifa_global_y_cambiar_limite_voz_autoservicio(emp_voz):
    original = VCU.tarifa_actual()
    try:
        r = VOZ_PLAN.actualizar_tarifa_global(0.00005, 50.0, actualizado_por="tester@local")
        assert r["cost_basis_per_char_usd"] == pytest.approx(0.00005, abs=1e-8)
        assert r["margen_pct"] == pytest.approx(50.0, abs=1e-6)
        assert VCU.tarifa_actual() == (pytest.approx(0.00005, abs=1e-8), pytest.approx(50.0, abs=1e-6))
    finally:
        VOZ_PLAN.actualizar_tarifa_global(original[0], original[1], actualizado_por="tester@local")

    resumen = VOZ_PLAN.cambiar_limite_voz(emp_voz, 5000)
    assert resumen["limite_mensual_chars"] == 5000
    resumen_sin_limite = VOZ_PLAN.cambiar_limite_voz(emp_voz, None)
    assert resumen_sin_limite["limite_mensual_chars"] is None
