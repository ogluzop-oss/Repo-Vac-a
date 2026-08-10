"""
Migración 0158 — Precios editables de los extras del TPV (bolsas / sobres de regalo). ADITIVA, reversible.

Persiste el precio de los 4 extras rápidos del TPV para que un administrador pueda ajustarlos desde la
ventana "Precio bolsas" (en vez de quedar fijos en el código). El TPV lee el precio de aquí; si no hay
fila, usa el valor por defecto del catálogo. Multiempresa opcional (clave por código, global a la
instalación mono-empresa actual).
"""

VERSION = "0158"
DESCRIPCION = "TPV: tabla tpv_extras_precios (precio editable de bolsas/sobres de regalo)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_SEED = [
    ("BOLSA_GRANDE", "Bolsa grande", 0.20),
    ("BOLSA_PEQUENA", "Bolsa pequeña", 0.10),
    ("SOBRE_REGALO_PEQUENO", "Sobre regalo pequeño", 0.50),
    ("SOBRE_REGALO_GRANDE", "Sobre regalo grande", 1.00),
]


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tpv_extras_precios (
            codigo VARCHAR(60) NOT NULL PRIMARY KEY,
            nombre VARCHAR(120),
            precio DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    for codigo, nombre, precio in _SEED:
        cur.execute("INSERT IGNORE INTO tpv_extras_precios (codigo, nombre, precio) VALUES (%s,%s,%s)",
                    (codigo, nombre, precio))


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS tpv_extras_precios")
