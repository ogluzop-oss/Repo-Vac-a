# Certificación Operacional — Etapa F · Fase F8

Certificación de preparación para **producción continua** del ERP Enterprise Smart Manager AI, sobre la
infraestructura existente y las fachadas operacionales añadidas en las fases F1–F7 (todas aditivas,
reversibles y sin motores paralelos).

**Fecha:** 2026-07-18 · **Suite:** 452 passed, 1 skipped (helm no instalado) · **Regresiones:** 0.

## Dimensiones certificadas

| Dimensión | Evidencia | Estado |
|-----------|-----------|--------|
| **Rendimiento** | 14 índices `id_empresa` (migr 0151); `EXPLAIN` de la consulta operacional → `ref`/`idx_f5_sch_ej_emp` (no full-scan). Pruebas de carga F7: 8 subsistemas × 300, **0 errores**. | ✅ |
| **Estabilidad** | 452 pruebas verdes; 2 400 operaciones de carga sin error; p95/p99 estables (sin colas largas). | ✅ |
| **Disponibilidad** | Supervisión de nodos (`cloud.nodes/heartbeat`), failover (`cloud.failover`), edge (`edge_node`); orquestador `recuperacion.estado_ha`. | ✅ |
| **Recuperación** | `recuperacion.recuperar_todo`: outbox (watchdog), scheduler (`procesar_pendientes`), inbox (idempotente), Event Bus (**replay, sin reentrega** → sin doble procesamiento). | ✅ |
| **Seguridad** | Rotación de secretos operacional **verificada** (preserva el texto plano); anomalías → alertas; caducidad/revocación de tokens; bloqueo por cuenta; `estado_seguridad`. | ✅ |
| **Escalabilidad** | Multiempresa/multitienda estricto (aislamiento por tenant verificado); imagen Docker + Kubernetes/Helm + HPA (Etapa E · F4). | ✅ |

## Superficies operacionales (F1–F7)

- **F1 · Observabilidad**: `/api/v1/metrics` expone métricas de negocio + API + **Scheduler/Event Bus/
  Marketplace/SDK** (motor Prometheus único); correlación E2E (`X-Correlation-ID`).
- **F2 · Operación**: `/api/v1/system/status | status/tenant | selftest | diagnostico` (autenticado,
  aislado por tenant). Self-test: 14 checks, 0 fallidos.
- **F3 · Alta disponibilidad**: `resiliencia.recuperacion` (autoheal/HA unificado).
- **F4 · Backup operacional**: `dr.backup_operacional` (planificación/verificación/restauración
  total·tenant·**parcial**/simulacros/estado).
- **F5 · Rendimiento**: migración de índices 0151 (idempotente, reversible).
- **F6 · Seguridad operacional**: `seguridad.operacion` (rotación verificada, anomalías→alertas, estado).
- **F7 · Pruebas de carga**: `tests/load/` + [`PRUEBAS_CARGA_F7.md`](PRUEBAS_CARGA_F7.md).

## Resultados de carga (N=300, 0 errores)

| Subsistema | ops/s | p95 (ms) |
|---|---|---|
| API | 2 569 | 0.65 |
| Marketplace | 268 | 6.50 |
| SDK | 191 546 | 0.005 |
| Scheduler | 1 023 | 1.47 |
| Event Bus | 1 205 304 | 0.001 |
| Comercio Digital | 21 826 | 0.06 |
| BI/Observabilidad | 124 | 10.30 |
| IA | 69 | 20.83 |

## Huecos críticos detectados en F8

**Ninguno.** Todas las dimensiones verifican con la infraestructura existente + fachadas F1–F7. No se
realizaron cambios de código en esta fase.

## Veredicto

**APTO para producción continua.** El sistema es observable, operable, recuperable, seguro y escalable,
reutilizando exclusivamente la infraestructura existente y manteniendo la arquitectura congelada.

## Mejoras recomendadas (no implementadas — Regla 3)

Consolidadas de F1–F7: instrumentación push de métricas con labels; reentrega segura de Event Bus
(requiere semántica de entrega — decisión de arquitectura); bloqueo inteligente por IP; rotación de la
clave de firma JWT; carga distribuida real (k6/Locust) sobre Kubernetes/HPA; índices compuestos por
profiling de producción.
