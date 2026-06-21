# src/utils/registro_venta.py
from src.utils.logger import LOG_TPV

# ============================================================
# BLOQUE REGISTRO DE VENTAS EN BASE DE DATOS
# ============================================================

def registrar_venta(codigo: str, cantidad_vendida: int) -> bool:
    """Registra una venta de un artículo. H2: DELEGA en la ruta canónica
    `conexion.registrar_venta_con_items` para que la venta sincronizada reciba el MISMO
    tratamiento que cualquier otra (Verifactu, contabilidad, kárdex, FEFO, stock_almacen,
    política M4 de salida de stock — nunca negativo). Mantiene el contrato (codigo, cantidad)
    → bool para compatibilidad con `utils/sincronizar_ventas.py`."""
    try:
        from src.db.conexion import registrar_venta_con_items, obtener_articulo
        cantidad = int(cantidad_vendida or 0)
        if not codigo or cantidad <= 0:
            return False
        art = obtener_articulo(codigo) or {}
        if not art:
            LOG_TPV.warning("El artículo con código %r no existe en la base de datos.", codigo)
            return False
        # Conserva la garantía histórica de esta ruta: NO vender sin stock suficiente.
        stock_actual = int(art.get("Stock_tienda") or 0)
        if stock_actual < cantidad:
            LOG_TPV.warning("Stock insuficiente para %r (%s<%s).", codigo, stock_actual, cantidad)
            return False
        precio = float(art.get("precio") or 0)
        vid = registrar_venta_con_items(
            [{"codigo_articulo": codigo, "nombre": art.get("nombre"), "cantidad": cantidad,
              "precio_unitario": precio, "subtotal": round(precio * cantidad, 2)}],
            forma_pago="sincronizada")
        return bool(vid)
    except Exception:
        LOG_TPV.exception("Error al registrar la venta")
        return False
