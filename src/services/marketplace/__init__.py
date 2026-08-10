"""
Marketplace — App Store de Plugins y Extensiones (Fase IV · Bloque 2) — fachada pública (API-First).

App Store OFICIAL del ERP: amplía sus capacidades instalando/administrando PLUGINS, EXTENSIONES y
conectores oficiales (Cloudflare, Stripe, WooCommerce, Shopify, Amazon, SEUR/MRW/Correos, Microsoft
365/Google Workspace, etc.). NO es un canal de comercio electrónico ni gestiona negocio (Regla 5): solo
INSTALA y ADMINISTRA; la EJECUCIÓN de cada conector pertenece a su módulo consumidor (p. ej. Canal Web
ejecuta el conector de dominios/pasarela; el Marketplace solo lo instala). (Rearquitectura CD · Fase 3.)

Convierte el Plugin SDK existente en un Marketplace profesional SIN modificarlo: catálogo de
repositorios (oficial/privado/git/zip/local), firma digital, dependencias, licencias, política por
empresa e instalación con rollback. Reutiliza `src.sdk` para el estado instalado y el Corporate
Event Bus para los eventos. Multiempresa estricto.

    from src.services import marketplace
    marketplace.catalogo(id_empresa=emp)
    marketplace.instalar("mi_plugin", id_empresa=emp, usuario="admin")
    marketplace.rollback("mi_plugin", id_empresa=emp)
"""

from src.services.marketplace.servicio import (  # noqa: F401
    POLITICAS, POLITICA_DEFECTO, politica, fijar_politica, catalogo, categorias, detalle,
    instalar, desinstalar, reinstalar, rollback, verificar_integridad, historial,
    actualizar, actualizaciones_disponibles,
)
from src.services.marketplace import (  # noqa: F401
    firmas, validacion, dependencias, licencias, repositorios,
)
# Fase WEB-03: submódulo AMPLIADO "Integraciones Comerciales" (conexión con plataformas ecommerce). NO altera
# la gestión de plugins/"Extensiones Smart Manager"; es un bloque INDEPENDIENTE. Import perezoso para no
# acoplar el arranque; se accede como `marketplace.integraciones_comerciales`.
from src.services.marketplace import integraciones_comerciales  # noqa: F401

__all__ = ["POLITICAS", "POLITICA_DEFECTO", "politica", "fijar_politica", "catalogo", "categorias",
           "detalle", "instalar", "desinstalar", "reinstalar", "rollback", "verificar_integridad",
           "historial", "actualizar", "actualizaciones_disponibles",
           "firmas", "validacion", "dependencias", "licencias", "repositorios",
           "integraciones_comerciales"]
