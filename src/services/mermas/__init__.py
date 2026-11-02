"""Capa fina de mermas para consumidores que no deben hablar con la BD directamente (p. ej. la REST
API). Delega en `db.mermas` (motor completo: descuento de stock, kárdex, FEFO, ledger multialmacén y
publicación del evento `MERMA_REGISTRADA` — no se reimplementa nada de eso aquí, solo se mapea el
`origen` del formulario a la columna de stock y se resuelven nombres para el listado)."""

_ORIGEN_A_COLUMNA = {"lineal": "Stock_tienda", "almacen": "Stock_total"}


def registrar(id_empresa, id_tienda, codigo, cantidad, motivo, origen) -> dict:
    """`origen`: 'lineal' (stock de tienda) o 'almacen' (stock de almacén) — mismas dos opciones que
    el escritorio (`gui/gestion_mermas.py`, "STOCK LINEAL"/"STOCK ALMACÉN")."""
    codigo = (codigo or "").strip()
    motivo = (motivo or "").strip()
    if not codigo or not motivo:
        return {"ok": False, "error": "Código y motivo son obligatorios."}
    try:
        cantidad = float(cantidad)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Cantidad inválida."}
    if cantidad <= 0:
        return {"ok": False, "error": "La cantidad debe ser mayor que 0."}
    columna = _ORIGEN_A_COLUMNA.get(origen)
    if not columna:
        return {"ok": False, "error": "Origen inválido (usa 'lineal' o 'almacen')."}

    from src.db import mermas as _db
    # `mermas.id_tienda` es INT; escritorio SIEMPRE graba un entero (0 = "sin tienda concreta", vía
    # `tienda_actual_id_int()` — mismo centinela en todo el proyecto). La API móvil no tiene ese
    # concepto de sesión y pasaría NULL — se coacciona aquí para que una merma registrada desde el
    # móvil aparezca en el listado mensual de escritorio (que sí filtra por ese 0 por defecto).
    id_tienda = id_tienda if id_tienda is not None else 0
    id_merma = _db.registrar_merma(codigo, cantidad, motivo, columna_stock=columna,
                                   id_empresa=id_empresa, id_tienda=id_tienda)
    if not id_merma:
        return {"ok": False, "error": "No se pudo registrar la merma."}
    return {"ok": True, "id": id_merma}


def listar(id_empresa, id_tienda=None, limite=50) -> list[dict]:
    """Últimas mermas de la empresa/tienda, con el nombre del artículo resuelto (igual que
    `db.mermas.obtener_mermas_pendientes`, pero sin el filtro de "no exportada")."""
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    filtros, params = ["m.id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("m.id_tienda=%s")
        params.append(id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT m.id, m.codigo, COALESCE(a.nombre, m.codigo) AS nombre, m.cantidad, "
                "m.motivo, m.fecha, d.id_documento AS id_documento_foto "
                "FROM mermas m LEFT JOIN articulos a ON a.codigo = m.codigo "
                "LEFT JOIN documentos_registro d ON d.referencia = CONCAT('MERMA:', m.id) "
                "AND d.id_empresa = m.id_empresa "
                "WHERE " + " AND ".join(filtros) + " ORDER BY m.fecha DESC LIMIT %s",
                (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []
