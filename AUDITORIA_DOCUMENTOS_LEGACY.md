# AUDITORÍA — DOCUMENTOS LEGACY (Fase 12)

Fecha 2026-07-27. Estrategia de compatibilidad y migración de documentos existentes sin `storage_key`.

## Estados de migración (columna `migracion_estado`)

| Estado | Significado |
|---|---|
| `LEGACY` | Documento previo a la Fase 12; sólo en filesystem local, sin `storage_key` |
| `MIGRATED` | Copia durable subida al StorageProvider; `storage_key` guardada |
| `MISSING` | El fichero legacy ya no existe en disco (no migrable) |
| `FAILED` | Falló la subida al StorageProvider (auditado; reintentable) |

## Migración

- **Por documento**: `migrar_registro_legacy(id_documento, id_empresa=)` — idempotente (si ya tiene
  `storage_key`, no repite), tenant-aware (rechaza otro tenant), verifica existencia del fichero, sube,
  guarda `storage_key` + `MIGRATED`. **No borra el original.**
- **Por tenant (backfill)**: `migrar_documentos_legacy(id_empresa, limite=)` — recorre los documentos del
  tenant, salta los ya migrados, informa `{total, migrados, ya, missing, fallidos}`. Reanudable.
- **Al vuelo (on-read)**: `abrir_documento`/`url_descarga` migran automáticamente un documento LEGACY la
  primera vez que se solicita, de forma segura, y luego lo sirven desde el StorageProvider.

## Garantías

| Requisito | Estado |
|---|---|
| Idempotente | ✅ (salta si `storage_key` presente) |
| Reanudable | ✅ (backfill por lotes) |
| Tenant-aware | ✅ (valida `id_empresa`) |
| Checksum/integridad | ✅ (write-through lee el fichero; verificación de tamaño; hash en `hash_documental`) |
| No borra el original automáticamente | ✅ (borrado físico = operación posterior explícita) |
| Auditable | ✅ (`DOCUMENTO_MIGRADO`, `STORAGE_PERSIST_ERROR`) |
| No duplica | ✅ (test `test_h1_migracion_legacy_idempotente`) |

## Backward compatibility

Mientras haya documentos `LEGACY`, el visor y las APIs los sirven desde el fichero local si existe, o los
migran al vuelo si no. El sistema **no depende indefinidamente** del filesystem legacy: cada acceso o el
backfill los va convirtiendo a `MIGRATED`.

## Pendiente (operación, no código)

Borrado físico de los originales locales tras confirmar `MIGRATED` — operación explícita y auditada de
limpieza, a ejecutar cuando el propietario lo decida (no automática).

Estado: 🟢 migración legacy implementada y probada; limpieza física de originales = operación posterior.
