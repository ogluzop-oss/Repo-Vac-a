# INFORME — Fase III · Infraestructura Enterprise (plataforma tecnológica)

**Proyecto:** Smart Manager AI · **Fase:** III (Event Bus, REST API, Scheduler, Plugin SDK, Rules
Engine, Audit Replay, Observability, GraphQL-prep) · **Estado:** implementado y validado ·
**Fecha:** 2026-07-12

---

## 1. Arquitectura implementada

Smart Manager AI evoluciona de ERP a **plataforma tecnológica extensible**. Se añaden 8 capas de
infraestructura, **todas aditivas, API-First (servicios sin PyQt), multiempresa y reversibles**,
reutilizando la infraestructura existente. La capa de servicios queda limpia
(`REST → servicios → dominio → BD`), lista para SaaS, API pública, móvil/portal, IA y plugins.

## 2. Componentes nuevos

| Bloque | Ubicación | Función |
|---|---|---|
| **B1 Corporate Event Bus** | `src/services/eventbus/` | Fachada publish/subscribe/unsubscribe/replay sobre el bus existente + **Event Registry** (catálogo oficial de eventos estándar) + serializer + subscription_manager + event_store. |
| **B2 Enterprise REST API** | `src/api/` | Blueprint Flask versionado `/api/v1` que **solo consume servicios**: seguridad JWT + API Keys + rate limit + aislamiento por tenant + RBAC; **OpenAPI/Swagger** (`/openapi.json`, `/docs`). Routers: auth, system, communications, conversations, templates, campaigns, contacts, audit. |
| **B3 Enterprise Scheduler** | `src/services/scheduler_enterprise/` | Planificación inmediata/diferida/diaria/…/cron con **persistencia** (`scheduler_schedules`/`_ejecuciones`), reintentos, prioridades, cancelación, logs y auditoría. |
| **B4 Plugin SDK** | `src/sdk/` + `plugins/ejemplo/` | manifest.json + carga dinámica + registro persistente (`plugins_instalados`) + hooks + puntos de extensión (menús/pantallas/acciones/permisos/eventos/workflows/comunicaciones/API/widgets/informes) + desinstalación segura + compatibilidad por versión. |
| **B5 Corporate Rules Engine** | `src/services/rules/` | Reglas SIN código (`rules`): SI condiciones ENTONCES acciones (enviar comunicación, lanzar evento, notificar, crear workflow/tarea/incidencia/alerta, cambiar prioridad, actualizar estado). Suscribible al Event Bus. |
| **B6 Audit Replay** | `src/services/audit_replay/` | Reconstrucción (solo lectura) de cualquier proceso por Communication ID / entidad, uniendo eventos + comunicaciones + timeline + auditoría. |
| **B7 Enterprise Observability** | `src/services/observabilidad/dashboards.py` | Dashboards por dominio (sistema/comunicación/workflow/API/scheduler/plugins/usuarios/empresas) + alertas (colas bloqueadas, campañas fallidas…) sobre metricas/alertas_tecnicas. |
| **B8 GraphQL-prep** | `src/api/graphql/` | SOLO arquitectura: descriptor de tipos/consultas → servicio + README. Sin resolvers. |

Migraciones (aditivas, reversibles): `0130_scheduler_schedules`, `0131_rules`, `0132_plugins`.

## 3. Componentes reutilizados (no reescritos)

Event bus base `services.eventos` · Scheduler base `services.scheduler(_registry)` · Backend Flask
`src/backend/app.py` · JWT `seguridad.tokens` · rate limit `seguridad.rate_limit` · RBAC
`services.autorizacion` · tenant `services.seguridad.tenant_guard` / `empresa_actual_id` · CCP
(comunicaciones/plantillas/campañas/analítica/conversaciones) · Workflow · notificaciones ·
observabilidad (metricas Prometheus, tracing OTel, health, alertas_tecnicas).

## 4. Diagrama de capas

```
Cliente (REST / futuro GraphQL / móvil / IA / plugin)
        │
   src/api  (JWT + API keys + rate limit + tenant + RBAC + OpenAPI)   ── nunca toca la BD
        │
   Servicios: eventbus · rules · scheduler_enterprise · audit_replay · observabilidad · ccp · …
        │
   Dominio / capas de datos existentes  ─→  BD (MariaDB)

Event Bus  ⇄  Rules Engine (suscripción)   ·   Scheduler ─→ jobs/CCP   ·   SDK ─→ extension points/hooks
```

