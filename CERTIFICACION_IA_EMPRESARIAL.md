# CERTIFICACIÓN — IA PREDICTIVA EMPRESARIAL (Fase 6)

**🟢 OPERATIVO Y VERIFICADO · 🟡 VALIDADO LOCALMENTE/PARCIAL · 🔵 PREPARADO · 🟣 BLOQUEADO EXTERNO · 🔴 NO IMPL.**

## Resumen ejecutivo
Se ha completado el **ciclo de vida persistente de modelos**, la **integración SOMA** (respuesta explicable
con el motor real) y el **contrato de UI** para las previsiones, sobre el motor de la Fase 5. Todo reutiliza
Event Bus/SSE/tenant/RBAC/auditoría (N7). Única tabla nueva justificada: `prediccion_modelos` (migr 0163).
Sin mocks del flujo, sin motor/IA/bus/UI paralelos, sin presentar heurística como IA.

## Cambios (archivos)
- **Nuevos:** migr `0163_prediccion_modelos`, `prediccion/modelos.py` (ciclo de vida/versionado/comparación/
  degradación), `prediccion/consulta.py` (SOMA + `resumen_ui`).
- **Modificados:** `prediccion/forecasting.py` (`persistir=True` → registra modelo), `prediccion/motor.py`
  (ya expone `forecast_ventas`), `seguridad/catalogo.py` (permisos `prediccion.*`), migraciones `__init__`.
- **Tests:** `tests/unit/test_prediccion_modelos.py` (7). **Docs:** AUDITORIA/ARQUITECTURA/RUNBOOK/esta.

## Evidencia (tests reales)
- Ciclo de vida + comparación: activar sin activo → activa; modelo con **menor MAE** → activa y depreca el
  anterior; modelo **peor** → **rechazado** (activo intacto). ✔
- **No activa sin VALIDATED** (estado TRAINING → error). ✔
- **Aislamiento multi-tenant:** activar un modelo de otro tenant → rechazado. ✔
- **Degradación:** WAPE estable → HEALTHY; WAPE muy peor → DEGRADED/RETRAIN (+eventos). ✔
- **Persistencia:** `forecast_ventas` registra el modelo (VALIDATED, hash de integridad). ✔
- **SOMA:** respuesta con modelo real; sin datos → "No hay datos suficientes" (no inventa); `resumen_ui`
  etiqueta el origen (heurística ≠ ML). ✔
- **RBAC:** `prediccion.ver/entrenar/activar/gestionar` en el catálogo. ✔
- **Regresión completa: 624 passed, 1 skipped (0 regresiones).** Migración 0163 aplicada.

## Matriz de estado
| Capacidad | Estado | Evidencia |
|---|---|---|
| Motor predictivo / Prophet / backtesting / calidad / explicabilidad | 🟢 | Fase 5 + tests |
| Versionado PERSISTENTE de modelos | 🟢 | tabla `prediccion_modelos` + `registrar` |
| Ciclo de vida (TRAINING→VALIDATED→ACTIVE→DEPRECATED/FAILED) | 🟢 | `test_ciclo_vida_y_comparacion` |
| Comparación de modelos (MAE) + activación validada | 🟢 | idem (activa solo si mejora) |
| Detección de degradación + eventos | 🟢 | `test_degradacion` |
| Retraining CONTROLADO | 🟡 | recalcular+activar (manual/scheduler); auto no activado |
| Multi-tenant | 🟢 | `test_aislamiento_multitenant` |
| RBAC `prediccion.*` + auditoría | 🟢 | catálogo + `PRED_MODELO_*` |
| Event Bus + SSE (tiempo real) | 🟢 | `prediccion.generada`/`modelo_activado`/`modelo_degradado` |
| SOMA (respuesta predictiva explicable) | 🟢 (servicio) / 🟡 (conversacional) | `consulta.responder`; cableado en copilot incremental |
| UI (tarjetas de previsión) | 🟡 | `consulta.resumen_ui` (contrato listo); pintado por pantalla incremental |
| Modelos globales/segmentados multi-tenant | 🟣 | requieren agregación autorizada |

## Distinción de honestidad
IA **heurística** (media móvil) · IA **estadística** (tendencia lineal) · **Machine Learning real (Prophet)**
(`es_ml=True`). SOMA y UI etiquetan el origen con estos términos; jamás "IA avanzada" para una heurística.

## Veredicto
**FASE 6 — IA PREDICTIVA EMPRESARIAL — COMPLETADA (núcleo operativo y verificado).** Ciclo de vida
persistente, comparación/activación validada, degradación con eventos, multi-tenant, RBAC, auditoría, SOMA
explicable y contrato de UI — todo verificado por tests, 0 regresiones. Pendientes honestos: pintado de
tarjetas por pantalla (🟡), cableado conversacional de SOMA en el copilot (🟡), retraining automático (🟡) y
modelos globales multi-tenant (🟣). N7, compatibilidad hacia atrás, RBAC/MFA/WebAuthn/auditoría/Event Bus/SSE:
intactos. Sin mocks, sin motores paralelos, sin falsear IA.
