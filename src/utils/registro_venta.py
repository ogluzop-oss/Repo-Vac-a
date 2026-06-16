# src/utils/registro_venta.py
from datetime import datetime

from src.db.conexion import transaccion
from src.utils.logger import LOG_TPV

# ============================================================
# BLOQUE REGISTRO DE VENTAS EN BASE DE DATOS
# ============================================================

def registrar_venta(codigo: str, cantidad_vendida: int) -> bool:
    """
    Registra una venta y descuenta el stock de tienda (Stock_tienda).

    Parámetros:
        codigo (str): Código único del artículo vendido.
        cantidad_vendida (int): Unidades vendidas.

    Retorna:
        bool: True si la venta fue registrada correctamente.
    """
    try:
        # A2.2: transacción real + SELECT … FOR UPDATE → atómico y sin carrera
        # (el bloqueo de fila evita que dos ventas simultáneas sobrevendan).
        with transaccion() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT Stock_tienda FROM articulos WHERE codigo = %s FOR UPDATE", (codigo,)
            )
            resultado = cur.fetchone()

            if not resultado:
                LOG_TPV.warning("El artículo con código %r no existe en la base de datos.", codigo)
                return False

            stock_actual = resultado[0] if not isinstance(resultado, dict) else resultado["Stock_tienda"]

            if stock_actual < cantidad_vendida:
                print(
                    f"❌ Stock insuficiente para '{codigo}'. "
                    f"Stock actual: {stock_actual}, solicitado: {cantidad_vendida}."
                )
                return False

            fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # A4.1: etiquetar la venta con el tenant activo (no depender del default).
            from src.db.empresa import empresa_actual_id, tienda_actual_id
            cur.execute(
                "INSERT INTO ventas (codigo, cantidad, fecha, id_empresa, id_tienda) "
                "VALUES (%s, %s, %s, %s, %s)",
                (codigo, cantidad_vendida, fecha_venta, empresa_actual_id(), tienda_actual_id()),
            )
            cur.execute(
                "UPDATE articulos SET Stock_tienda = Stock_tienda - %s WHERE codigo = %s",
                (cantidad_vendida, codigo),
            )

            print(
                f"✅ Venta registrada: {cantidad_vendida} uds de '{codigo}'. "
                f"Nuevo stock tienda: {stock_actual - cantidad_vendida}"
            )
            return True

    except Exception:
        LOG_TPV.exception("Error al registrar la venta")
        return False
