"""
Bandeja de entrada omnicanal (Social CRM) — sincroniza conversaciones/mensajes reales desde los
clientes de plataforma (`plataformas/`), persiste en `redes_sociales_conversaciones`/`_mensajes`,
permite responder (dispatch al cliente real de la plataforma) y vincula un hilo a un cliente real
del ERP (`db.clientes`) para componer el "cliente 360".

Honestidad de alcance por plataforma (cada una expone un modelo de API distinto, no es un hueco de
implementación sino una limitación real de la plataforma — ver `plataformas/*.py`):
  • instagram/facebook: sincronización completa de conversaciones + mensajes (Graph API real).
  • youtube/tiktok: no hay DMs; se sincronizan HILOS DE COMENTARIOS. Por defecto se auto-descubren
    los vídeos PROPIOS ya publicados desde este módulo (`calendario.listar_publicaciones`,
    `estado='publicada'`) y se sincronizan los comentarios de todos ellos — sin que el
    superadministrador tenga que pegar manualmente un ID de vídeo cada vez (fricción cero,
    petición explícita). `id_externo_video` sigue aceptándose como override puntual para un vídeo
    publicado fuera de Smart Manager antes de conectar la cuenta.
  • x: DMs requieren una conversación ya conocida; las menciones nuevas se sincronizan por
    usuario (`id_externo_usuario` obligatorio, la cuenta propia).
"""

import logging

from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.plataformas import cliente_para

logger = logging.getLogger("redes_sociales.inbox")


class InboxError(Exception):
    pass


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _persistir_conversacion(id_empresa, id_cuenta, plataforma, tipo, externo_id, *,
                            remitente_nombre=None, remitente_handle=None,
                            remitente_externo_id=None, cur=None) -> int:
    cur.execute(
        "SELECT id FROM redes_sociales_conversaciones WHERE id_empresa=%s AND id_cuenta=%s "
        "AND externo_id=%s", (id_empresa, id_cuenta, externo_id))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE redes_sociales_conversaciones SET fecha_ultimo_mensaje=NOW() "
                   "WHERE id=%s", (row[0],))
        return row[0]
    cur.execute(
        "INSERT INTO redes_sociales_conversaciones (id_empresa, id_cuenta, plataforma, tipo, "
        "externo_id, remitente_nombre, remitente_handle, remitente_externo_id, "
        "fecha_ultimo_mensaje) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
        (id_empresa, id_cuenta, plataforma, tipo, externo_id, remitente_nombre, remitente_handle,
         remitente_externo_id))
    return cur.lastrowid


