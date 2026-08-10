"""
Migración 0160 — Política MFA por EMPRESA (Gobernanza MFA · Fase 0). ADITIVA, reversible.

Espeja el patrón de `seguridad_password_politica` (migr 0120): una fila por empresa que define si el
MFA es opcional u obligatorio, qué métodos se permiten y qué roles quedan obligados (override por rol).
El FACTOR MFA sigue perteneciendo al usuario (`mfa_usuarios`, migr 0060); esta tabla SOLO gobierna la
POLÍTICA. No toca tablas existentes ni el login. Multiempresa (una fila por id_empresa; NULL = global).
"""

VERSION = "0160"
DESCRIPCION = "Seguridad: tabla mfa_politica (política MFA por empresa + override por rol)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mfa_politica (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) DEFAULT NULL,
            modo VARCHAR(20) NOT NULL DEFAULT 'opcional',        -- opcional | obligatorio
            metodos VARCHAR(120) NOT NULL DEFAULT 'totp',        -- csv: totp,webauthn,recovery
            roles_obligatorios VARCHAR(255) NOT NULL DEFAULT '', -- csv de roles con MFA obligatorio
            activo TINYINT NOT NULL DEFAULT 1,
            actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_mfa_politica (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS mfa_politica")
