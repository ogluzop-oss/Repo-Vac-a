"""
Migración 0340 — Mapeo empresa → base de datos física (ADITIVA).

A partir de ahora, cada empresa nueva dada de alta desde el sitio web recibe su PROPIA base de
datos MariaDB (aislamiento real a nivel de motor — ver `services.provisioning.
aprovisionar_tenant_nuevo`), en vez de vivir en la `smart_manager_db` compartida. Esta tabla
(en la base COMPARTIDA del backend, no en la del tenant) es lo que permite al sitio web resolver
"esta empresa → esta base de datos" cuando necesita leer su suscripción, generar un código de
instalación, etc. — operaciones que arrancan sabiendo solo el `id_empresa` de la sesión web.

Las empresas que YA existían antes de este cambio (en `smart_manager_db`) no tienen fila aquí a
propósito: siguen resolviéndose contra la base compartida de siempre (comportamiento sin cambios).
"""

VERSION = "0340"
DESCRIPCION = "Mapeo id_empresa -> base de datos física del tenant"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenants_db (
            id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
            nombre_db   VARCHAR(64)  NOT NULL,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_tenants_db_nombre (nombre_db)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS tenants_db")
