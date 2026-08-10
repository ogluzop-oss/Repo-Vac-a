# AUDITORÍA — IA PREDICTIVA: UI + SOMA + CICLO DE VIDA (Fase 6, previa)

## Existente (Fase 5, reutilizable)
- Motor de forecasting unificado (`prediccion/forecasting.py`): calidad → selección → backtesting (MAE/
  RMSE/WAPE) → Prophet real/estadística/heurística → intervalos → explicabilidad → evento
  `prediccion.generada`. `PredictionService.forecast_ventas` sobre series reales por tenant.
- Event Bus + Realtime Hub + SSE (Fase 4), aislamiento por tenant, RBAC, auditoría, observabilidad.
- **Copilot** (`services/copilot/motor.py::CopilotService.preguntar`) YA consume `prediccion.servicio()`
  (línea 253-255) → punto de integración de SOMA existente.

## Brechas (antes de esta fase)
- 🔴 Versionado PERSISTENTE de modelos (solo metadatos en memoria; sin tabla).
- 🔴 Ciclo de vida (TRAINING→VALIDATED→ACTIVE→DEPRECATED), comparación de modelos, activación validada.
- 🔴 Detección de degradación con eventos.
- 🔴 Permisos RBAC `prediccion.*`.
- 🟡 Integración SOMA conversacional (copilot ya llama al servicio, pero sin respuesta de previsión
  explicable dedicada).
- 🟡 Integración UI (sin tarjetas de previsión en Smart Stock/Reabastecimiento/…).

## Clasificación previa
| Componente | Estado previo |
|---|---|
| Motor/Prophet/backtesting/calidad/explicabilidad | 🟢 |
| Versionado persistente / ciclo de vida / comparación / degradación | 🔴 |
| RBAC prediccion.* | 🔴 |
| SOMA predictivo explicable | 🟡 |
| UI (tarjetas de previsión) | 🟡 |

## Conclusión
Completar la persistencia/ciclo de vida (tabla + servicio), la integración SOMA (respuesta explicable) y el
contrato de UI, reutilizando Event Bus/SSE/tenant/RBAC/auditoría. **1 tabla nueva justificada**
(`prediccion_modelos`, migr 0163); ninguna otra duplicidad.
