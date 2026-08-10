"""
AgentManager (Paquete Enterprise 6, SUBFASE 6.1). Registra, localiza y coordina los agentes
especializados. NO realiza calculos: delega. Permite colaboracion entre agentes (6.11),
delegacion automatica (6.12), coordinacion multi-agente ("¿que deberia hacer hoy?") y estadisticas
para el panel (6.15). Extensible: registrar nuevos agentes sin tocar el manager (6.16).
"""

import logging
import time

logger = logging.getLogger("agentes.manager")


class AgentManager:
    def __init__(self):
        self._agentes = []
        self._stats = {}   # nombre -> {consultas, ultima, tiempo_total_ms}

    def registrar(self, agente) -> None:
        if agente not in self._agentes:
            self._agentes.append(agente)
            self._stats.setdefault(agente.nombre, {"consultas": 0, "ultima": None, "tiempo_total_ms": 0})

    def agentes(self) -> list:
        return list(self._agentes)

    def localizar(self, dominio):
        return next((a for a in self._agentes if a.responde(dominio)), None)

    def _track(self, nombre, ms):
        s = self._stats.setdefault(nombre, {"consultas": 0, "ultima": None, "tiempo_total_ms": 0})
        s["consultas"] += 1
        s["ultima"] = time.strftime("%Y-%m-%d %H:%M:%S")
        s["tiempo_total_ms"] += int(ms)

    def delegar(self, dominio, consulta, ctx) -> dict | None:
        """Delegacion automatica al especialista del dominio (SUBFASE 6.12). None si no hay agente."""
        a = self.localizar(dominio)
        if not a:
            return None
        # Enterprise 8 (SUBFASE 8.13): el agente consulta el Gemelo Digital ANTES de actuar.
        # Se inyecta el estado vivo del dominio en el contexto (best-effort, fuente unica).
        if "estado_twin" not in ctx:
            try:
                from src.services import gemelo
                ctx = {**ctx, "estado_twin": gemelo.servicio().contexto_dominio(dominio, ctx.get("id_empresa"))}
            except Exception as e:
                logger.debug("twin contexto agente: %s", e)
        t0 = time.perf_counter()
        try:
            r = a.responder(consulta, ctx, manager=self)
        except Exception as e:
            logger.error("agente %s: %s", a.nombre, e)
            r = {"agente": a.nombre, "texto": "El especialista no pudo responder.", "fuentes": []}
        self._track(a.nombre, (time.perf_counter() - t0) * 1000)
        r.setdefault("agente", a.nombre)
        return r

    def consultar(self, dominio, consulta, ctx) -> dict:
        """Consulta agente-a-agente (SUBFASE 6.11). Devuelve {} si no hay especialista."""
        return self.delegar(dominio, consulta, ctx) or {}

    def coordinar(self, consulta, ctx, *, dominios=None) -> dict:
        """Respuesta integrada de VARIOS agentes (SUBFASE 6.12 "¿que deberia hacer hoy?").
        Nunca genera respuestas contradictorias: agrega por especialista con su fuente."""
        doms = dominios or ["inventario", "comercial", "financiero", "compras"]
        partes, fuentes, agentes = [], set(), []
        for d in doms:
            r = self.delegar(d, consulta, ctx)
            if r and r.get("texto"):
                partes.append(f"• [{r['agente']}] {r['texto']}")
                fuentes.update(r.get("fuentes", []))
                agentes.append(r["agente"])
        return {"agente": "coordinador", "agentes": agentes, "multi": True,
                "texto": "\n".join(partes) or "Sin datos relevantes.", "fuentes": sorted(fuentes)}

    def panel(self) -> dict:
        """Panel de agentes (SUBFASE 6.15): disponibles, estado y estadisticas."""
        filas = []
        for a in self._agentes:
            s = self._stats.get(a.nombre, {})
            cons = s.get("consultas", 0)
            medio = int(s.get("tiempo_total_ms", 0) / cons) if cons else 0
            filas.append({"agente": a.nombre, "titulo": a.titulo, "dominios": list(a.dominios),
                          "estado": "activo", "consultas": cons, "ultima": s.get("ultima"),
                          "tiempo_medio_ms": medio})
        return {"total": len(self._agentes), "agentes": filas}


_manager = AgentManager()


def manager() -> AgentManager:
    # Alta perezosa de los especialistas (idempotente).
    if not _manager.agentes():
        try:
            from src.services.agentes.especialistas import AGENTES
            for a in AGENTES:
                _manager.registrar(a)
        except Exception as e:
            logger.error("registro agentes: %s", e)
    return _manager
