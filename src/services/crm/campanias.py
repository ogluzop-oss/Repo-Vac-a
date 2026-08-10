"""
CRM · Campañas comerciales / Marketing (Módulo 1, enriquecimiento). Gestión de campañas: creación,
segmentación de destinatarios (reutiliza clientes/leads existentes), ejecución por canal (reutiliza el
sistema de correo/comunicaciones), resultados y cierre. Integra auditoría + Event Bus (para SOMA/BI/
Workflow) + BI. NO duplica lógica: se apoya en clientes, leads y correo ya existentes.
"""

import json
import logging

logger = logging.getLogger("crm.campanias")

ESTADOS = ("BORRADOR", "ACTIVA", "PAUSADA", "FINALIZADA", "CANCELADA")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.crm.identidad_crm import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("crm", accion, "crm_campanias", (detalle or "")[:255])
    except Exception:
        pass


def _evento(nombre, payload):
    try:
        from src.services import eventos
        eventos.publicar(nombre, ref_entidad="crm_campania", ref_id=(payload or {}).get("id"),
                         id_empresa=(payload or {}).get("id_empresa"), payload=payload)
    except Exception:
        pass


def crear_campania(nombre, *, canal="email", segmento_objetivo=None, presupuesto=0,
                   fecha_inicio=None, fecha_fin=None, responsable=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO crm_campanias (id_empresa, nombre, canal, segmento_objetivo, "
                        "presupuesto, fecha_inicio, fecha_fin, responsable) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, nombre[:160], canal, segmento_objetivo, float(presupuesto or 0),
                         fecha_inicio, fecha_fin, responsable))
            cid = cur.lastrowid
            c.commit()
        _audit("CAMPANA_CREADA", f"{cid}:{nombre}")
        _evento("crm.campana_creada", {"id": cid, "id_empresa": emp})
        return cid
    except Exception as e:
        logger.error("crear_campania: %s", e)
        return None


def añadir_destinatarios_por_segmento(id_campania, segmento=None, *, id_empresa=None) -> int:
    """Añade como destinatarios los CLIENTES del segmento indicado (reutiliza la tabla clientes)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT id FROM clientes WHERE id_empresa<=>%s AND estado='activo'"
            p = [emp]
            if segmento:
                q += " AND segmento=%s"; p.append(segmento)
            cur.execute(q, p)
            ids = [f["id"] for f in _filas_a_dicts(cur, cur.fetchall())]
            for cli in ids:
                cur.execute("INSERT INTO crm_campania_destinatarios (id_campania, id_cliente) "
                            "VALUES (%s,%s)", (id_campania, cli))
            c.commit()
        _audit("CAMPANA_DESTINATARIOS", f"{id_campania}:+{len(ids)}")
        return len(ids)
    except Exception as e:
        logger.error("añadir_destinatarios: %s", e)
        return 0


def activar(id_campania, *, id_empresa=None) -> dict:
    """Marca la campaña ACTIVA. El envío real por canal reutiliza el sistema de correo/comunicaciones
    (services.correo / integraciones) cuando esté configurado; aquí solo se registra el disparo."""
    return _set_estado(id_campania, "ACTIVA", id_empresa=id_empresa)


def _set_estado(id_campania, estado, *, id_empresa=None) -> dict:
    if estado not in ESTADOS:
        return {"ok": False, "motivo": "estado inválido"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE crm_campanias SET estado=%s WHERE id=%s", (estado, id_campania))
            c.commit()
        _audit("CAMPANA_ESTADO", f"{id_campania}={estado}")
        _evento("crm.campana_estado", {"id": id_campania, "estado": estado})
        return {"ok": True, "estado": estado}
    except Exception as e:
        logger.error("_set_estado: %s", e)
        return {"ok": False, "motivo": str(e)}


def resultados(id_campania) -> dict:
    """Métricas de la campaña: nº destinatarios, contactados, convertidos (reutiliza destinatarios)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) n FROM crm_campania_destinatarios "
                        "WHERE id_campania=%s GROUP BY estado", (id_campania,))
            por = {f["estado"]: int(f["n"]) for f in _filas_a_dicts(cur, cur.fetchall())}
        total = sum(por.values())
        return {"total": total, "por_estado": por,
                "convertidos": por.get("CONVERTIDO", 0), "contactados": por.get("CONTACTADO", 0)}
    except Exception as e:
        logger.debug("resultados: %s", e)
        return {"total": 0, "por_estado": {}}


def listar(id_empresa=None, *, limite=100) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM crm_campanias WHERE id_empresa<=>%s ORDER BY creada DESC LIMIT %s",
                        (emp, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar campañas: %s", e)
        return []
