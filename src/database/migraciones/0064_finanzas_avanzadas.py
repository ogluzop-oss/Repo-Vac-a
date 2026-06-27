"""
Migracion 0064 — Finanzas avanzadas: presupuestos, deuda/financiacion, credito/riesgo.
ADITIVA, idempotente, reversible. NO toca tesoreria/conciliacion/SEPA/contabilidad existentes.
Reutiliza contabilidad (PyG/balance), tesoreria (vencimientos/movimientos) y BI. Multiempresa.
"""

VERSION = "0064"
DESCRIPCION = "Finanzas avanzadas: presupuestos, financiacion (prestamos/leasing), credito/riesgo"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── FASE A · Presupuestos financieros ─────────────────────────────────────
    ("presupuestos_financieros", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        ejercicio INT NOT NULL,
        periodicidad VARCHAR(12) NOT NULL DEFAULT 'mensual',
        estado VARCHAR(12) NOT NULL DEFAULT 'borrador',
        version_activa INT NOT NULL DEFAULT 1,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pptos (id_empresa, codigo, ejercicio),
        INDEX idx_pptos (id_empresa, ejercicio, estado)"""),
    ("presupuesto_versiones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_presupuesto INT NOT NULL,
        version INT NOT NULL DEFAULT 1,
        nota VARCHAR(255) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pver (id_presupuesto, version)"""),
    ("presupuesto_escenarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_presupuesto INT NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'base',
        factor DECIMAL(8,4) NOT NULL DEFAULT 1,
        descripcion VARCHAR(160) DEFAULT NULL,
        UNIQUE KEY uq_pesc (id_presupuesto, tipo)"""),
    ("presupuesto_lineas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_presupuesto INT NOT NULL,
        version INT NOT NULL DEFAULT 1,
        escenario VARCHAR(16) NOT NULL DEFAULT 'base',
        categoria VARCHAR(16) NOT NULL DEFAULT 'gasto',
        concepto VARCHAR(160) NOT NULL,
        cuenta_contable VARCHAR(20) DEFAULT NULL,
        periodo INT NOT NULL DEFAULT 0,
        importe DECIMAL(16,2) NOT NULL DEFAULT 0,
        INDEX idx_plin (id_presupuesto, version, escenario, periodo)"""),
    # ── FASE B · Deuda / Financiacion ─────────────────────────────────────────
    ("financiaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'prestamo',
        codigo VARCHAR(40) DEFAULT NULL,
        entidad VARCHAR(160) DEFAULT NULL,
        capital DECIMAL(16,2) NOT NULL DEFAULT 0,
        tipo_interes DECIMAL(8,4) NOT NULL DEFAULT 0,
        periodicidad VARCHAR(12) NOT NULL DEFAULT 'mensual',
        num_cuotas INT NOT NULL DEFAULT 0,
        cuota DECIMAL(16,2) NOT NULL DEFAULT 0,
        saldo_pendiente DECIMAL(16,2) NOT NULL DEFAULT 0,
        valor_residual DECIMAL(16,2) NOT NULL DEFAULT 0,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        id_cuenta INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'vigente',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_fin (id_empresa, tipo, estado)"""),
    ("financiacion_cuotas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_financiacion INT NOT NULL,
        numero INT NOT NULL,
        fecha DATE DEFAULT NULL,
        cuota DECIMAL(16,2) NOT NULL DEFAULT 0,
        interes DECIMAL(16,2) NOT NULL DEFAULT 0,
        principal DECIMAL(16,2) NOT NULL DEFAULT 0,
        saldo_vivo DECIMAL(16,2) NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        id_vencimiento INT DEFAULT NULL,
        INDEX idx_fincuota (id_financiacion, numero)"""),
    # ── FASE C · Credito / Riesgo ─────────────────────────────────────────────
    ("credit_scoring", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_cliente INT NOT NULL,
        score INT NOT NULL DEFAULT 0,
        nivel VARCHAR(10) NOT NULL DEFAULT 'medio',
        detalle TEXT DEFAULT NULL,
        calculado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_score (id_empresa, id_cliente)"""),
    ("alertas_credito", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_cliente INT NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'limite_superado',
        detalle VARCHAR(255) DEFAULT NULL,
        importe DECIMAL(16,2) NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_alcred (id_empresa, id_cliente, estado)"""),
    ("bloqueos_credito", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_cliente INT NOT NULL,
        motivo VARCHAR(255) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado_por VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        liberado_en DATETIME DEFAULT NULL,
        INDEX idx_blqcred (id_empresa, id_cliente, activo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
