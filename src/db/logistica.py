import json
import logging
import os
import re
from datetime import datetime

from src.db.conexion import (
    formatear_nombre_centro,
    obtener_conexion,
    stock_signals,
    tabla_existe,
    transaccion,
)

logger = logging.getLogger("logistica_db")

SCHEMA_LOGISTICA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "database", "schema_logistica.sql"
)

ESTADOS_LOGISTICOS_ABIERTOS = ("PENDIENTE", "EN TRANSITO", "PARCIAL")


def _tenant_actual():
    """(id_empresa, id_tienda) ACTIVOS para etiquetar documentos logísticos (3b.2)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return empresa_actual_id(), tienda_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID, None


# ============================================================
# BLOQUE UTILIDADES INTERNAS
# ============================================================

def _row_to_dict(cursor, row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    columnas = [desc[0] for desc in (cursor.description or [])]
    return dict(zip(columnas, row, strict=False))


def _rows_to_dicts(cursor, rows):
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return list(rows)
    columnas = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columnas, row, strict=False)) for row in rows]


def _normalizar_codigo_logistico(valor: str) -> str:
    base = formatear_nombre_centro(str(valor or "ALMC"))
    limpio = re.sub(r"[^A-Z0-9_-]", "", base.upper())
    return limpio or "ALMC"


def _normalizar_id_visual_pale(id_visual: str) -> str:
    base = str(id_visual or "PALE01").upper().strip()
    base = re.sub(r"\s+", "", base)
    return re.sub(r"[^A-Z0-9_-]", "", base) or "PALE01"


def _construir_id_pale(id_visual: str, secuencial: int, origen: str) -> str:
    return f"PAL-{_normalizar_id_visual_pale(id_visual)}-{int(secuencial):03d}-TRA-{_normalizar_codigo_logistico(origen)}"


# ============================================================
# BLOQUE ESQUEMA DE BASE DE DATOS LOGÍSTICA
# ============================================================

_logistica_ready = False


def ensure_schema_logistica():
    # No-op tras la primera verificación (evita una consulta tabla_existe en
    # CADA función de logística, que se llamaban en cascada al cargar pantallas).
    global _logistica_ready
    if _logistica_ready:
        return

    if tabla_existe("documentos_logisticos"):
        _logistica_ready = True
        return

    if not os.path.exists(SCHEMA_LOGISTICA_PATH):
        raise FileNotFoundError(f"No existe el esquema SQL: {SCHEMA_LOGISTICA_PATH}")

    with open(SCHEMA_LOGISTICA_PATH, encoding="utf-8") as f:
        contenido = f.read()

    with obtener_conexion() as conn:
        with conn.cursor() as cur:
            for sentencia in contenido.split(";"):
                sql = sentencia.strip()
                if sql:
                    cur.execute(sql)
        conn.commit()
    _logistica_ready = True


# ============================================================
# BLOQUE GENERACIÓN DE IDENTIFICADORES DE TRASPASO
# ============================================================

def generar_id_traspaso(origen: str, destino: str):
    """Genera IDs del tipo TRA-ALMC-001-2026."""
    ensure_schema_logistica()

    origen_codigo = _normalizar_codigo_logistico(origen)
    anio_actual = datetime.now().year
    secuencial = 1

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id_documento
                    FROM documentos_logisticos
                    WHERE id_documento LIKE %s
                    ORDER BY fecha_creacion DESC, id_documento DESC
                    LIMIT 1
                    """,
                    (f"TRA-{origen_codigo}-%-{anio_actual}",),
                )
                row = _row_to_dict(cur, cur.fetchone())
                if row and row.get("id_documento"):
                    partes = str(row["id_documento"]).split("-")
                    if len(partes) >= 4:
                        try:
                            secuencial = int(partes[-2]) + 1
                        except ValueError:
                            secuencial = 1
    except Exception as e:
        logger.error(f"Error generando nuevo ID de traspaso: {e}")

    id_documento = f"TRA-{origen_codigo}-{secuencial:03d}-{anio_actual}"
    return id_documento, secuencial, origen_codigo, anio_actual


# ============================================================
# BLOQUE REGISTRO DE TRASPASOS
# ============================================================

def guardar_traspaso_logistico(
    origen: str,
    destino: str,
    usuario: str,
    agencia: str,
    observaciones: str,
    pales: dict,
    id_documento: str | None = None,
    fecha_envio=None,
    *,
    id_empresa=None,
    id_tienda=None,
    id_centro_origen=None,
    id_centro_destino=None,
    id_almacen_origen=None,
):
    ensure_schema_logistica()

    if not pales:
        raise ValueError("No hay líneas ni palés para registrar el traspaso.")

    id_doc, secuencial, origen_codigo, anio = generar_id_traspaso(origen, destino)
    if id_documento:
        id_doc = str(id_documento)
        partes = id_doc.split("-")
        if len(partes) >= 4:
            try:
                secuencial = int(partes[-2])
            except ValueError:
                pass
            origen_codigo = partes[1]

    resumen = []
    total_lineas = 0

    with transaccion() as conn:        # A2.3: transacción unificada (commit/rollback automáticos)
        try:
            _emp, _tnd = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos (
                        id_documento, tipo_documento, origen, destino, estado,
                        usuario_emisor, agencia, observaciones, resumen, fecha_envio,
                        id_empresa, id_tienda, id_centro_origen, id_centro_destino, id_almacen_origen
                    ) VALUES (%s, 'TRASPASO', %s, %s, 'EN PREPARACION', %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s)
                    """,
                    (
                        id_doc,
                        str(origen).upper().strip(),
                        str(destino).upper().strip(),
                        str(usuario or "SISTEMA"),
                        str(agencia or "PROPIA"),
                        str(observaciones or ""),
                        "",
                        fecha_envio or datetime.now(),
                        _emp, _tnd, id_centro_origen, id_centro_destino, id_almacen_origen,
                    ),
                )

                for id_visual, data_pale in pales.items():
                    id_visual_norm = _normalizar_id_visual_pale(id_visual)
                    peso_bulto = data_pale.get("peso")
                    id_pale = _construir_id_pale(id_visual_norm, secuencial, origen_codigo)

                    cur.execute(
                        """
                        INSERT INTO documentos_logisticos_pales (
                            id_documento, id_pale, id_visual, peso_bulto, estado
                        ) VALUES (%s, %s, %s, %s, 'PENDIENTE')
                        """,
                        (id_doc, id_pale, id_visual_norm, peso_bulto),
                    )

                    for articulo in data_pale.get("articulos", []):
                        codigo = str(articulo.get("codigo") or "").strip().upper()
                        nombre = str(articulo.get("nombre") or codigo).strip()
                        cantidad = int(articulo.get("cantidad") or 0)

                        if not codigo or cantidad <= 0:
                            continue

                        resumen.append(f"{cantidad}x {nombre}")
                        total_lineas += 1

                        cur.execute(
                            """
                            INSERT INTO documentos_logisticos_lineas (
                                id_documento, id_pale, id_visual, codigo_articulo,
                                nombre_articulo, cantidad_enviada, cantidad_recibida,
                                estado_linea, peso_bulto
                            ) VALUES (%s, %s, %s, %s, %s, %s, 0, 'PENDIENTE', %s)
                            """,
                            (id_doc, id_pale, id_visual_norm, codigo, nombre, cantidad, peso_bulto),
                        )

                cur.execute(
                    "UPDATE documentos_logisticos SET resumen = %s WHERE id_documento = %s",
                    (", ".join(resumen)[:500], id_doc),
                )

            return {                       # commit gestionado por transaccion()
                "id_documento": id_doc,
                "secuencial": secuencial,
                "origen_codigo": origen_codigo,
                "anio": anio,
                "total_lineas": total_lineas,
            }
        except Exception:
            raise          # transaccion() hace rollback automático


# ============================================================
# BLOQUE CONSULTA DE HISTORIAL Y TRAZABILIDAD
# ============================================================

def obtener_historial_traspasos(estado_filtro="PENDIENTE", texto_filtro="", *,
                                id_empresa=None, id_tienda=None):
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        d.id_documento,
                        d.tipo_documento AS tipo,
                        d.origen,
                        d.destino,
                        d.fecha_creacion,
                        d.fecha_envio,
                        d.estado,
                        d.agencia,
                        d.usuario_emisor AS emisor,
                        COUNT(DISTINCT p.id_pale) AS bultos
                    FROM documentos_logisticos d
                    LEFT JOIN documentos_logisticos_pales p ON d.id_documento = p.id_documento
                    LEFT JOIN documentos_logisticos_lineas l ON d.id_documento = l.id_documento
                    WHERE d.tipo_documento IN ('TRASPASO', 'B2B')
                """
                params = []
                # Aislamiento por tenant (3b.2): solo traspasos de la tienda activa. Si se pasa
                # id_empresa explícito (REST, sin sesión de escritorio), se usa tal cual.
                # Unificación de recepciones: el Historial de "Traspasos" incluye TAMBIÉN los pedidos
                # B2B recibidos desde aquí (mismo motor logístico, `registrar_documento_b2b`) — ambos
                # son recepciones y se muestran juntos.
                _emp, _tnd = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                query += " AND d.id_empresa = %s"
                params.append(_emp)
                if _tnd is not None:
                    query += " AND d.id_tienda = %s"
                    params.append(_tnd)

                if estado_filtro == "ABIERTOS":
                    query += " AND d.estado IN (%s,%s,%s)"
                    params.extend(ESTADOS_LOGISTICOS_ABIERTOS)
                elif estado_filtro and estado_filtro != "TODOS":
                    query += " AND d.estado = %s"
                    params.append(estado_filtro)

                if texto_filtro:
                    txt = f"%{texto_filtro}%"
                    query += """
                        AND (
                            d.id_documento LIKE %s
                            OR d.origen LIKE %s
                            OR d.destino LIKE %s
                            OR COALESCE(l.codigo_articulo, '') LIKE %s
                            OR COALESCE(l.nombre_articulo, '') LIKE %s
                        )
                    """
                    params.extend([txt, txt, txt, txt, txt])

                query += """
                    GROUP BY d.id_documento, d.tipo_documento, d.origen, d.destino, d.fecha_creacion,
                             d.fecha_envio, d.estado, d.agencia, d.usuario_emisor
                    ORDER BY d.fecha_envio DESC
                """
                cur.execute(query, tuple(params))
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error en obtener_historial_traspasos: {e}")
        return []


