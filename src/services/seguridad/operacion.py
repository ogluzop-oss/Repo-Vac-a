"""
Seguridad · Operación de seguridad (Etapa F · Fase F6).

Fachada que COMPONE las capacidades de seguridad YA EXISTENTES en operaciones de producción, sin crear
motores nuevos ni duplicar seguridad (Reglas 6/7):

  · Rotación de secretos → `secret_manager.rotar` (re-cifra preservando el texto plano). Aquí se añade
    la rotación OPERACIONAL (masiva) sobre las credenciales cifradas de conexiones, con VERIFICACIÓN
    (descifra antes/después) y modo report-only por defecto.
  · Detección de anomalías → `seguridad.anomalias.detectar_fuerza_bruta` (abre incidentes).
  · Alertas de seguridad → se CABLEA la detección a `observabilidad.alertas_tecnicas`.
  · Bloqueo inteligente → ya existe el bloqueo progresivo por cuenta (`db.usuario`: intentos/bloqueo);
    aquí se reporta.
  · Caducidad de tokens → ya existe (`seguridad.tokens` exp/refresh/revocación); aquí se reporta.
  · Auditoría → `seguridad.auditoria` + `incidentes` (reutilizados).

Solo lectura salvo la rotación (idempotente y verificada). Degradable, multiempresa, aditivo/reversible.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("seguridad.operacion")

FASE = "F6"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _scalar(sql, params=()):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


# ── Detección de anomalías + ALERTAS de seguridad (cableado) ──────────────────
def escanear_anomalias(*, id_empresa=None, umbral=5, ventana_min=15, alertar=True) -> dict:
    """Ejecuta la detección de fuerza bruta (abre incidentes) y, si `alertar`, emite una alerta técnica
    de seguridad por cada anomalía. Reutiliza `anomalias` + `incidentes` + `alertas_tecnicas`."""
    emp = _emp(id_empresa)
    incidentes = []
    try:
        from src.services.seguridad import anomalias
        incidentes = anomalias.detectar_fuerza_bruta(umbral=umbral, ventana_min=ventana_min,
                                                     id_empresa=emp) or []
    except Exception as e:
        logger.debug("escanear_anomalias: %s", e)
    alertas = 0
    if alertar and incidentes:
        try:
            from src.services.observabilidad import alertas_tecnicas
            for iid in incidentes:
                alertas_tecnicas.emitir("seguridad", f"Anomalía de seguridad (incidente {iid})",
                                        severidad="alta", id_empresa=emp)
                alertas += 1
        except Exception as e:
            logger.debug("escanear_anomalias alertar: %s", e)
    return {"incidentes": incidentes, "alertas": alertas}


# ── Rotación de secretos operacional (masiva, verificada) ─────────────────────
def secretos_rotables(id_empresa=None) -> int:
    """Nº de credenciales cifradas de conexiones susceptibles de rotación para el tenant."""
    emp = _emp(id_empresa)
    return _scalar("SELECT COUNT(*) FROM cd_conexiones WHERE id_empresa=%s AND "
                   "credenciales_cifradas IS NOT NULL", (emp,))


def rotar_secretos(id_empresa=None, *, aplicar=False, limite=500) -> dict:
    """Rotación OPERACIONAL de las credenciales cifradas (re-cifra con la clave actual). Por defecto
    `aplicar=False` (solo informa). Cada rotación se VERIFICA (el texto plano descifrado debe coincidir
    antes de escribir); si no coincide, se omite (no rompe la conexión). Reutiliza `secret_manager`."""
    emp = _emp(id_empresa)
    res = {"candidatos": 0, "rotados": 0, "omitidos": 0, "aplicar": bool(aplicar)}
    try:
        from src.db.conexion import obtener_conexion
        from src.services.seguridad import secret_manager
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, credenciales_cifradas FROM cd_conexiones WHERE id_empresa=%s AND "
                        "credenciales_cifradas IS NOT NULL LIMIT %s", (emp, int(limite)))
            filas = [(r["id"], r["credenciales_cifradas"]) if isinstance(r, dict) else (r[0], r[1])
                     for r in cur.fetchall()]
            res["candidatos"] = len(filas)
            for cid, token in filas:
                nuevo = secret_manager.rotar(token)
                # Verificación de seguridad: el nuevo token debe descifrar al mismo valor.
                if not nuevo or secret_manager.descifrar(nuevo) != secret_manager.descifrar(token):
                    res["omitidos"] += 1
                    continue
                if aplicar and nuevo != token:
                    cur.execute("UPDATE cd_conexiones SET credenciales_cifradas=%s WHERE id=%s",
                                (nuevo, cid))
                    res["rotados"] += 1
            if aplicar:
                conn.commit()
        _audit("ROTAR_SECRETOS", f"{emp}: rotados={res['rotados']} omitidos={res['omitidos']}")
    except Exception as e:
        logger.error("rotar_secretos: %s", e)
        res["error"] = str(e)
    return res


def _audit(accion, detalle):
    try:
        from src.services.seguridad import auditoria
        auditoria.registrar(accion, detalles=detalle)
    except Exception:
        pass


# ── Estado de seguridad operacional ───────────────────────────────────────────
def estado_seguridad(id_empresa=None) -> dict:
    """Foto operacional de seguridad: incidentes abiertos, secretos rotables, caducidad de tokens y
    bloqueos de cuenta activos. Compone incidentes/tokens/usuario/secret_manager."""
    emp = _emp(id_empresa)
    out = {"id_empresa": emp}
    try:
        from src.services.seguridad import incidentes
        out["incidentes_abiertos"] = len(incidentes.listar(estado="abierto", id_empresa=emp) or [])
    except Exception as e:
        logger.debug("estado incidentes: %s", e)
    out["secretos_rotables"] = secretos_rotables(emp)
    out["cuentas_bloqueadas"] = _scalar(
        "SELECT COUNT(*) FROM usuarios WHERE id_empresa=%s AND bloqueado_hasta IS NOT NULL AND "
        "bloqueado_hasta > NOW()", (emp,))
    try:
        from src.seguridad import tokens
        out["tokens"] = {"acceso_minutos": getattr(tokens, "ACCESO_MINUTOS", None),
                         "refresh_dias": getattr(tokens, "REFRESH_DIAS", None), "revocable": True}
    except Exception as e:
        logger.debug("estado tokens: %s", e)
    return out


def registrar_jobs(id_empresa=None) -> bool:
    """Registra el escaneo periódico de anomalías en el Scheduler (capacidad, degradable/opt-in)."""
    try:
        from src.services.scheduler_enterprise import core as sch
        sch.registrar_job("seguridad_escanear_anomalias", lambda *_a, **_k: escanear_anomalias())
        return True
    except Exception as e:
        logger.debug("registrar_jobs seguridad: %s", e)
        return False


def descriptor() -> dict:
    return {"servicio": "seguridad.operacion", "etapa": "F", "fase": FASE,
            "estado": "implementado", "motor_nuevo": False,
            "reutiliza": ["secret_manager (rotar)", "seguridad.anomalias", "seguridad.incidentes",
                          "observabilidad.alertas_tecnicas", "seguridad.tokens (caducidad)",
                          "db.usuario (bloqueo)"],
            "operaciones": ["escanear_anomalias", "secretos_rotables", "rotar_secretos",
                            "estado_seguridad", "registrar_jobs"],
            "rotacion_verificada": True}


__all__ = ["FASE", "escanear_anomalias", "secretos_rotables", "rotar_secretos", "estado_seguridad",
           "registrar_jobs", "descriptor"]
