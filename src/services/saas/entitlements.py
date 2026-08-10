"""
Entitlements / Capabilities SaaS (Fase 16) — FUENTE ÚNICA de verdad de las capacidades avanzadas y las cuotas
por plan. Evoluciona el licenciamiento existente (N7): reutiliza `licensing.licencia_activa`/`_contar`/
`LicenciaError`; NO es un motor paralelo ni crea tablas. Los módulos consultan CAPACIDADES (`has`/`can`/`limit`/
`require`), nunca el plan directamente (`if plan == "PRO"` prohibido).

Reglas fundamentales:
  • **PLUS = acceso total**: todas las booleanas → True; todos los límites → ILIMITADO (None).
  • **BASIC/PRO**: restricciones por matriz; NUNCA rompen un flujo operativo principal (sólo capacidades
    avanzadas y cuotas cuantitativas).
  • **Legacy (sin licencia)**: sin restricción (comportamiento actual intacto) → se resuelve como PLUS.
  • **Downgrade no destructivo**: si el uso supera el límite tras bajar de plan → estado `OVER_LIMIT`; se
    bloquea SOLO crear nuevos; los recursos existentes se conservan y se pueden editar/eliminar.
  • Multi-tenant: todo se resuelve por `id_empresa`; jamás con variables globales ni el plan de otro tenant.

Entitlements ≠ RBAC: RBAC decide si el USUARIO puede hacer la acción; entitlements decide si la CAPACIDAD está
disponible para el TENANT según su plan. Ambos coexisten.
"""

import logging

logger = logging.getLogger("saas.entitlements")

UNLIMITED = None  # representación semántica de "sin límite" (PLUS)

# ── Catálogo de capacidades ───────────────────────────────────────────────────
BOOLEANS = (
    "tpv.avanzado", "ia.forecasting.ml", "ia.retraining", "multi_tienda.enabled",
    "storage.s3", "api.access", "realtime.distributed", "mobile.app",
)
# Capacidad de límite → tabla de conteo del uso actual (None = sin conteo → se asume 0).
LIMITES = {
    "usuarios.max": "usuarios",
    "tiendas.max": "tiendas",
    "almacenes.max": "almacenes",
    "correo.buzones.max": "correos_corporativos",
}
CAPABILITIES = BOOLEANS + tuple(LIMITES)
PLANES = ("BASIC", "PRO", "PLUS")

# ── MATRIZ CENTRAL (única fuente de verdad). PLUS NO se enumera: regla = todo true / ilimitado. ──
_MATRIZ = {
    "BASIC": {
        "tpv.avanzado": False, "ia.forecasting.ml": False, "ia.retraining": False,
        "multi_tienda.enabled": False, "storage.s3": False, "api.access": False,
        "realtime.distributed": False, "mobile.app": False,
        "usuarios.max": 5, "tiendas.max": 1, "almacenes.max": 1, "correo.buzones.max": 1,
    },
    "PRO": {
        "tpv.avanzado": True, "ia.forecasting.ml": True, "ia.retraining": False,
        "multi_tienda.enabled": True, "storage.s3": True, "api.access": True,
        "realtime.distributed": True, "mobile.app": False,
        "usuarios.max": 50, "tiendas.max": 10, "almacenes.max": 50, "correo.buzones.max": 10,
    },
    # "PLUS": resuelto por regla (todo true / ilimitado).
}


def matriz() -> dict:
    """Vista de la matriz central (para UI/administración). PLUS se expresa como todo true/ilimitado."""
    out = {p: dict(_MATRIZ[p]) for p in ("BASIC", "PRO")}
    out["PLUS"] = {c: (True if c in BOOLEANS else UNLIMITED) for c in CAPABILITIES}
    return out


# ── Resolución de plan (multi-tenant) ─────────────────────────────────────────
def plan_actual(id_empresa=None) -> str:
    """Plan efectivo del tenant. Sin licencia (legacy) → 'PLUS' (sin restricción). Estado no operativo
    (suspendida/cancelada/bloqueada) → 'BLOQUEADO'."""
    from src.services.saas import licensing as L
    lic = L.licencia_activa(id_empresa)
    if not lic:
        return "PLUS"                                    # legacy = acceso total (comportamiento actual)
    if lic.get("estado") not in ("activa", "prueba"):
        return "BLOQUEADO"
    return (lic.get("codigo_plan") or "BASIC").upper()