def _persistir_mensaje(id_empresa, id_conversacion, *, direccion="entrante", autor=None,
                       cuerpo=None, externo_id=None, generado_por_ia=False, cur=None) -> int | None:
    if externo_id:
        cur.execute("SELECT id FROM redes_sociales_mensajes WHERE id_conversacion=%s AND "
                   "externo_id=%s", (id_conversacion, externo_id))
        if cur.fetchone():
            return None  # ya sincronizado, evita duplicados en re-sync
    cur.execute(
        "INSERT INTO redes_sociales_mensajes (id_empresa, id_conversacion, direccion, autor, "
        "cuerpo, externo_id, generado_por_ia) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (id_empresa, id_conversacion, direccion, autor, cuerpo, externo_id, bool(generado_por_ia)))
    return cur.lastrowid


def _videos_propios(id_cuenta, plataforma, id_empresa, *, cur) -> list:
    """IDs externos de los vídeos YA publicados desde este módulo para esta cuenta (origen de
    `calendario.publicar_ahora`) — fuente de auto-descubrimiento para sincronizar comentarios sin
    que el superadministrador tenga que pegar manualmente un ID de vídeo (YouTube/TikTok, ambas
    plataformas de comentarios-sobre-vídeo sin concepto de "bandeja" nativo)."""
    cur.execute(
        "SELECT externo_id FROM redes_sociales_publicaciones WHERE id_cuenta=%s AND "
        "plataforma=%s AND estado='publicada' AND externo_id IS NOT NULL ORDER BY "
        "fecha_publicada DESC LIMIT 50", (id_cuenta, plataforma))
    return [r[0] for r in cur.fetchall()]


def sincronizar(id_cuenta, *, id_externo_video=None, id_externo_usuario=None,
               id_empresa=None) -> dict:
    """Sincroniza conversaciones/mensajes nuevos de una cuenta conectada. Devuelve
    `{"ok": True, "nuevas_conversaciones": n, "nuevos_mensajes": n}` o un degradado honesto."""
    id_empresa = _emp(id_empresa)
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == id_cuenta), None)
    if not cuenta:
        raise InboxError("Cuenta no encontrada.")
    plataforma = cuenta["plataforma"]
    cli = cliente_para(plataforma)
    if cli is None:
        return {"ok": False, "estado": "plataforma_no_soportada"}

    n_conv = n_msg = 0
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            if plataforma in ("instagram", "facebook"):
                canal = "instagram" if plataforma == "instagram" else "messenger"
                r = cli.listar_conversaciones(id_cuenta, cuenta["id_externo"],
                                              plataforma_canal=canal, id_empresa=id_empresa)
                if not r.get("ok"):
                    return r
                for conv in r.get("conversaciones", []):
                    participantes = (conv.get("participants") or {}).get("data", [])
                    otro = next((p for p in participantes
                                if p.get("id") != cuenta["id_externo"]), {})
                    id_conv = _persistir_conversacion(
                        id_empresa, id_cuenta, plataforma, "dm", conv["id"],
                        remitente_nombre=otro.get("name"),
                        remitente_externo_id=otro.get("id"), cur=cur)
                    n_conv += 1
                    rm = cli.listar_mensajes(id_cuenta, conv["id"], id_empresa=id_empresa)
                    if rm.get("ok"):
                        for m in rm.get("mensajes", []):
                            desde = (m.get("from") or {}).get("id")
                            direccion = "saliente" if desde == cuenta["id_externo"] else "entrante"
                            if _persistir_mensaje(
                                    id_empresa, id_conv, direccion=direccion,
                                    autor=(m.get("from") or {}).get("name"),
                                    cuerpo=m.get("message"), externo_id=m.get("id"),
                                    cur=cur) is not None:
                                n_msg += 1
            elif plataforma == "youtube":
                videos = [id_externo_video] if id_externo_video else _videos_propios(
                    id_cuenta, plataforma, id_empresa, cur=cur)
                if not videos:
                    return {"ok": False, "estado": "sin_videos_propios_conocidos"}
                for vid in videos:
                    r = cli.listar_comentarios(id_cuenta, vid, id_empresa=id_empresa)
                    if not r.get("ok"):
                        continue
                    for hilo in r.get("comentarios", []):
                        top = (hilo.get("snippet") or {}).get("topLevelComment", {})
                        sn = top.get("snippet", {})
                        id_conv = _persistir_conversacion(
                            id_empresa, id_cuenta, plataforma, "comentario", hilo["id"],
                            remitente_nombre=sn.get("authorDisplayName"), cur=cur)
                        n_conv += 1
                        if _persistir_mensaje(
                                id_empresa, id_conv, direccion="entrante",
                                autor=sn.get("authorDisplayName"), cuerpo=sn.get("textOriginal"),
                                externo_id=top.get("id"), cur=cur) is not None:
                            n_msg += 1
            elif plataforma == "tiktok":
                videos = [id_externo_video] if id_externo_video else _videos_propios(
                    id_cuenta, plataforma, id_empresa, cur=cur)
                if not videos:
                    return {"ok": False, "estado": "sin_videos_propios_conocidos"}
                for vid in videos:
                    r = cli.listar_comentarios(id_cuenta, vid, id_empresa=id_empresa)
                    if not r.get("ok"):
                        continue
                    for c in r.get("comentarios", []):
                        cid = c.get("comment_id") or c.get("id")
                        texto_c = c.get("text") or c.get("comment_text")
                        autor_c = (c.get("user") or {}).get("display_name") or c.get("nickname")
                        id_conv = _persistir_conversacion(
                            id_empresa, id_cuenta, plataforma, "comentario", str(cid),
                            remitente_nombre=autor_c, cur=cur)
                        n_conv += 1
                        if _persistir_mensaje(
                                id_empresa, id_conv, direccion="entrante", autor=autor_c,
                                cuerpo=texto_c, externo_id=str(cid), cur=cur) is not None:
                            n_msg += 1
            elif plataforma == "x":
                if not id_externo_usuario:
                    return {"ok": False, "estado": "falta_id_externo_usuario"}
                r = cli.listar_menciones(id_cuenta, id_externo_usuario, id_empresa=id_empresa)
                if not r.get("ok"):
                    return r
                for tw in r.get("menciones", []):
                    id_conv = _persistir_conversacion(
                        id_empresa, id_cuenta, plataforma, "mencion", tw["id"],
                        remitente_externo_id=tw.get("author_id"), cur=cur)
                    n_conv += 1
                    if _persistir_mensaje(
                            id_empresa, id_conv, direccion="entrante",
                            cuerpo=tw.get("text"), externo_id=tw["id"], cur=cur) is not None:
                        n_msg += 1
            else:
                return {"ok": False, "estado": "no_disponible_en_la_plataforma"}
    except Exception as e:
        logger.error("sincronizar(%s): %s", id_cuenta, e)
        return {"ok": False, "estado": "error", "detalle": str(e)}

    if n_msg:
        try:
            from src.services import eventos as _EV
            _EV.publicar("REDES_SOCIALES_MENSAJES_RECIBIDOS", id_empresa=id_empresa,
                         origen=f"redes_sociales:{plataforma}", ref_entidad="redes_sociales_cuenta",
                         ref_id=id_cuenta, payload={"nuevos_mensajes": n_msg})
        except Exception:
            pass
        try:
            from src.services.redes_sociales import reputacion as _reputacion
            _reputacion.evaluar_mensajes_nuevos(id_empresa=id_empresa)
        except Exception as e:
            logger.debug("evaluar_mensajes_nuevos tras sync: %s", e)
    return {"ok": True, "nuevas_conversaciones": n_conv, "nuevos_mensajes": n_msg}


