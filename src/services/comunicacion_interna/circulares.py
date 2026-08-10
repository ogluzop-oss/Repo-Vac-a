"""
Circulares internas — comunicación del emisor a todos los centros de la empresa, con confirmación de
lectura por perfil (nombre + contraseña), comentario y adjuntos (texto/imagen) en envío y respuestas.
"""

from __future__ import annotations

import logging

from . import adjuntos as ADJ

logger = logging.getLogger("comunicacion_interna.circulares")

ENTIDAD = "CIRCULAR"


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

def crear_circular(titulo, cuerpo, *, adjuntos=None, usuario=None, id_empresa=None) -> dict:
    """Crea y publica una circular. `adjuntos` = lista de rutas de archivo. Devuelve {ok, id, ...}."""
    titulo = (titulo or "").strip()
    if not titulo:
        return {"ok": False, "error": "El título es obligatorio."}
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO com_circulares (id_empresa, titulo, cuerpo, creador_id, creador_nombre) "
                "VALUES (%s,%s,%s,%s,%s)",
                (emp, titulo, cuerpo or "", str(u.get("id")) if u.get("id") is not None else None,
                 u.get("nombre") or "—"))
            cid = cur.lastrowid
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=cid, origen="EMISOR", cur=cur)
            conn.commit()
        return {"ok": True, "id": cid}
    except Exception as e:
        logger.error(f"crear_circular: {e}")
        return {"ok": False, "error": str(e)}


# ─── Bandeja / lectura ────────────────────────────────────────────────────────

def listar_circulares(*, id_empresa=None) -> list[dict]:
    """Bandeja: circulares de la empresa (más recientes primero) + nº de confirmaciones."""
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.titulo, c.creador_nombre, c.creado, c.estado, "
                "  (SELECT COUNT(*) FROM com_circular_confirmaciones k WHERE k.id_circular=c.id) AS confirmaciones "
                "FROM com_circulares c WHERE c.id_empresa=%s ORDER BY c.creado DESC, c.id DESC", (emp,))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_circulares degradado: {e}")
        return []


def obtener_circular(id_circular) -> dict | None:
    """Circular completa: cabecera + adjuntos del emisor + confirmaciones (con comentario y adjuntos)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM com_circulares WHERE id=%s", (id_circular,))
            filas = _rows(cur)
            if not filas:
                return None
            circ = filas[0]
            cur.execute(
                "SELECT id, usuario_nombre, id_centro, comentario, creado FROM com_circular_confirmaciones "
                "WHERE id_circular=%s ORDER BY creado ASC", (id_circular,))
            confs = _rows(cur)
        circ["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_circular, origen="EMISOR", id_respuesta=None)
        for cf in confs:
            cf["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_circular, origen="RESPUESTA",
                                                 id_respuesta=cf["id"])
        circ["confirmaciones"] = confs
        return circ
    except Exception as e:
        logger.error(f"obtener_circular: {e}")
        return None


def confirmar_lectura(id_circular, *, usuario_nombre, password, comentario="", adjuntos=None,
                      id_empresa=None) -> dict:
    """Confirma la lectura verificando perfil+contraseña. Registra comentario + adjuntos de respuesta."""
    from src.db.usuario import validar_login_empleado
    u = validar_login_empleado(usuario_nombre or "", password or "")
    if not u:
        return {"ok": False, "error": "Perfil o contraseña incorrectos."}
    # Aislamiento: el perfil debe pertenecer a la empresa de la circular.
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Circular no encontrada."}
            if u.get("id_empresa") and emp and str(u["id_empresa"]) != str(emp):
                return {"ok": False, "error": "El perfil no pertenece a esta empresa."}
            cur.execute(
                "INSERT INTO com_circular_confirmaciones "
                "(id_circular, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_circular, str(u.get("id")), u.get("nombre"), u.get("tienda_id"), comentario or ""))
            conf_id = cur.lastrowid
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_circular,
                               origen="RESPUESTA", id_respuesta=conf_id, cur=cur)
            conn.commit()
        return {"ok": True, "id": conf_id, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"confirmar_lectura: {e}")
        return {"ok": False, "error": str(e)}


def eliminar_circular(id_circular, *, id_empresa=None) -> bool:
    """Elimina una circular y sus confirmaciones/adjuntos (registro; los ficheros quedan en disco)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM com_circular_confirmaciones WHERE id_circular=%s", (id_circular,))
            cur.execute("DELETE FROM com_adjuntos WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_circular))
            cur.execute("DELETE FROM com_circulares WHERE id=%s", (id_circular,))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"eliminar_circular: {e}")
        return False
