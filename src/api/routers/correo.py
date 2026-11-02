"""
Router /correo — exposición REST (cero lógica de negocio nueva) del Correo Corporativo de
escritorio: bandeja unificada (Gmail real, solo lectura, + circulares/encuestas internas), detalle,
creación con destinatarios Para/CC/Cco (interno/centro/externo), reenvío, respuesta AUTENTICADA (sin
contraseña, reutiliza la identidad del token), autocompletado de destinatarios, marcado de leído y
las 5 carpetas reales (Borradores/Programados/Papelera/Pospuestos/Importantes).

Consume EXCLUSIVAMENTE los servicios ya existentes — `src.db.correo` (buzones/Gmail sincronizado) y
`src.services.comunicacion_interna.{circulares,encuestas,usuarios_internos}` (motor de circulares/
encuestas, aislamiento multiempresa ya certificado en `tests/integration/test_circulares_
destinatarios.py`) — sin tocar ni duplicar ninguna regla de negocio ni de aislamiento: este módulo
solo normaliza/combina lo que esos servicios ya devuelven, igual que `gui/correo_corporativo.py::
_cargar_bandeja_unificada()` hace en escritorio (misma fusión, mismo criterio de orden), y las
acciones de carpeta son envoltorios finos de `circulares.py`/`encuestas.py`/`db/correo.py`, mismo
conjunto de acciones que `gui/correo_corporativo.py::_fila_acciones_carpeta()`.

Sin permiso RBAC dedicado todavía (no existe ningún `correo.*`/`circulares.*` en el catálogo de
`seguridad/catalogo.py`): exige solo autenticación, igual que `/losses`/`/location`/`/articles`.

Tenant/identidad: `id_empresa` sale SIEMPRE de `g.ctx["id_empresa"]` (token) y el usuario actual de
`g.ctx["usuario"]` — nunca de un parámetro de la petición (misma regla que documenta
`api/security.py` y sigue cualquier otro router)."""

import datetime

from src.api.security import requiere_auth


def _parse_fecha(valor):
    """Parsea una fecha/hora ISO (`YYYY-MM-DDTHH:MM[:SS]` o con espacio) enviada por el cliente
    móvil. Nunca lanza con un valor vacío/None (devuelve None); una cadena inválida propaga
    ValueError, que el endpoint convierte en 400 (nunca se guarda basura silenciosamente)."""
    if not valor:
        return None
    if isinstance(valor, datetime.datetime):
        return valor
    return datetime.datetime.fromisoformat(str(valor).strip())


def _normalizar_folder(tipo, item, *, campo_fecha="creado", leido=True):
    return {
        "tipo": tipo, "id": item.get("id"),
        "remitente_o_emisor": item.get("creador_nombre") or item.get("remitente") or "—",
        "asunto_o_titulo": item.get("titulo") or item.get("asunto") or "—",
        "fecha": item.get(campo_fecha),
        "leido": leido,
    }


def _leido_ids(tipo_entidad: str, ids: list, usuario_id) -> set:
    """IDs de `ids` que `usuario_id` ya marcó leídos (`com_destinatarios.leido=1`). Lectura directa
    de solo consulta — mismo criterio que `gui/correo_corporativo.py::_leido_ids` (la escritura
    sigue viviendo en la capa de servicio, `circulares.marcar_leido_circular`/
    `encuestas.marcar_leido_encuesta`)."""
    ids = [i for i in (ids or []) if i is not None]
    if not ids or usuario_id is None:
        return set()
    try:
        from src.db.conexion import obtener_conexion
        marcadores = ",".join(["%s"] * len(ids))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id_entidad FROM com_destinatarios WHERE tipo_entidad=%s AND usuario_id=%s "
                f"AND id_entidad IN ({marcadores}) AND leido=1",
                (tipo_entidad, usuario_id, *ids))
            return {r[0] for r in cur.fetchall()}
    except Exception:
        return set()


