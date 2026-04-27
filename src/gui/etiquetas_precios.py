from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QInputDialog,
    QFileDialog,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
import sqlite3
import os
import pandas as pd
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm


class EtiquetasPreciosWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        self.pendientes = []

        self.setup_ui()
        self.setWindowTitle("Etiquetas de Precio")
        self.resize(800, 550)

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)

        title = QLabel("Gestión de etiquetas de precios")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            ["Código", "Nombre", "Precio (€)", "Ubicación", "Pendiente"]
        )
        self.tabla.setStyleSheet(
            "QTableWidget { background-color: #1A1D23; color: white; }"
        )
        layout.addWidget(self.tabla)

        btn_cambiar = QPushButton("Cambiar precio")
        btn_cambiar.clicked.connect(self.cambiar_precio)
        self.estilo_boton(btn_cambiar)
        layout.addWidget(btn_cambiar)

        btn_actualizar = QPushButton("Actualizar lista desde Central")
        btn_actualizar.clicked.connect(self.actualizar_lista_precios)
        self.estilo_boton(btn_actualizar)
        layout.addWidget(btn_actualizar)

        btn_exportar = QPushButton("Exportar etiquetas pendientes (PDF)")
        btn_exportar.clicked.connect(self.exportar_etiquetas_pendientes_pdf)
        self.estilo_boton(btn_exportar)
        layout.addWidget(btn_exportar)

        btn_volver = QPushButton("Volver al menú principal")
        btn_volver.clicked.connect(self.volver_menu_principal)
        self.estilo_boton(btn_volver, rojo=True)
        layout.addWidget(btn_volver, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet("background-color: #0E1117;")

    # ============================================================
    # BLOQUE ESTILO DE BOTONES
    # ============================================================

    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "12px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "20px"

        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {base};
                color: {text_color};
                font-weight: bold;
                border-radius: 15px;
                padding: {padding};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        )
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    # ============================================================
    # BLOQUE GESTIÓN DE PRECIOS
    # ============================================================

    def cambiar_precio(self):
        """Permite cambiar el precio y marca el artículo como pendiente de imprimir."""
        try:
            codigo, ok = QInputDialog.getText(
                self, "Cambiar precio", "Código del artículo:"
            )
            if not ok or not codigo:
                return

            nuevo_precio, ok = QInputDialog.getDouble(
                self,
                "Nuevo precio",
                "Introduce el nuevo precio (€):",
                0.0,
                0.0,
                999999.0,
                2,
            )
            if not ok:
                return

            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "database", "stock.db")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            cur.execute("SELECT nombre FROM articulos WHERE codigo = ?", (codigo,))
            articulo = cur.fetchone()
            if not articulo:
                QMessageBox.warning(
                    self,
                    "No encontrado",
                    f"No se encontró el artículo con código {codigo}.",
                )
                conn.close()
                return

            nombre = articulo[0]
            cur.execute(
                "UPDATE articulos SET precio = ? WHERE codigo = ?",
                (nuevo_precio, codigo),
            )
            conn.commit()
            conn.close()

            self.pendientes.append((codigo, nombre, nuevo_precio))
            self.actualizar_tabla_pendientes()

            QMessageBox.information(
                self,
                "Precio actualizado",
                f"Precio de {nombre} ({codigo}) actualizado a {nuevo_precio} €.\nEtiqueta pendiente de imprimir añadida.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cambiar el precio: {e}")

    def actualizar_lista_precios(self):
        """Importa XLSX/TXT con columnas (codigo, nuevo_precio) y actualiza la BD."""
        try:
            ruta_archivo, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar lista de precios",
                "",
                "Archivos Excel (*.xlsx);;Archivos TXT (*.txt)",
            )
            if not ruta_archivo:
                return

            if ruta_archivo.lower().endswith(".txt"):
                df = pd.read_csv(ruta_archivo, sep="\t")
            else:
                df = pd.read_excel(ruta_archivo)

            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "database", "stock.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            for _, row in df.iterrows():
                codigo = row["codigo"]
                nuevo_precio = row["nuevo_precio"]
                cur.execute(
                    "UPDATE articulos SET precio = ? WHERE codigo = ?",
                    (nuevo_precio, codigo),
                )
                cur.execute("SELECT nombre FROM articulos WHERE codigo = ?", (codigo,))
                nombre = cur.fetchone()
                if nombre:
                    self.pendientes.append((codigo, nombre[0], nuevo_precio))

            conn.commit()
            conn.close()

            self.actualizar_tabla_pendientes()
            QMessageBox.information(
                self,
                "Actualización completa",
                "Los precios se han actualizado y añadido a etiquetas pendientes.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al actualizar precios: {e}")

    # ============================================================
    # BLOQUE VISUALIZACIÓN DE PENDIENTES
    # ============================================================

    def actualizar_tabla_pendientes(self):
        """Actualiza la tabla con los artículos pendientes."""
        self.tabla.setRowCount(len(self.pendientes))
        for fila, (codigo, nombre, precio) in enumerate(self.pendientes):
            self.tabla.setItem(fila, 0, QTableWidgetItem(codigo))
            self.tabla.setItem(fila, 1, QTableWidgetItem(nombre))
            self.tabla.setItem(fila, 2, QTableWidgetItem(f"{precio:.2f}"))
            self.tabla.setItem(fila, 4, QTableWidgetItem("✅ Pendiente"))

    # ============================================================
    # BLOQUE GENERACIÓN DE ETIQUETAS PDF
    # ============================================================

    def exportar_etiquetas_pendientes_pdf(self):
        """Exporta las etiquetas pendientes a un PDF con diseño mejorado."""
        if not self.pendientes:
            QMessageBox.information(
                self, "Nada que exportar", "No hay etiquetas pendientes para imprimir."
            )
            return

        try:
            from reportlab.lib import colors

            base_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../")
            )
            export_dir = os.path.join(base_dir, "documentos")
            os.makedirs(export_dir, exist_ok=True)

            nombre_archivo = (
                f"etiquetas_pendientes_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"
            )
            ruta_pdf = os.path.join(export_dir, nombre_archivo)

            c = canvas.Canvas(ruta_pdf, pagesize=A4)
            page_width, page_height = A4

            etiqueta_width = 70 * mm
            etiqueta_height = 40 * mm
            margen_x = 10 * mm
            margen_y = 10 * mm
            espacio_x = 5 * mm
            espacio_y = 5 * mm

            etiquetas_por_fila = int(
                (page_width - 2 * margen_x + espacio_x) // (etiqueta_width + espacio_x)
            )
            etiquetas_por_col = int(
                (page_height - 2 * margen_y + espacio_y)
                // (etiqueta_height + espacio_y)
            )

            x_start = margen_x
            y_start = page_height - margen_y - etiqueta_height

            fila = 0
            col = 0

            for codigo, nombre, precio in self.pendientes:
                x = x_start + col * (etiqueta_width + espacio_x)
                y = y_start - fila * (etiqueta_height + espacio_y)

                c.setFillColor(colors.white)
                c.rect(x, y, etiqueta_width, etiqueta_height, stroke=0, fill=1)
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.rect(x, y, etiqueta_width, etiqueta_height, stroke=1, fill=0)

                c.setFont("Helvetica-Bold", 12)
                c.setFillColor(colors.black)
                c.drawString(x + 5 * mm, y + etiqueta_height - 10 * mm, f"{nombre}")

                descripcion = "Marca genérica"
                c.setFont("Helvetica", 9)
                c.drawString(x + 5 * mm, y + etiqueta_height - 16 * mm, descripcion)

                c.setFont("Helvetica-Bold", 28)
                precio_texto = f"{precio:.2f} €"
                text_width = c.stringWidth(precio_texto, "Helvetica-Bold", 28)
                c.drawString(
                    x + etiqueta_width - text_width - 8 * mm, y + 4 * mm, precio_texto
                )

                c.setFont("Helvetica", 9)
                c.drawString(x + 5 * mm, y + 9 * mm, f"Código: {codigo}")

                barcode_obj = code128.Code128(
                    str(codigo), barHeight=4 * mm, barWidth=0.45
                )
                barcode_obj.drawOn(c, x + 5 * mm, y + 2 * mm)

                col += 1
                if col >= etiquetas_por_fila:
                    col = 0
                    fila += 1
                    if fila >= etiquetas_por_col:
                        c.showPage()
                        fila = 0

            c.save()

            QMessageBox.information(
                self,
                "Exportado",
                f"PDF de etiquetas generado correctamente:\n{ruta_pdf}",
            )
            self.pendientes.clear()
            self.actualizar_tabla_pendientes()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar el PDF: {e}")

    # ============================================================
    # BLOQUE NAVEGACIÓN
    # ============================================================

    def volver_menu_principal(self):
        """Cierra la ventana y ejecuta el retorno al menú principal."""
        if self.callback_vuelta:
            self.callback_vuelta()
            self.close()
        else:
            self.close()
