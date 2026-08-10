"""
Adaptador REST genérico — para API propia o proveedores aún sin adaptador específico.
Formato neutro: POST {endpoint}/labels/{label_id} con {store_id, data}. Bearer opcional.
"""

from src.services.esl.proveedores.base import AdaptadorESL, resultado


class AdaptadorRestGenerico(AdaptadorESL):
    codigo = "rest_generico"

    def push(self, label_id, datos, ctx, transport):
        url = f"{self._base(ctx)}/labels/{label_id}"
        status, _txt = transport("POST", url, self._headers(ctx),
                                 {"store_id": ctx.get("store_id"), "data": datos})
        return resultado(status)

    def localizar(self, label_id, ctx, transport):
        url = f"{self._base(ctx)}/labels/{label_id}/blink"
        status, _txt = transport("POST", url, self._headers(ctx), {"store_id": ctx.get("store_id")})
        return {"ok": 200 <= (status or 0) < 300, "detalle": f"HTTP {status}"}
