"""
Política MFA por EMPRESA (Gobernanza MFA · Fase 0). Espeja el patrón arquitectónico de
`password_politica.py`: una fila por empresa (`mfa_politica`, migr 0160) que define si el MFA es
opcional u obligatorio, los métodos permitidos y qué roles quedan obligados (override por rol).

Modelo: el FACTOR MFA pertenece al USUARIO (`mfa_usuarios`, motor `seguridad/mfa.py`); la POLÍTICA
pertenece a la EMPRESA. La política EFECTIVA se resuelve por USUARIO + EMPRESA + ROL. No toca el login
ni el motor TOTP. No asocia la política a tienda ni a dispositivo. Multiempresa, auditado. No duplica.
"""

import logging

logger = logging.getLogger("seguridad.mfa_politica")

MODOS = ("opcional", "obligatorio")
METODOS = ("totp", "webauthn", "recovery")
_DEFECTO = {"modo": "opcional", "metodos": "totp", "roles_obligatorios": "", "activo": 1}

# Suelo de seguridad: estos perfiles llevan MFA obligatorio SIEMPRE que la política esté activa,
# aunque la empresa la tenga en modo "opcional" (no se puede bajar de este mínimo). Adaptativo · Fase 6.
ROLES_CRITICOS = ("SUPERADMIN", "ADMINISTRADOR")
# Contextos NO humanos / autoservicio: nunca MFA interactivo (API/M2M, autocobro/kiosco desatendido).
CONTEXTOS_SIN_MFA = ("api", "m2m", "autocobro", "kiosco")


def _emp(id_empresa=None):
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        try:
            from src.services.gemelo import fuentes
            return fuentes.emp(id_empresa)
        except Exception:
            return id_empresa


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def obtener_politica(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM mfa_politica WHERE id_empresa<=>%s LIMIT 1", (emp,))
            filas = _filas(cur)
        if filas:
            return filas[0]
    except Exception as e:
        logger.debug("obtener_politica: %s", e)
    return dict(_DEFECTO)


def guardar_politica(id_empresa=None, *, actor=None, **campos) -> dict:
    """Fija la política MFA de la empresa. Solo debería invocarse tras validar `mfa.admin.enforce`
    (la comprobación RBAC la hace el llamador/UI). Emite MFA_POLICY_CHANGED (sin secretos)."""
    emp = _emp(id_empresa)
    pol = obtener_politica(emp)
    pol.update({k: v for k, v in campos.items() if k in _DEFECTO})
    if pol.get("modo") not in MODOS:
        pol["modo"] = "opcional"
    # Normaliza los métodos permitidos a la lista canónica.
    met = [m.strip().lower() for m in str(pol.get("metodos") or "totp").split(",") if m.strip()]
    met = [m for m in met if m in METODOS] or ["totp"]
    pol["metodos"] = ",".join(dict.fromkeys(met))
    pol["roles_obligatorios"] = ",".join(
        r.strip().upper() for r in str(pol.get("roles_obligatorios") or "").split(",") if r.strip())
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO mfa_politica (id_empresa, modo, metodos, roles_obligatorios, activo) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE modo=VALUES(modo), "
                "metodos=VALUES(metodos), roles_obligatorios=VALUES(roles_obligatorios), "
                "activo=VALUES(activo), actualizado=NOW()",
                (emp, pol["modo"], pol["metodos"], pol["roles_obligatorios"], int(pol["activo"])))
            c.commit()
        try:
            from src.services.seguridad import mfa_eventos
            mfa_eventos.emitir("MFA_POLICY_CHANGED", id_empresa=emp, actor=actor,
                               detalle=f"modo={pol['modo']} metodos={pol['metodos']} "
                                       f"roles={pol['roles_obligatorios']}")
        except Exception:
            pass
        return {"ok": True, "politica": pol}
    except Exception as e:
        logger.error("guardar_politica: %s", e)
        return {"ok": False, "motivo": str(e)}


def politica_efectiva(usuario=None, *, rol=None, id_empresa=None, contexto=None) -> dict:
    """Resuelve la política MFA EFECTIVA (adaptativa) para un usuario: USUARIO + EMPRESA + ROL +
    CONTEXTO de terminal. Orden de prioridad: POLÍTICA EMPRESA → OVERRIDE ROL → CONTEXTO.
    Devuelve {obligatorio, opcional, modo, metodos:[...], perfil, contexto, critico}. NO exige nada por
    sí misma; informa a los llamadores (login/API/step-up). `contexto` ∈ api/m2m/autocobro/kiosco/tpv/
    pda/escritorio (los cuatro primeros = sin MFA humano)."""
    pol = obtener_politica(id_empresa)
    metodos = [m.strip().lower() for m in str(pol.get("metodos") or "totp").split(",") if m.strip()]
    perfil = (rol or (usuario or {}).get("perfil") or "").upper()
    ctx = str(contexto or "").lower()
    base = {"metodos": metodos, "perfil": perfil, "contexto": ctx, "critico": perfil in ROLES_CRITICOS}
    # 1) Contexto NO humano / autoservicio → nunca MFA interactivo.
    if ctx in CONTEXTOS_SIN_MFA:
        return {**base, "obligatorio": False, "opcional": False, "modo": ctx}
    # 2) Política desactivada por la empresa.
    if not int(pol.get("activo", 1)):
        return {**base, "obligatorio": False, "opcional": False, "modo": "desactivado"}
    # 3) EMPRESA (modo) → OVERRIDE ROL (roles_obligatorios) → SUELO de roles críticos.
    roles_obl = [r.strip().upper()
                 for r in str(pol.get("roles_obligatorios") or "").split(",") if r.strip()]
    obligatorio = base["critico"] or (pol.get("modo") == "obligatorio") or (perfil in roles_obl)
    return {**base, "obligatorio": bool(obligatorio), "opcional": not obligatorio,
            "modo": pol.get("modo")}
