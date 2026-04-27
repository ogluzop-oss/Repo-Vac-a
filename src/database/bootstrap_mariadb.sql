CREATE DATABASE IF NOT EXISTS smart_manager_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE smart_manager_db;

CREATE TABLE IF NOT EXISTS configuraciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre_empresa VARCHAR(255) NOT NULL DEFAULT 'SMART MANAGER AI',
    codigo_local VARCHAR(50) NOT NULL DEFAULT 'ALMC',
    email VARCHAR(255) NOT NULL DEFAULT 'info@smartmanagerai.local',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS almacen (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tiendas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    password VARCHAR(255) NOT NULL,
    perfil VARCHAR(50) NOT NULL,
    tienda_id VARCHAR(50) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_usuarios_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS articulos (
    codigo VARCHAR(50) PRIMARY KEY,
    nombre VARCHAR(255),
    descripcion TEXT,
    precio DECIMAL(10,2) DEFAULT 0.00,
    Stock_total INT DEFAULT 0,
    Stock_tienda INT DEFAULT 0,
    Stock_central INT DEFAULT 0,
    Stock_esperado INT DEFAULT 0,
    capacidad_lineal DECIMAL(10,2) DEFAULT 0,
    estado VARCHAR(20) DEFAULT 'activo',
    bloqueado TINYINT(1) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documentos_logisticos (
    id_documento VARCHAR(50) PRIMARY KEY,
    tipo_documento VARCHAR(30) NOT NULL DEFAULT 'TRASPASO',
    origen VARCHAR(100) NOT NULL,
    destino VARCHAR(100) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'EN TRANSITO',
    usuario_emisor VARCHAR(100),
    usuario_receptor VARCHAR(100),
    agencia VARCHAR(255),
    observaciones TEXT,
    resumen TEXT,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_envio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_recepcion DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documentos_logisticos_pales (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento VARCHAR(50) NOT NULL,
    id_pale VARCHAR(80) NOT NULL,
    id_visual VARCHAR(30) NOT NULL,
    peso_bulto DECIMAL(10,2) NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    usuario_receptor VARCHAR(100),
    fecha_recepcion DATETIME NULL,
    observaciones TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_documento_pale_visual (id_documento, id_visual),
    KEY idx_dlp_documento (id_documento),
    KEY idx_dlp_id_pale (id_pale),
    CONSTRAINT fk_dlp_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documentos_logisticos_lineas (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento VARCHAR(50) NOT NULL,
    id_pale VARCHAR(80) NOT NULL,
    id_visual VARCHAR(30) NOT NULL,
    codigo_articulo VARCHAR(50) NOT NULL,
    nombre_articulo VARCHAR(255) NOT NULL,
    cantidad_enviada INT NOT NULL DEFAULT 0,
    cantidad_recibida INT NOT NULL DEFAULT 0,
    estado_linea VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    peso_bulto DECIMAL(10,2) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_dll_documento (id_documento),
    KEY idx_dll_id_pale (id_pale),
    KEY idx_dll_codigo (codigo_articulo),
    CONSTRAINT fk_dll_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recepciones_logisticas (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento VARCHAR(50) NOT NULL,
    id_pale VARCHAR(80) NOT NULL,
    centro_receptor VARCHAR(100) NOT NULL,
    usuario_receptor VARCHAR(100) NOT NULL,
    total_lineas INT NOT NULL DEFAULT 0,
    total_unidades INT NOT NULL DEFAULT 0,
    incidencias TEXT,
    fecha_recepcion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_rl_documento (id_documento),
    KEY idx_rl_id_pale (id_pale),
    CONSTRAINT fk_rl_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS movimientos_stock (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    codigo_articulo VARCHAR(50) NOT NULL,
    tipo_movimiento VARCHAR(40) NOT NULL,
    cantidad INT NOT NULL DEFAULT 0,
    id_documento VARCHAR(50),
    id_pale VARCHAR(80),
    origen VARCHAR(100),
    destino VARCHAR(100),
    usuario VARCHAR(100),
    observaciones TEXT,
    fecha_movimiento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ms_codigo (codigo_articulo),
    KEY idx_ms_documento (id_documento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO configuraciones (id, nombre_empresa, codigo_local, email)
VALUES (1, 'SMART MANAGER AI', 'ALMC', 'info@smartmanagerai.local')
ON DUPLICATE KEY UPDATE
    nombre_empresa = VALUES(nombre_empresa),
    codigo_local = VALUES(codigo_local),
    email = VALUES(email);

CREATE TABLE IF NOT EXISTS auditoria_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(100),
    accion VARCHAR(255) NOT NULL,
    tabla_afectada VARCHAR(100),
    detalles TEXT,
    ip_origen VARCHAR(45),
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_auditoria_usuario (usuario),
    KEY idx_auditoria_fecha (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS configuracion_mapa (
    id INT AUTO_INCREMENT PRIMARY KEY,
    planta_index INT NOT NULL DEFAULT 0,
    ruta_imagen VARCHAR(500),
    matriz_binaria LONGBLOB,
    escala_px_metro DOUBLE DEFAULT 1.0,
    muros_vectoriales LONGTEXT,
    puntos_infraestructura LONGTEXT,
    ancla_x DOUBLE DEFAULT 0.0,
    ancla_y DOUBLE DEFAULT 0.0,
    fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_planta_index (planta_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ubicaciones (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    epc VARCHAR(100),
    codigo_articulo VARCHAR(50),
    pasillo VARCHAR(50),
    estanteria VARCHAR(50),
    balda VARCHAR(20),
    mapa_x DOUBLE DEFAULT 0,
    mapa_y DOUBLE DEFAULT 0,
    real_x DOUBLE DEFAULT 0,
    real_y DOUBLE DEFAULT 0,
    verificado TINYINT(1) DEFAULT 0,
    ubicacion_tienda VARCHAR(255),
    ubicacion_almacen VARCHAR(255),
    pasillo_almacen VARCHAR(50),
    estanteria_almacen VARCHAR(50),
    nivel_almacen VARCHAR(20),
    incidencia_ubicacion TINYINT(1) DEFAULT 0,
    ultima_incidencia DATETIME NULL,
    ultima_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_ubi_epc (epc),
    KEY idx_ubi_codigo (codigo_articulo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO almacen (nombre) VALUES
    ('ALMACÉN CENTRAL')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO tiendas (nombre) VALUES
    ('TIENDA 01'),
    ('TIENDA 02'),
    ('TIENDA 03')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO usuarios (nombre, password, perfil, tienda_id)
VALUES ('ADMIN', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'ADMINISTRADOR', 'ALMC')
ON DUPLICATE KEY UPDATE
    password = VALUES(password),
    perfil = VALUES(perfil),
    tienda_id = VALUES(tienda_id);
