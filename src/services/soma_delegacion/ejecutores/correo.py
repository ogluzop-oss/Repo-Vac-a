"""
Ejecutor de delegación — Correo: responder correos entrantes automáticamente, SOLO cuando
encajan con las instrucciones del SUPERADMIN. Nunca inventa una respuesta a ciegas: si SOMA no
tiene seguridad de que el correo encaja con las instrucciones, declina (estado "descartado") en
vez de responder igualmente. Reutiliza `services.correo.servicio.responder_correo` (enhebrado
real In-Reply-To/References), nunca un motor de envío paralelo.
"""

import logging

logger = logging.getLogger("soma_delegacion.ejecutores.correo")


def contexto_desde_evento(ev: dict) -> dict | None:
    """Traduce el evento `CORREO_RECIBIDO` (publicado por `db.correo.guardar_recibido`,
    `ref_id` = id del correo recibido) al contexto que espera `ejecutar_respuesta_correo`."""
    id_recibido = ev.get("ref_id")
    if not id_recibido:
        return None
    from src.db import correo as correo_db
    recibido = correo_db.obtener_recibido(id_recibido, id_empresa=ev.get("id_empresa"))
    if not recibido:
        return None
    return {"id_correo": recibido.get("id_correo"), "id_recibido": recibido.get("id"),
           "remitente": recibido.get("remitente"), "asunto": recibido.get("asunto"),
           "cuerpo": recibido.get("cuerpo")}


def ejecutar_respuesta_correo(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    """`contexto` esperado: {"id_correo", "id_recibido", "remitente", "asunto", "cuerpo"}."""
    from src.services.soma_delegacion.motor import MOTIVOS_LEGIBLES, preguntar_soma

    prompt = (
        "Eres SOMA, el asistente de IA de un ERP, actuando en nombre de la empresa para "
        "responder automáticamente a correos entrantes — PERO SOLO cuando el correo encaje "
        "claramente con las instrucciones que te ha dado el administrador. Si tienes CUALQUIER "
        "duda sobre si aplica, o el correo trata un asunto distinto, debes declinar — nunca "
        "inventes una respuesta fuera de lo que te han autorizado a responder.\n\n"
        f"Instrucciones del administrador:\n\"\"\"\n{regla.get('instrucciones', '')}\n\"\"\"\n\n"
        f"Correo recibido:\nDe: {contexto.get('remitente', '')}\n"
        f"Asunto: {contexto.get('asunto', '')}\n"
        f"Cuerpo:\n{contexto.get('cuerpo', '')}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON, sin texto adicional: "
        '{"aplica": true o false, "motivo": "por qué aplica o no, en una frase", '
        '"respuesta": "el texto de la respuesta a enviar, en tono profesional (solo si aplica es true)"}'
    )
    r = preguntar_soma(prompt, id_empresa=id_empresa, usuario=usuario, tarea="soma_delegacion_correo")
    if not r.get("ok"):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": MOTIVOS_LEGIBLES.get(r.get("motivo"), "No se pudo evaluar el correo.")}

    datos = r["datos"]
    if not datos.get("aplica"):
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": datos.get("motivo") or
                         "SOMA decidió que este correo no encaja con las instrucciones."}

    respuesta_txt = (datos.get("respuesta") or "").strip()
    if not respuesta_txt:
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": "SOMA no generó texto de respuesta."}

    if regla.get("modo_aplicacion") != "automatico":
        # "Revisar antes": el borrador queda guardado en el historial (decision["respuesta"]);
        # el SUPERADMIN lo envía desde la pantalla de Delegación IA con un clic, o lo descarta.
        return {"ok": True, "estado": "pendiente_revision", "decision": datos,
               "detalle": "Borrador de respuesta generado, pendiente de revisión."}

    from src.services.correo import servicio as correo_srv
    ok, msg = correo_srv.responder_correo(contexto.get("id_correo"), contexto.get("id_recibido"),
                                          respuesta_txt, id_empresa=id_empresa)
    return {"ok": ok, "estado": "aplicado" if ok else "error", "decision": datos, "detalle": msg}
