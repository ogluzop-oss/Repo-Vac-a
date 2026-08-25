"""
Servicio de DOCUMENTOS (registro/consulta de metadatos). Capa fina sobre `src/db/documentos.py`
para consumidores que no deben hablar con la BD directamente (p. ej. la REST API).

Alcance de esta iteración: SOLO lectura de metadatos (listar/buscar/obtener). La descarga del
fichero en sí vive en `src/services/storage/documentos.py` (backend de almacenamiento + URLs
firmadas) y queda fuera de este alcance por ahora — no se expone todavía en el móvil.
"""

# Campos seguros para un consumidor externo (REST): `ruta` es una ruta de disco DEL SERVIDOR y
# `storage_key`/`migracion_estado` son detalles internos de almacenamiento — no se exponen.
_CAMPOS_PUBLICOS = (
    "id_documento", "id_tienda", "tipo_documento", "nombre", "referencia", "cliente",
    "trabajador", "importe", "estado", "fecha_generacion", "mime_type", "size_bytes",
)


def _saneado(doc: dict) -> dict:
    return {k: doc.get(k) for k in _CAMPOS_PUBLICOS}


def buscar(id_empresa, texto: str = "", tipo: str | None = None, limite: int = 200) -> list[dict]:
    from src.db import documentos as _db
    docs = _db.listar_documentos(tipo=tipo, id_empresa=id_empresa, texto=texto or None,
                                 limite=limite)
    return [_saneado(d) for d in docs]


def obtener(id_empresa, id_documento: str) -> dict | None:
    """Ficha de un documento. Aísla por empresa aunque `db.obtener_documento` no filtre por
    id_empresa (solo busca por id): evita que un tenant vea el documento de otro por REST."""
    from src.db import documentos as _db
    doc = _db.obtener_documento(id_documento)
    if not doc or str(doc.get("id_empresa")) != str(id_empresa):
        return None
    return _saneado(doc)
