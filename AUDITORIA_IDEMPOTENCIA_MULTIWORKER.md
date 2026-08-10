# AUDITORÍA — IDEMPOTENCIA MULTI-WORKER (Fase 12, H3)

Fecha 2026-07-27. Cierre del pendiente "backend DB de idempotencia para multi-worker SQS". No se mezcla con H1.

## Estado previo (Fase 11)

Idempotencia con backend `memory`: válida para **DEV/single-process/tests**, pero **insuficiente** para varios
workers concurrentes (cada proceso tenía su propia memoria → dos workers podían ejecutar el mismo job).

## Requisito de producción

Con **SQS + múltiples workers ECS**, la idempotencia debe ser **atómica y compartida**. Backend `db`
(`JOB_IDEMPOTENCY_BACKEND=db`) es **obligatorio en producción**; `memory` queda reservado a DEV/tests.

## Implementación (atómica, sin segundo sistema de jobs)

- Migración `0165_jobs_idempotencia`: tabla `jobs_idempotencia(job_id PK, id_empresa, estado, attempt, ...)`.
- `idempotencia.reclamar(job_id, id_empresa=)` — **reclamo atómico**:
  - `INSERT (job_id, 'EN_CURSO')` → si el PK ya existe, `IntegrityError` en todos los workers menos uno.
  - Si existe: `UPDATE ... SET estado='EN_CURSO' WHERE job_id=? AND estado IN ('PENDIENTE','FALLIDO')`
    (atómico por `WHERE`); `rowcount==1` → reclamado; si no, se lee el estado.
  - Devuelve `claimed` / `duplicate` (COMPLETADO) / `en_curso` (otro worker).
- `worker.procesar` usa `reclamar`: sólo el worker que obtiene `claimed` ejecuta; los demás →
  `JOB_DUPLICATE_IGNORED`.

## Garantías (verificadas)

| Propiedad | Estado | Evidencia |
|---|---|---|
| Dos workers, mismo `job_id` → sólo uno ejecuta | 🟢 | `test_h3_reclamo_atomico_db`: `claimed` luego `en_curso` |
| Job completado → reentrega ignorada | 🟢 | tras `COMPLETADO` → `duplicate` |
| Atomicidad | 🟢 | PK `job_id` + `UPDATE ... WHERE` (InnoDB) |
| Backend memory (DEV) | 🟢 | `test_h3_reclamo_memoria` |
| Degradación sin tabla | 🟢 | `_db_reclamar` devuelve None → cae a memoria sin romper |
| Estados COMPLETED/FAILED/RETRYING | 🟢 | `marcar` + clasificación permanente/temporal (Fase 11) |
| No segundo sistema de jobs | 🟢 | reutiliza `services/jobs` |

## Condiciones de carrera

El `INSERT` con PK y el `UPDATE ... WHERE estado IN (...)` son atómicos a nivel de fila InnoDB → dos workers
concurrentes no pueden ambos obtener `claimed`. No se usan locks aplicativos ni polling.

## Honestidad

- Backend `db` **probado contra MariaDB local** (suite). Con **SQS real** (multi-worker distribuido) queda
  🟣 pendiente de validación en AWS.
- Producción **debe** fijar `JOB_IDEMPOTENCY_BACKEND=db` (ya en `.env.production.example`).

Estado: 🟢 idempotencia multi-worker implementada y probada (BD local) · 🟣 validación con SQS real externa.
