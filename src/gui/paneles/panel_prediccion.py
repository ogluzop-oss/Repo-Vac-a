"""
Panel Predicción (pestaña del Centro de Inteligencia Empresarial). Presenta el abanico completo del
PredictionService: predicciones por dominio (stock/clientes/tesorería/rrhh), riesgos y panel
predictivo. Solo orquesta el servicio; no calcula.
"""

import logging

from PyQt6.QtWidgets import QLabel

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseTable)
from src.gui.foundation.shell import QtEnterprisePanel
from src.utils.texto import capitalizar_sigla

logger = logging.getLogger("gui.paneles.prediccion")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelPrediccion(QtEnterprisePanel):
    titulo = "Predicción"
    concepto = "prediccion"

    def cargar(self):
        self.add_toolbar_widget(QLabel("Anticipación de problemas y oportunidades"))
        self.toolbar_stretch()

        # Fase 8: KPIs del MOTOR PREDICTIVO REAL (forecasting/modelos) — riesgo, demanda, calidad de modelos.
        self.grid_ia = EnterpriseDashboardGrid(columnas=4)
        self.contenido.addWidget(QLabel("Inteligencia predictiva (motor real)"))
        self.contenido.addWidget(self.grid_ia)

        self.grid = EnterpriseDashboardGrid(columnas=4)
        self.contenido.addWidget(QLabel("Predicciones por dominio"))
        self.contenido.addWidget(self.grid)

        # "Actualizar" propio de CADA tabla (esquina superior derecha), no compartido en la cabecera
        # del panel — y el contador "N filas" pasa a la esquina INFERIOR derecha (`contador_abajo`),
        # dejando la esquina superior libre para el botón.
        self.tabla = EnterpriseTable(["Dominio", "Métrica", "Valor"], con_busqueda=True, pagina=12,
                                     con_actualizar=self._refrescar, actualizar_pos="derecha",
                                     contador_abajo=True)
        self.contenido.addWidget(self.tabla)

        self.contenido.addWidget(QLabel("Riesgos previstos"))
        self.tabla_riesgos = EnterpriseTable(["Riesgo", "Detalle"], con_busqueda=True,
                                             con_actualizar=self._refrescar, actualizar_pos="derecha",
                                             contador_abajo=True)
        self.contenido.addWidget(self.tabla_riesgos)

        self._refrescar()

    def _refrescar(self):
        emp = _emp(self.id_empresa)
        try:
            from src.services import prediccion
            svc = prediccion.servicio()
        except Exception as e:
            self.set_status(f"PredictionService no disponible: {e}", "critico")
            return

        # Fase 8: KPIs del motor real (forecasting/modelos), explicables. Degradable.
        self.grid_ia.limpiar()
        try:
            from src.services.prediccion import panel as _panel
            k = _panel.kpis_predictivos(emp)["kpis"]
            rg, dm, md = k["riesgo"], k["demanda"], k["modelos"]
            self.grid_ia.add_card(EnterpriseCard("Riesgo alto (rotura)", rg["articulos_riesgo_alto"],
                                                 modo="riesgo", riesgo="critico", subtitulo=rg["explicacion"]))
            self.grid_ia.add_card(EnterpriseCard("Riesgo medio", rg["articulos_riesgo_medio"],
                                                 modo="riesgo", riesgo="advertencia"))
            self.grid_ia.add_card(EnterpriseCard(
                "Demanda 7d", dm["prevision_7d"] if dm["prevision_7d"] is not None else "sin datos",
                concepto="prediccion",
                subtitulo=f"Tendencia: {dm['tendencia']} · {dm['tipo'] or '—'}\nCalidad: {dm['calidad_datos']}"))
            self.grid_ia.add_card(EnterpriseCard("Modelos activos", md["activos"], concepto="prediccion",
                                                 subtitulo=f"Total {md['total']} · MAE {md['mae_medio']} · "
                                                           f"WAPE {md['wape_medio']}"))
        except Exception as e:
            logger.debug("kpis_predictivos: %s", e)

        filas, cards = [], []
        for dom in ("stock", "clientes", "tesoreria", "rrhh"):
            try:
                d = getattr(svc, dom)(emp)
            except Exception as e:
                logger.debug("prediccion %s: %s", dom, e)
                continue
            preds = d.get("predicciones", []) if isinstance(d, dict) else []
            for p in preds:
                filas.append({"Dominio": dom, "Métrica": p.get("metrica"), "Valor": p.get("valor")})
            if preds:
                cards.append(EnterpriseCard(capitalizar_sigla(dom), len(preds), modo="prediccion",
                                            concepto="prediccion", subtitulo=f"{len(preds)} señales"))
        self.grid.limpiar()
        for c in cards:
            self.grid.add_card(c)
        self.tabla.set_datos(filas)

        riesgos = []
        try:
            for r in svc.riesgos(emp):
                riesgos.append({"Riesgo": r.get("categoria") or r.get("dominio") or "riesgo",
                                "Detalle": r.get("texto") or r.get("descripcion") or ""})
        except Exception as e:
            logger.debug("riesgos: %s", e)
        self.tabla_riesgos.set_datos(riesgos)
        self.set_status(f"{len(filas)} predicciones · {len(riesgos)} riesgos · empresa {emp}", "info")
