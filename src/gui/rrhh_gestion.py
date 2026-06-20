"""
GUI de RRHH — gestión de empleados y visor de expediente (F4.4).

Capa VISUAL sobre la infraestructura ya existente (no recalcula, no toca motor/
persistencia/migraciones): consume `src/rrhh/db/*` (empleados + expediente) y reutiliza
los patrones de `catalogo_gestion`/`contabilidad_gestion` (sidebar, helpers, estilo).

- Listado de empleados (búsqueda + filtro por estado, por id_empresa/id_tienda).
- Alta/edición de empleado (rrhh_empleados) con validaciones.
- Visor de expediente (ficha + contratos + nóminas + vacaciones + ausencias + documentos)
  vía `empleados.expediente()`.
"""

import json
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialogButtonBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QMessageBox, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _SIDEBAR, _TEXT,
                                      _btn, _combo, _inp, _tabla)

logger = logging.getLogger("rrhh.gui")

_ESTADOS = [("Activo", "activo"), ("Baja", "baja"), ("Suspendido", "suspendido"),
            ("Excedencia", "excedencia")]
_SEXOS = [("—", ""), ("Hombre", "H"), ("Mujer", "M"), ("Otro", "X")]


def _it(txt):
    return QTableWidgetItem("" if txt is None else str(txt))


