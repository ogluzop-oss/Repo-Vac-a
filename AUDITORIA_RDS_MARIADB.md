# AUDITORÍA — Amazon RDS for MariaDB (Fase 9)

Objetivo: compatibilidad de la capa de datos con RDS MariaDB. **No migrar de motor** (sigue MariaDB).

## Evidencia

- Driver: `PyMySQL` + `DBUtils` (PooledDB) en `db/conexion.py`. `ping=1` (valida conexión del pool).
- Config: host/puerto/usuario/BD por entorno; `charset=utf8mb4`; `autocommit=True`; `port` configurable.
- **TLS listo**: `DB_SSL_CA` / `DB_SSL_CERT` / `DB_SSL_KEY` → `DB_CONFIG["ssl"]` (compatible con `rds-ca` bundle).
- Esquema: `ENGINE=InnoDB` + `DEFAULT CHARSET=utf8mb4` en todo el bootstrap; migraciones idempotentes
  (`migraciones/__init__.py` aplica pendientes).
- **Sin construcciones que requieran privilegios especiales en RDS**: no hay `CREATE TRIGGER` / `PROCEDURE` /
  `EVENT` / `SET GLOBAL` / `SUPER` / `LOAD DATA` reales (verificado por grep; las coincidencias eran comentarios/
  nombres de función Python).
- Versión objetivo: `mariadb:11` (compose) → RDS MariaDB 11.x.

## Compatibilidad

| Aspecto | Estado | Nota |
|---|---|---|
| Motor / versión | 🟢 | InnoDB + MariaDB 11 → RDS MariaDB directo |
| Charset/collation | 🟢 | utf8mb4 / utf8mb4_unicode_ci (fijar en parameter group) |
| Conexión / pool | 🟢 | DBUtils pool con ping; compatible con endpoint RDS |
| TLS | 🟢 (listo) | activar `DB_SSL_CA` con el bundle `rds-combined-ca` |
| Privilegios | 🟢 | sin SUPER/eventos → sin fricción con el usuario master de RDS |
| Foreign keys / índices | 🟢 | estándar InnoDB |
| Timezone | 🟡 | fijar `time_zone` en parameter group (o UTC en app) para consistencia |
| `sql_mode` | 🟡 | alinear parameter group con el modo asumido por la app (STRICT) |
| Multi-AZ / réplica | 🟣 | infraestructura externa (alta disponibilidad) |
| Tamaño / nº tablas | ℹ️ | ~444 tablas activas (404 aisladas por tenant directo, 12 vía padre, 3 vía usuario, 11 globales, 14 allowlist) |
| Backups | 🔵 | RDS automated backups + snapshots (ver `AUDITORIA` DR) |

## Cambios para RDS (siguiente fase)

1. Crear parameter group (utf8mb4, `time_zone=UTC`, `sql_mode` alineado, `max_connections` según pool×tareas).
2. Activar TLS: montar CA de RDS y setear `DB_SSL_CA`.
3. Dimensionar `max_connections` = (workers gunicorn × tareas ECS × pool) + margen.
4. Multi-AZ (externo) + ventana de backup + retención.

**Veredicto: 🟢 compatible / 🟡 adaptación de parámetros.** Sin necesidad de cambiar de motor. Ningún 🔴.
