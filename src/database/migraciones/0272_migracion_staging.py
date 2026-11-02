"""
Migración 0272 — Motor de migración/importación por etapas (Fase A, rearquitectura del importador
maestro): staging + errores por fila. ADITIVA, idempotente, reversible.

`migracion_lotes_staging` = cabecera de un LOTE de migración (una "corrida" de `MigrationEngine.stage`):
qué entidad, con qué mapeo de columnas, en qué estado (`borrador` → recién apilado sin validar,
`simulado` → pasó por `validate()`/`simulate()`, `confirmado` → ya se ejecutó `commit()` con éxito,
`cancelado`). `id_trabajo` enlaza (débilmente, sin FK física — mismo criterio que el resto del esquema,
sin ORM) con el `import_trabajos.id` REAL que crea `commit()` al completar (vía la `_registrar_trabajo`
ya existente, sin duplicar esa lógica).

`migracion_filas_staging` = el detalle fila a fila de ese lote: el dato ORIGINAL tal cual venía del
fichero/consulta de origen (`datos_originales`, JSON), el dato YA MAPEADO a campos canónicos
(`datos_mapeados`, JSON) y el resultado de `validate()` (`estado`: pendiente/valido/advertencia/error).
`external_id` es la trazabilidad que pide el negocio: el identificador de la fila en el sistema de
ORIGEN (columna id/código propios del ERP legado), para poder cruzar el histórico después — se guarda
aquí, a nivel de staging, y NO como columna nueva en `articulos`/`clientes`/`proveedores`/etc. (decisión
de alcance: no se justifica ensanchar el esquema núcleo del producto para esto; la traza ya queda
completa en esta tabla de staging, que es auditable y no se purga automáticamente).

`import_trabajos_errores` = detalle fila a fila de una importación YA EJECUTADA de verdad (liga con
`import_trabajos.id`, que hasta ahora solo guardaba contadores agregados) — alimenta el futuro "clic en
una fila del Historial → ver qué falló y por qué" y "descargar informe de errores" (Fase B, GUI).

AISLAMIENTO por `id_empresa` en las tablas de staging (mismo patrón que el resto del importador,
migración 0179). No toca datos existentes ni las tablas `import_trabajos`/`import_mapeos`.
"""

VERSION = "0272"
DESCRIPCION = ("Motor de migración por etapas: migracion_lotes_staging + migracion_filas_staging "
              "(dry-run/staging) + import_trabajos_errores (detalle de errores por fila)")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("migracion_lotes_staging", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_trabajo BIGINT DEFAULT NULL,
        entidad VARCHAR(32) NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'borrador',
        mapeo TEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        usuario VARCHAR(80) DEFAULT NULL,
        INDEX idx_mig_lotes_emp (id_empresa, entidad, creado),
        INDEX idx_mig_lotes_trabajo (id_trabajo)"""),
    ("migracion_filas_staging", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_lote_staging BIGINT NOT NULL,
        numero_fila INT NOT NULL,
        external_id VARCHAR(120) DEFAULT NULL,
        datos_originales TEXT DEFAULT NULL,
        datos_mapeados TEXT DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_mig_filas_lote (id_lote_staging, estado),
        INDEX idx_mig_filas_ext (id_lote_staging, external_id)"""),
    ("import_trabajos_errores", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_trabajo BIGINT NOT NULL,
        numero_fila INT DEFAULT NULL,
        campo VARCHAR(80) DEFAULT NULL,
        valor_original TEXT DEFAULT NULL,
        severidad VARCHAR(20) NOT NULL DEFAULT 'error',
        motivo TEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_imp_err_trabajo (id_trabajo, severidad)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
