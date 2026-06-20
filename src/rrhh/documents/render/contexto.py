"""
Ejecución del render documental RRHH con contexto inyectado (F3.0.4b).

`ejecutar(impl, ctx)` ejecuta el cuerpo VERBATIM `impl` usando `ctx` como espacio de
nombres (globals). `ctx` se construye en el wizard como {**globals(), **locals()} tras
el preámbulo de `_generar_pdf`, replicando EXACTAMENTE el scope (Global+Local) que veían
las closures anidadas originales. No introduce lógica nueva: solo formaliza el contexto.
"""

import types


def ejecutar(impl, ctx):
    fn = types.FunctionType(impl.__code__, ctx, impl.__name__)
    fn()
