"""
Migracion 0116 — Enriquecimiento de Calidad (Módulo 16). ADITIVA, idempotente, reversible.
Auditoría: Calidad ya cubre planes de inspección por fase/criterios, inspecciones, no conformidades,
CAPA (correctivas/preventivas), auditorías con hallazgos, trazabilidad de lote/artículo y analítica
(KPIs/anomalías/tendencia). Se añade lo ausente: CALIBRACIÓN de equipos de medida (metrología),
CERTIFICADOS de análisis por lote y SPC (Cp/Cpk). No duplica.
"""

VERSION = "0116"
DESCRIPCION = "Calidad: metrología/calibración + certificados de análisis + SPC (Cp/Cpk)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("calidad_equipos_medida", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        ubicacion VARCHAR(120) DEFAULT NULL,
        frecuencia_dias INT NOT NULL DEFAULT 365,
        ultima_calibracion DATE DEFAULT NULL,
        proxima_calibracion DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_equipo (id_empresa, codigo)"""),
    ("calidad_calibraciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_equipo INT NOT NULL,
        fecha DATE NOT NULL,
        resultado VARCHAR(20) NOT NULL DEFAULT 'CONFORME',
        certificado VARCHAR(120) DEFAULT NULL,
        proveedor VARCHAR(120) DEFAULT NULL,
        desviacion DECIMAL(12,4) DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_calib (id_equipo, fecha)"""),
    ("calidad_certificados", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        numero VARCHAR(60) DEFAULT NULL,
        articulo VARCHAR(64) DEFAULT NULL,
        id_lote INT DEFAULT NULL,
        resultados MEDIUMTEXT DEFAULT NULL,
        conforme TINYINT NOT NULL DEFAULT 1,
        emitido_por VARCHAR(80) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_cert (id_empresa, articulo, id_lote)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
