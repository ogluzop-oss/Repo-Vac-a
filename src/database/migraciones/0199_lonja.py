"""
Migración 0199 — Lonja B2B (mercado/subasta entre empresas). ADITIVA, idempotente, reversible.

La Lonja es el MERCADO COMPARTIDO entre varias empresas compradoras y los vendedores (proveedores): un
vendedor publica un listado (precio de compra directa + puja mínima + divisa + cantidad) y las empresas
compran ya (primero que llega se lo lleva) o pujan. A diferencia del resto del ERP, los `listados` y
`vendedores` NO están aislados por empresa (son visibles por todas las compradoras); cada `puja` y
`transacción` registra la empresa compradora que actúa. La compra es ATÓMICA (bloqueo de fila) para que no
haya dobles ventas, e IDEMPOTENTE (clave única) para que un reintento no duplique.

Reutiliza el motor de compras del comprador (db.compras crea el pedido real en su propio tenant) y el
sistema multidivisa; no crea stock ni pedidos paralelos.
"""

VERSION = "0199"
DESCRIPCION = "Lonja B2B: vendedores, listados, pujas, transacciones e importes de cambio (mercado/subasta)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # Vendedor global del mercado (proveedor como vendedor de la Lonja; define su DIVISA de referencia).
    ("lonja_vendedores", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(160) NOT NULL,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        token VARCHAR(64) NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'activo',
        id_empresa_origen VARCHAR(36) DEFAULT NULL,
        id_proveedor_origen BIGINT DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_lv_token (token),
        INDEX idx_lv (estado)"""),
    # Listado publicado (oferta viva del mercado): compra directa y/o puja.
    ("lonja_listados", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_vendedor BIGINT NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        precio DECIMAL(14,4) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        puja_minima DECIMAL(14,4) NOT NULL DEFAULT 0,
        unidad_medida VARCHAR(12) NOT NULL DEFAULT 'unidad',
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 1,
        cantidad_disponible DECIMAL(14,4) NOT NULL DEFAULT 1,
        permite_compra_directa TINYINT NOT NULL DEFAULT 1,
        permite_puja TINYINT NOT NULL DEFAULT 1,
        estado VARCHAR(12) NOT NULL DEFAULT 'activo',
        fecha_limite DATETIME DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ll (codigo_articulo, estado),
        INDEX idx_ll_v (id_vendedor)"""),
    # Puja de una empresa compradora sobre un listado.
    ("lonja_pujas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_listado BIGINT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        importe DECIMAL(14,4) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        estado VARCHAR(12) NOT NULL DEFAULT 'pujada',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_lp (id_listado, estado),
        INDEX idx_lp_emp (id_empresa)"""),
    # Transacción cerrada (compra directa o adjudicación) — idempotente por clave.
    ("lonja_transacciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_listado BIGINT NOT NULL,
        id_vendedor BIGINT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(14,4) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        tipo VARCHAR(16) NOT NULL DEFAULT 'compra_directa',
        estado VARCHAR(12) NOT NULL DEFAULT 'confirmada',
        id_pedido BIGINT DEFAULT NULL,
        clave_idem VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_lt_idem (clave_idem),
        INDEX idx_lt (id_listado),
        INDEX idx_lt_emp (id_empresa)"""),
    # Tipos de cambio del mercado (1 unidad de `divisa` = `tasa_eur` EUR). Editable; 1.0 si se desconoce.
    ("lonja_tipos_cambio", """
        divisa VARCHAR(8) NOT NULL PRIMARY KEY,
        tasa_eur DECIMAL(18,8) NOT NULL DEFAULT 1,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