def obtener_trazabilidad_logistica(
    origen: str | None = None,
    destino: str | None = None,
    busqueda: str = "",
) -> list[dict]:
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        d.id_documento,
                        d.origen,
                        d.destino,
                        d.fecha_envio,
                        d.fecha_recepcion,
                        d.estado,
                        COUNT(DISTINCT p.id_pale) AS bultos
                    FROM documentos_logisticos d
                    LEFT JOIN documentos_logisticos_pales p ON d.id_documento = p.id_documento
                    LEFT JOIN documentos_logisticos_lineas l ON d.id_documento = l.id_documento
                    WHERE d.tipo_documento IN ('TRASPASO', 'B2B')
                """
                params = []
                # Aislamiento por tenant (3b.2). Incluye también B2B (ver obtener_historial_traspasos).
                _emp, _tnd = _tenant_actual()
                query += " AND d.id_empresa = %s"
                params.append(_emp)
                if _tnd is not None:
                    query += " AND d.id_tienda = %s"
                    params.append(_tnd)

                if origen:
                    query += " AND (d.origen = %s OR d.origen LIKE %s)"
                    params.extend([origen, f"%{origen}%"])

                if destino:
                    query += " AND d.destino = %s"
                    params.append(destino)

                if busqueda:
                    txt = f"%{busqueda}%"
                    query += """
                        AND (
                            d.id_documento LIKE %s
                            OR d.origen LIKE %s
                            OR d.destino LIKE %s
                            OR d.estado LIKE %s
                            OR CAST(d.fecha_envio AS CHAR) LIKE %s
                            OR COALESCE(p.id_pale, '') LIKE %s
                            OR COALESCE(l.codigo_articulo, '') LIKE %s
                            OR COALESCE(l.nombre_articulo, '') LIKE %s
                        )
                    """
                    params.extend([txt, txt, txt, txt, txt, txt, txt, txt])

                query += """
                    GROUP BY d.id_documento, d.origen, d.destino, d.fecha_envio, d.fecha_recepcion, d.estado
                    ORDER BY d.fecha_envio DESC
                """
                cur.execute(query, tuple(params))
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error en obtener_trazabilidad_logistica: {e}")
        return []


def obtener_documento_logistico_completo(id_documento: str, *, id_empresa=None, id_tienda=None):
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        id_documento, origen, destino, fecha_envio, fecha_recepcion,
                        estado, agencia, observaciones, usuario_emisor AS usuario,
                        usuario_receptor, resumen
                    FROM documentos_logisticos
                    WHERE id_documento = %s
                """
                params = [id_documento]
                # Aislamiento por tenant: id_documento es predecible (TRA-{origen}-{seq}-{año}), no un
                # UUID — sin este filtro un id_empresa/id_tienda explícito (REST) podría leer
                # documentos de otro tenant probando IDs.
                if id_empresa is not None:
                    query += " AND id_empresa = %s"
                    params.append(id_empresa)
                    if id_tienda is not None:
                        query += " AND id_tienda = %s"
                        params.append(id_tienda)
                cur.execute(query, tuple(params))
                maestro = _row_to_dict(cur, cur.fetchone())
                if not maestro:
                    return None, []

                cur.execute(
                    """
                    SELECT
                        id AS id_linea, id_documento, id_pale, id_visual,
                        codigo_articulo AS codigo, nombre_articulo AS nombre,
                        cantidad_enviada AS cantidad, cantidad_recibida,
                        estado_linea, peso_bulto, picking_completo
                    FROM documentos_logisticos_lineas
                    WHERE id_documento = %s
                    ORDER BY id_visual ASC, nombre_articulo ASC
                    """,
                    (id_documento,),
                )
                detalles = _rows_to_dicts(cur, cur.fetchall())
                return maestro, detalles
    except Exception as e:
        logger.error(f"Error en obtener_documento_logistico_completo: {e}")
        return None, []


# ============================================================
# BLOQUE CONSULTA DE PALÉS
# ============================================================

def obtener_pales_por_documento_logistico(
    id_documento: str, busqueda: str = ""
) -> list[dict]:
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        p.id_pale, p.id_visual, d.origen, d.fecha_envio,
                        p.estado, p.peso_bulto
                    FROM documentos_logisticos_pales p
                    JOIN documentos_logisticos d ON d.id_documento = p.id_documento
                    WHERE p.id_documento = %s
                """
                params = [id_documento]

                if busqueda:
                    query += " AND (p.id_pale LIKE %s OR p.id_visual LIKE %s)"
                    params.extend([f"%{busqueda}%", f"%{busqueda}%"])

                query += " ORDER BY p.id_visual ASC"
                cur.execute(query, tuple(params))
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error en obtener_pales_por_documento_logistico: {e}")
        return []


def obtener_items_por_pale_logistico(id_pale: str, busqueda: str = "") -> list[dict]:
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        id_pale, id_visual,
                        codigo_articulo AS codigo, nombre_articulo AS nombre,
                        cantidad_enviada AS cantidad, cantidad_recibida,
                        estado_linea, peso_bulto
                    FROM documentos_logisticos_lineas
                    WHERE id_pale = %s
                """
                params = [id_pale]

                if busqueda:
                    txt = f"%{busqueda}%"
                    query += " AND (codigo_articulo LIKE %s OR nombre_articulo LIKE %s)"
                    params.extend([txt, txt])

                query += " ORDER BY nombre_articulo ASC"
                cur.execute(query, tuple(params))
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error en obtener_items_por_pale_logistico: {e}")
        return []


