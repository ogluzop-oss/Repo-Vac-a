"""
Formulario INLINE de REGISTRO de BAJAS/AUSENCIAS LABORALES (pestaña "Bajas laborales" del sidebar
de RRHH).

Sustituye al antiguo formulario que generaba un PDF ("Generar baja (PDF)"): esta pestaña es pura
REGISTRACIÓN. Escribe directamente en `rrhh_ausencias` a través del MISMO servicio real que ya usa
el diálogo "Vac./Ausencias" de la pestaña Empleados (`GestionLaboralDialog._tab_aus`, en
`rrhh_gestion.py`) — `src.rrhh.ausencias_servicio.registrar()`/`listar()`. No crea un segundo
mecanismo paralelo de seguimiento de bajas ni genera ningún documento: solo el registro estructurado
en base de datos, que ya publica el evento `BAJA_REGISTRADA` (ver `src/rrhh/db/ausencias.py`).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)
from src.gui.catalogo_gestion import _tabla

logger = logging.getLogger("gui.rrhh.baja_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
# Desplegables: 1px menos que los campos de texto (mismo criterio que el resto de formularios RRHH).
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")


class BajaLaboralForm(QWidget):
    """Registro directo de una baja/ausencia laboral (sin PDF). `id_empresa_getter` es un callable
    (igual que el resto de formularios inline de esta ventana)."""

    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._empleados = []
        self._build()
        self._cargar_empleados()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(40)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border:none;"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_ACCION_TEXTO};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};}}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};}}")
        b.clicked.connect(cb); return b

    def _seccion(self, ly, titulo):
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLOR_BORDE};")
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;font-weight:900;"
                          "letter-spacing:1px;background:transparent;margin-top:4px;")
        ly.addWidget(lbl); ly.addWidget(line)

    def _build(self):
        from src.rrhh import ausencias_servicio as AS

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(self._lbl("Empleado:"))
        self.cb_emp = QComboBox(); self.cb_emp.setMinimumWidth(280)
        self.cb_emp.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        self.cb_emp.currentIndexChanged.connect(self._on_empleado)
        top.addWidget(self.cb_emp, 1)
        top.addStretch()
        root.addLayout(top)

        # Ficha del trabajador (solo lectura, autocompletada al elegir empleado — no son datos que
        # se envíen al registrar: el vínculo real es `id_empleado`, ya conocido por la selección).
        self.lbl_ficha = QLabel("Selecciona un empleado para ver su ficha.")
        self.lbl_ficha.setWordWrap(True)
        self.lbl_ficha.setStyleSheet("color:#9BA3AE;font-family:'Segoe UI';font-size:13px;"
                                     "background:transparent;")
        root.addWidget(self.lbl_ficha)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); form_ly = QVBoxLayout(cont)
        form_ly.setContentsMargins(2, 4, 12, 4); form_ly.setSpacing(14)

        self._seccion(form_ly, "Datos de la baja")
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)

        def _campo(row, col, etiqueta, widget, span=1):
            cel = QVBoxLayout(); cel.setSpacing(2)
            cel.addWidget(self._lbl(etiqueta)); cel.addWidget(widget)
            w = QWidget(); w.setLayout(cel)
            grid.addWidget(w, row, col, 1, span)

        self.cb_tipo = QComboBox(); self.cb_tipo.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for k, et in AS.TIPOS.items():
            self.cb_tipo.addItem(et, k)
        self.cb_tipo.currentIndexChanged.connect(self._actualizar_visibilidad_contingencia)
        _campo(0, 0, "Tipo de baja *", self.cb_tipo)

        self.in_ini = QLineEdit(); self.in_ini.setPlaceholderText("AAAA-MM-DD")
        self.in_ini.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        _campo(0, 1, "Fecha de baja *", self.in_ini)

        self.in_fin = QLineEdit(); self.in_fin.setPlaceholderText("AAAA-MM-DD")
        self.in_fin.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        _campo(1, 0, "Fecha prevista de alta *", self.in_fin)

        self.chk_justificada = QCheckBox("Justificada")
        self.chk_justificada.setStyleSheet("color:#C9D1D9;font-family:'Segoe UI';font-size:13px;"
                                           "background:transparent;")
        self.chk_justificada.setChecked(True)
        cel = QVBoxLayout(); cel.setSpacing(2)
        cel.addWidget(self._lbl(" "))
        cel.addWidget(self.chk_justificada)
        wchk = QWidget(); wchk.setLayout(cel)
        grid.addWidget(wchk, 1, 1, 1, 1)

        holder = QWidget(); holder.setLayout(grid)
        form_ly.addWidget(holder)

        # Contingencia: solo visible/relevante cuando el tipo elegido es baja médica
        # (`AS.TIPO_BAJA_MEDICA`) — alimenta el motor de Incapacidad Temporal (Fase F). Mismo
        # criterio condicional que `GestionLaboralDialog._tab_aus`.
        fc = QHBoxLayout()
        self.lbl_conting = self._lbl("Tipo de contingencia:")
        fc.addWidget(self.lbl_conting)
        self.cb_conting = QComboBox(); self.cb_conting.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for k, et in AS.TIPOS_CONTINGENCIA.items():
            self.cb_conting.addItem(et, k)
        fc.addWidget(self.cb_conting, 1)
        form_ly.addLayout(fc)
        self._actualizar_visibilidad_contingencia()

        self._seccion(form_ly, "Motivo / observaciones")
        self.in_motivo = QPlainTextEdit(); self.in_motivo.setFixedHeight(70)
        self.in_motivo.setStyleSheet(f"QPlainTextEdit{{{_INP_SS}}}")
        form_ly.addWidget(self.in_motivo)

        form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        bottom.addWidget(self._btn("Registrar baja", self._registrar, primary=True))
        root.addLayout(bottom)

        self._seccion_lista = self._lbl("BAJAS / AUSENCIAS YA REGISTRADAS DEL EMPLEADO")
        root.addWidget(self._seccion_lista)
        self.tbl = _tabla(["Tipo", "Inicio", "Fin", "Días", "Contingencia", "Motivo"])
        self.tbl.setMinimumHeight(160)
        root.addWidget(self.tbl)

    def _actualizar_visibilidad_contingencia(self, *_args):
        from src.rrhh import ausencias_servicio as AS
        es_baja_medica = self.cb_tipo.currentData() == AS.TIPO_BAJA_MEDICA
        self.lbl_conting.setVisible(es_baja_medica)
        self.cb_conting.setVisible(es_baja_medica)

    # ── Datos ─────────────────────────────────────────────────────────────────
    def _cargar_empleados(self):
        try:
            from src.rrhh.db import empleados
            self._empleados = empleados.listar_empleados(self._id_empresa(), estado="activo") or []
        except Exception as e:
            logger.debug("cargar empleados: %s", e); self._empleados = []
        self.cb_emp.blockSignals(True); self.cb_emp.clear()
        self.cb_emp.addItem("— Selecciona un empleado —", None)
        for e in self._empleados:
            nom = f"{e.get('nombre','')} {e.get('apellidos','')}".strip()
            self.cb_emp.addItem(f"{nom}  ·  {e.get('nif','')}", e)
        self.cb_emp.blockSignals(False)

    def _on_empleado(self, _i):
        emp = self.cb_emp.currentData()
        if not emp:
            self.lbl_ficha.setText("Selecciona un empleado para ver su ficha.")
            self.tbl.setRowCount(0)
            return
        nom = f"{emp.get('nombre','')} {emp.get('apellidos','')}".strip()
        self.lbl_ficha.setText(
            f"{nom}  ·  DNI/NIE {emp.get('nif','—')}  ·  Nº SS {emp.get('num_ss') or '—'}  ·  "
            f"Categoría {emp.get('categoria') or '—'}  ·  Puesto {emp.get('puesto') or '—'}")
        self._refrescar_lista(emp.get("id"))

    def _refrescar_lista(self, id_empleado):
        if not id_empleado:
            self.tbl.setRowCount(0)
            return
        from src.rrhh import ausencias_servicio as AS
        filas = AS.listar(id_empleado, self._id_empresa())
        self.tbl.setRowCount(len(filas))
        for i, a in enumerate(filas):
            vals = [
                AS.TIPOS.get(a.get("tipo"), a.get("tipo")),
                a.get("fecha_inicio"), a.get("fecha_fin"), a.get("dias"),
                AS.TIPOS_CONTINGENCIA.get(a.get("tipo_contingencia"), a.get("tipo_contingencia") or "—"),
                a.get("motivo"),
            ]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

    # ── Registro ──────────────────────────────────────────────────────────────
    def _registrar(self):
        from src.rrhh import ausencias_servicio as AS
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Bajas laborales", "Selecciona primero un empleado.", "warning")
            return
        tipo = self.cb_tipo.currentData()
        conting = self.cb_conting.currentData() if tipo == AS.TIPO_BAJA_MEDICA else None
        try:
            AS.registrar(
                emp["id"], tipo, self.in_ini.text().strip(), self.in_fin.text().strip(),
                motivo=self.in_motivo.toPlainText().strip(),
                justificada=self.chk_justificada.isChecked(),
                tipo_contingencia=conting, id_empresa=self._id_empresa())
        except AS.GestionLaboralError as e:
            mostrar_mensaje(self, "Bajas laborales", str(e), "error")
            return
        except Exception as e:
            logger.error("registrar baja: %s", e)
            mostrar_mensaje(self, "Bajas laborales", "No se pudo registrar la baja.", "error")
            return
        mostrar_mensaje(self, "Bajas laborales", "Baja registrada correctamente.", "success")
        self.in_ini.clear(); self.in_fin.clear(); self.in_motivo.clear()
        self.chk_justificada.setChecked(True)
        self._refrescar_lista(emp["id"])
