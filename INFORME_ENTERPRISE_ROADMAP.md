# INFORME ENTERPRISE ROADMAP — Smart Manager AI · Fase V

> Mobile Platform · Web Portal · API Pública · Business Process Designer · AI Agents Platform ·
> Data Lake + Enterprise BI · Multi-Tenant Cloud Manager

Fase **aditiva** sobre el núcleo desacoplado (IOC, CCP, REST, GraphQL, Event Bus, Scheduler,
Workflow, Rules, Observabilidad, Plugins/Marketplace, Preparación Microservicios). **No modifica**
ninguna infraestructura existente: solo la extiende. API-First · Service-First · Event-First ·
Multiempresa · Multitienda · Compatible hacia atrás.

---

## 1. Arquitectura global

```
                 ┌──────────── INTERFACES (consumen REST/GraphQL, NUNCA SQL) ────────────┐
   Móvil (Android/iOS)      Portal Web (6 tipos)      Terceros (SDK + OAuth2)
        │                        │                          │
        └───────────► REST API  /  GraphQL Enterprise ◄──────┘
                              │
        ┌─────────────────────┴───────────────────── SERVICIOS (dominio) ───────────────┐
   CCP · Workflow · Rules · Scheduler · Event Bus · Observabilidad · Marketplace · BI/DW
        │            │          │                                        │
   AI Agents    Business    Data Lake (reutiliza bi_corp.dw)     Cloud Manager (reutiliza SaaS)
   Platform     Process                                          Multi-Tenant
                Designer
                              │
                        Dominio / BD (MariaDB)  ·  Service Registry (src/platform)
```

Regla transversal: **GraphQL/Mobile/Portal → Servicios → Dominio → BD**. Nunca acceso directo a BD
desde una interfaz.

---

## 2. Nuevos componentes (por bloque)

| Bloque | Paquete | Reutiliza | Notas |
|---|---|---|---|
| 1 · Mobile | `src/services/mobile/` (core/networking/auth/sync/push/sesion) | REST API, `seguridad.tokens`+MFA, notificaciones/CCP | Offline-first (outbox + conflictos). Cliente REST real (test-client). |
| 2 · Web Portal | `src/services/portal/` (portales/acceso/sesion_portal) | REST/GraphQL, tokens, observabilidad | 6 tipos con scopes de mínimo privilegio. |
| 3 · API Pública | `src/services/api_publica/` (developer/oauth/sdks/openapi) · migr `0135` | REST security, `tokens`, OpenAPI | OAuth2 client-credentials + scopes; SDK Py/JS/TS/C#/Java/PHP desde OpenAPI. |
| 4 · BPD | `src/services/bpd/` (bloques/diseno/compilador) · migr `0136` | **Workflow Engine** | Diseño versionado (borrador/publicado/rollback) → compila a Workflow. |
| 5 · AI Agents | `src/services/agents_platform/` (agente/capacidades) | **`services.agentes`** + CCP/Workflow/Rules | 12 agentes; cada uno módulo independiente. |
| 6 · Data Lake + BI | `src/services/datalake/` (lake/dashboards) | **`bi_corp.dw`** (mismo almacén) | ETL/snapshots/dashboards; sin segundo almacén. |
| 7 · Cloud Manager | `src/services/cloud_manager/` (tenants/licencias/monitorizacion) + GUI | **SaaS** (licensing/planes/métricas/backup), Observabilidad, plataforma | Panel maestro SUPERADMIN. |

Integración: los 7 subsistemas se auto-registran en el **Service Registry** (`platform.bootstrap`),
con descubrimiento por capacidad/ruta y dependencias declaradas hacia la infraestructura existente.

---

## 3. Reutilización de infraestructura (cero motores paralelos)

- **Workflow**: BPD compila a `workflow_engine.iniciar_proceso`; los agentes solicitan aprobaciones
  por el mismo motor. No se crea un segundo workflow.
- **BI/DW**: el Data Lake **es** una capa de orquestación sobre `bi_corp.dw` (mismos hechos).
- **SaaS**: el Cloud Manager delega altas/planes/consumo/backup en `services.saas`.
- **IA**: los agentes reutilizan los Especialistas IA (`services.agentes.manager`).
- **Seguridad**: Mobile/Portal/API pública reutilizan JWT/OAuth/MFA/scopes/rate-limit ya existentes.
- **Event Bus**: única vía de eventos (ningún bus nuevo).

---

## 4. Compatibilidad y rollback

- **Compatible hacia atrás**: todo es aditivo; ninguna firma/tabla existente se modifica.
- **Migraciones** `0135_api_publica`, `0136_bpd`: **aditivas, idempotentes y reversibles**
  (`revertir()` hace `DROP TABLE`). El resto de bloques no requiere esquema nuevo.
- **Rollback funcional**: BPD (rollback de versión publicada), Marketplace (rollback de plugin),
  Cloud Manager (suspender/reactivar), tokens revocables. Rollback técnico: desregistrar del
  Service Registry y quitar las tarjetas de menú — sin impacto en el núcleo.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Interfaz accediendo a BD | Test que prohíbe `src.db`/SQL en Mobile/Portal y en los resolvers GraphQL. |
| Fuga entre empresas (multi-tenant) | Tenant siempre del token; tests de aislamiento (API pública, BPD, Cloud). |
| Duplicar motores | Tests que verifican delegación (BPD→Workflow, agents→especialistas, lake→DW). |
| GUI + audio de SOMA (heap) | Toda GUI nueva (Cloud Manager) es **inline, sin modales**. |
| Cloud Manager visible a no-superadmin | Tarjeta y ventana gateadas a `SUPERADMIN`. |

---

## 6. Preparación futura (declarado, no implementado)

