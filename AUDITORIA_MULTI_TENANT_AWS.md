# AUDITORÍA — AISLAMIENTO MULTI-TENANT (AWS, Fase 10)

Fecha 2026-07-27. Auditoría read-only del aislamiento por tenant en las abstracciones nuevas y su relación con
los flujos reales.

## 1. Abstracciones nuevas — aislamiento VERIFICADO (🟢)

| Superficie | Garantía | Evidencia |
|---|---|---|
| Storage (guard base) | clave `tenant/{id_empresa}/…`; toda op valida el tenant | `test_storage_tenant_aislamiento`: B no lee/borra/firma/metadatos de A |
| Storage — path traversal | rechaza `..`, `/` inicial, `\`, prefijo de otro tenant | mismo test |
| Storage — `id_empresa` obligatorio | vacío/None → `TenantIsolationError` | `test_storage_id_empresa_obligatorio` |
| Presigned URL | exige tenant correcto **y** `autorizado=True` (RBAC del llamador) | `test_storage_url_firmada_requiere_autorizacion` |
| Eventos (hub + distribución) | reparto filtra por `id_empresa`; A no llega a B | `test_distribucion_reparto_aislado_por_tenant`, `_inprocess_..._preserva_tenant` |
| Distribución — anti-loop | evento remoto no se reenvía (`_remoto=True`) | `test_distribucion_forward_local_no_remoto` |
| Jobs | `Job` exige `id_empresa`; worker ejecuta sólo en ese tenant | `test_job_exige_tenant`, `test_worker_procesa_forecast_tenant_aislado` |

## 2. Matiz crítico de honestidad

El aislamiento del **guard de storage sólo protege lo que pasa por `StorageProvider`**. Como la adopción es
**0%** (ver `AUDITORIA_STORAGE_INTEGRATION.md`), los ~96 flujos reales de documentos **todavía escriben en
filesystem sin ese guard**. El aislamiento de esos ficheros hoy depende de la lógica de negocio y del
`id_empresa` en `documentos_registro`, no del nuevo guard. → El aislamiento multi-tenant del NUEVO storage es
🟢 en el componente, pero 🟡 a nivel de sistema hasta que se integre.

## 3. Aislamiento existente (previo, se conserva)

- BD: 404 tablas aisladas por tenant + `tenant_guard` (auditorías previas, 0 fugas nuevas).
- SSE: tenant SIEMPRE del token; hub filtra por `id_empresa`.
- RBAC/MFA/WebAuthn/auditoría: intactos.

## 4. Superficies AWS (cuando se activen)

| Superficie | Aislamiento previsto | Estado |
|---|---|---|
| S3 | prefijo por tenant + IAM condicional + presigned validada | 🔵 (guard software 🟢) |
| Redis (distribución) | `id_empresa` en el evento; hub filtra | 🔵 (ver defecto self-echo en `AUDITORIA_JOBS_SQS_REDIS`) |
| SQS (jobs) | `id_empresa` obligatorio en el Job + MessageAttribute | 🔵 |
| Backups/documentos S3 | prefijo por tenant | 🔵 |

## 5. Bypass buscados

- Path traversal / manipulación de `id_empresa` / clave de otro tenant → **bloqueados** (tests).
- Presigned sin autorización → **bloqueado**.
- Evento cross-tenant en distribución → **bloqueado** (filtro por tenant).
- **No se hallaron bypass** en las abstracciones nuevas. El riesgo real es de **cobertura** (0% de adopción),
  no de un fallo del guard.

**Veredicto**: aislamiento de componentes 🟢; aislamiento a nivel de sistema para documentos 🟡 (pendiente de
integrar StorageProvider).
