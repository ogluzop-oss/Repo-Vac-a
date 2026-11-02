"""
Motor de despacho de la delegación a SOMA: `procesar_evento` evalúa todas las reglas ACTIVAS de
un tipo para una empresa y delega en el ejecutor registrado en `catalogo`; `preguntar_soma` es el
ÚNICO punto de llamada a la IA de esta capa (mismo cliente Anthropic degradable y el mismo
chokepoint medido/auditado que el resto de asistentes SOMA — `copilot.motor_llm`/
`ia_control_uso.ejecutar_tarea_ia`), para que cada ejecutor solo construya su prompt de dominio.

NOTA: este módulo NUNCA importa `catalogo` a nivel de módulo — `catalogo._registrar_tipos_
integrados()` importa los `ejecutores/*` al cargarse, y esos ejecutores importan `preguntar_soma`
de aquí; importar `catalogo` arriba crearía un ciclo. Los imports de `catalogo` van siempre
dentro de las funciones.
"""

import json
import logging

logger = logging.getLogger("soma_delegacion.motor")


def preguntar_soma(prompt: str, *, id_empresa, usuario: dict | None = None,
                   tarea: str = "soma_delegacion", max_tokens: int = 800) -> dict:
    """Llamada de UN SOLO TURNO a Anthropic pidiendo una respuesta JSON — sin herramientas ni
    historial (no es una conversación, es "evalúa esta situación y decide"). Devuelve SIEMPRE un
    dict, nunca lanza: éxito -> {"ok": True, "datos": dict}; degradación ->
    {"ok": False, "motivo": "sin_api_key"|"sin_contexto"|"limite_ia"|"respuesta_invalida"|
    "error_inesperado"} — igual criterio honesto que `catalogo.ia_contenido`/
    `proyectos.carteles.generar_copy_ia`: nunca se inventa una decisión sin IA disponible."""
    from src.services.copilot.motor_llm import _MODELO, _cliente
    from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia

    cliente = _cliente()
    if cliente is None:
        return {"ok": False, "motivo": "sin_api_key"}
    if not id_empresa:
        return {"ok": False, "motivo": "sin_contexto"}
    id_usuario = (usuario or {}).get("id")
    try:
        respuesta = ejecutar_tarea_ia(
            id_empresa, id_usuario, tarea,
            lambda: cliente.messages.create(
                model=_MODELO, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]))
    except LimiteUsoIAExcedido:
        return {"ok": False, "motivo": "limite_ia"}
    except Exception as e:
        logger.warning("preguntar_soma: %s", e)
        return {"ok": False, "motivo": "error_inesperado"}

    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1 or fin < inicio:
        return {"ok": False, "motivo": "respuesta_invalida"}
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except Exception:
        return {"ok": False, "motivo": "respuesta_invalida"}
    if not isinstance(datos, dict):
        return {"ok": False, "motivo": "respuesta_invalida"}
    return {"ok": True, "datos": datos}


MOTIVOS_LEGIBLES = {
    "sin_api_key": "SOMA no tiene configurada la conexión con la IA.",
    "sin_contexto": "Falta contexto para que SOMA pueda decidir.",
    "limite_ia": "Se ha alcanzado el límite de uso de IA del plan de la empresa.",
    "respuesta_invalida": "SOMA no pudo estructurar una respuesta válida.",
    "error_inesperado": "Error en la conexión con la API de SOMA.",
}


def procesar_evento(tipo: str, contexto: dict, *, id_empresa, usuario: dict | None = None) -> list:
    """Evalúa TODAS las reglas activas de `tipo` para `id_empresa` contra `contexto`, delegando
    en el ejecutor de ese tipo (`catalogo.obtener(tipo)["ejecutor"]`) y registrando cada
    evaluación en el historial. Devuelve la lista de resultados (uno por regla evaluada) — vacía
    si no hay ninguna regla activa de ese tipo (ninguna automatización delegada, nada que hacer)."""
    from src.services.soma_delegacion import catalogo, historial, reglas

    tipo_def = catalogo.obtener(tipo)
    if not tipo_def:
        logger.warning("procesar_evento: tipo desconocido %s", tipo)
        return []
    resultados = []
    for regla in reglas.listar_reglas(id_empresa=id_empresa, tipo=tipo, solo_activas=True):
        try:
            r = tipo_def["ejecutor"](regla, contexto, id_empresa=id_empresa, usuario=usuario)
        except Exception as e:
            logger.error("procesar_evento(%s, regla=%s): %s", tipo, regla.get("id"), e)
            r = {"ok": False, "estado": "error", "decision": None, "detalle": str(e)}
        historial.registrar(regla["id"], tipo, contexto=contexto, decision=r.get("decision"),
                            estado=r.get("estado", "aplicado" if r.get("ok") else "error"),
                            resultado=r.get("detalle"), id_empresa=id_empresa)
        resultados.append(r)
    return resultados