def _bandeja_unificada(id_empresa, usuario_id) -> list[dict]:
    """Fusiona Gmail (buzones Google conectados de la empresa) + circulares + encuestas dirigidas al
    usuario actual en una sola lista normalizada `{tipo, id, remitente_o_emisor, asunto_o_titulo,
    fecha, leido}`, ordenada de más reciente a más antigua — mismo criterio exacto que
    `gui/correo_corporativo.py::_cargar_bandeja_unificada()`."""
    from src.db import correo as correo_db
    from src.services.comunicacion_interna import circulares, encuestas
    from src.services.correo import servicio as correo_svc

    filas = []
    buzones_google = [b for b in correo_db.listar_correos(id_empresa) if b.get("proveedor") == "google"]
    conectados = [b for b in buzones_google if correo_svc.estado_oauth(b["id_correo"]).get("conectado")]
    for b in conectados:
        for m in correo_db.listar_recibidos(id_correo=b["id_correo"], id_empresa=id_empresa):
            filas.append({
                "tipo": "gmail", "id": m.get("id"),
                "remitente_o_emisor": m.get("remitente") or "—",
                "asunto_o_titulo": m.get("asunto") or "—",
                "fecha": m.get("fecha") or m.get("fecha_descarga"),
                "leido": bool(m.get("leido")),
            })

    circs = circulares.listar_circulares(id_empresa=id_empresa, usuario_id=usuario_id)
    leidos_c = _leido_ids("CIRCULAR", [c["id"] for c in circs], usuario_id)
    for c in circs:
        filas.append({
            "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
            "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("creado"),
            "leido": c["id"] in leidos_c,
        })

    encs = encuestas.listar_encuestas(id_empresa=id_empresa, usuario_id=usuario_id)
    leidos_e = _leido_ids("ENCUESTA", [e["id"] for e in encs], usuario_id)
    for e in encs:
        filas.append({
            "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
            "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("creado"),
            "leido": e["id"] in leidos_e,
        })

    filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
    return filas


