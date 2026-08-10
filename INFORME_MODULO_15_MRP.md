# Informe Técnico — Módulo 15: MRP

**Auditoría (ya existía, `services/mrp/planificador.py`):** explosión de BOM multinivel sobre una
demanda → necesidades brutas → **netas** (descontando stock) → sugerencias de compra/fabricación
(`calcular_necesidades`, `generar_sugerencias`), con BOM (`bom.py`), centros/capacidad (`centros.py`)
y costes (`costes.py`).

**Gaps implementados (migr 0115 + `src/services/mrp/mps.py`):**
- **Plan Maestro de Producción (MPS)** (`mrp_plan_maestro`): `fijar_linea_mps` (consolida demanda de
  pedidos + previsión por periodo/artículo; el plan de producción por defecto iguala la demanda
  total), `plan_maestro`, `confirmar_periodo`.
- **Lanzamiento MRP desde el MPS** (`lanzar_mrp`): entrega el plan del periodo al planificador
  existente (**`planificador.generar_sugerencias`**) para obtener necesidades netas y sugerencias.
  No reimplementa el cálculo de necesidades.

**Reutilización:** `planificador.generar_sugerencias` (explosión BOM/stock/sugerencias) intacto;
auditoría; multiempresa. El MPS es la capa de consolidación de demanda que faltaba **por encima** del
planificador.

**Pruebas:** migr 0115; línea MPS (pedidos 100 + previsión 40 = 140), confirmación de periodo,
`lanzar_mrp` → sugerencias del planificador. **smoke 5 passed.**

**Mejoras futuras:** poblar `demanda_pedidos` automáticamente desde pedidos de cliente y
`demanda_prevision` desde el forecast de BI; horizonte multi-periodo con time-fences; ATP/CTP.
