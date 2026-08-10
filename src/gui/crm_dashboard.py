"""
CRM-I — Dashboard CRM. Secciones: Leads, Pipeline, Oportunidades, Actividades, Forecast,
CRM SaaS, KPIs. Reutiliza el estilo global y los servicios CRM. Read-only/operativo ligero.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _tabla

logger = logging.getLogger("gui.crm")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class CRMDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("CRM Comercial · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))   # X roja (como el resto de ventanas)
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)

        self.tabs = QTabWidget()
        self.tbl_leads = _tabla(["ID", "Nombre", "Empresa", "Estado", "Prioridad", "Valor", "Score"])
        self.tbl_ops = _tabla(["ID", "Titulo", "Estado", "Valor", "Prob %", "Cierre prev.", "Doc.", "Proy."])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        # Enriquecimiento CRM (Módulo 1): campañas/marketing, objetivos comerciales y rutas comerciales.
        self.tbl_camp = _tabla(["ID", "Nombre", "Canal", "Segmento", "Estado", "Presupuesto"])
        self.tbl_obj = _tabla(["Responsable", "Tipo", "Objetivo", "Real", "%", "Cumplido"])
        self.tbl_rutas = _tabla(["ID", "Nombre", "Responsable", "Fecha", "Estado"])
        self.tabs.addTab(self.tbl_leads, "Leads")
        self.tabs.addTab(self._tab_oportunidades(), "Oportunidades")
        self.tabs.addTab(self.tbl_kpi, "KPIs / Forecast")
        self.tabs.addTab(self.tbl_camp, "Campañas")
        self.tabs.addTab(self.tbl_obj, "Objetivos")
        self.tabs.addTab(self.tbl_rutas, "Rutas")
        # Submódulos del dominio CRM (reutilizan las ventanas existentes, sin duplicarlas): gestión de
        # clientes y servicio postventa (SAT). El Cuadro de mando es la entrada; estas son sus áreas.
        try:
            from src.gui.clientes_gui import ClientesWindow
            self.tabs.addTab(ClientesWindow(callback_vuelta=None, usuario=usuario, main=main), "Clientes")
        except Exception as e:
            logger.debug("tab clientes: %s", e)
        try:
            from src.gui.sat_dashboard import SATDashboardWindow
            self.tabs.addTab(SATDashboardWindow(callback_vuelta=None, usuario=usuario, main=main),
                             "SAT / Postventa")
        except Exception as e:
            logger.debug("tab SAT: %s", e)
        root.addWidget(self.tabs)
        self._load()

    def _tab_oportunidades(self):
        """Pestaña Oportunidades = tabla + barra con 'Convertir a factura' (genera una proforma)."""
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(self.tbl_ops)
        barra = QHBoxLayout(); barra.addStretch()
        self._btn_conv = _btn("🧾 Convertir a factura", self._convertir_factura, primary=True)
        self._btn_proy = _btn("📁 Convertir a proyecto", self._convertir_proyecto, primary=True)
        try:
            from src.services.autorizacion import puede
            self._btn_conv.setEnabled(puede(self.usuario, "ventas.facturar"))
            self._btn_proy.setEnabled(puede(self.usuario, "proyectos.gestionar"))
        except Exception:
            pass
        barra.addWidget(self._btn_conv)
        barra.addWidget(self._btn_proy)
        ly.addLayout(barra)
        return w

    def _msg(self, titulo, texto, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, titulo, texto, nivel=nivel)
        except Exception:
            self.lbl.setText(texto)

    def _convertir_factura(self):
        row = self.tbl_ops.currentRow()
        if row < 0 or self.tbl_ops.item(row, 0) is None:
            self._msg("Convertir a factura", "Selecciona antes una oportunidad de la tabla.")
            return
        try:
            oid = int(self.tbl_ops.item(row, 0).text())
        except (TypeError, ValueError):
            return
        from src.services.crm import conversion
        r = conversion.convertir_a_factura(oid)
        if r.get("ok"):
            if r.get("existente"):
                self._msg("Convertir a factura", f"La oportunidad ya tenía el documento #{r['id_factura']}.")
            else:
                self._msg("Convertir a factura",
                          f"Proforma #{r['id_factura']} generada a partir de la oportunidad.\n"
                          "Puedes convertirla en factura desde Facturación.", "success")
        else:
            self._msg("Convertir a factura", "No se pudo convertir: " + r.get("error", ""), "warning")
        self._load()

    def _convertir_proyecto(self):
        row = self.tbl_ops.currentRow()
        if row < 0 or self.tbl_ops.item(row, 0) is None:
            self._msg("Convertir a proyecto", "Selecciona antes una oportunidad de la tabla.")
            return
        try:
            oid = int(self.tbl_ops.item(row, 0).text())
        except (TypeError, ValueError):
            return
        from src.services.crm import conversion
        r = conversion.convertir_a_proyecto(oid)
        if r.get("ok"):
            if r.get("existente"):
                self._msg("Convertir a proyecto", f"La oportunidad ya tenía el proyecto #{r['id_proyecto']}.")
            else:
                self._msg("Convertir a proyecto",
                          f"Proyecto #{r['id_proyecto']} creado a partir de la oportunidad "
                          "(presupuesto = valor de la oportunidad).", "success")
        else:
            self._msg("Convertir a proyecto", "No se pudo convertir: " + r.get("error", ""), "warning")
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.crm import analitica, leads, oportunidades
            ls = leads.listar_leads(id_empresa=eid)
            self.tbl_leads.setRowCount(len(ls))
            for i, l in enumerate(ls):
                for j, v in enumerate([l.get("id"), l.get("nombre"), l.get("empresa"), l.get("estado"),
                                       l.get("prioridad"), l.get("valor_estimado"), l.get("score")]):
                    self.tbl_leads.setItem(i, j, _it(v))
            ops = oportunidades.listar(id_empresa=eid)
            self.tbl_ops.setRowCount(len(ops))
            for i, o in enumerate(ops):
                doc = o.get("id_factura")
                proy = o.get("id_proyecto")
                for j, v in enumerate([o.get("id"), o.get("titulo"), o.get("estado"), o.get("valor"),
                                       o.get("probabilidad"), o.get("fecha_cierre_prevista"),
                                       f"#{doc}" if doc else "—", f"#{proy}" if proy else "—"]):
                    self.tbl_ops.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"Forecast ponderado: {k.get('forecast', 0)} € · Conversión: {k.get('conversion_pct', 0)}%")
        except Exception as e:
            logger.error("load CRM: %s", e)
            self.lbl.setText(f"Error: {e}")
        # Enriquecimiento CRM (Módulo 1): campañas · objetivos · rutas.
        try:
            from src.services.crm import campanias, objetivos, rutas
            cps = campanias.listar(id_empresa=eid)
            self.tbl_camp.setRowCount(len(cps))
            for i, cp in enumerate(cps):
                for j, v in enumerate([cp.get("id"), cp.get("nombre"), cp.get("canal"),
                                       cp.get("segmento_objetivo"), cp.get("estado"), cp.get("presupuesto")]):
                    self.tbl_camp.setItem(i, j, _it(v))
            obs = objetivos.progreso(id_empresa=eid)
            self.tbl_obj.setRowCount(len(obs))
            for i, o in enumerate(obs):
                for j, v in enumerate([o.get("responsable"), o.get("tipo"), o.get("objetivo_valor"),
                                       o.get("real"), o.get("pct"), "Sí" if o.get("cumplido") else "No"]):
                    self.tbl_obj.setItem(i, j, _it(v))
            rts = rutas.listar_rutas(id_empresa=eid)
            self.tbl_rutas.setRowCount(len(rts))
            for i, rt in enumerate(rts):
                for j, v in enumerate([rt.get("id"), rt.get("nombre"), rt.get("responsable"),
                                       rt.get("fecha"), rt.get("estado")]):
                    self.tbl_rutas.setItem(i, j, _it(v))
        except Exception as e:
            logger.debug("load CRM enriquecimiento: %s", e)