def obtener_items_pale_traspaso(id_pale_buscado, *, id_empresa=None, id_tienda=None):
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        l.codigo_articulo AS codigo,
                        l.nombre_articulo AS nombre,
                        l.cantidad_enviada AS cantidad,
                        d.origen,
                        d.id_documento,
                        p.id_visual,
                        p.id_pale
                    FROM documentos_logisticos_lineas l
                    JOIN documentos_logisticos d ON d.id_documento = l.id_documento
                    JOIN documentos_logisticos_pales p
                        ON p.id_documento = l.id_documento AND p.id_pale = l.id_pale
                    WHERE l.id_pale = %s
                      AND d.estado IN (%s, %s, %s)
                """
                params = [id_pale_buscado, *ESTADOS_LOGISTICOS_ABIERTOS]
                if id_empresa is not None:
                    query += " AND d.id_empresa = %s"
                    params.append(id_empresa)
                    if id_tienda is not None:
                        query += " AND d.id_tienda = %s"
                        params.append(id_tienda)
                query += " ORDER BY l.nombre_articulo ASC"
                cur.execute(query, tuple(params))
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error al recuperar el contenido del palé {id_pale_buscado}: {e}")
        return []


# ============================================================
# BLOQUE B2B — unificación de recepciones (Logística recibe TAMBIÉN los pedidos B2B)
# ============================================================
# Un pedido B2B tramitado (`services.compras.b2b_pedidos.tramitar`) genera su albarán
# (`services.compras.b2b_albaran.generar_albaran_pedido`) que, ADEMÁS del PDF de siempre, registra
# aquí un `documentos_logisticos` (tipo_documento='B2B') con UN ÚNICO palé sintético que envuelve
# todas las líneas del pedido — no hay concepto de "varios bultos" en un pedido B2B como sí lo hay en
# un traspaso con picking. Esto permite que el ESCANEO en `gui/recepcion_pale.py` (que localiza
# documentos por `documentos_logisticos_pales.id_pale`) encuentre el pedido B2B exactamente con el
# mismo mecanismo que ya usa para un traspaso interno — la única diferencia es el paso final de
# COMMIT: para 'B2B' la GUI delega en `b2b_pedidos.recibir_mercancia` (el motor de stock/lote oficial
# de Smart Suppliers, sin tocar), nunca en `procesar_recepcion_logistica` (que es el motor de stock
# de los traspasos internos) — así no hay dos motores de stock compitiendo por el mismo documento.


def registrar_documento_b2b(id_tx, *, origen, destino, usuario, lineas, id_empresa=None, id_tienda=None):
    """Crea (idempotente) el documento logístico 'B2B' de un pedido ya tramitado, con un único palé
    sintético (`id_visual='PEDIDO'`) cuyo `id_pale` es el propio `id_documento` (`B2B-{id_tx}`) — así
    el operario solo tiene que escanear/introducir ese identificador, ya impreso en el albarán PDF
    del pedido, sin necesidad de una etiqueta de palé aparte. Si el documento ya existe (regeneración
    del albarán, o llamada duplicada) no hace nada y devuelve el existente."""
    ensure_schema_logistica()
    id_doc = f"B2B-{id_tx}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_documento FROM documentos_logisticos WHERE id_documento=%s", (id_doc,))
            if cur.fetchone():
                return {"ok": True, "id_documento": id_doc, "ya_existia": True}

        if not lineas:
            return {"ok": False, "error": "pedido_sin_lineas"}

        with transaccion() as conn:
            with conn.cursor() as cur:
                resumen = []
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos (
                        id_documento, tipo_documento, id_tx, origen, destino, estado,
                        usuario_emisor, agencia, observaciones, resumen, fecha_envio,
                        id_empresa, id_tienda
                    ) VALUES (%s, 'B2B', %s, %s, %s, 'EN TRANSITO', %s, 'PROVEEDOR B2B', %s, %s, NOW(),
                              %s, %s)
                    """,
                    (id_doc, str(id_tx), str(origen or "PROVEEDOR")[:100], str(destino or "")[:100],
                     str(usuario or "SISTEMA"),
                     "Pedido B2B tramitado desde el Portal Empresa.", "", id_empresa, id_tienda),
                )
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos_pales (
                        id_documento, id_pale, id_visual, estado
                    ) VALUES (%s, %s, 'PEDIDO', 'PENDIENTE')
                    """,
                    (id_doc, id_doc),
                )
                for ln in lineas:
                    codigo = str(ln.get("codigo") or "").strip().upper()
                    nombre = str(ln.get("nombre") or codigo).strip()
                    cantidad = int(ln.get("cantidad") or 0)
                    if not codigo or cantidad <= 0:
                        continue
                    resumen.append(f"{cantidad}x {nombre}")
                    cur.execute(
                        """
                        INSERT INTO documentos_logisticos_lineas (
                            id_documento, id_pale, id_visual, codigo_articulo,
                            nombre_articulo, cantidad_enviada, cantidad_recibida, estado_linea
                        ) VALUES (%s, %s, 'PEDIDO', %s, %s, %s, 0, 'PENDIENTE')
                        """,
                        (id_doc, id_doc, codigo, nombre, cantidad),
                    )
                cur.execute(
                    "UPDATE documentos_logisticos SET resumen=%s WHERE id_documento=%s",
                    (", ".join(resumen)[:500], id_doc),
                )
            return {"ok": True, "id_documento": id_doc, "ya_existia": False}
    except Exception as e:
        logger.error(f"registrar_documento_b2b({id_tx}): {e}")
        return {"ok": False, "error": "error_interno"}


def registrar_documento_traspaso_pedido_online(id_pedido, *, origen, destino, usuario, lineas,
                                               id_empresa=None, id_tienda=None):
    """Crea (idempotente) el documento logístico 'TRASPASO' de un pedido online enrutado entre
    almacenes/tiendas (encargo a almacén / pedido entre tiendas), con un único palé sintético
    (`id_visual='PEDIDO'`, `id_pale=id_documento`) — mismo patrón que `registrar_documento_b2b`.

    Seguridad de stock (petición explícita): al "enviar" el pedido el almacén de ORIGEN ya se ha
    descontado en un solo sentido (ver `_descontar_stock_pedido`, vía `stock_almacen.decrementar_stock`
    — NUNCA `traspasar_stock`, que sumaría al destino de forma instantánea). El almacén/tienda de
    DESTINO solo incrementa su stock cuando reciba físicamente la mercancía, reutilizando TAL CUAL
    el motor de recepción de palés ya existente (`procesar_recepcion_logistica`) — se le entrega a
    este documento `tipo_documento='TRASPASO'` (no 'B2B') precisamente para que la recepción lo trate
    exactamente igual que un traspaso manual entre tiendas, sin ningún cambio en la GUI/motor de
    recepción. `id_tienda` debe ser la tienda DESTINO (la que debe ver el documento pendiente en su
    pantalla de Logística/Recepciones)."""
    ensure_schema_logistica()
    id_doc = f"PEDIDO-{id_pedido}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_documento FROM documentos_logisticos WHERE id_documento=%s", (id_doc,))
            if cur.fetchone():
                return {"ok": True, "id_documento": id_doc, "ya_existia": True}

        if not lineas:
            return {"ok": False, "error": "pedido_sin_lineas"}

        with transaccion() as conn:
            with conn.cursor() as cur:
                resumen = []
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos (
                        id_documento, tipo_documento, id_tx, origen, destino, estado,
                        usuario_emisor, agencia, observaciones, resumen, fecha_envio,
                        id_empresa, id_tienda
                    ) VALUES (%s, 'TRASPASO', %s, %s, %s, 'EN TRANSITO', %s, 'PEDIDO ONLINE', %s, %s, NOW(),
                              %s, %s)
                    """,
                    (id_doc, str(id_pedido), str(origen or "")[:100], str(destino or "")[:100],
                     str(usuario or "SISTEMA"),
                     "Traspaso generado automáticamente al enviar un pedido online.", "",
                     id_empresa, id_tienda),
                )
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos_pales (
                        id_documento, id_pale, id_visual, estado
                    ) VALUES (%s, %s, 'PEDIDO', 'PENDIENTE')
                    """,
                    (id_doc, id_doc),
                )
                for ln in lineas:
                    codigo = str(ln.get("codigo") or "").strip().upper()
                    nombre = str(ln.get("nombre") or codigo).strip()
                    cantidad = int(ln.get("cantidad") or 0)
                    if not codigo or cantidad <= 0:
                        continue
                    resumen.append(f"{cantidad}x {nombre}")
                    cur.execute(
                        """
                        INSERT INTO documentos_logisticos_lineas (
                            id_documento, id_pale, id_visual, codigo_articulo,
                            nombre_articulo, cantidad_enviada, cantidad_recibida, estado_linea
                        ) VALUES (%s, %s, 'PEDIDO', %s, %s, %s, 0, 'PENDIENTE')
                        """,
                        (id_doc, id_doc, codigo, nombre, cantidad),
                    )
                cur.execute(
                    "UPDATE documentos_logisticos SET resumen=%s WHERE id_documento=%s",
                    (", ".join(resumen)[:500], id_doc),
                )
            return {"ok": True, "id_documento": id_doc, "ya_existia": False}
    except Exception as e:
        logger.error(f"registrar_documento_traspaso_pedido_online({id_pedido}): {e}")
        return {"ok": False, "error": "error_interno"}


def registrar_documento_produccion(id_of, *, origen, destino, usuario, lineas,
                                   id_centro_origen=None, id_centro_destino=None,
                                   id_almacen_origen=None, id_empresa=None, id_tienda=None) -> dict:
    """Crea (idempotente) el documento logístico 'PRODUCCION' de una Orden de Fabricación ya
    finalizada con centro destino elegido (petición explícita, flujo Producción -> Logística
    automático: "al finalizar una OP, el sistema genera de forma automática el registro de entrada
    de mercancía disponible para expedición, evitando duplicidad"). Mismo patrón EXACTO que
    `registrar_documento_traspaso_pedido_online` (palé sintético `id_visual='OF'`, `id_pale=
    id_documento`) — ningún motor de documentos paralelo. `estado='PENDIENTE'` (no 'EN TRANSITO'):
    la mercancía recién fabricada está lista para expedir, pero solo pasa a tránsito real cuando
    `cross_docking_rutas.evaluar_cross_docking_automatico` la enlaza a una ruta, o al expedirse
    manualmente después."""
    ensure_schema_logistica()
    id_doc = f"OF-{id_of}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_documento FROM documentos_logisticos WHERE id_documento=%s", (id_doc,))
            if cur.fetchone():
                return {"ok": True, "id_documento": id_doc, "ya_existia": True}

        if not lineas:
            return {"ok": False, "error": "produccion_sin_lineas"}

        _emp, _tnd = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
        with transaccion() as conn:
            with conn.cursor() as cur:
                resumen = []
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos (
                        id_documento, tipo_documento, origen, destino, estado,
                        usuario_emisor, agencia, observaciones, resumen, fecha_envio,
                        id_empresa, id_tienda, id_centro_origen, id_centro_destino, id_almacen_origen
                    ) VALUES (%s, 'PRODUCCION', %s, %s, 'PENDIENTE', %s, 'PROPIA', %s, %s, NOW(),
                              %s, %s, %s, %s, %s)
                    """,
                    (id_doc, str(origen or "PRODUCCION")[:100], str(destino or "")[:100],
                     str(usuario or "SISTEMA"),
                     "Mercancía disponible para expedición generada automáticamente al registrar "
                     "producción de la OF.", "", _emp, _tnd, id_centro_origen, id_centro_destino,
                     id_almacen_origen),
                )
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos_pales (
                        id_documento, id_pale, id_visual, estado
                    ) VALUES (%s, %s, 'OF', 'PENDIENTE')
                    """,
                    (id_doc, id_doc),
                )
                for ln in lineas:
                    codigo = str(ln.get("codigo") or "").strip().upper()
                    nombre = str(ln.get("nombre") or codigo).strip()
                    cantidad = int(ln.get("cantidad") or 0)
                    if not codigo or cantidad <= 0:
                        continue
                    resumen.append(f"{cantidad}x {nombre}")
                    cur.execute(
                        """
                        INSERT INTO documentos_logisticos_lineas (
                            id_documento, id_pale, id_visual, codigo_articulo,
                            nombre_articulo, cantidad_enviada, cantidad_recibida, estado_linea
                        ) VALUES (%s, %s, 'OF', %s, %s, %s, 0, 'PENDIENTE')
                        """,
                        (id_doc, id_doc, codigo, nombre, cantidad),
                    )
                cur.execute(
                    "UPDATE documentos_logisticos SET resumen=%s WHERE id_documento=%s",
                    (", ".join(resumen)[:500], id_doc),
                )
            return {"ok": True, "id_documento": id_doc, "ya_existia": False}
    except Exception as e:
        logger.error(f"registrar_documento_produccion({id_of}): {e}")
        return {"ok": False, "error": "error_interno"}


def obtener_tipo_documento_por_pale(id_pale: str, *, id_empresa=None, id_tienda=None):
    """Resuelve, a partir de lo escaneado en Recepciones, si corresponde a un TRASPASO interno o a un
    pedido B2B (y en ese caso su `id_tx`) — mismo patrón de aislamiento opcional por tenant que
    `obtener_items_pale_traspaso`/`obtener_documento_logistico_completo` (sin filtro si no se pasa
    `id_empresa`, igual que el resto de lecturas que ya usa `recepcion_pale.py` desde escritorio)."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = """
                SELECT d.id_documento, d.tipo_documento, d.id_tx, d.origen, d.destino, d.estado,
                       p.id_pale, p.estado AS estado_pale
                FROM documentos_logisticos_pales p
                JOIN documentos_logisticos d ON d.id_documento = p.id_documento
                WHERE p.id_pale = %s
            """
            params = [id_pale]
            if id_empresa is not None:
                query += " AND d.id_empresa = %s"
                params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda = %s"
                    params.append(id_tienda)
            query += " ORDER BY d.fecha_envio DESC LIMIT 1"
            cur.execute(query, tuple(params))
            return _row_to_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error(f"obtener_tipo_documento_por_pale({id_pale}): {e}")
        return None


def marcar_documento_b2b_recibido(id_documento: str, usuario_receptor: str) -> bool:
    """Cierra, en el motor logístico, el documento 'B2B' cuyo stock/lote YA registró
    `b2b_pedidos.recibir_mercancia` — puramente de estado/trazabilidad (Historial, Trazabilidad):
    no toca stock ni kárdex (eso ya lo hizo el motor oficial de Smart Suppliers)."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE documentos_logisticos_lineas SET cantidad_recibida = cantidad_enviada, "
                "estado_linea = 'RECIBIDO' WHERE id_documento = %s", (id_documento,))
            cur.execute(
                "UPDATE documentos_logisticos_pales SET estado='RECIBIDO', fecha_recepcion=NOW(), "
                "usuario_receptor=%s WHERE id_documento = %s", (usuario_receptor, id_documento))
            cur.execute(
                "UPDATE documentos_logisticos SET estado='RECIBIDO', fecha_recepcion=NOW(), "
                "usuario_receptor=%s WHERE id_documento = %s", (usuario_receptor, id_documento))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"marcar_documento_b2b_recibido({id_documento}): {e}")
        return False


