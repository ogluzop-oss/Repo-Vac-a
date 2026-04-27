# ---------------------------
# Generar_Codigo.py
# ---------------------------
from barcode import EAN13
from barcode.writer import ImageWriter
import os
import sqlite3

# ---------------------------
# Configuración de códigos
# ---------------------------
codigos_articulos = [
    1,
    2,
    3,
    100,
    101,
    102,
    103,
    104,
    105,
    106,
    107,
    108,
    109,
    1001,
    1002,
    1003,
    1004,
]

# Directorio donde se guardarán las imágenes
output_dir = os.path.join(os.getcwd(), "codigos_generados")
os.makedirs(output_dir, exist_ok=True)

# Ruta a la base de datos SQLite
db_path = r"src/database/stock.db"  # <-- CAMBIA esta ruta según tu proyecto

# Conexión a la base de datos
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# ---------------------------
# Generación de códigos
# ---------------------------
for codigo in codigos_articulos:
    # Rellenar con ceros a la izquierda hasta 12 dígitos
    codigo_12 = str(codigo).zfill(12)

    # Generar EAN-13 con ImageWriter
    ean = EAN13(codigo_12, writer=ImageWriter())

    # Obtener código completo con dígito de control (13 dígitos)
    codigo_full = ean.get_fullcode()

    # Guardar imagen
    filename = os.path.join(output_dir, f"{codigo_full}.png")
    ean.save(filename)

    # Guardar en base de datos con código exacto
    cur.execute(
        """
        INSERT OR REPLACE INTO articulos (codigo, nombre, categoria, precio)
        VALUES (?, ?, ?, ?)
    """,
        (codigo_full, f"Artículo {codigo}", "General", 0.0),
    )

# Guardar cambios y cerrar conexión
conn.commit()
conn.close()

print(f"Generación de códigos completada. Imágenes guardadas en: {output_dir}")
