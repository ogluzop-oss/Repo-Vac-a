"""
Migracion 0113 — Enriquecimiento de BI (Módulo 13). ADITIVA, idempotente, reversible.
Auditoría: BI ya cubre Data Warehouse, motor de KPIs (con registro de KPIs personalizados),
calculadores por dominio, forecasting Prophet, snapshots (scheduler), dashboard, y a nivel corporativo
OLAP (cubos/drill/slice/dice), consolidación multiempresa, benchmarking, alertas explicables, export
e IA ejecutiva. Se añade lo ausente: SUSCRIPCIONES / distribución programada de informes-KPI y
CUADROS DE MANDO PERSONALES por usuario. No duplica.
"""

VERSION = "0113"
DESCRIPCION = "BI: suscripciones/distribución de informes + cuadros de mando personales"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("bi_suscripciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'dashboard',
        recurso VARCHAR(120) DEFAULT NULL,
        usuarios VARCHAR(255) DEFAULT NULL,
        roles VARCHAR(255) DEFAULT NULL,
        canal VARCHAR(20) NOT NULL DEFAULT 'notificacion',
        periodicidad VARCHAR(20) NOT NULL DEFAULT 'mensual',
        proxima_fecha DATE NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        ultima_envio DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_suscripcion (id_empresa, activo, proxima_fecha)"""),
    ("bi_cuadros_personales", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        usuario VARCHAR(80) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        layout MEDIUMTEXT DEFAULT NULL,
        predeterminado TINYINT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_cuadro (id_empresa, usuario)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
