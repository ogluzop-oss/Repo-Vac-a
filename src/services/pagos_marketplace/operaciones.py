"""
Orquestación de alto nivel del Marketplace + Pagos (F5) — capa fina que consume la GUI.

Reúne cuentas conectadas (KYB), escrow y ledger en operaciones listas para la interfaz, para que las
ventanas SOLO orqueste (regla de arquitectura: nada de lógica de negocio en la GUI). El step-up MFA de la
liberación de fondos se aplica en el chokepoint de la GUI (patrón `mfa_gui.step_up_sesion`), después de RBAC.
"""

import logging

logger = logging.getLogger("pagos_marketplace.operaciones")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


# ── Cuentas conectadas (KYB) ─────────────────────────────────────────────────
def conectar_cobros(tipo_parte, id_parte, *, email=None, id_empresa=None) -> dict:
    """Inicia el onboarding KYB de una parte (proveedor/vendedor/empresa) en el PSP."""
    from src.services.pagos_marketplace import cuentas
    return cuentas.crear_onboarding(tipo_parte, id_parte, email=email, id_empresa=id_empresa)


def estado_cobros(tipo_parte, id_parte, *, refrescar=False, id_empresa=None) -> dict | None:
    """Resumen de cobros para la UI (banco/últimos4/estado). Si `refrescar`, consulta el PSP antes."""
    from src.services.pagos_marketplace import cuentas
    if refrescar:
        r = cuentas.refrescar_estado(tipo_parte, id_parte, id_empresa=id_empresa)
        if r.get("resumen"):
            return r["resumen"]
    return cuentas.resumen(tipo_parte, id_parte, id_empresa=id_empresa)


# ── Transacciones + escrow ───────────────────────────────────────────────────
def transacciones(id_empresa=None, *, solo_con_escrow=False, limite=200) -> list:
    """Transacciones de la Lonja de la empresa (compradora) con su estado de pago, para la tabla de la UI."""
    emp = _emp(id_empresa)
    from src.services.lonja._common import _conn, _filas
    cond = "id_empresa=%s" + (" AND estado_pago IS NOT NULL" if solo_con_escrow else "")
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_listado, id_vendedor, cantidad, precio_unitario, divisa, tipo, "
                        "estado_pago, comision_importe, creado_en FROM lonja_transacciones "
                        "WHERE " + cond + " ORDER BY id DESC LIMIT %s", (emp, int(limite)))
            filas = _filas(cur)
        for f in filas:
            f["importe"] = float(f.get("cantidad") or 0) * float(f.get("precio_unitario") or 0)
        return filas
    except Exception as e:
        logger.error("transacciones: %s", e)
        return []


def confirmar_recepcion(id_transaccion) -> dict:
    """El comprador confirma la recepción conforme → libera los fondos (DELIVERY_CONFIRMED → FUNDS_RELEASED)."""
    from src.services.pagos_marketplace import escrow
    return escrow.confirmar_entrega(id_transaccion)


def abrir_disputa(id_transaccion, motivo=None) -> dict:
    from src.services.pagos_marketplace import escrow
    return escrow.abrir_disputa(id_transaccion, motivo=motivo)


def liberar(id_transaccion) -> dict:
    """Libera fondos manualmente (acción crítica: la GUI exige step-up MFA ANTES de llamar aquí)."""
    from src.services.pagos_marketplace import escrow
    return escrow.liberar(id_transaccion)


def reembolsar(id_transaccion, *, importe=None) -> dict:
    from src.services.pagos_marketplace import escrow
    return escrow.reembolsar(id_transaccion, importe=importe)


def ledger(id_transaccion) -> list:
    """Historial inmutable de movimientos de una transacción (para el visor de la UI)."""
    from src.services.pagos_marketplace import ledger as L
    return L.libro(id_transaccion)
