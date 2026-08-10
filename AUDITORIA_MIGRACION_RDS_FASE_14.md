# AUDITORÍA — MIGRACIÓN MariaDB → Amazon RDS for MariaDB (Fase 14)

Fecha 2026-07-27. Read-only. Verificación de compatibilidad y del proceso de migración de datos.

## 1. Compatibilidad de esquema/acceso (verificado en código)

| Elemento | Evidencia | Estado |
|---|---|---|
| Motor / charset | `ENGINE=InnoDB` + `DEFAULT CHARSET=utf8mb4` en todo el bootstrap | 🟢 |
| Driver / pool | `db/conexion.py`: PyMySQL + DBUtils PooledDB (`ping=1`), `autocommit`, `connect_timeout` | 🟢 |
| SSL/TLS | `DB_SSL_CA/CERT/KEY` → `DB_CONFIG["ssl"]` (compatible bundle `rds-combined-ca`) | 🟢 (listo) |
| Reconexión | pool con `ping=1` revalida la conexión al sacarla | 🟢 |
| Privilegios especiales | **sin** `CREATE TRIGGER/PROCEDURE/EVENT`, `SET GLOBAL`, `SUPER`, `LOAD DATA` (grep) | 🟢 |
| Migraciones | `migraciones/` idempotentes (ADD COLUMN/CREATE TABLE IF NOT EXISTS); auto-aplican en el destino | 🟢 |
| Persistencia de datos en filesystem | ninguna (los datos viven en la BD; los documentos van a StorageProvider/S3) | 🟢 |
| Timezone / sql_mode | fijar en parameter group RDS (UTC/STRICT) | 🟡 config RDS |

## 2. Veredicto de compatibilidad

La migración **MariaDB local → RDS MariaDB** puede realizarse **sin cambios de software adicionales**. Sólo
requiere configuración de infraestructura (parameter group utf8mb4/UTC, TLS CA, `max_connections` dimensionado
= workers×tareas×pool). 🟢 software / 🟡 config RDS / 🟣 instancia real.

## 3. Proceso de migración de datos

| Fase del proceso | Soporte actual | Estado |
|---|---|---|
| Backup previo | `dr/backup_operacional`, `saas/backup_tenant.exportar_empresa` | 🟢 (tenant) / 🔵 (full-DB vía mysqldump) |
| Exportación/Importación | `exportar_tenant` / `importar_empresa` (round-trip probado en `test_backup_restore`/`test_saas_deployment`) | 🟢 tenant |
| Validación de integridad/checksum | export incluye conteos; `hash_documental` en documentos | 🟢 tenant / 🟡 full-DB |
| Conteo de registros/tablas | `backup_operacional.estado` (nº backups, edad) | 🟡 |
| Validación multi-tenant | export/import por `id_empresa` (aislado) | 🟢 |
| Rollback | restaurar desde snapshot/backup previo | 🔵 (RDS snapshot) |
| Ventana de mantenimiento / cutover | **procedimiento a formalizar en runbook** | 🟡 |
| Validación posterior | migraciones + smoke `/health/ready` | 🟢 |

## 4. Pendientes (no bloqueantes de software)

- **Runbook de cutover full-DB** (mysqldump → RDS import → verificación de conteos globales) — documentación
  operativa, no cambio de código. Marcar 🟡.
- Ejecución real sobre RDS → 🟣 externo.

## Estado

🟢 **Software compatible con RDS sin cambios**. Proceso de migración: 🟢 a nivel tenant (round-trip probado);
🟡 runbook de cutover full-DB por formalizar; 🟣 ejecución sobre RDS real.
