"""
Iconografía ÚNICA del sistema Enterprise (Foundation). Un solo icono por concepto, para eliminar la
proliferación de iconos distintos para la misma idea. Registro `ICON[concepto]`. Se usan glifos
(emoji/Unicode) por coherencia con el resto de la app y por portabilidad; un futuro tema por SVG solo
tendría que sustituir este mapa sin tocar el resto.
"""

ICON = {
    # Dominios / paquetes Enterprise
    "inteligencia": "🧠",
    "dashboard": "📊",
    "actividad": "📡",
    "gemelo": "🌐",
    "prediccion": "🔮",
    "simulador": "🧪",
    "gobierno": "🏛️",
    "automatizacion": "⚙️",
    "autonomia": "🤖",
    "workflow": "🗂️",
    "historial": "🕓",
    "ia": "✨",
    # Conceptos transversales (un único icono por concepto)
    "riesgo": "⚠️",
    "ok": "✅",
    "critico": "⛔",
    "info": "ℹ️",
    "analisis": "📈",
    "alerta": "🔔",
    "tarea": "📋",
    "exportar": "📤",
    "buscar": "🔍",
    "filtro": "⛃",
    "actualizar": "🔄",
    "empresa": "🏢",
    "tienda": "🏬",
    "usuario": "👤",
    "dinero": "💶",
    "stock": "📦",
}


def icon(concepto: str) -> str:
    """Glifo único para un concepto (cadena vacía si no existe, nunca falla)."""
    return ICON.get(str(concepto).lower(), "")


def etiqueta(concepto: str, texto: str) -> str:
    """Compone 'icono texto' de forma homogénea para títulos de pestaña/tarjeta."""
    g = icon(concepto)
    return f"{g} {texto}".strip()
