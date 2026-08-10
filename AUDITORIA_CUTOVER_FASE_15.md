# AUDITORÍA CUTOVER — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay entorno AWS destino al que migrar.**

## Estado

🟣 **NO EJECUTADO**. El cutover (Fase 15.18) no puede realizarse: no existe producción AWS destino. No se
ejecuta: backup final, migración, validación, congelación de escrituras, cutover, actualización DNS,
monitorización.

## Procedimiento previsto (a ejecutar cuando exista AWS)

1. Backup final (RDS snapshot + export tenants + S3 de documentos).
2. Migración de datos (mysqldump→RDS) y documentos (`migrar_documentos_legacy`).
3. Validación (conteos, checksum, aislamiento por tenant, registros críticos).
4. Congelación de escrituras (ventana de mantenimiento) si procede.
5. Cutover + actualización DNS (Route 53) → nuevo entorno.
6. Validación post-cutover (smoke E2E) + monitorización (CloudWatch).
7. **Rollback disponible**; no eliminar la infraestructura/BD anterior hasta validar producción.

## Resume

Requiere Fases 15.1–15.14 completadas (infra + despliegue + validación). Estado: 🔵 procedimiento definido / 🟣
ejecución externa. Runbook de cutover full-DB 🟡 a formalizar (ver `AUDITORIA_MIGRACION_RDS_FASE_14.md`).
