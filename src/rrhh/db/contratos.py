"""
Capa de datos: HISTORIAL CONTRACTUAL (`rrhh_contratos`) — F4.1.2. Multi-tenant.

Contratos, renovaciones, modificaciones y anexos vinculados al expediente del
trabajador. Patrón CRUD idéntico a db.centros.
"""

import datetime as _dt
import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.contratos")

_PERMITIDOS = (
    "tipo_registro", "modalidad", "fecha_inicio", "fecha_fin", "salario",
    "jornada", "id_centro", "ref_documento", "datos_snapshot", "estado",
    # Fase B (RRHH — Contratos: IRPF/modelo de pago/bolsa de horas; el IRPF NO vive aquí,
    # vive en `rrhh_datos_fiscales` — Fase B2, deliberadamente fuera de esta tabla):
    "modelo_pago", "tarifa_hora",
    "bolsa_horas_activa", "bolsa_horas_vigencia_meses", "bolsa_horas_compensacion",
    "bolsa_horas_plus_disponibilidad", "bolsa_horas_periodo_regularizacion_meses",
    "firmado", "fecha_firma",
    "complemento_it_activo", "complemento_it_tipo", "complemento_it_porcentaje",
    "complemento_it_tramo_dias_inicio", "complemento_it_tramo_dias_fin",
)


def crear_contrato(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_contratos ({', '.join(cols)}) VALUES ({ph})", vals)
            cid = cur.lastrowid
            conn.commit()
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("CONTRATO_GENERADO", id_empresa=id_empresa, origen="rrhh",
                         ref_entidad="contrato", ref_id=cid,
                         payload={"id_empleado": id_empleado, "modalidad": datos.get("modalidad")})
        except Exception:
            pass
        return cid
    except Exception as e:
        logger.error("crear_contrato(emp=%s): %s", id_empleado, e)
        return None


def obtener_contrato(id_contrato, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_contratos WHERE id=%s AND id_empresa=%s",
                        (id_contrato, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_contrato(%s): %s", id_contrato, e)
        return None


def listar_contratos(id_empleado, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_contratos WHERE id_empleado=%s AND id_empresa=%s "
                        "ORDER BY fecha_inicio DESC, id DESC", (id_empleado, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_contratos(%s): %s", id_empleado, e)
        return []


def actualizar_contrato(id_contrato, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_contratos SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_contrato, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_contrato(%s): %s", id_contrato, e)
        return False


def marcar_firmado(id_contrato, id_empresa=None, creado_por=None) -> bool:
    """Marca el contrato como firmado (`firmado=1`, `fecha_firma=ahora`) y, si la cláusula
    de bolsa de horas está activa (`bolsa_horas_activa=1`), crea automáticamente la fila de
    seguimiento en `rrhh_bolsa_horas` (Fase A). Derivación de fechas — todas calculadas por
    el propio servidor MariaDB vía `DATE_ADD` (que ya resuelve correctamente el desborde de
    fin de mes, p. ej. firmar un 31 de enero con vigencia de 1 mes cae a 28/29 de febrero):
      - `fecha_inicio_vigencia` = fecha de la firma (solo la parte de fecha).
      - `fecha_fin_vigencia` = `fecha_inicio_vigencia` + `bolsa_horas_vigencia_meses` meses.
      - `fecha_regularizacion_limite` = `fecha_fin_vigencia` +
        `bolsa_horas_periodo_regularizacion_meses` meses (el plazo que la Fase G vigila para
        avisar del riesgo de perder/deber las horas si vence sin compensar).
    `horas_diarias` nace NULL — la asigna más tarde un admin/superadmin desde Horarios
    (Fase E, botón "Definir horas diarias de trabajo").
    Idempotente: si el contrato ya estaba firmado, no reinserta una segunda fila de bolsa de
    horas (devuelve True sin tocar nada, igual que si acabara de firmarlo)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT firmado, bolsa_horas_activa, bolsa_horas_vigencia_meses, "
                "bolsa_horas_periodo_regularizacion_meses, id_empleado "
                "FROM rrhh_contratos WHERE id=%s AND id_empresa=%s",
                (id_contrato, id_empresa))
            fila = _fila_a_dict(cur, cur.fetchone())
            if not fila:
                return False
            if fila.get("firmado"):
                return True  # ya firmado: idempotente, no duplica la fila de bolsa de horas
            ahora = _dt.datetime.now()
            cur.execute(
                "UPDATE rrhh_contratos SET firmado=1, fecha_firma=%s WHERE id=%s AND id_empresa=%s",
                (ahora, id_contrato, id_empresa))
            ok = cur.rowcount > 0
            if ok and fila.get("bolsa_horas_activa"):
                vig = int(fila.get("bolsa_horas_vigencia_meses") or 12)
                reg = int(fila.get("bolsa_horas_periodo_regularizacion_meses") or 12)
                cur.execute(
                    "INSERT INTO rrhh_bolsa_horas "
                    "(id_empresa, id_empleado, id_contrato, horas_diarias, "
                    " fecha_inicio_vigencia, fecha_fin_vigencia, fecha_regularizacion_limite, "
                    " creado_por, fecha_creacion) "
                    "VALUES (%s, %s, %s, NULL, DATE(%s), "
                    " DATE_ADD(DATE(%s), INTERVAL %s MONTH), "
                    " DATE_ADD(DATE_ADD(DATE(%s), INTERVAL %s MONTH), INTERVAL %s MONTH), "
                    " %s, %s)",
                    (id_empresa, fila["id_empleado"], id_contrato,
                     ahora, ahora, vig, ahora, vig, reg, creado_por, ahora))
            conn.commit()
            return ok
    except Exception as e:
        logger.error("marcar_firmado(%s): %s", id_contrato, e)
        return False


def nuevas_altas_indefinidas(anio, id_empresa=None) -> list[dict]:
    """Empleados con una nueva contratación INDEFINIDA iniciada en `anio` (para la Calculadora Fiscal
    de Contabilidad). `modalidad IS NULL` cuenta como indefinido — misma normalización por defecto que
    usa `rrhh.documents.render.render_contrato` (`(subtipo or "INDEFINIDO").upper()`). Devuelve
    también `fecha_nacimiento`/`discapacidad_pct` de cada empleado para poder clasificar bonificados
    (menores de 30 años o discapacidad ≥33%) sin una segunda consulta."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id AS id_contrato, c.id_empleado, c.fecha_inicio, "
                "e.fecha_nacimiento, e.discapacidad_pct "
                "FROM rrhh_contratos c JOIN rrhh_empleados e "
                "ON e.id=c.id_empleado AND e.id_empresa=c.id_empresa "
                "WHERE c.id_empresa=%s AND c.estado='vigente' AND YEAR(c.fecha_inicio)=%s "
                "AND (UPPER(c.modalidad) LIKE 'INDEFINIDO%%' OR c.modalidad IS NULL)",
                (id_empresa, int(anio)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("nuevas_altas_indefinidas(%s): %s", anio, e)
        return []


def eliminar_contrato(id_contrato, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_contratos WHERE id=%s AND id_empresa=%s",
                        (id_contrato, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_contrato(%s): %s", id_contrato, e)
        return False
