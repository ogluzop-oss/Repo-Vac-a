"""
Ejecutor de delegación — Posventa/SAT: responder tickets de soporte nuevos automáticamente, SOLO
cuando encajan con las instrucciones del SUPERADMIN. Mismo criterio honesto que el ejecutor de
correo: si SOMA no tiene seguridad de que el ticket encaja, declina en vez de responder a ciegas.
Reutiliza `services.sat.tickets.comentar` (el CRUD real de comentarios de ticket, el mismo que usa
la GUI de escritorio) — nunca un motor de mensajería paralelo.
"""

import logging

logger = logging.getLogger("soma_delegacion.ejecutores.sat")


def contexto_desde_evento(ev: dict) -> dict | None:
    """Traduce el evento `TICKET_CREADO` (`ref_id` = id del ticket) al contexto que espera
    `ejecutar_respuesta_ticket`."""
    id_ticket = ev.get("ref_id")
    if not id_ticket:
        return None
    from src.services.sat import tickets
    ticket = tickets.obtener(id_ticket)
    if not ticket or str(ticket.get("id_empresa")) != str(ev.get("id_empresa")):
        return None
    return {"id_ticket": id_ticket, "asunto": ticket.get("asunto"),
           "descripcion": ticket.get("descripcion"), "categoria": ticket.get("categoria")}


def ejecutar_respuesta_ticket(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    from src.services.soma_delegacion.motor import MOTIVOS_LEGIBLES, preguntar_soma

    prompt = (
        "Eres SOMA, el asistente de IA de un ERP, respondiendo automáticamente a tickets de "
        "soporte entrantes — PERO SOLO cuando el ticket encaje claramente con las instrucciones "
        "del administrador. Si tienes CUALQUIER duda, o el ticket trata un asunto distinto, "
        "debes declinar — nunca inventes una respuesta fuera de lo autorizado.\n\n"
        f"Instrucciones del administrador:\n\"\"\"\n{regla.get('instrucciones', '')}\n\"\"\"\n\n"
        f"Ticket recibido:\nAsunto: {contexto.get('asunto', '')}\n"
        f"Categoría: {contexto.get('categoria') or '(sin categoría)'}\n"
        f"Descripción:\n{contexto.get('descripcion', '')}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON, sin texto adicional: "
        '{"aplica": true o false, "motivo": "por qué aplica o no, en una frase", '
        '"respuesta": "el texto de la respuesta a publicar en el ticket, en tono profesional "'
        '"(solo si aplica es true)"}'
    )
    r = preguntar_soma(prompt, id_empresa=id_empresa, usuario=usuario, tarea="soma_delegacion_sat")
    if not r.get("ok"):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": MOTIVOS_LEGIBLES.get(r.get("motivo"), "No se pudo evaluar el ticket.")}

    datos = r["datos"]
    if not datos.get("aplica"):
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": datos.get("motivo") or
                         "SOMA decidió que este ticket no encaja con las instrucciones."}

    respuesta_txt = (datos.get("respuesta") or "").strip()
    if not respuesta_txt:
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": "SOMA no generó texto de respuesta."}

    if regla.get("modo_aplicacion") != "automatico":
        return {"ok": True, "estado": "pendiente_revision", "decision": datos,
               "detalle": "Borrador de respuesta generado, pendiente de revisión."}

    from src.services.sat import tickets
    cid = tickets.comentar(contexto.get("id_ticket"), respuesta_txt, autor="SOMA",
                           es_cliente=False, interno=False, id_empresa=id_empresa)
    ok = cid is not None
    return {"ok": ok, "estado": "aplicado" if ok else "error", "decision": datos,
           "detalle": "Respuesta publicada en el ticket." if ok else
                     "No se pudo publicar la respuesta en el ticket."}
