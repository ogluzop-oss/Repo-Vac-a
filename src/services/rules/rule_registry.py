"""Registro de reglas (Fase III · B5) — CRUD sobre `rules` (condiciones/acciones en JSON)."""

import json
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("rules.registry")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def crear_regla(nombre, *, evento=None, condiciones=None, acciones=None, prioridad=100,
                id_empresa=None, usuario=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO rules (id_empresa, nombre, evento, condiciones, acciones, "
                        "prioridad, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, nombre, evento, json.dumps(condiciones or []),
                         json.dumps(acciones or []), int(prioridad), usuario))
            rid = cur.lastrowid
            conn.commit()
            return rid
    except Exception as e:
        logger.error("crear_regla(%s): %s", nombre, e)
        return None


def listar_reglas(id_empresa=None, *, evento=None, solo_activas=True) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM rules WHERE id_empresa=%s"
    p = [id_empresa]
    if evento:
        q += " AND evento=%s"; p.append(evento)
    if solo_activas:
        q += " AND activo=1"
    q += " ORDER BY prioridad, id"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            filas = _filas_a_dicts(cur, cur.fetchall())
        for f in filas:
            f["condiciones"] = _json(f.get("condiciones"))
            f["acciones"] = _json(f.get("acciones"))
        return filas
    except Exception as e:
        logger.debug("listar_reglas: %s", e)
        return []


def activar(id_regla, activo=True) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE rules SET activo=%s, actualizado=NOW() WHERE id=%s",
                        (1 if activo else 0, id_regla))
            conn.commit()
            return True
    except Exception as e:
        logger.error("activar(%s): %s", id_regla, e)
        return False


def _json(v):
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v) if v else []
    except Exception:
        return []
