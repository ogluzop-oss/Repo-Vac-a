"""
CRM-B — Pipeline comercial configurable + etapas. Multiempresa, auditado.
Etapas por defecto: Lead/Contacto/Propuesta/Negociacion/Pendiente/Ganado/Perdido con probabilidad.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.pipeline")

# (codigo, nombre, orden, probabilidad, color, es_ganado, es_perdido)
ETAPAS_DEFECTO = [
    ("lead", "Lead", 1, 10, "#888888", 0, 0),
    ("contacto", "Contacto", 2, 25, "#3498db", 0, 0),
    ("propuesta", "Propuesta", 3, 45, "#9b59b6", 0, 0),
    ("negociacion", "Negociacion", 4, 70, "#f39c12", 0, 0),
    ("pendiente", "Pendiente", 5, 85, "#1abc9c", 0, 0),
    ("ganado", "Ganado", 6, 100, "#2ecc71", 1, 0),
    ("perdido", "Perdido", 7, 0, "#e74c3c", 0, 1),
]


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def asegurar_pipeline_defecto(*, id_empresa=None) -> int:
    """Crea (idempotente) el pipeline 'comercial' por defecto con sus etapas. Devuelve su id."""
    eid = _emp(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO crm_pipelines (id_empresa, codigo, nombre) VALUES (%s,'comercial','Comercial') "
                    "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre)", (eid,))
        cur.execute("SELECT id FROM crm_pipelines WHERE id_empresa=%s AND codigo='comercial'", (eid,))
        pid = cur.fetchone()
        pid = pid[0] if not isinstance(pid, dict) else list(pid.values())[0]
        for cod, nom, orden, prob, color, gan, perd in ETAPAS_DEFECTO:
            cur.execute("INSERT INTO crm_etapas (id_empresa, id_pipeline, codigo, nombre, orden, "
                        "probabilidad, color, es_ganado, es_perdido) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), orden=VALUES(orden), "
                        "probabilidad=VALUES(probabilidad), color=VALUES(color)",
                        (eid, pid, cod, nom, orden, prob, color, gan, perd))
        conn.commit()
    return pid


def listar_etapas(id_pipeline=None, *, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    if id_pipeline is None:
        id_pipeline = asegurar_pipeline_defecto(id_empresa=eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM crm_etapas WHERE id_empresa=%s AND id_pipeline=%s ORDER BY orden",
                        (eid, id_pipeline))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_etapas: %s", e)
        return []


def etapa_por_codigo(codigo, *, id_empresa=None) -> dict | None:
    eid = _emp(id_empresa)
    pid = asegurar_pipeline_defecto(id_empresa=eid)
    for e in listar_etapas(pid, id_empresa=eid):
        if e["codigo"] == codigo:
            return e
    return None
