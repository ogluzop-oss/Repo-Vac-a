"""
Adaptador SES-imagotag / VusionGroup (VusionCloud).

Modelo de VusionCloud: no se escribe "en la etiqueta" directamente, se ACTUALIZA EL ITEM (producto) en la
tienda y las etiquetas vinculadas a ese item se refrescan solas. El endpoint base y el store_id son
configurables (cada cliente tiene su cloud/tenant). Autenticación por Bearer token (API key/OAuth del
tenant). La localización usa el "flash" del LED de la etiqueta.

Endpoints modelados sobre la API de items de VusionCloud (configurable vía `endpoint`):
  · Precio:     POST  {endpoint}/stores/{store}/items      body {"items":[{itemId,price,labelId,...}]}
  · Localizar:  POST  {endpoint}/stores/{store}/labels/{labelId}/flash
Degradable: sin endpoint/credencial el gateway ni siquiera llega aquí (queda en simulado).
"""

from src.services.esl.proveedores.base import AdaptadorESL, resultado


class AdaptadorImagotag(AdaptadorESL):
    codigo = "imagotag"

    def push(self, label_id, datos, ctx, transport):
        url = f"{self._base(ctx)}/stores/{ctx.get('store_id') or ''}/items"
        item = {"itemId": datos.get("codigo"), "price": datos.get("precio"), "labelId": str(label_id)}
        if datos.get("plantilla"):
            item["page"] = datos["plantilla"]      # plantilla/página de la etiqueta
        status, _txt = transport("POST", url, self._headers(ctx), {"items": [item]})
        return resultado(status)

    def localizar(self, label_id, ctx, transport):
        url = f"{self._base(ctx)}/stores/{ctx.get('store_id') or ''}/labels/{label_id}/flash"
        status, _txt = transport("POST", url, self._headers(ctx), {})
        return {"ok": 200 <= (status or 0) < 300, "detalle": f"HTTP {status}"}
