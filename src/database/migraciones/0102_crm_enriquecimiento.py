"""
Migracion 0102 — Enriquecimiento funcional del CRM (Módulo 1). ADITIVA, idempotente, reversible.
Añade SOLO lo que faltaba tras la auditoría (el resto del CRM ya existe y NO se toca):
  · geolocalización de clientes (latitud/longitud),
  · vínculo oportunidad → venta/pedido (id_venta),
  · campañas comerciales / marketing (crm_campanias + destinatarios),
  · objetivos comerciales (crm_objetivos),
  · rutas comerciales (crm_rutas + crm_ruta_paradas).
Multiempresa por id_empresa. No duplica lógica: reutiliza clientes/leads/ventas/actividades existentes.
"""

VERSION = "0102"
DESCRIPCION = "CRM: geo clientes + oportunidad↔venta + campañas + objetivos + rutas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = [
    ("clientes", "latitud", "DECIMAL(10,7) DEFAULT NULL"),
    ("clientes", "longitud", "DECIMAL(10,7) DEFAULT NULL"),
    ("crm_oportunidades", "id_venta", "INT DEFAULT NULL"),
]

_TABLAS = [
    ("crm_campanias", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        canal VARCHAR(40) DEFAULT 'email',
        segmento_objetivo VARCHAR(60) DEFAULT NULL,
        presupuesto DECIMAL(12,2) DEFAULT 0,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR',
        resultado_json TEXT DEFAULT NULL,
        responsable VARCHAR(80) DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_camp (id_empresa, estado)"""),
    ("crm_campania_destinatarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_campania INT NOT NULL,
        id_cliente INT DEFAULT NULL,
        id_lead INT DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_campdest (id_campania, estado)"""),
    ("crm_objetivos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        responsable VARCHAR(80) DEFAULT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'ventas',
        periodo VARCHAR(20) DEFAULT NULL,
        objetivo_valor DECIMAL(14,2) NOT NULL DEFAULT 0,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_obj (id_empresa, responsable, tipo)"""),
    ("crm_rutas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        responsable VARCHAR(80) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PLANIFICADA',
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ruta (id_empresa, estado)"""),
    ("crm_ruta_paradas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_ruta INT NOT NULL,
        id_cliente INT DEFAULT NULL,
        orden INT NOT NULL DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
        notas VARCHAR(255) DEFAULT NULL,
        id_actividad INT DEFAULT NULL,
        INDEX idx_parada (id_ruta, orden)"""),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for tabla, col, definicion in _COLUMNAS:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
