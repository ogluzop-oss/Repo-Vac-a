"""
Migración 0222 — Smart Suppliers · Fase B: sesión de la Extranet de Empresa + carrito B2B. ADITIVA,
idempotente, reversible.

`b2b_sesiones_empresa` la emite el botón "Entrar al portal B2B" del escritorio (Fase E) — captura
`id_tienda` de la conexión remota activa EN ESE MOMENTO; el portal no permite cambiarla (requisito de
negocio confirmado: reponer solo a la tienda con la que se está conectado remotamente).

`b2b_carrito_lineas` es el carrito, con dos orígenes posibles por línea: 'catalogo' (añadida buscando
en el catálogo B2B) o 'reposicion' (añadida desde "Desde reposición", enlazada a `reab_propuestas` vía
`id_reab_propuesta` para poder marcarla "Añadida" sin que desaparezca de la lista de sugerencias).
"""

VERSION = "0222"
DESCRIPCION = "Smart Suppliers: sesión Portal Empresa (con tienda fija) + carrito B2B"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_sesiones_empresa", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        token_sesion VARCHAR(64) NOT NULL,
        id_empresa CHAR(36) NOT NULL,
        id_usuario INT DEFAULT NULL,
        nombre_usuario VARCHAR(255) DEFAULT NULL,
        id_tienda INT DEFAULT NULL,
        sector_id INT DEFAULT NULL,
        expira DATETIME NOT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_b2bses_token (token_sesion),
        INDEX idx_b2bses_emp (id_empresa)"""),
    ("b2b_carrito_lineas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        token_sesion VARCHAR(64) NOT NULL,
        id_suministrador BIGINT DEFAULT NULL,
        codigo VARCHAR(50) NOT NULL,
        nombre VARCHAR(255) NOT NULL,
        unidad_medida VARCHAR(20) DEFAULT NULL,
        cantidad INT NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(12,4) NOT NULL DEFAULT 0,
        origen VARCHAR(20) NOT NULL DEFAULT 'catalogo',
        id_reab_propuesta INT DEFAULT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_b2bcart_ses (token_sesion)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
