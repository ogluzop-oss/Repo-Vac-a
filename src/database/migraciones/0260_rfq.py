"""
Migración 0260 — Subastas inversas / Licitaciones privadas (RFQ) (Smart Suppliers B2B, Punto 2).
ADITIVA, idempotente (`CREATE TABLE IF NOT EXISTS`), reversible.

Dos tablas nuevas, ninguna existente se toca:
  - `rfq`: petición de precio que una empresa lanza a SUS proveedores homologados (subasta inversa: el
    proveedor con mejor oferta gana). `codigo_articulo`/`categoria` son ambos NULL-ables porque una RFQ
    puede pedirse sobre un artículo concreto del maestro o sobre una categoría genérica (aprovisionamiento
    puntual sin ficha de artículo todavía). `sector_comercial_id` acota qué proveedores del sector B2B
    (`sectores_comerciales`, migración 0217) pueden verla — reutiliza el mismo grafo de compatibilidad que
    ya filtra el catálogo B2B (`services.compras.sectores.compatibles_de/son_compatibles`), sin tabla de
    match propia.
  - `rfq_ofertas`: pujas de los proveedores. `UNIQUE KEY uq_rfq_oferta (id_rfq, id_suministrador)` es la
    guardia de idempotencia REAL a nivel de motor (mismo criterio que `uq_rl_ventana` en la migración
    0258): garantiza "una puja activa por proveedor y RFQ" — `responder_rfq` hace upsert
    (`INSERT...ON DUPLICATE KEY UPDATE`) amparado por esta clave, así que la base de datos impide por
    construcción que un proveedor tenga dos pujas vivas a la vez, no solo un SELECT previo en Python.

Tipos de columna alineados con el resto del ecosistema B2B: `id_rfq`/`id_oferta CHAR(36)` (mismo estilo
UUID que `transaccion_comercial.id_tx`, generado en Python), `id_empresa CHAR(36)` (mismo tipo que
`transaccion_comercial.id_empresa`), `id_suministrador BIGINT` (mismo tipo que
`transaccion_comercial.id_suministrador`/`suministradores.id`).

Histórico recuperable (NO resucitado tal cual — ver `services/compras/b2b_rfq.py`):
`git show 408548b~1:src/services/compras/portal/rfq.py` (`portal_rfq`/`portal_rfq_ofertas`, motor de
pedidos y modelo de sesión ya retirados). `rfq`/`rfq_ofertas` son tablas limpias, nombres deliberadamente
sin el prefijo `portal_` (el portal actual es un módulo Flask distinto, `src.backend.portal_*`).
"""

VERSION = "0260"
DESCRIPCION = ("RFQ B2B: rfq (licitaciones/subastas inversas) + rfq_ofertas (pujas ciegas de "
               "proveedores, una viva por proveedor)")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("rfq", """
        id_rfq                CHAR(36)      NOT NULL PRIMARY KEY,
        id_empresa             CHAR(36)      NOT NULL,
        codigo_articulo         VARCHAR(50)   DEFAULT NULL,
        categoria               VARCHAR(100)  DEFAULT NULL,
        cantidad                 DECIMAL(14,3) NOT NULL,
        unidad_medida            VARCHAR(20)   NOT NULL DEFAULT 'unidad',
        fecha_limite_entrega     DATE          DEFAULT NULL,
        fecha_cierre_subasta     DATETIME      NOT NULL,
        sector_comercial_id      INT           DEFAULT NULL,
        estado                   VARCHAR(20)   NOT NULL DEFAULT 'abierta',
        creado_por               VARCHAR(150)  DEFAULT NULL,
        fecha_creacion           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_rfq_empresa (id_empresa),
        INDEX idx_rfq_estado (estado),
        INDEX idx_rfq_cierre (fecha_cierre_subasta),
        INDEX idx_rfq_sector (sector_comercial_id)"""),
    ("rfq_ofertas", """
        id_oferta            CHAR(36)      NOT NULL PRIMARY KEY,
        id_rfq                CHAR(36)      NOT NULL,
        id_suministrador       BIGINT        NOT NULL,
        precio_unitario         DECIMAL(14,4) NOT NULL,
        moq                     DECIMAL(14,3) DEFAULT NULL,
        plazo_entrega_dias      INT           DEFAULT NULL,
        fecha_oferta            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             ON UPDATE CURRENT_TIMESTAMP,
        estado                   VARCHAR(20)   NOT NULL DEFAULT 'activa',
        UNIQUE KEY uq_rfq_oferta (id_rfq, id_suministrador),
        INDEX idx_ro_rfq (id_rfq),
        INDEX idx_ro_sum (id_suministrador),
        CONSTRAINT fk_ro_rfq FOREIGN KEY (id_rfq) REFERENCES rfq(id_rfq) ON DELETE CASCADE"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
