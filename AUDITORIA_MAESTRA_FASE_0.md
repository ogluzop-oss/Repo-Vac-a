# AUDITORÍA MAESTRA — FASE 0 (estado real del repositorio, read-only)

Fecha 2026-07-27. Auditoría de estado ANTES de cualquier corrección. Metodología: verificación de wiring real
(no "existe archivo = implementado") mediante lectura de código, grep y ejecución runtime.

## Inventario verificado

| Elemento | Evidencia real | Estado |
|---|---|---|
| Migraciones | 163 ficheros `NNNN_*.py` (última `0163_prediccion_modelos`) | 🟢 |
| Tests | 105 ficheros en `tests/unit` + `tests/integration` + `tests/load` + `smoke` | 🟢 |
| Git | rama `main`; 647 ficheros con cambios locales sin commitear (todo el desarrollo de fases) | 🟡 sin commitear |
| Multi-tenant | `saas.aislamiento.auditoria()` → directa **404**, via_padre 12, via_usuario 3, global 11, allowlist 14 | 🟢 |
| Health | `/health/live`, `/health/ready`, `/health/version` en `api/routers/system.py` | 🟢 |
| API pública | `api_publica.oauth.emitir_token`/`verificar_scope` (OAuth2 client-credentials + scopes) | 🟢 |
| Docker/CI | `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`, 3 workflows en `.github/workflows` | 🟢 |
| Env templates | `.env.example`, `.env.staging.example`, `.env.production.example` (placeholders `<desde-secret-store>`) | 🟢 sin secretos |
| SSE tiempo real | `eventbus/realtime.py` + `realtime_client.py` + `api/routers/realtime.py`; test `test_realtime.py` (3) | 🟢 |
| IA forecasting | `prediccion/forecasting.py` (heurística/estadística/Prophet real); test `test_forecasting.py` | 🟢 |
| Modelos IA | `prediccion/modelos.py` + migr 0163; test `test_prediccion_modelos.py` | 🟢 |
| IA UI/SOMA | `prediccion/consulta.py`, `gui/prediccion_card.py`, `copilot/motor.py` hook; `test_ia_ui.py`, `test_ia_fase8.py` | 🟢 |
| MFA/WebAuthn | `services/seguridad/mfa*.py`, migr 0060/0160/0161/0162 | 🟢 (motor) |
| Infra cloud real | NO existe (sin proveedor/cuenta/DNS/TLS/CDN/2ª región) | 🟣 EXTERNO |

## Clasificación de partida (a confirmar en las fases siguientes)

- **Existe e integrado**: multi-tenant, health, API pública, SSE, IA (motor+UI+SOMA), MFA, RBAC, auditoría.
- **Existe y preparado (pendiente de infra/integración adicional)**: refresco SSE end-to-end en UI (necesita
  API corriendo), retraining automático (manual/programable), tarjeta IA inline en Compras/Ventas.
- **Bloqueado externo**: despliegue en producción real (infra cloud), modelos globales multi-tenant,
  ML avanzado (xgboost/sklearn), multi-instancia SSE con broker.
- **No existe**: WebSocket bidireccional (SSE cubre push server→cliente — no requerido).

Sin cambios en esta fase. La verificación detallada y las correcciones mínimas se documentan en
`AUDITORIA_MAESTRA_FINAL_8_FASES.md` y `BRECHAS_ENCONTRADAS_Y_CORRECCIONES.md`.
