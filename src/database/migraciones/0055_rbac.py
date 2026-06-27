"""
Migración 0055 — RBAC / ACL empresarial. ADITIVA, idempotente, reversible.

Modelo completo de roles, permisos, grupos y ACL, multiempresa, SIN tocar `usuarios.perfil`
(que permanece como capa LEGACY). El catálogo `permisos` es global (codigo único); roles y
grupos son por empresa; las asignaciones y ACL llevan ámbito (empresa/tienda/almacén/depto).
"""

VERSION = "0055"
DESCRIPCION = "RBAC/ACL empresarial: roles, permisos, grupos, asignaciones y ACL"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Catálogo global de permisos (modulo.accion).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permisos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            codigo      VARCHAR(80)  NOT NULL,
            modulo      VARCHAR(40)  NOT NULL,
            accion      VARCHAR(40)  NOT NULL,
            descripcion VARCHAR(160) DEFAULT NULL,
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_permiso (codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Roles por empresa.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            codigo      VARCHAR(40)  NOT NULL,
            nombre      VARCHAR(120) NOT NULL,
            descripcion VARCHAR(255) DEFAULT NULL,
            es_sistema  TINYINT      NOT NULL DEFAULT 0,
            estado      VARCHAR(12)  NOT NULL DEFAULT 'activo',
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            actualizado_en DATETIME  DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rol (id_empresa, codigo),
            INDEX idx_rol_emp (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS roles_permisos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_rol      INT          NOT NULL,
            id_permiso  INT          NOT NULL,
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rol_permiso (id_rol, id_permiso),
            INDEX idx_rp_emp (id_empresa, id_rol)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_roles (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_usuario  INT          NOT NULL,
            id_rol      INT          NOT NULL,
            ambito_tipo VARCHAR(16)  NOT NULL DEFAULT 'empresa',
            ambito_id   VARCHAR(40)  DEFAULT NULL,
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usuario_rol (id_usuario, id_rol, ambito_tipo, ambito_id),
            INDEX idx_ur_emp (id_empresa, id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Grupos por empresa.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            codigo      VARCHAR(40)  NOT NULL,
            nombre      VARCHAR(120) NOT NULL,
            estado      VARCHAR(12)  NOT NULL DEFAULT 'activo',
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_grupo (id_empresa, codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupos_permisos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_grupo    INT          NOT NULL,
            id_permiso  INT          NOT NULL,
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_grupo_permiso (id_grupo, id_permiso),
            INDEX idx_gp_emp (id_empresa, id_grupo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_grupos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_usuario  INT          NOT NULL,
            id_grupo    INT          NOT NULL,
            creado_en   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usuario_grupo (id_usuario, id_grupo),
            INDEX idx_ug_emp (id_empresa, id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # ACL por recurso/objeto (override fino: allow/deny por sujeto y acción).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS acl_recursos (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa   VARCHAR(36) NOT NULL,
            recurso_tipo VARCHAR(40) NOT NULL,
            recurso_id   VARCHAR(64) DEFAULT NULL,
            sujeto_tipo  VARCHAR(12) NOT NULL,
            sujeto_id    VARCHAR(64) NOT NULL,
            accion       VARCHAR(40) NOT NULL,
            permitido    TINYINT     NOT NULL DEFAULT 1,
            ambito_tipo  VARCHAR(16) NOT NULL DEFAULT 'empresa',
            ambito_id    VARCHAR(40) DEFAULT NULL,
            creado_en    DATETIME    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_acl (id_empresa, recurso_tipo, recurso_id, sujeto_tipo, sujeto_id, accion),
            INDEX idx_acl_recurso (id_empresa, recurso_tipo, recurso_id),
            INDEX idx_acl_sujeto (id_empresa, sujeto_tipo, sujeto_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    for t in ("acl_recursos", "usuarios_grupos", "grupos_permisos", "grupos",
              "usuarios_roles", "roles_permisos", "roles", "permisos"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
