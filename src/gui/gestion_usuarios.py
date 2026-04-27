from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QPushButton,
    QComboBox,
    QLabel,
    QMessageBox,
    QHeaderView,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from src.db.usuario import (
    listar_usuarios,
    crear_perfil,
    eliminar_usuario,
    sesion_global,
)


class GestionUsuariosView(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        self.resize(950, 650)
        self.setWindowTitle("Smart Manager AI - Gestion de Accesos")

        self.set_dark_theme()
        self.init_ui()
        self.refrescar_datos()

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def set_dark_theme(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0E1117"))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def init_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(30, 20, 30, 30)
        layout_principal.setSpacing(10)

        nav_bar = QHBoxLayout()
        btn_volver = QPushButton("← VOLVER AL MENÚ")
        btn_volver.setFixedWidth(180)
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_volver.setStyleSheet(
            """
            QPushButton {
                background-color: transparent; color: #FF4B4B; border: 2px solid #FF4B4B;
                border-radius: 8px; padding: 8px; font-weight: bold; font-size: 10px;
            }
            QPushButton:hover { background-color: #FF4B4B; color: #0E1117; }
        """
        )
        btn_volver.clicked.connect(self.ejecutar_regreso)

        lbl_seccion = QLabel("GESTIÓN DE ACCESOS")
        lbl_seccion.setStyleSheet(
            "color: #FFFFFF; font-weight: bold; font-size: 14px; letter-spacing: 3px;"
        )

        nav_bar.addWidget(btn_volver)
        nav_bar.addStretch()
        nav_bar.addWidget(lbl_seccion)
        layout_principal.addLayout(nav_bar)

        line = QFrame()
        line.setStyleSheet("background-color: #00FFC6; border: none;")
        line.setFixedHeight(2)
        layout_principal.addWidget(line)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 15, 0, 0)
        content_layout.setSpacing(25)

        form_container = QFrame()
        form_container.setStyleSheet(
            "background-color: #1A1E26; border-radius: 12px; border: 1px solid #3E4451;"
        )
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(25, 25, 25, 25)
        form_layout.setSpacing(8)

        lbl_add = QLabel("NUEVA CREDENCIAL")
        lbl_add.setStyleSheet(
            "color: #00FFC6; font-weight: bold; font-size: 13px; border: none; margin-bottom: 10px;"
        )
        form_layout.addWidget(lbl_add)

        label_style = "color: #3E4451; font-weight: bold; font-size: 10px; border: none; margin-top: 5px;"
        input_css = """
            QLineEdit, QComboBox {
                background-color: #0E1117; color: white; border: 1px solid #3E4451;
                border-radius: 6px; padding: 10px; font-size: 12px; margin-bottom: 10px;
            }
            QLineEdit:focus { border: 1px solid #00FFC6; }
        """

        form_layout.addWidget(QLabel("NOMBRE DE USUARIO", styleSheet=label_style))
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej: JuanPerez")
        self.input_nombre.setStyleSheet(input_css)
        form_layout.addWidget(self.input_nombre)

        form_layout.addWidget(QLabel("CONTRASEÑA", styleSheet=label_style))
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setPlaceholderText("••••••••")
        self.input_pass.setStyleSheet(input_css)
        form_layout.addWidget(self.input_pass)

        form_layout.addWidget(QLabel("NIVEL DE PERFIL", styleSheet=label_style))
        self.combo_perfil = QComboBox()
        self.combo_perfil.addItems(["OPERARIO", "GERENTE", "ADMINISTRADOR"])
        self.combo_perfil.setStyleSheet(input_css)
        form_layout.addWidget(self.combo_perfil)

        btn_guardar = QPushButton("REGISTRAR EN SISTEMA")
        btn_guardar.setFixedHeight(45)
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.setStyleSheet(
            """
            QPushButton {
                background-color: #00FFC6; color: #0E1117; font-weight: bold; border-radius: 6px; margin-top: 15px;
            }
            QPushButton:hover { background-color: white; }
        """
        )
        btn_guardar.clicked.connect(self.ejecutar_creacion)
        form_layout.addWidget(btn_guardar)
        form_layout.addStretch()

        content_layout.addWidget(form_container, 1)

        tabla_layout = QVBoxLayout()
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(3)
        self.tabla.setHorizontalHeaderLabels(["ID REF", "USUARIO", "RANGO"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(
            """
            QTableWidget {
                background-color: #1A1E26; color: white; gridline-color: #242933;
                border: 1px solid #3E4451; border-radius: 10px; alternate-background-color: #242933;
            }
            QHeaderView::section {
                background-color: #0E1117; color: #00FFC6; padding: 10px;
                border: none; font-weight: bold; font-size: 10px;
            }
            QTableWidget::item { padding: 5px; border: none; }
            QTableWidget::item:selected { background-color: #00FFC6; color: #0E1117; }
        """
        )
        tabla_layout.addWidget(self.tabla)

        btn_eliminar = QPushButton("ELIMINAR USUARIO SELECCIONADO")
        btn_eliminar.setFixedHeight(45)
        btn_eliminar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eliminar.setStyleSheet(
            """
            QPushButton {
                background-color: transparent; color: #FF4B4B; border: 2px solid #FF4B4B;
                border-radius: 6px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #FF4B4B; color: white; }
        """
        )
        btn_eliminar.clicked.connect(self.ejecutar_eliminacion)
        tabla_layout.addWidget(btn_eliminar)

        content_layout.addLayout(tabla_layout, 2)
        layout_principal.addLayout(content_layout)

    # ============================================================
    # BLOQUE CARGA Y VISUALIZACIÓN DE DATOS
    # ============================================================

    def refrescar_datos(self):
        """Obtiene la lista de usuarios y actualiza la tabla con estilo neón."""
        self.tabla.setRowCount(0)
        usuarios = listar_usuarios()

        if not usuarios:
            return

        for i, u in enumerate(usuarios):
            self.tabla.insertRow(i)

            if isinstance(u, dict):
                valores = [
                    str(u.get("id", "")),
                    str(u.get("nombre", "")),
                    str(u.get("perfil", "")),
                ]
            else:
                valores = [str(u[0]), str(u[1]), str(u[2])]

            for col, texto in enumerate(valores):
                item = QTableWidgetItem(texto.upper())
                item.setForeground(QColor("#FFFFFF"))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(i, col, item)

        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    # ============================================================
    # BLOQUE ACCIONES DE USUARIOS
    # ============================================================

    def ejecutar_creacion(self):
        nombre = self.input_nombre.text().strip()
        pw = self.input_pass.text().strip()
        perfil = self.combo_perfil.currentText()

        if not nombre or not pw:
            QMessageBox.warning(self, "Aviso", "Los campos no pueden estar vacíos.")
            return

        if crear_perfil(nombre, pw, perfil):
            QMessageBox.information(self, "Sistema", f"Acceso concedido a {nombre}.")
            self.input_nombre.clear()
            self.input_pass.clear()
            self.refrescar_datos()
        else:
            QMessageBox.critical(self, "Error", "No se pudo registrar el perfil.")

    def ejecutar_eliminacion(self):
        """Gestiona el borrado de usuarios con protecciones de seguridad."""
        fila = self.tabla.currentRow()
        if fila < 0:
            QMessageBox.warning(
                self, "Selección", "Por favor, seleccione un usuario de la lista."
            )
            return

        id_user = self.tabla.item(fila, 0).text()
        nombre = self.tabla.item(fila, 1).text()

        if nombre.upper() == sesion_global.obtener_nombre().upper():
            QMessageBox.critical(
                self,
                "Seguridad",
                "Operación denegada: No puede eliminar su propia cuenta activa.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar permanentemente a {nombre}?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm == QMessageBox.StandardButton.Yes:
            try:
                if eliminar_usuario(id_user):
                    self.refrescar_datos()
                    QMessageBox.information(
                        self, "Éxito", f"Usuario {nombre} eliminado correctamente."
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "La base de datos rechazó la solicitud de eliminación.",
                    )
            except Exception as e:
                QMessageBox.critical(
                    self, "Error Crítico", f"Error al procesar la baja: {e}"
                )

    # ============================================================
    # BLOQUE NAVEGACIÓN
    # ============================================================

    def ejecutar_regreso(self):
        """Regresa al menú principal usando el callback y cierra la vista actual."""
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()
