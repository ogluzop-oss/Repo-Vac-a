"""
Monitorización de reputación — reglas por palabras clave sobre los mensajes/comentarios/menciones
entrantes ya sincronizados (`inbox.py`) y escalado automático a Incidencias
(`services.incidencias_internas.tickets.crear_ticket_automatico`, migr. 0325) cuando una regla
activa coincide. Detección deliberadamente simple (coincidencia de subcadena, sin NLP/sentimiento
de terceros): es honesta y predecible, nunca inventa un "análisis de sentimiento con IA" que no
existe en el repo — si en el futuro se conecta un motor de sentimiento real, este es el único
punto de enganche (`_coincide_regla`).
"""

import logging

logger = logging.getLogger("redes_sociales.reputacion")

# Regla predeterminada (petición explícita): cada empresa debe partir con un conjunto de palabras
# clave YA definido, sin que el superadministrador tenga que crearlo desde cero — pero totalmente
# editable/borrable después (ver `editar_regla`/`eliminar_regla`), nunca de solo lectura.
NOMBRE_REGLA_DEFECTO = "Quejas graves (predeterminada)"
PALABRAS_DEFECTO = ("estafa", "fraude", "denuncia", "demanda", "robo", "engaño", "boicot",
                    "pésimo servicio", "vergüenza", "incompetentes", "nunca más",
                    "no lo recomiendo")


class ReputacionError(Exception):
    pass


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _sembrar_default_si_vacio(id_empresa) -> None:
    """Crea la regla predeterminada la PRIMERA vez que una empresa consulta sus reglas (ninguna
    creada todavía) — siembra perezosa por tenant, sin tocar migraciones (multiempresa: cada
    empresa necesita su propia fila, no una fila global). Idempotente y silenciosa ante error."""
    try:
        from src.db.conexion import obtener_conexion, transaccion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM redes_sociales_reglas_reputacion WHERE "
                       "id_empresa=%s", (id_empresa,))
            if (cur.fetchone() or (0,))[0]:
                return
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO redes_sociales_reglas_reputacion (id_empresa, nombre, "
                "palabras_clave, prioridad_ticket) VALUES (%s,%s,%s,'alta')",
                (id_empresa, NOMBRE_REGLA_DEFECTO, ",".join(PALABRAS_DEFECTO)))
    except Exception as e:
        logger.debug("_sembrar_default_si_vacio(%s): %s", id_empresa, e)


def crear_regla(nombre, palabras_clave, *, prioridad_ticket="alta", id_empresa=None) -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ReputacionError("El nombre de la regla es obligatorio.")
    if isinstance(palabras_clave, (list, tuple)):
        palabras_clave = ",".join(str(p).strip().lower() for p in palabras_clave if str(p).strip())
    if not (palabras_clave or "").strip():
        raise ReputacionError("Debes indicar al menos una palabra clave.")
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO redes_sociales_reglas_reputacion (id_empresa, nombre, "
                "palabras_clave, prioridad_ticket) VALUES (%s,%s,%s,%s)",
                (id_empresa, nombre, palabras_clave, prioridad_ticket))
            id_regla = cur.lastrowid
        return {"ok": True, "id": id_regla}
    except Exception as e:
        logger.error("crear_regla: %s", e)
        raise ReputacionError("No se pudo crear la regla.") from e


