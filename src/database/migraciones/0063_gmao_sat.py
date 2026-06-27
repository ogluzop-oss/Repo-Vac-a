"""
Migracion 0063 — GMAO (mantenimiento de activos) + SAT/Helpdesk. ADITIVA, idempotente, reversible.

NO crea inventario paralelo: los repuestos se mueven por el KARDEX existente (movimientos_stock/lotes).
Reutiliza clientes/RRHH/correo/calendario/documentos. Multiempresa.
"""

VERSION = "0063"
DESCRIPCION = "GMAO (activos, planes, OT, costes) + SAT (tickets, SLA, colas, intervenciones, KB)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── GMAO-A · Activos ──────────────────────────────────────────────────────
    ("activos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'maquinaria',
        numero_serie VARCHAR(80) DEFAULT NULL,
        fabricante VARCHAR(120) DEFAULT NULL,
        modelo VARCHAR(120) DEFAULT NULL,
        ubicacion VARCHAR(160) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'operativo',
        criticidad VARCHAR(10) NOT NULL DEFAULT 'media',
        fecha_alta DATE DEFAULT NULL,
        fecha_compra DATE DEFAULT NULL,
        coste_adquisicion DECIMAL(14,2) NOT NULL DEFAULT 0,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_activo (id_empresa, codigo),
        INDEX idx_activo (id_empresa, tipo, estado)"""),
    ("activos_documentos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_activo INT NOT NULL,
        nombre VARCHAR(200) NOT NULL,
        ruta VARCHAR(512) DEFAULT NULL,
        id_documento INT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_actdoc (id_activo)"""),
    ("activos_garantias", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_activo INT NOT NULL,
        proveedor VARCHAR(160) DEFAULT NULL,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        cobertura VARCHAR(255) DEFAULT NULL,
        INDEX idx_actgar (id_activo)"""),
    ("activos_historial", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_activo INT NOT NULL,
        evento VARCHAR(40) NOT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        id_ot INT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_acthist (id_activo, fecha)"""),
    # ── GMAO-B · Planes preventivos ───────────────────────────────────────────
    ("planes_mantenimiento", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        id_activo INT DEFAULT NULL,
        frecuencia VARCHAR(16) NOT NULL DEFAULT 'mensual',
        intervalo_dias INT NOT NULL DEFAULT 30,
        proxima_fecha DATE DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_plan (id_empresa, codigo),
        INDEX idx_plan (id_empresa, activo, proxima_fecha)"""),
    ("planes_tareas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_plan INT NOT NULL,
        descripcion VARCHAR(255) NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        INDEX idx_plantarea (id_plan)"""),
    # ── GMAO-C · Ordenes de trabajo ───────────────────────────────────────────
    ("ordenes_trabajo", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        tipo VARCHAR(12) NOT NULL DEFAULT 'correctiva',
        id_activo INT DEFAULT NULL,
        id_plan INT DEFAULT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        prioridad VARCHAR(10) NOT NULL DEFAULT 'media',
        estado VARCHAR(12) NOT NULL DEFAULT 'borrador',
        tecnico INT DEFAULT NULL,
        id_almacen INT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_prevista DATE DEFAULT NULL,
        fecha_inicio DATETIME DEFAULT NULL,
        fecha_fin DATETIME DEFAULT NULL,
        INDEX idx_ot (id_empresa, estado, tipo)"""),
    ("ot_tareas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ot INT NOT NULL,
        descripcion VARCHAR(255) NOT NULL,
        completada TINYINT NOT NULL DEFAULT 0,
        INDEX idx_ottarea (id_ot)"""),
    ("ot_recursos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ot INT NOT NULL,
        tipo VARCHAR(12) NOT NULL DEFAULT 'repuesto',
        referencia VARCHAR(64) DEFAULT NULL,
        cantidad DECIMAL(14,4) NOT NULL DEFAULT 0,
        consumido TINYINT NOT NULL DEFAULT 0,
        reservado TINYINT NOT NULL DEFAULT 0,
        coste_unitario DECIMAL(14,4) NOT NULL DEFAULT 0,
        horas DECIMAL(10,2) NOT NULL DEFAULT 0,
        INDEX idx_otrec (id_ot)"""),
    ("costes_ot", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ot INT NOT NULL,
        coste_mano_obra DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_materiales DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_desplazamiento DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_externo DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_estimado DECIMAL(14,4) NOT NULL DEFAULT 0,
        coste_real DECIMAL(14,4) NOT NULL DEFAULT 0,
        desviacion DECIMAL(14,4) NOT NULL DEFAULT 0,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_costeot (id_empresa, id_ot)"""),
    # ── SAT-A · Tickets ───────────────────────────────────────────────────────
    ("tickets", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        asunto VARCHAR(200) NOT NULL,
        descripcion TEXT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        canal VARCHAR(12) NOT NULL DEFAULT 'manual',
        prioridad VARCHAR(10) NOT NULL DEFAULT 'media',
        estado VARCHAR(12) NOT NULL DEFAULT 'abierto',
        categoria VARCHAR(40) DEFAULT NULL,
        id_cola INT DEFAULT NULL,
        tecnico INT DEFAULT NULL,
        id_contrato INT DEFAULT NULL,
        sla_vencimiento DATETIME DEFAULT NULL,
        sla_incumplido TINYINT NOT NULL DEFAULT 0,
        email_origen VARCHAR(160) DEFAULT NULL,
        ref_correo INT DEFAULT NULL,
        satisfaccion INT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_primera_respuesta DATETIME DEFAULT NULL,
        fecha_resolucion DATETIME DEFAULT NULL,
        fecha_cierre DATETIME DEFAULT NULL,
        INDEX idx_ticket (id_empresa, estado, prioridad)"""),
    ("ticket_comentarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ticket INT NOT NULL,
        autor VARCHAR(80) DEFAULT NULL,
        es_cliente TINYINT NOT NULL DEFAULT 0,
        interno TINYINT NOT NULL DEFAULT 0,
        cuerpo TEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_tcom (id_ticket, fecha)"""),
    # ── SAT-B · Contratos / SLA ───────────────────────────────────────────────
    ("contratos_servicio", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_cliente INT DEFAULT NULL,
        codigo VARCHAR(40) DEFAULT NULL,
        cobertura VARCHAR(12) NOT NULL DEFAULT 'estandar',
        id_sla INT DEFAULT NULL,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        INDEX idx_contrato (id_empresa, id_cliente, activo)"""),
    ("sla_servicio", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        cobertura VARCHAR(12) NOT NULL DEFAULT 'estandar',
        horas_primera_respuesta INT NOT NULL DEFAULT 24,
        horas_resolucion INT NOT NULL DEFAULT 72,
        UNIQUE KEY uq_sla (id_empresa, codigo)"""),
    # ── SAT-C · Colas ─────────────────────────────────────────────────────────
    ("colas_soporte", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        auto_asignar TINYINT NOT NULL DEFAULT 0,
        responsable INT DEFAULT NULL,
        UNIQUE KEY uq_cola (id_empresa, codigo)"""),
    ("asignaciones_ticket", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ticket INT NOT NULL,
        tecnico INT DEFAULT NULL,
        modo VARCHAR(10) NOT NULL DEFAULT 'manual',
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_asigtk (id_ticket)"""),
    # ── SAT-D · Intervenciones ────────────────────────────────────────────────
    ("intervenciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_ticket INT DEFAULT NULL,
        id_ot INT DEFAULT NULL,
        tecnico INT DEFAULT NULL,
        tipo VARCHAR(12) NOT NULL DEFAULT 'visita',
        descripcion VARCHAR(255) DEFAULT NULL,
        horas DECIMAL(10,2) NOT NULL DEFAULT 0,
        ref_evento INT DEFAULT NULL,
        ref_actividad INT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_interv (id_empresa, id_ticket, id_ot)"""),
    ("partes_tecnicos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_intervencion INT NOT NULL,
        descripcion TEXT DEFAULT NULL,
        firmado TINYINT NOT NULL DEFAULT 0,
        ruta_pdf VARCHAR(512) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_parte (id_intervencion)"""),
    # ── SAT-E · Base de conocimiento ──────────────────────────────────────────
    ("kb_categorias", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        padre INT DEFAULT NULL,
        UNIQUE KEY uq_kbcat (id_empresa, nombre)"""),
    ("kb_articulos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_categoria INT DEFAULT NULL,
        titulo VARCHAR(200) NOT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        etiquetas VARCHAR(255) DEFAULT NULL,
        publicado TINYINT NOT NULL DEFAULT 0,
        version INT NOT NULL DEFAULT 1,
        vistas INT NOT NULL DEFAULT 0,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_kbart (id_empresa, publicado)"""),
    ("kb_versiones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_articulo INT NOT NULL,
        version INT NOT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        autor VARCHAR(80) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_kbver (id_articulo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
