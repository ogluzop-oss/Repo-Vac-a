"""
Migración 0058 — BI / Data Warehouse / KPIs. ADITIVA, idempotente, reversible.

Capa analítica INDEPENDIENTE (no toca tablas operativas): registro de KPIs, sus valores
históricos, snapshots y tablas de hechos por dominio. Multiempresa (id_empresa + dimensiones
tienda/almacén). Se alimenta de los servicios existentes; nunca duplica lógica de negocio.
"""

VERSION = "0058"
DESCRIPCION = "BI/DW: bi_kpi_def, bi_kpi_valores, bi_snapshots y bi_hechos_*"
REVERSIBLE = True
REQUIERE_BACKUP = False

_DIM = ("id_empresa VARCHAR(36) NOT NULL, id_tienda INT DEFAULT NULL, "
        "id_almacen INT DEFAULT NULL, fecha_snapshot DATE NOT NULL, "
        "periodo VARCHAR(10) DEFAULT NULL, "
        "creado_en DATETIME DEFAULT CURRENT_TIMESTAMP")

_HECHOS = ("ventas", "compras", "inventario", "rrhh", "tesoreria", "contabilidad", "aeat")


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bi_kpi_def (
            id INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(60) NOT NULL,
            dominio VARCHAR(20) NOT NULL,
            nombre VARCHAR(120) NOT NULL,
            unidad VARCHAR(16) DEFAULT NULL,
            objetivo DECIMAL(18,4) DEFAULT NULL,
            sentido VARCHAR(8) DEFAULT 'mayor',
            descripcion VARCHAR(255) DEFAULT NULL,
            UNIQUE KEY uq_kpi_def (codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bi_kpi_valores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NOT NULL,
            id_tienda INT DEFAULT NULL,
            id_almacen INT DEFAULT NULL,
            codigo VARCHAR(60) NOT NULL,
            valor DECIMAL(18,4) NOT NULL DEFAULT 0,
            periodo VARCHAR(10) NOT NULL,
            fecha DATE NOT NULL,
            creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_kpi_val (id_empresa, codigo, periodo, fecha, id_tienda, id_almacen),
            INDEX idx_kpi_val (id_empresa, codigo, fecha)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bi_snapshots (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NOT NULL,
            tipo VARCHAR(12) NOT NULL DEFAULT 'daily',
            fecha_snapshot DATE NOT NULL,
            kpis INT NOT NULL DEFAULT 0,
            estado VARCHAR(12) NOT NULL DEFAULT 'ok',
            creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_snap (id_empresa, tipo, fecha_snapshot),
            INDEX idx_snap (id_empresa, tipo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    for dom in _HECHOS:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS bi_hechos_{dom} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                {_DIM},
                metrica VARCHAR(60) NOT NULL,
                valor DECIMAL(18,4) NOT NULL DEFAULT 0,
                dim1 VARCHAR(80) DEFAULT NULL,
                UNIQUE KEY uq_h_{dom} (id_empresa, fecha_snapshot, periodo, metrica, dim1, id_tienda, id_almacen),
                INDEX idx_h_{dom} (id_empresa, metrica, fecha_snapshot)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


def revertir(cur):
    for dom in reversed(_HECHOS):
        cur.execute(f"DROP TABLE IF EXISTS bi_hechos_{dom}")
    for t in ("bi_snapshots", "bi_kpi_valores", "bi_kpi_def"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
