"""
Migración 0314 — tabla `vales_devolucion`. ADITIVA, idempotente, reversible.

Tercer método de reembolso en Devoluciones del TPV (junto a efectivo/tarjeta, política por
empresa): un vale descuento NO caduca, canjeable en CUALQUIER tienda de la empresa — por eso se
escopa SOLO por `id_empresa` (nunca por `id_tienda` en el canje), mismo criterio ya usado por el
motor de cupones promocionales (`cupones`, migración 0037) para "válido en toda la empresa".

No se reutiliza `cupones`: ese motor es de descuentos PROMOCIONALES sobre una compra nueva, con un
contador de usos (`usos_actuales`/`uso_maximo`), no un saldo de dinero canjeable parcialmente. Un
vale de devolución necesita llevar un IMPORTE real que se puede gastar parcialmente y generar un
vale nuevo por el sobrante — semántica distinta, tabla distinta.

`id_devolucion`/`id_vale_origen`/`id_venta_canje` son trazabilidad pura (de qué devolución nació,
si viene del sobrante de otro vale, en qué venta se canjeó) — ninguno es NOT NULL porque la fila
tiene sentido por sí misma sin esos enlaces (p. ej. un vale raíz recién emitido no tiene aún venta
de canje). `id_tienda_emision`/`id_tienda_canje` son SOLO informativos (auditoría); el canje NUNCA
filtra por tienda — sería contradecir "canjeable en cualquier tienda de la empresa".
"""

VERSION = "0314"
DESCRIPCION = "vales_devolucion (vale descuento de devoluciones TPV, canjeable en toda la empresa)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vales_devolucion (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            codigo VARCHAR(40) NOT NULL,
            importe DECIMAL(10,2) NOT NULL DEFAULT 0,
            importe_original DECIMAL(10,2) NOT NULL DEFAULT 0,
            estado VARCHAR(12) NOT NULL DEFAULT 'activo',
            id_devolucion INT DEFAULT NULL,
            id_vale_origen BIGINT DEFAULT NULL,
            id_venta_canje INT DEFAULT NULL,
            id_tienda_emision INT DEFAULT NULL,
            id_tienda_canje INT DEFAULT NULL,
            fecha_emision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_canje DATETIME DEFAULT NULL,
            UNIQUE KEY uq_vale_devolucion (id_empresa, codigo),
            KEY idx_vd_estado (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS vales_devolucion")
