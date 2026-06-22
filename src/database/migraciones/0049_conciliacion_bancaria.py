"""
Migración 0049 — Conciliación bancaria (rama Tesorería, FASE 8). ADITIVA, idempotente.

Tres tablas:
  • extractos_bancarios: cabecera de cada extracto importado (cuenta, formato, periodo, saldos).
  • extracto_lineas: apuntes del extracto (importe con signo, conciliado, link a movimiento).
  • conciliaciones: emparejamientos línea↔movimiento (modo manual/semi/auto + diferencia).
"""

VERSION = "0049"
DESCRIPCION = "Conciliación bancaria: extractos + líneas + conciliaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS extractos_bancarios (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_cuenta     INT          DEFAULT NULL,
            nombre_fichero VARCHAR(255) DEFAULT NULL,
            formato       VARCHAR(12)  NOT NULL DEFAULT 'CSV',
            fecha_importacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_inicio  DATE         DEFAULT NULL,
            fecha_fin     DATE         DEFAULT NULL,
            saldo_inicial DECIMAL(14,2) DEFAULT NULL,
            saldo_final   DECIMAL(14,2) DEFAULT NULL,
            num_lineas    INT          NOT NULL DEFAULT 0,
            estado        VARCHAR(12)  NOT NULL DEFAULT 'importado',
            INDEX idx_eb_emp (id_empresa, id_cuenta)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS extracto_lineas (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_extracto   INT          NOT NULL,
            fecha         DATE         NOT NULL,
            importe       DECIMAL(14,2) NOT NULL DEFAULT 0,
            concepto      VARCHAR(255) DEFAULT NULL,
            referencia    VARCHAR(120) DEFAULT NULL,
            saldo         DECIMAL(14,2) DEFAULT NULL,
            conciliado    TINYINT      NOT NULL DEFAULT 0,
            id_movimiento INT          DEFAULT NULL,
            hash          VARCHAR(64)  DEFAULT NULL,
            INDEX idx_el_extracto (id_extracto),
            INDEX idx_el_conc (id_empresa, conciliado, fecha, importe)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conciliaciones (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_linea      INT          NOT NULL,
            id_movimiento INT          NOT NULL,
            tipo          VARCHAR(8)   NOT NULL DEFAULT 'manual',
            diferencia    DECIMAL(14,2) NOT NULL DEFAULT 0,
            usuario       VARCHAR(80)  DEFAULT NULL,
            creado_en     DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_conc_emp (id_empresa, id_linea)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS conciliaciones")
    cur.execute("DROP TABLE IF EXISTS extracto_lineas")
    cur.execute("DROP TABLE IF EXISTS extractos_bancarios")
