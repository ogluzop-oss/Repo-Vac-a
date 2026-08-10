"""
Permisos VISUALES centralizados (Foundation). Resuelve el estado visual de un widget/panel —
`VISIBLE · OCULTO · SOLO_LECTURA · EDITABLE` — según rol/autoridad/empresa/tienda, reutilizando la
seguridad ya existente: RBAC (`services.autorizacion.puede`) + Gobierno Corporativo
(`services.gobierno`) + contexto multiempresa/tienda. NO sustituye la seguridad de backend: la
refuerza en la UI y elimina el control de acceso duplicado por pantalla.

Filosofía: **permisivo por defecto** (si no hay regla o el servicio no está disponible, no se
bloquea la UI; el backend sigue siendo la última barrera). Solo se restringe cuando hay una
denegación explícita.
"""

import logging

logger = logging.getLogger("gui.foundation.permissions")

VISIBLE = "visible"
OCULTO = "oculto"
SOLO_LECTURA = "solo_lectura"
EDITABLE = "editable"


def _perfil(usuario) -> str:
    if isinstance(usuario, dict):
        return str(usuario.get("perfil") or "").upper()
    return str(getattr(usuario, "perfil", "") or "").upper()


def _rbac(usuario, permiso) -> bool | None:
    """True/False si RBAC decide; None si no aplica/indeterminado (no bloquea)."""
    if not permiso:
        return None
    try:
        from src.services import autorizacion
        r = autorizacion.puede(usuario, permiso)
        return None if r is None else bool(r)
    except Exception as e:
        logger.debug("rbac: %s", e)
        return None


def _autoridad_ok(usuario, autoridad, id_empresa) -> bool | None:
    """Comprueba autoridad organizativa (Gobierno). None si no aplica."""
    if not autoridad:
        return None
    try:
        from src.services import gobierno
        uid = usuario.get("nombre") or usuario.get("usuario") if isinstance(usuario, dict) else str(usuario)
        ctx = gobierno.servicio().contexto_ia(uid, id_empresa, _perfil(usuario))
        permisos = ctx.get("permisos", []) if isinstance(ctx, dict) else []
        return (autoridad in permisos) if permisos else None
    except Exception as e:
        logger.debug("autoridad: %s", e)
        return None


def resolver(*, permiso=None, autoridad=None, solo_lectura_si_no_autoridad=True,
             usuario=None, id_empresa=None) -> str:
    """Estado visual resultante. Reglas:
       - RBAC deniega el permiso → OCULTO.
       - Autoridad requerida no cumplida → SOLO_LECTURA (o OCULTO si se configura).
       - En cualquier otro caso → EDITABLE (permisivo)."""
    r = _rbac(usuario, permiso)
    if r is False:
        return OCULTO
    a = _autoridad_ok(usuario, autoridad, id_empresa)
    if a is False:
        return SOLO_LECTURA if solo_lectura_si_no_autoridad else OCULTO
    return EDITABLE


def aplicar(widget, estado: str) -> None:
    """Aplica el estado visual a un widget Qt (best-effort; import de Qt diferido)."""
    try:
        if estado == OCULTO:
            widget.setVisible(False)
        elif estado == SOLO_LECTURA:
            widget.setVisible(True)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(False)
            if hasattr(widget, "setReadOnly"):
                try:
                    widget.setReadOnly(True)
                except Exception:
                    pass
        else:  # VISIBLE / EDITABLE
            widget.setVisible(True)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(True)
    except Exception as e:
        logger.debug("aplicar permiso: %s", e)


def puede_editar(estado: str) -> bool:
    return estado in (EDITABLE, VISIBLE)
