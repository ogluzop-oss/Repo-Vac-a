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
)

logger = logging.getLogger("logistica_db")

SCHEMA_LOGISTICA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "database", "schema_logistica.sql"
)

ESTADOS_LOGISTICOS_ABIERTOS = ("PENDIENTE", "EN TRANSITO", "PARCIAL")


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

    with obtener_conexion() as conn:
        conn.begin()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documentos_logisticos (
                        id_documento, tipo_documento, origen, destino, estado,
                        usuario_emisor, agencia, observaciones, resumen, fecha_envio
                    ) VALUES (%s, 'TRASPASO', %s, %s, 'EN TRANSITO', %s, %s, %s, %s, %s)
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

            conn.commit()
            return {
                "id_documento": id_doc,
                "secuencial": secuencial,
                "origen_codigo": origen_codigo,
                "anio": anio,
                "total_lineas": total_lineas,
            }
        except Exception:
            conn.rollback()
            raise


# ============================================================
# BLOQUE CONSULTA DE HISTORIAL Y TRAZABILIDAD
# ============================================================

def obtener_historial_traspasos(estado_filtro="PENDIENTE", texto_filtro=""):
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
                        d.estado,
                        d.agencia,
                        COUNT(DISTINCT p.id_pale) AS bultos
                    FROM documentos_logisticos d
                    LEFT JOIN documentos_logisticos_pales p ON d.id_documento = p.id_documento
                    LEFT JOIN documentos_logisticos_lineas l ON d.id_documento = l.id_documento
                    WHERE d.tipo_documento = 'TRASPASO'
                """
                params = []

                if estado_filtro and estado_filtro != "TODOS":
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
                    GROUP BY d.id_documento, d.origen, d.destino, d.fecha_envio, d.estado, d.agencia
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
                    WHERE d.tipo_documento = 'TRASPASO'
                """
                params = []

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


def obtener_documento_logistico_completo(id_documento: str):
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id_documento, origen, destino, fecha_envio, fecha_recepcion,
                        estado, agencia, observaciones, usuario_emisor AS usuario,
                        usuario_receptor, resumen
                    FROM documentos_logisticos
                    WHERE id_documento = %s
                    """,
                    (id_documento,),
                )
                maestro = _row_to_dict(cur, cur.fetchone())
                if not maestro:
                    return None, []

                cur.execute(
                    """
                    SELECT
                        id_documento, id_pale, id_visual,
                        codigo_articulo AS codigo, nombre_articulo AS nombre,
                        cantidad_enviada AS cantidad, cantidad_recibida,
                        estado_linea, peso_bulto
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


def obtener_items_pale_traspaso(id_pale_buscado):
    ensure_schema_logistica()

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
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
                    ORDER BY l.nombre_articulo ASC
                    """,
                    (id_pale_buscado, *ESTADOS_LOGISTICOS_ABIERTOS),
                )
                return _rows_to_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error(f"Error al recuperar el contenido del palé {id_pale_buscado}: {e}")
        return []


# ============================================================
# BLOQUE RECEPCIÓN DE MERCANCÍA
# ============================================================

def procesar_recepcion_logistica(
    id_pale_escaneado: str,
    centro_receptor: str,
    usuario_receptor: str,
    items_a_recibir: list,
):
    ensure_schema_logistica()

    with obtener_conexion() as conn:
        conn.begin()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        d.id_documento, d.origen, d.destino, d.estado,
                        p.id_pale, p.id_visual, p.estado AS estado_pale
                    FROM documentos_logisticos_pales p
                    JOIN documentos_logisticos d ON d.id_documento = p.id_documento
                    WHERE p.id_pale = %s
                    ORDER BY d.fecha_envio DESC
                    LIMIT 1
                    """,
                    (id_pale_escaneado,),
                )
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

                    cur.execute("SELECT codigo FROM articulos WHERE codigo = %s", (codigo,))
                    if not cur.fetchone():
                        articulos_no_encontrados.append(
                            {"ean": codigo, "nombre": nombre, "cantidad": cantidad}
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
                        (cantidad, cantidad, doc["id_documento"], id_pale_escaneado, codigo),
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

                cur.execute(
                    """
                    INSERT INTO recepciones_logisticas (
                        id_documento, id_pale, centro_receptor, usuario_receptor,
                        total_lineas, total_unidades, incidencias
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        doc["id_documento"], id_pale_escaneado, centro_receptor,
                        usuario_receptor, total_lineas, total_unidades, incidencias,
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

            conn.commit()

            for codigo in codigos_actualizados:
                try:
                    stock_signals.stock_actualizado.emit(str(codigo))
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
            conn.rollback()
            raise
