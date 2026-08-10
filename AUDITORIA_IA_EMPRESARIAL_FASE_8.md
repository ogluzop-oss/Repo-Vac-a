# AUDITORÍA — IA PREDICTIVA TRANSVERSAL (Fase 8)

Fecha 2026-07-27. Metodología: auditoría del wiring real (no "existe archivo = implementado") + tests runtime.

## 1. Estado auditado ANTES de la Fase 8

| Elemento | Hallazgo real |
|---|---|
| Motor predictivo | `forecasting.py` único, real, degradable (Prophet). ✅ |
| Servicios Fase 7 | `riesgo_rotura.py`, `retraining.py`, `prediccion_card.py`, `consulta.py` presentes y probados. ✅ |
| Pantallas que consumían IA | SOLO Reposición IA (Fase 7). Smart Stock/Compras/Ventas **no** consumían `consulta.resumen_ui`. |
| SSE→UI | `RealtimeClient` existe, pero **ninguna** pantalla lo consumía (grep en `src/gui` = 0). |
| Event Bus | `eventbus.publish` + canal `prediccion` (Fase 4). ✅ |
| RBAC | `prediccion.ver/entrenar/activar/gestionar` en catálogo (4 permisos). |
| Panel predictivo en hub | Ya existía `PanelPrediccion` (BI hub) mostrando el PredictionService por dominio. |
| Tenant | `db.empresa.empresa_actual_id()`; adaptadores filtran por `id_empresa`. ✅ |

**Conclusión de la auditoría:** el motor y los servicios eran reales; faltaba **integración transversal**
(varias pantallas), **SSE→UI**, **SOMA profundo** (sólo previsión de ventas) y un **agregador de KPIs**.

## 2. Cambios de la Fase 8 (todos aditivos / N7)

- **SOMA profundo** (`consulta.responder` reescrito como enrutador): añade intents **riesgo / tendencia /
  modelos** además de previsión. El copiloto ya llamaba a `consulta.responder` (Fase 7) → beneficio inmediato.
- **Panel de KPIs** (`services/prediccion/panel.kpis_predictivos`): agrega riesgo/demanda/modelos con
  explicación, reutilizando `stock.predecir`, `modelos.listar`, `forecasting`. Sin tabla nueva.
- **Recomendaciones de reposición** (`services/prediccion/recomendaciones`): asisten a Compras/Informes;
  **no** generan pedidos.
- **Hub BI enriquecido**: `PanelPrediccion` ahora muestra también los KPIs del motor real (grid `grid_ia`).
  NO se creó un panel paralelo (se eliminó el borrador `gui/prediccion_panel.py`).
- **Smart Stock**: tarjeta de previsión + riesgo (reutiliza `prediccion_card`), degradable.
- **SSE→Qt** (`gui/realtime_qt.RealtimePrediccionBridge`): envuelve `RealtimeClient` y re-emite el canal
  `prediccion` como señales Qt. No crea transporte nuevo.

## 3. Reglas verificadas

- Un solo motor (`forecasting`): ✅ todos los módulos lo consumen; 0 motores/PredictionService/tablas nuevos.
- Honestidad heurística/estadística/ML: ✅ extremo a extremo (`_ETIQUETA`, `es_ml` sólo Prophet).
- "No hay datos suficientes": ✅ en consulta (tendencia/modelos) y tarjetas.
- Multi-tenant: ✅ `id_empresa` en panel/recomendaciones/consulta; test `test_multitenant_aislado`.
- RBAC/MFA/WebAuthn/auditoría/Event Bus/SSE: intactos; sin sistemas paralelos.

## 4. Tests

`tests/unit/test_ia_fase8.py` (8) + `test_ia_ui.py` (Fase 7, 6). Regresión: `638 passed, 1 skipped` (baseline
629). 0 regresiones.
