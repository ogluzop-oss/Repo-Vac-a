"""
Migración 0331 — Códigos de aprovisionamiento de centros. ADITIVA, idempotente, reversible.

Flujo de alta de un ordenador nuevo en un centro (`services.provisioning`, botón 🔑 en
Configuración → Datos de empresa → Centros): el superadmin genera un código corto, de un solo
uso y caduco, que el instalador del nuevo equipo canjea contra el endpoint público
`POST /provisioning/emparejar` para recibir su `.env` (credenciales de BD compartidas de la
empresa + código de centro + URL del portal) sin tener que repartir un fichero de credenciales a
mano. Sustituye al login para ESE único propósito (no hay sesión todavía en un equipo recién
instalado).
"""

VERSION = "0331"
DESCRIPCION = "Códigos de aprovisionamiento de centros (alta automática de ordenador nuevo)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS codigos_aprovisionamiento (
            id            BIGINT       AUTO_INCREMENT PRIMARY KEY,
            codigo        VARCHAR(16)  NOT NULL,
            id_centro     VARCHAR(36)  NOT NULL,
            id_empresa    CHAR(36)     NOT NULL,
            usado         TINYINT(1)   NOT NULL DEFAULT 0,
            usado_en      DATETIME              DEFAULT NULL,
            expira        DATETIME     NOT NULL,
            creado_por    INT                   DEFAULT NULL,
            creado        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_codigo_aprov (codigo),
            INDEX idx_aprov_centro (id_centro, usado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS codigos_aprovisionamiento")
