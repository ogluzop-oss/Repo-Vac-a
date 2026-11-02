"""
Migración 0249 — `usuarios_permisos`: concesiones INDIVIDUALES de permiso por usuario. ADITIVA,
idempotente, reversible.

Complementa (no sustituye) el modelo RBAC existente (roles/permisos): es la capa que usa la nueva
pestaña "Roles" del módulo Seguridad para conceder un permiso puntual a UN usuario concreto, sin que
afecte a los demás usuarios de su mismo perfil base. Solo son concesiones ADITIVAS (no hay semántica
de "denegar" un permiso que el perfil ya conceda por defecto) — quitar aquí solo revoca una concesión
individual previamente hecha por esta misma vía.
"""

VERSION = "0249"
DESCRIPCION = "usuarios_permisos: concesiones individuales de permiso por usuario (aditivas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_permisos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36) NOT NULL,
            id_usuario  INT         NOT NULL,
            id_permiso  INT         NOT NULL,
            creado_en   DATETIME    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usuario_permiso (id_usuario, id_permiso),
            INDEX idx_up_emp (id_empresa, id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS usuarios_permisos")
