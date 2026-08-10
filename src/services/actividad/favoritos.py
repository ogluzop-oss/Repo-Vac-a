"""
Favoritos y seguimiento de actividad (Paquete Enterprise 2, SUBFASE 2.6/2.7).

- Favoritos: el usuario fija eventos (estrella) y puede filtrar "solo favoritos".
- Seguimiento: el usuario sigue un evento/entidad (p.ej. Incidencia 352); cuando llegan nuevos
  eventos sobre esa entidad, aparecen como novedades (badge/Centro). Reutiliza la cola de eventos.

Estado por usuario en actividad_favoritos / actividad_seguidos (migr 0091). No duplica datos.
"""

import logging

logger = logging.getLogger("actividad.favoritos")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _uid(usuario):
    if isinstance(usuario, dict):
        v = usuario.get("nombre") or usuario.get("usuario") or usuario.get("id")
        return str(v) if v is not None else None
    return str(usuario) if usuario is not None else None


# ── Favoritos ─────────────────────────────────────────────────────────────────
def marcar(id_evento, usuario, id_empresa=None) -> bool:
    emp, uid = _emp(id_empresa), _uid(usuario)
    if not uid:
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT IGNORE INTO actividad_favoritos (id_empresa, usuario, id_evento) "
                        "VALUES (%s,%s,%s)", (emp, uid, int(id_evento)))
            c.commit()
        return True
    except Exception as e:
        logger.error("marcar favorito: %s", e)
        return False


def desmarcar(id_evento, usuario, id_empresa=None) -> bool:
    emp, uid = _emp(id_empresa), _uid(usuario)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM actividad_favoritos WHERE id_empresa=%s AND usuario=%s "
                        "AND id_evento=%s", (emp, uid, int(id_evento)))
            c.commit()
        return True
    except Exception as e:
        logger.error("desmarcar favorito: %s", e)
        return False


def ids_favoritos(usuario, id_empresa=None) -> set:
    emp, uid = _emp(id_empresa), _uid(usuario)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_evento FROM actividad_favoritos WHERE id_empresa=%s AND usuario=%s",
                        (emp, uid))
            return {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    except Exception:
        return set()


def listar(usuario, id_empresa=None, limite=200) -> list:
    """Eventos marcados como favoritos por el usuario (mas recientes primero)."""
    emp, uid = _emp(id_empresa), _uid(usuario)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        from src.services.actividad import timeline
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT e.* FROM actividad_favoritos f JOIN eventos e ON e.id=f.id_evento "
                        "AND e.id_empresa=f.id_empresa WHERE f.id_empresa=%s AND f.usuario=%s "
                        "ORDER BY e.id DESC LIMIT %s", (emp, uid, int(limite)))
            filas = _filas_a_dicts(cur, cur.fetchall())
        for f in filas:
            f["tipo_legible"] = timeline._legible(f.get("tipo"))
            f["resumen"] = timeline._resumen(f.get("payload"))
        return filas
    except Exception as e:
        logger.error("listar favoritos: %s", e)
        return []


# ── Seguimiento ───────────────────────────────────────────────────────────────
def seguir(usuario, *, id_evento=None, ref_entidad=None, ref_id=None, id_empresa=None) -> bool:
    emp, uid = _emp(id_empresa), _uid(usuario)
    if not uid:
        return False
    # Si se sigue por evento, resolver su entidad para seguir la entidad completa.
    if id_evento and not ref_entidad:
        try:
            from src.services import eventos as _EV
            ev = _EV.obtener(id_evento, id_empresa=emp) or {}
            ref_entidad = ev.get("ref_entidad"); ref_id = ev.get("ref_id")
        except Exception:
            pass
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id),0) FROM eventos WHERE id_empresa=%s AND "
                        "ref_entidad=%s AND ref_id=%s", (emp, ref_entidad, str(ref_id) if ref_id else None))
            r = cur.fetchone()
            ult = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
            cur.execute("INSERT INTO actividad_seguidos (id_empresa, usuario, id_evento, ref_entidad, "
                        "ref_id, ultimo_id_visto) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE ultimo_id_visto=VALUES(ultimo_id_visto)",
                        (emp, uid, id_evento, ref_entidad, str(ref_id) if ref_id else None, ult))
            c.commit()
        return True
    except Exception as e:
        logger.error("seguir: %s", e)
        return False


def dejar_seguir(usuario, *, ref_entidad=None, ref_id=None, id_empresa=None) -> bool:
    emp, uid = _emp(id_empresa), _uid(usuario)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM actividad_seguidos WHERE id_empresa=%s AND usuario=%s AND "
                        "ref_entidad=%s AND ref_id=%s",
                        (emp, uid, ref_entidad, str(ref_id) if ref_id else None))
            c.commit()
        return True
    except Exception as e:
        logger.error("dejar_seguir: %s", e)
        return False


def novedades(usuario, id_empresa=None) -> list:
    """Nuevos eventos sobre entidades seguidas desde la ultima vez que se vieron (badge/Centro)."""
    emp, uid = _emp(id_empresa), _uid(usuario)
    out = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT ref_entidad, ref_id, ultimo_id_visto FROM actividad_seguidos "
                        "WHERE id_empresa=%s AND usuario=%s", (emp, uid))
            seg = cur.fetchall()
            for r in seg:
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                ent, rid, ult = g(0), g(1), int(g(2) or 0)
                cur.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM eventos WHERE id_empresa=%s "
                            "AND ref_entidad=%s AND ref_id=%s AND id>%s", (emp, ent, rid, ult))
                cr = cur.fetchone()
                n = int((cr[0] if not isinstance(cr, dict) else list(cr.values())[0]) or 0)
                if n > 0:
                    out.append({"ref_entidad": ent, "ref_id": rid, "novedades": n})
    except Exception as e:
        logger.error("novedades seguidos: %s", e)
    return out
