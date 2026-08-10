"""
Organigrama empresarial (Paquete Enterprise 7, SUBFASE 7.1/7.6). Modelo jerarquico completo
(grupo → empresa → central → zona → delegacion → tienda → departamento → empleado) con RUTA
MATERIALIZADA para consultas de subarbol/ancestros eficientes (SUBFASE 7.12). Solo modelo/backend.
"""

import json
import logging

logger = logging.getLogger("gobierno.organigrama")

TIPOS = ("grupo", "empresa", "central", "zona", "delegacion", "tienda", "almacen",
         "departamento", "empleado")


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


def _dicts(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def crear_nodo(tipo, nombre, *, padre_id=None, id_ref=None, datos=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    nivel, ruta_padre = 0, "/"
    if padre_id:
        p = obtener(padre_id, emp)
        if p:
            nivel = int(p["nivel"]) + 1
            ruta_padre = p["ruta"]
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO org_nodos (id_empresa, tipo, nombre, padre_id, nivel, ruta, "
                        "id_ref, datos) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, tipo, nombre, padre_id, nivel, ruta_padre, id_ref,
                         json.dumps(datos, default=str) if datos else None))
            nid = cur.lastrowid
            cur.execute("UPDATE org_nodos SET ruta=%s WHERE id=%s", (f"{ruta_padre}{nid}/", nid))
            c.commit()
            return nid
    except Exception as e:
        logger.error("crear_nodo: %s", e)
        return None


def obtener(id_nodo, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM org_nodos WHERE id=%s AND id_empresa=%s", (id_nodo, emp))
            r = _dicts(cur)
            return r[0] if r else None
    except Exception as e:
        logger.error("obtener nodo: %s", e)
        return None


def listar(id_empresa=None, *, tipo=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        q = "SELECT * FROM org_nodos WHERE id_empresa=%s"
        p = [emp]
        if tipo:
            q += " AND tipo=%s"; p.append(tipo)
        q += " ORDER BY ruta"
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            return _dicts(cur)
    except Exception as e:
        logger.error("listar nodos: %s", e)
        return []


def hijos(id_nodo, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM org_nodos WHERE id_empresa=%s AND padre_id=%s ORDER BY nombre",
                        (emp, id_nodo))
            return _dicts(cur)
    except Exception:
        return []


def subarbol(id_nodo, id_empresa=None) -> list:
    """Todos los descendientes (ruta LIKE '/…/id/%'). Consulta indexada, sin recorrer todo."""
    emp = _emp(id_empresa)
    n = obtener(id_nodo, emp)
    if not n:
        return []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM org_nodos WHERE id_empresa=%s AND ruta LIKE %s ORDER BY ruta",
                        (emp, n["ruta"] + "%"))
            return _dicts(cur)
    except Exception:
        return []


def ancestros(id_nodo, id_empresa=None) -> list:
    """Nodos padre a lo largo de la ruta materializada (de la raiz al padre)."""
    emp = _emp(id_empresa)
    n = obtener(id_nodo, emp)
    if not n:
        return []
    ids = [int(x) for x in n["ruta"].strip("/").split("/") if x and int(x) != int(id_nodo)]
    if not ids:
        return []
    try:
        from src.db.conexion import obtener_conexion
        marcas = ",".join(["%s"] * len(ids))
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"SELECT * FROM org_nodos WHERE id_empresa=%s AND id IN ({marcas}) ORDER BY nivel",
                        (emp, *ids))
            return _dicts(cur)
    except Exception:
        return []


def raiz(id_empresa=None) -> dict | None:
    r = listar(id_empresa)
    return next((n for n in r if n["nivel"] == 0), (r[0] if r else None))


def mapa(id_empresa=None) -> list:
    """Estructura completa ordenada por ruta (SUBFASE 7.6, backend del mapa corporativo)."""
    return [{"id": n["id"], "tipo": n["tipo"], "nombre": n["nombre"], "nivel": n["nivel"],
             "padre_id": n["padre_id"], "ruta": n["ruta"], "estado": n["estado"]}
            for n in listar(id_empresa)]
