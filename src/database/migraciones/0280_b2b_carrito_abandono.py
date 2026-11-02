"""
Migración 0280 — Smart Suppliers: detección de carritos B2B abandonados. ADITIVA, idempotente,
reversible.

`b2b_carrito_actividad` guarda la última vez que un carrito CAMBIÓ DE CONTENIDO (añadir o quitar una
línea) — `b2b_carrito_lineas.creado_en` (migr. 0222) solo se fija al INSERTAR y `quitar_linea` nunca
actualiza nada, así que por sí solo `MAX(creado_en)` no reflejaría una retirada de línea sin ningún
añadido posterior. Se mantiene como tabla propia (1 fila por `token_sesion`) en vez de añadir una
columna a `b2b_carrito_lineas` porque la "actividad" es del CARRITO, no de una línea concreta.

`b2b_carrito_abandono` es el registro de detección/notificación (evita re-notificar en cada pasada del
job el mismo carrito sin cambios) y la fuente que leen tanto el aviso del Portal Empresa ("Reanudar
Pedido") como la vista de carritos abandonados del Portal Proveedor.

Ver `src/services/compras/b2b_carrito_abandono.py` para la lógica y la limitación documentada sobre
la coincidencia entre el umbral de abandono (2h) y `b2b_sesion_empresa.MINUTOS_SESION` (120 min).
"""

VERSION = "0280"
DESCRIPCION = "Smart Suppliers: detección de carritos B2B abandonados (actividad + registro)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_carrito_actividad", """
        token_sesion VARCHAR(64) NOT NULL PRIMARY KEY,
        actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"""),
    ("b2b_carrito_abandono", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        token_sesion VARCHAR(64) NOT NULL,
        id_empresa CHAR(36) NOT NULL,
        id_suministrador BIGINT DEFAULT NULL,
        n_lineas INT NOT NULL DEFAULT 0,
        total DECIMAL(12,2) NOT NULL DEFAULT 0,
        ultima_actividad DATETIME NOT NULL,
        marcado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resuelto TINYINT(1) NOT NULL DEFAULT 0,
        UNIQUE KEY uq_b2bcarrab_token (token_sesion),
        INDEX idx_b2bcarrab_emp (id_empresa, resuelto),
        INDEX idx_b2bcarrab_sum (id_suministrador, resuelto)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
