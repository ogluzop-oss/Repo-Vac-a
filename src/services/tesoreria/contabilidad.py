"""
Integración contable de Tesorería (rama Tesorería, FASE 10).

Cada movimiento de tesorería (cobro/pago/transferencia) y las diferencias de conciliación
generan un asiento contable usando el patrón M1: asientos.crear_asiento(idempotente=True,
ref_origen=...), de modo que el reproceso NUNCA duplica el asiento. Respeta el interruptor de
contabilidad (no-op si está apagada). Cuentas PGC: 572 bancos, 570 caja, 430 clientes,
400 proveedores. No modifica el núcleo de contabilidad (posting/asientos).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID

logger = logging.getLogger("tesoreria_contab")

CUENTA_BANCO = "572"
CUENTA_CAJA = "570"
CUENTA_CLIENTES = "430"
CUENTA_PROVEEDORES = "400"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _activa(id_empresa):
    try:
        from src.services.contabilidad import cuentas as K
        return K.contabilidad_activa(id_empresa)
    except Exception:
        return False


def _cuenta_tesoreria(id_cuenta):
    """572 (banco) si el movimiento va a una cuenta bancaria; 570 (caja) si no hay cuenta."""
    return CUENTA_BANCO if id_cuenta is not None else CUENTA_CAJA


def _crear(fecha, lineas, concepto, ref, id_empresa):
    from src.services.contabilidad import asientos
    return asientos.crear_asiento(fecha, lineas, concepto=concepto, tipo="normal",
                                  origen="tesoreria", ref_origen=ref, idempotente=True,
                                  id_empresa=id_empresa)


def contabilizar_movimiento(mov: dict, id_empresa=None):
    """Asiento de un movimiento de tesorería (COBRO/PAGO). Idempotente por ref 'tes:<id>'.
    COBRO: Debe 572/570, Haber 430 (cliente). PAGO: Debe 400 (proveedor), Haber 572/570."""
    id_empresa = _emp(id_empresa)
    if not _activa(id_empresa):
        return None
    tipo = (mov.get("tipo") or "").upper()
    importe = abs(round(float(mov.get("importe") or 0), 2))
    if importe <= 0:
        return None
    ref = f"tes:{mov['id']}"
    cta_tes = _cuenta_tesoreria(mov.get("id_cuenta"))
    concepto = mov.get("concepto") or f"Tesorería {tipo}"
    if tipo == "COBRO":
        lineas = [{"codigo_cuenta": cta_tes, "descripcion": concepto, "debe": importe, "haber": 0},
                  {"codigo_cuenta": CUENTA_CLIENTES, "descripcion": concepto, "debe": 0, "haber": importe}]
    elif tipo == "PAGO":
        lineas = [{"codigo_cuenta": CUENTA_PROVEEDORES, "descripcion": concepto, "debe": importe, "haber": 0},
                  {"codigo_cuenta": cta_tes, "descripcion": concepto, "debe": 0, "haber": importe}]
    else:
        return None
    try:
        return _crear(mov.get("fecha"), lineas, concepto, ref, id_empresa)
    except Exception as e:
        logger.warning("contabilizar_movimiento(%s): %s", ref, e)
        return None


def contabilizar_transferencia(ref_trf, fecha, importe, id_empresa=None):
    """Asiento de una transferencia entre cuentas propias: Debe 572 / Haber 572 (neto 0
    a nivel de grupo, pero deja traza). Idempotente por ref 'trf:<ref>'."""
    id_empresa = _emp(id_empresa)
    if not _activa(id_empresa):
        return None
    importe = abs(round(float(importe or 0), 2))
    if importe <= 0:
        return None
    lineas = [{"codigo_cuenta": CUENTA_BANCO, "descripcion": "Transferencia (destino)", "debe": importe, "haber": 0},
              {"codigo_cuenta": CUENTA_BANCO, "descripcion": "Transferencia (origen)", "debe": 0, "haber": importe}]
    try:
        return _crear(fecha, lineas, "Transferencia entre cuentas", f"trf:{ref_trf}", id_empresa)
    except Exception as e:
        logger.warning("contabilizar_transferencia(%s): %s", ref_trf, e)
        return None


def contabilizar_diferencia_conciliacion(id_conciliacion, fecha, diferencia, id_empresa=None):
    """Asiento de la diferencia bancaria de una conciliación (p.ej. comisiones).
    diferencia>0 (cargo no registrado): Debe 626 (servicios bancarios) / Haber 572.
    Idempotente por ref 'conc:<id>'. Solo si hay diferencia != 0."""
    id_empresa = _emp(id_empresa)
    if not _activa(id_empresa):
        return None
    dif = round(float(diferencia or 0), 2)
    if dif == 0:
        return None
    imp = abs(dif)
    if dif > 0:
        lineas = [{"codigo_cuenta": "626", "descripcion": "Diferencia conciliación", "debe": imp, "haber": 0},
                  {"codigo_cuenta": CUENTA_BANCO, "descripcion": "Diferencia conciliación", "debe": 0, "haber": imp}]
    else:
        lineas = [{"codigo_cuenta": CUENTA_BANCO, "descripcion": "Diferencia conciliación", "debe": imp, "haber": 0},
                  {"codigo_cuenta": "769", "descripcion": "Diferencia conciliación", "debe": 0, "haber": imp}]
    try:
        return _crear(fecha, lineas, "Diferencia de conciliación", f"conc:{id_conciliacion}", id_empresa)
    except Exception as e:
        logger.warning("contabilizar_diferencia(%s): %s", id_conciliacion, e)
        return None
