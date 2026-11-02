"""
Portal de Incidencias / Helpdesk INTERNO (petición explícita, migr. 0323) — motor NUEVO (auditoría
previa: `services/sat/tickets.py` está construido alrededor de un cliente externo — SLA por
contrato, encuesta de satisfacción, portal de cliente — y no es reutilizable sin forzar conceptos
que no aplican a una incidencia interna de empleado). Multiempresa por `id_empresa`.

RBAC (petición explícita, aplicado en la GUI — `gui/portal_incidencias_gui.py`): ADMINISTRADOR solo
envía incidencias propias; SUPERADMIN las recibe/gestiona todas. Este módulo de servicio no impone
el rol — es la GUI quien decide qué pantalla mostrar; aquí solo se filtra por `id_usuario_solicitante`
cuando el llamador lo pide (autoservicio) o se listan todas (gestión).

Extensión (migr. 0325, módulo Redes Sociales): columna `origen` (`manual` por defecto vs
`reputacion_auto`) y `id_usuario_solicitante` ahora NULL-able — un ticket de origen
`reputacion_auto` no tiene empleado solicitante (lo genera el motor de monitorización de
reputación, sin intervención humana). Esto NO rompe el aislamiento ADMINISTRADOR/SUPERADMIN: un
ticket con `id_usuario_solicitante` NULL nunca puede coincidir con el filtro `id_usuario_solicitante=
<id_de_ese_administrador>` que usa la vista de autoservicio, así que sigue siendo visible
ÚNICAMENTE en la vista sin filtrar (gestión, exclusiva de SUPERADMIN) — tal como exige el encargo.
"""

import logging

logger = logging.getLogger("incidencias_internas")

CATEGORIAS = ("equipo_informatico", "soporte_tecnico", "consulta_rrhh", "reputacion_redes", "otro")
ORIGENES = ("manual", "reputacion_auto")
PRIORIDADES = ("baja", "media", "alta")
ESTADOS = ("pendiente", "en_proceso", "resuelto", "cerrado")
_TRANSICIONES = {
    "pendiente": ("en_proceso", "resuelto", "cerrado"),
    "en_proceso": ("resuelto", "cerrado", "pendiente"),
    "resuelto": ("cerrado", "en_proceso"),
    "cerrado": (),
}


class IncidenciaError(Exception):
    """Validación de negocio fallida (categoría/prioridad/estado inválidos, transición no permitida)."""


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _siguiente_codigo(cur, id_empresa) -> str:
    cur.execute("SELECT codigo FROM incidencias_internas WHERE id_empresa=%s "
                "ORDER BY id DESC LIMIT 1", (id_empresa,))
    row = cur.fetchone()
    ultimo = 0
    if row:
        try:
            ultimo = int(str(row[0]).split("-")[-1])
        except (ValueError, IndexError):
            ultimo = 0
    return f"INC-{ultimo + 1:05d}"


def crear_ticket(asunto, descripcion, categoria, *, prioridad="media", id_usuario_solicitante=None,
                 nombre_solicitante=None, id_empresa=None, origen="manual") -> dict:
    """Crea una incidencia nueva, siempre en estado `pendiente`. `id_usuario_solicitante` es
    OBLIGATORIO para `origen="manual"` (toda incidencia manual pertenece a quien la envió —
    autoservicio, nunca anónimo). Para `origen="reputacion_auto"` (escalado automático desde
    monitorización de reputación en redes sociales, ver `services.redes_sociales.reputacion`) no
    hay solicitante humano — usar `crear_ticket_automatico` en vez de llamar aquí directamente."""
    asunto = (asunto or "").strip()
    if not asunto:
        raise IncidenciaError("El asunto es obligatorio.")
    if categoria not in CATEGORIAS:
        raise IncidenciaError(f"Categoría no válida: {categoria!r}")
    if prioridad not in PRIORIDADES:
        raise IncidenciaError(f"Prioridad no válida: {prioridad!r}")
    if origen not in ORIGENES:
        raise IncidenciaError(f"Origen no válido: {origen!r}")
    if origen == "manual" and not id_usuario_solicitante:
        raise IncidenciaError("Falta el usuario solicitante.")
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            codigo = _siguiente_codigo(cur, id_empresa)
            cur.execute(
                "INSERT INTO incidencias_internas (id_empresa, codigo, categoria, asunto, "
                "descripcion, prioridad, id_usuario_solicitante, nombre_solicitante, origen) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, codigo, categoria, asunto, (descripcion or "").strip() or None,
                 prioridad, id_usuario_solicitante, nombre_solicitante, origen))
            id_ticket = cur.lastrowid
    except Exception as e:
        logger.error("crear_ticket: %s", e)
        raise IncidenciaError("No se pudo registrar la incidencia.") from e

    try:
        from src.services import eventos as _EV
        _EV.publicar("INCIDENCIA_INTERNA_CREADA", id_empresa=id_empresa,
                     origen="incidencias_internas", ref_entidad="incidencia_interna",
                     ref_id=id_ticket, payload={"codigo": codigo, "categoria": categoria,
                                                "prioridad": prioridad, "origen_ticket": origen})
    except Exception:
        pass
    return {"ok": True, "id": id_ticket, "codigo": codigo}


