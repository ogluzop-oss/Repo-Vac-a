"""
Motor del Copiloto Empresarial (Paquete Enterprise 5, SUBFASE 5.1) — `CopilotService`.

Fachada UNICA de interaccion en lenguaje natural con TODO Smart Manager AI. NO calcula: coordina.
Orquesta IAService + PredictionService + AutomationService + Centro de Actividad + Workflow/BPM,
reutilizandolos por completo. Con contexto (5.3), memoria (5.4), respuestas enriquecidas y
explicables (5.5/5.7), acciones orquestadas (5.6), recomendaciones contextuales (5.8) y seguridad
por rol (5.12). Multiempresa/multitienda. Asincrono cuando procede (5.13).
"""

import logging
import threading

from src.services.copilot import (acciones, contexto, intencion, memoria,
                                  respuestas, seguridad)

logger = logging.getLogger("copilot.motor")


class CopilotService:

    def _responder_prediccion(self, texto, ctx):
        """Hook de IA predictiva conversacional (Fase 7): delega en el motor real y devuelve respuesta
        explicable. None si la pregunta no es de previsión (para seguir con el flujo normal)."""
        try:
            from src.services.prediccion import consulta
            r = consulta.responder(texto, ctx["id_empresa"])
            if not r.get("aplicable"):
                return None
            return {"intent": "prediccion", "texto": r.get("texto", ""), "fuentes": ["PredictiveEngine"],
                    "prediccion": r, "contexto": ctx}
        except Exception:
            return None

    def preguntar(self, texto, usuario=None, id_empresa=None) -> dict:
        ctx = contexto.resolver(usuario, id_empresa)
        emp, rol, uid = ctx["id_empresa"], ctx["rol"], ctx["usuario"]
        cls = intencion.clasificar(texto, memoria.contexto(uid))

        # Enterprise 10 (SUBFASE 10.9): ejecucion supervisada conversacional. Capacidad ejecutiva:
        # se detecta ANTES del gate por dominio y se restringe a roles globales. Nunca ejecuta sin
        # autorizacion valida (plan APROBADO + Gobierno + Workflow).
        eje = self._responder_ejecucion(texto, ctx)
        if eje is not None:
            memoria.recordar(uid, dominio="ejecucion", consulta=texto)
            return eje

        # Enterprise 9 (SUBFASE 9.11): simulacion / escenarios what-if conversacionales. Es una
        # herramienta EJECUTIVA transversal (no un dominio concreto), por lo que se detecta ANTES
        # del gate por dominio y se restringe a roles globales dentro del propio hook.
        sim = self._responder_simulacion(texto, ctx)
        if sim is not None:
            memoria.recordar(uid, dominio="simulacion", consulta=texto)
            return sim

        # Fase 7 (IA predictiva conversacional): preguntas de previsión/demanda → PredictiveEngine REAL
        # (services/prediccion/consulta → forecasting). SOMA NO calcula la predicción; delega en el motor y
        # devuelve una respuesta EXPLICABLE (modelo/tipo/confianza) o "no hay datos suficientes".
        pred = self._responder_prediccion(texto, ctx)
        if pred is not None:
            memoria.recordar(uid, dominio="prediccion", consulta=texto)
            return pred

        # SUBFASE 5.12: seguridad por rol.
        if not seguridad.permite(cls["dominio"], rol):
            memoria.recordar(uid, consulta=texto)
            return {"intent": "denegado",
                    "texto": f"Tu rol ({rol}) no tiene acceso a informacion de «{cls['dominio']}».",
                    "fuentes": ["Seguridad"], "contexto": ctx}

        # SUBFASE 5.6: acciones desde la conversacion (delega en AutomationService/Workflow).
        if cls["es_accion"]:
            r = acciones.solicitar(cls, texto, ctx)
            memoria.recordar(uid, dominio=cls["dominio"], consulta=texto)
            return {"intent": "accion." + r.get("accion", ""), "texto": r.get("texto", ""),
                    "accion": r, "fuentes": r.get("fuentes", ["AutomationService"]), "contexto": ctx}

        # Enterprise 8 (SUBFASE 8.12): estado global/tienda desde el Gemelo Digital.
        # "¿Como esta la empresa?", "estado general", "¿que ocurre en la tienda de Valencia?".
        gt = self._responder_estado(texto, ctx)
        if gt is not None:
            memoria.recordar(uid, dominio="estado", consulta=texto)
            return gt

        # SUBFASE 5.4: seguimiento → reconstruye la consulta con el dominio recordado.
        texto_ef = texto
        if cls["es_seguimiento"] and cls["dominio"] != "general":
            texto_ef = f"{cls['dominio']} {cls.get('periodo') or ''}".strip()

        # Enterprise 6 (SUBFASE 6.12): DELEGA en el agente especialista, o COORDINA varios.
        base = None
        try:
            from src.services.agentes import manager as _agm
            mgr = _agm()
            tl = (texto or "").lower()
            if any(k in tl for k in ("deberia hacer", "debería hacer", "que hago hoy",
                                     "qué hago hoy", "prioridades", "que hacer hoy")):
                r = mgr.coordinar(texto, ctx)
                base = {"intent": "multi-agente", "texto": r["texto"], "datos": None,
                        "fuentes": r["fuentes"], "agente": "coordinador", "agentes": r.get("agentes", [])}
            else:
                ag = mgr.delegar(cls["dominio"], texto_ef, ctx)
                if ag and ag.get("texto"):
                    base = {"intent": cls["dominio"], "texto": ag["texto"], "datos": ag.get("datos"),
                            "fuentes": ag.get("fuentes", []), "agente": ag.get("agente"),
                            "predicciones": ag.get("predicciones", [])}
        except Exception as e:
            logger.debug("delegacion agentes: %s", e)

        # Fallback: si ningun agente atiende el dominio, IAService directo.
        if base is None:
            try:
                from src.services import ia
                base = ia.servicio().preguntar(texto_ef, emp, usuario=uid, perfil=rol)
            except Exception as e:
                logger.error("preguntar via IA: %s", e)
                base = {"intent": "error", "texto": "No he podido procesar la consulta.", "datos": None}

        resp = respuestas.enriquecer(base, ctx, emp)
        memoria.recordar(uid, dominio=cls["dominio"], periodo=cls.get("periodo"), consulta=texto)
        return resp

    def _responder_ejecucion(self, texto, ctx) -> dict | None:
        """SUBFASE 10.9: ejecucion supervisada conversacional. NUNCA ejecuta sin autorizacion.
        Reconoce: mostrar plan, ejecutar (solo primera fase / plan aprobado), no/cancelar."""
        t = (texto or "").lower()
        gatillos = ("ejecuta", "ejecutar", "muestrame el plan", "muéstrame el plan", "muestra el plan",
                    "plan de ejecucion", "plan de ejecución", "revisa el plan", "aprueba el plan",
                    "cancela el plan", "revierte", "revertir")
        if not any(g in t for g in gatillos):
            return None
        try:
            from src.services import autonomia
        except Exception:
            return None
        # Capacidad directiva: solo roles globales.
        if not seguridad.es_global(ctx["rol"]):
            return {"intent": "ejecucion", "texto": "La ejecucion supervisada esta reservada a "
                    "perfiles de gestion (administrador/gerente).", "fuentes": ["Seguridad",
                    "ExecutiveActionService"], "contexto": ctx}
        emp, uid, rol = ctx["id_empresa"], ctx["usuario"], ctx["rol"]
        svc = autonomia.servicio()
        # Localiza el plan objetivo: el mas reciente aprobado, o el mas reciente si se pide mostrar.
        aprobados = svc.planes(emp, estado="APROBADO")
        recientes = svc.planes(emp)
        plan_id = (aprobados[0]["id"] if aprobados else (recientes[0]["id"] if recientes else None))
        if plan_id is None:
            return {"intent": "ejecucion", "texto": "No hay ningun plan de ejecucion. Crea primero un "
                    "escenario y conviertelo en plan.", "fuentes": ["ExecutiveActionService"], "contexto": ctx}

        if any(g in t for g in ("muestrame", "muéstrame", "muestra", "revisa el plan")):
            expl = svc.explicar(plan_id, emp)
            return {"intent": "ejecucion.plan", "texto": "Plan #%s: %s | Riesgo %s | %d acciones criticas. "
                    "%s" % (plan_id, "; ".join(expl["que_hara"][:4]) or "sin acciones",
                            expl["riesgos"]["nivel"], len(expl["riesgos"]["acciones_criticas"]),
                            expl["aviso"]), "plan": plan_id, "explicacion": expl,
                    "fuentes": ["ExecutiveActionService", "Agentes"], "contexto": ctx}
        if t.strip() in ("no", "no.") or "cancela" in t:
            r = svc.cancelar_plan(plan_id, usuario=uid, id_empresa=emp)
            return {"intent": "ejecucion.cancelado", "texto": f"Entendido, plan #{plan_id} cancelado. "
                    "No se ha ejecutado nada.", "resultado": r, "fuentes": ["ExecutiveActionService"], "contexto": ctx}
        if "revert" in t or "revierte" in t:
            r = svc.revertir(plan_id, usuario=uid, id_empresa=emp)
            return {"intent": "ejecucion.revertido", "texto": f"Plan #{plan_id} revertido "
                    f"({r.get('revertidas',0)} acciones).", "resultado": r,
                    "fuentes": ["ExecutiveActionService"], "contexto": ctx}
        # Ejecutar (posible "solo la primera fase").
        solo_fase = 1 if any(k in t for k in ("primera fase", "fase 1", "solo la primera")) else None
        r = svc.ejecutar(plan_id, usuario=uid, perfil=rol, id_empresa=emp, solo_fase=solo_fase)
        if r.get("error"):
            return {"intent": "ejecucion", "texto": f"No puedo ejecutar el plan #{plan_id}: {r['error']}. "
                    "Debe estar APROBADO por la organizacion.", "resultado": r,
                    "fuentes": ["ExecutiveActionService", "Gobierno", "Workflow"], "contexto": ctx}
        fase_txt = f" (solo fase {solo_fase})" if solo_fase else ""
        return {"intent": "ejecucion.ejecutado", "texto": f"Plan #{plan_id} ejecutado{fase_txt}. "
                f"Estado: {r.get('estado')}. Las acciones criticas se han tramitado como propuesta.",
                "resultado": r, "fuentes": ["ExecutiveActionService", "AutomationService", "Workflow"],
                "contexto": ctx}

    def _responder_simulacion(self, texto, ctx) -> dict | None:
        """SUBFASE 9.11: crea/evalua escenarios what-if usando SOLO el SimulationService (virtual)."""
        try:
            from src.services import simulador
        except Exception:
            return None
        if not simulador.lenguaje.es_pregunta_simulacion(texto):
            return None
        # La simulacion estrategica es una capacidad directiva: solo roles globales.
        if not seguridad.es_global(ctx["rol"]):
            return {"intent": "simulacion", "texto": ("La simulacion estrategica esta reservada a "
                    "perfiles de gestion (administrador/gerente)."), "fuentes": ["Seguridad",
                    "SimulationService"], "contexto": ctx}
        vs = simulador.lenguaje.parsear(texto)
        if not vs:
            return {"intent": "simulacion", "texto": "¿Que variable quieres simular? Por ejemplo: "
                    "«¿que ocurriria si subimos los precios un 5%?» o «crea un escenario con dos "
                    "empleados mas».", "fuentes": ["SimulationService"], "contexto": ctx}
        emp, uid = ctx["id_empresa"], ctx["usuario"]
        svc = simulador.servicio()
        t = (texto or "").lower()
        # Si pide crear/guardar el escenario, se persiste; si solo pregunta, simulacion directa.
        if any(k in t for k in ("crea", "crear", "guarda", "escenario")):
            eid = svc.crear_escenario((texto or "Escenario")[:60], usuario=uid, id_empresa=emp)
            for v in vs:
                svc.añadir_variable(eid, v["variable"], v["valor"], id_empresa=emp)
            r = svc.simular(eid, emp)
            dif = {d["metrica"]: d for d in r.get("diferencias", [])}
            txt = (f"He creado el escenario #{eid} (VIRTUAL). Impacto: ingresos "
                   f"{dif.get('ingresos',{}).get('delta_pct',0):+.1f}%, beneficio "
                   f"{dif.get('beneficio',{}).get('delta_pct',0):+.1f}%. Riesgo {r['riesgo']['nivel']}, "
                   f"confianza {r['confianza']}. No se ha modificado ningun dato real.")
            return {"intent": "simulacion.escenario", "texto": txt, "escenario": eid, "resultado": r,
                    "fuentes": ["SimulationService", "Gemelo Digital", "PredictionService"], "contexto": ctx}
        r = svc.simular_directo(vs, emp)
        dif = {d["metrica"]: d for d in r["diferencias"]}
        txt = (f"Simulacion VIRTUAL: ingresos {dif['ingresos']['delta_pct']:+.1f}%, beneficio "
               f"{dif['beneficio']['delta_pct']:+.1f}%, margen {r['simulado']['margen_pct']}%. "
               f"Riesgo {r['riesgo']['nivel']}, confianza {r['confianza']}. No afecta a datos reales.")
        return {"intent": "simulacion", "texto": txt, "resultado": r,
                "fuentes": ["SimulationService", "Gemelo Digital", "PredictionService"], "contexto": ctx}

    def _responder_estado(self, texto, ctx) -> dict | None:
        """SUBFASE 8.12: responde el estado global/de tienda usando SOLO el DigitalTwinService."""
        t = (texto or "").lower()
        emp = ctx["id_empresa"]
        pregunta_estado = any(k in t for k in (
            "como esta la empresa", "cómo está la empresa", "estado general", "estado de la empresa",
            "estado global", "como va la empresa", "cómo va la empresa", "como estamos",
            "resumen general", "vision general", "visión general"))
        pregunta_tienda = ("que ocurre en" in t or "qué ocurre en" in t or "estado de la tienda" in t
                           or "como esta la tienda" in t or "cómo está la tienda" in t)
        if not (pregunta_estado or pregunta_tienda):
            return None
        try:
            from src.services import gemelo
            svc = gemelo.servicio()
            if pregunta_tienda:
                nombre = t.split(" en ")[-1] if " en " in t else t.split("tienda")[-1]
                nombre = nombre.replace("de ", "").replace("la ", "").strip(" ?.¿")
                r = svc.estado_tienda(nombre, emp)
                return {"intent": "estado.tienda", "texto": r.get("texto", ""), "datos": r,
                        "fuentes": ["Gemelo Digital", "Sincronizacion"], "contexto": ctx}
            g = svc.estado_empresa(emp)
            return {"intent": "estado.empresa", "texto": g.get("texto", g.get("resumen", "")),
                    "datos": {"riesgo_global": g.get("riesgo_global"), "alertas": g.get("alertas")},
                    "fuentes": ["Gemelo Digital"], "contexto": ctx}
        except Exception as e:
            logger.debug("responder_estado gemelo: %s", e)
            return None

    def preguntar_async(self, texto, usuario=None, id_empresa=None, callback=None) -> None:
        """SUBFASE 5.13: ejecuta la consulta en un hilo daemon y devuelve por callback."""
        def _run():
            r = self.preguntar(texto, usuario, id_empresa)
            if callable(callback):
                try:
                    callback(r)
                except Exception:
                    pass
        threading.Thread(target=_run, daemon=True).start()

    # ── Panel del Copiloto (SUBFASE 5.11) ──
    def panel(self, usuario=None, id_empresa=None) -> dict:
        ctx = contexto.resolver(usuario, id_empresa)
        emp, uid, rol = ctx["id_empresa"], ctx["usuario"], ctx["rol"]
        hist = memoria.contexto(uid).get("consultas", [])
        reco, pred, ries, estado = [], [], [], {}
        try:
            from src.services import ia
            reco = ia.servicio().recomendaciones(emp, limite=5)
        except Exception:
            pass
        try:
            from src.services import prediccion
            svc = prediccion.servicio()
            pred = svc.predicciones(emp)[:5]
            ries = svc.riesgos(emp)[:5]
        except Exception:
            pass
        try:
            from src.services import actividad
            estado["sincronizacion"] = actividad.sincronizacion.infraestructura(emp).get("global", {})
        except Exception:
            pass
        try:
            from src.services import automatizacion
            estado["automatizacion"] = automatizacion.panel.resumen(emp)
        except Exception:
            pass
        return {"contexto": ctx, "historial": hist[-10:], "consultas_recientes": hist[-5:],
                "acciones_propuestas": reco, "predicciones": pred, "riesgos": ries,
                "estado_sistema": estado, "atajos": self._atajos(rol)}

    def _atajos(self, rol) -> list:
        base = ["¿Qué ha ocurrido hoy?", "¿Cómo van las ventas?", "¿Qué productos debo comprar?",
                "¿Qué tienda necesita más reposición?"]
        if seguridad.es_global(rol):
            base += ["¿Qué facturas están pendientes?", "¿Hay riesgos?",
                     "¿Qué contratos vencen pronto?", "¿Qué debería hacer hoy?"]
        return base


_service = CopilotService()


def servicio() -> CopilotService:
    return _service
