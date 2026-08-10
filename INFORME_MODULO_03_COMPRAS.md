# Informe Técnico — Módulo 3: Compras (Enriquecimiento funcional)

Metodología: auditoría → informe → solo gaps → pruebas → verificación. Aditivo/reversible; sin duplicar.

## 1. Auditoría — ya existía (NO tocado)
| Propuesta | Estado | Dónde |
|---|---|---|
| planificación de compras · sugerencias inteligentes | ✅ | `db/reabastecimiento` (generar_propuestas_almacen, `_prevision_demanda` Prophet, schedule) |
| recepción parcial · múltiple | ✅ | `db/compras.recibir` (estado PARCIAL), `listar_recepciones` |
| consolidación | ✅ | `db/compras.crear_pedido_desde_propuestas` |
| contratos (acuerdos marco) | ✅ | `proveedor_acuerdos_marco` (Módulo 2) |
| incidencias · costes · facturas · devoluciones · evaluaciones | ✅ | `db/compras` |

## 2. Diferencias — faltaba (implementado, migr 0104)
| Propuesta | Acción |
|---|---|
| pedidos recurrentes | **nuevo** `compras_pedidos_recurrentes` + job Scheduler `compras_recurrentes` |
| órdenes abiertas (blanket) | **nuevo** `compras_ordenes_abiertas` + consumos/call-offs |
| comparativa automática de proveedores | **nuevo** `comparativa_proveedores(articulo)` (sin tabla; reutiliza datos) |
| aprobación multinivel | **cableado al Workflow** existente (`iniciar_proceso`/`aprobado`) por umbral de importe |

## 3. Reutilización (cero duplicidad)
- Recurrentes y órdenes abiertas **generan pedidos reutilizando `db.compras.crear_pedido`** (no reimplementan el pedido).
- Comparativa reutiliza `proveedor_precios_negociados` (M2) + `proveedores_evaluacion` (valoración) + `proveedores.lead_time_dias`.
- Aprobación multinivel **reutiliza el Workflow existente** (entidad `compra_pedido`); umbral configurable (`_UMBRAL_APROBACION=3000`).
- Job de recurrentes registrado en el JobRegistry → visible/configurable en "Programador". Auditoría en cada operación; multiempresa.

## 4. Nuevas funciones (`src/services/compras/compras_pro.py`)
- Recurrentes: `crear_recurrente` · `_job_recurrentes` · `listar_recurrentes`.
- Órdenes abiertas: `crear_orden_abierta` · `consumir_orden_abierta` (call-off→pedido) · `ordenes_abiertas`.
- Comparativa: `comparativa_proveedores(codigo_articulo)` (ranking precio neto/valoración/lead time).
- Aprobación: `solicitar_aprobacion_pedido` · `pedido_aprobado` (Workflow) + `registrar_jobs_compras`.

## 5. Pruebas superadas
migr 0104. Recurrente genera pedido; orden abierta + call-off de 30 genera pedido y actualiza consumo;
comparativa ordena y marca recomendado; aprobación exigida sobre umbral y omitida bajo umbral;
`compras_recurrentes` en el catálogo del Scheduler. **smoke 5 passed.**

## 6. Mejoras futuras
GUI en la sección Compras para recurrentes/órdenes abiertas/comparativa; aplicar `pedido_aprobado`
como gate en `enviar_pedido`; usar `comparativa_proveedores` al crear líneas de pedido.
