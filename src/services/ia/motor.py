"""
Motor central de IA (SUBFASE 1) — `IAService`, punto UNICO de entrada para toda la app
(Dashboard, Centro de Actividad, Timeline, BI, Workflow, CRM, Inventario, Facturacion, RRHH,
Compras, TPV, Tesoreria). Incluye memoria operativa en proceso (SUBFASE 10).

La IA solo LEE/analiza/explica/predice/recomienda (SUBFASE 12). Nunca modifica datos ni ejecuta
Workflow: las acciones las decide el humano o el motor Workflow/BPM existente.
"""

import logging

from src.services.ia import (analisis, anomalias, cache, configuracion,
                             consultas, predicciones, recomendaciones,
                             resumenes, riesgos)

logger = logging.getLogger("ia.motor")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


class IAService:
    """Fachada unica de la capa de IA. Desacoplada, multiempresa, read-only."""

    def __init__(self):
        self._memoria = {}   # {usuario: {"empresa","tienda","periodo","consultas":[...]}}

    # ── Memoria operativa (SUBFASE 10, en proceso; nada sensible se persiste) ──
    def recordar(self, usuario, **contexto):
        m = self._memoria.setdefault(str(usuario), {"consultas": []})
        m.update({k: v for k, v in contexto.items() if k != "consulta"})
        if contexto.get("consulta"):
            m["consultas"] = (m.get("consultas", []) + [contexto["consulta"]])[-20:]
        return m

    def contexto(self, usuario):
        return self._memoria.get(str(usuario), {})

    # ── Capacidades (SUBFASE 2-6, 9) ──
    def resumen(self, id_empresa=None, *, periodo="dia", usuario=None, perfil=None):
        if not configuracion.activo("resumenes", id_empresa):
            return {"periodo": periodo, "texto": "Resumenes IA desactivados.", "por_tipo": []}
        return resumenes.resumen(id_empresa, periodo=periodo, usuario=usuario, perfil=perfil)

    def anomalias(self, id_empresa=None):
        return [a.to_dict() for a in anomalias.detectar(id_empresa)]

    def recomendaciones(self, id_empresa=None, *, limite=30):
        return [r.to_dict() for r in recomendaciones.generar(id_empresa, limite=limite)]

    def predicciones(self, id_empresa=None):
        # SUBFASE 3.12: la IA NO calcula; DELEGA en el motor predictivo (PredictionService).
        try:
            from src.services import prediccion
            return prediccion.servicio().predicciones(id_empresa)
        except Exception as e:
            logger.debug("predicciones via PredictionService: %s", e)
            return [p.to_dict() for p in predicciones.predecir(id_empresa)]

    def riesgos(self, id_empresa=None):
        try:
            from src.services import prediccion
            return prediccion.servicio().riesgos(id_empresa)
        except Exception:
            return [r.to_dict() for r in riesgos.evaluar(id_empresa)]

    def predecir_futuro(self, texto, id_empresa=None):
        """¿Que ocurrira? — DELEGA en PredictionService (SUBFASE 3.12)."""
        try:
            from src.services import prediccion
            return prediccion.servicio().responder_futuro(texto, id_empresa)
        except Exception as e:
            logger.debug("predecir_futuro: %s", e)
            return {"intent": "prediccion", "texto": "Motor predictivo no disponible."}

    def panel_predictivo(self, id_empresa=None):
        try:
            from src.services import prediccion
            return prediccion.servicio().panel_predictivo(id_empresa)
        except Exception:
            return {}

    def analisis_bi(self, id_empresa=None, *, periodo="mes"):
        return [i.to_dict() for i in analisis.interpretar_kpis(id_empresa, periodo=periodo)]

    # ── ¿Que ha pasado? (usa AGRUPACION, no recorre millones de eventos) ──
    def que_ha_pasado(self, id_empresa=None, *, periodo="dia", usuario=None, perfil=None) -> dict:
        dias = {"dia": 1, "semana": 7, "mes": 30, "anio": 365}.get(periodo, 1)
        grupos = []
        try:
            from src.services.actividad import agrupacion
            grupos = agrupacion.resumen_ejecutivo(id_empresa, usuario=usuario, perfil=perfil, dias=dias)
        except Exception as e:
            logger.debug("que_ha_pasado: %s", e)
        top = sorted(grupos, key=lambda x: x.get("total", 0), reverse=True)
        lineas = [f"{g['total']} {str(g.get('tipo_legible') or g.get('tipo')).lower()}"
                  for g in top[:8] if g.get("total")]
        try:
            from src.services.actividad import sincronizacion
            off = len([t for t in sincronizacion.panel(id_empresa)
                       if str(t.get("estado")).upper() == "OFFLINE"])
            if off:
                lineas.append(f"{off} tiendas offline")
        except Exception:
            pass
        cab = {"dia": "Hoy", "semana": "Esta semana", "mes": "Este mes", "anio": "Este año"}.get(periodo, "Hoy")
        texto = f"{cab}: " + "; ".join(lineas) + "." if lineas else f"{cab}: sin actividad relevante."
        return {"periodo": periodo, "grupos": grupos, "texto": texto}

    # ── Consultas en lenguaje natural (SUBFASE 7) ──
    def preguntar(self, texto, id_empresa=None, *, usuario=None, perfil=None):
        if usuario is not None:
            self.recordar(usuario, empresa=_emp(id_empresa), consulta=texto)
        return consultas.responder(texto, id_empresa, usuario=usuario, perfil=perfil).to_dict()

    # ── Bloque para el Centro de Actividad (SUBFASE 8) ──
    def panel_centro(self, id_empresa=None, *, usuario=None, perfil=None) -> dict:
        clave = f"ia_panel:{_emp(id_empresa)}:{usuario}"
        cacheado = cache.get(clave)
        if cacheado is not None:
            return cacheado
        res = self.resumen(id_empresa, periodo="dia", usuario=usuario, perfil=perfil)
        panel = {
            "resumen": res.get("texto", ""),
            "destacados": res.get("destacados", []),
            "alertas": self.anomalias(id_empresa),
            "recomendaciones": self.recomendaciones(id_empresa, limite=6),
            "pendientes": res.get("puntos_atencion", []),
            "prediccion_alertas": [],
            "prediccion_titulares": [],
        }
        # SUBFASE 3.11: complementa el panel con alertas predictivas (no sustituye BI).
        try:
            from src.services import prediccion
            pp = prediccion.servicio().panel_predictivo(id_empresa)
            panel["prediccion_alertas"] = pp.get("alertas", [])[:6]
            panel["prediccion_titulares"] = pp.get("titulares", [])
        except Exception:
            pass
        # Enterprise 4 (SUBFASE 4.9): panel de automatizaciones en el Centro.
        panel["automatizacion"] = {}
        try:
            from src.services import automatizacion
            panel["automatizacion"] = automatizacion.panel.resumen(id_empresa)
        except Exception:
            pass
        return cache.set(clave, panel, ttl=30)

    def configuracion(self, id_empresa=None):
        return configuracion.estado(id_empresa)

    # ── Estado global via Gemelo Digital (Enterprise 8, SUBFASE 8.11) ──
    # La IA conoce el estado de la empresa EXCLUSIVAMENTE a traves del DigitalTwinService,
    # nunca consultando decenas de modulos por su cuenta.
    def estado_empresa(self, id_empresa=None) -> dict:
        try:
            from src.services import gemelo
            return gemelo.servicio().estado_empresa(id_empresa)
        except Exception as e:
            logger.debug("estado_empresa via gemelo: %s", e)
            return {"texto": "El Gemelo Digital no esta disponible.", "dominios": {}}

    def estado_dominio(self, dominio, id_empresa=None) -> dict:
        try:
            from src.services import gemelo
            return gemelo.servicio().contexto_dominio(dominio, id_empresa)
        except Exception as e:
            logger.debug("estado_dominio via gemelo: %s", e)
            return {}

    # ── Simulacion what-if via SimulationService (Enterprise 9, SUBFASE 9.10) ──
    # "¿Que ocurriria si subimos los precios un 5%?" / "¿Y si abrimos otra tienda?"
    def simular(self, texto, id_empresa=None) -> dict:
        try:
            from src.services import simulador
            vs = simulador.lenguaje.parsear(texto)
            if not vs:
                return {"intent": "simulacion", "texto": "No he identificado que variable simular. "
                        "Prueba: «¿que ocurriria si subimos los precios un 5%?».", "variables": []}
            r = simulador.servicio().simular_directo(vs, id_empresa)
            dif = {d["metrica"]: d for d in r["diferencias"]}
            txt = (f"Simulacion (VIRTUAL, no afecta a datos reales): ingresos "
                   f"{dif['ingresos']['delta_pct']:+.1f}%, beneficio {dif['beneficio']['delta_pct']:+.1f}%, "
                   f"margen resultante {r['simulado']['margen_pct']}%. Riesgo: {r['riesgo']['nivel']}. "
                   f"Confianza: {r['confianza']}.")
            return {"intent": "simulacion", "texto": txt, "variables": vs, "resultado": r,
                    "fuentes": ["SimulationService", "Gemelo Digital", "PredictionService"]}
        except Exception as e:
            logger.debug("simular: %s", e)
            return {"intent": "simulacion", "texto": "El simulador no esta disponible.", "variables": []}

    # ── Recomendacion sobre un plan de ejecucion (Enterprise 10, SUBFASE 10.10) ──
    # "¿Es recomendable ejecutar este plan?" / "¿Que riesgos quedan?" / "¿Que revisar antes?"
    def recomendar_ejecucion(self, id_plan, id_empresa=None) -> dict:
        try:
            from src.services import autonomia
            r = autonomia.servicio().recomendacion_ia(id_plan, id_empresa)
            return {"intent": "ejecucion.recomendacion", "texto": r["texto"], "resultado": r,
                    "fuentes": r.get("fuentes", ["IAService", "ExecutiveActionService"])}
        except Exception as e:
            logger.debug("recomendar_ejecucion: %s", e)
            return {"intent": "ejecucion.recomendacion", "texto": "El servicio de autonomia no esta disponible."}


_service = IAService()


def servicio() -> IAService:
    return _service
