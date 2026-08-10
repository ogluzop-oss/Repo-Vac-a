# MATRIZ FINAL — 8 FASES (Smart Manager AI)

Estados: 🟢 operativo/verificado · 🔵 preparado, pendiente de integración/validación · 🟡 validado localmente,
pendiente de infra real · 🟣 bloqueado por recurso externo · 🔴 no implementado.

| Fase | Área | Estado | Evidencia (dónde) | Tests | Integración | Pendiente | Bloqueo |
|---|---|---|---|---|---|---|---|
| 1 | Cloud / SaaS / Multi-tenant | 🟢 (código) · 🟣 (multi-región) | `saas/aislamiento`, `tenant_guard`, `api/routers/system`, `api_publica/oauth` | `test_cloud_infra`, `test_capacidades_avanzadas` | Aislamiento **404 directas** + 12 padre + 3 usuario + 11 global + 14 allowlist (0 fugas nuevas); health 3/3; OAuth2 | Multi-región/DNS/TLS/CDN | Infra cloud |
| 2 | Preparación despliegue SaaS | 🟡 production-**ready** | `Dockerfile`, `docker-compose.prod.yml`, 3 workflows CI, `.env.*.example` (placeholders) | `test_saas_deployment`, `test_backup_restore` | Backup/restore round-trip LOCAL; env sin secretos | Validación en prod real | Infra externa |
| 3 | Producción real | 🟣 NO desplegado | `INVENTARIO_INFRAESTRUCTURA_PRODUCCION`, `BLOQUEOS_EXTERNOS_FASE_3` | — (auditoría) | N/A (no hay infra) | Provisionar cloud/DNS/TLS/storage/CD | Infra externa |
| 4 | Tiempo real (SSE) | 🟢 SSE · 🔵 WebSocket · 🟣 multi-instancia | `eventbus/realtime.py`, `realtime_client.py`, `api/routers/realtime.py` | `test_realtime` (3): E2E, canal, seguridad | Publish→bus→hub→SSE→cliente; aislamiento tenant A≠B verificado | WebSocket bidireccional (no requerido) | Broker distribuido (multi-instancia) |
| 5 | IA predictiva (motor) | 🟢 | `prediccion/forecasting.py` | `test_forecasting` (7) | calidad→selección→backtest→Prophet real; MAE/RMSE/WAPE; intervalos; Event Bus | ML avanzado | xgboost/sklearn |
| 6 | IA empresarial / modelos / SOMA | 🟢 | `prediccion/modelos.py`+migr 0163, `consulta.py`, `copilot/motor.py` | `test_prediccion_modelos` (7) | ciclo TRAINING→VALIDATED→ACTIVE→DEPRECATED/FAILED; activar sólo si mejora; degradación; SOMA cita modelo/tipo/obs/calidad/confianza | modelos globales | anonimización autorizada |
| 7 | IA visible en la experiencia | 🟢 (núcleo) · 🟡 (Compras/Ventas inline) | `prediccion/riesgo_rotura.py`, `retraining.py`, `gui/prediccion_card.py`, `informe_reposicion.py` | `test_ia_ui` (6) | Reposición IA + tarjeta; oculta si <7 obs | Colocación inline Compras/Ventas; retraining auto | — |
| 8 | IA transversal | 🟢 (núcleo) · 🔵 (SSE UI live) | `prediccion/panel.py`, `recomendaciones.py`, `gui/realtime_qt.py`, `mostrar_stock.py`, `paneles/panel_prediccion.py` | `test_ia_fase8` (8) | Smart Stock + hub BI (grid_ia) + SOMA profundo + recomendaciones + multi-tenant | Refresco SSE end-to-end (API corriendo) | — |

## Notas de honestidad

- **Ninguna 🔵/🟣 se ha promovido a 🟢** sin evidencia. El refresco SSE end-to-end en UI queda 🔵 (el puente está
  probado en reparto de eventos; el ciclo completo requiere el API REST corriendo, recurso operativo).
- **Producción**: el software es **production-ready**, NO **production-deployed** (no existe infra cloud).
- **Distinción IA**: verificada en runtime — 7 obs→heurística (`es_ml=False`), 30 obs→estadística
  (`es_ml=False`), 90 obs→Prophet (`es_ml=True`).
