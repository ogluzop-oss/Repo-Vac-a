"""
Migración 0287 — `usuarios.email`.

HALLAZGO durante la implementación: `usuarios.email` YA EXISTÍA antes de esta migración —
`db/conexion.py::ensure_schema()` (el bootstrap idempotente que corre en cada arranque, trabajo de
identidad por usuario C1.4) ya ejecuta `ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email
VARCHAR(255) DEFAULT NULL` desde antes de esta sesión — por eso `db/usuario.py::validar_login_usuario`
ya tenía lógica `tiene_email` (detecta la columna con `SHOW COLUMNS` y permite login por email si
está presente). La premisa original de esta migración ("usuarios no tiene columna de email") era
incorrecta; se confirmó en vivo contra la base de desarrollo ANTES de escribir esta versión final
(`SHOW COLUMNS FROM usuarios` ya mostraba `email varchar(255)`).

Esta migración se mantiene de todos modos, como registro EXPLÍCITO en el motor de migraciones
versionado (`db/migrador.py`, pensado para SaaS/multi-tenant: "ejecutable por cada base/tenant de
forma independiente") de una columna de la que varios módulos nuevos pasan a depender de verdad
(`services/comunicacion_interna` — destinatarios Para/CC/Cco de circulares/encuestas por email, ver
`usuarios_internos.listar_usuarios_empresa`) — así un tenant/entorno que se aprovisione alguna vez
SOLO a través de `migrador.aplicar_pendientes` (sin pasar por `ensure_schema()`) también queda
cubierto. `VARCHAR(255)` (no 150, como se planteó antes de verificar) para coincidir EXACTAMENTE con
el tipo real ya desplegado por `ensure_schema()` — dos definiciones distintas de la misma columna
sería confuso y, en MariaDB, un ALTER a un tipo más corto sobre una columna ya poblada podría truncar
datos reales.

ADITIVA e idempotente (`IF NOT EXISTS`, columna NULL, sin tocar datos existentes). NO reversible de
verdad: esta migración no es la dueña de la columna (lo es `ensure_schema()`, que la recrearía en el
siguiente arranque de todas formas) — `revertir()` es un no-op deliberado, documentado abajo, en vez
de un DROP que daría una falsa sensación de reversibilidad real.

Sin índice: `usuarios` es una tabla pequeña por empresa y la única consulta nueva (`WHERE
id_empresa=... AND email LIKE ...`) ya usa el índice existente sobre `id_empresa` en el plan de
ejecución más caro (no es el caso de uso de esta app tener decenas de miles de empleados).
"""

VERSION = "0287"
DESCRIPCION = ("Registra usuarios.email en el motor de migraciones versionado (ya la crea "
               "ensure_schema(); ver docstring) — base del destinatario interno por correo en "
               "circulares/encuestas")
REVERSIBLE = False
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    # Normalmente ya existe (creada por `ensure_schema()`, ver docstring) — este ALTER solo actúa en
    # un tenant/entorno que se aprovisione exclusivamente vía `migrador`, sin pasar por ensure_schema.
    if not _existe_columna(cur, "usuarios", "email"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN email VARCHAR(255) DEFAULT NULL")


def revertir(cur):
    # No-op deliberado: esta migración no es la propietaria de la columna (lo es `ensure_schema()`,
    # que la recrearía en el siguiente arranque) — un DROP real aquí sería una reversibilidad falsa.
    pass
