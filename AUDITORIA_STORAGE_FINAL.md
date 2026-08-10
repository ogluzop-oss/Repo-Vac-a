# AUDITORÍA STORAGE FINAL (Fase 13)

Fecha 2026-07-27. Verificación final de la integración de StorageProvider (cierre H1, Fase 12). Read-only.
Amplía `AUDITORIA_FINAL_STORAGE_INTEGRATION.md`.

## Flujos documentales (inventario real)

- **18 ficheros** invocan `db.documentos.registrar_documento` (chokepoint único). Todos pasan por el
  write-through a `StorageProvider` y guardan `storage_key`. No se detecta ningún flujo de persistencia
  empresarial fuera del chokepoint.

| Camino | Punto | StorageProvider | Tenant | RBAC | Estado |
|---|---|---|---|---|---|
| CREATE | `registrar_documento`→`persistir_fichero` | ✅ | ✅ | (interno) | 🟢 |
| READ | `abrir_documento` | ✅ | ✅ | ✅ | 🟢 |
| DOWNLOAD | `url_descarga` (presigned) | ✅ | ✅ | ✅ + autorización | 🟢 |
| DELETE | `eliminar_documento` | ✅ | ✅ | ✅ | 🟢 |
| LEGACY | `migrar_registro_legacy` / on-read | ✅ | ✅ | — | 🟢 |
| VISOR | `_ruta_existente` (fallback storage) | ✅ | ✅ | ✅ | 🟢 |

## Seguridad de acceso (verificada)

- `storage_key` y `id_empresa` se resuelven SIEMPRE desde BD por `id_documento`; **nunca** del cliente.
- Cross-tenant read/download/delete → `otro tenant` (tests `test_h1_*`).
- Path traversal / cambio de tenant / clave arbitraria → `TenantIsolationError` (guard base, Fase 10-11).
- Presigned sólo tras autorización (`autorizado=True`).
- Borrado: si falla en storage, NO se pierde metadata (marca `FAILED`, audita).

## Fargate / filesystem efímero

- READ/DOWNLOAD/VISOR no dependen de que el fichero local persista: si no existe, se materializa/sirve desde
  StorageProvider. Verificado por diseño (`_ruta_existente` + `abrir_documento`) y por los tests de lectura.
- CREATE persiste durablemente (S3 en AWS). **Observación menor**: la generación produce un temporal local
  antes del write-through (tolerable en FS efímero; durabilidad en S3).

## Migración legacy

Idempotente, reanudable, tenant-aware, no destructiva; estados LEGACY/MIGRATED/MISSING/FAILED
(`migracion_estado`, migr 0164). Ver `AUDITORIA_DOCUMENTOS_LEGACY.md`.

## Backend

`STORAGE_BACKEND=local|s3`; sin fallback silencioso (error explícito si `s3` sin config/boto3).

## Veredicto

🟢 **Storage integrado y seguro** en todos los caminos, multi-tenant + RBAC. Validación de S3 real (presigned,
durabilidad) 🟣 externa. Observación menor de generación-a-temporal, no bloqueante.