# ── API central ───────────────────────────────────────────────────────────────
def has(cap, id_empresa=None) -> bool:
    """¿Está disponible la CAPACIDAD para el tenant? (booleana; para límites: True si el límite no es 0)."""
    if cap in LIMITES:
        lim = limit(cap, id_empresa)
        return lim is UNLIMITED or lim > 0
    p = plan_actual(id_empresa)
    if p == "PLUS":
        return True
    if p == "BLOQUEADO":
        return False
    return bool(_MATRIZ.get(p, {}).get(cap, False))


def limit(cap, id_empresa=None):
    """Límite de la capacidad cuantitativa. None = ILIMITADO (PLUS/legacy). 0 = bloqueado."""
    if cap not in LIMITES:
        return None
    p = plan_actual(id_empresa)
    if p == "PLUS":
        return UNLIMITED
    if p == "BLOQUEADO":
        return 0
    return _MATRIZ.get(p, {}).get(cap, 0)


def estado_cuota(cap, id_empresa=None) -> dict:
    """{limite, usado, disponible, ok, estado}. estado ∈ OK | AT_LIMIT | OVER_LIMIT. NO escribe nada."""
    lim = limit(cap, id_empresa)
    usado = _usado(cap, id_empresa)
    return _clasificar(usado, lim)


def puede_crear(cap, id_empresa=None) -> bool:
    """¿Se puede crear un recurso más de esta cuota? False en AT_LIMIT/OVER_LIMIT (no destruye nada)."""
    return estado_cuota(cap, id_empresa)["ok"]


def can(cap, id_empresa=None) -> bool:
    """Booleana → `has`; cuota → `puede_crear`."""
    return puede_crear(cap, id_empresa) if cap in LIMITES else has(cap, id_empresa)


def require(cap, id_empresa=None, usuario=None) -> bool:
    """Exige la capacidad ANTES de iniciar la operación (nunca a mitad de un flujo). Lanza LicenciaError y
    audita `ENTITLEMENT_DENIED` si no procede. Es enforcement de TENANT; coexiste con RBAC (usuario)."""
    if can(cap, id_empresa):
        return True
    _audit_denegado(cap, id_empresa, usuario)
    from src.services.saas.licensing import LicenciaError
    if cap in LIMITES:
        est = estado_cuota(cap, id_empresa)
        raise LicenciaError(f"Límite del plan alcanzado: {cap} ({est['usado']}/{est['limite']})")
    raise LicenciaError(f"Capacidad no incluida en el plan: {cap}")


def snapshot(id_empresa=None) -> dict:
    """Resolución completa de capacidades/cuotas del tenant (para UI/tests)."""
    p = plan_actual(id_empresa)
    return {
        "plan": p,
        "booleans": {c: has(c, id_empresa) for c in BOOLEANS},
        "limites": {c: limit(c, id_empresa) for c in LIMITES},
        "cuotas": {c: estado_cuota(c, id_empresa) for c in LIMITES},
    }


# ── internos ──────────────────────────────────────────────────────────────────
def _usado(cap, id_empresa) -> int:
    tabla = LIMITES.get(cap)
    if not tabla:
        return 0
    try:
        from src.services.saas import licensing as L
        return L._contar(tabla, L._emp(id_empresa))
    except Exception as e:
        logger.debug("_usado(%s): %s", cap, e)
        return 0


def _clasificar(usado, lim) -> dict:
    if lim is UNLIMITED:
        return {"limite": None, "usado": usado, "disponible": None, "ok": True, "estado": "OK"}
    if usado > lim:
        return {"limite": lim, "usado": usado, "disponible": 0, "ok": False, "estado": "OVER_LIMIT"}
    if usado >= lim:
        return {"limite": lim, "usado": usado, "disponible": 0, "ok": False, "estado": "AT_LIMIT"}
    return {"limite": lim, "usado": usado, "disponible": lim - usado, "ok": True, "estado": "OK"}


def _audit_denegado(cap, id_empresa, usuario):
    try:
        from src.db.conexion import log_auditoria
        from src.services.saas import licensing as L
        emp = L._emp(id_empresa)
        log_auditoria("saas", "ENTITLEMENT_DENIED", "entitlements",
                      f"emp={emp} cap={cap} plan={plan_actual(id_empresa)} usuario={usuario}")
    except Exception:
        pass
