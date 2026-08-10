"""
Migracion 0111 — Enriquecimiento de Finanzas (Módulo 11). ADITIVA, idempotente, reversible.
Auditoría: Finanzas ya cubre presupuestos (versiones/escenarios/real-vs-ppto/forecast), financiación
(préstamo/leasing/renting/póliza con cuadro francés y vencimientos AP), crédito/scoring, ratios
(EBITDA/ROE/CCC), simulación what-if e IA financiera; y toda la tesorería (posición, cash flow,
previsión, conciliación, SEPA). Se añade lo ausente: registro de INMOVILIZADO/activos fijos con
amortización contable, y CENTROS DE COSTE / contabilidad analítica dimensional. No duplica.
"""

VERSION = "0111"
DESCRIPCION = "Finanzas: inmovilizado (activos fijos + amortización) + centros de coste/analítica"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("inmovilizado_activos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) DEFAULT NULL,
        descripcion VARCHAR(200) NOT NULL,
        categoria VARCHAR(60) DEFAULT NULL,
        cuenta_contable VARCHAR(20) DEFAULT NULL,
        fecha_alta DATE DEFAULT NULL,
        valor_adquisicion DECIMAL(14,2) NOT NULL DEFAULT 0,
        valor_residual DECIMAL(14,2) NOT NULL DEFAULT 0,
        vida_util_meses INT NOT NULL DEFAULT 60,
        metodo VARCHAR(20) NOT NULL DEFAULT 'lineal',
        amortizado_acumulado DECIMAL(14,2) NOT NULL DEFAULT 0,
        id_centro_coste INT DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'ALTA',
        fecha_baja DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_activo (id_empresa, estado, categoria)"""),
    ("inmovilizado_amortizaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_activo INT NOT NULL,
        periodo VARCHAR(7) NOT NULL,
        importe DECIMAL(14,2) NOT NULL DEFAULT 0,
        acumulado DECIMAL(14,2) NOT NULL DEFAULT 0,
        valor_neto DECIMAL(14,2) NOT NULL DEFAULT 0,
        dotada TINYINT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_amort (id_activo, periodo)"""),
    ("centros_coste", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        id_padre INT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_centro (id_empresa, codigo)"""),
    ("imputaciones_analiticas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_centro_coste INT NOT NULL,
        origen_tipo VARCHAR(30) NOT NULL DEFAULT 'manual',
        origen_id VARCHAR(64) DEFAULT NULL,
        concepto VARCHAR(200) DEFAULT NULL,
        importe DECIMAL(14,2) NOT NULL DEFAULT 0,
        signo VARCHAR(10) NOT NULL DEFAULT 'gasto',
        periodo VARCHAR(7) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_imput (id_empresa, id_centro_coste, periodo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    # Widen 'signo' en BDs donde 0111 se aplicó con VARCHAR(6) (idempotente).
    try:
        cur.execute("ALTER TABLE imputaciones_analiticas MODIFY signo VARCHAR(10) NOT NULL DEFAULT 'gasto'")
    except Exception:
        pass


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