def ingerir_webhook_meta(payload, *, id_empresa=None) -> dict:
    """Ingesta en tiempo real desde el webhook de Meta (`api/routers/redes_sociales_webhooks.py`,
    firma ya verificada ahí) — complementa a `sincronizar` (sondeo manual): Meta recomienda
    suscripción a webhooks como mecanismo PRINCIPAL para mensajería/comentarios en producción.
    Soporta `entry[].messaging[]` (DMs, Messenger/Instagram) y `entry[].changes[]` con
    `field="comments"` (comentarios de Instagram). Estructura real documentada por Meta; cualquier
    otro campo se ignora (no se lanza, para no hacer fallar la entrega del webhook)."""
    id_empresa = _emp(id_empresa)
    n_conv = n_msg = 0
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            for entry in (payload or {}).get("entry", []):
                id_pagina = entry.get("id")
                cur.execute("SELECT id, plataforma FROM redes_sociales_cuentas WHERE "
                           "id_externo=%s AND estado='conectada' LIMIT 1", (id_pagina,))
                fila = cur.fetchone()
                if not fila:
                    continue
                id_cuenta, plataforma = fila
                for m in entry.get("messaging", []):
                    externo_remitente = (m.get("sender") or {}).get("id")
                    if externo_remitente == id_pagina:
                        continue  # eco de nuestro propio mensaje saliente
                    id_conv = _persistir_conversacion(
                        id_empresa, id_cuenta, plataforma, "dm",
                        f"dm_{externo_remitente}", remitente_externo_id=externo_remitente, cur=cur)
                    n_conv += 1
                    texto = (m.get("message") or {}).get("text")
                    mid = (m.get("message") or {}).get("mid")
                    if _persistir_mensaje(id_empresa, id_conv, direccion="entrante",
                                          cuerpo=texto, externo_id=mid, cur=cur) is not None:
                        n_msg += 1
                for ch in entry.get("changes", []):
                    if ch.get("field") != "comments":
                        continue
                    val = ch.get("value") or {}
                    id_conv = _persistir_conversacion(
                        id_empresa, id_cuenta, plataforma, "comentario", val.get("id"),
                        remitente_externo_id=(val.get("from") or {}).get("id"),
                        remitente_nombre=(val.get("from") or {}).get("username"), cur=cur)
                    n_conv += 1
                    if _persistir_mensaje(id_empresa, id_conv, direccion="entrante",
                                          cuerpo=val.get("text"), externo_id=val.get("id"),
                                          cur=cur) is not None:
                        n_msg += 1
    except Exception as e:
        logger.error("ingerir_webhook_meta: %s", e)
        return {"ok": False, "error": "error_interno"}

    if n_msg:
        try:
            from src.services.redes_sociales import reputacion as _reputacion
            _reputacion.evaluar_mensajes_nuevos(id_empresa=id_empresa)
        except Exception as e:
            logger.debug("evaluar_mensajes_nuevos tras webhook: %s", e)
    return {"ok": True, "nuevas_conversaciones": n_conv, "nuevos_mensajes": n_msg}


def listar_conversaciones(*, estado=None, id_cliente=None, id_empresa=None, limite=200) -> list:
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if id_cliente is not None:
        filtros.append("id_cliente=%s"); params.append(id_cliente)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM redes_sociales_conversaciones WHERE " + " AND ".join(filtros) +
                " ORDER BY FIELD(prioridad,'urgente','alta','media','baja'), "
                "fecha_ultimo_mensaje DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_conversaciones: %s", e)
        return []


