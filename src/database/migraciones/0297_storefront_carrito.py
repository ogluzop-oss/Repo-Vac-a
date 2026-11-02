"""
Migración 0297 — Motor de Alta Conversión e-Commerce: carrito persistente del storefront público
(Drawer Cart + One-Page Checkout) y detección/recuperación de carritos abandonados. ADITIVA,
reversible, idempotente.

No existía NINGÚN carrito incremental en el storefront público (`backend/storefront.py` era, hasta
esta fase, un catálogo de SOLO LECTURA — confirmado por auditoría previa) — `pedidos_online`
(migr. 0138) sigue siendo el sistema de registro del PEDIDO final, sin cambios; estas tablas son
SOLO el carrito EN CURSO, antes de confirmar. Mismo patrón exacto ya validado en producción para el
carrito B2B (`b2b_carrito_lineas`/`b2b_carrito_actividad`/`b2b_carrito_abandono`, migr. 0222/0280),
adaptado al comprador público (sin sesión de empresa: identificado solo por `token_sesion`, una
cookie opaca de navegador — ver `backend/storefront.py`).

`cd_carrito_lineas`: una fila por (token_sesion, codigo) — añadir el mismo artículo dos veces
INCREMENTA la cantidad (UNIQUE KEY + ON DUPLICATE KEY UPDATE), nunca duplica la línea.

`cd_carrito_actividad`: última vez que el carrito CAMBIÓ (añadir/quitar/actualizar cantidad) +
`email` — capturado en cuanto el comprador lo escribe en el checkout (antes de pagar), pedido
explícito ("captura temprana de leads"). Sin `email`, un carrito nunca puede recuperarse por
correo (degradación honesta: no se inventa un destinatario).

`cd_carrito_abandono`: registro de detección/notificación (evita renotificar el mismo carrito sin
cambios en cada pasada del job), con `token_restaurar` = el propio `token_sesion` (el carrito YA
vive bajo ese token; "restaurar con 1 clic" solo necesita volver a fijar la cookie a ese valor,
sin reconstruir nada) y `notificado` (el email de recuperación se envía como mucho una vez por
episodio de abandono).
"""

VERSION = "0297"
DESCRIPCION = "Storefront: carrito persistente (Drawer Cart) + detección/recuperación de abandono"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_carrito_lineas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        token_sesion VARCHAR(64) NOT NULL,
        id_empresa CHAR(36) NOT NULL,
        codigo VARCHAR(64) NOT NULL,
        nombre VARCHAR(255) DEFAULT NULL,
        imagen VARCHAR(500) DEFAULT NULL,
        cantidad INT NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cdcarr_token_codigo (token_sesion, codigo),
        INDEX idx_cdcarr_token (token_sesion),
        INDEX idx_cdcarr_emp (id_empresa)"""),
    ("cd_carrito_actividad", """
        token_sesion VARCHAR(64) NOT NULL PRIMARY KEY,
        id_empresa CHAR(36) NOT NULL,
        email VARCHAR(255) DEFAULT NULL,
        actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"""),
    ("cd_carrito_abandono", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        token_sesion VARCHAR(64) NOT NULL,
        id_empresa CHAR(36) NOT NULL,
        email VARCHAR(255) DEFAULT NULL,
        n_lineas INT NOT NULL DEFAULT 0,
        total DECIMAL(12,2) NOT NULL DEFAULT 0,
        ultima_actividad DATETIME NOT NULL,
        marcado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        notificado TINYINT(1) NOT NULL DEFAULT 0,
        resuelto TINYINT(1) NOT NULL DEFAULT 0,
        UNIQUE KEY uq_cdcarrab_token (token_sesion),
        INDEX idx_cdcarrab_emp (id_empresa, resuelto)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _cols in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
