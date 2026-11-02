"""
`src/mcp_server` — conector MCP (Model Context Protocol) de SOMA ("SOMA — Smart Manager Copilot").

Paquete NUEVO, foundational (transporte + autenticación únicamente). Submódulos:

- `registry.py`  — registro de tools MCP (`registrar_tool`) + resolución del contexto autenticado
                   de la llamada en curso. Punto de extensión para agentes FUTUROS: la lógica de
                   negocio real (stock/ventas/catálogo/pedidos/...) se añade aquí, nunca en
                   `transport.py`.
- `transport.py` — servidor `mcp.server.lowlevel.Server` + blueprint Flask que expone `/mcp`
                   (Streamable HTTP) sobre el mismo proceso/puerto que el resto del backend.
- `oauth.py`     — envoltura OAuth 2.1 (DCR + Authorization Code + PKCE) que emite los MISMOS JWT
                   que ya usa el resto de la app (`seguridad.tokens`), nunca un motor de auth
                   paralelo.

No contiene lógica de dominio: ninguna tool real se implementa en este paquete todavía.
"""
