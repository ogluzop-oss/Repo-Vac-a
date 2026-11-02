"""
Genera `assets/carga.webp` (animación de carga del login, con el fondo croma VERDE ya retirado)
a partir de un vídeo fuente (por defecto `assets/carga.mp4`).

Por qué existe esto (bug real, 3ª vuelta de la misma animación): el croma key en TIEMPO REAL
sobre el vídeo (`src.main.SmartManagerApp._on_frame_video_carga`, vía `QVideoSink`) obligaba a
elegir entre fluidez y calidad en cada fotograma, 24 veces por segundo:
  - A resolución nativa + reescalado suave: ~95-110ms/fotograma → se notaba "a trompicones"
    (fotogramas descartados por llegar tarde al presupuesto de 24fps).
  - Reducido a mitad de tamaño + reescalado barato (`FastTransformation`): ~25ms/fotograma, pero
    el reescalado por vecino-más-próximo amplificaba en bloques visibles cualquier resto de verde
    del borde → "contorno verde croma" + "pixelado".
  - Reducido a mitad + reescalado suave en los dos pasos: arregló la calidad, pero volvió a costar
    ~25-28ms/fotograma — de nuevo demasiado en máquinas más lentas o con el resto del arranque de
    la app compitiendo por CPU → "a trompicones" otra vez.

Los tres intentos pagaban el mismo coste en CADA arranque de la app, 24 veces por segundo, para
un resultado que es SIEMPRE el mismo (el vídeo no cambia de una sesión a otra). La solución real
es no competir con el reloj en absoluto: se hace el croma key UNA SOLA VEZ aquí (sin presupuesto
de tiempo, a resolución NATIVA, con el mismo algoritmo ya verificado), se hornea en un WebP
animado con canal alfa real, y en tiempo de ejecución la app vuelve al camino `QMovie` (gif/webp/
apng) que YA USABA ANTES para `carga.webp` — decodificar un fotograma de un WebP ya cocinado es
muchísimo más barato que recalcular croma + reescalar con numpy 24 veces por segundo, así que la
fluidez deja de depender de la velocidad de la máquina en cada arranque.

El código de croma key en tiempo real sobre vídeo (`_on_frame_video_carga`) NO se borra (Strangler
Pattern, ver CLAUDE.md) — sigue siendo el camino real si algún día se usa un asset que solo exista
en vídeo sin un WebP equivalente; simplemente deja de ser el camino activo para ESTE asset en
cuanto existe `assets/carga.webp` (`_montar_clip_carga` prioriza anim sobre vídeo).

Uso:
    python tools/generar_animacion_carga.py                        # assets/carga.mp4 → assets/carga.webp
    python tools/generar_animacion_carga.py --origen otro.mp4 --destino assets/carga.webp
"""

import argparse
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent


def _croma_key(frame_rgba: np.ndarray) -> np.ndarray:
    """Mismo algoritmo ya verificado (visual + numéricamente) en
    `src.main.SmartManagerApp._on_frame_video_carga`: el canal G muy por encima de R y B se vuelve
    transparente con una rampa (exceso 40→80), y el verde residual del borde se elimina POR
    COMPLETO (no solo se atenúa) capando el canal verde al máximo de rojo/azul — evita cualquier
    tinte verdoso en los píxeles semitransparentes del contorno.

    Realce de opacidad del sujeto (petición explícita): la rampa lineal deja semitransparentes
    los píxeles del borde del sujeto (antialiasing contra el croma), lo que se percibía como poca
    opacidad del logotipo. Se aplica una curva gamma (`alpha ** 0.6`) SOLO sobre el alpha ya
    calculado: empuja cualquier píxel YA parcialmente opaco (sujeto/borde) hacia opacidad total
    más rápido, pero un píxel de fondo puro (`alpha == 0`, croma verde sin mezclar) se queda
    exactamente en 0 — nunca gana opacidad el fondo, solo el sujeto."""
    arr = frame_rgba.copy()
    r = arr[..., 0].astype(np.int16)
    g0 = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    maxrb = np.maximum(r, b)
    exceso = g0 - maxrb
    alpha = np.clip((80 - exceso) * (1.0 / 40.0), 0.0, 1.0).astype(np.float32)
    alpha = np.power(alpha, 0.6, dtype=np.float32)
    arr[..., 3] = (alpha * 255).astype(np.uint8)
    arr[..., 1] = np.minimum(g0, maxrb).astype(np.uint8)
    return arr


def generar(origen: Path, destino: Path, *, lossless: bool = True, calidad: int = 90) -> dict:
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(origen))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo origen: {origen}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0

    frames = []
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
            keyed = _croma_key(frame_rgba)
            frames.append(Image.fromarray(keyed))
    finally:
        cap.release()

    if not frames:
        raise RuntimeError(f"El vídeo origen no tiene fotogramas legibles: {origen}")

    duracion_ms = int(round(1000.0 / fps))
    destino.parent.mkdir(parents=True, exist_ok=True)
    guardar_kwargs = dict(format="WEBP", save_all=True, append_images=frames[1:],
                          duration=duracion_ms, loop=0, method=4)
    if lossless:
        guardar_kwargs["lossless"] = True
        guardar_kwargs["quality"] = 100
    else:
        guardar_kwargs["quality"] = calidad
    frames[0].save(destino, **guardar_kwargs)

    return {"fotogramas": len(frames), "fps": fps, "tamano_bytes": destino.stat().st_size}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", default=str(RAIZ / "assets" / "carga.mp4"),
                   help="Vídeo fuente con fondo croma verde (por defecto assets/carga.mp4)")
    ap.add_argument("--destino", default=str(RAIZ / "assets" / "carga.webp"),
                   help="WebP animado de salida (por defecto assets/carga.webp)")
    ap.add_argument("--lossy", action="store_true",
                   help="Usa WebP CON pérdida (más pequeño, calidad=90) en vez de lossless "
                        "(por defecto; ~2.7MB para un clip de 2s/48 fotogramas a 1280x720).")
    args = ap.parse_args()

    origen, destino = Path(args.origen), Path(args.destino)
    info = generar(origen, destino, lossless=not args.lossy)
    print(f"OK: {destino} ({info['fotogramas']} fotogramas @ {info['fps']:.1f}fps, "
          f"{info['tamano_bytes']/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
