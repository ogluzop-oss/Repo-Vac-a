"""
Router /sales — Ventas (Fase 8 móvil): facturación de hoy/semana/mes, con filtro opcional por sección.
Consulta `services.ventas.resumen`, que delega 100% en `db.ventas_analitica` (mismo motor del
dashboard de escritorio `gui/ventas`) — no reimplementa ningún criterio de agregación.

Sin permiso RBAC dedicado todavía (igual que el resto de routers móviles): exige solo autenticación.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/sales/summary")
    @requiere_auth()
    def sales_resumen():
        from flask import g, jsonify, request
        from src.services import ventas
        seccion = request.args.get("seccion") or None
        r = ventas.resumen(g.ctx["id_empresa"], g.ctx["usuario"].get("id_tienda"), seccion=seccion)
        return jsonify(r)
