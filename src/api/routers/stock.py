"""
Router /stock — consulta de artículos + niveles de stock (solo lectura). Consume `src.services.stock`.

Nota de alcance: solo lectura (búsqueda/consulta). El flujo de ESCRITURA de stock (registrar un
escaneo de recepción desde el móvil) sigue pendiente de diseño en el backend — el Outbox offline-first
del cliente móvil ya está preparado para sincronizar contra `POST /stock` en cuanto exista.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/stock")
    @requiere_auth("inventario.ver")
    def stock_buscar():
        from flask import g, jsonify, request
        from src.services import stock
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 100))
        res = stock.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))
