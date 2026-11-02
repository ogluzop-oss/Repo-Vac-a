"""
Migración 0308 — Subfamilias (apartados) de productos a granel, editables por el superadministrador.
ADITIVA, idempotente, reversible.

Antes, los apartados de cada familia (p. ej. "Barras de pan"/"Hogazas"/"Panecillos" en Panes) eran
una lista fija en código (`services.tpv.familias_granel`). Ahora pasan a vivir en esta tabla para
que el superadministrador pueda crear nuevos apartados desde la propia ventana de edición de un
producto a granel (p. ej. Carnicería/Pescadería, que antes no tenían ninguno). Se siembran aquí los
apartados que YA existían en código (Panes, Bollería) para no perder nada, más los nuevos pedidos
para Carnicería (Ternera/Vacuno, Aves, Cordero/Cabrito, Conejo, Cerdo) y Pescadería (Pescado
blanco, Pescado rojo, Crustáceos, Cefalópodos, Moluscos). El resto de familias arrancan sin
apartados (crearlos pasa a ser opcional desde la GUI).
"""

VERSION = "0308"
DESCRIPCION = "Tabla familias_granel_subfamilias (apartados editables de cada familia a granel)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_SEED = [
    ("PANES", "BARRAS", "Barras de pan", 1),
    ("PANES", "HOGAZAS", "Hogazas", 2),
    ("PANES", "PANECILLOS", "Panecillos", 3),
    ("BOLLERIA", "DULCE", "Bollería dulce", 1),
    ("BOLLERIA", "SALADA", "Bollería salada", 2),
    ("CARNICERIA", "TERNERA", "Ternera / Vacuno", 1),
    ("CARNICERIA", "AVES", "Aves", 2),
    ("CARNICERIA", "CORDERO", "Cordero / Cabrito", 3),
    ("CARNICERIA", "CONEJO", "Conejo", 4),
    ("CARNICERIA", "CERDO", "Cerdo", 5),
    ("PESCADERIA", "PESCADO_BLANCO", "Pescado blanco", 1),
    ("PESCADERIA", "PESCADO_ROJO", "Pescado azul", 2),
    ("PESCADERIA", "CRUSTACEOS", "Crustáceos", 3),
    ("PESCADERIA", "CEFALOPODOS", "Cefalópodos", 4),
    ("PESCADERIA", "MOLUSCOS", "Moluscos", 5),
]


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS familias_granel_subfamilias (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            codigo_familia VARCHAR(40) NOT NULL,
            codigo         VARCHAR(50) NOT NULL,
            etiqueta       VARCHAR(100) NOT NULL,
            orden          INT NOT NULL DEFAULT 0,
            UNIQUE KEY uq_familia_subfamilia (codigo_familia, codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    for familia, codigo, etiqueta, orden in _SEED:
        cur.execute(
            "INSERT IGNORE INTO familias_granel_subfamilias "
            "(codigo_familia, codigo, etiqueta, orden) VALUES (%s, %s, %s, %s)",
            (familia, codigo, etiqueta, orden))


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS familias_granel_subfamilias")
