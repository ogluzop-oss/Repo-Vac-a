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
        self._main = main
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
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; }")
        self.tbl_leads = _tabla(["ID", "Nombre", "Empresa", "Estado", "Prioridad", "Valor", "Score"])
        self.tbl_ops = _tabla(["ID", "Titulo", "Estado", "Valor", "Prob %", "Cierre prev.", "Doc.", "Proy."])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        # Enriquecimiento CRM (Módulo 1): campañas/marketing, objetivos comerciales y rutas comerciales.
        self.tbl_camp = _tabla(["ID", "Nombre", "Canal", "Segmento", "Estado", "Presupuesto"])
        self.tbl_obj = _tabla(["Responsable", "Tipo", "Objetivo", "Real", "%", "Cumplido"])
        self.tbl_rutas = _tabla(["ID", "Nombre", "Responsable", "Fecha", "Estado"])
        self.tabs.addTab(self.tbl_leads, "Contactos")               # idx 0
        self.tabs.addTab(self._tab_oportunidades(), "Oportunidades")  # idx 1
        self.tabs.addTab(self.tbl_kpi, "KPIs / Previsión")            # idx 2
        self.tabs.addTab(self.tbl_camp, "Campañas")                  # idx 3
        self.tabs.addTab(self.tbl_obj, "Objetivos")                   # idx 4
        self.tabs.addTab(self.tbl_rutas, "Rutas")                     # idx 5

        # Lazy loading (init en primer acceso): las 6 pestañas de arriba ya existen como widgets
        # (tablas), pero poblarlas TODAS de golpe (6 consultas a BD seguidas) en __init__ es lo que
        # hacía tardar la apertura. Solo se carga de inmediato la pestaña visible (Contactos); el
        # resto carga sus datos la primera vez que el usuario la visita.
        self._load_tab_map = {
            0: self._load_leads, 1: self._load_oportunidades, 2: self._load_kpis,
            3: self._load_campanias, 4: self._load_objetivos, 5: self._load_rutas,
        }
        self._datos_cargados = set()
        self.tabs.currentChanged.connect(self._asegurar_datos_tab)
        self._asegurar_datos_tab(self.tabs.currentIndex())

        # Submódulos del dominio CRM (reutilizan las ventanas existentes, sin duplicarlas): gestión de
        # clientes y servicio postventa (SAT). Embeben ventanas completas con su propia carga pesada,
        # así que también se difieren hasta el primer acceso (instalar_pestanas_lazy, añadidas tras
        # las 6 pestañas de datos → índices 6+).
        from src.gui.transiciones import instalar_pestanas_lazy
        instalar_pestanas_lazy(self.tabs, [
            ("Clientes", self._construir_tab_clientes),
            ("SAT / Postventa", self._construir_tab_sat),
        ])
        root.addWidget(self.tabs)

    def _asegurar_datos_tab(self, idx):
        if idx in self._datos_cargados:
            return
        fn = self._load_tab_map.get(idx)
        if fn is None:
            return
        self._datos_cargados.add(idx)
        try:
            fn()
        except Exception as e:
            logger.debug("load CRM pestaña %s: %s", idx, e)

    def _construir_tab_clientes(self):
        try:
            from src.gui.clientes_gui import ClientesWindow
            return ClientesWindow(callback_vuelta=None, usuario=self.usuario, main=self._main)
        except Exception as e:
            logger.debug("tab clientes: %s", e)
            return QWidget()

    def _construir_tab_sat(self):
        try:
            from src.gui.sat_dashboard import SATDashboardWindow
            return SATDashboardWindow(callback_vuelta=None, usuario=self.usuario, main=self._main)
        except Exception as e:
            logger.debug("tab SAT: %s", e)
            return QWidget()

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
        """Recarga TODAS las pestañas de datos (botón «Actualizar»), sin importar cuáles se hayan
        visitado ya — a diferencia de `_asegurar_datos_tab`, que solo carga una vez por pestaña."""
        for idx, fn in self._load_tab_map.items():
            self._datos_cargados.add(idx)
            try:
                fn()
            except Exception as e:
                logger.debug("load CRM pestaña %s: %s", idx, e)

    def _load_leads(self):
        eid = _empresa()
        from src.services.crm import leads
        ls = leads.listar_leads(id_empresa=eid)
        self.tbl_leads.setRowCount(len(ls))
        for i, l in enumerate(ls):
            for j, v in enumerate([l.get("id"), l.get("nombre"), l.get("empresa"), l.get("estado"),
                                   l.get("prioridad"), l.get("valor_estimado"), l.get("score")]):
                self.tbl_leads.setItem(i, j, _it(v))

    def _load_oportunidades(self):
        eid = _empresa()
        from src.services.crm import oportunidades
        ops = oportunidades.listar(id_empresa=eid)
        self.tbl_ops.setRowCount(len(ops))
        for i, o in enumerate(ops):
            doc = o.get("id_factura")
            proy = o.get("id_proyecto")
            for j, v in enumerate([o.get("id"), o.get("titulo"), o.get("estado"), o.get("valor"),
                                   o.get("probabilidad"), o.get("fecha_cierre_prevista"),
                                   f"#{doc}" if doc else "—", f"#{proy}" if proy else "—"]):
                self.tbl_ops.setItem(i, j, _it(v))

    def _load_kpis(self):
        eid = _empresa()
        from src.services.crm import analitica
        k = analitica.kpis(id_empresa=eid)
        self.tbl_kpi.setRowCount(len(k))
        for i, (nombre, val) in enumerate(k.items()):
            self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
        self.lbl.setText(f"Forecast ponderado: {k.get('forecast', 0)} € · Conversión: {k.get('conversion_pct', 0)}%")

    # Enriquecimiento CRM (Módulo 1): campañas · objetivos · rutas.
    def _load_campanias(self):
        eid = _empresa()
        from src.services.crm import campanias
        cps = campanias.listar(id_empresa=eid)
        self.tbl_camp.setRowCount(len(cps))
        for i, cp in enumerate(cps):
            for j, v in enumerate([cp.get("id"), cp.get("nombre"), cp.get("canal"),
                                   cp.get("segmento_objetivo"), cp.get("estado"), cp.get("presupuesto")]):
                self.tbl_camp.setItem(i, j, _it(v))

    def _load_objetivos(self):
        eid = _empresa()
        from src.services.crm import objetivos
        obs = objetivos.progreso(id_empresa=eid)
        self.tbl_obj.setRowCount(len(obs))
        for i, o in enumerate(obs):
            for j, v in enumerate([o.get("responsable"), o.get("tipo"), o.get("objetivo_valor"),
                                   o.get("real"), o.get("pct"), "Sí" if o.get("cumplido") else "No"]):
                self.tbl_obj.setItem(i, j, _it(v))

    def _load_rutas(self):
        eid = _empresa()
        from src.services.crm import rutas
        rts = rutas.listar_rutas(id_empresa=eid)
        self.tbl_rutas.setRowCount(len(rts))
        for i, rt in enumerate(rts):
            for j, v in enumerate([rt.get("id"), rt.get("nombre"), rt.get("responsable"),
                                   rt.get("fecha"), rt.get("estado")]):
                self.tbl_rutas.setItem(i, j, _it(v))