# ── Formulario de alta / edición ──────────────────────────────────────────────
class EmpleadoFormDialog(QDialog):
    """Alta/edición sobre rrhh_empleados. `empleado` (dict) → modo edición."""

    def __init__(self, empleado=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.empleado = empleado or {}
        self.id_empresa = id_empresa
        self.resultado_id = None
        self.setWindowTitle("Editar empleado" if empleado else "Nuevo empleado")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};font-size:12px;}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        e = self.empleado
        # Identificación
        self.in_nombre = _inp("Nombre", ); self.in_nombre.setText(e.get("nombre", ""))
        self.in_apellidos = _inp(); self.in_apellidos.setText(e.get("apellidos") or "")
        self.cb_sexo = _combo(_SEXOS, e.get("sexo") or "")
        self.in_fnac = _inp("AAAA-MM-DD"); self.in_fnac.setText(str(e.get("fecha_nacimiento") or ""))
        self.in_nac = _inp(); self.in_nac.setText(e.get("nacionalidad") or "")
        self.in_nif = _inp("NIF/NIE *"); self.in_nif.setText(e.get("nif") or "")
        self.in_ss = _inp(); self.in_ss.setText(e.get("num_ss") or "")
        tabs.addTab(self._form([
            ("Nombre *", self.in_nombre), ("Apellidos", self.in_apellidos), ("Sexo", self.cb_sexo),
            ("Fecha nacimiento", self.in_fnac), ("Nacionalidad", self.in_nac),
            ("NIF/NIE *", self.in_nif), ("Nº Seguridad Social", self.in_ss)]), "Identificación")
        # Contacto
        self.in_dir = _inp(); self.in_dir.setText(e.get("direccion") or "")
        self.in_mun = _inp(); self.in_mun.setText(e.get("municipio") or "")
        self.in_prov = _inp(); self.in_prov.setText(e.get("provincia") or "")
        self.in_cp = _inp(); self.in_cp.setText(e.get("cp") or "")
        self.in_pais = _inp(); self.in_pais.setText(e.get("pais") or "ESPAÑA")
        self.in_tel = _inp(); self.in_tel.setText(e.get("telefono") or "")
        self.in_email = _inp(); self.in_email.setText(e.get("email") or "")
        tabs.addTab(self._form([
            ("Dirección", self.in_dir), ("Municipio", self.in_mun), ("Provincia", self.in_prov),
            ("CP", self.in_cp), ("País", self.in_pais), ("Teléfono", self.in_tel),
            ("Email", self.in_email)]), "Contacto")
        # Laboral
        self.cb_centro = _combo(self._opciones_centros(), e.get("id_centro"))
        self.in_cat = _inp(); self.in_cat.setText(e.get("categoria") or "")
        self.in_grupo = _inp(); self.in_grupo.setText(e.get("grupo_prof") or "")
        self.in_conv = _inp(); self.in_conv.setText(e.get("convenio") or "")
        self.in_puesto = _inp(); self.in_puesto.setText(e.get("puesto") or "")
        self.in_sal = _inp("0.00"); self.in_sal.setText(str(e.get("salario_base") or ""))
        self.in_jor = _inp(); self.in_jor.setText(e.get("jornada") or "")
        self.cb_estado = _combo(_ESTADOS, e.get("estado") or "activo")
        tabs.addTab(self._form([
            ("Centro de trabajo", self.cb_centro), ("Categoría", self.in_cat),
            ("Grupo profesional", self.in_grupo), ("Convenio", self.in_conv),
            ("Puesto", self.in_puesto), ("Salario base mensual", self.in_sal),
            ("Jornada", self.in_jor), ("Estado", self.cb_estado)]), "Laboral")
        root.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._guardar); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _form(self, filas):
        w = QWidget(); fl = QFormLayout(w)
        for et, widget in filas:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            fl.addRow(lab, widget)
        return w

    def _opciones_centros(self):
        ops = [("— Sin centro —", None)]
        try:
            from src.rrhh.db import centros
            for c in centros.listar_centros(self.id_empresa):
                ops.append((c.get("nombre_centro") or c.get("id_centro"), c.get("id_centro")))
        except Exception as ex:
            logger.error("opciones_centros: %s", ex)
        return ops

    def _campos(self):
        def _f(x):
            try:
                return float(str(x).replace(",", ".")) if str(x).strip() else 0.0
            except ValueError:
                return 0.0
        return dict(
            nombre=self.in_nombre.text().strip(), apellidos=self.in_apellidos.text().strip(),
            sexo=self.cb_sexo.currentData(), fecha_nacimiento=self.in_fnac.text().strip() or None,
            nacionalidad=self.in_nac.text().strip(), nif=self.in_nif.text().strip().upper(),
            num_ss=self.in_ss.text().strip(), direccion=self.in_dir.text().strip(),
            municipio=self.in_mun.text().strip(), provincia=self.in_prov.text().strip(),
            cp=self.in_cp.text().strip(), pais=self.in_pais.text().strip(),
            telefono=self.in_tel.text().strip(), email=self.in_email.text().strip(),
            id_centro=self.cb_centro.currentData(), categoria=self.in_cat.text().strip(),
            grupo_prof=self.in_grupo.text().strip(), convenio=self.in_conv.text().strip(),
            puesto=self.in_puesto.text().strip(), salario_base=_f(self.in_sal.text()),
            jornada=self.in_jor.text().strip(), estado=self.cb_estado.currentData() or "activo")

    def _guardar(self):
        from src.rrhh.db import empleados
        campos = self._campos()
        if not campos["nombre"] or not campos["nif"]:
            QMessageBox.warning(self, "RRHH", "Nombre y NIF/NIE son obligatorios.")
            return
        if self.empleado.get("id"):
            ok = empleados.actualizar_empleado(self.empleado["id"], self.id_empresa, **campos)
            if ok:
                self.resultado_id = self.empleado["id"]; self.accept()
            else:
                QMessageBox.warning(self, "RRHH", "No se pudo actualizar el empleado.")
        else:
            eid = empleados.crear_empleado(id_empresa=self.id_empresa, **campos)
            if eid:
                self.resultado_id = eid; self.accept()
            else:
                QMessageBox.warning(self, "RRHH",
                                    "No se pudo crear (¿NIF duplicado en esta empresa?).")


