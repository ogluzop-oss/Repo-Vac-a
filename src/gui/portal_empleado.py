"""
Portal del Empleado (F4.10) — GUI de autoconsulta del trabajador.

Solo lectura sobre la fachada `rrhh.portal_servicio` (que reutiliza expediente/servicios
RRHH). El trabajador ve SU información (resuelta por su cuenta de usuario) y puede
solicitar vacaciones y abrir/exportar sus documentos. Reutiliza los helpers de
`catalogo_gestion`. Multiempresa por id_empresa; nunca muestra datos de otros empleados.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTabWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BORDE, _CIAN, _DIM, _SIDEBAR, _TEXT,
                                      _btn, _inp, _tabla)

logger = logging.getLogger("rrhh.portal.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class PortalEmpleadoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Portal del Empleado")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.empleado = self._resolver()
        if not self.empleado:
            aviso = QLabel("Tu cuenta no tiene un expediente de empleado vinculado.\n"
                           "Contacta con RRHH para activar el portal.")
            aviso.setStyleSheet(f"color:{_DIM};font-size:14px;")
            root.addWidget(aviso, alignment=Qt.AlignmentFlag.AlignCenter)
            return

        self._panel = self._cargar_panel()
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        tabs.addTab(self._tab_personal(), "Mis datos")
        tabs.addTab(self._tab_contratos(), "Contratos")
        tabs.addTab(self._tab_nominas(), "Nóminas")
        tabs.addTab(self._tab_vacaciones(), "Vacaciones")
        tabs.addTab(self._tab_ausencias(), "Ausencias")
        tabs.addTab(self._tab_horario(), "Control horario")
        tabs.addTab(self._tab_pendientes(), "Documentos pendientes")
        tabs.addTab(self._tab_documentos(), "Documentos")
        root.addWidget(tabs)

    # ── resolución segura ─────────────────────────────────────────────────────
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _resolver(self):
        from src.rrhh import portal_servicio
        try:
            return portal_servicio.resolver_empleado(self.usuario, self._id_empresa())
        except Exception as e:
            logger.error("resolver portal: %s", e); return None

    def _cargar_panel(self):
        from src.rrhh import portal_servicio
        return portal_servicio.panel(self.empleado["id"], self._id_empresa())

    # ── pestañas ──────────────────────────────────────────────────────────────
    def _tabla(self, cols, filas, fila_fn):
        t = _tabla(cols); filas = filas or []
        t.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, v in enumerate(fila_fn(r)):
                t.setItem(i, j, _it(v))
        return t

    def _tab_personal(self):
        from PyQt6.QtWidgets import QFormLayout
        p = self._panel["personal"]
        w = QWidget(); fl = QFormLayout(w)
        for et, val in (("Nombre", f"{p.get('nombre','')} {p.get('apellidos') or ''}".strip()),
                        ("NIF/NIE", p.get("nif")), ("Email", p.get("email")),
                        ("Teléfono", p.get("telefono")), ("Puesto", p.get("puesto")),
                        ("Categoría", p.get("categoria")), ("Convenio", p.get("convenio")),
                        ("Fecha de alta", p.get("fecha_alta")), ("Estado", p.get("estado"))):
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            v = QLabel("" if val is None else str(val)); v.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            fl.addRow(lab, v)
        return w

    def _tab_contratos(self):
        return self._tabla(["Modalidad", "Inicio", "Fin", "Estado"], self._panel["contratos"],
                           lambda r: [r.get("modalidad"), r.get("fecha_inicio"), r.get("fecha_fin"),
                                      r.get("estado")])

    def _tab_nominas(self):
        return self._tabla(["Año", "Mes", "Bruto", "Neto", "IRPF", "SS", "Fecha"],
                           self._panel["nominas"],
                           lambda r: [r.get("anio"), r.get("mes"), r.get("bruto"), r.get("neto"),
                                      r.get("irpf_importe"), r.get("ss_importe"), r.get("fecha")])

    def _tab_vacaciones(self):
        w = QWidget(); ly = QVBoxLayout(w)
        s = self._panel["vacaciones"]["saldo"]
        lbl = QLabel(f"Saldo {s['anio']}: disponibles {s['disponibles']} · "
                     f"disfrutadas {s['disfrutados']} · pendientes {s['pendientes']}")
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        ly.addWidget(lbl)
        self.tbl_vac = self._tabla(["Inicio", "Fin", "Días", "Estado"],
                                   self._panel["vacaciones"]["lista"],
                                   lambda r: [r.get("fecha_inicio"), r.get("fecha_fin"),
                                              r.get("dias"), r.get("estado")])
        ly.addWidget(self.tbl_vac)
        f = QHBoxLayout()
        self.v_ini = _inp("Inicio AAAA-MM-DD"); self.v_fin = _inp("Fin AAAA-MM-DD")
        f.addWidget(self.v_ini); f.addWidget(self.v_fin)
        f.addWidget(_btn("Solicitar vacaciones", self._solicitar, primary=True))
        ly.addLayout(f)
        return w

    def _tab_ausencias(self):
        return self._tabla(["Tipo", "Inicio", "Fin", "Días", "Motivo"], self._panel["ausencias"],
                           lambda r: [r.get("tipo"), r.get("fecha_inicio"), r.get("fecha_fin"),
                                      r.get("dias"), r.get("motivo")])

    def _tab_horario(self):
        w = QWidget(); ly = QVBoxLayout(w)
        tot = self._panel["control_horario"]["totales"]
        lbl = QLabel(f"Días {tot['dias']} · efectivo {tot['efectivo_min']} min · "
                     f"horas extra {tot['exceso_min']} min · déficit {tot['deficit_min']} min")
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        ly.addWidget(lbl)
        ly.addWidget(self._tabla(["Fecha", "Entrada", "Salida", "Efectivo(min)", "Exceso", "Déficit"],
                     self._panel["control_horario"]["jornadas"],
                     lambda r: [r.get("fecha"), r.get("hora_entrada"), r.get("hora_salida"),
                                r.get("tiempo_efectivo_min"), r.get("exceso_min"), r.get("deficit_min")]))
        ly.addWidget(_btn("Exportar CSV", self._export_horario), alignment=Qt.AlignmentFlag.AlignLeft)
        return w

    def _tab_pendientes(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self._pend = self._panel.get("documentos_pendientes", [])
        self.tbl_pend = self._tabla(["id", "Fecha", "Tipo", "Estado", "Expira"], self._pend,
                                    lambda r: [r.get("id"), r.get("fecha"), r.get("tipo_doc"),
                                               r.get("estado_firma"), r.get("expira")])
        ly.addWidget(self.tbl_pend)
        b = QHBoxLayout()
        b.addWidget(_btn("Abrir", self._abrir_pend))
        b.addWidget(_btn("Aceptar", self._aceptar, primary=True))
        b.addWidget(_btn("Rechazar", self._rechazar))
        ly.addLayout(b)
        return w

    def _pend_sel(self):
        i = self.tbl_pend.currentRow()
        return self._pend[i] if 0 <= i < len(self._pend) else None

    def _abrir_pend(self):
        d = self._pend_sel()
        ruta = (d or {}).get("ref_documento")
        if ruta and os.path.exists(ruta):
            try:
                os.startfile(ruta)  # noqa: S606
            except Exception as e:
                QMessageBox.warning(self, "Portal", f"No se pudo abrir: {e}")
        else:
            QMessageBox.information(self, "Portal", "El documento no está disponible en disco.")

    def _firma(self, accion):
        from src.rrhh import portal_servicio
        from src.rrhh.firma_servicio import FirmaError
        d = self._pend_sel()
        if not d:
            QMessageBox.information(self, "Portal", "Selecciona un documento."); return
        usuario = (self.usuario or {}).get("nombre")
        fn = (portal_servicio.aceptar_documento if accion == "acepta"
              else portal_servicio.rechazar_documento)
        try:
            fn(self.empleado["id"], d["id"], usuario=usuario, id_empresa=self._id_empresa())
        except FirmaError as e:
            QMessageBox.warning(self, "Portal", str(e)); return
        QMessageBox.information(self, "Portal", f"Documento {accion}do.")
        self._panel = self._cargar_panel()
        self._pend = self._panel.get("documentos_pendientes", [])
        self.tbl_pend.setRowCount(0)
        for i, r in enumerate(self._pend):
            self.tbl_pend.insertRow(i)
            for j, v in enumerate([r.get("id"), r.get("fecha"), r.get("tipo_doc"),
                                   r.get("estado_firma"), r.get("expira")]):
                self.tbl_pend.setItem(i, j, _it(v))

    def _aceptar(self):
        self._firma("acepta")

    def _rechazar(self):
        self._firma("rechaza")

    def _tab_documentos(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self._docs = self._panel["documentos"]
        self.tbl_docs = self._tabla(["Fecha", "Tipo", "Referencia"], self._docs,
                                    lambda r: [r.get("fecha"), r.get("tipo_doc"), r.get("ref_documento")])
        ly.addWidget(self.tbl_docs)
        ly.addWidget(_btn("Abrir documento", self._abrir_doc), alignment=Qt.AlignmentFlag.AlignLeft)
        return w

    # ── acciones ──────────────────────────────────────────────────────────────
    def _solicitar(self):
        from src.rrhh import portal_servicio
        from src.rrhh.vacaciones_servicio import GestionLaboralError
        try:
            portal_servicio.solicitar_vacaciones(self.empleado["id"], self.v_ini.text().strip(),
                                                 self.v_fin.text().strip(), self._id_empresa())
        except GestionLaboralError as e:
            QMessageBox.warning(self, "Vacaciones", str(e)); return
        QMessageBox.information(self, "Vacaciones", "Solicitud enviada.")
        self._panel = self._cargar_panel()
        self.tbl_vac.setRowCount(0)
        for i, r in enumerate(self._panel["vacaciones"]["lista"]):
            self.tbl_vac.insertRow(i)
            for j, v in enumerate([r.get("fecha_inicio"), r.get("fecha_fin"), r.get("dias"), r.get("estado")]):
                self.tbl_vac.setItem(i, j, _it(v))

    def _export_horario(self):
        from PyQt6.QtWidgets import QFileDialog
        from src.rrhh import portal_servicio
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar control horario",
                                              "mi_control_horario.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                fh.write(portal_servicio.exportar_control_horario(self.empleado["id"], self._id_empresa()))
            QMessageBox.information(self, "Portal", f"Exportado a {ruta}")
        except Exception as e:
            QMessageBox.warning(self, "Portal", f"No se pudo exportar: {e}")

    def _abrir_doc(self):
        i = self.tbl_docs.currentRow()
        if not (0 <= i < len(self._docs)):
            QMessageBox.information(self, "Portal", "Selecciona un documento."); return
        ruta = self._docs[i].get("ref_documento")
        if ruta and os.path.exists(ruta):
            try:
                os.startfile(ruta)  # noqa: S606 (Windows; documento propio del empleado)
            except Exception as e:
                QMessageBox.warning(self, "Portal", f"No se pudo abrir: {e}")
        else:
            QMessageBox.information(self, "Portal", "El documento no está disponible en disco.")