## 5. Validaciones realizadas

- **Suite completa: 44 passed** (`smoke` + `test_correo_oauth` + `test_destinatarios` + `test_ccp` +
  `test_ccp_fase2` + `test_fase3` (8: B1 event bus, B2 REST API, B3 scheduler, B4 SDK, B5 rules,
  B6 audit replay, B7/B8, **API-First sin PyQt**)).
- **Sin regresiones**: CCP/Correo/OAuth/Gmail/SMTP/IMAP intactos.
- **REST API** (Flask test client): OpenAPI válido, `/system/health` público, `POST /communications`
  sin token → 401, con JWT → 200 (envía por la CCP), **aislamiento por tenant** (empresa del token).
- **Multiempresa (0 cruces)** verificado en eventbus/rules/scheduler/API.
- **API-First**: test que verifica que ningún servicio de la infraestructura Fase III importa PyQt.
- **Migraciones 0130–0132 reversibles** (revertir/reaplicar comprobado).

## 6. Riesgos y mitigación

- **Cron sin `croniter`**: el scheduler degrada (no auto-programa cron sin la librería); los demás
  tipos (diaria/semanal/…) funcionan con stdlib. *Riesgo bajo.*
- **Sandbox de plugins**: Python no ofrece aislamiento real; se invoca solo el `register(sdk)` y se
  captura todo error (best-effort, documentado). *Riesgo medio, mitigado por permisos/manifest.*
- **API en producción**: el blueprint es montable en el backend Flask; se recomienda TLS + gestión de
  API keys por empresa (hoy clave maestra por entorno). *Riesgo bajo.*
- **Procesado de scheduler/cola**: hoy bajo demanda (`procesar_pendientes`); conectar a un job del
  scheduler para ejecución periódica. *Riesgo bajo.*

## 7. Compatibilidad hacia atrás

100% aditivo. No se modificó el motor de envío, ni el bus base, ni el scheduler base, ni la lógica de
negocio. La REST API y los servicios nuevos consumen servicios existentes. Todo el código nuevo es
opcional (nada se activa sin invocarse).

## 8. Plan de rollback

- **Migraciones**: `revertir` de 0132→0130 (elimina `plugins_instalados`, `rules`,
  `scheduler_schedules`/`_ejecuciones`). Comprobado.
- **Servicios/API**: eliminar `src/api`, `src/services/eventbus|rules|audit_replay|scheduler_enterprise`,
  `src/sdk`, `observabilidad/dashboards.py` y `plugins/ejemplo` no afecta a nada previo.
- El backend Flask sigue funcionando sin el blueprint de la API.

## 9. Preparación para futuras fases

- **SaaS/API pública**: la REST API ya es multiempresa, versionada y con OpenAPI; añadir recursos = un
  router por recurso (los ~19 grupos del catálogo).
- **GraphQL**: capa de solo consulta sobre los mismos servicios (ver `api/graphql`), sin duplicar
  modelos.
- **Automatización**: Rules Engine + Scheduler + Event Bus componen automatizaciones sin código.
- **Extensibilidad**: el Plugin SDK permite ampliar sin tocar el núcleo.
- **Microservicios**: cada servicio es desacoplado y extraíble.

## 10. Recomendaciones técnicas para la siguiente evolución

1. **Servidor API** dedicado (gunicorn) + TLS + catálogo de API keys por empresa (tabla) + refresh
   token con revocación (ya hay `sesiones`/jti).
2. **Ejecución periódica**: job del scheduler que llame a `scheduler_enterprise.procesar_pendientes` y
   a `ccp.cola.procesar` / campañas programadas.
3. **Eventos asíncronos**: cola/broker para el Event Bus (hoy síncrono) manteniendo la misma API.
4. **GraphQL** real (resolvers → servicios) y **webhooks salientes** por evento estándar.
5. **Dashboards GUI** de observabilidad y un panel de administración de plugins/reglas/schedules.

---

**Resultado:** Smart Manager AI queda consolidado como **plataforma tecnológica Enterprise** —API,
eventos, automatización, reglas, extensibilidad por plugins, auditoría reconstruible y observabilidad—
sobre una arquitectura limpia, desacoplada, multiempresa y API-First, preparada para crecer durante los
próximos años sin rediseñar su arquitectura.
