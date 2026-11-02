"""
Chat de soporte del storefront — IA primero, escalado a humano (Fase 6 e-commerce, Catálogo Web).

Flujo: un visitante anónimo (sin cuenta, el storefront no exige login) manda un mensaje → mientras
no haya ticket, responde la IA (histórico en `cd_chat_mensajes`, migr. 0293). Se escala a un ticket
SAT REAL (`services.sat.tickets.crear_ticket(canal="chat_web", ...)` — motor YA existente, CERO
tabla/estado nuevo para el ciclo de vida del ticket) en dos casos: el visitante pide expresamente
hablar con una persona, o la IA no puede ayudar (incluida la degradación honesta sin API key — un
visitante NUNCA se queda sin respuesta solo porque no hay IA configurada, se le deriva a un agente
humano). En cuanto se escala, la conversación pasa a vivir ENTERAMENTE en `ticket_comentarios` (la
MISMA tabla que ya usa el panel interno `gui/sat_dashboard.py`) — nunca dos fuentes de verdad.

Motor IA: MISMO cliente/modelo degradable que el resto de la app
(`services.copilot.motor_llm._cliente`/`_MODELO`) y el MISMO punto único de ejecución medida
(`services.ia_control_uso.ejecutar_tarea_ia`) — pero NO `motor_llm.responder_con_llm` (ese depende
de `db.usuario.sesion_global`, una sesión de ESCRITORIO activa; un visitante anónimo del storefront,
servido por el proceso Flask, no tiene ninguna — mismo criterio de un solo turno sin sesión ya usado
en `services.catalogo.ia_contenido`, no un motor nuevo)."""

from __future__ import annotations

import logging
import uuid

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("cd.canal_web.soporte_chat")

_PALABRAS_HUMANO = ("hablar con una persona", "hablar con alguien", "agente humano",
                    "atencion humana", "atención humana", "quiero un humano", "operador humano")
_MARCADOR_ESCALADO = "ESCALAR_HUMANO"
_MAX_HISTORIAL = 12


def _nuevo_token() -> str:
    return uuid.uuid4().hex


def _visitante(token, id_empresa=None) -> dict | None:
    if not token:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cd_chat_visitantes WHERE token=%s", (token,))
            r = cur.fetchone()
            if not r:
                return None
            d = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
            if id_empresa and str(d.get("id_empresa")) != str(id_empresa):
                return None
            return d
    except Exception as e:
        logger.error("_visitante(%s): %s", token, e)
        return None


def _crear_visitante(id_empresa) -> str:
    token = _nuevo_token()
    with transaccion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO cd_chat_visitantes (token, id_empresa) VALUES (%s,%s)",
                    (token, id_empresa))
    return token


def _guardar_mensaje(token, remitente, texto) -> None:
    with transaccion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO cd_chat_mensajes (token, remitente, texto) VALUES (%s,%s,%s)",
                    (token, remitente, texto))
        cur.execute("UPDATE cd_chat_visitantes SET ultima_actividad=NOW() WHERE token=%s", (token,))


def _historial(token) -> list:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT remitente, texto, creado_en FROM cd_chat_mensajes WHERE token=%s "
                    "ORDER BY id ASC", (token,))
        cols = ("remitente", "texto", "creado_en")
        filas = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
        for f in filas:
            f["creado_en"] = str(f.get("creado_en") or "")   # serializable vía JSON (Flask)
        return filas


def _responder_ia(id_empresa, texto, historial) -> str | None:
    """`None` = degradación honesta (sin cliente configurado, límite de uso alcanzado, o cualquier
    error de la llamada real) — el llamador lo interpreta como "escalar a humano", nunca como
    "seguir esperando a la IA"."""
    from src.services.copilot.motor_llm import _MODELO, _cliente
    from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia
    cliente = _cliente()
    if cliente is None:
        return None
    mensajes = [{"role": "user" if h["remitente"] == "visitante" else "assistant", "content": h["texto"]}
               for h in historial[-_MAX_HISTORIAL:]]
    mensajes.append({"role": "user", "content": texto})
    system = (
        "Eres el asistente de atención al cliente de una tienda online. Responde en español, de "
        "forma breve, clara y amable, usando solo la información de la conversación. Si no puedes "
        "resolver la consulta, o el cliente pide expresamente hablar con una persona, responde "
        f"ÚNICAMENTE con el texto {_MARCADOR_ESCALADO} (sin nada más)."
    )
    try:
        respuesta = ejecutar_tarea_ia(
            id_empresa, None, "canal_web_chat_soporte",
            lambda: cliente.messages.create(model=_MODELO, max_tokens=400, system=system,
                                            messages=mensajes))
    except LimiteUsoIAExcedido:
        return None
    except Exception as e:
        logger.warning("_responder_ia: %s", e)
        return None
    texto_resp = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
    return texto_resp or None


