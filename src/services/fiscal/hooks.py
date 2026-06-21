"""
Ganchos de integración del núcleo fiscal con el TPV (C3.2).

`gancho_venta` se llama tras registrar una venta/factura. Está SIEMPRE detrás de
`fiscal_config.activo`: si la empresa no ha activado el módulo, retorna de inmediato
(una lectura de config por PK) → impacto prácticamente nulo y CERO cambio de flujo
en instalaciones existentes. Cuando está activo, genera el registro fiscal
(numeración + encadenado hash, síncrono) y lo encola para firma/envío asíncronos.

Es best-effort: NUNCA lanza ni revierte la venta (un fallo fiscal no debe impedir
cobrar). La política legal de atomicidad/bloqueo se concreta en C3.3 (Verifactu).
"""

import logging

logger = logging.getLogger("fiscal.hooks")


def fiscal_activo(id_empresa=None) -> bool:
    """True si la empresa tiene el módulo fiscal activado. Barato (PK lookup)."""
    try:
        from src.db import fiscal as F
        return bool(F.obtener_config(id_empresa).get("activo"))
    except Exception:
        return False


def gancho_venta(venta_id, total, tipo="ticket", referencia=None, id_caja=None,
                 id_empresa=None, id_tienda=None):
    """Genera (si el módulo está activo) el registro fiscal de una venta y lo
    encola. Devuelve el RegistroFiscal o None. Best-effort, no propaga errores."""
    try:
        from src.db import fiscal as F
        cfg = F.obtener_config(id_empresa)
        if not cfg.get("activo"):
            return None                      # desactivado → no-op
        # H4 — idempotencia: una referencia de venta = un registro fiscal. Si ya existe,
        # se devuelve sin volver a registrar (evita doble registro en reproceso/recuperación).
        _ref = referencia or str(venta_id)
        ya = F.existe_registro(_ref, id_empresa)
        if ya:
            return ya
        from src.services.fiscal.factory import proveedor_para
        prov = proveedor_para(cfg)
        if prov is None:
            return None
        reg = prov.registrar(tipo, referencia=_ref, total=total, id_caja=id_caja)
        if getattr(reg, "id", None):
            F.encolar(reg.id, id_empresa=id_empresa)   # firma/envío asíncronos
        return reg
    except Exception as e:
        logger.warning("gancho_venta(venta=%s): %s", venta_id, e)
        return None