- **Apps nativas**: la plataforma móvil es el contrato; la app Android/iOS consume el mismo REST.
- **Frontend web real**: el portal declara tipos/scopes/sesión; el SPA consume REST/GraphQL.
- **SDK autogenerados**: desde el OpenAPI (fuente única).
- **Editor visual BPD**: el modelo (grafo/versiones/compilador) está listo para un lienzo drag&drop.
- **Federación GraphQL, subscriptions en tiempo real, transporte de red del Gateway**: preparados.

---

## 7. Validación (pruebas obligatorias)

- **168 tests unit verdes** (incluye 3 suites nuevas Fase V: `test_fase5_frontends`, `test_fase5_bpd`,
  `test_fase5_ia_bi_cloud` = 19 tests) + todas las suites previas (REST/GraphQL/Workflow/Scheduler/
  CCP I-II/Event Bus/Rules/Plugins/Marketplace/Observabilidad/Microservicios). **Sin regresiones.**
- Verificado: consumo REST/GraphQL sin SQL en interfaces; OAuth2+scopes; BPD versionado+rollback+
  compilación a Workflow; agentes reutilizan Especialistas; Data Lake delega en DW; Cloud Manager
  reutiliza SaaS; aislamiento multiempresa (0 cruces); registro en la plataforma.

---

## 8. Recomendaciones técnicas

1. Instalar `graphene`/`strawberry` cuando se quiera GraphQL nativo (el registry ya lo alimenta).
2. Añadir `psutil` para métricas reales de sistema en el Cloud Manager (hoy degradable).
3. Cuando exista un microservicio real, exponer su `ServiceContract` con `health` y latir por
   `platform.heartbeat` — el Gateway/Routing ya lo enruta sin cambios.
4. Generar los SDK públicos en CI desde `openapi_publica.documento()`.
5. Mantener la regla en revisión de código: **ninguna interfaz importa `src.db`**.

---

**Estado**: Fase V completada y validada. Smart Manager AI queda preparado para apps móviles
oficiales, portal web, ecosistema de desarrolladores, automatización visual de procesos, agentes
inteligentes, Data Lake/BI corporativo y administración SaaS multiempresa — **sobre una única
arquitectura desacoplada, sin rediseñar el núcleo**.

---

# FASE VI — Plataforma SaaS distribuida mundial

> Bloque 11 Cloud Distributed Architecture · Bloque 12 Cloud Observability · Bloque 13 Global SaaS Platform

Fase **aditiva** de preparación para despliegue distribuido. No divide el ERP ni activa red: prepara
la arquitectura para operar en múltiples nodos/regiones/centros de datos con el mismo núcleo.

## Nuevos componentes

| Bloque | Paquete | Reutiliza | Notas |
|---|---|---|---|
| 11 · Cloud Distributed | `src/platform/cloud/` (nodes/heartbeat/cluster/discovery/routing/failover/storage) | Service Registry lógico | Node Registry físico, LB (RR/LeastConn/RegionFirst/Sticky), failover Primary→Secondary→Recovery **preparado**, storage abstraction Local/S3/Azure/GCS/MinIO. |
| 12 · Cloud Observability | `src/services/observabilidad/cloud/` (tracing/metricas/log_collector/alertas/dashboard) | Observabilidad Enterprise (correlation/tracing/metricas/alertas) | Trace/Span/Correlation/**Communication**/**Workflow** ID; logs ELK/OpenSearch/Loki **preparado**; Cloud Dashboard. |
| 13 · Global SaaS | `src/services/saas_global/` (regiones/planes_global/limites/consumo/feature_flags/configuracion_global/deployment) · migr `0137` | SaaS (licensing/planes/métricas/branding), i18n, Cloud | 5 regiones + resolución Region→Cluster→Node→Tenant; 6 planes; límites+consumo; **Feature Flags Cloud** jerárquicos; despliegue Cloud/On-Premise/Hybrid/Edge. |

## Reutilización (cero motores paralelos)

- **Sin segundo Event Bus/Scheduler/Workflow/IOC/CCP/Rules**: el Cloud usa el Service Registry
  existente; la Observabilidad Cloud **extiende** (no modifica) `observabilidad`; el Global SaaS
  reutiliza `saas.licensing/planes/métricas/branding` y **no** duplica `planes_saas`/`facturas_saas`.
- Migración `0137` añade **solo lo nuevo**: `saas_regiones`, `empresa_region`, `saas_limites`,
  `saas_consumo`, `cloud_feature_flags` (aditiva, idempotente, **reversible**).

## Compatibilidad, rollback y riesgos

- Todo aditivo; Node/Cluster/Feature-flags con precedencia jerárquica (usuario>empresa>plan>región>
  global). Failover y balanceo **no ejecutan** (preparación). Storage cloud degrada a Local.
- Rollback: `revertir()` de `0137`; desregistrar del Service Registry; nada del núcleo cambia.

## Validación

- **184 tests unit verdes** (3 suites nuevas Fase VI: `test_fase6_cloud`, `test_fase6_observability`,
  `test_fase6_saas_global` = 16 tests) + todas las anteriores. **Sin regresiones.**
- Verificado: registro/descubrimiento de nodos, balanceo (RR/LeastConn/RegionFirst/Sticky), failover
  preparado, cluster health, storage abstraction; tracing distribuido, dashboards cloud, logging
  centralizado preparado, alertas; regiones+resolución, planes, límites+gate de consumo, feature
  flags jerárquicos, config global, deployment; **aislamiento multiempresa/multi-región (0 cruces)**.

**Estado final**: Smart Manager AI es un ERP Enterprise **y** una plataforma SaaS global preparada
para despliegues distribuidos multi-región, manteniendo un único núcleo funcional y sin rediseñar la
arquitectura cuando llegue el momento de operar en múltiples centros de datos.
