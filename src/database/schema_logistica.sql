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
