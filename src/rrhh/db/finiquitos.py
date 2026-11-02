"""
Capa de datos: FINIQUITOS (`rrhh_finiquitos`, migr 0265). Multi-tenant. Mismo patrón CRUD y misma
disciplina `estado` (borrador|aprobada) que `src/rrhh/db/nominas.py` (`rrhh_nominas.estado`,
migr 0264) — un finiquito calculado nace SIEMPRE en 'borrador'; solo `aprobar_finiquito` (invocado
por la GUI tras verificar SUPERADMIN) lo pasa a 'aprobada'.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.finiquitos")

_PERMITIDOS = ("fecha_efectos", "total_bruto", "total_liquido", "conceptos", "ref_documento")


def crear_finiquito(id_empleado, id_empresa=None, **campos) -> int | None:
    """Crea un finiquito SIEMPRE en `estado='borrador'` (valor por defecto de la columna) —
    ningún camino de creación puede fijar `estado` directamente (solo `aprobar_finiquito` lo
    cambia), igual que `crear_nomina`."""
    id_empresa = id_empresa or empresa_actual_id()
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_finiquitos ({', '.join(cols)}) VALUES ({ph})", vals)
            fid = cur.lastrowid
            conn.commit()
        try:
            from src.services import eventos as _EV
            _EV.publicar("FINIQUITO_GENERADO", id_empresa=id_empresa, origen="rrhh",
                         ref_entidad="finiquito", ref_id=fid,
                         payload={"id_empleado": id_empleado,
                                  "fecha_efectos": campos.get("fecha_efectos")})
        except Exception:
            pass
        return fid
    except Exception as e:
        logger.error("crear_finiquito(emp=%s): %s", id_empleado, e)
        return None


def obtener_finiquito(id_finiquito, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_finiquitos WHERE id=%s AND id_empresa=%s",
                        (id_finiquito, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_finiquito(%s): %s", id_finiquito, e)
        return None


def listar_finiquitos(id_empleado, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_finiquitos WHERE id_empleado=%s AND id_empresa=%s "
                        "ORDER BY created_at DESC", (id_empleado, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_finiquitos(%s): %s", id_empleado, e)
        return []


def obtener_borrador_vigente(id_empleado, id_empresa=None) -> dict | None:
    """Último finiquito de este empleado que SIGUE en 'borrador' (el más reciente) — recalcular
    (pulsar «Calcular» otra vez) debe REFINAR ese mismo borrador en vez de amontonar filas nuevas
    en cada clic. Si el último finiquito del empleado ya está 'aprobada', devuelve None (nunca se
    pisa un finiquito ya aprobado: una nueva liquidación nace como fila nueva)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_finiquitos WHERE id_empleado=%s AND id_empresa=%s "
                        "ORDER BY created_at DESC LIMIT 1", (id_empleado, id_empresa))
            fila = _fila_a_dict(cur, cur.fetchone())
            return fila if fila and fila.get("estado") == "borrador" else None
    except Exception as e:
        logger.error("obtener_borrador_vigente(%s): %s", id_empleado, e)
        return None


def actualizar_finiquito(id_finiquito, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_finiquitos SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_finiquito, id_empresa))
            conn.commit()
            if cur.rowcount > 0:
                return True
            # rowcount==0 en MariaDB (sin CLIENT_FOUND_ROWS) puede significar "no encontrada" O
            # "encontrada pero con los MISMOS valores" (p.ej. recalcular un finiquito sin cambios
            # de fecha/importes) — se distingue comprobando si la fila sigue existiendo, para no
            # reportar como fallo un `calcular_y_guardar_borrador` que en realidad SÍ actualizó
            # (idempotentemente) el borrador vigente.
            cur.execute("SELECT 1 FROM rrhh_finiquitos WHERE id=%s AND id_empresa=%s",
                        (id_finiquito, id_empresa))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("actualizar_finiquito(%s): %s", id_finiquito, e)
        return False


def aprobar_finiquito(id_finiquito, id_empresa=None, aprobado_por=None) -> bool:
    """Único punto de escritura de `estado='aprobada'` — mismo espíritu que
    `vacaciones_servicio.aprobar` (transición explícita, nunca un UPDATE genérico vía
    `actualizar_finiquito`, que ni siquiera acepta `estado` en `_PERMITIDOS`). Solo aprueba desde
    'borrador' (evita reaprobar/perder `fecha_aprobacion` si se pulsa dos veces)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE rrhh_finiquitos SET estado='aprobada', aprobado_por=%s, "
                "fecha_aprobacion=NOW() WHERE id=%s AND id_empresa=%s AND estado='borrador'",
                (aprobado_por, id_finiquito, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            try:
                from src.services import eventos as _EV
                _EV.publicar("FINIQUITO_APROBADO", id_empresa=id_empresa, origen="rrhh",
                             ref_entidad="finiquito", ref_id=id_finiquito,
                             payload={"aprobado_por": aprobado_por})
            except Exception:
                pass
        return ok
    except Exception as e:
        logger.error("aprobar_finiquito(%s): %s", id_finiquito, e)
        return False


def eliminar_finiquito(id_finiquito, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_finiquitos WHERE id=%s AND id_empresa=%s",
                        (id_finiquito, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_finiquito(%s): %s", id_finiquito, e)
        return False
