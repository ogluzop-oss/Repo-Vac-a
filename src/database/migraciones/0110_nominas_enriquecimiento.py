"""
Migracion 0110 — Enriquecimiento de Nóminas (Módulo 10). ADITIVA, idempotente, reversible.
Auditoría: el motor de nómina (`src/rrhh/nomina_motor.py`) YA clasifica conceptos
(DEVENGO_SALARIAL/NO_SALARIAL/DEDUCCION), prorratea pagas extra, calcula bases SS con límites por
grupo, IRPF, anticipos, embargos, cotización del TRABAJADOR y de la EMPRESA (`ss_empresa`) y genera
PDF. Se añade solo lo ausente: gestión de anticipos (solicitud/aprobación/amortización), conceptos
recurrentes por empleado (retribución flexible/pluses fijos) e informe coste-empresa (agrega el
`ss_empresa` que el motor ya calcula pero no se reportaba). No reescribe el motor. No duplica.
"""

VERSION = "0110"
DESCRIPCION = "Nóminas: anticipos gestionados + conceptos recurrentes + informe coste-empresa"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("rrhh_anticipos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_empleado INT NOT NULL,
        importe_total DECIMAL(12,2) NOT NULL,
        cuotas INT NOT NULL DEFAULT 1,
        importe_cuota DECIMAL(12,2) NOT NULL DEFAULT 0,
        pendiente DECIMAL(12,2) NOT NULL DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'SOLICITADO',
        motivo VARCHAR(255) DEFAULT NULL,
        aprobado_por VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_anticipo (id_empresa, id_empleado, estado)"""),
    ("rrhh_conceptos_recurrentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_empleado INT NOT NULL,
        clave VARCHAR(40) NOT NULL,
        importe DECIMAL(12,2) NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_concepto (id_empleado, clave)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
