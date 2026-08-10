"""Interfaz común de los adaptadores de banca (open banking). Normaliza a [{fecha,importe,concepto,referencia}]."""


class AdaptadorBanca:
    codigo = "base"

    def _headers(self, ctx):
        h = {"Accept": "application/json"}
        if ctx.get("credencial"):
            h["Authorization"] = f"Bearer {ctx['credencial']}"
        return h

    def _base(self, ctx):
        return (ctx.get("endpoint") or "").rstrip("/")

    def obtener_movimientos(self, ctx, desde, hasta, transport):
        raise NotImplementedError
