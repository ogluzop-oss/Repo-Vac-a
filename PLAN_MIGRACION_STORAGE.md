# PLAN DE MIGRACIÓN DE STORAGE (local → S3) (Fase 10)

Migración **progresiva y no destructiva**. El backend se elige por `STORAGE_BACKEND` (local/s3); no se
introduce dependencia obligatoria de AWS en DEV.

## Estrategia por entorno

| Entorno | STORAGE_BACKEND |
|---|---|
| DEV | `local` |
| STAGING | `s3` |
| PROD | `s3` |

## Pasos

1. **Adoptar la abstracción**: migrar los puntos que hoy escriben en `documentos/` a `obtener_storage()`
   (gradual; `documentos_registro` acepta rutas locales antiguas y claves S3 nuevas → compatibilidad).
2. **Provisionar S3** (propietario): bucket privado + KMS + versioning + lifecycle (🟣 externo).
3. **Migrar ficheros existentes**: `storage.migracion.migrar_local_a_s3(id_empresa, dry_run=True)` para
   reportar; luego `dry_run=False` para copiar con verificación de checksum. **No borra local**.
4. **Verificar**: conteo, checksums, duplicados, integridad (el informe los detalla).
5. **Conmutar** `STORAGE_BACKEND=s3` en staging → validar descargas (URLs firmadas + guard tenant) → prod.
6. **Retención local**: conservar el filesystem hasta validar S3 en producción; borrado manual y auditado.

## Garantías

- No destructiva (nunca borra local automáticamente).
- Idempotente (si el objeto ya existe en S3 con el mismo checksum, no lo reescribe; si difiere, error, no pisa).
- Aislamiento por tenant preservado (claves `tenant/{id_empresa}/…`).

## Estado

Herramienta 🟢 (probada en dry-run/degradable). Ejecución real 🟣 (requiere bucket S3).
