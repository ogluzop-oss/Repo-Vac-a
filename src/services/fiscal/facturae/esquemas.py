"""
Validación XSD de Facturae (C3.4) con resolución OFFLINE de xmldsig.

El XSD de Facturae importa `xmldsig-core-schema.xsd` desde una URL de w3.org. Para
validar sin red (y dentro del .exe) se intercepta ese import con un resolver de lxml
que devuelve el fichero local, SIN modificar el XSD oficial. `lxml` es dev/build
(opcional en runtime: si falta, la validación se omite con elegancia).
"""

import logging
import os

from src.services.fiscal.facturae import _XSD, NS_FACTURAE

logger = logging.getLogger("fiscal.facturae.esquemas")


def _dir() -> str:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "esquemas", "facturae")
    try:
        from src.utils.recursos import es_frozen, ruta_recurso
        if es_frozen():
            return ruta_recurso("src", "services", "fiscal", "esquemas", "facturae")
    except Exception:
        pass
    return os.path.normpath(base)


def _ruta_xmldsig() -> str:
    return os.path.normpath(os.path.join(_dir(), "..", "xmldsig-core-schema.xsd"))


def ruta_xsd(version: str = "3.2.2") -> str:
    return os.path.join(_dir(), _XSD.get(version, _XSD["3.2.2"]))


def _schema(version: str):
    """Compila el XSD de Facturae resolviendo xmldsig al fichero local."""
    from lxml import etree

    xmldsig_local = _ruta_xmldsig()

    class _Resolver(etree.Resolver):
        def resolve(self, url, pubid, context):
            if "xmldsig-core-schema" in (url or ""):
                return self.resolve_filename(xmldsig_local, context)
            return None

    parser = etree.XMLParser()
    parser.resolvers.add(_Resolver())
    doc = etree.parse(ruta_xsd(version), parser)
    return etree.XMLSchema(doc)


def validar(xml_bytes, version: str = "3.2.2") -> tuple:
    """(ok, errores) validando contra el XSD de Facturae. Si lxml no está, (True, 'lxml-ausente')."""
    try:
        from lxml import etree
    except Exception:
        return True, "lxml-ausente"
    try:
        sch = _schema(version)
        doc = etree.fromstring(xml_bytes if isinstance(xml_bytes, bytes) else xml_bytes.encode("utf-8"))
        ok = sch.validate(doc)
        return ok, ("" if ok else str(sch.error_log))
    except Exception as e:
        return False, str(e)
