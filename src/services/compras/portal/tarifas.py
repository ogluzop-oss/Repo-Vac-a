"""Autoservicio de tarifas del proveedor en el portal.

El proveedor SUBE/ACTUALIZA su propia lista de precios (adiós al import manual desde la empresa). La
escritura REUTILIZA `proveedores_pro.set_precio_negociado` (misma tabla versionada de la bolsa); la
lectura muestra la tarifa vigente (la más reciente por artículo+unidad).
"""

from ._common import _conn, _emp, _filas, logger


def listar_tarifas(id_proveedor, id_empresa=None) -> list:
    """Tarifa vigente del proveedor (una fila por artículo+unidad, la más reciente)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT pn.codigo_articulo, pn.precio, pn.descuento, pn.unidad_medida, "
                "pn.cantidad_minima, pn.creada FROM proveedor_precios_negociados pn "
                "WHERE pn.id_empresa<=>%s AND pn.id_proveedor=%s AND pn.id=("
                "  SELECT MAX(pn2.id) FROM proveedor_precios_negociados pn2 "
                "  WHERE pn2.id_empresa<=>pn.id_empresa AND pn2.id_proveedor=pn.id_proveedor "
                "  AND pn2.codigo_articulo=pn.codigo_articulo AND pn2.unidad_medida=pn.unidad_medida) "
                "ORDER BY pn.codigo_articulo", (emp, id_proveedor))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_tarifas: %s", e)
        return []


def subir_tarifa(id_proveedor, codigo_articulo, precio, *, unidad_medida="unidad", descuento=0,
                 cantidad_minima=1, id_empresa=None):
    """Alta/actualización de una tarifa (el proveedor sube su precio). Reutiliza set_precio_negociado."""
    from src.services.compras.proveedores_pro import set_precio_negociado
    return set_precio_negociado(id_proveedor, str(codigo_articulo).strip().upper(), precio,
                                unidad_medida=unidad_medida, descuento=descuento,
                                cantidad_minima=cantidad_minima, id_empresa=id_empresa)