def _escalar(id_empresa, token, historial) -> int | None:
    """Crea el ticket SAT y traslada el hilo previo (IA) a `ticket_comentarios` — a partir de aquí
    la conversación vive ENTERAMENTE ahí (nunca dos fuentes de verdad para el mismo tramo)."""
    from src.services.sat import tickets as _tk
    transcripcion = "\n".join(f"[{h['remitente']}] {h['texto']}" for h in historial)
    id_ticket = _tk.crear_ticket(
        f"Chat storefront — visitante {token[:8]}",
        descripcion=transcripcion or "(sin mensajes previos)",
        canal="chat_web", id_empresa=id_empresa)
    if id_ticket:
        for h in historial:
            es_cliente = h["remitente"] == "visitante"
            cuerpo = h["texto"] if es_cliente else f"[IA] {h['texto']}"
            _tk.comentar(id_ticket, cuerpo, autor=f"visitante:{token[:8]}" if es_cliente else "ia",
                        es_cliente=es_cliente, id_empresa=id_empresa)
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_chat_visitantes SET id_ticket=%s WHERE token=%s", (id_ticket, token))
    return id_ticket


def _mensajes_publicos_ticket(id_ticket, id_empresa) -> list:
    from src.services.sat import tickets as _tk
    salida = []
    for c in _tk.listar_comentarios(id_ticket, solo_publicos=True, id_empresa=id_empresa):
        salida.append({"remitente": "visitante" if c.get("es_cliente") else "agente",
                       "texto": c.get("cuerpo") or "", "fecha": str(c.get("fecha") or "")})
    return salida


def enviar_mensaje(id_empresa, token, texto) -> dict:
    """Punto de entrada del widget del storefront (`backend/storefront.py`). Devuelve SIEMPRE
    `{"token", "mensajes", "escalado", "id_ticket"}` — nunca lanza, nunca deja al visitante sin
    respuesta (sin IA disponible ⇒ escalado automático a un ticket real)."""
    if not (texto or "").strip():
        return {"error": "texto_vacio"}
    vis = _visitante(token, id_empresa)
    if vis is None:
        token = _crear_visitante(id_empresa)
        vis = {"token": token, "id_empresa": id_empresa, "id_ticket": None}

    if vis.get("id_ticket"):
        from src.services.sat import tickets as _tk
        _tk.comentar(vis["id_ticket"], texto.strip(), autor=f"visitante:{token[:8]}", es_cliente=True,
                    id_empresa=id_empresa)
        return {"token": token, "mensajes": _mensajes_publicos_ticket(vis["id_ticket"], id_empresa),
               "escalado": True, "id_ticket": vis["id_ticket"]}

    _guardar_mensaje(token, "visitante", texto.strip())
    historial = _historial(token)
    pide_humano = any(p in texto.lower() for p in _PALABRAS_HUMANO)
    respuesta_ia = None if pide_humano else _responder_ia(id_empresa, texto.strip(), historial)

    if pide_humano or respuesta_ia is None or respuesta_ia.strip() == _MARCADOR_ESCALADO:
        id_ticket = _escalar(id_empresa, token, historial)
        if id_ticket:
            from src.services.sat import tickets as _tk
            aviso = ("Un agente humano revisará tu consulta en breve "
                    f"(ticket #{id_ticket}). Puedes seguir escribiendo aquí mismo.")
            _tk.comentar(id_ticket, f"[IA] {aviso}", autor="ia", es_cliente=False, id_empresa=id_empresa)
            return {"token": token, "mensajes": _mensajes_publicos_ticket(id_ticket, id_empresa),
                   "escalado": True, "id_ticket": id_ticket}
        # Ni IA ni escalado disponibles (p. ej. BD caída a medias): degradación final honesta.
        aviso = "No se pudo procesar tu consulta ahora mismo. Inténtalo de nuevo en unos minutos."
        _guardar_mensaje(token, "ia", aviso)
        return {"token": token, "mensajes": _historial(token), "escalado": False, "id_ticket": None}

    _guardar_mensaje(token, "ia", respuesta_ia)
    return {"token": token, "mensajes": _historial(token), "escalado": False, "id_ticket": None}


def obtener_hilo(id_empresa, token) -> dict:
    """Solo lectura, para que el widget refresque el hilo (p. ej. para ver respuestas nuevas de un
    agente humano tras escalar) sin mandar ningún mensaje nuevo."""
    vis = _visitante(token, id_empresa)
    if vis is None:
        return {"token": None, "mensajes": [], "escalado": False, "id_ticket": None}
    if vis.get("id_ticket"):
        return {"token": token, "mensajes": _mensajes_publicos_ticket(vis["id_ticket"], id_empresa),
               "escalado": True, "id_ticket": vis["id_ticket"]}
    return {"token": token, "mensajes": _historial(token), "escalado": False, "id_ticket": None}
