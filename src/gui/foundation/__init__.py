"""
gui/foundation — capa base del sistema de UI Enterprise de Smart Manager AI.

REGLAS DE ARQUITECTURA (obligatorias, ver CLAUDE.md · sección "UI / Enterprise Shell"):
  1. Toda pantalla NUEVA se construye con el Enterprise Shell (`QtEnterpriseWindow`/`QtEnterprisePanel`)
     y la librería `gui/components/`. No se crean widgets/tablas/tarjetas/buscadores/toolbars fuera
     de la librería salvo justificación técnica documentada.
  2. La GUI NO implementa lógica de negocio: solo presentación/navegación/orquestación. La lógica
     vive en `services/` (y a futuro `domain/`/`repositories/`).
  3. Deprecación: al sustituir una pantalla no se elimina de inmediato (marcar @deprecated, mantener
     un ciclo, eliminar solo cuando no queden referencias).
  4. Migración incremental (Strangler Pattern): prohibido reescribir módulos completos.

DIRECCIÓN DE DEPENDENCIAS: Foundation → Components → Panels → Windows. **Foundation NUNCA depende de
Components.** Este paquete solo contiene primitivas: tokens, iconografía, permisos, exportación,
shell y eventos.
"""

from src.gui.foundation import events, export, icons, permissions, tokens  # noqa: F401

__all__ = ["tokens", "icons", "permissions", "export", "events"]
