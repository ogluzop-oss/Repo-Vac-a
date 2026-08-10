"""
Escenarios del simulador (Paquete Enterprise 9, SUBFASE 9.2). Cada escenario es INDEPENDIENTE y
VIRTUAL: captura una foto de las metricas base (del Gemelo Digital) al crearse y guarda las
variables alteradas y los resultados calculados. NUNCA modifica produccion.
"""

import json
import logging

from src.services.simulador import base as B
from src.services.simulador import modelo as M

logger = logging.getLogger("simulador.escenarios")


def _emp(id_empresa=None):
    return B._emp(id_empresa)


def _dicts(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def crear(nombre, *, descripcion=None, usuario=None, id_empresa=None, base_metricas=None) -> int | None:
    """Crea un escenario capturando la foto base actual del Gemelo Digital."""
    emp = _emp(id_empresa)
    base_m = base_metricas or B.metricas_base(emp)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO sim_escenarios (id_empresa, usuario, nombre, descripcion, "
                        "estado, base_json) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, usuario, nombre[:160], (descripcion or "")[:255], M.BORRADOR,
                         json.dumps(base_m, default=str)))
            eid = cur.lastrowid
            c.commit()
            return eid
    except Exception as e:
        logger.error("crear escenario: %s", e)
        return None


def obtener(id_escenario, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM sim_escenarios WHERE id=%s AND id_empresa=%s",
                        (id_escenario, emp))
            r = _dicts(cur)
            if not r:
                return None
            esc = r[0]
            try:
                esc["base"] = json.loads(esc.get("base_json") or "{}")
            except Exception:
                esc["base"] = {}
            return esc
    except Exception as e:
        logger.error("obtener escenario: %s", e)
        return None


def listar(id_empresa=None, *, estado=None, limite=100) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        q = "SELECT id, nombre, descripcion, estado, confianza, usuario, creado FROM sim_escenarios WHERE id_empresa=%s"
        p = [emp]
        if estado:
            q += " AND estado=%s"; p.append(estado)
        q += " ORDER BY creado DESC LIMIT %s"; p.append(int(limite))
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            return _dicts(cur)
    except Exception as e:
        logger.error("listar escenarios: %s", e)
        return []


def marcar(id_escenario, estado, *, confianza=None, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if confianza:
                cur.execute("UPDATE sim_escenarios SET estado=%s, confianza=%s WHERE id=%s AND id_empresa=%s",
                            (estado, confianza, id_escenario, emp))
            else:
                cur.execute("UPDATE sim_escenarios SET estado=%s WHERE id=%s AND id_empresa=%s",
                            (estado, id_escenario, emp))
            c.commit()
            return True
    except Exception as e:
        logger.debug("marcar escenario: %s", e)
        return False


def eliminar(id_escenario, id_empresa=None) -> bool:
    """Borra el escenario y su contenido virtual. No afecta a ningun dato real."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM sim_resultados WHERE id_escenario=%s AND id_empresa=%s", (id_escenario, emp))
            cur.execute("DELETE FROM sim_variables WHERE id_escenario=%s AND id_empresa=%s", (id_escenario, emp))
            cur.execute("DELETE FROM sim_escenarios WHERE id=%s AND id_empresa=%s", (id_escenario, emp))
            c.commit()
            return True
    except Exception as e:
        logger.debug("eliminar escenario: %s", e)
        return False
