"""
Catálogo EXTENSIBLE de tipos de delegación a SOMA — cada tipo mapea un módulo + evento disparador
(o "manual", sin disparador automático) a un `ejecutor(regla, contexto, *, id_empresa) -> dict`
concreto. Registro vía `registrar_tipo` (mismo patrón que `services.automatizacion.acciones.
registrar_accion`): sumar un módulo nuevo es añadir una entrada aquí, nunca tocar el motor.

`ejecutor(regla, contexto, *, id_empresa) -> dict` siempre devuelve:
    {"ok": bool, "estado": "aplicado"|"pendiente_revision"|"descartado"|"error",
     "decision": dict|None, "detalle": str}

No existe ninguna pantalla propia de "Delegación a SOMA" en el menú principal — cada tipo se
gestiona desde una pestaña "Delegación IA" dentro de la ventana del módulo al que pertenece
(`pantalla`, ver `gui.soma_delegacion_gui.DelegacionSomaPanel`).
"""

import logging

logger = logging.getLogger("soma_delegacion.catalogo")

_TIPOS: dict[str, dict] = {}


def registrar_tipo(codigo, *, modulo, pantalla, nombre, descripcion, evento=None, ejecutor,
                   contexto_desde_evento=None, ejemplo_instrucciones=""):
    """`modulo` es solo la etiqueta de agrupación que ve el SUPERADMIN; `pantalla` es el
    identificador de la ventana GUI que aloja la pestaña "Delegación IA" de este tipo (p. ej.
    "correo", "crm", "sat", "compras_avanzado", "configuracion") — lo usa
    `DelegacionSomaPanel(pantalla=...)` para filtrar qué tipos mostrar en cada ventana.

    `evento` es el nombre publicado en el Event Bus (`services.eventos`) que dispara este tipo
    automáticamente; None = solo se invoca manualmente (p. ej. un botón "Generar con SOMA" en la
    propia pantalla del módulo, no una reacción a un evento). `contexto_desde_evento(ev) ->
    dict|None` traduce el payload genérico del Event Bus al `contexto` que espera `ejecutor` —
    obligatorio si `evento` está definido (es lo que permite que `wiring.py` se suscriba de forma
    genérica sin saber nada del dominio de cada tipo)."""
    _TIPOS[codigo] = {"codigo": codigo, "modulo": modulo, "pantalla": pantalla, "nombre": nombre,
                      "descripcion": descripcion, "evento": evento, "ejecutor": ejecutor,
                      "contexto_desde_evento": contexto_desde_evento,
                      "ejemplo_instrucciones": ejemplo_instrucciones}


def obtener(codigo) -> dict | None:
    return _TIPOS.get(codigo)


def listar() -> list:
    return sorted(_TIPOS.values(), key=lambda t: (t["modulo"], t["nombre"]))


def por_pantalla(pantalla) -> list:
    return [t for t in _TIPOS.values() if t.get("pantalla") == pantalla]


def por_evento(evento) -> list:
    return [t for t in _TIPOS.values() if t.get("evento") == evento]


