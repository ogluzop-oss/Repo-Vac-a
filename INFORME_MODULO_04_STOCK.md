# Informe Técnico — Módulo 4: Stock (Enriquecimiento funcional)

Metodología: auditoría → informe → solo gaps → pruebas → verificación. Aditivo/reversible; sin duplicar.

## 1. Auditoría — ya existía (NO tocado)
trazabilidad/kárdex + movimientos (`db/kardex`, `movimientos_stock`), **FEFO** (`db/lotes.consumir_fefo`),
lotes + caducidades (`db/lotes`), **series** (numero_serie), inventario físico (`db/inventario_fisico`),
stock por almacén (`db/stock_almacen`), reservas de venta (pedidos_online / ventas_comercial).

## 2. Diferencias — faltaba (implementado)
| Propuesta | Acción |
|---|---|
| FIFO / LIFO | **ampliación** de `db/lotes`: `consumir_fefo(orden=…)` + `consumir_fifo`/`consumir_lifo`/`consumir_por_politica` (reutilizan el MISMO cuerpo de consumo; FEFO intacto) |
| stock comprometido / futuro | **nuevo** `stock_pro.stock_comprometido` (pedidos venta pendientes) / `stock_futuro` (compras en camino) + `disponibilidad` proyectada |
| inventarios cíclicos / conteos inteligentes | **nuevo** `articulos_para_conteo` (por rotación) + job `inventario_conteo_ciclico` (crea tarea) |
| reubicación inteligente | **nuevo** `sugerencias_reubicacion` (por rotación) |

## 3. Reutilización (cero duplicidad)
- FIFO/LIFO **no reimplementan** el consumo: reutilizan `consumir_fefo` cambiando solo el `ORDER BY`
  (FEFO por defecto → comportamiento previo intacto).
- comprometido/futuro **se calculan** de las tablas existentes (`pedidos_online(_items)`,
  `compras_pedidos(_lineas)`); disponibilidad usa el kárdex.
- Conteo cíclico y reubicación reutilizan `movimientos_stock` (rotación) + `services.tareas` +
  inventario físico. Job en el JobRegistry → "Programador". Auditoría; multiempresa.

## 4. Nuevas funciones
- `db/lotes.py`: `consumir_fifo` · `consumir_lifo` · `consumir_por_politica` (+ `orden` en consumir_fefo).
- `src/services/inventario/stock_pro.py`: `stock_comprometido` · `stock_futuro` · `disponibilidad` ·
  `articulos_para_conteo` · `_job_conteo_ciclico` · `sugerencias_reubicacion` · `registrar_jobs_inventario`.

## 5. Pruebas superadas
FIFO/LIFO/política presentes; consumo sin lotes no rompe; comprometido/futuro/disponibilidad calculan;
job de conteo cíclico funciona y aparece en el catálogo del Scheduler; reubicación sugiere.
**smoke 5 passed.** FEFO/lotes/kárdex existentes intactos.

## 6. Mejoras futuras
Series completas por unidad; conteo cíclico ABC ponderado por valor; reubicación con distancias reales
de ubicación; exponer disponibilidad proyectada en Mostrar Stock.
