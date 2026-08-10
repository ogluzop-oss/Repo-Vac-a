"""
Design tokens del sistema Enterprise (Foundation). Fuente ÚNICA de color, tipografía y espaciado.
Alineado con el tema oscuro+cian ya existente (`catalogo_gestion` / `assets/estilo_global`), para no
romper la identidad visual actual. Sin dependencia de Qt (solo constantes y helpers de QSS).

Colores SEMÁNTICOS (rol → color), no colores sueltos:
    INFO=cian · ANALISIS=azul · ADVERTENCIA=naranja · CRITICO=rojo · OK=verde
"""

# ── Base (heredada del tema actual) ───────────────────────────────────────────
BG = "#0E1117"
BG2 = "#161B22"
SIDEBAR = "#111418"
BORDE = "#30363D"
TEXT = "#E6EDF3"
DIM = "#8B949E"
FONT = "Segoe UI"

# ── Colores semánticos (rol → color) ──────────────────────────────────────────
INFO = "#00FFC6"        # cian    — información / acento principal
ANALISIS = "#4EA1FF"    # azul    — análisis / datos
ADVERTENCIA = "#FFB020"  # naranja — advertencia
CRITICO = "#F85149"     # rojo    — crítico / error
OK = "#3FB950"          # verde   — correcto / éxito
NEUTRO = DIM

COLOR = {
    "info": INFO, "analisis": ANALISIS, "advertencia": ADVERTENCIA,
    "critico": CRITICO, "ok": OK, "neutro": NEUTRO,
}

# Mapa de nivel de riesgo → color semántico (reutilizado por RiskIndicator/StatusBadge).
RIESGO_COLOR = {"BAJO": OK, "MEDIO": ADVERTENCIA, "ALTO": CRITICO,
                "OK": OK, "ADVERTENCIA": ADVERTENCIA, "CRITICO": CRITICO}


def color(rol: str) -> str:
    """Devuelve el color de un rol semántico (por defecto, acento INFO)."""
    return COLOR.get(str(rol).lower(), INFO)


def color_riesgo(nivel: str) -> str:
    return RIESGO_COLOR.get(str(nivel).upper(), NEUTRO)


# ── Espaciado ─────────────────────────────────────────────────────────────────
SPACING_XS, SPACING_S, SPACING_M, SPACING_L = 4, 8, 12, 20
RADIO = 10


# ── Helpers de QSS (strings; no crean widgets) ────────────────────────────────
def qss_panel() -> str:
    return f"background:{BG};color:{TEXT};font-family:'{FONT}';"


def qss_titulo(acento: str = INFO) -> str:
    return f"color:{acento};font-size:20px;font-weight:bold;background:transparent;border:none;"


def qss_tarjeta(acento: str = INFO) -> str:
    return (f"background:{BG2};border:1px solid {BORDE};border-left:4px solid {acento};"
            f"border-radius:{RADIO}px;")


def qss_scrollbar(acento: str = INFO) -> str:
    """Scrollbars con la barra (handle) turquesa y EXTREMOS REDONDEADOS. El `margin` en el handle es
    imprescindible para que el border-radius se renderice como extremos redondeados (si el handle toca
    los bordes del groove, Qt lo dibuja cuadrado)."""
    return (
        f"QScrollBar:vertical{{background:transparent;width:16px;margin:0;}}"
        f"QScrollBar::handle:vertical{{background:{acento};min-height:36px;border-radius:5px;margin:3px;}}"
        f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;width:0;}}"
        f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}"
        f"QScrollBar:horizontal{{background:transparent;height:16px;margin:0;}}"
        f"QScrollBar::handle:horizontal{{background:{acento};min-width:36px;border-radius:5px;margin:3px;}}"
        f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;height:0;}}"
        f"QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{{background:transparent;}}")


def qss_tabla() -> str:
    """Estilo ESTÁNDAR de tabla de la app (idéntico a catalogo_gestion._tabla): contorno neón
    turquesa, cabeceras con hover swap y esquinas redondeadas. Fuente única para todas las tablas."""
    return f"""
        QTableWidget{{background:{BG};color:{TEXT};border:2px solid {INFO};border-radius:12px;
                      gridline-color:{BORDE};font-family:'{FONT}';font-size:13px;outline:none;}}
        QHeaderView::section{{background:{BG};color:{INFO};border:none;
                              border-bottom:2px solid {BORDE};padding:8px;font-weight:900;font-size:11px;}}
        QHeaderView::section:hover{{background:{INFO};color:{BG};}}
        QHeaderView::section:first{{border-top-left-radius:12px;}}
        QHeaderView::section:last{{border-top-right-radius:12px;}}
        QTableWidget::item{{padding:6px;}}
        QTableWidget::item:selected{{background:#00FFC622;color:white;}}
        QScrollBar:vertical{{background:transparent;width:16px;margin:0;}}
        QScrollBar::handle:vertical{{background:{INFO};min-height:36px;border-radius:5px;margin:3px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;width:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}
        QScrollBar:horizontal{{background:transparent;height:16px;margin:0;}}
        QScrollBar::handle:horizontal{{background:{INFO};min-width:36px;border-radius:5px;margin:3px;}}
        QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;height:0;}}
        QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{{background:transparent;}}"""


def qss_tabs() -> str:
    """Estilo ESTÁNDAR de pestañas (el del Centro de Inteligencia Empresarial). Fuente única para
    todas las ventanas con QTabWidget, para una experiencia homogénea."""
    return (
        f"QTabWidget::pane{{border:1px solid {BORDE};border-radius:{RADIO}px;background:{BG};}}"
        f"QTabBar::tab{{background:{BG2};color:{DIM};padding:8px 16px;margin-right:2px;"
        f"border-top-left-radius:8px;border-top-right-radius:8px;font-family:'{FONT}';font-weight:700;}}"
        f"QTabBar::tab:selected{{background:{BG};color:{INFO};border:1px solid {BORDE};"
        f"border-bottom:2px solid {INFO};}}"
        f"QTabBar::tab:hover{{color:{INFO};}}")


def qss_boton(acento: str = INFO) -> str:
    """Botón Enterprise estándar (relleno al hover)."""
    return (f"QPushButton{{background:{BG2};color:{acento};border:2px solid {acento};"
            f"border-radius:8px;font-weight:800;padding:6px 14px;}}"
            f"QPushButton:hover{{background:{acento};color:{BG};}}")