def _registrar_tipos_integrados():
    """Importa perezosamente los ejecutores reales y los registra — perezoso para que importar
    este módulo nunca arrastre (ni falle por) las dependencias de cada dominio de negocio."""
    try:
        from src.services.soma_delegacion.ejecutores import correo as _correo
        registrar_tipo(
            "correo.responder_automatico", modulo="Correo", pantalla="correo",
            evento="CORREO_RECIBIDO", nombre="Responder correos automáticamente",
            descripcion="SOMA redacta (y, en modo automático, envía) una respuesta a un correo "
                       "entrante cuando encaja con las instrucciones dadas.",
            ejecutor=_correo.ejecutar_respuesta_correo,
            contexto_desde_evento=_correo.contexto_desde_evento,
            ejemplo_instrucciones=(
                "Responde automáticamente solo a correos que pregunten por el horario de "
                "apertura o la ubicación de la tienda, con un tono cercano y profesional. Si el "
                "correo trata cualquier otro asunto (reclamaciones, pedidos, facturación…), no "
                "respondas — un humano debe encargarse."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo correo.responder_automatico: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import crm as _crm
        registrar_tipo(
            "crm.generar_presupuesto", modulo="CRM", pantalla="crm", evento=None,
            nombre="Generar presupuestos para clientes",
            descripcion="SOMA redacta un borrador de presupuesto (líneas, cantidades, "
                       "observaciones) a partir de una breve descripción de lo que pide el "
                       "cliente — siempre como borrador, pendiente de tu aprobación manual.",
            ejecutor=_crm.ejecutar_generar_presupuesto,
            ejemplo_instrucciones=(
                "Aplica un 10% de descuento en presupuestos para clientes habituales (más de 5 "
                "compras). No incluyas artículos descatalogados. Añade siempre una observación "
                "indicando el plazo de validez de 15 días."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo crm.generar_presupuesto: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import centros as _centros
        registrar_tipo(
            "configuracion.autorrelleno_centro", modulo="Configuración", pantalla="configuracion",
            evento="CENTRO_CREADO", nombre="Autorrellenar datos de un centro nuevo",
            descripcion="SOMA completa los campos vacíos de un centro recién creado (país, "
                       "teléfono, email, provincia, municipio…) con los datos corporativos de "
                       "la empresa — nunca sobrescribe un dato ya introducido a mano.",
            ejecutor=_centros.ejecutar_autorrelleno_centro,
            contexto_desde_evento=_centros.contexto_desde_evento,
            ejemplo_instrucciones=(
                "Rellena los datos de contacto y localización de cualquier centro nuevo con los "
                "datos fiscales de la empresa, salvo el nombre del centro (que debe quedar "
                "siempre en blanco para que lo decida la persona que lo crea)."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo configuracion.autorrelleno_centro: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import autorrelleno_entidad as _ae
        registrar_tipo(
            "configuracion.autorrelleno_cliente", modulo="CRM", pantalla="crm",
            evento="CLIENTE_CREADO", nombre="Autorrellenar datos de un cliente nuevo",
            descripcion="SOMA propone valores para los campos vacíos de un cliente recién dado "
                       "de alta (condiciones de pago, régimen fiscal, país…), siguiendo la "
                       "política que describas — nunca sobrescribe un dato ya introducido.",
            ejecutor=_ae.ejecutar_autorrelleno_cliente,
            contexto_desde_evento=_ae.contexto_desde_evento_cliente,
            ejemplo_instrucciones=(
                "Los clientes nuevos sin país indicado son de España. Por defecto, condiciones "
                "de pago a 30 días y régimen fiscal general, salvo que el NIF tenga formato "
                "extranjero, en cuyo caso márcalo como intracomunitario si es de la UE."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo configuracion.autorrelleno_cliente: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import autorrelleno_entidad as _ae
        registrar_tipo(
            "configuracion.autorrelleno_proveedor", modulo="Compras", pantalla="compras_avanzado",
            evento="PROVEEDOR_CREADO", nombre="Autorrellenar datos de un proveedor nuevo",
            descripcion="SOMA propone valores para los campos vacíos de un proveedor recién "
                       "dado de alta (plazo de pago, divisa, pedido mínimo…), siguiendo la "
                       "política que describas — nunca sobrescribe un dato ya introducido.",
            ejecutor=_ae.ejecutar_autorrelleno_proveedor,
            contexto_desde_evento=_ae.contexto_desde_evento_proveedor,
            ejemplo_instrucciones=(
                "Proveedores nacionales: plazo de pago a 60 días, divisa EUR. Proveedores cuyo "
                "nombre o email sugiera que son extranjeros: plazo de pago a 30 días y revisa si "
                "la divisa debería ser distinta del euro."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo configuracion.autorrelleno_proveedor: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import sat as _sat
        registrar_tipo(
            "sat.responder_ticket", modulo="Posventa", pantalla="sat", evento="TICKET_CREADO",
            nombre="Responder tickets de soporte automáticamente",
            descripcion="SOMA redacta (y, en modo automático, publica) una primera respuesta a "
                       "un ticket de soporte nuevo cuando encaja con las instrucciones dadas.",
            ejecutor=_sat.ejecutar_respuesta_ticket,
            contexto_desde_evento=_sat.contexto_desde_evento,
            ejemplo_instrucciones=(
                "Responde automáticamente solo a tickets que pregunten cómo hacer una "
                "devolución, indicando el plazo de 30 días y el enlace al formulario de "
                "devoluciones. Cualquier otro asunto (avería, reclamación, facturación) debe "
                "esperar a un técnico — no respondas."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo sat.responder_ticket: %s", e)

    try:
        from src.services.soma_delegacion.ejecutores import compras as _compras
        registrar_tipo(
            "compras.generar_pedido", modulo="Compras", pantalla="compras_avanzado", evento=None,
            nombre="Generar pedidos de compra a proveedor",
            descripcion="SOMA redacta un borrador de pedido de compra (líneas, cantidades) a un "
                       "proveedor a partir de una breve descripción de lo que hace falta — "
                       "siempre como borrador, pendiente de tu aprobación manual.",
            ejecutor=_compras.ejecutar_generar_pedido,
            ejemplo_instrucciones=(
                "Pide siempre en múltiplos de la unidad de caja cuando el artículo la tenga "
                "definida. No incluyas artículos de proveedores bloqueados u homologación "
                "caducada. Añade una observación pidiendo confirmación de plazo de entrega."))
    except Exception as e:
        logger.warning("No se pudo registrar el tipo compras.generar_pedido: %s", e)


_registrar_tipos_integrados()
