"""
Migración 0169 — Precio dinámico (reglas por horario/stock/caducidad). ADITIVA e IDEMPOTENTE.

  · `precio_reglas` — reglas de ajuste automático de precio por empresa (+tienda opcional). `params` es un
                      JSON con la condición según `tipo` (horario/stock/caducidad).
  · `articulos.precio_base` — precio de REFERENCIA (no destructivo): el motor recalcula `articulos.precio`
                      a partir de `precio_base`, de modo que al dejar de cumplirse una regla el precio vuelve
                      a la referencia. NULL = aún no gestionado por reglas (se inicializa con el precio actual
                      la primera vez que una regla lo toca).
"""

VERSION = "0169"
DESCRIPCION = "Precio dinámico: precio_reglas + articulos.precio_base"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS precio_reglas (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa   VARCHAR(36)  DEFAULT NULL,
            id_tienda    VARCHAR(36)  DEFAULT NULL,
            nombre       VARCHAR(120) NOT NULL,
            tipo         VARCHAR(20)  NOT NULL,
            params       TEXT                  DEFAULT NULL,
            ajuste_tipo  VARCHAR(10)  NOT NULL DEFAULT 'pct',
            ajuste_valor DECIMAL(12,4) NOT NULL DEFAULT 0,
            prioridad    INT          NOT NULL DEFAULT 0,
            activo       TINYINT(1)   NOT NULL DEFAULT 1,
            creado       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_preglas_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS precio_base DECIMAL(12,4) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS precio_base")
    cur.execute("DROP TABLE IF EXISTS precio_reglas")
