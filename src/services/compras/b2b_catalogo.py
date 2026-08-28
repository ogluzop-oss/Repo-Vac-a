"""
Catálogo B2B del proveedor (Smart Suppliers · Fase A). Alta manual e import masivo (CSV/Excel) de
artículos ofertados, con Unidad de Medida Mayorista y Cantidad Mínima de Pedido (MOQ) OBLIGATORIAS
(requisito explícito: sin unidad no hay alta posible). El import masivo NO parsea el fichero aquí (eso
es responsabilidad de la vista/edge, ver `src/backend/portal_proveedor.py`) — recibe una lista de filas
ya parseadas y valida/audita cada una, para poder mostrarle al proveedor exactamente qué falló.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_catalogo")

UNIDADES_MAYORISTA = ("kg", "unidad", "pale", "caja")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _validar(codigo, nombre, unidad_medida, moq, precio_unitario) -> str | None:
    """Devuelve el motivo del error, o None si la fila es válida."""
    if not str(codigo or "").strip():
        return "codigo_obligatorio"
    if not str(nombre or "").strip():
        return "nombre_obligatorio"
    if unidad_medida not in UNIDADES_MAYORISTA:
        return f"unidad_medida_invalida (válidas: {', '.join(UNIDADES_MAYORISTA)})"
    try:
        if int(moq) < 1:
            return "moq_debe_ser_mayor_o_igual_a_1"
    except (TypeError, ValueError):
        return "moq_invalido"
    try:
        if float(precio_unitario) < 0:
            return "precio_no_puede_ser_negativo"
    except (TypeError, ValueError):
        return "precio_invalido"
    return None


def crear_articulo(id_suministrador, codigo: str, nombre: str, *, unidad_medida: str, moq: int = 1,
                   precio_unitario: float = 0, descripcion: str | None = None,
                   sector_id: int | None = None) -> dict:
    error = _validar(codigo, nombre, unidad_medida, moq, precio_unitario)
    if error:
        return {"ok": False, "error": error}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_catalogo (id_suministrador, codigo, nombre, descripcion, "
                "unidad_medida, moq, precio_unitario, sector_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), descripcion=VALUES(descripcion), "
                "unidad_medida=VALUES(unidad_medida), moq=VALUES(moq), "
                "precio_unitario=VALUES(precio_unitario), activo=1",
                (id_suministrador, codigo.strip(), nombre.strip(), descripcion, unidad_medida,
                 int(moq), float(precio_unitario), sector_id))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("crear_articulo(%s,%s): %s", id_suministrador, codigo, e)
        return {"ok": False, "error": "error_interno"}


def desactivar_articulo(id_suministrador, codigo: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_catalogo SET activo=0 WHERE id_suministrador=%s AND codigo=%s",
                        (id_suministrador, codigo))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("desactivar_articulo: %s", e)
        return False


def listar_por_suministrador(id_suministrador, *, solo_activos=True) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM b2b_catalogo WHERE id_suministrador=%s"
            p = [id_suministrador]
            if solo_activos:
                q += " AND activo=1"
            q += " ORDER BY nombre"
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_por_suministrador(%s): %s", id_suministrador, e)
        return []


def buscar_para_empresa(sector_ids: set, *, texto: str | None = None, limite: int = 200) -> list[dict]:
    """Catálogo visible para una empresa compradora: SOLO artículos activos de proveedores cuyo
    `sector_id` esté en `sector_ids` (el propio + los marcados compatibles, ver `sectores.compatibles_de`).
    Aislamiento estricto: sin sectores compatibles, no hay resultados (nunca se muestra "todo" por
    defecto)."""
    if not sector_ids:
        return []
    try:
        ensure_schema()
        placeholders = ",".join(["%s"] * len(sector_ids))
        q = (f"SELECT c.*, s.razon_social AS proveedor_nombre FROM b2b_catalogo c "
             f"JOIN suministradores s ON s.id = c.id_suministrador "
             f"WHERE c.activo=1 AND c.sector_id IN ({placeholders})")
        params = list(sector_ids)
        if texto:
            q += " AND (c.nombre LIKE %s OR c.codigo LIKE %s)"
            params += [f"%{texto}%", f"%{texto}%"]
        q += " ORDER BY c.actualizado_en DESC LIMIT %s"
        params.append(int(limite))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, params)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("buscar_para_empresa: %s", e)
        return []


def importar_lote(id_suministrador, filas: list[dict], *, archivo_nombre: str | None = None) -> dict:
    """Alta masiva. `filas` = [{codigo, nombre, unidad_medida, moq, precio_unitario, descripcion?}, ...]
    ya parseadas por la vista. Cada fila se valida de forma independiente (una fila inválida no aborta
    el resto) y el resultado se audita en `b2b_catalogo_import_lotes` para que el proveedor vea
    exactamente qué se importó y qué no."""
    ok, errores = 0, []
    for i, fila in enumerate(filas, start=1):
        r = crear_articulo(
            id_suministrador, fila.get("codigo"), fila.get("nombre"),
            unidad_medida=str(fila.get("unidad_medida") or "").strip().lower(),
            moq=fila.get("moq", 1), precio_unitario=fila.get("precio_unitario", 0),
            descripcion=fila.get("descripcion"))
        if r.get("ok"):
            ok += 1
        else:
            errores.append({"fila": i, "codigo": fila.get("codigo"), "error": r.get("error")})
    try:
        import json
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_catalogo_import_lotes (id_suministrador, archivo_nombre, filas_ok, "
                "filas_error, detalle_errores) VALUES (%s,%s,%s,%s,%s)",
                (id_suministrador, archivo_nombre, ok, len(errores),
                 json.dumps(errores, ensure_ascii=False) if errores else None))
            lote_id = cur.lastrowid
            conn.commit()
    except Exception as e:
        logger.error("importar_lote registro auditoría: %s", e)
        lote_id = None
    return {"ok": True, "lote_id": lote_id, "filas_ok": ok, "filas_error": len(errores), "errores": errores}
