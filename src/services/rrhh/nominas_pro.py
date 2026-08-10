"""
Nóminas PRO (Módulo 10, enriquecimiento). Añade SOLO lo ausente sobre el motor de nómina existente
(`src/rrhh/nomina_motor.py` + `nomina_servicio.py`), que ya cubre el cálculo completo (conceptos,
bases, SS trabajador/empresa, IRPF, PDF):
  · Gestión de ANTICIPOS (solicitud → aprobación → amortización por cuotas que alimenta el campo
    `anticipos` de la nómina).
  · CONCEPTOS RECURRENTES por empleado (retribución flexible / pluses fijos) que se inyectan en los
    `datos` antes de `construir_input`.
  · Informe COSTE-EMPRESA (agrega el `ss_empresa` que el motor YA calcula, no reportado hasta ahora).
Reutiliza el motor; NO recalcula SS ni IRPF por su cuenta. Multiempresa, auditado. Sin duplicación.
"""

import logging

logger = logging.getLogger("nominas.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.rrhh.identidad_rrhh import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="rrhh_anticipos"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("nominas", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Anticipos ────────────────────────────────────────────────────────────────
def solicitar_anticipo(id_empleado, importe_total, *, cuotas=1, motivo=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    importe_total = round(float(importe_total or 0), 2)
    cuotas = max(1, int(cuotas or 1))
    cuota = round(importe_total / cuotas, 2)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_anticipos (id_empresa, id_empleado, importe_total, cuotas, "
                        "importe_cuota, pendiente, motivo) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_empleado, importe_total, cuotas, cuota, importe_total, motivo))
            aid = cur.lastrowid
            c.commit()
        _audit("ANTICIPO_SOLICITADO", f"{aid}:emp{id_empleado} {importe_total}€ x{cuotas}")
        # Aprobación opcional vía Workflow (no bloqueante).
        try:
            from src.services.workflow import workflow_engine
            workflow_engine.iniciar_proceso("rrhh_anticipo", aid,
                                            contexto={"importe": importe_total}, id_empresa=emp)
        except Exception:
            pass
        return aid
    except Exception as e:
        logger.error("solicitar_anticipo: %s", e)
        return None


def aprobar_anticipo(id_anticipo, *, aprobado_por=None, id_empresa=None) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE rrhh_anticipos SET estado='VIGENTE', aprobado_por=%s, actualizado=NOW() "
                        "WHERE id=%s AND estado='SOLICITADO'", (aprobado_por, id_anticipo))
            afectadas = cur.rowcount
            c.commit()
        _audit("ANTICIPO_APROBADO", f"{id_anticipo}:{aprobado_por}")
        return {"ok": afectadas > 0}
    except Exception as e:
        logger.error("aprobar_anticipo: %s", e)
        return {"ok": False, "motivo": str(e)}


def cuota_anticipo_pendiente(id_empleado, *, id_empresa=None) -> float:
    """Importe total de cuotas de anticipo a descontar en la próxima nómina (anticipos VIGENTES)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(LEAST(importe_cuota, pendiente)),0) FROM rrhh_anticipos "
                        "WHERE id_empresa<=>%s AND id_empleado=%s AND estado='VIGENTE' AND pendiente>0",
                        (emp, id_empleado))
            r = cur.fetchone()
            return round(float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0), 2)
    except Exception as e:
        logger.error("cuota_anticipo_pendiente: %s", e)
        return 0.0


def amortizar_anticipos(id_empleado, *, id_empresa=None) -> dict:
    """Aplica una cuota a cada anticipo VIGENTE del empleado (al confirmar la nómina). Devuelve total
    amortizado. Marca LIQUIDADO cuando el pendiente llega a 0."""
    emp = _emp(id_empresa)
    total = 0.0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, importe_cuota, pendiente FROM rrhh_anticipos WHERE id_empresa<=>%s "
                        "AND id_empleado=%s AND estado='VIGENTE' AND pendiente>0", (emp, id_empleado))
            for row in _filas(cur):
                cuota = min(float(row["importe_cuota"] or 0), float(row["pendiente"] or 0))
                nuevo = round(float(row["pendiente"] or 0) - cuota, 2)
                total += cuota
                estado = "LIQUIDADO" if nuevo <= 0.001 else "VIGENTE"
                cur.execute("UPDATE rrhh_anticipos SET pendiente=%s, estado=%s, actualizado=NOW() "
                            "WHERE id=%s", (max(0.0, nuevo), estado, row["id"]))
            c.commit()
        total = round(total, 2)
        _audit("ANTICIPO_AMORTIZADO", f"emp{id_empleado} {total}€")
        return {"ok": True, "amortizado": total}
    except Exception as e:
        logger.error("amortizar_anticipos: %s", e)
        return {"ok": False, "motivo": str(e)}


def anticipos_empleado(id_empleado, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_anticipos WHERE id_empresa<=>%s AND id_empleado=%s "
                        "ORDER BY creado DESC", (emp, id_empleado))
            return _filas(cur)
    except Exception as e:
        logger.error("anticipos_empleado: %s", e)
        return []


# ── Conceptos recurrentes (retribución flexible / pluses fijos) ──────────────
def set_concepto_recurrente(id_empleado, clave, importe, *, id_empresa=None) -> dict:
    """Fija un concepto recurrente del empleado (plus_convenio, nocturnidad, bonus, plus_transporte,
    dietas, embargos…) que se inyectará automáticamente en cada nómina."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO rrhh_conceptos_recurrentes (id_empresa, id_empleado, clave, importe) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE importe=VALUES(importe), activo=1",
                        (emp, id_empleado, clave, round(float(importe or 0), 2)))
            c.commit()
        _audit("CONCEPTO_RECURRENTE", f"emp{id_empleado} {clave}={importe}", "rrhh_conceptos_recurrentes")
        return {"ok": True}
    except Exception as e:
        logger.error("set_concepto_recurrente: %s", e)
        return {"ok": False, "motivo": str(e)}


def conceptos_para_datos(id_empleado, *, id_empresa=None) -> dict:
    """Devuelve los conceptos recurrentes activos como dict {clave: importe} listo para fusionar en
    los `datos` que consume `nomina_servicio.construir_input`."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT clave, importe FROM rrhh_conceptos_recurrentes WHERE id_empresa<=>%s "
                        "AND id_empleado=%s AND activo=1", (emp, id_empleado))
            return {r["clave"]: float(r["importe"] or 0) for r in _filas(cur)}
    except Exception as e:
        logger.error("conceptos_para_datos: %s", e)
        return {}


def preparar_datos_nomina(id_empleado, datos, *, id_empresa=None) -> dict:
    """Enriquece los `datos` de nómina con los conceptos recurrentes y la cuota de anticipo pendiente,
    SIN recalcular nada (el motor existente hace el cálculo). Devuelve el dict listo para el motor."""
    d = dict(datos or {})
    for clave, importe in conceptos_para_datos(id_empleado, id_empresa=id_empresa).items():
        d.setdefault(clave, importe)
    cuota = cuota_anticipo_pendiente(id_empleado, id_empresa=id_empresa)
    if cuota:
        d["anticipos"] = round(float(d.get("anticipos") or 0) + cuota, 2)
    return d


# ── Informe coste-empresa (reutiliza lo que el motor YA calcula) ─────────────
def coste_empresa(datos, *, pais="ES") -> dict:
    """Coste total para la empresa = devengado + SS a cargo de la empresa. Reutiliza el `ss_empresa`
    que el motor de nómina ya computa; NO recalcula cotizaciones."""
    try:
        from src.rrhh import nomina_servicio
        res = nomina_servicio.calcular_desde_datos(datos, pais)
        ss_emp = getattr(res, "ss_empresa", {}) or {}
        total_ss_emp = round(sum(float(v or 0) for v in ss_emp.values()), 2)
        devengado = round(float(getattr(res, "total_devengado", 0) or 0), 2)
        return {"total_devengado": devengado, "ss_empresa": total_ss_emp,
                "coste_total_empresa": round(devengado + total_ss_emp, 2),
                "liquido_trabajador": round(float(getattr(res, "liquido", 0) or 0), 2),
                "detalle_ss_empresa": {k: round(float(v or 0), 2) for k, v in ss_emp.items()}}
    except Exception as e:
        logger.error("coste_empresa: %s", e)
        return {"coste_total_empresa": 0.0, "error": str(e)}
