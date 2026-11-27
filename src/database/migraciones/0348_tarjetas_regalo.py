"""
Migración 0348 — tabla `tarjetas_regalo`. ADITIVA, idempotente, reversible.

Petición explícita, 2026-11-16: botón "Consultar saldo" en el escaneo de tarjeta regalo del TPV
(`tpv._EscanearTarjetaDialog`). Hasta ahora, vender una tarjeta regalo (`_add_tarjeta_regalo`) solo
añadía una línea al ticket (código + importe cargado) — el "saldo" de la tarjeta NO se guardaba en
ningún sitio, así que no había nada que consultar. Esta tabla es el saldo real, por tarjeta.

Mismo criterio que `vales_devolucion` (migración 0314): escopada SOLO por `id_empresa` (nunca por
tienda) — una tarjeta regalo, igual que un vale, debe poder consultarse/usarse en cualquier tienda
de la empresa. `codigo` es el código de barras YA IMPRESO en la tarjeta física (no se genera aquí,
al contrario que `vales_devolucion.codigo`), de ahí la clave única (id_empresa, codigo): vender dos
veces la misma tarjeta física es un error, no un caso válido.

Alcance de esta migración/servicio: alta de saldo al VENDER la tarjeta + consulta de saldo. El
canje de saldo como forma de pago en caja NO se aborda aquí (no pedido en este punto) — igual que
hoy la línea de venta de la tarjeta tampoco se integra con ningún cobro.
"""

VERSION = "0348"
DESCRIPCION = "tarjetas_regalo (saldo real de tarjetas regalo vendidas en TPV, consultable en toda la empresa)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarjetas_regalo (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            codigo VARCHAR(60) NOT NULL,
            saldo DECIMAL(10,2) NOT NULL DEFAULT 0,
            saldo_inicial DECIMAL(10,2) NOT NULL DEFAULT 0,
            estado VARCHAR(12) NOT NULL DEFAULT 'activa',
            id_tienda_emision INT DEFAULT NULL,
            fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion DATETIME DEFAULT NULL,
            UNIQUE KEY uq_tarjeta_regalo (id_empresa, codigo),
            KEY idx_tr_estado (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS tarjetas_regalo")
