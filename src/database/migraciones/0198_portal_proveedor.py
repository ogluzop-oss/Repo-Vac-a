"""
Migración 0198 — Portal de proveedor (enlace bidireccional empresa↔proveedor). ADITIVA, idempotente,
reversible. Multiempresa (id_empresa VARCHAR(36)).

NO duplica infraestructura existente (N7): las TARIFAS siguen en `proveedor_precios_negociados`
(migr 0103/0197), los PEDIDOS en `compras_pedidos` (con su máquina de estados), las INCIDENCIAS en
`compras_incidencias` y la EVALUACIÓN en `proveedores_evaluacion`. Este esquema solo añade lo que el
portal necesita y que aún no existía:

- `portal_proveedor_cuentas`   → la cuenta/enlace de acceso de cada proveedor (invitación + token).
- `portal_pedido_estado`       → el estado que el PROVEEDOR reporta de un pedido (aceptado/en reparto/…).
- `portal_proveedor_stock`     → el stock que el proveedor declara por artículo/unidad.
- `portal_rfq` + `portal_rfq_ofertas` → petición de oferta (RFQ / subasta inversa) y sus respuestas.
- `portal_mensajes`            → mensajería empresa↔proveedor (por pedido o general).

El portal es DEGRADABLE: sin desplegar el enlace remoto, la empresa sigue operando en local; estas
tablas son la base compartida que el día de producción sincroniza ambos lados.
"""

VERSION = "0198"
DESCRIPCION = "Portal de proveedor: cuentas/invitaciones, estado de pedido, stock, RFQ/ofertas y mensajería"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── Cuenta/enlace del proveedor (invitación + token de acceso) ──────────────
    ("portal_proveedor_cuentas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_proveedor BIGINT NOT NULL,
        email VARCHAR(160) DEFAULT NULL,
        token VARCHAR(64) NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'invitado',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        ultima_conexion DATETIME DEFAULT NULL,
        UNIQUE KEY uq_ppc (id_empresa, id_proveedor),
        UNIQUE KEY uq_ppc_token (token),
        INDEX idx_ppc (id_empresa, estado)"""),
    # ── Estado que el PROVEEDOR reporta de un pedido (uno vigente por pedido) ────
    ("portal_pedido_estado", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_pedido BIGINT NOT NULL,
        id_proveedor BIGINT DEFAULT NULL,
        estado_proveedor VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        nota VARCHAR(255) DEFAULT NULL,
        actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ppe (id_empresa, id_pedido),
        INDEX idx_ppe (id_empresa, estado_proveedor)"""),
    # ── Stock que el proveedor declara por artículo/unidad ──────────────────────
    ("portal_proveedor_stock", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_proveedor BIGINT NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        stock DECIMAL(14,4) NOT NULL DEFAULT 0,
        unidad_medida VARCHAR(12) NOT NULL DEFAULT 'unidad',
        actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pps (id_empresa, id_proveedor, codigo_articulo, unidad_medida),
        INDEX idx_pps (id_empresa, codigo_articulo)"""),
    # ── RFQ (petición de oferta / subasta inversa) ──────────────────────────────
    ("portal_rfq", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 1,
        unidad_medida VARCHAR(12) NOT NULL DEFAULT 'unidad',
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        fecha_limite DATE DEFAULT NULL,
        id_pedido_adjudicado BIGINT DEFAULT NULL,
        creado_por VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_rfq (id_empresa, estado)"""),
    ("portal_rfq_ofertas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_rfq BIGINT NOT NULL,
        id_proveedor BIGINT NOT NULL,
        precio DECIMAL(12,4) NOT NULL DEFAULT 0,
        unidad_medida VARCHAR(12) NOT NULL DEFAULT 'unidad',
        plazo_dias INT DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'ofertada',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_rfqof (id_empresa, id_rfq, id_proveedor),
        INDEX idx_rfqof (id_empresa, id_rfq)"""),
    # ── Mensajería empresa↔proveedor (por pedido o general) ─────────────────────
    ("portal_mensajes", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_proveedor BIGINT NOT NULL,
        id_pedido BIGINT DEFAULT NULL,
        autor VARCHAR(10) NOT NULL DEFAULT 'empresa',
        cuerpo VARCHAR(2000) NOT NULL,
        leido TINYINT NOT NULL DEFAULT 0,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_pmsg (id_empresa, id_proveedor, id_pedido)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
