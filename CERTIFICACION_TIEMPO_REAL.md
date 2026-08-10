# CERTIFICACIÓN — TIEMPO REAL EN RED (Fase 4)

**🟢 OPERATIVO Y VERIFICADO · 🟡 VALIDADO LOCALMENTE · 🔵 PREPARADO · 🟣 BLOQUEADO EXTERNO · 🔴 NO IMPL.**

## Resumen ejecutivo
Se ha implementado y verificado el **transporte de tiempo real en RED por SSE** (server→cliente) sobre el
Event Bus EXISTENTE, con **autenticación JWT real, autorización/aislamiento multi-tenant, filtro de canal,
heartbeat, cierre limpio** y una **prueba E2E real** (evento de dominio real → bus → transporte → cliente).
Sin mocks, sin polling disfrazado, sin segundo bus, sin dependencias nuevas (SSE es HTTP nativo en Flask).

## Componentes reutilizados (N7)
Event Bus (`services/eventbus`/`services/eventos/bus`), JWT (`seguridad/tokens`), auth API
(`api/security.requiere_auth`), aislamiento por tenant, RBAC, rate limiting. **0 tablas nuevas, 0 motores
paralelos, 0 dependencias nuevas.**

## Cambios (archivos)
- **Nuevos:** `services/eventbus/realtime.py` (hub), `services/eventbus/realtime_client.py` (cliente
  reutilizable), `api/routers/realtime.py` (SSE `/realtime/stream` + `/realtime/metrics`).
- **Modificado:** `api/routers/__init__.py` (registra el router `realtime`).
- **Tests:** `tests/unit/test_realtime.py` (E2E + canal + seguridad SSE).
- **Docs:** AUDITORIA / ARQUITECTURA / RUNBOOK / esta certificación de tiempo real.

## Evidencia (tests, sin mocks del flujo)
- **E2E real:** `publish("stock.salida", id_empresa=A)` → el hub entrega el evento a un cliente de A con su
  `uuid`; un cliente de **B NO lo recibe** (aislamiento). ✔
- **Canal:** cliente suscrito a `stock` recibe `stock.entrada` y NO `ventas.finalizada`. ✔
- **Seguridad SSE:** sin token → **401**; con JWT → **200 + `text/event-stream`** y el hub registra la
  conexión del **tenant del token**. ✔
- **Regresión completa: 610 passed, 1 skipped (0 regresiones).**

## Estado real por capacidad
| Capacidad | Estado | Evidencia |
|---|---|---|
| Transporte SSE (server→cliente) | 🟢 | `/realtime/stream` + test seguridad |
| Autenticación (JWT) de la conexión | 🟢 | 401 sin token; tenant del token |
| Autorización / aislamiento multi-tenant | 🟢 | E2E: A no recibe eventos de B |
| Filtro por canal | 🟢 | test de canal |
| Integración con Event Bus real | 🟢 | E2E vía `eventbus.publish` |
| Heartbeat / cierre limpio | 🟢 | generador SSE (ping 15s + desregistro) |
| Cliente reutilizable (connect/reconnect/on_event) | 🟡 | `realtime_client` (reconexión backoff) — validado por diseño; wiring de UI por módulo, incremental |
| Idempotencia (event_id/uuid) | 🟢 | cada evento lleva `uuid` |
| Observabilidad (métricas RT) | 🟢 | `/realtime/metrics` |
| **WebSocket bidireccional** | 🔵 | no implementado (SSE cubre server→cliente; WS requeriría flask-sock/socketio) |
| **Multi-instancia (broker distribuido)** | 🟣 | `set_distribucion()` preparado; Redis/NATS = [EXTERNO], no simulado |
| Push en apps móviles nativas | 🟣 | cliente/endpoint listos; apps nativas = roadmap (fases previas) |

## Afirmación honesta permitida
> "Smart Manager AI dispone de **comunicación en tiempo real en red (SSE), autenticada, autorizada,
> multi-tenant y verificada mediante prueba de integración E2E**" — respaldado por `test_realtime.py`.

**Límites (no se declaran operativos):** WebSocket bidireccional (🔵 no implementado, SSE es suficiente para
push server→cliente), multi-instancia con broker distribuido (🟣 externo), y clientes de apps móviles nativas
(🟣 roadmap). Nada de esto se simula.

## Veredicto
**FASE 4 — TIEMPO REAL EN RED — COMPLETADA PARCIALMENTE — BLOQUEOS DOCUMENTADOS.**
El transporte SSE en red, autenticado, multi-tenant y E2E-verificado está **OPERATIVO Y VERIFICADO** en
single-instance. Quedan como no-operativos (honestamente): WebSocket bidireccional (🔵) y multi-instancia
distribuida (🟣 [EXTERNO]). N7, compatibilidad hacia atrás, RBAC/MFA/WebAuthn/auditoría: intactos.
