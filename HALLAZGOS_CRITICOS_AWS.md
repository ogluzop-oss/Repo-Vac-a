# HALLAZGOS CRÍTICOS Y ALTOS — Auditoría Final AWS (Fase 10)

Fecha 2026-07-27. Sólo severidad CRÍTICA/ALTA (+ un MEDIO relevante). **No se corrige nada** (auditoría). Los
defectos de los backends AWS están en caminos 🔵 no activos (sin infraestructura), por lo que **no afectan a la
operación actual**, pero deben resolverse antes del despliegue.

## H1 · StorageProvider NO integrado (0% adopción) — ALTA
- **Hallazgo**: 0 módulos usan `obtener_storage()`; ~96 ficheros escriben/leen documentos directamente en
  filesystem.
- **Archivos**: RRHH `documents/render/*_pdf.py`, `services/aeat/documento.py`, `gui/ventas.py`,
  `gui/etiquetas_precios.py`, `services/bi_corp/export.py`, `db/documentos.py`, … (patrón en ~96).
- **Impacto**: en Fargate (filesystem efímero) se perderían PDFs/nóminas/contratos/facturas; esos ficheros no
  pasan por el guard de tenant del nuevo storage.
- **Riesgo**: pérdida de datos en producción AWS; aislamiento no reforzado para documentos.
- **Recomendación**: migración gradual (Strangler) a `obtener_storage()`, priorizando RRHH/fiscal/facturación.
- **Prioridad**: ALTA. **Bloquea** el 🟢 limpio de la Fase 10 (por eso el veredicto es 🟡 con pendientes).

## H2 · RedisDistribution: self-echo (doble entrega) — ALTA (path 🔵)
- **Hallazgo**: `RedisDistribution` publica y se suscribe al MISMO canal → la instancia origen recibe su propio
  evento y lo entrega **dos veces** a sus clientes SSE. Sin filtro `instance_id`.
- **Archivo**: `src/services/eventbus/distribucion.py` (`publicar` L87 / `iniciar` L92-101).
- **Impacto**: eventos duplicados en la UI al escalar a multi-instancia con Redis.
- **Recomendación**: añadir `instance_id` y descartar mensajes propios en la entrega; manejar reconexión.
- **Prioridad**: ALTA (antes de activar Redis). No afecta hoy (Redis inactivo).

## H3 · Jobs sin idempotencia (SQS at-least-once) — MEDIA (path 🔵)
- **Hallazgo**: el worker no deduplica; SQS reentrega. Reproceso → `predecir_ventas` persiste modelo por
  ejecución → modelos duplicados.
- **Archivos**: `src/services/jobs/worker.py`, `src/services/jobs/sqs.py`.
- **Recomendación**: idempotencia por `correlation_id`/`job.id`; DLQ + visibility timeout; persistencia
  idempotente del modelo.
- **Prioridad**: MEDIA (antes de activar SQS).

## H4 · IaC `main.tf` con HCL inválido — BAJA
- **Hallazgo**: argumentos separados por coma dentro de bloques (`{ type = string, default = ... }`) — HCL no
  lo admite; `terraform validate` fallaría.
- **Archivo**: `infra/aws/main.tf` L29-31.
- **Impacto**: nulo hoy (skeleton no aplicado); corregir antes de usar la IaC.
- **Prioridad**: BAJA.

## No se hallaron (verificado)
- Secretos reales en Git/`.env.production.example` (sólo placeholders). ✅
- Bypass de tenant en las abstracciones nuevas (storage/eventos/jobs). ✅
- Segundo motor de forecasting/retraining (el worker reutiliza el único). ✅
- Fallback silencioso a S3/SQS inseguro (fallan explícito sin boto3). ✅

## Regla de detención
Todos los hallazgos quedan documentados; **ninguno se corrige** en esta auditoría. H2/H3 requieren además
infraestructura AWS para validarse → 🟣 en su validación real.
