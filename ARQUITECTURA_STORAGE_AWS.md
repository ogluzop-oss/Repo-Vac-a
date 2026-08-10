# ARQUITECTURA — STORAGE ABSTRACTION (Fase 10)

## Objetivo

Eliminar el acceso directo al filesystem desde los módulos de negocio. Una única abstracción (`StorageProvider`)
con backends intercambiables por configuración. En Fargate el filesystem es efímero → los documentos
persistentes van a S3.

## Componentes

```
services/storage/
  base.py     StorageProvider (API + guard de tenant + URLs firmadas)
  local.py    LocalStorageProvider  (DEV, filesystem seguro bajo documentos/_storage/)
  s3.py       S3StorageProvider     (boto3 perezoso; SSE-KMS; presigned)  — PREPARADO
  migracion.py  migrar_local_a_s3   (no destructiva, checksum)
  __init__.py  obtener_storage()    (factory por STORAGE_BACKEND=local|s3)
```

## API única

`clave · guardar · leer · existe · borrar · metadatos · listar · url_firmada`. Todas exigen `id_empresa` y
validan el tenant en la clase base (heredado por todos los backends).

## Configuración

| Variable | Valor |
|---|---|
| `STORAGE_BACKEND` | `local` (DEV) / `s3` (STAGING/PROD) |
| `STORAGE_LOCAL_ROOT` | raíz local (opcional) |
| `S3_BUCKET`, `AWS_REGION`, `S3_PREFIX` | destino S3 |
| `S3_SSE`, `S3_KMS_KEY_ID` | cifrado en reposo |
| `AWS_ENDPOINT_URL` | sólo pruebas locales (MinIO/localstack) |

## Migración a los módulos (gradual, compatible)

Los puntos que hoy escriben en `documentos/` migrarán a `obtener_storage().guardar(...)` conservando
compatibilidad (aceptar rutas locales antiguas y claves S3 nuevas en `documentos_registro`). La generación de
PDFs no cambia: sólo cambia dónde se persiste/lee el binario.

## Honestidad

Sin boto3/bucket, `STORAGE_BACKEND=s3` es un **error explícito** (no fallback silencioso, no simulado). El
backend local prueba TODO el flujo (incluido el aislamiento multi-tenant) hoy.
