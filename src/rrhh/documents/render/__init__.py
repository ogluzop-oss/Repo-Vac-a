"""Servicios de render documental RRHH (F3.0.4b)."""

from src.rrhh.documents.render.render_contrato import render_contrato  # noqa: F401
from src.rrhh.documents.render.render_nomina import render_nomina  # noqa: F401
from src.rrhh.documents.render.render_carta_despido import render_carta_despido  # noqa: F401
from src.rrhh.documents.render.render_certificado import render_certificado  # noqa: F401
from src.rrhh.documents.render.render_alta_baja import render_alta_baja  # noqa: F401
from src.rrhh.documents.render.render_finiquito import render_finiquito  # noqa: F401
from src.rrhh.documents.render.render_generico import render_generico  # noqa: F401
from src.rrhh.documents.render.render_cert_laboral import render_cert_laboral  # noqa: F401
from src.rrhh.documents.render.render_vacaciones import render_vacaciones  # noqa: F401

__all__ = ["render_contrato", "render_nomina", "render_carta_despido", "render_certificado",
           "render_alta_baja", "render_finiquito", "render_generico",
           "render_cert_laboral", "render_vacaciones"]
