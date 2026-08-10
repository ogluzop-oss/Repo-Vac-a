"""
Motor · PIPELINE DE IMPORTACIÓN (Fase WEB-13). Interfaces SEPARADAS por dominio (plataforma → Smart Manager).
Todos los métodos elevan `NotImplementedError`: arquitectura preparada, sin ninguna llamada externa.
"""

from abc import ABC, abstractmethod


class _ImportadorBase(ABC):
    dominio = "base"

    @abstractmethod
    def importar(self, *, id_empresa=None, id_tienda=None, modo="incremental", cursor=None) -> dict: ...


def _importador(dominio):
    def importar(self, *, id_empresa=None, id_tienda=None, modo="incremental", cursor=None) -> dict:
        raise NotImplementedError(f"importación de {dominio} preparada (sin conexión real)")
    return type(f"Importador{dominio.capitalize()}", (_ImportadorBase,),
               {"dominio": dominio, "importar": importar})


ImportadorProductos = _importador("productos")
ImportadorClientes = _importador("clientes")
ImportadorPedidos = _importador("pedidos")
ImportadorStock = _importador("stock")
ImportadorPrecios = _importador("precios")
ImportadorEstados = _importador("estados")
ImportadorTransportistas = _importador("transportistas")
ImportadorReservas = _importador("reservas")
ImportadorClickCollect = _importador("click_collect")

IMPORTADORES = {
    "productos": ImportadorProductos, "clientes": ImportadorClientes, "pedidos": ImportadorPedidos,
    "stock": ImportadorStock, "precios": ImportadorPrecios, "estados": ImportadorEstados,
    "transportistas": ImportadorTransportistas, "reservas": ImportadorReservas,
    "click_collect": ImportadorClickCollect,
}
