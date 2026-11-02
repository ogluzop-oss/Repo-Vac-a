"""
Migración 0322 — RRHH: IBAN de domiciliación de nómina (cifrado + máscara), aprobación en
cascada de vacaciones (responsable → RRHH) y firma criptográfica real de documentos. ADITIVA,
idempotente, reversible.

Auditoría previa: `rrhh_empleados` no tenía NINGÚN campo bancario (ni `iban` ni `cuenta_bancaria`);
el precedente de cifrado+máscara a reutilizar es `db.tesoreria.cuentas_bancarias`/`db.sepa`
(columna cifrada + columna de máscara para la UI, vía `utils.cripto`/`utils.iban`). La aprobación
de vacaciones (`rrhh_vacaciones.estado`) solo tenía un paso (`pendiente→aprobada/denegada`); se
añade `aprobado_por_responsable` para registrar AMBOS aprobadores (responsable directo + RRHH) sin
perder al que ya se guardaba en `aprobado_por` (que pasa a representar siempre la aprobación FINAL).
La firma documental (`rrhh_documentos.estado_firma`, migr. 0019) era solo trazabilidad de
aceptación (hash SHA-256 + clic + auditoría) sin ninguna firma criptográfica real — se añade
`firma_criptografica` (firma RSA-PSS/SHA-256 del hash, con clave propia POR EMPRESA, nunca el
certificado fiscal de AEAT) y `cifrado` (si el PDF en disco está cifrado en reposo, para el
"repositorio cifrado" de nóminas/certificados).
"""

VERSION = "0322"
DESCRIPCION = "rrhh_empleados.iban + id_responsable, vacaciones en cascada, firma criptográfica RRHH"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Domiciliación de nómina (petición explícita): IBAN cifrado en reposo (nunca en claro) +
    # máscara para mostrar siempre SOLO los 4 últimos dígitos en UI/documentos generados.
    cur.execute("ALTER TABLE rrhh_empleados ADD COLUMN IF NOT EXISTS iban VARCHAR(255) NULL")
    cur.execute("ALTER TABLE rrhh_empleados ADD COLUMN IF NOT EXISTS iban_mascara VARCHAR(40) NULL")

    # Responsable directo (jefe/manager) del empleado — base de la aprobación jerárquica en
    # cascada de vacaciones/ausencias. Auto-referencia a la propia tabla.
    cur.execute("ALTER TABLE rrhh_empleados ADD COLUMN IF NOT EXISTS id_responsable BIGINT NULL")
    cur.execute("ALTER TABLE rrhh_empleados ADD INDEX IF NOT EXISTS idx_emp_responsable (id_responsable)")

    # Aprobación en cascada: el responsable directo aprueba primero (opcional, solo si el
    # empleado tiene `id_responsable`); RRHH da el visto bueno final. `aprobado_por` sigue
    # siendo SIEMPRE el aprobador final (compatibilidad con lecturas existentes).
    cur.execute("ALTER TABLE rrhh_vacaciones ADD COLUMN IF NOT EXISTS aprobado_por_responsable "
               "VARCHAR(120) NULL")

    # Firma criptográfica real (RSA-PSS/SHA-256) sobre el hash ya anclado del documento, y marca
    # de si el PDF en disco está cifrado en reposo (repositorio cifrado de nóminas/certificados).
    cur.execute("ALTER TABLE rrhh_documentos ADD COLUMN IF NOT EXISTS firma_criptografica "
               "TEXT NULL")
    cur.execute("ALTER TABLE rrhh_documentos ADD COLUMN IF NOT EXISTS cifrado "
               "TINYINT(1) NOT NULL DEFAULT 0")

    # Clave de firma POR EMPRESA (nunca la del certificado fiscal AEAT, dominio legal distinto):
    # clave privada SIEMPRE cifrada con `utils.cripto` antes de persistir, clave pública en claro
    # (necesaria para que cualquiera pueda verificar la firma).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rrhh_firma_claves (
            id_empresa             CHAR(36) NOT NULL PRIMARY KEY,
            clave_privada_cifrada  TEXT     NOT NULL,
            clave_publica          TEXT     NOT NULL,
            creado                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS rrhh_firma_claves")
    cur.execute("ALTER TABLE rrhh_documentos DROP COLUMN IF EXISTS cifrado")
    cur.execute("ALTER TABLE rrhh_documentos DROP COLUMN IF EXISTS firma_criptografica")
    cur.execute("ALTER TABLE rrhh_vacaciones DROP COLUMN IF EXISTS aprobado_por_responsable")
    cur.execute("ALTER TABLE rrhh_empleados DROP COLUMN IF EXISTS id_responsable")
    cur.execute("ALTER TABLE rrhh_empleados DROP COLUMN IF EXISTS iban_mascara")
    cur.execute("ALTER TABLE rrhh_empleados DROP COLUMN IF EXISTS iban")
