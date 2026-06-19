"""
Diálogos RRHH de empleados: identificación, PIN y asignación (F3.0.3).

Clases EXTRAÍDAS VERBATIM desde gui/gestion_usuarios.py (mover + shim): mismo
código, señales, estilos y nombres. Las dependencias compartidas del módulo
original se importan de forma diferida al final (uso en runtime) para romper el
ciclo de imports sin duplicar lógica (mismo patrón validado en F3.0.2).
"""

import json
import math
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBitmap,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,  # Añadir QTimeEdit y QCalendarWidget (Ya estaban)
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,  # <-- ¡Añadir esta importación!
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProxyStyle,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import (
    mostrar_confirmacion,
    mostrar_mensaje,
)
from src.db.conexion import guardar_referencia, obtener_referencias
from src.db.usuario import (
    cambiar_password_usuario,
    crear_perfil,
    eliminar_usuario,
    listar_fichajes,
    listar_usuarios,
    obtener_fichaje_abierto,
    registrar_entrada,
    registrar_salida,
    sesion_global,
    validar_pin_fichaje,
)
from src.db import devoluciones_baneados
from src.utils import divisas, i18n, pdf_fonts
from src.utils.i18n import tr
from src.utils.logger import LOG_DOCUMENTOS


class _PinDialog(QDialog):
    """Verificación de PIN de usuario con rol MÍNIMO requerido (jerárquico):
    un perfil de rango igual o superior al exigido también autoriza
    (p. ej. exigir GERENTE acepta GERENTE, ADMINISTRADOR y SUPERADMIN)."""

    _RANK = {"OPERARIO": 1, "GERENTE": 2, "ADMINISTRADOR": 3, "SUPERADMIN": 4}

    def __init__(self, rol_requerido="GERENTE", motivo="autorizar esta acción", parent=None,
                 roles_label=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._rol = rol_requerido
        self._roles_label = roles_label or rol_requerido
        self._ok = False
        self._usuario_nombre = ""
        self._usuario_id = None
        self._build(motivo)

    def _roles_permitidos(self) -> list:
        base = self._RANK.get(self._rol, 2)
        return [r for r, v in self._RANK.items() if v >= base]

    def _build(self, motivo):
        card = QFrame(self); card.setObjectName("pc")
        card.setStyleSheet("QFrame#pc{background:#0E1117;border:2px solid #E3B341;border-radius:18px;}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(32, 28, 32, 28); ly.setSpacing(14)

        lbl_t = QLabel("🔐  " + tr("cfg.pin_auth_title", default="SE REQUIERE AUTORIZACIÓN DE {rol}", rol=self._roles_label))
        lbl_t.setStyleSheet("color:#E3B341;font-family:'Segoe UI';font-weight:900;font-size:14px;")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setWordWrap(True)
        lbl_m = QLabel(tr("cfg.pin_auth_msg", default="Introduzca el PIN de un {rol} para {motivo}.", rol=self._roles_label.lower(), motivo=motivo))
        lbl_m.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m.setWordWrap(True)
        ly.addWidget(lbl_t); ly.addWidget(lbl_m)

        self._pin_inp = QLineEdit()
        self._pin_inp.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_inp.setPlaceholderText(tr("cfg.pin_ph4", default="PIN (4 dígitos)"))
        self._pin_inp.setMaxLength(4)
        self._pin_inp.setFixedHeight(52)
        self._pin_inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pin_inp.setStyleSheet(
            "QLineEdit{background:#161B22;color:white;border:2px solid #E3B341;"
            "border-radius:12px;font-family:'Segoe UI';font-weight:900;font-size:22px;}"
        )
        ly.addWidget(self._pin_inp)

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:#F85149;font-family:'Segoe UI';font-size:11px;")
        self._lbl_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(self._lbl_err)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.verify", default="VERIFICAR")); bk.setFixedHeight(40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet("QPushButton{background:#0D1117;color:#E3B341;border:2px solid #E3B341;border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}QPushButton:hover{background:#E3B341;color:#0D1117;}")
        bk.clicked.connect(self._verificar)
        self._pin_inp.returnPressed.connect(self._verificar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedSize(520, 300)

    def _verificar(self):
        pin = self._pin_inp.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            self._lbl_err.setText(tr("cfg.pin_len_err", default="El PIN debe tener exactamente 4 dígitos.")); return
        import hashlib
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        roles = self._roles_permitidos()
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("SHOW COLUMNS FROM usuarios")
                cols = [r["Field"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
                col = "nombre" if "nombre" in cols else "usuario"
                ph = ",".join(["%s"] * len(roles))
                cur.execute(
                    f"SELECT id, {col} FROM usuarios WHERE password=%s AND activo=1 AND perfil IN ({ph})",
                    (pin_hash, *roles))
                row = cur.fetchone()
                if row:
                    self._ok = True
                    self._usuario_id = row[0] if not isinstance(row, dict) else row["id"]
                    self._usuario_nombre = row[1] if not isinstance(row, dict) else row[col]
                    self.accept(); return
            self._lbl_err.setText(tr("cfg.pin_wrong_auth", default="PIN incorrecto o usuario no autorizado."))
            self._pin_inp.clear(); self._pin_inp.setFocus()
        except Exception:
            self._lbl_err.setText(tr("cfg.pin_conn_err", default="Error de conexión con la base de datos."))

    def verificado(self) -> bool:
        return self._ok

    def usuario_nombre(self) -> str:
        return self._usuario_nombre

    def usuario_id(self):
        return self._usuario_id
class _AsignarEmpleadoDialog(QDialog):
    """Selección del empleado responsable de la caja registradora que se va a habilitar."""

    def __init__(self, id_caja: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._empleado_nombre: str = ""
        self._build(id_caja)

    def _build(self, id_caja: str):
        card = QFrame(self)
        card.setObjectName("ae")
        card.setStyleSheet(
            f"QFrame#ae{{background:#0E1117;border:2px solid {_CIAN};"
            f"border-radius:18px;min-width:420px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(14)

        lbl_t = QLabel("👤  " + tr("cfg.assign_emp_title", default="ASIGNAR EMPLEADO — {id}", id=id_caja))
        lbl_t.setStyleSheet(
            f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:14px;"
        )
        ly.addWidget(lbl_t)

        lbl_sub = QLabel(tr("cfg.assign_emp_sub", default="Selecciona el empleado responsable de esta caja registradora:"))
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
        ly.addWidget(lbl_sub)

        # Filtro de búsqueda
        self._inp_buscar = QLineEdit()
        self._inp_buscar.setPlaceholderText("🔍  " + tr("cfg.search_emp_ph", default="Buscar empleado..."))
        self._inp_buscar.setFixedHeight(36)
        self._inp_buscar.setStyleSheet(
            f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};"
            f"border-radius:8px;padding:4px 12px;font-family:'Segoe UI';font-size:13px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        self._inp_buscar.textChanged.connect(self._filtrar)
        ly.addWidget(self._inp_buscar)

        # Lista de empleados
        self._lista = QListWidget()
        self._lista.setFixedHeight(180)
        self._lista.setStyleSheet(
            f"QListWidget{{background:#161B22;color:white;border:2px solid {_BORDE};"
            f"border-radius:8px;font-family:'Segoe UI';font-size:13px;outline:none;}}"
            f"QListWidget::item{{padding:8px 12px;border-bottom:1px solid #21262D;}}"
            f"QListWidget::item:selected{{background:{_CIAN};color:#0D1117;border-radius:6px;}}"
            f"QListWidget::item:hover{{background:#21262D;}}"
        )
        self._lista.itemSelectionChanged.connect(self._on_sel)
        ly.addWidget(self._lista)

        self._lbl_sel = QLabel(tr("cfg.none_selected", default="Ningún empleado seleccionado"))
        self._lbl_sel.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;")
        ly.addWidget(self._lbl_sel)

        # Botones
        br = QHBoxLayout()
        br.setSpacing(16)

        bc = QPushButton(tr("cfg.cancel", default="CANCELAR"))
        bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            "QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}"
        )
        bc.clicked.connect(self.reject)

        _ss_off = (
            "QPushButton{background:#161B22;color:#6E7681;border:2px solid #6E7681;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
        )
        _ss_on = (
            f"QPushButton{{background:{_CIAN};color:#0D1117;border:2px solid {_CIAN};"
            f"border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}}"
            f"QPushButton:hover{{background:#FFFFFF;color:#0D1117;border:2px solid #FFFFFF;}}"
        )
        self._ss_off = _ss_off
        self._ss_on  = _ss_on

        self._btn_ok = QPushButton("✔  " + tr("cfg.assign_btn", default="ASIGNAR"))
        self._btn_ok.setFixedHeight(40)
        self._btn_ok.setMinimumWidth(140)
        self._btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ok.setStyleSheet(_ss_off)
        self._btn_ok.setEnabled(False)
        self._btn_ok.clicked.connect(self._confirmar)

        br.addWidget(bc)
        br.addStretch(1)
        br.addWidget(self._btn_ok)
        ly.addLayout(br)

        # Cargar empleados
        self._todos: list[str] = []
        try:
            for u in listar_usuarios():
                nombre = u.get("nombre") or u.get("usuario") or ""
                if nombre:
                    self._todos.append(nombre.upper())
        except Exception:
            pass
        self._poblar(self._todos)

    def _poblar(self, nombres: list[str]):
        self._lista.clear()
        for n in nombres:
            item = QListWidgetItem(n)
            self._lista.addItem(item)

    def _filtrar(self, texto: str):
        txt = texto.strip().upper()
        filtrados = [n for n in self._todos if txt in n] if txt else self._todos
        self._poblar(filtrados)

    def _on_sel(self):
        items = self._lista.selectedItems()
        if items:
            self._empleado_nombre = items[0].text()
            self._lbl_sel.setText(tr("cfg.selected_x", default="Seleccionado: {x}", x=self._empleado_nombre))
            self._lbl_sel.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-size:11px;font-weight:bold;")
            self._btn_ok.setEnabled(True)
            self._btn_ok.setStyleSheet(self._ss_on)
        else:
            self._empleado_nombre = ""
            self._lbl_sel.setText(tr("cfg.none_selected", default="Ningún empleado seleccionado"))
            self._lbl_sel.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;")
            self._btn_ok.setEnabled(False)
            self._btn_ok.setStyleSheet(self._ss_off)

    def _confirmar(self):
        if self._empleado_nombre:
            self.accept()

    def get_empleado(self) -> str:
        return self._empleado_nombre
class _IdentificacionEmpleadoDialog(QDialog):
    """Selección de empleado + verificación de PIN de 4 dígitos."""

    def __init__(self, subtitulo: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._empleado_id: int | None = None
        self._empleado_nombre: str = ""
        self._build(subtitulo)

    def _build(self, subtitulo: str):
        card = QFrame(self); card.setObjectName("ied_card")
        card.setStyleSheet(
            f"QFrame#ied_card{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}"
        )
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(32, 28, 32, 28); ly.setSpacing(14)

        lbl_t = QLabel("🔐  " + tr("cfg.id_emp_title", default="IDENTIFICACIÓN DE EMPLEADO"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_t)

        if subtitulo:
            lbl_sub = QLabel(subtitulo)
            lbl_sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
            lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_sub.setWordWrap(True)
            ly.addWidget(lbl_sub)

        def _lbl(txt):
            l = QLabel(txt)
            l.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:13px;font-weight:bold;")
            return l

        ly.addWidget(_lbl(tr("cfg.emp_label", default="Empleado:")))
        self._combo_emp = _NeonComboBox()
        self._combo_emp.addItem(tr("cfg.select_emp_combo", default="— Seleccionar empleado —"), None)
        try:
            for u in listar_usuarios():
                self._combo_emp.addItem(f"{u['nombre']}  ({tr('roles.' + str(u['perfil']).lower(), default=u['perfil']).upper()})", u["id"])
        except Exception:
            pass
        self._combo_emp.setFixedHeight(44)
        self._combo_emp.set_cover_style("#161B22", 10)
        self._combo_emp.setStyle(_get_no_arrow_style())
        self._combo_emp.setStyleSheet(
            f"QComboBox{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:10px;padding:8px 36px 8px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:#E6EDF3;border:2px solid {_CIAN};"
            f"border-radius:10px;selection-background-color:{_CIAN};selection-color:#0D1117;outline:none;}}"
            f"QComboBox QAbstractItemView::item{{height:38px;padding:0 14px;}}"
        )
        ly.addWidget(self._combo_emp)

        ly.addWidget(_lbl(tr("cfg.pin_label_4", default="PIN (4 dígitos):")))
        self._pin_inp = QLineEdit()
        self._pin_inp.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_inp.setPlaceholderText("• • • •")
        self._pin_inp.setMaxLength(4)
        self._pin_inp.setFixedHeight(52)
        self._pin_inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pin_inp.setStyleSheet(
            f"QLineEdit{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:12px;font-family:'Segoe UI';font-weight:900;font-size:22px;letter-spacing:6px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        ly.addWidget(self._pin_inp)

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:#F85149;font-family:'Segoe UI';font-size:11px;")
        self._lbl_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(self._lbl_err)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(42)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            "QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}"
        )
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.confirm", default="CONFIRMAR")); bk.setFixedHeight(42)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        bk.clicked.connect(self._verificar)
        self._pin_inp.returnPressed.connect(self._verificar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedSize(520, 380)

    def _verificar(self):
        uid = self._combo_emp.currentData()
        if uid is None:
            self._lbl_err.setText(tr("cfg.select_emp_err", default="Selecciona un empleado.")); return
        pin = self._pin_inp.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            self._lbl_err.setText(tr("cfg.pin_len_err", default="El PIN debe tener exactamente 4 dígitos.")); return
        import hashlib
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("SHOW COLUMNS FROM usuarios")
                cols = [r["Field"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
                col = "nombre" if "nombre" in cols else "usuario"
                cur.execute(
                    f"SELECT {col} FROM usuarios WHERE id=%s AND password=%s AND activo=1",
                    (uid, pin_hash)
                )
                row = cur.fetchone()
                if row:
                    self._empleado_id = uid
                    self._empleado_nombre = (row[col] if isinstance(row, dict) else row[0])
                    self.accept(); return
            self._lbl_err.setText(tr("cfg.pin_wrong_emp", default="PIN incorrecto para el empleado seleccionado."))
            self._pin_inp.clear(); self._pin_inp.setFocus()
        except Exception:
            self._lbl_err.setText(tr("cfg.pin_conn_err", default="Error de conexión con la base de datos."))

    def get_empleado_id(self) -> int | None:
        return self._empleado_id

    def get_empleado_nombre(self) -> str:
        return self._empleado_nombre


# ── Dependencias compartidas del módulo original (import diferido: runtime;
# rompe el ciclo de imports con gui/gestion_usuarios sin duplicar). ──
from src.gui.gestion_usuarios import (  # noqa: E402,F401
    _BORDE,
    _CIAN,
    _NeonComboBox,
    _get_no_arrow_style,
)
