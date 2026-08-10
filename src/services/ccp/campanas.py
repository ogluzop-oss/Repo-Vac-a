"""
Campaign Manager (CCP Fase II · B3) — campañas corporativas sobre la Outgoing Queue.

Crear/programar/pausar/reanudar/cancelar campañas (marketing/avisos/RRHH/legal…) a listas de
destinatarios resueltas por el Identity Resolver, despachadas por la Outgoing Queue vía el Corporate
Communication Service. Estadísticas + prioridades. Multiempresa. API-First (sin PyQt).
"""

import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.campanas")

TIPOS = ("marketing", "promocion", "incidencia", "mantenimiento", "aviso", "recordatorio", "legal",
         "rrhh")
ESTADOS = ("borrador", "programada", "en_curso", "pausada", "cancelada", "finalizada")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def _resolver_destinatarios(id_empresa, destinatarios, resolver) -> list:
    """Normaliza a [(correo, nombre)]. `destinatarios`: lista de correos o dicts {correo,nombre}.
    `resolver`: dict de búsqueda (texto/contexto) que usa el Identity Resolver para expandir a una
    lista de contactos."""
    out = {}
    for d in (destinatarios or []):
        if isinstance(d, str) and "@" in d:
            out[d.strip().lower()] = d
        elif isinstance(d, dict) and d.get("correo"):
            out[d["correo"].strip().lower()] = d.get("nombre") or d["correo"]
    if resolver:
        try:
            from src.services.ccp import identidad as _id
            for x in _id.resolver_destinatarios(id_empresa, resolver.get("texto", ""),
                                                contexto=resolver.get("contexto"),
                                                limite=resolver.get("limite", 500)):
                if x.correo and "@" in x.correo:
                    out.setdefault(x.correo.strip().lower(), x.nombre_mostrado)
        except Exception as e:
            logger.debug("resolver campaña: %s", e)
    return list(out.items())


def crear_campana(nombre, *, id_empresa=None, tipo="aviso", canal="email", asunto="", cuerpo="",
                  plantilla_codigo=None, contexto=None, prioridad="normal", programada_para=None,
                  destinatarios=None, resolver=None, usuario=None) -> int | None:
    id_empresa = _emp(id_empresa)
    usuario = _usuario(usuario)
    if tipo not in TIPOS:
        tipo = "aviso"
    contactos = _resolver_destinatarios(id_empresa, destinatarios, resolver)
    estado = "programada" if programada_para else "borrador"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ccp_campanas (id_empresa, nombre, tipo, canal, estado, plantilla_codigo, "
                "asunto, cuerpo, contexto, prioridad, programada_para, total, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, nombre, tipo, canal, estado, plantilla_codigo, asunto, cuerpo, contexto,
                 prioridad, programada_para, len(contactos), usuario))
            cid = cur.lastrowid
            for correo, nom in contactos:
                cur.execute("INSERT INTO ccp_campana_destinatarios (id_campana, id_empresa, correo, "
                            "nombre, estado) VALUES (%s,%s,%s,%s,'pendiente')",
                            (cid, id_empresa, correo, nom))
            conn.commit()
            return cid
    except Exception as e:
        logger.error("crear_campana(%s): %s", nombre, e)
        return None


def cambiar_estado(id_campana, estado) -> bool:
    if estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ccp_campanas SET estado=%s, actualizado=NOW() WHERE id=%s",
                        (estado, id_campana))
            conn.commit()
            return True
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_campana, e)
        return False


def pausar(id_campana):    return cambiar_estado(id_campana, "pausada")
def reanudar(id_campana):  return cambiar_estado(id_campana, "programada")
def cancelar(id_campana):  return cambiar_estado(id_campana, "cancelada")


def procesar_campana(id_campana, *, limite=1000) -> int:
    """Encola las pendientes de la campaña en la Outgoing Queue y las despacha. No procesa si la
    campaña está pausada/cancelada. Devuelve el nº de comunicaciones procesadas."""
    camp = obtener_campana(id_campana)
    if not camp or camp.get("estado") in ("pausada", "cancelada", "finalizada"):
        return 0
    id_empresa = camp.get("id_empresa")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT correo FROM ccp_campana_destinatarios WHERE id_campana=%s AND "
                        "estado='pendiente' LIMIT %s", (id_campana, int(limite)))
            pendientes = [r[0] if not isinstance(r, dict) else r.get("correo")
                          for r in cur.fetchall()]
    except Exception as e:
        logger.error("procesar_campana lectura(%s): %s", id_campana, e)
        return 0
    if not pendientes:
        cambiar_estado(id_campana, "finalizada")
        return 0
    cambiar_estado(id_campana, "en_curso")
    from src.services.ccp import cola as _cola
    q = _cola.cola()
    for correo in pendientes:
        q.encolar(id_empresa=id_empresa, destinatario=correo, asunto=camp.get("asunto") or "",
                  cuerpo=camp.get("cuerpo") or "", canal=camp.get("canal") or "email",
                  plantilla_codigo=camp.get("plantilla_codigo"), contexto=camp.get("contexto"),
                  prioridad=camp.get("prioridad") or "normal", id_campana=id_campana,
                  usuario=camp.get("usuario"))
    n = q.procesar(limite=len(pendientes), id_empresa=id_empresa)
    # Si ya no quedan pendientes, finaliza.
    if not _pendientes(id_campana):
        cambiar_estado(id_campana, "finalizada")
    return n


def _pendientes(id_campana) -> int:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ccp_campana_destinatarios WHERE id_campana=%s AND "
                        "estado='pendiente'", (id_campana,))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


def obtener_campana(id_campana) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ccp_campanas WHERE id=%s", (id_campana,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_campana(%s): %s", id_campana, e)
        return None


def listar_campanas(id_empresa=None, *, estado=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM ccp_campanas WHERE id_empresa=%s"
    p = [id_empresa]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY id DESC"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_campanas: %s", e)
        return []


def estadisticas(id_campana) -> dict:
    camp = obtener_campana(id_campana) or {}
    total = int(camp.get("total") or 0)
    env = int(camp.get("enviados") or 0)
    fall = int(camp.get("fallidos") or 0)
    return {"total": total, "enviados": env, "fallidos": fall, "pendientes": _pendientes(id_campana),
            "estado": camp.get("estado"),
            "progreso_pct": round(100 * (env + fall) / total, 1) if total else 0.0}