# ============================================================
# BLOQUE RECEPCIÓN DE MERCANCÍA
# ============================================================

def procesar_recepcion_logistica(
    id_pale_escaneado: str,
    centro_receptor: str,
    usuario_receptor: str,
    items_a_recibir: list,
    *,
    id_empresa=None,
    id_tienda=None,
):
    ensure_schema_logistica()

    with transaccion() as conn:        # A2.3: transacción unificada (commit/rollback automáticos)
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        d.id_documento, d.origen, d.destino, d.estado,
                        p.id_pale, p.id_visual, p.estado AS estado_pale
                    FROM documentos_logisticos_pales p
                    JOIN documentos_logisticos d ON d.id_documento = p.id_documento
                    WHERE p.id_pale = %s
                """
                params = [id_pale_escaneado]
                if id_empresa is not None:
                    query += " AND d.id_empresa = %s"
                    params.append(id_empresa)
                    if id_tienda is not None:
                        query += " AND d.id_tienda = %s"
                        params.append(id_tienda)
                query += " ORDER BY d.fecha_envio DESC LIMIT 1"
                cur.execute(query, tuple(params))
                doc = _row_to_dict(cur, cur.fetchone())
                if not doc:
                    raise ValueError(
                        f"El palé {id_pale_escaneado} no existe en la base logística."
                    )

                if str(doc.get("destino") or "").upper().strip() != str(
                    centro_receptor or ""
                ).upper().strip():
                    return {
                        "ok": False,
                        "motivo": "destino_incorrecto",
                        "destino": doc.get("destino"),
                        "documento": doc,
                    }

                if str(doc.get("estado_pale") or "").upper() == "RECIBIDO":
                    return {
                        "ok": False,
                        "motivo": "pale_ya_recibido",
                        "documento": doc,
                    }

                articulos_no_encontrados = []
                codigos_actualizados = []
                cantidades_recibidas = []
                total_unidades = 0
                total_lineas = 0
                codigos_ignorar = {
                    "LOGISTICA", "PALE", "PALÉ", "CARTON", "CARTÓN",
                    "PLASTICO", "PLÁSTICO", "VACIO", "VACÍO", "BULTO", "JAULA", "CAJA",
                }

                for item in items_a_recibir or []:
                    if isinstance(item, dict):
                        codigo = str(item.get("codigo") or "").strip().upper()
                        nombre = str(item.get("nombre") or codigo).strip()
                        cantidad = int(item.get("cantidad") or 0)
                    else:
                        codigo = str(item[0] or "").strip().upper()
                        nombre = str(item[1] or codigo).strip()
                        cantidad = int(item[2] or 0)

                    if not codigo or cantidad <= 0:
                        continue
                    if any(token in codigo for token in codigos_ignorar):
                        continue

                    total_lineas += 1
                    total_unidades += cantidad
                    codigo_linea = codigo   # valor ORIGINAL de la línea (ver comentario abajo)

                    cur.execute("SELECT codigo FROM articulos WHERE codigo = %s", (codigo,))
                    if not cur.fetchone():
                        # Resolución por equivalencia (petición explícita): el código escaneado
                        # puede ser la referencia ORIGINAL del proveedor, no el EAN interno — se
                        # intenta resolver vía `equivalencias_referencia_proveedor` ANTES de darlo
                        # por no encontrado (ver `db/equivalencias_proveedor.py`). `codigo_linea`
                        # (la referencia tal cual venía en la línea del documento) se conserva para
                        # el UPDATE de `documentos_logisticos_lineas` de más abajo — esa tabla
                        # siempre guarda la referencia ORIGINAL, nunca la resuelta — mientras que
                        # `codigo` pasa a ser el EAN interno para el resto de la recepción (stock).
                        codigo_resuelto = None
                        try:
                            from src.db import equivalencias_proveedor as _EQ
                            _emp_eq, _ = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                            codigo_resuelto = _EQ.resolver_por_referencia(codigo, id_empresa=_emp_eq)
                        except Exception as e:
                            logger.debug(f"resolver_por_referencia en recepción ({codigo}): {e}")
                        if codigo_resuelto:
                            codigo = codigo_resuelto
                        else:
                            articulos_no_encontrados.append(
                                {"ean": codigo, "nombre": nombre, "cantidad": cantidad,
                                 "referencia_no_registrada": True}
                            )
                            continue

                    cur.execute(
                        """
                        UPDATE articulos
                        SET Stock_total = COALESCE(Stock_total, 0) + %s,
                            Stock_tienda = COALESCE(Stock_tienda, 0) + %s
                        WHERE codigo = %s
                        """,
                        (cantidad, cantidad, codigo),
                    )
                    codigos_actualizados.append(codigo)
                    cantidades_recibidas.append((codigo, cantidad))

                    cur.execute(
                        """
                        INSERT INTO movimientos_stock (
                            codigo_articulo, tipo_movimiento, cantidad, id_documento,
                            id_pale, origen, destino, usuario, observaciones
                        ) VALUES (%s, 'ENTRADA_TRASPASO', %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            codigo, cantidad, doc["id_documento"], id_pale_escaneado,
                            doc["origen"], doc["destino"], usuario_receptor,
                            "Recepción logística desde Recepción/Traspasos",
                        ),
                    )

                    cur.execute(
                        """
                        UPDATE documentos_logisticos_lineas
                        SET cantidad_recibida = LEAST(
                                cantidad_enviada,
                                COALESCE(cantidad_recibida, 0) + %s
                            ),
                            estado_linea = CASE
                                WHEN COALESCE(cantidad_recibida, 0) + %s >= cantidad_enviada
                                    THEN 'RECIBIDO'
                                ELSE 'PARCIAL'
                            END
                        WHERE id_documento = %s AND id_pale = %s AND codigo_articulo = %s
                        """,
                        (cantidad, cantidad, doc["id_documento"], id_pale_escaneado, codigo_linea),
                    )

                cur.execute(
                    """
                    UPDATE documentos_logisticos_pales
                    SET estado = 'RECIBIDO', fecha_recepcion = NOW(), usuario_receptor = %s
                    WHERE id_documento = %s AND id_pale = %s
                    """,
                    (usuario_receptor, doc["id_documento"], id_pale_escaneado),
                )

                incidencias = (
                    json.dumps(articulos_no_encontrados, ensure_ascii=False)
                    if articulos_no_encontrados else None
                )

                _emp_r, _tnd_r = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                cur.execute(
                    """
                    INSERT INTO recepciones_logisticas (
                        id_documento, id_pale, centro_receptor, usuario_receptor,
                        total_lineas, total_unidades, incidencias, id_empresa, id_tienda
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        doc["id_documento"], id_pale_escaneado, centro_receptor,
                        usuario_receptor, total_lineas, total_unidades, incidencias,
                        _emp_r, _tnd_r,
                    ),
                )

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM documentos_logisticos_pales
                    WHERE id_documento = %s AND estado <> 'RECIBIDO'
                    """,
                    (doc["id_documento"],),
                )
                pendientes = cur.fetchone()[0]
                nuevo_estado = "RECIBIDO" if pendientes == 0 else "PARCIAL"

                if pendientes == 0:
                    cur.execute(
                        """
                        UPDATE documentos_logisticos
                        SET estado = %s, fecha_recepcion = NOW(), usuario_receptor = %s
                        WHERE id_documento = %s
                        """,
                        (nuevo_estado, usuario_receptor, doc["id_documento"]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE documentos_logisticos
                        SET estado = %s, usuario_receptor = %s
                        WHERE id_documento = %s
                        """,
                        (nuevo_estado, usuario_receptor, doc["id_documento"]),
                    )

            # commit gestionado por transaccion()
            for codigo in codigos_actualizados:
                try:
                    stock_signals.stock_actualizado.emit(str(codigo))
                except Exception:
                    pass

            # Write-through (best-effort, no bloqueante) a `stock_almacen` — la fuente de verdad
            # multi-almacén ("Mutaciones (fuente de verdad)", ver `db/stock_almacen.py`): esta
            # recepción solo mutaba las columnas caché legadas (`articulos.Stock_total/Stock_tienda`,
            # arriba); sin este paso, el almacén concreto de la tienda receptora nunca quedaba
            # reflejado en `stock_almacen` (usado por Disponibilidad/Reservas/ATP), aunque el
            # agregado global sí subiera. Degrada en silencio si no hay almacén resuelto para la
            # tienda receptora (p. ej. tienda sin almacén propio todavía).
            try:
                _emp_sa, _tnd_sa = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                if _tnd_sa is not None:
                    from src.db import stock_almacen as _SA_recep
                    id_almacen_receptor = _SA_recep.almacen_de_tienda(_tnd_sa, _emp_sa)
                    if id_almacen_receptor:
                        for codigo, cantidad in cantidades_recibidas:
                            _SA_recep.incrementar_stock(codigo, id_almacen_receptor, cantidad, _emp_sa)
            except Exception as e:
                logger.debug(f"Write-through stock_almacen en recepción ({id_pale_escaneado}): {e}")

            # INV.3: entrada de lote (best-effort) solo si la línea aporta 'lote'.
            try:
                from src.db import lotes
                _emp_l, _tnd_l = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                for item in items_a_recibir or []:
                    if not isinstance(item, dict):
                        continue
                    lote = (item.get("lote") or "").strip()
                    cod = str(item.get("codigo") or "").strip().upper()
                    qty = int(item.get("cantidad") or 0)
                    if lote and cod and qty > 0:
                        lotes.registrar_entrada(
                            cod, lote, qty, fecha_caducidad=item.get("caducidad") or item.get("fecha_caducidad"),
                            id_empresa=_emp_l, id_tienda=_tnd_l, origen="recepcion",
                            id_documento=doc.get("id_documento"), usuario=usuario_receptor)
            except Exception:
                pass

            doc["estado"] = nuevo_estado
            return {
                "ok": True,
                "documento": doc,
                "count_actualizados": len(codigos_actualizados),
                "articulos_no_encontrados": articulos_no_encontrados,
            }
        except Exception:
            raise          # transaccion() hace rollback automático


# ============================================================
# BLOQUE BULTOS — recepción de un palé desglosada caja a caja
# ============================================================
# Hasta esta fase un palé solo podía recepcionarse ENTERO de una vez (bloque anterior). Se añade la
# vía alternativa: el operario, tras escanear el palé y optar por "revisar los bultos", declara
# cuántos bultos lo componen (`generar_bultos_para_pale`, reparto proporcional de cada artículo,
# editable al confirmar cada bulto) y recepciona cada uno por separado (`confirmar_recepcion_bulto`)
# escaneando su etiqueta — generada e impresa en ese momento (`services.logistics.bulto_label_service`).
# Reutiliza el MISMO motor de stock que `procesar_recepcion_logistica` (UPDATE articulos.Stock_total/
# Stock_tienda + INSERT movimientos_stock), nunca un segundo motor paralelo. Solo aplica a TRASPASO
# interno — un pedido B2B es, por diseño, un único palé sintético sin concepto de bultos (ver
# docstring de `registrar_documento_b2b`), así que la GUI nunca debe ofrecer "revisar bultos" para
# `tipo_documento == 'B2B'`.

def _extraer_codigo_plano(codigo: str) -> str:
    """Admite tanto un código plano (el contrato real de `remote_scan.py`, que devuelve la cadena
    escaneada tal cual) como, defensivamente, un QR con contenido JSON (algunas etiquetas PDF de este
    módulo —p. ej. el QR del albarán— codifican `{"documento": ...}` en vez de texto plano) — nunca
    lanza, degrada al texto original si no es JSON o no tiene ninguna clave reconocida."""
    texto = str(codigo or "").strip()
    if texto.startswith("{"):
        try:
            data = json.loads(texto)
            for clave in ("documento", "doc", "pale", "bulto"):
                if data.get(clave):
                    return str(data[clave]).strip()
        except Exception:
            pass
    return texto


def resolver_codigo_escaneado(codigo: str, *, id_empresa=None, id_tienda=None) -> dict:
    """Clasifica un código escaneado en el landing de Recepción: DOCUMENTO (albarán completo) | PALE
    | BULTO | None (no reconocido). Primer paso del flujo obligatorio "albarán → palé → (bultos)"."""
    ensure_schema_logistica()
    plano = _extraer_codigo_plano(codigo)
    if not plano:
        return {"tipo": None, "codigo": plano}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = "SELECT id_documento, tipo_documento, origen, destino, estado FROM documentos_logisticos WHERE id_documento=%s"
            params = [plano]
            if id_empresa is not None:
                query += " AND id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND id_tienda=%s"; params.append(id_tienda)
            cur.execute(query, tuple(params))
            doc = _row_to_dict(cur, cur.fetchone())
            if doc:
                return {"tipo": "DOCUMENTO", "codigo": plano, "documento": doc}

            query = ("SELECT p.id_pale, p.id_visual, p.estado, d.id_documento, d.tipo_documento "
                     "FROM documentos_logisticos_pales p JOIN documentos_logisticos d "
                     "ON d.id_documento=p.id_documento WHERE p.id_pale=%s")
            params = [plano]
            if id_empresa is not None:
                query += " AND d.id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda=%s"; params.append(id_tienda)
            cur.execute(query, tuple(params))
            pale = _row_to_dict(cur, cur.fetchone())
            if pale:
                return {"tipo": "PALE", "codigo": plano, "pale": pale}

            query = ("SELECT b.id_bulto, b.id_visual, b.estado, b.id_pale, d.id_documento, d.tipo_documento "
                     "FROM documentos_logisticos_bultos b JOIN documentos_logisticos d "
                     "ON d.id_documento=b.id_documento WHERE b.id_bulto=%s")
            params = [plano]
            if id_empresa is not None:
                query += " AND d.id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda=%s"; params.append(id_tienda)
            cur.execute(query, tuple(params))
            bulto = _row_to_dict(cur, cur.fetchone())
            if bulto:
                return {"tipo": "BULTO", "codigo": plano, "bulto": bulto}
    except Exception as e:
        logger.error(f"resolver_codigo_escaneado({plano}): {e}")
    return {"tipo": None, "codigo": plano}


def obtener_documento_con_pales(id_documento: str, *, id_empresa=None, id_tienda=None) -> dict | None:
    """Carga la cabecera del albarán + todos sus palés (con nº de líneas y si ya está recibido) —
    pantalla intermedia obligatoria tras escanear el albarán, antes de elegir un palé."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = "SELECT * FROM documentos_logisticos WHERE id_documento=%s"
            params = [id_documento]
            if id_empresa is not None:
                query += " AND id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND id_tienda=%s"; params.append(id_tienda)
            cur.execute(query, tuple(params))
            doc = _row_to_dict(cur, cur.fetchone())
            if not doc:
                return None
            cur.execute(
                """
                SELECT p.id_pale, p.id_visual, p.estado, p.fecha_recepcion,
                       COUNT(l.id) AS num_lineas, COALESCE(SUM(l.cantidad_enviada), 0) AS total_unidades
                FROM documentos_logisticos_pales p
                LEFT JOIN documentos_logisticos_lineas l
                    ON l.id_documento = p.id_documento AND l.id_pale = p.id_pale
                WHERE p.id_documento = %s
                GROUP BY p.id_pale, p.id_visual, p.estado, p.fecha_recepcion
                ORDER BY p.id_visual ASC
                """,
                (id_documento,),
            )
            doc["pales"] = _rows_to_dicts(cur, cur.fetchall())
            return doc
    except Exception as e:
        logger.error(f"obtener_documento_con_pales({id_documento}): {e}")
        return None


def historial_bultos_pales(centro_receptor: str, *, id_empresa=None, id_tienda=None) -> list:
    """Nivel 1 del historial de "Bultos recibidos" (Logística → Historial): un palé por fila, solo
    los que tienen AL MENOS un bulto declarado (los recepcionados enteros de una vez no aparecen
    aquí — ya se ven en el historial de Recepciones de siempre)."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = """
                SELECT p.id_pale, p.id_visual, p.id_documento, d.origen, d.fecha_envio,
                       COUNT(b.id_bulto) AS num_bultos,
                       SUM(CASE WHEN b.estado='RECIBIDO' THEN 1 ELSE 0 END) AS num_recibidos
                FROM documentos_logisticos_bultos b
                JOIN documentos_logisticos_pales p ON p.id_pale = b.id_pale
                JOIN documentos_logisticos d ON d.id_documento = p.id_documento
                WHERE d.destino = %s
            """
            params = [centro_receptor]
            if id_empresa is not None:
                query += " AND d.id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda=%s"; params.append(id_tienda)
            query += " GROUP BY p.id_pale, p.id_visual, p.id_documento, d.origen, d.fecha_envio ORDER BY d.fecha_envio DESC"
            cur.execute(query, tuple(params))
            return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"historial_bultos_pales({centro_receptor}): {e}")
        return []


def obtener_bultos_pale(id_pale: str) -> list:
    """Bultos ya declarados para un palé (vacío si todavía no se ha elegido "revisar bultos")."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id_bulto, id_documento, id_pale, id_visual, estado, fecha_recepcion, "
                "usuario_receptor FROM documentos_logisticos_bultos WHERE id_pale=%s ORDER BY id_visual ASC",
                (id_pale,))
            return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"obtener_bultos_pale({id_pale}): {e}")
        return []


