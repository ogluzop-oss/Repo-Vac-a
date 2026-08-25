"""Integración de Smart Stock con IOC (Bloque III.2). Adaptador de identidad sobre IdentityAPI."""


def buscar(id_empresa, texto: str = "", id_familia=None, limite: int = 100) -> list[dict]:
    """Búsqueda de artículos + niveles de stock (tienda/total/central) por código o nombre. Capa fina
    sobre `src/db/articulos.py::buscar_stock` para consumidores que no deben hablar con la BD
    directamente (p. ej. la REST API)."""
    from src.db import articulos as _db
    filas = _db.buscar_stock(texto or "", id_familia=id_familia, id_empresa=id_empresa)
    out = []
    for codigo, nombre, tienda, total, central in filas[:limite]:
        out.append({"codigo": codigo, "nombre": nombre, "stock_tienda": tienda,
                    "stock_total": total, "stock_central": central})
    return out
