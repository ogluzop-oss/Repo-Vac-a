# src/autocobro_app.py
"""
Punto de entrada del TERMINAL DE AUTOCOBRO independiente.

Ejecútalo como proceso separado (idealmente en otra pantalla táctil / monitor):

    python -m src.autocobro_app

Comparte la MISMA base de datos MariaDB, stock, ventas y servicios que el TPV
del cajero (mismo .env / misma conexión), pero con su propia interfaz de cliente.
"""
import logging
import sys

from PyQt6.QtWidgets import QApplication

from assets.estilo_global import aplicar_estilo_app
from src.db.conexion import init_db
from src.gui.autocobro import AutocobroWindow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("autocobro_app")


def main():
    init_db()  # asegura el esquema compartido (idempotente)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        aplicar_estilo_app(app)
    except Exception as e:
        logger.warning(f"No se pudo aplicar el estilo global: {e}")

    # ID de caja de autocobro: permite varios terminales (AUTO-01, AUTO-02…)
    id_caja = sys.argv[1] if len(sys.argv) > 1 else "AUTO-01"

    win = AutocobroWindow(id_caja=id_caja)
    win.showFullScreen()
    logger.info(f"Terminal de autocobro '{id_caja}' iniciado.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
