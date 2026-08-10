"""
Ejemplo de arranque del SDK de Python de Smart Manager AI.

Ejecuta:  python quickstart.py
Requiere las variables de entorno SM_BASE_URL y SM_TOKEN (o SM_API_KEY + SM_EMPRESA).
"""

import os

from smartmanager import Client, SmartManagerError


def main():
    base = os.getenv("SM_BASE_URL", "https://api.tu-dominio/api/v1")
    if os.getenv("SM_TOKEN"):
        c = Client(base, token=os.environ["SM_TOKEN"])
    else:
        c = Client(base, api_key=os.getenv("SM_API_KEY"), empresa=os.getenv("SM_EMPRESA"))

    try:
        print("Salud:", c.health())
        # Listado paginado (sobre estándar)
        pagina = c.communications.list(limit=10, sort="fecha", order="desc")
        print("Comunicaciones (página):", pagina)
        # Iteración transparente por cursor
        for contacto in c.contacts.paginate(q="ana"):
            print("Contacto:", contacto)
    except SmartManagerError as e:
        print("Error de API:", e, "status:", e.status)


if __name__ == "__main__":
    main()
