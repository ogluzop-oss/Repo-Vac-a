"""
Migración 0159 — Configuración del % de descuento de PERSONAL (empleados). ADITIVA, reversible.

Persiste el porcentaje de descuento de empleado por empresa, editable solo por admin/superadmin desde
el TPV (ventana "Acciones avanzadas" → "Editar % descuento personal"). El TPV lo aplica en la "Compra
personal" (previa validación del PIN del empleado). Multiempresa (clave por id_empresa).
"""

VERSION = "0159"
DESCRIPCION = "TPV: tabla config_descuentos (% de descuento de personal por empresa)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config_descuentos (
            id_empresa VARCHAR(64) NOT NULL PRIMARY KEY,
            descuento_personal_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS config_descuentos")
