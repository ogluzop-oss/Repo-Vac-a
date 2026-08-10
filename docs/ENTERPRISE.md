# Smart Manager AI — Documentación Enterprise (Release 1.0)

Documentación definitiva de la plataforma. Consolida y enlaza la documentación detallada existente.
Arquitectura **congelada** (ver [ADR](architecture/adr/) y [Contratos congelados](CONTRATOS_CONGELADOS_G2.md)).

---

## 1. Arquitectura final

ERP Enterprise por capas **API-First** con dependencia estricta `UI / API → servicios → dominio → datos`
+ `platform` (capacidades transversales). Detalle y vistas: [`architecture/`](architecture/README.md) ·
[diagramas C4/dependencias/eventos](architecture/diagrams.md).

```
src/gui/        UI PyQt6 (foundation → components → panels → windows)
src/api/        Enterprise REST API (/api/v1) + GraphQL ; consume servicios
src/backend/    App Flask/WSGI (gunicorn) + probes/metrics
src/services/   Lógica de negocio (78 dominios)
src/platform/   capabilities · registry · discovery · gateway · cloud · contracts
src/db/         Acceso a datos (pymysql) ; src/database/migraciones (151)
src/sdk/        SDK de plugins ; sdk/ SDK cliente distribuible (pip/npm)
```

## 2. ADR definitivos

13 decisiones de arquitectura indexadas en [`architecture/adr/`](architecture/adr/README.md): API-First,
motores únicos (N7), Strangler + migraciones reversibles, multitenancy estricta, platform.capabilities,
Event Bus, seguridad (RBAC/JWT/Secret Manager), Adapter Pattern, UI Enterprise Shell, paginación REST,
conectores Enterprise, SDK desde OpenAPI, Kubernetes/Helm.

## 3. Roadmap ejecutado (Etapas A–G)

| Etapa | Contenido | Estado |
|---|---|---|
| **A–D** | Núcleo ERP + dominios Enterprise (comercio, TPV, compras, ventas, inventario, logística, RRHH, finanzas, CRM, MRP, GMAO, SAT, calidad, BI, IA, fiscalidad, workflow, RBAC…) | ✅ |
| **E** | Enterprise Platform Completion (paginación API, conectores, SDK, K8s/Helm, ADR/diagramas) | ✅ |
| **F** | Operations & Production Readiness (observabilidad, operación, HA, backup, índices, seguridad, carga, certificación) | ✅ |
| **G** | Enterprise Certification & Release 1.0 (auditoría, contratos congelados, certificaciones, limpieza, documentación) | ✅ |

## 4. Módulos implementados (78 dominios de servicio)

Comercial/Comercio Digital · TPV · Compras/Aprovisionamiento · Ventas/Facturación · Inventario/Kárdex ·
Logística · RRHH/Nómina · Finanzas/Tesorería/SEPA · Contabilidad · Fiscalidad (AEAT/Verifactu/Facturae) ·
CRM · Producción/MRP · GMAO · SAT/Helpdesk · Calidad · BI/BI-corp/DW · IA/Inteligencia · Automatización ·
Workflow/BPM/BPD · Marketplace · SDK · API pública · Comunicaciones/CCP · Gobierno · Gemelo Digital ·
Simulador · Autonomía · Resiliencia/Offline · DR · Observabilidad · Seguridad · SaaS/multitenant ·
Videovigilancia · SOMA (copiloto).

## 5. Capacidades Enterprise (motores únicos — N7)

Event Bus · Scheduler · Rules · Workflow · IA · BI · Marketplace · SDK/Plugins · Observabilidad ·
Secret Manager · RBAC/ACL · platform.capabilities · Adapter Pattern (conectores) · DR/Backup · Cloud
(nodos/failover). Cada capacidad tiene **una** implementación reutilizada en todo el sistema.

## 6. Dependencias

Runtime (`requirements.txt`): PyQt6, PyMySQL + DBUtils (pool), Flask + gunicorn, cryptography, pyOpenSSL,
signxml (XAdES), argon2-cffi, PyJWT, reportlab, Pillow, pandas/numpy, openpyxl, requests, qrcode,
python-barcode, prophet (opcional, forecasting). Sin ORM (pymysql directo). Ver notas de versión pinneada
en `requirements.txt` (compatibilidades fiscales críticas).

## 7. Principios arquitectónicos

