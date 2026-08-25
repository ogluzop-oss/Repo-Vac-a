"""
Incidencias OPERATIVAS de tienda/almacén (roturas, limpieza, averías de equipo, incidencias con
clientes, etc.), pensadas para reportarse desde el cliente móvil del personal de tienda/almacén.

DISTINTO de `src/services/seguridad/incidentes.py` (incidentes de SEGURIDAD: fuerza bruta, token
comprometido, acceso sospechoso — ámbito exclusivo de seguridad/administración). No se reutiliza ese
módulo para no mezclar dominios ni exponer datos de seguridad por una vía operativa general.

Multiempresa y auditado. `reportar` está en el rol OPERARIO; `gestionar` (ver todas/asignar/cerrar)
es de gerencia — ver `src/services/seguridad/catalogo.py`.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("incidencias_operativas")

PRIORIDADES = ("baja", "normal", "alta", "critica")
ESTADOS = ("abierta", "en_curso", "resuelta", "cancelada")
ESTADOS_CIERRE = ("resuelta", "cancelada")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def abrir(tipo, titulo, descripcion="", *, prioridad="normal", ubicacion=None, reportado_por=None,
          ref_entidad=None, ref_id=None, id_empresa=None) -> int | None:
    """Reporta una incidencia operativa. Notifica (best-effort) a gerencia/administración."""
    id_empresa = _emp(id_empresa)
    if prioridad not in PRIORIDADES:
        prioridad = "normal"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidencias_operativas (id_empresa, tipo, titulo, descripcion, "
                "prioridad, ubicacion, reportado_por, ref_entidad, ref_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, tipo, titulo, descripcion, prioridad, ubicacion, reportado_por,
                 ref_entidad, (str(ref_id) if ref_id is not None else None)))
            iid = cur.lastrowid
            conn.commit()
        _audit("INCIDENCIA_OPERATIVA_ABIERTA", f"id={iid} {tipo} prio={prioridad}")
        try:
            from src.services import notificaciones
            notificaciones.emitir(
                "incidencia_operativa", f"Nueva incidencia: {titulo}", descripcion or "",
                modulo="incidencias", prioridad=prioridad, roles=["GERENTE", "ADMINISTRADOR"],
                ref_entidad="incidencia_operativa", ref_id=iid, id_empresa=id_empresa)
        except Exception:
            pass
        return iid
    except Exception as e:
        logger.error("abrir: %s", e)
        return None


def asignar(id_incidencia, usuario, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE incidencias_operativas SET asignado_a=%s, estado='en_curso' "
                        "WHERE id=%s AND id_empresa=%s", (usuario, id_incidencia, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            _audit("INCIDENCIA_OPERATIVA_ASIGNADA", f"id={id_incidencia} -> {usuario}")
            try:
                from src.services import notificaciones
                notificaciones.emitir("incidencia_operativa", "Incidencia asignada", "",
                                      modulo="incidencias", usuarios=[usuario], id_empresa=id_empresa)
            except Exception:
                pass
        return ok
    except Exception as e:
        logger.error("asignar(%s): %s", id_incidencia, e)
        return False


def cambiar_estado(id_incidencia, estado, *, resolucion=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado}")
    cierre = ", fecha_cierre=NOW()" if estado in ESTADOS_CIERRE else ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE incidencias_operativas SET estado=%s, resolucion=COALESCE(%s, "
                        f"resolucion){cierre} WHERE id=%s AND id_empresa=%s",
                        (estado, resolucion, id_incidencia, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            _audit("INCIDENCIA_OPERATIVA_ESTADO", f"id={id_incidencia} -> {estado}")
        return ok
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_incidencia, e)
        return False


def mias(usuario, *, estado=None, id_empresa=None, limite=200) -> list:
    """Incidencias reportadas por el usuario o asignadas a él."""
    id_empresa = _emp(id_empresa)
    q = ("SELECT * FROM incidencias_operativas WHERE id_empresa=%s "
         "AND (reportado_por=%s OR asignado_a=%s)")
    p = [id_empresa, usuario, usuario]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += (" ORDER BY FIELD(prioridad,'critica','alta','normal','baja'), fecha_creacion DESC "
          "LIMIT %s")
    p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("mias: %s", e)
        return []


def listar(*, estado=None, tipo=None, prioridad=None, id_empresa=None, limite=500) -> list:
    """Todas las incidencias de la empresa (vista de gestión)."""
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM incidencias_operativas WHERE id_empresa=%s"
    p = [id_empresa]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    if prioridad:
        q += " AND prioridad=%s"; p.append(prioridad)
    q += (" ORDER BY FIELD(prioridad,'critica','alta','normal','baja'), fecha_creacion DESC "
          "LIMIT %s")
    p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def obtener(id_incidencia, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM incidencias_operativas WHERE id=%s AND id_empresa=%s",
                        (id_incidencia, id_empresa))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener(%s): %s", id_incidencia, e)
        return None


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "incidencias_operativas", detalle)
    except Exception:
        pass
