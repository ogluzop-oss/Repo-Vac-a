# Cursores personalizados de la app

Coloca aquí **3 imágenes PNG** (fondo transparente, ~24–32 px) para que la app use TUS cursores en 3 estados.
El resto de estados (espera, cruz, redimensionar, prohibido…) no se tocan.

| Fichero (se aceptan alias)        | Estado                     | Punto activo (hotspot) |
|-----------------------------------|----------------------------|------------------------|
| `arrow.png`                       | Flecha (normal)            | esquina arriba-izquierda (0,0) |
| `hand.png` / `pointer.png`        | Mano señalando (clicable)  | la punta del dedo (arriba) |
| `ibeam.png`                       | Texto (I-beam)             | el centro |
| `openhand.png` / `open hand.png`  | Mano abierta (arrastrar)   | el centro |

- Si falta algún fichero, ese estado usa el cursor del sistema (nada se rompe).
- Tras añadir/cambiar los ficheros, **reinicia la app** para que se carguen.
- Se cargan al arrancar desde `src/utils/cursores.py` (`instalar(app)` en `src/main.py`).

> Nota: los PNG no llevan hotspot incorporado; se usa uno razonable por forma. Si necesitas precisión de
> hotspot, puedes ajustarlo en `src/utils/cursores.py::_hotspot`.
