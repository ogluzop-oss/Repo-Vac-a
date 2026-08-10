# RUNBOOK — Backups, Restauración y Disaster Recovery (AWS)

## Backups

### Base de datos (RDS MariaDB)
- **Automated backups** (retención configurada por entorno: dev 7 / staging 14 / prod 30 días) + **snapshots
  manuales** antes de cambios mayores. Cifrado con KMS.
- Snapshot manual: `aws rds create-db-snapshot --db-instance-identifier <id> --db-snapshot-identifier <nombre>`.
- Backup lógico por tenant (app): `dr/backup_operacional.exportar_tenant` / `saas/backup_tenant.exportar_empresa`.

### Documentos (S3)
- **Versioning ON** + lifecycle (transición a IA a 90 días, expiración de versiones no vigentes a 365).
  Recuperación accidental → restaurar versión anterior del objeto.

### Secretos / config
- Secrets Manager conserva versiones; KMS con rotación. La IaC (`infra/aws`) está en Git (estado remoto en S3
  versionado).

## Restauración (validar SIEMPRE en entorno controlado antes de producción)

### RDS
```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier <nuevo-id> --db-snapshot-identifier <snapshot>
```
- Apuntar la app al nuevo endpoint (`DB_HOST`). Verificar conteos e integridad + **aislamiento por tenant**.

### Documentos
- S3 versioning: restaurar versión concreta; o re-migrar desde origen con `storage.migracion` /
  `storage.documentos.migrar_documentos_legacy` (idempotente, checksum).

> Un backup **no** está validado hasta haberlo restaurado correctamente. Programar un ejercicio de restore.

## Disaster Recovery

| Fallo | Respuesta |
|---|---|
| Caída de tarea/instancia ECS | ECS reprograma automáticamente (app stateless: docs→S3, sesión→JWT) |
| Caída de AZ | **Multi-AZ** RDS conmuta; ECS reparte en varias AZ |
| Caída de RDS | Failover Multi-AZ o restore desde snapshot/PITR |
| Pérdida de región | Restore en 2ª región desde snapshot + **S3 cross-region replication** (fase de dominio) |
| Corrupción de datos | PITR (point-in-time recovery) al instante previo |

### RPO / RTO
- Instrumentados por `dr/backup_operacional.estado` y `dr/dr_pitr`. **Valores SLA definitivos** dependen de la
  frecuencia de snapshots + Multi-AZ (fijar en el provisionado). Medir con un **simulacro real** tras desplegar:
  registrar hora de fallo, detección, recuperación, datos perdidos.

### Simulacro (drill)
- Ejecutar `dr/dr_drills` contra el entorno de staging y documentar el resultado. No se declara DR validado
  hasta ejecutar el simulacro sobre AWS real.
