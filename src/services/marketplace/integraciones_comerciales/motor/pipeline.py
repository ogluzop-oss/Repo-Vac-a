"""
Motor · PIPELINE DE SINCRONIZACIÓN (Fase WEB-13). Define el orden canónico de pasos y arma el PLAN dirigido
por CAPACIDADES (nunca por `if plataforma`). NO ejecuta ninguna llamada externa: `ejecutar()` está preparado
(eleva `NotImplementedError`). El plan indica qué ámbitos entran según lo que la plataforma declara soportar.
"""

from src.services.marketplace.integraciones_comerciales.motor.capacidades import \
    capacidades

# Orden canónico del pipeline.
PASOS = ("VALIDAR", "AUTENTICAR", "DESCUBRIR", "IMPORTAR", "SINCRONIZAR", "VERIFICAR", "FINALIZAR")

# Ámbito de datos → capacidad requerida (dirige el plan por capacidades).
_AMBITO_CAPACIDAD = {
    "productos": "supports_products", "pedidos": "supports_orders", "clientes": "supports_customers",
    "stock": "supports_inventory", "precios": "supports_prices", "click_collect": "supports_click_collect",
    "reservas": "supports_click_collect", "estados": "supports_orders", "transportistas": "supports_tracking",
    "devoluciones": "supports_returns", "reviews": "supports_reviews",
}


class PipelineSincronizacion:
    """Pipeline de sincronización de UNA plataforma. Solo arma el plan (declarativo). Sin conexión real."""

    def __init__(self, plataforma):
        self.plataforma = (plataforma or "").lower()
        self.caps = capacidades(self.plataforma)

    def ambitos_soportados(self) -> list:
        """Ámbitos de datos que la plataforma soporta (según sus capacidades)."""
        return [amb for amb, cap in _AMBITO_CAPACIDAD.items() if self.caps.soporta(cap)]

    def plan(self) -> dict:
        """Plan del pipeline: pasos canónicos + ámbitos aplicables (por capacidades). No ejecuta nada."""
        return {"plataforma": self.plataforma, "pasos": list(PASOS),
                "ambitos": self.ambitos_soportados(), "estado": "PREPARADO"}

    def ejecutar(self, contexto=None) -> dict:
        raise NotImplementedError("pipeline preparado (Fase WEB-13: sin ejecución real)")