def registrar(bp):
    @bp.get("/correo/bandeja")
    @requiere_auth()
    def correo_bandeja():
        from flask import g, jsonify
        from src.api import paginacion
        filas = _bandeja_unificada(g.ctx["id_empresa"], g.ctx["usuario"].get("id"))
        return jsonify(paginacion.envolver(filas))

    @bp.get("/correo/circular/<int:id_circular>")
    @requiere_auth()
    def correo_circular_detalle(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        c = circulares.obtener_circular(id_circular)
        if not c or str(c.get("id_empresa")) != str(g.ctx["id_empresa"]):
            return jsonify({"error": "No encontrada"}), 404
        return jsonify(c)

    @bp.get("/correo/encuesta/<int:id_encuesta>")
    @requiere_auth()
    def correo_encuesta_detalle(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        e = encuestas.obtener_encuesta(id_encuesta)
        if not e or str(e.get("id_empresa")) != str(g.ctx["id_empresa"]):
            return jsonify({"error": "No encontrada"}), 404
        return jsonify(e)

    @bp.get("/correo/gmail/<int:id_recibido>")
    @requiere_auth()
    def correo_gmail_detalle(id_recibido):
        from flask import g, jsonify
        from src.db import correo as correo_db
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(m)

    @bp.post("/correo/circular")
    @requiere_auth()
    def correo_circular_crear():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.crear_circular(
            d.get("titulo"), d.get("cuerpo"), adjuntos=d.get("adjuntos"),
            destinatarios=d.get("destinatarios"),
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (201 if r.get("ok") else 400)

    @bp.post("/correo/encuesta")
    @requiere_auth()
    def correo_encuesta_crear():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.crear_encuesta(
            d.get("titulo"), d.get("intro"), d.get("preguntas") or [],
            adjuntos=d.get("adjuntos"), destinatarios=d.get("destinatarios"),
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (201 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/reenviar")
    @requiere_auth()
    def correo_circular_reenviar(id_circular):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.reenviar_circular(
            id_circular, d.get("destinatarios") or [],
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/reenviar")
    @requiere_auth()
    def correo_encuesta_reenviar(id_encuesta):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.reenviar_encuesta(
            id_encuesta, d.get("destinatarios") or [],
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/responder")
    @requiere_auth()
    def correo_circular_responder(id_circular):
        """Responde reutilizando la identidad del token (sin contraseña) — paralelo de
        `confirmar_lectura` (que sigue reservado al flujo de terminal compartido, no expuesto aquí)."""
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.responder_circular(
            id_circular, usuario=g.ctx["usuario"], comentario=d.get("comentario") or "",
            adjuntos=d.get("adjuntos"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/responder")
    @requiere_auth()
    def correo_encuesta_responder(id_encuesta):
        """Responde reutilizando la identidad del token (sin contraseña) — paralelo de
        `responder_encuesta` (que sigue reservado al flujo de terminal compartido, no expuesto aquí)."""
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.responder_encuesta_autenticado(
            id_encuesta, usuario=g.ctx["usuario"], respuestas=d.get("respuestas") or {},
            comentario=d.get("comentario") or "", adjuntos=d.get("adjuntos"),
            id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/correo/destinatarios/sugerencias")
    @requiere_auth()
    def correo_destinatarios_sugerencias():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna.usuarios_internos import (
            listar_centros_empresa, listar_contactos_externos, listar_usuarios_empresa)
        texto = (request.args.get("q") or "").strip()
        emp = g.ctx["id_empresa"]
        uid = g.ctx["usuario"].get("id")
        resultados = []
        for u in listar_usuarios_empresa(emp, texto):
            resultados.append({
                "origen": "usuario", "icono": "👤",
                "texto": u.get("nombre") or u.get("email") or "—",
                "identidad": {"usuario_id": u.get("id"), "nombre": u.get("nombre")},
                "tooltip": f"{u.get('nombre') or '—'} · {u.get('centro') or '—'}"})
        for c in listar_centros_empresa(emp, texto):
            resultados.append({
                "origen": "centro", "icono": "🏢",
                "texto": c.get("nombre") or c.get("email") or "—",
                "identidad": {"centro_codigo": c.get("centro_codigo")},
                "tooltip": "Difusión a todos los empleados de este centro"})
        for e in listar_contactos_externos(emp, uid, texto):
            resultados.append({
                "origen": "externo", "icono": "✉️",
                "texto": e.get("nombre") or e.get("email") or "—",
                "identidad": {"email_externo": e.get("email"), "nombre": e.get("nombre")},
                "tooltip": "Contacto externo (sin cuenta en Smart Manager)"})
        return jsonify(resultados[:20])

    @bp.post("/correo/gmail/<int:id_recibido>/leido")
    @requiere_auth()
    def correo_gmail_leido(id_recibido):
        from flask import g, jsonify
        from src.db import correo as correo_db
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify({"ok": correo_db.marcar_recibido_leido(id_recibido, g.ctx["id_empresa"])})

    @bp.post("/correo/circular/<int:id_circular>/leido")
    @requiere_auth()
    def correo_circular_leido(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        c = circulares.obtener_circular(id_circular)
        if not c or str(c.get("id_empresa")) != str(g.ctx["id_empresa"]):
            return jsonify({"error": "No encontrada"}), 404
        ok = circulares.marcar_leido_circular(id_circular, g.ctx["usuario"].get("id"))
        return jsonify({"ok": ok})

    @bp.post("/correo/encuesta/<int:id_encuesta>/leido")
    @requiere_auth()
    def correo_encuesta_leido(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        e = encuestas.obtener_encuesta(id_encuesta)
        if not e or str(e.get("id_empresa")) != str(g.ctx["id_empresa"]):
            return jsonify({"error": "No encontrada"}), 404
        ok = encuestas.marcar_leido_encuesta(id_encuesta, g.ctx["usuario"].get("id"))
        return jsonify({"ok": ok})

    # ── Las 5 carpetas reales (Borradores/Programados/Papelera/Pospuestos/Importantes) ───────────
    # Envoltorios finos: cada lista fusiona circulares+encuestas (+Gmail donde aplica, ver
    # docstring del módulo) con la MISMA normalización que `/correo/bandeja`; cada acción delega
    # 1:1 en la función de servicio ya certificada (mismo criterio exacto que
    # `gui/correo_corporativo.py::_fila_acciones_carpeta()`). Gmail no tiene Borradores/Programados
    # (sync de solo lectura, sin concepto de "redactar"), igual que en escritorio.

    @bp.get("/correo/enviados")
    @requiere_auth()
    def correo_enviados():
        """Mensajes/encuestas internos creados por el usuario actual (mismo criterio que
        `gui/correo_corporativo.py::_pintar_enviados` — Gmail no se incluye: su sync es de solo
        lectura y no registra lo que el usuario envía desde su cuenta real de Gmail)."""
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares, encuestas
        u = g.ctx["usuario"]
        uid, nombre = u.get("id"), u.get("nombre")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("circular", c) for c in circulares.listar_circulares(
                     id_empresa=emp, usuario_id=uid) if c.get("creador_nombre") == nombre]
                 + [_normalizar_folder("encuesta", e) for e in encuestas.listar_encuestas(
                     id_empresa=emp, usuario_id=uid) if e.get("creador_nombre") == nombre])
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        return jsonify(filas)

    @bp.get("/correo/borradores")
    @requiere_auth()
    def correo_borradores():
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares, encuestas
        uid = g.ctx["usuario"].get("id")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("circular", c) for c in circulares.listar_borradores(uid, id_empresa=emp)]
                 + [_normalizar_folder("encuesta", e) for e in encuestas.listar_borradores(uid, id_empresa=emp)])
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        return jsonify(filas)

    @bp.post("/correo/circular/borrador")
    @requiere_auth()
    def correo_circular_guardar_borrador():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.guardar_borrador(
            d.get("id_circular"), titulo=d.get("titulo"), cuerpo=d.get("cuerpo") or "",
            adjuntos=d.get("adjuntos"), destinatarios=d.get("destinatarios"),
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/borrador")
    @requiere_auth()
    def correo_encuesta_guardar_borrador():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.guardar_borrador(
            d.get("id_encuesta"), titulo=d.get("titulo"), intro=d.get("intro") or "",
            preguntas=d.get("preguntas"), adjuntos=d.get("adjuntos"),
            destinatarios=d.get("destinatarios"),
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/publicar")
    @requiere_auth()
    def correo_circular_publicar_borrador(id_circular):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.publicar_borrador(
            id_circular, destinatarios=d.get("destinatarios") or [], titulo=d.get("titulo"),
            cuerpo=d.get("cuerpo"), usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/publicar")
    @requiere_auth()
    def correo_encuesta_publicar_borrador(id_encuesta):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.publicar_borrador(
            id_encuesta, destinatarios=d.get("destinatarios") or [], titulo=d.get("titulo"),
            intro=d.get("intro"), preguntas=d.get("preguntas"),
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/eliminar_borrador")
    @requiere_auth()
    def correo_circular_eliminar_borrador(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        r = circulares.eliminar_borrador(id_circular, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/eliminar_borrador")
    @requiere_auth()
    def correo_encuesta_eliminar_borrador(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        r = encuestas.eliminar_borrador(id_encuesta, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/correo/programados")
    @requiere_auth()
    def correo_programados():
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares, encuestas
        uid = g.ctx["usuario"].get("id")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("circular", c, campo_fecha="fecha_programada")
                  for c in circulares.listar_programadas(uid, id_empresa=emp)]
                 + [_normalizar_folder("encuesta", e, campo_fecha="fecha_programada")
                    for e in encuestas.listar_programadas(uid, id_empresa=emp)])
        filas.sort(key=lambda x: str(x["fecha"] or ""))
        return jsonify(filas)

    @bp.post("/correo/circular/programar")
    @requiere_auth()
    def correo_circular_programar():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        try:
            fecha = _parse_fecha(d.get("fecha_programada"))
        except ValueError:
            return jsonify({"ok": False, "error": "Fecha programada inválida."}), 400
        if not fecha:
            return jsonify({"ok": False, "error": "Indica la fecha/hora de envío."}), 400
        r = circulares.programar(
            d.get("id_circular_borrador"), titulo=d.get("titulo"), cuerpo=d.get("cuerpo"),
            fecha_programada=fecha, destinatarios=d.get("destinatarios") or [],
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/programar")
    @requiere_auth()
    def correo_encuesta_programar():
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        try:
            fecha = _parse_fecha(d.get("fecha_programada"))
        except ValueError:
            return jsonify({"ok": False, "error": "Fecha programada inválida."}), 400
        if not fecha:
            return jsonify({"ok": False, "error": "Indica la fecha/hora de envío."}), 400
        r = encuestas.programar(
            d.get("id_encuesta_borrador"), titulo=d.get("titulo"), intro=d.get("intro"),
            preguntas=d.get("preguntas"), fecha_programada=fecha,
            destinatarios=d.get("destinatarios") or [],
            usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/cancelar_programacion")
    @requiere_auth()
    def correo_circular_cancelar_programacion(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        r = circulares.cancelar_programacion(id_circular, usuario=g.ctx["usuario"],
                                             id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/cancelar_programacion")
    @requiere_auth()
    def correo_encuesta_cancelar_programacion(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        r = encuestas.cancelar_programacion(id_encuesta, usuario=g.ctx["usuario"],
                                            id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/correo/papelera")
    @requiere_auth()
    def correo_papelera():
        from flask import g, jsonify
        from src.db import correo as correo_db
        from src.services.comunicacion_interna import circulares, encuestas
        uid = g.ctx["usuario"].get("id")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("gmail", m) for m in correo_db.listar_recibidos_papelera(emp)]
                 + [_normalizar_folder("circular", c) for c in circulares.listar_papelera(uid, id_empresa=emp)]
                 + [_normalizar_folder("encuesta", e) for e in encuestas.listar_papelera(uid, id_empresa=emp)])
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        return jsonify(filas)

    @bp.post("/correo/circular/<int:id_circular>/papelera")
    @requiere_auth()
    def correo_circular_papelera(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        r = circulares.mover_papelera(id_circular, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/circular/<int:id_circular>/restaurar")
    @requiere_auth()
    def correo_circular_restaurar(id_circular):
        from flask import g, jsonify
        from src.services.comunicacion_interna import circulares
        r = circulares.restaurar_de_papelera(id_circular, usuario=g.ctx["usuario"],
                                             id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/papelera")
    @requiere_auth()
    def correo_encuesta_papelera(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        r = encuestas.mover_papelera(id_encuesta, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/restaurar")
    @requiere_auth()
    def correo_encuesta_restaurar(id_encuesta):
        from flask import g, jsonify
        from src.services.comunicacion_interna import encuestas
        r = encuestas.restaurar_de_papelera(id_encuesta, usuario=g.ctx["usuario"],
                                            id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/gmail/<int:id_recibido>/papelera")
    @requiere_auth()
    def correo_gmail_papelera(id_recibido):
        from flask import g, jsonify
        from src.db import correo as correo_db
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify({"ok": correo_db.mover_recibido_papelera(id_recibido, g.ctx["id_empresa"])})

    @bp.post("/correo/gmail/<int:id_recibido>/restaurar")
    @requiere_auth()
    def correo_gmail_restaurar(id_recibido):
        from flask import g, jsonify
        from src.db import correo as correo_db
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify({"ok": correo_db.restaurar_recibido(id_recibido, g.ctx["id_empresa"])})

    @bp.get("/correo/pospuestos")
    @requiere_auth()
    def correo_pospuestos():
        from flask import g, jsonify
        from src.db import correo as correo_db
        from src.services.comunicacion_interna import circulares, encuestas
        uid = g.ctx["usuario"].get("id")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("gmail", m, campo_fecha="pospuesto_hasta")
                  for m in correo_db.listar_recibidos_pospuestos(emp)]
                 + [_normalizar_folder("circular", c, campo_fecha="pospuesto_hasta")
                    for c in circulares.listar_pospuestos(uid, id_empresa=emp)]
                 + [_normalizar_folder("encuesta", e, campo_fecha="pospuesto_hasta")
                    for e in encuestas.listar_pospuestos(uid, id_empresa=emp)])
        filas.sort(key=lambda x: str(x["fecha"] or ""))
        return jsonify(filas)

    @bp.post("/correo/circular/<int:id_circular>/posponer")
    @requiere_auth()
    def correo_circular_posponer(id_circular):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        try:
            hasta = _parse_fecha(d.get("hasta"))
        except ValueError:
            return jsonify({"ok": False, "error": "Fecha inválida."}), 400
        if not hasta:
            return jsonify({"ok": False, "error": "Indica hasta cuándo posponer."}), 400
        r = circulares.posponer(id_circular, hasta, id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/posponer")
    @requiere_auth()
    def correo_encuesta_posponer(id_encuesta):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        try:
            hasta = _parse_fecha(d.get("hasta"))
        except ValueError:
            return jsonify({"ok": False, "error": "Fecha inválida."}), 400
        if not hasta:
            return jsonify({"ok": False, "error": "Indica hasta cuándo posponer."}), 400
        r = encuestas.posponer(id_encuesta, hasta, id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/gmail/<int:id_recibido>/posponer")
    @requiere_auth()
    def correo_gmail_posponer(id_recibido):
        from flask import g, jsonify, request
        from src.db import correo as correo_db
        d = request.get_json(silent=True) or {}
        try:
            hasta = _parse_fecha(d.get("hasta"))
        except ValueError:
            return jsonify({"ok": False, "error": "Fecha inválida."}), 400
        if not hasta:
            return jsonify({"ok": False, "error": "Indica hasta cuándo posponer."}), 400
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify({"ok": correo_db.posponer_recibido(id_recibido, hasta, g.ctx["id_empresa"])})

    @bp.get("/correo/importantes")
    @requiere_auth()
    def correo_importantes():
        from flask import g, jsonify
        from src.db import correo as correo_db
        from src.services.comunicacion_interna import circulares, encuestas
        uid = g.ctx["usuario"].get("id")
        emp = g.ctx["id_empresa"]
        filas = ([_normalizar_folder("gmail", m) for m in correo_db.listar_recibidos_importantes(emp)]
                 + [_normalizar_folder("circular", c) for c in circulares.listar_importantes(uid, id_empresa=emp)]
                 + [_normalizar_folder("encuesta", e) for e in encuestas.listar_importantes(uid, id_empresa=emp)])
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        return jsonify(filas)

    @bp.post("/correo/circular/<int:id_circular>/importante")
    @requiere_auth()
    def correo_circular_importante(id_circular):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import circulares
        d = request.get_json(silent=True) or {}
        r = circulares.marcar_importante(id_circular, bool(d.get("valor", True)), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/encuesta/<int:id_encuesta>/importante")
    @requiere_auth()
    def correo_encuesta_importante(id_encuesta):
        from flask import g, jsonify, request
        from src.services.comunicacion_interna import encuestas
        d = request.get_json(silent=True) or {}
        r = encuestas.marcar_importante(id_encuesta, bool(d.get("valor", True)), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/correo/gmail/<int:id_recibido>/importante")
    @requiere_auth()
    def correo_gmail_importante(id_recibido):
        from flask import g, jsonify, request
        from src.db import correo as correo_db
        d = request.get_json(silent=True) or {}
        m = correo_db.obtener_recibido(id_recibido, g.ctx["id_empresa"])
        if not m:
            return jsonify({"error": "No encontrado"}), 404
        ok = correo_db.marcar_recibido_importante(id_recibido, bool(d.get("valor", True)), g.ctx["id_empresa"])
        return jsonify({"ok": ok})
