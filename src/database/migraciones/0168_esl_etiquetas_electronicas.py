"""
Migración 0168 — ESL / Etiquetas electrónicas (precio dinámico en el lineal). ADITIVA e IDEMPOTENTE.

Dos tablas nuevas:
  · `esl_config`  — configuración del sistema ESL por empresa+tienda (proveedor, endpoint, store_id,
                    credencial CIFRADA vía Secret Manager, modo simulado). Una fila por (empresa, tienda).
  · `esl_labels`  — mapeo etiqueta física ↔ artículo (label_id ↔ codigo_articulo) + estado de
                    sincronización y último precio empujado. Push MANUAL: el estado indica si está
                    pendiente de sincronizar.
No modifica datos existentes.
"""

VERSION = "0168"
DESCRIPCION = "ESL: etiquetas electrónicas de precio dinámico (esl_config + esl_labels)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esl_config (
            id                 INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa         VARCHAR(36)  DEFAULT NULL,
            id_tienda          VARCHAR(36)  DEFAULT NULL,
            proveedor          VARCHAR(40)  NOT NULL DEFAULT 'simulado',
            endpoint           VARCHAR(255)          DEFAULT NULL,
            store_id           VARCHAR(120)          DEFAULT NULL,
            credencial_cifrada TEXT                  DEFAULT NULL,
            modo_simulado      TINYINT(1)   NOT NULL DEFAULT 1,
            activo             TINYINT(1)   NOT NULL DEFAULT 1,
            creado             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_esl_config (id_empresa, id_tienda)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esl_labels (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa          VARCHAR(36)  DEFAULT NULL,
            id_tienda           VARCHAR(36)  DEFAULT NULL,
            codigo_articulo     VARCHAR(64)  NOT NULL,
            label_id            VARCHAR(120) NOT NULL,
            proveedor           VARCHAR(40)           DEFAULT NULL,
            plantilla           VARCHAR(60)           DEFAULT NULL,
            precio_sincronizado DECIMAL(12,4)         DEFAULT NULL,
            estado              VARCHAR(20)  NOT NULL DEFAULT 'PENDIENTE',
            ultimo_error        VARCHAR(255)          DEFAULT NULL,
            ultima_sync         DATETIME              DEFAULT NULL,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_esl_label (id_empresa, id_tienda, label_id),
            INDEX idx_esl_art (id_empresa, id_tienda, codigo_articulo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS esl_labels")
    cur.execute("DROP TABLE IF EXISTS esl_config")
