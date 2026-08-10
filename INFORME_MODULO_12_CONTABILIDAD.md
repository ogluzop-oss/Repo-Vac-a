# Informe Técnico — Módulo 12: Contabilidad

**Auditoría (ya existía):** PGC PYMES (`plan_pgc.py`, `cuentas.py`), asientos doble partida con cuadre
y cadena de auditoría hash (`asientos.py`), diario/mayor/balances/PyG (`informes.py`), libros de IVA
+ 303 (`iva.py`), cola de posting automático ventas/compras/devoluciones/nómina (`posting.py`),
cierre formal completo — **regularización → cierre → apertura → arrastre de saldos** (`cierre.py`),
idempotencia contable (M1).

**Gaps implementados (migr 0112 + `src/services/contabilidad/plantillas.py`):**
- **Plantillas de asiento**: `crear_plantilla` (líneas cuadradas reutilizables) · `listar_plantillas`
  · `generar_desde_plantilla` (crea el asiento real **reutilizando `asientos.crear_asiento`** con
  idempotencia por `ref_origen`).
- **Asientos recurrentes/periódicos**: `programar_recurrente` (mensual…anual, con fecha_fin) +
  job de Scheduler `contab_asientos_recurrentes` (`_job_asientos_recurrentes` genera los vencidos y
  avanza la programación; se auto-desactiva al superar `fecha_fin`). Registrado en el JobRegistry.

**Reutilización:** `asientos.crear_asiento` (0 reimplementación de la partida doble); idempotencia
contable existente; Scheduler/JobRegistry; auditoría; multiempresa. Además, se **corrigió el hook de
amortización del M11** para encolar por `posting.encolar` (módulo real) en lugar de un `cola`
inexistente.

**Pruebas:** migr 0112; plantilla de alquiler (621/572) → asiento nº 985, segunda generación
idempotente; recurrente mensual + job genera ≥1; job en `CATALOGO`. **smoke 5 passed.**

**Mejoras futuras:** plantillas con importes variables/porcentuales por parámetro; conciliación/punteo
de cuentas contables; generación de asientos recurrentes con distribución analítica automática a
centros de coste (M11).
