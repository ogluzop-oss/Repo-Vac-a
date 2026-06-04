# src/utils/config.py
import platform

# ============================================================
# BLOQUE DETECCIÓN DE SISTEMA OPERATIVO
# ============================================================

OS = platform.system()  # 'Windows', 'Darwin' (macOS), 'Linux'


# ============================================================
# BLOQUE IDENTIDAD DE LA APLICACIÓN
# ============================================================

APP_TITLE = "Smart Manager"


# ============================================================
# BLOQUE COLORES Y ESTILOS
# ============================================================

PRIMARY_COLOR = "#2D89EF"   # azul botones
DANGER_COLOR  = "#D9534F"   # rojo cerrar sesión
BG_COLOR      = "#F5F7FA"
CARD_COLOR    = "#FFFFFF"
TEXT_COLOR    = "#222222"
FONT_FAMILY   = "Segoe UI, Arial"


# ============================================================
# BLOQUE DIMENSIONES DE COMPONENTES
# ============================================================

BTN_HEIGHT = 70
BTN_RADIUS = 12
