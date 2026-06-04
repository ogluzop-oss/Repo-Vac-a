import logging

logger = logging.getLogger("logistics_service")


def listar_documentos_por_estado(estados: tuple) -> list[dict]:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                ph = ",".join(["%s"] * len(estados))
                cur.execute(f"""
                    SELECT id_documento, tipo_documento, origen, destino,
                           estado, usuario_emisor, fecha_creacion, observaciones
                    FROM documentos_logisticos
                    WHERE estado IN ({ph})
                    ORDER BY fecha_creacion DESC
                """, estados)
                return [
                    {
                        "id": r[0], "tipo": r[1], "origen": r[2], "destino": r[3],
                        "estado": r[4], "emisor": r[5], "fecha": r[6], "obs": r[7],
                    }
                    for r in cur.fetchall()
                ]
    except Exception as e:
        logger.error(f"listar_documentos_por_estado: {e}")
        return []


def listar_incidencias(estado: str | None = None) -> list[dict]:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                if estado and estado != "TODAS":
                    cur.execute("""
                        SELECT id, id_documento, id_pale, codigo_articulo,
                               tipo, descripcion, cantidad_afectada,
                               usuario, estado, fecha_creacion, fecha_cierre
                        FROM incidencias_logisticas
                        WHERE estado=%s ORDER BY fecha_creacion DESC
                    """, (estado,))
                else:
                    cur.execute("""
                        SELECT id, id_documento, id_pale, codigo_articulo,
                               tipo, descripcion, cantidad_afectada,
                               usuario, estado, fecha_creacion, fecha_cierre
                        FROM incidencias_logisticas
                        ORDER BY fecha_creacion DESC
                    """)
                return [
                    {
                        "id": r[0], "id_documento": r[1], "id_pale": r[2],
                        "codigo": r[3], "tipo": r[4], "descripcion": r[5],
                        "cantidad": r[6], "usuario": r[7], "estado": r[8],
                        "fecha_creacion": r[9], "fecha_cierre": r[10],
                    }
                    for r in cur.fetchall()
                ]
    except Exception as e:
        logger.error(f"listar_incidencias: {e}")
        return []


def registrar_incidencia(id_documento: str, tipo: str, descripcion: str,
                         usuario: str, id_pale: str = None,
                         codigo_articulo: str = None,
                         cantidad_afectada: int = 0) -> int | None:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO incidencias_logisticas
                        (id_documento, id_pale, codigo_articulo, tipo,
                         descripcion, cantidad_afectada, usuario, estado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ABIERTA')
                """, (id_documento, id_pale, codigo_articulo, tipo,
                      descripcion, cantidad_afectada, usuario))
                iid = cur.lastrowid
            conn.commit()
            return iid
    except Exception as e:
        logger.error(f"registrar_incidencia: {e}")
        return None


def cerrar_incidencia(inc_id: int) -> bool:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE incidencias_logisticas
                    SET estado='CERRADA', fecha_cierre=NOW()
                    WHERE id=%s
                """, (inc_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"cerrar_incidencia: {e}")
        return False
