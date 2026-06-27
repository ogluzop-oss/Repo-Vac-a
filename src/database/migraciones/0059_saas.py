"""
Migración 0059 — SaaS: licenciamiento, suscripciones, billing, multiempresa y branding.
ADITIVA, idempotente, reversible. NO toca tablas existentes (usuarios/empresas permanecen).

planes_saas/modulos_saas/plan_modulos (catálogo), empresa_licencia + historico/eventos,
suscripciones/facturas_saas/pagos_saas (billing), usuarios_empresas (multi-pertenencia),
empresa_branding. Multiempresa.
"""

VERSION = "0059"
DESCRIPCION = "SaaS: planes, licencias, suscripciones, billing, usuarios_empresas, branding"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("planes_saas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(30) NOT NULL,
        nombre VARCHAR(80) NOT NULL,
        precio_mensual DECIMAL(10,2) NOT NULL DEFAULT 0,
        max_empresas INT NOT NULL DEFAULT 1,
        max_tiendas INT NOT NULL DEFAULT 1,
        max_usuarios INT NOT NULL DEFAULT 3,
        max_almacenes INT NOT NULL DEFAULT 1,
        max_correos INT NOT NULL DEFAULT 3,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_plan (codigo)"""),
    ("modulos_saas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        UNIQUE KEY uq_modulo (codigo)"""),
    ("plan_modulos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_plan INT NOT NULL,
        codigo_modulo VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_plan_mod (id_plan, codigo_modulo)"""),
    ("empresa_licencia", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo_plan VARCHAR(30) NOT NULL DEFAULT 'BASIC',
        estado VARCHAR(12) NOT NULL DEFAULT 'activa',
        fecha_alta DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_baja DATETIME DEFAULT NULL,
        proximo_cobro DATE DEFAULT NULL,
        ultima_renovacion DATE DEFAULT NULL,
        UNIQUE KEY uq_emp_lic (id_empresa)"""),
    ("historico_licencias", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo_plan VARCHAR(30) NOT NULL,
        estado VARCHAR(12) NOT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        detalle VARCHAR(255) DEFAULT NULL,
        INDEX idx_histlic (id_empresa, fecha)"""),
    ("eventos_licencia", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        evento VARCHAR(30) NOT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evlic (id_empresa, evento)"""),
    ("suscripciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo_plan VARCHAR(30) NOT NULL,
        ciclo VARCHAR(12) NOT NULL DEFAULT 'mensual',
        estado VARCHAR(14) NOT NULL DEFAULT 'prueba',
        proveedor_pago VARCHAR(20) DEFAULT NULL,
        ref_externa VARCHAR(120) DEFAULT NULL,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        proximo_cobro DATE DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_susc (id_empresa, estado)"""),
    ("facturas_saas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_suscripcion INT DEFAULT NULL,
        numero VARCHAR(40) DEFAULT NULL,
        importe DECIMAL(10,2) NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'emitida',
        fecha DATE DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_facsaas (id_empresa, estado)"""),
    ("pagos_saas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_factura INT DEFAULT NULL,
        proveedor VARCHAR(20) DEFAULT NULL,
        importe DECIMAL(10,2) NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        ref_externa VARCHAR(120) DEFAULT NULL,
        intentos INT NOT NULL DEFAULT 0,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_pagosaas (id_empresa, estado)"""),
    ("usuarios_empresas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        rol VARCHAR(40) NOT NULL DEFAULT 'OPERARIO',
        tipo_relacion VARCHAR(20) NOT NULL DEFAULT 'empleado',
        estado VARCHAR(10) NOT NULL DEFAULT 'activo',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_user_emp (id_usuario, id_empresa),
        INDEX idx_uemp (id_empresa, estado)"""),
    ("empresa_branding", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        nombre_comercial VARCHAR(160) DEFAULT NULL,
        logo_ruta VARCHAR(512) DEFAULT NULL,
        color_primario VARCHAR(12) DEFAULT NULL,
        color_secundario VARCHAR(12) DEFAULT NULL,
        dominio VARCHAR(160) DEFAULT NULL,
        correo_principal VARCHAR(160) DEFAULT NULL,
        pie_documental VARCHAR(512) DEFAULT NULL,
        UNIQUE KEY uq_branding (id_empresa)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
