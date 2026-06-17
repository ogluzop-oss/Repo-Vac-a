"""
Migración 0013 — Contabilidad base (E6.1). ADITIVA y reversible.

Crea las tablas del cuadro contable (config + ejercicios + cuentas), multiempresa
por `id_empresa`. NO siembra el plan: el PGC se clona POR EMPRESA al activar la
contabilidad (`contabilidad.cuentas.activar`). No toca ventas/compras/fiscal.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0013"
DESCRIPCION = "Contabilidad base (contab_config, contab_ejercicios, contab_cuentas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_config (
            id_empresa        CHAR(36)    NOT NULL PRIMARY KEY,
            activo            TINYINT(1)  NOT NULL DEFAULT 0,
            plan              VARCHAR(20) NOT NULL DEFAULT 'pgc_pymes',
            estrategia_posting VARCHAR(20) NOT NULL DEFAULT 'cola_diaria',
            ejercicio_actual  INT                  DEFAULT NULL,
            fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_ejercicios (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            anio          INT          NOT NULL,
            fecha_inicio  DATE                  DEFAULT NULL,
            fecha_fin     DATE                  DEFAULT NULL,
            estado        VARCHAR(10)  NOT NULL DEFAULT 'abierto',  -- abierto|cerrado
            fecha_cierre  DATETIME              DEFAULT NULL,
            UNIQUE KEY uq_ejercicio (id_empresa, anio),
            INDEX idx_ej_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_cuentas (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            codigo        VARCHAR(10)  NOT NULL,
            nombre        VARCHAR(160) NOT NULL,
            grupo         TINYINT      NOT NULL DEFAULT 0,          -- 1er dígito (1..7)
            tipo          VARCHAR(12)  NOT NULL DEFAULT 'otro',     -- activo|pasivo|pn|gasto|ingreso
            naturaleza    VARCHAR(10)  NOT NULL DEFAULT 'deudora',  -- deudora|acreedora
            admite_apuntes TINYINT(1)  NOT NULL DEFAULT 1,
            estado        VARCHAR(10)  NOT NULL DEFAULT 'activa',
            UNIQUE KEY uq_cuenta (id_empresa, codigo),
            INDEX idx_cta_emp (id_empresa),
            INDEX idx_cta_grupo (id_empresa, grupo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS contab_cuentas")
    cur.execute("DROP TABLE IF EXISTS contab_ejercicios")
    cur.execute("DROP TABLE IF EXISTS contab_config")
