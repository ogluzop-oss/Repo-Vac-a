"""
Migración 0034 — Homologación y evaluación de proveedores (CMP.8). ADITIVA, reversible.
KPIs por proveedor + estado de homologación. compras_incidencias ya existe (0030).
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0034"
DESCRIPCION = "Evaluación de proveedores: proveedores_evaluacion + estado homologación"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS homologacion_estado "
                "VARCHAR(12) NOT NULL DEFAULT 'pendiente'")  # pendiente|aprobado|suspendido|bloqueado
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS proveedores_evaluacion (
            id            BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36) NOT NULL DEFAULT '{emp}',
            id_proveedor  BIGINT NOT NULL,
            periodo       VARCHAR(7)           DEFAULT NULL,  -- AAAA-MM
            cumplimiento_plazo DECIMAL(5,2) NOT NULL DEFAULT 0,
            calidad       DECIMAL(5,2) NOT NULL DEFAULT 0,
            incidencias   INT NOT NULL DEFAULT 0,
            rechazos      INT NOT NULL DEFAULT 0,
            devoluciones  INT NOT NULL DEFAULT 0,
            valoracion_global DECIMAL(5,2) NOT NULL DEFAULT 0,
            observaciones VARCHAR(255)         DEFAULT NULL,
            fecha         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_eval_prov (id_empresa, id_proveedor)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS proveedores_evaluacion")
    cur.execute("ALTER TABLE proveedores DROP COLUMN IF EXISTS homologacion_estado")
