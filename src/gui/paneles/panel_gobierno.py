"""
Panel Gobierno Corporativo — pestaña alojada dentro de Seguridad (misma familia: control de acceso y
autoridad). Sub-secciones: Organigrama · Autoridad · Delegaciones (unifica autoridad organizativa +
delegación de tareas) · Políticas · Escalados, más indicadores. Orquesta SOLO el GovernanceService.

Se construye con componentes Enterprise (regla: única librería visual). No migra la ventana de
Seguridad al shell (Strangler): solo añade esta pestaña, de forma aditiva y compatible.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.gobierno")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _svc():
    from src.services import gobierno
    return gobierno.servicio()


class PanelGobierno(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=5)
        root.addWidget(self.grid)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())   # mismo diseño de pestañas que el Centro de Inteligencia
        root.addWidget(self.tabs, 1)

        # Cada tabla lleva su Actualizar (emoji) a la derecha de su barra de búsqueda.
        self.t_org = EnterpriseTable(["Id", "Tipo", "Nombre", "Nivel", "Estado"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_aut = EnterpriseTable(["Rol", "Permisos"], con_busqueda=True, con_actualizar=self._cargar)
        self.t_del = EnterpriseTable(["Origen", "Delegado", "Desde", "Hasta"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_pol = EnterpriseTable(["Clave", "Valor", "Ámbito"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_esc = EnterpriseTable(["Referencia", "Desde", "Hacia", "Nivel", "Horas"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.tabs.addTab(self._wrap(self.t_org), "Organigrama")
        self.tabs.addTab(self._wrap(self.t_aut), "Autoridad")
        self.tabs.addTab(self._wrap(self.t_del, self._barra_delegaciones()), "Delegaciones")
        self.tabs.addTab(self._wrap(self.t_pol), "Políticas")
        self.tabs.addTab(self._wrap(self.t_esc, self._barra_escalados()), "Escalados")

        self._cargar()

    def _wrap(self, tabla, barra=None):
        w = QWidget(); w.setStyleSheet(f"background:{T.BG};")
        lay = QVBoxLayout(w)
        if barra:
            lay.addLayout(barra)
        lay.addWidget(tabla)
        return w

    def _barra_delegaciones(self):
        b = QHBoxLayout()
        lbl = QLabel("Sustitución de autoridad (Gobierno) + delegación de tareas (Workflow)")
        lbl.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        b.addWidget(lbl); b.addStretch(1)
        return b

    def _barra_escalados(self):
        b = QHBoxLayout(); b.addStretch(1)
        bt = QPushButton("Revisar escalados")
        bt.clicked.connect(self._revisar_escalados)
        bt.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{T.ADVERTENCIA};"
                         f"border:2px solid {T.ADVERTENCIA};border-radius:8px;font-weight:800;padding:4px 12px;}}"
                         f"QPushButton:hover{{background:{T.ADVERTENCIA};color:{T.BG};}}")
        b.addWidget(bt)
        return b

    def _revisar_escalados(self):
        try:
            _svc().revisar_escalados(self.id_empresa)
        except Exception as e:
            logger.debug("revisar escalados: %s", e)
        self._cargar()

    def _cargar(self):
        emp = self.id_empresa
        svc = _svc()
        # Indicadores
        self.grid.limpiar()
        try:
            ind = svc.dashboard(emp)
            for clave, etiqueta, concepto in (("nodos_total", "Nodos", "gobierno"),
                                              ("tiendas", "Tiendas", "tienda"),
                                              ("delegaciones_activas", "Delegaciones", "usuario"),
                                              ("aprobaciones_pendientes", "Aprob. pend.", "tarea"),
                                              ("escalados", "Escalados", "riesgo")):
                self.grid.add_card(EnterpriseCard(etiqueta, ind.get(clave, 0), modo="kpi", concepto=concepto))
        except Exception as e:
            logger.debug("dashboard gobierno: %s", e)

        # Organigrama
        try:
            self.t_org.set_datos([{"Id": n.get("id"), "Tipo": n.get("tipo"), "Nombre": n.get("nombre"),
                                   "Nivel": n.get("nivel"), "Estado": n.get("estado")}
                                  for n in _importar_mapa(emp)])
        except Exception as e:
            logger.debug("organigrama: %s", e)

        # Autoridad (matriz rol → permisos)
        try:
            from src.services.gobierno import autoridad as _A
            self.t_aut.set_datos([{"Rol": rol, "Permisos": ", ".join(sorted(_A.permisos_de(rol)))}
                                  for rol in getattr(_A, "ROLES_ORG", ())])
        except Exception as e:
            logger.debug("autoridad: %s", e)

        # Delegaciones activas
        try:
            self.t_del.set_datos([{"Origen": d.get("usuario_origen"), "Delegado": d.get("usuario_delegado"),
                                   "Desde": d.get("desde"), "Hasta": d.get("hasta")}
                                  for d in svc.delegaciones_activas(emp)])
        except Exception as e:
            logger.debug("delegaciones: %s", e)

        # Políticas efectivas
        try:
            from src.services.gobierno import politicas as _P
            efect = _P.efectivas(emp) if hasattr(_P, "efectivas") else {}
            filas = [{"Clave": k, "Valor": v, "Ámbito": "empresa"} for k, v in (efect or {}).items()]
            self.t_pol.set_datos(filas)
        except Exception as e:
            logger.debug("politicas: %s", e)

        # Escalados
        try:
            from src.services.gobierno.escalado import listar_escalados
            rows = listar_escalados(emp)
            self.t_esc.set_datos([{"Referencia": r.get("referencia"), "Desde": r.get("desde_usuario"),
                                   "Hacia": r.get("hacia_usuario"), "Nivel": r.get("nivel"),
                                   "Horas": r.get("horas")} for r in rows])
        except Exception as e:
            logger.debug("escalados tabla: %s", e)


def _importar_mapa(emp):
    from src.services.gobierno import organigrama as _O
    return _O.mapa(emp)
