"""
Migracion 0062 — MRP/Fabricacion + Calidad. ADITIVA, idempotente, reversible.

NO toca tablas existentes (articulos/movimientos_stock/lotes/compras permanecen). La produccion
se integra en el kardex existente (movimientos_stock + lotes), NO crea stock paralelo. Multiempresa.
"""

VERSION = "0062"
DESCRIPCION = "MRP (BOM, centros prod, rutas, OF, costes, motor) + Calidad (inspecciones, NC, CAPA, auditorias)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── MRP-A · BOM ───────────────────────────────────────────────────────────
    ("bom", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        articulo_final VARCHAR(64) NOT NULL,
        version VARCHAR(20) NOT NULL DEFAULT '1',
        nombre VARCHAR(160) DEFAULT NULL,
        cantidad_base DECIMAL(14,4) NOT NULL DEFAULT 1,
        estado VARCHAR(12) NOT NULL DEFAULT 'borrador',
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bom (id_empresa, articulo_final, version),
        INDEX idx_bom (id_empresa, articulo_final, estado)"""),
    ("bom_lineas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_bom INT NOT NULL,
        componente VARCHAR(64) NOT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 1,
        merma_pct DECIMAL(6,2) NOT NULL DEFAULT 0,
        es_alternativo TINYINT NOT NULL DEFAULT 0,
        sustituye_a VARCHAR(64) DEFAULT NULL,
        orden INT NOT NULL DEFAULT 0,
        INDEX idx_boml (id_bom)"""),
    # ── MRP-B · Centros de trabajo productivos ────────────────────────────────
    ("centros_trabajo_prod", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'linea',
        coste_hora DECIMAL(12,4) NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_ctp (id_empresa, codigo)"""),
    ("capacidades_prod", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_centro INT NOT NULL,
        horas_dia DECIMAL(6,2) NOT NULL DEFAULT 8,
        unidades_hora DECIMAL(12,4) NOT NULL DEFAULT 0,
        INDEX idx_cap (id_centro)"""),
    ("calendarios_prod", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_centro INT NOT NULL,
        fecha DATE NOT NULL,
        disponible TINYINT NOT NULL DEFAULT 1,
        horas DECIMAL(6,2) NOT NULL DEFAULT 8,
        INDEX idx_calp (id_centro, fecha)"""),
    ("turnos_prod", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_centro INT NOT NULL,
        nombre VARCHAR(60) NOT NULL,
        hora_inicio VARCHAR(5) DEFAULT NULL,
        hora_fin VARCHAR(5) DEFAULT NULL,
        INDEX idx_turno (id_centro)"""),
    # ── MRP-C · Rutas ─────────────────────────────────────────────────────────
    ("rutas_fabricacion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        articulo_final VARCHAR(64) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_ruta (id_empresa, codigo)"""),
    ("operaciones_fabricacion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ruta INT NOT NULL,
        secuencia INT NOT NULL DEFAULT 10,
        nombre VARCHAR(160) NOT NULL,
        id_centro INT DEFAULT NULL,
        tiempo_estandar_min DECIMAL(12,2) NOT NULL DEFAULT 0,
        INDEX idx_opf (id_ruta, secuencia)"""),
    # ── MRP-D · Ordenes de fabricacion ────────────────────────────────────────
    ("ordenes_fabricacion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        articulo_final VARCHAR(64) NOT NULL,
        id_bom INT DEFAULT NULL,
        id_ruta INT DEFAULT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 1,
        cantidad_producida DECIMAL(14,4) NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'borrador',
        id_almacen INT DEFAULT NULL,
        lote_destino VARCHAR(64) DEFAULT NULL,
        responsable INT DEFAULT NULL,
        fecha_prevista DATE DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_inicio DATETIME DEFAULT NULL,
        fecha_fin DATETIME DEFAULT NULL,
        INDEX idx_of (id_empresa, estado)"""),
    ("of_operaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_of INT NOT NULL,
        secuencia INT NOT NULL DEFAULT 10,
        nombre VARCHAR(160) NOT NULL,
        id_centro INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        tiempo_real_min DECIMAL(12,2) NOT NULL DEFAULT 0,
        INDEX idx_ofop (id_of, secuencia)"""),
    ("of_consumos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_of INT NOT NULL,
        componente VARCHAR(64) NOT NULL,
        cantidad_plan DECIMAL(14,4) NOT NULL DEFAULT 0,
        cantidad_real DECIMAL(14,4) NOT NULL DEFAULT 0,
        consumido TINYINT NOT NULL DEFAULT 0,
        INDEX idx_ofcon (id_of)"""),
    ("of_produccion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_of INT NOT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 0,
        lote VARCHAR(64) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ofprod (id_of)"""),
    # ── MRP-F · Costes ────────────────────────────────────────────────────────
    ("costes_fabricacion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        articulo_final VARCHAR(64) NOT NULL,
        coste_materiales DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_mano_obra DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_maquina DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_indirecto DECIMAL(14,4) NOT NULL DEFAULT 0,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cfab (id_empresa, articulo_final)"""),
    ("costes_of", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_of INT NOT NULL,
        coste_estimado DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_real DECIMAL(14,4) NOT NULL DEFAULT 0,
        desviacion DECIMAL(14,4) NOT NULL DEFAULT 0,
        detalle TEXT DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cof (id_empresa, id_of)"""),
    # ── MRP-G · Sugerencias del planificador ──────────────────────────────────
    ("mrp_sugerencias", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(12) NOT NULL,
        articulo VARCHAR(64) NOT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 0,
        origen VARCHAR(160) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_mrpsug (id_empresa, tipo, estado)"""),
    # ── CAL-A · Inspecciones ──────────────────────────────────────────────────
    ("tipos_inspeccion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        fase VARCHAR(16) NOT NULL DEFAULT 'recepcion',
        UNIQUE KEY uq_tinsp (id_empresa, codigo)"""),
    ("planes_inspeccion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        fase VARCHAR(16) NOT NULL DEFAULT 'recepcion',
        articulo VARCHAR(64) DEFAULT NULL,
        criterios TEXT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_plinsp (id_empresa, codigo)"""),
    ("inspecciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_plan INT DEFAULT NULL,
        fase VARCHAR(16) NOT NULL DEFAULT 'recepcion',
        articulo VARCHAR(64) DEFAULT NULL,
        id_lote INT DEFAULT NULL,
        id_of INT DEFAULT NULL,
        id_proveedor INT DEFAULT NULL,
        cantidad_inspeccionada DECIMAL(14,4) NOT NULL DEFAULT 0,
        cantidad_rechazada DECIMAL(14,4) NOT NULL DEFAULT 0,
        resultado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        inspector INT DEFAULT NULL,
        observaciones TEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_insp (id_empresa, fase, resultado)"""),
    # ── CAL-B · No conformidades ──────────────────────────────────────────────
    ("no_conformidades", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        origen VARCHAR(16) NOT NULL DEFAULT 'interna',
        descripcion VARCHAR(255) NOT NULL,
        severidad VARCHAR(10) NOT NULL DEFAULT 'media',
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        articulo VARCHAR(64) DEFAULT NULL,
        id_lote INT DEFAULT NULL,
        id_proveedor INT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        id_of INT DEFAULT NULL,
        id_inspeccion INT DEFAULT NULL,
        responsable INT DEFAULT NULL,
        fecha_apertura DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_cierre DATETIME DEFAULT NULL,
        INDEX idx_nc (id_empresa, estado, origen)"""),
    # ── CAL-C · CAPA ──────────────────────────────────────────────────────────
    ("acciones_correctivas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_nc INT DEFAULT NULL,
        tipo VARCHAR(12) NOT NULL DEFAULT 'correctiva',
        descripcion VARCHAR(255) NOT NULL,
        responsable INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        fecha_limite DATE DEFAULT NULL,
        fecha_cierre DATETIME DEFAULT NULL,
        eficacia VARCHAR(12) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_capa (id_empresa, tipo, estado)"""),
    # ── CAL-D · Auditorias de calidad ─────────────────────────────────────────
    ("auditorias_calidad", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        tipo VARCHAR(12) NOT NULL DEFAULT 'interna',
        alcance VARCHAR(255) DEFAULT NULL,
        id_proveedor INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'planificada',
        auditor INT DEFAULT NULL,
        fecha_plan DATE DEFAULT NULL,
        fecha_realizada DATE DEFAULT NULL,
        resultado VARCHAR(24) DEFAULT NULL,
        INDEX idx_audcal (id_empresa, tipo, estado)"""),
    ("hallazgos_auditoria", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_auditoria INT NOT NULL,
        descripcion VARCHAR(255) NOT NULL,
        severidad VARCHAR(10) NOT NULL DEFAULT 'media',
        id_nc INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'abierto',
        INDEX idx_hall (id_auditoria)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
