"""
Migración 0174 — Conexión bancaria en vivo (open banking / PSD2). ADITIVA e IDEMPOTENTE.

Tabla `banca_conexiones`: configuración de la conexión con la entidad bancaria por cuenta (proveedor
agregador, endpoint, id de cuenta en el proveedor, credencial CIFRADA, modo simulado). Una fila por
(empresa, cuenta). El sistema importa los movimientos reales al mismo motor de conciliación existente.
No modifica datos existentes.
"""

VERSION = "0174"
DESCRIPCION = "Banca online: tabla banca_conexiones"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS banca_conexiones (
            id                 INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa         VARCHAR(36)  DEFAULT NULL,
            id_cuenta          INT          NOT NULL,
            proveedor          VARCHAR(40)  NOT NULL DEFAULT 'simulado',
            endpoint           VARCHAR(255)          DEFAULT NULL,
            account_id         VARCHAR(120)          DEFAULT NULL,
            credencial_cifrada TEXT                  DEFAULT NULL,
            modo_simulado      TINYINT(1)   NOT NULL DEFAULT 1,
            activo             TINYINT(1)   NOT NULL DEFAULT 1,
            ultima_sync        DATETIME              DEFAULT NULL,
            creado             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_banca_conex (id_empresa, id_cuenta)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS banca_conexiones")
