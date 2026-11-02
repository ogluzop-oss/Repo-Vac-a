"""
Panel Autonomía Supervisada — pestaña alojada en Aprobaciones (Workflow). Orquesta SOLO el
ExecutiveActionService: modo de empresa, indicador de autonomía, lista de planes y el circuito
gobernado solicitar→aprobar→ejecutar(por fases)→revertir. Nunca ejecuta sin aprobación; las
acciones críticas quedan como propuesta (garantía 10.14 en el servicio). GUI = orquestación.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseFilter, EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.autonomia")

_MODOS = [("Manual", "MANUAL"), ("Asistida", "ASISTIDA"), ("Semiautomática", "SEMIAUTO"),
          ("Avanzada", "AVANZADA")]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _aviso(parent, titulo, msg, nivel="info"):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    except Exception:
        pass


class _NuevoPlanDialog(QDialog):
    """Nuevo plan de ejecución a partir de un escenario ya simulado (`ExecutiveActionService.
    plan_desde_escenario` reutiliza el motor del Simulador — sin editor de acciones manual
    redundante). Mismo precedente de diálogo modal que `panel_simulador._CompararDialog`."""

    def __init__(self, parent, escenarios):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless
        v = _dialogo_frameless(self, "Nuevo plan desde escenario", ancho=420)
        v.addWidget(QLabel("Escenario simulado:"))
        self.cmb = EnterpriseFilter([(e.get("nombre"), e.get("id")) for e in escenarios])
        self.cmb.setMinimumWidth(320)
        v.addWidget(self.cmb)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Crear plan", self.accept, primary=True))
        v.addLayout(fila)

    def escenario_sel(self):
        return self.cmb.currentData()


class _DetallePlanDialog(QDialog):
    """Detalle legible del plan (fases/acciones), explicación (`explicabilidad.explicar`) y
    recomendación IA (`recomendacion_ia`) unidas en un único diálogo de solo lectura — evita
    multiplicar botones/diálogos casi idénticos sobre el mismo plan."""

    def __init__(self, parent, detalle, explicacion, recomendacion):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless, _lbl, _tabla
        v = _dialogo_frameless(self, f"Plan #{detalle.get('id_plan')} · {detalle.get('nombre', '')}",
                               ancho=680)
        resumen = QLabel(f"Riesgo: {detalle.get('riesgo', '-')}  ·  Confianza: {detalle.get('confianza', '-')}"
                         f"  ·  Tiempo estimado: {detalle.get('tiempo_estimado_min', 0)} min  ·  "
                         f"Responsables: {', '.join(detalle.get('responsables', [])) or '-'}")
        resumen.setWordWrap(True)
        resumen.setStyleSheet(f"color:{T.TEXT};font-size:12px;")
        v.addWidget(resumen)
        tabla = _tabla(["Fase", "Acción", "Crítica", "Reversible"])
        filas = [(f_num, a.get("titulo") or a.get("codigo"), "Sí" if a.get("critica") else "No",
                  "Sí" if a.get("reversible") else "No")
                 for f_num, acciones in sorted((detalle.get("fases") or {}).items())
                 for a in acciones]
        tabla.setRowCount(len(filas))
        for i, row in enumerate(filas):
            for j, val in enumerate(row):
                tabla.setItem(i, j, _it(val))
        tabla.setMinimumSize(640, 200)
        v.addWidget(tabla)
        v.addWidget(_lbl("Explicación", dim=False))
        texto_exp = (f"{explicacion.get('por_que', '')}\n"
                    f"Módulos afectados: {', '.join(explicacion.get('modulos_afectados', [])) or '-'}\n"
                    f"{explicacion.get('aviso', '')}")
        exp = QLabel(texto_exp)
        exp.setWordWrap(True)
        exp.setStyleSheet(f"color:{T.DIM};font-size:12px;")
        v.addWidget(exp)
        v.addWidget(_lbl("Recomendación IA", dim=False))
        rec = QLabel(recomendacion.get("texto") or "—")
        rec.setWordWrap(True)
        rec.setStyleSheet(f"color:{T.DIM};font-size:12px;")
        v.addWidget(rec)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(fila)


class _RevisarAgentesDialog(QDialog):
    """Revisión del plan por agentes IA (`agentes_revision.revisar` — devuelve una LISTA de
    dictámenes, uno por dominio/agente implicado)."""

    def __init__(self, parent, dictamenes):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless, _tabla
        v = _dialogo_frameless(self, "Revisión por agentes IA", ancho=680)
        tabla = _tabla(["Agente", "Dominio", "Veredicto", "Observaciones", "Riesgos"])
        tabla.setRowCount(len(dictamenes))
        for i, d in enumerate(dictamenes):
            tabla.setItem(i, 0, _it(d.get("agente")))
            tabla.setItem(i, 1, _it(d.get("dominio")))
            tabla.setItem(i, 2, _it(d.get("veredicto")))
            tabla.setItem(i, 3, _it(d.get("observaciones")))
            tabla.setItem(i, 4, _it(", ".join(d.get("riesgos", []))))
        tabla.setMinimumSize(640, 280)
        v.addWidget(tabla)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(fila)


class _ValidarPlanDialog(QDialog):
    """Checklist de validación previa a ejecutar (`ExecutiveActionService.validar`)."""

    def __init__(self, parent, resultado):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless, _tabla
        ok = resultado.get("ok")
        v = _dialogo_frameless(self, f"Validación del plan — {'OK' if ok else 'CON INCIDENCIAS'}", ancho=560)
        tabla = _tabla(["Comprobación", "Resultado", "Detalle"])
        checks = resultado.get("checks", [])
        tabla.setRowCount(len(checks))
        for i, c in enumerate(checks):
            tabla.setItem(i, 0, _it(c.get("nombre")))
            tabla.setItem(i, 1, _it("OK" if c.get("ok") else "FALLA"))
            tabla.setItem(i, 2, _it(c.get("detalle")))
        tabla.setMinimumSize(520, 220)
        v.addWidget(tabla)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(fila)


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _svc():
    from src.services import autonomia
    return autonomia.servicio()


class PanelAutonomia(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._plan_sel = None
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=4)
        root.addWidget(self.grid)

        # Barra: modo de empresa + circuito
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Modo de empresa:"))
        self.cmb_modo = EnterpriseFilter(_MODOS)
        self.cmb_modo.setFixedWidth(210)   # más ancho: no corta el texto de los modos
        barra.addWidget(self.cmb_modo)
        barra.addWidget(self._btn("Aplicar modo", self._aplicar_modo, T.ANALISIS))
        barra.addStretch(1)
        btn_nuevo_plan = self._btn("Nuevo plan", self._nuevo_plan, T.ANALISIS)
        btn_nuevo_plan.setMinimumWidth(btn_nuevo_plan.sizeHint().width() + 16)
        barra.addWidget(btn_nuevo_plan)
        barra.addWidget(self._btn("Detalle / IA", self._detalle, T.INFO))
        barra.addWidget(self._btn("Revisar con agentes", self._revisar_agentes, T.ANALISIS))
        barra.addWidget(self._btn("Validar", self._validar, T.INFO))
        btn_solicitar = self._btn("Solicitar aprobación", self._solicitar, T.INFO)
        btn_solicitar.setMinimumWidth(btn_solicitar.sizeHint().width() + 16)
        barra.addWidget(btn_solicitar)
        barra.addWidget(self._btn("Aprobar", self._aprobar, T.OK))
        barra.addWidget(self._btn("Ejecutar", self._ejecutar, T.INFO))
        barra.addWidget(self._btn("Revertir", self._revertir, T.CRITICO))
        barra.addWidget(self._btn("Cancelar plan", self._cancelar, T.CRITICO))
        root.addLayout(barra)

        self.aviso = QLabel("La IA propone, la organización decide, el sistema ejecuta solo lo "
                            "autorizado. Las acciones críticas quedan como propuesta.")
        self.aviso.setStyleSheet(f"color:{T.ADVERTENCIA};font-size:11px;")
        self.aviso.setWordWrap(True)
        root.addWidget(self.aviso)

        root.addWidget(QLabel("Planes de ejecución"))
        # Actualizar en la esquina superior derecha de la tabla; contador "N filas" abajo-izquierda.
        self.t_planes = EnterpriseTable(["Id", "Nombre", "Estado", "Riesgo", "Modo"], con_busqueda=True,
                                        con_actualizar=self._cargar, contador_abajo=True,
                                        actualizar_pos="derecha")
        self.t_planes.tabla.cellClicked.connect(self._sel_plan)
        root.addWidget(self.t_planes)

        self._cargar()

    def _btn(self, txt, slot, color):
        from PyQt6.QtCore import Qt
        b = QPushButton(txt); b.clicked.connect(slot)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};border:2px solid {color};"
                        f"border-radius:8px;font-weight:800;font-size:14px;padding:5px 12px;}}"
                        f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        return b

    def _perfil(self):
        return (self.usuario.get("perfil") if isinstance(self.usuario, dict) else None) or "ADMINISTRADOR"

    def _uid(self):
        return self.usuario.get("nombre") if isinstance(self.usuario, dict) else None

    def _sel_plan(self, row, _col):
        it = self.t_planes.tabla.item(row, 0)
        self._plan_sel = int(it.text()) if it and it.text().isdigit() else None

    _NIVEL_AVISO = {"ok": "success", "critico": "error", "advertencia": "warning", "info": "info"}

    def _notificar(self, txt, rol="info"):
        """Aviso emergente (mismo criterio que el resto de la app) — sin estado inline persistente."""
        _aviso(self, "Autonomía IA", txt, self._NIVEL_AVISO.get(rol, "info"))

    def _aplicar_modo(self):
        try:
            _svc().establecer_modo(self.cmb_modo.currentData(), self.id_empresa)
            self._notificar(f"Modo de empresa: {self.cmb_modo.currentData()}", "ok")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error modo: {e}", "critico")

    def _nuevo_plan(self):
        try:
            from src.services import simulador
            escenarios = simulador.servicio().escenarios(self.id_empresa)
        except Exception as e:
            _aviso(self, "Nuevo plan", f"Error al listar escenarios: {e}", "error")
            return
        if not escenarios:
            _aviso(self, "Nuevo plan", "No hay escenarios simulados todavía — crea uno primero en "
                                       "el Simulador (Centro de Inteligencia).", "warning")
            return
        dlg = _NuevoPlanDialog(self, escenarios)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        id_escenario = dlg.escenario_sel()
        if not id_escenario:
            return
        try:
            pid = _svc().plan_desde_escenario(id_escenario, usuario=self._uid(), id_empresa=self.id_empresa)
            if pid:
                _aviso(self, "Nuevo plan", f"Plan #{pid} creado correctamente.", "success")
                self._cargar()
            else:
                _aviso(self, "Nuevo plan", "No se pudo crear el plan a partir del escenario.", "error")
        except Exception as e:
            _aviso(self, "Nuevo plan", str(e), "error")

    def _requiere_plan(self):
        if not self._plan_sel:
            self._notificar("Selecciona un plan en la tabla.", "advertencia")
            return False
        return True

    def _detalle(self):
        if not self._requiere_plan():
            return
        try:
            svc = _svc()
            det = svc.detalle_plan(self._plan_sel, self.id_empresa)
            if det.get("error"):
                self._notificar(det["error"], "critico")
                return
            exp = svc.explicar(self._plan_sel, self.id_empresa)
            rec = svc.recomendacion_ia(self._plan_sel, self.id_empresa)
            _DetallePlanDialog(self, det, exp, rec).exec()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _revisar_agentes(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().revisar_con_agentes(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                           id_empresa=self.id_empresa)
            _RevisarAgentesDialog(self, r).exec()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _validar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().validar(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                               id_empresa=self.id_empresa)
            _ValidarPlanDialog(self, r).exec()
            self._notificar(f"Plan #{self._plan_sel}: validación {'OK' if r.get('ok') else 'con incidencias'}",
                             "ok" if r.get("ok") else "advertencia")
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _cancelar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().cancelar_plan(self._plan_sel, usuario=self._uid(), id_empresa=self.id_empresa)
            self._notificar(f"Plan #{self._plan_sel} → {r.get('estado')}", "advertencia")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _solicitar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().solicitar_aprobacion(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                            id_empresa=self.id_empresa)
            self._notificar(f"Plan #{self._plan_sel}: {r.get('estado')}", "info")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _aprobar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().aprobar_plan(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                    id_empresa=self.id_empresa)
            ok = r.get("aprobado")
            self._notificar((f"Plan #{self._plan_sel} APROBADO" if ok else f"No aprobado: {r.get('motivo')}"),
                             "ok" if ok else "critico")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _ejecutar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().ejecutar(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                id_empresa=self.id_empresa)
            if r.get("error"):
                self._notificar(f"No ejecutado: {r['error']}", "critico")
            else:
                self._notificar(f"Plan #{self._plan_sel} → {r.get('estado')} "
                                 "(críticas tramitadas como propuesta)", "ok")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _revertir(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().revertir(self._plan_sel, usuario=self._uid(), id_empresa=self.id_empresa)
            self._notificar(f"Plan #{self._plan_sel} revertido ({r.get('revertidas', 0)} acciones)", "advertencia")
            self._cargar()
        except Exception as e:
            self._notificar(f"Error: {e}", "critico")

    def _cargar(self):
        emp = self.id_empresa
        svc = _svc()
        self.grid.limpiar()
        try:
            db = svc.dashboard(emp)
            self.grid.add_card(EnterpriseCard("Automatización", f"{db.get('nivel_automatizacion_pct', 0)}%",
                                              modo="kpi", concepto="autonomia"))
            self.grid.add_card(EnterpriseCard("Ejecutados", db.get("planes_ejecutados", 0), modo="kpi", concepto="ok"))
            self.grid.add_card(EnterpriseCard("Reversiones", db.get("reversiones", 0), modo="kpi", concepto="riesgo"))
            self.grid.add_card(EnterpriseCard("Modo", db.get("modo_empresa", "-"), modo="estado", concepto="gobierno"))
        except Exception as e:
            logger.debug("dashboard autonomia: %s", e)
        try:
            filas = [{"Id": p.get("id"), "Nombre": p.get("nombre"), "Estado": p.get("estado"),
                      "Riesgo": p.get("riesgo"), "Modo": p.get("modo")} for p in svc.planes(emp)]
            self.t_planes.set_datos(filas)
        except Exception as e:
            logger.debug("planes: %s", e)