def obtener_items_bulto(id_bulto: str) -> list:
    """Contenido ESPERADO de un bulto (lista de artículos+cantidad), editable por el operario antes
    de confirmar su recepción."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo_articulo AS codigo, nombre_articulo AS nombre, cantidad_enviada AS cantidad, "
                "cantidad_recibida, estado_linea FROM documentos_logisticos_bultos_lineas "
                "WHERE id_bulto=%s ORDER BY nombre_articulo ASC", (id_bulto,))
            return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"obtener_items_bulto({id_bulto}): {e}")
        return []


def generar_bultos_para_pale(id_pale: str, numero_bultos: int, *, id_empresa=None, id_tienda=None) -> dict:
    """Declara cuántos bultos componen un palé y reparte PROPORCIONALMENTE la cantidad esperada de
    cada artículo entre ellos (reparto entero exacto: resto repartido en los primeros bultos, nunca se
    pierde ni se inventa unidad alguna). Idempotente: si el palé YA tiene bultos declarados, los
    devuelve tal cual en vez de duplicar. La cantidad real de cada bulto es EDITABLE al confirmarlo
    (`confirmar_recepcion_bulto`), para absorber cualquier discrepancia que el reparto proporcional no
    adivine exactamente."""
    ensure_schema_logistica()
    numero_bultos = int(numero_bultos or 0)
    if numero_bultos < 1:
        return {"ok": False, "motivo": "El número de bultos debe ser al menos 1."}
    try:
        existentes = obtener_bultos_pale(id_pale)
        if existentes:
            return {"ok": True, "bultos": existentes, "ya_existian": True}

        with obtener_conexion() as conn, conn.cursor() as cur:
            query = ("SELECT p.id_documento, p.id_visual, d.tipo_documento FROM documentos_logisticos_pales p "
                     "JOIN documentos_logisticos d ON d.id_documento=p.id_documento WHERE p.id_pale=%s")
            params = [id_pale]
            if id_empresa is not None:
                query += " AND d.id_empresa=%s"; params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda=%s"; params.append(id_tienda)
            cur.execute(query, tuple(params))
            pale = _row_to_dict(cur, cur.fetchone())
            if not pale:
                return {"ok": False, "motivo": "El palé no existe."}
            if str(pale.get("tipo_documento") or "").upper() == "B2B":
                return {"ok": False, "motivo": "Un pedido B2B no admite desglose por bultos."}

            cur.execute(
                "SELECT codigo_articulo, nombre_articulo, cantidad_enviada FROM documentos_logisticos_lineas "
                "WHERE id_pale=%s", (id_pale,))
            lineas = _rows_to_dicts(cur, cur.fetchall())
            if not lineas:
                return {"ok": False, "motivo": "El palé no tiene artículos registrados."}

            bultos_ids = [f"BUL-{id_pale}-{i+1:02d}" for i in range(numero_bultos)]
            for i, id_bulto in enumerate(bultos_ids):
                cur.execute(
                    "INSERT INTO documentos_logisticos_bultos (id_bulto, id_documento, id_pale, id_visual, estado) "
                    "VALUES (%s,%s,%s,%s,'PENDIENTE')",
                    (id_bulto, pale["id_documento"], id_pale, f"BULTO {i+1:02d}"))

            for linea in lineas:
                total = int(linea.get("cantidad_enviada") or 0)
                base, resto = divmod(total, numero_bultos)
                for i, id_bulto in enumerate(bultos_ids):
                    cantidad_i = base + (1 if i < resto else 0)
                    if cantidad_i <= 0:
                        continue
                    cur.execute(
                        "INSERT INTO documentos_logisticos_bultos_lineas "
                        "(id_bulto, codigo_articulo, nombre_articulo, cantidad_enviada) VALUES (%s,%s,%s,%s)",
                        (id_bulto, linea["codigo_articulo"], linea["nombre_articulo"], cantidad_i))
            conn.commit()
        return {"ok": True, "bultos": obtener_bultos_pale(id_pale), "ya_existian": False}
    except Exception as e:
        logger.error(f"generar_bultos_para_pale({id_pale}): {e}")
        return {"ok": False, "motivo": "No se pudieron generar los bultos."}


def confirmar_recepcion_bulto(id_bulto: str, centro_receptor: str, usuario_receptor: str,
                              lineas_recibidas: list, *, id_empresa=None, id_tienda=None) -> dict:
    """Recepciona UN bulto: actualiza stock/kárdex (mismo motor que `procesar_recepcion_logistica`),
    acumula la cantidad sobre la línea del palé padre y, si era el último bulto pendiente, finaliza el
    palé entero (y recalcula el estado del documento) exactamente igual que una recepción completa."""
    ensure_schema_logistica()
    with transaccion() as conn:
        try:
            with conn.cursor() as cur:
                query = ("SELECT b.id_pale, b.id_documento, b.estado AS estado_bulto, "
                        "d.origen, d.destino, d.estado AS estado_doc "
                        "FROM documentos_logisticos_bultos b JOIN documentos_logisticos d "
                        "ON d.id_documento=b.id_documento WHERE b.id_bulto=%s")
                params = [id_bulto]
                if id_empresa is not None:
                    query += " AND d.id_empresa=%s"; params.append(id_empresa)
                    if id_tienda is not None:
                        query += " AND d.id_tienda=%s"; params.append(id_tienda)
                cur.execute(query, tuple(params))
                bulto = _row_to_dict(cur, cur.fetchone())
                if not bulto:
                    return {"ok": False, "motivo": "El bulto no existe."}
                if str(bulto.get("destino") or "").upper().strip() != str(centro_receptor or "").upper().strip():
                    return {"ok": False, "motivo": "destino_incorrecto", "destino": bulto.get("destino")}
                if str(bulto.get("estado_bulto") or "").upper() == "RECIBIDO":
                    return {"ok": False, "motivo": "bulto_ya_recibido"}

                id_pale = bulto["id_pale"]
                id_documento = bulto["id_documento"]
                codigos_actualizados = []
                cantidades_recibidas = []
                no_encontrados = []

                for item in lineas_recibidas or []:
                    codigo = str((item.get("codigo") if isinstance(item, dict) else item[0]) or "").strip().upper()
                    cantidad = int((item.get("cantidad") if isinstance(item, dict) else item[1]) or 0)
                    if not codigo:
                        continue

                    cur.execute(
                        "UPDATE documentos_logisticos_bultos_lineas SET cantidad_recibida=%s, "
                        "estado_linea=CASE WHEN %s >= cantidad_enviada THEN 'RECIBIDO' ELSE 'PARCIAL' END "
                        "WHERE id_bulto=%s AND codigo_articulo=%s", (cantidad, cantidad, id_bulto, codigo))

                    if cantidad <= 0:
                        continue

                    codigo_linea = codigo   # referencia ORIGINAL de la línea (ver pallet-level)
                    cur.execute("SELECT codigo FROM articulos WHERE codigo=%s", (codigo,))
                    if not cur.fetchone():
                        # Misma resolución por equivalencia que en `procesar_recepcion_logistica`
                        # (petición explícita) — antes esto se omitía en silencio (asimetría
                        # detectada en la auditoría previa): ahora, si tampoco resuelve por
                        # equivalencia, se recoge en `no_encontrados` en vez de desaparecer sin aviso.
                        codigo_resuelto = None
                        try:
                            from src.db import equivalencias_proveedor as _EQ
                            _emp_eq, _ = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                            codigo_resuelto = _EQ.resolver_por_referencia(codigo, id_empresa=_emp_eq)
                        except Exception as e:
                            logger.debug(f"resolver_por_referencia en recepción de bulto ({codigo}): {e}")
                        if codigo_resuelto:
                            codigo = codigo_resuelto
                        else:
                            no_encontrados.append({"ean": codigo, "cantidad": cantidad,
                                                   "referencia_no_registrada": True})
                            continue

                    cur.execute(
                        "UPDATE articulos SET Stock_total=COALESCE(Stock_total,0)+%s, "
                        "Stock_tienda=COALESCE(Stock_tienda,0)+%s WHERE codigo=%s",
                        (cantidad, cantidad, codigo))
                    codigos_actualizados.append(codigo)
                    cantidades_recibidas.append((codigo, cantidad))

                    cur.execute(
                        "INSERT INTO movimientos_stock (codigo_articulo, tipo_movimiento, cantidad, "
                        "id_documento, id_pale, origen, destino, usuario, observaciones) "
                        "VALUES (%s,'ENTRADA_TRASPASO',%s,%s,%s,%s,%s,%s,%s)",
                        (codigo, cantidad, id_documento, id_pale, bulto.get("origen"), bulto.get("destino"),
                         usuario_receptor, f"Recepción logística por bulto ({id_bulto})"))

                    # OJO: NUNCA referenciar `cantidad_recibida` dos veces en el mismo SET (una vez
                    # para la propia columna y otra dentro del CASE de `estado_linea`) — MariaDB
                    # evalúa las asignaciones de un UPDATE en orden y la segunda referencia ya ve el
                    # valor NUEVO recién asignado, no el antiguo, duplicando el incremento y marcando
                    # RECIBIDO antes de tiempo (bug real detectado al acumular varios bultos sobre la
                    # misma línea). Se lee el valor previo aparte y se escribe ya calculado.
                    cur.execute(
                        "SELECT cantidad_enviada, cantidad_recibida FROM documentos_logisticos_lineas "
                        "WHERE id_documento=%s AND id_pale=%s AND codigo_articulo=%s FOR UPDATE",
                        (id_documento, id_pale, codigo_linea))
                    fila_linea = cur.fetchone()
                    enviada_linea = int(fila_linea[0] or 0) if fila_linea else cantidad
                    recibida_previa = int(fila_linea[1] or 0) if fila_linea else 0
                    recibida_nueva = min(enviada_linea, recibida_previa + cantidad)
                    estado_linea_nuevo = "RECIBIDO" if recibida_previa + cantidad >= enviada_linea else "PARCIAL"
                    cur.execute(
                        "UPDATE documentos_logisticos_lineas SET cantidad_recibida=%s, estado_linea=%s "
                        "WHERE id_documento=%s AND id_pale=%s AND codigo_articulo=%s",
                        (recibida_nueva, estado_linea_nuevo, id_documento, id_pale, codigo_linea))

                cur.execute(
                    "UPDATE documentos_logisticos_bultos SET estado='RECIBIDO', fecha_recepcion=NOW(), "
                    "usuario_receptor=%s WHERE id_bulto=%s", (usuario_receptor, id_bulto))

                cur.execute(
                    "SELECT COUNT(*) FROM documentos_logisticos_bultos WHERE id_pale=%s AND estado<>'RECIBIDO'",
                    (id_pale,))
                bultos_pendientes = cur.fetchone()[0]
                pale_completo = bultos_pendientes == 0

                if pale_completo:
                    cur.execute(
                        "UPDATE documentos_logisticos_pales SET estado='RECIBIDO', fecha_recepcion=NOW(), "
                        "usuario_receptor=%s WHERE id_documento=%s AND id_pale=%s",
                        (usuario_receptor, id_documento, id_pale))

                    _emp_r, _tnd_r = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                    cur.execute(
                        "SELECT COUNT(*), COALESCE(SUM(cantidad_enviada),0) FROM documentos_logisticos_lineas "
                        "WHERE id_documento=%s AND id_pale=%s", (id_documento, id_pale))
                    total_lineas, total_unidades = cur.fetchone()
                    cur.execute(
                        "INSERT INTO recepciones_logisticas (id_documento, id_pale, centro_receptor, "
                        "usuario_receptor, total_lineas, total_unidades, incidencias, id_empresa, id_tienda) "
                        "VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s)",
                        (id_documento, id_pale, centro_receptor, usuario_receptor, total_lineas,
                         total_unidades, _emp_r, _tnd_r))

                    cur.execute(
                        "SELECT COUNT(*) FROM documentos_logisticos_pales WHERE id_documento=%s AND estado<>'RECIBIDO'",
                        (id_documento,))
                    pendientes_doc = cur.fetchone()[0]
                    nuevo_estado = "RECIBIDO" if pendientes_doc == 0 else "PARCIAL"
                    if pendientes_doc == 0:
                        cur.execute(
                            "UPDATE documentos_logisticos SET estado=%s, fecha_recepcion=NOW(), "
                            "usuario_receptor=%s WHERE id_documento=%s",
                            (nuevo_estado, usuario_receptor, id_documento))
                    else:
                        cur.execute(
                            "UPDATE documentos_logisticos SET estado=%s, usuario_receptor=%s WHERE id_documento=%s",
                            (nuevo_estado, usuario_receptor, id_documento))

            for codigo in codigos_actualizados:
                try:
                    stock_signals.stock_actualizado.emit(str(codigo))
                except Exception:
                    pass

            # Write-through a `stock_almacen` (mismo criterio que `procesar_recepcion_logistica`,
            # ver su comentario) — best-effort, no bloqueante.
            try:
                _emp_sa, _tnd_sa = (id_empresa, id_tienda) if id_empresa is not None else _tenant_actual()
                if _tnd_sa is not None:
                    from src.db import stock_almacen as _SA_recep
                    id_almacen_receptor = _SA_recep.almacen_de_tienda(_tnd_sa, _emp_sa)
                    if id_almacen_receptor:
                        for codigo, cantidad in cantidades_recibidas:
                            _SA_recep.incrementar_stock(codigo, id_almacen_receptor, cantidad, _emp_sa)
            except Exception as e:
                logger.debug(f"Write-through stock_almacen en recepción de bulto ({id_bulto}): {e}")

            return {"ok": True, "pale_completo": pale_completo,
                    "count_actualizados": len(codigos_actualizados),
                    "articulos_no_encontrados": no_encontrados}
        except Exception:
            raise          # transaccion() hace rollback automático


# ============================================================
# BLOQUE PICKING DE TRASPASOS (Ajuste post-lanzamiento · Módulo 8)
# ============================================================

def marcar_linea_picking(id_documento, id_linea, pickeado, *, id_empresa=None, id_tienda=None) -> bool:
    """Marca/desmarca UNA línea de un traspaso como recogida (picking). Granularidad por línea/palé."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = "UPDATE documentos_logisticos_lineas l " \
                    "JOIN documentos_logisticos d ON d.id_documento = l.id_documento " \
                    "SET l.picking_completo = %s " \
                    "WHERE l.id = %s AND l.id_documento = %s"
            params = [1 if pickeado else 0, id_linea, id_documento]
            if id_empresa is not None:
                query += " AND d.id_empresa = %s"
                params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND d.id_tienda = %s"
                    params.append(id_tienda)
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"marcar_linea_picking: {e}")
        return False


