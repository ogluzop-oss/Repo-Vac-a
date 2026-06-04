# src/gui/importar_stock.py
import os

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog

from src.db.conexion import obtener_conexion

# ============================================================
# BLOQUE IMPORTACIÓN DESDE FICHERO
# ============================================================

class ImportarStock:
    def cargar_desde_fichero(self, formatos_permitidos=["*.xlsx", "*.txt"]):
        """Permite al usuario seleccionar un archivo Excel o TXT e importar datos."""
        fichero, _ = QFileDialog.getOpenFileName(
            None,
            "Selecciona un fichero",
            "",
            "Excel (*.xlsx);;Texto (*.txt);;Todos los archivos (*)",
        )
        if not fichero:
            return

        progreso = QProgressDialog("Importación en curso...", None, 0, 0)
        progreso.setWindowModality(Qt.WindowModality.ApplicationModal)
        progreso.setWindowTitle("Importando stock")
        progreso.setCancelButton(None)
        progreso.show()

        self.hilo = ImportarHilo(fichero)
        self.hilo.finalizado.connect(
            lambda mensaje: self._finalizar_importacion(progreso, mensaje)
        )
        self.hilo.start()

    def _finalizar_importacion(self, progreso, mensaje):
        progreso.close()
        QMessageBox.information(None, "Resultado de la importación", mensaje)


# ============================================================
# BLOQUE HILO DE IMPORTACIÓN EN SEGUNDO PLANO
# ============================================================

class ImportarHilo(QThread):
    finalizado = pyqtSignal(str)

    def __init__(self, ruta_fichero):
        super().__init__()
        self.ruta_fichero = ruta_fichero

    def run(self):
        try:
            extension = os.path.splitext(self.ruta_fichero)[1].lower()
            if extension == ".xlsx":
                df = pd.read_excel(self.ruta_fichero)
            elif extension == ".txt":
                try:
                    df = pd.read_csv(self.ruta_fichero, sep="\t")
                except Exception:
                    df = pd.read_csv(self.ruta_fichero, sep=",")
            else:
                self.finalizado.emit(
                    "Formato no permitido. Solo Excel (.xlsx) o TXT (.txt)."
                )
                return

            if df.empty:
                self.finalizado.emit("El fichero seleccionado está vacío.")
                return

            df.columns = [c.strip().lower() for c in df.columns]

            with obtener_conexion() as conn:
                cur = conn.cursor()

                # Retrieve existing columns from MariaDB INFORMATION_SCHEMA
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'articulos'"
                )
                columnas_existentes = {row[0].lower() for row in cur.fetchall()}

                for col in df.columns:
                    if col not in columnas_existentes:
                        cur.execute(
                            f"ALTER TABLE articulos ADD COLUMN `{col}` TEXT"
                        )
                        columnas_existentes.add(col)

                for _, row in df.iterrows():
                    cols = list(row.index)
                    values = [row[c] for c in cols]
                    col_names = ", ".join(f"`{c}`" for c in cols)
                    placeholders = ", ".join("%s" for _ in cols)
                    updates = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in cols if c != "codigo")
                    query = (
                        f"INSERT INTO articulos ({col_names}) VALUES ({placeholders}) "
                        f"ON DUPLICATE KEY UPDATE {updates}"
                    )
                    cur.execute(query, values)

                conn.commit()

            self.finalizado.emit(
                f"Stock importado correctamente desde:\n{self.ruta_fichero}"
            )

        except Exception as e:
            self.finalizado.emit(f"No se pudo importar el fichero:\n{str(e)}")
