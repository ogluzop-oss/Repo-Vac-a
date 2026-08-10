"""
Migración 0138 — PCD · Fase 0 (RFC-CD-006): FORMALIZACIÓN del esquema del canal de venta online.

Lleva al sistema de migraciones versionadas el esquema que hoy declara `conexion.ensure_schema`
(pedidos_online, pedidos_online_items, ecommerce_config, pasarela_config, pagos_webhooks_log).
ADITIVA e IDEMPOTENTE: `CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS` → no cambia ninguna
columna ni crea funcionalidad nueva; es un no-op sobre instalaciones existentes.

Prerrequisito de la estrategia Strangler (N6/RFC-CD-006 §4 Fase 0). `ensure_schema` se mantiene como
garantía en tiempo de ejecución (ambas rutas son idempotentes → 0 regresión). Por eso `revertir` es
un **no-op**: revertir una formalización NO debe destruir datos de producción (las tablas siguen
siendo propiedad de `ensure_schema`; su retirada de ahí sería un ADR posterior).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID as _EMP

VERSION = "0138"
DESCRIPCION = ("PCD Fase 0: formalización del esquema de venta online "
               "(pedidos_online[_items], ecommerce_config, pasarela_config, pagos_webhooks_log)")
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # 1) Pedidos online (neutro respecto a plataforma; referencia_externa).
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS pedidos_online (
            id_pedido          CHAR(36)     NOT NULL PRIMARY KEY,
            id_empresa         CHAR(36)     NOT NULL DEFAULT '{_EMP}',
            id_tienda          INT                   DEFAULT NULL,
            id_usuario         INT                   DEFAULT NULL,
            trabajador         VARCHAR(255)          DEFAULT NULL,
            cliente_id         INT                   DEFAULT NULL,
            cliente_nombre     VARCHAR(255)          DEFAULT NULL,
            cliente_telefono   VARCHAR(50)           DEFAULT NULL,
            cliente_email      VARCHAR(255)          DEFAULT NULL,
            direccion_envio    VARCHAR(500)          DEFAULT NULL,
            total              DECIMAL(12,2) NOT NULL DEFAULT 0,
            estado             VARCHAR(20)  NOT NULL DEFAULT 'PENDIENTE',
            plataforma         VARCHAR(30)  NOT NULL DEFAULT 'interno',
            referencia_externa VARCHAR(120)          DEFAULT NULL,
            observaciones      TEXT                  DEFAULT NULL,
            fecha              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_po_empresa (id_empresa),
            INDEX idx_po_tienda (id_tienda),
            INDEX idx_po_estado (estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(
        "ALTER TABLE pedidos_online "
        "ADD COLUMN IF NOT EXISTS stock_descontado TINYINT(1) NOT NULL DEFAULT 0, "
        "ADD COLUMN IF NOT EXISTS transportista VARCHAR(120) DEFAULT NULL, "
        "ADD COLUMN IF NOT EXISTS seguimiento   VARCHAR(120) DEFAULT NULL, "
        "ADD COLUMN IF NOT EXISTS fecha_envio   DATETIME     DEFAULT NULL, "
        "ADD COLUMN IF NOT EXISTS referencia_pago VARCHAR(160) DEFAULT NULL, "
        "ADD COLUMN IF NOT EXISTS enlace_pago     VARCHAR(600) DEFAULT NULL, "
        "ADD COLUMN IF NOT EXISTS estado_pago     VARCHAR(20)  DEFAULT NULL")

    # 2) Ítems del pedido online.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_online_items (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_pedido       CHAR(36)     NOT NULL,
            codigo_articulo VARCHAR(50)           DEFAULT NULL,
            nombre          VARCHAR(255)          DEFAULT NULL,
            cantidad        INT          NOT NULL DEFAULT 1,
            precio_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
            subtotal        DECIMAL(12,2) NOT NULL DEFAULT 0,
            origen_stock    VARCHAR(20)  NOT NULL DEFAULT 'central',
            INDEX idx_poi_pedido (id_pedido)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 3) Configuración de e-commerce por empresa (adaptador multiplataforma).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ecommerce_config (
            id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
            plataforma  VARCHAR(30)  NOT NULL DEFAULT 'web',
            base_url    VARCHAR(500)          DEFAULT NULL,
            api_key     VARCHAR(255)          DEFAULT NULL,
            api_secret  VARCHAR(255)          DEFAULT NULL,
            estado      VARCHAR(20)  NOT NULL DEFAULT 'activo',
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 4) Configuración de la pasarela de pago por empresa (+ webhook_secret).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pasarela_config (
            id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
            proveedor   VARCHAR(30)  NOT NULL DEFAULT 'redsys',
            api_key     VARCHAR(255)          DEFAULT NULL,
            api_secret  VARCHAR(255)          DEFAULT NULL,
            comercio    VARCHAR(120)          DEFAULT NULL,
            modo        VARCHAR(10)  NOT NULL DEFAULT 'test',
            moneda      VARCHAR(3)   NOT NULL DEFAULT 'EUR',
            estado      VARCHAR(20)  NOT NULL DEFAULT 'activo',
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(
        "ALTER TABLE pasarela_config "
        "ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(255) DEFAULT NULL")

    # 5) Registro/idempotencia de webhooks de pago.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS pagos_webhooks_log (
            id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa  CHAR(36)     NOT NULL DEFAULT '{_EMP}',
            proveedor   VARCHAR(30)  NOT NULL,
            evento_id   VARCHAR(180) NOT NULL,
            evento_tipo VARCHAR(80)           DEFAULT NULL,
            referencia  VARCHAR(180)          DEFAULT NULL,
            id_pedido   CHAR(36)              DEFAULT NULL,
            estado      VARCHAR(20)           DEFAULT NULL,
            resultado   VARCHAR(20)  NOT NULL DEFAULT 'procesado',
            ip_origen   VARCHAR(60)           DEFAULT NULL,
            recibido    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_wh_evento (id_empresa, proveedor, evento_id),
            INDEX idx_wh_pedido (id_pedido), INDEX idx_wh_ref (referencia)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    # NO-OP intencional (ver docstring): es una migración de FORMALIZACIÓN. Las tablas siguen siendo
    # garantizadas por `ensure_schema`; revertir no debe destruir datos de producción. La retirada de
    # estas tablas de `ensure_schema` (para que la migración pase a ser dueña) será un ADR posterior.
    pass