def confirmar_picking_y_expedir(id_documento, usuario, *, id_empresa=None, id_tienda=None) -> dict:
    """Si TODAS las líneas del documento tienen picking_completo=1, expide el traspaso
    (EN PREPARACION -> EN TRANSITO). Si falta alguna, no expide y devuelve cuántas faltan."""
    ensure_schema_logistica()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = "SELECT id_documento, estado FROM documentos_logisticos WHERE id_documento = %s"
            params = [id_documento]
            if id_empresa is not None:
                query += " AND id_empresa = %s"
                params.append(id_empresa)
                if id_tienda is not None:
                    query += " AND id_tienda = %s"
                    params.append(id_tienda)
            cur.execute(query, tuple(params))
            doc = _row_to_dict(cur, cur.fetchone())
            if not doc:
                return {"ok": False, "motivo": "no_encontrado"}

            cur.execute(
                "SELECT COUNT(*) FROM documentos_logisticos_lineas "
                "WHERE id_documento = %s AND picking_completo = 0",
                (id_documento,),
            )
            faltan = cur.fetchone()[0]
            if faltan > 0:
                return {"ok": False, "motivo": "picking_incompleto", "faltan": faltan}

            cur.execute(
                "UPDATE documentos_logisticos SET estado = 'EN TRANSITO', fecha_envio = NOW() "
                "WHERE id_documento = %s",
                (id_documento,),
            )
            conn.commit()
            return {"ok": True, "id_documento": id_documento, "estado": "EN TRANSITO"}
    except Exception as e:
        logger.error(f"confirmar_picking_y_expedir: {e}")
        return {"ok": False, "motivo": "error"}


