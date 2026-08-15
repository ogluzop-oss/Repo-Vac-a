"""
RRHH PRO (Módulo 8, enriquecimiento). Añade SOLO lo ausente tras la auditoría del paquete src/rrhh
(que ya cubre empleados, ausencias, fichajes, nómina, vacaciones, contratos, documentos, firma y
portal): evaluación de desempeño, formación/capacitación, selección/candidatos (ATS ligero) y
planificación de turnos de personal. Multiempresa, auditado, sin duplicar nada del paquete rrhh.
"""

import json
import logging

logger = logging.getLogger("rrhh.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.rrhh.identidad_rrhh import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _tid(valor):
    """Coacciona id_tienda a la convención INT unificada (migr 0195): None/'' = sin tienda (NULL); el
    resto (código 'ALMC' incluido) al entero canónico (código no numérico → 0)."""
    if valor is None or valor == "":
        return None
    from src.db.empresa import tienda_actual_id_int
    return tienda_actual_id_int(valor)


def _audit(accion, detalle, tabla):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("rrhh", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Evaluación de desempeño ──────────────────────────────────────────────────
def crear_evaluacion(id_empleado, *, periodo=None, evaluador=None, competencias=None,
                     objetivos=None, comentarios=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_evaluaciones (id_empresa, id_empleado, periodo, evaluador, "
                        "competencias, objetivos, comentarios) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_empleado, periodo, evaluador,
                         json.dumps(competencias or {}, ensure_ascii=False, default=str),
                         json.dumps(objetivos or [], ensure_ascii=False, default=str), comentarios))
            eid = cur.lastrowid
            c.commit()
        _audit("EVAL_CREADA", f"{eid}:emp{id_empleado} {periodo}", "rrhh_evaluaciones")
        return eid
    except Exception as e:
        logger.error("crear_evaluacion: %s", e)
        return None


def cerrar_evaluacion(id_evaluacion, *, id_empresa=None) -> dict:
    """Cierra la evaluación calculando la puntuación media de las competencias (0-100)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT competencias FROM rrhh_evaluaciones WHERE id=%s", (id_evaluacion,))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "no existe"}
            raw = r[0] if not isinstance(r, dict) else list(r.values())[0]
            try:
                comp = json.loads(raw or "{}")
                vals = [float(v) for v in comp.values() if isinstance(v, (int, float, str)) and str(v).strip()]
                punt = round(sum(vals) / len(vals), 2) if vals else None
            except Exception:
                punt = None
            cur.execute("UPDATE rrhh_evaluaciones SET puntuacion=%s, estado='CERRADA', cerrado=NOW() "
                        "WHERE id=%s", (punt, id_evaluacion))
            c.commit()
        _audit("EVAL_CERRADA", f"{id_evaluacion}:{punt}", "rrhh_evaluaciones")
        return {"ok": True, "puntuacion": punt}
    except Exception as e:
        logger.error("cerrar_evaluacion: %s", e)
        return {"ok": False, "motivo": str(e)}


def evaluaciones(id_empresa=None, *, id_empleado=None, periodo=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM rrhh_evaluaciones WHERE id_empresa<=>%s"; p = [emp]
            if id_empleado is not None:
                q += " AND id_empleado=%s"; p.append(id_empleado)
            if periodo:
                q += " AND periodo=%s"; p.append(periodo)
            q += " ORDER BY creado DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("evaluaciones: %s", e)
        return []


# ── Formación / capacitación ─────────────────────────────────────────────────
def crear_formacion(titulo, *, tipo="curso", proveedor=None, horas=0, coste=0, fecha_inicio=None,
                    fecha_fin=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_formacion (id_empresa, titulo, tipo, proveedor, horas, coste, "
                        "fecha_inicio, fecha_fin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, titulo[:160], tipo, proveedor, float(horas or 0), float(coste or 0),
                         fecha_inicio, fecha_fin))
            fid = cur.lastrowid
            c.commit()
        _audit("FORMACION_CREADA", f"{fid}:{titulo}", "rrhh_formacion")
        return fid
    except Exception as e:
        logger.error("crear_formacion: %s", e)
        return None


def inscribir_formacion(id_formacion, id_empleado) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_formacion_asistentes (id_formacion, id_empleado) VALUES (%s,%s)",
                        (id_formacion, id_empleado))
            c.commit()
        _audit("FORMACION_INSCRITO", f"form{id_formacion} emp{id_empleado}", "rrhh_formacion_asistentes")
        return {"ok": True}
    except Exception as e:
        logger.error("inscribir_formacion: %s", e)
        return {"ok": False, "motivo": str(e)}


def registrar_aprovechamiento(id_formacion, id_empleado, aprovechamiento) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE rrhh_formacion_asistentes SET aprovechamiento=%s, estado='COMPLETADO' "
                        "WHERE id_formacion=%s AND id_empleado=%s",
                        (float(aprovechamiento), id_formacion, id_empleado))
            c.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("registrar_aprovechamiento: %s", e)
        return {"ok": False, "motivo": str(e)}


def formaciones(id_empresa=None, *, estado=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM rrhh_formacion WHERE id_empresa<=>%s"; p = [emp]
            if estado:
                q += " AND estado=%s"; p.append(estado)
            q += " ORDER BY COALESCE(fecha_inicio, creado) DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("formaciones: %s", e)
        return []


# ── Selección / candidatos (ATS ligero) ─────────────────────────────────────
_FASES = ("RECIBIDO", "CRIBADO", "ENTREVISTA", "OFERTA", "CONTRATADO", "DESCARTADO")


def registrar_candidato(nombre, *, vacante=None, email=None, telefono=None, cv_ruta=None,
                        id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_seleccion_candidatos (id_empresa, vacante, nombre, email, "
                        "telefono, cv_ruta) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, vacante, nombre[:160], email, telefono, cv_ruta))
            cid = cur.lastrowid
            c.commit()
        _audit("CANDIDATO_ALTA", f"{cid}:{nombre} vac{vacante}", "rrhh_seleccion_candidatos")
        return cid
    except Exception as e:
        logger.error("registrar_candidato: %s", e)
        return None


def mover_fase_candidato(id_candidato, fase, *, valoracion=None, notas=None) -> dict:
    if fase not in _FASES:
        return {"ok": False, "motivo": "fase inválida"}
    sets, params = ["fase=%s", "actualizado=NOW()"], [fase]
    if valoracion is not None:
        sets.append("valoracion=%s"); params.append(float(valoracion))
    if notas is not None:
        sets.append("notas=%s"); params.append(notas)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"UPDATE rrhh_seleccion_candidatos SET {', '.join(sets)} WHERE id=%s",
                        (*params, id_candidato))
            c.commit()
        _audit("CANDIDATO_FASE", f"{id_candidato}:{fase}", "rrhh_seleccion_candidatos")
        return {"ok": True}
    except Exception as e:
        logger.error("mover_fase_candidato: %s", e)
        return {"ok": False, "motivo": str(e)}


def candidatos(id_empresa=None, *, vacante=None, fase=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM rrhh_seleccion_candidatos WHERE id_empresa<=>%s"; p = [emp]
            if vacante:
                q += " AND vacante=%s"; p.append(vacante)
            if fase:
                q += " AND fase=%s"; p.append(fase)
            q += " ORDER BY creado DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("candidatos: %s", e)
        return []


# ── Planificación de turnos de personal ──────────────────────────────────────
def planificar_turno(id_empleado, fecha, *, hora_inicio=None, hora_fin=None, rol=None,
                     id_tienda=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_turnos_plan (id_empresa, id_tienda, id_empleado, fecha, "
                        "hora_inicio, hora_fin, rol) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, _tid(id_tienda), id_empleado, fecha, hora_inicio, hora_fin, rol))
            tid = cur.lastrowid
            c.commit()
        _audit("TURNO_PLANIFICADO", f"{tid}:emp{id_empleado} {fecha}", "rrhh_turnos_plan")
        return tid
    except Exception as e:
        logger.error("planificar_turno: %s", e)
        return None


def cuadrante(fecha_desde, fecha_hasta, *, id_tienda=None, id_empleado=None, id_empresa=None) -> list:
    """Devuelve el cuadrante de turnos planificados en el rango (para la vista de planificación)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT * FROM rrhh_turnos_plan WHERE id_empresa<=>%s AND fecha BETWEEN %s AND %s")
            p = [emp, fecha_desde, fecha_hasta]
            if id_tienda is not None:
                q += " AND id_tienda<=>%s"; p.append(_tid(id_tienda))
            if id_empleado is not None:
                q += " AND id_empleado=%s"; p.append(id_empleado)
            q += " ORDER BY fecha, hora_inicio"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("cuadrante: %s", e)
        return []
