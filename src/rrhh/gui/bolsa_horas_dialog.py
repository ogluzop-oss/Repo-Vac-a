"""
GUI de "Bolsa de horas" (RRHH Fase E) — botón por tabla semanal de Horarios. Orquestación PURA de
interfaz: toda la lógica de cálculo/persistencia vive en `src.rrhh.bolsa_horas` (CLAUDE.md: "No
lógica de negocio en la GUI"), nunca aquí.

Expone:
  - `elegir_empleado_dialog(parent, pares)`: selector de empleado (ADMINISTRADOR/SUPERADMIN).
  - `abrir_bolsa_horas(parent, id_empleado, nombre_empleado, puede_definir)`: punto de entrada
    único que muestra el popup (estado vacío o barra+4 campos) para UN empleado.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import mostrar_mensaje
from src.utils.i18n import tr

logger = logging.getLogger("rrhh.gui.bolsa_horas")

_CIAN = "#00FFC6"

_BTN_TURQUESA_SS = (
    f"QPushButton{{background:#11181D;border:2px solid {_CIAN};border-radius:10px;"
    f"color:{_CIAN};font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 18px;}}"
    f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}"
)
_BTN_CANCEL_SS = (
    "QPushButton{background:#11181D;border:1px solid #2A3A47;border-radius:8px;color:#6E7681;"
    "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 20px;}"
    f"QPushButton:hover{{background:{_CIAN};border-color:{_CIAN};color:#0E1117;}}"
)
_BTN_CONFIRM_SS = (
    f"QPushButton{{background:#11181D;border:2px solid {_CIAN};border-radius:8px;color:{_CIAN};"
    "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 20px;}"
    f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}"
)


def _card_dialog(parent) -> "tuple[QDialog, QVBoxLayout]":
    """Diálogo sin marco con la tarjeta oscura + borde cian estándar de la app (mismo patrón que
    `_AusenciaDialog` en `rrhh/gui/horarios.py`)."""
    dlg = QDialog(parent)
    dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setStyleSheet("background: transparent;")
    card = QFrame(dlg)
    card.setObjectName("bh_card")
    card.setStyleSheet(f"QFrame#bh_card{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
    root = QVBoxLayout(dlg)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(card)
    ly = QVBoxLayout(card)
    ly.setContentsMargins(28, 24, 28, 24)
    ly.setSpacing(16)
    return dlg, ly


def _titulo(texto: str) -> QLabel:
    lbl = QLabel(texto)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        "color:#E6EDF3;font-family:'Segoe UI';font-weight:bold;font-size:15px;"
        "background:transparent;border:none;"
    )
    return lbl


def elegir_empleado_dialog(parent, pares: list) -> "int | None":
    """`pares`: `[(id_empleado, label), ...]` de los empleados presentes en la tabla de Horarios
    que llamó al botón "Bolsa de horas". Se asume no vacío (el llamador comprueba y muestra su
    propio mensaje de error dedicado si no hay ninguno — ver `_HorarioSemana._on_bolsa_horas`).
    Devuelve el id elegido, o `None` si se cancela."""
    dlg, ly = _card_dialog(parent)
    dlg.setMinimumWidth(360)
    ly.addWidget(_titulo(tr("rrhh.bolsa_elegir_empleado", default="¿Bolsa de horas de qué empleado?")))

    combo = QComboBox()
    combo.setStyleSheet(
        f"QComboBox{{background:#11181D;border:2px solid {_CIAN};border-radius:8px;"
        "color:#E6EDF3;font-family:'Segoe UI';font-size:13px;padding:6px 10px;min-height:28px;}}"
    )
    for eid, label in pares:
        combo.addItem(label or "", eid)
    ly.addWidget(combo)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    btn_cancel = QPushButton(tr("cfg.cancel", default="CANCELAR"))
    btn_cancel.setFixedHeight(36)
    btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_cancel.setStyleSheet(_BTN_CANCEL_SS)
    btn_cancel.clicked.connect(dlg.reject)
    btn_ok = QPushButton(tr("cfg.confirm", default="CONFIRMAR"))
    btn_ok.setFixedHeight(36)
    btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_ok.setStyleSheet(_BTN_CONFIRM_SS)
    btn_ok.clicked.connect(dlg.accept)
    btn_row.addWidget(btn_cancel)
    btn_row.addWidget(btn_ok)
    ly.addLayout(btn_row)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        return combo.currentData()
    return None


class DefinirHorasDiariasDialog(QDialog):
    """Formulario mínimo: `horas_diarias` (DECIMAL(4,2)) de la bolsa de horas YA existente del
    empleado (creada por `rrhh.db.contratos.marcar_firmado`). Solo alcanzable para
    ADMINISTRADOR/SUPERADMIN — el gate de rol vive en `_HorarioSemana`/`BolsaHorasDialog`."""

    def __init__(self, parent, bolsa: dict):
        super().__init__(parent)
        self._bolsa = bolsa
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        card = QFrame(self)
        card.setObjectName("dhd_card")
        card.setStyleSheet(f"QFrame#dhd_card{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(16)
        ly.addWidget(_titulo(tr("rrhh.bolsa_definir_titulo", default="Horas diarias de trabajo")))

        lbl = QLabel(tr("rrhh.bolsa_definir_ayuda",
                        default="Jornada diaria pactada en la cláusula de bolsa de horas del contrato."))
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#9FB0C3;font-family:'Segoe UI';font-size:12px;background:transparent;border:none;")
        ly.addWidget(lbl)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.25, 24.0)
        self._spin.setSingleStep(0.25)
        self._spin.setDecimals(2)
        self._spin.setSuffix(" h")
        self._spin.setValue(8.0)
        self._spin.setFixedHeight(40)
        self._spin.setStyleSheet(
            f"QDoubleSpinBox{{background:#11181D;border:2px solid {_CIAN};border-radius:8px;"
            "color:#E6EDF3;font-family:'Segoe UI';font-size:14px;padding:0 10px;}}"
        )
        ly.addWidget(self._spin)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_cancel = QPushButton(tr("cfg.cancel", default="CANCELAR"))
        btn_cancel.setFixedHeight(38)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(_BTN_CANCEL_SS)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("cfg.confirm", default="CONFIRMAR"))
        btn_ok.setFixedHeight(38)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(_BTN_CONFIRM_SS)
        btn_ok.clicked.connect(self._guardar)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        ly.addLayout(btn_row)

    def _guardar(self):
        from src.rrhh import bolsa_horas as _bh
        try:
            ok = _bh.definir_horas_diarias(self._bolsa["id"], self._spin.value())
        except ValueError as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), str(exc), "error")
            return
        if ok:
            self.accept()
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("rrhh.bolsa_definir_err", default="No se pudo guardar."), "error")


class BolsaHorasDialog(QDialog):
    """Popup de "Bolsa de horas" de UN empleado. Estados:
       - Sin fila en `rrhh_bolsa_horas` -> "Este empleado no tiene bolsa de horas activa."
       - Fila sin `horas_diarias` -> "Aún no se han definido las horas diarias de trabajo." +
         botón "Definir horas diarias de trabajo del empleado" (solo si `puede_definir`).
       - Fila con `horas_diarias` -> barra de progreso + 4 campos (cálculo día a día real).
    """

    def __init__(self, parent, id_empleado: int, nombre_empleado: str, puede_definir: bool):
        super().__init__(parent)
        self._id_empleado = id_empleado
        self._nombre = nombre_empleado or ""
        self._puede_definir = puede_definir
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.setMinimumWidth(440)

        card = QFrame(self)
        card.setObjectName("bhd_card")
        card.setStyleSheet(f"QFrame#bhd_card{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)
        self._ly = QVBoxLayout(card)
        self._ly.setContentsMargins(28, 24, 28, 24)
        self._ly.setSpacing(16)

        self._ly.addWidget(_titulo(tr("rrhh.bolsa_titulo", default="Bolsa de horas — {n}", n=self._nombre)))

        self._body = QWidget()
        self._ly.addWidget(self._body)

        close_row = QHBoxLayout()
        close_row.addStretch()
        btn_close = QPushButton(tr("cfg.close", default="CERRAR"))
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(_BTN_CANCEL_SS)
        btn_close.clicked.connect(self.reject)
        close_row.addWidget(btn_close)
        self._ly.addLayout(close_row)

        self._cargar()

    def _cargar(self):
        from src.rrhh import bolsa_horas as _bh
        try:
            bolsa = _bh.obtener_bolsa_horas(self._id_empleado)
        except Exception as exc:
            logger.error("BolsaHorasDialog._cargar: %s", exc)
            bolsa = None
        if not bolsa:
            self._mostrar_vacio(
                tr("rrhh.bolsa_sin_clausula",
                   default="Este empleado no tiene bolsa de horas activa (su contrato no incluye esa cláusula)."),
                None)
            return
        if bolsa.get("horas_diarias") is None:
            self._mostrar_vacio(
                tr("rrhh.bolsa_sin_horas", default="Aún no se han definido las horas diarias de trabajo."),
                bolsa)
            return
        try:
            resultado = _bh.calcular_bolsa_horas_empleado(self._id_empleado, bolsa=bolsa)
        except Exception as exc:
            self._mostrar_vacio(
                tr("rrhh.bolsa_error", default="No se pudo calcular la bolsa de horas: {exc}", exc=exc), None)
            return
        self._mostrar_resultado(resultado)

    def _mostrar_vacio(self, mensaje: str, bolsa):
        ly = QVBoxLayout(self._body)
        ly.setSpacing(14)
        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#9FB0C3;font-family:'Segoe UI';font-size:13px;background:transparent;border:none;")
        ly.addWidget(lbl)
        if self._puede_definir and bolsa is not None:
            btn = QPushButton(tr("rrhh.bolsa_definir_btn",
                                 default="DEFINIR HORAS DIARIAS DE TRABAJO DEL EMPLEADO"))
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_BTN_TURQUESA_SS)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(btn)
            row.addStretch()
            ly.addLayout(row)
            btn.clicked.connect(lambda: self._abrir_definir(bolsa))
        self.adjustSize()

    def _abrir_definir(self, bolsa):
        dlg = DefinirHorasDiariasDialog(self, bolsa)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Las horas ya quedaron definidas: se cierra este popup — reabrir "Bolsa de horas"
            # desde la tabla vuelve a mostrar el cálculo ya con datos.
            self.accept()

    def _mostrar_resultado(self, r: dict):
        ly = QVBoxLayout(self._body)
        ly.setSpacing(14)

        esperadas = r.get("horas_esperadas") or 0.0
        trabajadas = r.get("horas_trabajadas") or 0.0
        pct = 0
        if esperadas > 0:
            pct = max(0, min(100, round(trabajadas / esperadas * 100)))
        barra = QProgressBar()
        barra.setRange(0, 100)
        barra.setValue(pct)
        barra.setTextVisible(True)
        barra.setFormat(f"{pct}%")
        barra.setFixedHeight(24)
        barra.setStyleSheet(
            "QProgressBar{background:#11181D;border:1px solid #2A3A47;border-radius:8px;"
            "color:#E6EDF3;text-align:center;font-family:'Segoe UI';font-weight:bold;}"
            f"QProgressBar::chunk{{background:{_CIAN};border-radius:8px;}}"
        )
        ly.addWidget(barra)

        campos = [
            (tr("rrhh.bolsa_esperadas", default="Horas de trabajo esperadas"),
             f"{esperadas:.2f} h"),
            (tr("rrhh.bolsa_trabajadas", default="Horas trabajadas"),
             f"{trabajadas:.2f} h"),
            (tr("rrhh.bolsa_compensar_emp", default="Horas a compensar por el empleado"),
             f"{r.get('horas_compensar_empleado', 0.0):.2f} h"),
            (tr("rrhh.bolsa_compensar_empresa", default="Horas a compensar por la empresa"),
             f"{r.get('horas_compensar_empresa', 0.0):.2f} h"),
        ]
        form = QFormLayout()
        form.setSpacing(10)
        for label_txt, val_txt in campos:
            lbl = QLabel(label_txt)
            lbl.setStyleSheet("color:#9FB0C3;font-family:'Segoe UI';font-size:12px;background:transparent;border:none;")
            val = QLabel(val_txt)
            val.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:bold;font-size:14px;background:transparent;border:none;")
            form.addRow(lbl, val)
        ly.addLayout(form)

        limite = r.get("fecha_regularizacion_limite")
        if limite:
            lbl_lim = QLabel(tr("rrhh.bolsa_regularizacion_limite",
                                default="Plazo de regularización: {f}", f=str(limite)))
            lbl_lim.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;background:transparent;border:none;")
            ly.addWidget(lbl_lim)

        self.adjustSize()


def abrir_bolsa_horas(parent, id_empleado: int, nombre_empleado: str, puede_definir: bool):
    """Punto de entrada único usado por `_HorarioSemana._on_bolsa_horas` (ver
    `rrhh/gui/horarios.py`)."""
    if not id_empleado:
        mostrar_mensaje(parent, tr("rrhh.bolsa_titulo_corto", default="Bolsa de horas"),
                        tr("rrhh.bolsa_sin_empleado", default="No se pudo identificar al empleado."),
                        "warning")
        return
    dlg = BolsaHorasDialog(parent, id_empleado, nombre_empleado, puede_definir)
    dlg.exec()
