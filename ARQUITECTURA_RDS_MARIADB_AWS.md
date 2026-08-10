# ARQUITECTURA — RDS MariaDB en AWS (Fase 10)

Se mantiene **MariaDB** (no se migra de motor). Complementa `AUDITORIA_RDS_MARIADB.md` (Fase 9).

## Preparación (ya en el software)

- `db/conexion.py`: pool (DBUtils, `ping=1`), `charset=utf8mb4`, `autocommit`, **TLS listo**
  (`DB_SSL_CA/CERT/KEY`), host/puerto/usuario/BD por entorno.
- Esquema InnoDB + utf8mb4; migraciones idempotentes; **sin triggers/procedimientos/eventos/SUPER** → sin
  fricción con el usuario master de RDS.

## Config para RDS (cuando exista)

| Variable | Valor |
|---|---|
| `DB_HOST` | endpoint RDS [EXTERNO] |
| `DB_PORT` | 3306 |
| `DB_NAME`, `DB_USER` | producción, mínimos privilegios |
| `DB_PASSWORD` | Secrets Manager [EXTERNO] |
| `DB_SSL_CA` | bundle `rds-combined-ca` |

## Parameter group / operación

- `character_set_server=utf8mb4`, `collation_server=utf8mb4_unicode_ci`, `time_zone=UTC`, `sql_mode` alineado.
- `max_connections` ≥ (workers gunicorn × tareas ECS × tamaño de pool) + margen.
- Multi-AZ (HA) + ventana de backup + retención → 🟣 externo.

## Migraciones

Se aplican con `migraciones` (idempotentes) contra el endpoint RDS. Rol de migración con permisos DDL sólo
sobre la BD de la app. No se ejecuta migración real sin RDS. Estado: 🟢 software compatible / 🔵 config RDS /
🟣 instancia externa.
