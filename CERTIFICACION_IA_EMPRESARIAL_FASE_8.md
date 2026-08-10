# CERTIFICACIÓN — IA PREDICTIVA TRANSVERSAL (Fase 8)

Fecha 2026-07-27 · Reglas: N7 (un solo motor), sin mocks, honestidad de origen/datos, multi-tenant, RBAC/MFA/
WebAuthn/auditoría/Event Bus/SSE intactos, 0 regresiones. Baseline 629 → **638 passed, 1 skipped**.

## Matriz honesta

| Capacidad | Estado | Evidencia |
|---|---|---|
| SOMA profundo (riesgo/tendencia/modelos/previsión) | 🟢 OPERATIVO | `consulta.responder` enrutador; tests `test_consulta_enruta_intents`, `test_copilot_responde_riesgo` |
| "No hay datos suficientes" honesto | 🟢 OPERATIVO | verificado en tendencia/modelos/tarjetas |
| Distinción heurística/estadística/ML-Prophet | 🟢 OPERATIVO | `_ETIQUETA`, `es_ml` sólo Prophet, extremo a extremo |
| Panel de KPIs predictivos (servicio) | 🟢 OPERATIVO | `panel.kpis_predictivos`; test `test_panel_kpis_estructura` |
| Dashboard en hub BI (KPIs motor real) | 🟢 VERIFICADO | `PanelPrediccion.grid_ia` enriquecido (N7, sin panel paralelo); test offscreen |
| Recomendaciones de reposición (asisten, no piden) | 🟢 OPERATIVO | `recomendaciones.recomendaciones_reposicion`; test |
| Smart Stock con IA (previsión + riesgo) | 🟢 VERIFICADO (offscreen) | `_StockTiendaPage._cargar_ia_predictiva`; test de instanciación |
| Puente SSE→Qt (reparto de eventos) | 🟢 VERIFICADO (reparto) | `RealtimePrediccionBridge`; test de reparto de evento |
| Refresco en vivo end-to-end por SSE | 🔵 PREPARADO | requiere API REST corriendo; el puente está listo y probado en reparto |
| Compras/Ventas: tarjeta inline en pantalla | 🟡 SERVICIO LISTO, inline pendiente | `recomendaciones`/`consulta` listos; colocación en esas 2 pantallas no cableada |
| Retraining automático por scheduler | 🟡 MANUAL/PROGRAMABLE | `retrain` invocable; no auto-registrado (evita reentrenos no supervisados) |
| Multi-tenant (aislamiento) | 🟢 VERIFICADO | `id_empresa` en todo; test `test_multitenant_aislado` |
| RBAC `prediccion.*` | 🟢 REUTILIZADO | permisos existentes cubren consultar/generar/activar/gestionar (mapa en arquitectura) |
| Auditoría/trazabilidad | 🟢 INTACTA | `PRED_MODELO_*` en `log_auditoria`; sin eliminar auditorías |
| Modelos globales multi-tenant | 🟣 BLOQUEADO | requiere anonimización/agregación autorizada entre empresas — no disponible; no se mezcla |
| ML avanzado (xgboost/sklearn) | 🟣 BLOQUEO EXTERNO | no instalados; Prophet sí (degradable). No se simula |
| Demanda por SKU (vs agregada de empresa) | 🟡 FUTURO | la previsión es agregada de empresa (contexto); riesgo por SKU usa su propia cobertura |

**Veredicto:** IA predictiva **integrada transversalmente** (SOMA, hub BI, Smart Stock, Reposición) con
servicios reales para Compras/Informes y transporte de tiempo real listo. Núcleo 🟢; elementos que dependen de
colocación GUI adicional o de infra corriendo marcados 🟡/🔵; bloqueos de diseño/externos 🟣. No se declara 🟢
nada no verificado.

## Punto 11 — Modelos globales multi-tenant (bloqueo documentado)

- **Qué falta**: mecanismo legal y seguro de anonimización/agregación de series entre empresas.
- **Por qué está bloqueado**: mezclar datos de distintos tenants viola el aislamiento vigente; no hay
  autorización ni capa de anonimización.
- **Qué haría falta**: política de consentimiento por tenant + pipeline de anonimización + almacenamiento
  segregado del modelo global. Decisión de arquitectura/negocio, no de código.

## Regla de detención

No se necesitó infraestructura externa (Redis/NATS/broker/credenciales) para lo entregado. El **refresco en
vivo end-to-end** por SSE requiere el API REST corriendo (recurso operativo, no un tercero): queda 🔵 preparado
y probado en reparto de eventos, sin simular un servidor.

## Cambios

- **Nuevos**: `services/prediccion/panel.py`, `services/prediccion/recomendaciones.py`,
  `gui/realtime_qt.py`, `tests/unit/test_ia_fase8.py`.
- **Modificados**: `services/prediccion/consulta.py` (enrutador de intents), `gui/mostrar_stock.py` (IA en
  Smart Stock), `gui/paneles/panel_prediccion.py` (KPIs motor real).
- **Eliminado**: borrador `gui/prediccion_panel.py` (evita panel duplicado — N7).
- **Tablas nuevas**: 0. **Dependencias nuevas**: 0.
