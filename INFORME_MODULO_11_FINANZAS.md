# Informe Técnico — Módulo 11: Finanzas

**Auditoría (ya existía):** presupuestos financieros (versiones/escenarios/real-vs-ppto/forecast de
cierre — `finanzas/presupuestos.py`), financiación (préstamo/leasing/renting/póliza con cuadro de
amortización francés + vencimientos AP — `finanzas/financiacion.py`), crédito/scoring
(`finanzas/credito.py`), ratios EBITDA/ROE/CCC (`finanzas/ratios.py`), simulación what-if
(`finanzas/simulacion.py`), IA financiera (`finanzas/ia.py`), y toda la **tesorería** (posición,
cash flow, previsión, conciliación CSV/N43/CAMT, SEPA pain.001/008).

**Gaps implementados (migr 0111):**
- **Inmovilizado / activos fijos** (`finanzas/inmovilizado.py` + `inmovilizado_activos`/
  `inmovilizado_amortizaciones`): `alta_activo`, `plan_amortizacion` (lineal, última cuota ajusta al
  valor residual), `dotar_amortizacion` (idempotente por periodo; encola asiento 681→281x en la cola
  contable existente si está disponible), `valor_neto_contable`, `baja_activo`, `listar_activos`.
  Antes el inmovilizado solo existía como grupo del PGC, sin registro de bienes.
- **Centros de coste / contabilidad analítica** (`finanzas/centros_coste.py` + `centros_coste`/
  `imputaciones_analiticas`): `crear_centro` (jerárquico), `imputar` (gasto/ingreso desde cualquier
  origen: nómina/compra/amortización/manual), `resultado_por_centro` (ingresos−gastos por centro y
  periodo). Dimensión analítica transversal genuinamente ausente.

**Reutilización:** cola contable existente para el asiento de dotación; el inmovilizado enlaza a
centro de coste; auditoría; multiempresa. NO recalcula tesorería/ratios (ya existían).

**Pruebas:** migr 0111; activo 24.000€/48m → cuota 500, dotación 2026-01 (idempotente), VNC 23.500€;
centro de coste con ingreso 3.000 − gasto 800 = 2.200€. **smoke 5 passed.** (Corregido en el acto un
`VARCHAR(6)` insuficiente para 'ingreso' → `VARCHAR(10)` + ALTER idempotente en la migración.)

**Mejoras futuras:** métodos de amortización degresivo/por unidades; asignación automática de
imputaciones analíticas desde asientos contables por cuenta; informe P&G por centro de coste en BI.