def listar_mensajes(id_conversacion, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM redes_sociales_mensajes WHERE id_conversacion=%s AND "
                "id_empresa=%s ORDER BY fecha ASC, id ASC", (id_conversacion, id_empresa))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_mensajes(%s): %s", id_conversacion, e)
        return []


def responder(id_conversacion, texto, *, autor=None, generado_por_ia=False, id_empresa=None) -> dict:
    """Responde un hilo: llama al cliente real de la plataforma y, si tiene éxito, persiste el
    mensaje saliente y marca la conversación como `respondida`."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM redes_sociales_conversaciones WHERE id=%s AND "
                       "id_empresa=%s", (id_conversacion, id_empresa))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            conv = dict(zip(cols, row)) if row else None
    except Exception as e:
        logger.error("responder: lectura conversación %s: %s", id_conversacion, e)
        conv = None
    if not conv:
        raise InboxError("Conversación no encontrada.")

    cli = cliente_para(conv["plataforma"])
    if cli is None:
        return {"ok": False, "estado": "plataforma_no_soportada"}
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == conv["id_cuenta"]), None)

    if conv["tipo"] == "dm" and conv["plataforma"] in ("instagram", "facebook"):
        r = cli.enviar_mensaje(conv["id_cuenta"], cuenta["id_externo"],
                               conv["remitente_externo_id"], texto, id_empresa=id_empresa)
    elif conv["tipo"] == "dm" and conv["plataforma"] == "x":
        r = cli.enviar_mensaje(conv["id_cuenta"], conv["remitente_externo_id"], texto,
                               id_empresa=id_empresa)
    elif conv["tipo"] in ("comentario", "mencion"):
        r = cli.responder_comentario(conv["id_cuenta"], conv["externo_id"], texto,
                                     id_empresa=id_empresa)
    else:
        r = {"ok": False, "estado": "no_disponible_en_la_plataforma"}
    if not r.get("ok"):
        return r

    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            _persistir_mensaje(id_empresa, id_conversacion, direccion="saliente", autor=autor,
                               cuerpo=texto, externo_id=r.get("id_externo"),
                               generado_por_ia=generado_por_ia, cur=cur)
            cur.execute("UPDATE redes_sociales_conversaciones SET estado='respondida', "
                       "fecha_ultimo_mensaje=NOW() WHERE id=%s", (id_conversacion,))
    except Exception as e:
        logger.error("responder: persistencia %s: %s", id_conversacion, e)
    return {"ok": True}


def vincular_cliente(id_conversacion, id_cliente, id_empresa=None) -> dict:
    """Enlaza manualmente un hilo con un cliente real del ERP (`db.clientes`) — no existe ningún
    identificador universal que una un handle/remitente social con una ficha de cliente, así que
    el vínculo lo confirma un humano desde la bandeja (autocompletado por nombre/teléfono/email
    si coincide, pero SIEMPRE con confirmación, nunca automático y silencioso)."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE redes_sociales_conversaciones SET id_cliente=%s WHERE id=%s "
                       "AND id_empresa=%s", (id_cliente, id_conversacion, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("vincular_cliente(%s): %s", id_conversacion, e)
        return {"ok": False, "error": "error_interno"}


def cliente_360(id_conversacion, id_empresa=None) -> dict:
    """Compone la vista 360: ficha de cliente ERP (si está vinculado) + sus facturas recientes.
    Nueva composición (no existía ninguna función de 'cliente 360' en el repo, ver auditoría) a
    partir de piezas reales ya existentes: `db.clientes.obtener_cliente` +
    `db.facturas_cliente.listar_facturas`."""
    id_empresa = _emp(id_empresa)
    conv = next((c for c in listar_conversaciones(id_empresa=id_empresa, limite=100000)
                if c["id"] == id_conversacion), None)
    if not conv or not conv.get("id_cliente"):
        return {"ok": True, "vinculado": False, "conversacion": conv}
    try:
        from src.db.clientes import obtener_cliente
        cliente = obtener_cliente(conv["id_cliente"])
    except Exception as e:
        logger.debug("cliente_360: obtener_cliente: %s", e)
        cliente = None
    facturas = []
    try:
        from src.db.facturas_cliente import listar_facturas
        facturas = listar_facturas(id_empresa, conv["id_cliente"], None, 20) or []
    except Exception as e:
        logger.debug("cliente_360: listar_facturas: %s", e)
    return {"ok": True, "vinculado": True, "conversacion": conv, "cliente": cliente,
           "facturas_recientes": facturas}