1. **API-First** (REST/GraphQL → servicios → dominio → datos).
2. **N7 — motores únicos**: prohibido crear motores paralelos; reutilizar siempre.
3. **Strangler + migraciones reversibles**; compatibilidad hacia atrás.
4. **Multitenancy estricta**: `id_empresa` del token, nunca del cuerpo.
5. **Provider-agnostic + degradable** (Adapter Pattern, capabilities → None).
6. **Secretos nunca en código** (Secret Manager).
7. Ver reglas permanentes en [`CLAUDE.md`](../CLAUDE.md) y [ADR](architecture/adr/).

## 8. Convenciones

- **Migraciones**: `NNNN_nombre.py` en `src/database/migraciones/`, registradas en `MODULOS`, con
  `VERSION/DESCRIPCION/REVERSIBLE/aplicar(cur)/revertir(cur)`, idempotentes. Ver [migraciones.md](migraciones.md).
- **UI**: `QtEnterpriseWindow`/`QtEnterprisePanel` + librería `gui/components`; sin lógica de negocio en GUI.
- **API**: routers en `src/api/routers`, `@requiere_auth(permiso)`, paginación estándar
  (`limit/offset/cursor/sort/order/filters`).
- **Eventos**: solo eventos de dominio por el Event Bus; solo eventos de UI por el Event Registry de UI.
- **Tests**: `tests/unit` (rápidos) + `tests/integration` (BD) + `tests/load` (carga). Ver [testing.md](testing.md).

## 9. Guía para desarrolladores

1. Requisitos: Python 3.11+, MariaDB, `.env` (DB_HOST/USER/PASSWORD/NAME/PORT). `pip install -r requirements.txt`.
2. Arranque UI: `python src/main.py`. Backend API: `gunicorn -w4 -b0.0.0.0:8000 wsgi:app`.
3. Tests: `QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python -m pytest tests/unit`.
4. Añadir una pantalla → shell Enterprise + `components`. Añadir lógica → `services/`. Añadir tabla →
   migración numerada reversible. Añadir endpoint → router + `requiere_auth`. **Nunca** crear un motor
   paralelo: reutilizar la capacidad existente vía `platform.capabilities`.
5. SDK cliente: [`sdk/`](../sdk/README.md). Plugins: `src/sdk` + Marketplace.

## 10. Guía de despliegue

- **Docker/Compose**: `Dockerfile` + `docker-compose.yml`/`.prod.yml` (gunicorn `wsgi:app` en `:8000`).
- **Kubernetes**: [`deploy/k8s`](../deploy/k8s/README.md) (`kubectl apply -k`) — ConfigMap/Secret/Deployment/
  Service/Ingress/HPA, probes `/api/v1/live` y `/ready`.
- **Helm**: [`deploy/helm/smart-manager`](../deploy/helm/smart-manager/README.md).
- Secretos gestionados fuera de git; BD gestionada aparte. Ver [tenancy.md](tenancy.md), [seguridad.md](seguridad.md).

## 11. Guía de operación

- **Health**: `/api/v1/live` · `/ready` · `/health` · `/metrics` (Prometheus).
- **Estado operacional**: `/api/v1/system/status | status/tenant | selftest | diagnostico`.
- **Observabilidad**: métricas de negocio/API/Scheduler/EventBus/Marketplace/SDK; correlación `X-Correlation-ID`.
- **Alta disponibilidad / recuperación**: `resiliencia.recuperacion.recuperar_todo` (outbox/scheduler/inbox/
  eventbus-replay/HA).
- **Backup/DR**: `dr.backup_operacional` (planificación/verificación/restauración total·tenant·parcial/
  simulacros). Ver [RUNBOOK_BACKUP.md](RUNBOOK_BACKUP.md).
- **Seguridad operacional**: `seguridad.operacion` (rotación verificada, anomalías→alertas). Ver
  [Certificación operacional](CERTIFICACION_OPERACIONAL_F8.md).

## 12. Guía de mantenimiento

- **Migraciones**: añadir `NNNN_*.py` reversible; aplicar con `db.migrador.aplicar_pendientes`. 151 aplicadas.
- **Contratos**: no eliminar/renombrar endpoints/eventos/conectores certificados (ver
  [Contratos congelados](CONTRATOS_CONGELADOS_G2.md)); cambios de ruptura → nueva versión mayor (`/api/v2`).
- **Tests**: mantener `tests/unit` verde; `tests/load/run_load.py` para regresión de rendimiento.
- **Deuda residual conocida**: goldens RRHH-PDF y asserts de conteo GUI a actualizar; deuda de lint ruff
  (no bloqueante); ver informes de certificación G3/G7.
- **Extensión post-1.0**: siempre aditiva (nuevos endpoints/eventos/conectores/plugins); reutilizar motores.

---

**Documentación definitiva — Smart Manager AI Enterprise 1.0.** Arquitectura congelada.
