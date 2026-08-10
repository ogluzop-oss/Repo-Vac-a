# CERTIFICACIÓN — IA PREDICTIVA VISIBLE Y OPERATIVA (Fase 7)

Fecha: 2026-06-30 · Alcance: integración VISIBLE + conversacional del motor predictivo real (Fases 5-6) en
la experiencia empresarial. Reglas aplicadas: **N7** (reutilizar infraestructura, un solo motor por
responsabilidad), **sin mocks**, **honestidad de origen** (heurística ≠ estadística ≠ ML/Prophet), aislamiento
multi-tenant, RBAC/auditoría intactos, 0 regresiones.

## Matriz honesta de estado

| Capacidad | Estado | Evidencia |
|---|---|---|
| Tarjeta de previsión reutilizable (`gui/prediccion_card`) | 🟢 OPERATIVA | Reutiliza `EnterpriseCard`; test offscreen `test_tarjeta_prevision_offscreen` |
| Riesgo de rotura (servicio `prediccion/riesgo_rotura`) | 🟢 OPERATIVO | Función pura + `riesgo_articulo` (forecast real + stock BD); test `test_riesgo_rotura_niveles` |
| SOMA/Copilot conversacional predictivo | 🟢 OPERATIVO | `CopilotService._responder_prediccion` delega en `consulta.responder` (motor real); tests `test_copilot_hook_*` |
| "No hay datos suficientes" (honestidad) | 🟢 OPERATIVO | `consulta` rechaza sin histórico; verificado en tests |
| Distinción heurística/estadística/ML/Prophet | 🟢 OPERATIVO | `_ETIQUETA` + `es_ml` sólo Prophet; nunca llama IA a heurística |
| Retraining CONTROLADO (`prediccion/retraining`) | 🟢 OPERATIVO | Entrena candidato→compara→activa sólo si mejora; test `test_retraining_controlado` |
| Tarjeta cableada en pantalla real (Reposición IA) | 🟢 VERIFICADO (1 pantalla) | `informe_reposicion._EstadoReposicionPage`; test offscreen de instanciación |
| Tarjeta en Smart Stock / Compras / Ventas | 🟡 COMPONENTE LISTO, cableado pendiente | El componente es reutilizable; falta colocarlo en esas 3 pantallas |
| Retraining AUTOMÁTICO por scheduler | 🟡 MANUAL/PROGRAMABLE | `retrain()` es invocable/registrable; NO auto-registrado (evita side-effects) |
| SSE en tiempo real → refresco visual de tarjetas | 🟡 TRANSPORTE LISTO | Canal `prediccion` (Fase 4) emite; el repintado en vivo de la tarjeta no está cableado |
| Modelos globales multi-tenant (transfer learning) | 🟣 BLOQUEO DE DISEÑO | Cada tenant entrena el suyo; global requiere decisión de arquitectura |
| ML avanzado (xgboost/sklearn) | 🟣 BLOQUEO EXTERNO | No instalados; Prophet sí (degradable). No se simula |

**Veredicto:** IA predictiva **operativa y verificable** en su núcleo (motor, riesgo, conversación, retraining
controlado, 1 pantalla). Elementos de despliegue visual amplio marcados 🟡 con honestidad; no se declara 🟢 lo
no verificado.

## Origen de la inteligencia (clasificación exigida)

- **Heurística** (media móvil): < 14 observaciones. NO es IA/ML — etiquetada como "estimación heurística".
- **Estadística** (tendencia lineal): 14-59 observaciones — "modelo estadístico".
- **ML real (Prophet)**: ≥ 60 observaciones y Prophet disponible — "Machine Learning (Prophet)", `es_ml=True`.
- Sin datos suficientes (< 7): "No hay datos suficientes para generar una predicción fiable."

## Regresión

`629 passed, 1 skipped` (624 baseline + 5 nuevas de Fase 7 · antes de añadir el test de pantalla; total del
fichero `test_ia_ui.py`: 6). 0 regresiones. Cambios aditivos: 3 servicios/GUI nuevos + 1 cableado degradable en
`informe_reposicion.py`, sin tablas ni dependencias nuevas.
