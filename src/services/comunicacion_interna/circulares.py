"""
Circulares internas — comunicación del emisor a todos los centros de la empresa, con confirmación de
lectura por perfil (nombre + contraseña), comentario y adjuntos (texto/imagen) en envío y respuestas.
"""

from __future__ import annotations

import logging

from . import adjuntos as ADJ

logger = logging.getLogger("comunicacion_interna.circulares")

ENTIDAD = "CIRCULAR"


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

def crear_circular(titulo, cuerpo, *, adjuntos=None, destinatarios=None, usuario=None,
                   id_empresa=None) -> dict:
    """Crea y publica una circular. `adjuntos` = lista de rutas de archivo.

    `destinatarios` (opcional) acepta 3 formas, libremente mezcladas:
      · `{"usuario_id":int, "tipo":"PARA"|"CC"|"CCO", "nombre":str?}` — interno, RE-VALIDADO contra
        la empresa real (nunca se confía en que el llamador ya filtró bien — la GUI solo ofrece
        usuarios de la empresa activa, pero la frontera de seguridad real es esta función, igual que
        ya hace `reenviar_circular`).
      · `{"centro_codigo":str, "tipo":...}` — se EXPANDE a un `usuario_id` por cada empleado activo
        de ESE centro, en ESTA empresa (fan-out, ver `usuarios_internos.expandir_destinatarios`); un
        centro que no pertenece a la empresa se descarta en silencio, nunca se expande.
      · `{"email_externo":str, "nombre":str?, "tipo":...}` — contacto FUERA del ERP: no genera fila
        en `com_destinatarios` (no es usuario_id-addressable), se envía como correo REAL best-effort
        tras crear la circular (ver `_enviar_externos`) y nunca rompe la creación si falla.

    Se exige al menos un destinatario "PARA" válido tras expandir/filtrar (interno O externo); si no
    queda ninguno, no se crea nada. Si `destinatarios` no se indica (None/vacío), se conserva el
    comportamiento histórico: difusión a toda la empresa (compatibilidad con llamadores existentes).
    Devuelve {ok, id, externos_fallidos?} — `externos_fallidos` (lista de emails) solo aparece si
    algún envío externo falló; nunca indica que la circular en sí no se creó."""
    titulo = (titulo or "").strip()
    if not titulo:
        return {"ok": False, "error": "El título es obligatorio."}
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
                "INSERT INTO com_circulares (id_empresa, titulo, cuerpo, creador_id, creador_nombre) "
                "VALUES (%s,%s,%s,%s,%s)",
                (emp, titulo, cuerpo or "", str(u.get("id")) if u.get("id") is not None else None,
                 u.get("nombre") or "—"))
            cid = cur.lastrowid
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=cid, origen="EMISOR", cur=cur)
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, cid, destinatarios_validos)
            conn.commit()
    except Exception as e:
        logger.error(f"crear_circular: {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "id": cid}
    if externos:
        fallidos = _enviar_externos(titulo, cuerpo or "", externos, id_empresa=emp, usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def _enviar_externos(titulo, cuerpo, externos, *, id_empresa, usuario=None) -> list[str]:
    """Envía la circular, como correo REAL, a cada destinatario `email_externo` desde el buzón
    corporativo ACTIVO de la empresa (mismo criterio de selección de buzón que ya usa
    `gui/correo_corporativo.py`: el primer buzón con `estado='activo'`). Best-effort y NUNCA rompe el
    flujo principal (`crear_circular`/`reenviar_circular` ya completaron la parte interna) — un fallo
    aquí solo se refleja en la lista devuelta (`externos_fallidos` para el llamador). Registra cada
    envío correcto en el histórico (`destinatarios.historico`) para que ese contacto se siga
    sugiriendo en el futuro (cierra el círculo con `usuarios_internos.listar_contactos_externos`)."""
    fallidos = []
    try:
        from src.db import correo as correo_db
        buzones = [b for b in correo_db.listar_correos(id_empresa) if b.get("estado") == "activo"]
    except Exception as e:
        logger.debug(f"_enviar_externos: no se pudo listar buzones: {e}")
        buzones = []
    if not buzones:
        logger.warning("_enviar_externos: sin buzón corporativo activo, %d destinatario(s) externo(s) "
                       "no recibieron la circular.", len(externos))
        return [d.get("email_externo") for d in externos if d.get("email_externo")]
    id_correo = buzones[0]["id_correo"]
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
                    modulo_contexto="circular")
            except Exception:
                pass
        else:
            fallidos.append(correo)
    return fallidos


# ─── Bandeja / lectura ────────────────────────────────────────────────────────

def listar_circulares(*, id_empresa=None, usuario_id=None) -> list[dict]:
    """Bandeja: circulares de la empresa (más recientes primero) + nº de confirmaciones.

    `usuario_id` (opcional) filtra a "mi bandeja": aparecen las circulares donde el usuario es
    destinatario registrado (Para/CC/Cco, incluido por reenvío), las que él mismo creó, y las
    LEGACY sin ningún destinatario registrado (difusión histórica, compatibilidad hacia atrás).
    Sin `usuario_id`, se mantiene el comportamiento histórico (todas las de la empresa,
    cualquier estado — lo usan los tests de aislamiento y herramientas administrativas).

    Con `usuario_id` (bandeja real de Recibidos/Enviados), SOLO se listan circulares PUBLICADAS
    y NO pospuestas (`pospuesto_hasta` NULL o ya vencido) — Borradores/Programadas/Papelera tienen
    sus propias funciones (`listar_borradores`/`listar_programadas`/`listar_papelera`) y Pospuestos
    la suya (`listar_pospuestos`), para no duplicar lo que ya aparece en "mi bandeja"."""
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            sql = (
                "SELECT c.id, c.titulo, c.creador_nombre, c.creado, c.estado, c.importante, "
                "  (SELECT COUNT(*) FROM com_circular_confirmaciones k WHERE k.id_circular=c.id) AS confirmaciones "
                "FROM com_circulares c WHERE c.id_empresa=%s")
            params = [emp]
            if usuario_id is not None:
                sql += (
                    " AND c.estado='PUBLICADA' "
                    "AND (c.pospuesto_hasta IS NULL OR c.pospuesto_hasta<=NOW()) AND ("
                    "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                    "AND d.id_entidad=c.id AND d.usuario_id=%s)"
                    " OR c.creador_id=%s"
                    " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                    "AND d2.id_entidad=c.id)"
                    ")")
                params += [ENTIDAD, usuario_id, str(usuario_id), ENTIDAD]
            sql += " ORDER BY c.creado DESC, c.id DESC"
            cur.execute(sql, tuple(params))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_circulares degradado: {e}")
        return []


