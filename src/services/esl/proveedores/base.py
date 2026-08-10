"""
Interfaz común de los adaptadores de proveedor ESL. Cada adaptador traduce la operación genérica
(push de precio / localizar) al formato REST concreto del fabricante. El envío se delega en un
`transport(metodo, url, headers, cuerpo) -> (status|None, texto)` inyectable (probable sin red).
"""


class AdaptadorESL:
    codigo = "base"

    def _headers(self, ctx):
        h = {"Content-Type": "application/json"}
        cred = ctx.get("credencial")
        if cred:
            h["Authorization"] = f"Bearer {cred}"
        return h

    def _base(self, ctx):
        return (ctx.get("endpoint") or "").rstrip("/")

    def push(self, label_id, datos, ctx, transport):
        raise NotImplementedError

    def localizar(self, label_id, ctx, transport):
        raise NotImplementedError


def resultado(status, accion="actualizada"):
    """Normaliza la respuesta HTTP a {ok, estado, detalle}. 2xx = éxito."""
    ok = 200 <= (status or 0) < 300
    return {"ok": ok, "estado": accion if ok else "error", "detalle": f"HTTP {status}"}
