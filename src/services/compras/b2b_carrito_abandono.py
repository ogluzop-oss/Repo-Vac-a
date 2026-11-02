"""
Detección de carritos B2B abandonados (Smart Suppliers · cierre de brecha de automatización).

No existía ningún concepto de "abandono" hasta ahora (auditado: sin coincidencias para "abandon" en
todo el repo). `b2b_carrito_lineas.creado_en` (migr. 0222) se fija SOLO al insertar — `anadir()`
siempre inserta una fila nueva, `quitar_linea()` solo borra, nunca actualiza nada — así que
`MAX(creado_en)` por sí solo sería una señal honesta pero IMPRECISA: no reflejaría que el usuario quitó
una línea hace 5 minutos aunque las que quedan se añadieran hace 3 horas. Para una señal más fiable se
añadió `b2b_carrito_actividad` (migr. 0280, token_sesion -> actualizado_en), tocada por
`b2b_carrito.anadir/quitar_linea/vaciar`. Sigue siendo una aproximación honesta y no una certeza
absoluta: solo captura "última vez que el carrito CAMBIÓ de contenido", no "última vez que el usuario
miró la página" (este portal no tiene telemetría de vistas — sin JS de sondeo, página por página,
igual que el resto de portales B2B, ver docstring de `b2b_chat.py`).

Un carrito con líneas NUNCA puede corresponder a un pedido ya tramitado: `b2b_pedidos.tramitar` vacía
el carrito (`b2b_carrito.vaciar`) en la misma operación que crea el pedido (ver `tramitar()`, línea
final `b2b_carrito.vaciar(token_sesion)`). Por eso basta con "tiene líneas y lleva tiempo sin
actividad" — no hace falta cruzar con `transaccion_comercial` para descartar un checkout ya hecho.

`b2b_carrito_abandono` (migr. 0280) es el registro de detección/notificación: persiste qué carritos ya
se marcaron (para no re-notificar en cada pasada del job uno sin cambios) y es la fuente que leen tanto
el aviso "Reanudar Pedido" del Portal Empresa como la vista de carritos abandonados del Portal
Proveedor — una sola tabla para ambos consumidores, sin duplicar estado.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_carrito_abandono")

HORAS_UMBRAL_DEFECTO = 2.0


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _candidatos(horas_umbral) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT cl.token_sesion,
                       MIN(cl.id_suministrador) AS id_suministrador,
                       COUNT(*) AS n_lineas,
                       SUM(cl.cantidad * cl.precio_unitario) AS total,
                       COALESCE(act.actualizado_en, MAX(cl.creado_en)) AS ultima_actividad,
                       ses.id_empresa AS id_empresa
                FROM b2b_carrito_lineas cl
                LEFT JOIN b2b_carrito_actividad act ON act.token_sesion = cl.token_sesion
                LEFT JOIN b2b_sesiones_empresa ses ON ses.token_sesion = cl.token_sesion
                GROUP BY cl.token_sesion, ses.id_empresa
                HAVING ultima_actividad < (NOW() - INTERVAL %s HOUR)
            """, (float(horas_umbral),))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("_candidatos: %s", e)
        return []


