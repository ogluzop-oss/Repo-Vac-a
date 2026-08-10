"""
Versionado LATERAL de entidades sincronizables (Fase 2, SUBFASE 2.8).

Aporta version/revision/autor/origen/timestamp/hash a CUALQUIER entidad sin modificar sus
tablas (tabla lateral `entidad_versiones`). Base para la resolucion de conflictos: nunca se
sobrescribe sin conocer la version.
"""

import hashlib
import logging

logger = logging.getLogger("distribucion.versionado")


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


def _hash(payload):
    if payload is None:
        return None
    try:
        import json
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    except Exception:
        return None


def registrar_version(entidad, entidad_id, *, autor=None, origen=None, payload=None,
                      id_empresa=None) -> dict | None:
    """Incrementa (o crea) la version de una entidad. Devuelve la version resultante."""
    emp = _emp(id_empresa)
    h = _hash(payload)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO entidad_versiones (id_empresa, entidad, entidad_id, version, revision, "
                "autor, origen, hash) VALUES (%s,%s,%s,1,0,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE version=version+1, revision=revision+1, "
                "autor=VALUES(autor), origen=VALUES(origen), hash=VALUES(hash)",
                (emp, str(entidad), str(entidad_id), autor, origen, h))
            c.commit()
    except Exception as e:
        logger.error("registrar_version(%s,%s): %s", entidad, entidad_id, e)
        return None
    return obtener_version(entidad, entidad_id, id_empresa=emp)


def obtener_version(entidad, entidad_id, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM entidad_versiones WHERE id_empresa=%s AND entidad=%s "
                        "AND entidad_id=%s", (emp, str(entidad), str(entidad_id)))
            r = _filas_a_dicts(cur, cur.fetchall())
            return r[0] if r else None
    except Exception as e:
        logger.error("obtener_version: %s", e)
        return None
