"""
Migracion 0094 — Gemelo Digital Empresarial (Paquete Enterprise 8). ADITIVA, idempotente,
reversible. El Gemelo Digital NO duplica la base de datos: es una CAPA DE CONOCIMIENTO construida
sobre ella. Estas tablas solo persisten lo que NO existe en ningun otro modulo:

  - dt_dependencias : el GRAFO de dependencias entre entidades (pedido→recepcion→stock→venta→
                      factura→cobro→contabilidad). Recorrible en ambos sentidos. (SUBFASE 8.8)
  - dt_incoherencias: el LOG de inconsistencias detectadas por la verificacion de consistencia
                      (SUBFASE 8.15), para auditoria y resincronizacion.
  - dt_snapshots    : una FOTO materializada del estado global por empresa (para lectura
                      instantanea del dashboard y como linea base de consistencia). Es cache
                      reconstruible desde las fuentes existentes; nunca fuente de verdad.

El estado VIVO por dominio se calcula bajo demanda reutilizando los servicios Enterprise ya
existentes (Event Bus, Centro de Actividad, BI, PredictionService, Gobierno, adaptadores IA);
no se almacena aqui para no duplicar datos. Multiempresa/multitienda/SaaS.
"""

VERSION = "0094"
DESCRIPCION = "Gemelo Digital: dt_dependencias, dt_incoherencias, dt_snapshots"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("dt_dependencias", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        origen_entidad VARCHAR(40) NOT NULL,
        origen_id VARCHAR(80) NOT NULL,
        destino_entidad VARCHAR(40) NOT NULL,
        destino_id VARCHAR(80) NOT NULL,
        relacion VARCHAR(40) NOT NULL DEFAULT 'deriva_en',
        origen_evento BIGINT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_dep (id_empresa, origen_entidad, origen_id, destino_entidad, destino_id, relacion),
        INDEX idx_dep_origen (id_empresa, origen_entidad, origen_id),
        INDEX idx_dep_destino (id_empresa, destino_entidad, destino_id)"""),

    ("dt_incoherencias", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        dominio VARCHAR(30) NOT NULL,
        entidad VARCHAR(40) DEFAULT NULL,
        entidad_id VARCHAR(80) DEFAULT NULL,
        tipo VARCHAR(40) NOT NULL,
        gravedad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        detalle VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'ABIERTA',
        hash VARCHAR(64) DEFAULT NULL,
        detectado DATETIME DEFAULT CURRENT_TIMESTAMP,
        resuelto DATETIME DEFAULT NULL,
        UNIQUE KEY uq_incoh (id_empresa, hash),
        INDEX idx_incoh (id_empresa, estado, dominio, detectado)"""),

    ("dt_snapshots", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        ambito VARCHAR(30) NOT NULL DEFAULT 'global',
        estado MEDIUMTEXT DEFAULT NULL,
        riesgo VARCHAR(12) NOT NULL DEFAULT 'BAJO',
        hash VARCHAR(64) DEFAULT NULL,
        generado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_snap (id_empresa, ambito, generado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
