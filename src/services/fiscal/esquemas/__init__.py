"""
Acceso a los esquemas XSD/WSDL de Verifactu (C3.3.1.1).

Localiza los ficheros (compatible con PyInstaller) y ofrece un validador XSD
basado en `lxml`. `lxml` es opcional en runtime: si no está disponible, la
validación se omite con elegancia (la conformidad se garantiza en tests/build).
Ver `PROCEDENCIA.md` para la trazabilidad oficial vs espejo.
"""

import logging
import os

logger = logging.getLogger("fiscal.esquemas")

# Namespaces oficiales (de los XSD de AEAT).
NS = {
    "sf": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
          "aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd",
    "sfLR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
            "aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd",
    "sfR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
           "aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
}


def dir_esquemas() -> str:
    """Carpeta con los .xsd/.wsdl (junto a este módulo, también en el .exe)."""
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        from src.utils.recursos import ruta_recurso, es_frozen
        if es_frozen():
            return ruta_recurso("src", "services", "fiscal", "esquemas")
    except Exception:
        pass
    return base


def ruta(nombre: str) -> str:
    return os.path.join(dir_esquemas(), nombre)


def validador(raiz_xsd: str = "SuministroLR.xsd"):
    """Devuelve un `lxml.etree.XMLSchema` (o None si lxml no está disponible)."""
    try:
        from lxml import etree
    except Exception:
        logger.debug("lxml no disponible: se omite la validación XSD en runtime.")
        return None
    return etree.XMLSchema(etree.parse(ruta(raiz_xsd)))


def validar(xml_bytes, raiz_xsd: str = "SuministroLR.xsd"):
    """Valida `xml_bytes` contra el XSD. Devuelve (ok: bool, errores: str).
    Si lxml no está, devuelve (True, "lxml-ausente") para no bloquear runtime."""
    try:
        from lxml import etree
    except Exception:
        return True, "lxml-ausente"
    try:
        sch = etree.XMLSchema(etree.parse(ruta(raiz_xsd)))
        doc = etree.fromstring(xml_bytes if isinstance(xml_bytes, bytes)
                               else xml_bytes.encode("utf-8"))
        ok = sch.validate(doc)
        return ok, ("" if ok else str(sch.error_log))
    except Exception as e:
        return False, str(e)
