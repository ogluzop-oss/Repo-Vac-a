"""
Contrato base de los agentes especializados (Paquete Enterprise 6). Un agente NO accede a la BD
directamente ni duplica logica: solo aporta conocimiento ESPECIALIZADO reutilizando IAService,
PredictionService, AutomationService, Centro de Actividad y BI. Toda respuesta es EXPLICABLE
(agente + fuentes + datos/predicciones) y nunca inventa.
"""


def respuesta(agente, texto, *, fuentes=None, datos=None, predicciones=None,
              automatizaciones=None, extra=None) -> dict:
    r = {"agente": agente, "texto": texto or "", "fuentes": list(fuentes or []),
         "datos": datos, "predicciones": predicciones or [], "automatizaciones": automatizaciones or []}
    if extra:
        r.update(extra)
    return r


class Agente:
    """Contrato de agente especializado. Los agentes se registran en el AgentManager y solo
    coordinan servicios existentes; no realizan escrituras ni consultas SQL propias."""

    nombre = "base"
    titulo = "Agente base"
    dominios = ()          # dominios de intencion que atiende (ventas, stock, tesoreria...)

    def responde(self, dominio) -> bool:
        return str(dominio) in self.dominios

    def responder(self, consulta, ctx, *, manager=None) -> dict:
        raise NotImplementedError

    # ── Helpers reutilizables (delegan en los servicios Enterprise) ──
    def _ia(self, consulta, ctx):
        from src.services import ia
        return ia.servicio().preguntar(consulta, ctx.get("id_empresa"),
                                       usuario=ctx.get("usuario"), perfil=ctx.get("rol"))

    def _prediccion(self):
        from src.services import prediccion
        return prediccion.servicio()

    def _emp(self, ctx):
        return ctx.get("id_empresa")

    def _twin(self, ctx):
        """Enterprise 8 (SUBFASE 8.13): estado vivo del dominio segun el Gemelo Digital.

        Cada agente consulta el gemelo (fuente unica de estado) ANTES de actuar, en lugar de
        cruzar consultas entre modulos. El manager ya lo inyecta en ctx['estado_twin']; si no,
        se pide al DigitalTwinService directamente."""
        est = ctx.get("estado_twin")
        if est is not None:
            return est
        try:
            from src.services import gemelo
            dom = self.dominios[0] if self.dominios else "empresa"
            return gemelo.servicio().contexto_dominio(dom, ctx.get("id_empresa"))
        except Exception:
            return {}
