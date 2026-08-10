"""
FASE 3.7 — Remesas SEPA de COBRO de cliente (adeudos directos, pain.008).

Puente que emite remesas DESDE LOS VENCIMIENTOS AR (cuentas a cobrar), NO desde las facturas
directamente, reutilizando el MOTOR SEPA existente (`src.db.sepa` + `src.services.tesoreria.sepa`).
No duplica nada: el ciclo de estados, la numeración de la remesa, la validación de IBAN/XSD y la
auditoría (fecha/usuario/empresa/remesa/estado) las gestiona el módulo SEPA ya validado.
"""

import logging

logger = logging.getLogger("facturacion.remesas_cliente")


def cobros_ar_pendientes(id_empresa=None) -> list:
    """Vencimientos de COBRO (AR) pendientes/parciales — candidatos a remesa de adeudo."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        from src.db.empresa import empresa_actual_id
        emp = id_empresa or empresa_actual_id()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, importe, pendiente, tercero, concepto, fecha_vencimiento, "
                        "id_documento FROM vencimientos WHERE id_empresa=%s AND tipo='COBRO' "
                        "AND estado IN ('PENDIENTE','PARCIAL') AND pendiente>0 "
                        "ORDER BY fecha_vencimiento", (emp,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("cobros_ar_pendientes: %s", e)
        return []


def crear_remesa_cobros(operaciones, *, id_cuenta=None, id_empresa=None) -> int | None:
    """Crea una remesa SEPA de ADEUDO (pain.008) de cobros de cliente a partir de vencimientos AR.

    operaciones = [{id_vencimiento, nombre, iban, importe, concepto, bic?}].
    Reutiliza `db.sepa` (valida IBAN, audita). Devuelve id_remesa (estado 'borrador').
    El XML se genera con `generar_xml_remesa`. Best-effort por operación: una operación con
    IBAN inválido se omite sin abortar la remesa."""
    from src.db import sepa as S
    rid = S.crear_remesa("ADEUDO", id_cuenta=id_cuenta, id_empresa=id_empresa)
    if not rid:
        return None
    n = 0
    for op in (operaciones or []):
        try:
            S.anadir_operacion(
                rid, op.get("nombre") or "Cliente", op.get("iban"), op.get("importe"),
                concepto=op.get("concepto"), bic=op.get("bic"),
                id_vencimiento=op.get("id_vencimiento"), id_empresa=id_empresa)
            n += 1
        except Exception as e:
            logger.warning("remesa cobro op (omitida): %s", e)
    return rid if n else rid  # devuelve la remesa aunque queden 0 ops (se podrá completar)


def generar_xml_remesa(id_remesa, id_empresa=None) -> dict:
    """Genera y valida el XML pain.008 de la remesa (reutiliza tesoreria.sepa.generar_xml)."""
    from src.services.tesoreria import sepa as SX
    return SX.generar_xml(id_remesa, id_empresa=id_empresa)
