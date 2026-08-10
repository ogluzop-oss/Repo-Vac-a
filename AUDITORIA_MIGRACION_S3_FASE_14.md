# AUDITORÍA — MIGRACIÓN DE DOCUMENTOS A S3 (Fase 14)

Fecha 2026-07-27. Read-only. Verifica la arquitectura de storage y el procedimiento de migración documental.

## Arquitectura (verificada)

- `StorageProvider` (base + guard tenant) · `LocalStorageProvider` · `S3StorageProvider` (boto3 perezoso,
  SSE-KMS, presigned) · factory `obtener_storage()` (sin fallback silencioso).
- `services/storage/documentos`: CREATE (`persistir_fichero`), READ (`abrir_documento`), DOWNLOAD
  (`url_descarga`), DELETE (`eliminar_documento`), LEGACY (`migrar_registro_legacy`/`migrar_documentos_legacy`).
- `documentos_registro` (migr 0164): `storage_key`, `storage_backend`, `mime_type`, `size_bytes`,
  `migracion_estado` (LEGACY|MIGRATED|MISSING|FAILED).

## Procedimiento de migración local → S3 (existe y es completo)

| Requisito | Soporte | Estado |
|---|---|---|
| Migración masiva | `migrar_documentos_legacy(id_empresa, limite=)` (por lotes) | 🟢 |
| Migración por doc | `migrar_registro_legacy(id_documento)` | 🟢 |
| On-read (al vuelo) | `abrir_documento`/`url_descarga` migran el LEGACY la primera vez | 🟢 |
| Reintentos | estado FAILED reintetable; `storage.migracion.migrar_local_a_s3` (checksum) | 🟢 |
| Checksum/integridad | lee bytes, verifica; `hash_documental`; `size_bytes` | 🟢 |
| Detección de duplicados | idempotente: salta si `storage_key` ya existe; en destino compara checksum | 🟢 |
| Idempotencia | ✅ (`test_h1_migracion_legacy_idempotente`) | 🟢 |
| Rollback | no destructivo (no borra el original); reversible | 🟢 |
| Validación de tenant | valida `id_empresa` en cada operación | 🟢 |
| No borra original automáticamente | ✅ (borrado físico = operación posterior explícita) | 🟢 |

## Seguridad del storage (Objetivo 4) — verificada

Tenant A **NO** puede, sobre documentos de B: leer / descargar / borrar / firmar URL / modificar `storage_key` /
manipular `id_empresa` / path traversal / usar clave de otro tenant. La `storage_key` se resuelve **siempre**
desde BD por `id_documento`; nunca del cliente. Tests: `test_h1_read_tenant_aislado`, `_url_descarga_tenant`,
`_delete_seguro`, `_no_acepta_clave_del_cliente`.

## Depende de infraestructura externa (🟣)

Bucket privado + Block Public Access, SSE-KMS (cifrado en reposo), bucket policy, IAM efectiva, presigned real,
expiración — se validan sobre S3 real. No se simulan.

## Estado

🟢 **Arquitectura y procedimiento de migración documental completos y seguros** (masiva/on-read/idempotente/
checksum/tenant). Ejecución sobre S3 real + controles de bucket/KMS/IAM 🟣 externos.
