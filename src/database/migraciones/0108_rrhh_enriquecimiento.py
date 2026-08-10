"""
Migracion 0108 — Enriquecimiento de RRHH (Módulo 8). ADITIVA, idempotente, reversible.
Auditoría: empleados, ausencias, fichajes/jornadas/pausas, control horario, nómina (motor +
cotización), vacaciones, contratos, documentos (contrato/finiquito/nómina/certificado), firma y
portal del empleado YA existen. Se añade solo lo ausente: evaluación de desempeño, formación/
capacitación, selección/candidatos (ATS ligero) y planificación de turnos de personal. No duplica.
"""

VERSION = "0108"
DESCRIPCION = "RRHH: evaluación desempeño + formación + selección + turnos de personal"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("rrhh_evaluaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_empleado INT DEFAULT NULL,
        periodo VARCHAR(20) DEFAULT NULL,
        evaluador VARCHAR(80) DEFAULT NULL,
        competencias MEDIUMTEXT DEFAULT NULL,
        puntuacion DECIMAL(5,2) DEFAULT NULL,
        objetivos MEDIUMTEXT DEFAULT NULL,
        comentarios TEXT DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        cerrado DATETIME DEFAULT NULL,
        INDEX idx_eval (id_empresa, id_empleado, periodo)"""),
    ("rrhh_formacion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        titulo VARCHAR(160) NOT NULL,
        tipo VARCHAR(40) DEFAULT 'curso',
        proveedor VARCHAR(120) DEFAULT NULL,
        horas DECIMAL(6,1) DEFAULT 0,
        coste DECIMAL(12,2) DEFAULT 0,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PLANIFICADA',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_form (id_empresa, estado)"""),
    ("rrhh_formacion_asistentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_formacion INT NOT NULL,
        id_empleado INT NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'INSCRITO',
        aprovechamiento DECIMAL(5,2) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_form_asis (id_formacion, id_empleado)"""),
    ("rrhh_seleccion_candidatos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        vacante VARCHAR(160) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        email VARCHAR(160) DEFAULT NULL,
        telefono VARCHAR(40) DEFAULT NULL,
        cv_ruta VARCHAR(255) DEFAULT NULL,
        fase VARCHAR(30) NOT NULL DEFAULT 'RECIBIDO',
        valoracion DECIMAL(5,2) DEFAULT NULL,
        notas TEXT DEFAULT NULL,
        id_empleado INT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_cand (id_empresa, vacante, fase)"""),
    ("rrhh_turnos_plan", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_tienda VARCHAR(40) DEFAULT NULL,
        id_empleado INT NOT NULL,
        fecha DATE NOT NULL,
        hora_inicio TIME DEFAULT NULL,
        hora_fin TIME DEFAULT NULL,
        rol VARCHAR(60) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PLANIFICADO',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_turno_plan (id_empresa, id_tienda, fecha),
        INDEX idx_turno_emp (id_empleado, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
