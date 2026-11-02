"""
Migración 0248 — `registros_temperatura`: control de temperaturas (neveras/cámaras/congeladores)
registrado por el personal OPERARIO/ADMINISTRADOR de cada tienda. ADITIVA, reversible.

Nuevo módulo "Registro Temperatura" (distinto de la TAREA programada en `tareas_empleados` que recuerda
hacer la comprobación — una cosa es que el SUPERADMIN programe "revisar temperaturas" como tarea, y otra
la ejecución real: el empleado va, mide, y anota el valor aquí).
"""

VERSION = "0248"
DESCRIPCION = "registros_temperatura: control de temperaturas por tienda (OPERARIO/ADMINISTRADOR)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = """
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa CHAR(36) NOT NULL,
    id_tienda INT NOT NULL,
    equipo VARCHAR(120) NOT NULL,
    valor DECIMAL(5,2) NOT NULL,
    observaciones VARCHAR(255) DEFAULT NULL,
    usuario INT DEFAULT NULL,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rt (id_empresa, id_tienda, fecha_registro)
"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS registros_temperatura ({_TABLA}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS registros_temperatura")