def crear_ticket_automatico(asunto, descripcion, *, prioridad="alta", id_empresa=None,
                            categoria="reputacion_redes") -> dict:
    """Escalado automático SIN solicitante humano (p. ej. mención/queja grave detectada por
    `services.redes_sociales.reputacion`). Siempre `origen="reputacion_auto"` — visible
    ÚNICAMENTE en la vista de gestión sin filtrar (SUPERADMIN), nunca en el autoservicio de
    ADMINISTRADOR (ver nota de clase arriba)."""
    return crear_ticket(asunto, descripcion, categoria, prioridad=prioridad,
                        id_usuario_solicitante=None, nombre_solicitante="Sistema (Monitorización de reputación)",
                        id_empresa=id_empresa, origen="reputacion_auto")


def obtener_ticket(id_ticket, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM incidencias_internas WHERE id=%s AND id_empresa=%s",
                        (id_ticket, id_empresa))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
    except Exception as e:
        logger.error("obtener_ticket(%s): %s", id_ticket, e)
        return None


def listar_tickets(*, id_empresa=None, estado=None, categoria=None, id_usuario_solicitante=None,
                   limite=500) -> list:
    """Sin `id_usuario_solicitante`: TODAS las incidencias de la empresa (vista de gestión,
    SUPERADMIN). Con `id_usuario_solicitante`: solo las enviadas por ese usuario (autoservicio,
    ADMINISTRADOR) — aislamiento real, nunca ve las de otros compañeros."""
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if categoria:
        filtros.append("categoria=%s"); params.append(categoria)
    if id_usuario_solicitante is not None:
        filtros.append("id_usuario_solicitante=%s"); params.append(id_usuario_solicitante)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM incidencias_internas WHERE " + " AND ".join(filtros) +
                " ORDER BY FIELD(estado,'pendiente','en_proceso','resuelto','cerrado'), "
                "FIELD(prioridad,'alta','media','baja'), fecha_creacion DESC LIMIT %s",
                (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_tickets: %s", e)
        return []


def cambiar_estado(id_ticket, nuevo_estado, *, usuario=None, respuesta=None, id_empresa=None) -> dict:
    """Transición de estado — valida que sea un salto permitido desde el estado actual
    (`_TRANSICIONES`). `respuesta` (opcional): nota de resolución, visible al solicitante."""
    id_empresa = _emp(id_empresa)
    if nuevo_estado not in ESTADOS:
        raise IncidenciaError(f"Estado no válido: {nuevo_estado!r}")
    actual = obtener_ticket(id_ticket, id_empresa)
    if not actual:
        raise IncidenciaError("Incidencia no encontrada.")
    if nuevo_estado not in _TRANSICIONES.get(actual["estado"], ()):
        raise IncidenciaError(f"No se puede pasar de '{actual['estado']}' a '{nuevo_estado}'.")
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            if nuevo_estado == "resuelto":
                cur.execute("UPDATE incidencias_internas SET estado=%s, respuesta=COALESCE(%s,respuesta), "
                           "fecha_resolucion=NOW() WHERE id=%s AND id_empresa=%s",
                           (nuevo_estado, respuesta, id_ticket, id_empresa))
            else:
                cur.execute("UPDATE incidencias_internas SET estado=%s, respuesta=COALESCE(%s,respuesta) "
                           "WHERE id=%s AND id_empresa=%s",
                           (nuevo_estado, respuesta, id_ticket, id_empresa))
        if respuesta:
            comentar(id_ticket, respuesta, autor=usuario, es_solicitante=False, id_empresa=id_empresa)
        return {"ok": True}
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_ticket, e)
        return {"ok": False, "error": "error_interno"}


def asignar(id_ticket, asignado_a, nombre_asignado=None, *, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE incidencias_internas SET asignado_a=%s, nombre_asignado=%s "
                       "WHERE id=%s AND id_empresa=%s",
                       (asignado_a, nombre_asignado, id_ticket, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("asignar(%s): %s", id_ticket, e)
        return {"ok": False, "error": "error_interno"}


def comentar(id_ticket, cuerpo, *, autor=None, es_solicitante=False, id_empresa=None) -> dict:
    cuerpo = (cuerpo or "").strip()
    if not cuerpo:
        raise IncidenciaError("El comentario no puede estar vacío.")
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidencias_internas_comentarios (id_empresa, id_incidencia, autor, "
                "es_solicitante, cuerpo) VALUES (%s,%s,%s,%s,%s)",
                (id_empresa, id_ticket, autor, bool(es_solicitante), cuerpo))
            id_com = cur.lastrowid
        return {"ok": True, "id": id_com}
    except Exception as e:
        logger.error("comentar(%s): %s", id_ticket, e)
        return {"ok": False, "error": "error_interno"}


def listar_comentarios(id_ticket, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM incidencias_internas_comentarios WHERE id_incidencia=%s "
                       "AND id_empresa=%s ORDER BY fecha ASC, id ASC", (id_ticket, id_empresa))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_comentarios(%s): %s", id_ticket, e)
        return []


def contar_pendientes(id_empresa=None) -> int:
    """Nº de incidencias `pendiente`/`en_proceso` — alimenta el badge de la tarjeta del menú
    principal, mismo criterio visual que el resto de módulos (Documentos/Stock/Permisos)."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM incidencias_internas WHERE id_empresa=%s "
                       "AND estado IN ('pendiente','en_proceso')", (id_empresa,))
            fila = cur.fetchone()
            return int(fila[0] or 0) if fila else 0
    except Exception as e:
        logger.error("contar_pendientes: %s", e)
        return 0
