"""
GraphQL-prep · Descriptor (Fase III · B8) — SOLO arquitectura, sin resolvers ni lógica.

Describe los tipos y consultas que una FUTURA capa GraphQL podría exponer, derivados de los mismos
recursos REST y consumiendo los MISMOS servicios (REST→servicios→dominio→BD). No se implementan
resolvers: solo se garantiza que la capa de servicios es suficiente para construir GraphQL después
sin duplicar modelos.
"""

# Tipos GraphQL previstos (derivados de los schemas REST / objetos de servicio).
TIPOS = {
    "Communication": ["com_id", "canal", "estado", "destinatario", "asunto", "contexto", "creado",
                      "conversation_id"],
    "Conversation": ["id", "correo", "asunto", "canales", "estado", "n_mensajes"],
    "Contact": ["correo", "nombre_mostrado", "tipo", "etiqueta", "empresa", "avisos", "favorito"],
    "Template": ["id", "codigo", "categoria", "idioma", "estado", "version_actual"],
    "Campaign": ["id", "nombre", "tipo", "estado", "total", "enviados", "fallidos"],
    "AuditEvent": ["fuente", "fecha", "tipo", "detalle", "actor", "ref"],
}

# Consultas previstas → servicio que las resolvería (sin implementar aún).
CONSULTAS = {
    "communications(idEmpresa, limite)": "ccp.historial_comunicaciones",
    "conversation(id)": "ccp.conversaciones.mensajes",
    "contacts(idEmpresa, q, contexto)": "ccp.buscar_destinatarios",
    "templates(idEmpresa)": "ccp.templates.listar_plantillas",
    "campaigns(idEmpresa)": "ccp.campanas.listar_campanas",
    "auditReplay(idEmpresa, comId)": "audit_replay.reconstruir",
}


def esquema_previsto() -> dict:
    """Descriptor del esquema GraphQL previsto (tipos + consultas → servicio). No ejecuta nada."""
    return {"tipos": TIPOS, "consultas": CONSULTAS,
            "nota": "Capa de solo consulta sobre servicios existentes; sin resolvers todavía."}
