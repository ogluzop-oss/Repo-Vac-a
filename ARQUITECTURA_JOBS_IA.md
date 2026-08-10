# ARQUITECTURA — JOBS ASÍNCRONOS + WORKER IA (Fase 10)

## Motivación

Prophet (forecasting/retraining) es CPU-intensivo y puede bloquear el proceso web. Se descarga a **jobs
asíncronos** procesados por un **worker** separable (servicio ECS `worker-ia`). NO es un segundo motor de IA:
el worker INVOCA `services/prediccion` existente.

## Flujo

```
Request/UI → encolar_prediccion(id_empresa, ...) → JobQueue
                                                      │
                                     worker.procesar(job)  (proceso worker / tick scheduler)
                                                      │
                          forecasting.predecir_ventas / retraining.retrain / evaluar_degradacion
                                                      │
                              guarda resultado + audita + emite 'prediccion.job_finalizado'
                                                      │
                                        Event Bus → SSE (canal 'prediccion') → UI
```

## Contexto de tenant OBLIGATORIO

`Job(id_empresa, tipo, payload, usuario_origen, correlation_id, created_at)` — `id_empresa` es obligatorio
(ValueError si falta). El worker ejecuta el job EXCLUSIVAMENTE en el tenant del job; nunca en otro. Auditoría:
`JOB_CREADO / JOB_INICIADO / JOB_COMPLETADO / JOB_FALLIDO` en `log_auditoria`.

## Tipos soportados

`prediccion.forecast` · `prediccion.retrain` · `prediccion.degradacion`. Todos reutilizan los servicios reales
y mantienen versionado/métricas/backtesting/degradación.

## Backends (`services/jobs`)

| Backend | Uso | Estado |
|---|---|---|
| `LocalQueue` | DEV / single-proceso (en memoria, thread-safe) | 🟢 |
| `SQSQueue` | AWS (Amazon SQS, boto3 perezoso) | 🔵 PREPARADO |

Factory `obtener_cola()` por `JOB_QUEUE_BACKEND=local|sqs`. Sin boto3/cola, `sqs` es error explícito.

## Separación de responsabilidades

- **SQS** → jobs asíncronos. **Redis** → distribución de eventos SSE. **Event Bus** → dominio. No se mezclan.
