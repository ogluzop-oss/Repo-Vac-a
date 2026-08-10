# AUDITORÍA S3 PRODUCCIÓN — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay bucket S3 ni credenciales AWS.**

## Software (verificado)

🟢 `S3StorageProvider` (boto3 perezoso, SSE-KMS, presigned), guard de tenant en la clase base, capa
`storage/documentos` (CREATE/READ/DOWNLOAD/DELETE/LEGACY), migración `migrar_documentos_legacy` idempotente con
checksum. `documentos_registro` con `storage_key`/`storage_backend`/`migracion_estado` (migr 0164).

## Validación en AWS (Fase 15.4)

🟣 **BLOQUEADA**. No ejecutado: creación de bucket privado + SSE-KMS + policy, migración real de documentos,
validación cross-tenant sobre S3 real, presigned reales con expiración, CREATE/READ/DOWNLOAD/DELETE/LEGACY
contra S3. **boto3 tampoco está instalado** (S3StorageProvider es 🔵 degradable, no operativo).

## Resume

Provisionar bucket privado (Block Public Access) + CMK KMS + CloudFront OAC. Variables: `S3_BUCKET`,
`S3_PREFIX`, `S3_SSE`, `S3_KMS_KEY_ID`, `AWS_REGION`, `STORAGE_BACKEND=s3`. Instalar boto3 en la imagen. Después:
migración `migrar_documentos_legacy` por tenant + validación de aislamiento A≠B sobre S3 real. Estado: 🟢
software / 🔵 adapter / 🟣 validación externa.
