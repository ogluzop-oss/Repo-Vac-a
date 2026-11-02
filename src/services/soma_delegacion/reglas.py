"""CRUD de reglas de delegación (`soma_delegaciones`). Multiempresa, sin Qt."""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("soma_delegacion.reglas")

MODOS_APLICACION = ("automatico", "revisar_antes")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def crear_regla(tipo, instrucciones, *, modo_aplicacion="revisar_antes", activa=True,
                creado_por=None, id_empresa=None) -> int | None:
    """Crea una regla de delegación. `instrucciones` es OBLIGATORIO y no puede quedar vacío —
    es precisamente lo que el encargo exige: el SUPERADMIN SIEMPRE debe definir cómo debe
    proceder SOMA antes de poder delegarle nada."""
    from src.services.soma_delegacion import catalogo
    if not catalogo.obtener(tipo):
        logger.warning("crear_regla: tipo desconocido %s", tipo)
        return None
    instrucciones = (instrucciones or "").strip()
    if not instrucciones:
        return None
    if modo_aplicacion not in MODOS_APLICACION:
        modo_aplicacion = "revisar_antes"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_delegaciones (id_empresa, tipo, instrucciones, modo_aplicacion, "
                "activa, creado_por) VALUES (%s,%s,%s,%s,%s,%s)",
                (_emp(id_empresa), tipo, instrucciones, modo_aplicacion, 1 if activa else 0,
                 creado_por))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_regla: %s", e)
        return None


def listar_reglas(id_empresa=None, *, tipo=None, solo_activas=False) -> list:
    filtros, params = ["id_empresa=%s"], [_emp(id_empresa)]
    if tipo:
        filtros.append("tipo=%s"); params.append(tipo)
    if solo_activas:
        filtros.append("activa=1")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM soma_delegaciones WHERE " + " AND ".join(filtros) +
                        " ORDER BY creado DESC", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_reglas: %s", e)
        return []


def obtener_regla(id_regla, id_empresa=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM soma_delegaciones WHERE id=%s AND id_empresa=%s",
                        (id_regla, _emp(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_regla: %s", e)
        return None


def actualizar_regla(id_regla, id_empresa=None, *, instrucciones=None, modo_aplicacion=None,
                     activa=None) -> bool:
    sets, params = [], []
    if instrucciones is not None:
        instrucciones = instrucciones.strip()
        if not instrucciones:
            return False   # nunca se permite vaciar las instrucciones de una regla existente
        sets.append("instrucciones=%s"); params.append(instrucciones)
    if modo_aplicacion is not None and modo_aplicacion in MODOS_APLICACION:
        sets.append("modo_aplicacion=%s"); params.append(modo_aplicacion)
    if activa is not None:
        sets.append("activa=%s"); params.append(1 if activa else 0)
    if not sets:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE soma_delegaciones SET {', '.join(sets)} WHERE id=%s AND id_empresa=%s",
                        (*params, id_regla, _emp(id_empresa)))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("actualizar_regla: %s", e)
        return False


def eliminar_regla(id_regla, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM soma_delegaciones WHERE id=%s AND id_empresa=%s",
                        (id_regla, _emp(id_empresa)))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_regla: %s", e)
        return False
