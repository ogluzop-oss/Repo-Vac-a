"""
Generador y validador de códigos de barras EAN-13.

Un EAN-13 son 13 dígitos: 12 de datos + 1 dígito de control calculado con la fórmula módulo-10 de GS1
(suma ponderada 1,3,1,3,… de derecha a izquierda sobre los 12 primeros; el control es lo que falta para
la decena superior). Aquí generamos el prefijo con el rango RESERVADO A USO INTERNO/INSTORE (GS1 asigna
'20'–'29' a códigos internos de tienda, no exportables a terceros), evitando colisiones con EAN reales de
fabricante. La unicidad frente al catálogo se comprueba con `existe_fn` (inyectado por la GUI).
"""

import random

PREFIJO_INTERNO = "20"   # rango GS1 reservado a códigos internos (no fabricante)


def digito_control(doce: str) -> int:
    """Dígito de control (checksum módulo-10 GS1) de una cadena de 12 dígitos."""
    d = [int(c) for c in str(doce)]
    if len(d) != 12:
        raise ValueError("EAN-13: se requieren 12 dígitos para calcular el control.")
    # Ponderación 1,3,1,3,… empezando por el primer dígito (posición impar peso 1).
    suma = sum(v * (1 if i % 2 == 0 else 3) for i, v in enumerate(d))
    return (10 - (suma % 10)) % 10


def es_valido(codigo: str) -> bool:
    """True si `codigo` es un EAN-13 numérico de 13 dígitos con el dígito de control correcto."""
    c = str(codigo or "").strip()
    if len(c) != 13 or not c.isdigit():
        return False
    return digito_control(c[:12]) == int(c[12])


def _construir(cuerpo_11: str) -> str:
    doce = f"{PREFIJO_INTERNO}{cuerpo_11}"[:12].ljust(12, "0")
    return f"{doce}{digito_control(doce)}"


def generar(existe_fn=None, intentos: int = 1000) -> str | None:
    """Genera un EAN-13 VÁLIDO y ÚNICO (prefijo interno '20' + 10 dígitos aleatorios + control).
    `existe_fn(codigo)->bool` decide si ya existe en el catálogo; si se agotan los intentos, None."""
    for _ in range(max(1, intentos)):
        cuerpo = "".join(str(random.randint(0, 9)) for _ in range(10))  # 10 dígitos tras el prefijo '20'
        codigo = _construir(cuerpo)
        if existe_fn is None or not existe_fn(codigo):
            return codigo
    return None
