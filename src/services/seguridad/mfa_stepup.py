"""
Step-Up Authentication (Gobernanza MFA · Fase 7). Exige MFA RECIENTE para acciones de alto riesgo.
Reutiliza el motor MFA existente (`mfa.verificar` / `usar_recovery_code`) y la auditoría; NO crea un
sistema paralelo. La "ventana de confianza" es EFÍMERA: vive en memoria del proceso (sesión), caduca por
TTL y NUNCA es un bypass permanente (no se persiste; muere con el proceso). Vinculada a usuario+empresa.

Modelo: usuario autenticado → acción sensible → ¿MFA reciente? SÍ → permitir; NO → reto MFA → éxito →
abre la ventana temporal de confianza. Auditoría: acción, usuario, empresa, método, resultado (sin
secretos). El caso de usuario SIN MFA activo lo resuelve el llamador (reautenticación/RBAC).
"""

import logging
import time

logger = logging.getLogger("seguridad.mfa_stepup")

VENTANA_SEG = 300   # 5 minutos de confianza tras un step-up correcto

# Acciones de ALTO RIESGO que requieren MFA reciente (Fase 7). Claves estables (módulo.accion).
ACCIONES_CRITICAS = frozenset({
    "password.cambiar", "email.cambiar",
    "mfa.desactivar", "mfa.recovery.regenerar", "mfa.admin.reset",
    "roles.cambiar", "permisos.cambiar",
    "pagos.pasarela.configurar", "canal_web.dominios",
    "secretos.acceder", "saas.admin", "finanzas.critica",
})

# Ventana en memoria: (id_usuario, id_empresa) → timestamp del último step-up correcto.
_ventana: dict = {}


def requiere(accion) -> bool:
    """True si la acción es de alto riesgo (necesita MFA reciente)."""
    return str(accion or "") in ACCIONES_CRITICAS


def _clave(id_usuario, id_empresa):
    return (str(id_usuario), str(id_empresa or ""))


def reciente(id_usuario, *, id_empresa=None, ventana_seg=VENTANA_SEG) -> bool:
    """True si el usuario tiene un step-up correcto dentro de la ventana temporal (no caducado)."""
    ts = _ventana.get(_clave(id_usuario, id_empresa), 0)
    return (time.time() - ts) < int(ventana_seg)


def recovery_valido_stepup(id_empresa=None) -> bool:
    """Un recovery code NO vale como factor de step-up de alto riesgo salvo que la política de la
    empresa lo permita explícitamente (Fase 10: `metodos` incluye `recovery`)."""
    try:
        from src.services.seguridad import mfa_politica
        pol = mfa_politica.politica_efectiva(id_empresa=id_empresa)
        return "recovery" in (pol.get("metodos") or [])
    except Exception:
        return False


def registrar(id_usuario, *, id_empresa=None, metodo="totp", accion=None) -> None:
    """Abre/renueva la ventana de confianza tras un step-up correcto. Audita (sin secretos)."""
    _ventana[_clave(id_usuario, id_empresa)] = time.time()
    try:
        from src.services.seguridad import mfa_eventos
        mfa_eventos.emitir("STEP_UP_SUCCESS", id_usuario=id_usuario, id_empresa=id_empresa,
                           detalle=f"metodo={metodo} accion={accion or '-'}")
    except Exception:
        pass


def verificar(id_usuario, codigo, *, id_empresa=None, accion=None) -> bool:
    """Verifica el 2º factor para un step-up. TOTP siempre; recovery SOLO si la política lo permite
    (métodos de la empresa). Si es válido abre la ventana. Audita STEP_UP_SUCCESS/FAILURE (sin secretos)."""
    metodo = "totp"
    try:
        from src.services.seguridad import mfa
        ok = bool(mfa.verificar(id_usuario, codigo))
        if not ok and recovery_valido_stepup(id_empresa) and mfa.usar_recovery_code(id_usuario, codigo):
            ok, metodo = True, "recovery"
    except Exception as e:
        logger.debug("verificar step-up: %s", e)
        ok = False
    if ok:
        registrar(id_usuario, id_empresa=id_empresa, metodo=metodo, accion=accion)
        return True
    try:
        from src.services.seguridad import mfa_eventos
        mfa_eventos.emitir("STEP_UP_FAILURE", id_usuario=id_usuario, id_empresa=id_empresa,
                           detalle=f"accion={accion or '-'}")
    except Exception:
        pass
    return False


def invalidar(id_usuario, *, id_empresa=None) -> None:
    """Cierra la ventana de confianza (p. ej. al cerrar sesión)."""
    _ventana.pop(_clave(id_usuario, id_empresa), None)
