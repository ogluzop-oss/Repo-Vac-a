# src/utils/config.py
import platform

# Detección de Sistema Operativo
OS = platform.system()  # 'Windows', 'Darwin' (macOS), 'Linux'

APP_TITLE = "Smart Manager AI"
# Colores y estilos (puedes ajustar)
PRIMARY_COLOR = "#2D89EF"  # azul botones
DANGER_COLOR = "#D9534F"  # rojo cerrar sesión
BG_COLOR = "#F5F7FA"
CARD_COLOR = "#FFFFFF"
TEXT_COLOR = "#222222"
FONT_FAMILY = "Segoe UI, Arial"  # si falta, Qt usará la por defecto

# Tamaños
BTN_HEIGHT = 70
BTN_RADIUS = 12