# ============================================================
# BLOQUE INCIDENCIAS LOGÍSTICAS (trasladado desde gui/recepcion_pale.py, ya tenant-safe)
# ============================================================

def listar_incidencias(estado_filtro=None, texto_filtro="", *, id_empresa=None) -> list:
    """`incidencias_logisticas` no tiene columna `id_tienda` — solo se filtra por `id_empresa`.
    Sin `id_empresa` explícito (escritorio), cae en `_tenant_actual()` (mismo patrón del resto del
    fichero) — nunca lista sin aislar por tenant."""
    ensure_schema_logistica()
    emp = id_empresa if id_empresa is not None else _tenant_actual()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = (
                "SELECT id, id_documento, id_pale, codigo_articulo, tipo, "
                "descripcion, cantidad_afectada, usuario, estado, "
                "fecha_creacion, fecha_cierre FROM incidencias_logisticas WHERE 1=1"
            )
            params = []
            if emp is not None:
                query += " AND id_empresa = %s"
                params.append(emp)
            if estado_filtro and estado_filtro != "TODAS":
                query += " AND estado = %s"
                params.append(estado_filtro)
            if texto_filtro:
                txt = f"%{texto_filtro}%"
                query += (" AND (id_documento LIKE %s OR codigo_articulo LIKE %s "
                          "OR descripcion LIKE %s OR tipo LIKE %s)")
                params.extend([txt, txt, txt, txt])
            query += " ORDER BY fecha_creacion DESC"
            cur.execute(query, tuple(params))
            filas = cur.fetchall()
            return [
                {"id": r[0], "id_documento": r[1], "id_pale": r[2],
                 "codigo": r[3], "tipo": r[4], "descripcion": r[5],
                 "cantidad": r[6], "usuario": r[7], "estado": r[8],
                 "fecha_creacion": r[9], "fecha_cierre": r[10]}
                for r in filas
            ]
    except Exception as e:
        logger.error(f"listar_incidencias: {e}")
        return []