# ─── Borradores / Papelera / Programados / Pospuestos / Importantes ──────────
# Simplificación deliberada y documentada: `estado`/`pospuesto_hasta`/`importante` son columnas
# ÚNICAS por circular (no por-destinatario) — a diferencia de un snooze/trash/star real de Gmail
# (que es siempre personal, por buzón), aquí "posponer"/"papelera"/"importante" son estados
# COMPARTIDOS por todos los que ven esa circular (igual que ya lo es `leido` a nivel de
# com_destinatarios, pero eso SÍ es por-usuario; estos 3 no lo son). Aceptable para esta primera
# versión real (ver informe de la tarea): "papelera" se restringe al CREADOR (retractar su propio
# mensaje), evitando que cualquier destinatario pueda ocultarlo para todos los demás.

def guardar_borrador(id_circular=None, *, titulo, cuerpo="", adjuntos=None, destinatarios=None,
                     usuario=None, id_empresa=None) -> dict:
    """Crea o (si se pasa `id_circular`) actualiza un BORRADOR. No exige destinatarios ni valida
    "Para" (un borrador puede quedar incompleto). Los destinatarios INTERNOS (usuario_id/
    centro_codigo, ya expandidos/filtrados por empresa) se guardan de verdad en
    `com_destinatarios` para poder reabrir el borrador con los chips ya rellenos; los externos
    (`email_externo`) NO se persisten entre sesiones (no hay tabla para ellos sin convertirlos en
    destinatario real) — limitación conocida, documentada también en el informe de la tarea."""
    titulo = (titulo or "").strip()
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            if id_circular:
                cur.execute("SELECT id_empresa, creador_id, estado FROM com_circulares WHERE id=%s",
                           (id_circular,))
                row = cur.fetchone()
                if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                    return {"ok": False, "error": "Borrador no encontrado."}
                if row[1] is not None and str(row[1]) != str(u.get("id")):
                    return {"ok": False, "error": "Este borrador pertenece a otro usuario."}
                cur.execute("UPDATE com_circulares SET titulo=%s, cuerpo=%s WHERE id=%s",
                           (titulo, cuerpo or "", id_circular))
                cid = id_circular
            else:
                cur.execute(
                    "INSERT INTO com_circulares (id_empresa, titulo, cuerpo, creador_id, "
                    "creador_nombre, estado) VALUES (%s,%s,%s,%s,%s,'BORRADOR')",
                    (emp, titulo, cuerpo or "", str(u.get("id")) if u.get("id") is not None else None,
                     u.get("nombre") or "—"))
                cid = cur.lastrowid
            if adjuntos:
                ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=cid, origen="EMISOR", cur=cur)
            if destinatarios is not None:
                from src.services.comunicacion_interna.usuarios_internos import (
                    expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
                usuario_entries, _externos = expandir_destinatarios(cur, emp, destinatarios)
                destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
                cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                           (ENTIDAD, cid))
                if destinatarios_validos:
                    insertar_destinatarios(cur, ENTIDAD, cid, destinatarios_validos)
            conn.commit()
        return {"ok": True, "id": cid}
    except Exception as e:
        logger.error(f"guardar_borrador(circular): {e}")
        return {"ok": False, "error": str(e)}


