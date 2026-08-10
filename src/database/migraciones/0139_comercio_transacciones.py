"""
Migración 0139 — PCD · Fase 2 (RFC-CD-002/006): Transacción Comercial (piedra angular).

Entidad UNIFICADA (N1/N8) + líneas + eventos (timeline) + historial de decisiones (N9 → Audit Replay).
ADITIVA, idempotente, reversible (tablas NUEVAS → revert las elimina). Multiempresa/multitienda.
No cambia nada existente; `pedidos_online` sigue intacto (Strangler: se enlaza por id_pedido_origen).
"""

VERSION = "0139"
DESCRIPCION = "PCD Fase 2: transaccion_comercial + lineas + eventos + decisiones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("transaccion_comercial", """
        id_tx        CHAR(36)     NOT NULL PRIMARY KEY,
        id_empresa   CHAR(36)     NOT NULL,
        id_tienda    INT                   DEFAULT NULL,
        origen       VARCHAR(30)  NOT NULL DEFAULT 'web',     -- canal (N8)
        tipo         VARCHAR(20)  NOT NULL DEFAULT 'pedido',  -- presupuesto|carrito|reserva|pedido|...
        estado       VARCHAR(20)  NOT NULL DEFAULT 'BORRADOR',
        cliente_id   INT                   DEFAULT NULL,
        cliente_nombre   VARCHAR(255)      DEFAULT NULL,
        cliente_telefono VARCHAR(50)       DEFAULT NULL,
        cliente_email    VARCHAR(255)      DEFAULT NULL,
        direccion_envio  VARCHAR(500)      DEFAULT NULL,
        moneda       VARCHAR(3)   NOT NULL DEFAULT 'EUR',
        subtotal     DECIMAL(12,2) NOT NULL DEFAULT 0,
        descuento    DECIMAL(12,2) NOT NULL DEFAULT 0,
        impuestos    DECIMAL(12,2) NOT NULL DEFAULT 0,
        total        DECIMAL(12,2) NOT NULL DEFAULT 0,
        referencia_externa VARCHAR(120)    DEFAULT NULL,
        referencia_pago    VARCHAR(160)    DEFAULT NULL,
        id_factura         VARCHAR(64)     DEFAULT NULL,
        id_transaccion_padre CHAR(36)      DEFAULT NULL,      -- abono/devolución ↔ venta origen
        id_pedido_origen     CHAR(36)      DEFAULT NULL,      -- enlace Strangler a pedidos_online
        usuario      VARCHAR(255)          DEFAULT NULL,
        trabajador   VARCHAR(255)          DEFAULT NULL,
        metadata     MEDIUMTEXT            DEFAULT NULL,
        idempotencia_key VARCHAR(120)      DEFAULT NULL,
        creada       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actualizada  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_tx_idem (id_empresa, idempotencia_key),
        INDEX idx_tx_emp (id_empresa), INDEX idx_tx_tienda (id_tienda),
        INDEX idx_tx_estado (estado), INDEX idx_tx_origen (origen),
        INDEX idx_tx_pedido (id_pedido_origen)"""),
    ("transaccion_lineas", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_tx        CHAR(36)     NOT NULL,
        id_empresa   CHAR(36)     DEFAULT NULL,
        codigo_articulo VARCHAR(50) DEFAULT NULL,
        nombre       VARCHAR(255)          DEFAULT NULL,
        tipo_producto VARCHAR(20) NOT NULL DEFAULT 'fisico',  -- fisico|digital|servicio|suscripcion|...
        cantidad     INT          NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
        descuento    DECIMAL(12,2) NOT NULL DEFAULT 0,
        impuesto     DECIMAL(12,2) NOT NULL DEFAULT 0,
        subtotal     DECIMAL(12,2) NOT NULL DEFAULT 0,
        id_publicacion BIGINT              DEFAULT NULL,       -- FK futura (CD-004)
        sourcing     MEDIUMTEXT            DEFAULT NULL,       -- decisión Availability/Fulfillment (CD-005)
        estado_linea VARCHAR(20)  NOT NULL DEFAULT 'pendiente',
        INDEX idx_txl_tx (id_tx)"""),
    ("transaccion_eventos", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_tx        CHAR(36)     NOT NULL,
        id_empresa   CHAR(36)     DEFAULT NULL,
        tipo_evento  VARCHAR(40)  NOT NULL,
        estado_desde VARCHAR(20)           DEFAULT NULL,
        estado_hasta VARCHAR(20)           DEFAULT NULL,
        actor        VARCHAR(120)          DEFAULT NULL,
        payload      MEDIUMTEXT            DEFAULT NULL,
        ts           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_txe_tx (id_tx)"""),
    ("transaccion_decisiones", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_tx        CHAR(36)     NOT NULL,
        id_linea     BIGINT                DEFAULT NULL,
        id_empresa   CHAR(36)     DEFAULT NULL,
        motor        VARCHAR(20)  NOT NULL,                    -- availability|fulfillment|rules|ia|workflow|humano
        decision     VARCHAR(255)          DEFAULT NULL,
        motivo       TEXT                  DEFAULT NULL,
        entradas     MEDIUMTEXT            DEFAULT NULL,
        resultado    MEDIUMTEXT            DEFAULT NULL,
        confianza    DECIMAL(5,3)          DEFAULT NULL,
        actor        VARCHAR(120)          DEFAULT NULL,
        ts           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_txd_tx (id_tx)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
