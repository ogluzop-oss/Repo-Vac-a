"""
Memoria conversacional del Copiloto (Paquete Enterprise 5, SUBFASE 5.4). Mantiene el ultimo
dominio/periodo y el historial por usuario (en proceso, nada sensible persistido) para resolver
seguimientos: "¿y respecto a la semana pasada?" tras "¿como van las ventas?".
"""

_MEM = {}   # usuario -> {"dominio","periodo","consultas":[...]}


def contexto(usuario) -> dict:
    return _MEM.get(str(usuario), {"consultas": []})


def recordar(usuario, *, dominio=None, periodo=None, consulta=None) -> dict:
    m = _MEM.setdefault(str(usuario), {"consultas": []})
    if dominio and dominio != "general":
        m["dominio"] = dominio
    if periodo:
        m["periodo"] = periodo
    if consulta:
        m["consultas"] = (m.get("consultas", []) + [consulta])[-20:]
    return m


def limpiar(usuario=None):
    if usuario is None:
        _MEM.clear()
    else:
        _MEM.pop(str(usuario), None)
