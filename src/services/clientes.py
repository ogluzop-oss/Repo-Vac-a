"""
Servicio de CLIENTES (directorio comercial). Capa fina sobre `src/db/clientes.py` para consumidores
que no deben hablar con la BD directamente (p. ej. la REST API) — no reimplementa reglas de negocio,
delega íntegramente en la capa de datos ya usada por el TPV de escritorio.
"""


def buscar(id_empresa, texto: str = "", limite: int = 50) -> list[dict]:
    """Búsqueda de clientes activos por nombre/NIF/teléfono/email, acotada por empresa."""
    from src.db import clientes as _db
    return _db.buscar_clientes(texto or "", id_empresa=id_empresa, limite=limite)


def obtener(id_empresa, cliente_id) -> dict | None:
    """Ficha de un cliente. Aísla por empresa aunque `db.obtener_cliente` no filtre por id_empresa
    (solo busca por id): evita que un tenant vea el cliente de otro por REST."""
    from src.db import clientes as _db
    cliente = _db.obtener_cliente(cliente_id)
    if not cliente or str(cliente.get("id_empresa")) != str(id_empresa):
        return None
    return cliente
