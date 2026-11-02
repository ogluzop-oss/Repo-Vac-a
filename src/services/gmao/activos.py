"""
GMAO-A — Activos (maquinaria/equipos/instalaciones/vehiculos/herramientas) con ficha completa,
documentos, garantias e historial. Multiempresa, auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("gmao.activos")
TIPOS = ("maquinaria", "equipo", "instalacion", "vehiculo", "herramienta")
ESTADOS = ("operativo", "averiado", "mantenimiento", "baja")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.gmao.identidad_gmao import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_activo(codigo, nombre, *, tipo="maquinaria", numero_serie=None, fabricante=None,
                 modelo=None, ubicacion=None, criticidad="media", fecha_alta=None, fecha_compra=None,
                 coste_adquisicion=0, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO activos (id_empresa, codigo, nombre, tipo, numero_serie, fabricante, "
                        "modelo, ubicacion, criticidad, fecha_alta, fecha_compra, coste_adquisicion) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "nombre=VALUES(nombre), tipo=VALUES(tipo), modelo=VALUES(modelo)",
                        (eid, codigo, nombre, tipo if tipo in TIPOS else "maquinaria", numero_serie,
                         fabricante, modelo, ubicacion, criticidad, fecha_alta, fecha_compra, coste_adquisicion))
            cur.execute("SELECT id FROM activos WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            aid = cur.fetchone()
            aid = aid[0] if not isinstance(aid, dict) else list(aid.values())[0]
            conn.commit()
        _historial(aid, "ALTA", f"Activo {codigo}", eid)
        log_auditoria("gmao", "ACTIVO_CREADO", "activos", f"activo={aid} {codigo}")
        return aid
    except Exception as e:
        logger.error("crear_activo: %s", e)
        return None


def cambiar_estado(id_activo, estado, *, id_empresa=None) -> bool:
    if estado not in ESTADOS:
        raise ValueError(f"estado invalido: {estado}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE activos SET estado=%s WHERE id=%s", (estado, id_activo))
            conn.commit()
        _historial(id_activo, "CAMBIO_ESTADO", estado, _emp(id_empresa))
        log_auditoria("gmao", "ACTIVO_ESTADO", "activos", f"activo={id_activo} {estado}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado activo: %s", e)
        return False


def adjuntar_documento(id_activo, nombre, *, ruta=None, id_documento=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO activos_documentos (id_empresa, id_activo, nombre, ruta, id_documento) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, id_activo, nombre, ruta, id_documento))
            did = cur.lastrowid
            conn.commit()
        return did
    except Exception as e:
        logger.error("adjuntar_documento: %s", e)
        return None


def registrar_garantia(id_activo, *, proveedor=None, fecha_inicio=None, fecha_fin=None,
                       cobertura=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO activos_garantias (id_empresa, id_activo, proveedor, fecha_inicio, "
                        "fecha_fin, cobertura) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eid, id_activo, proveedor, fecha_inicio, fecha_fin, cobertura))
            gid = cur.lastrowid
            conn.commit()
        return gid
    except Exception as e:
        logger.error("registrar_garantia: %s", e)
        return None


def listar_garantias(id_activo) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM activos_garantias WHERE id_activo=%s ORDER BY fecha_inicio DESC",
                        (id_activo,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_garantias: %s", e)
        return []


def listar_documentos(id_activo) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM activos_documentos WHERE id_activo=%s ORDER BY id DESC",
                        (id_activo,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_documentos: %s", e)
        return []


def historial(id_activo) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM activos_historial WHERE id_activo=%s ORDER BY fecha DESC", (id_activo,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("historial: %s", e)
        return []


def obtener(id_activo) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM activos WHERE id=%s", (id_activo,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener activo: %s", e)
        return None


def buscar_por_codigo(codigo, *, id_empresa=None) -> dict | None:
    """Localiza un activo por su `codigo` (lo que trae el QR impreso vía "Imprimir QR" en escritorio)
    — punto de entrada del flujo móvil de escaneo de activo."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM activos WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("buscar_por_codigo: %s", e)
        return None


def listar(*, tipo=None, estado=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM activos WHERE id_empresa=%s"
    p = [eid]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY codigo LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar activos: %s", e)
        return []


def gastos_activos_periodo(desde, hasta, id_empresa=None) -> list[dict]:
    """Altas de activos (maquinaria/vehículos) con coste de adquisición dentro de `[desde, hasta]`
    (ambos 'YYYY-MM-DD'), listas para plegarse en el Libro de Gastos / Informe Anual (categorías de
    inversión maquinaria/vehículos). Una fila por activo; SOLO lectura, sin efectos secundarios.
    Formato: {concepto, fecha, importe, tipo}."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, tipo, fecha_compra, coste_adquisicion FROM activos "
                "WHERE id_empresa=%s AND tipo IN ('maquinaria','vehiculo') "
                "AND fecha_compra IS NOT NULL AND fecha_compra BETWEEN %s AND %s "
                "AND coste_adquisicion IS NOT NULL AND coste_adquisicion > 0 "
                "ORDER BY fecha_compra", (eid, desde, hasta))
            filas = [_fila(cur, r) for r in cur.fetchall()]
        # `codigo` se incluye (campo adicional, no rompe a quien ya leía solo concepto/fecha/
        # importe/tipo) para que `contabilidad.estado_flujos` pueda cruzarlo con
        # `finanzas.inmovilizado_activos.codigo` y evitar contar dos veces la misma compra física
        # si el mismo activo se dio de alta en ambos registros (ver auditoría de doble cómputo).
        return [{"concepto": f"Alta activo ({r['tipo']}): {r['nombre']}", "codigo": r.get("codigo"),
                 "fecha": r["fecha_compra"], "importe": float(r["coste_adquisicion"]), "tipo": r["tipo"]}
                for r in filas]
    except Exception as e:
        logger.error("gastos_activos_periodo: %s", e)
        return []


def _historial(id_activo, evento, detalle, eid, id_ot=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO activos_historial (id_empresa, id_activo, evento, detalle, id_ot) "
                        "VALUES (%s,%s,%s,%s,%s)", (eid, id_activo, evento, (detalle or "")[:255], id_ot))
            conn.commit()
    except Exception:
        pass
