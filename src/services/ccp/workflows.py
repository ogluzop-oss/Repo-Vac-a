"""
Workflow Communication Engine (CCP Fase II · B2) — flujos de comunicación reutilizables.

Define flujos como secuencias de pasos-tipo (enviar_comunicacion / esperar N días / condición /
notificar responsable / crear incidencia) que se ejecutan SOBRE la CCP y la infraestructura existente
(workflow engine / notificaciones). Sin lógica específica por módulo: los flujos son reutilizables.
Multiempresa. API-First (sin PyQt).

Los pasos con 'esperar' se difieren (se integran con el scheduler de jobs del ERP); en ejecución
inmediata (`simular_esperas=True`) se saltan las esperas para pruebas/uso síncrono.
"""

import logging

logger = logging.getLogger("ccp.workflows")

_FLUJOS: dict = {}


def registrar_flujo(clave, pasos, *, descripcion=None):
    """Registra un flujo reutilizable. `pasos` = lista de dicts {tipo, ...}. Tipos:
      - {'tipo':'enviar', 'plantilla'|'asunto'/'cuerpo', 'canal'?}
      - {'tipo':'esperar', 'dias':N}
      - {'tipo':'condicion', 'clave':k, 'op':'==','>','<', 'valor':v}  (evalúa contexto)
      - {'tipo':'notificar', 'titulo','mensaje','roles'?/'usuarios'?}
      - {'tipo':'incidencia', 'titulo','mensaje'}"""
    _FLUJOS[clave] = {"pasos": pasos, "descripcion": descripcion}
    return clave


def flujos() -> dict:
    return dict(_FLUJOS)


def _cond(op, a, b):
    try:
        a = float(a); b = float(b)
    except (TypeError, ValueError):
        a, b = str(a), str(b)
    return {"==": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}.get(op, False)


def ejecutar_flujo(clave, contexto, *, id_empresa=None, destinatario=None, pistas=None,
                   simular_esperas=True) -> dict:
    """Ejecuta un flujo. `contexto` = dict con datos para condiciones/variables. Devuelve
    {ok, traza:[...], detenido_en}. Con `simular_esperas=False`, al primer 'esperar' se detiene y
    devuelve el índice para reanudar por el scheduler."""
    flujo = _FLUJOS.get(clave)
    if not flujo:
        return {"ok": False, "traza": [], "detenido_en": None, "error": "flujo no registrado"}
    from src.services import ccp
    traza = []
    contexto = contexto or {}
    for i, paso in enumerate(flujo["pasos"]):
        t = paso.get("tipo")
        if t == "esperar":
            if not simular_esperas:
                traza.append({"paso": i, "tipo": "esperar", "diferido": True, "dias": paso.get("dias")})
                return {"ok": True, "traza": traza, "detenido_en": i}
            traza.append({"paso": i, "tipo": "esperar", "simulada": True})
        elif t == "condicion":
            cumple = _cond(paso.get("op", "=="), contexto.get(paso.get("clave")), paso.get("valor"))
            traza.append({"paso": i, "tipo": "condicion", "cumple": cumple})
            if not cumple:
                return {"ok": True, "traza": traza, "detenido_en": i}   # corta el flujo
        elif t == "enviar":
            res = ccp.enviar_comunicacion(
                id_empresa=id_empresa, destinatario=destinatario, pistas=pistas,
                asunto=paso.get("asunto", ""), cuerpo=paso.get("cuerpo", ""),
                plantilla=paso.get("plantilla"), variables=contexto, canal=paso.get("canal"),
                contexto=paso.get("contexto") or clave)
            traza.append({"paso": i, "tipo": "enviar", "ok": res.ok, "com_id": res.com_id})
        elif t == "notificar":
            try:
                ccp.notificaciones_centro.notificar(
                    paso.get("titulo", ""), paso.get("mensaje", ""), id_empresa=id_empresa,
                    usuarios=paso.get("usuarios"), roles=paso.get("roles"))
                traza.append({"paso": i, "tipo": "notificar", "ok": True})
            except Exception as e:
                traza.append({"paso": i, "tipo": "notificar", "ok": False, "error": str(e)})
        elif t == "incidencia":
            try:
                from src.services import notificaciones as _noti
                _noti.emitir("incidencia", paso.get("titulo", "Incidencia"), paso.get("mensaje", ""),
                             prioridad="alta", modulo="ccp", id_empresa=id_empresa)
                traza.append({"paso": i, "tipo": "incidencia", "ok": True})
            except Exception as e:
                traza.append({"paso": i, "tipo": "incidencia", "ok": False, "error": str(e)})
        else:
            traza.append({"paso": i, "tipo": t, "ignorado": True})
    return {"ok": True, "traza": traza, "detenido_en": None}


# ── Flujos SEMILLA (reutilizables) ────────────────────────────────────────────
def _sembrar():
    registrar_flujo("factura_pendiente", [
        {"tipo": "enviar", "plantilla": "facturas", "contexto": "facturacion"},
        {"tipo": "esperar", "dias": 7},
        {"tipo": "condicion", "clave": "pendiente", "op": "==", "valor": True},
        {"tipo": "enviar", "asunto": "Recordatorio de factura pendiente",
         "cuerpo": "Le recordamos que su factura sigue pendiente."},
        {"tipo": "esperar", "dias": 7},
        {"tipo": "notificar", "titulo": "Factura sin cobrar", "mensaje": "Revisar factura pendiente",
         "roles": ["ADMINISTRADOR", "GERENTE"]},
        {"tipo": "incidencia", "titulo": "Impago", "mensaje": "Factura pendiente tras avisos"},
    ], descripcion="Ciclo de recordatorio de facturas pendientes")


_sembrar()
