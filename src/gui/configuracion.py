import json
import math
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import (QByteArray, QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer,
                          pyqtSignal)
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
    QTransform,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,  # Añadir QTimeEdit y QCalendarWidget (Ya estaban)
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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
    QProgressBar,
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
    SmartMessageDialog,
    _blindar_tamano_fijo,
    mostrar_confirmacion,
    mostrar_mensaje,
)
from src.gui.components import EnterpriseTabs
from src.gui.components.completer_articulos import instalar_sugerencias_articulo
from src.gui.transiciones import StackedActual, abrir_dialogo_deslizante
from src.db.usuario import (
    actualizar_usuario,
    cambiar_password_usuario,
    crear_perfil,
    eliminar_usuario,
    listar_fichajes_empleado,
    listar_usuarios,
    meses_con_fichajes_empleado,
    obtener_fichaje_abierto,
    obtener_usuario,
    registrar_entrada,
    registrar_salida,
    sesion_global,
    validar_pin_fichaje,
    vincular_centro_trabajo,
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

# Icono de CAJA FUERTE (caja de caudales con dial de combinación) para el botón "APERTURA CAJA
# FUERTE". SVG propio → QIcon (mismo patrón que menu_principal.crear_icono), sin dependencias.
_SVG_CAJA_FUERTE = """
<svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
  <rect x="16" y="18" width="96" height="92" rx="9" fill="#C3C7CB" stroke="#23262B" stroke-width="5"/>
  <rect x="27" y="28" width="74" height="72" rx="5" fill="none" stroke="#23262B" stroke-width="3"/>
  <rect x="11" y="34" width="8" height="16" rx="2" fill="#9AA0A6" stroke="#23262B" stroke-width="2"/>
  <rect x="11" y="78" width="8" height="16" rx="2" fill="#9AA0A6" stroke="#23262B" stroke-width="2"/>
  <path d="M74 40 h18 a4 4 0 0 1 4 4 v18" fill="none" stroke="#23262B" stroke-width="6" stroke-linecap="round"/>
  <circle cx="55" cy="66" r="20" fill="#EDEFF1" stroke="#23262B" stroke-width="3"/>
  <circle cx="55" cy="66" r="7" fill="#15181C"/>
  <g stroke="#D23B3B" stroke-width="2">
    <line x1="55" y1="48" x2="55" y2="53"/><line x1="55" y1="79" x2="55" y2="84"/>
    <line x1="37" y1="66" x2="42" y2="66"/><line x1="68" y1="66" x2="73" y2="66"/>
  </g>
  <g fill="#8A9096">
    <circle cx="26" cy="28" r="2.6"/><circle cx="102" cy="28" r="2.6"/>
    <circle cx="26" cy="100" r="2.6"/><circle cx="102" cy="100" r="2.6"/>
  </g>
  <rect x="26" y="110" width="12" height="8" rx="2" fill="#9AA0A6" stroke="#23262B" stroke-width="2"/>
  <rect x="90" y="110" width="12" height="8" rx="2" fill="#9AA0A6" stroke="#23262B" stroke-width="2"/>
</svg>
"""


def _icono_svg(svg: str, size: int = 128) -> QIcon:
    """Renderiza un SVG a QIcon (transparente). Reutilizable para iconos de imagen en botones."""
    try:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        return QIcon()


def _icono_caja_fuerte() -> QIcon:
    """Icono del botón APERTURA CAJA FUERTE: usa el PNG del repo (assets/caja_fuerte.png) y,
    si no está disponible, cae al icono SVG propio."""
    try:
        from src.utils import recursos
        ruta = recursos.ruta_recurso("assets", "caja_fuerte.png")
        pm = QPixmap(ruta)
        if not pm.isNull():
            return QIcon(pm)
    except Exception:
        pass
    return _icono_svg(_SVG_CAJA_FUERTE)


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

    # Texto MOSTRADO para un código de perfil, cuando difiere del propio código (p. ej. "SUPERADMIN"
    # se ve como "Superadministrador") — `currentText()` sigue devolviendo el código real
    # ("SUPERADMIN"), que es lo que se guarda en `usuarios.perfil` y compara el resto de la app.
    _ETIQUETAS = {"SUPERADMIN": "SUPERADMINISTRADOR"}

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

    def _etiqueta(self, opcion):
        return self._ETIQUETAS.get(opcion, opcion)

    def _refresh_btn(self):
        self._btn.set_display_text(self._etiqueta(self._valor))

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
            btn = QPushButton(self._etiqueta(opcion))
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
            # Petición explícita: el billete SIEMPRE se muestra tumbado (horizontal), sea cual sea
            # la divisa — algunos assets (p. ej. CHF) vienen en vertical/cuadrado, así que si el
            # origen es más alto que ancho se rota 90° (mismo criterio ya usado en `tpv._BilleteButton`
            # para los botones de denominación de la ventana de cobro). Las monedas (circulares) no
            # necesitan este ajuste.
            if denom.get("tipo") == "billete" and pm.height() > pm.width():
                pm = pm.transformed(QTransform().rotate(90), Qt.TransformationMode.SmoothTransformation)
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


class _DialogoPantallaCompleta(QDialog):
    """Base para un QDialog que SIEMPRE se abre MAXIMIZADO de verdad — geometría explícita al
    ÁREA DE TRABAJO del monitor (`availableGeometry()`: la pantalla completa MENOS la barra de
    tareas, igual que cualquier ventana nativa maximizada — petición explícita, 2026-11-20, NO
    debe tapar la barra de tareas), SIN pasar por ningún estado de ventana
    (`showMaximized()`/`showFullScreen()`). El propio `card` de cada diálogo concreto ocupa TODO
    el área de este diálogo (sin tamaño fijo ni centrado) — así el contenido se ve y se comporta
    como una ventana de aplicación maximizada de verdad, no como una tarjeta pequeña flotando
    sobre un fondo oscuro aparte.

    Hallazgo real #1, 2026-11-20: combinar `showMaximized()`/`showFullScreen()` con geometría
    reafirmada a mano NO se sostiene — el propio LOG en vivo lo probaba:
    `maxSize=POINT(x=1366,y=728)`, el ÁREA DE TRABAJO del monitor, aunque se pidiera la pantalla
    física entera (1366×768). Esos métodos marcan un ESTADO de ventana y Windows aplica sus
    propias reglas de esa familia de estados (clamping al área de trabajo) sean cuales sean los
    intentos de `setGeometry()` posteriores. La solución: NO cambiar el estado de la ventana en
    absoluto — un `QDialog` frameless normal con `setGeometry()` explícito no está sujeto a esa
    regla (mismo criterio que `tpv._BuscarTicketDialog`, que ya funciona así). Se reafirma en TRES
    momentos (antes de `exec()`, en `showEvent()`, y diferido un ciclo de eventos después) porque
    la secuencia interna de `QDialog.show()` SÍ reajusta la ventana a su `sizeHint()` después de
    construirla — ese reajuste no está ligado a maximizar/fullscreen, así que sigue haciendo falta
    reafirmar la geometría, solo que ahora sin ningún cambio de estado. Mismo patrón de 3 pasos ya
    usado (y probado) en `circulares_gui._DialogoBase` para este mismo problema — la diferencia es
    que aquí nunca se llama a `showMaximized()`/`showFullScreen()`, solo `setGeometry()`.

    Se abre con `transiciones.abrir_dialogo_deslizante` (animación de entrada/salida, petición
    explícita) — compatible con esta reafirmación porque, igual que en `_DialogoBase`, el
    refuerzo de `exec()` solo reafirma una geometría que para entonces ya es correcta (el diálogo
    ya se ha revelado en su sitio final antes de que `abrir_dialogo_deslizante` llegue a llamar a
    `exec()`), no una que esté a medio animar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def _forzar_pantalla_completa(self):
        try:
            pantalla = self.screen() or QApplication.primaryScreen()
            if pantalla:
                self.setGeometry(pantalla.availableGeometry())
        except Exception:
            pass

    def exec(self):
        self._forzar_pantalla_completa()
        return super().exec()

    def showEvent(self, event):
        super().showEvent(event)
        self._forzar_pantalla_completa()
        QTimer.singleShot(0, self._forzar_pantalla_completa)

    def _tamano_card(self, pct_ancho: float, pct_alto: float, min_ancho=560, min_alto=0) -> tuple:
        """Tamaño de la tarjeta de contenido como PORCENTAJE de la pantalla disponible (petición
        explícita, 2026-11-20: con la ventana ya a pantalla completa de verdad, una tarjeta de
        tamaño fijo en píxeles se quedaba pequeña y desproporcionada en medio de todo ese espacio
        — aquí se calcula relativa al tamaño real de la pantalla, con un mínimo para no encogerse
        de más en monitores pequeños)."""
        try:
            pantalla = self.screen() or QApplication.primaryScreen()
            # `.geometry()` (pantalla física entera), NO `.availableGeometry()`: esta propia
            # ventana ya cubre también el área de la barra de tareas (ver `_forzar_pantalla_
            # completa`), así que el contenido puede aprovechar ESE espacio igualmente.
            geo = pantalla.geometry() if pantalla else None
        except Exception:
            geo = None
        if geo is None:
            return max(min_ancho, 900), max(min_alto, 650)
        return (max(min_ancho, int(geo.width() * pct_ancho)),
                max(min_alto, int(geo.height() * pct_alto)))

    def exec(self):
        self._forzar_pantalla_completa()
        return super().exec()

    def showEvent(self, event):
        super().showEvent(event)
        self._forzar_pantalla_completa()
        QTimer.singleShot(0, self._forzar_pantalla_completa)


class _PinEmpleadoDialog(QDialog):
    """Verifica el PIN de 4 dígitos de UN empleado CONCRETO (por id) — a diferencia de `_PinDialog`
    (rrhh.gui.empleados, verifica cualquier usuario dentro de un RANGO de perfiles, p. ej.
    "cualquier ADMINISTRADOR"), este exige que el PIN pertenezca EXACTAMENTE al empleado indicado
    (`db.usuario.validar_pin_de_usuario`, por id, no por rol). Petición explícita, 2026-11-20:
    cuando una caja registradora está asignada a un ÚNICO empleado no hay ningún paso de selección
    de perfil (a diferencia de una caja con varios empleados, donde elegir entre varios botones ya
    sirve de identificación mínima) — sin esto, abrir/cerrar esa caja no exigía NINGUNA
    verificación real de quién era de verdad el cajero. Mismo diseño visual (ámbar) que `_PinDialog`."""

    def __init__(self, id_empleado, nombre_empleado, motivo, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._id_empleado = id_empleado
        self._ok = False
        self._build(nombre_empleado, motivo)

    def _build(self, nombre_empleado, motivo):
        card = QFrame(self); card.setObjectName("pce")
        card.setStyleSheet("QFrame#pce{background:#0E1117;border:2px solid #E3B341;border-radius:18px;}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(32, 28, 32, 28); ly.setSpacing(14)

        lbl_t = QLabel("🔐  " + tr("cfg.pin_emp_title", default="VERIFICACIÓN DE PIN"))
        lbl_t.setStyleSheet("color:#E3B341;font-family:'Segoe UI';font-weight:900;font-size:14px;")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m = QLabel(tr("cfg.pin_emp_msg", default="Introduce el PIN de {nombre} para {motivo}.",
                          nombre=nombre_empleado, motivo=motivo))
        lbl_m.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
        lbl_m.setWordWrap(True)
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self._lbl_err.setWordWrap(True)
        ly.addWidget(self._lbl_err)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            "QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.verify", default="VERIFICAR")); bk.setFixedHeight(40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(
            "QPushButton{background:#0D1117;color:#E3B341;border:2px solid #E3B341;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#E3B341;color:#0D1117;}")
        bk.clicked.connect(self._verificar)
        self._pin_inp.returnPressed.connect(self._verificar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedSize(520, 300)
        self._pin_inp.setFocus()

    def _verificar(self):
        pin = self._pin_inp.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            self._lbl_err.setText(tr("cfg.pin_len_err", default="El PIN debe tener exactamente 4 dígitos."))
            return
        from src.db.usuario import validar_pin_de_usuario
        try:
            resp = validar_pin_de_usuario(self._id_empleado, pin)
        except Exception:
            resp = None
        if resp:
            self._ok = True
            self.accept()
            return
        self._pin_inp.clear(); self._pin_inp.setFocus()
        msg = tr("cfg.pin_wrong_auth", default="PIN incorrecto.")
        self._lbl_err.setText(msg)
        mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"), msg, "error")

    def verificado(self) -> bool:
        return self._ok


class _ConteoEfectivoDialog(_DialogoPantallaCompleta):
    """Modal de arqueo de efectivo con tabla de denominaciones y totales en tiempo real.
    La tabla es DINÁMICA según la divisa de empresa: imagen | valor | cantidad | total."""

    def __init__(self, titulo="ARQUEO DE EFECTIVO", fondo_esperado=None, parent=None):
        super().__init__(parent)
        self._total = 0.0
        self._fondo_esperado = fondo_esperado
        self._spins: list = []
        self._sub_items: list = []
        # Denominaciones de la divisa de empresa activa (dinámico): si el admin
        # cambia la divisa, el siguiente arqueo se construye con la nueva.
        self._denoms = divisas.denominaciones()
        self._build(titulo)
        # Petición explícita, 2026-11-16: TODAS las ventanas de recuento de monedas/billetes, sea
        # cual sea el flujo que las abra (apertura/cierre de caja registradora, cambio de cajero,
        # caja fuerte...), a pantalla completa — las 5 reutilizan esta MISMA clase (que ya hereda
        # de `_DialogoPantallaCompleta`), así que basta con heredar de ella una vez.

    @staticmethod
    def _btn_ss(bg, fg, border):
        return (f"QPushButton{{background:{bg};color:{fg};border:2px solid {border};"
                f"border-radius:10px;font-family:'Segoe UI';font-weight:900;"
                f"font-size:13px;padding:0 24px;}}"
                f"QPushButton:hover{{background:{fg};color:{bg};}}")

    def _build(self, titulo):
        # Fondo OPACO explícito del propio diálogo (hallazgo real, 2026-11-16: con
        # `WA_TranslucentBackground` retirado por `asegurar_pantalla_completa`, el fondo de la
        # ventana pasa a depender de esta hoja de estilos — selector con objectName, mismo
        # criterio ya probado en `tpv._BuscarTicketDialog`).
        self.setObjectName("dlg_conteo_efectivo")
        self.setStyleSheet("#dlg_conteo_efectivo{background:#0E1117;border:none;}")
        # Petición explícita, 2026-11-20: la ventana es ya una ventana maximizada de verdad — su
        # CONTENIDO debe llenarla igual que cualquier app maximizada, no una tarjeta pequeña
        # centrada sobre un fondo aparte. `card` ya no tiene tamaño fijo ni borde/radio propios
        # (nada que la distinga visualmente de "ser la ventana"); se reserva `_card_h` solo como
        # estimación inicial de la altura disponible para la tabla (ver más abajo).
        _card_w, self._card_h = self._tamano_card(0.78, 0.92, min_ancho=720, min_alto=640)
        card = QFrame(self)
        card.setObjectName("cc")
        card.setStyleSheet("QFrame#cc{background:#0E1117;border:none;}")
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
        # Petición explícita, 2026-11-16: el botón "CANCELAR" de abajo desaparece — su función
        # pasa a la X roja de la esquina superior derecha, mismo diseño que el resto de la app.
        hr.addSpacing(14)
        bx = QPushButton("✕")
        bx.setFixedSize(36, 36)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;border-radius:18px;"
            "padding:0;font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 36, 36)
        bx.clicked.connect(self.reject)
        hr.addWidget(bx)
        ly.addLayout(hr)

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
        # Altura inicial de la tabla relativa al tamaño ya calculado de la tarjeta (reserva ~230px
        # para cabecera/total/botonera) — `_apply_tbl_cover` (más abajo) la ajusta para encajar un
        # nº entero de filas sin dejar tira vacía, partiendo de ESTE tamaño en vez de uno fijo.
        tbl.setFixedHeight(max(300, self._card_h - 230))
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

        btn_vincular = QPushButton("⚖  " + tr("cfg.auto_count", default="RECUENTO AUTOMÁTICO"))
        btn_vincular.setFixedHeight(34)
        btn_vincular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_vincular.setEnabled(True)
        btn_vincular.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid {_BORDE};color:#8B949E;"
            f"border-radius:8px;font-family:'Segoe UI';font-weight:900;font-size:11px;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}"
        )
        btn_vincular.clicked.connect(self._recuento_automatico_click)

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

        # Petición explícita, 2026-11-16: "CONFIRMAR ARQUEO" → "CONTINUAR" en las 5 ventanas de
        # recuento que reutilizan esta clase (ver docstring de cabecera) — el resumen final con
        # cuadre/descuadre que se muestra a continuación (`_ResumenArqueoDialog`) es ahora el
        # paso que de verdad "confirma".
        bk = QPushButton("✔  " + tr("cfg.arqueo_continuar", default="CONTINUAR")); bk.setFixedSize(260, 44)
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
        br.addWidget(bk)
        ly.addLayout(br)

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

    def _recuento_automatico_click(self):
        """Botón "RECUENTO AUTOMÁTICO": intenta conectar con la báscula CONTADORA de monedas/
        billetes (`services/tpv/bascula_recuento`, que reutiliza pyserial igual que
        `scale_service` — no un cliente de hardware paralelo). Degrada honestamente con el
        diálogo propio de la app (`mostrar_mensaje` — nunca QMessageBox nativo, ver `tpv._msg`):
        sin báscula configurada -> aviso info; configurada pero sin respuesta -> aviso error;
        conectada -> se LEE el informe de recuento real por puerto serie (la báscula ya calculó
        las cantidades por denominación al pesarlas en el propio aparato) y, si la lectura falla
        o no trae ninguna denominación reconocible, se avisa con el mismo estilo de error en vez
        de transferir datos inventados."""
        from src.services.tpv.bascula_recuento import intentar_conectar, leer_recuento

        resultado = intentar_conectar()
        estado = resultado.get("estado")

        if estado == "no_configurada":
            mostrar_mensaje(
                self,
                tr("cfg.bascula_title", default="Báscula de recuento"),
                tr("cfg.bascula_no_conectada",
                   default="No hay ninguna báscula conectada. Por favor conecte la báscula "
                           "para poder iniciar el recuento automático."),
                "info",
            )
            return

        if estado == "error_conexion":
            mostrar_mensaje(
                self,
                tr("cfg.bascula_title", default="Báscula de recuento"),
                tr("cfg.bascula_error",
                   default="La báscula no se pudo conectar al sistema. Por favor, revise que "
                           "la báscula esté bien conectada."),
                "error",
            )
            return

        # estado == "conectada": se lee el informe de recuento REAL de la báscula (una vez que
        # el cajero ya ha pesado cada denominación en el propio aparato).
        lectura = leer_recuento(self._denoms)
        if lectura.get("estado") != "ok":
            mostrar_mensaje(
                self,
                tr("cfg.bascula_title", default="Báscula de recuento"),
                lectura.get("detalle") or tr(
                    "cfg.bascula_error_lectura",
                    default="No se pudo leer el recuento de la báscula."),
                "error",
            )
            return

        recuento = lectura["recuento"]
        resp = mostrar_mensaje(
            self,
            tr("cfg.bascula_title", default="Báscula de recuento"),
            tr("cfg.bascula_conectada",
               default="Báscula conectada correctamente. El recuento automático está listo "
                       "para transferirse a la tabla."),
            "success",
            botones=[("transferir", tr("cfg.bascula_transferir", default="Transferir recuento")),
                     "cancel"],
        )
        if resp == SmartMessageDialog.ROLE_TO_RESULT["transferir"]:
            self._aplicar_recuento_automatico(recuento)

    def _aplicar_recuento_automatico(self, recuento: dict):
        """Rellena las celdas CANTIDAD ya existentes de la tabla de arqueo con el recuento
        recibido de la báscula (por valor de denominación) — reutiliza los mismos `_QtyInput`
        de la tabla, sin construir una tabla paralela."""
        for valor, qty in self._spins:
            cantidad = int(recuento.get(valor, 0) or 0)
            qty._inp.setText(str(cantidad))


class _ResumenArqueoDialog(_DialogoPantallaCompleta):
    """Resumen final del recuento de monedas/billetes (petición explícita, 2026-11-16), mostrado
    al pulsar "CONTINUAR" en `_ConteoEfectivoDialog` — ANTES de aplicar de verdad el arqueo (apertura/
    cierre/cambio de cajero). Muestra el desglose contado, compara contra `fondo_esperado`
    (cuadra/descuadra) si se conoce, el nº de devoluciones del día si se pasa, y dos acciones:
    "VOLVER" (código propio `VOLVER` — el llamador debe reabrir el `_ConteoEfectivoDialog` original
    para editar, SIN perder lo ya contado) o el botón de continuar (pide una confirmación final
    antes de devolver `QDialog.DialogCode.Accepted`). `texto_continuar` permite fusionar esta
    confirmación con una acción posterior (p. ej. "GENERAR CIERRE DIARIO" en el cierre de caja
    fuerte, ver `ConfiguracionWindow._fn_cierre_fuerte`)."""

    VOLVER = 2  # Accepted=1 y Rejected=0 ya los reserva Qt

    def __init__(self, *, titulo, detalle, total, fondo_esperado=None, n_devoluciones=None,
                 texto_continuar=None, parent=None):
        super().__init__(parent)
        self._titulo = titulo
        self._detalle = detalle or []
        self._total = total
        self._fondo_esperado = fondo_esperado
        self._n_devoluciones = n_devoluciones
        self._texto_continuar = texto_continuar or tr("cfg.resumen_arqueo_continuar", default="CONTINUAR")
        self._build()

    def _build(self):
        from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon

        # Fondo OPACO explícito del propio diálogo (petición explícita, 2026-11-16, hallazgo real:
        # con `WA_TranslucentBackground` ya retirado por `_DialogoPantallaCompleta`, el fondo de
        # la ventana pasa a depender de esta hoja de estilos — selector con objectName, mayor
        # especificidad que el `QDialog{border:2px solid CIAN}` global, igual criterio ya probado
        # en `tpv._BuscarTicketDialog`).
        self.setObjectName("dlg_resumen_arqueo")
        self.setStyleSheet("#dlg_resumen_arqueo{background:#0E1117;border:none;}")
        card = QFrame(self); card.setObjectName("ra")
        # Petición explícita, 2026-11-20: la ventana es ya una ventana maximizada de verdad — sin
        # tamaño/borde propios en `card`, para que su contenido llene la ventana igual que
        # cualquier app maximizada, en vez de una tarjeta flotando sobre un fondo aparte.
        card.setStyleSheet("QFrame#ra{background:#0E1117;border:none;}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)

        ly = QVBoxLayout(card); ly.setContentsMargins(28, 22, 28, 22); ly.setSpacing(12)

        # Petición explícita, 2026-11-16: el botón "VOLVER" de abajo desaparece — su función (volver
        # a `_ConteoEfectivoDialog` para corregir el recuento) pasa a la X roja de la esquina
        # superior derecha, mismo diseño que el resto de ventanas a pantalla completa de la app.
        hdr = QHBoxLayout()
        lbl_t = QLabel(tr("cfg.resumen_arqueo_titulo", default="RESUMEN DEL RECUENTO"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;")
        hdr.addWidget(lbl_t)
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(36, 36)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;border-radius:18px;"
            "padding:0;font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bx.setProperty("sin_glow", True)
        # Blindaje de tamaño fijo (petición explícita: hover circular, no "píldora" — ver
        # `assets/estilo_global._blindar_tamano_fijo`, mismo bug ya corregido en el resto de
        # botones "✕" pequeños de diálogos frameless+translúcidos de la app).
        _blindar_tamano_fijo(bx, 36, 36)
        bx.clicked.connect(lambda: self.done(self.VOLVER))
        hdr.addWidget(bx)
        ly.addLayout(hdr)

        lbl_sub = QLabel(self._titulo)
        # Petición explícita: +1pt (12→13px) — este texto es el título pasado por el llamador
        # (p. ej. "CIERRE CAJA-01 — ARQUEO FINAL").
        lbl_sub.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:bold;font-size:13px;")
        ly.addWidget(lbl_sub)

        tbl = QTableWidget(len(self._detalle), 3)
        tbl.setHorizontalHeaderLabels([
            tr("cfg.col_denominacion", default="DENOMINACIÓN"),
            tr("cfg.col_qty", default="CANTIDAD"),
            tr("cfg.col_total", default="TOTAL"),
        ])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(1, 110); tbl.setColumnWidth(2, 130)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setFrameShape(QFrame.Shape.NoFrame)
        tbl.setAlternatingRowColors(True)
        # Petición explícita: mismo diseño EXACTO que el resto de tablas de la app (contorno neón,
        # cabeceras con hover swap, esquinas redondeadas) — antes llevaba una hoja de estilos
        # propia distinta del resto. Petición explícita posterior, 2026-11-20: la scrollbar debe
        # verse EXACTAMENTE igual que el resto de scrollbars genéricas de la app
        # (`assets/estilo_global.QSS_SCROLLBARS` — turquesa sólido, extremos redondeados), solo
        # un poco más gruesa — se REDEFINE por completo (groove + handle + add/sub-line/page), en
        # vez de solo parchear el `::handle` encima de `_ss_tabla_neon()` (que dejaba el grosor y
        # el margen asimétrico de la "groove" de esa función, pensados para su turquesa
        # translúcido, no para este). El margen de verdad redondeado va en el PROPIO handle, no
        # solo en la "groove" (si el handle llega a tocar sus bordes — barra corta, recuento con
        # pocas filas, caso típico de esta tabla — Qt lo pinta cuadrado; mismo criterio ya
        # documentado en `foundation.tokens.qss_scrollbar`). Se añade DESPUÉS de `_ss_tabla_neon()`
        # para que gane por cascada, sin tocar esa función compartida (usada tal cual en el resto
        # de la app).
        tbl.setStyleSheet(_ss_tabla_neon() + (
            f"QScrollBar:vertical{{background:transparent;width:10px;margin:0px;}}"
            f"QScrollBar::handle:vertical{{background:{_CIAN};border-radius:5px;min-height:26px;margin:2px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;background:none;border:none;}}"
            f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:none;}}"
            f"QScrollBar:horizontal{{background:transparent;height:10px;margin:0px;}}"
            f"QScrollBar::handle:horizontal{{background:{_CIAN};border-radius:5px;min-width:26px;margin:2px;}}"
            f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;background:none;border:none;}}"
            f"QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{{background:none;}}"
        ))
        self._round_tbl = _RoundTableCorners(tbl, radius=10)
        for row, d in enumerate(self._detalle):
            tbl.setItem(row, 0, QTableWidgetItem(str(d.get("denominacion", ""))))
            it_q = QTableWidgetItem(str(d.get("cantidad", 0)))
            it_q.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(row, 1, it_q)
            it_s = QTableWidgetItem(divisas.formatear(d.get("subtotal", 0)))
            it_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(row, 2, it_s)
        tbl.setFixedHeight(min(260, 40 + 32 * max(1, len(self._detalle))))
        if not self._detalle:
            tbl.setVisible(False)
        ly.addWidget(tbl)

        tf = QFrame()
        # Petición explícita, 2026-11-16: sin el contorno turquesa de este panel (Total contado/
        # Esperado/Cuadra/Devoluciones hoy, incluidos los dos importes).
        tf.setStyleSheet("QFrame{background:#161B22;border:none;border-radius:12px;}")
        t_ly = QVBoxLayout(tf); t_ly.setContentsMargins(16, 10, 16, 10); t_ly.setSpacing(4)

        fila_total = QHBoxLayout()
        fila_total.addWidget(QLabel(tr("cfg.resumen_arqueo_contado", default="TOTAL CONTADO:"),
                                    styleSheet="color:#6E7681;font-weight:900;font-size:13px;"))
        fila_total.addStretch()
        fila_total.addWidget(QLabel(divisas.formatear(self._total),
                                    styleSheet=f"color:{_CIAN};font-weight:900;font-size:20px;"))
        t_ly.addLayout(fila_total)

        if self._fondo_esperado is not None and self._fondo_esperado > 0:
            diff = round(self._total - self._fondo_esperado, 2)
            cuadra = abs(diff) < 0.005
            fila_esp = QHBoxLayout()
            fila_esp.addWidget(QLabel(tr("cfg.resumen_arqueo_esperado", default="Esperado:"),
                                      styleSheet="color:#6E7681;font-size:12px;"))
            fila_esp.addStretch()
            fila_esp.addWidget(QLabel(divisas.formatear(self._fondo_esperado),
                                      styleSheet="color:#8B949E;font-size:12px;"))
            t_ly.addLayout(fila_esp)
            color_cuadre = "#3FB950" if cuadra else "#F85149"
            texto_cuadre = (tr("cfg.resumen_arqueo_cuadra", default="✓ CUADRA")
                           if cuadra else
                           tr("cfg.resumen_arqueo_descuadra", default="⚠ DESCUADRE: {x}",
                              x=f"{'+' if diff > 0 else ''}{divisas.formatear(diff)}"))
            lbl_cuadre = QLabel(texto_cuadre)
            lbl_cuadre.setStyleSheet(f"color:{color_cuadre};font-weight:900;font-size:14px;")
            t_ly.addWidget(lbl_cuadre)

        if self._n_devoluciones is not None:
            lbl_dev = QLabel(tr("cfg.resumen_arqueo_devoluciones",
                                default="Devoluciones hoy: {n}", n=self._n_devoluciones))
            # Petición explícita: +1pt (12→13px).
            lbl_dev.setStyleSheet("color:#8B949E;font-size:13px;font-weight:bold;margin-top:4px;")
            t_ly.addWidget(lbl_dev)

        ly.addWidget(tf)

        br = QHBoxLayout(); br.setSpacing(8); br.addStretch()
        bc = QPushButton("✔  " + self._texto_continuar); bc.setFixedSize(280, 44)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:10px;font-family:'Segoe UI';font-weight:900;font-size:13px;padding:0 10px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        bc.clicked.connect(self._continuar)
        br.addWidget(bc)
        ly.addLayout(br)

    def _continuar(self):
        if not mostrar_confirmacion(
                self, tr("cfg.resumen_arqueo_confirm_title", default="Confirmar"),
                tr("cfg.resumen_arqueo_confirm_msg",
                   default="¿Confirmas que estos datos son correctos y quieres continuar?")):
            return
        self.done(QDialog.DialogCode.Accepted)


from src.gui.selector_perfil import _PerfilBoton as _PerfilBotonBase  # noqa: E402


class _PerfilBotonCaja(_PerfilBotonBase):
    """`selector_perfil._PerfilBoton` (mismo icono de persona + hover swap) + un estado MARCADO
    persistente — necesario aquí (checkable) pero no en el selector de perfil original (ahí un
    clic navega y el botón desaparece, nunca necesita "seguir marcado"). Sin este añadido, al
    sacar el ratón de un botón ya marcado, `_PerfilBoton.leaveEvent` restauraría el icono turquesa
    de reposo sobre el propio fondo turquesa del estado `:checked` — invisible."""

    HOJA_ESTILOS = (
        f"QToolButton{{background:#161B22;color:#FFFFFF;border:2px solid {_BORDE};"
        f"border-radius:16px;font-family:'Segoe UI';font-size:13px;font-weight:700;padding:10px 6px;}}"
        f"QToolButton:hover{{background:{_CIAN};color:#0E1117;border:2px solid {_CIAN};}}"
        f"QToolButton:checked{{background:{_CIAN};color:#0E1117;border:2px solid {_CIAN};}}"
        f"QToolButton:pressed{{background:#00C79A;color:#0E1117;}}"
    )

    def enterEvent(self, e):
        if not self.isChecked():
            super().enterEvent(e)

    def leaveEvent(self, e):
        if not self.isChecked():
            super().leaveEvent(e)


class _SeleccionarEmpleadosCajaDialog(_DialogoPantallaCompleta):
    """Selección de empleado(s) del centro mediante BOTONES DE PERFIL (mismo lenguaje visual que
    el selector de perfil del login del TPV) — SIN PIN. Petición explícita, 2026-11-16: sustituye
    tanto al desplegable+PIN de `_IdentificacionEmpleadoDialog` como al checklist de
    `_EmpleadosAutorizadosCajaDialog` (retirada) para ASIGNAR (`multiple=True`, apertura de caja:
    cualquier número de perfiles puede quedar marcado a la vez, con atajo "TODOS") y para
    DESASIGNAR (`multiple=False`, cierre de caja: pulsar un perfil lo deja marcado en exclusiva —
    un único empleado, el que está cerrando) una caja registradora. Ninguno de los dos casos pide
    ya el PIN de 4 dígitos del empleado — la autorización real de acceso sigue viviendo en
    `tpv._caja_pertenece`/`ConfiguracionWindow._caja_autoriza` contra la lista aquí elegida."""

    def __init__(self, titulo, subtitulo, multiple: bool, parent=None, empleados=None):
        super().__init__(parent)
        self._multiple = multiple
        # Petición explícita, 2026-11-16: `empleados` restringe la lista a un conjunto fijo (p. ej.
        # cierre de caja — solo los empleados YA autorizados en esa caja, no todo el centro). None
        # (por defecto, apertura) = todos los empleados del centro, como siempre.
        self._empleados_fijos = empleados
        self._botones: dict = {}
        self._nombres: dict = {}
        self._seleccionados: set = set()
        self._build(titulo, subtitulo)

    def _build(self, titulo, subtitulo):
        from PyQt6.QtCore import QSize
        from src.gui.selector_perfil import _icono_persona

        # Fondo OPACO explícito del propio diálogo (petición explícita, 2026-11-16, hallazgo real:
        # con `WA_TranslucentBackground` ya retirado por `asegurar_pantalla_completa`, el fondo de
        # la ventana pasa a depender de esta hoja de estilos — selector con objectName, mayor
        # especificidad que el `QDialog{border:2px solid CIAN}` global, igual criterio ya probado
        # en `tpv._BuscarTicketDialog`).
        self.setObjectName("dlg_sel_empleados_caja")
        self.setStyleSheet("#dlg_sel_empleados_caja{background:#0E1117;border:none;}")
        card = QFrame(self); card.setObjectName("sec")
        # Petición explícita, 2026-11-20: la ventana es ya una ventana maximizada de verdad — sin
        # tamaño/borde propios en `card`, para que su contenido llene la ventana igual que
        # cualquier app maximizada, en vez de una tarjeta flotando sobre un fondo aparte.
        card.setStyleSheet("QFrame#sec{background:#0E1117;border:none;}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(28, 22, 28, 22); ly.setSpacing(12)

        # Petición explícita: el botón "CANCELAR" de abajo desaparece — su función pasa a la X
        # roja de la esquina superior derecha, mismo diseño que el resto de la app.
        hdr = QHBoxLayout()
        lbl = QLabel(titulo)
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:15px;font-family:'Segoe UI';")
        hdr.addWidget(lbl)
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(36, 36)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;border-radius:18px;"
            "padding:0;font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 36, 36)
        bx.clicked.connect(self.reject)
        hdr.addWidget(bx)
        ly.addLayout(hdr)

        if subtitulo:
            sub = QLabel(subtitulo)
            sub.setWordWrap(True)
            sub.setStyleSheet("color:#8B949E;font-size:12px;font-family:'Segoe UI';")
            ly.addWidget(sub)

        if self._multiple:
            chk_todos = _NeonCheckBox(
                tr("cfg.autorizados_caja_todos", default="TODOS los empleados del centro"))
            chk_todos.toggled.connect(self._marcar_todos)
            ly.addWidget(chk_todos)
            self._chk_todos = chk_todos

        empleados = (self._empleados_fijos if self._empleados_fijos is not None
                    else self._empleados_del_centro())

        # Petición explícita, 2026-11-16: MISMO diseño que los botones de perfil de "Selecciona tu
        # perfil" (`selector_perfil._PerfilBoton`/`_icono_persona`) — tarjeta cuadrada con icono de
        # persona + nombre debajo, en vez de la fila de texto plana de antes. `_PerfilBotonCaja`
        # añade el estado MARCADO persistente (checkable) que ese botón original no necesitaba.
        icono_normal = _icono_persona(_CIAN)
        icono_hover = _icono_persona("#0E1117")
        # Petición explícita, 2026-11-20: con la ventana ocupando de verdad todo el ancho (ya no
        # hay una "tarjeta" de ancho fijo), el nº de columnas se calcula a partir del ancho real
        # disponible (botón 150px + 12px de separación) en vez de un tope fijo de 5 — aprovecha
        # el ancho real del monitor del usuario, sea cual sea.
        _ancho_disp = self._tamano_card(1.0, 0.0, min_ancho=480)[0] - 2 * 28 - 2 * 14 - 4
        ncols = min(max(1, len(empleados)), max(1, (_ancho_disp + 12) // (150 + 12)))

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFixedHeight(min(520, 40 + 162 * -(-len(empleados) // ncols)))
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:#161B22;border:2px solid {_BORDE};border-radius:10px;}}")
        host = QWidget(); host.setStyleSheet("background:transparent;")
        grid = QGridLayout(host); grid.setContentsMargins(14, 14, 14, 14); grid.setSpacing(12)
        for idx, e in enumerate(empleados):
            eid, nombre = e.get("id"), (e.get("nombre") or "").strip()
            if not nombre or eid is None:
                continue
            btn = _PerfilBotonCaja(icono_normal, icono_hover)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(56, 56))
            btn.setText(nombre.upper())
            btn.setFixedSize(150, 150)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_PerfilBotonCaja.HOJA_ESTILOS)
            btn.clicked.connect(lambda _c=False, i=eid: self._alternar(i))
            grid.addWidget(btn, idx // ncols, idx % ncols)
            self._botones[eid] = btn
            self._nombres[eid] = nombre
        scroll.setWidget(host)
        ly.addWidget(scroll)
        self._refrescar_estilo()

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:#F85149;font-size:11px;font-family:'Segoe UI';")
        ly.addWidget(self._lbl_err)

        br = QHBoxLayout(); br.setSpacing(16); br.addStretch()
        bk = QPushButton(tr("cfg.arqueo_continuar", default="CONTINUAR")); bk.setFixedHeight(44)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(_ConteoEfectivoDialog._btn_ss("#0D1117", _CIAN, _CIAN))
        bk.clicked.connect(self._confirmar)
        br.addWidget(bk)
        ly.addLayout(br)

    def _empleados_del_centro(self) -> list:
        # Mismo criterio de resolución (+ fallback) que `tpv._LoginTPVDialog._cargar_empleados_centro`
        # (hallazgo real, 2026-11-16: `usuarios.centro_codigo` casi nunca está relleno de verdad).
        try:
            from src.db import centros as centros_db
            from src.db.empresa import empresa_actual_id, tienda_actual_id
            from src.db.usuario import listar_usuarios_empresa
            id_empresa = empresa_actual_id()
            id_tienda = tienda_actual_id()
            codigo_centro = None
            if id_tienda is not None:
                for c in centros_db.listar_centros(id_empresa):
                    if c.get("id_tienda") == id_tienda:
                        codigo_centro = c.get("codigo_centro")
                        break
            empleados = (listar_usuarios_empresa(id_empresa, centro_codigo=codigo_centro)
                        if codigo_centro else [])
            return empleados or listar_usuarios_empresa(id_empresa)
        except Exception:
            return []

    def _alternar(self, eid):
        if self._multiple:
            if eid in self._seleccionados:
                self._seleccionados.discard(eid)
            else:
                self._seleccionados.add(eid)
        else:
            self._seleccionados = {eid}
        self._refrescar_estilo()
        self._lbl_err.setText("")

    def _marcar_todos(self, activo):
        self._seleccionados = set(self._botones.keys()) if activo else set()
        self._refrescar_estilo()

    def _refrescar_estilo(self):
        """QSS (`QToolButton:checked`) ya pinta fondo/borde del estado marcado — aquí solo se fija
        `setChecked` (dispara ese estado) y se fuerza el icono (turquesa↔oscuro), que la hoja de
        estilos no puede tocar por sí sola."""
        for eid, btn in self._botones.items():
            marcado = eid in self._seleccionados
            btn.setChecked(marcado)
            btn.setIcon(btn._ic_hover if marcado else btn._ic_normal)

    def _confirmar(self):
        if not self._seleccionados:
            self._lbl_err.setText(
                tr("cfg.select_emp_err", default="Selecciona al menos un empleado."))
            return
        self.accept()

    def get_seleccionados(self) -> list:
        """[{id, nombre}] de todos los perfiles marcados, en el orden en que aparecen en la lista."""
        return [{"id": eid, "nombre": self._nombres[eid]} for eid in self._botones
                if eid in self._seleccionados]

    # Compatibilidad con el uso single-select (cierre de caja, antes `_IdentificacionEmpleadoDialog`).
    def get_empleado_id(self):
        sel = self.get_seleccionados()
        return sel[0]["id"] if sel else None

    def get_empleado_nombre(self):
        sel = self.get_seleccionados()
        return sel[0]["nombre"] if sel else ""


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

        self._btn_ok = QPushButton(tr("cfg.continue", default="Continuar")); self._btn_ok.setFixedHeight(40)
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


class _ConfirmarPerfilEmpleadoDialog(QDialog):
    """Pide el código de 6 dígitos enviado al email del nuevo empleado antes de crear su perfil
    (`services.seguridad.confirmacion_perfil_empleado`). Reintentos/caducidad los valida el
    propio servicio; este diálogo solo pide el código y muestra el motivo de error tal cual."""

    def __init__(self, id_confirmacion: int, email: str, parent=None):
        super().__init__(parent)
        self._id_confirmacion = id_confirmacion
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build(email)

    def _build(self, email):
        card = QFrame(self); card.setObjectName("md")
        card.setStyleSheet(f"QFrame#md{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(12)

        lbl_h = QLabel(tr("cfg.confirm_perfil_titulo", default="Confirmar nuevo perfil"))
        lbl_h.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;")
        ly.addWidget(lbl_h)

        lbl_sub = QLabel(tr("cfg.confirm_perfil_sub",
                            default="Hemos enviado un código de 6 dígitos a {email}. "
                                    "Pídeselo al empleado e introdúcelo aquí.", email=email))
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;")
        ly.addWidget(lbl_sub)

        self._input = QLineEdit()
        self._input.setMaxLength(6)
        self._input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input.setPlaceholderText(tr("cfg.confirm_perfil_ph", default="CÓDIGO DE 6 DÍGITOS"))
        self._input.setStyleSheet(f"""
            QLineEdit{{background:#161B22;color:white;border:2px solid {_BORDE};border-radius:10px;
                      padding:12px;font-family:'Segoe UI';font-size:20px;font-weight:900;
                      letter-spacing:6px;}}
            QLineEdit:focus{{border-color:{_CIAN};}}
        """)
        self._input.returnPressed.connect(self._confirmar)
        ly.addWidget(self._input)

        self._lbl_error = QLabel("")
        self._lbl_error.setWordWrap(True)
        self._lbl_error.setStyleSheet("color:#F85149;font-family:'Segoe UI';font-size:11px;font-weight:bold;")
        ly.addWidget(self._lbl_error)

        fila_reenvio = QHBoxLayout()
        btn_reenviar = QPushButton(tr("cfg.confirm_perfil_reenviar", default="Reenviar código"))
        btn_reenviar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reenviar.setFlat(True)
        btn_reenviar.setStyleSheet(f"QPushButton{{color:{_CIAN};border:none;background:transparent;"
                                   f"font-family:'Segoe UI';font-size:11px;text-decoration:underline;}}")
        btn_reenviar.clicked.connect(self._reenviar)
        fila_reenvio.addWidget(btn_reenviar)
        fila_reenvio.addStretch(1)
        ly.addLayout(fila_reenvio)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("cfg.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
                        "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
                        "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        self._btn_ok = QPushButton(tr("cfg.confirm_perfil_confirmar", default="CONFIRMAR"))
        self._btn_ok.setFixedHeight(40); self._btn_ok.setMinimumWidth(130)
        self._btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ok.setStyleSheet(
            "QPushButton{background:#3FB950;color:#0D1117;border:2px solid #3FB950;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#FFFFFF;color:#0D1117;border:2px solid #FFFFFF;}")
        self._btn_ok.clicked.connect(self._confirmar)
        br.addWidget(bc); br.addStretch(1); br.addWidget(self._btn_ok)
        ly.addLayout(br)
        self.setFixedSize(420, 300)

    def _confirmar(self):
        codigo = self._input.text().strip()
        if len(codigo) != 6 or not codigo.isdigit():
            self._lbl_error.setText(tr("cfg.confirm_perfil_formato",
                                       default="Introduce los 6 dígitos del código."))
            return
        from src.services.seguridad import confirmacion_perfil_empleado as _conf
        res = _conf.confirmar(self._id_confirmacion, codigo)
        if res.get("ok"):
            self.accept()
        else:
            self._lbl_error.setText(res.get("motivo") or tr("cfg.confirm_perfil_error",
                                                             default="Código incorrecto."))
            self._input.selectAll()

    def _reenviar(self):
        from src.services.seguridad import confirmacion_perfil_empleado as _conf
        res = _conf.reenviar(self._id_confirmacion)
        self._lbl_error.setStyleSheet(
            f"color:{'#3FB950' if res.get('ok') else '#F85149'};font-family:'Segoe UI';"
            "font-size:11px;font-weight:bold;")
        self._lbl_error.setText(res.get("motivo") or "")


class _SeleccionarCajaAperturaDialog(QDialog):
    """Selección de CUÁL de las {N_CAJAS_MAX} cajas registradoras abrir (petición explícita,
    2026-11-16) — sustituye la numeración incremental automática (CAJA-01, CAJA-02…), que podía
    intentar reabrir una caja YA ACTIVA si se cerraba una que no fuera la última (hallazgo real:
    con CAJA-01 y CAJA-02 abiertas, cerrar CAJA-01 y pedir abrir otra volvía a calcular "CAJA-02"
    — la que seguía abierta — en vez de una libre). Las cajas YA ABIERTAS se EXCLUYEN aquí por
    completo de la lista: bajo ningún concepto se ofrece como opción una que ya esté activa. Cada
    opción muestra el último fondo con el que se cerró esa caja (`cajas_activas`/
    `ultimos_cierres`), o "sin fondos registrados" si nunca se ha usado."""

    N_CAJAS_MAX = 20

    def __init__(self, ultimos_cierres: dict, ids_abiertas: set, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._caja_id = None
        self._build(ultimos_cierres or {}, ids_abiertas or set())

    def _build(self, ultimos_cierres: dict, ids_abiertas: set):
        card = QFrame(self); card.setObjectName("sca")
        card.setStyleSheet(f"QFrame#sca{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(14)

        lbl_t = QLabel(tr("cfg.select_caja_apertura_title", default="¿QUÉ CAJA REGISTRADORA QUIERES ABRIR?"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:14px;")
        lbl_t.setWordWrap(True)
        ly.addWidget(lbl_t)

        self._combo = QComboBox()
        self._combo.setFixedHeight(44)
        self._combo.setStyleSheet(
            f"QComboBox{{background:#161B22;color:white;border:2px solid {_CIAN};"
            f"border-radius:10px;padding:8px 14px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:#E6EDF3;border:2px solid {_CIAN};"
            f"border-radius:10px;selection-background-color:{_CIAN};selection-color:#0D1117;outline:none;}}"
            f"QComboBox QAbstractItemView::item{{min-height:34px;padding:0 14px;}}")
        for n in range(1, self.N_CAJAS_MAX + 1):
            cid = f"CAJA-{n:02d}"
            if cid in ids_abiertas:
                continue
            fondo = ultimos_cierres.get(cid)
            etiqueta = (tr("cfg.caja_fondo_conocido", default="{id}  (Último fondo: {x})",
                           id=cid, x=divisas.formatear(fondo))
                       if fondo is not None else
                       tr("cfg.caja_sin_fondos", default="{id}  (Sin fondos registrados)", id=cid))
            self._combo.addItem(etiqueta, cid)
        ly.addWidget(self._combo)

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:#F85149;font-size:11px;font-family:'Segoe UI';")
        self._lbl_err.setWordWrap(True)
        ly.addWidget(self._lbl_err)
        if self._combo.count() == 0:
            self._lbl_err.setText(
                tr("cfg.todas_cajas_abiertas",
                   default="Las {n} cajas registradoras ya están abiertas.", n=self.N_CAJAS_MAX))
            self._combo.setEnabled(False)

        br = QHBoxLayout(); br.setSpacing(16)
        bc = QPushButton(tr("common.cancel", default="CANCELAR")); bc.setFixedHeight(40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(
            "QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
            "border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bc.clicked.connect(self.reject)
        bk = QPushButton(tr("cfg.arqueo_continuar", default="CONTINUAR")); bk.setFixedHeight(40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;padding:0 20px;font-family:'Segoe UI';font-weight:900;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}")
        bk.clicked.connect(self._confirmar)
        br.addWidget(bc); br.addWidget(bk)
        ly.addLayout(br)
        self.setFixedWidth(460)

    def _confirmar(self):
        cid = self._combo.currentData()
        if not cid:
            return
        self._caja_id = cid
        self.accept()

    def get_caja_id(self):
        return self._caja_id


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
        try:
            # Verificación canónica Argon2id (dual SHA-256 legado + rehash); sin igualdad en SQL.
            from src.db import usuario as _usuario
            _resp = _usuario.validar_pin_de_usuario(uid, pin)
            if not _resp:
                _msg = tr("cfg.pin_wrong_emp", default="PIN incorrecto para el empleado seleccionado.")
                self._lbl_error.setText(_msg)
                mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"), _msg, "error")
                self._pin_mov.clear(); self._pin_mov.setFocus(); return
            _empleado_nombre = _resp.get("nombre")
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

from src.rrhh.documents.forms_rrhh import WizardFormsRRHHMixin  # noqa: E402


class _WizardDocumentoFiscal(WizardFormsRRHHMixin, QDialog):
    """Asistente paso a paso para generar documentos laborales y fiscales."""

    DOCS = {
        # ── LABORAL ───────────────────────────────────────────────────────────
        "CONTRATO":       ("📄  CONTRATO LABORAL",    ["INDEFINIDO", "TEMPORAL", "FIJO DISCONTINUO", "PARCIAL", "PRÁCTICAS", "SUSTITUCIÓN"]),
        "NÓMINA":         ("📊  NÓMINA MENSUAL",       []),
        "ALTA":           ("✅  ALTA LABORAL",         []),
        "BAJA":           ("❌  BAJA LABORAL",         ["VOLUNTARIA", "FIN CONTRATO", "DESPIDO", "JUBILACIÓN", "INCAPACIDAD", "FALLECIMIENTO"]),
        "CERTIFICADO":    ("🏢  CERTIFICADO EMPRESA",  ["VIDA LABORAL", "COTIZACIÓN", "EMPRESA"]),
        "CERT LABORAL":   ("📃  CERTIFICADO LABORAL",  ["GENERAL", "INGRESOS", "ANTIGÜEDAD", "FUNCIONES", "JORNADA", "VACACIONES"]),
        "CARTA DESPIDO":  ("📮  CARTA DE DESPIDO",     ["DISCIPLINARIO", "OBJETIVO", "IMPROCEDENTE", "FIN CONTRATO", "BAJA VOLUNTARIA", "COLECTIVO", "PERÍODO DE PRUEBA"]),
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

    def __init__(self, tipo_inicial=None, parent=None, subtipo_inicial=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tipo = tipo_inicial
        self._subtipo_inicial = subtipo_inicial   # preselección de subtipo (p. ej. periodo de prueba)
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
            # 2) Tiendas + 3) Almacenes (cliente fino: capa de datos, sin SQL directo en la GUI).
            try:
                from src.db.tiendas import listar_tiendas
                for t in listar_tiendas(eid):
                    nom = t.get("nombre") or ""; cod = t.get("codigo_tienda") or ""
                    if nom:
                        cb.addItem("🏪  " + nom + (f" ({cod})" if cod else ""),
                                   {"id_centro": None, "nombre": nom, "codigo": cod, "fuente": "tienda"})
            except Exception:
                pass
            try:
                from src.db.stock_almacen import listar_almacenes
                for a in listar_almacenes(eid):
                    nom = a.get("nombre") or ""; cod = a.get("codigo_almacen") or ""
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
            "QPushButton{background:transparent;color:#F85149;border:none;"
            "border-radius:11px;font-family:'Segoe UI';font-weight:900;font-size:11px;padding:0px;}"
            "QPushButton:hover{background:#F85149;color:#0D1117;}"
        )
        btn_x.setProperty("sin_glow", True)
        _blindar_tamano_fijo(btn_x, 22, 22)
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
        # CONTRATO anexos/políticas/PRL (petición explícita): se guardan las etiquetas marcadas,
        # para renderizarlas dentro del PDF y para dar de alta cada una como documento firmable.
        if hasattr(self, "_checks_anexos"):
            self._datos["anexos_firmables"] = [
                t for t, cb in self._checks_anexos if cb.isChecked()
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
        bs = self._nav_btn("✔  " + tr("cfg.gen_doc_btn", default="Generar documento"))
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
            from src.utils import plataforma
            bo.clicked.connect(lambda: plataforma.abrir_archivo(_ruta))
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
            anexos_firmables   = self._datos.get("anexos_firmables", [])
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
            def _pdf_resumen_fiscal():
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


            from src.rrhh.documents.render import (  # noqa: E402
                render_contrato, render_nomina, render_carta_despido,
                render_certificado, render_alta_baja, render_finiquito, render_generico,
                render_cert_laboral, render_vacaciones, render_libro_ingresos,
                render_libro_gastos, render_informe_auditoria,
            )
            ctx = {**globals(), **locals()}   # scope auto-capturado (G+L) para el render RRHH
            _pdf_dispatch = {
                "CONTRATO": render_contrato,
                "NÓMINA": render_nomina,
                "ALTA": render_alta_baja,
                "BAJA": render_alta_baja,
                "CERTIFICADO": render_certificado,
                "CERT LABORAL": render_cert_laboral,
                "CARTA DESPIDO": render_carta_despido,
                "FINIQUITO": render_finiquito,
                "VACACIONES": render_vacaciones,
                "RESUMEN FISCAL": lambda _ctx: _pdf_resumen_fiscal(),
                "LIBRO INGRESOS": render_libro_ingresos,
                "LIBRO GASTOS": render_libro_gastos,
                "INFORME AUDIT": render_informe_auditoria,
            }
            _pdf_dispatch.get(self._tipo, render_generico)(ctx)
            # ── Observaciones generales ───────────────────────────────────────
            if obs and self._tipo not in ("CARTA DESPIDO", "CERTIFICADO", "ALTA", "BAJA",
                                          "FINIQUITO", "RESUMEN FISCAL", "CONTRATO",
                                          "LIBRO INGRESOS", "LIBRO GASTOS", "INFORME AUDIT"):
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
            # "Repositorio cifrado" (petición explícita) — SOLO nóminas/certificados (no el resto
            # de tipos fiscales que también pasan por este wizard legado, p. ej. libros de
            # ingresos/gastos, que no son documentos de "Histórico de Nóminas y Certificados").
            if self._tipo in ("NÓMINA", "CERTIFICADO", "CERT LABORAL"):
                from src.utils import cripto
                cripto.cifrar_archivo_en_disco(ruta)
            self._pdf_ruta = ruta

            # F4.2.1: traza en el expediente laboral (best-effort, post-PDF). Nunca
            # afecta a la generación: si falla, el PDF queda intacto y se registra.
            try:
                from src.rrhh.persistencia import registrar_generacion
                registrar_generacion(self._tipo, self._datos, ruta)
            except Exception:
                LOG_DOCUMENTOS.exception("Persistencia de expediente RRHH (no crítica)")

            # Anexos/políticas/PRL del contrato como documentos FIRMABLES independientes
            # (petición explícita — "Expediente y Firma Digital"): cada anexo marcado queda
            # pendiente de aceptación/firma en el portal del empleado, apuntando al MISMO PDF del
            # contrato (el contenido ya se renderizó dentro de él, ver render_contrato.py) — no se
            # genera un fichero por anexo. Best-effort: nunca afecta al contrato ya generado.
            if self._tipo == "CONTRATO" and self._datos.get("anexos_firmables"):
                try:
                    from src.rrhh import firma_servicio
                    from src.rrhh.db import documentos as _RRHH_DOCS
                    from src.rrhh.db import empleados as _RRHH_EMP
                    from src.rrhh.documents.forms_rrhh import ANEXOS_CONTRATO_TIPOS
                    from src.rrhh.persistencia import _fecha_iso
                    _mapa_tipo = dict(ANEXOS_CONTRATO_TIPOS)
                    _emp_doc = _RRHH_EMP.obtener_por_nif(self._datos.get("nif"))
                    if _emp_doc:
                        for etiqueta in self._datos["anexos_firmables"]:
                            tipo_doc = _mapa_tipo.get(etiqueta)
                            if not tipo_doc:
                                continue
                            id_doc = _RRHH_DOCS.crear_documento(
                                _emp_doc["id"], _emp_doc["id_empresa"], tipo_doc=tipo_doc,
                                fecha=_fecha_iso(self._datos.get("fecha")), ref_documento=ruta)
                            if id_doc:
                                firma_servicio.marcar_requiere_firma(id_doc, id_empresa=_emp_doc["id_empresa"])
                except Exception:
                    LOG_DOCUMENTOS.exception("Alta de anexos firmables del contrato (no crítica)")

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
    (representantes legales y centros de empresa)."""

    def __init__(self, titulo, campos, valores=None, parent=None, sin_cancelar=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._campos = campos
        self._inps = {}
        # sin_cancelar: opt-in SOLO para "Centros de empresa" (ver `_de_add_centro`/`_de_edit_centro`)
        # — sustituye el botón CANCELAR por una ✕ roja redonda arriba a la derecha, mismo patrón que
        # `gui/selector_tienda.py::_btn_x`. El resto de usos de esta clase (p. ej. Representantes
        # legales) NO pasan este parámetro y conservan su comportamiento (CANCELAR) intacto.
        self._sin_cancelar = sin_cancelar
        self._build(titulo, valores or {})

    def _build(self, titulo, valores):
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:#0E1117;border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        cab.addWidget(t, 1)
        if self._sin_cancelar:
            btn_x = QPushButton("✕")
            btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_x.setFixedSize(36, 36)
            btn_x.setStyleSheet(
                "QPushButton{background:transparent;color:#F85149;border:none;border-radius:18px;"
                "padding:0;font-weight:900;font-size:16px;}"
                "QPushButton:hover{background:#F85149;color:#0D1117;}")
            btn_x.setProperty("sin_glow", True)
            # Blindaje de tamaño fijo (ver `assets/estilo_global.py::_blindar_tamano_fijo`): sin
            # esto, el filtro global de estilos reinicia la política de tamaño a Minimum en cada
            # Show/Polish de este diálogo frameless+translúcido, e infla el ancho del botón (redondo
            # en reposo, "píldora" ancha al hacer hover) — mismo patrón que
            # `gui/selector_tienda.py::_btn_x`.
            _blindar_tamano_fijo(btn_x, 36, 36)
            btn_x.clicked.connect(self.reject)
            cab.addWidget(btn_x)
        ly.addLayout(cab)
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
        if not self._sin_cancelar:
            bc = QPushButton(tr("cfg.ban_cancelar", default="CANCELAR")); bc.setFixedHeight(38)
            bc.setCursor(Qt.CursorShape.PointingHandCursor)
            bc.setStyleSheet("QPushButton{background:#0E1117;color:#F85149;border:2px solid #F85149;border-radius:8px;font-weight:900;font-size:12px;padding:0 18px;}QPushButton:hover{background:#F85149;color:#0E1117;}")
            bc.clicked.connect(self.reject)
            br.addWidget(bc)
        bg = QPushButton(tr("cfg.de_guardar_corto", default="Guardar")); bg.setFixedHeight(38)
        bg.setCursor(Qt.CursorShape.PointingHandCursor)
        bg.setStyleSheet("QPushButton{background:#0E1117;color:#3FB950;border:2px solid #3FB950;border-radius:8px;font-weight:900;font-size:12px;padding:0 18px;}QPushButton:hover{background:#3FB950;color:#0E1117;}")
        bg.clicked.connect(self.accept)
        br.addWidget(bg); ly.addLayout(br)
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
        self.setup_ui()
        # Abrir directamente en una pestaña concreta (p. ej. desde "VER CITA").
        ti = kwargs.get("tab_inicial")
        if (ti is not None and hasattr(self, "btns") and 0 <= ti < len(self.btns)
                and self.btns[ti] is not None):
            try:
                self.btns[ti].click()
            except Exception:
                pass
        # UX-TPV-01 (P5/5.1): acceso directo desde el TPV (Transferir efectivo/Cambio cajero). Antes
        # disparaba la acción SOLA, automáticamente, tras un margen — pero el diálogo modal de
        # autorización que abre esa acción (`_AutorizacionAdminDialog.exec()`, un segundo bucle de
        # eventos anidado) competía con la animación de entrada del propio módulo la trababa, por
        # poco margen que se le diera. Ahora `accion_inicial` no dispara nada por sí solo: el usuario
        # pulsa el botón correspondiente ya con el módulo asentado (mismo botón, visible de entrada
        # en la pantalla principal de Gestión Caja) — sin ningún diálogo compitiendo con ninguna
        # animación.

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reafirmar_geometria()

    def _reafirmar_geometria(self):
        # Mismo criterio CONFIRMADO con log real que `_BasculaDialog._reafirmar_geometria` (tpv.py)
        # y `_PagoDialog` (misma clase): `menu_principal.py::manejar_apertura` ya fija esta ventana
        # a `availableGeometry()` (el área de trabajo, SIN la barra de tareas) antes de llamar a
        # `showMaximized()` — pero al ser una ventana SIN MARCO (`FramelessWindowHint`), Windows
        # vuelve a maximizarla varias veces durante su propio arranque usando la geometría COMPLETA
        # de la pantalla (cubriendo la barra de tareas), ignorando ese ajuste inicial. Un reajuste
        # puntual en `showEvent` puede acabar corrigiendo contra uno de esos valores transitorios en
        # vez del definitivo; `resizeEvent` reacciona a CADA cambio, así que siempre acaba asentado
        # en el objetivo real sea cual sea el número de pasadas que Windows necesite.
        try:
            scr = self.screen() or QApplication.primaryScreen()
            geo = scr.availableGeometry() if scr is not None else self.geometry()
            if self.geometry() != geo:
                self.setGeometry(geo)
        except Exception:
            pass

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SIDEBAR ---
        sidebar = QFrame()
        self.sidebar = sidebar  # P3: referencia para el toggle colapsable
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"background-color: {_PANEL_BG};")   # sin border-right (línea gris fina)
        side_ly = QVBoxLayout(sidebar)

        lbl_tit = QLabel(tr("cfg.smart_config", default="SMART CONFIG").upper())
        # Mismo estilo que el resto de sidebars (sin margen superior extra): título justo bajo la flecha.
        lbl_tit.setStyleSheet(
            "color: white; font-weight: 900; font-size: 16px; letter-spacing: 2px;"
            "padding: 0 0 24px 28px; background: transparent;"
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
            "cfg.tab_referencia", "cfg.tab_datos_empresa", "cfg.tab_modo_tactil",
            "cfg.tab_soma", "cfg.tab_colores", "cfg.tab_mfa", "cfg.tab_edicion",
            "cfg.tab_estado_cuenta", "cfg.tab_delegacion_ia", "cfg.tab_suscripcion",
        ]
        _tab_def = [
            "GESTIÓN CAJA", "PLAZO DEVOLUCIÓN", "GENERAR PERFIL EMPLEADO",
            "HORARIO EMPLEADOS", "FICHAJES", "LOGO CORPORATIVO",
            "PLANIFICAR CITAS", "FISCALIDAD", "ASIGNAR REFERENCIA",
            "DATOS DE EMPRESA", "MODO TÁCTIL", "ASISTENTE SOMA", "PERSONALIZACIÓN", "SEGURIDAD (MFA)", "VERSIÓN",
            "ESTADO DE LA CUENTA", "DELEGACIÓN IA", "SUSCRIPCIÓN",
        ]

        _perfil_cfg = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper() if sesion_global else ""
        self.btns = []
        for i, key in enumerate(self._tab_keys):
            # P4.1: GESTIÓN CAJA (índice 0) ya NO es una pestaña de Configuración;
            # vive en su propia ventana (GestionCajaWindow). Mantenemos un placeholder
            # en self.btns para no re-indexar el resto de pestañas ni su lógica.
            if i in (0, 3, 4, 6, 7, 8):
                # 0 = GESTIÓN CAJA (ventana propia). 3 = HORARIO EMPLEADOS y 4 = FICHAJES
                # (restructuración 2026-09: extraídas a ventanas propias del menú principal —
                # `HorariosWindow` en horarios_gui.py y `FichajesWindow` en fichajes_gui.py — ya
                # NO son pestañas de Configuración). 6 = PLANIFICAR CITAS, extraída al módulo
                # propio "Eventos" del menú principal (EventosWindow en eventos_gui.py), SOLO
                # SUPERADMIN — petición explícita. 7 = FISCALIDAD (migrada a RRHH/Contabilidad).
                # 8 = ASIGNAR REFERENCIA (RETIRADA — sustituida por Identidad Operativa/IOC).
                # Placeholder para no re-indexar el resto de pestañas.
                self.btns.append(None)
                continue
            if i == 2 and _perfil_cfg != "SUPERADMIN":
                # GENERAR PERFIL EMPLEADO (alta/edición de perfiles de acceso): SOLO SUPERADMIN.
                self.btns.append(None)
                continue
            if i == 11 and _perfil_cfg != "SUPERADMIN":
                # ASISTENTE SOMA: el propio asistente está restringido a SUPERADMIN (ver
                # main.py::_iniciar_soma), así que no tiene sentido mostrar sus ajustes a perfiles
                # que nunca podrán usarlo.
                self.btns.append(None)
                continue
            if i == 16 and _perfil_cfg != "SUPERADMIN":
                # DELEGACIÓN IA (autorrelleno de centros nuevos — services.soma_delegacion):
                # SOLO SUPERADMIN, mismo gate que el resto de delegaciones a SOMA del resto de
                # módulos (Correo/CRM/Posventa/Compras).
                self.btns.append(None)
                continue
            if i == 17 and _perfil_cfg != "SUPERADMIN":
                # SUSCRIPCIÓN (migrada tal cual desde la tarjeta "SaaS" del menú principal —
                # petición explícita): esa tarjeta ya era SOLO SUPERADMIN hoy (`saas` no está en
                # `DEFAULT_ADMINISTRADOR`/`DEFAULT_OPERARIO`) — se conserva el mismo gate al migrar.
                self.btns.append(None)
                continue
            btn = _SidebarBtn(tr(key, default=_tab_def[i]).upper())
            btn.clicked.connect(lambda _, idx=i: self._cambiar_vista(idx))
            self.side_btns_ly.addWidget(btn)
            self.btns.append(btn)

        self.side_btns_ly.addStretch()
        scroll_side.setWidget(side_content)
        side_ly.addWidget(scroll_side)

        self._btn_salir = btn_salir = _SidebarBtn(tr("cfg.exit", default="SALIR AL MENÚ").upper())
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
        # StackedActual (no QStackedWidget "a pelo"): sin esto el ancho/alto mínimo de la ventana
        # reflejaba el máximo de TODAS las páginas ya visitadas (aunque solo una esté visible),
        # forzando una ventana más grande que la pantalla real del usuario y provocando el fallo
        # nativo de Windows al no poder concederle esa geometría (mismo bug ya resuelto en
        # Contabilidad/RRHH/Cámaras/Mermas).
        self.stack = StackedActual()
        self._page_builders = {
            0: QWidget,  # P4.1: caja gestionada en GestionCajaWindow (placeholder aquí)
            1: self._crear_page_plazo_devolucion,
            2: self._crear_page_perfiles,
            3: QWidget,  # HORARIO EMPLEADOS extraída a HorariosWindow (horarios_gui.py). Placeholder.
            4: QWidget,  # FICHAJES extraída a FichajesWindow (fichajes_gui.py). Placeholder.
            5: self._crear_page_logo,
            6: QWidget,  # PLANIFICAR CITAS extraída a EventosWindow (eventos_gui.py). Placeholder.
            7: QWidget,  # FISCALIDAD migrada (LABORAL→RRHH, FISCAL→Contabilidad). Placeholder.
            8: QWidget,  # ASIGNAR REFERENCIA RETIRADA (deprecada → Identidad Operativa/IOC). Placeholder.
            9: self._crear_page_datos_empresa,
            10: self._crear_page_modo_tactil,
            11: self._crear_page_soma,
            12: self._crear_page_colores,
            13: self._crear_page_mfa,
            14: self._crear_page_edicion,   # EDICIÓN (versión por tipo de comercio) — visor de segmentación
            15: self._crear_page_estado_cuenta,  # ESTADO DE LA CUENTA — progreso de configuración (agregado)
            16: self._crear_page_delegacion_ia,  # DELEGACIÓN IA — autorrelleno de centros nuevos
            17: self._crear_page_suscripcion,  # SUSCRIPCIÓN — migrada desde la tarjeta "SaaS" del menú
        }
        self._loaded_pages = set()
        for i in range(len(self._page_builders)):
            if i == 1:
                # Primera pestaña visible ahora que GESTIÓN CAJA (0) tiene ventana propia.
                self.stack.addWidget(self._crear_page_plazo_devolucion())
                self._loaded_pages.add(1)
            else:
                self.stack.addWidget(QWidget())  # placeholder — se crea al visitarla

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)
        self.stack.setCurrentIndex(1)
        if len(self.btns) > 1 and self.btns[1] is not None:
            self.btns[1].setChecked(True)
        i18n.conectar_retraduccion(self, self._retraducir_cfg)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="configuracion")
        except Exception:
            pass

    def _crear_page_edicion(self):
        """EDICIÓN — visor de la segmentación por tipo de comercio. Muestra la edición del build y qué funciones
        están activas/ocultas/sustituidas (según `services.verticales`). Solo lectura: la edición se fija por
        instalación (SMART_MANAGER_EDITION), no se cambia aquí."""
        from PyQt6.QtWidgets import (QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
        from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
        from src.services import verticales
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(24, 20, 24, 20); ly.setSpacing(12)
        titulo = QLabel(verticales.nombre_edicion().upper())
        titulo.setStyleSheet("color:#00FFC6;font-size:18px;font-weight:900;")
        ly.addWidget(titulo)
        sub = QLabel(f"Versión: {verticales.edicion()}. Misma base y misma tarifa; cada versión muestra solo "
                     "las funciones de su tipo de comercio (fijado por instalación).")
        sub.setStyleSheet("color:#8B949E;"); sub.setWordWrap(True)
        ly.addWidget(sub)

        # ── EXPERIENCIA: modo pyme simple + asistente de primeros pasos (R1) ──
        from src.services import onboarding as _onb
        exp = QLabel("EXPERIENCIA")
        exp.setStyleSheet("color:#00FFC6;font-weight:900;font-size:13px;margin-top:6px;")
        ly.addWidget(exp)
        chk_simple = QCheckBox(tr("cfg.modo_simple",
                                  default="Modo pyme simple — muestra solo lo esencial en el menú"))
        chk_simple.setChecked(_onb.modo_simple())
        chk_simple.setStyleSheet("color:#E6EDF3;font-family:'Segoe UI';font-size:13px;")

        def _toggle_simple(estado):
            _onb.fijar_modo_simple(bool(estado))
            mostrar_mensaje(self, tr("cfg.modo_simple_titulo", default="Modo pyme simple"),
                            tr("cfg.modo_simple_aplicar",
                               default="Se aplicará al volver al menú."), "info")
        chk_simple.toggled.connect(_toggle_simple)
        ly.addWidget(chk_simple)

        tabla = QTableWidget(0, 3)
        tabla.setHorizontalHeaderLabels(["Función", "Estado", "Sustituida por"])
        tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabla.horizontalHeader().setHighlightSections(False)
        tabla.verticalHeader().setVisible(False)          # retira la columna de índices (1..6)
        tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        # Contorno de NEÓN turquesa + cabeceras redondeadas + hover-swap (estilo canónico compartido). La máscara
        # de `_RoundTableCorners` redondea las 4 esquinas de la tabla y las superiores de la cabecera para que el
        # contorno neón no se corte.
        tabla.setStyleSheet(_ss_tabla_neon())
        self._round_tabla_edicion = _RoundTableCorners(tabla, radius=10)
        _EST = {"visible": "✅ Activa", "oculto": "— Oculta", "sustituida": "↷ Sustituida"}
        for f in verticales.funciones():
            r = tabla.rowCount(); tabla.insertRow(r)
            tabla.setItem(r, 0, QTableWidgetItem(f["label"]))
            tabla.setItem(r, 1, QTableWidgetItem(_EST.get(f["estado"], f["estado"])))
            tabla.setItem(r, 2, QTableWidgetItem(f["sustituto"] or ""))
        self._tabla_edicion = tabla
        ly.addWidget(tabla, 1)
        return w

    def _crear_page_estado_cuenta(self):
        """ESTADO DE LA CUENTA — progreso de configuración (agregado, solo lectura). Reutiliza
        `services.cuenta.resumen` (que a su vez agrega onboarding/verticales/SaaS/activacion). Muestra el %
        completado, el checklist de lo que falta y el estado de las integraciones de producción (opcionales)."""
        from PyQt6.QtWidgets import (QHeaderView, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
                                     QVBoxLayout, QWidget)
        from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
        cont = QWidget(); ly = QVBoxLayout(cont); ly.setContentsMargins(24, 20, 24, 20); ly.setSpacing(12)

        try:
            from src.services import cuenta
            data = cuenta.resumen()
        except Exception as e:
            data = {"porcentaje": 0, "items": [], "pendientes": [], "integraciones": {"detalle": []},
                    "edicion": None, "plan": None, "_err": str(e)}

        pct = int(data.get("porcentaje") or 0)
        titulo = QLabel(tr("cfg.estado_cuenta_titulo", default="ESTADO DE LA CUENTA"))
        titulo.setStyleSheet("color:#00FFC6;font-size:18px;font-weight:900;")
        ly.addWidget(titulo)

        # Cabecera con % y barra de progreso.
        cab = QLabel(tr("cfg.estado_cuenta_pct", default="Configuración completada: {p}%", p=pct))
        cab.setStyleSheet("color:#E6EDF3;font-size:15px;font-weight:800;")
        ly.addWidget(cab)
        barra = QProgressBar(); barra.setRange(0, 100); barra.setValue(pct); barra.setTextVisible(False)
        barra.setFixedHeight(14)
        _col = "#00FFC6" if pct >= 100 else ("#F5A623" if pct >= 50 else "#F85149")
        barra.setStyleSheet("QProgressBar{background:#161B22;border:1px solid #30363D;border-radius:7px;}"
                            f"QProgressBar::chunk{{background:{_col};border-radius:6px;}}")
        ly.addWidget(barra)

        pend = data.get("pendientes") or []
        resumen_txt = (tr("cfg.estado_cuenta_ok", default="¡Tu cuenta está configurada al 100%!")
                       if not pend else
                       tr("cfg.estado_cuenta_faltan", default="Te faltan {n} paso(s) para completar tu cuenta.",
                          n=len(pend)))
        sub = QLabel(resumen_txt); sub.setStyleSheet("color:#8B949E;font-size:12px;"); sub.setWordWrap(True)
        ly.addWidget(sub)

        # Checklist de configuración (ítems core).
        t1 = QTableWidget(0, 3)
        t1.setHorizontalHeaderLabels([tr("cfg.ec_col_item", default="Parámetro"),
                                      tr("cfg.ec_col_estado", default="Estado"),
                                      tr("cfg.ec_col_detalle", default="Detalle / dónde")])
        t1.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t1.verticalHeader().setVisible(False)
        t1.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t1.setFrameShape(QTableWidget.Shape.NoFrame)
        t1.setStyleSheet(_ss_tabla_neon())
        self._round_tabla_estado = _RoundTableCorners(t1, radius=10)
        for it in data.get("items", []):
            r = t1.rowCount(); t1.insertRow(r)
            t1.setItem(r, 0, QTableWidgetItem(it.get("titulo") or ""))
            t1.setItem(r, 1, QTableWidgetItem("✅ Hecho" if it.get("hecho") else "⚠️ Pendiente"))
            det = it.get("detalle") or ""
            if not it.get("hecho") and it.get("accion"):
                det = f"{det}  ·  {it['accion']}"
            t1.setItem(r, 2, QTableWidgetItem(det))
        ly.addWidget(t1)

        # Integraciones de producción (opcionales — no penalizan el %).
        integ = (data.get("integraciones") or {}).get("detalle") or []
        cab2 = QLabel(tr("cfg.ec_integraciones",
                         default="INTEGRACIONES DE PRODUCCIÓN (opcionales — requieren credenciales)"))
        cab2.setStyleSheet("color:#00FFC6;font-weight:900;font-size:13px;margin-top:6px;")
        ly.addWidget(cab2)
        t2 = QTableWidget(0, 3)
        t2.setHorizontalHeaderLabels([tr("cfg.ec_col_integr", default="Integración"),
                                      tr("cfg.ec_col_modo", default="Estado"),
                                      tr("cfg.ec_col_falta", default="Qué falta para activar")])
        t2.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t2.verticalHeader().setVisible(False)
        t2.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t2.setFrameShape(QTableWidget.Shape.NoFrame)
        t2.setStyleSheet(_ss_tabla_neon())
        self._round_tabla_integr = _RoundTableCorners(t2, radius=10)
        for it in integ:
            r = t2.rowCount(); t2.insertRow(r)
            t2.setItem(r, 0, QTableWidgetItem(f"[{it.get('requisito','')}] {it.get('nombre','')}"))
            t2.setItem(r, 1, QTableWidgetItem("🟢 En producción" if it.get("listo") else "🟡 Preparada"))
            t2.setItem(r, 2, QTableWidgetItem("" if it.get("listo") else " · ".join(it.get("requiere") or [])))
        ly.addWidget(t2)

        # Envolver en scroll (contenido puede crecer).
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        scroll.setWidget(cont)
        return scroll

    def _retraducir_cfg(self):
        """Re-traduce el chrome (título, pestañas, salir) al cambiar de idioma."""
        self.setWindowTitle(tr("cfg.window_title", default="CONFIGURACIÓN DEL SISTEMA"))
        _tab_def = [
            "GESTIÓN CAJA", "PLAZO DEVOLUCIÓN", "GENERAR PERFIL EMPLEADO",
            "HORARIO EMPLEADOS", "FICHAJES", "LOGO CORPORATIVO",
            "PLANIFICAR CITAS", "FISCALIDAD", "ASIGNAR REFERENCIA",
            "DATOS DE EMPRESA", "MODO TÁCTIL", "ASISTENTE SOMA", "PERSONALIZACIÓN", "SEGURIDAD (MFA)", "VERSIÓN",
            "ESTADO DE LA CUENTA", "DELEGACIÓN IA", "SUSCRIPCIÓN",
        ]
        for i, btn in enumerate(self.btns):
            if btn is None:  # P4.1: índice 0 (caja) no tiene pestaña en Configuración
                continue
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
        # Access control: GENERAR PERFIL EMPLEADO (index 2) — SUPERADMIN only
        if index == 2:
            _perfil = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper() if sesion_global else ""
            if _perfil != "SUPERADMIN":
                mostrar_mensaje(
                    self, tr("cfg.access_restricted_title", default="Acceso restringido"),
                    tr("cfg.access_restricted_perfil_msg",
                       default="Solo SUPERADMIN puede generar o editar perfiles de empleado."), "error"
                )
                return
        # Access control: ASISTENTE SOMA (index 11) — SUPERADMIN only (botón ya oculto para el
        # resto, pero esta ruta también es alcanzable por índice directo, p. ej. desde
        # `abrir_modulo_configuracion(tab_inicial=11)`).
        if index == 11:
            _perfil = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper() if sesion_global else ""
            if _perfil != "SUPERADMIN":
                mostrar_mensaje(
                    self, tr("cfg.access_restricted_title", default="Acceso restringido"),
                    tr("cfg.access_restricted_soma_msg",
                       default="El Asistente SOMA está disponible solo para SUPERADMIN."), "error"
                )
                return
        # Access control: SUSCRIPCIÓN (index 17) — SUPERADMIN only (botón ya oculto para el resto,
        # misma red de seguridad por índice directo que GENERAR PERFIL/ASISTENTE SOMA).
        if index == 17:
            _perfil = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper() if sesion_global else ""
            if _perfil != "SUPERADMIN":
                mostrar_mensaje(
                    self, tr("cfg.access_restricted_title", default="Acceso restringido"),
                    tr("cfg.access_restricted_saas_msg",
                       default="La gestión de suscripción está disponible solo para SUPERADMIN."), "error"
                )
                return
        self._ensure_page(index)
        self.stack.setCurrentIndex(index)
        if index == 2:  # Perfiles
            self.refrescar_datos_usuarios()

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
    # Unificación "Centros de empresa" (migración 0257): centros_trabajo absorbe lo que hasta hoy
    # vivía en centros_perfil (retirada) — tipo_centro va PRIMERO (pedido explícito). id_almacen NO
    # se expone aquí como desplegable: _FormDialogCorp solo guarda `currentText()` de los combos
    # (texto plano), no un id separado, así que un desplegable de almacenes necesitaría un mapeo
    # texto→id que esta clase genérica no soporta (y no se quiso ampliar solo para este caso) — se
    # deja enlazable programáticamente/vía una acción de vinculación futura, igual que se decidió
    # para el enlace tienda↔centro. Geolocalización automática por código postal (nunca editable a
    # mano — no hay campos latitud/longitud: ver `src/db/centros.py::_geocodificar_y_propagar`).
    # Cada código va JUSTO después de su campo.
    _TIPOS_CENTRO = ["tienda", "almacen", "fabrica", "oficina", "otro"]
    _CAMPOS_CT = [
        ("tipo_centro", "Tipo de centro", _TIPOS_CENTRO),
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

    # Agregador logístico del centro (Fase etiquetas de transporte, migración 0328) — formulario
    # SEPARADO de los datos corporativos del centro (arriba): credenciales/remitente, no datos
    # fiscales/laborales. `api_key`/`api_secret` son WRITE-ONLY a propósito (nunca se precargan con
    # el valor real, mismo criterio que el resto de "secretos" del proyecto) — dejarlos en blanco al
    # editar conserva las credenciales ya guardadas tal cual, sin pedir volver a escribirlas.
    _CAMPOS_AGG = [
        ("id_agregador", "Agregador", ("sendcloud", "packlink", "shipmondo")),
        ("api_key", "API Key (déjalo en blanco para no cambiarla)"),
        ("api_secret", "API Secret (déjalo en blanco para no cambiarla)"),
        ("nombre_remitente", "Nombre remitente"), ("direccion_remitente", "Dirección remitente"),
        ("codigo_postal_remitente", "Código postal remitente"),
        ("telefono_remitente", "Teléfono remitente"),
        ("email_remitente", "Correo electrónico remitente"),
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

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        # Petición explícita, 2026-11-20: el contenido de esta pestaña (p. ej. la tabla "Centros de
        # empresa", con `setMinimumWidth(1070)` para sus 7 columnas) puede ser más ancho que la
        # propia pestaña con ventanas/paneles estrechos — antes quedaba cortado sin forma de verlo
        # (scrollbar horizontal desactivada). `AsNeeded` solo la muestra cuando de verdad hace
        # falta, sin cambiar nada cuando el contenido ya cabe.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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

        # ── Sector Comercial (Smart Suppliers B2B, migr. 0217/0296): condiciona qué proveedores del
        # catálogo B2B puede ver la empresa — DISTINTO de la edición/vertical de la instalación
        # (`services.verticales`, que gatea funciones y se fija una sola vez en el onboarding de la
        # app); aquí se reutilizan las mismas 5 etiquetas por familiaridad, pero cambiar esto NUNCA
        # toca qué funciones están visibles, solo el filtro de proveedores del Portal B2B.
        il.addWidget(self._de_sec(tr("cfg.de_sec_sector", default="SECTOR COMERCIAL")))
        rl_sec = QHBoxLayout(); rl_sec.setSpacing(8)
        col_sec = QVBoxLayout()
        col_sec.addWidget(self._de_lbl(tr("cfg.de_sector_lbl", default="Sector comercial:")))
        self._de_sector = _NeonComboBox(); self._de_sector.setFixedHeight(38)
        self._de_sector.setObjectName("de_sector_cb")
        self._de_sector.setMaxVisibleItems(6)
        self._de_sector.setStyleSheet(
            "QComboBox#de_sector_cb{combobox-popup:0;background:#161B22;color:white;"
            f"border:2px solid {_CIAN};border-radius:8px;padding:0 12px;font-size:12px;"
            "font-family:'Segoe UI';}"
            "QComboBox#de_sector_cb::drop-down{border:none;width:24px;}"
        )
        from src.services import verticales as _vert
        from src.services.compras import sectores as _sect
        _secs_por_codigo = {s["codigo"]: s for s in _sect.listar()}
        for _v in _vert.VERTICALES:   # mismo orden que la matriz de ediciones (nunca alfabético)
            _s = _secs_por_codigo.get(_v.lower())
            if _s:
                self._de_sector.addItem(_s["nombre"], _s["id"])
        # Ancho suficiente para que ningún texto se corte (pedido explícito) — mismo criterio ya
        # usado para el desplegable de divisas de Canal Web.
        self._de_sector.view().setMinimumWidth(260)
        self._de_sector.setMinimumWidth(260)
        _sector_actual = emp.get("sector_id")
        if _sector_actual:
            _ix_sec = self._de_sector.findData(int(_sector_actual))
            if _ix_sec >= 0:
                self._de_sector.setCurrentIndex(_ix_sec)
        self._de_sector.setEnabled(self._de_admin)
        col_sec.addWidget(self._de_sector)
        rl_sec.addLayout(col_sec, 1)
        rl_sec.addStretch(1)
        il.addLayout(rl_sec)

        bg = QHBoxLayout(); bg.addStretch()
        self._de_btn_guardar = self._de_btn_verde(
            tr("cfg.de_guardar", default="Guardar datos de empresa"), self._de_guardar_empresa)
        self._de_btn_guardar.setEnabled(self._de_admin); bg.addWidget(self._de_btn_guardar)
        il.addLayout(bg)

        # ── BLOQUE REPRESENTANTES LEGALES ──
        hr = QHBoxLayout(); hr.addWidget(self._de_sec(tr("cfg.de_sec_reps", default="REPRESENTANTES LEGALES")), 1)
        self._de_btn_add_rep = self._de_btn_cian(tr("cfg.de_add_rep", default="➕  AÑADIR REPRESENTANTE"), self._de_add_rep)
        self._de_btn_add_rep.setEnabled(self._de_admin); hr.addWidget(self._de_btn_add_rep)
        il.addLayout(hr)
        self._tabla_reps = self._de_tabla(["NOMBRE", "DNI / NIE", "CARGO", "PRINCIPAL", "ACCIONES"])
        il.addWidget(self._de_wrap(self._tabla_reps))

        # ── BLOQUE CENTROS DE EMPRESA (unificado, migración 0257 — antes "Centros de trabajo" +
        # "Centros" en dos bloques separados; ver src/db/centros.py) ──
        hc = QHBoxLayout(); hc.addWidget(self._de_sec(tr("cfg.de_sec_centros", default="CENTROS DE EMPRESA")), 1)
        self._de_btn_add_ct = self._de_btn_cian(tr("cfg.de_add_ct", default="➕  AÑADIR CENTRO"), self._de_add_centro)
        self._de_btn_add_ct.setEnabled(self._de_admin); hc.addWidget(self._de_btn_add_ct)
        il.addLayout(hc)
        self._tabla_cts = self._de_tabla(
            ["TIPO", "CÓDIGO", "NOMBRE", "MUNICIPIO", "CCC", "PRINCIPAL", "ACCIONES"])
        # Anchura fija por columna (en vez de Stretch, heredado de `_de_tabla`): con 5 botones en
        # ACCIONES (★/✎/🏷/🔑/🗑) el modo Stretch los apretaba hasta solaparse al reducir la ventana.
        # Columnas con ancho propio + scrollbar horizontal cuando no caben (pedido explícito).
        _h_cts = self._tabla_cts.horizontalHeader()
        for _c in range(6):
            _h_cts.setSectionResizeMode(_c, QHeaderView.ResizeMode.Interactive)
        _h_cts.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        for _c, _w in enumerate([90, 110, 230, 150, 160, 100, 230]):
            self._tabla_cts.setColumnWidth(_c, _w)
        self._tabla_cts.setMinimumWidth(1070)
        self._tabla_cts.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        if hasattr(self, "_de_sector") and self._de_sector.currentData():
            campos["sector_id"] = self._de_sector.currentData()
        # Step-up MFA solo si cambia el correo corporativo (acción crítica `email.cambiar`).
        if "email_principal" in campos:
            try:
                actual = (self._de_emp_mod.obtener_empresa(
                    self._de_emp_mod.empresa_actual_id()) or {}).get("email_principal") or ""
            except Exception:
                actual = ""
            if campos["email_principal"] != actual:
                from src.gui.mfa_gui import step_up_sesion
                if not step_up_sesion("email.cambiar", self):
                    return
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
            t.setItem(r, 0, QTableWidgetItem((ct.get("tipo_centro") or "—").upper()))
            t.setItem(r, 1, QTableWidgetItem(ct.get("codigo_centro") or "—"))
            t.setItem(r, 2, QTableWidgetItem(ct.get("nombre_centro") or "—"))
            t.setItem(r, 3, QTableWidgetItem(ct.get("municipio") or "—"))
            t.setItem(r, 4, QTableWidgetItem(ct.get("codigo_cuenta_cotizacion") or "—"))
            pr = QTableWidgetItem("★ SÍ" if ct.get("es_principal") else "—")
            pr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ct.get("es_principal"):
                pr.setForeground(QColor("#D29922"))
            t.setItem(r, 5, pr)
            cont = QWidget(); cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont); hl.setContentsMargins(4, 0, 4, 0); hl.setSpacing(6)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._de_admin:
                if not ct.get("es_principal"):
                    hl.addWidget(self._de_mini("★", "#D29922",
                        lambda _=0, i=ct.get("id_centro"): self._de_principal_centro(i)))
                hl.addWidget(self._de_mini("✎", _CIAN, lambda _=0, d=ct: self._de_edit_centro(d)))
                hl.addWidget(self._de_mini("🏷", "#3FB950",
                    lambda _=0, d=ct: self._de_config_agregador(d)))
                hl.addWidget(self._de_mini("🔑", "#D29922",
                    lambda _=0, d=ct: self._de_generar_codigo_instalacion(d)))
                hl.addWidget(self._de_mini("🗑", "#F85149",
                    lambda _=0, i=ct.get("id_centro"): self._de_baja_centro(i)))
            t.setCellWidget(r, 6, cont)

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
        id_empresa = self._de_emp_mod.empresa_actual_id()
        # Hallazgo real, 2026-11-20: "Centros de empresa" creaba centros sin límite, sea cual sea
        # el plan contratado — el chokepoint de licencias (`services.saas.licensing`) existía
        # (recurso "max_tiendas", el límite de CENTROS de cara al cliente — ver su comentario en
        # `_CONTADORES`) pero ningún punto de la GUI llegaba a invocarlo. Se comprueba AQUÍ, ANTES
        # de abrir el formulario (para no hacer rellenar datos a un centro que luego se rechaza).
        from src.gui._licencia_ui import verificar_limite_o_avisar
        if not verificar_limite_o_avisar(self, "max_tiendas", id_empresa):
            return
        dlg = _FormDialogCorp(tr("cfg.de_nuevo_ct", default="NUEVO CENTRO"), self._CAMPOS_CT, {},
                              self, sin_cancelar=True)
        if dlg.exec():
            creador_id = None
            try:
                creador_id = (sesion_global.usuario_actual or {}).get("id")
            except Exception:
                pass
            valores = dlg.valores()
            id_centro = self._de_cts_mod.crear_centro(
                id_empresa=id_empresa, creado_por_id=creador_id, **valores)
            # Auto-provisioning (F1, fix definitivo — decisión explícita del usuario): un centro
            # `tipo_centro='tienda'` nace AQUÍ MISMO con su propia tienda real vinculada, en una
            # sola operación de guardado — nunca hace falta un paso de "vincular a una tienda YA
            # existente" (diseño anterior, `_VincularTiendaDialog`, retirado por poco intuitivo:
            # cada centro tiene su PROPIA identidad desde la creación, no la de otra tienda).
            if id_centro and valores.get("tipo_centro") == "tienda":
                ct = self._de_cts_mod.obtener_centro(id_centro) or {}
                from src.db import tiendas as _t
                id_tienda = _t.crear_tienda(
                    ct.get("nombre_centro") or valores.get("nombre_centro"),
                    id_empresa=id_empresa, codigo_tienda=ct.get("codigo_centro"))
                if id_tienda:
                    self._de_cts_mod.actualizar_centro(id_centro, id_tienda=id_tienda)
                else:
                    mostrar_mensaje(
                        self, tr("cfg.error_title", default="Error"),
                        tr("cfg.tienda_autoprov_err", default="El centro se creó, pero no se pudo "
                                                               "crear su tienda real vinculada. "
                                                               "Edítalo para reintentarlo."), "error")
            self._de_refrescar_centros()

    def _de_edit_centro(self, ct):
        if not self._de_admin:
            return
        dlg = _FormDialogCorp(tr("cfg.de_edit_ct", default="EDITAR CENTRO"), self._CAMPOS_CT, ct,
                              self, sin_cancelar=True)
        if dlg.exec():
            self._de_cts_mod.actualizar_centro(ct.get("id_centro"), **dlg.valores())
            self._de_refrescar_centros()

    def _de_config_agregador(self, ct):
        """Configura el agregador logístico (etiquetas de transporte) de un centro — formulario
        SEPARADO de "Editar centro" (arriba): credenciales/remitente, no datos corporativos.
        Precarga el remitente con los datos del propio centro la primera vez (editable)."""
        if not self._de_admin:
            return
        id_centro = ct.get("id_centro")
        from src.services.logistica import envios as _env_mod
        actual = _env_mod.config_centro(id_centro) or {}
        # Fallback telefono/email: si el propio centro no los tiene rellenos (campo opcional en
        # "Editar centro"), se usan los de la EMPRESA (pestaña DATOS DE EMPRESA) — mismo criterio
        # ya aplicado al resto de campos de remitente, nunca se deja el campo vacío si hay un dato
        # razonable disponible.
        emp_actual = self._de_emp_mod.obtener_empresa() or {}
        valores = {
            "id_agregador": actual.get("id_agregador") or "sendcloud",
            "nombre_remitente": actual.get("nombre_remitente") or ct.get("nombre_centro"),
            "direccion_remitente": actual.get("direccion_remitente") or ct.get("direccion"),
            "codigo_postal_remitente": actual.get("codigo_postal_remitente") or ct.get("codigo_postal"),
            "telefono_remitente": (actual.get("telefono_remitente") or ct.get("telefono")
                                   or emp_actual.get("telefono")),
            "email_remitente": (actual.get("email_remitente") or ct.get("email")
                                or emp_actual.get("email_principal")),
        }
        dlg = _FormDialogCorp(tr("cfg.de_config_agregador", default="AGREGADOR LOGÍSTICO DEL CENTRO"),
                              self._CAMPOS_AGG, valores, self, sin_cancelar=True)
        if dlg.exec():
            v = dlg.valores()
            id_empresa = self._de_emp_mod.empresa_actual_id()
            r = _env_mod.guardar_config_centro(
                id_centro, id_agregador=v.get("id_agregador"), id_empresa=id_empresa,
                nombre_remitente=v.get("nombre_remitente") or None,
                direccion_remitente=v.get("direccion_remitente") or None,
                codigo_postal_remitente=v.get("codigo_postal_remitente") or None,
                telefono_remitente=v.get("telefono_remitente") or None,
                email_remitente=v.get("email_remitente") or None,
                api_key=v.get("api_key") or None, api_secret=v.get("api_secret") or None)
            if r.get("ok"):
                msg = tr("cfg.agregador_guardado", default="Configuración guardada.")
                if r.get("aviso_persistencia"):
                    msg += "\n\n" + r["aviso_persistencia"]
                mostrar_mensaje(self, tr("cfg.agregador_title", default="Agregador logístico"),
                               msg, "success")
            else:
                mostrar_mensaje(self, tr("cfg.agregador_title", default="Agregador logístico"),
                               tr("cfg.agregador_error", default="No se pudo guardar: {e}",
                                  e=r.get("mensaje") or ""), "error")

    def _de_generar_codigo_instalacion(self, ct):
        """Código de un solo uso (caduca en 30 min) para dar de alta automáticamente el ordenador
        de este centro: el instalador lo introduce en la pantalla de primer arranque de Smart
        Manager y recibe su `.env` completo (credenciales de BD compartidas de la empresa,
        código de centro, CA de TLS) sin tener que copiar nada a mano. Ver `services.provisioning`."""
        if not self._de_admin:
            return
        id_centro = ct.get("id_centro")
        from src.services import provisioning as _prov
        id_empresa = self._de_emp_mod.empresa_actual_id()
        creador_id = None
        try:
            creador_id = (sesion_global.usuario_actual or {}).get("id")
        except Exception:
            pass
        r = _prov.generar_codigo(id_centro, id_empresa, creado_por=creador_id)
        if r.get("ok"):
            mostrar_mensaje(
                self, tr("cfg.aprov_title", default="Código de instalación"),
                tr("cfg.aprov_ok_msg",
                   default="Código para {nombre} (válido 30 minutos, un solo uso):\n\n{codigo}"
                           "\n\nIntrodúcelo en la pantalla de primer arranque de Smart Manager "
                           "en el ordenador de esta tienda.",
                   nombre=ct.get("nombre_centro") or "", codigo=r["codigo"]),
                "success")
        else:
            mostrar_mensaje(
                self, tr("cfg.aprov_title", default="Código de instalación"),
                tr("cfg.aprov_error", default="No se pudo generar el código: {e}",
                   e=r.get("error") or ""), "error")

    def _de_principal_centro(self, i):
        self._de_cts_mod.marcar_principal(i); self._de_refrescar_centros()

    def _de_baja_centro(self, i):
        self._de_cts_mod.baja_centro(i); self._de_refrescar_centros()

    # --- PESTAÑA 1: GESTIÓN CAJA ---
    def _crear_selector_divisa(self):
        """Selector de DIVISA EMPRESA (global, independiente del idioma). Solo lo
        puede cambiar ADMINISTRADOR; al cambiarlo, las tablas de arqueo
        y los importes pasan a esa divisa (sin reiniciar)."""
        frame = QFrame()
        frame.setObjectName("divisaBox")
        frame.setMinimumHeight(60)  # responsive (P2): antes fijo
        frame.setStyleSheet(f"QFrame#divisaBox{{background:#161B22;border:2px solid {_BORDE};border-radius:14px;}}")
        ly = QHBoxLayout(frame)
        ly.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(tr("cfg.divisa_empresa", default="DIVISA DE LA EMPRESA:"))
        lbl.setStyleSheet("color:#6E7681;font-family:'Segoe UI';font-weight:900;font-size:12px;background:transparent;border:none;")
        # _NeonComboBox: flecha PNG + popup + hover los aporta el estilado global
        # de la app (igual que el resto de desplegables), y abre correctamente.
        combo = _NeonComboBox()
        combo.setFixedHeight(46)   # más alto: el texto de la divisa no se corta por debajo
        combo.setMinimumWidth(200)  # responsive (P2): cabe en pantallas estrechas (antes 320)
        combo.setMaximumWidth(420)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        # Petición explícita, 2026-11-16: el desplegable debe quedar JUNTO al texto de la
        # etiqueta, no empujado al extremo derecho del marco — el `addStretch()` pasa a ir
        # DESPUÉS del combo (ocupa el resto del ancho sobrante, sin separar visualmente ambos).
        ly.addWidget(lbl)
        ly.addWidget(combo)
        ly.addStretch()
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
        status_frame.setMinimumHeight(60)  # responsive (P2): antes fijo
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

        # Petición explícita, 2026-11-16: la impresión automática del ticket deja de ser una
        # casilla aquí — pasa a estar SIEMPRE activa por defecto (ver `gui.tpv`, sin gate).

        # ── Grid de botones ──────────────────────────────────────────────────
        grid = QGridLayout(); grid.setSpacing(16)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)  # responsive: 2 col elásticas

        def _mk_btn(txt, icono="", icono_img=None):
            # icono_img (QIcon) → icono de IMAGEN a la izquierda del texto (sin emoji); si no,
            # se antepone el emoji `icono` al texto (comportamiento por defecto).
            b = QPushButton(txt if icono_img else (f"{icono}  {txt}" if icono else txt))
            if icono_img is not None:
                b.setIcon(icono_img)
                b.setIconSize(QSize(52, 52))
            # Responsive (P2): expansible en ancho, alto táctil; antes era fijo 310x88.
            b.setMinimumSize(200, 72)
            b.setMaximumHeight(96)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton{{background:#161B22;border:2px solid {_CIAN};color:white;
                             border-radius:14px;font-family:'Segoe UI';font-weight:900;font-size:13px;}}
                QPushButton:hover{{background:{_CIAN};color:#0D1117;}}
                QPushButton:disabled{{background:#0D1117;border-color:{_BORDE};color:#484F58;}}
            """)
            return b

        self.btn_apertura    = _mk_btn(tr("cfg.btn_apertura_fuerte", default="ABRIR CAJA FUERTE"),    "🔑")
        self.btn_habilitar   = _mk_btn(tr("cfg.btn_habilitar", default="ABRIR CAJA REGISTRADORA"),   "🔑")
        self.btn_cierre_reg  = _mk_btn(tr("cfg.btn_cierre_reg", default="CERRAR CAJA REGISTRADORA"), "🔒")
        self.btn_cierre_fuerte = _mk_btn(tr("cfg.btn_cierre_fuerte", default="CERRAR CAJA FUERTE"),   "🔒")
        self.btn_movimiento  = _mk_btn(tr("cfg.btn_movimiento", default="TRANSFERIR EFECTIVO"),      "💸")
        self.btn_cambio_cajero = _mk_btn(tr("cfg.btn_cambio_cajero", default="CAMBIO DE CAJERO"),     "🔁")
        # "CIERRE DIARIO" retirado de aquí (petición explícita, 2026-11-16) — migrado al resumen
        # previo del cierre de caja fuerte, ver `_fn_cierre_fuerte`/`_ejecutar_cierre_diario`.

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
        sign = "+" if diff > 0 else ""
        dlg = _PinDialog("ADMINISTRADOR", f"continuar con este descuadre de {sign}{divisas.formatear(diff)}", self)
        dlg.exec()
        return dlg.verificado()

    def _autorizar_admin(self, motivo: str):
        """Exige la verificación de un perfil ADMINISTRADOR (o superior).
        Devuelve (ok: bool, nombre_usuario: str) del responsable que autoriza.

        `motivo` llega ya traducido (`tr("cfg.auth_...")`) — `_frase()` (i18n) capitaliza SIEMPRE
        la primera palabra de cualquier texto traducido, lo cual es correcto como frase suelta pero
        incorrecto aquí, porque `_PinDialog` lo inserta en mitad de una oración ("...para {motivo}.":
        petición explícita, 2026-11-24, tras ver "para Abrir la caja registradora" con mayúscula
        indebida) — se baja la inicial de vuelta antes de pasarlo."""
        motivo_frase = (motivo[:1].lower() + motivo[1:]) if motivo else motivo
        dlg = _PinDialog("ADMINISTRADOR", motivo_frase, parent=self,
                         roles_label=tr("cfg.rol_ger_admin", default="ADMINISTRADOR"))
        dlg.exec()
        return dlg.verificado(), dlg.usuario_nombre()

    def _confirmar_con_resumen(self, dlg, *, titulo, fondo_esperado=None, n_devoluciones=None,
                               texto_continuar=None) -> bool:
        """Envuelve un `_ConteoEfectivoDialog` YA aceptado (`dlg.exec()==Accepted`) con el resumen
        de confirmación (petición explícita, 2026-11-16): si el usuario pulsa "Volver", reabre el
        MISMO `dlg` (sin perder lo ya contado) y vuelve a mostrar el resumen. Devuelve True solo
        si el usuario confirmó de verdad "CONTINUAR" en el resumen."""
        while True:
            resumen = _ResumenArqueoDialog(
                titulo=titulo, detalle=dlg.get_detalle(), total=dlg.get_total(),
                fondo_esperado=fondo_esperado, n_devoluciones=n_devoluciones,
                texto_continuar=texto_continuar, parent=self)
            # Petición explícita, 2026-11-20: animación de deslizamiento de entrada/salida — ver
            # docstring de `_DialogoPantallaCompleta` sobre por qué ya es seguro combinarla con su
            # propia reafirmación de geometría (antes no lo era, mientras esa reafirmación pasaba
            # por `showMaximized()`/`showFullScreen()`).
            resultado = abrir_dialogo_deslizante(resumen, self)
            if resultado == QDialog.DialogCode.Accepted:
                return True
            if resultado == _ResumenArqueoDialog.VOLVER:
                if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
                    return False
                continue
            return False

    def _devoluciones_hoy(self, caja: str | None = None) -> int:
        """Nº de devoluciones de HOY — `caja` es el id visible ("CAJA-01"); se traduce al nº
        entero que usa `devoluciones.numero_caja` (petición explícita, 2026-11-16)."""
        try:
            from src.services.tpv import cierre_z
            num = None
            if caja:
                try:
                    num = int(str(caja).split("-")[-1])
                except (ValueError, IndexError):
                    num = None
            return cierre_z.contar_devoluciones_dia(datetime.now().strftime("%Y-%m-%d"), caja=num)
        except Exception:
            return 0

    # ── Caja: acciones ────────────────────────────────────────────────────────

    def _fn_apertura(self):
        ok, usuario = self._autorizar_admin(
            tr("cfg.auth_apertura_fuerte", default="abrir la caja fuerte"))
        if not ok:
            return
        est = self._get_caja_estado()
        ultimo = est.get("ultimos_cierres", {}).get("CAJA_FUERTE", 0.0)
        titulo_apertura_fuerte = "🔓  " + tr("cfg.conteo_apertura_fuerte", default="APERTURA — ARQUEO CAJA FUERTE")
        dlg = _ConteoEfectivoDialog(titulo_apertura_fuerte, fondo_esperado=ultimo, parent=self)
        if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
            return
        if not self._confirmar_con_resumen(dlg, titulo=titulo_apertura_fuerte, fondo_esperado=ultimo):
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
        # 1. Qué caja registradora abrir — petición explícita, 2026-11-16: desplegable con las 20
        # cajas posibles (CAJA-01..CAJA-20), cada una con su ÚLTIMO fondo conocido (o "sin fondos
        # registrados"); las YA ABIERTAS se excluyen por completo — nunca se ofrece reabrir una
        # activa. Sustituye la numeración incremental automática (bug real: cerrar una caja que
        # no fuera la última podía volver a calcular el id de una que seguía abierta).
        ids_abiertas = {c["id"] for c in est.get("cajas_activas", [])}
        dlg_caja = _SeleccionarCajaAperturaDialog(est.get("ultimos_cierres", {}), ids_abiertas, self)
        if dlg_caja.exec() != QDialog.DialogCode.Accepted:
            return
        id_caja = dlg_caja.get_caja_id()

        # 2. Autorización de ADMINISTRADOR
        if not self._autorizar_admin(
                tr("cfg.auth_abrir_caja", default="abrir la caja registradora {id}", id=id_caja))[0]:
            return
        # 3. Empleado(s) a los que se asigna la caja — petición explícita, 2026-11-16: botones de
        # perfil (uno o varios a la vez, con atajo "TODOS"), sin PIN — sustituye tanto al
        # desplegable+PIN de identificación como al checklist aparte de empleados adicionales.
        dlg_sel = _SeleccionarEmpleadosCajaDialog(
            tr("cfg.id_apertura_caja", default="Apertura de {id}", id=id_caja),
            tr("cfg.autorizados_caja_desc_multi",
               default="Marca a todos los empleados del centro que van a usar esta caja "
                       "(puedes marcar más de uno)."),
            multiple=True, parent=self)
        if abrir_dialogo_deslizante(dlg_sel, self) != QDialog.DialogCode.Accepted:
            return
        seleccionados = dlg_sel.get_seleccionados()
        usuario = seleccionados[0]["nombre"]
        usuario_id = seleccionados[0]["id"]
        responsables_id = [e["id"] for e in seleccionados]

        # Petición explícita, 2026-11-20: cuando la caja queda asignada a UN SOLO empleado, elegir
        # su perfil (botón) ya no basta como identificación — con varios empleados marcados, al
        # menos hay un acto de SELECCIÓN entre varias opciones; con uno solo, el perfil ni siquiera
        # se elige de verdad (es el único disponible), así que no había NINGUNA verificación real
        # de quién estaba abriendo la caja. Se exige su PIN de 4 dígitos antes de continuar.
        if len(seleccionados) == 1:
            dlg_pin = _PinEmpleadoDialog(
                usuario_id, usuario,
                tr("cfg.pin_motivo_abrir_caja", default="abrir {id}", id=id_caja), self)
            if dlg_pin.exec() != QDialog.DialogCode.Accepted or not dlg_pin.verificado():
                return

        # Aviso NO bloqueante: si alguno de los empleados elegidos YA tiene otra caja
        # registradora activa asignada, se confirma con el ADMINISTRADOR/SUPERADMIN si desea
        # asignarle también esta (caja adicional) en vez de impedirlo silenciosamente.
        caja_previa = next((c for c in est.get("cajas_activas", [])
                            if any(rid in (c.get("responsables_id") or [c.get("responsable_id")])
                                   for rid in responsables_id)), None)
        if caja_previa is not None:
            if not mostrar_confirmacion(
                self,
                tr("cfg.emp_ya_asignado_title", default="Empleado ya asignado"),
                tr("cfg.emp_ya_asignado_msg",
                   default="Este empleado ya tiene una caja registradora asignada ({id}). "
                           "¿Desea asignarle otra caja registradora adicional?",
                   id=caja_previa.get("id", "")),
            ):
                return

        # "Sin fondos registrados" (petición explícita, 2026-11-21): MISMO criterio exacto que ya
        # usa `_SeleccionarCajaAperturaDialog` para esa misma etiqueta — la clave está AUSENTE del
        # diccionario, no simplemente "vale 0" (una caja que de verdad se cerró alguna vez con
        # 0,00 € tiene la clave presente, con ese valor — no es "sin fondos registrados").
        sin_fondos_registrados = id_caja not in est.get("ultimos_cierres", {})
        ultimo = est.get("ultimos_cierres", {}).get(id_caja, 0.0)

        titulo_habilitar = tr("cfg.conteo_habilitar", default="HABILITAR {id} — ARQUEO INICIAL", id=id_caja)
        dlg = _ConteoEfectivoDialog(titulo_habilitar, fondo_esperado=ultimo, parent=self)
        if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
            return
        if not self._confirmar_con_resumen(dlg, titulo=titulo_habilitar, fondo_esperado=ultimo):
            return
        fondo = dlg.get_total()
        detalle = dlg.get_detalle()

        diff = fondo - ultimo if ultimo > 0 else 0.0
        if ultimo > 0:
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

        # Petición explícita, 2026-11-21: el fondo inicial de una caja SIN fondos registrados
        # (nunca usada antes) tiene que SALIR de algún sitio físico real — la caja fuerte — en vez
        # de aparecer de la nada. Se descuenta automáticamente de `fondo_caja_fuerte` y se registra
        # como una TRANSFERENCIA de efectivo más (mismo tipo de movimiento/ticket que genera
        # `_fn_movimiento` a mano, con el mismo desglose de denominaciones ya contado aquí mismo —
        # no hace falta volver a contarlo). Una caja que SÍ tiene fondo conocido se reabre con SU
        # PROPIO fondo histórico (el efectivo ya existía, vuelve a circular, no es dinero nuevo
        # saliendo de la caja fuerte) — ahí no se toca la caja fuerte, como hasta ahora.
        transferencia_fuerte = None
        if sin_fondos_registrados and fondo > 0:
            disponible_fuerte = est.get("fondo_caja_fuerte", 0.0)
            if fondo > disponible_fuerte:
                mostrar_mensaje(
                    self, tr("cfg.fondo_fuerte_insuficiente_title", default="Fondo insuficiente en caja fuerte"),
                    tr("cfg.fondo_fuerte_insuficiente_msg",
                       default="La caja fuerte solo tiene {d} € disponibles — no se puede completar "
                               "la apertura de {id} con un fondo inicial de {f} €.",
                       d=divisas.formatear(disponible_fuerte), id=id_caja, f=divisas.formatear(fondo)),
                    "warning")
                return
            est["fondo_caja_fuerte"] = round(disponible_fuerte - fondo, 2)
            transferencia_fuerte = disponible_fuerte
            est.setdefault("historial", []).append({
                "accion": "MOVIMIENTO TRANSFERENCIA", "usuario": usuario,
                "origen": tr("cfg.tk_caja_fuerte_lbl", default="CAJA FUERTE"), "destino": id_caja,
                "importe": fondo,
                "motivo": tr("cfg.motivo_transferencia_apertura",
                            default="Fondo inicial de apertura de {id}", id=id_caja),
                "hora": datetime.now().strftime("%H:%M:%S"),
            })

        responsable = usuario

        est["cajas_activas"].append({
            "id": id_caja, "responsable": responsable, "responsable_id": usuario_id,
            # "responsables_id" (petición explícita, 2026-11-16): lista de TODOS los empleados
            # autorizados a usar esta caja (siempre incluye a `responsable_id`) — `responsable`/
            # `responsable_id` se conservan tal cual para no romper nada que ya los lea (tickets,
            # historial, `_fn_cierre_reg`), pero el control de acceso real del TPV
            # (`tpv._caja_pertenece`) ya comprueba contra esta lista.
            "responsables_id": responsables_id,
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

        campos_extra = None
        extra_msg = ""
        if ultimo > 0:
            campos_extra = [
                (tr("cfg.tk_esperado", default="Esperado"), divisas.formatear(ultimo)),
                (tr("cfg.tk_contado", default="Contado"), divisas.formatear(fondo)),
                (tr("cfg.tk_descuadre", default="Descuadre"),
                 f"{'+' if diff > 0 else ''}{divisas.formatear(diff)}"),
            ]
            if abs(diff) < 0.005:
                desc_line = tr("cfg.descuadre_val", x=divisas.formatear(0))
            else:
                sign = "+" if diff > 0 else ""
                desc_line = tr("cfg.descuadre_val", default="Descuadre: {x} €", x=f"{sign}{divisas.formatear(diff)}")
            extra_msg = ("\n\n" + tr("cfg.contado_esperado", default="Contado: {c} €  ·  Esperado: {e} €",
                                     c=divisas.formatear(fondo), e=divisas.formatear(ultimo)) + "\n" + desc_line)

        self._generar_ticket_pdf(f"APERTURA {id_caja}", fondo, responsable, detalle, campos_extra=campos_extra)

        transferencia_msg = ""
        if transferencia_fuerte is not None:
            # Ticket de TRANSFERENCIA aparte (petición explícita, 2026-11-21) — mismo tipo/formato
            # que genera `_fn_movimiento` a mano (prefijo "MOV", tipo documental
            # "transferencia_efectivo"), con el MISMO desglose de denominaciones ya contado arriba
            # (nunca se vuelve a pedir recontar el mismo efectivo dos veces).
            self._generar_ticket_pdf(
                "MOVIMIENTO — TRANSFERENCIA", fondo, responsable, detalle,
                subtitulo="TRANSFERENCIA",
                campos_extra=[
                    (tr("cfg.tk_tipo", default="Tipo"), tr("cfg.tipo_transferencia", default="TRANSFERENCIA")),
                    (tr("cfg.tk_origen", default="Origen"), tr("cfg.tk_caja_fuerte_lbl", default="CAJA FUERTE")),
                    (tr("cfg.tk_destino", default="Destino"), id_caja),
                    (tr("cfg.tk_motivo", default="Motivo"),
                     tr("cfg.motivo_transferencia_apertura",
                        default="Fondo inicial de apertura de {id}", id=id_caja)),
                ])
            transferencia_msg = "\n\n" + tr(
                "cfg.transferencia_fuerte_msg",
                default="Se ha transferido {x} € desde la Caja Fuerte (quedan {r} €). Ticket de "
                        "transferencia generado.",
                x=divisas.formatear(fondo), r=divisas.formatear(est.get("fondo_caja_fuerte", 0.0)))

        mostrar_mensaje(self, tr("cfg.caja_habilitada_title", default="{id} habilitada", id=id_caja),
                        tr("cfg.caja_habilitada_msg", default="{id} abierta con fondo de {x} €.\nResponsable: {resp}", id=id_caja, x=divisas.formatear(fondo), resp=responsable) + extra_msg + transferencia_msg, "success")

    def _caja_autoriza(self, caja: dict, usuario_id) -> bool:
        """¿Puede `usuario_id` operar/cerrar `caja`? Comprueba la lista `responsables_id`
        (petición explícita, 2026-11-16 — varios empleados autorizados por caja) y, como
        respaldo (cajas antiguas abiertas ANTES de este cambio, sin `responsables_id` todavía),
        el `responsable_id` singular de siempre. Mismo criterio que `tpv._caja_pertenece`."""
        if usuario_id is None:
            return False
        responsables_id = caja.get("responsables_id")
        if responsables_id:
            return any(str(rid) == str(usuario_id) for rid in responsables_id)
        rid = caja.get("responsable_id")
        return rid is not None and str(rid) == str(usuario_id)

    def _fn_cierre_reg(self):
        est = self._get_caja_estado()
        cajas = est.get("cajas_activas", [])
        if not cajas:
            return

        # 1. Autorización de ADMINISTRADOR
        if not self._autorizar_admin(
                tr("cfg.auth_cerrar_caja", default="cerrar una caja registradora"))[0]:
            return

        # 2. Selección de caja (obligatoria si hay más de una; automática si solo hay una) —
        # petición explícita, 2026-11-16: se resuelve ANTES que el empleado (al revés que antes)
        # porque ahora el paso de empleado depende de CUÁNTOS están asignados a ESTA caja.
        if len(cajas) == 1:
            caja_data = cajas[0]
        else:
            dlg_sel = _SeleccionarCajaDialog(cajas, self)
            if dlg_sel.exec() != QDialog.DialogCode.Accepted:
                return
            caja_data = next((c for c in cajas if c["id"] == dlg_sel.get_caja_id()), cajas[0])

        id_caja = caja_data["id"]

        # 3. Empleado que cierra la caja — petición explícita, 2026-11-16: SOLO si esta caja tiene
        # MÁS DE UN empleado asignado se pregunta (botones de perfil, uno a la vez, SIN PIN,
        # restringidos a los empleados realmente autorizados en esta caja — no todo el centro).
        # Con un único empleado asignado, su nombre ya es `caja_data["responsable"]` (no hay nada
        # que elegir), pero SÍ se le exige el PIN (petición explícita, 2026-11-20 — ver más abajo).
        responsables_id = caja_data.get("responsables_id") or [caja_data.get("responsable_id")]
        if len(responsables_id) <= 1:
            usuario = caja_data.get("responsable")
            usuario_id = caja_data.get("responsable_id")
            # Petición explícita, 2026-11-20: con un ÚNICO empleado asignado no hay paso de
            # selección (se usa directamente, sin mostrar ningún diálogo — ver comentario de
            # arriba) y por tanto tampoco ninguna verificación real de quién está cerrando la
            # caja. Se exige su PIN de 4 dígitos antes de continuar al arqueo.
            dlg_pin = _PinEmpleadoDialog(
                usuario_id, usuario,
                tr("cfg.pin_motivo_cerrar_caja", default="cerrar {id}", id=id_caja), self)
            if dlg_pin.exec() != QDialog.DialogCode.Accepted or not dlg_pin.verificado():
                return
        else:
            from src.db.usuario import obtener_usuario
            empleados_caja = []
            for rid in responsables_id:
                u = obtener_usuario(rid)
                empleados_caja.append({"id": rid, "nombre": (u or {}).get("nombre") or str(rid)})
            dlg_emp = _SeleccionarEmpleadosCajaDialog(
                tr("cfg.id_cierre_reg", default="Cierre de caja registradora"),
                tr("cfg.cierre_quien_desc", default="Indica qué empleado está cerrando la caja."),
                multiple=False, parent=self, empleados=empleados_caja)
            if abrir_dialogo_deslizante(dlg_emp, self) != QDialog.DialogCode.Accepted:
                return
            usuario = dlg_emp.get_empleado_nombre()
            usuario_id = dlg_emp.get_empleado_id()

        # 4. Arqueo final
        titulo_cierre_reg = "🔒  " + tr("cfg.conteo_cierre_caja", default="CIERRE {id} — ARQUEO FINAL", id=id_caja)
        dlg = _ConteoEfectivoDialog(
            titulo_cierre_reg,
            fondo_esperado=caja_data.get("fondo", 0.0),
            parent=self
        )
        if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
            return
        # Petición explícita, 2026-11-16: nº de devoluciones de HOY en ESTA caja, en el resumen
        # previo al cierre de caja registradora.
        if not self._confirmar_con_resumen(
                dlg, titulo=titulo_cierre_reg, fondo_esperado=caja_data.get("fondo", 0.0),
                n_devoluciones=self._devoluciones_hoy(id_caja)):
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
        # Hallazgo real, 2026-11-16 (bug confirmado): cerrar UNA caja registradora mientras quedan
        # OTRAS abiertas forzaba el estado global a "CIERRE_CAJAS" — y ese estado deshabilita
        # "Abrir caja registradora" (ver `_refresh_caja_ui`). Cerrar una caja (p. ej. fin de turno
        # de un cajero) es una acción normal e independiente: NO implica que la tienda quiera
        # cerrar todas las demás ni la caja fuerte. Con cajas restantes, el estado se queda TAL
        # CUAL estaba (sigue operativa); solo al cerrar la ÚLTIMA se vuelve a CAJA_FUERTE_ABIERTA
        # (habilita "Cerrar caja fuerte" sin tener que reabrirla).
        if n_restantes == 0:
            est["estado"] = "CAJA_FUERTE_ABIERTA"
        else:
            est["estado"] = estado_anterior
        est.setdefault("ultimos_cierres", {})[id_caja] = total_contado
        est["historial"].append({
            "accion": f"CIERRE {id_caja}", "usuario": usuario,
            "hora": datetime.now().strftime("%H:%M:%S"), "importe": total_contado,
        })
        self._set_caja_estado(est)
        self._refresh_caja_ui()
        self._generar_ticket_pdf(f"CIERRE {id_caja}", total_contado, usuario, detalle)
        if n_restantes == 0:
            # Ambos siguen siendo ciertos con el estado "CAJA_FUERTE_ABIERTA"/n_cajas==0: se puede
            # tanto cerrar la caja fuerte como habilitar una nueva caja registradora (petición
            # explícita, 2026-11-16 — cerrar la última caja no debe bloquear abrir otra). Mismos
            # textos cataloged ya existentes (sin tocar sus claves), solo concatenados.
            msg = (tr("cfg.cierre_msg_all", default="Todas las cajas cerradas. Ya puede realizar el cierre de caja fuerte.")
                  + "\n" + tr("cfg.cierre_msg_zero", default="{id} cerrada. Puede habilitar una nueva caja registradora.", id=id_caja))
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

        # 0. Autorización de ADMINISTRADOR (responsable de turno → firma del ticket)
        ok_aut, responsable_turno = self._autorizar_admin(
            tr("cfg.auth_cambio_cajero", default="realizar un cambio de cajero"))
        if not ok_aut:
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
        titulo_cambio_cajero = "🔁  " + tr("cfg.conteo_cambio_cajero", default="CAMBIO DE CAJERO {id} — ARQUEO", id=id_caja)
        dlg = _ConteoEfectivoDialog(
            titulo_cambio_cajero, fondo_esperado=caja_data.get("fondo", 0.0), parent=self)
        if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
            return
        if not self._confirmar_con_resumen(
                dlg, titulo=titulo_cambio_cajero, fondo_esperado=caja_data.get("fondo", 0.0)):
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
                # Hallazgo real, 2026-11-16: si el cajero ENTRANTE no estaba ya entre los
                # `responsables_id` de esta caja (p. ej. era un refuerzo nuevo, no de los
                # autorizados al abrirla), sin esto `_caja_pertenece`/`_caja_autoriza` lo
                # rechazarían pese a que el sistema acaba de decirle que la caja ya es suya — el
                # traspaso quedaría a medias (ticket/pantalla dicen una cosa, el acceso real
                # otra). Se calcula ANTES de pisar `responsable_id` de abajo (si no hubiera
                # `responsables_id` todavía, el respaldo debe ser el SALIENTE de antes del
                # traspaso, no el entrante). Se AÑADE, nunca se quita a nadie (el saliente u
                # otros autorizados conservan su acceso, tal como ya tenían).
                responsables_id = list(c.get("responsables_id") or [c.get("responsable_id")])
                if entrante_id is not None and entrante_id not in responsables_id:
                    responsables_id.append(entrante_id)
                c["responsable"] = entrante
                c["responsable_id"] = entrante_id
                c["responsables_id"] = responsables_id
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
        # Ticket de cambio de cajero: detalle + recuento + firmas (cajero saliente ENCIMA,
        # responsable de turno DEBAJO).
        self._generar_ticket_pdf(
            f"CAMBIO CAJERO {id_caja}", total_contado, f"{saliente} → {entrante}", detalle,
            subtitulo=tr("cfg.tk_caja_x", default="Caja {id}", id=id_caja),
            campos_extra=[
                (tr("cfg.tk_caja", default="Caja"), id_caja),
                (tr("cfg.tk_cajero_saliente", default="Cajero saliente"), saliente),
                (tr("cfg.tk_cajero_entrante", default="Cajero entrante"), entrante),
                (tr("cfg.tk_esperado", default="Esperado"), divisas.formatear(fondo_esperado)),
                (tr("cfg.tk_contado", default="Contado"), divisas.formatear(total_contado)),
            ],
            firmas=[
                (tr("cfg.tk_firma_saliente", default="Firma cajero saliente"), saliente),
                (tr("cfg.tk_firma_responsable", default="Firma responsable de turno"), responsable_turno),
            ])

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
        """True si el empleado identificado puede traspasar esta caja como cajero SALIENTE.
        Hallazgo real, 2026-11-16: antes solo comprobaba el `responsable_id` SINGULAR —
        inconsistente con el resto del sistema (venta/cierre) desde que una caja admite VARIOS
        empleados autorizados (`responsables_id`, ver `_caja_autoriza`): un empleado legítimo de
        esa caja que no fuera el primero en seleccionarse al abrirla se veía rechazado aquí. Ahora
        delega en `_caja_autoriza` — cualquiera de los autorizados puede iniciar el traspaso."""
        if id_empleado is not None:
            return self._caja_autoriza(caja, id_empleado)
        a = str(caja.get("responsable") or "").strip().casefold()
        b = str(nombre or "").strip().casefold()
        return bool(b) and a == b

    def _fn_cierre_fuerte(self):
        ok, usuario = self._autorizar_admin(
            tr("cfg.auth_cierre_fuerte", default="cerrar la caja fuerte"))
        if not ok:
            return
        est = self._get_caja_estado()

        titulo_cierre_fuerte = "🏦  " + tr("cfg.conteo_cierre_fuerte", default="CIERRE CAJA FUERTE — ARQUEO FINAL")
        dlg = _ConteoEfectivoDialog(
            titulo_cierre_fuerte,
            fondo_esperado=est.get("fondo_caja_fuerte", 0.0),
            parent=self
        )
        if abrir_dialogo_deslizante(dlg, self) != QDialog.DialogCode.Accepted:
            return
        # Petición explícita, 2026-11-16: el botón independiente "CIERRE DIARIO" se retiró de la
        # ventana principal — el resumen previo de ESTE cierre (el último paso antes del cierre
        # diario) es ahora el que, al "continuar", dispara directamente el cierre diario
        # (`_ejecutar_cierre_diario`, más abajo). También muestra el nº de devoluciones de HOY
        # (todas las cajas).
        if not self._confirmar_con_resumen(
                dlg, titulo=titulo_cierre_fuerte, fondo_esperado=est.get("fondo_caja_fuerte", 0.0),
                n_devoluciones=self._devoluciones_hoy(),
                texto_continuar=tr("cfg.resumen_arqueo_generar_cierre_diario",
                                   default="GENERAR CIERRE DIARIO")):
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
        # Petición explícita, 2026-11-16: el cierre diario se dispara aquí, fusionado con el
        # cierre de caja fuerte (ya confirmado en el resumen de arriba — `confirmar=False`).
        self._ejecutar_cierre_diario(confirmar=False)

    def _fn_movimiento(self):
        ok, usuario = self._autorizar_admin(
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
            subtitulo=res["tipo"],
            campos_extra=[
                (tr("cfg.tk_tipo", default="Tipo"), res["tipo"]),
                (tr("cfg.tk_origen", default="Origen"), res["origen_txt"]),
                (tr("cfg.tk_destino", default="Destino"), res["destino_txt"]),
                (tr("cfg.tk_motivo", default="Motivo"), res.get("motivo") or "—"),
            ])

        # Construir mensaje informativo con saldos actualizados
        lineas = [tr("cfg.mov_line1", default="{tipo} de {x} € registrado.", tipo=res['tipo'], x=divisas.formatear(imp)) + "\n"]
        lineas.append(tr("cfg.mov_origen", default="Origen:  {x}", x=res['origen_txt']))
        lineas.append(tr("cfg.mov_destino", default="Destino: {x}", x=res['destino_txt']) + "\n")
        lineas.append(tr("cfg.mov_caja_fuerte", default="Caja Fuerte → {x} €", x=divisas.formatear(est.get('fondo_caja_fuerte', 0.0))))
        for c in est.get("cajas_activas", []):
            lineas.append(f"{c['id']} → {divisas.formatear(c.get('fondo', 0.0))}")
        mostrar_mensaje(self, tr("cfg.mov_registrado_title", default="Movimiento registrado"), "\n".join(lineas), "success")

    def _generar_ticket_pdf(self, tipo: str, importe: float, responsable: str, detalle: list = None,
                            *, firmas=None, campos_extra=None, subtitulo=None):
        """Genera el ticket de OPERACIÓN de caja (documento interno de empresa) en el MISMO formato
        recibo que el ticket de compra: logo, cabecera fiscal, tienda+referencia, nº de ticket ÚNICO,
        empleado, fecha/hora exactas, recuento de billetes/monedas y, si procede, firmas. Sin códigos
        de barras ni QR; margen izquierdo ampliado para archivar. Lo comparten apertura/cierre de caja
        fuerte y registradoras, movimiento de efectivo y cambio de cajero. Devuelve la ruta o None."""
        try:
            from src.utils.impresion import generar_ticket_operacion_pdf
            from src.utils.ticket_data import construir_datos_operacion
        except Exception:
            LOG_DOCUMENTOS.exception("Ticket de operación no disponible")
            return None

        # Prefijo/título de trazabilidad según el tipo de operación.
        t = str(tipo or "").upper()
        if t.startswith("APERTURA CAJA FUERTE"):
            pref, titulo, caja = "ACF", tr("cfg.tk_apertura_fuerte", default="APERTURA CAJA FUERTE"), None
        elif t.startswith("APERTURA"):
            pref, titulo, caja = "ACR", tr("cfg.tk_apertura_caja", default="APERTURA CAJA REGISTRADORA"), tipo.replace("APERTURA", "").strip()
        elif t.startswith("CIERRE CAJA FUERTE"):
            pref, titulo, caja = "CCF", tr("cfg.tk_cierre_fuerte", default="CIERRE CAJA FUERTE"), None
        elif t.startswith("CIERRE"):
            pref, titulo, caja = "CCR", tr("cfg.tk_cierre_caja", default="CIERRE CAJA REGISTRADORA"), tipo.replace("CIERRE", "").strip()
        elif t.startswith("CAMBIO CAJERO"):
            pref, titulo, caja = "CBC", tr("cfg.tk_cambio_cajero", default="CAMBIO DE CAJERO"), tipo.replace("CAMBIO CAJERO", "").strip()
        elif t.startswith("MOVIMIENTO"):
            pref, titulo, caja = "MOV", tr("cfg.tk_movimiento", default="MOVIMIENTO DE EFECTIVO"), None
        else:
            pref, titulo, caja = "OP", str(tipo), None

        secciones = []
        if campos_extra:
            secciones.append((tr("cfg.tk_detalle_op", default="DETALLE"), list(campos_extra)))
        total_label = (tr("cfg.tk_total_recuento", default="TOTAL RECUENTO") if detalle
                       else tr("cfg.tk_importe", default="IMPORTE"))

        datos = construir_datos_operacion(
            titulo, responsable, prefijo=pref, subtitulo=subtitulo, caja=caja or None,
            secciones=secciones, denominaciones=detalle or [],
            total=(total_label, importe), firmas=firmas)

        carpeta = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..",
                                                 "documentos", "tickets_operaciones"))
        os.makedirs(carpeta, exist_ok=True)
        ref = (datos.get("operacion") or {}).get("ticket_num") or datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(carpeta, f"{ref}.pdf")
        try:
            generar_ticket_operacion_pdf(datos, ruta)
        except Exception:
            LOG_DOCUMENTOS.exception("Error generando ticket de operación PDF (caja)")
            return None
        # Centro documental: registrar el ticket (trazabilidad por su referencia única). NO se abre el PDF
        # automáticamente: el ticket queda disponible en Documentos (punto rojo de aviso) y es el usuario
        # quien decide cuándo abrirlo. Vale para apertura/cierre de caja fuerte y registradoras, cambio de
        # cajero y movimiento de efectivo (todos usan este generador único).
        # Tipo documental por operación (pestaña propia en el Centro Documental — a petición del
        # usuario): NUNCA "ticket" a secas, ese tipo queda reservado en exclusiva a los tickets de
        # COMPRA del TPV (excluidos siempre del Centro Documental, ver `db.documentos.listar_documentos`).
        # Estos SÍ deben verse ahí (son documentos internos que se queda la empresa, con su zona de
        # perforación) y necesitan su propio tipo para tener pestaña dedicada.
        _tipo_doc = {
            "ACF": "caja_fuerte", "CCF": "caja_fuerte",
            "ACR": "caja_registradora", "CCR": "caja_registradora",
            "CBC": "cambio_cajero",
            "MOV": "transferencia_efectivo",
        }.get(pref, "otros")
        try:
            from src.db import documentos as _docreg
            _docreg.registrar_documento(ruta, tipo=_tipo_doc, nombre=f"{titulo} — {ref}",
                                        referencia=ref, importe=importe, trabajador=responsable,
                                        estado="generado")
        except Exception:
            pass
        return ruta

    def _ejecutar_cierre_diario(self, *, confirmar=True) -> bool:
        """CIERRE DIARIO — recopila los hechos económicos del día (todas las cajas), hace arqueo,
        persiste un Cierre Z inmutable/auditable, procesa la contabilidad y genera el ticket-resumen
        PDF con la facturación del día. Reutiliza el MOTOR ÚNICO `services.tpv.cierre_z` (N7).

        Petición explícita, 2026-11-16: el botón independiente "CIERRE DIARIO" se retiró de la
        ventana principal de Gestión caja — ahora se dispara SOLO desde el resumen previo del
        cierre de caja fuerte (`_fn_cierre_fuerte`), que ya pidió su propia confirmación
        ("GENERAR CIERRE DIARIO"); por eso `confirmar=False` en ese caso, para no pedir una
        segunda confirmación redundante. Devuelve True si el cierre se generó correctamente."""
        try:
            from src.services.tpv import cierre_z
        except Exception as e:
            mostrar_mensaje(self, tr("cfg.cierre_diario", default="Cierre diario"),
                            tr("cfg.cierre_diario_no_disp", default="Módulo no disponible: {e}", e=str(e)), "error")
            return False

        # Precondición: no puede haber cajas registradoras activas (el resto del tiempo está
        # disponible, incluso con la caja fuerte abierta, y es reimprimible por si hubo un error).
        est = self._get_caja_estado()
        if est.get("cajas_activas"):
            mostrar_mensaje(
                self, tr("cfg.cierre_diario", default="Cierre diario"),
                tr("cfg.cierre_diario_bloqueado",
                   default="Antes del cierre diario debe cerrar todas las cajas registradoras."),
                "warning")
            return False

        hoy = datetime.now().strftime("%Y-%m-%d")
        id_tienda = ""
        try:
            from src.db.empresa import tienda_actual_id
            id_tienda = tienda_actual_id() or ""
        except Exception:
            pass
        usuario = ""
        try:
            if sesion_global and sesion_global.usuario_actual:
                usuario = sesion_global.obtener_nombre()
        except Exception:
            pass

        # Reimprimible: si ya existe el cierre de hoy, se regenera su MISMO ticket (mismo nº y hash)
        # por si hubo un error humano. No se crea un duplicado (lo gestiona generar_cierre_z).
        # El arqueo YA se hizo al cerrar las registradoras y la caja fuerte: el CIERRE DIARIO NO
        # vuelve a pedirlo. Solo confirma la impresión del ticket con los hechos económicos del día.
        fondo_inicial = float(est.get("fondo_caja_fuerte", 0.0) or 0.0)
        res = cierre_z.resumen_dia(hoy, caja=None)
        esperado = round(fondo_inicial + res.get("cobros", {}).get("efectivo", 0.0), 2)

        if confirmar and not mostrar_confirmacion(
                self, tr("cfg.cierre_diario", default="Cierre diario"),
                tr("cfg.cierre_diario_confirm",
                   default=("¿Generar e imprimir el ticket de CIERRE DIARIO con todos los hechos "
                            "económicos de hoy?\n\nFacturación del día: {fact}\nNº de tickets: {tk}\n\n"
                            "Se contabilizarán los asientos del día en cola."),
                   fact=divisas.formatear(res.get("total_cobrado", 0)), tk=res.get("num_tickets", 0))):
            return False

        # Sin nuevo arqueo: el efectivo declarado = esperado (ya conciliado en los cierres previos).
        cierre = cierre_z.generar_cierre_z(hoy, esperado, usuario=usuario, id_tienda=id_tienda,
                                           caja=None, fondo_inicial=fondo_inicial)
        if not cierre:
            mostrar_mensaje(self, tr("cfg.cierre_diario", default="Cierre diario"),
                            tr("cfg.cierre_diario_err", default="No se pudo generar el cierre diario."), "error")
            return False

        post = cierre.get("posting") or {}
        if cierre.get("duplicado"):
            # Reimpresión del cierre ya existente (mismo nº y hash).
            msg = tr(
                "cfg.cierre_diario_reimpreso",
                default=("CIERRE DIARIO Nº {n} — {fecha}  (reimpresión)\n\n"
                         "Facturación del día: {fact}\n"
                         "Nº de tickets (clientes): {tk}\n\n"
                         "Se ha regenerado el mismo ticket (sin duplicar el cierre)."),
                n=f"{int(cierre.get('numero') or 0):05d}", fecha=hoy,
                fact=divisas.formatear(cierre.get("total_cobrado", 0)),
                tk=res.get("num_tickets", 0))
        else:
            msg = tr(
                "cfg.cierre_diario_ok",
                default=("CIERRE DIARIO Nº {n} — {fecha}\n\n"
                         "Facturación del día: {fact}\n"
                         "Nº de tickets (clientes): {tk}\n"
                         "Ticket medio: {tm}\n"
                         "Asientos contabilizados (excl. nóminas): {asi}\n\n"
                         "Ticket generado y archivado en el Centro Documental."),
                n=f"{int(cierre.get('numero') or 0):05d}", fecha=hoy,
                fact=divisas.formatear(cierre.get("total_cobrado", 0)),
                tk=res.get("num_tickets", 0), tm=divisas.formatear(res.get("ticket_medio", 0)),
                asi=post.get("asientos", 0))
        mostrar_mensaje(self, tr("cfg.cierre_diario_gen", default="Cierre diario generado"),
                        msg, "success")

        ruta = cierre.get("ruta_pdf")
        if ruta and os.path.exists(ruta):
            try:
                os.startfile(ruta)  # noqa: S606 — abrir el ticket PDF del cierre (Windows)
            except Exception:
                pass
        self._refresh_caja_ui()
        return True

    # --- PESTAÑAS 4/5 (HORARIO EMPLEADOS / FICHAJES) EXTRAÍDAS ---
    # Restructuración 2026-09: movidas a ventanas propias del menú principal —
    # HorariosWindow (src/gui/horarios_gui.py) y FichajesWindow (src/gui/fichajes_gui.py).
    # Ya no son pestañas de Configuración (ver placeholders en self._page_builders/self.btns).

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
                background: #0E1117;
                color: {_CIAN};
                border: 2px solid {_CIAN};
                border-radius: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: #0E1117;
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


    # --- PESTAÑA 2: PLAZO DEVOLUCIÓN ---
    def _crear_page_plazo_devolucion(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(50, 40, 50, 30)
        ly.setSpacing(18)

        title = QLabel(tr("cfg.plazo_title", default="CONFIGURACIÓN DE PLAZOS Y TICKETS"))
        title.setStyleSheet(f"color: {_CIAN}; font-size: 22px; font-weight: 900;")
        ly.addWidget(title)

        # Subpestañas (petición explícita, 2026-11-23: unificar el aspecto con el resto de la app —
        # antes era un trío de QPushButton a mano con relleno cian, distinto del estándar de
        # subpestañas de CCP/EnterpriseTabs; ahora es el propio componente compartido).
        tabs_devol = EnterpriseTabs()
        tabs_devol.addTab(self._modulo_periodo(), tr("cfg.mod_periodo", default="PERIODO DE DEVOLUCIÓN"))
        tabs_devol.addTab(self._modulo_baneados(), tr("cfg.mod_baneados", default="ARTÍCULOS BANEADOS"))
        tabs_devol.addTab(self._modulo_descuento(), tr("cfg.mod_descuento", default="ARTÍCULOS CON DESCUENTO"))
        ly.addWidget(tabs_devol, 1)
        return page

    def _btn_guardar_verde(self, slot):
        b = QPushButton(tr("cfg.save_changes", default="Guardar cambios"))
        b.setFixedSize(200, 45); b.setCursor(Qt.CursorShape.PointingHandCursor)
        # `padding:0` explícito: SIN esto, un contenedor padre con padding propio (p. ej. el
        # QFrame#form de "Artículos con descuento", `padding:24px`) lo hereda por cascada de Qt CSS
        # y, sobre un botón de ALTO FIJO (45px), deja el área de contenido en negativo — el texto
        # desaparece por completo (bug real: "al botón verde no se le ve el texto").
        b.setStyleSheet("QPushButton{background:#0E1117;color:#238636;border:2px solid #238636;border-radius:10px;"
                        "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0;}"
                        "QPushButton:hover{background:#238636;color:#0E1117;}")
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
            logging.getLogger("configuracion").warning("No se pudo guardar config_ticket: %s", e)
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
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:11px;background:transparent;border:none;")
        v.addWidget(sub)

        fila = QHBoxLayout(); fila.setSpacing(10)
        self.inp_ban = QLineEdit(); self.inp_ban.setFixedHeight(40)
        self.inp_ban.setPlaceholderText(tr("cfg.ban_ph", default="Buscar por EAN o nombre del artículo…"))
        self.inp_ban.setStyleSheet(f"QLineEdit{{background:#0D1117;color:white;border:2px solid {_CIAN};border-radius:10px;padding:0 14px;font-size:14px;}}")
        self.inp_ban.returnPressed.connect(self._buscar_para_banear)
        instalar_sugerencias_articulo(self.inp_ban)
        bb = QPushButton("🔍")
        bb.setToolTip(tr("cfg.ban_buscar", default="Buscar / banear"))
        bb.setFixedSize(48, 48)  # evita que el glifo emoji 🔍 se vea recortado
        bb.setCursor(Qt.CursorShape.PointingHandCursor)
        bb.setStyleSheet(f"QPushButton{{background:#161B22;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;font-size:18px;padding:0;}}QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
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
        if "–" in term:  # viene del autocompletado "CÓDIGO – NOMBRE"
            term = term.split("–")[0].strip()
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

    # ── Módulo 3: bloqueo de devolución por % de descuento vendido ───────────
    def _modulo_descuento(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(14)

        t = QLabel("🏷  " + tr("cfg.desc_titulo", default="ARTÍCULOS CON DESCUENTO"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;background:transparent;border:none;")
        v.addWidget(t)
        sub = QLabel(tr("cfg.desc_sub",
                        default="Define el % mínimo de descuento de venta a partir del cual (incluido) "
                                "NINGÚN artículo admite devolución en el TPV, sea cual sea su EAN — "
                                "independiente de la lista de artículos baneados."))
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:11px;background:transparent;border:none;")
        v.addWidget(sub)

        form = QFrame()
        form.setStyleSheet(f"background:{_PANEL_BG};border-radius:20px;padding:24px;border:2px solid {_BORDE};")
        form_ly = QVBoxLayout(form); form_ly.setSpacing(14)

        self.lbl_desc_estado = QLabel("")
        self.lbl_desc_estado.setWordWrap(True)
        self.lbl_desc_estado.setStyleSheet("font-family:'Segoe UI';font-weight:900;font-size:13px;background:transparent;border:none;")
        form_ly.addWidget(self.lbl_desc_estado)

        fila = QHBoxLayout(); fila.setSpacing(12)
        fila.addWidget(QLabel(tr("cfg.desc_umbral_label", default="% descuento mínimo que bloquea la devolución:"),
                             styleSheet="color:white;font-weight:900;background:transparent;border:none;"))
        self.spin_desc_umbral = QDoubleSpinBox()
        self.spin_desc_umbral.setRange(0.0, 100.0)
        self.spin_desc_umbral.setDecimals(0)
        self.spin_desc_umbral.setSuffix(" %")
        self.spin_desc_umbral.setFixedSize(140, 48)
        self.spin_desc_umbral.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_desc_umbral.setStyleSheet(
            f"QDoubleSpinBox{{background:#0D1117;color:white;border:2px solid {_CIAN};border-radius:10px;"
            "font-family:'Segoe UI';font-weight:900;font-size:16px;padding:4px 10px;}}")
        fila.addWidget(self.spin_desc_umbral)
        fila.addStretch()
        form_ly.addLayout(fila)

        btns = QHBoxLayout(); btns.setSpacing(14)
        btn_desactivar = QPushButton("🚫  " + tr("cfg.desc_desactivar", default="DESACTIVAR BLOQUEO"))
        btn_desactivar.setFixedHeight(44); btn_desactivar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_desactivar.setStyleSheet(
            "QPushButton{background:#0E1117;color:#F85149;border:2px solid #F85149;border-radius:10px;"
            "font-weight:900;font-size:12px;padding:0 18px;}"
            "QPushButton:hover{background:#F85149;color:#0E1117;}")
        btn_desactivar.clicked.connect(self._desactivar_descuento_bloqueo)
        btns.addWidget(btn_desactivar)
        btns.addStretch()
        btns.addWidget(self._btn_guardar_verde(self._guardar_descuento_bloqueo))
        form_ly.addLayout(btns)

        v.addWidget(form)
        v.addStretch()
        self._refrescar_estado_descuento_bloqueo()
        return w

    def _refrescar_estado_descuento_bloqueo(self):
        try:
            from src.db.config_ticket import obtener_config_ticket
            umbral = obtener_config_ticket().get("descuento_min_bloqueo")
        except Exception:
            umbral = None
        if umbral:
            self.spin_desc_umbral.setValue(float(umbral))
            self.lbl_desc_estado.setText(
                "✔  " + tr("cfg.desc_estado_activo",
                          default="Bloqueo ACTIVO: no se admite devolver artículos vendidos con "
                                  "{u:.0f}% de descuento o más.", u=float(umbral)))
            self.lbl_desc_estado.setStyleSheet(
                "color:#3FB950;font-family:'Segoe UI';font-weight:900;font-size:13px;background:transparent;border:none;")
        else:
            self.spin_desc_umbral.setValue(0.0)
            self.lbl_desc_estado.setText(
                "—  " + tr("cfg.desc_estado_inactivo",
                          default="Bloqueo DESACTIVADO: ningún artículo se excluye de la devolución por descuento."))
            self.lbl_desc_estado.setStyleSheet(
                "color:#8B949E;font-family:'Segoe UI';font-weight:900;font-size:13px;background:transparent;border:none;")

    def _guardar_descuento_bloqueo(self):
        umbral = self.spin_desc_umbral.value()
        if umbral <= 0:
            mostrar_mensaje(self, tr("cfg.desc_err_t", default="Valor no válido"),
                            tr("cfg.desc_err_cero",
                               default="Introduce un % mayor que 0, o usa DESACTIVAR BLOQUEO si no "
                                       "quieres aplicar esta política."), "warning")
            return
        try:
            from src.db.config_ticket import guardar_config_ticket
            ok = guardar_config_ticket(descuento_min_bloqueo=float(umbral))
        except Exception as e:
            ok = False
            logging.getLogger("configuracion").warning("No se pudo guardar descuento_min_bloqueo: %s", e)
        if ok:
            self._refrescar_estado_descuento_bloqueo()
            mostrar_mensaje(self, tr("cfg.guardado_t", default="Guardado"),
                            tr("cfg.desc_ok_guardar",
                               default="Bloqueo activado: desde ahora no se admiten devoluciones de "
                                       "artículos vendidos con {u:.0f}% de descuento o más.", u=float(umbral)),
                            "info")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.desc_err_guardar",
                               default="No se pudo guardar la configuración. Inténtalo de nuevo."), "error")

    def _desactivar_descuento_bloqueo(self):
        try:
            from src.db.config_ticket import obtener_config_ticket
            if not obtener_config_ticket().get("descuento_min_bloqueo"):
                mostrar_mensaje(self, tr("cfg.desc_info_t", default="Sin cambios"),
                                tr("cfg.desc_ya_inactivo", default="El bloqueo ya estaba desactivado."), "info")
                return
        except Exception:
            pass
        if mostrar_confirmacion and not mostrar_confirmacion(
            self, tr("cfg.desc_desact_t", default="Desactivar bloqueo"),
            tr("cfg.desc_desact_msg",
               default="¿Seguro que quieres desactivar el bloqueo de devolución por descuento?")):
            return
        try:
            from src.db.config_ticket import guardar_config_ticket
            ok = guardar_config_ticket(descuento_min_bloqueo=None)
        except Exception as e:
            ok = False
            logging.getLogger("configuracion").warning("No se pudo desactivar descuento_min_bloqueo: %s", e)
        if ok:
            self._refrescar_estado_descuento_bloqueo()
            mostrar_mensaje(self, tr("cfg.desc_desact_ok_t", default="Bloqueo desactivado"),
                            tr("cfg.desc_desact_ok",
                               default="Ya no se bloqueará ninguna devolución por motivo de descuento."), "info")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.desc_err_guardar",
                               default="No se pudo guardar la configuración. Inténtalo de nuevo."), "error")

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

        # Email AHORA OBLIGATORIO (antes opcional): necesario para que el empleado pueda ser
        # sugerido/insertado como destinatario interno en circulares/encuestas
        # (`usuarios_internos.listar_usuarios_empresa` excluye a quien no tenga email — ver
        # migración 0287). Validado como requerido en `ejecutar_creacion_usuario`, igual que
        # nombre/contraseña.
        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText(
            tr("cfg.ph_email", default="EMAIL (para circulares/encuestas)"))
        self.input_email.setStyleSheet(input_css)

        self.combo_perfil = _PerfilDropdown(["OPERARIO", "ADMINISTRADOR", "SUPERADMIN"])

        form_layout.addWidget(self.input_nombre)
        form_layout.addWidget(self.input_pass)
        form_layout.addWidget(self.input_pass2)
        form_layout.addWidget(self.input_email)
        form_layout.addWidget(self.combo_perfil)

        btn_guardar = QPushButton(tr("cfg.register_emp", default="REGISTRAR EMPLEADO"))
        btn_guardar.setFixedHeight(50)
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.setStyleSheet(f"""
            QPushButton {{
                background-color: #0E1117;
                color: {_CIAN};
                font-weight: bold;
                border-radius: 10px;
                border: 2px solid {_CIAN};
            }}
            QPushButton:hover {{
                background-color: {_CIAN};
                color: #0E1117;
            }}
        """)
        btn_guardar.clicked.connect(self.ejecutar_creacion_usuario)
        form_layout.addWidget(btn_guardar)
        form_layout.addStretch()

        # Tabla Derecha
        tabla_container = QFrame()
        tabla_ly = QVBoxLayout(tabla_container)

        self.tabla_usuarios = QTableWidget()
        self.tabla_usuarios.setColumnCount(4)
        self.tabla_usuarios.setHorizontalHeaderLabels([
            tr("cfg.col_id", default="ID"),
            tr("cfg.col_employee", default="EMPLEADO"),
            tr("cfg.col_level", default="NIVEL"),
            tr("cfg.col_centro", default="CENTRO"),
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

        btn_editar_email = QPushButton("✉️  " + tr("cfg.edit_email", default="EDITAR EMAIL"))
        btn_editar_email.setFixedHeight(44)
        btn_editar_email.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_editar_email.setStyleSheet(f"""
            QPushButton {{
                background: #0D1117; color: {_CIAN};
                border: 2px solid {_CIAN}; border-radius: 12px;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 14px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_editar_email.clicked.connect(self.ejecutar_editar_email)

        btn_editar_perfil = QPushButton("📝  " + tr("cfg.edit_profile", default="EDITAR PERFIL"))
        btn_editar_perfil.setFixedHeight(44)
        btn_editar_perfil.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_editar_perfil.setStyleSheet(f"""
            QPushButton {{
                background: #0D1117; color: {_CIAN};
                border: 2px solid {_CIAN}; border-radius: 12px;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 14px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_editar_perfil.clicked.connect(self.ejecutar_editar_perfil)

        # 🔗 Vincular a centro (Sistema de Centros, Parte E) — esta pestaña ya es SUPERADMIN-only
        # (gateada a nivel de sidebar), así que se muestra siempre, sin comprobación extra de rol.
        btn_vincular_centro = QPushButton("🔗  " + tr("cfg.link_centro", default="VINCULAR A CENTRO"))
        btn_vincular_centro.setFixedHeight(44)
        btn_vincular_centro.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_vincular_centro.setStyleSheet(f"""
            QPushButton {{
                background: #0D1117; color: {_CIAN};
                border: 2px solid {_CIAN}; border-radius: 12px;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 14px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_vincular_centro.clicked.connect(self.ejecutar_vincular_centro)

        tabla_ly.addWidget(self.tabla_usuarios)
        tabla_ly.addWidget(btn_cambiar_pin)
        tabla_ly.addWidget(btn_editar_email)
        tabla_ly.addWidget(btn_editar_perfil)
        tabla_ly.addWidget(btn_vincular_centro)
        # RESETEAR MFA (Fase 3): solo visible para quien tiene el permiso `mfa.admin.reset`.
        try:
            from src.db.usuario import sesion_global
            from src.services import autorizacion
            if autorizacion.puede(sesion_global.usuario_actual or {}, "mfa.admin.reset"):
                btn_reset_mfa = QPushButton("🔒  " + tr("cfg.reset_mfa", default="RESETEAR MFA"))
                btn_reset_mfa.setFixedHeight(44)
                btn_reset_mfa.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_reset_mfa.setStyleSheet(
                    f"QPushButton {{ background:#0D1117; color:{_CIAN}; border:2px solid {_CIAN};"
                    f"border-radius:12px; font-family:'Segoe UI'; font-weight:bold; font-size:14px; }}"
                    f"QPushButton:hover {{ background:{_CIAN}; color:#0E1117; }}")
                btn_reset_mfa.clicked.connect(self.ejecutar_reset_mfa)
                tabla_ly.addWidget(btn_reset_mfa)
        except Exception:
            pass
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
            _perfil_u = u["perfil"].upper()
            self.tabla_usuarios.setItem(
                i, 2, QTableWidgetItem(_PerfilDropdown._ETIQUETAS.get(_perfil_u, _perfil_u)))
            self.tabla_usuarios.setItem(i, 3, QTableWidgetItem(self._centro_label_de_usuario(u)))

    def _centro_label_de_usuario(self, u) -> str:
        """Texto de la columna CENTRO ("Centros de empresa" unificados, migración 0257). SUPERADMIN:
        todos los centros que ha creado (`centros_trabajo.creado_por_id`), compacto. Resto: el
        centro cuyo `codigo_centro` coincide con `usuarios.centro_codigo` (ya trae
        `listar_usuarios()`) — «—» si no hay coincidencia. `solo_activos=False`: mismo criterio que
        la antigua `centros_perfil` (sin noción de baja), se listan todos."""
        try:
            from src.db import centros as _cts
            perfil = str(u.get("perfil", "")).upper()
            if perfil == "SUPERADMIN":
                propios = _cts.listar_centros(creado_por_id=u.get("id"), solo_activos=False)
                if not propios:
                    return "—"
                if len(propios) > 2:
                    return tr("cfg.n_centros", default="{n} centros", n=len(propios))
                return ", ".join(c.get("nombre_centro") or c.get("codigo_centro") or "?"
                                 for c in propios)
            codigo = u.get("centro_codigo")
            if not codigo:
                return "—"
            match = next((c for c in _cts.listar_centros(solo_activos=False)
                         if c.get("codigo_centro") == codigo), None)
            return (match.get("nombre_centro") or codigo) if match else codigo
        except Exception:
            return "—"

    def ejecutar_reset_mfa(self):
        """Reset MFA administrativo del usuario seleccionado (Fase 3). Abre el diálogo con
        reautenticación + step-up del administrador; el permiso ya se comprobó al crear el botón."""
        row = self.tabla_usuarios.currentRow()
        if row < 0 or not self.tabla_usuarios.item(row, 0):
            return
        try:
            oid = int(self.tabla_usuarios.item(row, 0).text())
        except (TypeError, ValueError):
            return
        onombre = self.tabla_usuarios.item(row, 1).text()
        from src.db.usuario import sesion_global
        actor = sesion_global.usuario_actual or {}
        from src.gui.mfa_gui import MFAResetAdminDialog
        MFAResetAdminDialog(oid, onombre, actor, parent=self).exec()

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
        email = self.input_email.text().strip()
        if not email:
            mostrar_mensaje(self, tr("cfg.incomplete_title", default="Datos incompletos"),
                            tr("cfg.incomplete_msg",
                               default="Introduce un nombre y una contraseña de 4 dígitos."), "warning")
            return
        if "@" not in email:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.email_invalid_msg",
                               default="El email, si se indica, debe tener un formato válido."),
                            "warning")
            return
        # Hallazgo real, 2026-11-20: "Generar perfil empleado" daba de alta usuarios sin límite,
        # sea cual sea el plan contratado (Basic: 3, Plus: 50, Pro: ilimitado) — se comprueba AQUÍ,
        # ANTES de enviar el código de confirmación por email (para no hacer esperar un código a un
        # alta que luego se va a rechazar).
        from src.gui._licencia_ui import verificar_limite_o_avisar
        if not verificar_limite_o_avisar(self, "max_usuarios"):
            return
        # El perfil YA NO se crea aquí directamente: se envía primero un código de 6 dígitos al
        # email indicado (`services.seguridad.confirmacion_perfil_empleado`) y solo se crea de
        # verdad (vía `crear_perfil`, dentro del diálogo de confirmación) si el código introducido
        # es correcto — evita dar de alta perfiles con un email que no pertenece al empleado.
        from src.db.usuario import sesion_global as _ses_g
        from src.services.seguridad import confirmacion_perfil_empleado as _conf
        creador_id = (_ses_g.usuario_actual or {}).get("id") if _ses_g else None
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
        res = _conf.solicitar(nom, pw, self.combo_perfil.currentText(), email=email,
                              id_empresa=id_empresa, creado_por_id=creador_id)
        if not res.get("ok"):
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            res.get("motivo") or tr("cfg.confirm_perfil_envio_error",
                                                    default="No se pudo enviar el código de confirmación."),
                            "warning")
            return
        dlg = _ConfirmarPerfilEmpleadoDialog(res["id_confirmacion"], email, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.input_nombre.clear()
            self.input_pass.clear()
            self.input_pass2.clear()
            self.input_email.clear()
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
        # Acción de alto riesgo (cambio de credenciales) → STEP-UP MFA reciente del administrador.
        try:
            from src.db.usuario import sesion_global
            from src.gui.mfa_gui import pedir_step_up
            if not pedir_step_up(sesion_global.usuario_actual or {}, "password.cambiar", parent=self):
                return
        except Exception:
            pass
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

        btn_ok = QPushButton(tr("cfg.save", default="Guardar"))
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

        # Política de contraseñas empresarial (capa ADICIONAL sobre la validación de PIN de arriba,
        # ver src/services/seguridad/password_politica.py) — degradable: si el módulo de política
        # falla por cualquier motivo, no bloquea un cambio ya validado por la política de PIN existente.
        try:
            from src.db.empresa import empresa_actual_id
            from src.services.seguridad import password_politica
            eid = empresa_actual_id()
            v = password_politica.validar_complejidad(pin, id_empresa=eid)
            if not v.get("ok", True):
                mostrar_mensaje(self, tr("cfg.pin_policy_title", default="Política de contraseñas"),
                                "\n".join(v.get("errores", [])), "warning")
                return
            if password_politica.reutilizada(id_u, pin, id_empresa=eid):
                mostrar_mensaje(self, tr("cfg.pin_policy_title", default="Política de contraseñas"),
                                tr("cfg.pin_reused_msg",
                                   default="No puedes reutilizar una contraseña/PIN reciente."), "warning")
                return
        except Exception:
            pass

        if cambiar_password_usuario(id_u, pin):
            mostrar_mensaje(self, tr("cfg.pin_updated_title", default="PIN actualizado"), tr("cfg.pin_updated_msg", default="PIN de {nombre} actualizado correctamente.", nombre=nombre), "success")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.pin_update_err", default="No se pudo actualizar el PIN."), "error")

    def ejecutar_editar_email(self):
        """Fija/edita el EMAIL del empleado (migración 0287) — necesario para que pueda ser
        sugerido/insertado como destinatario interno en circulares/encuestas (`usuarios_internos.
        listar_usuarios_empresa` excluye a quien no tenga email). Re-lee nombre/perfil/centro_codigo
        ACTUALES antes de escribir (mismo patrón que `ejecutar_vincular_centro`/
        `ejecutar_editar_perfil`: `actualizar_usuario` reescribe esas 3 columnas juntas) para no
        perder ninguna; `email` es el único campo nuevo que esta acción realmente cambia."""
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje(self, tr("cfg.nosel_title", default="Sin selección"),
                            tr("cfg.nosel_email_msg", default="Selecciona un empleado de la tabla "
                                                               "antes de editar su email."), "warning")
            return
        id_u = int(self.tabla_usuarios.item(fila, 0).text())
        nombre_fila = self.tabla_usuarios.item(fila, 1).text()
        actual = obtener_usuario(id_u) or {}

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setFixedWidth(380)

        card = QFrame(dlg)
        card.setObjectName("email_card")
        card.setStyleSheet(
            f"QFrame#email_card{{background:{_FONDO};border:2px solid {_CIAN};"
            f"border-radius:18px;}}"
        )
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setSpacing(12)
        ly.setContentsMargins(24, 24, 24, 24)

        lbl_titulo = QLabel(f"Email de  <b>{nombre_fila}</b>:")
        lbl_titulo.setStyleSheet("color:white;font-family:'Segoe UI';font-size:14px;background:transparent;")
        ly.addWidget(lbl_titulo)

        inp = QLineEdit(actual.get("email") or "")
        inp.setPlaceholderText(tr("cfg.ph_email", default="EMAIL (opcional, para circulares/encuestas)"))
        inp.setFixedHeight(44)
        inp.setStyleSheet(
            f"background:#0D1117;color:white;border:2px solid {_CIAN};"
            f"border-radius:8px;padding:6px 12px;font-size:14px;font-family:'Segoe UI';"
        )
        ly.addWidget(inp)

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

        btn_ok = QPushButton(tr("cfg.save", default="Guardar"))
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

        nuevo_email = inp.text().strip()
        if nuevo_email and "@" not in nuevo_email:
            mostrar_mensaje(self, tr("cfg.email_invalid_title", default="Email inválido"),
                            tr("cfg.email_invalid_msg",
                               default="El email, si se indica, debe tener un formato válido."),
                            "warning")
            return

        ok = actualizar_usuario(id_u, actual.get("nombre") or nombre_fila, actual.get("perfil"),
                                actual.get("centro_codigo"), email=nuevo_email or "")
        if ok:
            mostrar_mensaje(self, tr("cfg.email_updated_title", default="Email actualizado"),
                            tr("cfg.email_updated_msg", default="Email de {nombre} actualizado correctamente.",
                               nombre=nombre_fila), "success")
            self.refrescar_datos_usuarios()
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.email_update_err", default="No se pudo actualizar el email."), "error")

    def ejecutar_editar_perfil(self):
        """Cambia el PERFIL BASE (OPERARIO/ADMINISTRADOR/SUPERADMIN) de un empleado ya existente
        — es el único punto de la interfaz que llama a `actualizar_usuario`. Distinto de Seguridad/
        Asignaciones (roles RBAC): el menú principal gatea sus tarjetas por este perfil base, no por
        los roles RBAC, así que este es el cambio real que hace falta para dar/quitar acceso SUPERADMIN."""
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje(self, tr("cfg.nosel_title", default="Sin selección"),
                            tr("cfg.nosel_profile_msg", default="Selecciona un empleado de la tabla "
                                                                 "antes de editar su perfil."), "warning")
            return
        # Elevar/cambiar el perfil base es una acción de alto riesgo → STEP-UP MFA reciente.
        try:
            from src.db.usuario import sesion_global
            from src.gui.mfa_gui import pedir_step_up
            if not pedir_step_up(sesion_global.usuario_actual or {}, "perfil.cambiar", parent=self):
                return
        except Exception:
            pass

        id_u = int(self.tabla_usuarios.item(fila, 0).text())
        nombre = self.tabla_usuarios.item(fila, 1).text()
        perfil_actual = self.tabla_usuarios.item(fila, 2).text().upper()

        opciones = [perfil_actual] + [p for p in ("OPERARIO", "ADMINISTRADOR", "SUPERADMIN")
                                      if p != perfil_actual]

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setFixedWidth(360)

        card = QFrame(dlg)
        card.setObjectName("perfil_card")
        card.setStyleSheet(
            f"QFrame#perfil_card{{background:{_FONDO};border:2px solid {_CIAN};"
            f"border-radius:18px;}}"
        )
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setSpacing(12)
        ly.setContentsMargins(24, 24, 24, 24)

        lbl_titulo = QLabel(f"Nuevo perfil para  <b>{nombre}</b>:")
        lbl_titulo.setStyleSheet(
            "color:white;font-family:'Segoe UI';font-size:14px;background:transparent;"
        )
        ly.addWidget(lbl_titulo)

        combo = _PerfilDropdown(opciones)
        ly.addWidget(combo)

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

        btn_ok = QPushButton(tr("cfg.save", default="Guardar"))
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

        nuevo_perfil = combo.currentText()
        if nuevo_perfil == perfil_actual:
            return

        # No se toca el nombre ni el centro asignado del empleado — se relee su centro_codigo
        # actual (actualizar_usuario reescribe las 3 columnas juntas) para no perderlo.
        centro_codigo = None
        for u in listar_usuarios():
            if u["id"] == id_u:
                centro_codigo = u.get("centro_codigo")
                break

        if actualizar_usuario(id_u, nombre, nuevo_perfil, centro_codigo):
            mostrar_mensaje(self, tr("cfg.profile_updated_title", default="Perfil actualizado"),
                            tr("cfg.profile_updated_msg",
                               default="Perfil de {nombre} cambiado a {perfil}.",
                               nombre=nombre, perfil=nuevo_perfil), "success")
            self.refrescar_datos_usuarios()
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.profile_update_err", default="No se pudo actualizar el perfil."),
                            "error")

    def ejecutar_vincular_centro(self):
        """🔗 Vincular a centro ("Centros de empresa" unificados, migración 0257): asigna el
        empleado seleccionado a un `centros_trabajo` — escribe `usuarios.id_centro_trabajo` Y
        `usuarios.centro_codigo` (sincronizados: `centro_codigo` tiene otros consumidores
        existentes — kárdex, logística, sesión — que no deben romperse). Abre el selector en modo
        "elegir" (mismo aislamiento entre superadmins + desbloqueo por PIN que "Cambiar de Centro",
        ver `selector_tienda.py`)."""
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje(self, tr("cfg.nosel_title", default="Sin selección"),
                            tr("cfg.nosel_centro_msg", default="Selecciona un empleado de la tabla "
                                                                "antes de vincularlo a un centro."),
                            "warning")
            return
        id_u = int(self.tabla_usuarios.item(fila, 0).text())
        nombre_fila = self.tabla_usuarios.item(fila, 1).text()

        from src.gui.selector_tienda import SelectorCentroDialog
        dlg = SelectorCentroDialog(self, modo="elegir")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        centro = dlg.get_resultado()
        if not centro:
            return

        # Re-leer nombre/perfil ACTUALES antes de escribir (actualizar_usuario sobreescribe las 3
        # columnas juntas) — mismo patrón que ejecutar_editar_perfil, para no clobberear ninguno.
        actual = obtener_usuario(id_u) or {}
        ok_base = actualizar_usuario(
            id_u, actual.get("nombre") or nombre_fila, actual.get("perfil"),
            centro.get("codigo_centro"))
        ok_link = vincular_centro_trabajo(id_u, centro.get("id_centro"))
        if ok_base and ok_link:
            mostrar_mensaje(
                self, tr("cfg.link_ok_t", default="Centro vinculado"),
                tr("cfg.link_ok_msg", default="{nombre} vinculado a «{centro}».",
                   nombre=nombre_fila,
                   centro=centro.get("nombre_centro") or centro.get("codigo_centro")),
                "success")
            self.refrescar_datos_usuarios()
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.link_err", default="No se pudo vincular el centro."), "error")

    # PESTAÑA 9 «ASIGNAR REFERENCIA»: RETIRADA (deprecada → Identidad Operativa/IOC). El slot del stack es
    # un placeholder QWidget; la identidad de la terminal se gestiona en Centros de trabajo (IOC).

    def _id_usuario_actual(self):
        """ID del usuario activo (self.usuario puede ser dict u objeto)."""
        u = self.usuario
        return (u or {}).get("id") if isinstance(u, dict) else getattr(u, "id", None)

    def _crear_page_modo_tactil(self):
        """Selector de perfil táctil (NORMAL/TÁCTIL/TPV/PDA). Persiste por usuario y aplica en caliente."""
        from PyQt6.QtWidgets import QButtonGroup, QRadioButton

        from src.utils import perfil_tactil

        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 30, 40, 40)
        ly.setSpacing(14)

        titulo = QLabel(tr("cfg.tactil_title", default="MODO TÁCTIL / DISPOSITIVO"))
        titulo.setStyleSheet("color: white; font-weight: 900; font-size: 20px; letter-spacing: 1px;")
        ly.addWidget(titulo)

        desc = QLabel(tr("cfg.tactil_desc",
                         default="Ajusta el tamaño táctil de botones, campos, combos, tablas y pestañas "
                                 "en toda la interfaz. Se guarda por usuario y se aplica al instante."))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8B949E; font-size: 13px;")
        ly.addWidget(desc)
        ly.addSpacing(8)

        opciones = [
            (perfil_tactil.NORMAL, tr("cfg.tactil_normal", default="NORMAL"),
             tr("cfg.tactil_normal_sub", default="Ratón/teclado — sin ampliación")),
            (perfil_tactil.TACTIL, tr("cfg.tactil_tactil", default="TÁCTIL"),
             tr("cfg.tactil_tactil_sub", default="Pantalla táctil — controles ≥ 48 px")),
            (perfil_tactil.TPV, tr("cfg.tactil_tpv", default="TPV"),
             tr("cfg.tactil_tpv_sub", default="Terminal punto de venta — controles ≥ 56 px")),
            (perfil_tactil.PDA, tr("cfg.tactil_pda", default="PDA / MDE"),
             tr("cfg.tactil_pda_sub", default="Terminal de mano — controles ≥ 44 px")),
        ]
        actual = perfil_tactil.perfil_actual()
        self._tactil_group = QButtonGroup(self)
        self._tactil_radios = {}
        for val, lbl, sub in opciones:
            rb = QRadioButton(f"{lbl}   —   {sub}")
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setChecked(val == actual)
            rb.setStyleSheet(
                "QRadioButton { color: white; font-family: 'Segoe UI'; font-size: 15px; font-weight: bold;"
                " padding: 10px; spacing: 12px; }"
                "QRadioButton::indicator { width: 20px; height: 20px; }"
                f"QRadioButton:hover {{ color: {_CIAN}; }}"
            )
            self._tactil_group.addButton(rb)
            self._tactil_radios[val] = rb
            ly.addWidget(rb)

        ly.addStretch()
        btn = QPushButton(tr("cfg.tactil_apply", default="Guardar y aplicar"))
        btn.setFixedSize(220, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: #0E1117; color: #238636; border: 2px solid #238636; border-radius: 12px;"
            " font-family: 'Segoe UI'; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background: #238636; color: #0E1117; }"
        )
        btn.clicked.connect(self._aplicar_perfil_tactil)
        h = QHBoxLayout(); h.addStretch(); h.addWidget(btn)
        ly.addLayout(h)
        return page

    def _aplicar_perfil_tactil(self):
        """Persiste el perfil elegido (por usuario) y lo aplica en caliente a toda la app."""
        from src.utils import perfil_tactil
        sel = next((v for v, rb in self._tactil_radios.items() if rb.isChecked()), perfil_tactil.NORMAL)
        perfil_tactil.guardar_en_preferencias(self._id_usuario_actual(), sel)
        try:
            from PyQt6.QtWidgets import QApplication

            from assets.estilo_global import aplicar_estilo_app
            aplicar_estilo_app(QApplication.instance())  # re-aplica el QSS global sin reiniciar
        except Exception:
            pass
        mostrar_mensaje(
            self, tr("cfg.saved_title", default="Guardado"),
            tr("cfg.tactil_saved", default="Perfil táctil aplicado: {p}", p=sel.upper()),
            "success",
        )

    # ── SOMA (activación + voz) ───────────────────────────────────────────────
    def _crear_page_delegacion_ia(self):
        """Delegación a SOMA — autorrelleno de centros nuevos (ver services.soma_delegacion,
        pantalla="configuracion"). NO confundir con "ASISTENTE SOMA" (arriba): aquella pestaña
        ajusta el asistente conversacional (voz/consumo de IA); esta gestiona reglas de
        automatización con instrucciones propias, un concepto distinto."""
        from src.gui.soma_delegacion_gui import DelegacionSomaPanel
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 30, 40, 40)
        ly.setSpacing(16)
        titulo = QLabel("DELEGACIÓN IA")
        titulo.setStyleSheet("color: white; font-weight: 900; font-size: 20px; letter-spacing: 1px;")
        ly.addWidget(titulo)
        ly.addWidget(DelegacionSomaPanel(pantalla="configuracion", usuario=self.usuario), 1)
        return page

    def _crear_page_suscripcion(self):
        """SUSCRIPCIÓN — migrada tal cual (petición explícita) desde la antigua tarjeta "SaaS" del
        menú principal: la propia `SaaSAdminWindow` (plan/consumo/IA/voz), embebida aquí SIN su
        botón X de cierre (se omite pasando `callback_vuelta=None` — la propia clase ya construye
        ese botón solo "if callback_vuelta", nada que tocar en ella) ya que, como pestaña de
        Configuración, el cierre lo da el propio sidebar de Configuración, no un X duplicado."""
        from src.gui.saas_admin import SaaSAdminWindow
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(SaaSAdminWindow(usuario=self.usuario, parent=page))
        return page

    def _crear_page_soma(self):
        """Ajustes del asistente SOMA: desactivar la voz (chat solo-texto), desactivarlo por
        completo, o elegir la modalidad de consumo de IA (limitado/ilimitado) de la empresa."""
        from PyQt6.QtWidgets import QButtonGroup, QCheckBox, QRadioButton

        from src.utils import tema
        cfg = tema.cargar()

        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 30, 40, 40)
        ly.setSpacing(16)

        titulo = QLabel(tr("cfg.soma_title", default="ASISTENTE SOMA"))
        titulo.setStyleSheet("color: white; font-weight: 900; font-size: 20px; letter-spacing: 1px;")
        ly.addWidget(titulo)

        desc = QLabel(tr("cfg.soma_desc",
                         default="Controla el asistente SOMA. Los cambios se aplican al reiniciar la "
                                 "aplicación (SOMA arranca al iniciar sesión)."))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8B949E; font-size: 13px;")
        ly.addWidget(desc)
        ly.addSpacing(8)

        _chk_ss = (
            "QCheckBox { color: white; font-family: 'Segoe UI'; font-size: 15px; font-weight: bold;"
            " padding: 10px; spacing: 12px; }"
            "QCheckBox::indicator { width: 22px; height: 22px; }"
            f"QCheckBox:hover {{ color: {_CIAN}; }}"
        )

        self._soma_chk_activo = QCheckBox(tr("cfg.soma_enabled", default="SOMA activado"))
        self._soma_chk_activo.setChecked(bool(cfg.get("soma_activo", True)))
        self._soma_chk_activo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._soma_chk_activo.setStyleSheet(_chk_ss)
        ly.addWidget(self._soma_chk_activo)

        sub1 = QLabel(tr("cfg.soma_enabled_sub",
                         default="Si se desactiva, SOMA no aparece ni interviene en ninguna parte de la app."))
        sub1.setWordWrap(True); sub1.setStyleSheet("color: #6B7685; font-size: 12px; margin-left: 44px;")
        ly.addWidget(sub1)

        self._soma_chk_voz = QCheckBox(tr("cfg.soma_voice", default="Voz de SOMA (escuchar y hablar)"))
        self._soma_chk_voz.setChecked(bool(cfg.get("soma_voz", True)))
        self._soma_chk_voz.setCursor(Qt.CursorShape.PointingHandCursor)
        self._soma_chk_voz.setStyleSheet(_chk_ss)
        ly.addWidget(self._soma_chk_voz)

        sub2 = QLabel(tr("cfg.soma_voice_sub",
                         default="Si se desactiva la voz, SOMA NO escuchará el micrófono ni responderá en "
                                 "voz alta: solo se comunicará por el chat de texto."))
        sub2.setWordWrap(True); sub2.setStyleSheet("color: #6B7685; font-size: 12px; margin-left: 44px;")
        ly.addWidget(sub2)

        # Voz deshabilitada (y forzada a desmarcada) si SOMA está desactivado: nunca debe poder
        # guardarse la combinación imposible voz=activa + SOMA=desactivado.
        def _sync_voz():
            activo = self._soma_chk_activo.isChecked()
            self._soma_chk_voz.setEnabled(activo)
            if not activo:
                self._soma_chk_voz.setChecked(False)
        self._soma_chk_activo.toggled.connect(lambda _: _sync_voz())
        _sync_voz()

        # ── Modalidad de consumo de IA (empresas.ai_plan_type: LIMITED / PAY_AS_YOU_GO) ──────
        ly.addSpacing(12)
        titulo_ia = QLabel(tr("cfg.soma_ia_title", default="USO DE IA DE LA EMPRESA"))
        titulo_ia.setStyleSheet("color: white; font-weight: 900; font-size: 16px; letter-spacing: 1px;")
        ly.addWidget(titulo_ia)

        desc_ia = QLabel(tr("cfg.soma_ia_desc",
                            default="SOMA y otras funciones de IA de la empresa consumen la API de "
                                    "Anthropic. Elige si quieres un límite diario de seguridad de coste "
                                    "o consumo sin límite."))
        desc_ia.setWordWrap(True)
        desc_ia.setStyleSheet("color: #8B949E; font-size: 13px;")
        ly.addWidget(desc_ia)
        ly.addSpacing(6)

        try:
            from src.db.empresa import empresa_actual_id
            self._soma_id_empresa_ia = empresa_actual_id()
        except Exception:
            self._soma_id_empresa_ia = None

        plan_actual = "LIMITED"
        if self._soma_id_empresa_ia:
            try:
                from src.services.saas.ia_plan import resumen_uso_ia
                plan_actual = (resumen_uso_ia(self._soma_id_empresa_ia).get("plan_type") or "LIMITED")
            except Exception:
                plan_actual = "LIMITED"

        self._soma_group_ia = QButtonGroup(self)
        self._soma_rb_limitado = QRadioButton(tr("cfg.soma_ia_limitado", default="Uso limitado"))
        self._soma_rb_ilimitado = QRadioButton(tr("cfg.soma_ia_ilimitado", default="Uso ilimitado"))
        for rb in (self._soma_rb_limitado, self._soma_rb_ilimitado):
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setStyleSheet(_chk_ss)
            self._soma_group_ia.addButton(rb)
            ly.addWidget(rb)

        self._soma_rb_limitado.setChecked(plan_actual != "PAY_AS_YOU_GO")
        self._soma_rb_ilimitado.setChecked(plan_actual == "PAY_AS_YOU_GO")
        # Valor cargado al construir la pestaña — permite a `_guardar_soma` detectar si el usuario
        # realmente cambió la modalidad y evitar escrituras/auditoría en cada guardado sin cambios.
        self._soma_plan_ia_cargado = plan_actual

        sub_lim = QLabel(tr("cfg.soma_ia_limitado_sub",
                            default="Bloquea nuevas llamadas de IA al alcanzar el límite diario de "
                                    "seguridad. Recomendado."))
        sub_lim.setWordWrap(True); sub_lim.setStyleSheet("color: #6B7685; font-size: 12px; margin-left: 44px;")
        ly.addWidget(sub_lim)

        sub_ilim = QLabel(tr("cfg.soma_ia_ilimitado_sub",
                             default="Sin límite diario: la empresa asume el coste real de todo el "
                                     "consumo de IA."))
        sub_ilim.setWordWrap(True); sub_ilim.setStyleSheet("color: #6B7685; font-size: 12px; margin-left: 44px;")
        ly.addWidget(sub_ilim)

        # Confirmación NO destructiva cada vez que el usuario SELECCIONA "ilimitado" (yes/no,
        # revertible si cancela) — nunca un bloqueo duro: solo informa del riesgo de coste antes
        # de aplicar el cambio. Se omite mientras se está construyendo la pestaña (carga del
        # valor guardado), para no re-preguntar por un estado que el usuario no acaba de elegir.
        self._soma_ia_inicializando = True

        def _on_ilimitado_toggled(marcado):
            if not marcado or self._soma_ia_inicializando:
                return
            if not mostrar_confirmacion(
                self,
                tr("cfg.soma_ia_confirm_title", default="Cambiar a uso ilimitado"),
                tr("cfg.soma_ia_confirm_msg",
                   default="Vas a desactivar el límite diario de seguridad de coste de IA para esta "
                           "empresa. Un uso excesivo puede incrementar significativamente la factura. "
                           "¿Continuar?"),
            ):
                self._soma_rb_ilimitado.blockSignals(True)
                self._soma_rb_limitado.blockSignals(True)
                self._soma_rb_ilimitado.setChecked(False)
                self._soma_rb_limitado.setChecked(True)
                self._soma_rb_ilimitado.blockSignals(False)
                self._soma_rb_limitado.blockSignals(False)

        self._soma_rb_ilimitado.toggled.connect(_on_ilimitado_toggled)
        self._soma_ia_inicializando = False

        # ── SOMA Conectores Externos (MCP) ────────────────────────────────────────────────
        # Permite que apps de IA externas (ChatGPT, Claude Desktop) se conecten a Smart Manager a
        # través de SOMA por el protocolo MCP (ver src/mcp_server/). No hay ningún ajuste nuevo que
        # persistir aquí (el servidor MCP está siempre activo junto al backend, igual que el resto
        # de la REST API) — esta sección es solo estado/acciones (comprobar, copiar URL, revocar
        # apps), nunca un botón de guardado propio: se integra bajo el ÚNICO botón "GUARDAR" de la
        # pestaña (ver `_guardar_soma`) solo para lo que de verdad cambia de estado.
        ly.addSpacing(12)
        titulo_mcp = QLabel(tr("cfg.soma_mcp_title", default="SOMA CONECTORES EXTERNOS (MCP)"))
        titulo_mcp.setStyleSheet("color: white; font-weight: 900; font-size: 16px; letter-spacing: 1px;")
        ly.addWidget(titulo_mcp)

        desc_mcp = QLabel(tr("cfg.soma_mcp_desc",
                             default="Permite que apps de IA externas (ChatGPT, Claude Desktop) se "
                                     "conecten a Smart Manager a través de SOMA usando el protocolo "
                                     "MCP (Model Context Protocol). Cada app se autentica con un "
                                     "usuario real de esta empresa y queda listada abajo; puedes "
                                     "revocarla en cualquier momento."))
        desc_mcp.setWordWrap(True)
        desc_mcp.setStyleSheet("color: #8B949E; font-size: 13px;")
        ly.addWidget(desc_mcp)
        ly.addSpacing(6)

        # Estado del servidor: proxy HONESTO (backend vivo = condición necesaria y suficiente para
        # que /mcp esté disponible; /mcp en sí exige un JWT válido, así que no se puede "hacer ping"
        # sin credenciales de un cliente MCP real — comprobar lo mismo que ya comprueba
        # `main._backend_remoto_info` es la pieza honesta más fuerte disponible aquí).
        fila_estado = QHBoxLayout()
        lbl_estado = QLabel(tr("cfg.soma_mcp_estado", default="Estado del servidor:"))
        lbl_estado.setStyleSheet("color: white; font-size: 13px;")
        fila_estado.addWidget(lbl_estado)
        from src.gui.components.enterprise import EnterpriseStatusBadge
        self._mcp_badge_estado = EnterpriseStatusBadge(
            tr("cfg.soma_mcp_comprobando", default="Comprobando…"), rol="neutro")
        fila_estado.addWidget(self._mcp_badge_estado)
        btn_comprobar = QPushButton(tr("cfg.soma_mcp_comprobar", default="🔄 Comprobar"))
        btn_comprobar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_comprobar.setStyleSheet(
            "QPushButton { background: #161B22; color: #00FFC6; border: 1px solid #00FFC6;"
            " border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px; }"
            "QPushButton:hover { background: #00FFC6; color: #0E1117; }"
        )
        btn_comprobar.clicked.connect(self._soma_mcp_comprobar_estado)
        fila_estado.addWidget(btn_comprobar)
        fila_estado.addStretch()
        ly.addLayout(fila_estado)

        # URL del endpoint: IP de LAN real (no "localhost" — una app externa no puede resolver el
        # localhost de ESTA máquina), mismo truco UDP que ya usa `utils.reab_webhook.get_local_ip`
        # para las URLs de reabastecimiento remoto; mismo puerto que el resto del backend
        # (`BACKEND_PORT`/`PORT`, igual fórmula que `gui/tpv.py::_abrir_portal_empleado`).
        fila_url = QHBoxLayout()
        self._mcp_url_edit = QLineEdit(self._soma_mcp_url())
        self._mcp_url_edit.setReadOnly(True)
        self._mcp_url_edit.setCursorPosition(0)
        self._mcp_url_edit.setStyleSheet(
            "QLineEdit { background: #0E1117; color: #E6EDF3; border: 1px solid #30363D;"
            " border-radius: 6px; padding: 6px 10px; font-family: 'Consolas'; font-size: 12px; }"
        )
        fila_url.addWidget(self._mcp_url_edit, 1)
        btn_copiar = QPushButton(tr("cfg.soma_mcp_copiar",
                                    default="📋 Copiar URL de Integración para ChatGPT / Claude"))
        btn_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copiar.setStyleSheet(
            "QPushButton { background: #0E1117; color: #00FFC6; border: 1px solid #00FFC6;"
            " border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 6px 12px; }"
            "QPushButton:hover { background: #00FFC6; color: #0E1117; }"
        )
        btn_copiar.clicked.connect(self._soma_mcp_copiar_url)
        fila_url.addWidget(btn_copiar)
        ly.addLayout(fila_url)
        ly.addSpacing(10)

        # Apps vinculadas: mismo patrón de lista+revocar que `gui/mfa_gui.py` (dispositivos de
        # confianza/passkeys) — contenedor reconstruido en cada refresco, reutiliza
        # `services.api_publica.developer.listar_apps/revocar_app` (ya existentes, scope "mcp").
        titulo_apps = QLabel(tr("cfg.soma_mcp_apps_title", default="Apps vinculadas"))
        titulo_apps.setStyleSheet("color: #00FFC6; font-weight: 800; font-size: 14px;")
        ly.addWidget(titulo_apps)
        desc_apps = QLabel(tr("cfg.soma_mcp_apps_desc",
                              default="Aplicaciones externas que se han conectado a Smart Manager "
                                      "por MCP. Revócalas si no las reconoces."))
        desc_apps.setWordWrap(True)
        desc_apps.setStyleSheet("color: #8B949E; font-size: 12px;")
        ly.addWidget(desc_apps)

        self._mcp_apps_cont = QVBoxLayout()
        self._mcp_apps_cont.setSpacing(6)
        _mcp_apps_w = QWidget()
        _mcp_apps_w.setLayout(self._mcp_apps_cont)
        ly.addWidget(_mcp_apps_w)

        self._soma_mcp_comprobar_estado()
        self._soma_mcp_refrescar_apps()

        ly.addStretch()
        btn = QPushButton(tr("cfg.save", default="Guardar"))
        btn.setFixedSize(220, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: #0E1117; color: #238636; border: 2px solid #238636;"
            " border-radius: 12px; font-family: 'Segoe UI'; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background: #238636; color: #0E1117; }"
        )
        btn.clicked.connect(self._guardar_soma)
        h = QHBoxLayout(); h.addStretch(); h.addWidget(btn)
        ly.addLayout(h)

        # Scroll (mismo patrón que el resto de pestañas largas de esta ventana, p. ej.
        # `_crear_page_colores`/"Estado de la cuenta"): la sección "Conectores Externos (MCP)"
        # añadió contenido suficiente para que, en pantallas más bajas, la pestaña ya no quepa
        # entera — sin esto, el tramo final (apps vinculadas, guardar) queda inaccesible, sin
        # ninguna forma de llegar a él. Bug real reportado por el usuario tras usar la nueva
        # sección MCP.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        scroll.setWidget(page)
        return scroll

    def _soma_mcp_url(self) -> str:
        """URL honesta del endpoint MCP (ver comentario en `_crear_page_soma`)."""
        try:
            from src.utils.reab_webhook import get_local_ip
            host = get_local_ip()
        except Exception:
            host = "127.0.0.1"
        puerto = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
        return f"http://{host}:{puerto}/mcp"

    def _soma_mcp_comprobar_estado(self):
        """Backend vivo (`/salud`, igual chequeo que `main._backend_remoto_info`) como proxy
        honesto de que `/mcp` está operativo — ver nota de diseño en `_crear_page_soma`."""
        import json
        import urllib.request
        puerto = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
        vivo = False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/salud", timeout=1.5) as r:
                datos = json.loads(r.read().decode("utf-8"))
            vivo = datos.get("servicio") == "smart-manager-backend"
        except Exception:
            vivo = False
        if hasattr(self, "_mcp_badge_estado"):
            if vivo:
                self._mcp_badge_estado.set_estado(
                    tr("cfg.soma_mcp_vivo", default="Backend activo · /mcp disponible"), rol="ok")
            else:
                self._mcp_badge_estado.set_estado(
                    tr("cfg.soma_mcp_caido", default="Backend no responde"), rol="critico")

    def _soma_mcp_copiar_url(self):
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self._mcp_url_edit.text())
        mostrar_mensaje(self, tr("cfg.saved_title", default="Copiado"),
                        tr("cfg.soma_mcp_copiado", default="URL copiada al portapapeles."),
                        "success")

    def _soma_mcp_refrescar_apps(self):
        if not hasattr(self, "_mcp_apps_cont"):
            return
        while self._mcp_apps_cont.count():
            it = self._mcp_apps_cont.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        id_empresa = getattr(self, "_soma_id_empresa_ia", None)
        apps = []
        try:
            from src.services.api_publica import developer
            todas = developer.listar_apps(id_empresa=id_empresa)
            apps = [a for a in todas if "mcp" in str(a.get("scopes") or "").split(",")
                    and a.get("estado") == "activa"]
        except Exception:
            apps = []
        if not apps:
            lbl_vacio = QLabel(tr("cfg.soma_mcp_apps_vacio", default="No hay apps MCP vinculadas."))
            lbl_vacio.setStyleSheet("color: #6B7685; font-size: 12px;")
            self._mcp_apps_cont.addWidget(lbl_vacio)
            return
        for app in apps:
            fila = QHBoxLayout()
            nombre = app.get("nombre") or app.get("client_id")
            lbl = QLabel(f"🔌  {nombre}  ({app.get('client_id')})")
            lbl.setStyleSheet("color: white; font-size: 12px;")
            fila.addWidget(lbl)
            fila.addStretch()
            btn_rev = QPushButton(tr("cfg.soma_mcp_revocar", default="Revocar"))
            btn_rev.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rev.setStyleSheet(
                "QPushButton { background: #0E1117; color: #F85149; border: 1px solid #F85149;"
                " border-radius: 8px; font-size: 12px; padding: 4px 10px; }"
                "QPushButton:hover { background: #F85149; color: #0E1117; }"
            )
            btn_rev.clicked.connect(
                lambda _=False, cid=app.get("client_id"), emp=app.get("id_empresa"):
                    self._soma_mcp_revocar_app(cid, emp))
            fila.addWidget(btn_rev)
            w = QWidget()
            w.setLayout(fila)
            self._mcp_apps_cont.addWidget(w)

    def _soma_mcp_revocar_app(self, client_id, id_empresa_app=None):
        """`id_empresa_app` es el `id_empresa` REAL de la fila (normalmente NULL para un conector
        MCP registrado por DCR — ver `mcp_server/oauth.py`: "la empresa se decide en /authorize, no
        en el registro del cliente"), NUNCA la empresa de la sesión actual: `developer.revocar_app`
        exige una coincidencia exacta (`id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL)`) y
        pasar la empresa de la sesión no afectaría ninguna fila cuando la app es NULL-tenant."""
        if not client_id:
            return
        if not mostrar_confirmacion(
            self, tr("cfg.soma_mcp_revocar_title", default="Revocar app MCP"),
            tr("cfg.soma_mcp_revocar_msg",
               default="La app dejará de poder usar MCP para acceder a Smart Manager. ¿Continuar?"),
        ):
            return
        try:
            from src.services.api_publica import developer
            developer.revocar_app(client_id, id_empresa=id_empresa_app)
        except Exception:
            pass
        self._soma_mcp_refrescar_apps()

    def _guardar_soma(self):
        from src.utils import tema
        ok = tema.guardar({
            "soma_activo": self._soma_chk_activo.isChecked(),
            "soma_voz": self._soma_chk_voz.isChecked(),
        })

        # Modalidad de consumo de IA de la empresa (empresas.ai_plan_type): mismo botón "Guardar",
        # misma acción — solo se escribe/audita si el usuario realmente cambió el valor cargado.
        plan_ok = True
        id_empresa = getattr(self, "_soma_id_empresa_ia", None)
        plan_elegido = "PAY_AS_YOU_GO" if self._soma_rb_ilimitado.isChecked() else "LIMITED"
        if id_empresa and plan_elegido != getattr(self, "_soma_plan_ia_cargado", plan_elegido):
            try:
                from src.services.saas.ia_plan import cambiar_plan_ia
                cambiar_plan_ia(id_empresa, plan_elegido)
                self._soma_plan_ia_cargado = plan_elegido
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "No se pudo guardar la modalidad de uso de IA (empresa %s).", id_empresa)
                plan_ok = False

        if ok and plan_ok:
            mostrar_mensaje(
                self, tr("cfg.saved_title", default="Guardado"),
                tr("cfg.soma_saved",
                   default="Ajustes de SOMA guardados. Reinicia la aplicación para aplicar los cambios."),
                "success")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.soma_save_err", default="No se pudieron guardar los ajustes de SOMA."),
                            "error")

    # ── COLORES (tema de la interfaz + color de SOMA) ─────────────────────────
    def _fila_color(self, layout, etiqueta, clave, valor_actual, *, subtitulo=None):
        """Añade una fila de selección de color: rótulo + muestra clicable (abre selector) + HEX."""
        cont = QVBoxLayout(); cont.setSpacing(2)
        lbl = QLabel(etiqueta)
        lbl.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent;")
        cont.addWidget(lbl)
        if subtitulo:
            sub = QLabel(subtitulo); sub.setWordWrap(True)
            sub.setStyleSheet("color: #6B7685; font-size: 11px; background: transparent;")
            cont.addWidget(sub)

        fila = QHBoxLayout(); fila.setSpacing(12)
        muestra = QPushButton()
        muestra.setFixedSize(64, 34)
        muestra.setCursor(Qt.CursorShape.PointingHandCursor)
        hexlbl = QLabel(valor_actual.upper())
        hexlbl.setStyleSheet("color: #C9D1D9; font-family: 'Consolas','Segoe UI'; font-size: 13px;"
                             " font-weight: bold; background: transparent;")

        def _pinta(color_hex):
            muestra.setStyleSheet(
                f"QPushButton {{ background: {color_hex}; border: 2px solid #30363D; border-radius: 8px; }}"
                f"QPushButton:hover {{ border: 2px solid {_CIAN}; }}")
            hexlbl.setText(color_hex.upper())
            self._colores_sel[clave] = color_hex.upper()

        _pinta(valor_actual)

        def _elegir():
            from src.gui.color_picker import seleccionar_color
            actual = self._colores_sel.get(clave, valor_actual)
            hexval = seleccionar_color(self, actual, tr("cfg.color_pick", default="Selector de color"))
            if hexval:
                _pinta(hexval)
        muestra.clicked.connect(_elegir)

        fila.addWidget(muestra); fila.addWidget(hexlbl); fila.addStretch()
        cont.addLayout(fila)
        layout.addLayout(cont)

    def _crear_page_mfa(self):
        """Pestaña de autoservicio MFA (Fase 1): enrolamiento/estado/desactivación del segundo factor
        del usuario en sesión. Reutiliza el panel `gui/mfa_gui.MFASeguridadPanel` (motor `seguridad.mfa`)."""
        try:
            from src.gui.mfa_gui import MFASeguridadPanel
            usuario = getattr(self, "usuario", None)
            return MFASeguridadPanel(usuario=usuario)
        except Exception:
            return QWidget()

    def _crear_page_colores(self):
        """Selector de colores del tema (fondo, acción/tablas, cancelar, confirmar, retorno) + SOMA."""
        from PyQt6.QtWidgets import QScrollArea

        from src.utils import tema
        cfg = tema.cargar()
        self._colores_sel = {}

        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 30, 40, 20)
        outer.setSpacing(10)

        titulo = QLabel(tr("cfg.colors_title", default="PERSONALIZACIÓN DE LA INTERFAZ"))
        titulo.setStyleSheet("color: white; font-weight: 900; font-size: 20px; letter-spacing: 1px;")
        outer.addWidget(titulo)
        aviso = QLabel(tr("cfg.colors_desc",
                          default="Personaliza los colores del software y de SOMA. Los cambios se aplican "
                                  "al REINICIAR la aplicación. Por defecto: turquesa + azul oscuro."))
        aviso.setWordWrap(True); aviso.setStyleSheet("color: #8B949E; font-size: 13px;")
        outer.addWidget(aviso)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); ly = QVBoxLayout(cont); ly.setSpacing(18); ly.setContentsMargins(2, 8, 12, 8)

        def _sep(txt):
            s = QLabel(txt)
            s.setStyleSheet(f"color: {_CIAN}; font-size: 12px; font-weight: 900; letter-spacing: 1px;"
                            " margin-top: 6px; background: transparent;")
            ly.addWidget(s)

        _sep(tr("cfg.colors_g1", default="1 · FONDO DE LAS VENTANAS"))
        self._fila_color(ly, tr("cfg.colors_bg", default="Color de fondo"), "fondo_app", cfg["fondo_app"])

        _sep(tr("cfg.colors_g2", default="2 · TABLAS Y BOTONES DE ACCIÓN"))
        self._fila_color(ly, tr("cfg.colors_action", default="Color de tablas y botones de acción"),
                         "accion_bg", cfg["accion_bg"],
                         subtitulo=tr("cfg.colors_action_sub",
                                      default="Tablas y botones que inician una acción comparten color."))
        self._fila_color(ly, tr("cfg.colors_action_txt", default="Color del texto (hover-swap)"),
                         "accion_texto", cfg["accion_texto"])

        _sep(tr("cfg.colors_g3", default="3 · BOTONES DE CANCELAR"))
        self._fila_color(ly, tr("cfg.colors_cancel", default="Color de botones de cancelar"),
                         "cancelar_bg", cfg["cancelar_bg"])
        self._fila_color(ly, tr("cfg.colors_cancel_txt", default="Color del texto"),
                         "cancelar_texto", cfg["cancelar_texto"])

        _sep(tr("cfg.colors_g4", default="4 · BOTONES DE CONFIRMAR / AVANZAR"))
        self._fila_color(ly, tr("cfg.colors_confirm", default="Color de botones de confirmar"),
                         "confirmar_bg", cfg["confirmar_bg"])
        self._fila_color(ly, tr("cfg.colors_confirm_txt", default="Color del texto"),
                         "confirmar_texto", cfg["confirmar_texto"])

        _sep(tr("cfg.colors_g5", default="5 · BOTONES DE RETORNO"))
        self._fila_color(ly, tr("cfg.colors_back", default="Color de botones de retorno"),
                         "retorno_bg", cfg["retorno_bg"])
        self._fila_color(ly, tr("cfg.colors_back_txt", default="Color del texto"),
                         "retorno_texto", cfg["retorno_texto"])

        _sep(tr("cfg.colors_soma", default="SOMA · COLOR DEL PERSONAJE"))
        self._fila_color(ly, tr("cfg.colors_soma_lbl", default="Color de SOMA"), "soma_color",
                         cfg["soma_color"],
                         subtitulo=tr("cfg.colors_soma_sub",
                                      default="Tiñe al asistente SOMA con este color."))

        ly.addStretch()
        scroll.setWidget(cont)
        outer.addWidget(scroll, 1)

        # Botonera: RESTABLECER + GUARDAR.
        h = QHBoxLayout()
        btn_reset = QPushButton(tr("cfg.colors_reset", default="Restablecer"))
        btn_reset.setFixedSize(180, 48); btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:12px;font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}")
        btn_reset.clicked.connect(self._restablecer_colores)
        btn_save = QPushButton(tr("cfg.save", default="Guardar"))
        btn_save.setFixedSize(180, 48); btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(
            "QPushButton { background: #0E1117; color: #238636; border: 2px solid #238636; border-radius: 12px; font-weight: bold;"
            " font-size: 14px; }"
            "QPushButton:hover { background: #238636; color: #0E1117; }")
        btn_save.clicked.connect(self._guardar_colores)
        h.addStretch(); h.addWidget(btn_reset); h.addWidget(btn_save)
        outer.addLayout(h)
        return page

    def _guardar_colores(self):
        from src.utils import tema
        if tema.guardar(self._colores_sel):
            mostrar_mensaje(
                self, tr("cfg.saved_title", default="Guardado"),
                tr("cfg.colors_saved",
                   default="Colores guardados. Reinicia la aplicación para ver los cambios."),
                "success")
        else:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"),
                            tr("cfg.colors_save_err", default="No se pudieron guardar los colores."),
                            "error")

    def _restablecer_colores(self):
        from src.utils import tema
        tema.restablecer()
        mostrar_mensaje(
            self, tr("cfg.saved_title", default="Guardado"),
            tr("cfg.colors_reset_ok",
               default="Colores restablecidos a los valores por defecto. Reinicia la aplicación para "
                       "ver los cambios."),
            "success")

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
    _EmpSelectCell,   # RRHH Fase E: renombrada desde `_EmpNameEdit` (texto libre -> desplegable)
    _HorarioLoadingWidget,
    _AusenciaDialog,
    _HorarioTable,
    _HorarioSemana,
    _HorarioContainer,
)


