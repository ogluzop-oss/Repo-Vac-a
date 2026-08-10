# IMPLEMENTACIÓN H1 — STORAGE PERSISTENTE COMPLETO (Fase 12)

Fecha 2026-07-27. Cierre de H1: `StorageProvider` integrado en CREATE/READ/DOWNLOAD/DELETE + `storage_key`
persistente + migración legacy + visor. Aditivo, N7, sin infraestructura AWS, sin simulación.

## Cambios

| Fichero | Cambio |
|---|---|
| `migraciones/0164_documentos_storage.py` | ADD COLUMN `storage_key/storage_backend/mime_type/size_bytes/migracion_estado` en `documentos_registro` (idempotente, reversible) |
| `migraciones/0165_jobs_idempotencia.py` | Tabla `jobs_idempotencia` (dedup atómico multi-worker) |
| `services/storage/documentos.py` | **Capa única** CREATE (`persistir_fichero`) + READ (`abrir_documento`) + DOWNLOAD (`url_descarga`) + DELETE (`eliminar_documento`) + LEGACY (`migrar_registro_legacy`/`migrar_documentos_legacy`); guard tenant+RBAC en cada camino |
| `db/documentos.py` | `registrar_documento` captura la `storage_key` y la persiste (con conexión propia); |
| `gui/centro_documental.py` | `_ruta_existente` → si el fichero local no existe, **materializa desde StorageProvider** (tenant+RBAC) a un temporal (visor S3-ready); DEV sin cambios |
| `services/jobs/idempotencia.py` | `reclamar()` **atómico** (backend `db` vía PK / `memory`) |
| `services/jobs/worker.py` | usa `reclamar` (multi-worker seguro) en vez de check-then-mark |
| `tests/unit/test_aws_fase12.py` | 8 tests (create/read/download/delete/legacy/seguridad + reclamo atómico db/memory) |

## Flujos (objetivo cumplido)

- **CREATE**: generador → ruta temporal → `registrar_documento` → write-through a `StorageProvider`
  (`tenant/{id_empresa}/{tipo}/{nombre}`) → guarda `storage_key`/`backend`/`size`/`mime`/`MIGRATED`.
- **READ/DOWNLOAD**: `abrir_documento`/`url_descarga` resuelven el registro por `id_documento` en BD, validan
  `id_empresa` (tenant) + RBAC, obtienen la `storage_key` (nunca del cliente) y sirven bytes / presigned. Si el
  documento es LEGACY, se migra al vuelo.
- **DELETE**: `eliminar_documento` valida tenant+RBAC, borra el objeto vía `StorageProvider.borrar`, audita y
  elimina el registro. Si el borrado en storage falla → NO se pierde la metadata (marca `FAILED`, audita).
- **VISOR**: `centro_documental._ruta_existente` usa el fichero local si existe; si no (Fargate/S3), materializa
  desde el StorageProvider a un temporal para abrir/imprimir/compartir a nivel de SO.

## Seguridad (verificada por tests)

- Tenant A no puede leer/descargar/borrar documentos de B (aunque conozca el id) → `otro tenant`.
- La `storage_key` y el `id_empresa` SIEMPRE se resuelven en BD; nunca se aceptan del cliente.
- Clave saneada + guard de la clase base (path traversal / cambio de tenant bloqueados, Fase 10-11).

## Backend selection

`STORAGE_BACKEND=local` (DEV) / `s3` (AWS). Sin fallback silencioso (error explícito si `s3` sin config).

## Caveat honesto (menor)

Los 17 generadores siguen escribiendo primero un fichero temporal local (no se convirtieron a `BytesIO`, por
la regla de no tocarlos salvo imprescindible). Ese temporal es tolerante a filesystem efímero (la copia durable
está en S3). Recomendación futura opcional: borrar el temporal tras el write-through y/o generar a `BytesIO`.