def listar_borradores(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_circulares "
                "WHERE id_empresa=%s AND estado='BORRADOR' AND creador_id=%s "
                "ORDER BY creado DESC, id DESC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_borradores: {e}")
        return []


def publicar_borrador(id_circular, *, destinatarios, titulo=None, cuerpo=None, usuario=None,
                      id_empresa=None) -> dict:
    """Publica de verdad un borrador: exige al menos un "Para" válido, inserta destinatarios reales
    (sustituyendo cualquier preliminar del borrador) y envía a los externos — el mismo camino que
    `crear_circular`, factorizado para no duplicarlo. `titulo`/`cuerpo` (opcionales) permiten
    guardar de paso una edición hecha tras reabrir el borrador, sin pasar antes por «Guardar
    borrador»."""
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado, titulo, cuerpo FROM com_circulares "
                       "WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                return {"ok": False, "error": "Borrador no encontrado."}
            if titulo is not None:
                cur.execute("UPDATE com_circulares SET titulo=%s, cuerpo=%s WHERE id=%s",
                           ((titulo or "").strip(), cuerpo or "", id_circular))
            from src.services.comunicacion_interna.usuarios_internos import (
                expandir_destinatarios, filtrar_destinatarios_de_empresa, insertar_destinatarios)
            usuario_entries, externos = expandir_destinatarios(cur, emp, destinatarios or [])
            destinatarios_validos = filtrar_destinatarios_de_empresa(cur, emp, usuario_entries)
            hay_para = (any((d.get("tipo") or "").upper() == "PARA" for d in destinatarios_validos)
                       or any((d.get("tipo") or "").upper() == "PARA" for d in externos))
            if not hay_para:
                return {"ok": False, "error": "Debes indicar al menos un destinatario en «Para»."}
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                       (ENTIDAD, id_circular))
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, id_circular, destinatarios_validos)
            cur.execute("UPDATE com_circulares SET estado='PUBLICADA', creado=NOW() WHERE id=%s",
                       (id_circular,))
            titulo_final = titulo if titulo is not None else row[3]
            cuerpo_final = cuerpo if cuerpo is not None else row[4]
            conn.commit()
    except Exception as e:
        logger.error(f"publicar_borrador: {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "id": id_circular}
    if externos:
        fallidos = _enviar_externos(titulo_final, cuerpo_final or "", externos, id_empresa=emp, usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def eliminar_borrador(id_circular, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_circulares WHERE id=%s",
                       (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "BORRADOR":
                return {"ok": False, "error": "Borrador no encontrado."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Este borrador pertenece a otro usuario."}
    except Exception as e:
        logger.error(f"eliminar_borrador: {e}")
        return {"ok": False, "error": str(e)}
    return {"ok": eliminar_circular(id_circular, id_empresa=id_empresa)}


def programar(id_circular_borrador=None, *, titulo=None, cuerpo=None, fecha_programada,
             destinatarios, usuario=None, id_empresa=None) -> dict:
    """Programa el envío: si `id_circular_borrador` se indica, convierte ESE borrador; si no, crea
    la fila directamente en estado PROGRAMADA. Los destinatarios INTERNOS se validan/insertan YA
    (solo se "disparan" visualmente al llegar la hora); los `email_externo` NO se soportan en envío
    programado todavía (se devuelven en `externos_no_programables`, nunca se pierden en silencio)."""
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
            if id_circular_borrador:
                cur.execute("SELECT id_empresa, estado FROM com_circulares WHERE id=%s",
                           (id_circular_borrador,))
                row = cur.fetchone()
                if not row or str(row[0]) != str(emp) or row[1] != "BORRADOR":
                    return {"ok": False, "error": "Borrador no encontrado."}
                cid = id_circular_borrador
                if titulo is not None:
                    cur.execute("UPDATE com_circulares SET titulo=%s, cuerpo=%s WHERE id=%s",
                               ((titulo or "").strip(), cuerpo or "", cid))
            else:
                titulo = (titulo or "").strip()
                if not titulo:
                    return {"ok": False, "error": "El título es obligatorio."}
                cur.execute(
                    "INSERT INTO com_circulares (id_empresa, titulo, cuerpo, creador_id, "
                    "creador_nombre, estado) VALUES (%s,%s,%s,%s,%s,'BORRADOR')",
                    (emp, titulo, cuerpo or "", str(u.get("id")) if u.get("id") is not None else None,
                     u.get("nombre") or "—"))
                cid = cur.lastrowid
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                       (ENTIDAD, cid))
            insertar_destinatarios(cur, ENTIDAD, cid, destinatarios_validos)
            cur.execute("UPDATE com_circulares SET estado='PROGRAMADA', fecha_programada=%s WHERE id=%s",
                       (fecha_programada, cid))
            conn.commit()
        resultado = {"ok": True, "id": cid}
        if externos:
            resultado["externos_no_programables"] = [d.get("email_externo") for d in externos
                                                      if d.get("email_externo")]
        return resultado
    except Exception as e:
        logger.error(f"programar(circular): {e}")
        return {"ok": False, "error": str(e)}


def cancelar_programacion(id_circular, *, usuario=None, id_empresa=None) -> dict:
    """Revierte una circular PROGRAMADA a BORRADOR (nunca la publica ni la borra)."""
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, estado FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[1] != "PROGRAMADA":
                return {"ok": False, "error": "No hay ninguna programación que cancelar."}
            cur.execute("UPDATE com_circulares SET estado='BORRADOR', fecha_programada=NULL WHERE id=%s",
                       (id_circular,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"cancelar_programacion(circular): {e}")
        return {"ok": False, "error": str(e)}


def listar_programadas(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado, fecha_programada FROM com_circulares "
                "WHERE id_empresa=%s AND estado='PROGRAMADA' AND creador_id=%s "
                "ORDER BY fecha_programada ASC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_programadas: {e}")
        return []


def disparar_programadas_vencidas(id_empresa=None) -> str:
    """Job del scheduler (`com_programados_envio`): publica toda circular PROGRAMADA cuya
    `fecha_programada` ya venció — el mismo efecto que si `crear_circular` se hubiera llamado en
    ese instante (los destinatarios ya se insertaron al programar, ver `programar()`)."""
    emp = _empresa(id_empresa)
    n = 0
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM com_circulares WHERE id_empresa=%s AND estado='PROGRAMADA' "
                       "AND fecha_programada IS NOT NULL AND fecha_programada<=NOW()", (emp,))
            ids = [r[0] for r in cur.fetchall()]
            for cid in ids:
                cur.execute("UPDATE com_circulares SET estado='PUBLICADA', creado=NOW() WHERE id=%s",
                           (cid,))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error(f"disparar_programadas_vencidas(circular): {e}")
        return f"error={e}"
    return f"circulares_disparadas={n}"


def mover_papelera(id_circular, *, usuario=None, id_empresa=None) -> dict:
    """Papelera LOCAL (soft, compartida — ver nota de diseño arriba): solo el CREADOR puede
    retractar su propia circular PUBLICADA."""
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_circulares WHERE id=%s",
                       (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp):
                return {"ok": False, "error": "Circular no encontrada."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Solo el creador puede mover esta circular a la papelera."}
            if row[2] != "PUBLICADA":
                return {"ok": False, "error": "Solo se puede mover a la papelera una circular publicada."}
            cur.execute("UPDATE com_circulares SET estado='PAPELERA' WHERE id=%s", (id_circular,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"mover_papelera(circular): {e}")
        return {"ok": False, "error": str(e)}


def restaurar_de_papelera(id_circular, *, usuario=None, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, creador_id, estado FROM com_circulares WHERE id=%s",
                       (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[2] != "PAPELERA":
                return {"ok": False, "error": "No está en la papelera."}
            if row[1] is not None and str(row[1]) != str(u.get("id")):
                return {"ok": False, "error": "Solo el creador puede restaurar esta circular."}
            cur.execute("UPDATE com_circulares SET estado='PUBLICADA' WHERE id=%s", (id_circular,))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"restaurar_de_papelera(circular): {e}")
        return {"ok": False, "error": str(e)}


def listar_papelera(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_circulares "
                "WHERE id_empresa=%s AND estado='PAPELERA' AND creador_id=%s "
                "ORDER BY creado DESC, id DESC", (emp, str(usuario_id)))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_papelera: {e}")
        return []


def marcar_importante(id_circular, valor: bool, *, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp):
                return {"ok": False, "error": "Circular no encontrada."}
            cur.execute("UPDATE com_circulares SET importante=%s WHERE id=%s",
                       (1 if valor else 0, id_circular))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"marcar_importante(circular): {e}")
        return {"ok": False, "error": str(e)}


def listar_importantes(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado FROM com_circulares c "
                "WHERE c.id_empresa=%s AND c.importante=1 AND c.estado='PUBLICADA' AND ("
                "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                "AND d.id_entidad=c.id AND d.usuario_id=%s)"
                " OR c.creador_id=%s"
                " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                "AND d2.id_entidad=c.id)) ORDER BY c.creado DESC, c.id DESC",
                (emp, ENTIDAD, usuario_id, str(usuario_id), ENTIDAD))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_importantes: {e}")
        return []


def posponer(id_circular, hasta, *, id_empresa=None) -> dict:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, estado FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row or str(row[0]) != str(emp) or row[1] != "PUBLICADA":
                return {"ok": False, "error": "Circular no encontrada o no publicada."}
            cur.execute("UPDATE com_circulares SET pospuesto_hasta=%s WHERE id=%s",
                       (hasta, id_circular))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"posponer(circular): {e}")
        return {"ok": False, "error": str(e)}


def listar_pospuestos(usuario_id, *, id_empresa=None) -> list[dict]:
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, creador_nombre, creado, estado, pospuesto_hasta FROM com_circulares c "
                "WHERE c.id_empresa=%s AND c.estado='PUBLICADA' AND c.pospuesto_hasta IS NOT NULL "
                "AND c.pospuesto_hasta>NOW() AND ("
                "EXISTS (SELECT 1 FROM com_destinatarios d WHERE d.tipo_entidad=%s "
                "AND d.id_entidad=c.id AND d.usuario_id=%s)"
                " OR c.creador_id=%s"
                " OR NOT EXISTS (SELECT 1 FROM com_destinatarios d2 WHERE d2.tipo_entidad=%s "
                "AND d2.id_entidad=c.id)) ORDER BY c.pospuesto_hasta ASC",
                (emp, ENTIDAD, usuario_id, str(usuario_id), ENTIDAD))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"listar_pospuestos: {e}")
        return []


