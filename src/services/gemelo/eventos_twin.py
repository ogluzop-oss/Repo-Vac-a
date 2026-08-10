"""
Actualizacion del Gemelo Digital por EVENTOS (Paquete Enterprise 8, SUBFASE 8.9).

Cada cambio relevante actualiza el gemelo AUTOMATICAMENTE y SOLO a traves del Event Bus: nunca
por llamadas manuales entre modulos. El gemelo se SUSCRIBE a '*' (todos los tipos) con un unico
manejador que:

  1. Invalida el estado cacheado del/los dominio(s) afectado(s) → la proxima consulta lo recalcula
     desde las fuentes vivas (nunca queda desactualizado; SUBFASE 8.15/8.16).
  2. Registra oportunisticamente aristas del grafo de dependencias (SUBFASE 8.8) cuando el evento
     lleva pistas de trazabilidad en su payload (dt_origen / dt_destino), o segun la cadena de
     valor conocida por tipo de evento.

El manejador es BULLETPROOF: cualquier fallo se ignora; jamas puede romper al publicador (que ya
es a su vez a prueba de fallos en el bus).
"""

import logging

from src.services.gemelo import dependencias as DEP

logger = logging.getLogger("gemelo.eventos")

# Tipo de evento → dominios del gemelo cuyo estado deja de ser valido.
MAPA_DOMINIOS = {
    "VENTA_REGISTRADA":        ["comercial", "inventario", "empresa"],
    "FACTURA_GENERADA":        ["comercial", "financiero", "empresa"],
    "FACTURA_ANULADA":         ["comercial", "financiero"],
    "FACTURA_RECTIFICADA":     ["comercial", "financiero"],
    "COBRO_REGISTRADO":        ["financiero", "comercial"],
    "PEDIDO_RECIBIDO":         ["logistico", "inventario", "empresa"],
    "PROVEEDOR_ACTUALIZADO":   ["logistico"],
    "KARDEX_MOVIMIENTO":       ["inventario"],
    "INVENTARIO_CORREGIDO":    ["inventario"],
    "MERMA_REGISTRADA":        ["inventario"],
    "REPOSICION_GENERADA":     ["inventario", "logistico"],
    "CLIENTE_CREADO":          ["comercial"],
    "CLIENTE_MODIFICADO":      ["comercial"],
    "CONTRATO_GENERADO":       ["rrhh", "empresa"],
    "NOMINA_GENERADA":         ["rrhh", "financiero"],
    "ASIENTO_CONTABILIZADO":   ["financiero"],
    "USUARIO_CREADO":          ["empresa"],
    "USUARIO_BLOQUEADO":       ["empresa"],
    "SINCRONIZACION_COMPLETADA": ["empresa", "logistico"],
}

# Cadena de valor por tipo de evento: (entidad_destino, relacion). El origen lo aporta el payload.
CADENA_POR_TIPO = {
    "PEDIDO_RECIBIDO":       ("recepcion", "recepcionado_en"),
    "FACTURA_GENERADA":      ("factura", "facturado_en"),
    "COBRO_REGISTRADO":      ("cobro", "cobrado_en"),
    "ASIENTO_CONTABILIZADO": ("contabilidad", "contabilizado_en"),
}

_SUSCRITO = False


def _invalidar(dominios, id_empresa):
    try:
        from src.services.gemelo import motor
        motor.servicio().invalidar(dominios, id_empresa)
    except Exception as e:
        logger.debug("invalidar %s: %s", dominios, e)


def _registrar_dependencias(ev):
    """Registra aristas de dependencia a partir de las pistas del evento (best-effort)."""
    payload = ev.get("payload") or {}
    if not isinstance(payload, dict):
        return
    emp = ev.get("id_empresa")
    # Pista explicita: el publicador indica de que entidad deriva este evento.
    origen = payload.get("dt_origen")  # {"entidad":..,"id":..}
    destino = payload.get("dt_destino")
    if isinstance(origen, dict) and isinstance(destino, dict):
        DEP.registrar(origen.get("entidad"), origen.get("id"), destino.get("entidad"),
                      destino.get("id"), id_empresa=emp, origen_evento=ev.get("id"))
        return
    # Cadena de valor por tipo: origen = ref del evento anterior indicado en payload.
    tipo = ev.get("tipo")
    if tipo in CADENA_POR_TIPO and isinstance(origen, dict):
        dest_ent, rel = CADENA_POR_TIPO[tipo]
        DEP.registrar(origen.get("entidad"), origen.get("id"), dest_ent,
                      ev.get("ref_id") or payload.get("id"), relacion=rel,
                      id_empresa=emp, origen_evento=ev.get("id"))


def _handler(ev):
    try:
        tipo = ev.get("tipo")
        dominios = MAPA_DOMINIOS.get(tipo, ["empresa"])
        _invalidar(dominios, ev.get("id_empresa"))
        _registrar_dependencias(ev)
    except Exception as e:
        logger.debug("handler gemelo: %s", e)


def suscribir() -> bool:
    """Suscribe el gemelo al Event Bus (idempotente). Se llama al iniciar el servicio."""
    global _SUSCRITO
    if _SUSCRITO:
        return True
    try:
        from src.services import eventos as EV
        EV.suscribir("*", _handler)
        _SUSCRITO = True
        logger.info("Gemelo Digital suscrito al Event Bus.")
        return True
    except Exception as e:
        logger.debug("suscribir gemelo: %s", e)
        return False
