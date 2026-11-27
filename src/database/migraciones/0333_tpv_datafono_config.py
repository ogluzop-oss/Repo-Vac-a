"""
Migración 0333 — Config del DATÁFONO FÍSICO por tienda (cobro real con tarjeta en TPV/autocobro).
ADITIVA, idempotente, reversible.

A diferencia de `pasarela_config` (pasarela de pago ONLINE, una fila por EMPRESA — Canal Web/
Click&Collect), el datáfono es un dispositivo FÍSICO de CADA tienda: cada centro empareja su
propio terminal con su propio proveedor (Viva/Stripe Terminal/SumUp/...), así que la config va por
(id_empresa, id_tienda). Consumida por `services.tpv.datafono` (registro extensible de
proveedores) y resuelta por `services.tpv.card_terminal_service.TerminalManager` según la tienda
activa de la sesión.
"""

VERSION = "0333"
DESCRIPCION = "Config del datáfono físico por tienda (cobro real con tarjeta, TPV/autocobro)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tpv_datafono_config (
            id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL,
            id_tienda       INT          NOT NULL,
            proveedor       VARCHAR(30)  NOT NULL DEFAULT 'simulado',
            api_key         VARCHAR(255)          DEFAULT NULL,
            api_secret      VARCHAR(255)          DEFAULT NULL,
            comercio        VARCHAR(120)          DEFAULT NULL,
            terminal_id     VARCHAR(120)          DEFAULT NULL,
            terminal_nombre VARCHAR(120)          DEFAULT NULL,
            modo            VARCHAR(10)  NOT NULL DEFAULT 'test',
            moneda          VARCHAR(3)   NOT NULL DEFAULT 'EUR',
            estado          VARCHAR(20)  NOT NULL DEFAULT 'activo',
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_datafono_tienda (id_empresa, id_tienda)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS tpv_datafono_config")
