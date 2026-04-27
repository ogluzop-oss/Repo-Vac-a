# src/gui/importar_stock.py
import os
import sqlite3
import pandas as pd
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QProgressDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal


# ============================================================
# BLOQUE INICIALIZACIÓN Y ESQUEMA DE BASE DE DATOS
# ============================================================

class ImportarStock:
    def __init__(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._crear_tabla_si_no_existe()

    def _crear_tabla_si_no_existe(self):
        """Crea la tabla articulos si no existe."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS articulos (
                codigo TEXT PRIMARY KEY,
                nombre TEXT,
                Stock_total INTEGER DEFAULT 0,
                Stock_tienda INTEGER DEFAULT 0,
                stock_esperado INTEGER DEFAULT 0,
                ultima_recepcion TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def _agregar_columnas_si_faltan(self, columnas):
        """Agregar automáticamente columnas que existen en el archivo pero no en DB."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(articulos)")
        columnas_existentes = [c[1] for c in cur.fetchall()]
        for col in columnas:
            if col not in columnas_existentes:
                cur.execute(f"ALTER TABLE articulos ADD COLUMN '{col}' TEXT")
        conn.commit()
        conn.close()


# ============================================================
# BLOQUE IMPORTACIÓN DESDE FICHERO
# ============================================================

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

        self.hilo = ImportarHilo(fichero, self.db_path)
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

    def __init__(self, ruta_fichero, db_path):
        super().__init__()
        self.ruta_fichero = ruta_fichero
        self.db_path = db_path

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

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(articulos)")
            columnas_existentes = [c[1] for c in cur.fetchall()]
            for col in df.columns:
                if col not in columnas_existentes:
                    cur.execute(f"ALTER TABLE articulos ADD COLUMN '{col}' TEXT")

            for _, row in df.iterrows():
                cols = list(row.index)
                values = [row[c] for c in cols]
                col_names = ",".join(f"'{c}'" for c in cols)
                placeholders = ",".join("?" for _ in cols)
                query = f"REPLACE INTO articulos ({col_names}) VALUES ({placeholders})"
                cur.execute(query, values)

            conn.commit()
            conn.close()
            self.finalizado.emit(
                f"Stock importado correctamente desde:\n{self.ruta_fichero}"
            )

        except Exception as e:
            self.finalizado.emit(f"No se pudo importar el fichero:\n{str(e)}")
