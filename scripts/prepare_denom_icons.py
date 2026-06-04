"""
Convierte imágenes de denominaciones euro en PNGs con fondo transparente.

USO:
  1. Guarda tus imágenes (JPG o PNG, con fondo blanco o transparente) en la
     carpeta  assets/denominaciones/raw/  con estos nombres exactos:
       1ct, 2ct, 5ct, 10ct, 20ct, 50ct
       1e, 2e, 5e, 10e, 20e, 50e, 100e, 200e, 500e
     (extensión .jpg, .jpeg o .png)

  2. Ejecuta:   python scripts/prepare_denom_icons.py

  3. Los PNGs con fondo transparente se guardan en assets/denominaciones/
"""

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "assets" / "denominaciones" / "raw"
OUT_DIR = ROOT / "assets" / "denominaciones"

NAMES = [
    "1ct", "2ct", "5ct", "10ct", "20ct", "50ct",
    "1e", "2e", "5e", "10e", "20e", "50e", "100e", "200e", "500e",
]


def remove_white_bg(img: Image.Image, threshold: int = 230) -> Image.Image:
    """Hace transparentes los píxeles cercanos al blanco."""
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.uint8)
    r, g, b, a = data[..., 0], data[..., 1], data[..., 2], data[..., 3]
    white_mask = (r >= threshold) & (g >= threshold) & (b >= threshold)
    data[white_mask, 3] = 0
    return Image.fromarray(data, "RGBA")


def process():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    found = 0
    for name in NAMES:
        src = None
        for ext in (".png", ".jpg", ".jpeg"):
            candidate = RAW_DIR / f"{name}{ext}"
            if candidate.is_file():
                src = candidate
                break
        if src is None:
            print(f"  [FALTA]  {name}  — no encontrado en {RAW_DIR}")
            continue

        img = Image.open(src)
        if img.mode == "RGBA":
            result = img
        else:
            result = remove_white_bg(img)

        out_path = OUT_DIR / f"{name}.png"
        result.save(out_path, "PNG")
        print(f"  [OK]     {out_path.name}  ({result.size[0]}x{result.size[1]})")
        found += 1

    print(f"\nProcesadas {found}/{len(NAMES)} denominaciones.")
    if found < len(NAMES):
        print("Coloca las imágenes que faltan en:", RAW_DIR)


if __name__ == "__main__":
    process()
