"""
Comunicación interna de la empresa (dentro del módulo de Correo): CIRCULARES y ENCUESTAS entre centros.

Bandeja única para publicar circulares (con confirmación de lectura por centro) y encuestas
personalizables (preguntas de opciones o de texto, opción "Otro", texto introductorio), con adjuntos
de texto/imagen tanto en el envío como en las respuestas. Multiempresa estricto (aislamiento por
id_empresa). Reutiliza usuarios (perfil+contraseña), centros y documentos existentes; sin motor nuevo.
"""

from . import adjuntos, circulares, encuestas  # noqa: F401

__all__ = ["adjuntos", "circulares", "encuestas"]
