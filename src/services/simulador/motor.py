"""
SimulationService (Paquete Enterprise 9, SUBFASE 9.1) — FACHADA PUBLICA UNICA del Simulador
Empresarial. Toda simulacion pasa por aqui. Responde "¿que ocurriria si...?" SIN tocar jamas los
datos reales: opera sobre el Gemelo Digital (estado base) y propaga consecuencias con heuristicas +
PredictionService. Coordina escenarios, variables, propagacion, riesgo, comparador y explicabilidad.
NO duplica motores: reutiliza DigitalTwin/Prediction/IA/Copilot/Agentes/BI.
"""

import json
import logging

from src.services.simulador import (base, comparador, escenarios, explicabilidad,
                                     modelo, propagacion, riesgo, seguridad, variables)

logger = logging.getLogger("simulador.motor")


class SimulationService:

    # ── Escenarios (9.2) ──
    def crear_escenario(self, nombre, *, descripcion=None, usuario=None, id_empresa=None) -> int | None:
        return escenarios.crear(nombre, descripcion=descripcion, usuario=usuario, id_empresa=id_empresa)

    def escenario(self, id_escenario, id_empresa=None):
        return escenarios.obtener(id_escenario, id_empresa)

    def escenarios(self, id_empresa=None, *, estado=None):
        return escenarios.listar(id_empresa, estado=estado)

    def eliminar_escenario(self, id_escenario, id_empresa=None) -> bool:
        return escenarios.eliminar(id_escenario, id_empresa)

    # ── Variables what-if (9.3) ──
    def añadir_variable(self, id_escenario, variable, valor, *, id_empresa=None, **k) -> bool:
        return variables.añadir(id_escenario, variable, valor, id_empresa=id_empresa, **k)

    def variables(self, id_escenario, id_empresa=None):
        return variables.listar(id_escenario, id_empresa)

    # ── Ejecutar simulacion (9.4 propagacion + 9.9 riesgo + 9.15 explicabilidad) ──
    def simular(self, id_escenario, id_empresa=None) -> dict:
        emp = base._emp(id_empresa)
        esc = escenarios.obtener(id_escenario, emp)
        if not esc:
            return {"error": "escenario no encontrado"}
        base_m = esc.get("base") or base.metricas_base(emp)
        vars_ = variables.listar(id_escenario, emp)
        prop = propagacion.propagar(base_m, vars_)
        sim_m = prop["metricas"]
        ries = riesgo.evaluar(emp, base_m, sim_m)
        sim_m_riesgo = dict(sim_m); sim_m_riesgo["riesgo"] = ries["nivel"]
        conf = modelo.confianza_por_variables(len(vars_), [v.get("dominio") for v in vars_])
        expl = explicabilidad.construir(vars_, prop["cadena"], conf)

        self._persistir_resultados(id_escenario, emp, base_m, sim_m)
        escenarios.marcar(id_escenario, modelo.SIMULADO, confianza=conf, id_empresa=emp)
        return {
            "id_escenario": id_escenario, "nombre": esc.get("nombre"),
            "base": base_m, "simulado": sim_m_riesgo,
            "diferencias": self._diferencias(base_m, sim_m),
            "riesgo": ries, "explicabilidad": expl, "confianza": conf,
            "seguridad": seguridad.garantia(),
        }

    def _diferencias(self, base_m, sim_m) -> list:
        out = []
        for met in modelo.METRICAS:
            b = float(base_m.get(met, 0) or 0); s = float(sim_m.get(met, 0) or 0)
            d = round(s - b, 2); dp = round((d / b * 100), 2) if b else (100.0 if s else 0.0)
            out.append({"metrica": met, "base": round(b, 2), "simulado": round(s, 2),
                        "delta": d, "delta_pct": dp})
        return out

    def _persistir_resultados(self, id_escenario, emp, base_m, sim_m):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("DELETE FROM sim_resultados WHERE id_escenario=%s AND id_empresa=%s",
                            (id_escenario, emp))
                for met in modelo.METRICAS:
                    b = float(base_m.get(met, 0) or 0); s = float(sim_m.get(met, 0) or 0)
                    d = round(s - b, 2); dp = round((d / b * 100), 2) if b else 0.0
                    cur.execute("INSERT INTO sim_resultados (id_escenario, id_empresa, metrica, "
                                "valor_base, valor_sim, delta, delta_pct) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                (id_escenario, emp, met, b, s, d, dp))
                c.commit()
        except Exception as e:
            logger.debug("persistir resultados: %s", e)

    # ── Simulacion directa sin persistir (para IA/Copiloto rapidos) ──
    def simular_directo(self, variables_list, id_empresa=None) -> dict:
        """Aplica un conjunto de variables sobre el estado base actual y devuelve el resultado,
        sin crear escenario. Cada item: {'variable':..,'valor':..}."""
        emp = base._emp(id_empresa)
        base_m = base.metricas_base(emp)
        for v in variables_list:
            v.setdefault("dominio", variables.DOMINIO_DE.get(v.get("variable"), "comercial"))
        prop = propagacion.propagar(base_m, variables_list)
        sim_m = prop["metricas"]
        ries = riesgo.evaluar(emp, base_m, sim_m)
        conf = modelo.confianza_por_variables(len(variables_list),
                                              [v.get("dominio") for v in variables_list])
        return {"base": base_m, "simulado": sim_m, "diferencias": self._diferencias(base_m, sim_m),
                "riesgo": ries, "confianza": conf,
                "explicabilidad": explicabilidad.construir(variables_list, prop["cadena"], conf),
                "seguridad": seguridad.garantia()}

    # ── Comparador (9.13) ──
    def comparar(self, ids_escenario, id_empresa=None) -> dict:
        emp = base._emp(id_empresa)
        cols = []
        for eid in ids_escenario:
            r = self.simular(eid, emp)
            if "simulado" in r:
                cols.append({"id": eid, "nombre": r.get("nombre") or f"Escenario {eid}",
                             "metricas": r["simulado"]})
        return comparador.comparar(emp, cols)

    # ── Evaluacion por agentes (9.12) ──
    def evaluar_con_agentes(self, id_escenario, id_empresa=None, *, usuario=None, rol="ADMINISTRADOR") -> dict:
        """Cada agente evalua el impacto del escenario en su dominio (comercial/rrhh/financiero...)."""
        emp = base._emp(id_empresa)
        r = self.simular(id_escenario, emp)
        if "simulado" not in r:
            return r
        dif = {d["metrica"]: d for d in r["diferencias"]}
        evaluaciones = []
        try:
            from src.services.agentes import manager as _m
            mgr = _m()
            ctx = {"id_empresa": emp, "usuario": usuario, "rol": rol, "simulacion": r}
            mapa = {"comercial": "ventas", "financiero": "financiero", "rrhh": "rrhh",
                    "inventario": "stock", "compras": "compras"}
            for etiqueta, dom in mapa.items():
                ag = mgr.delegar(dom, f"impacto del escenario {id_escenario}", dict(ctx))
                if ag and ag.get("texto"):
                    evaluaciones.append({"agente": ag.get("agente"), "dominio": etiqueta,
                                         "texto": ag.get("texto"), "fuentes": ag.get("fuentes", [])})
        except Exception as e:
            logger.debug("evaluar_con_agentes: %s", e)
        # Titulares por dominio derivados de la propia simulacion (siempre presentes).
        titulares = [
            {"dominio": "comercial", "texto": f"Ingresos {dif['ingresos']['delta_pct']:+.1f}%, "
             f"unidades {dif['unidades']['delta_pct']:+.1f}%."},
            {"dominio": "rrhh", "texto": f"Plantilla {int(r['simulado']['plantilla'])}, "
             f"coste personal {dif['coste_personal']['delta_pct']:+.1f}%."},
            {"dominio": "financiero", "texto": f"Beneficio {dif['beneficio']['delta_pct']:+.1f}%, "
             f"margen {r['simulado']['margen_pct']}%."},
        ]
        return {"simulacion": r, "evaluaciones_agentes": evaluaciones, "titulares": titulares}

    # ── Dashboard comparativo (9.14) ──
    def dashboard(self, ids_escenario=None, id_empresa=None) -> dict:
        emp = base._emp(id_empresa)
        ids = ids_escenario or [e["id"] for e in escenarios.listar(emp, limite=5)]
        comp = self.comparar(ids, emp) if ids else {"filas": [], "columnas": ["Actual"]}
        base_m = base.metricas_base(emp)
        return {
            "actual": base_m,
            "escenarios": escenarios.listar(emp, limite=10),
            "comparativa": comp,
            "metricas_clave": ["ingresos", "beneficio", "liquidez", "margen_pct", "stock_roturas",
                               "plantilla"],
        }

    # ── Seguridad (9.16) ──
    def seguridad(self) -> dict:
        return seguridad.garantia()


_service = SimulationService()


def servicio() -> SimulationService:
    return _service
