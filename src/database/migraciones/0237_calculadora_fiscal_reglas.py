"""
Migración 0237 — Reglas fiscales editables de la Calculadora Fiscal (Contabilidad). SUSTITUYE el
JSON plano de la primera versión (`assets/fiscalidad/impuesto_sociedades_es.json`): a partir de aquí
el tipo general y las deducciones se editan desde la propia pantalla de la Calculadora Fiscal (CRUD),
nunca a mano en un fichero. Mismo idioma que `precio_reglas` (migr. `0169_precio_dinamico.py`).

`ccaa`/`tipo_entidad`/`base_desde`/`base_hasta`/`vigente_desde`/`vigente_hasta` NULL = "sin esa
condición" (aplica siempre en esa dimensión) — así una regla nacional simple es solo 3 columnas
rellenas, y un tramo/condición se modela como una fila adicional más específica.
"""

VERSION = "0237"
DESCRIPCION = "Reglas editables del Impuesto de Sociedades (Calculadora Fiscal)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fiscal_is_reglas (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa     VARCHAR(36)   DEFAULT NULL,
            concepto       VARCHAR(30)   NOT NULL,
            ccaa           VARCHAR(60)   DEFAULT NULL,
            tipo_entidad   VARCHAR(20)   DEFAULT NULL,
            base_desde     DECIMAL(14,2) DEFAULT NULL,
            base_hasta     DECIMAL(14,2) DEFAULT NULL,
            unidad         VARCHAR(4)    NOT NULL DEFAULT 'pct',
            valor          DECIMAL(12,4) NOT NULL DEFAULT 0,
            vigente_desde  DATE          DEFAULT NULL,
            vigente_hasta  DATE          DEFAULT NULL,
            prioridad      INT           NOT NULL DEFAULT 0,
            activo         TINYINT(1)    NOT NULL DEFAULT 1,
            creado         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fiscalis_emp (id_empresa),
            INDEX idx_fiscalis_concepto (id_empresa, concepto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS fiscal_is_reglas")
