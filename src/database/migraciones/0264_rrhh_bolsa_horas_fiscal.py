"""
Migración 0264 — RRHH Fase A "Cimientos de datos" del sistema de bolsa de horas + nómina dual +
trazabilidad de bajas + IRPF real (Modelo 145 AEAT). ADITIVA, idempotente, reversible. Solo sienta el
esquema; las Fases B-G (formularios, motor de nómina/IT, pantalla Modelo 145, avisos de SOMA...) lo
consumen en tandas posteriores, no forman parte de esta migración.

1. `rrhh_contratos` gana: modelo de pago (fijo/hora) + tarifa/hora, cláusula opcional de "bolsa de
   horas" (vigencia/compensación/plus de disponibilidad/periodo de regularización), firma del contrato
   (firmado/fecha_firma) y cláusula opcional independiente de "Complemento de convenio por IT".
   El IRPF NO vive aquí a propósito: no es una cláusula contractual pactada, es una retención
   tributaria variable que se calcula aparte — ver `rrhh_datos_fiscales.irpf_pct_calculado` (único
   sitio del IRPF de un empleado).
2. Nueva tabla `rrhh_bolsa_horas` — ventana de seguimiento de la bolsa de horas por empleado/contrato.
   Queda VACÍA tras esta migración: la fila se crea en la Fase B cuando un contrato con
   `bolsa_horas_activa=1` se marca `firmado=1`.
3. `rrhh_nominas` gana `estado` (borrador|aprobada), necesario para el flujo "generar borrador, aprobar
   humano" de la Fase F. Backfill: las filas que ya existieran ANTES de esta migración se marcan
   'aprobada' (se asumen históricamente cerradas/finales); no afecta a filas futuras.
4. `rrhh_ausencias` (ya existe, no se recrea) gana `tipo_contingencia`, solo relevante cuando
   `tipo='baja_medica'` — alimenta el motor de Incapacidad Temporal de la Fase F. Valores esperados
   (VARCHAR libre, mismo criterio que `rrhh_ausencias.tipo`/`rrhh_contratos.estado`, no ENUM):
   CONTINGENCIAS_COMUNES | CONTINGENCIAS_PROFESIONALES | MENSTRUACION_INCAPACITANTE |
   INTERRUPCION_EMBARAZO_GESTACION | NACIMIENTO_CUIDADO_MENOR.
5. Nuevo bloque de datos fiscales del Modelo 145 AEAT, completamente separado del contrato:
   `rrhh_datos_fiscales` (uno por empleado) + `rrhh_datos_fiscales_hijos` +
   `rrhh_datos_fiscales_ascendientes` (tablas hijas, patrón "borrar e insertar" al guardar, Fase B2).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0264"
DESCRIPCION = ("RRHH Fase A: bolsa de horas (clausula de contrato + rrhh_bolsa_horas), "
               "rrhh_nominas.estado, rrhh_ausencias.tipo_contingencia, datos fiscales IRPF (Modelo 145)")
REVERSIBLE = True
REQUIERE_BACKUP = False


_COLUMNAS_CONTRATOS = [
    ("modelo_pago", "VARCHAR(10) NOT NULL DEFAULT 'fijo'"),                        # fijo|hora
    ("tarifa_hora", "DECIMAL(8,2) NULL"),                                          # solo si modelo_pago='hora'
    ("bolsa_horas_activa", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("bolsa_horas_vigencia_meses", "INT NOT NULL DEFAULT 12"),
    ("bolsa_horas_compensacion", "VARCHAR(20) NOT NULL DEFAULT 'descanso'"),        # descanso|eleccion_trabajador|pago
    ("bolsa_horas_plus_disponibilidad", "DECIMAL(8,2) NULL"),
    ("bolsa_horas_periodo_regularizacion_meses", "INT NOT NULL DEFAULT 12"),
    ("firmado", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("fecha_firma", "DATETIME NULL"),
    ("complemento_it_activo", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("complemento_it_tipo", "VARCHAR(20) NOT NULL DEFAULT 'ninguno'"),              # porcentaje_hasta|importe_fijo|ninguno
    ("complemento_it_porcentaje", "DECIMAL(5,2) NULL"),
    ("complemento_it_tramo_dias_inicio", "INT NULL"),
    ("complemento_it_tramo_dias_fin", "INT NULL"),
]

_COLUMNAS_NOMINAS = [
    ("estado", "VARCHAR(12) NOT NULL DEFAULT 'borrador'"),                         # borrador|aprobada
]

_COLUMNAS_AUSENCIAS = [
    ("tipo_contingencia", "VARCHAR(30) NULL"),                                     # solo si tipo='baja_medica'
]


def _columna_existe(cur, tabla, columna) -> bool:
    cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE '{columna}'")
    return cur.fetchone() is not None


def _add_columns_if_missing(cur, tabla, columnas):
    for nombre, ddl in columnas:
        if not _columna_existe(cur, tabla, nombre):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {ddl}")


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID

    _add_columns_if_missing(cur, "rrhh_contratos", _COLUMNAS_CONTRATOS)

    # rrhh_nominas.estado: si la columna no existía todavía, se acaba de crear con DEFAULT 'borrador'
    # (MariaDB rellena las filas YA existentes con ese default) — backfill a 'aprobada' SOLO en ese
    # caso, para no pisar borradores genuinos de una ejecución futura de la Fase F.
    nominas_era_nueva = not _columna_existe(cur, "rrhh_nominas", "estado")
    _add_columns_if_missing(cur, "rrhh_nominas", _COLUMNAS_NOMINAS)
    if nominas_era_nueva:
        cur.execute("UPDATE rrhh_nominas SET estado='aprobada' WHERE estado='borrador'")

    _add_columns_if_missing(cur, "rrhh_ausencias", _COLUMNAS_AUSENCIAS)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_bolsa_horas (
            id                              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa                      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado                     BIGINT       NOT NULL,
            id_contrato                     BIGINT       NOT NULL,
            horas_diarias                   DECIMAL(4,2)          DEFAULT NULL,
            fecha_inicio_vigencia           DATE                  DEFAULT NULL,
            fecha_fin_vigencia              DATE                  DEFAULT NULL,
            fecha_regularizacion_limite     DATE                  DEFAULT NULL,
            creado_por                      VARCHAR(150)          DEFAULT NULL,
            fecha_creacion                  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_bh_empleado (id_empresa, id_empleado),
            INDEX idx_bh_contrato (id_contrato),
            INDEX idx_bh_regularizacion (fecha_regularizacion_limite),
            CONSTRAINT fk_bh_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE,
            CONSTRAINT fk_bh_contrato FOREIGN KEY (id_contrato)
                REFERENCES rrhh_contratos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_datos_fiscales (
            id                              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa                      CHAR(36)      NOT NULL DEFAULT '{emp}',
            id_empleado                     BIGINT        NOT NULL,
            situacion_familiar              ENUM('1','2','3')      DEFAULT NULL,
            nif_conyuge                     VARCHAR(20)             DEFAULT NULL,
            discapacidad_trabajador         VARCHAR(20)   NOT NULL DEFAULT 'ninguna',
            ayuda_terceros_movilidad        TINYINT(1)    NOT NULL DEFAULT 0,
            movilidad_geografica             TINYINT(1)    NOT NULL DEFAULT 0,
            rentas_irregulares               TINYINT(1)    NOT NULL DEFAULT 0,
            pension_compensatoria_anual     DECIMAL(10,2)           DEFAULT NULL,
            anualidades_alimentos_anual     DECIMAL(10,2)           DEFAULT NULL,
            vivienda_habitual_pre2013       TINYINT(1)    NOT NULL DEFAULT 0,
            irpf_pct_calculado              DECIMAL(5,2)            DEFAULT NULL,
            fecha_calculo                   DATETIME                DEFAULT NULL,
            created_at                      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at                      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_df_empleado (id_empresa, id_empleado),
            CONSTRAINT fk_df_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rrhh_datos_fiscales_hijos (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_datos_fiscales   BIGINT       NOT NULL,
            anio_nacimiento     SMALLINT               DEFAULT NULL,
            anio_adopcion       SMALLINT               DEFAULT NULL,
            grado_discapacidad  VARCHAR(20)   NOT NULL DEFAULT 'ninguna',
            computo_entero      TINYINT(1)    NOT NULL DEFAULT 0,
            INDEX idx_dfh_datos_fiscales (id_datos_fiscales),
            CONSTRAINT fk_dfh_datos_fiscales FOREIGN KEY (id_datos_fiscales)
                REFERENCES rrhh_datos_fiscales(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rrhh_datos_fiscales_ascendientes (
            id                                BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_datos_fiscales                 BIGINT       NOT NULL,
            anio_nacimiento                   SMALLINT              DEFAULT NULL,
            grado_discapacidad                VARCHAR(20)  NOT NULL DEFAULT 'ninguna',
            convivencia_otros_descendientes   TINYINT(1)   NOT NULL DEFAULT 0,
            INDEX idx_dfa_datos_fiscales (id_datos_fiscales),
            CONSTRAINT fk_dfa_datos_fiscales FOREIGN KEY (id_datos_fiscales)
                REFERENCES rrhh_datos_fiscales(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    for t in ("rrhh_datos_fiscales_ascendientes", "rrhh_datos_fiscales_hijos",
              "rrhh_datos_fiscales", "rrhh_bolsa_horas"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    for tabla, columnas in (
        ("rrhh_ausencias", _COLUMNAS_AUSENCIAS),
        ("rrhh_nominas", _COLUMNAS_NOMINAS),
        ("rrhh_contratos", _COLUMNAS_CONTRATOS),
    ):
        for nombre, _ in columnas:
            if _columna_existe(cur, tabla, nombre):
                cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {nombre}")
