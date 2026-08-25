"""
Servicio de PROVEEDORES. Capa fina sobre `src/db/proveedores.py` para consumidores que no deben
hablar con la BD directamente (p. ej. la REST API) — no reimplementa reglas de negocio.
"""


def buscar(id_empresa, texto: str = "", limite: int = 50) -> list[dict]:
    """Búsqueda de proveedores por razón social/nombre comercial/CIF, acotada por empresa."""
    from src.db import proveedores as _db
    return _db.listar_proveedores(id_empresa=id_empresa, texto=texto or None, limite=limite)


def obtener(id_empresa, id_proveedor) -> dict | None:
    """Ficha de un proveedor (ya filtrada por empresa en la propia consulta SQL)."""
    from src.db import proveedores as _db
    return _db.obtener_proveedor(id_proveedor, id_empresa=id_empresa)