# ── Visor de expediente ───────────────────────────────────────────────────────
class ExpedienteDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Expediente del trabajador")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        from src.rrhh.db import empleados
        exp = empleados.expediente(self.id_empleado, self.id_empresa) or {}
        self.exp = exp
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        emp = exp.get("empleado") or {}
        tabs.addTab(self._ficha(emp), "Ficha")
        tabs.addTab(self._tabla_simple(exp.get("contratos"),
                    ["Modalidad", "Inicio", "Fin", "Salario", "Estado"],
                    lambda r: [r.get("modalidad"), r.get("fecha_inicio"), r.get("fecha_fin"),
                               r.get("salario"), r.get("estado")]), "Contratos")
        tabs.addTab(self._tabla_simple(exp.get("nominas"),
                    ["Año", "Mes", "Bruto", "Base", "IRPF", "SS", "Neto"],
                    lambda r: [r.get("anio"), r.get("mes"), r.get("bruto"), r.get("base"),
                               r.get("irpf_importe"), r.get("ss_importe"), r.get("neto")]), "Nóminas")
        tabs.addTab(self._tabla_simple(exp.get("vacaciones"),
                    ["Año", "Tipo", "Inicio", "Fin", "Días", "Estado"],
                    lambda r: [r.get("anio"), r.get("tipo"), r.get("fecha_inicio"),
                               r.get("fecha_fin"), r.get("dias"), r.get("estado")]), "Vacaciones")
        tabs.addTab(self._tabla_simple(exp.get("ausencias"),
                    ["Tipo", "Inicio", "Fin", "Días", "Motivo"],
                    lambda r: [r.get("tipo"), r.get("fecha_inicio"), r.get("fecha_fin"),
                               r.get("dias"), r.get("motivo")]), "Ausencias")
        tabs.addTab(self._docs(exp.get("documentos")), "Documentos")
        root.addWidget(tabs)
        cerrar = _btn("Cerrar", self.accept)
        root.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)

    def _ficha(self, emp):
        w = QWidget(); fl = QFormLayout(w)
        campos = [("Nombre", f"{emp.get('nombre','')} {emp.get('apellidos','') or ''}".strip()),
                  ("NIF/NIE", emp.get("nif")), ("Nº SS", emp.get("num_ss")),
                  ("Puesto", emp.get("puesto")), ("Categoría", emp.get("categoria")),
                  ("Grupo prof.", emp.get("grupo_prof")), ("Convenio", emp.get("convenio")),
                  ("Salario base", emp.get("salario_base")), ("Jornada", emp.get("jornada")),
                  ("Estado", emp.get("estado")), ("Email", emp.get("email")),
                  ("Teléfono", emp.get("telefono"))]
        for et, val in campos:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            v = QLabel("" if val is None else str(val)); v.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            fl.addRow(lab, v)
        return w

    def _tabla_simple(self, filas, cols, fila_fn):
        filas = filas or []
        t = _tabla(cols)
        t.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, val in enumerate(fila_fn(r)):
                t.setItem(i, j, _it(val))
        return t

    def _docs(self, docs):
        docs = docs or []
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_docs = _tabla(["Fecha", "Tipo", "Referencia"])
        self.tbl_docs.setRowCount(len(docs))
        self._docs_data = docs
        for i, d in enumerate(docs):
            self.tbl_docs.setItem(i, 0, _it(d.get("fecha")))
            self.tbl_docs.setItem(i, 1, _it(d.get("tipo_doc")))
            self.tbl_docs.setItem(i, 2, _it(d.get("ref_documento")))
        ly.addWidget(self.tbl_docs)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Abrir PDF", self._abrir_pdf))
        bar.addWidget(_btn("Ver datos", self._ver_snapshot))
        ly.addLayout(bar)
        return w

    def _doc_sel(self):
        i = self.tbl_docs.currentRow()
        return self._docs_data[i] if 0 <= i < len(self._docs_data) else None

    def _abrir_pdf(self):
        d = self._doc_sel()
        ruta = (d or {}).get("ref_documento")
        if ruta and os.path.exists(ruta):
            try:
                os.startfile(ruta)  # noqa: S606 (Windows; apertura del PDF del expediente)
            except Exception as ex:
                QMessageBox.warning(self, "RRHH", f"No se pudo abrir: {ex}")
        else:
            QMessageBox.information(self, "RRHH", "El PDF no está disponible en disco.")

    def _ver_snapshot(self):
        d = self._doc_sel()
        snap = (d or {}).get("datos_snapshot")
        if not snap:
            QMessageBox.information(self, "RRHH", "Sin datos de snapshot."); return
        try:
            txt = json.dumps(json.loads(snap), ensure_ascii=False, indent=2)
        except Exception:
            txt = str(snap)
        QMessageBox.information(self, "Datos del documento", txt[:4000])


