"""Plugin de ejemplo (Fase III · B4). Demuestra el SDK: registra un menú, un hook y un evento."""


def register(sdk):
    # Contribución de menú (punto de extensión).
    sdk.registrar_extension("menus", {"clave": "ejemplo", "titulo": "Ejemplo", "icono": "🧩"},
                            plugin="ejemplo")
    # Hook al iniciar.
    sdk.registrar_hook("al_iniciar", lambda **kw: "ejemplo:iniciado", plugin="ejemplo")
