"""
Capa de datos: HISTORIAL SALARIAL (`rrhh_nominas`) — F4.1.2. Multi-tenant.

Nóminas generadas por empleado/período (anio+mes único por empresa). Patrón CRUD.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.nominas")

_PERMITIDOS = ("anio", "mes", "fecha", "bruto", "base", "irpf_pct", "irpf_importe",
               "ss_pct", "ss_importe", "neto", "conceptos", "ref_documento")


def crear_nomina(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    if not campos.get("anio") or not campos.get("mes"):
        logger.warning("crear_nomina: anio y mes obligatorios")
        return None
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_nominas ({', '.join(cols)}) VALUES ({ph})", vals)
            nid = cur.lastrowid
            conn.commit()
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("NOMINA_GENERADA", id_empresa=id_empresa, origen="rrhh",
                         ref_entidad="nomina", ref_id=nid,
                         payload={"id_empleado": id_empleado,
                                  "anio": campos.get("anio"), "mes": campos.get("mes")})
        except Exception:
            pass
        return nid
    except Exception as e:
        logger.error("crear_nomina(emp=%s): %s", id_empleado, e)
        return None


def obtener_nomina(id_nomina, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_nominas WHERE id=%s AND id_empresa=%s",
                        (id_nomina, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_nomina(%s): %s", id_nomina, e)
        return None


def listar_nominas(id_empleado, id_empresa=None, anio=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empleado=%s", "id_empresa=%s"], [id_empleado, id_empresa]
    if anio:
        filtros.append("anio=%s"); params.append(int(anio))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_nominas WHERE " + " AND ".join(filtros)
                        + " ORDER BY anio DESC, mes DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_nominas(%s): %s", id_empleado, e)
        return []


def actualizar_nomina(id_nomina, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_nominas SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_nomina, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_nomina(%s): %s", id_nomina, e)
        return False


def aprobar_nomina(id_nomina, id_empresa=None, aprobado_por=None) -> bool:
    """Único punto de escritura de `estado='aprobada'` (columna añadida en migr 0264, `estado
    VARCHAR(12) DEFAULT 'borrador'`). `estado` NO está en `_PERMITIDOS`/`actualizar_nomina` a
    propósito: la transición borrador→aprobada tiene su propia función explícita (mismo criterio
    que `vacaciones_servicio.aprobar`/`finiquitos.aprobar_finiquito`), nunca un UPDATE genérico.
    Solo aprueba desde 'borrador' (evita perder trazabilidad si se pulsa dos veces).

    Auditoría (sesión finiquitos): esta función NO existía — el comentario de
    `nomina_servicio.generar_borradores_mes_cerrado` ("un humano cambia estado a 'aprobada' desde
    el listado de nóminas del expediente del empleado") describía un flujo que aún no estaba
    cableado en ningún sitio. Se añade aquí para dejarlo realmente operativo (GUI:
    `rrhh_gestion.ExpedienteDialog._tab_nominas`)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE rrhh_nominas SET estado='aprobada' WHERE id=%s AND id_empresa=%s "
                "AND estado='borrador'", (id_nomina, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            try:
                from src.services import eventos as _EV
                _EV.publicar("NOMINA_APROBADA", id_empresa=id_empresa, origen="rrhh",
                             ref_entidad="nomina", ref_id=id_nomina,
                             payload={"aprobado_por": aprobado_por})
            except Exception:
                pass
        return ok
    except Exception as e:
        logger.error("aprobar_nomina(%s): %s", id_nomina, e)
        return False


def eliminar_nomina(id_nomina, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_nominas WHERE id=%s AND id_empresa=%s",
                        (id_nomina, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_nomina(%s): %s", id_nomina, e)
        return False
