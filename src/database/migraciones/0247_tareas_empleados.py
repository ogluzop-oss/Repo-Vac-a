"""
Migración 0247 — `tareas_empleados`: encargos programados por un SUPERADMIN (conectado a una tienda,
vía el selector de tienda ya existente) para el personal OPERARIO/ADMINISTRADOR de esa tienda concreta.
ADITIVA, reversible.

Restructuración Aprobaciones/Tareas: distinto del Programador de Jobs (`services.scheduler`, tareas de
FONDO internas de la app, ver `panel_jobs.py`) — esto son encargos para una PERSONA (p. ej. "registrar
la temperatura de las neveras"), con ciclo de vida simple (pendiente → completada/cancelada) y
resolución manual por el propio empleado ("marcar como finalizada"), no una máquina de estados de
aprobación (no usa el motor Workflow/BPM).
"""

VERSION = "0247"
DESCRIPCION = "tareas_empleados: encargos programados por tienda (SUPERADMIN → OPERARIO/ADMIN)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = """
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa CHAR(36) NOT NULL,
    id_tienda INT NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT DEFAULT NULL,
    frecuencia VARCHAR(20) DEFAULT NULL,
    creado_por INT DEFAULT NULL,
    estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
    completado_por INT DEFAULT NULL,
    fecha_completado DATETIME DEFAULT NULL,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_te (id_empresa, id_tienda, estado)
"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS tareas_empleados ({_TABLA}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS tareas_empleados")
