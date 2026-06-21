"""
Migracion 0036 - Promociones (VTA.2): promociones + promociones_reglas. ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0036"
DESCRIPCION = "Promociones (VTA.2): promociones + promociones_reglas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS promociones (
            id_promocion BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa  CHAR(36) NOT NULL DEFAULT '{emp}',
            nombre      VARCHAR(120) NOT NULL,
            tipo        VARCHAR(16) NOT NULL DEFAULT 'descuento_pct',
            valor       DECIMAL(10,2) NOT NULL DEFAULT 0,
            ambito      VARCHAR(16) NOT NULL DEFAULT 'articulo',
            id_tienda   INT DEFAULT NULL,
            segmento    VARCHAR(50) DEFAULT NULL,
            fecha_inicio DATE DEFAULT NULL,
            fecha_fin   DATE DEFAULT NULL,
            hora_inicio TIME DEFAULT NULL,
            hora_fin    TIME DEFAULT NULL,
            prioridad   INT NOT NULL DEFAULT 0,
            activa      TINYINT(1) NOT NULL DEFAULT 1,
            fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_promo_emp (id_empresa, activa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS promociones_reglas (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_promocion BIGINT NOT NULL,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            clave VARCHAR(20) NOT NULL,
            valor VARCHAR(120) DEFAULT NULL,
            INDEX idx_pr_promo (id_promocion),
            CONSTRAINT fk_pr_promo FOREIGN KEY (id_promocion)
                REFERENCES promociones(id_promocion) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS promociones_reglas")
    cur.execute("DROP TABLE IF EXISTS promociones")
