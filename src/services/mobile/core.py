"""
Mobile · Core (Fase V · Bloque 1). Configuración y capacidades de la plataforma móvil. Declara las
plataformas soportadas y las funcionalidades previstas (todas sobre la REST API oficial). Sin BD.
"""

from __future__ import annotations

PLATAFORMAS = ("android", "ios")

# Funcionalidades previstas → recurso REST oficial que las alimenta (nunca SQL).
# Rediseño móvil (Grupo A + Grupo B): el móvil ya NO es una versión reducida de escritorio — solo cubre
# pasos que exigen presencia física (escanear un código/QR, caminar hasta una ubicación, fotografiar
# algo in situ) que un PC de escritorio no puede ejecutar. Cada capacidad corresponde a un momento
# concreto de ese tipo (ver `mobile_client/src/api/capabilities.ts`, espejo 1:1 con comentarios por
# capacidad). Todo lo que sea buscar/listar/formulario sin componente físico se queda en escritorio.
CAPACIDADES = {
    "login": "/api/v1/auth/login",
    "stock": "/api/v1/stock/inventory",
    "mermas": "/api/v1/losses",
    "logistica": "/api/v1/logistics/transfers",
    "ubicacion": "/api/v1/location",
    "etiquetas": "/api/v1/labels/esl",
    "pedidos": "/api/v1/distribution/picking",
    "gmao": "/api/v1/gmao/assets",
    "calidad": "/api/v1/calidad/inspections",
    "sat": "/api/v1/sat/tickets",
    "transporte": "/api/v1/transporte/routes",
    "obrador": "/api/v1/obrador/parts",
    "mrp": "/api/v1/mrp/orders",
    # Correo: ÚNICA excepción deliberada a la regla de "solo presencia física" de arriba — no hay
    # componente físico, pero sí urgencia real (leer/responder una circular o un correo urgente sin
    # esperar a volver al escritorio). Alcance recortado a propósito frente a escritorio (sin
    # borradores/papelera/programados/pospuestos/estrella — ver mobile_client/src/screens/
    # CorreoScreen.tsx), igual que el resto del catálogo recorta formularios/administración.
    "correo": "/api/v1/correo/bandeja",
    # Gastos de viaje: ÚNICA pieza de autoservicio RRHH que vuelve al móvil (petición explícita,
    # decisión confirmada tras auditoría) — fotografiar el ticket EN EL MOMENTO con lectura
    # automática por IA SÍ tiene componente físico (misma lógica que Mermas/Calidad/SAT).
    # Nóminas/vacaciones/documentos pendientes de firma se quedan en escritorio (Portal del
    # Empleado, RRHH) — son formularios/consultas sin componente físico.
    "gastos_viaje": "/api/v1/rrhh/me/gastos",
    # Info Artículo (petición explícita, solo 2 de las 4 pestañas de escritorio): "Imagen artículo"
    # es Grupo B puro (fotografiar el artículo EN EL LINEAL, igual que Mermas/Calidad/SAT/Obrador/
    # MRP). "Buscar artículo" se incluye junto a ella por la misma petición explícita — consultar
    # stock/ubicación/precio DE PIE delante de la estantería, sin ir a buscar un terminal de
    # escritorio, es el caso de uso real. "Editar artículo" y "Familias" (administración pura, sin
    # componente físico) se quedan en escritorio. La ficha mostrada es la MISMA que escritorio, sin
    # excepción — ver `api/routers/articles.py::articles_ficha` (reutiliza, no duplica).
    "info_articulo": "/api/v1/articles",
}
# "articulo_scan" y "escaneo_remoto" retirados: eran pantallas redundantes con el botón "Escanear"
# ya existente (que ahora, al pulsarlo, atiende directamente cualquier solicitud de escaneo remoto en
# curso — ver `EscaneoRemotoOverlay` en el cliente móvil). No sustituyen a un capítulo del catálogo,
# se retiran del todo.

# Capacidad móvil → función segmentable de `services.verticales` que la gatea (MISMO motor que ya usa
# escritorio: `verticales.visible(...)`, sin duplicar la matriz de reglas). Solo se listan las
# capacidades que de verdad varían por edición/vertical — el resto son transversales (siempre
# visibles en toda instalación, cualquiera que sea su tipo de comercio).
_CAPACIDAD_A_FUNCION = {
    "mrp": "almacenes.mrp",
    "obrador": "bakery.obrador",
    "transporte": "transporte.reparto",
    "pedidos": "distribucion.expedicion",
}

# Capas de la arquitectura móvil (contrato para la futura app nativa).
CAPAS = ("core", "networking", "auth", "sync", "cache_offline", "actualizaciones",
         "push", "sesion")

VERSION = "1.0.0"


def capacidades_visibles() -> list:
    """Claves de `CAPACIDADES` visibles en la edición/vertical de ESTA instalación — la misma que ya
    decide qué módulos de escritorio se ven u ocultan (`services.verticales`), para que el móvil
    nunca muestre módulos de ediciones mutuamente excluyentes (p. ej. Obrador y MRP a la vez: solo
    UNA edición está activa por instalación)."""
    try:
        from src.services import verticales
        ocultas = {cap for cap, fn in _CAPACIDAD_A_FUNCION.items() if not verticales.visible(fn)}
    except Exception:
        ocultas = set()
    return [k for k in CAPACIDADES if k not in ocultas]


def descriptor() -> dict:
    """Descriptor de la plataforma móvil (para el Service Registry / documentación)."""
    return {
        "version": VERSION,
        "plataformas": list(PLATAFORMAS),
        "capas": list(CAPAS),
        "capacidades": CAPACIDADES,
        "comunicacion": "rest",     # SIEMPRE REST API oficial; nunca SQL ni servicios internos
        "offline_first": True,
        "seguridad": ["oauth", "jwt", "refresh_token", "pin", "biometria", "mfa", "revocacion"],
    }


__all__ = ["PLATAFORMAS", "CAPACIDADES", "CAPAS", "VERSION", "descriptor", "capacidades_visibles"]
