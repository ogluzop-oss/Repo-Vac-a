"""
CRUD de reglas de precio dinámico. `params` se guarda como JSON (dict de condición según `tipo`).
Multiempresa; `id_tienda` vacío = la regla aplica a TODAS las tiendas de la empresa.
"""

import json
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("precio_dinamico.reglas")

TIPOS = ("horario", "stock", "caducidad")
AJUSTES = ("pct", "fijo")


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _tid(valor):
    """Coacciona `id_tienda` a la convención INT unificada (migr 0192): None/'' = TODAS las tiendas
    (NULL); cualquier otro valor (código 'ALMC' incluido) al entero canónico (código no numérico → 0)."""
    if valor is None or valor == "":
        return None
    from src.db.empresa import tienda_actual_id_int
    return tienda_actual_id_int(valor)


def crear_regla(nombre, tipo, params, ajuste_tipo="pct", ajuste_valor=0, prioridad=0,
                id_tienda=None, id_empresa=None):
    nombre = (nombre or "").strip()
    if not nombre or tipo not in TIPOS or ajuste_tipo not in AJUSTES:
        return None
    pj = json.dumps(params) if isinstance(params, (dict, list)) else (params or "{}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO precio_reglas (id_empresa,id_tienda,nombre,tipo,params,ajuste_tipo,"
                "ajuste_valor,prioridad) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (_empresa(id_empresa), _tid(id_tienda), nombre, tipo, pj, ajuste_tipo,
                 float(ajuste_valor), int(prioridad)))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_regla: %s", e)
        return None


def listar_reglas(id_empresa=None, solo_activas=False, id_tienda=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM precio_reglas WHERE id_empresa=%s"
            params = [_empresa(id_empresa)]
            if solo_activas:
                q += " AND activo=1"
            if id_tienda is not None:
                # NULL = regla global (todas las tiendas); si no, la tienda concreta.
                q += " AND (id_tienda=%s OR id_tienda IS NULL)"
                params.append(_tid(id_tienda))
            q += " ORDER BY prioridad DESC, id"
            cur.execute(q, tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_reglas: %s", e)
        return []


def obtener_regla(id_regla, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM precio_reglas WHERE id=%s AND id_empresa=%s",
                        (id_regla, _empresa(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_regla: %s", e)
        return None


def actualizar_regla(id_regla, id_empresa=None, **campos):
    permitidos = ("nombre", "tipo", "params", "ajuste_tipo", "ajuste_valor", "prioridad", "activo",
                  "id_tienda")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if "params" in datos and isinstance(datos["params"], (dict, list)):
        datos["params"] = json.dumps(datos["params"])
    if "id_tienda" in datos:
        datos["id_tienda"] = _tid(datos["id_tienda"])   # convención INT/NULL (migr 0192)
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE precio_reglas SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_regla, _empresa(id_empresa)))
            return True
    except Exception as e:
        logger.error("actualizar_regla: %s", e)
        return False


def eliminar_regla(id_regla, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM precio_reglas WHERE id=%s AND id_empresa=%s",
                        (id_regla, _empresa(id_empresa)))
            return True
    except Exception as e:
        logger.error("eliminar_regla: %s", e)
        return False
