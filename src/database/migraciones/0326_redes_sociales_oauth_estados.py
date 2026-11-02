"""
Migración 0326 — Estado efímero del flujo OAuth de Redes Sociales (`services.redes_sociales.oauth`).

Corrige un error de arquitectura detectado en revisión propia: el escritorio (donde se construye la
URL de autorización) y el backend Flask (donde llega el callback HTTP tras el login real en la
plataforma) son DOS PROCESOS SEPARADOS — un diccionario en memoria no es visible entre ambos. Ambos
procesos SÍ comparten la misma MariaDB, así que el estado (incluido el `code_verifier` de PKCE para
X) se persiste aquí en vez de en memoria. ADITIVA, idempotente, reversible. Fila de corta vida
(TTL ~10 min, aplicado en código, no en la BD) — no requiere limpieza programada aparte.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0326"
DESCRIPCION = "Estado efímero (state/PKCE) del flujo OAuth de Redes Sociales"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_oauth_estados (
            state               VARCHAR(64)  NOT NULL PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            plataforma          VARCHAR(20)  NOT NULL,
            code_verifier       VARCHAR(160)          DEFAULT NULL,
            usuario             VARCHAR(120)          DEFAULT NULL,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rsoauth_creado (creado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS redes_sociales_oauth_estados")
