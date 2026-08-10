"""
Integraciones Comerciales (Fase WEB-02) — arquitectura PREPARADA que **Marketplace** asumirá para conectar
plataformas externas. El Canal Web (Escenario B: la empresa YA tiene web) redirige aquí; Marketplace realiza
la integración. NO modifica `services/marketplace/*` ni implementa integraciones reales todavía.

Reutilización futura (N7): la persistencia de plataforma externa es `db/ecommerce.py` (Escenario A); los
conectores concretos vivirán aquí como `ConectorComercial`. Nada se conecta ni se ejecuta en esta fase.
"""

from src.services.comercio_digital.integraciones_comerciales import catalogo
from src.services.comercio_digital.integraciones_comerciales.base import \
    ConectorComercial

# Identificador del apartado que hospedará Marketplace.
APARTADO = "integraciones_comerciales"
ESTADO = "PREPARADO"   # ninguna integración implementada


def listar_plataformas(tipo=None) -> list:
    return catalogo.listar(tipo)


def descriptor() -> dict:
    return {"apartado": APARTADO, "estado": ESTADO, "propietario": "marketplace",
            "origen_redireccion": "canal_web", "plataformas": catalogo.listar()}


__all__ = ["APARTADO", "ESTADO", "ConectorComercial", "listar_plataformas", "descriptor", "catalogo"]
