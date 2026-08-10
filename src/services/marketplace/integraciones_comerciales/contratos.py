"""
Integraciones Comerciales · CONTRATOS reutilizables (Fase WEB-03). Interfaces que cada plataforma ecommerce
implementará. En esta fase TODOS los métodos elevan `NotImplementedError`: la arquitectura queda preparada,
sin ninguna conexión real (ni API, ni OAuth, ni webhooks). Preparados para: OAuth · API Keys · Webhooks ·
Polling · sync incremental/completa · jobs · colas · reintentos (nada implementado todavía).
"""


class ConectorMarketplace:
    """Contrato base de un conector de plataforma. Gestiona conexión/credenciales/estado. Las
    implementaciones NUNCA guardan credenciales en claro (Secret Manager). Todo DEGRADABLE."""

    plataforma = "base"

    def disponible(self) -> bool:
        return False

    def validar_credenciales(self, config) -> bool:
        raise NotImplementedError("integración no implementada (Fase WEB-03: solo arquitectura)")

    def conectar(self, config) -> dict:
        raise NotImplementedError

    def desconectar(self) -> dict:
        raise NotImplementedError


class ConectorProductos:
    def sincronizar_productos(self, *, id_empresa=None, modo="incremental") -> dict:
        raise NotImplementedError


class ConectorPedidos:
    def sincronizar_pedidos(self, *, id_empresa=None, modo="incremental") -> dict:
        raise NotImplementedError


class ConectorClientes:
    def sincronizar_clientes(self, *, id_empresa=None, modo="incremental") -> dict:
        raise NotImplementedError


class ConectorInventario:
    def sincronizar_stock(self, *, id_empresa=None) -> dict:
        raise NotImplementedError


class ConectorPrecios:
    def sincronizar_precios(self, *, id_empresa=None) -> dict:
        raise NotImplementedError


# Conjunto de contratos que una plataforma completa debe cubrir.
CONTRATOS = (ConectorMarketplace, ConectorProductos, ConectorPedidos, ConectorClientes,
             ConectorInventario, ConectorPrecios)