# ── F3.0.3: diálogos de empleado extraídos a src/rrhh/gui/empleados.py ──
# Shim de compatibilidad (reexport): imports y referencias internas intactos.
from src.rrhh.gui.empleados import (  # noqa: E402,F401
    _PinDialog,
    _AsignarEmpleadoDialog,
    _IdentificacionEmpleadoDialog,
)


# ============================================================
# P4.1 — GESTIÓN DE CAJA EN VENTANA PROPIA
# ============================================================
class GestionCajaWindow(ConfiguracionWindow):
    """Ventana INDEPENDIENTE de Gestión de Caja (UX-TPV-01, P4/P4.1).

    REUTILIZA íntegramente la lógica de caja de ConfiguracionWindow (todos los
    métodos `_fn_*`, `_get_caja_estado`, `_crear_page_caja`, etc. se heredan). Solo
    cambia el contenedor: en vez de una pestaña dentro de Configuración, es una
    ventana propia accesible desde el Menú Principal y el TPV. NO duplica lógica.
    """

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabecera con título + botón de regreso (a la altura del título).
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color:{_PANEL_BG};border-bottom:1px solid #30363D;")
        h_ly = QHBoxLayout(header)
        h_ly.setContentsMargins(28, 0, 28, 0)
        titulo = QLabel(tr("cfg.tab_caja", default="GESTIÓN CAJA"))
        titulo.setStyleSheet("color:white;font-weight:900;font-size:16px;letter-spacing:1px;")
        h_ly.addWidget(titulo)
        h_ly.addStretch()
        btn_volver = QPushButton("✕")
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_volver.setFixedSize(50, 50)
        btn_volver.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;"
            "border-radius:25px;padding:0;font-family:'Segoe UI';font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0E1117;}"
        )
        btn_volver.setProperty("sin_glow", True)
        _blindar_tamano_fijo(btn_volver, 50, 50)
        btn_volver.clicked.connect(self.ejecutar_regreso)
        h_ly.addWidget(btn_volver)
        root.addWidget(header)

        # Página de caja reutilizada (misma construcción y lógica que en Configuración).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(self._crear_page_caja())
        root.addWidget(scroll)
