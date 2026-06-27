"""
Migración 0057 — Integraciones y Comunicaciones empresariales. ADITIVA, idempotente, reversible.

Modelo completo (multiempresa) de: notificaciones, scheduler, correo recibido + plantillas,
mensajería interna, tareas empresariales, calendario y webhooks salientes. NO toca ninguna
tabla existente (correo_corporativos, pagos_webhooks_log, etc. permanecen intactas).
"""

VERSION = "0057"
DESCRIPCION = "Comunicaciones: notificaciones, scheduler, correo rx, plantillas, mensajería, tareas, calendario, webhooks salientes"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("notificaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(40) NOT NULL DEFAULT 'info',
        modulo VARCHAR(40) DEFAULT NULL,
        titulo VARCHAR(160) NOT NULL,
        mensaje TEXT DEFAULT NULL,
        prioridad VARCHAR(10) NOT NULL DEFAULT 'normal',
        ref_entidad VARCHAR(40) DEFAULT NULL,
        ref_id VARCHAR(64) DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_notif_emp (id_empresa, fecha_creacion)"""),
    ("notificaciones_destinatarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_notificacion INT NOT NULL,
        usuario_destino INT DEFAULT NULL,
        rol_destino VARCHAR(40) DEFAULT NULL,
        estado VARCHAR(10) NOT NULL DEFAULT 'pendiente',
        INDEX idx_notifd (id_empresa, usuario_destino, estado),
        INDEX idx_notifd_n (id_notificacion)"""),
    ("notificaciones_lecturas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_notificacion INT NOT NULL,
        usuario INT NOT NULL,
        fecha_lectura DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_notif_lec (id_notificacion, usuario)"""),
    ("scheduler_jobs", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) NOT NULL,
        descripcion VARCHAR(160) DEFAULT NULL,
        intervalo_horas INT NOT NULL DEFAULT 24,
        proxima_ejecucion DATETIME DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        ultima_ejecucion DATETIME DEFAULT NULL,
        UNIQUE KEY uq_job (id_empresa, codigo)"""),
    ("scheduler_historial", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'ok',
        detalle VARCHAR(255) DEFAULT NULL,
        intentos INT NOT NULL DEFAULT 1,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_schist (codigo, fecha)"""),
    ("correos_recibidos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_correo VARCHAR(64) DEFAULT NULL,
        remitente VARCHAR(255) DEFAULT NULL,
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        message_id VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT NULL,
        leido TINYINT NOT NULL DEFAULT 0,
        fecha_descarga DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_corr_rx (id_empresa, id_correo, message_id),
        INDEX idx_corr_rx (id_empresa, leido)"""),
    ("correos_adjuntos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_correo_recibido INT NOT NULL,
        nombre VARCHAR(255) DEFAULT NULL,
        ruta VARCHAR(512) DEFAULT NULL,
        descargado TINYINT NOT NULL DEFAULT 0,
        INDEX idx_corr_adj (id_correo_recibido)"""),
    ("plantillas_correo", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        tipo VARCHAR(30) NOT NULL DEFAULT 'general',
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_plantilla (id_empresa, codigo)"""),
    ("conversaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        asunto VARCHAR(160) DEFAULT NULL,
        alcance VARCHAR(16) NOT NULL DEFAULT 'usuario',
        ambito_id VARCHAR(40) DEFAULT NULL,
        creado_por INT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        estado VARCHAR(12) NOT NULL DEFAULT 'activa',
        INDEX idx_conv (id_empresa, estado)"""),
    ("conversaciones_participantes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_conversacion INT NOT NULL,
        usuario INT NOT NULL,
        UNIQUE KEY uq_conv_part (id_conversacion, usuario)"""),
    ("mensajes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_conversacion INT NOT NULL,
        emisor INT DEFAULT NULL,
        cuerpo TEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_msg (id_conversacion, fecha)"""),
    ("tareas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        titulo VARCHAR(160) NOT NULL,
        descripcion TEXT DEFAULT NULL,
        asignado_a INT DEFAULT NULL,
        creado_por INT DEFAULT NULL,
        prioridad VARCHAR(10) NOT NULL DEFAULT 'normal',
        estado VARCHAR(14) NOT NULL DEFAULT 'pendiente',
        vencimiento DATE DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_cierre DATETIME DEFAULT NULL,
        INDEX idx_tarea (id_empresa, asignado_a, estado)"""),
    ("tareas_comentarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tarea INT NOT NULL,
        usuario INT DEFAULT NULL,
        comentario TEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_tarea_com (id_tarea)"""),
    ("calendario_eventos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        titulo VARCHAR(160) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'evento',
        inicio DATETIME NOT NULL,
        fin DATETIME DEFAULT NULL,
        descripcion TEXT DEFAULT NULL,
        creado_por INT DEFAULT NULL,
        ref_entidad VARCHAR(40) DEFAULT NULL,
        ref_id VARCHAR(64) DEFAULT NULL,
        INDEX idx_cal (id_empresa, inicio)"""),
    ("calendario_participantes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_evento INT NOT NULL,
        usuario INT NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'invitado',
        UNIQUE KEY uq_cal_part (id_evento, usuario)"""),
    ("webhooks_suscripciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        evento VARCHAR(40) NOT NULL,
        url VARCHAR(512) NOT NULL,
        secreto VARCHAR(128) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_whsub (id_empresa, evento, activo)"""),
    ("webhooks_historial", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_suscripcion INT DEFAULT NULL,
        evento VARCHAR(40) NOT NULL,
        url VARCHAR(512) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        codigo_http INT DEFAULT NULL,
        intentos INT NOT NULL DEFAULT 0,
        payload MEDIUMTEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_whhist (id_empresa, evento)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
