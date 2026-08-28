"""
Migración 0218 — Smart Suppliers · Fase A: identidad del proveedor en la plataforma (Portal Web) +
invitación por email. ADITIVA, idempotente, reversible.

`suministradores` es la identidad ÚNICA de cada proveedor en la plataforma (login propio del Portal
Web, independiente de cualquier empresa compradora). `proveedores.id_suministrador` es el puente hacia
esa identidad — NO sustituye la tabla `proveedores` existente (que sigue siendo el registro por
empresa compradora usado por Homologar/Devoluciones/Incidencias/Evaluación tal cual hoy).

Nunca se guarda un IBAN/dato bancario en claro: `cuenta_conectada_id` es el identificador OPACO que
devuelve el PSP (Stripe Connect u otro) — mismo principio que el `psp_cuentas_conectadas` retirado.
"""

VERSION = "0218"
DESCRIPCION = "Smart Suppliers: suministradores (identidad Portal Web) + invitaciones + sesiones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("suministradores", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        razon_social VARCHAR(255) NOT NULL,
        cif VARCHAR(20) NOT NULL,
        sector_id INT DEFAULT NULL,
        email_login VARCHAR(255) NOT NULL,
        contacto VARCHAR(255) DEFAULT NULL,
        telefono VARCHAR(50) DEFAULT NULL,
        estado_kyb VARCHAR(20) NOT NULL DEFAULT 'pendiente',
        cuenta_conectada_id VARCHAR(120) DEFAULT NULL,
        fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_suministrador_cif (cif),
        INDEX idx_sum_sector (sector_id), INDEX idx_sum_estado (estado_kyb)"""),
    ("invitaciones_proveedor", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) NOT NULL,
        id_proveedor INT DEFAULT NULL,
        email VARCHAR(255) NOT NULL,
        token VARCHAR(64) NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
        expira DATETIME NOT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        usado_en DATETIME DEFAULT NULL,
        UNIQUE KEY uq_invit_token (token),
        INDEX idx_invit_emp (id_empresa), INDEX idx_invit_prov (id_proveedor)"""),
    ("suministrador_sesiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_suministrador BIGINT NOT NULL,
        token_sesion VARCHAR(64) NOT NULL,
        expira DATETIME NOT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_sesion_token (token_sesion),
        INDEX idx_sesion_sum (id_suministrador)"""),
]

_PROVEEDORES = [("id_suministrador", "BIGINT DEFAULT NULL")]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for col, ddl in _PROVEEDORES:
        cur.execute(f"ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _PROVEEDORES:
        cur.execute(f"ALTER TABLE proveedores DROP COLUMN IF EXISTS {col}")
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
