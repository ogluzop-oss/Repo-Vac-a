import os
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QSpinBox,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QInputDialog,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt

from src.db.mermas import (
    registrar_merma,
    modificar_merma,
    obtener_mermas,
    eliminar_merma,
)


class GestionMermasWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()

        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        self.setWindowTitle("Gestión de Mermas")
        self.resize(850, 600)

        self.setup_ui()
        self.cargar_mermas()

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        self.setLayout(layout)

        title = QLabel("Gestión de Mermas")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #00FFC6; margin-bottom: 10px;")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Código", "Cantidad", "Motivo", "Fecha"]
        )
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(
            """
            QTableWidget {
                background-color: #1A1D23;
                color: white;
                gridline-color: #30363D;
                border: 1px solid #30363D;
                border-radius: 8px;
            }
            QTableWidget::item { padding: 10px; }
            QHeaderView::section {
                background-color: #0E1117;
                color: #00FFC6;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #30363D;
            }
        """
        )
        self.tabla.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tabla)

        form_container = QWidget()
        form_layout = QHBoxLayout(form_container)

        self.input_codigo = QSpinBox()
        self.input_codigo.setMaximum(999999)
        self.input_codigo.setPrefix("Código: ")
        self.input_codigo.setStyleSheet(
            "background-color: #1A1D23; color: white; padding: 8px; border-radius: 5px;"
        )

        self.input_cantidad = QSpinBox()
        self.input_cantidad.setMaximum(1000)
        self.input_cantidad.setPrefix("Cantidad: ")
        self.input_cantidad.setStyleSheet(
            "background-color: #1A1D23; color: white; padding: 8px; border-radius: 5px;"
        )

        self.combo_motivo = QComboBox()
        self.combo_motivo.addItems(["Caducidad", "Roto", "Robo", "Otro"])
        self.combo_motivo.setStyleSheet(
            "background-color: #1A1D23; color: white; padding: 8px; border-radius: 5px;"
        )

        self.btn_registrar = QPushButton("Registrar Merma")
        self.btn_registrar.clicked.connect(self.registrar_merma_ui)
        self.estilo_boton(self.btn_registrar)

        form_layout.addWidget(self.input_codigo)
        form_layout.addWidget(self.input_cantidad)
        form_layout.addWidget(self.combo_motivo)
        form_layout.addWidget(self.btn_registrar)
        layout.addWidget(form_container)

        if str(self.perfil).upper() in ["GERENTE", "ADMINISTRADOR"]:
            admin_layout = QHBoxLayout()

            self.btn_modificar = QPushButton("Modificar Selección")
            self.btn_modificar.clicked.connect(self.modificar_merma_ui)
            self.estilo_boton(self.btn_modificar)

            self.btn_eliminar = QPushButton("Eliminar Merma")
            self.btn_eliminar.clicked.connect(self.eliminar_merma_ui)
            self.estilo_boton(self.btn_eliminar)

            self.btn_exportar = QPushButton("Exportar Excel")
            self.btn_exportar.clicked.connect(self.exportar_mermas_ui)
            self.estilo_boton(self.btn_exportar)

            admin_layout.addWidget(self.btn_modificar)
            admin_layout.addWidget(self.btn_eliminar)
            admin_layout.addWidget(self.btn_exportar)
            layout.addLayout(admin_layout)

        btn_volver = QPushButton("Volver al Menú Principal")
        btn_volver.clicked.connect(self.volver_menu_principal)
        self.estilo_boton(btn_volver, rojo=True)
        layout.addWidget(btn_volver, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet("background-color: #0E1117;")

    # ============================================================
    # BLOQUE ESTILO DE BOTONES
    # ============================================================

    def estilo_boton(self, btn, rojo=False):
        base = "#FF4B4B" if rojo else "#00FFC6"
        hover = "#FF2222" if rojo else "#00DDAA"
        text = "#FFFFFF" if rojo else "#0E1117"

        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {base};
                color: {text};
                font-weight: bold;
                border-radius: 12px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        )
        btn.setFont(QFont("Segoe UI", 10))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    # ============================================================
    # BLOQUE CARGA Y VISUALIZACIÓN DE DATOS
    # ============================================================

    def cargar_mermas(self):
        try:
            datos = obtener_mermas()
            self.tabla.setRowCount(0)
            if datos:
                for row_idx, row_data in enumerate(datos):
                    self.tabla.insertRow(row_idx)
                    for col_idx, val in enumerate(row_data):
                        item = QTableWidgetItem(str(val))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.tabla.setItem(row_idx, col_idx, item)
        except Exception as e:
            print(f"Error visualizando mermas: {e}")

    # ============================================================
    # BLOQUE ACCIONES DE MERMAS
    # ============================================================

    def registrar_merma_ui(self):
        codigo = self.input_codigo.value()
        cantidad = self.input_cantidad.value()
        motivo = self.combo_motivo.currentText()
        if registrar_merma(codigo, cantidad, motivo):
            QMessageBox.information(self, "Éxito", "Merma registrada correctamente ✅")
            self.cargar_mermas()
        else:
            QMessageBox.warning(self, "Error", "No se pudo registrar la merma ❌")

    def modificar_merma_ui(self):
        fila = self.tabla.currentRow()
        if fila == -1:
            QMessageBox.warning(self, "Error", "Selecciona una merma de la tabla.")
            return

        id_merma = int(self.tabla.item(fila, 0).text())
        nueva_cantidad, ok = QInputDialog.getInt(
            self,
            "Modificar",
            "Nueva cantidad:",
            value=int(self.tabla.item(fila, 2).text()),
        )

        if ok:
            if modificar_merma(id_merma, nueva_cantidad):
                QMessageBox.information(self, "Éxito", "Merma actualizada ✅")
                self.cargar_mermas()

    def eliminar_merma_ui(self):
        fila = self.tabla.currentRow()
        if fila == -1:
            QMessageBox.warning(self, "Error", "Selecciona una merma para eliminar.")
            return

        id_merma = int(self.tabla.item(fila, 0).text())
        confirmar = QMessageBox.question(
            self,
            "Confirmar",
            f"¿Eliminar merma ID {id_merma}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirmar == QMessageBox.StandardButton.Yes:
            if eliminar_merma(id_merma):
                self.cargar_mermas()

    # ============================================================
    # BLOQUE EXPORTACIÓN DE DATOS
    # ============================================================

    def exportar_mermas_ui(self):
        try:
            datos = []
            for r in range(self.tabla.rowCount()):
                datos.append(
                    [
                        self.tabla.item(r, c).text()
                        for c in range(self.tabla.columnCount())
                    ]
                )

            if not datos:
                return

            base_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../")
            )
            export_dir = os.path.join(base_dir, "documentos")
            os.makedirs(export_dir, exist_ok=True)

            nombre_archivo = f"mermas_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
            ruta_export = os.path.join(export_dir, nombre_archivo)

            df = pd.DataFrame(
                datos, columns=["ID", "Código", "Cantidad", "Motivo", "Fecha"]
            )
            df.to_excel(ruta_export, index=False)
            QMessageBox.information(
                self, "Exportado", f"Archivo guardado en:\n{ruta_export}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al exportar: {e}")

    # ============================================================
    # BLOQUE NAVEGACIÓN
    # ============================================================

    def volver_menu_principal(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()
