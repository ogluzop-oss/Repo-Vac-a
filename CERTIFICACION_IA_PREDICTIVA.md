# CERTIFICACIÓN — IA PREDICTIVA (Fase 5)

**🟢 OPERATIVO Y VERIFICADO · 🟡 VALIDADO LOCALMENTE · 🔵 PREPARADO · 🟣 BLOQUEADO EXTERNO · 🔴 NO IMPL.**

## Resumen ejecutivo
Se ha implementado y verificado un **motor de forecasting unificado REAL** que evoluciona la predicción de
Smart Manager desde heurística pura a: **calidad de datos + selección automática + Prophet real (ML) +
backtesting con métricas (MAE/RMSE/WAPE) + intervalos de confianza + explicabilidad honesta + versionado de
metadatos + eventos + tiempo real**, todo por tenant. **Sin mocks del flujo, sin motor paralelo, sin tablas
nuevas, sin presentar heurística como IA.** Prophet se integra realmente (instalado); es degradable.

## Componentes reutilizados (N7)
`services/prediccion` (motor/heurísticas/adaptadores), datos históricos reales (`ia/adaptadores`), Event Bus
(`eventbus.publish`), tiempo real SSE (Fase 4), aislamiento por tenant, RBAC/auditoría. **0 tablas nuevas,
0 dependencias nuevas** (Prophet ya estaba instalado).

## Archivos
- **Nuevo:** `services/prediccion/forecasting.py` (motor unificado).
- **Modificados:** `services/prediccion/motor.py` (`PredictionService.forecast_ventas`),
  `services/prediccion/__init__.py` (export `forecasting`).
- **Tests:** `tests/unit/test_forecasting.py` (7). **Docs:** AUDITORIA/ARQUITECTURA/RUNBOOK/esta certificación.

## Evidencia (tests reales, matemática verificada)
- Calidad de datos (GOOD/WARNING/INSUFFICIENT/INVALID). ✔
- Selección **heurística** por falta de datos; **estadística** (lineal) con tendencia + backtesting. ✔
- **Prophet REAL** con serie de 75 puntos (estacionalidad) → `tipo=ml`, intervalos yhat_lower/upper. ✔
- **Rechazo de Prophet** por datos insuficientes (<60 obs) → nunca ML. ✔
- **Backtesting temporal** con MAE/RMSE/WAPE numéricos. ✔
- **Multi-tenant + Event Bus + SSE E2E**: una predicción emite `prediccion.generada` que llega al hub de
  tiempo real (canal `prediccion`) del tenant. ✔
- Integración en `PredictionService.forecast_ventas` (no paralelo). ✔
- **Regresión completa: 617 passed, 1 skipped (0 regresiones).**

## Matriz de estado
| Capacidad | Estado | Evidencia |
|---|---|---|
| Heurística | 🟢 | `test_forecasting` |
| Selector automático | 🟢 | umbrales por nº obs + calidad |
| Prophet (ML real) | 🟢 | `test_prophet_real_cuando_procede` |
| Backtesting temporal | 🟢 | MAE/RMSE/WAPE reales |
| Métricas | 🟢 | idem |
| Calidad de datos | 🟢 | `calidad_datos` |
| Multi-tenant | 🟢 | por `id_empresa`; evento por tenant |
| Explicabilidad | 🟢 | `explicacion` distingue heurística/estadística/ML |
| Event Bus | 🟢 | `prediccion.generada` |
| SSE (tiempo real) | 🟢 | canal `prediccion` (Fase 4) |
| Versionado de modelos | 🟡 | metadatos (`model_id`/version/estado) en el resultado; tabla de registro = futuro |
| UI | 🔵 | contrato de datos listo; conectar tarjetas de previsión por módulo = incremental |
| SOMA | 🔵 | puede consumir `forecast_ventas` (contrato listo); cableado conversacional = incremental |
| Retraining automático | 🔵/🟣 | drift observable (WAPE); reentrenamiento controlado no activado |
| Modelos globales/segmentados | 🟣 | requieren agregación multi-tenant autorizada |

## Distinción de honestidad (obligatoria)
- **IA heurística:** media móvil (`tipo=heuristica`). 
- **IA estadística:** tendencia lineal (`tipo=estadistica`). 
- **Machine Learning real (Prophet):** `tipo=ml`, `es_ml=True`. 
El sistema NUNCA etiqueta como IA/ML una heurística; la explicación lo indica en texto.

## Veredicto
**FASE 5 — IA PREDICTIVA — COMPLETADA (núcleo operativo y verificado).** Motor unificado con Prophet real,
backtesting, calidad, explicabilidad, multi-tenant y tiempo real. Pendientes honestos (no operativos): tabla
de registro de modelos (🟡), cableado de UI/SOMA por pantalla (🔵), reentrenamiento automático (🔵) y modelos
globales multi-tenant (🟣). N7, compatibilidad hacia atrás, RBAC/MFA/WebAuthn/auditoría/Event Bus/SSE:
intactos. Sin mocks, sin motor paralelo, sin falsear IA.
