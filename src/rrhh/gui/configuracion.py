"""
Punto de entrada RRHH — ConfiguracionWindow (F3.0.1).

Fachada de compatibilidad: reexporta la ventana SIN modificar su implementación, que
permanece en `gui/gestion_usuarios.py`. Establece la ruta de import objetivo del
módulo RRHH; cuando la implementación se traslade aquí (fase futura), los consumidores
ya no tendrán que cambiar el import.
"""

from src.gui.gestion_usuarios import ConfiguracionWindow  # noqa: F401  (reexport intencionado)

__all__ = ["ConfiguracionWindow"]
