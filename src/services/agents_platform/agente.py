"""
AI Agents Platform · Agente (Fase V · Bloque 5). Un agente especializado como MÓDULO independiente
que combina el conocimiento del Especialista IA de su dominio (reutiliza `services.agentes`) con las
capacidades transversales (Workflow, CCP, Rules, Documental). Cada agente es autónomo pero se apoya
100% en la infraestructura existente. Multiempresa.
"""

from __future__ import annotations

from src.services.agents_platform import capacidades


class AgentePlataforma:
    """Agente de un dominio (compras, ventas, rrhh…). Expone las capacidades sobre su dominio."""

    def __init__(self, dominio, *, nombre=None):
        self.dominio = dominio
        self.nombre = nombre or dominio.upper()

    # ── conocimiento (Especialistas IA) ──
    def consultar(self, consulta, *, id_empresa=None, usuario=None):
        return capacidades.consultar(self.dominio, consulta, id_empresa=id_empresa, usuario=usuario)

    def analizar(self, consulta, *, id_empresa=None, usuario=None):
        return capacidades.analizar(self.dominio, consulta, id_empresa=id_empresa, usuario=usuario)

    def proponer(self, *, id_empresa=None, usuario=None):
        return capacidades.proponer(self.dominio, id_empresa=id_empresa, usuario=usuario)

    def responder(self, consulta, *, id_empresa=None, usuario=None):
        return self.consultar(consulta, id_empresa=id_empresa, usuario=usuario)

    # ── acción (infraestructura existente) ──
    def automatizar(self, regla, datos, *, id_empresa=None):
        return capacidades.automatizar(regla, datos, id_empresa=id_empresa)

    def generar_documento(self, tipo, datos, *, id_empresa=None, usuario=None):
        return capacidades.generar_documento(tipo, datos, id_empresa=id_empresa, usuario=usuario)

    def iniciar_workflow(self, entidad, entidad_id, *, id_empresa=None, actor=None, contexto=None):
        return capacidades.iniciar_workflow(entidad, entidad_id, id_empresa=id_empresa, actor=actor,
                                            contexto=contexto)

    def solicitar_aprobacion(self, entidad, entidad_id, *, id_empresa=None, actor=None):
        return capacidades.solicitar_aprobacion(entidad, entidad_id, id_empresa=id_empresa,
                                                actor=actor)

    def enviar_comunicacion(self, *, id_empresa=None, **kw):
        return capacidades.enviar_comunicacion(id_empresa=id_empresa, **kw)

    def capacidades(self):
        return list(capacidades.CAPACIDADES)

    def descriptor(self):
        return {"dominio": self.dominio, "nombre": self.nombre,
                "capacidades": self.capacidades(), "modulo_independiente": True}


__all__ = ["AgentePlataforma"]
