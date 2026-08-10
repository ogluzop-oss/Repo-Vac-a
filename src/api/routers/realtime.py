"""
Router /realtime — TRANSPORTE DE TIEMPO REAL EN RED (Server-Sent Events, server→cliente).

SSE (no WebSocket): suficiente para el push server→cliente y SIN dependencias nuevas (respuesta HTTP
`text/event-stream` en Flask). Autenticación JWT reutilizada (`requiere_auth`); el **tenant sale SIEMPRE del
token** (`g.ctx["id_empresa"]`), nunca del cliente → aislamiento multi-tenant estricto. Consume el hub
`services.eventbus.realtime`, que a su vez consume el Event Bus EXISTENTE. No abre un segundo bus ni una
segunda autenticación.
"""

import json

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/realtime/stream")
    @requiere_auth()
    def realtime_stream():
        from flask import Response, g, request, stream_with_context
        from src.services.eventbus import realtime

        emp = g.ctx["id_empresa"]
        canales_q = (request.args.get("canales") or "").strip()
        canales = [c.strip() for c in canales_q.split(",") if c.strip()] or None
        cliente = realtime.registrar(emp, canales=canales)

        @stream_with_context
        def _gen():
            try:
                # Handshake inmediato: el cliente confirma la conexión sin esperar a un evento.
                yield ("event: connected\n"
                       f"data: {json.dumps({'empresa': emp, 'canales': canales})}\n\n")
                while True:
                    try:
                        ev = cliente.cola.get(timeout=15)
                    except Exception:
                        yield ": ping\n\n"          # heartbeat cada 15s (mantiene viva la conexión)
                        continue
                    yield (f"event: {ev.get('tipo', 'evento')}\n"
                           f"id: {ev.get('uuid', '')}\n"
                           f"data: {json.dumps(ev, default=str)}\n\n")
            finally:
                realtime.desregistrar(cliente)      # cierre limpio: libera el slot del hub

        resp = Response(_gen(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"    # evita buffering en proxies (nginx)
        resp.headers["Connection"] = "keep-alive"
        return resp

    @bp.get("/realtime/metrics")
    @requiere_auth()
    def realtime_metrics():
        from flask import g, jsonify
        from src.services.eventbus import realtime
        m = realtime.metricas()
        m["conexiones_tenant"] = realtime.conexiones_de(g.ctx["id_empresa"])
        return jsonify(m)
