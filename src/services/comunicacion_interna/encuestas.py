"""
Encuestas internas — personalizables (preguntas de OPCIONES o de TEXTO, opciones ilimitadas, opción
"Otro" implícita con texto libre), texto introductorio, adjuntos en envío y respuestas. Cada centro
responde verificando perfil + contraseña.
"""

from __future__ import annotations

import logging

from . import adjuntos as ADJ

logger = logging.getLogger("comunicacion_interna.encuestas")

ENTIDAD = "ENCUESTA"
TIPO_OPCIONES = "OPCIONES"
TIPO_TEXTO = "TEXTO"


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or {}
    except Exception:
        return {}


def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ─── Creación (emisor) ────────────────────────────────────────────────────────

def crear_encuesta(titulo, intro, preguntas, *, adjuntos=None, destinatarios=None, usuario=None,
                   id_empresa=None) -> dict:
    """Crea una encuesta. `preguntas` = [{texto, tipo(OPCIONES/TEXTO), opciones:[str,...]}].
    Las preguntas de opciones muestran "Otro" automáticamente en la GUI (no se almacena).

    `destinatarios` (opcional) acepta 3 formas, libremente mezcladas (mismas reglas que
    `circulares.crear_circular`): `{"usuario_id":...}` interno (RE-VALIDADO contra la empresa real),
    `{"centro_codigo":...}` (expandido a un `usuario_id` por cada empleado activo de ese centro, EN
    ESTA empresa — nunca se expande un centro ajeno) y `{"email_externo":...,"nombre":...}` (contacto
    fuera del ERP: no genera fila en `com_destinatarios`, se envía como correo REAL best-effort tras
    crear la encuesta, ver `_enviar_externos`). Se exige al menos un destinatario "PARA" válido
    (interno O externo) tras expandir/filtrar; si no queda ninguno, no se crea nada. Si no se indica
    (None/vacío), se conserva el comportamiento histórico: difusión a toda la empresa. Devuelve
    {ok, id, externos_fallidos?}."""
    titulo = (titulo or "").strip()
    if not titulo:
        return {"ok": False, "error": "El título es obligatorio."}
    preguntas = [p for p in (preguntas or []) if (p.get("texto") or "").strip()]
    if not preguntas:
        return {"ok": False, "error": "Añade al menos una pregunta."}
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    externos = []
    try:
        with _conn() as conn, conn.cursor() as cur:
            destinatarios_validos = None
            if destinatarios:
                from src.services.comunicacion_interna.usuarios_internos import (
                    expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
                usuario_entries, externos = expandir_destinatarios(cur, emp, destinatarios)
                destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
                hay_para = (any((d.get("tipo") or "").upper() == "PARA" for d in destinatarios_validos)
                           or any((d.get("tipo") or "").upper() == "PARA" for d in externos))
                if not hay_para:
                    return {"ok": False, "error": "Debes indicar al menos un destinatario en «Para»."}
            cur.execute(
                "INSERT INTO com_encuestas (id_empresa, titulo, intro, creador_id, creador_nombre) "
                "VALUES (%s,%s,%s,%s,%s)",
                (emp, titulo, intro or "", str(u.get("id")) if u.get("id") is not None else None,
                 u.get("nombre") or "—"))
            eid = cur.lastrowid
            for i, p in enumerate(preguntas):
                tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                cur.execute(
                    "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                    "VALUES (%s,%s,%s,%s)", (eid, i, (p.get("texto") or "").strip(), tipo))
                pid = cur.lastrowid
                if tipo == TIPO_OPCIONES:
                    ops = [o for o in (p.get("opciones") or []) if (o or "").strip()]
                    for j, o in enumerate(ops):
                        cur.execute(
                            "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                            "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=eid, origen="EMISOR", cur=cur)
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, eid, destinatarios_validos)
            conn.commit()
    except Exception as e:
        logger.error(f"crear_encuesta: {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "id": eid}
    if externos:
        fallidos = _enviar_externos(titulo, intro or "", externos, id_empresa=emp, usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def _enviar_externos(titulo, intro, externos, *, id_empresa, usuario=None) -> list[str]:
    """Envía la encuesta, como correo REAL (resumen: título + intro + nota de que es una encuesta
    interna — NO se renderiza la UI de preguntas/respuestas por email), a cada destinatario
    `email_externo` desde el buzón corporativo ACTIVO de la empresa. Mismo patrón best-effort que
    `circulares._enviar_externos` (nunca rompe el flujo principal; un fallo solo se refleja en la
    lista devuelta). Registra cada envío correcto en el histórico para que el contacto se siga
    sugiriendo en el futuro."""
    fallidos = []
    try:
        from src.db import correo as correo_db
        buzones = [b for b in correo_db.listar_correos(id_empresa) if b.get("estado") == "activo"]
    except Exception as e:
        logger.debug(f"_enviar_externos: no se pudo listar buzones: {e}")
        buzones = []
    if not buzones:
        logger.warning("_enviar_externos: sin buzón corporativo activo, %d destinatario(s) externo(s) "
                       "no recibieron la encuesta.", len(externos))
        return [d.get("email_externo") for d in externos if d.get("email_externo")]
    id_correo = buzones[0]["id_correo"]
    cuerpo = (intro or "").strip()
    if cuerpo:
        cuerpo += "\n\n"
    cuerpo += ("Esta es una encuesta interna de la empresa. Ponte en contacto con el remitente para "
              "poder participar.")
    from src.services.correo import servicio as correo_svc
    from src.services.destinatarios import historico
    for d in externos:
        correo = (d.get("email_externo") or "").strip()
        if not correo:
            continue
        try:
            ok, _msg = correo_svc.enviar_documento(id_correo, correo, titulo, cuerpo)
        except Exception as e:
            logger.debug(f"_enviar_externos({correo}): {e}")
            ok = False
        if ok:
            try:
                historico.registrar_envio(
                    correo, d.get("nombre"), id_empresa=id_empresa,
                    id_usuario=(usuario or {}).get("nombre") or (usuario or {}).get("id"),
                    modulo_contexto="encuesta")
            except Exception:
                pass
        else:
            fallidos.append(correo)
    return fallidos


# ─── Bandeja / lectura ────────────────────────────────────────────────────────

def listar_encuestas(*, id_empresa=None, usuario_id=None) -> list[dict]:
    """`usuario_id` (opcional) filtra a "mi bandeja" — misma lógica que `listar_circulares`:
    destinatario registrado (Para/CC/Cco, incluido por reenvío), creador, o LEGACY sin ningún
    destinatario registrado (difusión histórica, compatibilidad hacia atrás).

    Con `usuario_id`, además SOLO se listan encuestas PUBLICADAS y NO pospuestas — mismo criterio
    que `circulares.listar_circulares` (ver ahí la nota sobre Borradores/Programadas/Papelera/
    Pospuestos teniendo sus propias funciones dedicadas)."""
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            sql = (
                "SELECT e.id, e.titulo, e.creador_nombre, e.creado, e.estado, e.importante, "
                "  (SELECT COUNT(*) FROM com_encuesta_respuestas r WHERE r.id_encuesta=e.id) AS respuestas "
                "FROM com_encuestas e WHERE e.id_empresa=%s")
            params = [emp]
            if usuario_id is not None:
                sql += (
                    " AND e.estado='PUBLICADA' "
                    "AND (e.pospuesto_hasta IS NULL OR e.pospuesto_hasta<=NOW()) AND ("
                    "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                    "AND d.id_entidad=e.id AND d.usuario_id=%s)"
                    " OR e.creador_id=%s"
                    " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                    "AND d2.id_entidad=e.id)"
                    ")")
                params += [ENTIDAD, usuario_id, str(usuario_id), ENTIDAD]
            sql += " ORDER BY e.creado DESC, e.id DESC"
            cur.execute(sql, tuple(params))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_encuestas degradado: {e}")
        return []


# ─── Borradores / Papelera / Programados / Pospuestos / Importantes ──────────
# Misma simplificación documentada que `circulares.py` (estado/pospuesto_hasta/importante son
# columnas ÚNICAS por encuesta, no por-destinatario).

def guardar_borrador(id_encuesta=None, *, titulo, intro="", preguntas=None, adjuntos=None,
                     destinatarios=None, usuario=None, id_empresa=None) -> dict:
    """Crea o actualiza un BORRADOR de encuesta. `preguntas` (opcional en un borrador) REEMPLAZA
    por completo las preguntas/opciones existentes si se indica (edición real); si se omite
    (None), conserva las que ya hubiera. Mismo límite de externos no persistidos que en
    `circulares.guardar_borrador`."""
    titulo = (titulo or "").strip()
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            if id_encuesta:
                cur.execute("SELECT id_empresa, creador_id, estado FROM com_encuestas WHERE id=%s",
                           (id_encuesta,))
                row = cur.fetchone()
                if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                    return {"ok": False, "error": "Borrador no encontrado."}
                if row[1] is not None and str(row[1]) != str(u.get("id")):
                    return {"ok": False, "error": "Este borrador pertenece a otro usuario."}
                cur.execute("UPDATE com_encuestas SET titulo=%s, intro=%s WHERE id=%s",
                           (titulo, intro or "", id_encuesta))
                eid = id_encuesta
            else:
                cur.execute(
                    "INSERT INTO com_encuestas (id_empresa, titulo, intro, creador_id, "
                    "creador_nombre, estado) VALUES (%s,%s,%s,%s,%s,'BORRADOR')",
                    (emp, titulo, intro or "", str(u.get("id")) if u.get("id") is not None else None,
                     u.get("nombre") or "—"))
                eid = cur.lastrowid
            if preguntas is not None:
                cur.execute("SELECT id FROM com_encuesta_preguntas WHERE id_encuesta=%s", (eid,))
                preg_ids = [r[0] for r in cur.fetchall()]
                if preg_ids:
                    marc = ",".join(["%s"] * len(preg_ids))
                    cur.execute(f"DELETE FROM com_encuesta_opciones WHERE id_pregunta IN ({marc})",
                               tuple(preg_ids))
                cur.execute("DELETE FROM com_encuesta_preguntas WHERE id_encuesta=%s", (eid,))
                preguntas = [p for p in preguntas if (p.get("texto") or "").strip()]
                for i, p in enumerate(preguntas):
                    tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                    cur.execute(
                        "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                        "VALUES (%s,%s,%s,%s)", (eid, i, (p.get("texto") or "").strip(), tipo))
                    pid = cur.lastrowid
                    if tipo == TIPO_OPCIONES:
                        ops = [o for o in (p.get("opciones") or []) if (o or "").strip()]
                        for j, o in enumerate(ops):
                            cur.execute(
                                "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                                "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            if adjuntos:
                ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=eid, origen="EMISOR", cur=cur)
            if destinatarios is not None:
                from src.services.comunicacion_interna.usuarios_internos import (
                    expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
                usuario_entries, _externos = expandir_destinatarios(cur, emp, destinatarios)
                destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
                cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                           (ENTIDAD, eid))
                if destinatarios_validos:
                    insertar_destinatarios(cur, ENTIDAD, eid, destinatarios_validos)
            conn.commit()
        return {"ok": True, "id": eid}
    except Exception as e:
        logger.error(f"guardar_borrador(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def listar_borradores(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_encuestas "
                "WHERE id_empresa=%s AND estado='BORRADOR' AND creador_id=%s "
                "ORDER BY creado DESC, id DESC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_borradores(encuesta): {e}")
        return []


def publicar_borrador(id_encuesta, *, destinatarios, titulo=None, intro=None, preguntas=None,
                      usuario=None, id_empresa=None) -> dict:
    """Publica un borrador. `titulo`/`intro`/`preguntas` (opcionales) permiten guardar de paso
    ediciones hechas en el compositor tras reabrir el borrador y publicar directamente, SIN pasar
    antes por «Guardar borrador» (mismo reemplazo completo de preguntas/opciones que
    `guardar_borrador`, para no perder una edición en silencio)."""
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado, titulo, intro FROM com_encuestas "
                       "WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                return {"ok": False, "error": "Borrador no encontrado."}
            if titulo is not None:
                cur.execute("UPDATE com_encuestas SET titulo=%s, intro=%s WHERE id=%s",
                           ((titulo or "").strip(), intro or "", id_encuesta))
            if preguntas is not None:
                cur.execute("SELECT id FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
                preg_ids = [r[0] for r in cur.fetchall()]
                if preg_ids:
                    marc = ",".join(["%s"] * len(preg_ids))
                    cur.execute(f"DELETE FROM com_encuesta_opciones WHERE id_pregunta IN ({marc})",
                               tuple(preg_ids))
                cur.execute("DELETE FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
                for i, p in enumerate(p for p in preguntas if (p.get("texto") or "").strip()):
                    tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                    cur.execute(
                        "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                        "VALUES (%s,%s,%s,%s)", (id_encuesta, i, (p.get("texto") or "").strip(), tipo))
                    pid = cur.lastrowid
                    if tipo == TIPO_OPCIONES:
                        for j, o in enumerate(o for o in (p.get("opciones") or []) if (o or "").strip()):
                            cur.execute(
                                "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                                "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            from src.services.comunicacion_interna.usuarios_internos import (
                expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
            usuario_entries, externos = expandir_destinatarios(cur, emp, destinatarios or [])
            destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
            hay_para = (any((d.get("tipo") or "").upper() == "PARA" for d in destinatarios_validos)
                       or any((d.get("tipo") or "").upper() == "PARA" for d in externos))
            if not hay_para:
                return {"ok": False, "error": "Debes indicar al menos un destinatario en «Para»."}
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                       (ENTIDAD, id_encuesta))
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, id_encuesta, destinatarios_validos)
            cur.execute("UPDATE com_encuestas SET estado='PUBLICADA', creado=NOW() WHERE id=%s",
                       (id_encuesta,))
            titulo_final = titulo if titulo is not None else row[3]
            intro_final = intro if intro is not None else row[4]
            conn.commit()
    except Exception as e:
        logger.error(f"publicar_borrador(encuesta): {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "id": id_encuesta}
    if externos:
        fallidos = _enviar_externos(titulo_final, intro_final or "", externos, id_empresa=emp, usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def eliminar_borrador(id_encuesta, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_encuestas WHERE id=%s",
                       (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                return {"ok": False, "error": "Borrador no encontrado."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Este borrador pertenece a otro usuario."}
    except Exception as e:
        logger.error(f"eliminar_borrador(encuesta): {e}")
        return {"ok": False, "error": str(e)}
    return {"ok": eliminar_encuesta(id_encuesta, id_empresa=id_empresa)}


def programar(id_encuesta_borrador=None, *, titulo=None, intro=None, preguntas=None,
             fecha_programada, destinatarios, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            from src.services.comunicacion_interna.usuarios_internos import (
                expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
            usuario_entries, externos = expandir_destinatarios(cur, emp, destinatarios or [])
            destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
            hay_para = any((d.get("tipo") or "").upper() == "PARA" for d in destinatarios_validos)
            if not hay_para:
                return {"ok": False, "error": "Debes indicar al menos un destinatario interno en «Para» "
                                              "(el envío programado no soporta contactos externos)."}
            if id_encuesta_borrador:
                cur.execute("SELECT id_empresa, estado FROM com_encuestas WHERE id=%s",
                           (id_encuesta_borrador,))
                row = cur.fetchone()
                if not row or str(row[0]) != str(emp) or row[1] != "BORRADOR":
                    return {"ok": False, "error": "Borrador no encontrado."}
                eid = id_encuesta_borrador
                if titulo is not None:
                    cur.execute("UPDATE com_encuestas SET titulo=%s, intro=%s WHERE id=%s",
                               ((titulo or "").strip(), intro or "", eid))
                if preguntas is not None:
                    cur.execute("SELECT id FROM com_encuesta_preguntas WHERE id_encuesta=%s", (eid,))
                    preg_ids = [r[0] for r in cur.fetchall()]
                    if preg_ids:
                        marc = ",".join(["%s"] * len(preg_ids))
                        cur.execute(f"DELETE FROM com_encuesta_opciones WHERE id_pregunta IN ({marc})",
                                   tuple(preg_ids))
                    cur.execute("DELETE FROM com_encuesta_preguntas WHERE id_encuesta=%s", (eid,))
                    for i, p in enumerate(p for p in preguntas if (p.get("texto") or "").strip()):
                        tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                        cur.execute(
                            "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                            "VALUES (%s,%s,%s,%s)", (eid, i, (p.get("texto") or "").strip(), tipo))
                        pid = cur.lastrowid
                        if tipo == TIPO_OPCIONES:
                            for j, o in enumerate(o for o in (p.get("opciones") or []) if (o or "").strip()):
                                cur.execute(
                                    "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                                    "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            else:
                titulo = (titulo or "").strip()
                if not titulo:
                    return {"ok": False, "error": "El título es obligatorio."}
                preguntas_validas = [p for p in (preguntas or []) if (p.get("texto") or "").strip()]
                if not preguntas_validas:
                    return {"ok": False, "error": "Añade al menos una pregunta."}
                cur.execute(
                    "INSERT INTO com_encuestas (id_empresa, titulo, intro, creador_id, "
                    "creador_nombre, estado) VALUES (%s,%s,%s,%s,%s,'BORRADOR')",
                    (emp, titulo, intro or "", str(u.get("id")) if u.get("id") is not None else None,
                     u.get("nombre") or "—"))
                eid = cur.lastrowid
                for i, p in enumerate(preguntas_validas):
                    tipo = TIPO_TEXTO if str(p.get("tipo", "")).upper() == TIPO_TEXTO else TIPO_OPCIONES
                    cur.execute(
                        "INSERT INTO com_encuesta_preguntas (id_encuesta, orden, texto, tipo) "
                        "VALUES (%s,%s,%s,%s)", (eid, i, (p.get("texto") or "").strip(), tipo))
                    pid = cur.lastrowid
                    if tipo == TIPO_OPCIONES:
                        for j, o in enumerate(o for o in (p.get("opciones") or []) if (o or "").strip()):
                            cur.execute(
                                "INSERT INTO com_encuesta_opciones (id_pregunta, orden, texto) "
                                "VALUES (%s,%s,%s)", (pid, j, o.strip()))
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                       (ENTIDAD, eid))
            insertar_destinatarios(cur, ENTIDAD, eid, destinatarios_validos)
            cur.execute("UPDATE com_encuestas SET estado='PROGRAMADA', fecha_programada=%s WHERE id=%s",
                       (fecha_programada, eid))
            conn.commit()
        resultado = {"ok": True, "id": eid}
        if externos:
            resultado["externos_no_programables"] = [d.get("email_externo") for d in externos
                                                      if d.get("email_externo")]
        return resultado
    except Exception as e:
        logger.error(f"programar(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def cancelar_programacion(id_encuesta, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, estado FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[1] != "PROGRAMADA":
                return {"ok": False, "error": "No hay ninguna programación que cancelar."}
            cur.execute("UPDATE com_encuestas SET estado='BORRADOR', fecha_programada=NULL WHERE id=%s",
                       (id_encuesta,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"cancelar_programacion(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def listar_programadas(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado, fecha_programada FROM com_encuestas "
                "WHERE id_empresa=%s AND estado='PROGRAMADA' AND creador_id=%s "
                "ORDER BY fecha_programada ASC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_programadas(encuesta): {e}")
        return []


def disparar_programadas_vencidas(id_empresa=None) -> str:
    """Job del scheduler (`com_programados_envio`): publica toda encuesta PROGRAMADA vencida."""
    emp = _empresa(id_empresa)
    n = 0
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM com_encuestas WHERE id_empresa=%s AND estado='PROGRAMADA' "
                       "AND fecha_programada IS NOT NULL AND fecha_programada<=NOW()", (emp,))
            ids = [r[0] for r in cur.fetchall()]
            for eid in ids:
                cur.execute("UPDATE com_encuestas SET estado='PUBLICADA', creado=NOW() WHERE id=%s",
                           (eid,))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error(f"disparar_programadas_vencidas(encuesta): {e}")
        return f"error={e}"
    return f"encuestas_disparadas={n}"


def mover_papelera(id_encuesta, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_encuestas WHERE id=%s",
                       (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp):
                return {"ok": False, "error": "Encuesta no encontrada."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Solo el creador puede mover esta encuesta a la papelera."}
            if row[2] != "PUBLICADA":
                return {"ok": False, "error": "Solo se puede mover a la papelera una encuesta publicada."}
            cur.execute("UPDATE com_encuestas SET estado='PAPELERA' WHERE id=%s", (id_encuesta,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"mover_papelera(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def restaurar_de_papelera(id_encuesta, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_encuestas WHERE id=%s",
                       (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "PAPELERA":
                return {"ok": False, "error": "No está en la papelera."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Solo el creador puede restaurar esta encuesta."}
            cur.execute("UPDATE com_encuestas SET estado='PUBLICADA' WHERE id=%s", (id_encuesta,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"restaurar_de_papelera(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def listar_papelera(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_encuestas "
                "WHERE id_empresa=%s AND estado='PAPELERA' AND creador_id=%s "
                "ORDER BY creado DESC, id DESC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_papelera(encuesta): {e}")
        return []


def marcar_importante(id_encuesta, valor: bool, *, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp):
                return {"ok": False, "error": "Encuesta no encontrada."}
            cur.execute("UPDATE com_encuestas SET importante=%s WHERE id=%s",
                       (1 if valor else 0, id_encuesta))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"marcar_importante(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def listar_importantes(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_encuestas e "
                "WHERE e.id_empresa=%s AND e.importante=1 AND e.estado='PUBLICADA' AND ("
                "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                "AND d.id_entidad=e.id AND d.usuario_id=%s)"
                " OR e.creador_id=%s"
                " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                "AND d2.id_entidad=e.id)) ORDER BY e.creado DESC, e.id DESC",
                (emp, ENTIDAD, usuario_id, str(usuario_id), ENTIDAD))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_importantes(encuesta): {e}")
        return []


def posponer(id_encuesta, hasta, *, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, estado FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[1] != "PUBLICADA":
                return {"ok": False, "error": "Encuesta no encontrada o no publicada."}
            cur.execute("UPDATE com_encuestas SET pospuesto_hasta=%s WHERE id=%s",
                       (hasta, id_encuesta))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"posponer(encuesta): {e}")
        return {"ok": False, "error": str(e)}


def listar_pospuestos(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado, pospuesto_hasta FROM com_encuestas e "
                "WHERE e.id_empresa=%s AND e.estado='PUBLICADA' AND e.pospuesto_hasta IS NOT NULL "
                "AND e.pospuesto_hasta>NOW() AND ("
                "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                "AND d.id_entidad=e.id AND d.usuario_id=%s)"
                " OR e.creador_id=%s"
                " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                "AND d2.id_entidad=e.id)) ORDER BY e.pospuesto_hasta ASC",
                (emp, ENTIDAD, usuario_id, str(usuario_id), ENTIDAD))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_pospuestos(encuesta): {e}")
        return []


def obtener_encuesta(id_encuesta) -> dict | None:
    """Encuesta completa: cabecera + preguntas(+opciones) + adjuntos emisor + respuestas(+items+adjuntos)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM com_encuestas WHERE id=%s", (id_encuesta,))
            filas = _rows(cur)
            if not filas:
                return None
            enc = filas[0]
            cur.execute("SELECT id, orden, texto, tipo FROM com_encuesta_preguntas "
                        "WHERE id_encuesta=%s ORDER BY orden ASC, id ASC", (id_encuesta,))
            preguntas = _rows(cur)
            for p in preguntas:
                cur.execute("SELECT id, orden, texto FROM com_encuesta_opciones "
                            "WHERE id_pregunta=%s ORDER BY orden ASC, id ASC", (p["id"],))
                p["opciones"] = _rows(cur)
            cur.execute("SELECT id, usuario_nombre, id_centro, comentario, creado "
                        "FROM com_encuesta_respuestas WHERE id_encuesta=%s ORDER BY creado ASC",
                        (id_encuesta,))
            respuestas = _rows(cur)
            for r in respuestas:
                cur.execute("SELECT id_pregunta, id_opcion, texto FROM com_encuesta_resp_items "
                            "WHERE id_respuesta=%s", (r["id"],))
                r["items"] = _rows(cur)
        enc["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_encuesta, origen="EMISOR", id_respuesta=None)
        for r in respuestas:
            r["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_encuesta, origen="RESPUESTA",
                                                id_respuesta=r["id"])
        enc["preguntas"] = preguntas
        enc["respuestas"] = respuestas
        enc["destinatarios"] = _destinatarios_de(id_encuesta)
        return enc
    except Exception as e:
        logger.error(f"obtener_encuesta: {e}")
        return None


def _destinatarios_de(id_encuesta) -> list[dict]:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT usuario_id, usuario_nombre, tipo, reenviado_por, leido, creado "
                "FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s ORDER BY creado ASC",
                (ENTIDAD, id_encuesta))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"_destinatarios_de(encuesta): {e}")
        return []


# ─── Reenvío ───────────────────────────────────────────────────────────────────

def reenviar_encuesta(id_encuesta, destinatarios, *, usuario=None, id_empresa=None) -> dict:
    """Reenvía una encuesta EXISTENTE a más destinatarios (no duplica la fila de la encuesta: solo
    añade destinatarios apuntando al mismo `id_encuesta`, con `reenviado_por`). Acepta las mismas 3
    formas que `crear_encuesta` (`usuario_id`/`centro_codigo` con fan-out/`email_externo`). Aislamiento
    estricto: la encuesta debe existir y, si se indica `id_empresa`, debe coincidir con la suya;
    además cada destinatario interno (original o expandido desde un centro) debe pertenecer a la
    MISMA empresa que la encuesta (nunca cruza empresas)."""
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    destinatarios_validos: list[dict] = []
    externos: list[dict] = []
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, titulo, intro FROM com_encuestas WHERE id=%s",
                       (id_encuesta,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Encuesta no encontrada."}
            id_emp_encuesta, titulo, intro = row[0], row[1], row[2]
            if emp and str(id_emp_encuesta) != str(emp):
                return {"ok": False, "error": "No puedes reenviar una encuesta de otra empresa."}
            from src.services.comunicacion_interna.usuarios_internos import (
                expandir_destinatarios, insertar_destinatarios)
            usuario_entries, externos = expandir_destinatarios(cur, id_emp_encuesta, destinatarios)
            ids = [d["usuario_id"] for d in usuario_entries]
            if ids:
                marcadores = ",".join(["%s"] * len(ids))
                cur.execute(
                    f"SELECT id FROM usuarios WHERE id IN ({marcadores}) AND id_empresa=%s AND activo=1",
                    tuple(ids) + (id_emp_encuesta,))
                validos = {r[0] for r in cur.fetchall()}
                destinatarios_validos = [d for d in usuario_entries if d["usuario_id"] in validos]
            if not destinatarios_validos and not externos:
                return {"ok": False, "error": "Indica al menos un destinatario para reenviar."}
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, id_encuesta, destinatarios_validos,
                                       reenviado_por=u.get("nombre") or "—")
            conn.commit()
    except Exception as e:
        logger.error(f"reenviar_encuesta: {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "n": len(destinatarios_validos)}
    if externos:
        fallidos = _enviar_externos(titulo, intro or "", externos, id_empresa=id_emp_encuesta,
                                    usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def responder_encuesta(id_encuesta, *, usuario_nombre, password, respuestas, comentario="",
                       adjuntos=None, id_empresa=None) -> dict:
    """Registra la respuesta verificando perfil+contraseña.
    `respuestas` = { id_pregunta: {'opciones':[id_opcion,...], 'otro': str, 'texto': str} }.

    La validación de credenciales se acota SIEMPRE a la empresa EXPLÍCITA de la encuesta (nunca a
    la empresa ambiente del proceso/hilo) — mismo criterio que `circulares.confirmar_lectura`."""
    emp = _empresa(id_empresa)
    from src.db.empresa import contexto_tenant
    from src.db.usuario import validar_login_empleado
    with contexto_tenant(emp):
        u = validar_login_empleado(usuario_nombre or "", password or "")
    if not u:
        return {"ok": False, "error": "Perfil o contraseña incorrectos."}
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Encuesta no encontrada."}
            if u.get("id_empresa") and emp and str(u["id_empresa"]) != str(emp):
                return {"ok": False, "error": "El perfil no pertenece a esta empresa."}
            cur.execute(
                "INSERT INTO com_encuesta_respuestas "
                "(id_encuesta, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_encuesta, str(u.get("id")), u.get("nombre"), u.get("centro_codigo"), comentario or ""))
            rid = cur.lastrowid
            for id_pregunta, resp in (respuestas or {}).items():
                resp = resp or {}
                for op in (resp.get("opciones") or []):
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, id_opcion) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, op))
                otro = (resp.get("otro") or "").strip()
                if otro:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, otro))
                texto = (resp.get("texto") or "").strip()
                if texto:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, texto))
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_encuesta,
                               origen="RESPUESTA", id_respuesta=rid, cur=cur)
            conn.commit()
        return {"ok": True, "id": rid, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"responder_encuesta: {e}")
        return {"ok": False, "error": str(e)}


def responder_encuesta_autenticado(id_encuesta, *, usuario, respuestas, comentario="", adjuntos=None,
                                   id_empresa=None) -> dict:
    """Responde a una encuesta reutilizando la identidad YA AUTENTICADA del llamador (sesión de
    escritorio ya logueada / token JWT móvil) — SIN re-pedir contraseña. Mismo efecto exacto y misma
    tabla (`com_encuesta_respuestas`+`com_encuesta_resp_items`) que `responder_encuesta`, del que es
    un PARALELO (Strangler Pattern): `responder_encuesta` sigue existiendo tal cual para el escenario
    de terminal compartido (reautenticación perfil+contraseña); esta función (nombre distinto porque
    `responder_encuesta` ya está tomado por la versión con contraseña) es la adecuada cuando quien
    llama YA demostró su identidad. Aislamiento igual que `reenviar_encuesta`: compara la empresa REAL
    de la encuesta (consultada aquí, nunca la que diga el llamador) contra `id_empresa`."""
    u = _usuario(usuario)
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_encuestas WHERE id=%s", (id_encuesta,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Encuesta no encontrada."}
            if emp and str(row[0]) != str(emp):
                return {"ok": False, "error": "No puedes responder a una encuesta de otra empresa."}
            cur.execute(
                "INSERT INTO com_encuesta_respuestas "
                "(id_encuesta, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_encuesta, str(u.get("id")) if u.get("id") is not None else None, u.get("nombre"),
                 u.get("centro_codigo"), comentario or ""))
            rid = cur.lastrowid
            for id_pregunta, resp in (respuestas or {}).items():
                resp = resp or {}
                for op in (resp.get("opciones") or []):
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, id_opcion) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, op))
                otro = (resp.get("otro") or "").strip()
                if otro:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, otro))
                texto = (resp.get("texto") or "").strip()
                if texto:
                    cur.execute("INSERT INTO com_encuesta_resp_items (id_respuesta, id_pregunta, texto) "
                                "VALUES (%s,%s,%s)", (rid, id_pregunta, texto))
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_encuesta,
                               origen="RESPUESTA", id_respuesta=rid, cur=cur)
            conn.commit()
        return {"ok": True, "id": rid, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"responder_encuesta_autenticado: {e}")
        return {"ok": False, "error": str(e)}


# ─── Estado de lectura (bandeja unificada de Correo) ──────────────────────────

def marcar_leido_encuesta(id_encuesta, usuario_id) -> bool:
    """Marca `com_destinatarios.leido=1` para la fila de ESTE usuario en esta encuesta (usado por
    la bandeja unificada de `gui.correo_corporativo` tras abrir el visor). Si el usuario no tiene
    fila de destinatario registrada (difusión legacy o es el propio creador), el UPDATE
    simplemente no afecta a ninguna fila — no se inventa una relación de destinatario que no
    existía. Deliberadamente tenant-unaware (una sola sentencia UPDATE): ya viene acotado por
    usuario_id+id_entidad, ambos ya validados antes de llegar aquí."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE com_destinatarios SET leido=1 WHERE tipo_entidad=%s AND id_entidad=%s "
                "AND usuario_id=%s", (ENTIDAD, id_encuesta, usuario_id))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"marcar_leido_encuesta: {e}")
        return False


def eliminar_encuesta(id_encuesta, *, id_empresa=None) -> bool:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM com_encuesta_respuestas WHERE id_encuesta=%s", (id_encuesta,))
            resp_ids = [r[0] for r in cur.fetchall()]
            if resp_ids:
                marc = ",".join(["%s"] * len(resp_ids))
                cur.execute(f"DELETE FROM com_encuesta_resp_items WHERE id_respuesta IN ({marc})",
                            tuple(resp_ids))
            cur.execute("SELECT id FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
            preg_ids = [r[0] for r in cur.fetchall()]
            if preg_ids:
                marc = ",".join(["%s"] * len(preg_ids))
                cur.execute(f"DELETE FROM com_encuesta_opciones WHERE id_pregunta IN ({marc})",
                            tuple(preg_ids))
            cur.execute("DELETE FROM com_encuesta_respuestas WHERE id_encuesta=%s", (id_encuesta,))
            cur.execute("DELETE FROM com_encuesta_preguntas WHERE id_encuesta=%s", (id_encuesta,))
            cur.execute("DELETE FROM com_adjuntos WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_encuesta))
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_encuesta))
            cur.execute("DELETE FROM com_encuestas WHERE id=%s", (id_encuesta,))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"eliminar_encuesta: {e}")
        return False
