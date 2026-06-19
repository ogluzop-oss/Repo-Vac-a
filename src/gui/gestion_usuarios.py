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

# ---------------------------------------------------------------------------
# CONSTANTES DE ESTILO
# ---------------------------------------------------------------------------
_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"

# Constants from ventas.py for calendar consistency
_VENTAS_BG = "#0E1117"
_VENTAS_SIDEBAR = "#111418"
_VENTAS_TEXTO = "#E6EDF3"
_BORDE = "#30363D"

_EVENTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "eventos_citas.json")
_LOGO_PATH   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "logo_corporativo.png"))
_CAJA_STATE_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "estado_caja.json"))

# (emoji, color) por estado; el texto se traduce vía _ESTADO_TXT_KEY.
_ESTADOS_CAJA = {
    "SIN_APERTURA":         ("🔒", "#6E7681"),
    "CAJA_FUERTE_ABIERTA":  ("🟡", "#E3B341"),
    "PRIMERA_CAJA_ABIERTA": ("🟢", "#3FB950"),
    "OPERATIVA":            ("✅", "#00FFC6"),
    "CIERRE_CAJAS":         ("🔶", "#F0883E"),
    "CIERRE_COMPLETADO":    ("🏁", "#58A6FF"),
}
_ESTADO_TXT_KEY = {
    "SIN_APERTURA":         ("cfg.estado_sin_apertura",      "SIN APERTURA"),
    "CAJA_FUERTE_ABIERTA":  ("cfg.estado_caja_fuerte",       "CAJA FUERTE ABIERTA"),
    "PRIMERA_CAJA_ABIERTA": ("cfg.estado_primera_caja",      "PRIMERA CAJA ACTIVA"),
    "OPERATIVA":            ("cfg.estado_operativa",         "SISTEMA OPERATIVO"),
    "CIERRE_CAJAS":         ("cfg.estado_cierre_cajas",      "CIERRE DE CAJAS EN CURSO"),
    "CIERRE_COMPLETADO":    ("cfg.estado_cierre_completado", "LISTO PARA CIERRE FUERTE"),
}


# ─── Horario Empleados ────────────────────────────────────────────────────────
_H_DAYS_LG = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]


def _dias_lg():
    """Nombres de día (lunes-domingo) traducidos al idioma activo."""
    return [tr("common.day_%d" % i, default=_H_DAYS_LG[i - 1]) for i in range(1, 8)]


# ── Wizard fiscal: traducción automática de etiquetas/placeholders de formulario ──
# Cubre las ~150 etiquetas de los 13 formularios _p2_* sin tocar cada llamada:
# los helpers _lbl_s/_mk_inp/_sep_lbl pasan su texto por _wz_tr(). Las opciones de
# combo y las cláusulas legales NO pasan por aquí (son valores lógicos / contenido).
_WZ_TR_EN = {
    # — p1 trabajador / fiscal —
    "Nombre completo:": "Full name:", "Nombre y apellidos del trabajador": "Worker full name",
    "NIF / NIE:": "NIF / NIE:", "Identificación fiscal": "Tax ID",
    "Fecha de nacimiento:": "Date of birth:", "DD/MM/AAAA": "DD/MM/YYYY",
    "Nº Seguridad Social:": "Social Security No.:", "Número de afiliación": "Affiliation number",
    "Nacionalidad:": "Nationality:", "Ej: ESPAÑOLA": "e.g. SPANISH",
    "Categoría profesional / Puesto:": "Professional category / Position:",
    "Ej: Vendedor/a, Cajero/a, Responsable…": "e.g. Salesperson, Cashier, Manager…",
    "Nivel formativo:": "Education level:", "Ej: ESO, Bachillerato, FP, Grado…": "e.g. Secondary, Baccalaureate, VET, Degree…",
    "Municipio de domicilio:": "Town of residence:", "Ciudad de residencia": "City of residence",
    "Razón social:": "Legal name:", "Nombre legal de la empresa": "Legal name of the company",
    "CIF / NIF:": "VAT ID:", "Ej: B12345678": "e.g. B12345678",
    "Dirección fiscal:": "Tax address:", "Calle, número, ciudad": "Street, number, city",
    "Fecha inicio (DD/MM/AAAA):": "Start date (DD/MM/YYYY):", "Fecha fin (DD/MM/AAAA):": "End date (DD/MM/YYYY):",
    "Observaciones / Notas adicionales:": "Remarks / Additional notes:", "Información adicional relevante...": "Relevant additional information...",
    "Fecha de efecto (DD/MM/AAAA):": "Effective date (DD/MM/YYYY):",
    # — separadores —
    "PUESTO DE TRABAJO": "JOB POSITION", "RETRIBUCIÓN Y CONTRATO": "PAY & CONTRACT",
    "CLÁUSULAS ADICIONALES (ANEXO)": "ADDITIONAL CLAUSES (ANNEX)", "DEVENGOS": "EARNINGS",
    "DEDUCCIONES": "DEDUCTIONS", "PRECEDENTES": "PRECEDENTS", "LIQUIDACIÓN": "SETTLEMENT",
    "CONCEPTOS A LIQUIDAR": "ITEMS TO SETTLE", "IMPORTES": "AMOUNTS",
    "TOTALES DEL PERÍODO": "PERIOD TOTALS", "PROVEEDOR PRINCIPAL": "MAIN SUPPLIER",
    "EMPRESA EMISORA": "ISSUING COMPANY", "PERÍODO": "PERIOD",
    # — CONTRATO —
    "Modalidad de contrato:": "Contract type:", "Fecha de inicio:": "Start date:", "Fecha de fin:": "End date:",
    "Puesto / Cargo:": "Position / Role:", "Ej: Colaborador Tienda, Cajero/a…": "e.g. Store Associate, Cashier…",
    "Grupo profesional:": "Professional group:", "Ej: Grupo 4, Vendedor 2º": "e.g. Group 4, Salesperson 2nd",
    "Funciones principales:": "Main duties:", "Descripción breve de las funciones": "Brief description of duties",
    "Centro de trabajo (dirección):": "Workplace (address):", "Calle, nº, localidad": "Street, no., town",
    "Trabajo a distancia:": "Remote work:", "Tipo de jornada:": "Working-hours type:",
    "Horas semanales:": "Weekly hours:", "Ej: 40 / 20": "e.g. 40 / 20",
    "Distribución horaria:": "Hours distribution:", "Ej: LUNES A DOMINGO": "e.g. MONDAY TO SUNDAY",
    "Salario bruto anual (€):": "Gross annual salary (€):", "Ej: 18000.00": "e.g. 18000.00",
    "Nº de pagas:": "No. of payments:", "Período de prueba:": "Probation period:", "Ej: TRES MESES": "e.g. THREE MONTHS",
    "Vacaciones:": "Holidays:", "Ej: Según Convenio / 23 días hábiles": "e.g. As per agreement / 23 working days",
    "Convenio colectivo aplicable:": "Applicable collective agreement:",
    "Ej: Convenio Colectivo del Comercio Textil de Barcelona": "e.g. Collective Agreement of the Textile Trade of Barcelona",
    # — NÓMINA —
    "Mes/período nómina (DD/MM/AAAA):": "Payslip month/period (DD/MM/YYYY):",
    "Salario base mensual (€):": "Monthly base salary (€):", "Ej: 1200.00": "e.g. 1200.00",
    "Plus transporte (€):": "Transport allowance (€):", "Ej: 50.00": "e.g. 50.00",
    "Plus convenio (€):": "Agreement allowance (€):", "Ej: 30.00": "e.g. 30.00",
    "Nocturnidad (€):": "Night-shift pay (€):", "Ej: 0.00": "e.g. 0.00",
    "Horas extra (€):": "Overtime (€):", "Incentivos / Bonus (€):": "Incentives / Bonus (€):",
    "Dietas (€):": "Per diems (€):", "IRPF (%):": "Income tax (%):", "Ej: 15.00": "e.g. 15.00",
    "SS trabajador (%):": "Employee SS (%):", "Ej: 6.35": "e.g. 6.35",
    "Anticipos (€):": "Advances (€):", "Embargos (€):": "Garnishments (€):",
    # — ALTA —
    "Fecha de alta:": "Registration date:", "Tipo de contrato:": "Contract type:",
    "Horario de trabajo:": "Work schedule:", "Ej: L-V 09:00-17:00": "e.g. Mon-Fri 09:00-17:00",
    "Categoría profesional:": "Professional category:", "Ej: Técnico, Auxiliar…": "e.g. Technician, Assistant…",
    "Convenio colectivo:": "Collective agreement:", "Convenio aplicable": "Applicable agreement",
    "Centro de trabajo:": "Workplace:", "Dirección del centro": "Workplace address",
    "Cuenta bancaria IBAN:": "Bank account IBAN:",
    # — BAJA —
    "Tipo de baja:": "Termination type:", "Fecha de efecto de la baja:": "Termination effective date:",
    "Motivo (descripción):": "Reason (description):", "Descripción del motivo": "Description of the reason",
    "Vacaciones pendientes (días):": "Pending holidays (days):", "Ej: 5": "e.g. 5",
    "Entrega de material empresa:": "Return of company equipment:",
    # — CERTIFICADO —
    "Tipo de certificado:": "Certificate type:", "Fecha de emisión:": "Issue date:",
    "Fecha inicio relación laboral:": "Employment start date:", "Fecha fin relación laboral:": "Employment end date:",
    "DD/MM/AAAA o EN ACTIVO": "DD/MM/YYYY or ACTIVE", "Grupo de cotización:": "Contribution group:", "Ej: Grupo 5": "e.g. Group 5",
    "Base cotización (€/mes):": "Contribution base (€/month):", "Ej: 1500.00": "e.g. 1500.00",
    "Base desempleo (€/mes):": "Unemployment base (€/month):", "Ej: 0": "e.g. 0",
    "Pagas extras pendientes:": "Pending extra payments:",
    # — CERT LABORAL —
    "Cargo / Puesto actual:": "Current role / position:", "Ej: Responsable de Tienda": "e.g. Store Manager",
    "Antigüedad (desde DD/MM/AAAA):": "Seniority (since DD/MM/YYYY):", "Fecha de incorporación": "Joining date",
    "Descripción de las funciones": "Description of duties",
    # — CARTA DESPIDO —
    "Tipo de despido:": "Dismissal type:", "Fecha de comunicación:": "Notice date:", "Fecha de efecto:": "Effective date:",
    "Artículo del ET invocado:": "Workers' Statute article invoked:",
    "Ej: Art. 54 ET (disciplinario) / Art. 52 ET (objetivo)": "e.g. Art. 54 WS (disciplinary) / Art. 52 WS (objective)",
    "Descripción de los hechos:": "Description of the facts:", "Descripción detallada de los hechos imputados…": "Detailed description of the alleged facts…",
    "Advertencias previas:": "Prior warnings:", "Expedientes disciplinarios previos:": "Prior disciplinary records:",
    "Indemnización (€):": "Severance (€):",
    # — FINIQUITO —
    "Salario bruto mensual (€):": "Gross monthly salary (€):", "Días trabajados pendientes:": "Pending worked days:", "Ej: 10": "e.g. 10",
    "Horas extra pendientes (€):": "Pending overtime (€):", "Anticipos descontados (€):": "Advances deducted (€):",
    "Fecha de baja:": "Termination date:",
    # — VACACIONES —
    "Tipo de documento:": "Document type:", "Fecha de inicio (DD/MM/AAAA):": "Start date (DD/MM/YYYY):",
    "Fecha de fin (DD/MM/AAAA):": "End date (DD/MM/YYYY):", "Responsable / Aprobado por:": "Manager / Approved by:",
    "Nombre del responsable que aprueba/deniega": "Name of the manager who approves/denies",
    "Motivo de rechazo (solo si DENEGACIÓN):": "Rejection reason (only if DENIAL):", "Dejar vacío si no aplica": "Leave blank if not applicable",
    # — RESUMEN FISCAL —
    "Período:": "Period:", "Trimestre (1-4) o Año:": "Quarter (1-4) or Year:", "Ej: 1 / 2025": "e.g. 1 / 2025",
    "Ejercicio fiscal:": "Tax year:", "Total ingresos (€):": "Total income (€):", "Ej: 10000.00": "e.g. 10000.00",
    "IVA repercutido (€):": "Output VAT (€):", "Ej: 2100.00": "e.g. 2100.00",
    "IVA soportado (€):": "Input VAT (€):", "Ej: 800.00": "e.g. 800.00",
    "Gastos deducibles (€):": "Deductible expenses (€):", "Ej: 500.00": "e.g. 500.00",
    # — LIBRO INGRESOS —
    "Fecha inicio:": "Start date:", "Fecha fin:": "End date:",
    "Facturas emitidas (nº):": "Issued invoices (no.):", "Ej: 25": "e.g. 25",
    "Nº de clientes:": "No. of customers:", "Ej: 12": "e.g. 12",
    "Importe total s/IVA (€):": "Total amount excl. VAT (€):", "Ej: 15000.00": "e.g. 15000.00",
    "IVA repercutido total (€):": "Total output VAT (€):", "Ej: 3150.00": "e.g. 3150.00",
    # — LIBRO GASTOS —
    "Proveedor:": "Supplier:", "Nombre o razón social del proveedor": "Supplier name or legal name",
    "CIF proveedor:": "Supplier VAT ID:", "Ej: B87654321": "e.g. B87654321",
    "Fecha factura:": "Invoice date:", "Concepto:": "Item:", "Descripción del gasto": "Expense description",
    "Importe s/IVA (€):": "Amount excl. VAT (€):", "Ej: 1000.00": "e.g. 1000.00", "Ej: 210.00": "e.g. 210.00",
    # — INFORME AUDIT —
    "Tipo de informe:": "Report type:", "Empleados incluidos en el filtro (vacío = todos):": "Employees included in the filter (empty = all):",
    "Nombre/s o NIF separados por coma": "Name(s) or NIF separated by comma",
    # — genérico —
    "Subtipo / Modalidad:": "Subtype / Modality:",
}


def _wz_tr(txt):
    """Traduce una etiqueta de formulario del wizard al idioma activo (es→en) y
    sustituye el símbolo de divisa (€) por el de la divisa de empresa activa, de
    modo que TODAS las etiquetas de importe (nóminas, fiscal, contratos…) quedan
    en la divisa correcta sin tocar cada cadena."""
    if not txt:
        return txt
    out = txt if i18n.current_language() == "es" else _WZ_TR_EN.get(txt, txt)
    try:
        sym = divisas.simbolo()
        if sym != "€" and "€" in out:
            out = out.replace("€", sym)
    except Exception:
        pass
    return out
# Column layout per day: J. INICIO | J. FIN | TOTAL H.
_H_COL_INI = 155   # px — J. INICIO comboboxes column
_H_COL_FIN = 155   # px — J. FIN comboboxes column
_H_COL_TOT = 125   # px — TOTAL HORAS label column

# Stylesheet applied per-combobox (batch, after all setCellWidget calls).
# background:transparent lets the parent _TurnoCelda container color show through
# (vacaciones yellow, baja red, or alternating row background).
_TURNO_CB_SS = (
    "QComboBox{background:transparent;color:#E6EDF3;"
    "border:2px solid #00FFC6;border-radius:8px;"
    "padding:2px 4px;min-height:26px;padding-right:4px;"
    "font-family:'Segoe UI';font-size:11px;font-weight:900;}"
    "QComboBox:hover{background:transparent;color:#00FFC6;border:2px solid #00FFC6;}"
    "QComboBox:disabled{color:#555555;border:2px solid #30363D;}"
    "QComboBox::drop-down{width:0px;border:none;}"
    "QComboBox::down-arrow{image:none;width:0px;height:0px;border:none;margin:0px;}"
    # Popup view and scrollbar are styled directly on the view widget in _fix_popup()
    # so that the combobox-propagated rule does not create a double border at the top.
)

# Common input style for neon effect
_NEON_INPUT_STYLE = f"""
    QLineEdit, QComboBox, QSpinBox, QTextEdit, QTimeEdit {{
        background-color: #161B22;
        color: #FFFFFF;
        border: 2px solid {_CIAN};
        border-radius: 12px;
        padding: 12px 20px;
        font-size: 16px;
        font-family: 'Segoe UI';
        font-weight: bold;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QTimeEdit:focus {{
        border: 2px solid {_CIAN};
        background-color: #1A2230;
    }}
"""

_NEON_BUTTON_STYLE = f"""
    QPushButton {{
        background-color: #0E1117;
        color: {_CIAN};
        font-weight: bold;
        border-radius: 14px;
        padding: 15px 30px;
        font-size: 14px;
        font-family: 'Segoe UI';
        border: 2px solid {_CIAN};
    }}
    QPushButton:hover {{
        background-color: {_CIAN};
        color: #0E1117;
        border: 2px solid {_CIAN};
    }}
"""


class _SidebarBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("btn_sidebar")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(55)  # Altura estándar
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: white; border: none;
                border-left: 4px solid transparent;
                border-radius: 0px; /* Esquinas puntiagudas */
                text-align: left; padding-left: 28px; font-family: 'Segoe UI'; font-weight: 900; font-size: 12px;
            }}
            QPushButton:checked {{
                background-color: #1A2230; border-left: 4px solid {_CIAN}; color: {_CIAN};
                border-radius: 0px;
            }}
            QPushButton:hover {{ background-color: #ffffff; color: #0E1117; }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Copied/Adapted Helper classes from ventas.py for calendar and combobox styling
# ─────────────────────────────────────────────────────────────────────────────


class _PopupBorderOverlay(QWidget):
    """Capa transparente sobre el popup del calendario para dibujar el borde neón."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(_CIAN), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class _NeonCalFrame(QFrame):
    """Ventana popup con fondo #11181D y borde neón."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background: {_VENTAS_SIDEBAR}; border: none;")

    def showEvent(self, event):
        super().showEvent(event)
        sz = self.size()
        if sz.width() > 0 and sz.height() > 0:
            bmp = QBitmap(sz)
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, sz.width(), sz.height(), 14, 14)
            p.end()
            self.setMask(bmp)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(_VENTAS_SIDEBAR))
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(_CIAN), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class _VentasCalendarWidget(QCalendarWidget):
    """Calendario propio de ventas con navegación controlada por la app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._month_btn = None
        self._year_btn = None
        self._month_popup = None
        self._year_popup = None
        self._nav_ready = False
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        self.setStyleSheet(f"""
            QCalendarWidget {{
                background: {_VENTAS_SIDEBAR};
                border: none;
            }}
            QCalendarWidget QWidget {{
                background: {_VENTAS_SIDEBAR};
                alternate-background-color: {_VENTAS_SIDEBAR};
                border: none;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: {_VENTAS_SIDEBAR};
                border: none;
                min-height: 42px;
            }}
            QCalendarWidget QTableView {{
                background: {_VENTAS_SIDEBAR};
                border: none;
                outline: none;
                gridline-color: transparent;
                selection-background-color: {_CIAN};
                selection-color: {_VENTAS_BG};
            }}
            QCalendarWidget QHeaderView::section {{
                background: {_VENTAS_SIDEBAR};
                color: {_CIAN};
                border: none;
                padding: 2px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: 900;
            }}
            QCalendarWidget QAbstractItemView {{
                background: {_VENTAS_SIDEBAR};
                color: {_VENTAS_TEXTO};
                border: none;
                outline: none;
                selection-background-color: {_CIAN};
                selection-color: {_VENTAS_BG};
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 900;
            }}
            QCalendarWidget QAbstractItemView:disabled {{
                color: #4B5563;
            }}
            QCalendarWidget QToolButton#qt_calendar_yearbutton,
            QCalendarWidget QSpinBox#qt_calendar_yearedit,
            QCalendarWidget QWidget#qt_calendar_yearselector {{
                max-width: 0px; max-height: 0px;
                min-width: 0px; min-height: 0px;
                border: none; background: transparent;
                color: transparent; padding: 0px; margin: 0px;
            }}
            """)
        self.setMinimumSize(318, 258)
        self._eventos_ref = {}
        self.currentPageChanged.connect(lambda _y, _m: self._sync_nav_texts())

    def set_events(self, eventos_dict):
        self._eventos_ref = eventos_dict
        self.update()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        evs = self._eventos_ref.get(date.toString("yyyy-MM-dd"))
        if evs:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            flag_color = QColor("#F85149")
            black = QColor("#000000")
            cx = rect.center().x()
            mast_bottom = float(rect.bottom() - 2)
            mast_top = mast_bottom - 14.0
            mast_x = float(cx - 3)
            flag_w = 10.0
            flag_h = 8.0

            # Mast as thin rectangle
            mast_path = QPainterPath()
            mast_path.addRect(mast_x - 1.0, mast_top, 2.0, mast_bottom - mast_top)

            # Flag triangle
            tri_path = QPainterPath()
            tri_path.moveTo(mast_x, mast_top)
            tri_path.lineTo(mast_x + flag_w, mast_top + flag_h / 2)
            tri_path.lineTo(mast_x, mast_top + flag_h)
            tri_path.closeSubpath()

            # Single unified shape → single black outline + red fill
            unified = mast_path.united(tri_path)
            painter.setPen(QPen(black, 1.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(flag_color)
            painter.drawPath(unified)

            # Count badge if more than 1 event
            count = len(evs)
            if count > 1:
                badge_r = 5
                bx = rect.right() - badge_r - 1
                by = rect.bottom() - badge_r - 1
                painter.setBrush(QColor("#F85149"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(bx - badge_r), int(by - badge_r), badge_r * 2, badge_r * 2)
                painter.setPen(QColor("white"))
                font = QFont("Segoe UI", 5, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(
                    QRect(int(bx - badge_r), int(by - badge_r), badge_r * 2, badge_r * 2),
                    Qt.AlignmentFlag.AlignCenter,
                    str(count),
                )
            painter.restore()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_custom_nav()
        QTimer.singleShot(0, self._style_popup)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_custom_nav()

    def _style_popup(self):
        """Aplica máscara redondeada y borde neón al popup que contiene el calendario."""
        try:
            popup = self.window()
            # Only style when the calendar lives inside a _NeonCalFrame popup.
            # When embedded in the main window, bail immediately — otherwise
            # setMask() is called on the main window, which causes a heavy OS
            # window-region update on every tab switch and freezes the UI.
            if not isinstance(popup, _NeonCalFrame):
                return
            sz = popup.size()
            if sz.width() <= 0 or sz.height() <= 0:
                return
            bmp = QBitmap(sz)
            bmp.fill(Qt.GlobalColor.color0)
            pa = QPainter(bmp)
            pa.setBrush(Qt.GlobalColor.color1)
            pa.setPen(Qt.PenStyle.NoPen)
            pa.drawRoundedRect(0, 0, sz.width(), sz.height(), 14, 14)
            pa.end()
            popup.setMask(QRegion(bmp))
            overlay = getattr(self, "_popup_overlay", None)
            if (
                overlay is None
                or not isinstance(overlay, _PopupBorderOverlay)
                or overlay.parent() is not popup
            ):
                overlay = _PopupBorderOverlay(popup)
                overlay.setGeometry(popup.rect())
                self._popup_overlay = overlay
                overlay.show()
            overlay.raise_()
        except Exception:
            pass

    def _ensure_custom_nav(self):
        if self._nav_ready:
            return True
        nav = self.findChild(QWidget, "qt_calendar_navigationbar")
        prev_btn = self.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = self.findChild(QToolButton, "qt_calendar_nextmonth")
        month_btn_orig = self.findChild(QToolButton, "qt_calendar_monthbutton")
        year_spin = self.findChild(QSpinBox, "qt_calendar_yearedit")
        if not nav or not prev_btn or not next_btn or not month_btn_orig:
            return False

        arrow_ss = f"""
            QToolButton {{
                color: {_CIAN};
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 20px;
                font-weight: 900;
                border: none;
                border-radius: 8px;
                padding: 0px 8px 4px 8px;
                min-width: 30px;
                min-height: 34px;
            }}
            QToolButton:hover {{
                background: rgba(0,255,198,0.15);
                color: {_CIAN};
            }}
        """
        prev_btn.setText("←")
        next_btn.setText("→")
        for btn in (prev_btn, next_btn):
            btn.setIcon(QIcon())
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setStyleSheet(arrow_ss)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        nav_ss = f"""
            QToolButton {{
                color: {_CIAN};
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 900;
                border: none;
                border-radius: 8px;
                padding: 4px 10px;
                min-height: 34px;
            }}
            QToolButton:hover {{
                background: rgba(0,255,198,0.15);
                color: {_CIAN};
            }}
            """

        # Ocultar widgets nativos
        month_btn_orig.setMaximumSize(0, 0)
        month_btn_orig.hide()
        if year_spin:
            year_spin.setMaximumSize(0, 0)
            year_spin.hide()

        # Centrar: prev ya esta en el layout nativo, insertar stretch + month + year + stretch
        layout = nav.layout()
        prev_idx = layout.indexOf(prev_btn)
        next_idx = layout.indexOf(next_btn)

        if self._month_btn is None:
            self._month_btn = QToolButton(nav)
            self._month_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._month_btn.setStyleSheet(nav_ss)
            self._month_btn.clicked.connect(self._open_month_popup)

        if self._year_btn is None:
            self._year_btn = QToolButton(nav)
            self._year_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._year_btn.setStyleSheet(nav_ss)
            self._year_btn.clicked.connect(self._open_year_popup)

        insert_at = prev_idx + 1 if prev_idx >= 0 else 1
        layout.insertStretch(insert_at, 1)
        layout.insertWidget(insert_at + 1, self._month_btn)
        layout.insertWidget(insert_at + 2, self._year_btn)
        layout.insertStretch(insert_at + 3, 1)

        self._sync_nav_texts()
        self._nav_ready = True
        return True

    def _sync_nav_texts(self):
        meses = [
            "",
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ]
        if self._month_btn is not None:
            self._month_btn.setText(f"{meses[self.monthShown()]} ▼")
        if self._year_btn is not None:
            self._year_btn.setText(f"{self.yearShown()} ▼")

    def _close_popup(self, attr_name):
        popup = getattr(self, attr_name, None)
        if popup is not None:
            try:
                popup.close()
            except Exception:
                pass
            setattr(self, attr_name, None)

    def _open_month_popup(self):
        self._close_popup("_year_popup")
        self._close_popup("_month_popup")
        if self._month_btn:
            self._month_btn.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
            self._month_btn.setDown(False)
            self._month_btn.repaint()

        popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setStyleSheet("background: transparent; border: none;")

        inner = QFrame(popup)
        inner.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL_BG};
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
            QPushButton {{
                background: {_PANEL_BG};
                color: {_VENTAS_TEXTO};
                border: none;
                border-radius: 10px;
                padding: 8px 6px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 900;
                min-width: 84px;
                min-height: 34px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: {_VENTAS_BG};
            }}
            """)

        grid = QGridLayout(inner)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        meses = [
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ]
        for i, mes in enumerate(meses):
            row, col = divmod(i, 4)
            btn = QPushButton(mes)
            if self.monthShown() == i + 1:
                btn.setStyleSheet(
                    f"background: {_CIAN}; color: {_VENTAS_BG}; border: none; font-weight: 900;"
                )
            month_number = i + 1
            btn.clicked.connect(
                lambda _checked=False, mo=month_number: (
                    self.setCurrentPage(self.yearShown(), mo),
                    self._close_popup("_month_popup"),
                )
            )
            grid.addWidget(btn, row, col)

        outer = QVBoxLayout(popup)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(inner)
        popup.setFixedSize(inner.sizeHint().width(), inner.sizeHint().height())
        popup.move(self._month_btn.mapToGlobal(self._month_btn.rect().bottomLeft()))
        popup.show()
        popup.raise_()
        self._month_popup = popup

    def _open_year_popup(self):
        self._close_popup("_month_popup")
        self._close_popup("_year_popup")
        if self._year_btn:
            self._year_btn.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
            self._year_btn.setDown(False)
            self._year_btn.repaint()

        popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setStyleSheet("background: transparent; border: none;")

        inner = QFrame(popup)
        inner.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL_BG};
                border: 2px solid {_CIAN};
                border-radius: 12px;
            }}
            QListWidget {{
                background: {_PANEL_BG};
                border: none;
                outline: none;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: 900;
            }}
            QListWidget::item {{
                color: {_VENTAS_TEXTO};
                padding: 7px 10px;
                border-radius: 8px;
                min-height: 24px;
            }}
            QListWidget::item:hover {{
                background: {_CIAN};
                color: {_VENTAS_BG};
            }}
            QListWidget::item:selected {{
                background: {_CIAN};
                color: {_VENTAS_BG};
            }}
            """)

        list_w = QListWidget(inner)
        list_w.setUniformItemSizes(True)
        list_w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        current_year = datetime.now().year
        years = list(range(current_year + 50, current_year - 6, -1))
        shown_year = self.yearShown()
        scroll_to_idx = 0
        bold_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        norm_font = QFont("Segoe UI", 11)

        for i, year in enumerate(years):
            item = QListWidgetItem(str(year))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if year == shown_year:
                item.setForeground(QColor(_CIAN))
                item.setFont(bold_font)
                scroll_to_idx = i
            else:
                item.setFont(norm_font)
            list_w.addItem(item)

        list_w.itemClicked.connect(
            lambda item: (
                self.setCurrentPage(int(item.text()), self.monthShown()),
                self._close_popup("_year_popup"),
            )
        )
        list_w.setFixedWidth(112)
        list_w.setFixedHeight(7 * 34)

        inner_ly = QVBoxLayout(inner)
        inner_ly.setContentsMargins(6, 6, 6, 6)
        inner_ly.addWidget(list_w)

        outer_ly = QVBoxLayout(popup)
        outer_ly.setContentsMargins(0, 0, 0, 0)
        outer_ly.setSpacing(0)
        outer_ly.addWidget(inner)
        popup.setFixedSize(inner.sizeHint().width(), inner.sizeHint().height())
        popup.move(self._year_btn.mapToGlobal(self._year_btn.rect().bottomLeft()))
        popup.show()
        popup.raise_()
        self._year_popup = popup

        QTimer.singleShot(
            0,
            lambda: list_w.scrollToItem(
                list_w.item(scroll_to_idx),
                QAbstractItemView.ScrollHint.PositionAtCenter,
            ),
        )


class _RoundedItemDelegate(QStyledItemDelegate):
    """Delegate that paints combo-box popup items with rounded corners."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_sel   = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        rect = QRectF(option.rect).adjusted(4, 2, -4, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)

        if is_sel:
            painter.fillPath(path, QColor(_CIAN))
        elif is_hover:
            painter.fillPath(path, QColor(0, 255, 198, 30))

        txt_color = QColor("#0D1117") if is_sel else (QColor(_CIAN) if is_hover else QColor("#E6EDF3"))
        painter.setPen(txt_color)
        f = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(f)
        painter.drawText(
            option.rect.adjusted(14, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data() or "",
        )
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(38)
        return sh


class _NeonComboBox(QComboBox):
    """QComboBox que delega TODO el estilado al sistema global: la flecha la
    provee el QSS global (PNG triangular cian, idéntico al de referencia) y el
    popup lo estiliza el filtro global (contorno lineal limpio), igual que el
    resto de desplegables de la app.

    Antes pintaba su propio cover+triángulo+borde y reposicionaba/mascaraba el
    popup a mano, lo que en Windows producía: dos diseños distintos (antes de
    abrir vs tras cerrar) y un pequeño corte en las esquinas superiores del
    popup. Delegar al estilado global elimina ambos artefactos."""

    def setStyle(self, style):
        # Ignorar el estilo "sin flecha": colapsaba el indicador y ocultaba la
        # flecha PNG del QSS global, que es justo la que queremos mostrar.
        if isinstance(style, _NoArrowComboStyle):
            return
        super().setStyle(style)

    def set_cover_style(self, color_hex, radius):
        # No-op (se mantiene por compatibilidad con las llamadas existentes):
        # la flecha la provee ahora el QSS global, no un cover pintado.
        pass


class _NeonCheckBox(QCheckBox):
    """QCheckBox con tick neón dibujado a mano en lugar de cuadrado relleno."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont("Segoe UI")
        font.setPointSize(9)
        font.setBold(True)
        self.setFont(font)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "QCheckBox { color: transparent; spacing: 0px; }"
            "QCheckBox::indicator { width: 0px; height: 0px; }"
        )

    def sizeHint(self):
        fm = self.fontMetrics()
        tw = fm.horizontalAdvance(self.text())
        h = max(22, fm.height() + 6)
        return QSize(16 + 8 + tw + 6, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        box_y = (self.height() - 16) // 2
        box = QRect(0, box_y, 16, 16)

        border_col = QColor(_CIAN) if (self._hovered or self.isChecked()) else QColor(_BORDE)
        pen = QPen(border_col, 2, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 3, 3)

        if self.isChecked():
            tick_pen = QPen(QColor(_CIAN), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(tick_pen)
            x0, y0 = box.left() + 3,  box.top() + 9
            x1, y1 = box.left() + 6,  box.top() + 13
            x2, y2 = box.left() + 13, box.top() + 4
            p.drawLine(x0, y0, x1, y1)
            p.drawLine(x1, y1, x2, y2)

        p.setFont(self.font())
        p.setPen(QPen(QColor("#E6EDF3")))
        text_rect = QRect(24, 0, self.width() - 24, self.height())
        p.drawText(text_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text())
        p.end()


class _NeonSymbolButton(QPushButton):
    """Botón que dibuja los símbolos + o - con trazos de neón reales."""

    def __init__(self, symbol, parent=None):
        super().__init__("", parent)
        self.symbol = symbol
        self.setFixedSize(55, 55)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)  # Dibuja fondo y bordes definidos en el CSS
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Color del trazo: si está hover, el fondo es cian y el trazo debe ser oscuro
        color = QColor(_CIAN)
        if self.underMouse():
            color = QColor("#0E1117")

        pen = QPen(color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)

        w, h = self.width(), self.height()
        m = 18  # Margen interno para el dibujo

        if self.symbol == "+":
            p.drawLine(m, h // 2, w - m, h // 2)
            p.drawLine(w // 2, m, w // 2, h - m)
        else:  # "-"
            p.drawLine(m, h // 2, w - m, h // 2)


class _NoArrowComboStyle(QProxyStyle):
    """Fusion-based style that collapses the drop-down indicator to zero width."""

    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def pixelMetric(self, metric, opt=None, widget=None):
        from PyQt6.QtWidgets import QStyle

        if metric == QStyle.PixelMetric.PM_MenuButtonIndicator:
            return 0
        return super().pixelMetric(metric, opt, widget)

    def subControlRect(self, cc, opt, sc, widget=None):
        from PyQt6.QtWidgets import QStyle

        if (
            cc == QStyle.ComplexControl.CC_ComboBox
            and sc == QStyle.SubControl.SC_ComboBoxArrow
        ):
            return QRect()
        return super().subControlRect(cc, opt, sc, widget)

    def drawPrimitive(self, elem, opt, p, widget=None):
        from PyQt6.QtWidgets import QStyle

        if elem in (
            QStyle.PrimitiveElement.PE_IndicatorArrowDown,
            QStyle.PrimitiveElement.PE_IndicatorButtonDropDown,
            QStyle.PrimitiveElement.PE_FrameFocusRect,
        ):
            return
        super().drawPrimitive(elem, opt, p, widget)


# Global variable for _NoArrowComboStyle instance
_no_arrow_style: Optional["_NoArrowComboStyle"] = None


def _get_no_arrow_style() -> "_NoArrowComboStyle":
    global _no_arrow_style
    if _no_arrow_style is None:
        _no_arrow_style = _NoArrowComboStyle()
    return _no_arrow_style


class _DropdownBtn(QPushButton):
    """QPushButton that paints value+arrow directly — no child widgets, no paint artifacts."""

    def __init__(self, show_arrow=True, font_size=10, parent=None):
        super().__init__(parent)
        self._show_arrow = show_arrow
        self._font_size = font_size
        self._display_text = ""
        self.setText("")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 10px;
            }}
            QPushButton:hover {{
                background-color: #161B22;
            }}
        """)

    def set_display_text(self, text):
        self._display_text = text
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", self._font_size, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        if self._show_arrow:
            painter.drawText(
                self.rect().adjusted(16, 0, -40, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._display_text,
            )
            painter.setPen(QColor(_CIAN))
            painter.drawText(
                self.rect().adjusted(0, 0, -16, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "▼",
            )
        else:
            painter.drawText(
                self.rect().adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignCenter,
                self._display_text,
            )
        painter.end()


class _PerfilDropdown(QWidget):
    """Collapsed dropdown; click to open a list-style popup with the profile options."""

    currentTextChanged = pyqtSignal(str)

    def __init__(self, opciones, parent=None):
        super().__init__(parent)
        self._opciones = opciones
        self._valor = opciones[0] if opciones else ""
        self._popup = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        self._btn = _DropdownBtn()
        self._btn.clicked.connect(self._toggle_popup)
        self._refresh_btn()
        ly.addWidget(self._btn)

    def _refresh_btn(self):
        self._btn.set_display_text(self._valor)

    def currentText(self):
        return self._valor

    def _toggle_popup(self):
        # El popup es Qt.Popup: al hacer clic en el botón estando abierto, Qt lo
        # auto-cierra (en el press) y el clicked (en el release) lo reabría. Con
        # el flag _suppress_reopen, ese segundo clic NO reabre → actúa como cierre.
        if getattr(self, "_suppress_reopen", False):
            return
        self._show_popup()

    def eventFilter(self, obj, event):
        if (obj is self._popup and event is not None
                and event.type() == QEvent.Type.Close):
            self._suppress_reopen = True
            QTimer.singleShot(250, lambda: setattr(self, "_suppress_reopen", False))
        return super().eventFilter(obj, event)

    def _show_popup(self):
        popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.setStyleSheet(f"""
            QFrame#perfilPopup {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 12px;
            }}
        """)
        popup.setObjectName("perfilPopup")

        gap = 6        # uniform gap: top edge, between items, bottom edge
        item_h = 46    # fixed height per item button
        n = len(self._opciones)

        inner_ly = QVBoxLayout(popup)
        inner_ly.setContentsMargins(gap, gap, gap, gap)
        inner_ly.setSpacing(gap)

        for opcion in self._opciones:
            is_sel = (opcion == self._valor)
            btn = QPushButton(opcion)
            btn.setFixedHeight(item_h)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("perfilItemSel" if is_sel else "perfilItem")
            btn.setStyleSheet(f"""
                QPushButton#perfilItemSel, QPushButton#perfilItem {{
                    background: {"#00FFC6" if is_sel else "#11181D"};
                    color: {"#0E1117" if is_sel else "#FFFFFF"};
                    border: none;
                    border-radius: 10px;
                    padding: 0px 20px;
                    font-family: 'Segoe UI';
                    font-weight: bold;
                    font-size: 13px;
                    text-align: left;
                }}
                QPushButton#perfilItemSel:hover, QPushButton#perfilItem:hover {{
                    background: rgba(0,255,198,0.18);
                    color: {_CIAN};
                }}
            """)
            btn.clicked.connect(lambda _c=False, o=opcion: self._on_select(o, popup))
            inner_ly.addWidget(btn)

        popup_w = max(self._btn.width(), self.width(), 200)
        # exact height: n items + (n+1) gaps (top + between + bottom)
        popup_h = n * item_h + (n + 1) * gap
        popup.setFixedSize(popup_w, popup_h)

        pos = self._btn.mapToGlobal(self._btn.rect().bottomLeft())
        popup.move(pos)
        popup.installEventFilter(self)  # para detectar el cierre (toggle)
        popup.show()
        self._popup = popup

        def _apply_mask():
            bm = QBitmap(popup.size())
            bm.fill(Qt.GlobalColor.color0)
            p = QPainter(bm)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(popup.rect(), 12, 12)
            p.end()
            popup.setMask(bm)
        QTimer.singleShot(0, _apply_mask)

    def _on_select(self, value, popup):
        changed = value != self._valor
        self._valor = value
        self._refresh_btn()
        try:
            popup.close()
        except Exception:
            pass
        self._popup = None
        if changed:
            self.currentTextChanged.emit(value)


class _TimeDropdown(QWidget):
    """Collapsible time-value dropdown — no arrow, scrollable list with neon scrollbar."""

    def __init__(self, opciones, parent=None, max_visible=6):
        super().__init__(parent)
        self._opciones = opciones
        self._valor = opciones[0] if opciones else ""
        self._popup = None
        self._max_visible = max_visible

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        self._btn = _DropdownBtn(show_arrow=False, font_size=11)
        self._btn.clicked.connect(self._toggle_popup)
        self._refresh_btn()
        ly.addWidget(self._btn)

    def _refresh_btn(self):
        self._btn.set_display_text(self._valor)

    def currentText(self):
        return self._valor

    def _toggle_popup(self):
        # Mismo toggle que _PerfilDropdown: tras el auto-cierre de Qt.Popup, el
        # segundo clic NO reabre (actúa como cierre).
        if getattr(self, "_suppress_reopen", False):
            return
        self._show_popup()

    def eventFilter(self, obj, event):
        if (obj is self._popup and event is not None
                and event.type() == QEvent.Type.Close):
            self._suppress_reopen = True
            QTimer.singleShot(250, lambda: setattr(self, "_suppress_reopen", False))
        return super().eventFilter(obj, event)

    def _show_popup(self):
        popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.setStyleSheet(f"""
            QFrame {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 12px;
            }}
        """)

        list_w = QListWidget(popup)
        list_w.addItems(self._opciones)
        sel_idx = 0
        for i in range(list_w.count()):
            if list_w.item(i).text() == self._valor:
                list_w.setCurrentRow(i)
                sel_idx = i
                break
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        list_w.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none; outline: none;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
            }}
            QListWidget::item {{
                background: #11181D; color: white;
                padding: 10px 14px; border-radius: 8px; margin: 2px 0px;
            }}
            QListWidget::item:hover {{
                background: rgba(0, 255, 198, 0.15); color: {_CIAN};
            }}
            QListWidget::item:selected {{
                background: {_CIAN}; color: #0E1117;
            }}
        """)
        list_w.itemClicked.connect(lambda item: self._on_select(item.text(), popup))

        inner_ly = QVBoxLayout(popup)
        inner_ly.setContentsMargins(6, 6, 6, 6)
        inner_ly.setSpacing(0)
        inner_ly.addWidget(list_w)

        visible_items = min(self._max_visible, len(self._opciones))
        popup_w = max(self._btn.width(), self.width(), 110)
        popup_h = visible_items * 40 + 16
        popup.setFixedSize(popup_w, popup_h)

        pos = self._btn.mapToGlobal(self._btn.rect().bottomLeft())
        popup.move(pos)
        popup.installEventFilter(self)  # para detectar el cierre (toggle)
        popup.show()
        self._popup = popup

        def _init():
            bm = QBitmap(popup.size())
            bm.fill(Qt.GlobalColor.color0)
            p = QPainter(bm)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(popup.rect(), 12, 12)
            p.end()
            popup.setMask(bm)
            list_w.scrollToItem(
                list_w.item(sel_idx),
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )
        QTimer.singleShot(0, _init)

    def _on_select(self, value, popup):
        self._valor = value
        self._refresh_btn()
        try:
            popup.close()
        except Exception:
            pass
        self._popup = None


class _CloseCircleBtn(QWidget):
    """Custom-painted close button — gray circle + white × by default, red on hover.
    Bypasses all Qt stylesheets so global QPushButton rules cannot interfere."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor("#F85149") if self._hovered else QColor("#6E7681")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(1, 1, 20, 20)
        pen = QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = 6
        p.drawLine(m, m, 22 - m, 22 - m)
        p.drawLine(22 - m, m, m, 22 - m)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  HORARIO EMPLEADOS — custom schedule grid
# ─────────────────────────────────────────────────────────────────────────────

class _MoveIcon(QWidget):
    """Custom-painted 4-directional move/drag handle in neon cyan."""

    def __init__(self, on_press, parent=None):
        super().__init__(parent)
        self._on_press = on_press
        self.setFixedSize(40, 36)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._hovered = False
        self.setMouseTracking(True)

    def enterEvent(self, ev):  self._hovered = True;  self.update()
    def leaveEvent(self, ev):  self._hovered = False; self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._on_press(ev.globalPosition().toPoint())

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clr = QColor(_CIAN) if self._hovered else QColor("#6E7681")
        bg  = QColor(0, 255, 198, 30) if self._hovered else QColor("#11181D")
        p.setPen(QPen(clr, 1))
        p.setBrush(bg)
        p.drawRoundedRect(1, 1, 38, 34, 8, 8)
        cx, cy  = 20, 17
        arm     = 11
        shaft   = 4
        hd      = 5
        hw      = 4.5
        pen = QPen(clr, 2.0, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(cx, cy - shaft, cx, cy - arm + hd)
        p.drawLine(cx, cy + shaft, cx, cy + arm - hd)
        p.drawLine(cx - shaft, cy, cx - arm + hd, cy)
        p.drawLine(cx + shaft, cy, cx + arm - hd, cy)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(clr)
        def tri(tip_x, tip_y, dx, dy):
            px, py = -dy * hw, dx * hw
            path = QPainterPath()
            path.moveTo(tip_x, tip_y)
            path.lineTo(tip_x - dx * hd + px, tip_y - dy * hd + py)
            path.lineTo(tip_x - dx * hd - px, tip_y - dy * hd - py)
            path.closeSubpath()
            p.drawPath(path)
        tri(cx,       cy - arm,  0.0, -1.0)
        tri(cx,       cy + arm,  0.0,  1.0)
        tri(cx - arm, cy,       -1.0,  0.0)
        tri(cx + arm, cy,        1.0,  0.0)
        p.setBrush(clr)
        p.drawEllipse(cx - 2, cy - 2, 4, 4)
        p.end()


def _h_parse_minutes(text: str) -> int:
    """'Xh YYmin' → total minutes; returns 0 for special/unparseable values."""
    try:
        text = text.strip()
        if "h" not in text:
            return 0
        parts = text.split("h")
        hh = int(parts[0].strip())
        mm = 0
        if len(parts) > 1 and "min" in parts[1]:
            mm = int(parts[1].replace("min", "").strip())
        return hh * 60 + mm
    except Exception:
        return 0


class _TableCornerCover(QWidget):
    """Overlay that repaints panel-color triangles over the 4 rounded corners of a
    neon-bordered table frame so row cells never bleed through the border-radius."""
    def __init__(self, parent, radius=10, panel_color="#0D1117", border_color=None):
        super().__init__(parent)
        self._r = float(radius)
        self._panel = QColor(panel_color)
        self._border = QColor(border_color or _CIAN)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(parent.rect())

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = float(self.width()), float(self.height())
        full = QPainterPath(); full.addRect(QRectF(0, 0, W, H))
        inner = QPainterPath(); inner.addRoundedRect(QRectF(0, 0, W, H), self._r, self._r)
        p.fillPath(full.subtracted(inner), self._panel)
        p.setPen(QPen(self._border, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), self._r - 1, self._r - 1)
        p.end()


class _QtyInput(QWidget):
    """Direct numeric input for the denomination table — no +/- buttons."""
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._val = 0
        ly = QHBoxLayout(self)
        ly.setContentsMargins(6, 4, 6, 4)
        ly.setSpacing(0)

        from PyQt6.QtGui import QIntValidator
        self._inp = QLineEdit("0")
        self._inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inp.setValidator(QIntValidator(0, 9999, self._inp))
        self._inp.setStyleSheet(
            f"QLineEdit{{background:#0D1117;color:white;border:2px solid {_CIAN};"
            f"border-radius:8px;font-family:'Segoe UI';font-weight:900;font-size:15px;"
            f"padding:0;}}"
            f"QLineEdit:focus{{border-color:#FFFFFF;color:{_CIAN};}}"
        )
        self._inp.textChanged.connect(self._on_change)
        ly.addWidget(self._inp)

    def _on_change(self, text):
        try:
            v = int(text) if text.strip() else 0
            self._val = max(0, v)
        except ValueError:
            self._val = 0
        self.valueChanged.emit(self._val)

    def value(self):
        return self._val


def _icono_denominacion(denom: dict) -> "QIcon":
    """Icono de una denominación de la divisa activa: usa su imagen real si existe;
    si falta, un icono GENÉRICO (círculo=moneda / rectángulo=billete), sin romper."""
    ruta = denom.get("imagen")
    if ruta and os.path.exists(ruta):
        pm = QPixmap(ruta)
        if not pm.isNull():
            return QIcon(pm)
    # Genérico (la imagen no estaba; ya se ha registrado el aviso en logs).
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    es_billete = denom.get("tipo") == "billete"
    p.setBrush(QColor("#2A3340"))
    p.setPen(QPen(QColor("#566273"), 2))
    if es_billete:
        p.drawRoundedRect(6, 18, 52, 28, 5, 5)
    else:
        p.drawEllipse(12, 12, 40, 40)
    p.setPen(QColor("#8B949E"))
    f = p.font(); f.setBold(True); f.setPointSize(11 if es_billete else 14); p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, divisas.simbolo())
    p.end()
    return QIcon(pm)


class _ConteoEfectivoDialog(QDialog):
    """Modal de arqueo de efectivo con tabla de denominaciones y totales en tiempo real.
    La tabla es DINÁMICA según la divisa de empresa: imagen | valor | cantidad | total."""

    def __init__(self, titulo="ARQUEO DE EFECTIVO", fondo_esperado=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._total = 0.0
        self._fondo_esperado = fondo_esperado
        self._spins: list = []
        self._sub_items: list = []
        # Denominaciones de la divisa de empresa activa (dinámico): si el admin
        # cambia la divisa, el siguiente arqueo se construye con la nueva.
        self._denoms = divisas.denominaciones()
        self._build(titulo)

    @staticmethod
    def _btn_ss(bg, fg, border):
        return (f"QPushButton{{background:{bg};color:{fg};border:2px solid {border};"
                f"border-radius:10px;font-family:'Segoe UI';font-weight:900;"
                f"font-size:13px;padding:0 24px;}}"
                f"QPushButton:hover{{background:{fg};color:{bg};}}")

    def _build(self, titulo):
        card = QFrame(self)
        card.setObjectName("cc")
        card.setStyleSheet(f"QFrame#cc{{background:#0E1117;border:2px solid {_CIAN};border-radius:20px;}}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(12)

        hr = QHBoxLayout()
        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;")
        lbl_d = QLabel(datetime.now().strftime("  %d/%m/%Y  —  %H:%M"))
        lbl_d.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:13px;font-weight:bold;")
        hr.addWidget(lbl_t); hr.addStretch(); hr.addWidget(lbl_d)
        ly.addLayout(hr)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{_BORDE};border:none;")
        ly.addWidget(sep)

        tbl_wrap = QWidget()
        tbl_wrap.setStyleSheet("background:#0D1117;")

        tbl = QTableWidget(len(self._denoms), 4)
        tbl.setHorizontalHeaderLabels([
            tr("cfg.col_image", default="IMAGEN"),
            tr("cfg.col_value", default="VALOR"),
            tr("cfg.col_qty", default="CANTIDAD"),
            tr("cfg.col_total", default="TOTAL"),
        ])
        _hdr = tbl.horizontalHeader()
        _hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        _hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        _hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        _hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(0, 86); tbl.setColumnWidth(2, 130); tbl.setColumnWidth(3, 120)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setFrameShape(QFrame.Shape.NoFrame)
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tbl.setViewportMargins(0, 0, 0, 0)
        tbl.setContentsMargins(0, 0, 0, 0)
        tbl.setStyleSheet(f"""
            QTableWidget{{background:#0D1117;border:none;
                          gridline-color:#21262d;color:white;font-family:'Segoe UI';
                          font-size:14px;font-weight:bold;outline:none;}}
            QHeaderView::section{{background:#161B22;color:{_CIAN};border:1px solid {_BORDE};
                                  padding:7px;font-family:'Segoe UI';font-weight:900;font-size:12px;}}
            QTableWidget::item{{padding:3px 8px;}}
            QTableWidget::item:hover{{background:rgba(0,255,198,25);}}
            QTableWidget::item:alternate{{background:#0A0F14;}}
            QTableWidget::item:alternate:hover{{background:rgba(0,255,198,25);}}
            QTableWidget::item:selected{{background:#00FFC622;color:white;}}
        """)
        tbl.setFixedHeight(360)
        tbl.setIconSize(QSize(64, 64))
        tbl.verticalHeader().setDefaultSectionSize(68)

        _cero = divisas.formatear(0)
        for row, den in enumerate(self._denoms):
            tipo_b = den["tipo"] == "billete"
            # Col 0 — IMAGEN (moneda/billete) con fallback genérico
            it_img = QTableWidgetItem()
            it_img.setIcon(_icono_denominacion(den))
            it_img.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl.setItem(row, 0, it_img)

            # Col 1 — VALOR
            it_v = QTableWidgetItem("  " + den["etiqueta"])
            it_v.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            it_v.setForeground(QColor("#E3B341" if tipo_b else "#E6EDF3"))
            tbl.setItem(row, 1, it_v)

            # Col 2 — CANTIDAD
            qty = _QtyInput()
            qty.valueChanged.connect(self._upd)
            tbl.setCellWidget(row, 2, qty)
            self._spins.append((den["valor"], qty))

            # Col 3 — TOTAL
            it_s = QTableWidgetItem(_cero)
            it_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_s.setForeground(QColor("#6E7681"))
            tbl.setItem(row, 3, it_s)
            self._sub_items.append(it_s)

        stack_ly = QStackedLayout(tbl_wrap)
        stack_ly.setContentsMargins(0, 0, 0, 0)
        stack_ly.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack_ly.addWidget(tbl)
        ly.addWidget(tbl_wrap)

        def _apply_tbl_cover():
            # Snap height so viewport bottom = last full row bottom (no empty strip)
            hdr_h = tbl.horizontalHeader().height()
            row_h = tbl.verticalHeader().defaultSectionSize()
            n_vis = max(1, (tbl.height() - hdr_h) // row_h)
            new_h = hdr_h + n_vis * row_h
            tbl.setFixedHeight(new_h)
            tbl_wrap.setFixedHeight(new_h)
            cover = _TableCornerCover(tbl_wrap, radius=10, panel_color="#0E1117")
            cover.setGeometry(tbl_wrap.rect())
            cover.raise_()
            cover.show()
            tbl.selectRow(0)
            _focus_qty(0)
        QTimer.singleShot(0, _apply_tbl_cover)

        tf = QFrame()
        tf.setStyleSheet(
            f"QFrame{{background:#161B22;border:2px solid {_CIAN};"
            f"border-radius:12px;}}"
        )
        t_ly = QHBoxLayout(tf)
        t_ly.setContentsMargins(14, 0, 14, 0)
        t_ly.setSpacing(0)
        t_ly.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        tf.setFixedHeight(54)

        btn_vincular = QPushButton("🔌  " + tr("cfg.link_machine", default="VINCULAR MÁQUINA"))
        btn_vincular.setFixedHeight(34)
        btn_vincular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_vincular.setEnabled(True)
        btn_vincular.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid {_BORDE};color:#8B949E;"
            f"border-radius:8px;font-family:'Segoe UI';font-weight:900;font-size:11px;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}"
        )

        t_ly.addWidget(btn_vincular)
        t_ly.addStretch()

        lbl_tt = QLabel(tr("cfg.total_counted", default="TOTAL CONTADO:"))
        lbl_tt.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:900;font-size:13px;border:none;background:transparent;")
        self._lbl_total = QLabel(divisas.formatear(0))
        self._lbl_total.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:22px;border:none;background:transparent;")
        t_ly.addWidget(lbl_tt)
        t_ly.addSpacing(10)
        t_ly.addWidget(self._lbl_total)
        if self._fondo_esperado is not None:
            le = QLabel(tr("cfg.expected_suffix", default="  |  Esperado: {x}", x=divisas.formatear(self._fondo_esperado)))
            le.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;border:none;background:transparent;")
            t_ly.addWidget(le)
        ly.addWidget(tf)

        br = QHBoxLayout()
        br.setSpacing(8)

        _nav_css = (
            f"QPushButton{{background:#161B22;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:10px;font-size:16px;font-weight:900;"
            f"min-width:46px;max-width:46px;min-height:44px;max-height:44px;padding:0;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )

        def _focus_qty(row):
            if 0 <= row < len(self._denoms):
                w = tbl.cellWidget(row, 2)
                if w is not None:
                    w._inp.setFocus()
                    w._inp.selectAll()

        def _nav(delta):
            row = tbl.currentRow()
            nrow = max(0, min(len(self._denoms) - 1, (row if row >= 0 else 0) + delta))
            tbl.selectRow(nrow)
            tbl.scrollTo(tbl.model().index(nrow, 0))
            _focus_qty(nrow)

        tbl.clicked.connect(lambda idx: _focus_qty(idx.row()))

        btn_up = QPushButton("▲")
        btn_up.setMaximumWidth(50); btn_up.setFixedHeight(44)
        btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_up.setStyleSheet(_nav_css)
        btn_up.clicked.connect(lambda: _nav(-1))

        btn_dn = QPushButton("▼")
        btn_dn.setMaximumWidth(50); btn_dn.setFixedHeight(44)
        btn_dn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dn.setStyleSheet(_nav_css)
        btn_dn.clicked.connect(lambda: _nav(1))

        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedSize(148, 44)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(self._btn_ss("#0D1117", "#F85149", "#F85149"))
        bc.clicked.connect(self.reject)
        bk = QPushButton("✔  " + tr("cfg.confirm_count", default="CONFIRMAR ARQUEO")); bk.setFixedSize(260, 44)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:10px;font-family:'Segoe UI';font-weight:900;"
            f"font-size:13px;padding:0 10px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        bk.clicked.connect(self.accept)

        br.addStretch()
        br.addWidget(btn_up); br.addWidget(btn_dn)
        br.addSpacing(12)
        br.addWidget(bc); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedSize(720, 640)

    def _upd(self):
        total = 0.0
        for i, (val, spin) in enumerate(self._spins):
            sub = round(val * spin.value(), 2)
            total += sub
            self._sub_items[i].setText(divisas.formatear(sub))
            self._sub_items[i].setForeground(QColor("#3FB950" if sub > 0 else "#6E7681"))
        self._total = round(total, 2)
        self._lbl_total.setText(divisas.formatear(self._total))

    def get_total(self) -> float:
        return self._total

    def get_detalle(self) -> list:
        return [
            {"denominacion": self._denoms[i]["etiqueta"], "valor": self._denoms[i]["valor"],
             "cantidad": sp.value(), "subtotal": round(self._denoms[i]["valor"] * sp.value(), 2)}
            for i, (_, sp) in enumerate(self._spins) if sp.value() > 0
        ]


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


class _MotivoDialog(QDialog):
    """Motivo obligatorio con validación de mínimo 15 caracteres."""

    def __init__(self, encabezado=None, parent=None):
        super().__init__(parent)
        if encabezado is None:
            encabezado = tr("cfg.motivo_default", default="Indique el motivo:")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._motivo = ""
        self._build(encabezado)

    def _build(self, encabezado):
        card = QFrame(self); card.setObjectName("md")
        card.setStyleSheet(f"QFrame#md{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(12)

        lbl_h = QLabel(encabezado); lbl_h.setWordWrap(True)
        lbl_h.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        ly.addWidget(lbl_h)

        self._txt = QTextEdit()
        self._txt.setFixedHeight(110)
        self._txt.setPlaceholderText(tr("cfg.motivo_ph", default="Describa el motivo con detalle (mínimo 15 caracteres)..."))
        self._txt.setStyleSheet(f"""
            QTextEdit{{background:#161B22;color:white;border:2px solid {_BORDE};
                       border-radius:10px;padding:10px;font-family:'Segoe UI';font-size:13px;}}
            QTextEdit:focus{{border-color:{_CIAN};}}
        """)
        self._txt.textChanged.connect(self._on_change)
        ly.addWidget(self._txt)

        self._lbl_c = QLabel(tr("cfg.chars_min", default="{n} / 15 caracteres mínimo", n=0))
        self._lbl_c.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;")
        ly.addWidget(self._lbl_c)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        _ss_continuar_off = (
            "QPushButton{background:#161B22;color:#6E7681;border:2px solid #6E7681;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
        )
        _ss_continuar_on = (
            "QPushButton{background:#3FB950;color:#0D1117;border:2px solid #3FB950;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#FFFFFF;color:#0D1117;border:2px solid #FFFFFF;}"
        )
        self._ss_off = _ss_continuar_off
        self._ss_on  = _ss_continuar_on

        self._btn_ok = QPushButton(tr("cfg.continue", default="CONTINUAR")); self._btn_ok.setFixedHeight(40)
        self._btn_ok.setMinimumWidth(130)
        self._btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ok.setStyleSheet(_ss_continuar_off)
        self._btn_ok.clicked.connect(self._confirm)
        br.addWidget(bc)
        br.addStretch(1)
        br.addWidget(self._btn_ok)
        ly.addLayout(br)
        self.setFixedSize(500, 290)

    def _on_change(self):
        n = len(self._txt.toPlainText().strip())
        ok = n >= 15
        self._lbl_c.setText(tr("cfg.chars_min", default="{n} / 15 caracteres mínimo", n=n))
        self._lbl_c.setStyleSheet(
            f"color:{'#3FB950' if ok else '#6E7681'};"
            "font-family:'Segoe UI';font-size:11px;"
        )
        self._btn_ok.setStyleSheet(self._ss_on if ok else self._ss_off)

    def _flash_error(self):
        """Borde rojo en textarea + contador rojo para indicar que faltan caracteres."""
        _CIAN = "#00FFC6"
        _BORDE = "#21262d"
        self._lbl_c.setStyleSheet(
            "color:#F85149;font-family:'Segoe UI';font-size:11px;font-weight:bold;"
        )
        self._txt.setStyleSheet("""
            QTextEdit{background:#161B22;color:white;border:2px solid #F85149;
                       border-radius:10px;padding:10px;font-family:'Segoe UI';font-size:13px;}
            QTextEdit:focus{border-color:#F85149;}
        """)
        QTimer.singleShot(1200, self._reset_error_style)

    def _reset_error_style(self):
        _CIAN = "#00FFC6"
        _BORDE = "#21262d"
        n = len(self._txt.toPlainText().strip())
        self._lbl_c.setStyleSheet(
            f"color:{'#3FB950' if n >= 15 else '#6E7681'};font-family:'Segoe UI';font-size:11px;"
        )
        self._txt.setStyleSheet(f"""
            QTextEdit{{background:#161B22;color:white;border:2px solid {_BORDE};
                       border-radius:10px;padding:10px;font-family:'Segoe UI';font-size:13px;}}
            QTextEdit:focus{{border-color:{_CIAN};}}
        """)

    def _confirm(self):
        if len(self._txt.toPlainText().strip()) < 15:
            self._flash_error()
            return
        self._motivo = self._txt.toPlainText().strip()
        self.accept()

    def get_motivo(self) -> str:
        return self._motivo


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


class _SeleccionarCajaDialog(QDialog):
    """Selección de caja registradora activa a cerrar."""

    def __init__(self, cajas: list, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._caja_id: str | None = None
        self._build(cajas)

    def _build(self, cajas: list):
        card = QFrame(self); card.setObjectName("scd")
        card.setStyleSheet(
            f"QFrame#scd{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}"
        )
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(14)

        lbl_t = QLabel(tr("cfg.select_caja_title", default="SELECCIONAR CAJA A CERRAR"))
        lbl_t.setStyleSheet(
            f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:14px;"
        )
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_t)

        lbl_sub = QLabel(tr("cfg.select_caja_sub", default="Selecciona la caja registradora que deseas cerrar:"))
        lbl_sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
        lbl_sub.setWordWrap(True)
        ly.addWidget(lbl_sub)

        self._lista = QListWidget()
        self._lista.setStyleSheet(
            f"QListWidget{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:10px;font-family:'Segoe UI';font-size:13px;outline:none;padding:4px;}}"
            f"QListWidget::item{{padding:12px 16px;border-radius:8px;margin:2px 4px;}}"
            f"QListWidget::item:selected{{background:{_CIAN};color:#0E1117;font-weight:900;border-radius:8px;}}"
            f"QListWidget::item:hover{{background:rgba(0,255,198,0.10);border-radius:8px;}}"
        )
        self._lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for c in cajas:
            resp = c.get("responsable", "—")
            fondo = c.get("fondo", 0.0)
            hora = c.get("hora_apertura", "—")
            item = QListWidgetItem(
                tr("cfg.caja_item", default="  {id}   ·   Responsable: {resp}   ·   Fondo: {x} €   ·   Apertura: {hora}",
                   id=c['id'], resp=resp, x=divisas.formatear(fondo), hora=hora)
            )
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self._lista.addItem(item)
        self._lista.setCurrentRow(0)
        self._lista.itemDoubleClicked.connect(self._confirmar)
        ly.addWidget(self._lista)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            "QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}"
        )
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.close_this_caja", default="CERRAR ESTA CAJA")); bk.setFixedHeight(40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        bk.clicked.connect(self._confirmar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedWidth(580)
        self.adjustSize()

    def _confirmar(self):
        item = self._lista.currentItem()
        if item:
            self._caja_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def get_caja_id(self) -> str | None:
        return self._caja_id


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


class _MovimientoDialog(QDialog):
    """Formulario de movimiento de efectivo con doble entrada (origen → destino)."""

    def __init__(self, cajas_activas=None, fondo_caja_fuerte=0.0, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._cajas = cajas_activas or []
        self._fondo_fuerte = fondo_caja_fuerte
        self._resultado = None
        self._build()

    @staticmethod
    def _inp_ss():
        return (f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};"
                f"border-radius:10px;padding:10px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
                f"QLineEdit:focus{{border-color:{_CIAN};}}")

    @staticmethod
    def _combo_ss():
        return (
            f"QComboBox{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:10px;padding:8px 36px 8px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:#E6EDF3;border:2px solid {_CIAN};"
            f"border-radius:10px;selection-background-color:{_CIAN};selection-color:#0D1117;outline:none;}}"
            f"QComboBox QAbstractItemView::item{{height:38px;padding:0 14px;}}"
            f"QComboBox QAbstractItemView::item:hover{{background:rgba(0,255,198,0.12);color:{_CIAN};}}"
        )

    def _opciones(self):
        opts = ["EXTERNO (PROSEGUR, LOOMIS, etc)", f"CAJA FUERTE  [{divisas.formatear(self._fondo_fuerte)}]"]
        for c in self._cajas:
            opts.append(f"{c.get('id','?')}  [{c.get('responsable','?')}  ·  {divisas.formatear(c.get('fondo', 0.0))}]")
        return opts

    def _build(self):
        card = QFrame(self); card.setObjectName("mvd")
        card.setStyleSheet(f"QFrame#mvd{{background:#0E1117;border:2px solid {_CIAN};border-radius:20px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        outer = QVBoxLayout(card); outer.setContentsMargins(30, 26, 30, 26); outer.setSpacing(10)

        # Título siempre visible
        lbl_t = QLabel(tr("cfg.mov_title", default="MOVIMIENTO DE EFECTIVO"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;")
        outer.addWidget(lbl_t)

        # ── Scroll area para el formulario ────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
        )

        form_w = QWidget(); form_w.setStyleSheet("background:transparent;")
        ly = QVBoxLayout(form_w); ly.setContentsMargins(0, 4, 8, 4); ly.setSpacing(10)

        def _lbl(txt):
            l = QLabel(txt)
            l.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:14px;font-weight:bold;")
            return l

        opts = self._opciones()

        ly.addWidget(_lbl(tr("cfg.mov_origen_lbl", default="Origen (de dónde sale el efectivo):")))
        self._combo_origen = _NeonComboBox()
        self._combo_origen.addItem(tr("cfg.select_origen", default="— Seleccionar origen —"))
        self._combo_origen.addItems(opts)
        self._combo_origen.setFixedHeight(44); self._combo_origen.set_cover_style("#161B22", 10)
        self._combo_origen.setStyle(_get_no_arrow_style())
        self._combo_origen.setStyleSheet(self._combo_ss())
        ly.addWidget(self._combo_origen)

        ly.addWidget(_lbl(tr("cfg.mov_destino_lbl", default="Destino (a dónde va el efectivo):")))
        self._combo_destino = _NeonComboBox()
        self._combo_destino.addItem(tr("cfg.select_destino", default="— Seleccionar destino —"))
        self._combo_destino.addItems(opts)
        self._combo_destino.setFixedHeight(44); self._combo_destino.set_cover_style("#161B22", 10)
        self._combo_destino.setStyle(_get_no_arrow_style())
        self._combo_destino.setStyleSheet(self._combo_ss())
        ly.addWidget(self._combo_destino)

        ly.addWidget(_lbl(tr("cfg.mov_importe_lbl", default="Importe (€):")))
        self._inp_imp = QLineEdit(); self._inp_imp.setPlaceholderText("0.00")
        self._inp_imp.setFixedHeight(44); self._inp_imp.setStyleSheet(self._inp_ss())
        ly.addWidget(self._inp_imp)

        ly.addWidget(_lbl(tr("cfg.mov_motivo_lbl", default="Motivo:")))
        self._inp_mot = QLineEdit(); self._inp_mot.setPlaceholderText(tr("cfg.mov_motivo_ph", default="Motivo del movimiento..."))
        self._inp_mot.setFixedHeight(44); self._inp_mot.setStyleSheet(self._inp_ss())
        ly.addWidget(self._inp_mot)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_BORDE};background:{_BORDE};border:none;max-height:1px;")
        ly.addWidget(sep)

        ly.addWidget(_lbl(tr("cfg.mov_emp_lbl", default="Empleado responsable:")))
        self._combo_emp_mov = _NeonComboBox()
        self._combo_emp_mov.addItem(tr("cfg.select_emp_combo", default="— Seleccionar empleado —"), None)
        try:
            for u in listar_usuarios():
                self._combo_emp_mov.addItem(f"{u['nombre']}  ({tr('roles.' + str(u['perfil']).lower(), default=u['perfil']).upper()})", u["id"])
        except Exception:
            pass
        self._combo_emp_mov.setFixedHeight(44)
        self._combo_emp_mov.set_cover_style("#161B22", 10)
        self._combo_emp_mov.setStyle(_get_no_arrow_style())
        self._combo_emp_mov.setStyleSheet(self._combo_ss())
        ly.addWidget(self._combo_emp_mov)

        ly.addWidget(_lbl(tr("cfg.pin_label_4", default="PIN (4 dígitos):")))
        self._pin_mov = QLineEdit()
        self._pin_mov.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_mov.setPlaceholderText("• • • •")
        self._pin_mov.setMaxLength(4)
        self._pin_mov.setFixedHeight(48)
        self._pin_mov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pin_mov.setStyleSheet(
            f"QLineEdit{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:12px;font-family:'Segoe UI';font-weight:900;font-size:20px;letter-spacing:6px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        ly.addWidget(self._pin_mov)
        ly.addStretch()

        scroll.setWidget(form_w)
        outer.addWidget(scroll, 1)

        # Error label y botones siempre visibles fuera del scroll
        self._lbl_error = QLabel("")
        self._lbl_error.setStyleSheet("color:#F85149;font-family:'Segoe UI';font-size:11px;")
        self._lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._lbl_error)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(42)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.register_mov", default="REGISTRAR MOVIMIENTO")); bk.setFixedHeight(42)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:#0D1117;}}")
        bk.clicked.connect(self._confirmar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(bk)
        outer.addLayout(br)
        self.setFixedSize(600, 560)

    @staticmethod
    def _parse_opcion(texto):
        """Devuelve ('EXTERNO'|'CAJA_FUERTE'|'CAJA', id_o_None)."""
        if texto.startswith("EXTERNO"):
            return "EXTERNO", None
        if texto.startswith("CAJA FUERTE"):
            return "CAJA_FUERTE", None
        caja_id = texto.split()[0]
        return "CAJA", caja_id

    def _confirmar(self):
        self._lbl_error.setText("")
        try:
            importe = float(self._inp_imp.text().replace(",", "."))
        except ValueError:
            self._lbl_error.setText(tr("cfg.imp_invalid", default="Introduce un importe válido.")); return
        if importe <= 0:
            self._lbl_error.setText(tr("cfg.imp_gt0", default="El importe debe ser mayor que 0 €.")); return
        if self._combo_origen.currentIndex() == 0:
            self._lbl_error.setText(tr("cfg.sel_origen_err", default="Selecciona el origen del efectivo.")); return
        if self._combo_destino.currentIndex() == 0:
            self._lbl_error.setText(tr("cfg.sel_destino_err", default="Selecciona el destino del efectivo.")); return
        if not self._inp_mot.text().strip():
            self._lbl_error.setText(tr("cfg.mot_err", default="Escribe un motivo para el movimiento.")); return

        uid = self._combo_emp_mov.currentData()
        if uid is None:
            self._lbl_error.setText(tr("cfg.sel_emp_resp_err", default="Selecciona el empleado responsable.")); return
        pin = self._pin_mov.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            self._lbl_error.setText(tr("cfg.pin_len_err", default="El PIN debe tener exactamente 4 dígitos.")); return
        import hashlib
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        try:
            from src.db.conexion import obtener_conexion as _ocon
            with _ocon() as _conn:
                _cur = _conn.cursor()
                _cur.execute("SHOW COLUMNS FROM usuarios")
                _cols = [r["Field"] if isinstance(r, dict) else r[0] for r in _cur.fetchall()]
                _col = "nombre" if "nombre" in _cols else "usuario"
                _cur.execute(
                    f"SELECT {_col} FROM usuarios WHERE id=%s AND password=%s AND activo=1",
                    (uid, pin_hash)
                )
                _row = _cur.fetchone()
                if not _row:
                    self._lbl_error.setText(tr("cfg.pin_wrong_emp", default="PIN incorrecto para el empleado seleccionado."))
                    self._pin_mov.clear(); self._pin_mov.setFocus(); return
                _empleado_nombre = _row[_col] if isinstance(_row, dict) else _row[0]
        except Exception:
            self._lbl_error.setText(tr("cfg.pin_conn_err", default="Error de conexión con la base de datos.")); return

        origen_txt  = self._combo_origen.currentText()
        destino_txt = self._combo_destino.currentText()
        tipo_o, id_o = self._parse_opcion(origen_txt)
        tipo_d, id_d = self._parse_opcion(destino_txt)

        if tipo_o != "EXTERNO" and tipo_d != "EXTERNO" and tipo_o == tipo_d and id_o == id_d:
            self._lbl_error.setText(tr("cfg.same_org_dest", default="El origen y el destino no pueden ser el mismo.")); return

        if tipo_o == "EXTERNO" and tipo_d == "EXTERNO":
            self._lbl_error.setText(tr("cfg.both_external", default="Origen y destino no pueden ser ambos EXTERNO.")); return

        # Validar saldo disponible en el origen
        if tipo_o == "CAJA_FUERTE":
            saldo = self._fondo_fuerte
            if importe > saldo:
                self._lbl_error.setText(
                    tr("cfg.saldo_fuerte", default="Saldo insuficiente en Caja Fuerte. Disponible: {x} €", x=divisas.formatear(saldo))
                ); return
        elif tipo_o == "CAJA":
            saldo = next((c.get("fondo", 0.0) for c in self._cajas if c["id"] == id_o), 0.0)
            if importe > saldo:
                self._lbl_error.setText(
                    tr("cfg.saldo_caja", default="Saldo insuficiente en {id}. Disponible: {x} €", id=id_o, x=divisas.formatear(saldo))
                ); return

        if tipo_o == "EXTERNO":
            tipo_mov = "INGRESO EXTERNO"
        elif tipo_d == "EXTERNO":
            tipo_mov = "RETIRADA"
        else:
            tipo_mov = "TRANSFERENCIA"

        self._resultado = {
            "tipo": tipo_mov,
            "origen_txt": origen_txt, "destino_txt": destino_txt,
            "tipo_origen": tipo_o, "id_origen": id_o,
            "tipo_destino": tipo_d, "id_destino": id_d,
            "importe": importe,
            "motivo": self._inp_mot.text().strip(),
            "empleado": _empleado_nombre,
        }
        self.accept()

    def get_resultado(self):
        return self._resultado


# ── FISCALIDAD — Document Wizard ──────────────────────────────────────────────

class _WizardDocumentoFiscal(QDialog):
    """Asistente paso a paso para generar documentos laborales y fiscales."""

    DOCS = {
        # ── LABORAL ───────────────────────────────────────────────────────────
        "CONTRATO":       ("📄  CONTRATO LABORAL",    ["INDEFINIDO", "TEMPORAL", "FIJO DISCONTINUO", "PARCIAL", "PRÁCTICAS", "SUSTITUCIÓN"]),
        "NÓMINA":         ("📊  NÓMINA MENSUAL",       []),
        "ALTA":           ("✅  ALTA LABORAL",         []),
        "BAJA":           ("❌  BAJA LABORAL",         ["VOLUNTARIA", "FIN CONTRATO", "DESPIDO", "JUBILACIÓN", "INCAPACIDAD", "FALLECIMIENTO"]),
        "CERTIFICADO":    ("🏢  CERTIFICADO EMPRESA",  ["VIDA LABORAL", "COTIZACIÓN", "EMPRESA"]),
        "CERT LABORAL":   ("📃  CERTIFICADO LABORAL",  ["GENERAL", "INGRESOS", "ANTIGÜEDAD", "FUNCIONES", "JORNADA", "VACACIONES"]),
        "CARTA DESPIDO":  ("📮  CARTA DE DESPIDO",     ["DISCIPLINARIO", "OBJETIVO", "IMPROCEDENTE", "FIN CONTRATO", "BAJA VOLUNTARIA", "COLECTIVO"]),
        "FINIQUITO":      ("💼  FINIQUITO",             []),
        "VACACIONES":     ("🌴  VACACIONES",            ["SOLICITUD", "APROBACIÓN", "DENEGACIÓN"]),
        # ── FISCAL ────────────────────────────────────────────────────────────
        "RESUMEN FISCAL": ("📋  RESUMEN IVA",           ["TRIMESTRAL", "ANUAL"]),
        "LIBRO INGRESOS": ("📈  LIBRO DE INGRESOS",     []),
        "LIBRO GASTOS":   ("📉  LIBRO DE GASTOS",       []),
        "INFORME AUDIT":  ("🔍  INFORME AUDITORÍA",     ["CAJA", "RRHH", "ACCESOS", "MOVIMIENTOS", "DOCUMENTOS"]),
    }
    # Types that do not involve a single worker — step 1 shows empresa/period data
    _FISCAL_TYPES = {"RESUMEN FISCAL", "LIBRO INGRESOS", "LIBRO GASTOS", "INFORME AUDIT"}

    def __init__(self, tipo_inicial=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tipo = tipo_inicial
        self._paso = 0
        self._datos = {}
        self._build()

    def _nav_btn(self, txt, color=None):
        c = color or _CIAN
        b = QPushButton(txt); b.setFixedHeight(42)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:#0D1117;color:{c};border:2px solid {c};border-radius:8px;padding:0 22px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}QPushButton:hover{{background:{c};color:#0D1117;}}")
        return b

    def _mk_inp(self, ph=""):
        ph = _wz_tr(ph)
        inp = QLineEdit(); inp.setPlaceholderText(ph); inp.setFixedHeight(44)
        inp.setStyleSheet(f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};border-radius:10px;padding:10px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        return inp

    def _mk_combo(self, items):
        cb = _NeonComboBox()
        cb.addItems(items)
        cb.setFixedHeight(44)
        cb.setMaxVisibleItems(12)
        cb.set_cover_style("#161B22", 10)
        cb.setStyle(_get_no_arrow_style())
        cb.setStyleSheet(f"""
            QComboBox {{
                background: #161B22;
                color: white;
                border: 2px solid {_CIAN};
                border-radius: 10px;
                padding: 8px 36px 8px 14px;
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 13px;
            }}
            QComboBox QAbstractItemView {{
                background: #0D1117;
                color: #E6EDF3;
                border: 2px solid {_CIAN};
                border-radius: 10px;
                selection-background-color: {_CIAN};
                selection-color: #0D1117;
                outline: none;
                padding: 6px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 40px;
                padding: 0 14px;
                border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: rgba(0,255,198,0.12);
                color: {_CIAN};
            }}
        """)
        return cb

    def _mk_combo_centros(self):
        """Combo con TODOS los centros de trabajo de la empresa: centros registrados
        (DATOS DE EMPRESA) + tiendas + almacenes + correos corporativos. El item
        lleva como data un dict {id_centro, nombre, codigo, municipio, fuente}."""
        cb = self._mk_combo([])
        cb.addItem(tr("cfg.wz_centro_principal", default="— Centro principal por defecto —"), None)
        try:
            from src.db import centros as _cts
            from src.db.conexion import obtener_conexion
            from src.db.empresa import empresa_actual_id
            eid = empresa_actual_id()
            # 1) Centros de trabajo registrados (datos completos)
            for c in _cts.listar_centros():
                etq = " · ".join(x for x in [c.get("codigo_centro"), c.get("nombre_centro")] if x)
                if c.get("municipio"):
                    etq += f" ({c.get('municipio')})"
                cb.addItem("🏢  " + (etq or "Centro"),
                           {"id_centro": c.get("id_centro"), "nombre": c.get("nombre_centro"),
                            "municipio": c.get("municipio"), "fuente": "centro"})
            with obtener_conexion() as cn, cn.cursor() as cu:
                # 2) Tiendas
                try:
                    cu.execute("SELECT nombre, codigo_tienda FROM tiendas WHERE id_empresa=%s AND activo=1 ORDER BY nombre", (eid,))
                    for r in cu.fetchall():
                        nom = (r[0] if not isinstance(r, dict) else r.get("nombre")) or ""
                        cod = (r[1] if not isinstance(r, dict) else r.get("codigo_tienda")) or ""
                        if nom:
                            cb.addItem("🏪  " + nom + (f" ({cod})" if cod else ""),
                                       {"id_centro": None, "nombre": nom, "codigo": cod, "fuente": "tienda"})
                except Exception:
                    pass
                # 3) Almacenes
                try:
                    cu.execute("SELECT nombre, codigo_almacen FROM almacen WHERE id_empresa=%s AND activo=1 ORDER BY nombre", (eid,))
                    for r in cu.fetchall():
                        nom = (r[0] if not isinstance(r, dict) else r.get("nombre")) or ""
                        cod = (r[1] if not isinstance(r, dict) else r.get("codigo_almacen")) or ""
                        if nom:
                            cb.addItem("📦  " + nom + (f" ({cod})" if cod else ""),
                                       {"id_centro": None, "nombre": nom, "codigo": cod, "fuente": "almacen"})
                except Exception:
                    pass
            # 4) Correos corporativos (cada buzón implica un centro)
            try:
                from src.db import correo as _co
                for m in _co.listar_correos():
                    dirn = m.get("direccion") or ""
                    if dirn:
                        cb.addItem("✉  " + dirn,
                                   {"id_centro": None, "nombre": dirn, "fuente": "correo"})
            except Exception:
                pass
        except Exception:
            pass
        return cb

    def _mk_combo_representantes(self):
        """Combo con los representantes legales registrados (DATOS DE EMPRESA).
        Data = id_representante (o None = representante principal por defecto)."""
        cb = self._mk_combo([])
        cb.addItem(tr("cfg.wz_rep_principal", default="— Representante principal por defecto —"), None)
        try:
            from src.db import representantes as _reps
            for r in _reps.listar_representantes():
                nom = " ".join(x for x in [r.get("nombre"), r.get("apellidos")] if x).strip()
                cargo = r.get("cargo") or ""
                etq = nom + (f" · {cargo}" if cargo else "")
                cb.addItem("👤  " + (etq or "Representante"), r.get("id_representante"))
        except Exception:
            pass
        return cb

    # Logos institucionales (cofinanciación). Si faltan, se usa banner de texto.
    _FSE_LOGOS = [
        "ue_cofinanciado.png", "ministerio_sepe.png", "fondos_europeos.png",
    ]

    def _fse_logos_flowable(self, usable_w):
        """Fila de logos institucionales disponibles en assets/logos_institucionales/.
        Devuelve un Table de imágenes o None si no hay ninguna (→ banner de texto)."""
        from reportlab.lib.units import cm
        from reportlab.platypus import Image, Table, TableStyle
        try:
            from src.utils import recursos
            base = recursos.ruta_recurso("assets", "logos_institucionales")
        except Exception:
            base = os.path.normpath(os.path.join(
                os.path.dirname(__file__), "..", "..", "assets", "logos_institucionales"))
        rutas = [os.path.join(base, f) for f in self._FSE_LOGOS if os.path.exists(os.path.join(base, f))]
        if not rutas:
            return None
        cell_w = usable_w / len(rutas)
        celdas = []
        for r in rutas:
            try:
                im = Image(r)
                ratio = (im.imageWidth / im.imageHeight) if im.imageHeight else 1.0
                h = 1.25 * cm
                w = h * ratio
                if w > cell_w - 0.3 * cm:
                    w = cell_w - 0.3 * cm
                    h = w / ratio if ratio else h
                im.drawWidth = w
                im.drawHeight = h
                celdas.append(im)
            except Exception:
                celdas.append("")
        t = Table([celdas], colWidths=[cell_w] * len(rutas))
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    def _lbl_s(self, txt):
        l = QLabel(_wz_tr(txt))
        l.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:14px;font-weight:bold;")
        return l

    _PDF_DOMINIO = {
        "CONTRATO": "laboral", "NÓMINA": "laboral", "ALTA": "laboral", "BAJA": "laboral",
        "CERTIFICADO": "laboral", "CERT LABORAL": "laboral", "FINIQUITO": "laboral",
        "VACACIONES": "laboral", "CARTA DESPIDO": "juridico",
        "RESUMEN FISCAL": "fiscal", "LIBRO INGRESOS": "fiscal", "LIBRO GASTOS": "fiscal",
        "INFORME AUDIT": "fiscal",
    }

    def _pdf_tr(self, texto):
        """Traduce texto del documento (etiquetas/cláusulas legales) al idioma activo
        mediante el traductor IA por dominio. En español o sin backend devuelve el
        original (degradación elegante: el PDF sale en español si no hay IA)."""
        if not texto or not isinstance(texto, str):
            return texto
        out = texto
        if i18n.current_language() != "es":
            try:
                from src.utils import ai_translator
                dominio = self._PDF_DOMINIO.get(self._tipo, "laboral")
                out = ai_translator.traducir(texto, i18n.current_language(), dominio=dominio)
            except Exception:
                out = texto
        # Símbolo de divisa de empresa (p. ej. "IMPORTE (€)" -> "IMPORTE ($)").
        try:
            sym = divisas.simbolo()
            if sym != "€" and "€" in out:
                out = out.replace("€", sym)
        except Exception:
            pass
        return out

    def _doc_label(self, tipo=None):
        """Título de documento traducido (emoji + texto), por clave cfg.doc_<tipo>."""
        tipo = tipo or self._tipo
        titulo_es, _ = self.DOCS.get(tipo, ("", []))
        emoji = titulo_es.split("  ", 1)[0] if "  " in titulo_es else ""
        texto_es = titulo_es.split("  ", 1)[-1] if "  " in titulo_es else titulo_es
        traducido = tr("cfg.doc_" + str(tipo), default=texto_es)
        return (emoji + "  " + traducido) if emoji else traducido

    def _build(self):
        card = QFrame(self); card.setObjectName("wz")
        card.setStyleSheet(f"QFrame#wz{{background:#0E1117;border:2px solid {_CIAN};border-radius:20px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)

        self._outer_ly = QVBoxLayout(card)
        self._outer_ly.setContentsMargins(0, 0, 0, 0)
        self._outer_ly.setSpacing(0)

        # Persistent top bar with close button — survives _render() clears
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        tb_ly = QHBoxLayout(top_bar)
        tb_ly.setContentsMargins(30, 12, 12, 4)
        tb_ly.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(22, 22)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setStyleSheet(
            "QPushButton{background:transparent;color:#6E7681;border:1px solid #6E7681;"
            "border-radius:11px;font-family:'Segoe UI';font-weight:900;font-size:11px;padding:0px;}"
            "QPushButton:hover{background:#F85149;color:white;border-color:#F85149;}"
        )
        btn_x.clicked.connect(self.reject)
        tb_ly.addWidget(btn_x)
        self._outer_ly.addWidget(top_bar)

        self._content_w = None
        self.setFixedSize(740, 620)
        self._render()

    def _render(self):
        # Synchronously detach and discard old content widget so no overlap occurs
        if self._content_w is not None:
            self._outer_ly.removeWidget(self._content_w)
            self._content_w.setParent(None)
            self._content_w = None

        content_w = QWidget()
        content_w.setStyleSheet("background: transparent;")
        self._content_w = content_w
        self._card_ly = QVBoxLayout(content_w)
        self._card_ly.setContentsMargins(30, 4, 30, 22)
        self._card_ly.setSpacing(12)
        self._outer_ly.addWidget(content_w)

        # En el contrato, el 2º paso se llama CENTRO TRABAJO (lo pidió el usuario);
        # en el resto de documentos, DATOS.
        _paso2 = (tr("cfg.step_centro_trabajo", default="DATOS DEL CONTRATO")
                  if self._tipo == "CONTRATO" else tr("cfg.step_datos", default="DATOS"))
        pasos = ([tr("cfg.step_empresa", default="EMPRESA"), _paso2, tr("cfg.step_preview", default="VISTA PREVIA"), tr("cfg.step_generar", default="GENERAR")]
                 if self._tipo in self._FISCAL_TYPES
                 else [tr("cfg.step_trabajador", default="TRABAJADOR"), _paso2, tr("cfg.step_preview", default="VISTA PREVIA"), tr("cfg.step_generar", default="GENERAR")])
        sr = QHBoxLayout()
        for i, p in enumerate(pasos):
            lp = QLabel(p)
            c = _CIAN if i == self._paso else ("#3FB950" if i < self._paso else "#484F58")
            lp.setStyleSheet(f"color:{c};font-family:'Segoe UI';font-weight:900;font-size:12px;")
            lp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sr.addWidget(lp)
            if i < len(pasos) - 1:
                arr = QLabel("›"); arr.setStyleSheet("color:#484F58;font-size:16px;")
                sr.addWidget(arr)
        self._card_ly.addLayout(sr)
        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background:{_BORDE};border:none;")
        self._card_ly.addWidget(sep)

        getattr(self, f"_p{self._paso + 1}")()

    def _scroll_ss(self):
        return "QScrollArea{border:none;background:transparent;}"

    def _p1(self):
        if self._tipo in self._FISCAL_TYPES:
            self._p1_fiscal()
        else:
            self._p1_worker()

    def _p1_worker(self):
        label = self._doc_label()
        lbl = QLabel(tr("cfg.wz_worker_title", default="Datos del trabajador  ·  {label}", label=label))
        lbl.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        self._card_ly.addWidget(lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(self._scroll_ss())
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 16, 0); il.setSpacing(8)

        il.addWidget(self._lbl_s(tr("cfg.wz_f_nombre", default="Nombre completo:")))
        self._inp_nombre = self._mk_inp(tr("cfg.wz_ph_nombre", default="Nombre y apellidos del trabajador"))
        il.addWidget(self._inp_nombre)

        row_nif_nac = QHBoxLayout(); row_nif_nac.setSpacing(8)
        col_nif = QVBoxLayout()
        col_nif.addWidget(self._lbl_s(tr("cfg.wz_f_nif", default="NIF / NIE:")))
        self._inp_nif = self._mk_inp(tr("cfg.wz_ph_idfiscal", default="Identificación fiscal"))
        col_nif.addWidget(self._inp_nif)
        col_nac = QVBoxLayout()
        col_nac.addWidget(self._lbl_s(tr("cfg.wz_f_fnac", default="Fecha de nacimiento:")))
        self._inp_fnac = self._mk_inp(tr("cfg.wz_ph_ddmmaaaa", default="DD/MM/AAAA"))
        col_nac.addWidget(self._inp_fnac)
        row_nif_nac.addLayout(col_nif); row_nif_nac.addLayout(col_nac)
        il.addLayout(row_nif_nac)

        row_ss_nac = QHBoxLayout(); row_ss_nac.setSpacing(8)
        col_ss = QVBoxLayout()
        col_ss.addWidget(self._lbl_s(tr("cfg.wz_f_ss", default="Nº Seguridad Social:")))
        self._inp_ss = self._mk_inp(tr("cfg.wz_ph_afiliacion", default="Número de afiliación"))
        col_ss.addWidget(self._inp_ss)
        col_nacion = QVBoxLayout()
        col_nacion.addWidget(self._lbl_s(tr("cfg.wz_f_nacion", default="Nacionalidad:")))
        self._inp_nacionalidad = self._mk_inp(tr("cfg.wz_ph_nacion", default="Ej: ESPAÑOLA"))
        col_nacion.addWidget(self._inp_nacionalidad)
        row_ss_nac.addLayout(col_ss); row_ss_nac.addLayout(col_nacion)
        il.addLayout(row_ss_nac)

        # Nivel formativo + su código (inline)
        row_nf = QHBoxLayout(); row_nf.setSpacing(8)
        c_form = QVBoxLayout(); c_form.addWidget(self._lbl_s(tr("cfg.wz_f_nivelform", default="Nivel formativo:")))
        self._inp_formativo = self._mk_inp(tr("cfg.wz_ph_nivelform", default="Ej: ESO, Bachillerato, FP, Grado…"))
        c_form.addWidget(self._inp_formativo)
        c_cnf = QVBoxLayout(); c_cnf.addWidget(self._lbl_s(tr("cfg.wz_f_cod_nivelform", default="Cód. nivel formativo:")))
        self._inp_cod_nivelform = self._mk_inp("Ej: 34"); c_cnf.addWidget(self._inp_cod_nivelform)
        row_nf.addLayout(c_form); row_nf.addLayout(c_cnf); il.addLayout(row_nf)

        il.addWidget(self._lbl_s(tr("cfg.wz_f_titulacion", default="Titulación (si procede):")))
        self._inp_titulacion = self._mk_inp(tr("cfg.wz_ph_titulacion", default="Ej: Grado en ADE, FP Comercio…"))
        il.addWidget(self._inp_titulacion)

        # Municipio de domicilio + su código (inline)
        row_mun = QHBoxLayout(); row_mun.setSpacing(8)
        c_mun = QVBoxLayout(); c_mun.addWidget(self._lbl_s(tr("cfg.wz_f_municipio", default="Municipio de domicilio:")))
        self._inp_municipio = self._mk_inp(tr("cfg.wz_ph_municipio", default="Ciudad de residencia"))
        c_mun.addWidget(self._inp_municipio)
        c_cmu = QVBoxLayout(); c_cmu.addWidget(self._lbl_s(tr("cfg.wz_f_cod_municipio", default="Cód. municipio:")))
        self._inp_cod_municipio = self._mk_inp("Ej: 08298"); c_cmu.addWidget(self._inp_cod_municipio)
        row_mun.addLayout(c_mun); row_mun.addLayout(c_cmu); il.addLayout(row_mun)

        # Provincia + su código (inline)
        row_prov = QHBoxLayout(); row_prov.setSpacing(8)
        c_prov = QVBoxLayout(); c_prov.addWidget(self._lbl_s(tr("cfg.wz_f_provincia", default="Provincia:")))
        self._inp_provincia = self._mk_inp(tr("cfg.wz_ph_provincia", default="Provincia de residencia"))
        c_prov.addWidget(self._inp_provincia)
        c_cpr = QVBoxLayout(); c_cpr.addWidget(self._lbl_s(tr("cfg.wz_f_cod_provincia", default="Cód. provincia:")))
        self._inp_cod_provincia = self._mk_inp("Ej: 08"); c_cpr.addWidget(self._inp_cod_provincia)
        row_prov.addLayout(c_prov); row_prov.addLayout(c_cpr); il.addLayout(row_prov)

        # País + su código (inline)
        row_pais = QHBoxLayout(); row_pais.setSpacing(8)
        c_pais = QVBoxLayout(); c_pais.addWidget(self._lbl_s(tr("cfg.wz_f_pais", default="País:")))
        self._inp_pais = self._mk_inp(tr("cfg.wz_ph_pais", default="ESPAÑA")); self._inp_pais.setText("ESPAÑA")
        c_pais.addWidget(self._inp_pais)
        c_cpa = QVBoxLayout(); c_cpa.addWidget(self._lbl_s(tr("cfg.wz_f_cod_pais", default="Cód. país (ej. 724):")))
        self._inp_cod_pais = self._mk_inp("Ej: 724"); c_cpa.addWidget(self._inp_cod_pais)
        row_pais.addLayout(c_pais); row_pais.addLayout(c_cpa); il.addLayout(row_pais)

        # Código postal + Sexo
        row_cp_sx = QHBoxLayout(); row_cp_sx.setSpacing(8)
        c_cp = QVBoxLayout(); c_cp.addWidget(self._lbl_s(tr("cfg.wz_f_cp", default="Código postal:")))
        self._inp_cp = self._mk_inp(tr("cfg.wz_ph_cp", default="Ej: 08500"))
        c_cp.addWidget(self._inp_cp)
        c_sexo = QVBoxLayout(); c_sexo.addWidget(self._lbl_s(tr("cfg.wz_f_sexo", default="Sexo:")))
        self._combo_sexo = self._mk_combo(["—", "MUJER", "HOMBRE", "OTRO"])
        c_sexo.addWidget(self._combo_sexo)
        row_cp_sx.addLayout(c_cp); row_cp_sx.addLayout(c_sexo); il.addLayout(row_cp_sx)

        # Teléfono + Correo
        row_tel_mail = QHBoxLayout(); row_tel_mail.setSpacing(8)
        c_tel = QVBoxLayout(); c_tel.addWidget(self._lbl_s(tr("cfg.wz_f_telefono", default="Teléfono:")))
        self._inp_telefono = self._mk_inp(tr("cfg.wz_ph_telefono", default="Ej: 600 000 000"))
        c_tel.addWidget(self._inp_telefono)
        c_mail = QVBoxLayout(); c_mail.addWidget(self._lbl_s(tr("cfg.wz_f_email", default="Correo electrónico:")))
        self._inp_email = self._mk_inp(tr("cfg.wz_ph_email", default="correo@ejemplo.com"))
        c_mail.addWidget(self._inp_email)
        row_tel_mail.addLayout(c_tel); row_tel_mail.addLayout(c_mail)
        il.addLayout(row_tel_mail)

        il.addStretch()
        scroll.setWidget(inner)
        self._card_ly.addWidget(scroll, 1)

        br = QHBoxLayout(); br.addStretch()
        bs = self._nav_btn(tr("cfg.nav_next", default="SIGUIENTE  →")); bs.clicked.connect(self._save_p1)
        br.addWidget(bs)
        self._card_ly.addLayout(br)

    def _p1_fiscal(self):
        label = self._doc_label()
        lbl = QLabel(tr("cfg.wz_fiscal_title", default="Datos de empresa y período  ·  {label}", label=label))
        lbl.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        self._card_ly.addWidget(lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(self._scroll_ss())
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 16, 0); il.setSpacing(8)

        # Load empresa data for auto-populate
        emp: dict = {}
        emp_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "datos_empresa.json")
        )
        if os.path.exists(emp_path):
            try:
                with open(emp_path, encoding="utf-8") as _f:
                    emp = json.load(_f)
            except Exception:
                pass

        il.addWidget(self._sep_lbl(tr("cfg.wz_sep_emisora", default="EMPRESA EMISORA")))
        il.addWidget(self._lbl_s(tr("cfg.wz_f_razon", default="Razón social:")))
        self._inp_emp_nombre = self._mk_inp(tr("cfg.wz_ph_razon", default="Nombre legal de la empresa"))
        self._inp_emp_nombre.setText(emp.get("razon_social", ""))
        il.addWidget(self._inp_emp_nombre)

        row_cif_dir = QHBoxLayout(); row_cif_dir.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s(tr("cfg.wz_f_cif", default="CIF / NIF:")))
        self._inp_emp_cif = self._mk_inp(tr("cfg.wz_ph_cif", default="Ej: B12345678"))
        self._inp_emp_cif.setText(emp.get("cif", ""))
        c1.addWidget(self._inp_emp_cif)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s(tr("cfg.wz_f_dirfiscal", default="Dirección fiscal:")))
        self._inp_emp_dir = self._mk_inp(tr("cfg.wz_ph_dir", default="Calle, número, ciudad"))
        self._inp_emp_dir.setText(emp.get("direccion", ""))
        c2.addWidget(self._inp_emp_dir)
        row_cif_dir.addLayout(c1); row_cif_dir.addLayout(c2)
        il.addLayout(row_cif_dir)

        il.addWidget(self._sep_lbl(tr("cfg.wz_sep_periodo", default="PERÍODO")))
        row_dates = QHBoxLayout(); row_dates.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s(tr("cfg.wz_f_fini", default="Fecha inicio (DD/MM/AAAA):")))
        self._inp_periodo_ini = self._mk_inp("01/01/" + str(datetime.now().year))
        c3.addWidget(self._inp_periodo_ini)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s(tr("cfg.wz_f_ffin", default="Fecha fin (DD/MM/AAAA):")))
        self._inp_periodo_fin = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_periodo_fin.setText(datetime.now().strftime("%d/%m/%Y"))
        c4.addWidget(self._inp_periodo_fin)
        row_dates.addLayout(c3); row_dates.addLayout(c4)
        il.addLayout(row_dates)

        il.addStretch()
        scroll.setWidget(inner)
        self._card_ly.addWidget(scroll, 1)

        br = QHBoxLayout(); br.addStretch()
        bs = self._nav_btn(tr("cfg.nav_next", default="SIGUIENTE  →")); bs.clicked.connect(self._save_p1)
        br.addWidget(bs)
        self._card_ly.addLayout(br)

    def _save_p1(self):
        if self._tipo in self._FISCAL_TYPES:
            self._datos["emp_nombre"] = self._inp_emp_nombre.text().strip()
            self._datos["emp_cif"] = self._inp_emp_cif.text().strip()
            self._datos["emp_dir"] = self._inp_emp_dir.text().strip()
            self._datos["periodo_ini"] = self._inp_periodo_ini.text().strip()
            self._datos["periodo_fin"] = self._inp_periodo_fin.text().strip()
        else:
            self._datos["trabajador"] = self._inp_nombre.text().strip()
            self._datos["nif"] = self._inp_nif.text().strip()
            self._datos["fecha_nacimiento"] = self._inp_fnac.text().strip()
            self._datos["ss"] = self._inp_ss.text().strip()
            self._datos["nacionalidad"] = self._inp_nacionalidad.text().strip()
            self._datos["nivel_formativo"] = self._inp_formativo.text().strip()
            self._datos["municipio_domicilio"] = self._inp_municipio.text().strip()
            self._datos["provincia_domicilio"] = self._inp_provincia.text().strip()
            self._datos["cp_domicilio"] = self._inp_cp.text().strip()
            self._datos["pais_domicilio"] = self._inp_pais.text().strip()
            sx = self._combo_sexo.currentText()
            self._datos["sexo"] = "" if sx == "—" else sx
            self._datos["telefono_trab"] = self._inp_telefono.text().strip()
            self._datos["email_trab"] = self._inp_email.text().strip()
            self._datos["titulacion"] = self._inp_titulacion.text().strip()
            self._datos["cod_pais_dom"] = self._inp_cod_pais.text().strip()
            self._datos["cod_provincia_dom"] = self._inp_cod_provincia.text().strip()
            self._datos["cod_municipio_dom"] = self._inp_cod_municipio.text().strip()
            self._datos["cod_nivel_formativo"] = self._inp_cod_nivelform.text().strip()
        self._ir(1)

    def _mk_check(self, txt):
        return _NeonCheckBox(txt)

    def _sep_lbl(self, txt):
        l = QLabel(f"  {_wz_tr(txt)}")
        l.setStyleSheet(
            f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:11px;"
            f"background:#161B22;border:none;border-radius:6px;padding:4px 10px;"
        )
        return l

    def _p2_scroll(self):
        """Returns (scroll, inner_widget, inner_layout) ready to populate."""
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(self._scroll_ss())
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 16, 0); il.setSpacing(8)
        return scroll, inner, il

    def _p2_nav(self):
        br = QHBoxLayout()
        ba = self._nav_btn(tr("cfg.nav_prev", default="←  ANTERIOR"), "#F85149"); ba.clicked.connect(lambda: self._ir(-1))
        bs = self._nav_btn(tr("cfg.nav_next", default="SIGUIENTE  →")); bs.clicked.connect(self._save_p2)
        br.addWidget(ba); br.addStretch(); br.addWidget(bs)
        self._card_ly.addLayout(br)

    def _p2_obs(self, il):
        il.addWidget(self._lbl_s(tr("cfg.wz_obs_label", default="Observaciones / Notas adicionales:")))
        self._inp_obs = QTextEdit()
        self._inp_obs.setPlaceholderText(tr("cfg.wz_obs_ph", default="Información adicional relevante..."))
        self._inp_obs.setMinimumHeight(60); self._inp_obs.setMaximumHeight(100)
        self._inp_obs.setStyleSheet(
            f"QTextEdit{{background:#161B22;color:white;border:2px solid {_BORDE};"
            f"border-radius:10px;padding:8px 14px;font-family:'Segoe UI';font-weight:bold;"
            f"font-size:13px;}}QTextEdit:focus{{border-color:{_CIAN};}}"
        )
        il.addWidget(self._inp_obs)

    def _p2_fecha_label(self, il, txt=None):
        if txt is None:
            txt = tr("cfg.wz_fecha_efecto", default="Fecha de efecto (DD/MM/AAAA):")
        il.addWidget(self._lbl_s(txt))
        self._inp_fecha = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_fecha.setText(datetime.now().strftime("%d/%m/%Y"))
        il.addWidget(self._inp_fecha)

    def _p2(self):
        label = self._doc_label()
        lbl = QLabel(tr("cfg.wz_config_title", default="Configure los datos  ·  {label}", label=label))
        lbl.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        self._card_ly.addWidget(lbl)
        dispatch = {
            "CONTRATO":       self._p2_CONTRATO,
            "NÓMINA":         self._p2_NOMINA,
            "ALTA":           self._p2_ALTA,
            "BAJA":           self._p2_BAJA,
            "CERTIFICADO":    self._p2_CERTIFICADO,
            "CERT LABORAL":   self._p2_CERT_LABORAL,
            "CARTA DESPIDO":  self._p2_CARTA_DESPIDO,
            "FINIQUITO":      self._p2_FINIQUITO,
            "VACACIONES":     self._p2_VACACIONES,
            "RESUMEN FISCAL": self._p2_RESUMEN_FISCAL,
            "LIBRO INGRESOS": self._p2_LIBRO_INGRESOS,
            "LIBRO GASTOS":   self._p2_LIBRO_GASTOS,
            "INFORME AUDIT":  self._p2_INFORME_AUDIT,
        }
        dispatch.get(self._tipo, self._p2_generico)()

    def _p2_CONTRATO(self):
        _, subtypes = self.DOCS["CONTRATO"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Modalidad de contrato:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        self._p2_fecha_label(il, "Fecha de inicio:")
        il.addWidget(self._lbl_s("Fecha fin (solo temporal / sustitución / prácticas):"))
        self._inp_fecha_fin = self._mk_inp("DD/MM/AAAA")
        il.addWidget(self._inp_fecha_fin)

        il.addWidget(self._sep_lbl("PUESTO DE TRABAJO"))
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Puesto / Cargo:"))
        self._inp_puesto = self._mk_inp("Ej: Colaborador Tienda, Cajero/a…")
        c1.addWidget(self._inp_puesto)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Grupo profesional:"))
        self._inp_grupo = self._mk_inp("Ej: Grupo 4, Vendedor 2º")
        c2.addWidget(self._inp_grupo)
        row1.addLayout(c1); row1.addLayout(c2)
        il.addLayout(row1)
        il.addWidget(self._lbl_s("Funciones principales:"))
        self._inp_funciones = self._mk_inp("Descripción breve de las funciones")
        il.addWidget(self._inp_funciones)
        il.addWidget(self._lbl_s("Centro de trabajo (registrado en DATOS DE EMPRESA):"))
        self._combo_centro = self._mk_combo_centros()
        il.addWidget(self._combo_centro)
        il.addWidget(self._lbl_s("Representante legal (firmante del contrato):"))
        self._combo_rep = self._mk_combo_representantes()
        il.addWidget(self._combo_rep)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Trabajo a distancia:"))
        self._combo_distancia = self._mk_combo(["NO", "SÍ"])
        c3.addWidget(self._combo_distancia)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Tipo de jornada:"))
        self._combo_jornada = self._mk_combo(["TIEMPO COMPLETO", "TIEMPO PARCIAL"])
        c4.addWidget(self._combo_jornada)
        row2.addLayout(c3); row2.addLayout(c4)
        il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Horas semanales:"))
        self._inp_horas = self._mk_inp("Ej: 40 / 20")
        c5.addWidget(self._inp_horas)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Distribución horaria:"))
        self._inp_distribucion = self._mk_inp("Ej: LUNES A DOMINGO")
        c6.addWidget(self._inp_distribucion)
        row3.addLayout(c5); row3.addLayout(c6)
        il.addLayout(row3)

        il.addWidget(self._sep_lbl("RETRIBUCIÓN Y CONTRATO"))
        row4 = QHBoxLayout(); row4.setSpacing(8)
        c7 = QVBoxLayout(); c7.addWidget(self._lbl_s("Salario bruto anual (€):"))
        self._inp_sal = self._mk_inp("Ej: 18000.00")
        c7.addWidget(self._inp_sal)
        c8 = QVBoxLayout(); c8.addWidget(self._lbl_s("Nº de pagas:"))
        self._combo_pagas = self._mk_combo(["12", "14"])
        c8.addWidget(self._combo_pagas)
        row4.addLayout(c7); row4.addLayout(c8)
        il.addLayout(row4)
        row5 = QHBoxLayout(); row5.setSpacing(8)
        c9 = QVBoxLayout(); c9.addWidget(self._lbl_s("Período de prueba:"))
        self._inp_prueba = self._mk_inp("Ej: TRES MESES")
        c9.addWidget(self._inp_prueba)
        c10 = QVBoxLayout(); c10.addWidget(self._lbl_s("Vacaciones:"))
        self._inp_vacaciones = self._mk_inp("Ej: Según Convenio / 23 días hábiles")
        c10.addWidget(self._inp_vacaciones)
        row5.addLayout(c9); row5.addLayout(c10)
        il.addLayout(row5)
        il.addWidget(self._lbl_s("Convenio colectivo aplicable:"))
        self._inp_convenio = self._mk_inp("Ej: Convenio Colectivo del Comercio Textil de Barcelona")
        il.addWidget(self._inp_convenio)

        il.addWidget(self._sep_lbl("ASISTENCIA LEGAL DE LOS TRABAJADORES"))
        il.addWidget(self._lbl_s("Tipo de representación:"))
        self._combo_asist = self._mk_combo([
            "No procede", "Comité de Empresa", "Delegado Sindical",
            "Representación Legal de los Trabajadores",
        ])
        il.addWidget(self._combo_asist)
        row_as1 = QHBoxLayout(); row_as1.setSpacing(8)
        ca1 = QVBoxLayout(); ca1.addWidget(self._lbl_s("Nombre y apellidos:"))
        self._inp_asist_nombre = self._mk_inp("Nombre del representante"); ca1.addWidget(self._inp_asist_nombre)
        ca2 = QVBoxLayout(); ca2.addWidget(self._lbl_s("DNI / NIE:"))
        self._inp_asist_nif = self._mk_inp("Identificación"); ca2.addWidget(self._inp_asist_nif)
        row_as1.addLayout(ca1); row_as1.addLayout(ca2); il.addLayout(row_as1)
        row_as2 = QHBoxLayout(); row_as2.setSpacing(8)
        ca3 = QVBoxLayout(); ca3.addWidget(self._lbl_s("Cargo:"))
        self._inp_asist_cargo = self._mk_inp("Ej: Presidente del comité"); ca3.addWidget(self._inp_asist_cargo)
        ca4 = QVBoxLayout(); ca4.addWidget(self._lbl_s("Organización / sindicato:"))
        self._inp_asist_org = self._mk_inp("Ej: CCOO, UGT…"); ca4.addWidget(self._inp_asist_org)
        row_as2.addLayout(ca3); row_as2.addLayout(ca4); il.addLayout(row_as2)

        il.addWidget(self._sep_lbl("COFINANCIACIÓN / LOGOS INSTITUCIONALES"))
        self._chk_fse = self._mk_check(
            "Contrato cofinanciado — mostrar logos institucionales en la cabecera (FSE+ / UE / Ministerio / SEPE)")
        self._chk_fse.setChecked(True)  # por defecto marcado (modelo SEPE/FSE)
        il.addWidget(self._chk_fse)

        il.addWidget(self._sep_lbl("CLÁUSULAS ADICIONALES (ANEXO)"))
        _clauses = [
            "Prorrateo de pagas extraordinarias",
            "Obligaciones de no competencia desleal (arts. 4.1 y 21.1 ET)",
            "Uso restringido de Internet y correo corporativo",
            "Protección de datos personales (LOPDGDD 3/2018)",
            "Compensación de horas extra con descanso",
            "Interrupción del período de prueba por IT/nacimiento",
            "Vacaciones en días laborables",
            "Obligación de comunicar baja/alta médica de forma inmediata",
        ]
        self._checks_adicionales = []
        for clause_txt in _clauses:
            cb_check = self._mk_check(clause_txt); cb_check.setChecked(True)
            il.addWidget(cb_check); self._checks_adicionales.append((clause_txt, cb_check))
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_NOMINA(self):
        scroll, inner, il = self._p2_scroll()
        self._p2_fecha_label(il, "Mes/período nómina (DD/MM/AAAA):")
        il.addWidget(self._sep_lbl("DEVENGOS"))
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Salario base mensual (€):"))
        self._inp_sal = self._mk_inp("Ej: 1200.00")
        c1.addWidget(self._inp_sal)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Nº de pagas:"))
        self._combo_pagas = self._mk_combo(["12", "14"])
        c2.addWidget(self._combo_pagas)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Plus transporte (€):"))
        self._inp_plus_trans = self._mk_inp("Ej: 50.00")
        c3.addWidget(self._inp_plus_trans)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Plus convenio (€):"))
        self._inp_plus = self._mk_inp("Ej: 30.00")
        c4.addWidget(self._inp_plus)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Nocturnidad (€):"))
        self._inp_noct = self._mk_inp("Ej: 0.00")
        c5.addWidget(self._inp_noct)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Horas extra (€):"))
        self._inp_he = self._mk_inp("Ej: 0.00")
        c6.addWidget(self._inp_he)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        row4 = QHBoxLayout(); row4.setSpacing(8)
        c7 = QVBoxLayout(); c7.addWidget(self._lbl_s("Incentivos / Bonus (€):"))
        self._inp_bonus = self._mk_inp("Ej: 0.00")
        c7.addWidget(self._inp_bonus)
        c8 = QVBoxLayout(); c8.addWidget(self._lbl_s("Dietas (€):"))
        self._inp_dietas = self._mk_inp("Ej: 0.00")
        c8.addWidget(self._inp_dietas)
        row4.addLayout(c7); row4.addLayout(c8); il.addLayout(row4)
        il.addWidget(self._sep_lbl("DEDUCCIONES"))
        row5 = QHBoxLayout(); row5.setSpacing(8)
        c9 = QVBoxLayout(); c9.addWidget(self._lbl_s("IRPF (%):"))
        self._inp_irpf = self._mk_inp("Ej: 15.00")
        c9.addWidget(self._inp_irpf)
        c10 = QVBoxLayout(); c10.addWidget(self._lbl_s("SS trabajador (%):"))
        self._inp_ss_pct = self._mk_inp("Ej: 6.35")
        c10.addWidget(self._inp_ss_pct)
        row5.addLayout(c9); row5.addLayout(c10); il.addLayout(row5)
        row6 = QHBoxLayout(); row6.setSpacing(8)
        c11 = QVBoxLayout(); c11.addWidget(self._lbl_s("Anticipos (€):"))
        self._inp_anticipos = self._mk_inp("Ej: 0.00")
        c11.addWidget(self._inp_anticipos)
        c12 = QVBoxLayout(); c12.addWidget(self._lbl_s("Embargos (€):"))
        self._inp_embargos = self._mk_inp("Ej: 0.00")
        c12.addWidget(self._inp_embargos)
        row6.addLayout(c11); row6.addLayout(c12); il.addLayout(row6)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_ALTA(self):
        scroll, inner, il = self._p2_scroll()
        self._p2_fecha_label(il, "Fecha de alta:")
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Tipo de contrato:"))
        self._combo_sub = self._mk_combo(["INDEFINIDO", "TEMPORAL", "FIJO DISCONTINUO", "PARCIAL", "PRÁCTICAS"])
        c1.addWidget(self._combo_sub)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Tipo de jornada:"))
        self._combo_jornada = self._mk_combo(["TIEMPO COMPLETO", "TIEMPO PARCIAL"])
        c2.addWidget(self._combo_jornada)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._lbl_s("Horario de trabajo:"))
        self._inp_distribucion = self._mk_inp("Ej: L-V 09:00-17:00")
        il.addWidget(self._inp_distribucion)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Categoría profesional:"))
        self._inp_puesto = self._mk_inp("Ej: Técnico, Auxiliar…")
        c3.addWidget(self._inp_puesto)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Convenio colectivo:"))
        self._inp_convenio = self._mk_inp("Convenio aplicable")
        c4.addWidget(self._inp_convenio)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        il.addWidget(self._lbl_s("Centro de trabajo:"))
        self._inp_centro = self._mk_inp("Dirección del centro")
        il.addWidget(self._inp_centro)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Salario bruto anual (€):"))
        self._inp_sal = self._mk_inp("Ej: 18000.00")
        c5.addWidget(self._inp_sal)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("IRPF (%):"))
        self._inp_irpf = self._mk_inp("Ej: 15.00")
        c6.addWidget(self._inp_irpf)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        il.addWidget(self._lbl_s("Cuenta bancaria IBAN:"))
        self._inp_iban = self._mk_inp("ES00 0000 0000 0000 0000 0000")
        il.addWidget(self._inp_iban)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_BAJA(self):
        _, subtypes = self.DOCS["BAJA"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de baja:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        self._p2_fecha_label(il, "Fecha de efecto de la baja:")
        il.addWidget(self._lbl_s("Motivo (descripción):"))
        self._inp_motivo_baja = self._mk_inp("Descripción del motivo")
        il.addWidget(self._inp_motivo_baja)
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Vacaciones pendientes (días):"))
        self._inp_vac_dias = self._mk_inp("Ej: 5")
        c1.addWidget(self._inp_vac_dias)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Entrega de material empresa:"))
        self._combo_material = self._mk_combo(["SÍ", "NO"])
        c2.addWidget(self._combo_material)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_CERTIFICADO(self):
        _, subtypes = self.DOCS["CERTIFICADO"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de certificado:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        self._p2_fecha_label(il, "Fecha de emisión:")
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha inicio relación laboral:"))
        self._inp_f_inicio_rel = self._mk_inp("DD/MM/AAAA")
        c1.addWidget(self._inp_f_inicio_rel)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha fin relación laboral:"))
        self._inp_f_fin_rel = self._mk_inp("DD/MM/AAAA o EN ACTIVO")
        c2.addWidget(self._inp_f_fin_rel)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Tipo de contrato:"))
        self._combo_jornada = self._mk_combo(["INDEFINIDO", "TEMPORAL", "FIJO DISCONTINUO", "PARCIAL"])
        c3.addWidget(self._combo_jornada)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Grupo de cotización:"))
        self._inp_grupo = self._mk_inp("Ej: Grupo 5")
        c4.addWidget(self._inp_grupo)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Base cotización (€/mes):"))
        self._inp_base_cot = self._mk_inp("Ej: 1500.00")
        c5.addWidget(self._inp_base_cot)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Base desempleo (€/mes):"))
        self._inp_base_desempleo = self._mk_inp("Ej: 1500.00")
        c6.addWidget(self._inp_base_desempleo)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        row4 = QHBoxLayout(); row4.setSpacing(8)
        c7 = QVBoxLayout(); c7.addWidget(self._lbl_s("Vacaciones pendientes (días):"))
        self._inp_vac_dias = self._mk_inp("Ej: 0")
        c7.addWidget(self._inp_vac_dias)
        c8 = QVBoxLayout(); c8.addWidget(self._lbl_s("Pagas extras pendientes:"))
        self._combo_pagas_pend = self._mk_combo(["Ninguna", "Proporcional", "Completas"])
        c8.addWidget(self._combo_pagas_pend)
        row4.addLayout(c7); row4.addLayout(c8); il.addLayout(row4)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_CERT_LABORAL(self):
        _, subtypes = self.DOCS["CERT LABORAL"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de certificado:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        self._p2_fecha_label(il, "Fecha de emisión:")
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Cargo / Puesto actual:"))
        self._inp_puesto = self._mk_inp("Ej: Responsable de Tienda")
        c1.addWidget(self._inp_puesto)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Antigüedad (desde DD/MM/AAAA):"))
        self._inp_antiguedad = self._mk_inp("Fecha de incorporación")
        c2.addWidget(self._inp_antiguedad)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._lbl_s("Funciones principales:"))
        self._inp_funciones = self._mk_inp("Descripción de las funciones")
        il.addWidget(self._inp_funciones)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Horario de trabajo:"))
        self._inp_distribucion = self._mk_inp("Ej: L-V 09:00-17:00")
        c3.addWidget(self._inp_distribucion)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Salario bruto anual (€):"))
        self._inp_sal = self._mk_inp("Ej: 18000.00")
        c4.addWidget(self._inp_sal)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_CARTA_DESPIDO(self):
        _, subtypes = self.DOCS["CARTA DESPIDO"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de despido:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha de comunicación:"))
        self._inp_fecha = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_fecha.setText(datetime.now().strftime("%d/%m/%Y"))
        c1.addWidget(self._inp_fecha)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha de efecto:"))
        self._inp_fecha_efecto = self._mk_inp("DD/MM/AAAA")
        c2.addWidget(self._inp_fecha_efecto)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._lbl_s("Artículo del ET invocado:"))
        self._inp_art_et = self._mk_inp("Ej: Art. 54 ET (disciplinario) / Art. 52 ET (objetivo)")
        il.addWidget(self._inp_art_et)
        il.addWidget(self._lbl_s("Descripción de los hechos:"))
        self._inp_hechos = QTextEdit()
        self._inp_hechos.setPlaceholderText(_wz_tr("Descripción detallada de los hechos imputados…"))
        self._inp_hechos.setMinimumHeight(70); self._inp_hechos.setMaximumHeight(100)
        self._inp_hechos.setStyleSheet(
            f"QTextEdit{{background:#161B22;color:white;border:2px solid {_BORDE};"
            f"border-radius:10px;padding:8px 14px;font-family:'Segoe UI';font-weight:bold;"
            f"font-size:13px;}}QTextEdit:focus{{border-color:{_CIAN};}}"
        )
        il.addWidget(self._inp_hechos)
        il.addWidget(self._sep_lbl("PRECEDENTES"))
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Advertencias previas:"))
        self._combo_advertencias = self._mk_combo(["SÍ", "NO"])
        c3.addWidget(self._combo_advertencias)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Expedientes disciplinarios previos:"))
        self._combo_expedientes = self._mk_combo(["SÍ", "NO"])
        c4.addWidget(self._combo_expedientes)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        il.addWidget(self._sep_lbl("LIQUIDACIÓN"))
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Indemnización (€):"))
        self._inp_indemnizacion = self._mk_inp("Ej: 0.00")
        c5.addWidget(self._inp_indemnizacion)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Vacaciones pendientes (días):"))
        self._inp_vac_dias = self._mk_inp("Ej: 5")
        c6.addWidget(self._inp_vac_dias)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_FINIQUITO(self):
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de baja:"))
        self._combo_sub = self._mk_combo(["VOLUNTARIA", "FIN CONTRATO", "DESPIDO", "JUBILACIÓN", "INCAPACIDAD"])
        il.addWidget(self._combo_sub)
        self._p2_fecha_label(il, "Fecha de baja:")
        il.addWidget(self._sep_lbl("CONCEPTOS A LIQUIDAR"))
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Salario bruto mensual (€):"))
        self._inp_sal = self._mk_inp("Ej: 1500.00")
        c1.addWidget(self._inp_sal)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Días trabajados pendientes:"))
        self._inp_dias_pend = self._mk_inp("Ej: 10")
        c2.addWidget(self._inp_dias_pend)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Vacaciones pendientes (días):"))
        self._inp_vac_dias = self._mk_inp("Ej: 5")
        c3.addWidget(self._inp_vac_dias)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Pagas extras pendientes:"))
        self._combo_pagas_pend = self._mk_combo(["Proporcional", "Ninguna", "Completas"])
        c4.addWidget(self._combo_pagas_pend)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Horas extra pendientes (€):"))
        self._inp_he = self._mk_inp("Ej: 0.00")
        c5.addWidget(self._inp_he)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Indemnización (€):"))
        self._inp_indemnizacion = self._mk_inp("Ej: 0.00")
        c6.addWidget(self._inp_indemnizacion)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        il.addWidget(self._lbl_s("Anticipos descontados (€):"))
        self._inp_anticipos = self._mk_inp("Ej: 0.00")
        il.addWidget(self._inp_anticipos)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_VACACIONES(self):
        _, subtypes = self.DOCS["VACACIONES"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de documento:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha de inicio (DD/MM/AAAA):"))
        self._inp_fecha = self._mk_inp("DD/MM/AAAA")
        c1.addWidget(self._inp_fecha)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha de fin (DD/MM/AAAA):"))
        self._inp_fecha_fin_vac = self._mk_inp("DD/MM/AAAA")
        c2.addWidget(self._inp_fecha_fin_vac)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._lbl_s("Responsable / Aprobado por:"))
        self._inp_responsable = self._mk_inp("Nombre del responsable que aprueba/deniega")
        il.addWidget(self._inp_responsable)
        il.addWidget(self._lbl_s("Motivo de rechazo (solo si DENEGACIÓN):"))
        self._inp_motivo_baja = self._mk_inp("Dejar vacío si no aplica")
        il.addWidget(self._inp_motivo_baja)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_RESUMEN_FISCAL(self):
        _, subtypes = self.DOCS["RESUMEN FISCAL"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Período:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Trimestre (1-4) o Año:"))
        self._inp_trimestre = self._mk_inp("Ej: 1 / 2025")
        c1.addWidget(self._inp_trimestre)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Ejercicio fiscal:"))
        self._inp_ejercicio = self._mk_inp(str(datetime.now().year))
        self._inp_ejercicio.setText(str(datetime.now().year))
        c2.addWidget(self._inp_ejercicio)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._sep_lbl("IMPORTES"))
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Total ingresos (€):"))
        self._inp_tot_ingresos = self._mk_inp("Ej: 10000.00")
        c3.addWidget(self._inp_tot_ingresos)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("IVA repercutido (€):"))
        self._inp_iva_rep = self._mk_inp("Ej: 2100.00")
        c4.addWidget(self._inp_iva_rep)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("IVA soportado (€):"))
        self._inp_iva_sop = self._mk_inp("Ej: 800.00")
        c5.addWidget(self._inp_iva_sop)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("Gastos deducibles (€):"))
        self._inp_gastos_ded = self._mk_inp("Ej: 500.00")
        c6.addWidget(self._inp_gastos_ded)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_LIBRO_INGRESOS(self):
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._sep_lbl(tr("cfg.wz_sep_periodo", default="PERÍODO")))
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha inicio:"))
        self._inp_fecha = self._mk_inp("01/01/" + str(datetime.now().year))
        c1.addWidget(self._inp_fecha)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha fin:"))
        self._inp_fecha_fin_vac = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_fecha_fin_vac.setText(datetime.now().strftime("%d/%m/%Y"))
        c2.addWidget(self._inp_fecha_fin_vac)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._sep_lbl("TOTALES DEL PERÍODO"))
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("Facturas emitidas (nº):"))
        self._inp_num_facturas = self._mk_inp("Ej: 25")
        c3.addWidget(self._inp_num_facturas)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Nº de clientes:"))
        self._inp_num_clientes = self._mk_inp("Ej: 12")
        c4.addWidget(self._inp_num_clientes)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Importe total s/IVA (€):"))
        self._inp_tot_ingresos = self._mk_inp("Ej: 15000.00")
        c5.addWidget(self._inp_tot_ingresos)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("IVA repercutido total (€):"))
        self._inp_iva_rep = self._mk_inp("Ej: 3150.00")
        c6.addWidget(self._inp_iva_rep)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_LIBRO_GASTOS(self):
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._sep_lbl(tr("cfg.wz_sep_periodo", default="PERÍODO")))
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha inicio:"))
        self._inp_fecha = self._mk_inp("01/01/" + str(datetime.now().year))
        c1.addWidget(self._inp_fecha)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha fin:"))
        self._inp_fecha_fin_vac = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_fecha_fin_vac.setText(datetime.now().strftime("%d/%m/%Y"))
        c2.addWidget(self._inp_fecha_fin_vac)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._sep_lbl("PROVEEDOR PRINCIPAL"))
        il.addWidget(self._lbl_s("Proveedor:"))
        self._inp_proveedor = self._mk_inp("Nombre o razón social del proveedor")
        il.addWidget(self._inp_proveedor)
        row2 = QHBoxLayout(); row2.setSpacing(8)
        c3 = QVBoxLayout(); c3.addWidget(self._lbl_s("CIF proveedor:"))
        self._inp_cif_prov = self._mk_inp("Ej: B87654321")
        c3.addWidget(self._inp_cif_prov)
        c4 = QVBoxLayout(); c4.addWidget(self._lbl_s("Fecha factura:"))
        self._inp_f_factura = self._mk_inp("DD/MM/AAAA")
        c4.addWidget(self._inp_f_factura)
        row2.addLayout(c3); row2.addLayout(c4); il.addLayout(row2)
        il.addWidget(self._lbl_s("Concepto:"))
        self._inp_concepto_gasto = self._mk_inp("Descripción del gasto")
        il.addWidget(self._inp_concepto_gasto)
        row3 = QHBoxLayout(); row3.setSpacing(8)
        c5 = QVBoxLayout(); c5.addWidget(self._lbl_s("Importe s/IVA (€):"))
        self._inp_tot_ingresos = self._mk_inp("Ej: 1000.00")
        c5.addWidget(self._inp_tot_ingresos)
        c6 = QVBoxLayout(); c6.addWidget(self._lbl_s("IVA soportado (€):"))
        self._inp_iva_sop = self._mk_inp("Ej: 210.00")
        c6.addWidget(self._inp_iva_sop)
        row3.addLayout(c5); row3.addLayout(c6); il.addLayout(row3)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_INFORME_AUDIT(self):
        _, subtypes = self.DOCS["INFORME AUDIT"]
        scroll, inner, il = self._p2_scroll()
        il.addWidget(self._lbl_s("Tipo de informe:"))
        self._combo_sub = self._mk_combo(subtypes)
        il.addWidget(self._combo_sub)
        row1 = QHBoxLayout(); row1.setSpacing(8)
        c1 = QVBoxLayout(); c1.addWidget(self._lbl_s("Fecha inicio (DD/MM/AAAA):"))
        self._inp_fecha = self._mk_inp("DD/MM/AAAA")
        c1.addWidget(self._inp_fecha)
        c2 = QVBoxLayout(); c2.addWidget(self._lbl_s("Fecha fin (DD/MM/AAAA):"))
        self._inp_fecha_fin_vac = self._mk_inp(datetime.now().strftime("%d/%m/%Y"))
        self._inp_fecha_fin_vac.setText(datetime.now().strftime("%d/%m/%Y"))
        c2.addWidget(self._inp_fecha_fin_vac)
        row1.addLayout(c1); row1.addLayout(c2); il.addLayout(row1)
        il.addWidget(self._lbl_s("Empleados incluidos en el filtro (vacío = todos):"))
        self._inp_filtro_emp = self._mk_inp("Nombre/s o NIF separados por coma")
        il.addWidget(self._inp_filtro_emp)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _p2_generico(self):
        """Fallback for any document type not yet mapped."""
        _, subtypes = self.DOCS.get(self._tipo, ("", []))
        scroll, inner, il = self._p2_scroll()
        if subtypes:
            il.addWidget(self._lbl_s("Subtipo / Modalidad:"))
            self._combo_sub = self._mk_combo(subtypes)
            il.addWidget(self._combo_sub)
        self._p2_fecha_label(il)
        self._p2_obs(il); il.addStretch()
        scroll.setWidget(inner); self._card_ly.addWidget(scroll, 1); self._p2_nav()

    def _save_p2(self):
        def _t(attr): return getattr(self, attr).text().strip() if hasattr(self, attr) else ""
        def _cb(attr): return getattr(self, attr).currentText() if hasattr(self, attr) else ""
        def _te(attr): return getattr(self, attr).toPlainText().strip() if hasattr(self, attr) else ""

        if hasattr(self, "_inp_fecha"):
            self._datos["fecha"] = _t("_inp_fecha")
        if hasattr(self, "_combo_sub"):
            self._datos["subtipo"] = _cb("_combo_sub")

        # Worker fields
        for key, attr in [
            ("puesto", "_inp_puesto"), ("grupo_prof", "_inp_grupo"),
            ("funciones", "_inp_funciones"), ("centro_trabajo", "_inp_centro"),
            ("horas_semanales", "_inp_horas"), ("distribucion", "_inp_distribucion"),
            ("periodo_prueba", "_inp_prueba"), ("vacaciones", "_inp_vacaciones"),
            ("convenio", "_inp_convenio"), ("salario", "_inp_sal"),
            ("iban", "_inp_iban"), ("antiguedad", "_inp_antiguedad"),
            ("base_cotizacion", "_inp_base_cot"), ("base_desempleo", "_inp_base_desempleo"),
            ("vacaciones_dias", "_inp_vac_dias"), ("articulo_et", "_inp_art_et"),
            ("motivo_baja", "_inp_motivo_baja"), ("responsable", "_inp_responsable"),
            ("indemnizacion", "_inp_indemnizacion"), ("dias_pendientes", "_inp_dias_pend"),
            ("anticipos", "_inp_anticipos"), ("embargos", "_inp_embargos"),
            ("fecha_efecto_2", "_inp_fecha_efecto"), ("fecha_fin_vac", "_inp_fecha_fin_vac"),
            ("f_inicio_rel", "_inp_f_inicio_rel"), ("f_fin_rel", "_inp_f_fin_rel"),
            ("filtro_emp", "_inp_filtro_emp"), ("fecha_fin", "_inp_fecha_fin"),
            ("asist_nombre", "_inp_asist_nombre"), ("asist_nif", "_inp_asist_nif"),
            ("asist_cargo", "_inp_asist_cargo"), ("asist_org", "_inp_asist_org"),
        ]:
            self._datos[key] = _t(attr)

        # Centro de trabajo seleccionado (centro registrado / tienda / almacén / correo)
        if hasattr(self, "_combo_centro"):
            _cd = self._combo_centro.currentData()
            if isinstance(_cd, dict):
                self._datos["id_centro"] = _cd.get("id_centro")
                self._datos["centro_info"] = _cd
            else:
                self._datos["id_centro"] = None
                self._datos["centro_info"] = None
        # Representante legal (firmante) elegido para el contrato
        if hasattr(self, "_combo_rep"):
            self._datos["id_representante"] = self._combo_rep.currentData()

        # Combo fields
        for key, attr in [
            ("trabajo_distancia", "_combo_distancia"), ("tipo_jornada", "_combo_jornada"),
            ("num_pagas", "_combo_pagas"), ("pagas_pendientes", "_combo_pagas_pend"),
            ("material_empresa", "_combo_material"), ("advertencias_previas", "_combo_advertencias"),
            ("expedientes_previos", "_combo_expedientes"), ("asist_tipo", "_combo_asist"),
        ]:
            self._datos[key] = _cb(attr)
        if hasattr(self, "_chk_fse"):
            self._datos["fse"] = self._chk_fse.isChecked()

        # Nómina devengos/deducciones
        for key, attr in [
            ("irpf_pct", "_inp_irpf"), ("ss_pct", "_inp_ss_pct"),
            ("plus_convenio", "_inp_plus"), ("horas_extras", "_inp_he"),
            ("plus_transporte", "_inp_plus_trans"), ("nocturnidad", "_inp_noct"),
            ("bonus", "_inp_bonus"), ("dietas", "_inp_dietas"),
        ]:
            self._datos[key] = _t(attr)

        # CONTRATO clauses
        if hasattr(self, "_checks_adicionales"):
            self._datos["clausulas_adicionales"] = [
                t for t, cb in self._checks_adicionales if cb.isChecked()
            ]

        # Fiscal fields
        for key, attr in [
            ("trimestre", "_inp_trimestre"), ("ejercicio", "_inp_ejercicio"),
            ("total_ingresos", "_inp_tot_ingresos"), ("iva_repercutido", "_inp_iva_rep"),
            ("iva_soportado", "_inp_iva_sop"), ("gastos_deducibles", "_inp_gastos_ded"),
            ("num_facturas", "_inp_num_facturas"), ("num_clientes", "_inp_num_clientes"),
            ("proveedor", "_inp_proveedor"), ("cif_proveedor", "_inp_cif_prov"),
            ("fecha_factura", "_inp_f_factura"), ("concepto_gasto", "_inp_concepto_gasto"),
        ]:
            self._datos[key] = _t(attr)

        # Textedit fields
        self._datos["observaciones"] = _te("_inp_obs")
        self._datos["hechos"] = _te("_inp_hechos")
        self._ir(1)

    def _p3(self):
        label = self._doc_label()
        lbl = QLabel(tr("cfg.preview_title", default="Vista previa del documento"))
        lbl.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        self._card_ly.addWidget(lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(self._scroll_ss())
        pf = QFrame()
        pf.setStyleSheet(f"QFrame{{background:#161B22;border:1px solid {_BORDE};border-radius:12px;}}")
        pf_ly = QVBoxLayout(pf); pf_ly.setContentsMargins(20, 16, 20, 16); pf_ly.setSpacing(5)

        d = self._datos
        if self._tipo in self._FISCAL_TYPES:
            lineas = [
                (tr("cfg.pv_documento", default="DOCUMENTO:"), label),
                (tr("cfg.pv_empresa", default="EMPRESA:"), d.get("emp_nombre", "—")),
                (tr("cfg.pv_cif", default="CIF:"), d.get("emp_cif", "—")),
                (tr("cfg.pv_periodo", default="PERÍODO:"), f"{d.get('periodo_ini','—')} → {d.get('periodo_fin','—')}"),
            ]
            if d.get("subtipo"): lineas.append((tr("cfg.pv_tipo", default="TIPO:"), d["subtipo"]))
            if d.get("trimestre"): lineas.append((tr("cfg.pv_periodo_fiscal", default="PERÍODO FISCAL:"), f"T{d['trimestre']} / {d.get('ejercicio','')}"))
            if d.get("total_ingresos"): lineas.append((tr("cfg.pv_ingresos", default="INGRESOS:"), f"{divisas.formatear(d['total_ingresos'])}"))
            if d.get("iva_repercutido"): lineas.append((tr("cfg.pv_iva_rep", default="IVA REPERCUTIDO:"), f"{divisas.formatear(d['iva_repercutido'])}"))
            if d.get("iva_soportado"): lineas.append((tr("cfg.pv_iva_sop", default="IVA SOPORTADO:"), f"{divisas.formatear(d['iva_soportado'])}"))
        else:
            lineas = [
                (tr("cfg.pv_documento", default="DOCUMENTO:"), label),
                (tr("cfg.pv_trabajador", default="TRABAJADOR:"), d.get("trabajador", "—")),
                (tr("cfg.pv_nif", default="NIF / NIE:"), d.get("nif", "—")),
            ]
            if d.get("ss"): lineas.append((tr("cfg.pv_ss", default="Nº SS:"), d["ss"]))
            if d.get("categoria"): lineas.append((tr("cfg.pv_categoria", default="CATEGORÍA:"), d["categoria"]))
            if d.get("fecha"): lineas.append((tr("cfg.pv_fecha_efecto", default="FECHA EFECTO:"), d["fecha"]))
            if d.get("subtipo"): lineas.append((tr("cfg.pv_subtipo", default="SUBTIPO:"), d["subtipo"]))
            if d.get("salario"): lineas.append((tr("cfg.pv_salario", default="SALARIO BRUTO:"), f"{divisas.formatear(d['salario'])}"))
            if d.get("puesto"): lineas.append((tr("cfg.pv_puesto", default="PUESTO:"), d["puesto"]))
            if d.get("tipo_jornada"): lineas.append((tr("cfg.pv_jornada", default="JORNADA:"), d["tipo_jornada"]))
            if d.get("convenio"): lineas.append((tr("cfg.pv_convenio", default="CONVENIO:"), d["convenio"]))
            if d.get("indemnizacion"): lineas.append((tr("cfg.pv_indemnizacion", default="INDEMNIZACIÓN:"), f"{divisas.formatear(d['indemnizacion'])}"))
            if d.get("vacaciones_dias"): lineas.append((tr("cfg.pv_vac_pend", default="VACACIONES PEND.:"), f"{d['vacaciones_dias']} " + tr("cfg.unit_dias", default="días")))

        if d.get("observaciones"): lineas.append((tr("cfg.pv_notas", default="NOTAS:"), d["observaciones"][:80] + ("…" if len(d.get("observaciones","")) > 80 else "")))
        lineas.append((tr("cfg.pv_generado", default="GENERADO:"), datetime.now().strftime("%d/%m/%Y %H:%M")))

        for k, v in lineas:
            row = QHBoxLayout()
            lk = QLabel(k); lk.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:11px;"); lk.setFixedWidth(140)
            lv = QLabel(v or "—"); lv.setStyleSheet("color:#E6EDF3;font-family:'Segoe UI';font-size:11px;"); lv.setWordWrap(True)
            row.addWidget(lk); row.addWidget(lv, 1)
            pf_ly.addLayout(row)

        pif = QLabel("<i>" + tr("cfg.tk_footer", default="Documento generado por Smart Manager") + "</i>")
        pif.setStyleSheet("color:#484F58;font-family:'Segoe UI';font-size:10px;"); pif.setTextFormat(Qt.TextFormat.RichText)
        pf_ly.addWidget(pif)
        scroll.setWidget(pf)
        self._card_ly.addWidget(scroll, 1)

        br = QHBoxLayout()
        ba = self._nav_btn(tr("cfg.nav_prev", default="←  ANTERIOR"), "#F85149"); ba.clicked.connect(lambda: self._ir(-1))
        bs = self._nav_btn("✔  " + tr("cfg.gen_doc_btn", default="GENERAR DOCUMENTO"))
        bs.setStyleSheet(bs.styleSheet().replace(_CIAN, "#3FB950"))
        bs.clicked.connect(lambda: self._ir(1))
        br.addWidget(ba); br.addStretch(); br.addWidget(bs)
        self._card_ly.addLayout(br)

    def _p4(self):
        self._pdf_ruta = None
        self._generar_pdf()
        self._card_ly.addStretch()
        if self._pdf_ruta and os.path.exists(self._pdf_ruta):
            ic = QLabel("✅"); ic.setStyleSheet("font-size:48px;"); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_ly.addWidget(ic)
            lbl = QLabel(tr("cfg.p4_ok", default="DOCUMENTO GENERADO CORRECTAMENTE"))
            lbl.setStyleSheet("color:#3FB950;font-family:'Segoe UI';font-weight:900;font-size:14px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_ly.addWidget(lbl)
            lbl2 = QLabel(tr("cfg.p4_saved", default="Guardado en  documentos/fiscalidad/"))
            lbl2.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:12px;")
            lbl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_ly.addWidget(lbl2)
        else:
            ic = QLabel("⚠️"); ic.setStyleSheet("font-size:48px;"); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_ly.addWidget(ic)
            lbl = QLabel(tr("cfg.p4_err", default="Error al generar el documento"))
            lbl.setStyleSheet("color:#F85149;font-family:'Segoe UI';font-weight:900;font-size:14px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_ly.addWidget(lbl)
        self._card_ly.addStretch()
        br = QHBoxLayout(); br.addStretch()
        if self._pdf_ruta and os.path.exists(self._pdf_ruta):
            _ruta = self._pdf_ruta
            bo = self._nav_btn("🔍  " + tr("cfg.open_pdf", default="ABRIR PDF"))
            bo.clicked.connect(lambda: os.startfile(_ruta))
            br.addWidget(bo)
        bc = self._nav_btn(tr("cfg.close", default="CERRAR"), "#6E7681"); bc.clicked.connect(self.accept)
        br.addWidget(bc); self._card_ly.addLayout(br)

    def _generar_pdf(self):
        try:
            _FN, _FB = pdf_fonts.fuentes_para(i18n.current_language())
            import hashlib

            from reportlab.lib.colors import HexColor
            from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import cm, mm
            from reportlab.platypus import (
                HRFlowable,
                KeepTogether,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            # Paleta institucional — estilo SEPE / Seguridad Social
            AZUL      = HexColor("#1F3C88")   # azul institucional
            AZUL_CLR  = HexColor("#D6E4F0")   # fondo sección azul claro
            NEGRO     = HexColor("#111111")   # texto principal
            GRIS      = HexColor("#555555")   # texto secundario
            GRIS_CLR  = HexColor("#F2F2F2")   # fondo tabla
            BORDE     = HexColor("#BBBBBB")
            BORDE_OSC = HexColor("#888888")
            BLANCO    = HexColor("#FFFFFF")

            # ── Prefijo DOC-ID ─────────────────────────────────────────────────
            prefix_map = {
                "CONTRATO": "CTR", "NÓMINA": "NOM", "ALTA": "ALT",
                "BAJA": "BAJ", "CERTIFICADO": "CER", "CERT LABORAL": "CLA",
                "CARTA DESPIDO": "DES", "FINIQUITO": "FIN", "VACACIONES": "VAC",
                "RESUMEN FISCAL": "FIS", "LIBRO INGRESOS": "LIN",
                "LIBRO GASTOS": "LGA", "INFORME AUDIT": "AUD",
            }
            now = datetime.now()
            _MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            def _fecha_larga(dt):
                # Mes en español (no en inglés) y traducido al idioma activo del PDF.
                return self._pdf_tr(f"{dt.day} de {_MESES_ES[dt.month - 1]} de {dt.year}")
            prefix = prefix_map.get(self._tipo, "DOC")
            ts_str = now.strftime("%Y%m%d_%H%M%S")
            doc_id = f"{prefix}-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
            safe = (self._tipo or "DOC").replace(" ", "_")
            fname = f"{safe}_{ts_str}.pdf"
            carpeta = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "fiscalidad")
            )
            os.makedirs(carpeta, exist_ok=True)
            ruta = os.path.join(carpeta, fname)

            # ── Datos corporativos: FUENTE ÚNICA (empresa + representante + centro) ──
            try:
                from src.db import empresa as _empresa_db
                _dc = _empresa_db.datos_corporativos(
                    id_centro=self._datos.get("id_centro"),
                    id_representante=self._datos.get("id_representante"))
            except Exception:
                _dc = {"empresa": {}, "representante": None, "centro": None}
            _e     = _dc.get("empresa") or {}
            _rep   = _dc.get("representante") or {}
            _centro = _dc.get("centro") or {}
            # Si el centro elegido es una tienda/almacén/correo (no un centro
            # registrado con datos completos), usar su nombre/municipio.
            _cinfo = self._datos.get("centro_info") or {}
            if _cinfo and not _cinfo.get("id_centro"):
                _centro = {"nombre_centro": _cinfo.get("nombre"),
                           "codigo_centro": _cinfo.get("codigo"),
                           "municipio": _cinfo.get("municipio")}
            emp = _e  # compat con referencias posteriores
            emp_nombre    = _e.get("razon_social") or _e.get("nombre_empresa") or "EMPRESA"
            emp_comercial = _e.get("nombre_comercial") or ""
            emp_cif       = _e.get("cif_nif") or ""
            emp_dir       = _e.get("direccion_fiscal") or ""
            emp_tel       = _e.get("telefono") or ""
            emp_email     = _e.get("email_principal") or ""
            emp_iban      = ""
            emp_ccc       = _e.get("ccc") or ""
            emp_municipio = _e.get("municipio") or ""
            emp_cp        = _e.get("cp") or ""
            emp_provincia = _e.get("provincia") or ""
            emp_pais      = _e.get("pais") or "ESPAÑA"
            emp_regimen   = _e.get("regimen_ss") or "0111"
            emp_cnae      = _e.get("cnae") or ""
            emp_actividad = _e.get("actividad_economica") or "Comercio al por menor"
            emp_convenio  = _e.get("convenio_colectivo") or ""
            # Representante legal (firmante del documento)
            rep_nombre_full = " ".join(x for x in [_rep.get("nombre"), _rep.get("apellidos")] if x).strip()
            rep_nif         = _rep.get("dni_nie") or ""
            rep_cargo       = _rep.get("cargo") or "REPRESENTANTE LEGAL"
            # Centro de trabajo (la dirección manual del asistente, si se rellenó,
            # alimenta el DOMICILIO de la sección del centro).
            ct_nombre    = _centro.get("nombre_centro") or ""
            ct_dir       = _centro.get("direccion") or self._datos.get("centro_trabajo", "") or ""
            ct_municipio = _centro.get("municipio") or ""
            ct_provincia = _centro.get("provincia") or ""
            ct_cp        = _centro.get("codigo_postal") or ""
            ct_pais      = _centro.get("pais") or "ESPAÑA"
            ct_ccc       = _centro.get("codigo_cuenta_cotizacion") or ""
            ct_actividad = _centro.get("actividad_economica") or ""
            ct_codigo    = _centro.get("codigo_centro_trabajo") or ""
            # Códigos oficiales (SEPE)
            emp_cod_pais = _e.get("cod_pais") or ""
            emp_cod_prov = _e.get("cod_provincia") or ""
            emp_cod_muni = _e.get("cod_municipio") or ""
            emp_cod_act  = _e.get("cod_actividad") or ""
            ct_cod_pais  = _centro.get("cod_pais") or ""
            ct_cod_muni  = _centro.get("cod_municipio") or ""
            ct_cod_act   = _centro.get("cod_actividad") or ""

            # ── Datos trabajador ───────────────────────────────────────────────
            trab               = self._datos.get("trabajador", "—")
            nif                = self._datos.get("nif", "—")
            ss                 = self._datos.get("ss", "")
            fecha              = self._datos.get("fecha", now.strftime("%d/%m/%Y"))
            subtipo            = self._datos.get("subtipo", "")
            salario_str        = self._datos.get("salario", "")
            obs                = self._datos.get("observaciones", "")
            fn_nac             = self._datos.get("fecha_nacimiento", "")
            nacionalidad       = self._datos.get("nacionalidad", "")
            nivel_formativo    = self._datos.get("nivel_formativo", "")
            municipio_dom      = self._datos.get("municipio_domicilio", "")
            provincia_dom      = self._datos.get("provincia_domicilio", "")
            cp_dom             = self._datos.get("cp_domicilio", "")
            pais_dom           = self._datos.get("pais_domicilio", "") or "ESPAÑA"
            sexo               = self._datos.get("sexo", "")
            tel_trab           = self._datos.get("telefono_trab", "")
            email_trab         = self._datos.get("email_trab", "")
            titulacion         = self._datos.get("titulacion", "")
            cod_pais_dom       = self._datos.get("cod_pais_dom", "")
            cod_prov_dom       = self._datos.get("cod_provincia_dom", "")
            cod_muni_dom       = self._datos.get("cod_municipio_dom", "")
            cod_nivel          = self._datos.get("cod_nivel_formativo", "")
            asist_tipo         = self._datos.get("asist_tipo", "")
            asist_nombre       = self._datos.get("asist_nombre", "")
            asist_nif          = self._datos.get("asist_nif", "")
            asist_cargo        = self._datos.get("asist_cargo", "")
            asist_org          = self._datos.get("asist_org", "")
            mostrar_fse        = bool(self._datos.get("fse"))
            puesto             = self._datos.get("puesto", "")
            grupo_prof         = self._datos.get("grupo_prof", "")
            funciones          = self._datos.get("funciones", "")
            centro_trabajo     = self._datos.get("centro_trabajo", emp_dir)
            trabajo_distancia  = self._datos.get("trabajo_distancia", "NO")
            tipo_jornada       = self._datos.get("tipo_jornada", "TIEMPO COMPLETO")
            horas_sem          = self._datos.get("horas_semanales", "40")
            distribucion       = self._datos.get("distribucion", "")
            num_pagas          = self._datos.get("num_pagas", "12")
            periodo_prueba     = self._datos.get("periodo_prueba", "")
            vacaciones         = self._datos.get("vacaciones", "Según Convenio")
            convenio           = self._datos.get("convenio") or emp_convenio
            clausulas_adicionales = self._datos.get("clausulas_adicionales", [])
            irpf_pct_str       = self._datos.get("irpf_pct", "15.0")
            ss_pct_str         = self._datos.get("ss_pct", "6.35")
            plus_convenio_str  = self._datos.get("plus_convenio", "0")
            horas_extras_str   = self._datos.get("horas_extras", "0")
            articulo_et        = self._datos.get("articulo_et", "")
            try:
                salario = float(salario_str.replace(",", ".").replace("€", "").strip()) if salario_str else 0.0
            except ValueError:
                salario = 0.0
            salario_mensual = round(salario / int(num_pagas) if num_pagas and salario > 0 else salario, 2)

            # ── Audit hash ────────────────────────────────────────────────────
            audit_raw = f"{doc_id}|{trab}|{nif}|{fecha}|{self._tipo}|{subtipo}"
            audit_hash = hashlib.sha256(audit_raw.encode()).hexdigest()[:24].upper()

            # ── Estilos ───────────────────────────────────────────────────────
            def _st(name, **kw):
                return ParagraphStyle(name, **kw)

            st_sec_hdr  = _st("sec_hdr",  fontName=_FB, fontSize=8,
                               textColor=AZUL, leading=10)
            # Valores de las tablas en AZUL (como el modelo oficial SEPE).
            st_cell_val = _st("cell_val", fontName=_FB, fontSize=8.5,
                               textColor=AZUL, leading=11)
            st_body     = _st("body",     fontName=_FN, fontSize=9, textColor=NEGRO,
                               leading=13, spaceAfter=2, alignment=TA_JUSTIFY)
            st_clause_h = _st("clause_h", fontName=_FB, fontSize=9,
                               textColor=NEGRO, leading=12, spaceBefore=4, spaceAfter=1)
            st_clause   = _st("clause",   fontName=_FN, fontSize=8.5, textColor=NEGRO,
                               leading=13, spaceAfter=3, alignment=TA_JUSTIFY)
            st_h2       = _st("h2",       fontName=_FB, fontSize=9, textColor=AZUL,
                               leading=12, spaceBefore=5, spaceAfter=2)
            st_center   = _st("center",   fontName=_FN, fontSize=8, textColor=GRIS,
                               leading=11, alignment=TA_CENTER)
            st_right    = _st("right",    fontName=_FN, fontSize=8, textColor=GRIS,
                               leading=11, alignment=TA_RIGHT)
            st_sign_lbl = _st("sign_lbl", fontName=_FN, fontSize=8, textColor=NEGRO,
                               leading=11, alignment=TA_CENTER)
            st_sign_val = _st("sign_val", fontName=_FB, fontSize=8, textColor=NEGRO,
                               leading=11, alignment=TA_CENTER)

            # ── Canvas callbacks ──────────────────────────────────────────────
            page_w, page_h = A4

            # ── Título del documento (contrato: tipo concreto; traducido) ──
            if self._tipo == "CONTRATO":
                titulo_doc = self._pdf_tr(f"CONTRATO DE TRABAJO {(subtipo or 'INDEFINIDO').upper()}")
            else:
                _lbl0 = self._doc_label()
                for _emo in ("📄","📊","✅","❌","🏢","📮","💼","📋","📃","🔍","🌴","📈","📉"):
                    _lbl0 = _lbl0.replace(_emo, "")
                titulo_doc = _lbl0.strip().upper()

            # ── Logos institucionales para la cabecera (si es cofinanciado) ──
            _logos_hdr = []
            if mostrar_fse:
                try:
                    from src.utils import recursos
                    _lbase = recursos.ruta_recurso("assets", "logos_institucionales")
                except Exception:
                    _lbase = os.path.normpath(os.path.join(
                        os.path.dirname(__file__), "..", "..", "assets", "logos_institucionales"))
                for _lf in self._FSE_LOGOS:
                    _lp = os.path.join(_lbase, _lf)
                    if os.path.exists(_lp):
                        _logos_hdr.append(_lp)
                _fse_plus_path = None  # logo FSE+ retirado (cabecera y pie)
            else:
                _fse_plus_path = None

            def _draw_header(c, doc):
                from reportlab.lib.utils import ImageReader
                c.saveState()
                if self._tipo == "CONTRATO":
                    # Cabecera de contrato: SOLO logos institucionales (cada página),
                    # sin franja azul ni nombre de empresa (esos van en el cuerpo).
                    if _logos_hdr:
                        n = len(_logos_hdr)
                        cell = usable_w / n
                        _maxlh = 2.1*cm  # altura máxima (Fondos Europeos, a la par del resto)
                        _cy = page_h - 1.0*cm - _maxlh / 2  # centro vertical común
                        for i, lp in enumerate(_logos_hdr):
                            try:
                                img = ImageReader(lp)
                                iw, ih = img.getSize()
                                ratio = (iw / ih) if ih else 1.0
                                # El logo de Fondos Europeos tiene mucho margen interno,
                                # así que se dibuja bastante más alto para igualar visualmente.
                                lh = 2.1*cm if "fondos_europeos" in lp else 1.2*cm
                                w = lh * ratio
                                if w > cell - 0.3*cm:
                                    w = cell - 0.3*cm
                                    lh = w / ratio if ratio else lh
                                cx = 1.5*cm + i*cell + (cell - w) / 2
                                c.drawImage(img, cx, _cy - lh / 2, w, lh,
                                            preserveAspectRatio=True, mask="auto")
                            except Exception:
                                pass
                        y_title = page_h - 1.0*cm - _maxlh - 0.4*cm
                    else:
                        y_title = page_h - 1.7*cm
                else:
                    # Cabecera estándar (nómina, certificados, fiscal...): nombre de
                    # empresa + logo corporativo (sin franja azul).
                    if os.path.exists(_LOGO_PATH):
                        try:
                            c.drawImage(_LOGO_PATH, page_w - 3.6*cm, page_h - 2.35*cm,
                                        2.9*cm, 1.5*cm, preserveAspectRatio=True, mask="auto")
                        except Exception:
                            pass
                    c.setFont(_FB, 11); c.setFillColor(NEGRO)
                    c.drawString(1.5*cm, page_h - 1.6*cm, emp_nombre.upper())
                    c.setFont(_FN, 7.5); c.setFillColor(GRIS)
                    meta_parts = [x for x in [f"CIF: {emp_cif}", emp_dir, emp_tel, emp_email] if x]
                    c.drawString(1.5*cm, page_h - 2.2*cm, "  ·  ".join(meta_parts))
                    y_title = page_h - 3.0*cm
                # En contratos el título va en un banner del cuerpo (pág. 1, modelo
                # SEPE); en el resto de documentos, título en la cabecera.
                if self._tipo != "CONTRATO":
                    c.setFont(_FB, 12); c.setFillColor(AZUL)
                    c.drawString(1.5*cm, y_title, titulo_doc)
                c.setFont(_FN, 7.5); c.setFillColor(GRIS)
                c.drawRightString(page_w - 1.5*cm, y_title, f"Ref: {doc_id}")
                c.setStrokeColor(BORDE_OSC); c.setLineWidth(0.8)
                c.line(1.5*cm, y_title - 0.4*cm, page_w - 1.5*cm, y_title - 0.4*cm)
                c.restoreState()

            def _draw_footer(c, doc):
                from reportlab.lib.utils import ImageReader
                c.saveState()
                c.setStrokeColor(BORDE)
                c.setLineWidth(0.5)
                c.line(1.5*cm, 1.7*cm, page_w - 1.5*cm, 1.7*cm)
                # Pie institucional FSE+ (cofinanciado), abajo a la izquierda.
                _tx = 1.5*cm
                if _fse_plus_path:
                    try:
                        img = ImageReader(_fse_plus_path)
                        iw, ih = img.getSize()
                        ph = 0.85*cm
                        pw = ph * ((iw / ih) if ih else 1.0)
                        c.drawImage(img, 1.5*cm, 0.5*cm, pw, ph,
                                    preserveAspectRatio=True, mask="auto")
                        c.setFont(_FB, 8); c.setFillColor(AZUL)
                        c.drawString(1.5*cm + pw + 0.18*cm, 1.05*cm, "FSE+")
                        c.setFont(_FN, 7); c.setFillColor(GRIS)
                        c.drawString(1.5*cm + pw + 0.18*cm, 0.72*cm, "Fondo Social Europeo Plus")
                    except Exception:
                        pass
                # Trazabilidad (Ref/Hash) + paginación a la derecha.
                c.setFont(_FN, 6.5)
                c.setFillColor(GRIS)
                c.drawRightString(page_w - 1.5*cm, 1.15*cm, f"Ref: {doc_id}  ·  Hash: {audit_hash}")
                c.drawRightString(page_w - 1.5*cm, 0.8*cm,
                                  f"{self._pdf_tr('Pág.')} {doc.page}  ·  {now.strftime('%d/%m/%Y %H:%M')}")
                c.restoreState()

            def on_page(c, doc):
                _draw_header(c, doc)
                _draw_footer(c, doc)

            # ── Documento ─────────────────────────────────────────────────────
            # El contrato tiene cabecera con logos grandes -> más margen superior.
            _top_margin = 4.4*cm if self._tipo == "CONTRATO" else 3.9*cm
            doc = SimpleDocTemplate(
                ruta, pagesize=A4,
                leftMargin=1.5*cm, rightMargin=1.5*cm,
                topMargin=_top_margin, bottomMargin=2.3*cm,
            )
            usable_w = page_w - 3.0*cm

            # ── Helpers SEPE ──────────────────────────────────────────────────
            def _P(txt, style):
                """Paragraph con traducción IA del cuerpo (cláusulas legales)."""
                return Paragraph(self._pdf_tr(txt), style)

            def _sec_header(txt):
                t = Table([[Paragraph(self._pdf_tr(txt), st_sec_hdr)]], colWidths=[usable_w])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), AZUL_CLR),
                    ("BOX", (0,0), (-1,-1), 0.6, AZUL),
                    ("TOPPADDING", (0,0), (-1,-1), 3),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                    ("LEFTPADDING", (0,0), (-1,-1), 6),
                ]))
                return t

            def _data_val_row(*pairs):
                cells = []
                for label, val in pairs:
                    cells.append(Paragraph(
                        f"<font size='6.5' color='#555555'>{self._pdf_tr(label)}</font><br/>"
                        f"<b>{val or '—'}</b>", st_cell_val))
                col_w = usable_w / len(pairs)
                t = Table([cells], colWidths=[col_w]*len(pairs))
                t.setStyle(TableStyle([
                    ("BOX", (0,0), (-1,-1), 0.5, BORDE_OSC),
                    ("INNERGRID", (0,0), (-1,-1), 0.4, BORDE),
                    ("TOPPADDING", (0,0), (-1,-1), 3),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                    ("LEFTPADDING", (0,0), (-1,-1), 5),
                    ("RIGHTPADDING", (0,0), (-1,-1), 5),
                    ("BACKGROUND", (0,0), (-1,-1), BLANCO),
                ]))
                return t

            def _vc(val, cod):
                """Valor + código oficial al lado (estilo SEPE), o solo el valor."""
                v = val if (val not in (None, "")) else "—"
                if cod:
                    return f"{v}&nbsp;&nbsp;<font size='7' color='#1F3C88'>· {cod}</font>"
                return v

            story = []

            # =================================================================
            if self._tipo == "CONTRATO":
            # =================================================================
                subtipo_label    = subtipo or "INDEFINIDO"
                _puesto_txt      = puesto or "Según categoría profesional"
                _grupo_txt       = grupo_prof or "Según convenio"
                _func_txt        = funciones or "Las propias del grupo profesional"
                _centro_txt      = (centro_trabajo
                                    or ", ".join(x for x in [ct_nombre, ct_dir, ct_municipio] if x)
                                    or emp_dir or "—")
                _horas_txt       = horas_sem or "40"
                _dist_txt        = distribucion or "Lunes a domingo"
                _prueba_txt      = periodo_prueba or "Conforme a convenio colectivo"
                _vac_txt         = vacaciones or "Según Convenio"
                _conv_txt        = convenio or "el aplicable al sector de actividad"
                _jornada_parcial = tipo_jornada == "TIEMPO PARCIAL"
                _distancia_si    = trabajo_distancia == "SÍ"
                _sal_mensual_fmt = f"{divisas.formatear(salario_mensual)}" if salario_mensual > 0 else "—"
                _sal_anual_fmt   = f"{divisas.formatear(salario)}" if salario > 0 else "—"

                # ── Modalidad contractual: determina cláusulas y código dinámicos ──
                _sub_norm    = (subtipo or "INDEFINIDO").upper()
                _es_fijodisc = "FIJO" in _sub_norm
                _es_sustit   = "SUSTITU" in _sub_norm
                _es_practic  = "CTIC" in _sub_norm                 # PRÁCTICAS / PRACTICAS
                _es_temporal = "TEMPORAL" in _sub_norm or _es_sustit
                _es_determinada = _es_temporal or _es_practic      # duración determinada (no indefinida)
                _fecha_fin   = self._datos.get("fecha_fin", "")

                # Los logos institucionales van en la cabecera de CADA página
                # (_draw_header), no en el cuerpo.
                # Banner del título (modelo SEPE) — barra sombreada a ancho completo.
                _tb = Table([[Paragraph(titulo_doc, _st("tbanner", fontName=_FB, fontSize=12,
                                                         textColor=AZUL, leading=15))]],
                            colWidths=[usable_w])
                _tb.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), HexColor("#E9EEF6")),
                    ("BOX", (0,0), (-1,-1), 0.6, AZUL),
                    ("TOPPADDING", (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING", (0,0), (-1,-1), 8),
                ]))
                story.append(_tb)
                story.append(Spacer(1, 2.5*mm))
                story.append(_sec_header("DATOS DE LA EMPRESA"))
                story.append(_data_val_row(("CIF/NIF/NIE", emp_cif)))
                story.append(_data_val_row(
                    ("D./DÑA. (REPRESENTANTE LEGAL)", rep_nombre_full or "—"),
                    ("NIF/NIE", rep_nif or "—"),
                ))
                story.append(_data_val_row(("EN CONCEPTO", rep_cargo or "REPRESENTANTE LEGAL")))
                story.append(_data_val_row(("NOMBRE O RAZÓN SOCIAL DE LA EMPRESA", emp_nombre)))
                story.append(_data_val_row(("DOMICILIO SOCIAL", emp_dir)))
                story.append(_data_val_row(
                    ("MUNICIPIO", _vc(emp_municipio, emp_cod_muni)),
                    ("PROVINCIA", _vc(emp_provincia, emp_cod_prov)),
                    ("CÓDIGO POSTAL", emp_cp or "—"),
                    ("PAÍS", _vc(emp_pais, emp_cod_pais)),
                ))
                story.append(Spacer(1, 1*mm))

                story.append(_sec_header("DATOS DE LA CUENTA DE COTIZACIÓN"))
                story.append(_data_val_row(
                    ("RÉGIMEN", emp_regimen or "0111"),
                    ("CÓDIGO CUENTA DE COTIZACIÓN", emp_ccc or "—"),
                ))
                story.append(_data_val_row(
                    ("ACTIVIDAD ECONÓMICA", _vc(emp_actividad, emp_cod_act)),
                    ("CNAE", emp_cnae or "—"),
                ))
                story.append(Spacer(1, 1*mm))

                story.append(_sec_header("DATOS DEL CENTRO DE TRABAJO"))
                if ct_nombre or ct_dir:
                    story.append(_data_val_row(("CENTRO DE TRABAJO", ct_nombre or "—"),
                                               ("CÓD. CENTRO", ct_codigo or "—")))
                    story.append(_data_val_row(("DOMICILIO", ct_dir or "—")))
                    story.append(_data_val_row(
                        ("MUNICIPIO", _vc(ct_municipio or emp_municipio, ct_cod_muni or emp_cod_muni)),
                        ("PROVINCIA", ct_provincia or "—"),
                        ("CÓDIGO POSTAL", ct_cp or "—"),
                        ("PAÍS", _vc(ct_pais, ct_cod_pais or emp_cod_pais)),
                    ))
                    story.append(_data_val_row(
                        ("CÓDIGO CUENTA DE COTIZACIÓN", ct_ccc or emp_ccc or "—"),
                        ("ACTIVIDAD ECONÓMICA", _vc(ct_actividad or emp_actividad, ct_cod_act or emp_cod_act)),
                    ))
                else:
                    story.append(_data_val_row(
                        ("MUNICIPIO", _vc(emp_municipio, emp_cod_muni)),
                        ("CÓDIGO POSTAL", emp_cp or "—"),
                        ("PAÍS", _vc(emp_pais, emp_cod_pais)),
                    ))
                story.append(Spacer(1, 1*mm))

                story.append(_sec_header("DATOS DE LA PERSONA TRABAJADORA"))
                story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif), ("SEXO", sexo or "—")))
                story.append(_data_val_row(
                    ("FECHA NACIMIENTO (dd/mm/aaaa)", fn_nac or "—"),
                    ("Nº SEGURIDAD SOCIAL", ss or "—"),
                    ("NACIONALIDAD", nacionalidad or "ESPAÑOLA"),
                ))
                story.append(_data_val_row(
                    ("NIVEL FORMATIVO", _vc(nivel_formativo, cod_nivel)),
                    ("TITULACIÓN", titulacion or "—"),
                ))
                story.append(_data_val_row(("MUNICIPIO DEL DOMICILIO", _vc(municipio_dom, cod_muni_dom)),
                                           ("PROVINCIA", _vc(provincia_dom, cod_prov_dom))))
                story.append(_data_val_row(
                    ("CÓDIGO POSTAL", cp_dom or "—"),
                    ("PAÍS DOMICILIO", _vc(pais_dom or "ESPAÑA", cod_pais_dom)),
                    ("TELÉFONO", tel_trab or "—"),
                ))
                if email_trab:
                    story.append(_data_val_row(("CORREO ELECTRÓNICO", email_trab)))
                story.append(Spacer(1, 2*mm))

                # Sección siempre presente (como el modelo oficial), aunque vacía.
                story.append(_sec_header("DATOS DE LA ASISTENCIA LEGAL (EN SU CASO)"))
                story.append(_data_val_row(
                    ("TIPO DE REPRESENTACIÓN", asist_tipo if (asist_tipo and asist_tipo != "No procede") else "—"),
                    ("ORGANIZACIÓN", asist_org or "—"),
                ))
                story.append(_data_val_row(
                    ("D./DÑA.", asist_nombre or "—"),
                    ("NIF/NIE", asist_nif or "—"),
                    ("CARGO", asist_cargo or "—"),
                ))
                story.append(Spacer(1, 2*mm))

                story.append(_P(
                    "Que reúnen los requisitos exigidos para la celebración del presente contrato y, "
                    "en su consecuencia, acuerdan formalizarlo con arreglo a las siguientes:",
                    st_body
                ))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("CLÁUSULAS"))
                story.append(Spacer(1, 1*mm))

                _td_txt = "SÍ" if _distancia_si else "NO"
                story.append(_P(
                    f"<b>PRIMERA:</b> El/la trabajador/a prestará sus servicios como <b>{_puesto_txt}</b>, "
                    f"incluido/a en el grupo profesional de <b>{_grupo_txt}</b>, para la realización de las "
                    f"funciones de <b>{_func_txt}</b>, de acuerdo con el sistema de clasificación profesional "
                    f"vigente en la empresa. En el centro de trabajo ubicado en (calle, nº y localidad): "
                    f"<b>{_centro_txt}</b>. Modalidad de trabajo a distancia: <b>{_td_txt}</b> "
                    f"(Ley 10/2021, de 9 de julio, de trabajo a distancia).",
                    st_clause))

                if _es_fijodisc:
                    _segunda_txt = (
                        f"<b>SEGUNDA:</b> El contrato se concierta para realizar trabajos fijos-discontinuos, "
                        f"de acuerdo con el artículo 16 del Estatuto de los Trabajadores. Los/as trabajadores/as "
                        f"serán llamados/as en el orden y la forma que se determine en el Convenio Colectivo de "
                        f"<b>{_conv_txt}</b> o acuerdo de empresa.")
                elif _es_sustit:
                    _segunda_txt = (
                        "<b>SEGUNDA:</b> El contrato se concierta para la sustitución de persona trabajadora "
                        "con derecho a reserva del puesto de trabajo, de acuerdo con el artículo 15.3 del "
                        "Estatuto de los Trabajadores.")
                elif _es_temporal:
                    _segunda_txt = (
                        "<b>SEGUNDA:</b> El contrato se concierta por circunstancias de la producción de "
                        "carácter ocasional e imprevisible, con duración determinada, de acuerdo con el "
                        "artículo 15 del Estatuto de los Trabajadores.")
                elif _es_practic:
                    _segunda_txt = (
                        "<b>SEGUNDA:</b> El contrato se concierta como contrato formativo para la obtención de "
                        "la práctica profesional adecuada al nivel de estudios, de acuerdo con el artículo 11.3 "
                        "del Estatuto de los Trabajadores.")
                else:
                    _segunda_txt = (
                        "<b>SEGUNDA:</b> El contrato se concierta por tiempo indefinido, de acuerdo con el "
                        "artículo 15 del Estatuto de los Trabajadores.")
                story.append(_P(_segunda_txt, st_clause))

                if _jornada_parcial:
                    jornada_txt = (
                        f"<b>TERCERA:</b> La jornada de trabajo será <b>a tiempo parcial</b>: <b>{_horas_txt} horas</b> "
                        f"a la semana, siendo esta jornada inferior a la de un trabajador a tiempo completo comparable. "
                        f"La distribución del tiempo de trabajo será de <b>{_dist_txt}</b>, conforme a lo previsto "
                        f"en el convenio colectivo.")
                else:
                    jornada_txt = (
                        f"<b>TERCERA:</b> La jornada de trabajo será <b>a tiempo completo</b>: <b>{_horas_txt} horas "
                        f"semanales</b>, con la distribución horaria de <b>{_dist_txt}</b>, con los descansos "
                        f"establecidos legal o convencionalmente.")
                story.append(_P(jornada_txt, st_clause))

                if _es_fijodisc:
                    _cuarta_txt = (
                        f"<b>CUARTA:</b> El presente contrato es <b>FIJO-DISCONTINUO</b> y de duración "
                        f"<b>INDEFINIDA</b>; la relación laboral se inicia en fecha <b>{fecha}</b>, con "
                        f"llamamientos sucesivos en el orden y la forma que determine el convenio colectivo. "
                        f"Se establece un período de prueba de <b>{_prueba_txt}</b>.")
                elif _es_determinada:
                    _fin_txt = (f" y finalizando el <b>{_fecha_fin}</b>" if _fecha_fin
                                else ", extendiéndose mientras subsista la causa que la motiva")
                    _cuarta_txt = (
                        f"<b>CUARTA:</b> La duración del presente contrato será <b>DETERMINADA</b>, "
                        f"iniciándose la relación laboral en fecha <b>{fecha}</b>{_fin_txt}. Se establece un "
                        f"período de prueba de <b>{_prueba_txt}</b>.")
                else:
                    _cuarta_txt = (
                        f"<b>CUARTA:</b> La duración del presente contrato será <b>INDEFINIDA</b>, "
                        f"iniciándose la relación laboral en fecha <b>{fecha}</b> y se establece un período de "
                        f"prueba de <b>{_prueba_txt}</b>.")
                story.append(_P(_cuarta_txt, st_clause))

                story.append(_P(
                    f"<b>QUINTA:</b> El/la trabajador/a percibirá una retribución total de "
                    f"<b>{_sal_anual_fmt} euros brutos anuales</b>, que se distribuirán en <b>{num_pagas} pagas</b> "
                    f"(importe mensual: <b>{_sal_mensual_fmt}</b>), conforme a los conceptos salariales del "
                    f"convenio colectivo y sujetos a las retenciones de IRPF y a las cotizaciones a la "
                    f"Seguridad Social legalmente establecidas.",
                    st_clause))

                story.append(_P(
                    "<b>SEXTA:</b> Complemento de apoyo al empleo para las personas trabajadoras que estén "
                    "percibiendo prestaciones por desempleo (disposición adicional 59ª del texto refundido de "
                    "la Ley General de la Seguridad Social). La empresa <b>NO</b> tiene autorizado un expediente "
                    "de regulación de empleo.",
                    st_clause))

                story.append(_P(
                    f"<b>SÉPTIMA:</b> La duración de las vacaciones anuales será de <b>{_vac_txt}</b>.",
                    st_clause))

                story.append(_P(
                    f"<b>OCTAVA:</b> En lo no previsto en este contrato, se estará a la legislación vigente que "
                    f"resulte de aplicación y, particularmente, al Estatuto de los Trabajadores (RDL 2/2015) y "
                    f"al Convenio Colectivo de <b>{_conv_txt}</b>.",
                    st_clause))

                story.append(_P(
                    "<b>NOVENA:</b> El presente contrato <b>NO</b> se formaliza bajo la modalidad "
                    "de contrato de relevo.",
                    st_clause))

                story.append(_P(
                    "<b>DÉCIMA:</b> ESTE CONTRATO PODRÁ SER COFINANCIADO POR EL FONDO SOCIAL EUROPEO.",
                    st_clause))

                story.append(_P(
                    "<b>UNDÉCIMA:</b> El contenido del presente contrato se comunicará al Servicio Público de "
                    "Empleo en el plazo de los 10 días siguientes a su concertación (art. 16.1 de la Ley de Empleo).",
                    st_clause))

                story.append(_P(
                    "<b>DUODÉCIMA:</b> PROTECCIÓN DE DATOS. Los datos consignados en el presente modelo tendrán "
                    "la protección derivada del Reglamento (UE) 2016/679 del Parlamento Europeo y del Consejo, "
                    "de 27 de abril de 2016, y de la Ley Orgánica 3/2018, de 5 de diciembre (LOPDGDD).",
                    st_clause))
                story.append(Spacer(1, 2*mm))

                story.append(_sec_header("TIPO DE CONTRATO — CÓDIGO"))
                if _es_fijodisc:
                    _cod_num = "300"
                    _mk_completo, _mk_parcial, _mk_fijo = "☐", "☐", "☑"
                elif _jornada_parcial:
                    _cod_num = "200"
                    _mk_completo, _mk_parcial, _mk_fijo = "☐", "☑", "☐"
                else:
                    _cod_num = "100"
                    _mk_completo, _mk_parcial, _mk_fijo = "☑", "☐", "☐"
                cod_data = [[
                    Paragraph(
                        f"{_mk_completo}  TIEMPO COMPLETO    "
                        f"{_mk_parcial}  TIEMPO PARCIAL    "
                        f"{_mk_fijo}  FIJO-DISCONTINUO",
                        st_body
                    ),
                    Paragraph(
                        _cod_num,
                        _st("cod", fontName=_FB, fontSize=14, textColor=AZUL,
                            leading=16, alignment=TA_CENTER)
                    ),
                ]]
                story.append(Table(cod_data, colWidths=[usable_w*0.75, usable_w*0.25],
                    style=TableStyle([
                        ("BOX", (0,0),(-1,-1), 0.6, BORDE_OSC),
                        ("INNERGRID",(0,0),(-1,-1), 0.4, BORDE),
                        ("TOPPADDING",(0,0),(-1,-1), 5),
                        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                        ("LEFTPADDING",(0,0),(-1,-1), 8),
                        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ])))

                if clausulas_adicionales:
                    story.append(Spacer(1, 3*mm))
                    story.append(_sec_header("CLÁUSULAS ADICIONALES — SEGÚN ANEXO"))
                    story.append(Spacer(1, 1*mm))
                    _cla_map = {
                        "Prorrateo de pagas extraordinarias":
                            "Empresa y trabajador/a acuerdan el prorrateo de las gratificaciones "
                            "extraordinarias establecidas por el convenio colectivo, de forma que "
                            "el/la trabajador/a percibirá mensualmente el importe correspondiente "
                            "a las pagas extraordinarias devengadas.",
                        "Obligaciones de no competencia desleal (arts. 4.1 y 21.1 ET)":
                            "El/La trabajador/a deberá abstenerse de inducir a trabajadores, "
                            "proveedores o clientes a infringir deberes contractuales, de conformidad "
                            "con los arts. 4.1 y 21.1 ET y los arts. 4.1 y 14 de la Ley de Competencia Desleal.",
                        "Uso restringido de Internet y correo corporativo":
                            "El acceso a Internet y el correo electrónico corporativo tienen carácter "
                            "estrictamente laboral. La empresa informa de la existencia de mecanismos "
                            "de control del uso de los medios informáticos de la empresa.",
                        "Protección de datos personales (LOPDGDD 3/2018)":
                            "Los datos personales serán tratados conforme a la LOPDGDD 3/2018 y el "
                            "RGPD (UE) 2016/679. Podrán comunicarse a terceros exclusivamente cuando "
                            "sea necesario para el desarrollo de la relación laboral.",
                        "Compensación de horas extra con descanso":
                            "El exceso de horas laborables respecto al calendario y el convenio "
                            "colectivo se compensará de común acuerdo con horas de descanso equivalentes.",
                        "Interrupción del período de prueba por IT/nacimiento":
                            "Las situaciones de IT, nacimiento, adopción, guarda, acogimiento, riesgo "
                            "durante el embarazo o la lactancia y violencia de género interrumpirán "
                            "el cómputo del período de prueba.",
                        "Vacaciones en días laborables":
                            "Las vacaciones anuales retribuidas se disfrutarán en días laborables, "
                            "respetando en todo caso la duración total establecida en convenio.",
                        "Obligación de comunicar baja/alta médica de forma inmediata":
                            "En casos de baja/alta médica, el/la trabajador/a informará a la empresa "
                            "de forma inmediata. El parte médico se remite por vía telemática.",
                    }
                    numerales = ["PRIMERA","SEGUNDA","TERCERA","CUARTA","QUINTA",
                                 "SEXTA","SÉPTIMA","OCTAVA","NOVENA","DÉCIMA"]
                    for i, cla_txt in enumerate(clausulas_adicionales, 1):
                        num = numerales[min(i-1, 9)]
                        cla_body = _cla_map.get(cla_txt, cla_txt)
                        story.append(_P(f"<b>{num}.</b> {cla_body}", st_clause))

                # ── Anexo específico según la modalidad contractual ──
                _anexos = []
                if _jornada_parcial:
                    _anexos.append((
                        "ANEXO — PACTO DE HORAS COMPLEMENTARIAS",
                        "El/la trabajador/a a tiempo parcial podrá realizar horas complementarias hasta "
                        "un máximo del 30% de las horas ordinarias (ampliable por convenio colectivo de "
                        "ámbito sectorial hasta el 60%), con un preaviso mínimo de 3 días, conforme al "
                        "artículo 12.5 del Estatuto de los Trabajadores. Se retribuirán como ordinarias y "
                        "computarán a efectos de cotización a la Seguridad Social."))
                if _es_fijodisc:
                    _anexos.append((
                        "ANEXO — TRABAJO FIJO-DISCONTINUO",
                        "El llamamiento se realizará por escrito, en el orden y la forma que determine el "
                        "convenio colectivo, con antelación suficiente. La falta de llamamiento equivaldrá a "
                        "un despido a efectos legales. Los periodos de inactividad no interrumpen el cómputo "
                        "de la antigüedad (art. 16 del Estatuto de los Trabajadores)."))
                if _es_temporal:
                    _anexos.append((
                        "ANEXO — CONTRATO DE DURACIÓN DETERMINADA",
                        "El contrato se extinguirá al finalizar la causa que lo motiva o, en su caso, en la "
                        "fecha pactada. A su término, el/la trabajador/a tendrá derecho a la indemnización "
                        "legalmente establecida (art. 49 del Estatuto de los Trabajadores)."))
                if _es_practic:
                    _anexos.append((
                        "ANEXO FORMATIVO",
                        "La empresa designa un/a tutor/a responsable del seguimiento del plan formativo "
                        "individual. La actividad se ajustará al nivel de estudios de la persona trabajadora "
                        "(art. 11.3 del Estatuto de los Trabajadores), con una duración mínima de 6 meses y "
                        "máxima de 1 año."))
                if _anexos:
                    story.append(Spacer(1, 2*mm))
                    story.append(_sec_header("ANEXO ESPECÍFICO DE LA MODALIDAD"))
                    story.append(Spacer(1, 1*mm))
                    for _ax_t, _ax_b in _anexos:
                        story.append(_P(f"<b>{_ax_t}.</b> {_ax_b}", st_clause))

            # =================================================================
            elif self._tipo == "NÓMINA":
            # =================================================================
                try:
                    irpf_pct = float(irpf_pct_str.replace(",",".").strip()) if irpf_pct_str else 15.0
                except ValueError:
                    irpf_pct = 15.0
                try:
                    ss_emp_pct = float(ss_pct_str.replace(",",".").strip()) if ss_pct_str else 6.35
                except ValueError:
                    ss_emp_pct = 6.35
                try:
                    plus_conv = float(plus_convenio_str.replace(",",".").strip()) if plus_convenio_str else 0.0
                except ValueError:
                    plus_conv = 0.0
                try:
                    horas_ext = float(horas_extras_str.replace(",",".").strip()) if horas_extras_str else 0.0
                except ValueError:
                    horas_ext = 0.0
                sal_base    = salario_mensual if salario_mensual > 0 else salario
                irpf_ret    = round(sal_base * irpf_pct / 100, 2)
                ss_ret      = round(sal_base * ss_emp_pct / 100, 2)
                bruto_total = round(sal_base + plus_conv + horas_ext, 2)
                neto        = round(bruto_total - irpf_ret - ss_ret, 2)

                story.append(_sec_header("DATOS DEL EMPLEADOR"))
                story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
                story.append(_data_val_row(("DOMICILIO", emp_dir), ("CCC", emp_ccc or "—")))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
                story.append(_data_val_row(("TRABAJADOR/A", trab), ("NIF/NIE", nif)))
                story.append(_data_val_row(
                    ("Nº SEG. SOCIAL", ss or "—"),
                    ("PERÍODO", fecha),
                    ("Nº PAGAS", num_pagas),
                ))
                story.append(_data_val_row(("CATEGORÍA/PUESTO", puesto or "—"), ("GRUPO PROF.", grupo_prof or "—")))
                story.append(Spacer(1, 2*mm))
                story.append(_sec_header("DESGLOSE DE NÓMINA"))
                th = _st("th", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
                th_c = _st("thc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)
                nom_data = [
                    [Paragraph(self._pdf_tr("CONCEPTO"), th), Paragraph(self._pdf_tr("DEVENGOS"), th_c), Paragraph(self._pdf_tr("DEDUCCIONES"), th_c)],
                    ["Salario base", f"{divisas.formatear(sal_base)}", ""],
                    ["Plus convenio", f"{divisas.formatear(plus_conv)}" if plus_conv else "—", ""],
                    ["Horas extras", f"{divisas.formatear(horas_ext)}" if horas_ext else "—", ""],
                    [f"Retención IRPF ({irpf_pct:.1f}%)", "", f"{divisas.formatear(irpf_ret)}"],
                    [f"Cuota S.S. trabajador ({ss_emp_pct:.2f}%)", "", f"{divisas.formatear(ss_ret)}"],
                    [
                        Paragraph("<b>"+self._pdf_tr("TOTAL BRUTO / TOTAL DEDUCCIONES")+"</b>", _st("tb", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)),
                        Paragraph(f"<b>{divisas.formatear(bruto_total)}</b>", _st("tb2", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
                        Paragraph(f"<b>{divisas.formatear(irpf_ret+ss_ret)}</b>", _st("tb3", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER)),
                    ],
                    [
                        Paragraph("<b>"+self._pdf_tr("LÍQUIDO A PERCIBIR")+"</b>", _st("liq", fontName=_FB, fontSize=10, textColor=AZUL, leading=12)),
                        Paragraph(f"<b>{divisas.formatear(neto)}</b>", _st("liq2", fontName=_FB, fontSize=10, textColor=AZUL, leading=12, alignment=TA_CENTER)),
                        "",
                    ],
                ]
                nom_tbl = Table(nom_data, colWidths=[usable_w*0.55, usable_w*0.225, usable_w*0.225])
                nom_tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0,0),(-1,0), GRIS_CLR),
                    ("FONTNAME", (0,1),(-1,-3), _FN),
                    ("FONTSIZE", (0,1),(-1,-1), 8.5),
                    ("ALIGN", (1,0),(-1,-1), "CENTER"),
                    ("GRID", (0,0),(-1,-1), 0.4, BORDE),
                    ("BOX", (0,0),(-1,-1), 0.8, BORDE_OSC),
                    ("ROWBACKGROUNDS", (0,1),(-1,-3), [BLANCO, HexColor("#F7F7F7")]),
                    ("BACKGROUND", (0,-2),(-1,-2), GRIS_CLR),
                    ("BACKGROUND", (0,-1),(-1,-1), AZUL_CLR),
                    ("LINEABOVE", (0,-2),(-1,-2), 1.0, BORDE_OSC),
                    ("LINEABOVE", (0,-1),(-1,-1), 1.5, AZUL),
                    ("TOPPADDING", (0,0),(-1,-1), 4),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                    ("LEFTPADDING", (0,0),(-1,-1), 6),
                    ("RIGHTPADDING", (0,0),(-1,-1), 6),
                ]))
                story.append(nom_tbl)
                story.append(Spacer(1, 3*mm))
                story.append(_P(
                    f"IBAN: {emp_iban or '—'}  ·  Convenio: {convenio or '—'}  ·  "
                    f"Generado: {now.strftime('%d/%m/%Y')}",
                    st_center
                ))

            # =================================================================
            elif self._tipo == "CARTA DESPIDO":
            # =================================================================
                subtipo_label = subtipo or "DISCIPLINARIO"
                story.append(_sec_header("DATOS DE LA EMPRESA COMUNICANTE"))
                story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
                story.append(_data_val_row(("DOMICILIO", emp_dir)))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DE LA PERSONA TRABAJADORA"))
                story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
                story.append(_data_val_row(("PUESTO", puesto or "—"), ("FECHA EFECTO", fecha)))
                story.append(Spacer(1, 3*mm))
                story.append(_P(
                    f"{emp_dir or '—'},  a {_fecha_larga(now)}",
                    st_right
                ))
                story.append(Spacer(1, 2*mm))
                story.append(_P(f"Estimado/a Sr./Sra. {trab}:", st_body))
                story.append(Spacer(1, 2*mm))
                intro_map = {
                    "DISCIPLINARIO": (
                        "Por medio de la presente, y en virtud de lo establecido en el artículo 54 "
                        "del Estatuto de los Trabajadores (RDL 2/2015), la dirección de la empresa "
                        f"le comunica la decisión de proceder a su <b>despido disciplinario</b>, "
                        f"con efectos desde el día <b>{fecha}</b>, por incumplimiento grave y culpable "
                        "de sus obligaciones laborales, en concreto por las causas que a continuación se detallan:"
                    ),
                    "OBJETIVO": (
                        "Por medio de la presente, y al amparo de lo previsto en el artículo 52 del "
                        "Estatuto de los Trabajadores, la empresa le notifica la extinción de su "
                        f"contrato de trabajo por <b>causas objetivas</b>, con efectos desde el día "
                        f"<b>{fecha}</b>. Tiene derecho a la indemnización legalmente establecida "
                        "de <b>20 días de salario por año de servicio</b>, prorrateándose los períodos "
                        "inferiores a un año."
                    ),
                    "IMPROCEDENTE": (
                        "La empresa reconoce el carácter <b>improcedente</b> del despido con efectos "
                        f"desde el día <b>{fecha}</b>, y le comunica la indemnización de "
                        "<b>33 días de salario por año de servicio</b> desde el 12/02/2012, "
                        "o de 45 días por los períodos anteriores (máximo 720 días de salario)."
                    ),
                }
                story.append(_P(intro_map.get(subtipo_label,
                    f"Se le comunica la extinción de su relación laboral con efectos desde el {fecha}."), st_body))
                if articulo_et:
                    story.append(Spacer(1, 2*mm))
                    story.append(_P(f"<b>PRECEPTO LEGAL INVOCADO:</b> {articulo_et}", st_body))
                if obs:
                    story.append(Spacer(1, 2*mm))
                    story.append(_sec_header("HECHOS Y FUNDAMENTOS"))
                    story.append(Spacer(1, 1*mm))
                    story.append(_P(obs, st_clause))
                story.append(Spacer(1, 3*mm))
                story.append(_P(
                    "Se le informa de su derecho a impugnar esta decisión ante el Juzgado de lo Social "
                    "competente en el plazo de <b>20 días hábiles</b> desde la notificación, previa "
                    "presentación de papeleta de conciliación ante el SMAC u organismo competente.",
                    st_body
                ))
                story.append(Spacer(1, 2*mm))
                story.append(_P(f"Atentamente,<br/><b>{emp_nombre}</b>", st_body))

            # =================================================================
            elif self._tipo == "CERTIFICADO":
            # =================================================================
                subtipo_label = subtipo or "EMPRESA"
                story.append(_sec_header("CERTIFICADO LABORAL — " + subtipo_label))
                story.append(Spacer(1, 2*mm))
                story.append(_P(
                    f"D./Dña. _________________________, en calidad de representante legal de "
                    f"<b>{emp_nombre}</b> (CIF: {emp_cif}), con domicilio en {emp_dir},",
                    st_body
                ))
                story.append(Spacer(1, 2*mm))
                story.append(_P("<b>CERTIFICA:</b>", st_h2))
                story.append(Spacer(1, 1*mm))
                cert_body = {
                    "VIDA LABORAL": (
                        f"Que <b>{trab}</b> (NIF/NIE: {nif}, Nº SS: {ss or '—'}), ha mantenido "
                        f"relación laboral con esta empresa, constando su alta en la Seguridad Social "
                        f"a efectos de {fecha}. El presente certificado se expide a petición del/de la "
                        f"interesado/a para los fines que estime conveniente."
                    ),
                    "COTIZACIÓN": (
                        f"Que <b>{trab}</b> (NIF/NIE: {nif}), figura en los registros de cotización "
                        f"de esta empresa como trabajador/a en alta. El salario bruto mensual es de "
                        f"{divisas.formatear(salario_mensual)} con las retenciones de IRPF y cotizaciones a la "
                        f"Seguridad Social que legalmente corresponden."
                    ),
                    "EMPRESA": (
                        f"Que los datos de la empresa <b>{emp_nombre}</b> son correctos y están "
                        f"debidamente registrados en las administraciones competentes. "
                        f"CIF: {emp_cif}. IBAN: {emp_iban or '—'}. "
                        f"Tel: {emp_tel or '—'}. Email: {emp_email or '—'}."
                    ),
                }.get(subtipo_label,
                      f"Los datos del/de la trabajador/a {trab} son verídicos según los registros internos.")
                story.append(_P(cert_body, st_body))
                if obs:
                    story.append(Spacer(1, 3*mm))
                    story.append(_P(obs, st_body))
                story.append(Spacer(1, 5*mm))
                story.append(_P(
                    f"Y para que así conste y surta los efectos oportunos, se expide el presente "
                    f"certificado en {emp_dir or '_______________'} a {_fecha_larga(now)}.",
                    st_body
                ))

            # =================================================================
            elif self._tipo in ("ALTA", "BAJA"):
            # =================================================================
                accion = "ALTA" if self._tipo == "ALTA" else "BAJA"
                story.append(_sec_header(f"COMUNICACIÓN DE {accion} LABORAL EN SEGURIDAD SOCIAL"))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DEL EMPLEADOR"))
                story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
                story.append(_data_val_row(("CCC", emp_ccc or "—"), ("DOMICILIO", emp_dir)))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
                story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
                story.append(_data_val_row(("Nº SEG. SOCIAL", ss or "—"), ("FECHA EFECTO", fecha)))
                story.append(Spacer(1, 3*mm))
                story.append(_P(
                    f"Se comunica el <b>{accion} LABORAL</b> en la Seguridad Social de "
                    f"<b>{trab}</b> (NIF/NIE: {nif}), con efectos desde el <b>{fecha}</b>, "
                    f"en la empresa <b>{emp_nombre}</b> (CIF: {emp_cif}), conforme a la "
                    f"Ley General de la Seguridad Social (RDL 8/2015) y normativa vigente.",
                    st_body
                ))
                if obs:
                    story.append(Spacer(1, 3*mm))
                    story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))

            # =================================================================
            elif self._tipo == "FINIQUITO":
            # =================================================================
                story.append(_sec_header("LIQUIDACIÓN Y FINIQUITO"))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DEL EMPLEADOR"))
                story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
                story.append(Spacer(1, 1*mm))
                story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
                story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
                story.append(_data_val_row(("PUESTO", puesto or "—"), ("FECHA EXTINCIÓN", fecha)))
                story.append(Spacer(1, 2*mm))
                story.append(_P(
                    f"La empresa <b>{emp_nombre}</b> (CIF: {emp_cif}) y el/la trabajador/a "
                    f"<b>{trab}</b> (NIF/NIE: {nif}) acuerdan la extinción definitiva de la relación "
                    f"laboral con efectos del <b>{fecha}</b>, procediéndose a la liquidación y finiquito "
                    "de los haberes pendientes conforme al siguiente desglose:",
                    st_body
                ))
                story.append(Spacer(1, 2*mm))
                fin_th = _st("fth", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10)
                fin_data = [
                    [Paragraph(self._pdf_tr("CONCEPTO"), fin_th), Paragraph(self._pdf_tr("IMPORTE (€)"), _st("fthc", fontName=_FB, fontSize=8, textColor=NEGRO, leading=10, alignment=TA_CENTER))],
                    [self._pdf_tr("Vacaciones no disfrutadas"), "___________"],
                    [self._pdf_tr("Parte proporcional pagas extraordinarias"), "___________"],
                    [self._pdf_tr("Salarios pendientes de pago"), "___________"],
                    [self._pdf_tr("Indemnización por extinción"), "___________"],
                    [self._pdf_tr("Otros conceptos"), "___________"],
                    [
                        Paragraph("<b>"+self._pdf_tr("TOTAL FINIQUITO")+"</b>", _st("ft", fontName=_FB, fontSize=9, textColor=NEGRO, leading=11)),
                        Paragraph("<b>___________</b>", _st("ft2", fontName=_FB, fontSize=9, textColor=NEGRO, leading=11, alignment=TA_CENTER)),
                    ],
                ]
                fin_tbl = Table(fin_data, colWidths=[usable_w*0.7, usable_w*0.3])
                fin_tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0,0),(-1,0), GRIS_CLR),
                    ("FONTNAME", (0,1),(-1,-2), _FN),
                    ("FONTSIZE", (0,0),(-1,-1), 8.5),
                    ("ALIGN", (1,0),(-1,-1), "CENTER"),
                    ("GRID", (0,0),(-1,-1), 0.4, BORDE),
                    ("BOX", (0,0),(-1,-1), 0.8, BORDE_OSC),
                    ("ROWBACKGROUNDS", (0,1),(-1,-2), [BLANCO, HexColor("#F7F7F7")]),
                    ("BACKGROUND", (0,-1),(-1,-1), AZUL_CLR),
                    ("LINEABOVE", (0,-1),(-1,-1), 1.5, AZUL),
                    ("TOPPADDING", (0,0),(-1,-1), 4),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                    ("LEFTPADDING", (0,0),(-1,-1), 6),
                    ("RIGHTPADDING", (0,0),(-1,-1), 6),
                ]))
                story.append(fin_tbl)
                if obs:
                    story.append(Spacer(1, 3*mm))
                    story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))
                story.append(Spacer(1, 3*mm))
                story.append(_P(
                    "El/La trabajador/a declara recibir la cantidad total correspondiente al finiquito y, "
                    "con su firma, reconoce que no tiene ninguna reclamación adicional pendiente contra "
                    "la empresa derivada de la relación laboral extinguida, salvo los derechos que "
                    "legalmente no sean renunciables.",
                    st_body
                ))

            # =================================================================
            elif self._tipo == "RESUMEN FISCAL":
            # =================================================================
                subtipo_label = subtipo or "TRIMESTRAL"
                story.append(_sec_header("DATOS DEL OBLIGADO TRIBUTARIO"))
                story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
                story.append(_data_val_row(("DOMICILIO FISCAL", emp_dir)))
                story.append(Spacer(1, 2*mm))
                story.append(_sec_header(f"RESUMEN FISCAL — {subtipo_label}  |  {fecha}"))
                story.append(Spacer(1, 2*mm))
                story.append(_P(
                    f"Resumen fiscal <b>{subtipo_label.lower()}</b> de la empresa <b>{emp_nombre}</b> "
                    f"(CIF: {emp_cif}). Ejercicio registrado a {now.strftime('%d/%m/%Y')}. "
                    "Los importes reflejados corresponden a las obligaciones tributarias del período "
                    "indicado y deben ser revisados por el/la asesor/a fiscal responsable antes de su "
                    "presentación ante la Agencia Tributaria (AEAT).",
                    st_body
                ))
                if obs:
                    story.append(Spacer(1, 3*mm))
                    story.append(_P(f"<b>Notas:</b> {obs}", st_body))

            # =================================================================
            else:
            # =================================================================
                story.append(_P(
                    obs or f"Documento generado por Smart Manager — Ref: {doc_id}", st_body))

            # ── Observaciones generales ───────────────────────────────────────
            if obs and self._tipo not in ("CARTA DESPIDO", "CERTIFICADO", "ALTA", "BAJA",
                                          "FINIQUITO", "RESUMEN FISCAL", "CONTRATO"):
                story.append(Spacer(1, 3*mm))
                story.append(_sec_header("OBSERVACIONES"))
                story.append(Spacer(1, 1*mm))
                story.append(_P(obs, st_clause))

            # ── Firmas ────────────────────────────────────────────────────────
            story.append(Spacer(1, 7*mm))
            sig_lugar_fecha = (
                f"En {emp_municipio or emp_dir or '_______________'}, "
                f"a {_fecha_larga(now)}"
            )
            story.append(_P(sig_lugar_fecha, st_body))
            story.append(Spacer(1, 5*mm))
            sig_data = [
                [
                    Paragraph(self._pdf_tr("El/La trabajador/a"), st_sign_lbl),
                    Paragraph(self._pdf_tr("El/La representante<br/>de la Empresa"), st_sign_lbl),
                    Paragraph(self._pdf_tr("El/La representante legal del/de la menor, si procede"), st_sign_lbl),
                ],
                [Spacer(1, 2.0*cm), Spacer(1, 2.0*cm), Spacer(1, 2.0*cm)],
                [
                    Paragraph(f"<b>{trab}</b><br/>{nif}", st_sign_val),
                    Paragraph(
                        (f"<b>{rep_nombre_full}</b><br/>{rep_nif}" if rep_nombre_full
                         else f"<b>{emp_nombre}</b><br/>{emp_cif}"),
                        st_sign_val),
                    Paragraph("________________________", st_sign_val),
                ],
            ]
            sig_tbl = Table(sig_data, colWidths=[usable_w/3]*3)
            sig_tbl.setStyle(TableStyle([
                ("BOX", (0,0),(-1,-1), 0.8, BORDE_OSC),
                ("INNERGRID", (0,0),(-1,-1), 0.4, BORDE),
                ("TOPPADDING", (0,0),(-1,-1), 5),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
                ("LEFTPADDING", (0,0),(-1,-1), 8),
                ("RIGHTPADDING", (0,0),(-1,-1), 8),
                ("ALIGN", (0,0),(-1,-1), "CENTER"),
                ("VALIGN", (0,0),(-1,-1), "TOP"),
                ("BACKGROUND", (0,0),(-1,0), GRIS_CLR),
                ("LINEBELOW", (0,1),(-1,1), 0.5, NEGRO),
            ]))
            story.append(KeepTogether([sig_tbl]))

            # ── Nota legal final ──────────────────────────────────────────────
            story.append(Spacer(1, 4*mm))
            story.append(HRFlowable(width=usable_w, thickness=0.5, color=BORDE))
            story.append(Spacer(1, 1*mm))
            story.append(_P(
                "(1) Director/a, Gerente, etc.  ·  "
                "(2) Padre, madre, tutor/a o persona o institución que le tenga a su cargo.  ·  "
                "IMPORTANTE: Todas las páginas cumplimentadas deberán ir firmadas en el margen "
                "izquierdo para mayor seguridad jurídica.",
                _st("nota", fontName=_FN, fontSize=6.5, textColor=GRIS, leading=9, alignment=TA_JUSTIFY)
            ))

            doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
            self._pdf_ruta = ruta

        except Exception:
            import traceback
            LOG_DOCUMENTOS.exception("Error generando PDF (wizard fiscal)")
            traceback.print_exc()

    def _ir(self, d):
        self._paso = max(0, min(3, self._paso + d)); self._render()


class _BanearDialog(QDialog):
    """Confirmación para banear un artículo de devolución, con motivo editable."""

    def __init__(self, codigo, nombre, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build(codigo, nombre)

    def _build(self, codigo, nombre):
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(12)

        t = QLabel("🚫  " + tr("cfg.ban_dlg_titulo", default="BANEAR ARTÍCULO PARA DEVOLUCIÓN"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)
        info = QLabel(tr("cfg.ban_dlg_art", default="{cod}  ·  {nom}", cod=codigo, nom=nombre or ""))
        info.setStyleSheet("color:#E6EDF3;font-family:'Segoe UI';font-size:13px;font-weight:700;background:#161B22;border:1px solid #30363D;border-radius:8px;padding:9px 11px;")
        info.setWordWrap(True); ly.addWidget(info)

        lbl = QLabel(tr("cfg.ban_dlg_motivo", default="MOTIVO (se mostrará en el TPV):"))
        lbl.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-weight:900;font-size:11px;background:transparent;border:none;")
        ly.addWidget(lbl)
        self.inp_motivo = QLineEdit(tr("cfg.ban_dlg_motivo_def", default="Artículo no retornable por política de la empresa."))
        self.inp_motivo.setFixedHeight(38)
        self.inp_motivo.setStyleSheet(f"QLineEdit{{background:#0D1117;color:white;border:2px solid {_CIAN};border-radius:10px;padding:0 12px;}}")
        ly.addWidget(self.inp_motivo)

        botones = QHBoxLayout(); botones.addStretch()
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedSize(140, 42)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(f"QPushButton{{background:#0E1117;color:#F85149;border:2px solid #F85149;border-radius:10px;font-weight:900;}}QPushButton:hover{{background:#F85149;color:#0E1117;}}")
        bc.clicked.connect(self.reject)
        bk = QPushButton("✔  " + tr("cfg.ban_dlg_aceptar", default="ACEPTAR")); bk.setFixedSize(180, 42)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:#0E1117;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        bk.clicked.connect(self.accept)
        botones.addWidget(bc); botones.addWidget(bk); ly.addLayout(botones)
        self.setFixedWidth(540)

    def motivo(self) -> str:
        return self.inp_motivo.text().strip()


class _FormDialogCorp(QDialog):
    """Diálogo genérico de alta/edición para datos corporativos
    (representantes legales y centros de trabajo)."""

    def __init__(self, titulo, campos, valores=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._campos = campos
        self._inps = {}
        self._build(titulo, valores or {})

    def _build(self, titulo, valores):
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        gl = QVBoxLayout(inner); gl.setContentsMargins(0, 0, 8, 0); gl.setSpacing(6)
        from PyQt6.QtWidgets import QComboBox
        self._combos = set()
        for campo in self._campos:
            key, label = campo[0], campo[1]
            choices = campo[2] if len(campo) > 2 else None
            lb = QLabel(label)
            lb.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:14px;font-weight:700;background:transparent;border:none;")
            gl.addWidget(lb)
            val = valores.get(key, "")
            if not val and key == "pais":
                val = "ESPAÑA"
            if choices:
                w = QComboBox(); w.setFixedHeight(38)
                w.addItems(list(choices))
                w.setStyleSheet(
                    f"QComboBox{{background:#161B22;color:white;border:2px solid {_CIAN};border-radius:8px;padding:0 12px;font-size:12px;}}"
                    f"QComboBox QAbstractItemView{{background:#0D1117;color:#E6EDF3;border:2px solid {_CIAN};border-radius:8px;"
                    f"selection-background-color:{_CIAN};selection-color:#0D1117;outline:none;padding:6px;}}"
                    f"QComboBox QAbstractItemView::item{{min-height:34px;padding:0 12px;border-radius:6px;}}")
                if val:
                    if w.findText(str(val)) < 0:
                        w.insertItem(0, str(val))
                    w.setCurrentText(str(val))
                self._combos.add(key)
                self._inps[key] = w; gl.addWidget(w)
            else:
                e = QLineEdit(str(val or "")); e.setFixedHeight(36)
                e.setStyleSheet(f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};border-radius:8px;padding:0 12px;font-size:12px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
                self._inps[key] = e; gl.addWidget(e)
        scroll.setWidget(inner); ly.addWidget(scroll, 1)
        br = QHBoxLayout(); br.addStretch()
        bc = QPushButton(tr("cfg.ban_cancelar", default="CANCELAR")); bc.setFixedHeight(38)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0E1117;color:#F85149;border:2px solid #F85149;border-radius:8px;font-weight:900;font-size:12px;padding:0 18px;}QPushButton:hover{background:#F85149;color:#0E1117;}")
        bc.clicked.connect(self.reject)
        bg = QPushButton(tr("cfg.de_guardar_corto", default="GUARDAR")); bg.setFixedHeight(38)
        bg.setCursor(Qt.CursorShape.PointingHandCursor)
        bg.setStyleSheet("QPushButton{background:#0E1117;color:#3FB950;border:2px solid #3FB950;border-radius:8px;font-weight:900;font-size:12px;padding:0 18px;}QPushButton:hover{background:#3FB950;color:#0E1117;}")
        bg.clicked.connect(self.accept)
        br.addWidget(bc); br.addWidget(bg); ly.addLayout(br)
        self.setFixedSize(560, min(640, 200 + 64 * len(self._campos)))

    def valores(self):
        out = {}
        for k, w in self._inps.items():
            if k in getattr(self, "_combos", set()):
                out[k] = w.currentText().strip()
            else:
                out[k] = w.text().strip()
        return out


class ConfiguracionWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()
        self.callback_vuelta = callback_vuelta
        self.usuario = usuario
        self.setWindowTitle(tr("cfg.window_title", default="CONFIGURACIÓN DEL SISTEMA"))
        self.resize(1200, 800)
        self.setStyleSheet(f"background-color: {_FONDO};")
        # Inicializado aquí porque la página de citas se crea de forma diferida
        # (lazy load) y _cerrar_cal_popup puede llamarse antes de visitarla.
        self._cal_popup = None
        self.setup_ui()
        # Abrir directamente en una pestaña concreta (p. ej. desde "VER CITA").
        ti = kwargs.get("tab_inicial")
        if ti is not None and hasattr(self, "btns") and 0 <= ti < len(self.btns):
            try:
                self.btns[ti].click()
            except Exception:
                pass

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SIDEBAR ---
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(
            f"background-color: {_PANEL_BG}; border-right: 1px solid #30363D;"
        )
        side_ly = QVBoxLayout(sidebar)

        lbl_tit = QLabel(tr("cfg.smart_config", default="SMART CONFIG"))
        lbl_tit.setStyleSheet(
            "color: white; font-weight: 900; font-size: 14px; margin: 30px; letter-spacing: 2px;"
        )
        side_ly.addWidget(lbl_tit)

        # Scroll para la Sidebar
        scroll_side = QScrollArea()
        scroll_side.setWidgetResizable(True)
        scroll_side.setStyleSheet("background: transparent; border: none;")
        side_content = QWidget()
        self.side_btns_ly = QVBoxLayout(side_content)
        self.side_btns_ly.setSpacing(5)

        self._tab_keys = [
            "cfg.tab_caja", "cfg.tab_plazo", "cfg.tab_perfil", "cfg.tab_horario",
            "cfg.tab_fichajes", "cfg.tab_logo", "cfg.tab_citas", "cfg.tab_fiscalidad",
            "cfg.tab_referencia", "cfg.tab_datos_empresa",
        ]
        _tab_def = [
            "GESTIÓN CAJA", "PLAZO DEVOLUCIÓN", "GENERAR PERFIL EMPLEADO",
            "HORARIO EMPLEADOS", "FICHAJES", "LOGO CORPORATIVO",
            "PLANIFICAR CITAS", "FISCALIDAD", "ASIGNAR REFERENCIA",
            "DATOS DE EMPRESA",
        ]

        self.btns = []
        for i, key in enumerate(self._tab_keys):
            btn = _SidebarBtn(tr(key, default=_tab_def[i]))
            btn.clicked.connect(lambda _, idx=i: self._cambiar_vista(idx))
            self.side_btns_ly.addWidget(btn)
            self.btns.append(btn)

        self.side_btns_ly.addStretch()
        scroll_side.setWidget(side_content)
        side_ly.addWidget(scroll_side)

        self._btn_salir = btn_salir = _SidebarBtn(tr("cfg.exit", default="SALIR AL MENÚ"))
        btn_salir.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #F85149;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
            }
            QPushButton:hover { background-color: #F85149; color: #0E1117; border-radius: 0px; }
        """)
        btn_salir.clicked.connect(self.ejecutar_regreso)
        side_ly.addWidget(btn_salir)

        # --- STACKED WIDGET (lazy load) ---
        # Construir las 9 páginas en el __init__ hacía la apertura lenta y en
        # blanco (p. ej. _crear_page_fiscalidad ~250 ms). Ahora solo se construye
        # la página inicial; el resto se crean la primera vez que se visitan.
        self.stack = QStackedWidget()
        self._page_builders = {
            0: self._crear_page_caja,
            1: self._crear_page_plazo_devolucion,
            2: self._crear_page_perfiles,
            3: self._crear_page_horarios,
            4: self._crear_page_fichajes,
            5: self._crear_page_logo,
            6: self._crear_page_citas,
            7: self._crear_page_fiscalidad,
            8: self._crear_page_referencia,
            9: self._crear_page_datos_empresa,
        }
        self._loaded_pages = set()
        for i in range(len(self._page_builders)):
            if i == 0:
                self.stack.addWidget(self._crear_page_caja())
                self._loaded_pages.add(0)
            else:
                self.stack.addWidget(QWidget())  # placeholder — se crea al visitarla

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)
        self.btns[0].setChecked(True)
        i18n.conectar_retraduccion(self, self._retraducir_cfg)

    def _retraducir_cfg(self):
        """Re-traduce el chrome (título, pestañas, salir) al cambiar de idioma."""
        self.setWindowTitle(tr("cfg.window_title", default="CONFIGURACIÓN DEL SISTEMA"))
        _tab_def = [
            "GESTIÓN CAJA", "PLAZO DEVOLUCIÓN", "GENERAR PERFIL EMPLEADO",
            "HORARIO EMPLEADOS", "FICHAJES", "LOGO CORPORATIVO",
            "PLANIFICAR CITAS", "FISCALIDAD", "ASIGNAR REFERENCIA",
            "DATOS DE EMPRESA",
        ]
        for i, btn in enumerate(self.btns):
            _def = _tab_def[i] if i < len(_tab_def) else ""
            btn.setText(tr(self._tab_keys[i], default=_def))
        if hasattr(self, "_btn_salir"):
            self._btn_salir.setText(tr("cfg.exit", default="SALIR AL MENÚ"))

    def _ensure_page(self, index):
        """Construye la página `index` la primera vez que se visita (lazy load)."""
        if index in self._loaded_pages:
            return
        builder = self._page_builders.get(index)
        if builder is None:
            return
        page = builder()
        old = self.stack.widget(index)
        self.stack.insertWidget(index, page)
        self.stack.removeWidget(old)
        old.deleteLater()
        self._loaded_pages.add(index)

    def _cambiar_vista(self, index):
        # Access control: HORARIO EMPLEADOS (index 3) — ADMINISTRADOR and GERENTE only
        if index == 3:
            if not (sesion_global and sesion_global.es_admin()):
                mostrar_mensaje(
                    self, tr("cfg.access_restricted_title", default="Acceso restringido"),
                    tr("cfg.access_restricted_msg", default="Solo ADMINISTRADOR y GERENTE pueden gestionar horarios."), "error"
                )
                return
        self._ensure_page(index)
        if index != self.stack.currentIndex() and hasattr(self, "_cerrar_cal_popup"):
            self._cerrar_cal_popup()
        self.stack.setCurrentIndex(index)
        if index == 2:  # Perfiles
            self.refrescar_datos_usuarios()
        elif index == 6:  # Citas — refresh calendar markers
            if hasattr(self, "_cal_widget"):
                self._cal_widget.update()

    # ============================================================
    # PESTAÑA 10: DATOS DE EMPRESA (fuente única de datos corporativos)
    # ============================================================
    # Cargos que pueden ejercer como representante legal (desplegable).
    _CARGOS_REP = [
        "ADMINISTRADOR/A ÚNICO/A", "ADMINISTRADOR/A SOLIDARIO/A",
        "ADMINISTRADOR/A MANCOMUNADO/A", "CONSEJERO/A DELEGADO/A",
        "APODERADO/A", "GERENTE", "DIRECTOR/A GENERAL",
        "DIRECTOR/A DE RECURSOS HUMANOS", "REPRESENTANTE LEGAL",
    ]
    _CAMPOS_REP = [
        ("nombre", "Nombre"), ("apellidos", "Apellidos"), ("dni_nie", "DNI / NIE"),
        ("cargo", "Cargo", _CARGOS_REP), ("telefono", "Teléfono"), ("email", "Email"),
    ]
    # Cada código va JUSTO después de su campo.
    _CAMPOS_CT = [
        ("nombre_centro", "Nombre del centro"), ("direccion", "Dirección"),
        ("codigo_postal", "Código postal"),
        ("municipio", "Municipio"), ("cod_municipio", "Cód. municipio (SEPE)"),
        ("provincia", "Provincia"), ("comunidad_autonoma", "Comunidad autónoma"),
        ("pais", "País"), ("cod_pais", "Cód. país (ej. 724)"),
        ("telefono", "Teléfono"), ("email", "Email"),
        ("codigo_cuenta_cotizacion", "Cuenta de cotización (CCC)"),
        ("actividad_economica", "Actividad económica"),
        ("cod_actividad", "Cód. actividad económica"),
    ]

    def _de_lbl(self, t):
        l = QLabel(t)
        l.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:14px;font-weight:700;background:transparent;")
        return l

    def _de_inp(self, val=""):
        e = QLineEdit(str(val or "")); e.setFixedHeight(38)
        e.setStyleSheet(f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};border-radius:8px;padding:0 12px;font-size:12px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        return e

    def _de_sec(self, t):
        l = QLabel("  " + t)
        l.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:12px;background:#161B22;border-radius:6px;padding:7px 10px;")
        return l

    def _de_btn_verde(self, txt, slot):
        b = QPushButton(txt); b.setFixedHeight(40); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:#0E1117;color:#3FB950;border:2px solid #3FB950;border-radius:10px;font-weight:900;font-size:12px;padding:0 18px;}QPushButton:hover{background:#3FB950;color:#0E1117;}")
        b.clicked.connect(slot); return b

    def _de_btn_cian(self, txt, slot):
        b = QPushButton(txt); b.setFixedHeight(36); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:#0E1117;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;font-size:11px;padding:0 14px;}}QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        b.clicked.connect(slot); return b

    def _de_mini(self, txt, color, slot):
        b = QPushButton(txt); b.setFixedSize(38, 32); b.setCursor(Qt.CursorShape.PointingHandCursor)
        # Fuente con glifos (la global es un TTF que no incluye estos iconos).
        b.setStyleSheet(
            f"QPushButton{{background:#0E1117;color:{color};border:2px solid {color};"
            f"border-radius:8px;font-family:'Segoe UI Emoji','Segoe UI Symbol','Segoe UI';"
            f"font-size:15px;font-weight:900;padding:0;}}"
            f"QPushButton:hover{{background:{color};color:#0E1117;}}")
        b.clicked.connect(slot); return b

    def _de_tabla(self, headers):
        t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.verticalHeader().setDefaultSectionSize(46)
        t.setMinimumHeight(150)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Fondo TRANSPARENTE: así el rectángulo de la tabla no tapa las esquinas
        # redondeadas del marco neón (el #0D1117 del wrap se ve a través).
        t.setStyleSheet(
            "QTableWidget{background:transparent;color:#E6EDF3;border:none;gridline-color:#21262D;font-size:12px;}"
            "QTableWidget::item{padding:6px;border-bottom:1px solid #21262D;background:transparent;}"
            "QHeaderView{background:transparent;border:none;}"
            f"QHeaderView::section{{background:#161B22;color:{_CIAN};border:none;padding:9px;font-weight:900;font-size:12px;}}"
            # Primera/última cabecera: redondeo de las 4 esquinas externas (barra tipo pastilla)
            f"QHeaderView::section:first{{border-top-left-radius:9px;border-bottom-left-radius:9px;}}"
            f"QHeaderView::section:last{{border-top-right-radius:9px;border-bottom-right-radius:9px;}}"
            f"QHeaderView::section:hover{{background:{_CIAN};color:#0E1117;}}"
        )
        return t

    def _de_wrap(self, tabla):
        wrap = QFrame()
        wrap.setStyleSheet(f"QFrame{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        wl = QVBoxLayout(wrap); wl.setContentsMargins(8, 8, 8, 8); wl.addWidget(tabla)
        return wrap

    def _crear_page_datos_empresa(self):
        from src.db import centros as _cts
        from src.db import empresa as _emp
        from src.db import representantes as _reps
        self._de_emp_mod, self._de_reps_mod, self._de_cts_mod = _emp, _reps, _cts

        page = QWidget(); page.setStyleSheet(f"background:{_FONDO};")
        root = QVBoxLayout(page); root.setContentsMargins(40, 28, 40, 18); root.setSpacing(12)
        titulo = QLabel("🏢  " + tr("cfg.de_titulo", default="DATOS CORPORATIVOS DE LA EMPRESA"))
        titulo.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:22px;background:transparent;")
        root.addWidget(titulo)
        sub = QLabel(tr("cfg.de_sub", default="Fuente única de datos. Se reutilizan automáticamente en todos los documentos (contratos, facturas, certificados, informes…)."))
        sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;font-weight:700;background:transparent;")
        sub.setWordWrap(True); root.addWidget(sub)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 12, 0); il.setSpacing(10)

        self._de_admin = bool(sesion_global and sesion_global.es_admin())

        # ── BLOQUE EMPRESA ──
        il.addWidget(self._de_sec(tr("cfg.de_sec_empresa", default="EMPRESA")))
        emp = _emp.obtener_empresa() or {}
        self._de_fields = {}
        filas = [
            # Cada código va JUNTO a su campo correspondiente.
            [("razon_social", "Razón social:"), ("nombre_comercial", "Nombre comercial:")],
            [("cif_nif", "CIF / NIF:"), ("telefono", "Teléfono:")],
            [("email_principal", "Correo corporativo:"), ("direccion_fiscal", "Domicilio social:")],
            [("municipio", "Municipio:"), ("cod_municipio", "Cód. municipio:")],
            [("provincia", "Provincia:"), ("cod_provincia", "Cód. provincia:")],
            [("pais", "País:"), ("cod_pais", "Cód. país (ej. 724):")],
            [("actividad_economica", "Actividad económica:"), ("cod_actividad", "Cód. actividad económica:")],
            [("comunidad_autonoma", "Comunidad autónoma:"), ("cp", "Código postal:")],
            [("regimen_ss", "Régimen SS:"), ("ccc", "Cuenta de cotización (CCC):")],
            [("cnae", "CNAE:"), ("convenio_colectivo", "Convenio colectivo:")],
        ]
        for fila in filas:
            rl = QHBoxLayout(); rl.setSpacing(8)
            for key, label in fila:
                col = QVBoxLayout(); col.addWidget(self._de_lbl(label))
                inp = self._de_inp(emp.get(key, "") or ("ESPAÑA" if key == "pais" else ""))
                self._de_fields[key] = inp; col.addWidget(inp)
                rl.addLayout(col)
            il.addLayout(rl)

        # ── País fiscal (determina el IVA automáticamente; no toca precios) ──
        from src.utils import fiscalidad as _fisc
        rl_pf = QHBoxLayout(); rl_pf.setSpacing(8)
        col_pf = QVBoxLayout()
        col_pf.addWidget(self._de_lbl(tr("cfg.de_pais_fiscal", default="País fiscal (determina el IVA):")))
        self._de_pais_fiscal = _NeonComboBox(); self._de_pais_fiscal.setFixedHeight(38)
        self._de_pais_fiscal.setObjectName("de_pf_cb")
        # NO 'horario_cb': así el filtro global redondea el popup (SetWindowRgn,
        # 4 esquinas) y, al tener stylesheet inline, lo guarda en _sm_qss_saved y
        # lo restaura al cerrar → el contorno neón del campo PERSISTE.
        # combobox-popup:0 + máx. 5 opciones visibles con scrollbar.
        self._de_pais_fiscal.setMaxVisibleItems(5)
        self._de_pais_fiscal.setStyleSheet(
            "QComboBox#de_pf_cb{combobox-popup:0;background:#161B22;color:white;"
            f"border:2px solid {_CIAN};border-radius:8px;padding:0 12px;font-size:12px;font-family:'Segoe UI';}}"
            "QComboBox#de_pf_cb::drop-down{border:none;width:24px;}"
        )
        for p in _fisc.paises_disponibles():
            self._de_pais_fiscal.addItem(f"{p['nombre']}  ·  IVA {p['iva']:g}%", p["code"])
        _pf = (emp.get("pais_fiscal") or "ES").upper()
        _ix = self._de_pais_fiscal.findData(_pf)
        if _ix >= 0:
            self._de_pais_fiscal.setCurrentIndex(_ix)
        self._de_pais_fiscal.setEnabled(self._de_admin)
        col_pf.addWidget(self._de_pais_fiscal)
        col_iva = QVBoxLayout()
        col_iva.addWidget(self._de_lbl(tr("cfg.de_iva_auto", default="IVA aplicado (automático):")))
        self._de_iva_lbl = self._de_inp(f"{_fisc.iva_de_pais(_pf):g} %")
        self._de_iva_lbl.setReadOnly(True)
        col_iva.addWidget(self._de_iva_lbl)

        def _pf_changed(_i):
            code = self._de_pais_fiscal.currentData()
            self._de_iva_lbl.setText(f"{_fisc.iva_de_pais(code):g} %")
        self._de_pais_fiscal.currentIndexChanged.connect(_pf_changed)
        rl_pf.addLayout(col_pf, 1); rl_pf.addLayout(col_iva, 1)
        il.addLayout(rl_pf)

        bg = QHBoxLayout(); bg.addStretch()
        self._de_btn_guardar = self._de_btn_verde(
            tr("cfg.de_guardar", default="GUARDAR DATOS DE EMPRESA"), self._de_guardar_empresa)
        self._de_btn_guardar.setEnabled(self._de_admin); bg.addWidget(self._de_btn_guardar)
        il.addLayout(bg)

        # ── BLOQUE REPRESENTANTES LEGALES ──
        hr = QHBoxLayout(); hr.addWidget(self._de_sec(tr("cfg.de_sec_reps", default="REPRESENTANTES LEGALES")), 1)
        self._de_btn_add_rep = self._de_btn_cian(tr("cfg.de_add_rep", default="➕  AÑADIR REPRESENTANTE"), self._de_add_rep)
        self._de_btn_add_rep.setEnabled(self._de_admin); hr.addWidget(self._de_btn_add_rep)
        il.addLayout(hr)
        self._tabla_reps = self._de_tabla(["NOMBRE", "DNI / NIE", "CARGO", "PRINCIPAL", "ACCIONES"])
        il.addWidget(self._de_wrap(self._tabla_reps))

        # ── BLOQUE CENTROS DE TRABAJO ──
        hc = QHBoxLayout(); hc.addWidget(self._de_sec(tr("cfg.de_sec_centros", default="CENTROS DE TRABAJO")), 1)
        self._de_btn_add_ct = self._de_btn_cian(tr("cfg.de_add_ct", default="➕  AÑADIR CENTRO"), self._de_add_centro)
        self._de_btn_add_ct.setEnabled(self._de_admin); hc.addWidget(self._de_btn_add_ct)
        il.addLayout(hc)
        self._tabla_cts = self._de_tabla(["CÓDIGO", "NOMBRE", "MUNICIPIO", "CCC", "PRINCIPAL", "ACCIONES"])
        il.addWidget(self._de_wrap(self._tabla_cts))

        il.addStretch()
        scroll.setWidget(inner); root.addWidget(scroll, 1)
        self._de_refrescar_reps(); self._de_refrescar_centros()
        return page

    def _de_guardar_empresa(self):
        if not getattr(self, "_de_admin", False):
            return
        campos = {k: e.text().strip() for k, e in self._de_fields.items()}
        if hasattr(self, "_de_pais_fiscal"):
            campos["pais_fiscal"] = self._de_pais_fiscal.currentData() or "ES"
        self._de_emp_mod.actualizar_empresa(self._de_emp_mod.empresa_actual_id(), **campos)
        mostrar_mensaje(
            self, tr("cfg.de_ok_t", default="Datos guardados"),
            tr("cfg.de_ok_msg", default="Los datos de empresa se han guardado y se usarán automáticamente en todos los documentos."),
            "info")

    def _de_refrescar_reps(self):
        reps = self._de_reps_mod.listar_representantes()
        t = self._tabla_reps; t.setRowCount(len(reps))
        for r, rep in enumerate(reps):
            nom = " ".join(x for x in [rep.get("nombre"), rep.get("apellidos")] if x) or "—"
            t.setItem(r, 0, QTableWidgetItem(nom))
            t.setItem(r, 1, QTableWidgetItem(rep.get("dni_nie") or "—"))
            t.setItem(r, 2, QTableWidgetItem(rep.get("cargo") or "—"))
            pr = QTableWidgetItem("★ SÍ" if rep.get("es_principal") else "—")
            pr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rep.get("es_principal"):
                pr.setForeground(QColor("#D29922"))
            t.setItem(r, 3, pr)
            cont = QWidget(); cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont); hl.setContentsMargins(4, 0, 4, 0); hl.setSpacing(6)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._de_admin:
                if not rep.get("es_principal"):
                    hl.addWidget(self._de_mini("★", "#D29922",
                        lambda _=0, i=rep.get("id_representante"): self._de_principal_rep(i)))
                hl.addWidget(self._de_mini("✎", _CIAN, lambda _=0, d=rep: self._de_edit_rep(d)))
                hl.addWidget(self._de_mini("🗑", "#F85149",
                    lambda _=0, i=rep.get("id_representante"): self._de_baja_rep(i)))
            t.setCellWidget(r, 4, cont)

    def _de_refrescar_centros(self):
        cts = self._de_cts_mod.listar_centros()
        t = self._tabla_cts; t.setRowCount(len(cts))
        for r, ct in enumerate(cts):
            t.setItem(r, 0, QTableWidgetItem(ct.get("codigo_centro") or "—"))
            t.setItem(r, 1, QTableWidgetItem(ct.get("nombre_centro") or "—"))
            t.setItem(r, 2, QTableWidgetItem(ct.get("municipio") or "—"))
            t.setItem(r, 3, QTableWidgetItem(ct.get("codigo_cuenta_cotizacion") or "—"))
            pr = QTableWidgetItem("★ SÍ" if ct.get("es_principal") else "—")
            pr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ct.get("es_principal"):
                pr.setForeground(QColor("#D29922"))
            t.setItem(r, 4, pr)
            cont = QWidget(); cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont); hl.setContentsMargins(4, 0, 4, 0); hl.setSpacing(6)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._de_admin:
                if not ct.get("es_principal"):
                    hl.addWidget(self._de_mini("★", "#D29922",
                        lambda _=0, i=ct.get("id_centro"): self._de_principal_centro(i)))
                hl.addWidget(self._de_mini("✎", _CIAN, lambda _=0, d=ct: self._de_edit_centro(d)))
                hl.addWidget(self._de_mini("🗑", "#F85149",
                    lambda _=0, i=ct.get("id_centro"): self._de_baja_centro(i)))
            t.setCellWidget(r, 5, cont)

    def _de_add_rep(self):
        if not self._de_admin:
            return
        dlg = _FormDialogCorp(tr("cfg.de_nuevo_rep", default="NUEVO REPRESENTANTE LEGAL"), self._CAMPOS_REP, {}, self)
        if dlg.exec():
            self._de_reps_mod.crear_representante(**dlg.valores()); self._de_refrescar_reps()

    def _de_edit_rep(self, rep):
        if not self._de_admin:
            return
        dlg = _FormDialogCorp(tr("cfg.de_edit_rep", default="EDITAR REPRESENTANTE"), self._CAMPOS_REP, rep, self)
        if dlg.exec():
            self._de_reps_mod.actualizar_representante(rep.get("id_representante"), **dlg.valores())
            self._de_refrescar_reps()

    def _de_principal_rep(self, i):
        self._de_reps_mod.marcar_principal(i); self._de_refrescar_reps()

    def _de_baja_rep(self, i):
        self._de_reps_mod.baja_representante(i); self._de_refrescar_reps()

    def _de_add_centro(self):
        if not self._de_admin:
            return
        dlg = _FormDialogCorp(tr("cfg.de_nuevo_ct", default="NUEVO CENTRO DE TRABAJO"), self._CAMPOS_CT, {}, self)
        if dlg.exec():
            self._de_cts_mod.crear_centro(**dlg.valores()); self._de_refrescar_centros()

    def _de_edit_centro(self, ct):
        if not self._de_admin:
            return
        dlg = _FormDialogCorp(tr("cfg.de_edit_ct", default="EDITAR CENTRO DE TRABAJO"), self._CAMPOS_CT, ct, self)
        if dlg.exec():
            self._de_cts_mod.actualizar_centro(ct.get("id_centro"), **dlg.valores())
            self._de_refrescar_centros()

    def _de_principal_centro(self, i):
        self._de_cts_mod.marcar_principal(i); self._de_refrescar_centros()

    def _de_baja_centro(self, i):
        self._de_cts_mod.baja_centro(i); self._de_refrescar_centros()

    # --- PESTAÑA 1: GESTIÓN CAJA ---
    def _crear_selector_divisa(self):
        """Selector de DIVISA EMPRESA (global, independiente del idioma). Solo lo
        pueden cambiar ADMINISTRADOR y GERENTE; al cambiarlo, las tablas de arqueo
        y los importes pasan a esa divisa (sin reiniciar)."""
        frame = QFrame()
        frame.setObjectName("divisaBox")
        frame.setFixedHeight(60)
        frame.setStyleSheet(f"QFrame#divisaBox{{background:#161B22;border:2px solid {_BORDE};border-radius:14px;}}")
        ly = QHBoxLayout(frame)
        ly.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(tr("cfg.divisa_empresa", default="💱  DIVISA DE LA EMPRESA:"))
        lbl.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:900;font-size:12px;background:transparent;border:none;")
        # _NeonComboBox: flecha PNG + popup + hover los aporta el estilado global
        # de la app (igual que el resto de desplegables), y abre correctamente.
        combo = _NeonComboBox()
        combo.setFixedHeight(38)
        combo.setMinimumWidth(320)
        combo.setMaxVisibleItems(10)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        # Borde neón ESTABLE: el filtro global guarda/restaura el QSS inline del
        # combo al abrir/cerrar el popup. Sin inline, lo restauraba a "" y en una
        # página persistente (no diálogo) el contorno turquesa se perdía tras el
        # primer ciclo. Con este QSS, el neón se conserva (y :on lo oculta mientras
        # el popup está abierto, para que solo el popup muestre el contorno).
        combo.setStyleSheet(
            f"QComboBox{{border:2px solid {_CIAN};border-radius:10px;}}"
            "QComboBox:on{border:2px solid transparent;}"
            f"QComboBox:disabled{{border:2px solid {_BORDE};}}"
        )
        for code in divisas.monedas_soportadas():
            inf = divisas.info(code)
            combo.addItem(f"{code} · {inf['nombre']} ({inf['simbolo']})", code)
        idx = combo.findData(divisas.divisa_actual())
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.setEnabled(bool(sesion_global and sesion_global.es_admin()))
        combo.currentIndexChanged.connect(
            lambda _i, c=combo: self._cambiar_divisa(c.currentData())
        )
        self._combo_divisa = combo
        ly.addWidget(lbl)
        ly.addStretch()
        ly.addWidget(combo)
        return frame

    def _cambiar_divisa(self, code):
        if not code or code == divisas.divisa_actual():
            return
        try:
            divisas.set_divisa(code)
            mostrar_mensaje(
                self, tr("cfg.divisa_title", default="Divisa actualizada"),
                tr("cfg.divisa_msg",
                   default="La divisa de la empresa es ahora {code}. Las tablas de "
                           "efectivo e importes se mostrarán en esta divisa.", code=code),
                "info",
            )
        except Exception as e:
            LOG_DOCUMENTOS.error("No se pudo cambiar la divisa: %s", e)
            mostrar_mensaje(
                self, tr("cfg.error_title", default="Error"),
                tr("cfg.divisa_error", default="No se pudo cambiar la divisa."), "error",
            )

    def _crear_page_caja(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(36, 30, 36, 30)
        outer.setSpacing(18)

        # ── Estado banner ────────────────────────────────────────────────────
        status_frame = QFrame()
        status_frame.setObjectName("cajaStatus")
        status_frame.setFixedHeight(60)
        status_frame.setStyleSheet(f"QFrame#cajaStatus{{background:#161B22;border:2px solid {_BORDE};border-radius:14px;}}")
        sf_ly = QHBoxLayout(status_frame); sf_ly.setContentsMargins(20, 0, 20, 0)

        lbl_estado_txt = QLabel(tr("cfg.caja_current_state", default="ESTADO ACTUAL:"))
        lbl_estado_txt.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:900;font-size:12px;background:transparent;border:none;")
        self._caja_status_lbl = QLabel("—")
        self._caja_status_lbl.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:900;font-size:14px;background:transparent;border:none;")
        self._caja_fondo_lbl = QLabel("")
        self._caja_fondo_lbl.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:12px;background:transparent;border:none;")
        self._caja_hora_lbl = QLabel("")
        self._caja_hora_lbl.setStyleSheet("color:#484F58;font-family:'Segoe UI';font-size:11px;background:transparent;border:none;")
        sf_ly.addWidget(lbl_estado_txt)
        sf_ly.addWidget(self._caja_status_lbl)
        sf_ly.addStretch()
        sf_ly.addWidget(self._caja_fondo_lbl)
        sf_ly.addSpacing(20)
        sf_ly.addWidget(self._caja_hora_lbl)
        outer.addWidget(status_frame)

        # ── Divisa de la empresa (independiente del idioma) ──────────────────
        outer.addWidget(self._crear_selector_divisa())

        # ── Grid de botones ──────────────────────────────────────────────────
        grid = QGridLayout(); grid.setSpacing(16)

        def _mk_btn(txt, icono=""):
            b = QPushButton(f"{icono}  {txt}" if icono else txt)
            b.setFixedSize(310, 88)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton{{background:#161B22;border:2px solid {_CIAN};color:white;
                             border-radius:14px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}
                QPushButton:hover{{background:{_CIAN};color:#0D1117;}}
                QPushButton:disabled{{background:#0D1117;border-color:{_BORDE};color:#484F58;}}
            """)
            return b

        self.btn_apertura    = _mk_btn(tr("cfg.btn_apertura", default="APERTURA"),                "🔓")
        self.btn_habilitar   = _mk_btn(tr("cfg.btn_habilitar", default="HABILITAR CAJA"),          "🖥️")
        self.btn_cierre_reg  = _mk_btn(tr("cfg.btn_cierre_reg", default="CIERRE CAJA REGISTRADORA"),"🔒")
        self.btn_cierre_fuerte = _mk_btn(tr("cfg.btn_cierre_fuerte", default="CIERRE CAJA FUERTE"),    "🏦")
        self.btn_movimiento  = _mk_btn(tr("cfg.btn_movimiento", default="MOVIMIENTOS DE EFECTIVO"),  "💸")
        self.btn_cambio_cajero = _mk_btn(tr("cfg.btn_cambio_cajero", default="CAMBIO DE CAJERO"),     "🔁")

        self.btn_apertura.clicked.connect(self._fn_apertura)
        self.btn_habilitar.clicked.connect(self._fn_habilitar_caja)
        self.btn_cierre_reg.clicked.connect(self._fn_cierre_reg)
        self.btn_cierre_fuerte.clicked.connect(self._fn_cierre_fuerte)
        self.btn_movimiento.clicked.connect(self._fn_movimiento)
        self.btn_cambio_cajero.clicked.connect(self._fn_cambio_cajero)

        grid.addWidget(self.btn_apertura,    0, 0)
        grid.addWidget(self.btn_habilitar,   0, 1)
        grid.addWidget(self.btn_cierre_reg,  1, 0)
        grid.addWidget(self.btn_cierre_fuerte, 1, 1)
        grid.addWidget(self.btn_movimiento,  2, 0)
        grid.addWidget(self.btn_cambio_cajero, 2, 1)
        outer.addLayout(grid)
        outer.addStretch()

        self._refresh_caja_ui()
        return page

    # ── Caja: estado ──────────────────────────────────────────────────────────

    def _nuevo_estado_caja(self) -> dict:
        return {"estado": "SIN_APERTURA", "fecha": datetime.now().strftime("%Y-%m-%d"),
                "fondo_caja_fuerte": 0.0, "apertura_hora": None, "responsable": None,
                "cajas_activas": [], "historial": [], "ultimos_cierres": {}}

    def _get_caja_estado(self) -> dict:
        try:
            if os.path.exists(_CAJA_STATE_FILE):
                with open(_CAJA_STATE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("fecha") == datetime.now().strftime("%Y-%m-%d"):
                    return data
                nuevo = self._nuevo_estado_caja()
                nuevo["ultimos_cierres"] = data.get("ultimos_cierres", {})
                return nuevo
        except Exception:
            pass
        return self._nuevo_estado_caja()

    def _set_caja_estado(self, data: dict):
        try:
            os.makedirs(os.path.dirname(_CAJA_STATE_FILE), exist_ok=True)
            with open(_CAJA_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error guardando estado caja: {e}")

    def _set_btn_state(self, btn, enabled: bool):
        btn.setEnabled(enabled)
        btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        if enabled:
            btn.setStyleSheet(f"""
                QPushButton{{background:#161B22;border:2px solid {_CIAN};color:white;
                             border-radius:14px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}
                QPushButton:hover{{background:{_CIAN};color:#0D1117;}}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton{{background:#0D1117;border:2px solid {_BORDE};color:#484F58;
                             border-radius:14px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}
            """)

    def _refresh_caja_ui(self):
        if not hasattr(self, "_caja_status_lbl"):
            return
        est = self._get_caja_estado()
        e = est.get("estado", "SIN_APERTURA")
        emoji, color = _ESTADOS_CAJA.get(e, ("", "#6E7681"))
        _k, _def = _ESTADO_TXT_KEY.get(e, ("cfg.estado_desconocido", "DESCONOCIDO"))
        texto = tr(_k, default=_def)
        self._caja_status_lbl.setText(f"{emoji}  {texto}".strip())
        self._caja_status_lbl.setStyleSheet(f"color:{color};font-family:'Segoe UI';font-weight:900;font-size:14px;background:transparent;border:none;")
        fondo = est.get("fondo_caja_fuerte", 0.0)
        self._caja_fondo_lbl.setText(tr("cfg.caja_fund", default="Fondo: {x} €", x=divisas.formatear(fondo)) if fondo else "")
        hora = est.get("apertura_hora") or ""
        resp = est.get("responsable") or ""
        self._caja_hora_lbl.setText(f"{hora}  {resp}".strip())

        cajas = est.get("cajas_activas", [])
        n_cajas = len(cajas)
        self._set_btn_state(self.btn_apertura,     e == "SIN_APERTURA")
        self._set_btn_state(self.btn_habilitar,    e in ("CAJA_FUERTE_ABIERTA", "PRIMERA_CAJA_ABIERTA", "OPERATIVA"))
        self._set_btn_state(self.btn_cierre_reg,   e in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA", "CIERRE_CAJAS") and n_cajas > 0)
        self._set_btn_state(self.btn_cierre_fuerte,(e == "CIERRE_COMPLETADO") or (e == "CAJA_FUERTE_ABIERTA" and n_cajas == 0))
        self._set_btn_state(self.btn_movimiento,   e in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA"))
        self._set_btn_state(self.btn_cambio_cajero, e in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA") and n_cajas > 0)

    def _usuario_actual(self) -> tuple:
        if not sesion_global or not sesion_global.usuario_actual:
            return "SISTEMA", "OPERARIO"
        nombre = sesion_global.obtener_nombre()
        nivel  = sesion_global.usuario_actual.get("perfil", "OPERARIO")
        return nombre, nivel

    def _pedir_pin_si_necesario(self, diff: float) -> bool:
        descuadre = abs(diff)
        if descuadre <= 5.0:
            return True
        rol = "GERENTE" if descuadre <= 20.0 else "ADMINISTRADOR"
        sign = "+" if diff > 0 else ""
        dlg = _PinDialog(rol, f"continuar con este descuadre de {sign}{divisas.formatear(diff)}", self)
        dlg.exec()
        return dlg.verificado()

    def _autorizar_ger_admin(self, motivo: str):
        """Exige la verificación de un perfil GERENTE o ADMINISTRADOR (o superior).
        Devuelve (ok: bool, nombre_usuario: str) del responsable que autoriza."""
        dlg = _PinDialog("GERENTE", motivo, parent=self,
                         roles_label=tr("cfg.rol_ger_admin", default="GERENTE o ADMINISTRADOR"))
        dlg.exec()
        return dlg.verificado(), dlg.usuario_nombre()

    # ── Caja: acciones ────────────────────────────────────────────────────────

    def _fn_apertura(self):
        ok, usuario = self._autorizar_ger_admin(
            tr("cfg.auth_apertura_fuerte", default="abrir la caja fuerte"))
        if not ok:
            return
        est = self._get_caja_estado()
        ultimo = est.get("ultimos_cierres", {}).get("CAJA_FUERTE", 0.0)
        dlg = _ConteoEfectivoDialog("🔓  " + tr("cfg.conteo_apertura_fuerte", default="APERTURA — ARQUEO CAJA FUERTE"),
                                    fondo_esperado=ultimo, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        total = dlg.get_total()
        detalle = dlg.get_detalle()

        if total <= 0:
            mostrar_mensaje(self, tr("cfg.importe_invalido_title", default="Importe inválido"), tr("cfg.fondo_inicial_msg", default="El fondo inicial debe ser mayor que 0 €."), "warning")
            return

        if ultimo > 0:
            diff = total - ultimo
            descuadre = abs(diff)
            if descuadre > 1.0:
                if not self._pedir_pin_si_necesario(diff):
                    mostrar_mensaje(self, tr("cfg.apertura_cancelada_title", default="Apertura cancelada"), tr("cfg.descuadre_no_auth", default="No se pudo autorizar el descuadre."), "warning")
                    return
                sign = "+" if diff > 0 else ""
                dlg_m = _MotivoDialog(
                    tr("cfg.motivo_apertura_fuerte", default="Descuadre de {x} € en apertura de Caja Fuerte.\nIndique el motivo:", x=f"{sign}{divisas.formatear(diff)}"), self
                )
                if dlg_m.exec() != QDialog.DialogCode.Accepted:
                    return
                est.setdefault("historial", []).append({
                    "accion": "DESCUADRE APERTURA FUERTE", "usuario": usuario,
                    "hora": datetime.now().strftime("%H:%M:%S"),
                    "importe": diff, "motivo": dlg_m.get_motivo(),
                })

        est["estado"] = "CAJA_FUERTE_ABIERTA"
        est["fondo_caja_fuerte"] = total
        est["apertura_hora"] = datetime.now().strftime("%H:%M")
        est["responsable"] = usuario
        est["historial"].append({
            "accion": "APERTURA CAJA FUERTE", "usuario": usuario,
            "hora": datetime.now().strftime("%H:%M:%S"), "importe": total,
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf("APERTURA CAJA FUERTE", total, usuario, detalle)
        diff = total - ultimo if ultimo > 0 else 0.0
        if abs(diff) < 0.005:
            desc_line = tr("cfg.descuadre_val", x=divisas.formatear(0))
        else:
            sign = "+" if diff > 0 else ""
            desc_line = tr("cfg.descuadre_val", default="Descuadre: {x} €", x=f"{sign}{divisas.formatear(diff)}")
        extra = "\n\n" + tr("cfg.contado_esperado", default="Contado: {c} €  ·  Esperado: {e} €", c=divisas.formatear(total), e=divisas.formatear(ultimo)) + "\n" + desc_line if ultimo > 0 else ""
        mostrar_mensaje(self, tr("cfg.apertura_confirmada_title", default="Apertura confirmada"),
                        tr("cfg.apertura_confirmada_msg", default="Caja fuerte abierta con fondo de {x} €.\nTicket de apertura generado.{extra}", x=divisas.formatear(total), extra=extra), "success")

    def _fn_habilitar_caja(self):
        est = self._get_caja_estado()
        n = len(est.get("cajas_activas", [])) + 1
        id_caja = f"CAJA-{n:02d}"
        # 1. Autorización de GERENTE/ADMINISTRADOR
        if not self._autorizar_ger_admin(
                tr("cfg.auth_abrir_caja", default="abrir la caja registradora {id}", id=id_caja))[0]:
            return
        # 2. Identificación del empleado (operario) al que se le asigna la caja
        dlg_id = _IdentificacionEmpleadoDialog(tr("cfg.id_apertura_caja", default="Apertura de {id}", id=id_caja), self)
        if dlg_id.exec() != QDialog.DialogCode.Accepted:
            return
        usuario = dlg_id.get_empleado_nombre()
        usuario_id = dlg_id.get_empleado_id()
        ultimo = est.get("ultimos_cierres", {}).get(id_caja, 0.0)

        dlg = _ConteoEfectivoDialog("🖥️  " + tr("cfg.conteo_habilitar", default="HABILITAR {id} — ARQUEO INICIAL", id=id_caja),
                                    fondo_esperado=ultimo, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fondo = dlg.get_total()
        detalle = dlg.get_detalle()

        if ultimo > 0:
            diff = fondo - ultimo
            descuadre = abs(diff)
            if descuadre > 1.0:
                if not self._pedir_pin_si_necesario(diff):
                    mostrar_mensaje(self, tr("cfg.apertura_cancelada_title", default="Apertura cancelada"), tr("cfg.descuadre_no_auth", default="No se pudo autorizar el descuadre."), "warning")
                    return
                sign = "+" if diff > 0 else ""
                dlg_m = _MotivoDialog(
                    tr("cfg.motivo_apertura_caja", default="Descuadre de {x} € en apertura de {id}.\nIndique el motivo:", x=f"{sign}{divisas.formatear(diff)}", id=id_caja), self
                )
                if dlg_m.exec() != QDialog.DialogCode.Accepted:
                    return
                est.setdefault("historial", []).append({
                    "accion": f"DESCUADRE APERTURA {id_caja}", "usuario": usuario,
                    "hora": datetime.now().strftime("%H:%M:%S"),
                    "importe": diff, "motivo": dlg_m.get_motivo(),
                })

        responsable = usuario

        est["cajas_activas"].append({
            "id": id_caja, "responsable": responsable, "responsable_id": usuario_id,
            "hora_apertura": datetime.now().strftime("%H:%M"), "fondo": fondo,
        })
        estado_nuevo = "PRIMERA_CAJA_ABIERTA" if est["estado"] == "CAJA_FUERTE_ABIERTA" else "OPERATIVA"
        est["estado"] = estado_nuevo
        est["historial"].append({
            "accion": f"HABILITAR {id_caja}", "usuario": usuario,
            "responsable": responsable,
            "hora": datetime.now().strftime("%H:%M:%S"), "importe": fondo,
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf(f"APERTURA {id_caja}", fondo, responsable, detalle)
        mostrar_mensaje(self, tr("cfg.caja_habilitada_title", default="{id} habilitada", id=id_caja),
                        tr("cfg.caja_habilitada_msg", default="{id} abierta con fondo de {x} €.\nResponsable: {resp}", id=id_caja, x=divisas.formatear(fondo), resp=responsable), "success")

    def _fn_cierre_reg(self):
        est = self._get_caja_estado()
        cajas = est.get("cajas_activas", [])
        if not cajas:
            return

        # 1. Autorización de GERENTE/ADMINISTRADOR
        if not self._autorizar_ger_admin(
                tr("cfg.auth_cerrar_caja", default="cerrar una caja registradora"))[0]:
            return

        # 2. Identificación del empleado (operario) responsable del cierre
        dlg_id = _IdentificacionEmpleadoDialog(tr("cfg.id_cierre_reg", default="Cierre de caja registradora"), self)
        if dlg_id.exec() != QDialog.DialogCode.Accepted:
            return
        usuario = dlg_id.get_empleado_nombre()

        # 2. Selección de caja (obligatoria si hay más de una; automática si solo hay una)
        if len(cajas) == 1:
            caja_data = cajas[0]
        else:
            dlg_sel = _SeleccionarCajaDialog(cajas, self)
            if dlg_sel.exec() != QDialog.DialogCode.Accepted:
                return
            caja_data = next((c for c in cajas if c["id"] == dlg_sel.get_caja_id()), cajas[0])

        id_caja = caja_data["id"]

        # 3. Arqueo final
        dlg = _ConteoEfectivoDialog(
            "🔒  " + tr("cfg.conteo_cierre_caja", default="CIERRE {id} — ARQUEO FINAL", id=id_caja),
            fondo_esperado=caja_data.get("fondo", 0.0),
            parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        total_contado = dlg.get_total()
        detalle = dlg.get_detalle()
        fondo_esperado = caja_data.get("fondo", 0.0)
        diff = total_contado - fondo_esperado
        descuadre = abs(diff)

        if descuadre > 1.0:
            if not self._pedir_pin_si_necesario(diff):
                mostrar_mensaje(self, tr("cfg.cierre_cancelado_title", default="Cierre cancelado"), tr("cfg.descuadre_no_auth", default="No se pudo autorizar el descuadre."), "warning")
                return
            dlg_m = _MotivoDialog(
                tr("cfg.motivo_cierre_caja", default="Descuadre de {x} € en {id}.\nIndique el motivo:", x=divisas.formatear(descuadre), id=id_caja), self
            )
            if dlg_m.exec() != QDialog.DialogCode.Accepted:
                return
            est["historial"].append({
                "accion": f"DESCUADRE {id_caja}", "usuario": usuario,
                "hora": datetime.now().strftime("%H:%M:%S"),
                "importe": descuadre, "motivo": dlg_m.get_motivo(),
            })

        estado_anterior = est.get("estado", "")
        est["cajas_activas"] = [c for c in cajas if c["id"] != id_caja]
        n_restantes = len(est["cajas_activas"])
        if n_restantes == 0:
            # Solo marcar CIERRE_COMPLETADO si el operador ya había iniciado el proceso
            # de cierre explícitamente (estado CIERRE_CAJAS). Si venía de un estado
            # operativo y cierra la última caja, volver a CAJA_FUERTE_ABIERTA para
            # permitir habilitar otra caja sin necesidad de reabrir la caja fuerte.
            if estado_anterior == "CIERRE_CAJAS":
                est["estado"] = "CIERRE_COMPLETADO"
            else:
                est["estado"] = "CAJA_FUERTE_ABIERTA"
        else:
            est["estado"] = "CIERRE_CAJAS"
        est.setdefault("ultimos_cierres", {})[id_caja] = total_contado
        est["historial"].append({
            "accion": f"CIERRE {id_caja}", "usuario": usuario,
            "hora": datetime.now().strftime("%H:%M:%S"), "importe": total_contado,
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf(f"CIERRE {id_caja}", total_contado, usuario, detalle)
        if n_restantes == 0 and est["estado"] == "CIERRE_COMPLETADO":
            msg = tr("cfg.cierre_msg_all", default="Todas las cajas cerradas. Ya puede realizar el cierre de caja fuerte.")
        elif n_restantes == 0:
            msg = tr("cfg.cierre_msg_zero", default="{id} cerrada. Puede habilitar una nueva caja registradora.", id=id_caja)
        else:
            msg = tr("cfg.cierre_msg_rest", default="{id} cerrada. Quedan {n} caja(s) activa(s).", id=id_caja, n=n_restantes)
        diff = total_contado - fondo_esperado
        if abs(diff) < 0.005:
            desc_line = tr("cfg.descuadre_val", x=divisas.formatear(0))
        else:
            sign = "+" if diff > 0 else ""
            desc_line = tr("cfg.descuadre_val", default="Descuadre: {x} €", x=f"{sign}{divisas.formatear(diff)}")
        mostrar_mensaje(self, tr("cfg.cierre_title", default="Cierre {id}", id=id_caja),
                        msg + "\n\n" + tr("cfg.contado_esperado", default="Contado: {c} €  ·  Esperado: {e} €", c=divisas.formatear(total_contado), e=divisas.formatear(fondo_esperado)) + "\n" + desc_line,
                        "success")

    def _fn_cambio_cajero(self):
        """Traspasa una caja registradora activa del cajero saliente al entrante
        sin cerrarla. Se hace un arqueo (multidivisa) cuyo descuadre se atribuye
        al cajero SALIENTE; el entrante recibe la caja con el efectivo contado
        como nuevo punto de partida (empieza cuadrada)."""
        est = self._get_caja_estado()
        cajas = est.get("cajas_activas", [])
        if not cajas:
            return

        # 0. Autorización de GERENTE/ADMINISTRADOR
        if not self._autorizar_ger_admin(
                tr("cfg.auth_cambio_cajero", default="realizar un cambio de cajero"))[0]:
            return

        # 1. Selección de la caja a traspasar
        if len(cajas) == 1:
            caja_data = cajas[0]
        else:
            dlg_sel = _SeleccionarCajaDialog(cajas, self)
            if dlg_sel.exec() != QDialog.DialogCode.Accepted:
                return
            caja_data = next((c for c in cajas if c["id"] == dlg_sel.get_caja_id()), cajas[0])
        id_caja = caja_data["id"]

        # 2. Identificación del cajero SALIENTE (debe ser el responsable actual)
        dlg_out = _IdentificacionEmpleadoDialog(
            tr("cfg.id_cajero_saliente", default="Cambio de cajero — Cajero SALIENTE ({id})", id=id_caja), self)
        if dlg_out.exec() != QDialog.DialogCode.Accepted:
            return
        saliente = dlg_out.get_empleado_nombre()
        saliente_id = dlg_out.get_empleado_id()
        if not self._es_responsable(caja_data, saliente, saliente_id):
            mostrar_mensaje(self, tr("cfg.cambio_no_responsable_title", default="Caja intransferible"),
                            tr("cfg.cambio_no_responsable_msg",
                               default="Solo el cajero responsable de {id} puede traspasarla.\nResponsable actual: {resp}",
                               id=id_caja, resp=caja_data.get("responsable", "—")), "warning")
            return

        # 3. Identificación del cajero ENTRANTE (define de antemano quién la recibe)
        dlg_in = _IdentificacionEmpleadoDialog(
            tr("cfg.id_cajero_entrante", default="Cambio de cajero — Cajero ENTRANTE ({id})", id=id_caja), self)
        if dlg_in.exec() != QDialog.DialogCode.Accepted:
            return
        entrante = dlg_in.get_empleado_nombre()
        entrante_id = dlg_in.get_empleado_id()
        if entrante_id is not None and str(entrante_id) == str(saliente_id):
            mostrar_mensaje(self, tr("cfg.cambio_mismo_title", default="Cajero no válido"),
                            tr("cfg.cambio_mismo_msg", default="El cajero entrante debe ser distinto del saliente."), "warning")
            return

        # 4. Arqueo — recuento de monedas y billetes en la divisa de la empresa
        dlg = _ConteoEfectivoDialog(
            "🔁  " + tr("cfg.conteo_cambio_cajero", default="CAMBIO DE CAJERO {id} — ARQUEO", id=id_caja),
            fondo_esperado=caja_data.get("fondo", 0.0), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        total_contado = dlg.get_total()
        detalle = dlg.get_detalle()
        fondo_esperado = caja_data.get("fondo", 0.0)
        diff = total_contado - fondo_esperado
        descuadre = abs(diff)

        # 5. Descuadre → SIEMPRE responsabilidad del cajero SALIENTE
        if descuadre > 1.0:
            if not self._pedir_pin_si_necesario(diff):
                mostrar_mensaje(self, tr("cfg.cambio_cancelado_title", default="Cambio cancelado"),
                                tr("cfg.descuadre_no_auth", default="No se pudo autorizar el descuadre."), "warning")
                return
            dlg_m = _MotivoDialog(
                tr("cfg.motivo_cambio_cajero",
                   default="Descuadre de {x} € en {id} (cajero saliente: {resp}).\nIndique el motivo:",
                   x=divisas.formatear(descuadre), id=id_caja, resp=saliente), self)
            if dlg_m.exec() != QDialog.DialogCode.Accepted:
                return
            est.setdefault("historial", []).append({
                "accion": f"DESCUADRE CAMBIO CAJERO {id_caja}", "usuario": saliente,
                "hora": datetime.now().strftime("%H:%M:%S"),
                "importe": diff, "motivo": dlg_m.get_motivo(),
            })

        # 6. Traspaso: la caja sigue ACTIVA, ahora a nombre del entrante, con el
        #    efectivo contado como nuevo punto de partida (entrante empieza cuadrado).
        for c in est["cajas_activas"]:
            if c["id"] == id_caja:
                c["responsable"] = entrante
                c["responsable_id"] = entrante_id
                c["fondo"] = total_contado
                c["hora_apertura"] = datetime.now().strftime("%H:%M")
                break
        est.setdefault("historial", []).append({
            "accion": f"CAMBIO CAJERO {id_caja}", "usuario": saliente,
            "responsable": entrante, "hora": datetime.now().strftime("%H:%M:%S"),
            "importe": total_contado,
        })
        est.setdefault("ultimos_cierres", {})  # (no se altera; la caja sigue abierta)
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf(f"CAMBIO CAJERO {id_caja}", total_contado,
                                 f"{saliente} → {entrante}", detalle)

        # 7. Resumen
        if abs(diff) < 0.005:
            desc_line = tr("cfg.descuadre_val", x=divisas.formatear(0))
        else:
            sign = "+" if diff > 0 else ""
            desc_line = tr("cfg.descuadre_val", default="Descuadre: {x} €", x=f"{sign}{divisas.formatear(diff)}")
        mostrar_mensaje(self, tr("cfg.cambio_ok_title", default="Cambio de cajero — {id}", id=id_caja),
                        tr("cfg.cambio_ok_msg",
                           default="{id} traspasada de {sal} a {ent}.\nLa caja sigue activa.",
                           id=id_caja, sal=saliente, ent=entrante)
                        + "\n\n" + tr("cfg.contado_esperado", default="Contado: {c} €  ·  Esperado: {e} €",
                                      c=divisas.formatear(total_contado), e=divisas.formatear(fondo_esperado))
                        + "\n" + desc_line, "success")

    def _es_responsable(self, caja: dict, nombre, id_empleado=None) -> bool:
        """True si el empleado identificado es el responsable de la caja (por id,
        con respaldo a nombre normalizado). Garantiza la intransferibilidad."""
        rid = caja.get("responsable_id")
        if id_empleado is not None and rid is not None:
            return str(rid) == str(id_empleado)
        a = str(caja.get("responsable") or "").strip().casefold()
        b = str(nombre or "").strip().casefold()
        return bool(b) and a == b

    def _fn_cierre_fuerte(self):
        ok, usuario = self._autorizar_ger_admin(
            tr("cfg.auth_cierre_fuerte", default="cerrar la caja fuerte"))
        if not ok:
            return
        est = self._get_caja_estado()

        dlg = _ConteoEfectivoDialog(
            "🏦  " + tr("cfg.conteo_cierre_fuerte", default="CIERRE CAJA FUERTE — ARQUEO FINAL"),
            fondo_esperado=est.get("fondo_caja_fuerte", 0.0),
            parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        total = dlg.get_total()
        detalle = dlg.get_detalle()
        fondo_fuerte_esp = est.get("fondo_caja_fuerte", 0.0)
        diff_f_signed = total - fondo_fuerte_esp
        descuadre = abs(diff_f_signed)

        if descuadre > 1.0:
            if not self._pedir_pin_si_necesario(diff_f_signed):
                mostrar_mensaje(self, tr("cfg.cierre_cancelado_title", default="Cierre cancelado"), tr("cfg.descuadre_no_auth", default="No se pudo autorizar el descuadre."), "warning")
                return
            dlg_m = _MotivoDialog(
                tr("cfg.motivo_cierre_fuerte", default="Descuadre de {x} € en el cierre de caja fuerte.\nIndique el motivo:", x=divisas.formatear(descuadre)), self
            )
            if dlg_m.exec() != QDialog.DialogCode.Accepted:
                return
            est["historial"].append({
                "accion": "DESCUADRE CIERRE FUERTE", "usuario": usuario,
                "hora": datetime.now().strftime("%H:%M:%S"),
                "importe": descuadre, "motivo": dlg_m.get_motivo(),
            })

        est["estado"] = "SIN_APERTURA"
        est["fondo_caja_fuerte"] = 0.0
        est["cajas_activas"] = []
        est.setdefault("ultimos_cierres", {})["CAJA_FUERTE"] = total
        est["historial"].append({
            "accion": "CIERRE CAJA FUERTE", "usuario": usuario,
            "hora": datetime.now().strftime("%H:%M:%S"), "importe": total,
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf("CIERRE CAJA FUERTE", total, usuario, detalle)
        diff_f = total - fondo_fuerte_esp
        if abs(diff_f) < 0.005:
            desc_line_f = tr("cfg.descuadre_val", x=divisas.formatear(0))
        else:
            sign_f = "+" if diff_f > 0 else ""
            desc_line_f = tr("cfg.descuadre_val", default="Descuadre: {x} €", x=f"{sign_f}{divisas.formatear(diff_f)}")
        mostrar_mensaje(self, tr("cfg.cierre_completado_title", default="Cierre completado"),
                        tr("cfg.cierre_fuerte_msg", default="Caja fuerte cerrada. Total final: {x} €.", x=divisas.formatear(total)) + "\n\n"
                        + tr("cfg.contado_esperado", default="Contado: {c} €  ·  Esperado: {e} €", c=divisas.formatear(total), e=divisas.formatear(fondo_fuerte_esp)) + "\n" + desc_line_f,
                        "success")

    def _fn_movimiento(self):
        ok, usuario = self._autorizar_ger_admin(
            tr("cfg.auth_movimiento", default="registrar un movimiento de efectivo"))
        if not ok:
            return
        if not usuario:
            usuario, _ = self._usuario_actual()
        est = self._get_caja_estado()
        dlg = _MovimientoDialog(est.get("cajas_activas", []), est.get("fondo_caja_fuerte", 0.0), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        res = dlg.get_resultado()
        if not res:
            return

        imp = res["importe"]
        tipo_o, id_o = res["tipo_origen"], res["id_origen"]
        tipo_d, id_d = res["tipo_destino"], res["id_destino"]

        # Descontar del origen
        if tipo_o == "CAJA_FUERTE":
            est["fondo_caja_fuerte"] = round(est.get("fondo_caja_fuerte", 0.0) - imp, 2)
        elif tipo_o == "CAJA":
            for c in est.get("cajas_activas", []):
                if c["id"] == id_o:
                    c["fondo"] = round(c.get("fondo", 0.0) - imp, 2)

        # Añadir al destino
        if tipo_d == "CAJA_FUERTE":
            est["fondo_caja_fuerte"] = round(est.get("fondo_caja_fuerte", 0.0) + imp, 2)
        elif tipo_d == "CAJA":
            for c in est.get("cajas_activas", []):
                if c["id"] == id_d:
                    c["fondo"] = round(c.get("fondo", 0.0) + imp, 2)

        empleado_mov = res.get("empleado", usuario)
        est["historial"].append({
            "accion": f"MOVIMIENTO {res['tipo']}", "usuario": empleado_mov,
            "origen": res["origen_txt"], "destino": res["destino_txt"],
            "importe": imp, "motivo": res["motivo"],
            "hora": datetime.now().strftime("%H:%M:%S"),
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf(
            f"MOVIMIENTO — {res['tipo']}", imp, empleado_mov,
            [{"denominacion": res["tipo"], "valor": imp, "cantidad": 1, "subtotal": imp}]
        )

        # Construir mensaje informativo con saldos actualizados
        lineas = [tr("cfg.mov_line1", default="{tipo} de {x} € registrado.", tipo=res['tipo'], x=divisas.formatear(imp)) + "\n"]
        lineas.append(tr("cfg.mov_origen", default="Origen:  {x}", x=res['origen_txt']))
        lineas.append(tr("cfg.mov_destino", default="Destino: {x}", x=res['destino_txt']) + "\n")
        lineas.append(tr("cfg.mov_caja_fuerte", default="Caja Fuerte → {x} €", x=divisas.formatear(est.get('fondo_caja_fuerte', 0.0))))
        for c in est.get("cajas_activas", []):
            lineas.append(f"{c['id']} → {divisas.formatear(c.get('fondo', 0.0))}")
        mostrar_mensaje(self, tr("cfg.mov_registrado_title", default="Movimiento registrado"), "\n".join(lineas), "success")

    def _generar_ticket_pdf(self, tipo: str, importe: float, responsable: str, detalle: list = None):
        try:
            from reportlab.lib.pagesizes import A5
            from reportlab.lib.units import cm
            from reportlab.pdfgen import canvas as rl_canvas
            safe = tipo.replace(" ", "_").replace("/", "-")
            fname = f"TICKET_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            carpeta = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "tickets"))
            os.makedirs(carpeta, exist_ok=True)
            ruta = os.path.join(carpeta, fname)
            c = rl_canvas.Canvas(ruta, pagesize=A5)
            w, h = A5
            if os.path.exists(_LOGO_PATH):
                c.drawImage(_LOGO_PATH, w - 4.5*cm, h - 3*cm, 3.5*cm, 2*cm, preserveAspectRatio=True)
            c.setFont("Helvetica-Bold", 13); c.setFillColorRGB(0, 1, 0.78)
            c.drawString(1*cm, h - 1.8*cm, tipo)
            c.setFont("Helvetica", 8); c.setFillColorRGB(0.6, 0.6, 0.6)
            c.drawString(1*cm, h - 2.5*cm, tr("cfg.tk_date_time", default="Fecha: {fecha}  Hora: {hora}", fecha=datetime.now().strftime('%d/%m/%Y'), hora=datetime.now().strftime('%H:%M:%S')))
            c.drawString(1*cm, h - 3.0*cm, tr("cfg.tk_responsable", default="Responsable: {x}", x=responsable))
            c.setStrokeColorRGB(0, 1, 0.78); c.line(1*cm, h - 3.4*cm, w - 1*cm, h - 3.4*cm)
            y = h - 4.2*cm
            if detalle:
                c.setFont("Helvetica-Bold", 8); c.setFillColorRGB(0.4, 0.9, 0.6)
                c.drawString(1*cm, y, tr("cfg.col_denom", default="DENOMINACIÓN")); c.drawRightString(w - 2.5*cm, y, tr("cfg.tk_cant", default="CANT.")); c.drawRightString(w - 1*cm, y, tr("cfg.col_subtotal", default="SUBTOTAL"))
                y -= 0.45*cm
                c.setFont("Helvetica", 8); c.setFillColorRGB(0.9, 0.9, 0.9)
                for item in detalle:
                    if y < 3*cm: c.showPage(); y = h - 2*cm
                    c.drawString(1*cm, y, str(item.get("denominacion", "")))
                    c.drawRightString(w - 2.5*cm, y, str(item.get("cantidad", "")))
                    c.drawRightString(w - 1*cm, y, f"{divisas.formatear(item.get('subtotal', 0))}")
                    y -= 0.42*cm
            y -= 0.5*cm
            c.setStrokeColorRGB(0, 1, 0.78); c.line(1*cm, y, w - 1*cm, y); y -= 0.55*cm
            c.setFont("Helvetica-Bold", 11); c.setFillColorRGB(0, 1, 0.78)
            c.drawString(1*cm, y, tr("cfg.tk_total", default="TOTAL:")); c.drawRightString(w - 1*cm, y, divisas.formatear(importe))
            y -= 2*cm
            c.setFont("Helvetica", 7); c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawString(1*cm, y, tr("cfg.tk_firma", default="Firma responsable: _______________________________"))
            c.setFont("Helvetica", 7); c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(w/2, 1.5*cm, tr("cfg.tk_footer", default="Documento generado por Smart Manager"))
            c.save()
        except Exception:
            LOG_DOCUMENTOS.exception("Error generando ticket PDF (caja)")

    # --- PESTAÑA 4: HORARIO EMPLEADOS ---
    def _crear_page_horarios(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 12)
        outer.setSpacing(10)
        hdr_row = QHBoxLayout()
        lbl = QLabel(tr("cfg.horario_title", default="HORARIO EMPLEADOS"))
        lbl.setStyleSheet(
            f"color: {_CIAN}; font-family: 'Segoe UI'; font-weight: 900; font-size: 16px;"
        )
        hdr_row.addWidget(lbl)
        hdr_row.addStretch()
        btn_new = QPushButton("＋  " + tr("cfg.nueva_semana", default="NUEVA SEMANA"))
        btn_new.setFixedHeight(38)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.setStyleSheet(f"""
            QPushButton {{
                background: {_CIAN}; border: none; border-radius: 10px;
                color: #0E1117;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 22px;
            }}
            QPushButton:hover {{ background: #0E1117; color: {_CIAN}; border: 2px solid {_CIAN}; }}
        """)
        btn_new.clicked.connect(self._h_nueva_semana)
        hdr_row.addWidget(btn_new)
        outer.addLayout(hdr_row)
        self._h_vscroll = QScrollArea()
        self._h_vscroll.setWidgetResizable(True)
        self._h_vscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._h_vscroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._h_container = _HorarioContainer()
        self._h_vscroll.setWidget(self._h_container)
        self._h_container._scroll_area = self._h_vscroll
        self._h_loading = _HorarioLoadingWidget()
        self._h_content_stack = QStackedWidget()
        self._h_content_stack.addWidget(self._h_loading)   # index 0: loading
        self._h_content_stack.addWidget(self._h_vscroll)   # index 1: content
        outer.addWidget(self._h_content_stack)
        save_row = QHBoxLayout()
        save_row.addStretch()
        btn_save = QPushButton("  " + tr("cfg.guardar_horarios", default="GUARDAR HORARIOS"))
        btn_save.setFixedHeight(42)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #22C55E; border: 2px solid #22C55E; border-radius: 10px;
                color: #0E1117;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 28px;
            }
            QPushButton:hover { background: #FFFFFF; color: #0E1117; }
        """)
        btn_save.clicked.connect(self._h_guardar_horarios)
        save_row.addWidget(btn_save)
        outer.addLayout(save_row)
        # Defer table building to after first paint — tab appears instantly, tables populate next tick.
        QTimer.singleShot(0, self._h_cargar_horarios)
        return page

    def _h_nueva_semana(self):
        semana = _HorarioSemana()
        self._h_container.add_semana(semana)
        QTimer.singleShot(60, lambda: (
            self._h_vscroll.verticalScrollBar().setValue(
                self._h_vscroll.verticalScrollBar().maximum()
            )
        ))

    def _h_cargar_horarios(self):
        self._h_loading.start()
        self._h_content_stack.setCurrentIndex(0)
        path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "horarios.json")
        )
        loaded = False
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    self._h_pending_builds = len(data)
                    for item in data:
                        # Pass employee count upfront to avoid a double build.
                        grid_data = item.get("grid", {})
                        n_emp = max(1, len(grid_data.get("names", [])))
                        semana = _HorarioSemana(n_emp=n_emp)
                        self._h_container.add_semana(semana)
                        # Fire set_state exactly once when the build finishes, then
                        # decrement the pending counter and reveal content when all done.
                        def _make_handler(s, d):
                            def _handler():
                                s._grid.build_complete.disconnect(_handler)
                                s.set_state(d)
                                self._h_pending_builds -= 1
                                if self._h_pending_builds <= 0:
                                    self._h_finish_loading()
                            return _handler
                        semana._grid.build_complete.connect(_make_handler(semana, item))
                    loaded = True
            except Exception:
                pass
        if not loaded:
            self._h_pending_builds = 1
            semana = _HorarioSemana()
            self._h_container.add_semana(semana)
            def _on_virgin():
                semana._grid.build_complete.disconnect(_on_virgin)
                self._h_pending_builds -= 1
                if self._h_pending_builds <= 0:
                    self._h_finish_loading()
            semana._grid.build_complete.connect(_on_virgin)

    def _h_finish_loading(self):
        self._h_loading.stop()
        self._h_content_stack.setCurrentIndex(1)

    def _h_guardar_horarios(self):
        try:
            path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "horarios.json")
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = [s.get_state() for s in self._h_container._semanas]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            mostrar_mensaje(self, tr("cfg.saved_title", default="Guardado"), tr("cfg.horarios_saved", default="Horarios guardados correctamente."), "info")
        except Exception as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.horarios_save_err", default="No se pudo guardar: {exc}", exc=exc), "error")

    # --- PESTAÑA 5: FICHAJES ---
    def _crear_page_fichajes(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(50, 50, 50, 50)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_clock = QLabel("⏳")
        lbl_clock.setStyleSheet(
            "font-size: 180px; background: transparent; border: none; margin-bottom: 30px;"
        )
        lbl_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_clock, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(20)

        ly.addWidget(
            QLabel(tr("cfg.attendance", default="CONTROL DE ASISTENCIA"),
                   styleSheet="color: white; font-weight: 900; font-size: 16px;"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        ly.addSpacing(20)

        self.input_pin = QLineEdit()
        self.input_pin.setPlaceholderText(tr("cfg.pin_ph", default="CÓDIGO DE 4 DÍGITOS"))
        self.input_pin.setMaxLength(4)
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setFixedWidth(300)
        self.input_pin.setFixedHeight(60)
        self.input_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_pin.setStyleSheet(
            f"border: 2px solid {_CIAN}; border-radius: 15px; "
            "font-size: 24px; color: white; background: #161B22;"
        )
        ly.addWidget(self.input_pin, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(15)

        self._f_btn = QPushButton(tr("cfg.start_shift", default="INICIAR JORNADA"))
        self._f_btn.setFixedSize(300, 60)
        self._f_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._f_btn.setStyleSheet(self._f_style_iniciar())
        self._f_btn.clicked.connect(self._f_on_btn_click)
        ly.addWidget(self._f_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(16)

        self._f_lbl_counter = QLabel("00:00:00")
        self._f_lbl_counter.setStyleSheet(
            f"color: {_CIAN}; font-family: 'Courier New'; font-size: 42px; "
            "font-weight: 900; background: transparent; letter-spacing: 4px;"
        )
        self._f_lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f_lbl_counter.hide()
        ly.addWidget(self._f_lbl_counter, alignment=Qt.AlignmentFlag.AlignCenter)

        ly.addStretch()

        # State
        self._f_fichaje_id: int | None = None
        self._f_usuario_id: int | None = None
        self._f_seconds: int = 0
        self._f_jornada_activa: bool = False
        self._f_timer = QTimer(self)
        self._f_timer.setInterval(1000)
        self._f_timer.timeout.connect(self._f_tick_contador)

        btn_hist = QPushButton(tr("cfg.hist_btn", default="HISTÓRICO DE FICHAJES"))
        btn_hist.setFixedHeight(38)
        btn_hist.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_hist.setStyleSheet(f"""
            QPushButton {{
                background: #11181D;
                border: 2px solid {_CIAN};
                border-radius: 10px;
                color: {_CIAN};
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 13px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: #0E1117;
            }}
        """)
        btn_hist.clicked.connect(self._f_historico_fichajes)
        h_bot = QHBoxLayout()
        h_bot.addWidget(btn_hist)
        h_bot.addStretch()
        ly.addLayout(h_bot)
        return page

    def _f_style_iniciar(self) -> str:
        return f"""
            QPushButton {{
                background: #0E1117;
                color: {_CIAN};
                border: 2px solid {_CIAN};
                border-radius: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: #0E1117;
            }}
        """

    def _f_style_finalizar(self) -> str:
        return """
            QPushButton {
                background: #0E1117;
                color: #EF4444;
                border: 2px solid #EF4444;
                border-radius: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #EF4444;
                color: #0E1117;
            }
        """

    def _f_on_btn_click(self):
        if self._f_jornada_activa:
            self._f_finalizar_jornada()
        else:
            self._f_iniciar_jornada()

    def _f_iniciar_jornada(self):
        pin = self.input_pin.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            mostrar_mensaje(self, tr("cfg.pin_invalid_title", default="PIN inválido"), tr("cfg.pin_invalid_msg", default="Introduce un código de 4 dígitos numéricos."), "warning")
            return
        usuario = validar_pin_fichaje(pin)
        if not usuario:
            mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"), tr("cfg.pin_wrong_msg", default="No se encontró ningún empleado con ese PIN."), "error")
            return
        # Resume if there's an open fichaje
        fichaje_abierto = obtener_fichaje_abierto(usuario["id"])
        if fichaje_abierto:
            self._f_fichaje_id = fichaje_abierto["id"]
            entrada_dt = fichaje_abierto["entrada"]
            if isinstance(entrada_dt, str):
                entrada_dt = datetime.fromisoformat(entrada_dt)
            self._f_seconds = max(0, int((datetime.now() - entrada_dt).total_seconds()))
        else:
            fichaje_id = registrar_entrada(usuario["id"], usuario["nombre"])
            if fichaje_id is None:
                mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.entry_err", default="No se pudo registrar la entrada en la base de datos."), "error")
                return
            self._f_fichaje_id = fichaje_id
            self._f_seconds = 0
        self._f_usuario_id = usuario["id"]
        self._f_jornada_activa = True
        self._f_btn.setText(tr("cfg.end_shift", default="FINALIZAR JORNADA"))
        self._f_btn.setStyleSheet(self._f_style_finalizar())
        self.input_pin.clear()
        self.input_pin.setPlaceholderText(tr("cfg.pin_to_end_ph", default="PIN PARA FINALIZAR"))
        self._f_update_counter_label()
        self._f_lbl_counter.show()
        self._f_timer.start()

    def _f_finalizar_jornada(self):
        pin = self.input_pin.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            mostrar_mensaje(self, tr("cfg.pin_required_title", default="PIN requerido"),
                            tr("cfg.pin_required_msg", default="Introduce tu PIN de 4 dígitos para finalizar la jornada."), "warning")
            return
        usuario = validar_pin_fichaje(pin)
        if not usuario or usuario["id"] != self._f_usuario_id:
            mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"),
                            tr("cfg.pin_mismatch_msg", default="El PIN introducido no coincide con el empleado que inició la jornada."), "error")
            self.input_pin.clear()
            return
        self._f_timer.stop()
        segundos = registrar_salida(self._f_fichaje_id) if self._f_fichaje_id else None
        self._f_jornada_activa = False
        self._f_fichaje_id = None
        self._f_usuario_id = None
        self._f_btn.setText(tr("cfg.start_shift", default="INICIAR JORNADA"))
        self._f_btn.setStyleSheet(self._f_style_iniciar())
        self._f_lbl_counter.hide()
        self._f_lbl_counter.setText("00:00:00")
        self._f_seconds = 0
        self.input_pin.clear()
        self.input_pin.setPlaceholderText(tr("cfg.pin_ph", default="CÓDIGO DE 4 DÍGITOS"))
        if segundos is not None:
            h = segundos // 3600
            m = (segundos % 3600) // 60
            s = segundos % 60
            mostrar_mensaje(self, tr("cfg.shift_done_title", default="Jornada finalizada"),
                            tr("cfg.worked_time", default="Has trabajado {h}h {m}m {s}s.", h=f"{h:02d}", m=f"{m:02d}", s=f"{s:02d}"), "info")
        else:
            mostrar_mensaje(self, tr("cfg.shift_done_title", default="Jornada finalizada"), tr("cfg.shift_registered", default="Jornada registrada correctamente."), "info")

    def _f_tick_contador(self):
        self._f_seconds += 1
        self._f_update_counter_label()

    def _f_update_counter_label(self):
        h = self._f_seconds // 3600
        m = (self._f_seconds % 3600) // 60
        s = self._f_seconds % 60
        self._f_lbl_counter.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _f_historico_fichajes(self):
        fichajes = listar_fichajes()

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setMinimumSize(820, 500)

        card = QFrame(dlg)
        card.setObjectName("hfcard")
        card.setStyleSheet(
            f"QFrame#hfcard{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}"
        )
        root_lay = QVBoxLayout(dlg)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(20, 20, 20, 16)
        ly.setSpacing(12)

        # Draggable header row
        _drag = [None]
        def _on_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                _drag[0] = e.globalPosition().toPoint() - dlg.frameGeometry().topLeft()
        def _on_move(e):
            if _drag[0] is not None and e.buttons() == Qt.MouseButton.LeftButton:
                dlg.move(e.globalPosition().toPoint() - _drag[0])
        def _on_release(e):
            _drag[0] = None
        card.mousePressEvent = _on_press
        card.mouseMoveEvent = _on_move
        card.mouseReleaseEvent = _on_release

        hdr_row = QHBoxLayout()
        lbl = QLabel(tr("cfg.hist_title", default="HISTÓRICO DE FICHAJES"))
        lbl.setStyleSheet(
            f"color: {_CIAN}; font-family: 'Segoe UI'; font-weight: 900; font-size: 16px;"
        )
        hdr_row.addWidget(lbl)
        ly.addLayout(hdr_row)

        headers = [
            tr("cfg.col_name", default="NOMBRE"),
            tr("cfg.col_entry", default="ENTRADA"),
            tr("cfg.col_exit", default="SALIDA"),
            tr("cfg.col_hours", default="HORAS TRABAJADAS"),
        ]
        tbl = QTableWidget(len(fichajes), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(False)
        tbl.verticalHeader().setVisible(False)
        hdr = tbl.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        tbl.setStyleSheet(f"""
            QTableWidget {{
                background: #161B22; color: white; border: none;
                font-size: 13px; gridline-color: #21262D;
                font-family: 'Segoe UI';
            }}
            QHeaderView::section {{
                background: #21262D; color: {_CIAN};
                font-weight: bold; border: none; padding: 6px 10px;
                font-family: 'Segoe UI'; font-size: 13px;
            }}
            QHeaderView::section:hover {{
                background: {_CIAN}; color: #0D1117;
            }}
            QTableWidget::item {{ padding: 5px 10px; }}
            QTableWidget::item:selected {{ background: #2D333B; }}
        """)

        for row, f in enumerate(fichajes):
            tbl.setItem(row, 0, QTableWidgetItem(f["nombre"]))
            entrada_dt = f["entrada"]
            entrada_str = entrada_dt.strftime("%d/%m/%Y  %H:%M:%S") if entrada_dt else "-"
            tbl.setItem(row, 1, QTableWidgetItem(entrada_str))
            salida_dt = f["salida"]
            salida_str = salida_dt.strftime("%d/%m/%Y  %H:%M:%S") if salida_dt else tr("cfg.in_progress", default="EN CURSO")
            item_sal = QTableWidgetItem(salida_str)
            if not salida_dt:
                item_sal.setForeground(QColor(_CIAN))
            tbl.setItem(row, 2, item_sal)
            seg = f["segundos"]
            if seg is not None:
                h = seg // 3600
                m_val = (seg % 3600) // 60
                s_val = seg % 60
                dur = f"{h:02d}h  {m_val:02d}m  {s_val:02d}s"
            else:
                dur = "-"
            item_dur = QTableWidgetItem(dur)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(row, 3, item_dur)

        ly.addWidget(tbl)

        btn_close = QPushButton(tr("cfg.close", default="CERRAR"))
        btn_close.setFixedHeight(38)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(dlg.accept)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {_CIAN}; color: #0E1117; border: none;
                border-radius: 8px; font-family: 'Segoe UI';
                font-weight: bold; font-size: 13px; padding: 0 24px;
            }}
            QPushButton:hover {{
                background: #0D1117; color: {_CIAN}; border: 2px solid {_CIAN};
            }}
        """)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        ly.addLayout(btn_row)
        # Pre-size and center on the parent window before exec() so the dialog
        # is at the correct position from the very first paint frame.
        dlg.resize(820, 500)
        parent = self.window()
        center = parent.mapToGlobal(parent.rect().center())
        dlg.move(center.x() - 410, center.y() - 250)
        dlg.exec()

    # --- PESTAÑA 6: LOGO CORPORATIVO ---
    def _crear_page_logo(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 40, 40, 40)
        ly.setSpacing(0)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icono de paleta — ocupa ~1/9 del área (aprox 160×160 px)
        icon = QLabel("🎨")
        icon.setStyleSheet(
            "font-size: 130px; background: transparent; border: none;"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedHeight(160)
        ly.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(20)

        self.lbl_preview = QLabel(tr("cfg.logo_preview", default="PREVISUALIZACIÓN DE LOGO"))
        self.lbl_preview.setFixedSize(400, 200)
        self.lbl_preview.setStyleSheet(
            f"border: 1px dashed {_BORDE}; border-radius: 10px; color: #484F58;"
            "font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;"
        )
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(self.lbl_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(24)

        btn_upload = QPushButton(tr("cfg.logo_upload", default="SUBIR LOGO"))
        btn_upload.setFixedSize(250, 50)
        btn_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_upload.setStyleSheet(f"""
            QPushButton {{
                background: {_CIAN};
                color: #0E1117;
                border: 2px solid {_CIAN};
                border-radius: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #0E1117;
                color: {_CIAN};
            }}
        """)
        btn_upload.clicked.connect(self._subir_logo)
        ly.addWidget(btn_upload, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(12)

        btn_delete = QPushButton(tr("cfg.logo_delete", default="ELIMINAR LOGO"))
        btn_delete.setFixedSize(250, 50)
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #0E1117;
                color: #E53935;
                border: 2px solid #E53935;
                border-radius: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #E53935;
                color: #0E1117;
            }
        """)
        btn_delete.clicked.connect(self._eliminar_logo)
        ly.addWidget(btn_delete, alignment=Qt.AlignmentFlag.AlignCenter)

        # Cargar logo existente si ya hay uno guardado
        self._logo_refresh_preview()
        return page

    def _logo_refresh_preview(self):
        if os.path.exists(_LOGO_PATH):
            pix = QPixmap(_LOGO_PATH)
            if not pix.isNull():
                self.lbl_preview.setPixmap(
                    pix.scaled(400, 200, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                self.lbl_preview.setText("")
                return
        self.lbl_preview.setPixmap(QPixmap())
        self.lbl_preview.setText(tr("cfg.logo_preview", default="PREVISUALIZACIÓN DE LOGO"))

    def _subir_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("cfg.logo_file_dialog", default="Seleccionar logo corporativo"), "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not path:
            return
        try:
            import shutil
            os.makedirs(os.path.dirname(_LOGO_PATH), exist_ok=True)
            shutil.copy2(path, _LOGO_PATH)
            self._logo_refresh_preview()
            mostrar_mensaje(self, tr("cfg.logo_saved_title", default="Logo guardado"), tr("cfg.logo_saved_msg", default="El logo corporativo se ha actualizado correctamente."), "success")
        except Exception as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.logo_save_err", default="No se pudo guardar el logo: {exc}", exc=exc), "error")

    def _eliminar_logo(self):
        if not os.path.exists(_LOGO_PATH):
            mostrar_mensaje(self, tr("cfg.logo_none_title", default="Sin logo"), tr("cfg.logo_none_msg", default="No hay ningún logo corporativo guardado."), "info")
            return
        try:
            os.remove(_LOGO_PATH)
            self._logo_refresh_preview()
            mostrar_mensaje(self, tr("cfg.logo_deleted_title", default="Logo eliminado"), tr("cfg.logo_deleted_msg", default="El logo corporativo ha sido eliminado."), "success")
        except Exception as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.logo_delete_err", default="No se pudo eliminar el logo: {exc}", exc=exc), "error")

    def _load_eventos(self):
        try:
            path = os.path.normpath(_EVENTS_FILE)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_eventos(self):
        try:
            path = os.path.normpath(_EVENTS_FILE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._eventos, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # --- PESTAÑA 7: PLANIFICAR CITAS ---
    def _crear_page_citas(self):
        self._eventos = self._load_eventos()
        self._cal_popup = None
        page = QWidget()
        self._citas_page = page
        ly = QHBoxLayout(page)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        # Calendar wrapped in neon border frame
        self._cal_widget = _VentasCalendarWidget()
        self._cal_widget.set_events(self._eventos)
        self._cal_widget.clicked.connect(self._on_calendar_clicked)

        cal_frame = QFrame()
        cal_frame.setStyleSheet(f"""
            QFrame {{
                background: {_VENTAS_SIDEBAR};
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        cal_frame_ly = QVBoxLayout(cal_frame)
        cal_frame_ly.setContentsMargins(12, 12, 12, 12)
        cal_frame_ly.addWidget(self._cal_widget)
        ly.addWidget(cal_frame, 2)

        form = QFrame()
        form.setStyleSheet(f"background: {_VENTAS_BG}; padding: 20px;")
        fl = QVBoxLayout(form)
        fl.setSpacing(15)
        fl.addWidget(
            QLabel(
                tr("cfg.detalles_del_evento", default="DETALLES DEL EVENTO"),
                styleSheet=f"color: {_CIAN}; font-weight: 900; font-family: 'Segoe UI';",
            )
        )

        fl.addWidget(QLabel(tr("cfg.asunto_lbl", default="ASUNTO:"), styleSheet="color: white; font-weight: bold;"))
        self._cal_asunto = QLineEdit()
        self._cal_asunto.setPlaceholderText(tr("cfg.asunto_ph", default="Introduzca el nombre del asunto"))
        self._cal_asunto.setStyleSheet(f"""
            QLineEdit {{
                background: #161B22; color: white; border: 2px solid {_CIAN};
                border-radius: 12px; padding: 10px 14px;
                font-family: 'Segoe UI'; font-size: 14px;
            }}
            QLineEdit::placeholder {{
                color: #6B737E;
            }}
        """)
        fl.addWidget(self._cal_asunto)

        fl.addWidget(QLabel(tr("cfg.hora_inicio", default="HORA INICIO:"), styleSheet="color: white; font-weight: bold;"))
        ly_inicio, self._inicio_h, self._inicio_m = self._crear_selector_tiempo_windows()
        fl.addLayout(ly_inicio)

        fl.addWidget(QLabel(tr("cfg.hora_fin", default="HORA FIN:"), styleSheet="color: white; font-weight: bold;"))
        ly_fin, self._fin_h, self._fin_m = self._crear_selector_tiempo_windows()
        fl.addLayout(ly_fin)

        fl.addStretch()
        btn_save = QPushButton(tr("cfg.save_event", default="GUARDAR EVENTO"))
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #238636; color: #0E1117; border-radius: 10px;
                padding: 12px; font-weight: 900;
            }
            QPushButton:hover {
                background: #FFFFFF; color: #0E1117;
            }
        """)
        btn_save.clicked.connect(self._guardar_evento)
        fl.addWidget(btn_save)

        ly.addWidget(form, 1)
        return page

    def _mostrar_cita_dialogo(self, titulo, mensaje, es_error, btn_texto):
        """Dialog estilizado con texto de botón garantizado visible."""
        accent = "#E3B341" if es_error else "#238636"
        icono = "!" if es_error else "✓"

        from PyQt6.QtWidgets import QDialog
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dlg.setModal(True)
        dlg.setMinimumWidth(380)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame(dlg)
        panel.setStyleSheet(f"""
            QFrame {{
                background: #0D1117;
                border: 2px solid {accent};
                border-radius: 14px;
            }}
        """)
        p_ly = QVBoxLayout(panel)
        p_ly.setContentsMargins(24, 20, 24, 20)
        p_ly.setSpacing(14)

        h_ly = QHBoxLayout()
        h_ly.setSpacing(14)
        icon_lbl = QLabel(icono)
        icon_lbl.setFixedSize(42, 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            QLabel {{
                background: {accent}; color: #0D1117;
                border-radius: 21px; font-size: 22px; font-weight: 900;
                font-family: 'Segoe UI'; border: none;
            }}
        """)
        title_lbl = QLabel(titulo)
        title_lbl.setStyleSheet(
            f"color: {accent}; font-weight: 900; font-size: 15px;"
            " background: transparent; border: none; font-family: 'Segoe UI';"
        )
        h_ly.addWidget(icon_lbl)
        h_ly.addWidget(title_lbl, 1)
        p_ly.addLayout(h_ly)

        msg_lbl = QLabel(mensaje)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            "color: #E6EDF3; font-size: 13px; background: transparent;"
            " border: none; font-family: 'Segoe UI';"
        )
        p_ly.addWidget(msg_lbl)

        btn = QPushButton(btn_texto)
        btn.setFixedHeight(44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {accent}; color: #0E1117;
                border-radius: 10px; font-weight: 900; font-size: 13px;
                font-family: 'Segoe UI'; border: 2px solid {accent};
            }}
            QPushButton:hover {{
                background: #0D1117; color: {accent};
            }}
        """)
        btn.clicked.connect(dlg.accept)
        p_ly.addWidget(btn)

        outer.addWidget(panel)
        dlg.exec()

    def _guardar_evento(self):
        # Cerrar popup de evento si estuviera abierto
        self._cerrar_cal_popup()

        asunto = self._cal_asunto.text().strip()
        if not asunto:
            self._mostrar_cita_dialogo(
                "INFORMACIÓN INCOMPLETA",
                "Para guardar un evento es necesario completar toda la información antes de guardarlo.",
                es_error=True,
                btn_texto="ENTENDIDO",
            )
            return

        fecha = self._cal_widget.selectedDate()
        fecha_str = fecha.toString("yyyy-MM-dd")
        hora_inicio = f"{self._inicio_h.currentText()} {self._inicio_m.currentText()}"
        hora_fin = f"{self._fin_h.currentText()} {self._fin_m.currentText()}"

        if fecha_str not in self._eventos:
            self._eventos[fecha_str] = []
        self._eventos[fecha_str].append({
            "asunto": asunto,
            "hora_inicio": hora_inicio,
            "hora_fin": hora_fin,
        })
        self._save_eventos()

        self._cal_widget.update()
        self._cal_asunto.clear()

        self._mostrar_cita_dialogo(
            "EVENTO GUARDADO",
            f"El evento '{asunto}' se ha guardado para el {fecha.toString('dd/MM/yyyy')}.",
            es_error=False,
            btn_texto="ACEPTAR",
        )

    def _cerrar_cal_popup(self):
        if self._cal_popup is not None:
            try:
                self._cal_popup.hide()
                self._cal_popup.deleteLater()
            except Exception:
                pass
            self._cal_popup = None

    def _on_calendar_clicked(self, qdate):
        self._cerrar_cal_popup()
        fecha_str = qdate.toString("yyyy-MM-dd")
        eventos = self._eventos.get(fecha_str, [])
        if not eventos:
            return

        popup = QFrame(self._citas_page)
        popup.setMinimumWidth(240)
        popup.setStyleSheet(f"""
            QFrame {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        self._cal_popup = popup

        outer_ly = QVBoxLayout(popup)
        outer_ly.setContentsMargins(14, 12, 14, 18)
        outer_ly.setSpacing(8)

        # Header: date + close button
        hdr = QHBoxLayout()
        title = QLabel(f"📅  {qdate.toString('dd/MM/yyyy')}")
        title.setStyleSheet(
            f"color: {_CIAN}; font-weight: 900; font-size: 13px; background: transparent; border: none;"
        )
        btn_x = _CloseCircleBtn(self._cerrar_cal_popup)
        hdr.addWidget(title, 1)
        hdr.addWidget(btn_x)
        outer_ly.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_CIAN}; border: none;")
        outer_ly.addWidget(sep)

        def _hacer_editar(idx, pop):
            ev = self._eventos[fecha_str][idx]
            self._cal_asunto.setText(ev["asunto"])
            self._inicio_h._valor = ev["hora_inicio"].split()[0]
            self._inicio_h._refresh_btn()
            self._inicio_m._valor = ev["hora_inicio"].split()[1]
            self._inicio_m._refresh_btn()
            self._fin_h._valor = ev["hora_fin"].split()[0]
            self._fin_h._refresh_btn()
            self._fin_m._valor = ev["hora_fin"].split()[1]
            self._fin_m._refresh_btn()
            del self._eventos[fecha_str][idx]
            if not self._eventos[fecha_str]:
                del self._eventos[fecha_str]
            self._save_eventos()
            self._cal_widget.update()
            self._cerrar_cal_popup()

        def _hacer_borrar(idx):
            del self._eventos[fecha_str][idx]
            if not self._eventos[fecha_str]:
                del self._eventos[fecha_str]
            self._save_eventos()
            self._cal_widget.update()
            self._cerrar_cal_popup()

        for i, ev in enumerate(list(eventos)):
            ev_frame = QFrame()
            ev_frame.setStyleSheet(
                "QFrame { background: #161B22; border-radius: 10px; border: none; }"
            )
            ev_ly = QVBoxLayout(ev_frame)
            ev_ly.setContentsMargins(12, 8, 12, 12)
            ev_ly.setSpacing(6)

            lbl_asunto = QLabel(ev["asunto"])
            lbl_asunto.setStyleSheet(
                "color: white; font-weight: 900; font-size: 12px; background: transparent; border: none;"
            )
            lbl_asunto.setWordWrap(True)

            lbl_tiempo = QLabel(f"⏰  {ev['hora_inicio']} — {ev['hora_fin']}")
            lbl_tiempo.setStyleSheet(
                f"color: {_CIAN}; font-size: 11px; background: transparent; border: none;"
            )

            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            btn_edit = QPushButton("✏  " + tr("cfg.edit", default="EDITAR"))
            btn_edit.setFixedHeight(34)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setStyleSheet(f"""
                QPushButton {{
                    background: #1A2230; color: {_CIAN}; border: 1px solid {_CIAN};
                    border-radius: 6px; font-size: 11px; font-weight: 900;
                }}
                QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
            """)
            btn_edit.clicked.connect(lambda _c=False, idx=i: _hacer_editar(idx, popup))

            btn_del = QPushButton("🗑  " + tr("cfg.borrar", default="BORRAR"))
            btn_del.setFixedHeight(34)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background: #1A2230; color: #F85149; border: 1px solid #F85149;
                    border-radius: 6px; font-size: 11px; font-weight: 900;
                }
                QPushButton:hover { background: #F85149; color: #0E1117; border: 1px solid #F85149; }
            """)
            btn_del.clicked.connect(lambda _c=False, idx=i: _hacer_borrar(idx))

            btn_row.addWidget(btn_edit)
            btn_row.addWidget(btn_del)

            ev_ly.addWidget(lbl_asunto)
            ev_ly.addWidget(lbl_tiempo)
            ev_ly.addLayout(btn_row)
            outer_ly.addWidget(ev_frame)

        # Show first so Qt can compute correct size, then reposition
        popup.show()
        popup.adjustSize()
        cur = self._citas_page.mapFromGlobal(QCursor.pos())
        pw, ph = popup.width(), popup.height()
        pr = self._citas_page.rect()
        x = min(cur.x() + 12, pr.width() - pw - 4)
        y = min(cur.y() + 12, pr.height() - ph - 4)
        popup.move(max(4, x), max(4, y))
        popup.raise_()

    def _crear_selector_tiempo_windows(self):
        """Crea un par de _TimeDropdown (Horas y Minutos) con estilo neón y scroll."""
        h_ly = QHBoxLayout()
        h_ly.setSpacing(10)

        combo_h = _TimeDropdown([f"{i}h" for i in range(24)], max_visible=5)
        combo_h.setFixedWidth(110)
        combo_h._btn.setFixedHeight(44)

        # Minutos en pasos de 5 (00,05,…,55) y máx. 5 visibles para que el
        # desplegable no sea demasiado largo.
        combo_m = _TimeDropdown(
            [f"{i:02}min" for i in range(0, 60, 5)], max_visible=5
        )
        combo_m.setFixedWidth(120)
        combo_m._btn.setFixedHeight(44)

        h_ly.addWidget(combo_h)
        h_ly.addWidget(combo_m)
        h_ly.addStretch()
        return h_ly, combo_h, combo_m

    # --- PESTAÑA 8: FISCALIDAD ---
    def _crear_page_fiscalidad(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(16)

        # ── Título ───────────────────────────────────────────────────────────
        lbl_tit = QLabel(tr("cfg.fis_title", default="CENTRO DE DOCUMENTACIÓN FISCAL Y LABORAL"))
        lbl_tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;")
        outer.addWidget(lbl_tit)

        # ── Módulos (4 botones de selección) ─────────────────────────────────
        # EMPRESA se retiró: los datos de empresa se gestionan en la pestaña
        # "DATOS DE EMPRESA" (fuente única).
        # AUDITORÍA Y REGISTRO DE DOCUMENTOS se retiró: el repositorio documental
        # está ahora centralizado en el menú → DOCUMENTOS (centro_documental.py).
        MODULOS = [
            ("👷  " + tr("cfg.mod_laboral", default="LABORAL"),   "#3FB950"),
            ("📋  " + tr("cfg.mod_fiscal", default="FISCAL"),    "#58A6FF"),
        ]
        mod_row = QHBoxLayout(); mod_row.setSpacing(8)
        self._fis_mod_btns = []
        self._fis_stack = QStackedWidget()

        for i, (label, color) in enumerate(MODULOS):
            b = QPushButton(label); b.setFixedHeight(46)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            b.setStyleSheet(
                f"QPushButton{{background:#161B22;color:{color};border:2px solid {color};"
                f"border-radius:10px;font-family:'Segoe UI';font-weight:900;font-size:12px;}}"
                f"QPushButton:checked{{background:{color};color:#0D1117;}}"
                f"QPushButton:hover{{background:{color};color:#0D1117;}}"
            )
            b.clicked.connect(lambda _, idx=i: self._fis_cambiar_modulo(idx))
            mod_row.addWidget(b)
            self._fis_mod_btns.append(b)

        outer.addLayout(mod_row)

        self._fis_stack.addWidget(self._fis_modulo_laboral())
        self._fis_stack.addWidget(self._fis_modulo_fiscal())
        outer.addWidget(self._fis_stack)

        self._fis_mod_btns[0].setChecked(True)
        return page

    def _fis_cambiar_modulo(self, idx):
        for i, b in enumerate(self._fis_mod_btns):
            b.setChecked(i == idx)
        self._fis_stack.setCurrentIndex(idx)

    def _fis_card_btn(self, icono, titulo, descripcion, tipo_wizard):
        """Tarjeta de acción para módulos de fiscalidad."""
        card = QFrame()
        card.setObjectName("fisCard")
        card.setStyleSheet(f"QFrame#fisCard{{background:#161B22;border:1px solid {_BORDE};border-radius:14px;}}QFrame#fisCard:hover{{border-color:{_CIAN};}}")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFixedHeight(90)
        ly = QHBoxLayout(card); ly.setContentsMargins(18, 0, 18, 0); ly.setSpacing(14)
        lbl_ic = QLabel(icono); lbl_ic.setStyleSheet("font-size:26px;background:transparent;")
        lbl_ic.setFixedWidth(36)
        info = QVBoxLayout(); info.setSpacing(2)
        lbl_t = QLabel(titulo); lbl_t.setStyleSheet("color:white;font-family:'Segoe UI';font-weight:900;font-size:13px;background:transparent;")
        lbl_d = QLabel(descripcion); lbl_d.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-size:11px;background:transparent;")
        info.addWidget(lbl_t); info.addWidget(lbl_d)
        lbl_arr = QLabel("›"); lbl_arr.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:900;background:transparent;")
        ly.addWidget(lbl_ic); ly.addLayout(info); ly.addStretch(); ly.addWidget(lbl_arr)

        def _click(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._abrir_wizard_fiscal(tipo_wizard)
        card.mousePressEvent = _click
        return card

    def _abrir_wizard_fiscal(self, tipo):
        dlg = _WizardDocumentoFiscal(tipo_inicial=tipo, parent=self)
        dlg.exec()

    def _fis_modulo_laboral(self):
        w = QWidget()
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget(); inner_ly = QVBoxLayout(inner); inner_ly.setSpacing(8); inner_ly.setContentsMargins(4, 8, 12, 8)
        entries = [
            ("📄", tr("cfg.lab_t1", default="CONTRATOS"), tr("cfg.lab_d1", default="Genera contratos laborales con validación legal automática"), "CONTRATO"),
            ("📊", tr("cfg.lab_t2", default="NÓMINAS"), tr("cfg.lab_d2", default="Cálculo y generación de nóminas con IRPF y cotización"), "NÓMINA"),
            ("✅", tr("cfg.lab_t3", default="ALTAS LABORALES"), tr("cfg.lab_d3", default="Tramitar altas en la Seguridad Social (preparado para SS RED)"), "ALTA"),
            ("❌", tr("cfg.lab_t4", default="BAJAS LABORALES"), tr("cfg.lab_d4", default="Tramitar bajas y situaciones de incapacidad temporal"), "BAJA"),
            ("💼", tr("cfg.lab_t5", default="FINIQUITOS"), tr("cfg.lab_d5", default="Genera finiquitos con cálculo automático de conceptos"), "FINIQUITO"),
            ("🏢", tr("cfg.lab_t6", default="CERTIFICADOS"), tr("cfg.lab_d6", default="Emite certificados de empresa y vida laboral"), "CERTIFICADO"),
            ("📃", tr("cfg.lab_t7", default="CERTIFICADOS LABORAL"), tr("cfg.lab_d7", default="Certificados de antigüedad, funciones, ingresos y jornada"), "CERT LABORAL"),
            ("📮", tr("cfg.lab_t8", default="CARTAS DE DESPIDO"), tr("cfg.lab_d8", default="Redacta cartas con motivos predeterminados y validación legal"), "CARTA DESPIDO"),
            ("🌴", tr("cfg.lab_t9", default="VACACIONES"), tr("cfg.lab_d9", default="Solicitudes, aprobaciones y denegaciones de vacaciones"), "VACACIONES"),
        ]
        for ic, tit, desc, tipo in entries:
            inner_ly.addWidget(self._fis_card_btn(ic, tit, desc, tipo))
        inner_ly.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(w); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        return w

    def _fis_modulo_fiscal(self):
        w = QWidget()
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget(); inner_ly = QVBoxLayout(inner); inner_ly.setSpacing(8); inner_ly.setContentsMargins(4, 8, 12, 8)
        entries = [
            ("📋", tr("cfg.fis_t1", default="RESUMEN IVA"), tr("cfg.fis_d1", default="Genera el resumen de IVA trimestral o anual"), "RESUMEN FISCAL"),
            ("📈", tr("cfg.fis_t2", default="LIBRO DE INGRESOS"), tr("cfg.fis_d2", default="Registro de facturas emitidas y totales del período"), "LIBRO INGRESOS"),
            ("📉", tr("cfg.fis_t3", default="LIBRO DE GASTOS"), tr("cfg.fis_d3", default="Registro de gastos y facturas recibidas del período"), "LIBRO GASTOS"),
            ("🔍", tr("cfg.fis_t4", default="INFORME AUDITORÍA"), tr("cfg.fis_d4", default="Informe de auditoría de caja, RRHH, accesos y movimientos"), "INFORME AUDIT"),
        ]
        for ic, tit, desc, tipo in entries:
            inner_ly.addWidget(self._fis_card_btn(ic, tit, desc, tipo))
        inner_ly.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(w); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        return w

    def _fis_modulo_empresa(self):
        w = QWidget()
        outer_ly = QVBoxLayout(w)
        outer_ly.setContentsMargins(0, 0, 0, 0)
        outer_ly.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        inner = QWidget()
        ly = QVBoxLayout(inner)
        ly.setContentsMargins(4, 10, 12, 10)
        ly.setSpacing(10)

        lbl = QLabel(tr("cfg.emp_title", default="DATOS DE EMPRESA"))
        lbl.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;")
        ly.addWidget(lbl)

        def _inp(ph):
            i = QLineEdit(); i.setPlaceholderText(ph); i.setFixedHeight(44)
            i.setStyleSheet(f"QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};border-radius:10px;padding:10px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
            return i

        def _lbl_s(txt):
            l = QLabel(txt); l.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:13px;font-weight:bold;"); return l

        campos = [
            (tr("cfg.emp_l1", default="Razón social:"), tr("cfg.emp_p1", default="Nombre legal de la empresa")),
            (tr("cfg.emp_l2", default="CIF / NIF empresa:"), tr("cfg.emp_p2", default="Ej: B12345678")),
            (tr("cfg.emp_l3", default="Dirección fiscal:"), tr("cfg.emp_p3", default="Calle, número, ciudad, CP")),
            (tr("cfg.emp_l4", default="Email empresa:"), tr("cfg.emp_p4", default="correo@empresa.com")),
            (tr("cfg.emp_l5", default="Teléfono:"), tr("cfg.emp_p5", default="+34 XXX XXX XXX")),
            (tr("cfg.emp_l6", default="IBAN empresa:"), tr("cfg.emp_p6", default="ES00 0000 0000 0000 0000 0000")),
        ]
        self._fis_emp_inps = []
        for lbl_txt, ph in campos:
            ly.addWidget(_lbl_s(lbl_txt))
            inp = _inp(ph); ly.addWidget(inp)
            self._fis_emp_inps.append(inp)

        btn_g = QPushButton(tr("cfg.emp_save_btn", default="GUARDAR DATOS DE EMPRESA"))
        btn_g.setFixedHeight(44); btn_g.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_g.setStyleSheet(f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}QPushButton:hover{{background:{_CIAN};color:#0D1117;}}")
        btn_g.clicked.connect(self._fis_guardar_empresa)
        ly.addWidget(btn_g)
        ly.addStretch()

        scroll.setWidget(inner)
        outer_ly.addWidget(scroll)

        self._fis_cargar_empresa()
        return w

    def _fis_empresa_path(self):
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "datos_empresa.json"))

    def _fis_cargar_empresa(self):
        # Fuente única: lee de la BD (empresas), no del JSON legacy (FASE 2c).
        try:
            from src.db import empresa as _emp
            e = _emp.obtener_empresa() or {}
            vals = [e.get("razon_social") or "", e.get("cif_nif") or "",
                    e.get("direccion_fiscal") or "", e.get("email_principal") or "",
                    e.get("telefono") or "", ""]
            for i, inp in enumerate(getattr(self, "_fis_emp_inps", [])):
                if i < len(vals):
                    inp.setText(str(vals[i]))
        except Exception:
            pass

    def _fis_guardar_empresa(self):
        # Fuente única: guarda en la BD (empresas); se refleja en todos los documentos.
        inps = getattr(self, "_fis_emp_inps", [])
        cols = ["razon_social", "cif_nif", "direccion_fiscal", "email_principal", "telefono"]
        sets = {cols[i]: inps[i].text().strip() for i in range(min(len(cols), len(inps)))}
        try:
            from src.db import empresa as _emp
            _emp.actualizar_empresa(_emp.empresa_actual_id(), **sets)
            mostrar_mensaje(self, tr("cfg.saved_title", default="Guardado"), tr("cfg.emp_saved", default="Datos de empresa guardados correctamente."), "success")
        except Exception as e:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.emp_save_err", default="No se pudieron guardar los datos: {e}", e=e), "error")

    # --- PESTAÑA 2: PLAZO DEVOLUCIÓN ---
    def _crear_page_plazo_devolucion(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(50, 40, 50, 30)
        ly.setSpacing(18)

        title = QLabel(tr("cfg.plazo_title", default="CONFIGURACIÓN DE PLAZOS Y TICKETS"))
        title.setStyleSheet(f"color: {_CIAN}; font-size: 22px; font-weight: 900;")
        ly.addWidget(title)

        # Conmutador de módulos (justo debajo del título): separa "Periodo de
        # devolución" de "Artículos baneados" para no saturar la pestaña.
        toggle = QHBoxLayout(); toggle.setSpacing(12)
        self._btn_mod_periodo = self._toggle_btn_devol(tr("cfg.mod_periodo", default="PERIODO DE DEVOLUCIÓN"))
        self._btn_mod_baneados = self._toggle_btn_devol(tr("cfg.mod_baneados", default="ARTÍCULOS BANEADOS"))
        self._btn_mod_periodo.clicked.connect(lambda: self._cambiar_mod_devol(0))
        self._btn_mod_baneados.clicked.connect(lambda: self._cambiar_mod_devol(1))
        toggle.addWidget(self._btn_mod_periodo)
        toggle.addWidget(self._btn_mod_baneados)
        toggle.addStretch()
        ly.addLayout(toggle)

        self._stack_devol = QStackedWidget()
        self._stack_devol.addWidget(self._modulo_periodo())    # 0
        self._stack_devol.addWidget(self._modulo_baneados())   # 1
        ly.addWidget(self._stack_devol, 1)
        self._cambiar_mod_devol(0)
        return page

    def _toggle_btn_devol(self, texto):
        b = QPushButton(texto)
        b.setCheckable(True); b.setFixedHeight(44); b.setMinimumWidth(240)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _cambiar_mod_devol(self, idx):
        self._stack_devol.setCurrentIndex(idx)
        for i, b in enumerate((self._btn_mod_periodo, self._btn_mod_baneados)):
            if i == idx:
                b.setChecked(True)
                b.setStyleSheet(f"QPushButton{{background:{_CIAN};color:#0E1117;border:2px solid {_CIAN};"
                                "border-radius:12px;font-family:'Segoe UI';font-weight:900;font-size:13px;padding:0 22px;}")
            else:
                b.setChecked(False)
                b.setStyleSheet(f"QPushButton{{background:{_PANEL_BG};color:{_CIAN};border:2px solid {_BORDE};"
                                "border-radius:12px;font-family:'Segoe UI';font-weight:900;font-size:13px;padding:0 22px;}"
                                f"QPushButton:hover{{border-color:{_CIAN};}}")

    def _btn_guardar_verde(self, slot):
        b = QPushButton(tr("cfg.save_changes", default="GUARDAR CAMBIOS"))
        b.setFixedSize(200, 45); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:#238636;color:#0E1117;border:2px solid #238636;border-radius:10px;"
                        "font-family:'Segoe UI';font-weight:bold;font-size:13px;}"
                        "QPushButton:hover{background:#FFFFFF;color:#0E1117;}")
        b.clicked.connect(slot)
        return b

    def _guardar_devol(self):
        try:
            from src.db.config_ticket import guardar_config_ticket
            dias = (self.spin_dias.value()
                    + self.spin_meses.value() * 30
                    + self.spin_anios.value() * 365)
            guardar_config_ticket(
                texto_legal=self.text_ticket.toPlainText().strip(),
                devol_dias=int(dias) or 30)
        except Exception as e:
            logging.getLogger("gestion_usuarios").warning("No se pudo guardar config_ticket: %s", e)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("cfg.guardado_t", default="Guardado"),
                            tr("cfg.guardado_msg", default="Cambios guardados correctamente."), "info")

    # ── Módulo 1: periodo de devolución + texto legal ────────────────────────
    def _modulo_periodo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(14)
        ly.addWidget(QLabel(tr("cfg.legal_text_label", default="TEXTO LEGAL PARA PIE DE TICKET:"),
                            styleSheet="color: white; font-weight: 900;"))
        self.text_ticket = QTextEdit()
        self.text_ticket.setPlaceholderText(
            tr("cfg.legal_text_ph", default="Redacte aquí el texto legal y el mensaje de despedida..."))
        self.text_ticket.setMaximumHeight(150)
        self.text_ticket.setStyleSheet(
            f"border: 2px solid {_CIAN}; border-radius: 15px; padding: 15px; color: white; background: #0D1117; font-family: 'Segoe UI';")
        ly.addWidget(self.text_ticket)

        form = QFrame()
        form.setStyleSheet(f"background: {_PANEL_BG}; border-radius: 20px; padding: 24px; border: 2px solid {_BORDE};")
        form_ly = QVBoxLayout(form); form_ly.setSpacing(15)
        self.spin_dias, self.layout_dias = self._crear_input_plazo_con_botones(tr("cfg.unit_days", default="DÍAS"))
        self.spin_meses, self.layout_meses = self._crear_input_plazo_con_botones(tr("cfg.unit_months", default="MESES"))
        self.spin_anios, self.layout_anios = self._crear_input_plazo_con_botones(tr("cfg.unit_years", default="AÑOS"))
        form_ly.addLayout(self.layout_dias); form_ly.addLayout(self.layout_meses); form_ly.addLayout(self.layout_anios)
        ly.addWidget(form)
        ly.addStretch()
        ly.addWidget(self._btn_guardar_verde(self._guardar_devol), alignment=Qt.AlignmentFlag.AlignRight)

        # Cargar la configuración guardada del ticket (texto legal + plazo)
        try:
            from src.db.config_ticket import obtener_config_ticket
            _c = obtener_config_ticket()
            self.text_ticket.setPlainText(_c.get("texto_legal") or "")
            self.spin_dias.setMaximum(3650)
            self.spin_dias.setValue(int(_c.get("devol_dias") or 30))
        except Exception:
            pass
        return w

    # ── Módulo 2: artículos baneados para devolución ─────────────────────────
    def _modulo_baneados(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(12)

        t = QLabel("🚫  " + tr("cfg.ban_titulo", default="ARTÍCULOS BANEADOS PARA DEVOLUCIÓN"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;background:transparent;border:none;")
        v.addWidget(t)
        sub = QLabel(tr("cfg.ban_sub", default="Estos artículos NO se podrán devolver en el TPV (política de empresa)."))
        sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:11px;background:transparent;border:none;")
        v.addWidget(sub)

        fila = QHBoxLayout(); fila.setSpacing(10)
        self.inp_ban = QLineEdit(); self.inp_ban.setFixedHeight(40)
        self.inp_ban.setPlaceholderText(tr("cfg.ban_ph", default="Buscar por EAN o nombre del artículo…"))
        self.inp_ban.setStyleSheet(f"QLineEdit{{background:#0D1117;color:white;border:2px solid {_CIAN};border-radius:10px;padding:0 14px;font-size:14px;}}")
        self.inp_ban.returnPressed.connect(self._buscar_para_banear)
        bb = QPushButton("🔍  " + tr("cfg.ban_buscar", default="BUSCAR / BANEAR")); bb.setFixedHeight(40)
        bb.setCursor(Qt.CursorShape.PointingHandCursor)
        bb.setStyleSheet(f"QPushButton{{background:#161B22;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;font-size:12px;padding:0 16px;}}QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        bb.clicked.connect(self._buscar_para_banear)
        fila.addWidget(self.inp_ban, 1); fila.addWidget(bb)
        v.addLayout(fila)

        self.tabla_ban = QTableWidget(0, 5)
        self.tabla_ban.setHorizontalHeaderLabels([
            tr("cfg.ban_col_cod", default="CÓDIGO"), tr("cfg.ban_col_art", default="ARTÍCULO"),
            tr("cfg.ban_col_motivo", default="MOTIVO"), tr("cfg.ban_col_fecha", default="FECHA"),
            tr("cfg.ban_col_acc", default="ACCIONES"),
        ])
        self.tabla_ban.verticalHeader().setVisible(False)
        self.tabla_ban.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_ban.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla_ban.setMinimumHeight(220)
        # Filas más altas para que quepa el botón DESBANEAR (centrado en su celda).
        self.tabla_ban.verticalHeader().setDefaultSectionSize(58)
        _h = self.tabla_ban.horizontalHeader()
        _h.setHighlightSections(False)
        # MOTIVO se estira (ocupa el espacio libre → más ancho); el resto fijas.
        # ARTÍCULO se reduce para ceder ese ancho a MOTIVO.
        for _c in (0, 1, 3, 4):
            _h.setSectionResizeMode(_c, QHeaderView.ResizeMode.Fixed)
        _h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_ban.setColumnWidth(0, 150)   # CÓDIGO
        self.tabla_ban.setColumnWidth(1, 200)   # ARTÍCULO (reducido)
        self.tabla_ban.setColumnWidth(3, 150)   # FECHA
        self.tabla_ban.setColumnWidth(4, 150)   # ACCIONES
        # Tabla sin borde propio; el contorno neón + esquinas redondeadas los aporta
        # el contenedor (la tabla va con margen para no cortar el contorno). Cabeceras
        # con hover-swap y esquinas superiores redondeadas (1ª/última columna).
        self.tabla_ban.setStyleSheet(f"""
            QTableWidget{{background:transparent;color:#E6EDF3;border:none;
                          gridline-color:{_BORDE};font-family:'Segoe UI';font-size:12px;outline:none;}}
            QHeaderView::section{{background:#0E1117;color:{_CIAN};border:none;border-bottom:2px solid {_BORDE};
                                  padding:8px;font-weight:900;font-size:11px;}}
            QHeaderView::section:first{{border-top-left-radius:10px;}}
            QHeaderView::section:last{{border-top-right-radius:10px;}}
            QHeaderView::section:hover{{background:{_CIAN};color:#0E1117;}}
        """)
        wrap = QFrame(); wrap.setObjectName("banWrap")
        wrap.setStyleSheet(f"QFrame#banWrap{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        wl = QVBoxLayout(wrap); wl.setContentsMargins(5, 5, 5, 5); wl.addWidget(self.tabla_ban)
        v.addWidget(wrap, 1)
        # Sin botón GUARDAR CAMBIOS: los baneos se guardan al instante (banear/desbanear).
        self._refrescar_tabla_baneados()
        return w

    def _buscar_para_banear(self):
        term = self.inp_ban.text().strip()
        if not term:
            return
        res = devoluciones_baneados.buscar_articulo(term)
        if not res:
            mostrar_mensaje(self, tr("cfg.ban_nores_t", default="Sin resultados"),
                            tr("cfg.ban_nores", default="No se encontró ningún artículo con '{t}'.", t=term), "info")
            return
        art = res[0]
        if devoluciones_baneados.esta_baneado(art.get("codigo")):
            mostrar_mensaje(self, tr("cfg.ban_ya_t", default="Ya baneado"),
                            tr("cfg.ban_ya", default="El artículo {c} ya está baneado.", c=art.get("codigo")), "info")
            return
        dlg = _BanearDialog(art.get("codigo"), art.get("nombre"), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            usuario = sesion_global.obtener_nombre() if sesion_global else ""
            devoluciones_baneados.banear_articulo(art["codigo"], art.get("nombre", ""), dlg.motivo(), usuario)
            self.inp_ban.clear()
            self._refrescar_tabla_baneados()

    def _refrescar_tabla_baneados(self):
        filas = devoluciones_baneados.listar_baneados()
        self.tabla_ban.setRowCount(len(filas))
        for r, b in enumerate(filas):
            for col, val in enumerate([b.get("codigo", ""), b.get("nombre") or "—",
                                       b.get("motivo") or "—", str(b.get("fecha") or "")]):
                it = QTableWidgetItem("  " + str(val))
                if col == 0:
                    it.setForeground(QColor("#E3B341"))
                self.tabla_ban.setItem(r, col, it)
            btn = QPushButton("🗑  " + tr("cfg.ban_desbanear", default="DESBANEAR"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setStyleSheet("QPushButton{background:#0E1117;color:#F85149;border:2px solid #F85149;border-radius:8px;font-weight:900;font-size:11px;padding:0 14px;}QPushButton:hover{background:#F85149;color:#0E1117;}")
            btn.clicked.connect(lambda _=False, bid=b.get("id"): self._desbanear(bid))
            # Contenedor que centra el botón vertical y horizontalmente en la celda
            # (así, al subir la altura de fila, el botón queda a media altura).
            cont = QWidget(); cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont); hl.setContentsMargins(6, 0, 6, 0)
            hl.addWidget(btn); hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla_ban.setCellWidget(r, 4, cont)

    def _desbanear(self, id_ban):
        if mostrar_confirmacion and not mostrar_confirmacion(
            self, tr("cfg.ban_desb_t", default="Desbanear artículo"),
            tr("cfg.ban_desb_msg", default="¿Permitir de nuevo la devolución de este artículo?")):
            return
        devoluciones_baneados.desbanear_articulo(id_ban=id_ban)
        self._refrescar_tabla_baneados()

    def _crear_input_plazo_con_botones(self, sufijo):
        """Crea un layout con botones +/- neón a la izquierda y el spinbox sin flechas."""
        ly = QHBoxLayout()
        ly.setSpacing(5)  # Reducir espacio para que quepan mejor

        sb = QSpinBox()
        sb.setSuffix(f" {sufijo}")
        sb.setFixedSize(220, 55)  # Tamaño aumentado para alineación perfecta
        sb.setStyleSheet(f"""
            QSpinBox {{ 
                border: 2px solid {_CIAN}; border-radius: 12px; padding: 10px 15px; 
                color: white; background: #161B22; font-weight: bold; font-size: 16px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; height: 0px; }}
        """)

        btn_style = f"""
            QPushButton {{
                background: #161B22; border: 2.5px solid {_CIAN}; color: {_CIAN};
                border-radius: 12px; font-family: 'Segoe UI'; font-weight: 900; font-size: 32px; width: 55px; height: 55px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """
        btn_min = _NeonSymbolButton("-")
        btn_min.setStyleSheet(btn_style)
        btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_min.clicked.connect(lambda: sb.setValue(sb.value() - 1))

        btn_plus = _NeonSymbolButton("+")
        btn_plus.setStyleSheet(btn_style)
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.clicked.connect(lambda: sb.setValue(sb.value() + 1))

        ly.addWidget(btn_min)
        ly.addWidget(btn_plus)
        ly.addWidget(sb)
        ly.addStretch()
        return sb, ly

    # --- PESTAÑA 3: GENERAR PERFIL EMPLEADO (Lógica Anterior) ---
    def _crear_page_perfiles(self):
        page = QWidget()
        layout_principal = QHBoxLayout(page)
        layout_principal.setContentsMargins(30, 30, 30, 30)
        layout_principal.setSpacing(25)

        # Formulario Izquierda
        form_container = QFrame()
        form_container.setFixedWidth(400)
        form_container.setStyleSheet(
            f"background-color: {_PANEL_BG}; border-radius: 12px; border: 1px solid {_BORDE};"
        )
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(25, 25, 25, 25)
        form_layout.setSpacing(10)

        lbl_add = QLabel(tr("cfg.new_profile", default="NUEVO PERFIL EMPLEADO"))
        lbl_add.setStyleSheet(
            f"color: {_CIAN}; font-weight: bold; font-size: 15px; border: none;"
        )
        form_layout.addWidget(lbl_add)

        input_css = f"""
            QLineEdit, QComboBox {{
                background-color: #0D1117; color: white; border: 2px solid {_CIAN};
                border-radius: 10px; padding: 12px; font-size: 13px; font-weight: bold;
            }}
        """

        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText(tr("cfg.ph_emp_name", default="NOMBRE DEL EMPLEADO"))
        self.input_nombre.setStyleSheet(input_css)

        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setPlaceholderText(tr("cfg.ph_password", default="CONTRASEÑA (4 DÍGITOS)"))
        self.input_pass.setMaxLength(4)
        self.input_pass.setStyleSheet(input_css)

        self.input_pass2 = QLineEdit()
        self.input_pass2.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass2.setPlaceholderText(tr("cfg.ph_password2", default="REPETIR CONTRASEÑA (4 DÍGITOS)"))
        self.input_pass2.setMaxLength(4)
        self.input_pass2.setStyleSheet(input_css)

        self.combo_perfil = _PerfilDropdown(["OPERARIO", "GERENTE", "ADMINISTRADOR", "SUPERADMIN"])

        form_layout.addWidget(self.input_nombre)
        form_layout.addWidget(self.input_pass)
        form_layout.addWidget(self.input_pass2)
        form_layout.addWidget(self.combo_perfil)

        btn_guardar = QPushButton(tr("cfg.register_emp", default="REGISTRAR EMPLEADO"))
        btn_guardar.setFixedHeight(50)
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.setStyleSheet(f"""
            QPushButton {{
                background-color: {_CIAN};
                color: #0E1117;
                font-weight: bold;
                border-radius: 10px;
                border: 2px solid {_CIAN};
            }}
            QPushButton:hover {{
                background-color: #0E1117;
                color: {_CIAN};
            }}
        """)
        btn_guardar.clicked.connect(self.ejecutar_creacion_usuario)
        form_layout.addWidget(btn_guardar)
        form_layout.addStretch()

        # Tabla Derecha
        tabla_container = QFrame()
        tabla_ly = QVBoxLayout(tabla_container)

        self.tabla_usuarios = QTableWidget()
        self.tabla_usuarios.setColumnCount(3)
        self.tabla_usuarios.setHorizontalHeaderLabels([
            tr("cfg.col_id", default="ID"),
            tr("cfg.col_employee", default="EMPLEADO"),
            tr("cfg.col_level", default="NIVEL"),
        ])
        self.tabla_usuarios.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabla_usuarios.verticalHeader().setVisible(False)
        self.tabla_usuarios.horizontalHeader().setStyleSheet(f"""
            QHeaderView {{
                background: transparent;
            }}
            QHeaderView::section {{
                background-color: #1A2230;
                color: {_CIAN};
                border: none;
                border-right: 1px solid {_BORDE};
                padding: 10px;
                font-weight: bold;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 15px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 15px;
                border-right: none;
            }}
            QHeaderView::section:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
        """)
        self.tabla_usuarios.setStyleSheet(f"""
            QTableWidget {{
                background: {_PANEL_BG}; color: white;
                border-radius: 15px; border: 2px solid {_CIAN};
            }}
        """)

        btn_eliminar = QPushButton(tr("cfg.del_profile", default="ELIMINAR PERFIL SELECCIONADO"))
        btn_eliminar.setFixedHeight(45)
        btn_eliminar.setStyleSheet("""
            QPushButton {
                background: #0E1117;
                color: #F85149;
                font-weight: bold;
                border-radius: 10px;
                border: 2px solid #F85149;
            }
            QPushButton:hover {
                background: #F85149;
                color: #0E1117;
            }
        """)
        btn_eliminar.clicked.connect(self.ejecutar_eliminacion_usuario)

        btn_cambiar_pin = QPushButton("🔑  " + tr("cfg.change_pin", default="CAMBIAR PIN"))
        btn_cambiar_pin.setFixedHeight(44)
        btn_cambiar_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cambiar_pin.setStyleSheet(f"""
            QPushButton {{
                background: #0D1117; color: {_CIAN};
                border: 2px solid {_CIAN}; border-radius: 12px;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 14px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_cambiar_pin.clicked.connect(self.ejecutar_cambio_pin)

        tabla_ly.addWidget(self.tabla_usuarios)
        tabla_ly.addWidget(btn_cambiar_pin)
        tabla_ly.addWidget(btn_eliminar)

        layout_principal.addWidget(form_container)
        layout_principal.addWidget(tabla_container)
        return page

    def refrescar_datos_usuarios(self):
        self.tabla_usuarios.setRowCount(0)
        usuarios = listar_usuarios()
        for i, u in enumerate(usuarios):
            self.tabla_usuarios.insertRow(i)
            self.tabla_usuarios.setItem(i, 0, QTableWidgetItem(str(u["id"])))
            self.tabla_usuarios.setItem(i, 1, QTableWidgetItem(u["nombre"].upper()))
            self.tabla_usuarios.setItem(i, 2, QTableWidgetItem(u["perfil"].upper()))

    def ejecutar_creacion_usuario(self):
        nom = self.input_nombre.text().strip()
        pw = self.input_pass.text().strip()
        pw2 = self.input_pass2.text().strip()
        if not nom or len(pw) < 4:
            mostrar_mensaje(self, tr("cfg.incomplete_title", default="Datos incompletos"), tr("cfg.incomplete_msg", default="Introduce un nombre y una contraseña de 4 dígitos."), "warning")
            return
        if not pw.isdigit():
            mostrar_mensaje(self, tr("cfg.pass_invalid_title", default="Contraseña inválida"), tr("cfg.pass_invalid_msg", default="La contraseña debe ser exactamente 4 dígitos numéricos."), "warning")
            return
        if pw != pw2:
            mostrar_mensaje(self, tr("cfg.pass_mismatch_title", default="Las contraseñas no coinciden"), tr("cfg.pass_mismatch_msg", default="Las dos contraseñas introducidas no son iguales."), "warning")
            return
        if crear_perfil(nom, pw, self.combo_perfil.currentText()):
            self.input_nombre.clear()
            self.input_pass.clear()
            self.input_pass2.clear()
            self.refrescar_datos_usuarios()

    def ejecutar_eliminacion_usuario(self):
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            return
        id_u = self.tabla_usuarios.item(fila, 0).text()
        if eliminar_usuario(id_u):
            self.refrescar_datos_usuarios()

    def ejecutar_cambio_pin(self):
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje(self, tr("cfg.nosel_title", default="Sin selección"), tr("cfg.nosel_pin_msg", default="Selecciona un empleado de la tabla antes de cambiar el PIN."), "warning")
            return
        id_u  = int(self.tabla_usuarios.item(fila, 0).text())
        nombre = self.tabla_usuarios.item(fila, 1).text()

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setFixedWidth(360)

        # Card interior con esquinas redondeadas
        card = QFrame(dlg)
        card.setObjectName("pin_card")
        card.setStyleSheet(
            f"QFrame#pin_card{{background:{_FONDO};border:2px solid {_CIAN};"
            f"border-radius:18px;}}"
        )
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setSpacing(12)
        ly.setContentsMargins(24, 24, 24, 24)

        lbl_titulo = QLabel(f"Nuevo PIN para  <b>{nombre}</b>:")
        lbl_titulo.setStyleSheet(
            "color:white;font-family:'Segoe UI';font-size:14px;background:transparent;"
        )
        ly.addWidget(lbl_titulo)

        _inp_ss = (
            f"background:#0D1117;color:white;border:2px solid {_CIAN};"
            f"border-radius:8px;padding:6px 12px;font-size:15px;font-family:'Segoe UI';"
        )

        inp = QLineEdit()
        inp.setEchoMode(QLineEdit.EchoMode.Password)
        inp.setPlaceholderText(tr("cfg.new_pin_ph", default="Nuevo PIN (4 dígitos)"))
        inp.setMaxLength(4)
        inp.setFixedHeight(44)
        inp.setStyleSheet(_inp_ss)
        ly.addWidget(inp)

        inp2 = QLineEdit()
        inp2.setEchoMode(QLineEdit.EchoMode.Password)
        inp2.setPlaceholderText(tr("cfg.repeat_pin_ph", default="Repetir PIN"))
        inp2.setMaxLength(4)
        inp2.setFixedHeight(44)
        inp2.setStyleSheet(_inp_ss)
        ly.addWidget(inp2)

        lbl_err = QLabel("")
        lbl_err.setStyleSheet("color:#FF4C4C;font-size:12px;background:transparent;")
        ly.addWidget(lbl_err)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        _btn_w, _btn_h = 115, 40
        btn_cancel = QPushButton(tr("cfg.cancel", default="CANCELAR"))
        btn_cancel.setFixedSize(_btn_w, _btn_h)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#0D1117;color:#8B949E;border:2px solid #30363D;"
            "border-radius:8px;font-family:'Segoe UI';font-weight:900;font-size:12px;padding:0;}"
            "QPushButton:hover{background:#30363D;color:white;}"
        )
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton(tr("cfg.save", default="GUARDAR"))
        btn_ok.setFixedSize(_btn_w, _btn_h)
        btn_ok.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;font-family:'Segoe UI';font-weight:900;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}"
        )
        btn_ok.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        ly.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        pin = inp.text().strip()
        pin2 = inp2.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            mostrar_mensaje(self, tr("cfg.pin_invalid2_title", default="PIN inválido"), tr("cfg.pin_invalid2_msg", default="El PIN debe ser exactamente 4 dígitos numéricos."), "warning")
            return
        if pin != pin2:
            mostrar_mensaje(self, tr("cfg.pins_mismatch_title", default="Los PINs no coinciden"), tr("cfg.pins_mismatch_msg", default="Los dos PINs introducidos no son iguales."), "warning")
            return

        if cambiar_password_usuario(id_u, pin):
            mostrar_mensaje(self, tr("cfg.pin_updated_title", default="PIN actualizado"), tr("cfg.pin_updated_msg", default="PIN de {nombre} actualizado correctamente.", nombre=nombre), "success")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.pin_update_err", default="No se pudo actualizar el PIN."), "error")

    # --- PESTAÑA 9: ASIGNAR REFERENCIA ---
    def _crear_page_referencia(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(0, 0, 0, 50)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Barra de Selección (Contorno neón). Guardamos las etiquetas traducidas
        # para comparar contra ellas (la lógica no depende del idioma).
        self._ref_lbl_tienda = tr("cfg.ref_store", default="TIENDA (T-)")
        self._ref_lbl_almacen = tr("cfg.ref_warehouse", default="ALMACÉN (A-)")
        self.combo_ref = _PerfilDropdown([self._ref_lbl_tienda, self._ref_lbl_almacen])
        self.combo_ref.setFixedWidth(450)
        self.combo_ref._btn.setFixedHeight(55)

        # Barra de Texto (Contorno neón)
        self.input_ref = QLineEdit()
        self.input_ref.setPlaceholderText(tr("cfg.ref_ph", default="NÚMERO O PALABRA DE REFERENCIA..."))
        self.input_ref.setFixedWidth(450)
        self.input_ref.setFixedHeight(55)
        self.input_ref.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {_CIAN}; border-radius: 12px; padding: 10px;
                color: white; background: #161B22; font-family: 'Segoe UI'; font-weight: bold; font-size: 16px;
            }}
        """)

        ly.addStretch()
        ly.addWidget(self.combo_ref, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(20)
        ly.addWidget(self.input_ref, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addStretch()

        # Botón Guardar Abajo Derecha
        btn_save = QPushButton(tr("cfg.save", default="GUARDAR"))
        btn_save.setFixedSize(180, 50)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton { background: #238636; color: #0E1117; border-radius: 12px; font-family: 'Segoe UI'; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background: #FFFFFF; color: #0E1117; }
        """)
        btn_save.clicked.connect(self._guardar_ref)

        h_bot = QHBoxLayout()
        h_bot.addStretch()
        h_bot.addWidget(btn_save)
        h_bot.setContentsMargins(0, 0, 40, 0)
        ly.addLayout(h_bot)

        # Al cambiar el tipo en el combo, cargar la referencia guardada para ese tipo
        self.combo_ref.currentTextChanged.connect(self._ref_on_combo_change)

        # Cargar valores guardados al inicializar
        self._ref_datos = obtener_referencias()
        self._ref_on_combo_change(self.combo_ref.currentText())

        return page

    def _ref_on_combo_change(self, text: str):
        """Rellena el input con la referencia guardada para el tipo seleccionado."""
        if not hasattr(self, "_ref_datos"):
            return
        if text == getattr(self, "_ref_lbl_almacen", "ALMACÉN (A-)"):
            self.input_ref.setText(self._ref_datos.get("ref_almacen", ""))
        else:
            self.input_ref.setText(self._ref_datos.get("ref_tienda", ""))

    def _guardar_ref(self):
        valor = self.input_ref.text().strip()
        if not valor:
            mostrar_mensaje(self, tr("cfg.ref_empty_title", default="Referencia vacía"), tr("cfg.ref_empty_msg", default="Escribe un número o palabra de referencia antes de guardar."), "warning")
            return
        text = self.combo_ref.currentText()
        tipo = "almacen" if text == getattr(self, "_ref_lbl_almacen", "ALMACÉN (A-)") else "tienda"
        ok = guardar_referencia(tipo, valor)
        if ok:
            # Actualizar caché local
            if not hasattr(self, "_ref_datos"):
                self._ref_datos = {}
            self._ref_datos[f"ref_{tipo}"] = valor
            _msg = tr("cfg.ref_saved_warehouse", default="Referencia de almacén guardada correctamente.") if tipo == "almacen" else tr("cfg.ref_saved_store", default="Referencia de tienda guardada correctamente.")
            mostrar_mensaje(self, tr("cfg.saved_title", default="Guardado"), _msg, "success")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.ref_save_err", default="No se pudo guardar la referencia. Revisa la conexión con la base de datos."), "error")

    def _crear_page_placeholder(self, nombre):
        page = QWidget()
        l = QVBoxLayout(page)
        l.addWidget(
            QLabel(
                f"MÓDULO: {nombre}",
                styleSheet="color: white; font-size: 24px; font-weight: bold;",
            ),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        return page

    def ejecutar_regreso(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()


# ── F3.0.2: horarios/turnos/ausencias extraídos a src/rrhh/gui/horarios.py ──
# Shim de compatibilidad (reexport): imports y referencias internas históricas
# intactos. Import diferido al final (las clases se usan en runtime).
from src.rrhh.gui.horarios import (  # noqa: E402,F401
    _HorarioComboBox,
    _TurnoCelda,
    _EmpNameEdit,
    _HorarioLoadingWidget,
    _AusenciaDialog,
    _HorarioTable,
    _HorarioSemana,
    _HorarioContainer,
)
