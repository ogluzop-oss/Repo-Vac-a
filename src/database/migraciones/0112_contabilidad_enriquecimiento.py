"""
Migracion 0112 — Enriquecimiento de Contabilidad (Módulo 12). ADITIVA, idempotente, reversible.
Auditoría: Contabilidad ya cubre PGC, asientos doble partida con cadena de auditoría, diario/mayor/
balances/PyG, libros de IVA + 303, cola de posting (ventas/compras/devoluciones/nómina), cierre
formal (regularización/cierre/apertura/arrastre de saldos) e informes. Se añade lo ausente: PLANTILLAS
de asiento y ASIENTOS RECURRENTES/periódicos (generación automática vía Scheduler). Reutiliza
`asientos.crear_asiento` — no reimplementa la contabilidad. No duplica.
"""

VERSION = "0112"
DESCRIPCION = "Contabilidad: plantillas de asiento + asientos recurrentes/periódicos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("contab_plantillas_asiento", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        concepto VARCHAR(200) DEFAULT NULL,
        lineas MEDIUMTEXT NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_plantilla (id_empresa, codigo)"""),
    ("contab_asientos_recurrentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_plantilla INT NOT NULL,
        concepto VARCHAR(200) DEFAULT NULL,
        periodicidad VARCHAR(20) NOT NULL DEFAULT 'mensual',
        proxima_fecha DATE NOT NULL,
        fecha_fin DATE DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        ultima_generacion DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_recurrente (id_empresa, activo, proxima_fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
