"""
SAT-E — Base de conocimiento: categorias, articulos versionados, busqueda. Reutiliza el centro
documental (documentos_registro) para adjuntos. Multiempresa, auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.kb")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_categoria(nombre, *, padre=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO kb_categorias (id_empresa, nombre, padre) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE padre=VALUES(padre)", (eid, nombre, padre))
            cur.execute("SELECT id FROM kb_categorias WHERE id_empresa=%s AND nombre=%s", (eid, nombre))
            cid = cur.fetchone()
            conn.commit()
        return cid[0] if not isinstance(cid, dict) else list(cid.values())[0]
    except Exception as e:
        logger.error("crear_categoria: %s", e)
        return None


def crear_articulo(titulo, cuerpo, *, id_categoria=None, etiquetas=None, publicado=False,
                   autor=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO kb_articulos (id_empresa, id_categoria, titulo, cuerpo, etiquetas, publicado) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (eid, id_categoria, titulo, cuerpo, etiquetas,
                                                       1 if publicado else 0))
            aid = cur.lastrowid
            cur.execute("INSERT INTO kb_versiones (id_empresa, id_articulo, version, cuerpo, autor) "
                        "VALUES (%s,%s,1,%s,%s)", (eid, aid, cuerpo, autor))
            conn.commit()
        log_auditoria("sat", "KB_CREADO", "kb_articulos", f"art={aid} {titulo}")
        return aid
    except Exception as e:
        logger.error("crear_articulo: %s", e)
        return None


def editar_articulo(id_articulo, cuerpo, *, autor=None, id_empresa=None) -> bool:
    """Edita un articulo creando una nueva version (historico en kb_versiones)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT version FROM kb_articulos WHERE id=%s", (id_articulo,))
            r = cur.fetchone()
            if not r:
                return False
            ver = (r[0] if not isinstance(r, dict) else list(r.values())[0]) + 1
            cur.execute("UPDATE kb_articulos SET cuerpo=%s, version=%s, actualizado=NOW() WHERE id=%s",
                        (cuerpo, ver, id_articulo))
            cur.execute("INSERT INTO kb_versiones (id_empresa, id_articulo, version, cuerpo, autor) "
                        "VALUES (%s,%s,%s,%s,%s)", (_emp(id_empresa), id_articulo, ver, cuerpo, autor))
            conn.commit()
        log_auditoria("sat", "KB_EDITADO", "kb_articulos", f"art={id_articulo} v{ver}")
        return True
    except Exception as e:
        logger.error("editar_articulo: %s", e)
        return False


def publicar(id_articulo, publicado=True) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE kb_articulos SET publicado=%s WHERE id=%s", (1 if publicado else 0, id_articulo))
            conn.commit()
        return True
    except Exception as e:
        logger.error("publicar: %s", e)
        return False


def buscar(texto, *, solo_publicados=True, id_empresa=None, limite=50) -> list:
    eid = _emp(id_empresa)
    q = "SELECT id, titulo, etiquetas, publicado, vistas FROM kb_articulos WHERE id_empresa=%s"
    p = [eid]
    if solo_publicados:
        q += " AND publicado=1"
    if texto:
        q += " AND (titulo LIKE %s OR cuerpo LIKE %s OR etiquetas LIKE %s)"
        like = f"%{texto}%"; p += [like, like, like]
    q += " ORDER BY vistas DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("buscar KB: %s", e)
        return []


def ver_articulo(id_articulo) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE kb_articulos SET vistas=vistas+1 WHERE id=%s", (id_articulo,))
            cur.execute("SELECT * FROM kb_articulos WHERE id=%s", (id_articulo,))
            r = cur.fetchone()
            conn.commit()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("ver_articulo: %s", e)
        return None
