"""
Migración 0052 — Infraestructura común de modelos AEAT (FASE AEAT-1). ADITIVA, idempotente.

  • aeat_declaraciones: cabecera de cada declaración (modelo/ejercicio/periodo, estado, resultado,
    hash documental, fichero, fechas). Estados BORRADOR/GENERADO/PRESENTADO/ANULADO.
  • aeat_declaracion_lineas: casillas (casilla/descripcion/importe) de cada declaración.
Reutilizable por todos los modelos (303, y futuros 390/111/190/347/349). Multiempresa.
"""

VERSION = "0052"
DESCRIPCION = "Infra AEAT: aeat_declaraciones + aeat_declaracion_lineas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aeat_declaraciones (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      VARCHAR(36)  NOT NULL,
            modelo          VARCHAR(8)   NOT NULL,
            ejercicio       INT          NOT NULL,
            periodo         VARCHAR(4)   NOT NULL,
            estado          VARCHAR(12)  NOT NULL DEFAULT 'BORRADOR',
            fecha_generacion   DATETIME  DEFAULT CURRENT_TIMESTAMP,
            fecha_presentacion DATETIME  DEFAULT NULL,
            resultado       DECIMAL(14,2) NOT NULL DEFAULT 0,
            hash            VARCHAR(64)  DEFAULT NULL,
            fichero_generado VARCHAR(255) DEFAULT NULL,
            observaciones   TEXT         DEFAULT NULL,
            INDEX idx_aeat_emp (id_empresa, modelo, ejercicio, periodo, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aeat_declaracion_lineas (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_declaracion  INT          NOT NULL,
            casilla         VARCHAR(8)   NOT NULL,
            descripcion     VARCHAR(160) DEFAULT NULL,
            importe         DECIMAL(14,2) NOT NULL DEFAULT 0,
            INDEX idx_aeat_lin (id_declaracion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS aeat_declaracion_lineas")
    cur.execute("DROP TABLE IF EXISTS aeat_declaraciones")
