# IMPLEMENTACIÓN DE CORRECCIONES AWS — FASE 11

Fecha 2026-07-27. Corrección de los hallazgos de la Auditoría Final de Fase 10 (H1-H4). Aditivo, N7, sin
infraestructura, sin simulación. Regresión: **661 passed, 1 skipped, 0 failed** (baseline 652 → +9 tests).

## H1 · Integración de StorageProvider (persistencia documental)

- **Hallazgo**: 0% de adopción; los documentos de negocio sólo vivían en el filesystem efímero.
- **Análisis**: la superficie real de documentos empresariales persistentes son **17 ficheros** que pasan por
  el **chokepoint único** `db.documentos.registrar_documento` (el resto de las ~96 coincidencias eran
  temporales/caché/preview/barcode/matplotlib — NO se migran, por diseño).
- **Corrección (N7, un solo punto)**: nueva fachada `services/storage/documentos.persistir_fichero` +
  **write-through** cableado en `registrar_documento`: al registrar un documento, se sube una copia durable al
  `StorageProvider` bajo `tenant/{id_empresa}/{tipo}/{nombre}`. En `local` = copia tenant-aware; en `s3` =
  objeto durable (resuelve la pérdida en Fargate). Aditivo y bulletproof (nunca rompe el registro).
- **Estado**: 🟡 **avanzado, no cerrado del todo**. Cubre la **persistencia (write)** de los 17 flujos en un
  punto, con aislamiento por tenant. **Pendiente** (honesto): (a) la generación sigue escribiendo primero en
  ruta local temporal; (b) lectura/descarga/borrado desde S3 y almacenamiento de la clave S3 en
  `documentos_registro` (requiere migración + retoque del visor). Ver `AUDITORIA_STORAGE_INTEGRATION.md`.

## H2 · Redis self-echo — CORREGIDO 🟢

- Cada instancia tiene `INSTANCE_ID`. `RedisDistribution.publicar` sella el evento con `_source_instance_id`;
  al recibir, `_entregar_si_remoto` **descarta el eco propio** (`es_eco`). Helpers `sellar`/`es_eco`/
  `limpiar_sello` + `InProcessBroker` determinista (para tests multi-instancia sin red).
- **Resultado**: publicar en A → A recibe 0 (sin eco), B y C exactamente 1; tenant intacto; sello limpiado.
- No rompe Local/InProcess ni el comportamiento local. Tests: `test_h2_*`.

## H3 · Idempotencia y robustez de jobs — CORREGIDO 🟢

- `Job.attempt`; errores clasificados `JobErrorPermanente`/`JobErrorTemporal`.
- `services/jobs/idempotencia` (backend `memory`/`db`): antes de ejecutar, si el job ya está COMPLETADO →
  **no re-ejecuta** (`JOB_DUPLICATE_IGNORED`). Permanente → FAILED (DLQ, sin reintento). Temporal → reintento
  controlado hasta `JOB_MAX_ATTEMPTS`/`SQS_MAX_RECEIVE_COUNT` → DLQ.
- `SQSQueue`: **borra el mensaje sólo tras éxito** (`confirmar`), permitiendo reentrega/DLQ; `VisibilityTimeout`
  y `SQS_DLQ_URL` configurables (nombres, sin infra).
- Auditoría: `JOB_CREADO/INICIADO/RETRIED/COMPLETADO/FAILED/DUPLICATE_IGNORED`. Tests: `test_h3_*`.

## H4 · Terraform IaC — CORREGIDO 🟢 (validate 🟣 externo)

- `infra/aws/main.tf`: argumentos ahora en líneas separadas (HCL válido); sin secretos ni valores hardcodeados.
- **Bloqueo**: `terraform` NO está instalado en el entorno → `terraform validate` no se puede ejecutar aquí
  (🟣 externo). El HCL es sintácticamente correcto por revisión + test `test_h4_hcl_sin_comas_invalidas`.

## Ficheros

- **Nuevos**: `services/storage/documentos.py`, `services/jobs/idempotencia.py`, `tests/unit/test_aws_fase11.py`.
- **Modificados**: `eventbus/distribucion.py` (instance_id/sellar/es_eco/InProcessBroker + RedisDistribution),
  `jobs/base.py` (attempt + JobError*), `jobs/worker.py` (idempotencia+retries+DLQ), `jobs/sqs.py`
  (confirmar/rechazar+visibility), `jobs/__init__.py` (reset), `db/documentos.py` (write-through),
  `infra/aws/main.tf` (HCL), `.env.production.example` (SQS DLQ/visibility, JOB_*, INSTANCE_ID).

## Veredicto

H2/H3/H4 **cerrados**; H1 **avanzado** (durabilidad resuelta en el chokepoint) pero **no cerrado del todo**
→ **FASE 11 COMPLETADA PARCIALMENTE**. No se declara 🟢 limpio. AWS PRODUCTION-DEPLOYED: 🔴.
