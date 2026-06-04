# ---------------------------
# Generar_Codigo.py
# ---------------------------
import os

from barcode import EAN13
from barcode.writer import ImageWriter

from src.db.conexion import obtener_conexion
from src.utils import pil_compat  # noqa: F401 — restaura ImageFont.getsize (Pillow>=10)

# ============================================================
# BLOQUE CONFIGURACIÓN
# ============================================================

codigos_articulos = [
    1, 2, 3,
    100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
    1001, 1002, 1003, 1004,
]


# ============================================================
# BLOQUE GENERACIÓN DE CÓDIGOS DE BARRAS
# ============================================================

def generar_codigos(codigos=None, output_dir=None):
    """Genera PNGs de códigos de barras EAN13 y registra los artículos en BD."""
    codigos = codigos or codigos_articulos
    output_dir = output_dir or os.path.join(os.getcwd(), "codigos_generados")
    os.makedirs(output_dir, exist_ok=True)

    with obtener_conexion() as conn:
        cur = conn.cursor()
        for codigo in codigos:
            codigo_12 = str(codigo).zfill(12)
            ean = EAN13(codigo_12, writer=ImageWriter())
            codigo_full = ean.get_fullcode()

            filename = os.path.join(output_dir, f"{codigo_full}.png")
            ean.save(filename)

            cur.execute(
                "INSERT INTO articulos (codigo, nombre, categoria, precio) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), categoria=VALUES(categoria), precio=VALUES(precio)",
                (codigo_full, f"Artículo {codigo}", "General", 0.0),
            )
        conn.commit()

    print(f"Generación de códigos completada. Imágenes guardadas en: {output_dir}")
    return output_dir


if __name__ == "__main__":
    generar_codigos()
