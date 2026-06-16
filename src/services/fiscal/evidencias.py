"""
Evidencias fiscales (C3.2) — los artefactos completos (XML, firma, acuses, QR)
viven como FICHEROS en `documentos/fiscal/` y se indexan en el CENTRO DOCUMENTAL
(`documentos_registro`). La BD fiscal guarda solo referencias/metadatos/hash/estado.

Patrón válido para Verifactu y Facturae: el núcleo no almacena binarios; deja una
evidencia trazable (ruta + hash) enlazada al registro fiscal por su `referencia`.
"""

import hashlib
import logging
import os

logger = logging.getLogger("fiscal.evidencias")

# clase de evidencia → (tipo del centro documental, extensión por defecto)
_CLASES = {
    "xml":   ("factura", "xml"),     # factura/ticket XML (Verifactu/Facturae)
    "firma": ("certificado", "xml"),  # firma XAdES / artefacto firmado
    "acuse": ("auditoria", "xml"),   # acuse/respuesta de la hacienda/integrador
    "qr":    ("otros", "png"),       # imagen del QR de cotejo
}


def _dir_evidencias(id_empresa: str) -> str:
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("fiscal", str(id_empresa))
    except Exception:
        base = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "documentos", "fiscal", str(id_empresa)))
    os.makedirs(base, exist_ok=True)
    return base


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ref(registro) -> tuple:
    """(referencia textual, serie, numero, id) de un registro (dict o RegistroFiscal)."""
    g = (lambda k: registro.get(k)) if isinstance(registro, dict) else (lambda k: getattr(registro, k, None))
    serie, numero = g("serie") or "A", g("numero") or 0
    return f"{serie}-{numero}", serie, numero, g("id")


def guardar_evidencia(registro, clase: str, contenido, extension: str | None = None,
                      id_empresa=None, id_tienda=None) -> dict | None:
    """Persiste una evidencia de `registro` como fichero + alta en el centro
    documental. `contenido` puede ser bytes o str. Devuelve
    {ruta, hash, id_documento, referencia} o None si falla.

    No escribe binarios en la BD fiscal: solo deja la referencia trazable."""
    tipo_doc, ext_def = _CLASES.get(clase, ("otros", "bin"))
    ext = (extension or ext_def).lstrip(".")
    ref, serie, numero, _id = _ref(registro)
    datos = contenido.encode("utf-8") if isinstance(contenido, str) else (contenido or b"")
    try:
        ruta = os.path.join(_dir_evidencias(id_empresa or _empresa_de(registro)),
                            f"{serie}_{numero}_{clase}.{ext}")
        with open(ruta, "wb") as f:
            f.write(datos)
        h = _hash_bytes(datos)
        id_doc = None
        try:
            from src.db.documentos import registrar_documento
            importe = registro.get("total") if isinstance(registro, dict) else getattr(registro, "total", None)
            id_doc = registrar_documento(
                ruta=ruta, tipo=tipo_doc, referencia=ref, importe=importe,
                estado="generado", hash_documental=h,
                id_empresa=id_empresa, id_tienda=id_tienda)
        except Exception as e:
            logger.warning("Evidencia guardada pero no indexada en el centro documental: %s", e)
        return {"ruta": ruta, "hash": h, "id_documento": id_doc, "referencia": ref}
    except Exception as e:
        logger.error("guardar_evidencia(%s/%s): %s", ref, clase, e)
        return None


def _empresa_de(registro):
    if isinstance(registro, dict) and registro.get("id_empresa"):
        return registro["id_empresa"]
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID
