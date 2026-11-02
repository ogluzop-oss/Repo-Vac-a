"""
Sincroniza el resultado de `cliente.verificar_licencia()` con el estado LOCAL de licencia
(`services.saas.licensing`, tabla `empresa_licencia`) — el `enforcement.acceso_modulo()` ya
existente hace el resto sin ningún cambio: esta pieza solo escribe, nunca decide qué bloquear.

También gestiona el periodo de GRACIA sin conexión: si la instalación lleva demasiado tiempo sin
poder verificar con éxito, se restringe localmente a solo lectura — no por una confirmación de
impago (podría no haberla), sino porque llevar ese mismo tiempo offline es indistinguible de un
impago real que el servidor central no ha podido comunicar.
"""

import datetime as _dt
import logging

logger = logging.getLogger("licencia_central.sincronizacion")

# Estado del servidor central (`services.saas.suscripciones.ESTADOS`) -> estado LOCAL
# (`services.saas.licensing.ESTADOS`) que consume `enforcement.acceso_modulo()`. "vencida" (impago
# reciente, aún sin escalar) se trata como solo-lectura, no como bloqueo total — el bloqueo total
# solo llega si el servidor central ya la canceló de verdad (secuencia de `saas.dunning`).
_MAPA_ESTADOS = {
    "activa": "activa",
    "prueba": "prueba",
    "suspendida": "suspendida",
    "vencida": "suspendida",
    "cancelada": "cancelada",
}

DIAS_GRACIA_SIN_CONEXION = 30


def _hoy_iso() -> str:
    return _dt.date.today().isoformat()


def procesar_respuesta(respuesta: dict, id_empresa) -> None:
    """Aplica el resultado de una verificación EXITOSA al estado local y renueva la marca de
    "última verificación con éxito" (la que cuenta para el periodo de gracia)."""
    from src.services.licencia_central import identidad
    datos = identidad._leer()
    datos["ultima_verificacion_ok"] = _hoy_iso()
    identidad._escribir(datos)

    plan = (respuesta.get("plan") or "BASIC").upper()
    estado_central = respuesta.get("estado") or "activa"
    estado_local = _MAPA_ESTADOS.get(estado_central, "suspendida")
    try:
        from src.services.saas import licensing
        licensing.asignar_plan(id_empresa, plan, estado=estado_local)
        logger.info("Licencia local sincronizada: plan=%s estado=%s (servidor central: %s)",
                   plan, estado_local, estado_central)
    except Exception as e:
        logger.error("No se pudo sincronizar la licencia local: %s", e)


def revisar_periodo_gracia(id_empresa) -> None:
    """Se llama cuando `verificar_licencia()` devolvió `None` (no se pudo comprobar). Si la
    instalación está activada pero lleva más de `DIAS_GRACIA_SIN_CONEXION` sin verificar con
    éxito, restringe localmente a solo lectura. Una instalación activada que TODAVÍA no ha hecho
    ninguna verificación con éxito no se sanciona (podría ser la primera vez, offline)."""
    from src.services.licencia_central import identidad
    if not identidad.activado():
        return
    datos = identidad._leer()
    ultima = datos.get("ultima_verificacion_ok")
    if not ultima:
        return
    try:
        fecha_ultima = _dt.date.fromisoformat(ultima)
    except Exception:
        return
    dias = (_dt.date.today() - fecha_ultima).days
    if dias <= DIAS_GRACIA_SIN_CONEXION:
        return
    try:
        from src.services.saas import licensing
        lic = licensing.licencia_activa(id_empresa)
        if lic and lic.get("estado") == "activa":
            licensing.asignar_plan(id_empresa, lic["codigo_plan"], estado="suspendida")
            logger.warning(
                "%s días sin poder verificar la licencia con el servidor central: "
                "acceso restringido a solo lectura hasta que se restablezca la conexión.", dias)
    except Exception as e:
        logger.error("revisar_periodo_gracia: %s", e)


def ejecutar_verificacion() -> None:
    """Punto de entrada ÚNICO para el hilo periódico (ver `main.py`). Nunca lanza: cualquier fallo
    queda registrado y la instalación sigue funcionando con el último estado local conocido."""
    try:
        from src.services.licencia_central import cliente, identidad
        if not identidad.activado():
            return
        from src.db.empresa import empresa_actual_id
        id_empresa = empresa_actual_id()
        respuesta = cliente.verificar_licencia()
        if respuesta:
            procesar_respuesta(respuesta, id_empresa)
        else:
            revisar_periodo_gracia(id_empresa)
    except Exception as e:
        logger.error("ejecutar_verificacion: %s", e)
