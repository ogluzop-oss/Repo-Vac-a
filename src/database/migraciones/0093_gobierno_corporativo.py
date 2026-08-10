"""
Migracion 0093 — Gobierno Corporativo (Paquete Enterprise 7). ADITIVA, idempotente, reversible.
NO toca ninguna tabla existente ni crea motores nuevos: modela la ORGANIZACION (organigrama,
responsables, delegaciones temporales, cadenas de aprobacion, politicas heredables y escalados).
Las aprobaciones/escalados reutilizan Workflow/AutomationService/Auditoria. Multiempresa/multitienda.

Rendimiento (SUBFASE 7.12): `org_nodos` usa RUTA MATERIALIZADA + nivel para consultas jerarquicas
eficientes (subarbol via `ruta LIKE '/x/%'`), sin recorrer toda la jerarquia.
"""

VERSION = "0093"
DESCRIPCION = "Gobierno: org_nodos, org_responsables, org_delegaciones, org_aprobacion_reglas, org_politicas, org_escalados"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("org_nodos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(20) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        padre_id BIGINT DEFAULT NULL,
        nivel INT NOT NULL DEFAULT 0,
        ruta VARCHAR(255) NOT NULL DEFAULT '/',
        estado VARCHAR(16) NOT NULL DEFAULT 'activo',
        id_ref VARCHAR(80) DEFAULT NULL,
        datos MEDIUMTEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_nodo_emp (id_empresa, tipo, estado),
        INDEX idx_nodo_padre (id_empresa, padre_id),
        INDEX idx_nodo_ruta (id_empresa, ruta)"""),

    ("org_responsables", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_nodo BIGINT NOT NULL,
        rol_org VARCHAR(20) NOT NULL,
        usuario VARCHAR(80) NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_resp (id_empresa, id_nodo, rol_org),
        INDEX idx_resp_nodo (id_empresa, id_nodo),
        INDEX idx_resp_user (id_empresa, usuario)"""),

    ("org_delegaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario_origen VARCHAR(80) NOT NULL,
        usuario_delegado VARCHAR(80) NOT NULL,
        motivo VARCHAR(120) DEFAULT NULL,
        desde DATETIME DEFAULT NULL,
        hasta DATETIME DEFAULT NULL,
        activa TINYINT(1) NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_deleg_dest (id_empresa, usuario_delegado, activa),
        INDEX idx_deleg_orig (id_empresa, usuario_origen, activa)"""),

    ("org_aprobacion_reglas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) NOT NULL,
        entidad VARCHAR(60) NOT NULL,
        condicion VARCHAR(120) DEFAULT NULL,
        cadena MEDIUMTEXT DEFAULT NULL,
        activa TINYINT(1) NOT NULL DEFAULT 1,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_apr (id_empresa, codigo),
        INDEX idx_apr_ent (entidad, activa)"""),

    ("org_politicas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_nodo BIGINT DEFAULT NULL,
        clave VARCHAR(60) NOT NULL,
        valor VARCHAR(255) DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pol (id_empresa, id_nodo, clave),
        INDEX idx_pol (id_empresa, clave)"""),

    ("org_escalados", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        referencia VARCHAR(120) DEFAULT NULL,
        desde_usuario VARCHAR(80) DEFAULT NULL,
        hacia_usuario VARCHAR(80) DEFAULT NULL,
        nivel INT NOT NULL DEFAULT 1,
        horas INT NOT NULL DEFAULT 0,
        motivo VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_esc (id_empresa, creado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    # Siembra el catalogo semilla de cadenas de aprobacion (idempotente, best-effort).
    try:
        from src.services.gobierno import aprobaciones as _A
        _A.sembrar(cur)
    except Exception:
        pass


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
