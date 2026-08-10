"""
Servicio ÚNICO de salida de stock — política única, AGNÓSTICO del origen (TPV, Comercio Digital, …).

Extrae la lógica oficial existente (antes embebida en `registrar_venta_con_items`) a un servicio
reutilizable, SIN cambiar su comportamiento: decremento físico de sala (clamp M4 `Stock_tienda`) +
kárdex `SALIDA_*` idempotente + consumo FEFO de lotes + reseed multialmacén. Idempotente por
(codigo, tipo, id_documento) a nivel de kárdex/FEFO.

NO crea ventas, NO duplica contabilidad ni Verifactu, NO introduce una nueva política de salida:
únicamente reutiliza los primitivos oficiales ya existentes.
"""

import logging

logger = logging.getLogger("db.salida_stock")


def salida_stock_ledger(codigo, cantidad, *, id_documento, id_empresa, id_tienda=None,
                        tipo="SALIDA_VENTA", origen="TIENDA", usuario=None, observaciones=None) -> dict:
    """Parte NO transaccional de la salida oficial (best-effort, tras el commit del llamador): kárdex
    idempotente + consumo FEFO + reseed multialmacén. Devuelve {id_almacen, id_lote} (trazabilidad).
    Es EXACTAMENTE lo que hacía `registrar_venta_con_items` tras commit, extraído sin cambios."""
    cod = str(codigo or "")
    qty = int(cantidad or 0)
    res = {"id_almacen": None, "id_lote": None}
    if not cod or qty <= 0:
        return res
    # INV.1 — kárdex SALIDA idempotente.
    try:
        from src.db import kardex
        kardex.registrar_movimiento(cod, tipo, qty, id_documento=id_documento, origen=origen,
                                    usuario=usuario, id_empresa=id_empresa, id_tienda=id_tienda,
                                    idempotente=True, observaciones=observaciones)
    except Exception as e:
        logger.debug("kardex salida (%s): %s", cod, e)
    # INV.3 + VTA.5 — consumo FEFO de lotes y almacén de salida.
    try:
        from src.db import lotes
        from src.db import stock_almacen as _SA
        destino = _SA.almacen_de_tienda(id_tienda, id_empresa) if id_tienda else _SA.almacen_central(id_empresa)
        r = lotes.consumir_fefo(cod, qty, tipo=tipo, id_empresa=id_empresa, id_tienda=id_tienda,
                                id_documento=id_documento, idempotente=True, usuario=usuario)
        res["id_almacen"] = destino
        res["id_lote"] = (r.get("detalle") or [{}])[0].get("id_lote") if r else None
    except Exception as e:
        logger.debug("FEFO salida (%s): %s", cod, e)
    # INV.4 — reseed multialmacén si el artículo está gestionado.
    try:
        from src.db import stock_almacen as SA
        if SA.esta_gestionado(cod, id_empresa):
            SA.reseed_articulo(cod, id_empresa)
    except Exception as e:
        logger.debug("reseed salida (%s): %s", cod, e)
    return res


def salida_fisica_clamp(cur, codigo, cantidad, *, contexto="salida", id_empresa=None) -> int:
    """Decremento físico de sala (clamp M4 `Stock_tienda`, nunca negativo) DENTRO de una transacción
    abierta (`cur`). Reutiliza la política única existente; devuelve el faltante (sobreventa)."""
    from src.db.conexion import _salida_stock_clamp
    return _salida_stock_clamp(cur, codigo, cantidad, contexto, id_empresa=id_empresa)


def salida_stock_oficial(codigo, cantidad, *, id_documento, id_empresa, id_tienda=None,
                         contexto="salida", tipo="SALIDA_VENTA", origen="TIENDA", usuario=None,
                         observaciones=None) -> dict:
    """Salida COMPLETA por la política única, para orígenes SIN transacción abierta (Comercio Digital
    u otros): decremento físico (clamp, tx propia) + ledger oficial (kárdex/FEFO/reseed). Idempotente
    por (codigo, tipo, id_documento) a nivel de kárdex/FEFO. Mismo flujo que la venta de sala."""
    from src.db.conexion import transaccion
    faltante = 0
    try:
        with transaccion() as conn, conn.cursor() as cur:
            faltante = salida_fisica_clamp(cur, codigo, cantidad, contexto=contexto,
                                           id_empresa=id_empresa)
    except Exception as e:
        logger.warning("salida_stock_oficial clamp (%s): %s", codigo, e)
    led = salida_stock_ledger(codigo, cantidad, id_documento=id_documento, id_empresa=id_empresa,
                              id_tienda=id_tienda, tipo=tipo, origen=origen, usuario=usuario,
                              observaciones=observaciones)
    return {"faltante": faltante, **led}


__all__ = ["salida_stock_ledger", "salida_fisica_clamp", "salida_stock_oficial"]
