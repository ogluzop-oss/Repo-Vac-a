"""
Router /orders — pedidos de RECEPCIÓN de palets (solo lectura). Consume `src.services.pedidos`.

Nota de dominio: hoy "pedido" en Smart Manager es la recepción de un palet (escaneo RFID/código en
almacén), no un pedido de venta ni de compra — ver el docstring de `src.services.pedidos`.

Sin permiso RBAC dedicado todavía (no existe `pedidos.ver` en el catálogo de `seguridad/catalogo.py`):
exige solo autenticación, igual que `/contacts` y el historial de `/communications`.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def _bool_o_none(valor):
    if valor is None:
        return None
    return str(valor).strip().lower() in ("1", "true", "si", "sí")


def registrar(bp):
    @bp.get("/orders")
    @requiere_auth()
    def orders_listar():
        from flask import g, jsonify, request
        from src.services import pedidos
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 100))
        procesado = _bool_o_none(request.args.get("procesado"))
        res = pedidos.listar(g.ctx["id_empresa"], procesado=procesado, limite=limite)
        return jsonify(envolver(res, p))
