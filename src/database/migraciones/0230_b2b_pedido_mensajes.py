"""
Migración 0230 — Chat por pedido B2B (Smart Suppliers B2B · Fase 3).

Mensajes rígidamente ligados a `transaccion_comercial.id_tx`, visibles tanto desde el Portal Empresa
como desde el Portal Proveedor. `b2b_pedido_lecturas` es una marca de agua por (pedido, lado) — mismo
patrón que `actividad_vistas` (src/services/actividad/badges.py) para no-leídos, en vez de un flag
`leido` por mensaje. ADITIVA, idempotente, reversible.
"""

VERSION = "0230"
DESCRIPCION = "Chat por pedido B2B (mensajes + marca de agua de lectura)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_pedido_mensajes", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_tx        CHAR(36)     NOT NULL,
        autor_tipo   ENUM('empresa','proveedor') NOT NULL,
        autor_nombre VARCHAR(255) DEFAULT NULL,
        cuerpo       TEXT         NOT NULL,
        creado_en    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        INDEX idx_b2b_msg_tx (id_tx, creado_en)"""),
    ("b2b_pedido_lecturas", """
        id_tx          CHAR(36)     NOT NULL,
        lado           ENUM('empresa','proveedor') NOT NULL,
        ultima_lectura DATETIME(6)  NOT NULL,
        PRIMARY KEY (id_tx, lado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
