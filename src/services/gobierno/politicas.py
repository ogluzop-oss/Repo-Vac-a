"""
Herencia de politicas (Paquete Enterprise 7, SUBFASE 7.8). Las politicas se definen a nivel de
empresa y se HEREDAN hacia todos los nodos, con posibilidad de sobrescribir localmente. La
resolucion sube por la ruta materializada: nodo → ancestros → empresa (el mas cercano gana).
"""

import logging

from src.services.gobierno import organigrama as _O

logger = logging.getLogger("gobierno.politicas")


def _emp(id_empresa=None):
    return _O._emp(id_empresa)


def set_politica(clave, valor, *, id_nodo=None, id_empresa=None) -> bool:
    """id_nodo=None → politica a nivel de EMPRESA (heredada por todos)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO org_politicas (id_empresa, id_nodo, clave, valor) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE valor=VALUES(valor)",
                        (emp, id_nodo, str(clave)[:60], str(valor)[:255]))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_politica: %s", e)
        return False


def obtener(clave, id_nodo=None, id_empresa=None):
    """Valor efectivo de una politica para un nodo, resolviendo herencia (mas cercano gana)."""
    emp = _emp(id_empresa)
    # Candidatos: el propio nodo, sus ancestros (mas cercano primero) y el nivel empresa (NULL).
    candidatos = []
    if id_nodo:
        candidatos.append(id_nodo)
        candidatos += [a["id"] for a in reversed(_O.ancestros(id_nodo, emp))]
    candidatos.append(None)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            for nid in candidatos:
                if nid is None:
                    cur.execute("SELECT valor FROM org_politicas WHERE id_empresa=%s AND id_nodo IS NULL "
                                "AND clave=%s", (emp, clave))
                else:
                    cur.execute("SELECT valor FROM org_politicas WHERE id_empresa=%s AND id_nodo=%s "
                                "AND clave=%s", (emp, nid, clave))
                r = cur.fetchone()
                if r:
                    return r[0] if not isinstance(r, dict) else r["valor"]
    except Exception as e:
        logger.error("obtener politica: %s", e)
    return None


def efectivas(id_nodo, id_empresa=None) -> dict:
    """Todas las politicas resueltas para un nodo (empresa + heredadas + locales)."""
    emp = _emp(id_empresa)
    claves = set()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT DISTINCT clave FROM org_politicas WHERE id_empresa=%s", (emp,))
            for r in cur.fetchall():
                claves.add(r[0] if not isinstance(r, dict) else r["clave"])
    except Exception:
        pass
    return {k: obtener(k, id_nodo, emp) for k in claves}
