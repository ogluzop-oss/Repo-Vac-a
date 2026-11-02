"""
Lee `logs/faulthandler.log` y muestra, de forma limpia, el ÚLTIMO crash nativo registrado (el
volcado que `faulthandler` escribe automáticamente cuando el proceso muere por un fallo nativo
tipo 0xc0000005 — accesos inválidos en una DLL de Qt/C++ — que un `try/except` de Python NUNCA
puede capturar). Uso:

    python tools/ultimo_crash.py            # solo el último crash de la última sesión
    python tools/ultimo_crash.py --todos     # todos los crashes de la última sesión
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RUTA_LOG = Path(__file__).resolve().parent.parent / "logs" / "faulthandler.log"


def main():
    if not RUTA_LOG.exists():
        print(f"No existe {RUTA_LOG} todavía — arranca la app al menos una vez (ya está "
              f"instrumentada, ver src/main.py).")
        return

    texto = RUTA_LOG.read_text(encoding="utf-8", errors="replace")

    # Cada arranque de la app deja una marca "===== ARRANQUE <fecha> =====" (ver src/main.py).
    # Nos quedamos solo con lo de la ÚLTIMA sesión — lo anterior son pruebas viejas.
    sesiones = re.split(r"\n===== ARRANQUE ([^=]+) =====\n", texto)
    if len(sesiones) >= 3:
        fecha_sesion = sesiones[-2]
        contenido = sesiones[-1]
    else:
        fecha_sesion = "(desconocida — log de antes de la marca de arranque)"
        contenido = texto

    # Cada crash termina en "Windows fatal exception: ...". Nos quedamos con el bloque
    # "Current thread ... (most recent call first): ... Windows fatal exception: ..." de cada uno
    # (el hilo que realmente petó, no los demás hilos en espera que también se listan).
    patron = re.compile(
        r"Current thread [^\n]*\n(.*?)\nWindows fatal exception: ([^\n]*)",
        re.DOTALL,
    )
    crashes = patron.findall(contenido)

    if not crashes:
        print(f"Sesión {fecha_sesion}: no hay ningún crash nativo registrado todavía. Bien.")
        return

    mostrar_todos = "--todos" in sys.argv
    a_mostrar = crashes if mostrar_todos else crashes[-1:]

    print(f"Sesión: {fecha_sesion}")
    print(f"Crashes nativos encontrados en esta sesión: {len(crashes)}"
          + ("" if mostrar_todos else " (mostrando solo el último — usa --todos para verlos todos)"))
    print("=" * 78)

    for i, (stack, tipo) in enumerate(a_mostrar, 1):
        n = len(crashes) - len(a_mostrar) + i
        print(f"\n--- Crash #{n}: {tipo.strip()} ---")
        lineas = [l for l in stack.strip().splitlines() if l.strip()]
        for l in lineas:
            print(" ", l.strip())
        # La línea más útil suele ser la PRIMERA (el frame donde estaba el intérprete justo al
        # morir) — se resalta aparte para no tener que buscarla entre el resto de la pila.
        if lineas:
            print(f"  >>> Punto exacto del crash: {lineas[0].strip()}")

    print("\n" + "=" * 78)
    print("Para ver los crashes EN VIVO mientras pruebas (sin esperar a que termine la sesión), "
          "en otra terminal PowerShell:\n"
          "  Get-Content logs\\faulthandler.log -Wait -Tail 0")


if __name__ == "__main__":
    main()
