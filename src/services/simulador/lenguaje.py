"""
Interprete de lenguaje natural del simulador (Paquete Enterprise 9, SUBFASE 9.10/9.11). Traduce
preguntas "¿que ocurriria si...?" a variables what-if, para que IAService y CopilotService creen y
evaluen escenarios conversacionalmente. Solo parsea; la simulacion la hace SimulationService.
"""

import re

_NUM_PALABRA = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "otra": 1, "otro": 1}

# Palabra clave → (variable, es_porcentaje, dominio)
_MAPA = [
    (("precio", "precios"), "precio", True),
    (("descuento", "descuentos", "rebaja"), "descuento", True),
    (("promocion", "promoción", "promo", "oferta"), "promocion", True),
    (("salario", "salarios", "sueldo", "sueldos", "nomina", "nómina"), "salario", True),
    (("empleado", "empleados", "contratar", "contratemos", "contratacion", "contratación",
      "plantilla", "despedir", "despido"), "plantilla", False),
    (("tienda", "tiendas", "sucursal", "local"), "tiendas", False),
    (("almacen", "almacén", "almacenes"), "almacenes", False),
    (("proveedor", "proveedores"), "proveedor", True),
    (("stock", "existencias", "inventario"), "stock", True),
    (("iva", "impuesto", "impuestos"), "impuestos", True),
    (("gasto", "gastos", "coste fijo", "costes fijos"), "gastos", False),
]

_NEG = ("baj", "reduc", "recort", "menos", "quit", "despedir", "despido", "cerrar", "cierre", "elimina")
_POS = ("sub", "aument", "increment", "mas", "más", "contrat", "abr", "nuev", "añad", "anad", "mejor")


def _signo(texto, variable) -> int:
    t = texto.lower()
    if any(k in t for k in _NEG):
        return -1
    if any(k in t for k in _POS):
        return 1
    return 1


def _numero(texto) -> float | None:
    m = re.search(r"(\d+[.,]?\d*)\s*%?", texto)
    if m:
        return float(m.group(1).replace(",", "."))
    for pal, n in _NUM_PALABRA.items():
        if re.search(rf"\b{pal}\b", texto.lower()):
            return float(n)
    return None


def es_pregunta_simulacion(texto) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in ("que ocurriria", "qué ocurriría", "que pasaria", "qué pasaría",
                                "que pasa si", "qué pasa si", "y si ", "simula", "simular",
                                "escenario", "que ocurre si", "qué ocurre si", "and if"))


def parsear(texto) -> list:
    """Devuelve una lista de variables what-if [{'variable':.., 'valor':..}]. Vacia si no detecta."""
    t = (texto or "").lower()
    num = _numero(t)
    variables = []
    for claves, variable, es_pct in _MAPA:
        if any(k in t for k in claves):
            signo = _signo(t, variable)
            if variable in ("tiendas", "almacenes", "plantilla"):
                valor = signo * (num if num is not None else 1)
            elif variable == "impuestos":
                valor = num if num is not None else 21
            elif variable == "gastos":
                valor = signo * (num if num is not None else 0)
            else:  # porcentuales
                valor = signo * (num if num is not None else 5)
            variables.append({"variable": variable, "valor": valor})
    return variables
