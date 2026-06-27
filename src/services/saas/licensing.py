"""
LicensingService — enforcement de licencias (FASE SAAS-C).

Resuelve el plan activo de una empresa y valida módulos y límites. COMPATIBILIDAD: si una
empresa NO tiene licencia asignada (instalación existente), se considera SIN restricción
(comportamiento legacy intacto). El enforcement solo actúa cuando se asigna un plan.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.services.saas import planes as _P

logger = logging.getLogger("saas.licensing")

ESTADOS = ("activa", "suspendida", "cancelada", "bloqueada", "prueba")


class LicenciaError(PermissionError):
    """Operación no permitida por el plan/licencia (módulo no incluido o límite superado)."""


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def asignar_plan(id_empresa, codigo_plan, *, estado="activa", usuario=None) -> bool:
    """Asigna/actualiza el plan de una empresa (idempotente) + histórico + evento."""
    id_empresa = _emp(id_empresa)
    codigo_plan = (codigo_plan or "BASIC").upper()
    if not _P.plan(codigo_plan):
        raise ValueError(f"plan inexistente: {codigo_plan}")
    try:
        ensure_schema()
        _P.sincronizar_planes()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO empresa_licencia (id_empresa, codigo_plan, estado) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE codigo_plan=VALUES(codigo_plan), estado=VALUES(estado)",
                        (id_empresa, codigo_plan, estado))
            cur.execute("INSERT INTO historico_licencias (id_empresa, codigo_plan, estado, detalle) "
                        "VALUES (%s,%s,%s,%s)", (id_empresa, codigo_plan, estado, "asignar_plan"))
            conn.commit()
        _evento(id_empresa, "PLAN_CAMBIADO", f"{codigo_plan}/{estado}")
        _audit("LICENCIA_ACTIVADA", id_empresa, f"{codigo_plan}/{estado}")
        return True
    except (ValueError, LicenciaError):
        raise
    except Exception as e:
        logger.error("asignar_plan: %s", e)
        return False


def licencia_activa(id_empresa=None) -> dict | None:
    """Licencia de la empresa: {codigo_plan, estado} o None si no tiene (legacy → sin límites)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_plan, estado FROM empresa_licencia WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if not r:
                return None
            d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
            return d
    except Exception as e:
        logger.error("licencia_activa: %s", e)
        return None


def estado_operativo(id_empresa=None) -> str:
    """'sin_licencia' (legacy) | estado real. Si suspendida/cancelada/bloqueada → bloqueante."""
    lic = licencia_activa(id_empresa)
    return lic["estado"] if lic else "sin_licencia"


def modulo_habilitado(modulo, id_empresa=None) -> bool:
    """True si el módulo está incluido en el plan (o sin licencia = todo permitido)."""
    lic = licencia_activa(id_empresa)
    if not lic:
        return True                              # legacy / sin licencia → sin restricción
    if lic["estado"] not in ("activa", "prueba"):
        return False                             # suspendida/cancelada/bloqueada → nada
    cfg = _P.plan(lic["codigo_plan"])
    return bool(cfg and modulo in cfg["modulos"])


_CONTADORES = {
    "max_tiendas": ("tiendas", "id_empresa"),
    "max_usuarios": ("usuarios", "id_empresa"),
    "max_almacenes": ("almacenes", "id_empresa"),
}


def _contar(tabla, id_empresa):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            return int(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception:
        return 0


def limite_disponible(recurso, id_empresa=None) -> dict:
    """Devuelve {limite, usado, disponible, ok} para un recurso (max_tiendas/usuarios/almacenes).
    Sin licencia → ilimitado."""
    id_empresa = _emp(id_empresa)
    lic = licencia_activa(id_empresa)
    if not lic:
        return {"limite": None, "usado": 0, "disponible": None, "ok": True}
    cfg = _P.plan(lic["codigo_plan"]) or {}
    limite = int(cfg.get("limites", {}).get(recurso, 9999))
    tabla = _CONTADORES.get(recurso, (None,))[0]
    usado = _contar(tabla, id_empresa) if tabla else 0
    return {"limite": limite, "usado": usado, "disponible": max(0, limite - usado), "ok": usado < limite}


def validar_operacion(*, modulo=None, recurso=None, id_empresa=None) -> bool:
    """Valida módulo y/o límite antes de una operación restringida. Lanza LicenciaError si no
    procede. Sin licencia (legacy) → siempre permite."""
    id_empresa = _emp(id_empresa)
    if licencia_activa(id_empresa) is None:
        return True
    if modulo and not modulo_habilitado(modulo, id_empresa):
        raise LicenciaError(f"Módulo no incluido en el plan: {modulo}")
    if recurso:
        info = limite_disponible(recurso, id_empresa)
        if not info["ok"]:
            raise LicenciaError(f"Límite del plan alcanzado: {recurso} ({info['usado']}/{info['limite']})")
    return True


def _evento(id_empresa, evento, detalle):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO eventos_licencia (id_empresa, evento, detalle) VALUES (%s,%s,%s)",
                        (id_empresa, evento, detalle))
            conn.commit()
    except Exception:
        pass


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "empresa_licencia", f"{id_empresa}: {detalle}")
    except Exception:
        pass
