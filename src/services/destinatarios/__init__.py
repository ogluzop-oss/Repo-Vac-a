"""
Servicio Corporativo de Resolución de Destinatarios (fachada pública).

PUNTO ÚNICO oficial de resolución de destinatarios de Smart Manager AI (restricción 1). Cualquier
canal (Correo, WhatsApp, SMS, push, IA, Bots, Firma, envío documental) debe resolver destinatarios
EXCLUSIVAMENTE a través de esta API. No consultar clientes/proveedores/empleados/usuarios por su
cuenta para localizar correos.

Uso típico:
    from src.services import destinatarios
    for d in destinatarios.buscar_destinatarios(id_empresa, "merca", contexto="compras"):
        d.correo, d.nombre_mostrado, d.tipo, d.etiqueta, d.avisos, d.favorito, d.score

Extensión (nuevas fuentes) — restricción 2:
    from src.services.destinatarios.fuentes import registrar_fuente, FuenteTabla
    registrar_fuente(FuenteTabla("mi_entidad", "mi_tabla", "mi_tipo", cols_nombre=("nombre",)))
"""

from src.services.destinatarios.modelo import Destinatario  # noqa: F401
# OJO: no exponer aquí la función `fuentes` (colisiona con el submódulo `fuentes`); se expone como
# `listar_fuentes` para evitar ensombrecer el submódulo al importar el paquete.
from src.services.destinatarios.fuentes import (  # noqa: F401
    FuenteBase, FuenteTabla, registrar_fuente, fuentes as listar_fuentes,
)
from src.services.destinatarios.servicio import (  # noqa: F401
    buscar_destinatarios, resolver_para_documento, registrar_envio, marcar_favorito,
    quitar_favorito, registrar_politica,
)

__all__ = [
    "buscar_destinatarios", "resolver_para_documento", "registrar_envio", "marcar_favorito",
    "quitar_favorito", "registrar_politica", "registrar_fuente", "listar_fuentes",
    "FuenteBase", "FuenteTabla", "Destinatario",
]
