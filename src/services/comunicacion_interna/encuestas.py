"""
Encuestas internas — personalizables (preguntas de OPCIONES o de TEXTO, opciones ilimitadas, opción
"Otro" implícita con texto libre), texto introductorio, adjuntos en envío y respuestas. Cada centro
responde verificando perfil + contraseña.
"""

from __future__ import annotations

import logging

from . import adjuntos as ADJ

logger = logging.getLogger("comunicacion_interna.encuestas")

ENTIDAD = "ENCUESTA"
TIPO_OPCIONES = "OPCIONES"
TIPO_TEXTO = "TEXTO"


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _empresa(id_empresa=None):
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
        return sesion_global.usuario_actual or {}
    except Exception:
        return {}


def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ─── Creación (emisor) ────────────────────────────────────────────────────────

def crear_encuesta(titulo, intro, preguntas, *, adjuntos=None, usuario=None, id_empresa=None) -> dict:
    """Crea una encuesta. `preguntas` = [{texto, tipo(OPCIONES/TEXTO), opciones:[str,...]}].
    Las preguntas de opciones muestran "Otro" automáticamente en la GUI (no se almacena)."""
    titulo = (titulo or "").strip()
    if not titulo:
        return {"ok": False, "error": "El título es obligatorio."}
    preguntas = [p for p in (preguntas or []) if (p.get("texto") or "").strip()]
    if not preguntas:
        return {"ok": False, "error": "Añade al menos una pregunta."}
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO com_encuestas (id_empresa, titulo, intro, creador_id, creador_nombre) "
                "VALUES (%s,%s,%s,%s,%s)",
                (emp, titulo, intro or "", str(u.get("id")) if u.get("id") is not None else None,
                 u.get("nombre") or "—"))
            eid = cur.lastrowid
            for i, p in enumerate(preguntas):
                tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                cur.execute(
                    "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                    "VALUES (%s,%s,%s,%s)", (eid, i, (p.get("texto") or "").strip(), tipo))
                pid = cur.lastrowid
                if tipo == TIPO_OPCIONES:
                    ops = [o for o in (p.get("opciones") or []) if (o or "").strip()]
                    for j, o in enumerate(ops):
                        cur.execute(
                            "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                            "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=eid, origen="EMISOR", cur=cur)
            conn.commit()
        return {"ok": True, "id": eid}
    except Exception as e:
        logger.error(f"crear_encuesta: {e}")
        return {"ok": False, "error": str(e)}


# ─── Bandeja / lectura ────────────────────────────────────────────────────────

def listar_encuestas(*, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT e.id, e.titulo, e.creador_nombre, e.creado, e.estado, "
                "  (SELECT COUNT(*) FROM com_encuesta_respuestas r WHERE r.id_encuesta=e.id) AS respuestas "
                "FROM com_encuestas e WHERE e.id_empresa=%s ORDER BY e.creado DESC, e.id DESC", (emp,))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_encuestas degradado: {e}")
        return []


def obtener_encuesta(id_encuesta) -> dict | None:
    """Encuesta completa: cabecera + preguntas(+opciones) + adjuntos emisor + respuestas(+items+adjuntos)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM com_encuestas WHERE id=%s", (id_encuesta,))
            filas = _rows(cur)
            if not filas:
                return None
            enc = filas[0]
            cur.execute("SELECT id, orden, texto, tipo FROM com_encuesta_preguntas "
                        "WHERE id_encuesta=%s ORDER BY orden ASC, id ASC", (id_encuesta,))
            preguntas = _rows(cur)
            for p in preguntas:
                cur.execute("SELECT id, orden, texto FROM com_encuesta_opciones "
                            "WHERE id_pregunta=%s ORDER BY orden ASC, id ASC", (p["id"],))
                p["opciones"] = _rows(cur)
            cur.execute("SELECT id, usuario_nombre, id_centro, comentario, creado "
                        "FROM com_encuesta_respuestas WHERE id_encuesta=%s ORDER BY creado ASC",
                        (id_encuesta,))
            respuestas = _rows(cur)
            for r in respuestas:
                cur.execute("SELECT id_pregunta, id_opcion, texto FROM com_encuesta_resp_items "
                            "WHERE id_respuesta=%s", (r["id"],))
                r["items"] = _rows(cur)
        enc["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_encuesta, origen="EMISOR", id_respuesta=None)
        for r in respuestas:
            r["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_encuesta, origen="RESPUESTA",
                                                id_respuesta=r["id"])
        enc["preguntas"] = preguntas
        enc["respuestas"] = respuestas
        return enc
    except Exception as e:
        logger.error(f"obtener_encuesta: {e}")
        return None


def responder_encuesta(id_encuesta, *, usuario_nombre, password, respuestas, comentario="",
                       adjuntos=None, id_empresa=None) -> dict:
    """Registra la respuesta verificando perfil+contraseña.
    `respuestas` = { id_pregunta: {'opciones':[id_opcion,...], 'otro': str, 'texto': str} }."""
    from src.db.usuario import validar_login_empleado
    u = validar_login_empleado(usuario_nombre or "", password or "")
    if not u:
        return {"ok": False, "error": "Perfil o contraseña incorrectos."}
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Encuesta no encontrada."}
            if u.get("id_empresa") and emp and str(u["id_empresa"]) != str(emp):
                return {"ok": False, "error": "El perfil no pertenece a esta empresa."}
            cur.execute(
                "INSERT INTO com_encuesta_respuestas "
                "(id_encuesta, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_encuesta, str(u.get("id")), u.get("nombre"), u.get("tienda_id"), comentario or ""))
            rid = cur.lastrowid
            for id_pregunta, resp in (respuestas or {}).items():
                resp = resp or {}
                for op in (resp.get("opciones") or []):
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, id_opcion) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, op))
                otro = (resp.get("otro") or "").strip()
                if otro:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, otro))
                texto = (resp.get("texto") or "").strip()
                if texto:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, texto))
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_encuesta,
                               origen="RESPUESTA", id_respuesta=rid, cur=cur)
            conn.commit()
        return {"ok": True, "id": rid, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"responder_encuesta: {e}")
        return {"ok": False, "error": str(e)}


def eliminar_encuesta(id_encuesta, *, id_empresa=None) -> bool:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM com_encuesta_respuestas WHERE id_encuesta=%s", (id_encuesta,))
            resp_ids = [r[0] for r in cur.fetchall()]
            if resp_ids:
                marc = ",".join(["%s"] * len(resp_ids))
                cur.execute(f"DELETE FROM com_encuesta_resp_items WHERE id_respuesta IN ({marc})",
                            tuple(resp_ids))
            cur.execute("SELECT id FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
            preg_ids = [r[0] for r in cur.fetchall()]
            if preg_ids:
                marc = ",".join(["%s"] * len(preg_ids))
                cur.execute(f"DELETE FROM com_encuesta_opciones WHERE id_pregunta IN ({marc})",
                            tuple(preg_ids))
            cur.execute("DELETE FROM com_encuesta_respuestas WHERE id_encuesta=%s", (id_encuesta,))
            cur.execute("DELETE FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
            cur.execute("DELETE FROM com_adjuntos WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_encuesta))
            cur.execute("DELETE FROM com_encuestas WHERE id=%s", (id_encuesta,))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"eliminar_encuesta: {e}")
        return False
