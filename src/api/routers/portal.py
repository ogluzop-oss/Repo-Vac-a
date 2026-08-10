"""
Router del Portal Web (Back Office) — Fase WEB-04. Router DELGADO que delega en el módulo independiente
`src/portal_web`. No contiene lógica: sólo cablea las rutas del portal en el blueprint API existente (N7).
"""


def registrar(bp):
    from src.portal_web.backend import rutas
    rutas.registrar(bp)
