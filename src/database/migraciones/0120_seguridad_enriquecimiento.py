"""
Migracion 0120 — Enriquecimiento de Seguridad (Módulo 20). ADITIVA, idempotente, reversible.
Auditoría: Seguridad ya cubre RBAC/ACL (roles/permisos/grupos + motor `autorizacion.puede`), MFA TOTP
+ recuperación, hashing Argon2id, bloqueo por intentos fallidos escalado (`db/usuario.py`),
administración de sesiones, anomalías, incidentes, RGPD, secret_manager, tenant_guard y auditoría de
seguridad. Se añade lo ausente: POLÍTICA DE CONTRASEÑAS empresarial (complejidad configurable +
caducidad periódica + historial de no-reutilización). Reutiliza `src/seguridad/passwords`. No duplica.
"""

VERSION = "0120"
DESCRIPCION = "Seguridad: política de contraseñas (complejidad + caducidad + historial)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("seguridad_password_politica", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        longitud_min INT NOT NULL DEFAULT 8,
        requiere_mayus TINYINT NOT NULL DEFAULT 1,
        requiere_minus TINYINT NOT NULL DEFAULT 1,
        requiere_digito TINYINT NOT NULL DEFAULT 1,
        requiere_simbolo TINYINT NOT NULL DEFAULT 0,
        dias_caducidad INT NOT NULL DEFAULT 0,
        historial_n INT NOT NULL DEFAULT 3,
        activo TINYINT NOT NULL DEFAULT 1,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_politica (id_empresa)"""),
    ("seguridad_password_historial", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_usuario INT NOT NULL,
        hash VARCHAR(255) NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_pwhist (id_usuario, creado)"""),
]

_COLUMNAS = [
    ("usuarios", "password_changed_at", "DATETIME DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna):
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for tabla, col, definicion in _COLUMNAS:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
    for tabla, col, _ in _COLUMNAS:
        try:
            if _existe_columna(cur, tabla, col):
                cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
        except Exception:
            pass
