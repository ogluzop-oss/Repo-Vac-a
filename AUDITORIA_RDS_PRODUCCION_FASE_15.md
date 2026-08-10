# AUDITORÍA RDS PRODUCCIÓN — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay RDS ni credenciales AWS.**

## Software (verificado, Fases 9-14)

🟢 `db/conexion.py` compatible con RDS MariaDB sin cambios: PyMySQL + pool DBUtils (`ping=1`), utf8mb4,
`autocommit`, TLS-ready (`DB_SSL_CA/CERT/KEY`). Esquema InnoDB/utf8mb4, sin triggers/procs/eventos/SUPER.
Migraciones idempotentes auto-aplicables.

## Validación en AWS (Fase 15.3)

🟣 **BLOQUEADA**. No ejecutado (ninguno): creación RDS, conectividad, validación SSL, aplicación de migraciones
sobre RDS, validación de esquema, smoke tests, migración de datos, comparación de conteos.

## Resume

Provisionar RDS MariaDB (Multi-AZ, cifrado KMS, TLS, parameter group utf8mb4/UTC, SG privado). Variables:
`DB_HOST/DB_PORT/DB_NAME/DB_USER` + `DB_PASSWORD` (Secrets Manager) + `DB_SSL_CA`. Después: aplicar migraciones,
smoke `/health/ready`, y (con autorización) migración de datos con backup+checksum+conteos. No borrar la BD
local hasta validar. Estado: 🟢 software / 🟣 validación externa.