# ── Ventana principal ─────────────────────────────────────────────────────────
class RRHHWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Recursos Humanos · Empleados")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        # Toolbar
        tb = QHBoxLayout()
        self.in_buscar = _inp("Buscar nombre / apellidos / NIF…")
        self.in_buscar.returnPressed.connect(self._cargar)
        self.cb_filtro = _combo([("Todos", ""), ("Activos", "activo"), ("Bajas", "baja"),
                                 ("Suspendidos", "suspendido"), ("Excedencias", "excedencia")], "")
        self.cb_filtro.currentIndexChanged.connect(self._cargar)
        tb.addWidget(self.in_buscar, 2); tb.addWidget(self.cb_filtro, 1)
        tb.addWidget(_btn("Buscar", self._cargar))
        tb.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        tb.addWidget(_btn("Editar", self._editar))
        tb.addWidget(_btn("Vac./Ausencias", self._gestion_laboral))
        tb.addWidget(_btn("Expediente", self._expediente, primary=True))
        root.addLayout(tb)
        # Tabla
        self.tbl = _tabla(["Nombre", "Apellidos", "NIF/NIE", "Puesto", "Convenio", "Estado", "Alta"])
        self.tbl.doubleClicked.connect(self._expediente)
        root.addWidget(self.tbl)
        self._cargar()

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _cargar(self):
        from src.rrhh.db import empleados
        estado = self.cb_filtro.currentData() or None
        texto = self.in_buscar.text().strip() or None
        self._filas = empleados.listar_empleados(self._id_empresa(), estado=estado, texto=texto)
        self.tbl.setRowCount(len(self._filas))
        for i, e in enumerate(self._filas):
            vals = [e.get("nombre"), e.get("apellidos"), e.get("nif"), e.get("puesto"),
                    e.get("convenio"), e.get("estado"), e.get("fecha_alta")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tbl.currentRow()
        return self._filas[i] if 0 <= i < len(self._filas) else None

    def _nuevo(self):
        dlg = EmpleadoFormDialog(id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _editar(self):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        dlg = EmpleadoFormDialog(empleado=e, id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _expediente(self, *_):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        ExpedienteDialog(e["id"], self._id_empresa(), parent=self).exec()

    def _gestion_laboral(self, *_):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        GestionLaboralDialog(e["id"], self._id_empresa(), parent=self).exec()


# ── Gestión operativa de vacaciones y ausencias (F4.7) ────────────────────────
class GestionLaboralDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Vacaciones y ausencias")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_saldo = QLabel(""); self.lbl_saldo.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        root.addWidget(self.lbl_saldo)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        tabs.addTab(self._tab_vac(), "Vacaciones")
        tabs.addTab(self._tab_aus(), "Ausencias")
        tabs.addTab(self._tab_cal(), "Calendario")
        root.addWidget(tabs)
        root.addWidget(_btn("Cerrar", self.accept), alignment=Qt.AlignmentFlag.AlignRight)
        self._refrescar()

    # Vacaciones
    def _tab_vac(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_vac = _tabla(["id", "Inicio", "Fin", "Días", "Estado", "Aprob. por"])
        ly.addWidget(self.tbl_vac)
        f = QHBoxLayout()
        self.v_ini = _inp("Inicio AAAA-MM-DD"); self.v_fin = _inp("Fin AAAA-MM-DD")
        f.addWidget(self.v_ini); f.addWidget(self.v_fin)
        f.addWidget(_btn("Solicitar", self._solicitar, primary=True))
        ly.addLayout(f)
        a = QHBoxLayout()
        a.addWidget(_btn("Aprobar", lambda: self._estado_vac("aprobar")))
        a.addWidget(_btn("Denegar", lambda: self._estado_vac("denegar")))
        a.addWidget(_btn("Cancelar", lambda: self._estado_vac("cancelar")))
        ly.addLayout(a)
        return w

    # Ausencias
    def _tab_aus(self):
        from src.rrhh import ausencias_servicio as AS
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_aus = _tabla(["id", "Tipo", "Inicio", "Fin", "Días", "Motivo"])
        ly.addWidget(self.tbl_aus)
        f = QHBoxLayout()
        self.a_tipo = _combo([(et, k) for k, et in AS.TIPOS.items()])
        self.a_ini = _inp("Inicio"); self.a_fin = _inp("Fin"); self.a_mot = _inp("Motivo")
        for wd in (self.a_tipo, self.a_ini, self.a_fin, self.a_mot):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar", self._registrar_aus, primary=True))
        ly.addLayout(f)
        return w

    def _tab_cal(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_cal = _tabla(["Tipo", "Estado", "Inicio", "Fin", "Días"])
        ly.addWidget(self.tbl_cal)
        return w

    def _refrescar(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh import vacaciones_servicio as VS
        s = VS.saldo(self.id_empleado, id_empresa=self.id_empresa)
        self.lbl_saldo.setText(
            f"Saldo {s['anio']}: asignados {s['asignados']} · disfrutados {s['disfrutados']} · "
            f"pendientes {s['pendientes']} · disponibles {s['disponibles']}")
        self._vac = VS.listar(self.id_empleado, self.id_empresa)
        self.tbl_vac.setRowCount(len(self._vac))
        for i, v in enumerate(self._vac):
            for j, val in enumerate([v.get("id"), v.get("fecha_inicio"), v.get("fecha_fin"),
                                     v.get("dias"), v.get("estado"), v.get("aprobado_por")]):
                self.tbl_vac.setItem(i, j, _it(val))
        self._aus = AS.listar(self.id_empleado, self.id_empresa)
        self.tbl_aus.setRowCount(len(self._aus))
        for i, a in enumerate(self._aus):
            for j, val in enumerate([a.get("id"), a.get("tipo"), a.get("fecha_inicio"),
                                     a.get("fecha_fin"), a.get("dias"), a.get("motivo")]):
                self.tbl_aus.setItem(i, j, _it(val))
        cal = AS.calendario(self.id_empleado, self.id_empresa)
        self.tbl_cal.setRowCount(len(cal))
        for i, ev in enumerate(cal):
            for j, val in enumerate([ev.get("tipo"), ev.get("estado"), ev.get("fecha_inicio"),
                                     ev.get("fecha_fin"), ev.get("dias")]):
                self.tbl_cal.setItem(i, j, _it(val))

    def _usuario(self):
        u = getattr(self.parent(), "usuario", None) or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _solicitar(self):
        from src.rrhh import vacaciones_servicio as VS
        try:
            VS.solicitar(self.id_empleado, self.v_ini.text().strip(), self.v_fin.text().strip(),
                         id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            QMessageBox.warning(self, "Vacaciones", str(e)); return
        self.v_ini.clear(); self.v_fin.clear(); self._refrescar()

    def _vac_sel(self):
        i = self.tbl_vac.currentRow()
        return self._vac[i] if 0 <= i < len(self._vac) else None

    def _estado_vac(self, accion):
        from src.rrhh import vacaciones_servicio as VS
        v = self._vac_sel()
        if not v:
            QMessageBox.information(self, "Vacaciones", "Selecciona una solicitud."); return
        fn = {"aprobar": VS.aprobar, "denegar": VS.denegar, "cancelar": VS.cancelar}[accion]
        try:
            fn(v["id"], usuario=self._usuario(), id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            QMessageBox.warning(self, "Vacaciones", str(e)); return
        self._refrescar()

    def _registrar_aus(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh.vacaciones_servicio import GestionLaboralError
        try:
            AS.registrar(self.id_empleado, self.a_tipo.currentData(), self.a_ini.text().strip(),
                         self.a_fin.text().strip(), motivo=self.a_mot.text().strip(),
                         id_empresa=self.id_empresa)
        except GestionLaboralError as e:
            QMessageBox.warning(self, "Ausencias", str(e)); return
        self.a_ini.clear(); self.a_fin.clear(); self.a_mot.clear(); self._refrescar()