def detectar_y_marcar(horas_umbral=HORAS_UMBRAL_DEFECTO) -> list[dict]:
    """Ejecuta la detección y persiste/actualiza `b2b_carrito_abandono`. Devuelve SOLO los carritos
    recién marcados (o re-marcados tras reactivarse y volver a quedar inactivos) en ESTA pasada —
    idempotente por `token_sesion`: si ya hay un registro sin resolver con la misma `ultima_actividad`,
    no se vuelve a notificar."""
    nuevos = []
    for c in _candidatos(horas_umbral):
        token = c["token_sesion"]
        if not c.get("id_empresa"):
            # Token sin sesión asociada (huérfano — p. ej. datos de prueba/carrito de una sesión ya
            # purgada). No se puede notificar sin saber a qué empresa avisar: se omite honestamente en
            # vez de adivinar.
            logger.debug("detectar_y_marcar: token %s sin sesión asociada, omitido", token)
            continue
        try:
            ensure_schema()
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT ultima_actividad, resuelto FROM b2b_carrito_abandono "
                            "WHERE token_sesion=%s", (token,))
                existente = cur.fetchone()
                existente = _fila(cur, existente) if existente else None
                reflagar = (existente is None or bool(existente["resuelto"]) or
                            str(existente["ultima_actividad"]) != str(c["ultima_actividad"]))
                cur.execute(
                    "INSERT INTO b2b_carrito_abandono (token_sesion, id_empresa, id_suministrador, "
                    "n_lineas, total, ultima_actividad, marcado_en, resuelto) "
                    "VALUES (%s,%s,%s,%s,%s,%s,NOW(),0) "
                    "ON DUPLICATE KEY UPDATE id_empresa=VALUES(id_empresa), "
                    "id_suministrador=VALUES(id_suministrador), n_lineas=VALUES(n_lineas), "
                    "total=VALUES(total), ultima_actividad=VALUES(ultima_actividad), "
                    "marcado_en=IF(%s, NOW(), marcado_en), resuelto=0",
                    (token, c["id_empresa"], c["id_suministrador"], c["n_lineas"], c["total"],
                     c["ultima_actividad"], reflagar))
                conn.commit()
        except Exception as e:
            logger.error("detectar_y_marcar(%s): %s", token, e)
            continue
        if reflagar:
            nuevos.append(c)
    return nuevos


def listar_para_empresa(id_empresa) -> list[dict]:
    """Carritos abandonados SIN resolver de una empresa (Portal Empresa, aviso "Reanudar Pedido")."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_carrito_abandono WHERE id_empresa=%s AND resuelto=0 "
                        "ORDER BY marcado_en DESC", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_para_empresa(%s): %s", id_empresa, e)
        return []


def listar_para_proveedor(id_suministrador) -> list[dict]:
    """Carritos abandonados SIN resolver que contienen artículos de este proveedor (Portal Proveedor,
    vista de carritos abandonados + oferta especial)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_carrito_abandono WHERE id_suministrador=%s AND resuelto=0 "
                        "ORDER BY marcado_en DESC", (id_suministrador,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_para_proveedor(%s): %s", id_suministrador, e)
        return []


def obtener(token_sesion) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_carrito_abandono WHERE token_sesion=%s", (token_sesion,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener(%s): %s", token_sesion, e)
        return None


def marcar_resuelto(token_sesion) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_carrito_abandono SET resuelto=1 WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("marcar_resuelto(%s): %s", token_sesion, e)
        return False


def _job_detectar(id_empresa=None):
    """Callable del Scheduler — firma `fn(id_empresa)` como exige `scheduler.ejecutar_job` (la
    detección es transversal a todas las empresas, `id_empresa` no se usa para filtrar)."""
    nuevos = detectar_y_marcar()
    if nuevos:
        logger.info("carrito_abandono: %d carrito(s) recién marcado(s) como abandonado(s)", len(nuevos))
    return f"nuevos={len(nuevos)}"


def registrar_jobs_abandono(id_empresa=None):
    """Registra el job en el Scheduler (idempotente), mismo patrón exacto que
    `b2b_rappels.registrar_jobs_rappels`/`sync_worker.registrar_jobs_sync_canales`. El job queda
    registrado con `intervalo_horas=1` (la granularidad mínima que admite la columna INT de
    `scheduler_jobs`) para auditoría/panel, pero la detección REAL (umbral de 2h) se dispara cada
    pocos minutos desde el latido de `main.py` (`_tick_ic_sync_canales`, 2 min — mismo mecanismo que ya
    usa `ic_sync_canales`), llamando a `scheduler.ejecutar_job` directamente sin esperar a
    `ejecutar_pendientes()`. Degradable: si el Scheduler no está disponible, la detección manual
    (`detectar_y_marcar()`) sigue funcionando igual."""
    try:
        from src.services import scheduler
        scheduler.registrar("b2b_carrito_abandono", _job_detectar)
        scheduler.registrar_job("b2b_carrito_abandono", intervalo_horas=1,
                                descripcion="Smart Suppliers: detectar carritos B2B abandonados "
                                           "(sin actividad desde hace más de 2h)", id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_abandono: %s", e)
