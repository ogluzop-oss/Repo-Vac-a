"""
Scheduler empresarial (FASE COM-3).

Unifica las automatizaciones dispersas en jobs registrables, con historial e idempotencia por
intervalo. No introduce un daemon: `ejecutar_pendientes()` se invoca al arrancar/cerrar la app
(como backup_si_corresponde) o desde un proceso externo. Cada job es una función registrada en
REGISTRO; el estado (próxima ejecución, intentos) se persiste. Multiempresa y auditado.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("scheduler")

# Registro en memoria: codigo → callable(id_empresa) -> str|None (detalle).
REGISTRO = {}


def registrar(codigo, fn):
    """Registra el callable de un job (idempotente)."""
    REGISTRO[codigo] = fn


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def registrar_job(codigo, *, intervalo_horas=24, descripcion=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO scheduler_jobs (id_empresa, codigo, descripcion, intervalo_horas) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE descripcion=VALUES(descripcion), "
                        "intervalo_horas=VALUES(intervalo_horas), activo=1",
                        (id_empresa, codigo, descripcion, int(intervalo_horas)))
            conn.commit()
            cur.execute("SELECT id FROM scheduler_jobs WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            r = cur.fetchone()
            return r[0] if not isinstance(r, dict) else list(r.values())[0]
    except Exception as e:
        logger.error("registrar_job: %s", e)
        return None


def cancelar_job(codigo, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE scheduler_jobs SET activo=0 WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cancelar_job: %s", e)
        return False


def _due(cur, id_empresa):
    cur.execute("SELECT codigo, intervalo_horas, proxima_ejecucion FROM scheduler_jobs "
                "WHERE id_empresa=%s AND activo=1", (id_empresa,))
    out = []
    ahora = _dt.datetime.now()
    for r in cur.fetchall():
        d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
        prox = d.get("proxima_ejecucion")
        if prox is None or (isinstance(prox, _dt.datetime) and prox <= ahora):
            out.append(d["codigo"])
    return out


def _config_job(cur, id_empresa, codigo) -> dict:
    """Config persistida del job (intervalo/timeout/reintentos). Vacío si no existe la fila/columnas."""
    try:
        cur.execute("SELECT intervalo_horas, timeout_seg, max_reintentos FROM scheduler_jobs "
                    "WHERE id_empresa=%s AND codigo=%s", (id_empresa, codigo))
    except Exception:
        cur.execute("SELECT intervalo_horas FROM scheduler_jobs WHERE id_empresa=%s AND codigo=%s",
                    (id_empresa, codigo))
    r = cur.fetchone()
    if not r:
        return {}
    d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
    return d


def ejecutar_job(codigo, *, id_empresa=None, intento=1) -> dict:
    """Ejecuta un job registrado con TIMEOUT (soft) medido, guarda historial (estado/detalle/duración)
    y reprograma según su intervalo. Devuelve {estado, detalle, duracion_ms}."""
    id_empresa = _emp(id_empresa)
    fn = REGISTRO.get(codigo)
    if not fn:
        return {"estado": "sin_registro", "detalle": codigo}
    # Lee la config (intervalo/timeout) para reprogramar y limitar la ejecución.
    iv, timeout_seg = 24, 300
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cfg = _config_job(cur, id_empresa, codigo)
        iv = int(cfg.get("intervalo_horas") or 24)
        timeout_seg = int(cfg.get("timeout_seg") or 300)
    except Exception:
        pass
    estado, detalle = "ok", None
    _t0 = _dt.datetime.now()
    resultado = {}

    def _run():
        try:
            resultado["detalle"] = fn(id_empresa)
        except Exception as e:
            resultado["error"] = str(e)
            logger.error("ejecutar_job(%s): %s", codigo, e)

    import threading as _th
    th = _th.Thread(target=_run, daemon=True, name=f"job-{codigo}")
    th.start()
    th.join(timeout=max(1, timeout_seg))
    if th.is_alive():
        estado, detalle = "timeout", f"excedió {timeout_seg}s (continúa en segundo plano)"
    elif "error" in resultado:
        estado, detalle = "error", resultado["error"]
    else:
        detalle = resultado.get("detalle")
    duracion_ms = int((_dt.datetime.now() - _t0).total_seconds() * 1000)
    try:
        prox = _dt.datetime.now() + _dt.timedelta(hours=iv)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE scheduler_jobs SET ultima_ejecucion=NOW(), proxima_ejecucion=%s "
                        "WHERE id_empresa=%s AND codigo=%s", (prox, id_empresa, codigo))
            try:
                cur.execute("INSERT INTO scheduler_historial (id_empresa, codigo, estado, detalle, "
                            "intentos, duracion_ms) VALUES (%s,%s,%s,%s,%s,%s)",
                            (id_empresa, codigo, estado, (detalle or "")[:255], intento, duracion_ms))
            except Exception:
                cur.execute("INSERT INTO scheduler_historial (id_empresa, codigo, estado, detalle, "
                            "intentos) VALUES (%s,%s,%s,%s,%s)",
                            (id_empresa, codigo, estado, (detalle or "")[:255], intento))
            conn.commit()
    except Exception as e:
        logger.error("ejecutar_job/persist(%s): %s", codigo, e)
    _audit("AUTOMATIZACION_EJECUTADA", f"{codigo}={estado} ({duracion_ms}ms)")
    return {"estado": estado, "detalle": detalle, "duracion_ms": duracion_ms}


def reintentar_job(codigo, *, id_empresa=None, max_intentos=3) -> dict:
    """Reejecuta un job hasta `max_intentos` mientras devuelva error."""
    res = {"estado": "error"}
    for i in range(1, int(max_intentos) + 1):
        res = ejecutar_job(codigo, id_empresa=id_empresa, intento=i)
        if res.get("estado") == "ok":
            break
    return res


def ejecutar_pendientes(id_empresa=None) -> dict:
    """Ejecuta los jobs ACTIVOS cuya próxima ejecución ha vencido, por orden de PRIORIDAD."""
    id_empresa = _emp(id_empresa)
    res = {"ejecutados": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            codigos = _due(cur, id_empresa)
            # Orden por prioridad (crítica→baja) si la columna existe.
            prio = {}
            try:
                cur.execute("SELECT codigo, prioridad FROM scheduler_jobs WHERE id_empresa<=>%s", (id_empresa,))
                for r in cur.fetchall():
                    d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
                    prio[d["codigo"]] = d.get("prioridad") or "normal"
            except Exception:
                pass
    except Exception as e:
        logger.error("ejecutar_pendientes: %s", e)
        return res
    codigos.sort(key=lambda c: _PRIORIDAD_ORDEN.get(str(prio.get(c, "normal")).lower(), 2))
    for c in codigos:
        ejecutar_job(c, id_empresa=id_empresa)
        res["ejecutados"] += 1
    return res


def historial(codigo, id_empresa=None, limite=50) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM scheduler_historial WHERE id_empresa=%s AND codigo=%s "
                        "ORDER BY fecha DESC LIMIT %s", (id_empresa, codigo, int(limite)))
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("historial: %s", e)
        return []


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("scheduler", accion, "scheduler_jobs", detalle)
    except Exception:
        pass


# ── Jobs Opt-In (Bloque 1): configuración editable + estado + seguridad ──────────
_PRIORIDAD_ORDEN = {"critica": 0, "alta": 1, "normal": 2, "baja": 3}


def _puede(usuario, permiso) -> bool:
    """Comprueba un permiso RBAC (True si no se exige permiso). Reutiliza `autorizacion`."""
    if not permiso:
        return True
    try:
        from src.services.seguridad import autorizacion
        return bool(autorizacion.puede(usuario, permiso))
    except Exception:
        return True   # sin motor RBAC disponible → no bloquear (comportamiento legacy)


def configurar_job(codigo, *, habilitado=None, intervalo_horas=None, prioridad=None,
                   timeout_seg=None, max_reintentos=None, usuario=None, id_empresa=None) -> dict:
    """Configura un job DESDE EL ERP (nunca desde código): habilitar/deshabilitar, frecuencia,
    prioridad, timeout, reintentos. Respeta el permiso RBAC del job, marca `configurado=1` (protege
    la elección frente a la sincronización del catálogo) y AUDITA quién lo cambió."""
    id_empresa = _emp(id_empresa)
    try:
        from src.services import scheduler_registry as _reg
        m = _reg.meta(codigo)
    except Exception:
        m = {"permiso": None}
    if not _puede(usuario, m.get("permiso")):
        return {"ok": False, "motivo": "sin permiso"}
    sets, params = [], []
    if habilitado is not None:
        sets.append("activo=%s"); params.append(1 if habilitado else 0)
    if intervalo_horas is not None:
        sets.append("intervalo_horas=%s"); params.append(int(intervalo_horas))
    if prioridad is not None:
        sets.append("prioridad=%s"); params.append(str(prioridad)[:10])
    if timeout_seg is not None:
        sets.append("timeout_seg=%s"); params.append(int(timeout_seg))
    if max_reintentos is not None:
        sets.append("max_reintentos=%s"); params.append(int(max_reintentos))
    if not sets:
        return {"ok": False, "motivo": "nada que cambiar"}
    sets.append("configurado=1")
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Asegura la fila (crea si no existe, con la descripción/intervalo del catálogo).
            cur.execute("INSERT IGNORE INTO scheduler_jobs (id_empresa, codigo, descripcion, "
                        "intervalo_horas) VALUES (%s,%s,%s,%s)",
                        (id_empresa, codigo, m.get("nombre", codigo), int(m.get("intervalo_horas", 24))))
            cur.execute(f"UPDATE scheduler_jobs SET {', '.join(sets)} WHERE id_empresa=%s AND codigo=%s",
                        (*params, id_empresa, codigo))
            conn.commit()
    except Exception as e:
        logger.error("configurar_job: %s", e)
        return {"ok": False, "motivo": str(e)}
    _audit("JOB_CONFIGURADO", f"{codigo} por {usuario or '?'}: {dict(zip([s.split('=')[0] for s in sets], params))}")
    return {"ok": True}


def estado_jobs(id_empresa=None) -> list:
    """Estado consolidado de todos los jobs del catálogo + su configuración persistida (para el ERP):
    habilitado, categoría, pesado, frecuencia, prioridad, timeout, reintentos, última/próxima ejecución."""
    id_empresa = _emp(id_empresa)
    from src.services import scheduler_registry as _reg
    filas = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM scheduler_jobs WHERE id_empresa<=>%s", (id_empresa,))
            for r in cur.fetchall():
                d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
                filas[d.get("codigo")] = d
    except Exception as e:
        logger.debug("estado_jobs: %s", e)
    out = []
    for cod in _reg.CATALOGO:
        m = _reg.meta(cod)
        row = filas.get(cod, {})
        out.append({
            "codigo": cod, "nombre": m["nombre"], "categoria": m["categoria"],
            "pesado": bool(row.get("pesado", m["pesado"])),
            "habilitado": bool(row.get("activo", 0)),
            "frecuencia_h": int(row.get("intervalo_horas") or m["intervalo_horas"]),
            "prioridad": row.get("prioridad") or m["prioridad"],
            "timeout_seg": int(row.get("timeout_seg") or m["timeout_seg"]),
            "reintentos": int(row.get("max_reintentos") or m["max_reintentos"]),
            "ultima": row.get("ultima_ejecucion"), "proxima": row.get("proxima_ejecucion"),
            "permiso": m["permiso"],
        })
    out.sort(key=lambda j: (j["categoria"], _PRIORIDAD_ORDEN.get(str(j["prioridad"]).lower(), 2)))
    return out


def ejecutar_ahora(codigo, *, usuario=None, id_empresa=None) -> dict:
    """Ejecución MANUAL desde el ERP (con permiso + reintentos del job). Reutiliza reintentar_job."""
    id_empresa = _emp(id_empresa)
    try:
        from src.services import scheduler_registry as _reg
        m = _reg.meta(codigo)
        _reg.registrar_callables(id_empresa)   # asegura el callable registrado
    except Exception:
        m = {"permiso": None, "max_reintentos": 1}
    if not _puede(usuario, m.get("permiso")):
        return {"ok": False, "motivo": "sin permiso"}
    _audit("JOB_EJECUTADO_MANUAL", f"{codigo} por {usuario or '?'}")
    return reintentar_job(codigo, id_empresa=id_empresa, max_intentos=int(m.get("max_reintentos", 1)))


# ── Jobs por defecto (automatizaciones iniciales COM-3) ──────────────────────
def _job_vencimientos(id_empresa):
    from src.db import vencimientos
    n = vencimientos.marcar_vencidos(id_empresa)
    return f"vencimientos marcados={n}"


def _job_workflow_sla(id_empresa):
    from src.services.workflow import workflow_engine
    r = workflow_engine.procesar_sla(id_empresa)
    return f"escaladas={r.get('escaladas')}"


def _job_backup(id_empresa):
    from src.db import backup
    r = backup.backup_si_corresponde(intervalo_horas=24, motivo="programado")
    return "backup ejecutado" if r else "no procede"


def _job_cobros_recordatorios(id_empresa):
    from src.services.facturacion import recordatorios
    r = recordatorios.procesar(id_empresa)
    return f"recordatorios enviados={r['enviados']} evaluadas={r['evaluadas']} errores={r['errores']}"


def _job_camaras_retencion(id_empresa):
    from src.services.camaras import grabacion
    return grabacion.job_retencion(id_empresa)


def _job_saas_facturacion(id_empresa):
    from src.services.saas import facturacion_automatica
    return facturacion_automatica.job(id_empresa)


def registrar_jobs_por_defecto(id_empresa=None):
    """Registra los callables y crea los jobs por defecto de la empresa (idempotente)."""
    registrar("vencimientos", _job_vencimientos)
    registrar("workflow_sla", _job_workflow_sla)
    registrar("backup", _job_backup)
    registrar("cobros_recordatorios", _job_cobros_recordatorios)
    registrar("camaras_retencion", _job_camaras_retencion)
    registrar("saas_facturacion", _job_saas_facturacion)   # opt-in (solo SaaS): no se crea job por defecto
    registrar_job("vencimientos", intervalo_horas=24, descripcion="Marcar vencimientos vencidos", id_empresa=id_empresa)
    registrar_job("workflow_sla", intervalo_horas=12, descripcion="Escalado SLA de aprobaciones", id_empresa=id_empresa)
    registrar_job("backup", intervalo_horas=24, descripcion="Backup programado", id_empresa=id_empresa)
    registrar_job("cobros_recordatorios", intervalo_horas=24,
                  descripcion="Recordatorios de cobro a clientes", id_empresa=id_empresa)
    registrar_job("camaras_retencion", intervalo_horas=24,
                  descripcion="Videovigilancia · purga de grabaciones antiguas", id_empresa=id_empresa)
    # Simulacros de Disaster Recovery (DR-D): verificacion/restore-test/consistencia.
    try:
        from src.services.dr import dr_drills
        dr_drills.registrar_jobs_dr(id_empresa=id_empresa)
    except Exception:
        pass
    # Gemelo Digital (Enterprise 8): verificacion periodica de consistencia del gemelo.
    try:
        from src.services.gemelo import consistencia as _gc
        _gc.registrar_jobs_gemelo(id_empresa=id_empresa)
    except Exception:
        pass
    # Jobs de mantenimiento Enterprise SEGUROS: ligeros/moderados, sin dependencias externas ni
    # credenciales, que aportan valor operativo (SLA, preventivos, automatización CRM, historia BI,
    # ratios financieros). Best-effort: si el módulo/tabla no está, se omite sin romper el arranque.
    # DELIBERADAMENTE OPT-IN (no se registran aquí por carga/dependencias): bi_corp_etl (ETL DW pesado),
    # bi_corp_alertas (depende del ETL), resiliencia_sync/watchdog/cache_warmup (escenario edge/offline),
    # sat_email_ticket (requiere IMAP), SAAS_DUNNING (solo instalaciones SaaS).
    import importlib
    for _mod, _fn in (
        ("src.services.sat.contratos_sla", "registrar_jobs_sat"),        # SLA de tickets (4 h)
        ("src.services.gmao.planes", "registrar_jobs_gmao"),             # mantenimiento preventivo (24 h)
        ("src.services.crm.automatizacion", "registrar_jobs_crm"),       # automatización CRM (24 h)
        ("src.services.bi.snapshots", "registrar_jobs_bi"),              # snapshots KPI (24 h/…)
        ("src.services.finanzas.dashboard", "registrar_jobs_finanzas"),  # ratios/riesgo/anomalías (24 h)
    ):
        try:
            getattr(importlib.import_module(_mod), _fn)(id_empresa=id_empresa)
        except Exception as _e:
            logger.debug("job Enterprise %s no registrado: %s", _fn, _e)