def listar_reglas(*, solo_activas=False, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    _sembrar_default_si_vacio(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if solo_activas:
        filtros.append("activa=1")
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM redes_sociales_reglas_reputacion WHERE " +
                " AND ".join(filtros) + " ORDER BY nombre", params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_reglas: %s", e)
        return []


def editar_regla(id_regla, *, nombre=None, palabras_clave=None, prioridad_ticket=None,
                 id_empresa=None) -> dict:
    """Edita una regla existente (petición explícita: las reglas, incluida la predeterminada, son
    totalmente editables). Solo actualiza los campos que se pasen."""
    id_empresa = _emp(id_empresa)
    if isinstance(palabras_clave, (list, tuple)):
        palabras_clave = ",".join(str(p).strip().lower() for p in palabras_clave if str(p).strip())
    sets, params = [], []
    if nombre is not None:
        nombre = nombre.strip()
        if not nombre:
            raise ReputacionError("El nombre de la regla es obligatorio.")
        sets.append("nombre=%s"); params.append(nombre)
    if palabras_clave is not None:
        if not palabras_clave.strip():
            raise ReputacionError("Debes indicar al menos una palabra clave.")
        sets.append("palabras_clave=%s"); params.append(palabras_clave)
    if prioridad_ticket is not None:
        sets.append("prioridad_ticket=%s"); params.append(prioridad_ticket)
    if not sets:
        return {"ok": False, "error": "sin_cambios"}
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE redes_sociales_reglas_reputacion SET {', '.join(sets)} "
                       f"WHERE id=%s AND id_empresa=%s", (*params, id_regla, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except ReputacionError:
        raise
    except Exception as e:
        logger.error("editar_regla(%s): %s", id_regla, e)
        return {"ok": False, "error": "error_interno"}


def eliminar_regla(id_regla, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM redes_sociales_reglas_reputacion WHERE id=%s AND "
                       "id_empresa=%s", (id_regla, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("eliminar_regla(%s): %s", id_regla, e)
        return {"ok": False, "error": "error_interno"}


def activar_regla(id_regla, activa, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE redes_sociales_reglas_reputacion SET activa=%s WHERE id=%s "
                       "AND id_empresa=%s", (bool(activa), id_regla, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("activar_regla(%s): %s", id_regla, e)
        return {"ok": False, "error": "error_interno"}


def _coincide_regla(texto, regla) -> bool:
    texto_l = (texto or "").lower()
    if not texto_l:
        return False
    palabras = [p.strip() for p in (regla.get("palabras_clave") or "").split(",") if p.strip()]
    return any(p in texto_l for p in palabras)


def evaluar_mensajes_nuevos(*, id_empresa=None, limite=500) -> dict:
    """Escanea mensajes entrantes sin alerta previa contra las reglas activas y escala a
    Incidencias los que coincidan. Se llama automáticamente tras cada `inbox.sincronizar` con
    nuevos mensajes; también puede invocarse manualmente desde la GUI ('Reevaluar ahora')."""
    id_empresa = _emp(id_empresa)
    reglas = listar_reglas(solo_activas=True, id_empresa=id_empresa)
    if not reglas:
        return {"ok": True, "evaluados": 0, "escalados": 0}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT m.id, m.id_conversacion, m.cuerpo, c.plataforma "
                "FROM redes_sociales_mensajes m JOIN redes_sociales_conversaciones c "
                "ON c.id=m.id_conversacion WHERE m.id_empresa=%s AND m.direccion='entrante' "
                "AND NOT EXISTS (SELECT 1 FROM redes_sociales_alertas a WHERE a.id_mensaje=m.id) "
                "ORDER BY m.id DESC LIMIT %s", (id_empresa, int(limite)))
            filas = cur.fetchall()
    except Exception as e:
        logger.error("evaluar_mensajes_nuevos: %s", e)
        return {"ok": False, "error": "error_interno"}

    escalados = 0
    for id_mensaje, id_conversacion, cuerpo, plataforma in filas:
        regla_match = next((r for r in reglas if _coincide_regla(cuerpo, r)), None)
        if not regla_match:
            continue
        try:
            _escalar(id_empresa, id_mensaje, id_conversacion, plataforma, cuerpo, regla_match)
            escalados += 1
        except Exception as e:
            logger.error("evaluar_mensajes_nuevos: escalado mensaje %s: %s", id_mensaje, e)
    return {"ok": True, "evaluados": len(filas), "escalados": escalados}


def _escalar(id_empresa, id_mensaje, id_conversacion, plataforma, texto, regla) -> None:
    from src.services.incidencias_internas import tickets as _tickets
    asunto = f"Mención negativa detectada en {plataforma} — regla '{regla['nombre']}'"
    descripcion = (f"Texto detectado: {(texto or '')[:500]}\n\nRegla aplicada: {regla['nombre']} "
                   f"(palabras clave: {regla['palabras_clave']})")
    r = _tickets.crear_ticket_automatico(asunto, descripcion,
                                         prioridad=regla.get("prioridad_ticket") or "alta",
                                         id_empresa=id_empresa)
    id_ticket = r.get("id") if r.get("ok") else None

    from src.db.conexion import transaccion
    with transaccion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO redes_sociales_alertas (id_empresa, id_mensaje, id_conversacion, "
            "id_regla, plataforma, texto_detectado, id_ticket_incidencia, estado) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'escalada')",
            (id_empresa, id_mensaje, id_conversacion, regla["id"], plataforma, texto, id_ticket))
        cur.execute("UPDATE redes_sociales_conversaciones SET prioridad='urgente' WHERE id=%s",
                   (id_conversacion,))
    try:
        from src.services import eventos as _EV
        _EV.publicar("REDES_SOCIALES_ALERTA_REPUTACION", id_empresa=id_empresa,
                     origen=f"redes_sociales:{plataforma}", ref_entidad="incidencia_interna",
                     ref_id=id_ticket, payload={"regla": regla["nombre"], "plataforma": plataforma})
    except Exception:
        pass


def listar_alertas(*, id_empresa=None, limite=200) -> list:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM redes_sociales_alertas WHERE id_empresa=%s ORDER BY "
                "fecha_creacion DESC LIMIT %s", (id_empresa, int(limite)))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_alertas: %s", e)
        return []
