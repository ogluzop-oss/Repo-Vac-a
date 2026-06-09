-- ============================================================
-- SMART MANAGER — Bootstrap MariaDB
-- Una sola fuente de verdad. Seguro de ejecutar sobre BD existente.
-- CREATE TABLE IF NOT EXISTS  → no toca tablas existentes.
-- ALTER TABLE … ADD COLUMN IF NOT EXISTS → añade columnas faltantes.
-- DROP TABLE IF EXISTS (al final) → elimina tablas obsoletas sin datos.
-- ============================================================

CREATE DATABASE IF NOT EXISTS smart_manager_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE smart_manager_db;

-- ============================================================
-- 1. CONFIGURACIÓN GLOBAL DE LA EMPRESA
-- ============================================================
CREATE TABLE IF NOT EXISTS configuraciones (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nombre_empresa VARCHAR(255) NOT NULL DEFAULT 'SMART MANAGER',
    codigo_local   VARCHAR(50)  NOT NULL DEFAULT 'ALMC',
    email          VARCHAR(255)          DEFAULT 'info@smartmanagerai.local',
    moneda         VARCHAR(3)   NOT NULL DEFAULT 'EUR'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2. CENTROS LOGÍSTICOS
-- ============================================================
CREATE TABLE IF NOT EXISTS almacen (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo TINYINT(1)   NOT NULL DEFAULT 1,
    -- Multiempresa: todo almacén pertenece a una empresa, con código y tipo.
    -- tipo_almacen: central | regional | tienda | logistico | temporal
    id_empresa     CHAR(36)    NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    codigo_almacen VARCHAR(20) NOT NULL DEFAULT '',
    tipo_almacen   VARCHAR(30) NOT NULL DEFAULT 'central',
    estado         VARCHAR(20) NOT NULL DEFAULT 'activo',
    fecha_creacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tiendas (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo TINYINT(1)   NOT NULL DEFAULT 1,
    -- Multiempresa (multi-tenant): toda tienda pertenece a una empresa.
    id_empresa    CHAR(36)    NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    codigo_tienda VARCHAR(20) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 1b. EMPRESAS (entidad RAÍZ del modelo multiempresa / multi-tenant)
-- ============================================================
CREATE TABLE IF NOT EXISTS empresas (
    id_empresa          CHAR(36)     NOT NULL PRIMARY KEY,
    codigo_empresa      VARCHAR(20)  NOT NULL UNIQUE,
    nombre_empresa      VARCHAR(255) NOT NULL DEFAULT 'SMART MANAGER',
    razon_social        VARCHAR(255)          DEFAULT NULL,
    cif_nif             VARCHAR(50)           DEFAULT NULL,
    direccion_fiscal    VARCHAR(255)          DEFAULT NULL,
    telefono            VARCHAR(50)           DEFAULT NULL,
    email_principal     VARCHAR(255)          DEFAULT NULL,
    estado              VARCHAR(20)  NOT NULL DEFAULT 'activa',
    plan_licencia       VARCHAR(50)  NOT NULL DEFAULT 'base',
    fecha_alta          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO empresas (id_empresa, codigo_empresa, nombre_empresa)
VALUES ('00000000-0000-0000-0000-000000000001', 'EMP-001', 'SMART MANAGER');

-- ============================================================
-- 3. USUARIOS Y ACCESO
-- ============================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    nombre    VARCHAR(120) NOT NULL UNIQUE,
    password  VARCHAR(255) NOT NULL,
    perfil    VARCHAR(50)  NOT NULL,
    tienda_id VARCHAR(50)  NULL,
    activo    TINYINT(1)   NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4. CATÁLOGO DE ARTÍCULOS Y STOCK
-- ============================================================
CREATE TABLE IF NOT EXISTS articulos (
    codigo              VARCHAR(50)    PRIMARY KEY,
    nombre              VARCHAR(255),
    descripcion         TEXT,
    categoria           VARCHAR(100),
    seccion             VARCHAR(100),
    precio              DECIMAL(10,2)  DEFAULT 0.00,
    Stock_total         INT            DEFAULT 0,
    Stock_tienda        INT            DEFAULT 0,
    Stock_central       INT            DEFAULT 0,
    Stock_esperado      INT            DEFAULT 0,
    capacidad_lineal    DECIMAL(10,2)  DEFAULT 0,
    ubicacion_tienda    VARCHAR(255),
    ubicacion_almacen   VARCHAR(255),
    bloqueado           TINYINT(1)     DEFAULT 0,
    estado              VARCHAR(20)    DEFAULT 'activo',
    promo_activa        TINYINT(1)     DEFAULT 0,
    precio_promo        DECIMAL(10,2)  DEFAULT 0.00,
    promo_fin           VARCHAR(50),
    imagen              VARCHAR(500),
    ultima_recepcion    VARCHAR(50),
    siguiente_recepcion VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5. VENTAS / TPV
-- ============================================================
CREATE TABLE IF NOT EXISTS ventas (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    fecha       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total       DECIMAL(10,2)          DEFAULT 0.00,
    forma_pago  VARCHAR(30)            DEFAULT 'efectivo',
    empleado    VARCHAR(100)           NULL,
    numero_caja INT                    NULL DEFAULT 1,
    -- columnas de compatibilidad para ventas simples de un artículo
    codigo      VARCHAR(50)            NULL,
    cantidad    INT                    NULL DEFAULT 0,
    KEY idx_v_fecha  (fecha),
    KEY idx_v_codigo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS venta_items (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    venta_id        INT            NOT NULL,
    codigo_articulo VARCHAR(50)    NOT NULL,
    nombre          VARCHAR(255),
    seccion         VARCHAR(100),
    cantidad        INT            NOT NULL DEFAULT 1,
    precio_unitario DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    subtotal        DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    KEY idx_vi_venta   (venta_id),
    KEY idx_vi_codigo  (codigo_articulo),
    KEY idx_vi_seccion (seccion),
    CONSTRAINT fk_vi_venta FOREIGN KEY (venta_id)
        REFERENCES ventas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5b. ERRORES DE SINCRONIZACIÓN DE VENTAS
-- ============================================================
CREATE TABLE IF NOT EXISTS ventas_errores (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    codigo   VARCHAR(50),
    cantidad INT,
    fecha    DATETIME,
    motivo   TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 6. LOG DE FACTURACIÓN DIARIA (registro de exportes PDF)
-- ============================================================
CREATE TABLE IF NOT EXISTS facturacion_diaria_log (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    fecha             DATE          NOT NULL,
    empresa           VARCHAR(255),
    tienda            VARCHAR(100),
    responsable       VARCHAR(100),
    total_efectivo    DECIMAL(10,2) DEFAULT 0.00,
    total_tarjeta     DECIMAL(10,2) DEFAULT 0.00,
    total             DECIMAL(10,2) DEFAULT 0.00,
    ruta_pdf          VARCHAR(500),
    fecha_exportacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_fdl_fecha (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 6b. PREVISIÓN — Histórico de facturación importado + real
-- ============================================================
CREATE TABLE IF NOT EXISTS prevision_historico (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    fecha           DATE          NOT NULL,
    total_facturado DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    fuente          VARCHAR(20)            DEFAULT 'IMPORTADO',
    dia_semana      TINYINT                DEFAULT NULL,
    es_festivo      TINYINT(1)             DEFAULT 0,
    UNIQUE KEY uk_ph_fecha_fuente (fecha, fuente),
    KEY idx_ph_fecha (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 6c. PREVISIÓN — Objetivos y previsiones por año
-- ============================================================
CREATE TABLE IF NOT EXISTS prevision_objetivos (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    anio             INT            NOT NULL,
    objetivo_anual   DECIMAL(12,2)          DEFAULT 0.00,
    calculado_ia     DECIMAL(12,2)          DEFAULT 0.00,
    excel_generado   TINYINT(1)             DEFAULT 0,
    ruta_excel_drive VARCHAR(500),
    UNIQUE KEY uk_po_anio (anio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 7. LOGÍSTICA — Documentos de traspaso
-- ============================================================
CREATE TABLE IF NOT EXISTS documentos_logisticos (
    id_documento     VARCHAR(50)  PRIMARY KEY,
    tipo_documento   VARCHAR(30)  NOT NULL DEFAULT 'TRASPASO',
    origen           VARCHAR(100) NOT NULL,
    destino          VARCHAR(100) NOT NULL,
    estado           VARCHAR(30)  NOT NULL DEFAULT 'EN TRANSITO',
    usuario_emisor   VARCHAR(100),
    usuario_receptor VARCHAR(100),
    agencia          VARCHAR(255),
    observaciones    TEXT,
    resumen          TEXT,
    fecha_creacion   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_envio      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_recepcion  DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documentos_logisticos_pales (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento     VARCHAR(50) NOT NULL,
    id_pale          VARCHAR(80) NOT NULL,
    id_visual        VARCHAR(30) NOT NULL,
    peso_bulto       DECIMAL(10,2) NULL,
    estado           VARCHAR(30)   NOT NULL DEFAULT 'PENDIENTE',
    usuario_receptor VARCHAR(100),
    fecha_recepcion  DATETIME NULL,
    observaciones    TEXT,
    UNIQUE KEY uk_documento_pale_visual (id_documento, id_visual),
    KEY idx_dlp_documento (id_documento),
    CONSTRAINT fk_dlp_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documentos_logisticos_lineas (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento      VARCHAR(50)  NOT NULL,
    id_pale           VARCHAR(80)  NOT NULL,
    id_visual         VARCHAR(30)  NOT NULL,
    codigo_articulo   VARCHAR(50)  NOT NULL,
    nombre_articulo   VARCHAR(255) NOT NULL,
    cantidad_enviada  INT NOT NULL DEFAULT 0,
    cantidad_recibida INT NOT NULL DEFAULT 0,
    estado_linea      VARCHAR(30)  NOT NULL DEFAULT 'PENDIENTE',
    peso_bulto        DECIMAL(10,2) NULL,
    KEY idx_dll_documento (id_documento),
    KEY idx_dll_codigo    (codigo_articulo),
    CONSTRAINT fk_dll_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recepciones_logisticas (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento     VARCHAR(50)  NOT NULL,
    id_pale          VARCHAR(80)  NOT NULL,
    centro_receptor  VARCHAR(100) NOT NULL,
    usuario_receptor VARCHAR(100) NOT NULL,
    total_lineas     INT NOT NULL DEFAULT 0,
    total_unidades   INT NOT NULL DEFAULT 0,
    incidencias      TEXT,
    fecha_recepcion  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_rl_documento (id_documento),
    CONSTRAINT fk_rl_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 7b. LOGÍSTICA — Incidencias
-- ============================================================
CREATE TABLE IF NOT EXISTS incidencias_logisticas (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_documento      VARCHAR(50)  NOT NULL,
    id_pale           VARCHAR(80)  DEFAULT NULL,
    codigo_articulo   VARCHAR(50)  DEFAULT NULL,
    tipo              VARCHAR(60)  NOT NULL DEFAULT 'ROTURA',
    descripcion       TEXT,
    cantidad_afectada INT          NOT NULL DEFAULT 0,
    usuario           VARCHAR(100) NOT NULL,
    estado            VARCHAR(20)  NOT NULL DEFAULT 'ABIERTA',
    fecha_creacion    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre      DATETIME     NULL,
    KEY idx_il_documento (id_documento),
    KEY idx_il_estado    (estado),
    CONSTRAINT fk_il_documento
        FOREIGN KEY (id_documento) REFERENCES documentos_logisticos(id_documento)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS movimientos_stock (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    codigo_articulo  VARCHAR(50)  NOT NULL,
    tipo_movimiento  VARCHAR(40)  NOT NULL,
    cantidad         INT          NOT NULL DEFAULT 0,
    id_documento     VARCHAR(50),
    id_pale          VARCHAR(80),
    origen           VARCHAR(100),
    destino          VARCHAR(100),
    usuario          VARCHAR(100),
    observaciones    TEXT,
    fecha_movimiento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ms_codigo    (codigo_articulo),
    KEY idx_ms_documento (id_documento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 8. MAPA DE PLANTA / GPS INTERNO
-- ============================================================
CREATE TABLE IF NOT EXISTS configuracion_mapa (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    planta_index           INT          NOT NULL DEFAULT 0,
    ruta_imagen            VARCHAR(500),
    titulo_plano           VARCHAR(255)          DEFAULT NULL,
    tipo                   VARCHAR(20)           DEFAULT 'LOCAL',
    altura_metros          DOUBLE                DEFAULT NULL,
    matriz_binaria         LONGBLOB,
    escala_px_metro        DOUBLE                DEFAULT 0.0,
    muros_vectoriales      LONGTEXT,
    puntos_infraestructura LONGTEXT,
    ancla_x                DOUBLE                DEFAULT 0.0,
    ancla_y                DOUBLE                DEFAULT 0.0,
    fecha_actualizacion    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_planta_index (planta_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ubicaciones (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    epc                   VARCHAR(100)  DEFAULT NULL,
    codigo_articulo       VARCHAR(50)   DEFAULT NULL,
    pasillo               VARCHAR(50)   DEFAULT NULL,
    estanteria            VARCHAR(50)   DEFAULT NULL,
    balda                 VARCHAR(20)   DEFAULT NULL,
    mapa_x                DOUBLE        DEFAULT 0,
    mapa_y                DOUBLE        DEFAULT 0,
    real_x                DOUBLE        DEFAULT 0,
    real_y                DOUBLE        DEFAULT 0,
    verificado            TINYINT(1)    DEFAULT 0,
    ubicacion_tienda      VARCHAR(255)  DEFAULT NULL,
    ubicacion_almacen     VARCHAR(255)  DEFAULT NULL,
    pasillo_almacen       VARCHAR(50)   DEFAULT NULL,
    estanteria_almacen    VARCHAR(50)   DEFAULT NULL,
    nivel_almacen         VARCHAR(20)   DEFAULT NULL,
    incidencia_ubicacion  TINYINT(1)    DEFAULT 0,
    ultima_incidencia     DATETIME      NULL,
    ultima_actualizacion  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    -- epc is unique per physical RFID device/marker
    UNIQUE KEY uk_ubi_epc    (epc),
    KEY idx_ubi_codigo (codigo_articulo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 9. ETIQUETAS DE PRECIO
-- ============================================================
CREATE TABLE IF NOT EXISTS etiquetas (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    codigo        VARCHAR(50)    NOT NULL,
    nombre        VARCHAR(255),
    precio_actual DECIMAL(10,2)  DEFAULT 0.00,
    nuevo_precio  DECIMAL(10,2)  DEFAULT 0.00,
    fecha         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_et_codigo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 10. MERMAS (bajas / pérdidas de stock)
-- ============================================================
CREATE TABLE IF NOT EXISTS mermas (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    codigo   VARCHAR(50) NOT NULL,
    cantidad INT         NOT NULL DEFAULT 0,
    motivo   TEXT,
    fecha    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mer_codigo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 11. PEDIDOS
-- ============================================================
CREATE TABLE IF NOT EXISTS pedidos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pale_codigo VARCHAR(100) NOT NULL,
    items       TEXT,
    procesado   TINYINT(1)   NOT NULL DEFAULT 0,
    fecha       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 12. FICHAJES (control de asistencia / jornada laboral)
-- ============================================================
CREATE TABLE IF NOT EXISTS fichajes (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id        INT            NOT NULL,
    nombre_empleado   VARCHAR(120)   NOT NULL,
    entrada           DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    salida            DATETIME       NULL,
    duracion_segundos INT            NULL,
    KEY idx_fich_usuario (usuario_id),
    KEY idx_fich_entrada (entrada)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 13. REABASTECIMIENTO INTELIGENTE
-- ============================================================
CREATE TABLE IF NOT EXISTS reab_config (
    codigo         VARCHAR(50)  PRIMARY KEY,
    umbral_min     INT          NOT NULL DEFAULT 5,
    stock_objetivo INT          NOT NULL DEFAULT 20,
    origen         VARCHAR(50)  NOT NULL DEFAULT 'ALMACÉN CENTRAL',
    automatico     TINYINT(1)   NOT NULL DEFAULT 1,
    CONSTRAINT fk_reab_cfg_art FOREIGN KEY (codigo)
        REFERENCES articulos(codigo) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS reab_propuestas (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    codigo          VARCHAR(50)   NOT NULL,
    nombre_articulo VARCHAR(255)  NOT NULL,
    cantidad        INT           NOT NULL DEFAULT 0,
    origen          VARCHAR(50)   NOT NULL DEFAULT 'ALMACÉN CENTRAL',
    stock_actual    INT           NOT NULL DEFAULT 0,
    stock_objetivo  INT           NOT NULL DEFAULT 0,
    estado          VARCHAR(20)   NOT NULL DEFAULT 'pendiente',
    fecha_creacion  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_accion    DATETIME      NULL,
    KEY idx_rp_codigo (codigo),
    KEY idx_rp_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 14. PROGRAMACIÓN DE ENVÍOS AUTOMÁTICOS
-- ============================================================
CREATE TABLE IF NOT EXISTS reab_schedule (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    email        VARCHAR(255) NOT NULL DEFAULT '',
    dias         VARCHAR(20)  NOT NULL DEFAULT '',
    hora         TINYINT      NOT NULL DEFAULT 8,
    minuto       TINYINT      NOT NULL DEFAULT 0,
    ultima_envio DATE         NULL,
    smtp_user    VARCHAR(255) NOT NULL DEFAULT '',
    smtp_pass    VARCHAR(255) NOT NULL DEFAULT '',
    updated_at   DATETIME     DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE reab_schedule ADD COLUMN IF NOT EXISTS smtp_user VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE reab_schedule ADD COLUMN IF NOT EXISTS smtp_pass VARCHAR(255) NOT NULL DEFAULT '';

-- ============================================================
-- 15. AUDITORÍA
-- ============================================================
CREATE TABLE IF NOT EXISTS auditoria_logs (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario        VARCHAR(100),
    accion         VARCHAR(255) NOT NULL,
    tabla_afectada VARCHAR(100),
    detalles       TEXT,
    ip_origen      VARCHAR(45),
    fecha          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_usuario (usuario),
    KEY idx_audit_fecha   (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 16. TPV ENTERPRISE — VENTA A GRANEL (BÁSCULA)
-- ============================================================
CREATE TABLE IF NOT EXISTS productos_granel (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    nombre               VARCHAR(255)   NOT NULL,
    precio_kg            DECIMAL(10,3)  NOT NULL DEFAULT 0.000,
    emoji                VARCHAR(10)    DEFAULT '🛒',
    categoria            VARCHAR(100)   DEFAULT 'GENERAL',
    codigo_interno       VARCHAR(50),
    activo               TINYINT(1)     NOT NULL DEFAULT 1,
    ultima_actualizacion DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_pg_activo (activo),
    KEY idx_pg_cat    (categoria)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 17. TPV ENTERPRISE — DEVOLUCIONES
-- ============================================================
CREATE TABLE IF NOT EXISTS devoluciones (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    fecha                 DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    venta_original_id     INT,
    total_reembolso       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    forma_reembolso       VARCHAR(30)   NOT NULL DEFAULT 'efectivo',
    forma_pago_original   VARCHAR(30),
    empleado              VARCHAR(100),
    numero_caja           INT,
    motivo                VARCHAR(500),
    autorizado_por        VARCHAR(100),
    requirio_autorizacion TINYINT(1)    DEFAULT 0,
    estado                VARCHAR(30)   DEFAULT 'COMPLETADA',
    observaciones         TEXT,
    KEY idx_dev_fecha (fecha),
    KEY idx_dev_venta (venta_original_id),
    CONSTRAINT fk_dev_venta FOREIGN KEY (venta_original_id)
        REFERENCES ventas(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS devolucion_items (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    devolucion_id   INT            NOT NULL,
    codigo_articulo VARCHAR(50)    NOT NULL DEFAULT 'GRANEL',
    nombre          VARCHAR(255),
    cantidad        DECIMAL(10,3)  NOT NULL DEFAULT 1.000,
    precio_unitario DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    subtotal        DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    KEY idx_di_dev (devolucion_id),
    CONSTRAINT fk_di_dev FOREIGN KEY (devolucion_id)
        REFERENCES devoluciones(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Extend venta_items for bulk/weight sales (idempotent)
ALTER TABLE venta_items
    ADD COLUMN IF NOT EXISTS peso_vendido DECIMAL(10,3) DEFAULT 0.000,
    ADD COLUMN IF NOT EXISTS precio_kg    DECIMAL(10,3) DEFAULT 0.000,
    ADD COLUMN IF NOT EXISTS modo_venta   VARCHAR(20)   DEFAULT 'UNIDAD';

-- Extend articulos for granel support (idempotent)
ALTER TABLE articulos
    ADD COLUMN IF NOT EXISTS es_granel TINYINT(1)    DEFAULT 0,
    ADD COLUMN IF NOT EXISTS precio_kg DECIMAL(10,3) DEFAULT 0.000;

-- Configurable return window (días) for devoluciones (idempotent)
ALTER TABLE configuraciones
    ADD COLUMN IF NOT EXISTS plazo_devoluciones_dias INT DEFAULT 30;

-- Prevent duplicate granel products on repeated seeding (idempotent)
ALTER TABLE productos_granel
    ADD UNIQUE INDEX IF NOT EXISTS uniq_pg_nombre (nombre);

-- ============================================================
-- DATOS INICIALES (idempotentes)
-- ============================================================
INSERT INTO configuraciones (id, nombre_empresa, codigo_local, email)
VALUES (1, 'SMART MANAGER', 'ALMC', 'info@smartmanagerai.local')
ON DUPLICATE KEY UPDATE
    nombre_empresa = VALUES(nombre_empresa),
    codigo_local   = VALUES(codigo_local),
    email          = VALUES(email);

INSERT INTO almacen (nombre) VALUES ('ALMACÉN CENTRAL')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO tiendas (nombre) VALUES ('TIENDA 01'), ('TIENDA 02'), ('TIENDA 03')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO usuarios (nombre, password, perfil, tienda_id)
VALUES ('ADMIN', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'ADMINISTRADOR', 'ALMC')
ON DUPLICATE KEY UPDATE perfil = VALUES(perfil), tienda_id = VALUES(tienda_id);

-- Productos granel por defecto
INSERT IGNORE INTO productos_granel (nombre, precio_kg, emoji, categoria) VALUES
    ('Manzana Golden',    2.49, '🍎', 'FRUTA'),
    ('Plátano',           1.89, '🍌', 'FRUTA'),
    ('Naranja',           1.29, '🍊', 'FRUTA'),
    ('Pera Conference',   2.09, '🍐', 'FRUTA'),
    ('Uva Blanca',        3.49, '🍇', 'FRUTA'),
    ('Tomate Rama',       2.19, '🍅', 'VERDURA'),
    ('Patata',            0.89, '🥔', 'VERDURA'),
    ('Cebolla',           0.99, '🧅', 'VERDURA'),
    ('Zanahoria',         0.79, '🥕', 'VERDURA'),
    ('Pimiento Rojo',     2.49, '🫑', 'VERDURA'),
    ('Almendra Cruda',   12.99, '🌰', 'FRUTOS SECOS'),
    ('Nuez',             14.99, '🥜', 'FRUTOS SECOS'),
    ('Pistacho',         18.99, '🫘', 'FRUTOS SECOS'),
    ('Gominola Surtida',  8.99, '🍬', 'DULCES'),
    ('Chocolate Granel',  9.99, '🍫', 'DULCES'),
    ('Palomitas Caramel', 6.99, '🍿', 'DULCES'),
    ('Queso Manchego',   16.50, '🧀', 'FRESCOS'),
    ('Jamón Serrano',    22.90, '🥩', 'FRESCOS');

-- ============================================================
-- MIGRACIONES — añade columnas faltantes en tablas pre-existentes
-- Seguro de ejecutar N veces (ADD COLUMN IF NOT EXISTS).
-- ============================================================

-- articulos: columnas añadidas tras la creación inicial
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS categoria           VARCHAR(100);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS seccion             VARCHAR(100);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS ubicacion_tienda    VARCHAR(255);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS ubicacion_almacen   VARCHAR(255);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS promo_activa        TINYINT(1)     DEFAULT 0;
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS precio_promo        DECIMAL(10,2)  DEFAULT 0.00;
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS promo_fin           VARCHAR(50);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS imagen              VARCHAR(500);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS ultima_recepcion    VARCHAR(50);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS siguiente_recepcion VARCHAR(50);
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS Stock_central       INT            DEFAULT 0;
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS Stock_esperado      INT            DEFAULT 0;
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS capacidad_lineal    DECIMAL(10,2)  DEFAULT 0;
ALTER TABLE articulos ADD COLUMN IF NOT EXISTS bloqueado           TINYINT(1)     DEFAULT 0;

-- ubicaciones: columnas de coordenadas de mapa y RFID
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS mapa_x               DOUBLE      DEFAULT 0;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS mapa_y               DOUBLE      DEFAULT 0;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS real_x               DOUBLE      DEFAULT 0;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS real_y               DOUBLE      DEFAULT 0;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS epc                  VARCHAR(100) DEFAULT NULL;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS pasillo              VARCHAR(50)  DEFAULT NULL;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS estanteria           VARCHAR(50)  DEFAULT NULL;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS verificado           TINYINT(1)   DEFAULT 0;
ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS fecha_actualizacion  DATETIME     NULL;
-- Ensure all nullable columns have explicit DEFAULT NULL (fixes strict-mode INSERT errors)
ALTER TABLE ubicaciones MODIFY COLUMN codigo_articulo VARCHAR(50)  DEFAULT NULL;
ALTER TABLE ubicaciones MODIFY COLUMN epc             VARCHAR(100) DEFAULT NULL;
ALTER TABLE ubicaciones MODIFY COLUMN balda           VARCHAR(20)  DEFAULT NULL;
-- Remove duplicate EPC rows keeping the latest, then add UNIQUE constraint for ON DUPLICATE KEY
SET FOREIGN_KEY_CHECKS=0;
DELETE u1 FROM ubicaciones u1
    INNER JOIN ubicaciones u2
    WHERE u1.id < u2.id AND u1.epc IS NOT NULL AND u1.epc = u2.epc;
SET FOREIGN_KEY_CHECKS=1;
ALTER TABLE ubicaciones ADD UNIQUE KEY IF NOT EXISTS uk_ubi_epc (epc);

-- etiquetas: upgrade non-unique index to UNIQUE for ON DUPLICATE KEY UPDATE support
ALTER TABLE etiquetas DROP INDEX IF EXISTS idx_et_codigo;
ALTER TABLE etiquetas ADD UNIQUE KEY IF NOT EXISTS uk_et_codigo (codigo);

-- venta_items: sección para analytics
ALTER TABLE venta_items ADD COLUMN IF NOT EXISTS seccion VARCHAR(100);
ALTER TABLE venta_items ADD COLUMN IF NOT EXISTS nombre  VARCHAR(255);

-- ventas: compatibilidad con código de artículo único
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS numero_caja INT NULL DEFAULT 1;
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS empleado    VARCHAR(100) NULL;
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS codigo      VARCHAR(50)  NULL;
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS cantidad    INT          NULL DEFAULT 0;

-- configuracion_mapa: columnas añadidas para GPS y previsión
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS muros_vectoriales      LONGTEXT;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS puntos_infraestructura LONGTEXT;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS matriz_binaria         LONGBLOB;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS altura_metros          DOUBLE DEFAULT NULL;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS titulo_plano           VARCHAR(255) DEFAULT NULL;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS tipo                   VARCHAR(20) DEFAULT 'LOCAL';
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS ancla_x               DOUBLE DEFAULT 0.0;
ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS ancla_y               DOUBLE DEFAULT 0.0;

-- ============================================================
-- LIMPIEZA — elimina tablas obsoletas (sin datos útiles)
-- ============================================================
DROP TABLE IF EXISTS pale_items;
DROP TABLE IF EXISTS ventas_items;
DROP TABLE IF EXISTS facturas;
DROP TABLE IF EXISTS historial_logistico;
DROP TABLE IF EXISTS movimientos_detalle;
