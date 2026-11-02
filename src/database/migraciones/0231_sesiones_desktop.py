"""
Migración 0231 — Sesiones activas del escritorio (límite de sesión simultánea por usuario).

Solo SUPERADMIN puede mantener varias sesiones de escritorio simultáneas (para monitorizar varias
tiendas a la vez de forma remota); ADMINISTRADOR/OPERARIO quedan limitados a una única sesión activa.
El registro se hace con un latido periódico (`latido_en`) para que una sesión huérfana (app cerrada
sin logout, cierre inesperado) expire sola tras `SESION_DESKTOP_TTL_SEG` sin bloquear al usuario para
siempre. ADITIVA, idempotente, reversible.
"""

VERSION = "0231"
DESCRIPCION = "Tabla de sesiones activas de escritorio (control de sesión única salvo SUPERADMIN)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("sesiones_desktop_activas", """
    id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_usuario   INT          NOT NULL,
    nombre       VARCHAR(255) NULL,
    perfil       VARCHAR(50)  NULL,
    iniciada_en  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    latido_en    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sesion_desktop_usuario (id_usuario)""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute(f"DROP TABLE IF EXISTS {_TABLA[0]}")
