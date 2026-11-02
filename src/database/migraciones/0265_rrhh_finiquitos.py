"""
Migración 0265 — Tabla `rrhh_finiquitos` (disciplina borrador/aprobada para FINIQUITOS). ADITIVA,
idempotente, reversible.

Auditoría (sesión RRHH/nóminas): a diferencia de `rrhh_nominas` (F4.1.2/Fase A, migr 0017/0264),
el cálculo de FINIQUITO nunca tuvo persistencia estructurada — `finiquito_servicio.
calcular_finiquito_empleado` es una función pura que devuelve un `FiniquitoResultado` en memoria,
y `rrhh_finiquito_inline.py._generar()` escribía el PDF directamente en disco y lo registraba
SOLO en el índice documental genérico (`src/db/documentos.registrar_documento` — ruta/tipo/nombre,
sin importes ni estado). `persistencia._TIPO_DOC["FINIQUITO"]` existía pero `registrar_generacion
("FINIQUITO", ...)` nunca se invocaba desde ningún sitio: no había ninguna fila con `estado` que un
humano pudiera aprobar, así que el PDF (documento legal) quedaba de facto auto-finalizado.

`rrhh_finiquitos` cierra esa brecha replicando la MISMA forma/semántica que `rrhh_nominas.estado`
(migr 0264): `estado VARCHAR(12) DEFAULT 'borrador'` (borrador|aprobada). Sin backfill especial
(tabla nueva, no hay filas previas que reclasificar).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0265"
DESCRIPCION = "RRHH: tabla rrhh_finiquitos (borrador/aprobada, mismo patrón que rrhh_nominas.estado)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_finiquitos (
            id                BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa        CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado       BIGINT       NOT NULL,
            fecha_efectos     DATE                  DEFAULT NULL,
            total_bruto       DECIMAL(12,2) NOT NULL DEFAULT 0,
            total_liquido     DECIMAL(12,2) NOT NULL DEFAULT 0,
            conceptos         JSON                  DEFAULT NULL,
            estado            VARCHAR(12)  NOT NULL DEFAULT 'borrador',  -- borrador|aprobada
            ref_documento     VARCHAR(255)          DEFAULT NULL,
            aprobado_por      VARCHAR(120)          DEFAULT NULL,
            fecha_aprobacion  DATETIME              DEFAULT NULL,
            created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_fin_empleado (id_empleado, fecha_efectos),
            INDEX idx_fin_estado (id_empresa, estado),
            CONSTRAINT fk_fin_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS rrhh_finiquitos")
