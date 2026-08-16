"""Vista UNIFICADA de la bolsa: tarifas fijas (per-tenant) + ofertas en vivo de la Lonja (mercado
compartido), clasificadas por origen y con el precio en la divisa original + convertido a la divisa de
referencia de la empresa (comparación justa).

No duplica lógica: agrega `proveedores_pro.bolsa_precios` (tarifas negociadas privadas) con
`lonja.listados.listar` (mercado público) y usa la conversión de `lonja.divisa`.
"""

from ._common import logger
from . import divisa as _d
from . import listados as _l
from . import transacciones as _t


def divisa_referencia() -> str:
    """Divisa de referencia de la empresa (con la que comparar). Cae a EUR si no hay multidivisa."""
    try:
        from src.utils import divisas
        return (divisas.divisa_actual() or "EUR").upper()
    except Exception:
        return "EUR"


def bolsa_unificada(codigo_articulo, *, id_empresa=None, divisa_ref=None) -> dict:
    """Devuelve {divisa_ref, filas[]}. Cada fila: origen('tarifa'|'lonja'), proveedor, precio, divisa,
    precio_ref (convertido), puja_minima(_ref), mejor_puja_ref, unidad, disponible, compra_directa, puja,
    id_listado, id_proveedor. Ordenadas por precio de referencia (más barato arriba)."""
    ref = (divisa_ref or divisa_referencia())
    cod = str(codigo_articulo or "").strip().upper()
    filas = []
    # 1) Tarifas fijas per-tenant (bolsa de proveedores existente: precios negociados privados).
    try:
        from src.services.compras import proveedores_pro as PP
        for t in PP.bolsa_precios(cod, id_empresa=id_empresa):
            precio = float(t.get("precio_neto") or t.get("precio") or 0)
            div = (t.get("divisa") or "EUR")
            filas.append({
                "origen": "tarifa", "proveedor": t.get("proveedor"),
                "precio": precio, "divisa": div, "precio_ref": _d.convertir(precio, div, ref),
                "puja_minima": None, "puja_minima_ref": None, "mejor_puja_ref": None,
                "unidad": t.get("unidad_medida"), "disponible": None,
                "compra_directa": True, "puja": False,
                "id_listado": None, "id_proveedor": t.get("id_proveedor"),
            })
    except Exception as e:
        logger.debug("bolsa_unificada tarifas: %s", e)
    # 2) Ofertas en vivo de la Lonja (mercado compartido entre empresas).
    try:
        for l in _l.listar(cod):
            precio = float(l.get("precio") or 0)
            div = (l.get("divisa") or "EUR")
            pmin = float(l.get("puja_minima") or 0)
            mp = _t.mejor_puja(l["id"])
            mp_ref = _d.convertir(float(mp["importe"]), mp["divisa"], ref) if mp else None
            filas.append({
                "origen": "lonja", "proveedor": l.get("vendedor"),
                "precio": precio, "divisa": div, "precio_ref": _d.convertir(precio, div, ref),
                "puja_minima": pmin, "puja_minima_ref": _d.convertir(pmin, div, ref), "mejor_puja_ref": mp_ref,
                "unidad": l.get("unidad_medida"),
                "disponible": float(l.get("cantidad_disponible") or 0),
                "compra_directa": bool(int(l.get("permite_compra_directa") or 0)),
                "puja": bool(int(l.get("permite_puja") or 0)),
                "id_listado": l["id"], "id_proveedor": None,
            })
    except Exception as e:
        logger.debug("bolsa_unificada lonja: %s", e)
    filas.sort(key=lambda r: (r.get("precio_ref") if r.get("precio_ref") is not None else 1e18))
    return {"divisa_ref": ref, "filas": filas}
