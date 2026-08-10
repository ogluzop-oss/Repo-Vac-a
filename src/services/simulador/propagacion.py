"""
Motor de PROPAGACION del simulador (Paquete Enterprise 9, SUBFASE 9.4).

Cuando una variable cambia, propaga automaticamente sus consecuencias por la cadena de valor
(la misma que modela el grafo del Gemelo Digital):

    Subir precio → menos ventas → menos reposiciones → menos compras → menos ingresos
                 → menos IVA → menos beneficio

Cada regla transforma el cuadro de metricas y deja traza de la cadena causal para la
explicabilidad. Las elasticidades son HEURISTICAS por defecto, enchufables (mismo espiritu que el
Estimador de PredictionService): se pueden sustituir sin tocar el resto.
"""

import logging

logger = logging.getLogger("simulador.propagacion")

# Elasticidades por defecto (configurables). Signo segun efecto sobre la DEMANDA (unidades).
ELASTICIDAD_PRECIO = -1.2     # +1% precio → -1.2% unidades
ELASTICIDAD_DESCUENTO = 0.8   # +1% descuento → +0.8% unidades
ELASTICIDAD_PROMO = 1.0       # +1% intensidad promo → +1.0% unidades (con coste en margen)


def _pct(v):
    """Normaliza un porcentaje: admite 5 (=5%) o 0.05 (=5%)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v / 100.0 if abs(v) > 1 else v


def _recomputar_derivadas(m, iva_tipo=0.21):
    """Recalcula beneficio/margen/IVA de forma coherente tras alterar componentes."""
    m["iva"] = round(m["ingresos"] * iva_tipo, 2)
    m["beneficio"] = round(m["ingresos"] - m["coste_ventas"] - m["coste_personal"] - m["gastos"], 2)
    m["margen_pct"] = round((m["beneficio"] / m["ingresos"] * 100) if m["ingresos"] else 0.0, 2)
    return m


# ── Reglas de propagacion por variable ────────────────────────────────────────
def _aplicar_precio(m, valor, traza):
    p = _pct(valor)
    dem = ELASTICIDAD_PRECIO * p
    m["unidades"] = round(m["unidades"] * (1 + dem), 2)
    m["ingresos"] = round(m["ingresos"] * (1 + p) * (1 + dem), 2)
    m["coste_ventas"] = round(m["coste_ventas"] * (1 + dem), 2)   # menos unidades → menos COGS
    traza.append(f"precio {p*100:+.1f}% → demanda {dem*100:+.1f}% → ingresos y coste_ventas ajustados")


def _aplicar_descuento(m, valor, traza):
    d = _pct(valor)
    dem = ELASTICIDAD_DESCUENTO * d
    m["unidades"] = round(m["unidades"] * (1 + dem), 2)
    m["ingresos"] = round(m["ingresos"] * (1 - d) * (1 + dem), 2)
    m["coste_ventas"] = round(m["coste_ventas"] * (1 + dem), 2)
    traza.append(f"descuento {d*100:.1f}% → demanda {dem*100:+.1f}% → ingresos netos y COGS ajustados")


def _aplicar_promocion(m, valor, traza):
    x = _pct(valor)
    dem = ELASTICIDAD_PROMO * x
    m["unidades"] = round(m["unidades"] * (1 + dem), 2)
    m["ingresos"] = round(m["ingresos"] * (1 + dem) * (1 - x * 0.5), 2)  # coste de la promo en margen
    m["coste_ventas"] = round(m["coste_ventas"] * (1 + dem), 2)
    traza.append(f"promocion intensidad {x*100:.1f}% → demanda {dem*100:+.1f}% (coste en margen)")


def _aplicar_salario(m, valor, traza):
    s = _pct(valor)
    m["coste_personal"] = round(m["coste_personal"] * (1 + s), 2)
    traza.append(f"salarios {s*100:+.1f}% → coste_personal {s*100:+.1f}%")


def _aplicar_plantilla(m, valor, traza):
    # valor = numero de empleados (delta absoluto). Coste medio via base.SALARIO_MEDIO_MES.
    from src.services.simulador.base import SALARIO_MEDIO_MES
    n = int(valor)
    m["plantilla"] = max(0, int(m["plantilla"]) + n)
    m["coste_personal"] = round(m["coste_personal"] + n * SALARIO_MEDIO_MES, 2)
    # Efecto suave sobre capacidad de venta (rendimientos decrecientes).
    if m["plantilla"] and n:
        factor = 1 + (n / max(m["plantilla"], 1)) * 0.15
        m["ingresos"] = round(m["ingresos"] * factor, 2)
        m["unidades"] = round(m["unidades"] * factor, 2)
        m["coste_ventas"] = round(m["coste_ventas"] * factor, 2)
    traza.append(f"plantilla {n:+d} empleados → coste_personal y capacidad ajustados")


def _aplicar_stock(m, valor, traza):
    x = _pct(valor)
    # Mas stock reduce roturas (hasta 0); menos stock las aumenta.
    m["stock_roturas"] = max(0, round(m["stock_roturas"] * (1 - x)))
    traza.append(f"stock {x*100:+.1f}% → roturas previstas ajustadas")


def _aplicar_proveedor(m, valor, traza):
    # valor = variacion del coste de compra (%). -10 = proveedor 10% mas barato.
    c = _pct(valor)
    m["coste_ventas"] = round(m["coste_ventas"] * (1 + c), 2)
    traza.append(f"coste proveedor {c*100:+.1f}% → coste_ventas {c*100:+.1f}%")


def _aplicar_impuestos(m, valor, traza):
    # valor = nuevo tipo IVA (p.ej. 0.10) o variacion en puntos si >1.
    nuevo = float(valor)
    tipo = nuevo if nuevo < 1 else nuevo / 100.0
    m["_iva_tipo"] = tipo
    traza.append(f"tipo IVA → {tipo*100:.1f}%")


def _aplicar_gastos(m, valor, traza):
    # valor absoluto en euros (delta) o % si se marca. Aqui: delta absoluto.
    try:
        delta = float(valor)
    except (TypeError, ValueError):
        delta = 0.0
    m["gastos"] = round(m["gastos"] + delta, 2)
    traza.append(f"gastos {delta:+.2f} € → gastos operativos ajustados")


def _aplicar_tiendas(m, valor, traza):
    n = int(valor)
    # Cada tienda nueva aporta ingresos ~ media por tienda actual (proxy) y sus costes.
    if n:
        # Estimacion: la empresa tiene >=1 tienda; se asume aporte proporcional prudente.
        aporte = 0.6  # una tienda nueva rinde al 60% de la media el primer periodo
        m["ingresos"] = round(m["ingresos"] * (1 + n * aporte), 2)
        m["unidades"] = round(m["unidades"] * (1 + n * aporte), 2)
        m["coste_ventas"] = round(m["coste_ventas"] * (1 + n * aporte), 2)
        m["gastos"] = round(m["gastos"] * (1 + n * 0.4), 2)
    traza.append(f"{n:+d} tienda(s) → ingresos, coste_ventas y gastos escalados (rendimiento prudente)")


def _aplicar_almacenes(m, valor, traza):
    n = int(valor)
    m["gastos"] = round(m["gastos"] * (1 + n * 0.05), 2)      # coste logistico
    m["stock_roturas"] = max(0, round(m["stock_roturas"] * (1 - n * 0.1)))  # mejor cobertura
    traza.append(f"{n:+d} almacen(es) → coste logistico y menor rotura")


_REGLAS = {
    "precio": _aplicar_precio,
    "descuento": _aplicar_descuento,
    "promocion": _aplicar_promocion,
    "salario": _aplicar_salario,
    "plantilla": _aplicar_plantilla,
    "stock": _aplicar_stock,
    "proveedor": _aplicar_proveedor,
    "impuestos": _aplicar_impuestos,
    "gastos": _aplicar_gastos,
    "tiendas": _aplicar_tiendas,
    "almacenes": _aplicar_almacenes,
}

VARIABLES = tuple(_REGLAS.keys())


def propagar(metricas_base, variables) -> dict:
    """Aplica las variables (en orden) sobre una COPIA de las metricas base y propaga
    consecuencias. Devuelve {metricas, cadena}. No modifica la entrada ni datos reales."""
    m = dict(metricas_base)
    m["_iva_tipo"] = 0.21
    cadena = []
    for v in variables:
        nombre = v.get("variable")
        regla = _REGLAS.get(nombre)
        if not regla:
            cadena.append(f"variable '{nombre}' desconocida (ignorada)")
            continue
        try:
            regla(m, v.get("valor"), cadena)
        except Exception as e:
            logger.debug("regla %s: %s", nombre, e)
    _recomputar_derivadas(m, iva_tipo=m.pop("_iva_tipo", 0.21))
    return {"metricas": m, "cadena": cadena}
