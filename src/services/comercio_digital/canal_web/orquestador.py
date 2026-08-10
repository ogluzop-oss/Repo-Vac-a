"""
Canal Web · ORQUESTADOR del ecosistema web (Fase WEB-02). El Canal Web pasa a ser el PUNTO DE ENTRADA que
decide CÓMO trabaja cada empresa con Internet — nada más. NO gestiona integraciones comerciales (eso es del
Marketplace) ni conoce WooCommerce/Shopify. Reutiliza el servicio Canal Web existente (N7): no crea motores.

Flujo inicial (asistente):
    ¿La empresa ya dispone de una página web?
      • NO  → crear una web profesional con **Hostinger** (proveedor oficial; arquitectura PREPARADA).
      • SÍ  → redirigir a **Marketplace › Integraciones Comerciales** (Marketplace realiza la conexión).

Este módulo sólo ORQUESTA/decide y registra la web creada; la publicación/sync/pickup/métricas/transacciones
siguen en el servicio Canal Web (sin cambios de contrato).
"""

import logging

logger = logging.getLogger("canal_web.orquestador")

# Escenarios del asistente inicial.
SIN_WEB = "SIN_WEB"   # → Hostinger (crear)
CON_WEB = "CON_WEB"   # → Marketplace (integraciones comerciales)

# Destinos de redirección (identificadores estables; la GUI los resuelve).
DESTINO_HOSTINGER = "canal_web.crear.hostinger"
DESTINO_INTEGRACIONES = "marketplace.integraciones_comerciales"


def tiene_web(id_empresa=None) -> bool:
    """True si la empresa YA tiene un canal web registrado (reutiliza canal_web.existe)."""
    try:
        from src.services.comercio_digital import canal_web
        return bool(canal_web.existe(id_empresa))
    except Exception as e:
        logger.debug("tiene_web: %s", e)
        return False


def escenario_recomendado(id_empresa=None) -> str:
    """Sugerencia inicial del asistente según el estado actual (el usuario decide en la GUI)."""
    return CON_WEB if tiene_web(id_empresa) else SIN_WEB


def flujo_inicial(id_empresa=None) -> dict:
    """Estado del asistente: la pregunta, la sugerencia y las DOS opciones posibles (sin ejecutar nada)."""
    return {
        "pregunta": "¿La empresa ya dispone de una página web?",
        "tiene_web_registrada": tiene_web(id_empresa),
        "recomendado": escenario_recomendado(id_empresa),
        "opciones": {
            SIN_WEB: {
                "titulo": "No dispone de página web",
                "accion": "Crear una página web profesional con Hostinger",
                "destino": DESTINO_HOSTINGER,
            },
            CON_WEB: {
                "titulo": "Ya dispone de página web",
                "accion": "Conectar la plataforma existente desde Marketplace › Integraciones Comerciales",
                "destino": DESTINO_INTEGRACIONES,
            },
        },
    }


def elegir(id_empresa=None, *, tiene_web_ya: bool) -> dict:
    """Resuelve la elección del usuario → destino. NO ejecuta la creación ni la conexión (arquitectura
    preparada). El Canal Web SÓLO redirige; Marketplace realiza la integración; Hostinger crea la web."""
    if tiene_web_ya:
        return {"escenario": CON_WEB, "destino": DESTINO_INTEGRACIONES,
                "mensaje": "Redirigiendo a Marketplace › Integraciones Comerciales."}
    return {"escenario": SIN_WEB, "destino": DESTINO_HOSTINGER,
            "mensaje": "Iniciar el asistente de creación de web con Hostinger (proveedor oficial)."}


def registrar_web_creada(*, id_empresa=None, usuario=None, dominio=None, nombre=None,
                         proveedor="hostinger", config_negocio=None) -> dict:
    """Registra en Smart Manager una web CREADA (p. ej. por Hostinger) reutilizando el servicio Canal Web
    (crear/guardar_presencia). Aditivo; no rompe contratos. La integración real con Hostinger se implementará
    después (aquí sólo se deja el punto de registro/vinculación)."""
    from src.services.comercio_digital import canal_web
    cfg = dict(config_negocio or {})
    if nombre:
        cfg.setdefault("nombre", nombre)
    try:
        if not canal_web.existe(id_empresa):
            r = canal_web.crear(config_negocio=cfg, id_empresa=id_empresa, usuario=usuario)
        else:
            r = canal_web.actualizar_config(cfg, id_empresa=id_empresa, usuario=usuario)
        # Marca de presencia (nombre) + dominio quedan en el servicio Canal Web / gestion_dominios.
        if dominio:
            try:
                from src.services.comercio_digital.canal_web import gestion_dominios
                gestion_dominios.cambiar_dominio(dominio, id_empresa=id_empresa, usuario=usuario)
            except Exception as e:
                logger.debug("registrar dominio: %s", e)
        _audit(id_empresa, usuario, proveedor, dominio)
        return {"ok": True, "proveedor": proveedor, "dominio": dominio, "resultado": r}
    except Exception as e:
        logger.error("registrar_web_creada: %s", e)
        return {"ok": False, "error": str(e)}


def _audit(id_empresa, usuario, proveedor, dominio):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("canal_web", "WEB_REGISTRADA", "canal_web",
                      f"emp={id_empresa} prov={proveedor} dom={dominio} por={usuario}")
    except Exception:
        pass


__all__ = ["SIN_WEB", "CON_WEB", "DESTINO_HOSTINGER", "DESTINO_INTEGRACIONES",
           "tiene_web", "escenario_recomendado", "flujo_inicial", "elegir", "registrar_web_creada"]