def _listar_incidencias_por_direccion(
    columna_direccion: str, codigo_local, estado_filtro=None, texto_filtro="", *, id_empresa=None
) -> list:
    """Helper interno compartido por `listar_incidencias_recepcion`/`listar_incidencias_traspaso`:
    misma consulta que `listar_incidencias`, pero unida a `documentos_logisticos` y filtrada por
    `origen`/`destino` = `codigo_local` — el mismo criterio ya usado por
    `HistorialTraspasosPage`/`HistorialRecepcionesPage` (gui/recepcion_pale.py) para separar
    documentos salientes (origen) de entrantes (destino) de este centro. Mismo shape de retorno
    que `listar_incidencias` para no tocar el renderizado de tabla existente."""
    ensure_schema_logistica()
    emp = id_empresa if id_empresa is not None else _tenant_actual()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = (
                "SELECT i.id, i.id_documento, i.id_pale, i.codigo_articulo, i.tipo, "
                "i.descripcion, i.cantidad_afectada, i.usuario, i.estado, "
                "i.fecha_creacion, i.fecha_cierre "
                "FROM incidencias_logisticas i "
                "INNER JOIN documentos_logisticos d ON d.id_documento = i.id_documento "
                f"WHERE d.{columna_direccion} = %s"
            )
            params = [codigo_local]
            if emp is not None:
                query += " AND i.id_empresa = %s"
                params.append(emp)
            if estado_filtro and estado_filtro != "TODAS":
                query += " AND i.estado = %s"
                params.append(estado_filtro)
            if texto_filtro:
                txt = f"%{texto_filtro}%"
                query += (" AND (i.id_documento LIKE %s OR i.codigo_articulo LIKE %s "
                          "OR i.descripcion LIKE %s OR i.tipo LIKE %s)")
                params.extend([txt, txt, txt, txt])
            query += " ORDER BY i.fecha_creacion DESC"
            cur.execute(query, tuple(params))
            filas = cur.fetchall()
            return [
                {"id": r[0], "id_documento": r[1], "id_pale": r[2],
                 "codigo": r[3], "tipo": r[4], "descripcion": r[5],
                 "cantidad": r[6], "usuario": r[7], "estado": r[8],
                 "fecha_creacion": r[9], "fecha_cierre": r[10]}
                for r in filas
            ]
    except Exception as e:
        logger.error(f"_listar_incidencias_por_direccion({columna_direccion}): {e}")
        return []


def listar_incidencias_recepcion(codigo_local, estado_filtro=None, texto_filtro="", *, id_empresa=None) -> list:
    """Incidencias de documentos ADDRESSED TO `codigo_local` (lado Recepción, entrante) —
    `documentos_logisticos.destino = codigo_local`, mismo criterio que
    `HistorialRecepcionesPage.cargar_datos()`."""
    return _listar_incidencias_por_direccion(
        "destino", codigo_local, estado_filtro, texto_filtro, id_empresa=id_empresa
    )


def listar_incidencias_traspaso(codigo_local, estado_filtro=None, texto_filtro="", *, id_empresa=None) -> list:
    """Incidencias de documentos ENVIADOS por `codigo_local` (lado Traspaso, saliente) —
    `documentos_logisticos.origen = codigo_local`, mismo criterio que
    `HistorialTraspasosPage.cargar_datos()`."""
    return _listar_incidencias_por_direccion(
        "origen", codigo_local, estado_filtro, texto_filtro, id_empresa=id_empresa
    )


def registrar_incidencia(id_documento, tipo, descripcion, usuario, id_pale=None, codigo=None,
                         cantidad=0, *, id_empresa=None):
    ensure_schema_logistica()
    try:
        emp = id_empresa if id_empresa is not None else _tenant_actual()[0]
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidencias_logisticas "
                "(id_documento, id_pale, codigo_articulo, tipo, descripcion, cantidad_afectada, "
                "usuario, estado, id_empresa) VALUES (%s, %s, %s, %s, %s, %s, %s, 'ABIERTA', %s)",
                (id_documento, id_pale, codigo, tipo, descripcion, cantidad, usuario, emp),
            )
            iid = cur.lastrowid
            conn.commit()
            return iid
    except Exception as e:
        logger.error(f"registrar_incidencia: {e}")
        return None


def cerrar_incidencia(id_incidencia, *, id_empresa=None) -> bool:
    ensure_schema_logistica()
    emp = id_empresa if id_empresa is not None else _tenant_actual()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = "UPDATE incidencias_logisticas SET estado='CERRADA', fecha_cierre=NOW() WHERE id=%s"
            params = [id_incidencia]
            if emp is not None:
                query += " AND id_empresa=%s"
                params.append(emp)
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"cerrar_incidencia: {e}")
        return False
