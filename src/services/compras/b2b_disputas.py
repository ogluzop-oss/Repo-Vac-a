"""
Puente de disputas B2B (Smart Suppliers · Fase D). Requisito 6 del prompt original: "Las
reclamaciones o solicitudes de reembolso fuera de plazo se deben tramitar obligatoriamente a través de
las pestañas 'Incidencias' o 'Devoluciones' (requiriendo mediación o aprobación del proveedor)."

NO crea un sistema de incidencias/devoluciones nuevo: usa las funciones YA EXISTENTES de
`src/db/compras.py` (`registrar_incidencia`/`crear_devolucion`, las mismas que respaldan hoy las
pestañas "Incidencias"/"Devoluciones" del módulo de Compras) y solo las conecta con la custodia de
fondos del pedido B2B — abrir una disputa bloquea la liberación automática
(`b2b_escrow.abrir_disputa`) hasta que se resuelva.
"""

import logging

logger = logging.getLogger("compras.b2b_disputas")


def _contexto_transaccion(id_tx):
    """(id_empresa, id_suministrador) de la transacción, o (None, None) si no existe."""
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_empresa, id_suministrador FROM transaccion_comercial WHERE id_tx=%s",
                   (id_tx,))
        row = cur.fetchone()
    if not row:
        return None, None
    return (row if not isinstance(row, dict) else (row["id_empresa"], row["id_suministrador"]))


def _id_proveedor_de(id_empresa, id_suministrador) -> int | None:
    """Resuelve el `proveedores.id_proveedor` (registro POR EMPRESA) a partir del
    `id_suministrador` (identidad de plataforma, ver Fase A) — puente entre ambos mundos."""
    if not id_suministrador:
        return None
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_proveedor FROM proveedores WHERE id_suministrador=%s AND id_empresa=%s "
                   "LIMIT 1", (id_suministrador, id_empresa))
        row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["id_proveedor"]) if row else None


def abrir_disputa(id_tx, motivo: str, *, usuario=None) -> dict:
    """Abre la disputa: bloquea la custodia de fondos del pedido (no se libera solo ni por
    expiración) Y registra la reclamación en Incidencias (la pestaña existente, no una nueva)."""
    id_empresa, id_suministrador = _contexto_transaccion(id_tx)
    if not id_empresa:
        return {"ok": False, "error": "transaccion_no_encontrada"}

    from src.services.compras import b2b_escrow as ESC
    r_escrow = ESC.abrir_disputa(id_tx, actor=usuario)
    if not r_escrow.get("ok"):
        return r_escrow

    id_proveedor = _id_proveedor_de(id_empresa, id_suministrador)
    id_incidencia = None
    try:
        from src.db import compras as C
        id_incidencia = C.registrar_incidencia(
            "otros", id_proveedor=id_proveedor,
            descripcion=f"[Pedido B2B {id_tx}] {motivo}"[:255], usuario=usuario, id_empresa=id_empresa)
    except Exception as e:
        logger.error("abrir_disputa registrar_incidencia(%s): %s", id_tx, e)
    return {"ok": True, "escrow": r_escrow, "id_incidencia": id_incidencia}


def tramitar_devolucion(id_tx, lineas: list, motivo: str, *, usuario=None) -> dict:
    """Procesa la devolución física al proveedor (descuenta stock, kárdex — reutiliza
    `db.compras.crear_devolucion` tal cual). El reembolso depende de dónde estén los fondos:
    - Aún retenidos sin disputa (FUNDS_HELD/IN_FULFILLMENT): se reembolsan directamente
      (`cancelar_y_reembolsar`, autoservicio).
    - Retenidos por una disputa abierta (IN_DISPUTE — ver `abrir_disputa`): se reembolsan vía
      resolución mediada (`resolver_disputa_con_reembolso`) — el dinero SIGUE en custodia, no se ha
      liberado, solo bloqueado hasta que se resuelva.
    - Ya liberados al proveedor (cualquier otro estado): el dinero ya salió de la custodia y NO hay
      reembolso automático posible desde aquí — se marca explícitamente para conciliación manual en
      vez de fingir un reembolso que no ha ocurrido."""
    id_empresa, id_suministrador = _contexto_transaccion(id_tx)
    if not id_empresa:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    id_proveedor = _id_proveedor_de(id_empresa, id_suministrador)
    if not id_proveedor:
        return {"ok": False, "error": "proveedor_no_resuelto"}

    from src.db import compras as C
    id_devolucion = C.crear_devolucion(id_proveedor=id_proveedor, lineas=lineas, motivo=motivo,
                                       usuario=usuario, id_empresa=id_empresa)
    if not id_devolucion:
        return {"ok": False, "error": "no_se_pudo_registrar_la_devolucion"}

    from src.services.compras import b2b_escrow as ESC
    esc = ESC.estado(id_tx) or {}
    estado_pago = (esc.get("escrow") or {}).get("estado_pago")
    if estado_pago in ("FUNDS_HELD", "IN_FULFILLMENT"):
        r = ESC.cancelar_y_reembolsar(id_tx, motivo=f"Devolución: {motivo}", actor=usuario)
        return {"ok": True, "id_devolucion": id_devolucion, "reembolso": r, "conciliacion_manual": False}
    if estado_pago == "IN_DISPUTE":
        r = ESC.resolver_disputa_con_reembolso(id_tx, motivo=f"Devolución: {motivo}", actor=usuario)
        return {"ok": True, "id_devolucion": id_devolucion, "reembolso": r, "conciliacion_manual": False}
    return {"ok": True, "id_devolucion": id_devolucion, "reembolso": None, "conciliacion_manual": True,
           "aviso": "Los fondos ya se habían liberado al proveedor; requiere conciliación manual."}
