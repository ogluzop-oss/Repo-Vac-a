"""
Alta ÚNICA de la cuenta del panel del fundador (Fase 4). Se ejecuta UNA vez, a mano, en el servidor
central — resuelve el problema del huevo y la gallina de un panel cuyo login exige una cuenta que
todavía no existe. No hay alta desde la propia web a propósito (`panel_fundador.crear_cuenta` ya se
niega a crear una segunda cuenta).

Uso (con las mismas variables DB_* que `backend_central.app`, apuntando a la BD central):

    python -m src.backend_central.crear_fundador <usuario> <password>
"""

import getpass
import sys


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m src.backend_central.crear_fundador <usuario> [password]")
        sys.exit(1)
    usuario = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Contraseña: ")

    from src.services.licencia_central import panel_fundador
    r = panel_fundador.crear_cuenta(usuario, password)
    if not r.get("ok"):
        print(f"Error: {r.get('error')}")
        sys.exit(1)
    print(f"Cuenta del panel del fundador creada: {usuario}")


if __name__ == "__main__":
    main()
