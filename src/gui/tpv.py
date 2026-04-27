# src/gui/tpv.py
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QInputDialog,
    QDialog,
    QLabel,
)
from PyQt6.QtCore import Qt
from src.db.conexion import obtener_articulo, stock_signals
from src.utils.reportes_safebag import generar_safebag_pdf
import datetime
import sqlite3
import os
import json

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "stock.db"
)

RENTENTIONS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ventas_retenidas.json"
)

UMBRAL_MAX_CAJA = 1000.0
UMBRAL_MIN_CAJA = 50.0


class TPVWindow(QWidget):
    def __init__(self, empleado_id=None, cliente_id=None):
        super().__init__()
        self.empleado_id = empleado_id
        self.cliente_id = cliente_id
        self.venta_temporal = []
        self.total_efectivo_actual = 0.0
        self.init_ui()

    # ============================================================
    # BLOQUE INTERFAZ
    # ============================================================

    def init_ui(self):
        self.setWindowTitle("TPV Smart Manager AI")
        layout = QVBoxLayout()

        self.input_sku = QLineEdit()
        self.input_sku.setPlaceholderText("Código de artículo")
        layout.addWidget(self.input_sku)

        self.btn_add = QPushButton("Agregar producto")
        self.btn_add.clicked.connect(self.add_item_by_sku)
        layout.addWidget(self.btn_add)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Nombre", "Cantidad", "Precio Unitario"]
        )
        layout.addWidget(self.table)

        self.btn_pago = QPushButton("Pagar")
        self.btn_pago.clicked.connect(self.realizar_pago)
        layout.addWidget(self.btn_pago)

        self.btn_retener = QPushButton("Retener compra")
        self.btn_retener.clicked.connect(self.retner_compra)
        layout.addWidget(self.btn_retener)

        self.btn_cajon = QPushButton("Abrir cajón")
        self.btn_cajon.clicked.connect(self.abrir_cajon)
        layout.addWidget(self.btn_cajon)

        self.btn_umbral = QPushButton("Umbral caja registradora")
        self.btn_umbral.clicked.connect(self.configurar_umbral_caja)
        layout.addWidget(self.btn_umbral)

        self.btn_safebag = QPushButton("Arqueo / SafeBag")
        self.btn_safebag.clicked.connect(self.abrir_safebag)
        layout.addWidget(self.btn_safebag)

        self.setLayout(layout)

    # ============================================================
    # BLOQUE GESTIÓN DE ARTÍCULOS EN VENTA
    # ============================================================

    def add_item_by_sku(self):
        codigo = self.input_sku.text().strip()
        if not codigo:
            return
        articulo = obtener_articulo(codigo)
        if not articulo:
            QMessageBox.warning(
                self, "Error", f"No se encontró el artículo con código {codigo}"
            )
            return
        codigo, nombre, stock_total, stock_tienda, precio_unitario, _, _, _ = articulo
        item = {
            "codigo": codigo,
            "nombre": nombre,
            "cantidad": 1,
            "precio_unitario": precio_unitario,
        }
        self.venta_temporal.append(item)
        self.refresh_table()
        self.input_sku.clear()

    def refresh_table(self):
        self.table.setRowCount(len(self.venta_temporal))
        for row, item in enumerate(self.venta_temporal):
            self.table.setItem(row, 0, QTableWidgetItem(str(item["codigo"])))
            self.table.setItem(row, 1, QTableWidgetItem(item["nombre"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(item["cantidad"])))
            self.table.setItem(
                row, 3, QTableWidgetItem(f"{item['precio_unitario']:.2f}")
            )

    # ============================================================
    # BLOQUE PROCESAMIENTO DE PAGOS
    # ============================================================

    def realizar_pago(self):
        if not self.venta_temporal:
            QMessageBox.warning(self, "Error", "No hay productos en la venta")
            return

        fecha = datetime.datetime.now().isoformat()
        total = sum([i["cantidad"] * i["precio_unitario"] for i in self.venta_temporal])
        forma_pago = "efectivo"

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ventas (fecha, empleado_id, cliente_id, total, forma_pago, estado)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    fecha,
                    self.empleado_id,
                    self.cliente_id,
                    total,
                    forma_pago,
                    "finalizada",
                ),
            )
            venta_id = cur.lastrowid
            for item in self.venta_temporal:
                subtotal = item["cantidad"] * item["precio_unitario"]
                cur.execute(
                    """
                    INSERT INTO venta_items (venta_id, codigo_articulo, cantidad, precio_unitario, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        venta_id,
                        item["codigo"],
                        item["cantidad"],
                        item["precio_unitario"],
                        subtotal,
                    ),
                )
            conn.commit()
            conn.close()

            for item in self.venta_temporal:
                stock_signals.stock_actualizado.emit(str(item["codigo"]))

            if forma_pago == "efectivo":
                self.total_efectivo_actual += total
                self.verificar_umbrales_caja(self.total_efectivo_actual)

            QMessageBox.information(
                self,
                "Venta registrada",
                f"Venta registrada correctamente.\nTotal: {total:.2f} €",
            )
            self.venta_temporal = []
            self.refresh_table()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo registrar la venta: {e}")

    # ============================================================
    # BLOQUE RETENCIÓN DE COMPRAS
    # ============================================================

    def retner_compra(self):
        if not self.venta_temporal:
            QMessageBox.warning(self, "Error", "No hay productos para retener")
            return
        if os.path.exists(RENTENTIONS_FILE):
            with open(RENTENTIONS_FILE, "r", encoding="utf-8") as f:
                retenidas = json.load(f)
        else:
            retenidas = []
        retenidas.append(
            {
                "fecha": datetime.datetime.now().isoformat(),
                "empleado_id": self.empleado_id,
                "cliente_id": self.cliente_id,
                "items": self.venta_temporal,
            }
        )
        with open(RENTENTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(retenidas, f, indent=4)
        QMessageBox.information(self, "Retención", "Compra retenida temporalmente")
        self.venta_temporal = []
        self.refresh_table()

    # ============================================================
    # BLOQUE GESTIÓN DE CAJA
    # ============================================================

    def abrir_cajon(self):
        QMessageBox.information(self, "Cajón", "Cajón abierto (simulado)")

    def configurar_umbral_caja(self):
        global UMBRAL_MAX_CAJA, UMBRAL_MIN_CAJA
        max_val, ok1 = QInputDialog.getDouble(
            self,
            "Umbral máximo caja",
            "Introduce el umbral máximo:",
            UMBRAL_MAX_CAJA,
            0,
            100000,
            2,
        )
        if ok1:
            UMBRAL_MAX_CAJA = max_val
        min_val, ok2 = QInputDialog.getDouble(
            self,
            "Umbral mínimo caja",
            "Introduce el umbral mínimo:",
            UMBRAL_MIN_CAJA,
            0,
            100000,
            2,
        )
        if ok2:
            UMBRAL_MIN_CAJA = min_val
        QMessageBox.information(
            self,
            "Umbral actualizado",
            f"Nuevo umbral máximo: {UMBRAL_MAX_CAJA}\nNuevo umbral mínimo: {UMBRAL_MIN_CAJA}",
        )

    def verificar_umbrales_caja(self, total_efectivo_actual):
        if total_efectivo_actual > UMBRAL_MAX_CAJA:
            QMessageBox.warning(
                self,
                "Exceso de efectivo",
                f"¡Atención! La caja ha sobrepasado el umbral máximo de {UMBRAL_MAX_CAJA} €.\n"
                "Se recomienda realizar una retirada de efectivo.",
            )
        elif total_efectivo_actual < UMBRAL_MIN_CAJA:
            QMessageBox.warning(
                self,
                "Defecto de efectivo",
                f"¡Atención! La caja ha caído por debajo del umbral mínimo de {UMBRAL_MIN_CAJA} €.\n"
                "Se recomienda ingresar efectivo a la caja.",
            )

    # ============================================================
    # BLOQUE ARQUEO Y SAFEBAG
    # ============================================================

    def abrir_safebag(self):
        dialog = SafeBagDialog(self)
        dialog.exec()


class SafeBagDialog(QDialog):
    def __init__(self, tpv_window):
        super().__init__()
        self.tpv = tpv_window
        self.init_ui()

    # ============================================================
    # BLOQUE INTERFAZ SAFEBAG
    # ============================================================

    def init_ui(self):
        self.setWindowTitle("Arqueo / SafeBag")
        layout = QVBoxLayout()

        self.label_efectivo = QLabel(
            f"Efectivo en caja actual: {self.tpv.total_efectivo_actual:.2f} €"
        )
        layout.addWidget(self.label_efectivo)

        self.input_retirada = QLineEdit()
        self.input_retirada.setPlaceholderText("Cantidad a retirar")
        layout.addWidget(self.input_retirada)

        self.input_referencia = QLineEdit()
        self.input_referencia.setPlaceholderText("Referencia SafeBag")
        layout.addWidget(self.input_referencia)

        self.btn_confirmar = QPushButton("Confirmar arqueo / retirada")
        self.btn_confirmar.clicked.connect(self.realizar_arqueo)
        layout.addWidget(self.btn_confirmar)

        self.setLayout(layout)

    # ============================================================
    # BLOQUE PROCESAMIENTO DE ARQUEO
    # ============================================================

    def realizar_arqueo(self):
        try:
            retirada = float(self.input_retirada.text() or 0)
            referencia = (
                self.input_referencia.text()
                or f"SB-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            self.tpv.total_efectivo_actual -= retirada
            if self.tpv.total_efectivo_actual < 0:
                self.tpv.total_efectivo_actual = 0

            self.tpv.verificar_umbrales_caja(self.tpv.total_efectivo_actual)

            generar_safebag_pdf(
                fecha=datetime.datetime.now().date(),
                total_efectivo=self.tpv.total_efectivo_actual,
                retirada=retirada,
                referencia=referencia,
            )

            QMessageBox.information(
                self,
                "SafeBag",
                f"Arqueo realizado y PDF generado.\nReferencia: {referencia}",
            )
            self.close()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo realizar el arqueo: {e}")
