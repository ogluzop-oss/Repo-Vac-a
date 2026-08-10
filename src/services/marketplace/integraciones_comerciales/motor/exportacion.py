"""
Motor · PIPELINE DE EXPORTACIÓN (Fase WEB-13). Interfaces SEPARADAS (Smart Manager → plataforma). Todos los
métodos elevan `NotImplementedError`: arquitectura preparada, sin ejecutar nada.
"""

from abc import ABC, abstractmethod


class _ExportadorBase(ABC):
    accion = "base"

    @abstractmethod
    def exportar(self, payload, *, id_empresa=None, id_tienda=None) -> dict: ...


def _exportador(accion):
    def exportar(self, payload, *, id_empresa=None, id_tienda=None) -> dict:
        raise NotImplementedError(f"exportación '{accion}' preparada (sin conexión real)")
    nombre = f"Exportador{''.join(p.capitalize() for p in accion.split('_'))}"
    return type(nombre, (_ExportadorBase,), {"accion": accion, "exportar": exportar})


ExportadorActualizarStock = _exportador("actualizar_stock")
ExportadorCrearPedidos = _exportador("crear_pedidos")
ExportadorActualizarPedidos = _exportador("actualizar_pedidos")
ExportadorActualizarEstados = _exportador("actualizar_estados")
ExportadorActualizarClientes = _exportador("actualizar_clientes")
ExportadorActualizarPrecios = _exportador("actualizar_precios")

EXPORTADORES = {
    "actualizar_stock": ExportadorActualizarStock, "crear_pedidos": ExportadorCrearPedidos,
    "actualizar_pedidos": ExportadorActualizarPedidos, "actualizar_estados": ExportadorActualizarEstados,
    "actualizar_clientes": ExportadorActualizarClientes, "actualizar_precios": ExportadorActualizarPrecios,
}
