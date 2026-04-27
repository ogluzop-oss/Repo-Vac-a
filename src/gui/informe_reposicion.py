# src/gui/informe_reposicion.py
import os
from datetime import datetime
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QInputDialog,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from src.db.conexion import obtener_articulo, set_stock_esperado, obtener_conexion
from src.db.conexion import stock_signals as global_stock_signals


class InformeReposicionWindow(QWidget):
    def __init__(
        self, callback_vuelta=None, usuario=None, stock_signals=None, **kwargs
    ):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        self.signals = stock_signals or global_stock_signals
        self.signals.stock_actualizado.connect(self.actualizar_stock_articulo)

        self.setWindowTitle("Informe de Reposición")
        self.resize(950, 600)

        self.crear_campo_repuesto()
        self.setup_ui()
        self.actualizar_lista(show_message=False)

    # ============================================================
    # BLOQUE INICIALIZACIÓN DE BASE DE DATOS
    # ============================================================

    def crear_campo_repuesto(self):
        """Verifica y añade la columna repuesto usando sintaxis MariaDB."""
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("SHOW COLUMNS FROM articulos LIKE 'repuesto'")
                if not cur.fetchone():
                    cur.execute(
                        "ALTER TABLE articulos ADD COLUMN repuesto INTEGER DEFAULT 0"
                    )
                    conn.commit()
        except Exception as e:
            print(f"Error al verificar/crear columna repuesto: {e}")

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(12)

        title = QLabel("Informe de Reposición (artículos bajo el umbral)")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        layout.addWidget(title)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            [
                "Código",
                "Nombre",
                "Stock_total (almacén)",
                "Stock_tienda",
                "Stock_esperado",
            ]
        )
        self.tabla.setStyleSheet(
            "QTableWidget { background-color: #1A1D23; color: white; }"
        )
        layout.addWidget(self.tabla)

        self.tabla.resizeColumnsToContents()
        self.tabla.resizeRowsToContents()
        self.tabla.horizontalHeader().setStretchLastSection(True)

        btn_refresh = QPushButton("Actualizar lista (manual)")
        btn_refresh.clicked.connect(lambda: self.actualizar_lista(show_message=True))
        self.estilo_boton(btn_refresh)
        layout.addWidget(btn_refresh)

        btn_editar_stock = QPushButton("Editar Stock_esperado")
        btn_editar_stock.clicked.connect(self.editar_stock_esperado)
        self.estilo_boton(btn_editar_stock)
        layout.addWidget(btn_editar_stock)

        btn_export = QPushButton("Exportar informe y marcar como repuesto")
        btn_export.clicked.connect(self.exportar_y_marcar)
        self.estilo_boton(btn_export)
        layout.addWidget(btn_export)

        btn_volver = QPushButton("Volver al menú principal")
        btn_volver.clicked.connect(self.volver_menu_principal)
        self.estilo_boton(btn_volver, rojo=True)
        layout.addWidget(btn_volver, alignment=Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)
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

    def _convert_to_int(self, valor):
        try:
            return int(valor)
        except (ValueError, TypeError):
            return 0

    # ============================================================
    # BLOQUE CONSULTA DE DATOS DE REPOSICIÓN
    # ============================================================

    def obtener_articulos_reposicion(self):
        """Obtiene artículos bajo el umbral usando el context manager."""
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT codigo, nombre, Stock_total, Stock_tienda, 
                           COALESCE(stock_esperado, 0), capacidad_lineal
                    FROM articulos
                    ORDER BY nombre ASC
                    """
                )
                resultados = []
                for (
                    codigo,
                    nombre,
                    stock_total,
                    stock_tienda,
                    stock_esperado,
                    capacidad_lineal,
                ) in cur.fetchall():

                    stock_total = self._convert_to_int(stock_total)
                    stock_tienda = self._convert_to_int(stock_tienda)
                    stock_esperado = self._convert_to_int(stock_esperado)

                    if stock_esperado == 0 and capacidad_lineal:
                        stock_esperado = capacidad_lineal // 2

                    if stock_tienda < stock_esperado:
                        resultados.append(
                            (codigo, nombre, stock_total, stock_tienda, stock_esperado)
                        )
                return resultados
        except Exception as e:
            print(f"[ERROR] No se pudieron obtener los artículos: {e}")
            return []

    # ============================================================
    # BLOQUE CARGA Y ACTUALIZACIÓN DE TABLA
    # ============================================================

    def actualizar_lista(self, show_message=False):
        try:
            articulos = self.obtener_articulos_reposicion()
            self.tabla.setRowCount(0)

            if not articulos:
                if show_message:
                    QMessageBox.information(
                        self,
                        "Sin resultados",
                        "No hay artículos bajo el umbral para reposición.",
                    )
                return

            for codigo, nombre, stock_total, stock_tienda, stock_esperado in articulos:
                row_pos = self.tabla.rowCount()
                self.tabla.insertRow(row_pos)

                if stock_tienda < stock_esperado:
                    color = QColor(80, 0, 0)
                elif stock_tienda > stock_esperado:
                    color = QColor(0, 80, 0)
                else:
                    color = QColor(26, 29, 35)

                for col, value in enumerate(
                    [codigo, nombre, stock_total, stock_tienda, stock_esperado]
                ):
                    item = QTableWidgetItem(str(value))
                    item.setBackground(color)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla.setItem(row_pos, col, item)

            self.tabla.resizeColumnsToContents()
            self.tabla.resizeRowsToContents()
            self.tabla.horizontalHeader().setStretchLastSection(True)

            if show_message:
                QMessageBox.information(
                    self,
                    "Actualizado",
                    "Lista de reposición actualizada correctamente.",
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar la lista:\n{e}")

    def actualizar_stock_articulo(self, codigo):
        try:
            articulo = obtener_articulo(codigo)
            if not articulo:
                return
            stock_total, stock_tienda, capacidad_lineal, stock_esperado = (
                self._convert_to_int(articulo[2]),
                self._convert_to_int(articulo[3]),
                articulo[5],
                self._convert_to_int(articulo[7]),
            )
            if stock_esperado == 0 and capacidad_lineal:
                stock_esperado = capacidad_lineal // 2
            nombre = articulo[1]

            for r in range(self.tabla.rowCount()):
                if self.tabla.item(r, 0).text() == codigo:
                    if stock_tienda < stock_esperado:
                        color = QColor(80, 0, 0)
                    elif stock_tienda > stock_esperado:
                        color = QColor(0, 80, 0)
                    else:
                        color = QColor(26, 29, 35)

                    for col, value in enumerate(
                        [codigo, nombre, stock_total, stock_tienda, stock_esperado]
                    ):
                        if not self.tabla.item(r, col):
                            self.tabla.setItem(r, col, QTableWidgetItem(str(value)))
                        else:
                            self.tabla.item(r, col).setText(str(value))
                        self.tabla.item(r, col).setBackground(color)
                        self.tabla.item(r, col).setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter
                        )
                    break
        except Exception as e:
            print(f"Error actualizando artículo {codigo}: {e}")

    # ============================================================
    # BLOQUE EDICIÓN DE STOCK ESPERADO
    # ============================================================

    def editar_stock_esperado(self):
        try:
            codigo, ok = QInputDialog.getText(
                self, "Editar Stock_esperado", "Introduce el código del artículo:"
            )
            if not ok or not codigo:
                return
            nuevo_stock, ok = QInputDialog.getInt(
                self, "Nuevo Stock_esperado", "Introduce el nuevo valor:", 0, 0, 99999
            )
            if not ok:
                return

            if not set_stock_esperado(codigo, nuevo_stock):
                QMessageBox.critical(
                    self,
                    "Error",
                    "No se pudo actualizar el Stock_esperado en la base de datos.",
                )
                return

            self.signals.stock_actualizado.emit(codigo)
            QMessageBox.information(
                self,
                "Actualizado",
                f"Stock_esperado de {codigo} actualizado a {nuevo_stock}.",
            )
            self.actualizar_lista()
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo actualizar el Stock_esperado:\n{e}"
            )

    # ============================================================
    # BLOQUE EXPORTACIÓN DE INFORME
    # ============================================================

    def exportar_y_marcar(self):
        try:
            filas_exportar = []

            for r in range(self.tabla.rowCount()):
                stock_tienda = self._convert_to_int(self.tabla.item(r, 3).text())
                stock_esperado = self._convert_to_int(self.tabla.item(r, 4).text())
                if stock_tienda < stock_esperado:
                    filas_exportar.append(
                        [self.tabla.item(r, c).text() for c in range(5)]
                    )

            if not filas_exportar:
                QMessageBox.warning(
                    self, "Aviso", "No hay artículos bajo el umbral para exportar."
                )
                return

            base_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../")
            )
            export_dir = os.path.join(base_dir, "documentos")
            os.makedirs(export_dir, exist_ok=True)

            nombre_archivo = (
                f"informe_reposicion_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
            )
            ruta_export = os.path.join(export_dir, nombre_archivo)

            df = pd.DataFrame(
                filas_exportar,
                columns=[
                    "Código",
                    "Nombre",
                    "Stock_total (almacén)",
                    "Stock_tienda",
                    "Stock_esperado",
                ],
            )
            df.to_excel(ruta_export, index=False)

            try:
                with obtener_conexion() as conn:
                    cur = conn.cursor()
                    hoy = datetime.now().strftime("%Y-%m-%d")

                    for fila in filas_exportar:
                        codigo = fila[0]
                        stock_esperado = self._convert_to_int(fila[4])

                        cur.execute(
                            """
                            UPDATE articulos 
                            SET repuesto = 1, Stock_tienda = ?, ultima_recepcion = ? 
                            WHERE codigo = ?
                            """,
                            (stock_esperado, hoy, codigo),
                        )
                    conn.commit()

                for fila in filas_exportar:
                    self.signals.stock_actualizado.emit(fila[0])

                QMessageBox.information(
                    self,
                    "Éxito",
                    f"Informe exportado y stock actualizado correctamente:\n{ruta_export}",
                )
                self.actualizar_lista()

            except Exception as db_error:
                QMessageBox.critical(
                    self,
                    "Error de Base de Datos",
                    f"No se pudo actualizar la BD: {db_error}",
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar el informe:\n{e}")

    # ============================================================
    # BLOQUE NAVEGACIÓN
    # ============================================================

    def volver_menu_principal(self):
        """Regresa al menú principal cerrando la ventana actual."""
        if self.callback_vuelta:
            self.callback_vuelta()
            self.close()
        else:
            self.close()
