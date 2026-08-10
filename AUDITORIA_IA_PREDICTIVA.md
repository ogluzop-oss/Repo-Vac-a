# AUDITORÍA — IA PREDICTIVA (Fase 5, previa)

Estado en modo lectura antes de implementar.

## Existente (reutilizable)
- `services/prediccion/motor.py` → `PredictionService` (singleton `servicio()`): predicción por dominio
  (stock/ventas/compras/tesoreria/rrhh/clientes) + alertas/predicciones/tendencias — **heurísticas**.
- `services/prediccion/heuristicas.py`: `Estimador` (media móvil + proyección lineal), enchufable
  (`set_estimador`), + `motor_activo()` (etiqueta heurística vs ML — añadido en fase anterior).
- **Fuentes de datos REALES**: `ia/adaptadores.ventas_por_dia(id_empresa, dias)` → serie diaria
  (`d/total/tickets`) desde la tabla `ventas`; `prediccion/adaptadores` (rotación, sin movimiento, clientes).
- **Prophet INSTALADO** (`prophet: True`); XGBoost/sklearn NO.
- Event Bus (`eventbus.publish`) + SSE (Fase 4) + aislamiento por tenant + RBAC + auditoría.

## Brechas (antes de esta fase)
- 🔴 No existía: selección automática de modelo, integración real de Prophet, backtesting, métricas
  (MAE/RMSE/WAPE), informe de calidad de datos, intervalos de confianza, explicabilidad estructurada,
  metadatos/versionado de modelo, emisión de eventos de predicción.
- El motor solo devolvía heurísticas; el `Estimador` era enchufable pero **sin nadie que enchufara Prophet**.

## Clasificación previa
| Componente | Estado previo |
|---|---|
| Heurística | 🟢 |
| Datos históricos reales | 🟢 (adaptadores) |
| Prophet | 🔵 (instalado, no integrado) |
| Selección automática / backtesting / métricas / calidad / explicabilidad / versionado / eventos | 🔴 |

## Conclusión
Se puede construir un **motor de forecasting unificado REAL** extendiendo `services/prediccion` (N7), con
Prophet real (local, sin GPU/cloud), backtesting y métricas reales, reutilizando datos/Event Bus/SSE/tenant.
