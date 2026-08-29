"""
Migración 0227 — Límite de gasto mensual B2B por empresa (Smart Suppliers B2B · Fase 3).

Tabla PROPIA de B2B (no `services.finanzas.presupuestos`, que son presupuestos contables por ejercicio
— concepto distinto; se evita la colisión de nombre). ADITIVA, idempotente, reversible.
"""

VERSION = "0227"
DESCRIPCION = "Límite de gasto mensual B2B por empresa (b2b_empresa_config)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("b2b_empresa_config", """
    id_empresa          CHAR(36)      NOT NULL PRIMARY KEY,
    presupuesto_mensual DECIMAL(12,2) DEFAULT NULL,
    actualizado_en      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute(f"DROP TABLE IF EXISTS {_TABLA[0]}")
