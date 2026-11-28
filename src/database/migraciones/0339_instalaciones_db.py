"""
Migración 0339 — Credenciales de base de datos POR INSTALACIÓN (ADITIVA).

Hasta ahora, `services.provisioning.datos_conexion` devolvía SIEMPRE el mismo usuario/contraseña
de MariaDB (`DB_REMOTE_USER`/`DB_REMOTE_PASSWORD`, variables de entorno globales) a CUALQUIER
ordenador que canjeara un código de emparejamiento — compartido no solo dentro de una empresa, sino
entre TODAS las empresas del SaaS. Si el `.env` de un solo ordenador se filtraba, la única forma de
cortarlo era rotar esa contraseña global, afectando a todos los demás ordenadores de todas las
empresas a la vez.

Esta tabla registra una credencial de MariaDB REAL Y DISTINTA por cada ordenador emparejado
(`CREATE USER`/`DROP USER` reales, ver `services.provisioning.crear_credencial_db`/
`revocar_credencial_db`) — mismos privilegios que el usuario compartido anterior (sigue sin haber
aislamiento de FILAS entre empresas a nivel de MariaDB, eso requeriría un cambio de arquitectura
mayor — la app de escritorio dejaría de hablar con la BD directamente), pero ahora cada ordenador
es revocable individualmente sin tocar a los demás.
"""

VERSION = "0339"
DESCRIPCION = "Credenciales de base de datos por instalación (revocables individualmente)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS instalaciones_db (
            id                BIGINT       AUTO_INCREMENT PRIMARY KEY,
            id_empresa        CHAR(36)     NOT NULL,
            id_centro         VARCHAR(36)  NOT NULL,
            db_usuario        VARCHAR(40)  NOT NULL,
            descripcion       VARCHAR(120)          DEFAULT NULL,
            creado            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ultima_conexion   DATETIME              DEFAULT NULL,
            revocado          TINYINT(1)   NOT NULL DEFAULT 0,
            revocado_en       DATETIME              DEFAULT NULL,
            UNIQUE KEY uq_instalaciones_db_usuario (db_usuario),
            INDEX idx_instalaciones_db_empresa (id_empresa, revocado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS instalaciones_db")
