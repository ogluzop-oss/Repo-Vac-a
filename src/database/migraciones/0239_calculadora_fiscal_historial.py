"""
Migración 0239 — Historial de simulaciones de la Calculadora Fiscal (Contabilidad). Mismo espíritu
que `sim_escenarios` (migr. `0095_simulador.py`, panel Simulador del Centro de Inteligencia
Empresarial), simplificado a un único registro por simulación (entrada + resultado ya calculado, sin
tablas satélite de variables/resultados — aquí no hacen falta).
"""

VERSION = "0239"
DESCRIPCION = "Historial de simulaciones de la Calculadora Fiscal"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fiscal_is_simulaciones (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa     VARCHAR(36)   DEFAULT NULL,
            usuario        VARCHAR(120)  DEFAULT NULL,
            anio           INT           DEFAULT NULL,
            tipo_entidad   VARCHAR(20)   DEFAULT NULL,
            ccaa           VARCHAR(60)   DEFAULT NULL,
            entrada_json   MEDIUMTEXT    DEFAULT NULL,
            resultado_json MEDIUMTEXT    DEFAULT NULL,
            creado         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fiscalsim_emp (id_empresa, creado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS fiscal_is_simulaciones")
