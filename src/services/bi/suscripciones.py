"""
Suscripciones a informes-KPI + cuadros de mando personales (Módulo 13, enriquecimiento de BI).
Genuinamente ausente. Permite programar la distribución periódica de un dashboard/KPI a usuarios/roles
(por notificación o email) y guardar cuadros de mando personales por usuario. La generación del
contenido REUTILIZA el motor de KPIs existente (`bi.kpis.obtener_dashboard`) y la entrega reutiliza
Comunicaciones. Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("bi.suscripciones")

_PERIODOS = {"diaria": 1, "semanal": 7, "mensual": 30, "trimestral": 91}


def _emp(id_empresa=None):
    # IOC v3 (Bloque VI): adopción — resolución vía IOC (sin depender del shim deprecado fuentes.emp).
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="bi_suscripciones"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bi", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Suscripciones ────────────────────────────────────────────────────────────
def crear_suscripcion(nombre, *, tipo="dashboard", recurso=None, usuarios=None, roles=None,
                      canal="notificacion", periodicidad="mensual", proxima_fecha=None,
                      id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    if periodicidad not in _PERIODOS:
        periodicidad = "mensual"
    proxima_fecha = proxima_fecha or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO bi_suscripciones (id_empresa, nombre, tipo, recurso, usuarios, "
                        "roles, canal, periodicidad, proxima_fecha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, nombre[:160], tipo, recurso,
                         ",".join(usuarios) if isinstance(usuarios, (list, tuple)) else usuarios,
                         ",".join(roles) if isinstance(roles, (list, tuple)) else roles,
                         canal, periodicidad, proxima_fecha))
            sid = cur.lastrowid
            c.commit()
        _audit("SUSCRIPCION_ALTA", f"{sid}:{nombre} {periodicidad}")
        return sid
    except Exception as e:
        logger.error("crear_suscripcion: %s", e)
        return None


def _contenido(susc, id_empresa) -> str:
    """Genera el resumen textual del recurso suscrito reutilizando el motor de KPIs."""
    try:
        from src.services.bi import kpis
        dash = kpis.obtener_dashboard(id_empresa) or {}
        kpivals = dash.get("kpis") or dash
        if isinstance(kpivals, dict):
            items = list(kpivals.items())[:12]
            return "; ".join(f"{k}={v}" for k, v in items) or "Sin datos"
        return str(kpivals)[:500]
    except Exception as e:
        logger.debug("_contenido: %s", e)
        return "Resumen de KPIs no disponible"


def enviar_suscripcion(id_suscripcion, *, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM bi_suscripciones WHERE id=%s AND id_empresa<=>%s", (id_suscripcion, emp))
            filas = _filas(cur)
        if not filas:
            return {"ok": False, "motivo": "no existe"}
        s = filas[0]
        cuerpo = _contenido(s, emp)
        usuarios = [u for u in (s.get("usuarios") or "").split(",") if u]
        roles = [r for r in (s.get("roles") or "").split(",") if r]
        try:
            from src.services.comunicaciones import notificaciones
            notificaciones.emitir("bi_informe", f"Informe BI: {s['nombre']}", cuerpo,
                                  prioridad="normal", modulo="bi",
                                  usuarios=usuarios or None, roles=roles or None, id_empresa=emp)
        except Exception as e:
            logger.debug("enviar_suscripcion notif: %s", e)
        _audit("SUSCRIPCION_ENVIO", f"{id_suscripcion}:{s['nombre']}")
        return {"ok": True, "contenido": cuerpo}
    except Exception as e:
        logger.error("enviar_suscripcion: %s", e)
        return {"ok": False, "motivo": str(e)}


def _job_distribucion_bi(id_empresa=None) -> dict:
    """Job de scheduler: envía las suscripciones cuya `proxima_fecha` venció y reprograma."""
    emp = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    enviados = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, periodicidad, proxima_fecha FROM bi_suscripciones "
                        "WHERE id_empresa<=>%s AND activo=1 AND proxima_fecha<=%s", (emp, hoy))
            pendientes = _filas(cur)
        for s in pendientes:
            if enviar_suscripcion(s["id"], id_empresa=emp).get("ok"):
                enviados += 1
            dias = _PERIODOS.get(s["periodicidad"], 30)
            try:
                prox = (_dt.date.fromisoformat(str(s["proxima_fecha"])[:10]) + _dt.timedelta(days=dias)).isoformat()
            except Exception:
                prox = (_dt.date.today() + _dt.timedelta(days=dias)).isoformat()
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE bi_suscripciones SET proxima_fecha=%s, ultima_envio=%s WHERE id=%s",
                            (prox, hoy, s["id"]))
                c.commit()
        return {"enviados": enviados}
    except Exception as e:
        logger.error("_job_distribucion_bi: %s", e)
        return {"enviados": enviados, "error": str(e)}


def registrar_jobs_bi_suscripciones(id_empresa=None):
    try:
        from src.services import scheduler
        scheduler.registrar("bi_suscripciones_distribucion", _job_distribucion_bi)
        scheduler.registrar_job("bi_suscripciones_distribucion", intervalo_horas=24,
                                descripcion="Distribución programada de informes BI")
    except Exception as e:
        logger.debug("registrar_jobs_bi_suscripciones: %s", e)


# ── Cuadros de mando personales ──────────────────────────────────────────────
def guardar_cuadro(usuario, nombre, layout, *, predeterminado=False, id_empresa=None) -> int | None:
    """`layout`: estructura JSON de widgets/KPIs elegidos por el usuario."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if predeterminado:
                cur.execute("UPDATE bi_cuadros_personales SET predeterminado=0 WHERE id_empresa<=>%s "
                            "AND usuario=%s", (emp, usuario))
            cur.execute("INSERT INTO bi_cuadros_personales (id_empresa, usuario, nombre, layout, "
                        "predeterminado) VALUES (%s,%s,%s,%s,%s)",
                        (emp, usuario, nombre[:160], json.dumps(layout, ensure_ascii=False, default=str),
                         1 if predeterminado else 0))
            cid = cur.lastrowid
            c.commit()
        _audit("CUADRO_GUARDADO", f"{cid}:{usuario}/{nombre}", "bi_cuadros_personales")
        return cid
    except Exception as e:
        logger.error("guardar_cuadro: %s", e)
        return None


def cuadros_de_usuario(usuario, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM bi_cuadros_personales WHERE id_empresa<=>%s AND usuario=%s "
                        "ORDER BY predeterminado DESC, nombre", (emp, usuario))
            filas = _filas(cur)
        for f in filas:
            try:
                f["layout"] = json.loads(f.get("layout") or "null")
            except Exception:
                pass
        return filas
    except Exception as e:
        logger.error("cuadros_de_usuario: %s", e)
        return []
