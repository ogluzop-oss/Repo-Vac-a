import os
import sqlite3
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
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from src.db.conexion import (
    listar_stock,
    modificar_stock_completo,
    ensure_schema,
    set_stock_esperado,
)
from src.gui.importar_stock import ImportarStock


class StockSignals(QObject):
    stock_actualizado = pyqtSignal(str)


stock_signals = StockSignals()


class MostrarStockWindow(QWidget):
    def __init__(
        self, callback_vuelta=None, usuario=None, stock_signals_instance=None, **kwargs
    ):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        ensure_schema()

        self.signals = stock_signals_instance or stock_signals
        self.signals.stock_actualizado.connect(self.actualizar_stock_articulo)

        self.setup_ui()
        self.cargar_stock()

        self.setStyleSheet("background-color: #0E1117; color: white;")

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def setup_ui(self):
        self.setWindowTitle("Mostrar Stock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(12)

        title = QLabel("Stock de tienda")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        layout.addWidget(title)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(6)
        self.tabla.setHorizontalHeaderLabels(
            [
                "Código",
                "Nombre",
                "Stock Almacén Central",
                "Stock Almacén Tienda",
                "Stock Lineal",
                "Stock Esperado",
            ]
        )
        self.tabla.setStyleSheet(
            "QTableWidget { background-color: #1A1D23; color: white; }"
        )
        layout.addWidget(self.tabla)

        if self.perfil == "Gerente":
            btn_modstock = QPushButton("Modificar stock (Gerente)")
            btn_modstock.clicked.connect(self.modificar_stock_ui)
            self.estilo_boton(btn_modstock)
            layout.addWidget(btn_modstock)

            btn_export = QPushButton("Exportar informe de stock completo")
            btn_export.clicked.connect(self.exportar_stock_completo_excel)
            self.estilo_boton(btn_export)
            layout.addWidget(btn_export)

            btn_export_agotado = QPushButton("Exportar informe de stock agotado")
            btn_export_agotado.clicked.connect(self.exportar_stock_agotado_excel)
            self.estilo_boton(btn_export_agotado)
            layout.addWidget(btn_export_agotado)

        btn_importar = QPushButton("📦 Importar stock desde fichero (Excel / TXT)")
        btn_importar.clicked.connect(self.importar_stock)
        self.estilo_boton(btn_importar)
        layout.addWidget(btn_importar)

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
    # BLOQUE CARGA DE STOCK
    # ============================================================

    def cargar_stock(self):
        try:
            rows = listar_stock()
            self.tabla.setRowCount(len(rows))

            for r, row in enumerate(rows):
                codigo = str(row[0])
                nombre = str(row[1])
                stock_central = self._convert_to_int(row[2])
                stock_total = self._convert_to_int(row[3])
                stock_tienda = self._convert_to_int(row[4])
                stock_esperado = self._convert_to_int(row[5])

                valores = [
                    codigo,
                    nombre,
                    stock_central,
                    stock_total,
                    stock_tienda,
                    stock_esperado,
                ]

                for c, val in enumerate(valores):
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla.setItem(r, c, item)

            self.tabla.resizeColumnsToContents()
            self.tabla.resizeRowsToContents()
            ancho_actual = self.tabla.columnWidth(3)
            self.tabla.setColumnWidth(3, ancho_actual + 60)

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo cargar el stock:\n{str(e)}"
            )

    def actualizar_stock_articulo(self, codigo):
        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
            )
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT Stock_central, Stock_total, Stock_tienda, COALESCE(stock_esperado, 0)
                FROM articulos WHERE codigo = ?
            """,
                (codigo,),
            )
            row = cur.fetchone()
            conn.close()

            if row:
                stock_central, stock_total, stock_tienda, stock_esperado = row
                fila = self._fila_codigo(codigo)
                if fila >= 0:
                    self.tabla.item(fila, 2).setText(str(stock_central))
                    self.tabla.item(fila, 3).setText(str(stock_total))
                    self.tabla.item(fila, 4).setText(str(stock_tienda))
                    self.tabla.item(fila, 5).setText(str(stock_esperado))
        except Exception as e:
            print(f"Error actualizando artículo {codigo}: {e}")

    def _fila_codigo(self, codigo):
        for r in range(self.tabla.rowCount()):
            item = self.tabla.item(r, 0)
            if item and item.text() == codigo:
                return r
        return -1

    # ============================================================
    # BLOQUE MODIFICACIÓN DE STOCK (GERENTE)
    # ============================================================

    def modificar_stock_ui(self):
        fila = self.tabla.currentRow()
        if fila == -1:
            QMessageBox.warning(self, "Aviso", "Selecciona un artículo para modificar")
            return

        codigo = self.tabla.item(fila, 0).text()
        stock_central_actual = self._convert_to_int(self.tabla.item(fila, 2).text())
        stock_total_actual = self._convert_to_int(self.tabla.item(fila, 3).text())
        stock_tienda_actual = self._convert_to_int(self.tabla.item(fila, 4).text())
        stock_esperado_actual = self._convert_to_int(self.tabla.item(fila, 5).text())

        nuevo_central, ok0 = QInputDialog.getInt(
            self,
            "Modificar Stock_almacén central",
            f"Nuevo Stock_almacén central para {codigo}:",
            value=stock_central_actual,
            min=0,
        )
        if not ok0:
            return

        nuevo_total, ok1 = QInputDialog.getInt(
            self,
            "Modificar Stock_total (almacén)",
            f"Nuevo Stock_total (almacén) para {codigo}:",
            value=stock_total_actual,
            min=0,
        )
        if not ok1:
            return

        nuevo_tienda, ok2 = QInputDialog.getInt(
            self,
            "Modificar Stock_tienda (lineal)",
            f"Nuevo Stock_tienda (lineal) para {codigo}:",
            value=stock_tienda_actual,
            min=0,
        )
        if not ok2:
            return

        nuevo_esperado, ok3 = QInputDialog.getInt(
            self,
            "Modificar Stock_esperado",
            f"Nuevo Stock_esperado para {codigo}:",
            value=stock_esperado_actual,
            min=0,
        )
        if not ok3:
            return

        try:
            ok_total = modificar_stock_completo(
                codigo, nuevo_central, nuevo_total, nuevo_tienda
            )
            ok_esperado = set_stock_esperado(codigo, nuevo_esperado)

            if ok_total and ok_esperado:
                self.signals.stock_actualizado.emit(codigo)
                QMessageBox.information(
                    self,
                    "Éxito",
                    f"Stock actualizado correctamente para el artículo {codigo}.",
                )
                self.cargar_stock()
            else:
                raise RuntimeError(
                    f"No se pudo actualizar completamente el stock (total={ok_total}, esperado={ok_esperado})"
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo actualizar el stock:\n{str(e)}"
            )

    # ============================================================
    # BLOQUE EXPORTACIÓN DE INFORMES
    # ============================================================

    def exportar_stock_completo_excel(self):
        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
            )
            conn = sqlite3.connect(db_path)
            query = """
                SELECT 
                    codigo AS Código, 
                    nombre AS Nombre,
                    Stock_central AS 'Stock_almacén central',
                    Stock_total AS 'Stock_total (almacén)',
                    Stock_tienda AS 'Stock_tienda (lineal)',
                    stock_esperado AS 'Stock_esperado'
                FROM articulos
            """
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                QMessageBox.information(
                    self, "Aviso", "No hay artículos para exportar."
                )
                return

            exports_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../documentos/stocks")
            )
            os.makedirs(exports_dir, exist_ok=True)
            ruta_excel = os.path.join(
                exports_dir,
                f"Stock_Completo_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            )
            df.to_excel(ruta_excel, index=False)
            QMessageBox.information(
                self, "Éxito", f"Informe exportado correctamente:\n{ruta_excel}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo exportar el informe:\n{str(e)}"
            )

    def exportar_stock_agotado_excel(self):
        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
            )
            conn = sqlite3.connect(db_path)
            query = """
                SELECT 
                    codigo AS Código, 
                    nombre AS Nombre,
                    Stock_central AS 'Stock_almacén central',
                    Stock_total AS 'Stock_total (almacén)',
                    Stock_tienda AS 'Stock_tienda (lineal)',
                    stock_esperado AS 'Stock_esperado'
                FROM articulos
                WHERE Stock_total <= 0
            """
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                QMessageBox.information(self, "Aviso", "No hay artículos agotados.")
                return

            exports_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../documentos/stocks")
            )
            os.makedirs(exports_dir, exist_ok=True)
            ruta_excel = os.path.join(
                exports_dir, f"Stock_Agotado_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            )
            df.to_excel(ruta_excel, index=False)
            QMessageBox.information(
                self, "Éxito", f"Informe exportado correctamente:\n{ruta_excel}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo exportar el informe:\n{str(e)}"
            )

    # ============================================================
    # BLOQUE IMPORTACIÓN DE STOCK
    # ============================================================

    def importar_stock(self):
        try:
            importador = ImportarStock()
            importador.cargar_desde_fichero(formatos_permitidos=["*.xlsx", "*.txt"])
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo importar el fichero:\n{str(e)}"
            )

    # ============================================================
    # BLOQUE NAVEGACIÓN
    # ============================================================

    def volver_menu_principal(self):
        """Regresa al menú principal usando el callback estandarizado."""
        if self.callback_vuelta:
            self.callback_vuelta()
            self.close()
        else:
            self.close()
