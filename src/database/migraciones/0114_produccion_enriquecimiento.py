"""
Migracion 0114 — Enriquecimiento de Producción (Módulo 14). ADITIVA, idempotente, reversible.
Auditoría: ya existen órdenes de fabricación con ciclo completo (crear/planificar/liberar/iniciar/
pausar/consumir materiales/registrar producción/finalizar/costes, integradas al kárdex real), centros
de trabajo con CAPACIDAD/calendarios/turnos, y rutas con operaciones (`services/mrp/*`). Se añade lo
ausente: PARTES DE TRABAJO (control de planta — registro de operaciones ejecutadas por centro con
tiempos reales y avance por operación de la ruta). El CRP (carga vs capacidad) se calcula reutilizando
la capacidad de centros existente. No duplica.
"""

VERSION = "0114"
DESCRIPCION = "Producción: partes de trabajo / control de planta + CRP (carga vs capacidad)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("partes_trabajo_prod", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_orden INT NOT NULL,
        id_centro INT DEFAULT NULL,
        id_operacion INT DEFAULT NULL,
        secuencia INT DEFAULT NULL,
        cantidad DECIMAL(14,3) NOT NULL DEFAULT 0,
        tiempo_min DECIMAL(12,2) NOT NULL DEFAULT 0,
        operario VARCHAR(80) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'REGISTRADO',
        fecha DATE DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_parte (id_empresa, id_orden),
        INDEX idx_parte_centro (id_centro, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