def obtener_circular(id_circular) -> dict | None:
    """Circular completa: cabecera + adjuntos del emisor + confirmaciones (con comentario y adjuntos)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM com_circulares WHERE id=%s", (id_circular,))
            filas = _rows(cur)
            if not filas:
                return None
            circ = filas[0]
            cur.execute(
                "SELECT id, usuario_nombre, id_centro, comentario, creado FROM com_circular_confirmaciones "
                "WHERE id_circular=%s ORDER BY creado ASC", (id_circular,))
            confs = _rows(cur)
        circ["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_circular, origen="EMISOR", id_respuesta=None)
        for cf in confs:
            cf["adjuntos"] = ADJ.listar_adjuntos(ENTIDAD, id_circular, origen="RESPUESTA",
                                                 id_respuesta=cf["id"])
        circ["confirmaciones"] = confs
        circ["destinatarios"] = _destinatarios_de(id_circular)
        return circ
    except Exception as e:
        logger.error(f"obtener_circular: {e}")
        return None


def _destinatarios_de(id_circular) -> list[dict]:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT usuario_id, usuario_nombre, tipo, reenviado_por, leido, creado "
                "FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s ORDER BY creado ASC",
                (ENTIDAD, id_circular))
            return _rows(cur)
    except Exception as e:
        logger.debug(f"_destinatarios_de(circular): {e}")
        return []


# ─── Reenvío ───────────────────────────────────────────────────────────────────

def reenviar_circular(id_circular, destinatarios, *, usuario=None, id_empresa=None) -> dict:
    """Reenvía una circular EXISTENTE a más destinatarios (no duplica la fila de la circular: solo
    añade destinatarios apuntando al mismo `id_circular`, con `reenviado_por`). Acepta las mismas 3
    formas que `crear_circular` (`usuario_id`/`centro_codigo` con fan-out/`email_externo`). Aislamiento
    estricto: la circular debe existir y, si se indica `id_empresa`, debe coincidir con la suya;
    además cada destinatario interno (original o expandido desde un centro) debe pertenecer a la
    MISMA empresa que la circular (nunca cruza empresas)."""
    emp = _empresa(id_empresa)
    u = _usuario(usuario)
    destinatarios_validos: list[dict] = []
    externos: list[dict] = []
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, titulo, cuerpo FROM com_circulares WHERE id=%s",
                       (id_circular,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Circular no encontrada."}
            id_emp_circular, titulo, cuerpo = row[0], row[1], row[2]
            if emp and str(id_emp_circular) != str(emp):
                return {"ok": False, "error": "No puedes reenviar una circular de otra empresa."}
            from src.services.comunicacion_interna.usuarios_internos import (
                expandir_destinatarios, insertar_destinatarios)
            usuario_entries, externos = expandir_destinatarios(cur, id_emp_circular, destinatarios)
            ids = [d["usuario_id"] for d in usuario_entries]
            if ids:
                marcadores = ",".join(["%s"] * len(ids))
                cur.execute(
                    f"SELECT id FROM usuarios WHERE id IN ({marcadores}) AND id_empresa=%s AND activo=1",
                    tuple(ids) + (id_emp_circular,))
                validos = {r[0] for r in cur.fetchall()}
                destinatarios_validos = [d for d in usuario_entries if d["usuario_id"] in validos]
            if not destinatarios_validos and not externos:
                return {"ok": False, "error": "Indica al menos un destinatario para reenviar."}
            if destinatarios_validos:
                insertar_destinatarios(cur, ENTIDAD, id_circular, destinatarios_validos,
                                       reenviado_por=u.get("nombre") or "—")
            conn.commit()
    except Exception as e:
        logger.error(f"reenviar_circular: {e}")
        return {"ok": False, "error": str(e)}
    resultado = {"ok": True, "n": len(destinatarios_validos)}
    if externos:
        fallidos = _enviar_externos(titulo, cuerpo or "", externos, id_empresa=id_emp_circular,
                                    usuario=u)
        if fallidos:
            resultado["externos_fallidos"] = fallidos
    return resultado


def confirmar_lectura(id_circular, *, usuario_nombre, password, comentario="", adjuntos=None,
                      id_empresa=None) -> dict:
    """Confirma la lectura verificando perfil+contraseña. Registra comentario + adjuntos de respuesta.

    La validación de credenciales se acota SIEMPRE a la empresa EXPLÍCITA de la circular (nunca a
    la empresa ambiente del proceso/hilo) — mismo criterio que el fix de `online_orders_service`
    (ambiente ≠ contexto real): sin esto, un terminal compartido confirmando una circular de una
    empresa B mientras el contexto ambiente sigue en la empresa A (p. ej. tras un cambio de
    empresa en curso, o cualquier proceso sin sesión de escritorio) autenticaría contra la
    empresa equivocada — o fallaría, si la ambiente ni siquiera coincide con ninguna real."""
    emp = _empresa(id_empresa)
    from src.db.empresa import contexto_tenant
    from src.db.usuario import validar_login_empleado
    with contexto_tenant(emp):
        u = validar_login_empleado(usuario_nombre or "", password or "")
    if not u:
        return {"ok": False, "error": "Perfil o contraseña incorrectos."}
    # Aislamiento: el perfil debe pertenecer a la empresa de la circular.
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Circular no encontrada."}
            if u.get("id_empresa") and emp and str(u["id_empresa"]) != str(emp):
                return {"ok": False, "error": "El perfil no pertenece a esta empresa."}
            cur.execute(
                "INSERT INTO com_circular_confirmaciones "
                "(id_circular, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_circular, str(u.get("id")), u.get("nombre"), u.get("centro_codigo"), comentario or ""))
            conf_id = cur.lastrowid
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_circular,
                               origen="RESPUESTA", id_respuesta=conf_id, cur=cur)
            conn.commit()
        return {"ok": True, "id": conf_id, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"confirmar_lectura: {e}")
        return {"ok": False, "error": str(e)}


def responder_circular(id_circular, *, usuario, comentario="", adjuntos=None, id_empresa=None) -> dict:
    """Responde a una circular reutilizando la identidad YA AUTENTICADA del llamador (sesión de
    escritorio ya logueada / token JWT móvil) — SIN re-pedir contraseña. Mismo efecto exacto y misma
    tabla (`com_circular_confirmaciones`) que `confirmar_lectura`, del que es un PARALELO (Strangler
    Pattern): `confirmar_lectura` sigue existiendo tal cual para el escenario de terminal compartido
    (reautenticación perfil+contraseña); esta función es la adecuada cuando quien llama YA demostró
    su identidad (no tiene sentido re-pedirle la contraseña para un comentario rápido). Aislamiento
    igual que `reenviar_circular`: compara la empresa REAL de la circular (consultada aquí, nunca la
    que diga el llamador) contra `id_empresa` — nunca se confía en un `id_empresa` ajeno."""
    u = _usuario(usuario)
    emp = _empresa(id_empresa)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM com_circulares WHERE id=%s", (id_circular,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "Circular no encontrada."}
            if emp and str(row[0]) != str(emp):
                return {"ok": False, "error": "No puedes responder a una circular de otra empresa."}
            cur.execute(
                "INSERT INTO com_circular_confirmaciones "
                "(id_circular, usuario_id, usuario_nombre, id_centro, comentario) VALUES (%s,%s,%s,%s,%s)",
                (id_circular, str(u.get("id")) if u.get("id") is not None else None, u.get("nombre"),
                 u.get("centro_codigo"), comentario or ""))
            conf_id = cur.lastrowid
            ADJ.guardar_varios(adjuntos, tipo_entidad=ENTIDAD, id_entidad=id_circular,
                               origen="RESPUESTA", id_respuesta=conf_id, cur=cur)
            conn.commit()
        return {"ok": True, "id": conf_id, "usuario": u.get("nombre")}
    except Exception as e:
        logger.error(f"responder_circular: {e}")
        return {"ok": False, "error": str(e)}


# ─── Estado de lectura (bandeja unificada de Correo) ──────────────────────────

def marcar_leido_circular(id_circular, usuario_id) -> bool:
    """Marca `com_destinatarios.leido=1` para la fila de ESTE usuario en esta circular (usado por
    la bandeja unificada de `gui.correo_corporativo` tras abrir el visor). Si el usuario no tiene
    fila de destinatario registrada (difusión legacy o es el propio creador), el UPDATE
    simplemente no afecta a ninguna fila — no se inventa una relación de destinatario que no
    existía. Deliberadamente tenant-unaware (una sola sentencia UPDATE): ya viene acotado por
    usuario_id+id_entidad, ambos ya validados antes de llegar aquí."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE com_destinatarios SET leido=1 WHERE tipo_entidad=%s AND id_entidad=%s "
                "AND usuario_id=%s", (ENTIDAD, id_circular, usuario_id))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"marcar_leido_circular: {e}")
        return False


def eliminar_circular(id_circular, *, id_empresa=None) -> bool:
    """Elimina una circular y sus confirmaciones/adjuntos (registro; los ficheros quedan en disco)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM com_circular_confirmaciones WHERE id_circular=%s", (id_circular,))
            cur.execute("DELETE FROM com_adjuntos WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_circular))
            cur.execute("DELETE FROM com_destinatarios WHERE tipo_entidad=%s AND id_entidad=%s",
                        (ENTIDAD, id_circular))
            cur.execute("DELETE FROM com_circulares WHERE id=%s", (id_circular,))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"eliminar_circular: {e}")
        return False
