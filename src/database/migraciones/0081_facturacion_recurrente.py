"""
Migracion 0081 — Facturacion recurrente + suscripciones (FASE 4.1/4.2). ADITIVA, reversible, idempotente.

- facturacion_recurrente: plantillas de facturas periodicas (alquileres, mantenimiento, cuotas…).
- cliente_suscripciones: suscripciones comerciales del CLIENTE (no confundir con la suscripcion
  SaaS del propio tenant). Nombre 'cliente_suscripciones' para evitar colision con el modulo SaaS.

Ambas generan facturas reutilizando el MOTOR ACTUAL (facturas_cliente.crear_factura). Aditivo.
"""

VERSION = "0081"
DESCRIPCION = "facturacion_recurrente + cliente_suscripciones (FASE 4.1/4.2)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturacion_recurrente (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_cliente BIGINT DEFAULT NULL,
            id_tienda INT DEFAULT NULL,
            concepto VARCHAR(160) DEFAULT NULL,
            estado VARCHAR(15) NOT NULL DEFAULT 'activa',
            fecha_inicio DATE DEFAULT NULL,
            fecha_fin DATE DEFAULT NULL,
            frecuencia VARCHAR(12) NOT NULL DEFAULT 'mensual',
            dia_facturacion INT DEFAULT 1,
            importe DECIMAL(12,2) NOT NULL DEFAULT 0,
            iva DECIMAL(5,2) DEFAULT NULL,
            divisa VARCHAR(3) DEFAULT NULL,
            tipo_documento VARCHAR(20) NOT NULL DEFAULT 'factura',
            plantilla VARCHAR(60) DEFAULT NULL,
            ultima_generacion DATE DEFAULT NULL,
            proxima_generacion DATE DEFAULT NULL,
            fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_frec_emp (id_empresa, estado),
            INDEX idx_frec_prox (proxima_generacion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cliente_suscripciones (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_cliente BIGINT DEFAULT NULL,
            plan VARCHAR(60) DEFAULT NULL,
            estado VARCHAR(15) NOT NULL DEFAULT 'activa',
            fecha_inicio DATE DEFAULT NULL,
            fecha_fin DATE DEFAULT NULL,
            renovacion_automatica TINYINT(1) NOT NULL DEFAULT 1,
            precio DECIMAL(12,2) NOT NULL DEFAULT 0,
            divisa VARCHAR(3) DEFAULT NULL,
            frecuencia VARCHAR(12) NOT NULL DEFAULT 'mensual',
            modo VARCHAR(12) NOT NULL DEFAULT 'mensual',
            ultima_renovacion DATE DEFAULT NULL,
            proxima_renovacion DATE DEFAULT NULL,
            id_recurrente BIGINT DEFAULT NULL,
            fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_susc_emp (id_empresa, estado),
            INDEX idx_susc_prox (proxima_renovacion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cliente_suscripciones")
    cur.execute("DROP TABLE IF EXISTS facturacion_recurrente")
