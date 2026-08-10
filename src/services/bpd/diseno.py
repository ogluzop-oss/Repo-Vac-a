"""
BPD · Diseño (Fase V · Bloque 4). Persistencia del diseño de procesos con VERSIONADO: borrador,
publicación y rollback. El diseño es un grafo {nodos, aristas} de bloques (`bloques.py`). No ejecuta
nada por sí mismo; lo compila `compilador.py` hacia el Workflow Engine. Multiempresa.
"""

from __future__ import annotations

import json
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.bpd import bloques

logger = logging.getLogger("bpd.diseno")


def crear_proceso(clave, nombre, *, id_empresa=None) -> int | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bpd_procesos (id_empresa, clave, nombre) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), actualizado=NOW()",
                        (id_empresa, clave, nombre))
            conn.commit()
            cur.execute("SELECT id FROM bpd_procesos WHERE clave=%s AND (id_empresa=%s OR "
                        "(%s IS NULL AND id_empresa IS NULL))", (clave, id_empresa, id_empresa))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else r["id"]) if r else None
    except Exception as e:
        logger.error("crear_proceso: %s", e); return None


def validar_definicion(definicion) -> tuple:
    """(ok, errores). Comprueba tipos de bloque válidos, un inicio y al menos un fin."""
    errores = []
    nodos = (definicion or {}).get("nodos") or []
    tipos = [n.get("tipo") for n in nodos]
    for n in nodos:
        if not bloques.es_valido(n.get("tipo")):
            errores.append(f"bloque inválido: {n.get('tipo')}")
    if "inicio" not in tipos:
        errores.append("falta bloque 'inicio'")
    if "fin" not in tipos:
        errores.append("falta bloque 'fin'")
    return (not errores), errores


def guardar_borrador(id_proceso, definicion, *, id_empresa=None, usuario=None) -> dict:
    ok, errores = validar_definicion(definicion)
    if not ok:
        return {"ok": False, "errores": errores}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(version),0)+1 FROM bpd_versiones WHERE id_proceso=%s",
                        (id_proceso,))
            r = cur.fetchone()
            ver = (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 1
            cur.execute("INSERT INTO bpd_versiones (id_proceso, id_empresa, version, definicion, "
                        "estado, usuario) VALUES (%s,%s,%s,%s,'borrador',%s)",
                        (id_proceso, id_empresa, ver, json.dumps(definicion), usuario))
            cur.execute("UPDATE bpd_procesos SET version_actual=%s, estado='borrador', "
                        "actualizado=NOW() WHERE id=%s", (ver, id_proceso))
            conn.commit()
        return {"ok": True, "version": ver}
    except Exception as e:
        logger.error("guardar_borrador: %s", e); return {"ok": False, "errores": [str(e)]}


def publicar(id_proceso, version, *, id_empresa=None) -> dict:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE bpd_versiones SET estado='publicado' WHERE id_proceso=%s AND "
                        "version=%s", (id_proceso, version))
            cur.execute("UPDATE bpd_procesos SET estado='publicado', version_actual=%s WHERE id=%s",
                        (version, id_proceso))
            conn.commit()
        return {"ok": True, "version": version}
    except Exception as e:
        return {"ok": False, "errores": [str(e)]}


def rollback(id_proceso, version, *, id_empresa=None) -> dict:
    """Vuelve a publicar una versión anterior (rollback de proceso publicado)."""
    v = obtener_version(id_proceso, version)
    if not v:
        return {"ok": False, "errores": ["versión inexistente"]}
    return publicar(id_proceso, version, id_empresa=id_empresa)


def obtener_version(id_proceso, version=None) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if version is None:
                cur.execute("SELECT * FROM bpd_versiones WHERE id_proceso=%s ORDER BY version DESC "
                            "LIMIT 1", (id_proceso,))
            else:
                cur.execute("SELECT * FROM bpd_versiones WHERE id_proceso=%s AND version=%s",
                            (id_proceso, version))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception:
        return None


def listar_procesos(id_empresa=None) -> list:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM bpd_procesos WHERE (id_empresa=%s OR id_empresa IS NULL) "
                        "ORDER BY actualizado DESC, id DESC", (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []


def definicion_de(version_row) -> dict:
    try:
        return json.loads((version_row or {}).get("definicion") or "{}")
    except Exception:
        return {}


__all__ = ["crear_proceso", "validar_definicion", "guardar_borrador", "publicar", "rollback",
           "obtener_version", "listar_procesos", "definicion_de"]
