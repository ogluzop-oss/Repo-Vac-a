"""
GUIs GMAO (BLOQUE 4) — AHORA OPERATIVAS.

  · GMAODashboardWindow — cuadro de mando + ACCIONES sobre Activos (alta + estado), Órdenes de Trabajo
                          (correctiva/preventiva: abierta→asignada→en_curso→pausada→finalizada/cancelada,
                          repuestos por KARDEX oficial, cierre con costes) y Planes preventivos
                          (alta + generación de OT preventivas vencidas).
  · ActivosWindow / PlanesMantenimientoWindow / OrdenesTrabajoWindow — alias de compatibilidad.

Reutiliza ÍNTEGRAMENTE `services.gmao.{activos,planes,ordenes,analitica}`. El consumo de repuestos pasa
por el MOTOR OFICIAL de stock/kardex (`ordenes.consumir_repuestos` → SALIDA_PRODUCCION, id_documento
`OT:<id>`). Auditoría (`GMAO_*`) la emite el backend. RBAC único vía `services.autorizacion` (permisos
`activos.gestionar`, `ot.crear`, `gmao.admin`). `tecnico`/`responsable` son columnas INT (id de usuario).
"""

import logging

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn as _btn_base, _btn_x,
                                      _dialogo_frameless, _tabla)

logger = logging.getLogger("gui.gmao")


def _btn(txt, slot=None, primary=False, danger=False):
    """Diseño global: los botones secundarios (antes grises) usan el estilo turquesa (contorno azul
    turquesa, fondo azul oscuro, texto turquesa, hover swap) — igual que 'Actualizar'. Los 'danger'
    (rojo) se conservan. Reutiliza el `_btn` compartido sin modificarlo (solo local a este módulo)."""
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


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


def _usuario_sesion(fallback=None):
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or fallback or {}
    except Exception:
        return fallback or {}


def _puede(usuario, permiso) -> bool:
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


def _combo(valores):
    cb = QComboBox(); cb.addItems(valores); return cb


class GMAODashboardWindow(QWidget):
    """Cuadro de mando de mantenimiento + acciones OPERATIVAS (activos, OT, planes)."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("GMAO · Mantenimiento")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()

        self.tbl_act = _tabla(["ID", "Código", "Nombre", "Tipo", "Estado", "Criticidad"])
        self.tbl_ot = _tabla(["ID", "Código", "Tipo", "Activo", "Estado", "Prioridad"])
        self.tbl_plan = _tabla(["ID", "Código", "Nombre", "Frecuencia", "Próxima"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])

        self.tabs.addTab(self._page(self.tbl_act, [
            ("➕  Nuevo activo", self._nuevo_activo, True),
            ("Poner en mantenimiento", lambda: self._activo_estado("mantenimiento"), False),
            ("Marcar operativo", lambda: self._activo_estado("operativo"), False),
            ("Dar de baja", lambda: self._activo_estado("baja"), False)]), "Activos")
        self.tabs.addTab(self._page(self.tbl_ot, [
            ("➕  Nueva OT", self._nueva_ot, True),
            ("Asignar", self._asignar, False),
            ("Iniciar", lambda: self._ot_estado("iniciar"), False),
            ("Pausar", lambda: self._ot_estado("pausar"), False),
            ("Añadir repuesto", self._anadir_repuesto, False),
            ("Consumir repuestos", self._consumir_repuestos, False),
            ("Finalizar", self._finalizar, False),
            ("Cancelar", lambda: self._ot_estado("cancelar"), False)]), "Órdenes de trabajo")
        self.tabs.addTab(self._page(self.tbl_plan, [
            ("➕  Nuevo plan", self._nuevo_plan, True),
            ("Generar OT preventivas vencidas", self._generar_preventivas, False)]), "Planes preventivos")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _page(self, tabla, botones):
        w = QWidget(); l = QVBoxLayout(w)
        bar = QHBoxLayout()
        for txt, fn, primary in botones:
            bar.addWidget(_btn(txt, fn, primary=primary))
        bar.addStretch()
        l.addLayout(bar); l.addWidget(tabla)
        return w

    def _load(self):
        eid = _empresa()
        try:
            from src.services.gmao import activos, analitica, ordenes, planes
            acts = activos.listar(id_empresa=eid)
            self.tbl_act.setRowCount(len(acts))
            for i, a in enumerate(acts):
                for j, v in enumerate([a.get("id"), a.get("codigo"), a.get("nombre"), a.get("tipo"),
                                       a.get("estado"), a.get("criticidad")]):
                    self.tbl_act.setItem(i, j, _it(v))
            ots = ordenes.listar(id_empresa=eid)
            self.tbl_ot.setRowCount(len(ots))
            for i, o in enumerate(ots):
                for j, v in enumerate([o.get("id"), o.get("codigo"), o.get("tipo"), o.get("id_activo"),
                                       o.get("estado"), o.get("prioridad")]):
                    self.tbl_ot.setItem(i, j, _it(v))
            pls = planes.listar(id_empresa=eid)
            self.tbl_plan.setRowCount(len(pls))
            for i, p in enumerate(pls):
                for j, v in enumerate([p.get("id"), p.get("codigo"), p.get("nombre"),
                                       p.get("frecuencia"), p.get("proxima_fecha")]):
                    self.tbl_plan.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"MTTR: {k.get('mttr_horas', 0)}h · Disponibilidad: {k.get('disponibilidad_pct', 0)}%")
        except Exception as e:
            logger.error("load GMAO: %s", e)
            self.lbl.setText(f"Error: {e}")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _set(self, msg):
        self.lbl.setText(msg)

    def _sel_id(self, tabla):
        row = tabla.currentRow()
        if row < 0:
            return None
        it = tabla.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _uid(self):
        return (self.usuario or {}).get("id")

    # ── Activos ───────────────────────────────────────────────────────────────
    def _nuevo_activo(self):
        if not _puede(self.usuario, "activos.gestionar"):
            self._set("Permiso requerido: activos.gestionar"); return
        dlg = _NuevoActivoDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import activos
            aid = activos.crear_activo(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Activo creado: {aid}" if aid else "No se pudo crear el activo.")
            self._load()

    def _activo_estado(self, estado):
        if not _puede(self.usuario, "activos.gestionar"):
            self._set("Permiso requerido: activos.gestionar"); return
        aid = self._sel_id(self.tbl_act)
        if not aid:
            self._set("Selecciona un activo."); return
        from src.services.gmao import activos
        ok = activos.cambiar_estado(aid, estado, id_empresa=_empresa())
        self._set(f"Activo {aid} → {estado}" if ok else f"No se pudo cambiar el activo {aid}.")
        self._load()

    # ── Órdenes de trabajo ────────────────────────────────────────────────────
    def _nueva_ot(self):
        if not _puede(self.usuario, "ot.crear"):
            self._set("Permiso requerido: ot.crear"); return
        dlg = _NuevaOTDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import ordenes
            oid = ordenes.crear_ot(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"OT creada: {oid}" if oid else "No se pudo crear la OT.")
            self._load()

    def _asignar(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT."); return
        tec, ok = QInputDialog.getInt(self, "Asignar OT", "ID del técnico:", self._uid() or 0, 0, 10_000_000, 1)
        if not ok:
            return
        from src.services.gmao import ordenes
        r = ordenes.asignar(oid, tec, id_empresa=_empresa())
        self._set(f"OT {oid} asignada al técnico {tec}" if r.get("ok") else f"OT {oid}: {r.get('error')}")
        self._load()

    def _ot_estado(self, accion):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT."); return
        from src.services.gmao import ordenes
        fn = {"iniciar": ordenes.iniciar, "cancelar": ordenes.cancelar,
              "pausar": lambda o, **k: ordenes.cambiar_estado(o, "pausada", **k)}[accion]
        r = fn(oid, id_empresa=_empresa())
        self._set(f"OT {oid} → {r.get('estado')}" if r.get("ok") else f"OT {oid}: {r.get('error')}")
        self._load()

    def _anadir_repuesto(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT."); return
        dlg = _RepuestoDialog(self)
        if dlg.exec() and dlg.resultado:
            ref, cant, coste = dlg.resultado
            from src.services.gmao import ordenes
            rid = ordenes.añadir_repuesto(oid, ref, cant, coste_unitario=coste, id_empresa=_empresa())
            self._set(f"Repuesto {ref} x{cant} añadido a OT {oid}" if rid else "No se pudo añadir el repuesto.")
            self._load()

    def _consumir_repuestos(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT."); return
        from src.services.gmao import ordenes
        r = ordenes.consumir_repuestos(oid, id_empresa=_empresa(), usuario=self._uid())
        self._set(f"OT {oid}: repuestos consumidos vía kárdex oficial ({len(r.get('consumidos', []))})."
                  if r.get("ok") else f"OT {oid}: {r.get('error')}")
        self._load()

    def _finalizar(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT."); return
        horas, ok = QInputDialog.getDouble(self, "Finalizar OT", "Horas de mano de obra:", 1, 0, 1000, 2)
        if not ok:
            return
        from src.services.gmao import ordenes
        r = ordenes.finalizar(oid, horas_mano_obra=horas, id_empresa=_empresa(), usuario=self._uid())
        self._set(f"OT {oid} FINALIZADA. Coste: {r.get('coste_total', '—')}" if r.get("ok")
                  else f"OT {oid}: {r.get('error')}")
        self._load()

    # ── Planes preventivos ────────────────────────────────────────────────────
    def _nuevo_plan(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        dlg = _NuevoPlanDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import planes
            pid = planes.crear_plan(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Plan preventivo creado: {pid}" if pid else "No se pudo crear el plan.")
            self._load()

    def _generar_preventivas(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin"); return
        from src.services.gmao import planes
        ots = planes.generar_ot_preventivas(id_empresa=_empresa())
        self._set(f"Generadas {len(ots)} OT preventivas de planes vencidos.")
        self._load()


class _NuevoActivoDialog(QDialog):
    """Alta de activo (reutiliza activos.crear_activo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nuevo activo")
        body = _dialogo_frameless(self, "Nuevo activo")
        f = QFormLayout(); body.addLayout(f)
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código del activo")
        self.in_nom = QLineEdit(); self.in_nom.setPlaceholderText("Nombre")
        self.cb_tipo = _combo(["maquinaria", "equipo", "instalacion", "vehiculo", "herramienta"])
        self.in_serie = QLineEdit(); self.in_serie.setPlaceholderText("(opcional) nº de serie")
        self.in_fab = QLineEdit(); self.in_fab.setPlaceholderText("(opcional) fabricante")
        self.in_mod = QLineEdit(); self.in_mod.setPlaceholderText("(opcional) modelo")
        self.in_ubi = QLineEdit(); self.in_ubi.setPlaceholderText("(opcional) ubicación")
        self.cb_crit = _combo(["baja", "media", "alta"])
        for lbl, w in (("Código:", self.in_cod), ("Nombre:", self.in_nom), ("Tipo:", self.cb_tipo),
                       ("Nº serie:", self.in_serie), ("Fabricante:", self.in_fab),
                       ("Modelo:", self.in_mod), ("Ubicación:", self.in_ubi), ("Criticidad:", self.cb_crit)):
            f.addRow(lbl, w)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        body.addLayout(row)

    def _ok(self):
        cod = self.in_cod.text().strip(); nom = self.in_nom.text().strip()
        if not cod or not nom:
            return
        self.resultado = {"codigo": cod, "nombre": nom, "tipo": self.cb_tipo.currentText(),
                          "numero_serie": self.in_serie.text().strip() or None,
                          "fabricante": self.in_fab.text().strip() or None,
                          "modelo": self.in_mod.text().strip() or None,
                          "ubicacion": self.in_ubi.text().strip() or None,
                          "criticidad": self.cb_crit.currentText()}
        self.accept()


class _NuevaOTDialog(QDialog):
    """Alta de Orden de Trabajo (reutiliza ordenes.crear_ot)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva Orden de Trabajo")
        body = _dialogo_frameless(self, "Nueva Orden de Trabajo")
        f = QFormLayout(); body.addLayout(f)
        self.cb_tipo = _combo(["correctiva", "preventiva", "predictiva"])
        self.in_act = QLineEdit(); self.in_act.setPlaceholderText("(opcional) ID de activo")
        self.in_desc = QLineEdit(); self.in_desc.setPlaceholderText("Descripción de la avería/tarea")
        self.cb_prio = _combo(["media", "baja", "alta", "critica"])
        self.in_alm = QLineEdit(); self.in_alm.setPlaceholderText("(opcional) ID almacén (repuestos)")
        for lbl, w in (("Tipo:", self.cb_tipo), ("Activo:", self.in_act), ("Descripción:", self.in_desc),
                       ("Prioridad:", self.cb_prio), ("Almacén:", self.in_alm)):
            f.addRow(lbl, w)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        body.addLayout(row)

    def _ok(self):
        desc = self.in_desc.text().strip()
        if not desc:
            return

        def _int(le):
            t = le.text().strip()
            try:
                return int(t) if t else None
            except ValueError:
                return None
        self.resultado = {"tipo": self.cb_tipo.currentText(), "id_activo": _int(self.in_act),
                          "descripcion": desc, "prioridad": self.cb_prio.currentText(),
                          "id_almacen": _int(self.in_alm)}
        self.accept()


class _RepuestoDialog(QDialog):
    """Añadir repuesto a una OT (reutiliza ordenes.añadir_repuesto → consumo por kárdex al consumir/finalizar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Añadir repuesto")
        body = _dialogo_frameless(self, "Añadir repuesto")
        f = QFormLayout(); body.addLayout(f)
        self.in_ref = QLineEdit(); self.in_ref.setPlaceholderText("Referencia/código del repuesto")
        self.sp_cant = QSpinBox(); self.sp_cant.setRange(1, 1_000_000); self.sp_cant.setValue(1)
        self.sp_coste = QDoubleSpinBox(); self.sp_coste.setRange(0, 1e9); self.sp_coste.setDecimals(2)
        f.addRow("Referencia:", self.in_ref)
        f.addRow("Cantidad:", self.sp_cant)
        f.addRow("Coste unitario:", self.sp_coste)
        row = QHBoxLayout()
        row.addWidget(_btn("Añadir", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        body.addLayout(row)

    def _ok(self):
        ref = self.in_ref.text().strip()
        if not ref:
            return
        self.resultado = (ref, self.sp_cant.value(), self.sp_coste.value())
        self.accept()


class _NuevoPlanDialog(QDialog):
    """Alta de plan de mantenimiento preventivo (reutiliza planes.crear_plan)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nuevo plan preventivo")
        body = _dialogo_frameless(self, "Nuevo plan preventivo")
        f = QFormLayout(); body.addLayout(f)
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código del plan")
        self.in_nom = QLineEdit(); self.in_nom.setPlaceholderText("Nombre")
        self.in_act = QLineEdit(); self.in_act.setPlaceholderText("(opcional) ID de activo")
        self.cb_frec = _combo(["mensual", "diario", "semanal", "trimestral", "anual"])
        for lbl, w in (("Código:", self.in_cod), ("Nombre:", self.in_nom),
                       ("Activo:", self.in_act), ("Frecuencia:", self.cb_frec)):
            f.addRow(lbl, w)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        body.addLayout(row)

    def _ok(self):
        cod = self.in_cod.text().strip(); nom = self.in_nom.text().strip()
        if not cod or not nom:
            return
        act = self.in_act.text().strip()
        try:
            act = int(act) if act else None
        except ValueError:
            act = None
        self.resultado = {"codigo": cod, "nombre": nom, "id_activo": act,
                          "frecuencia": self.cb_frec.currentText()}
        self.accept()


class ActivosWindow(GMAODashboardWindow): """Vista de activos (reutiliza el dashboard operativo)."""
class PlanesMantenimientoWindow(GMAODashboardWindow): """Vista de planes (reutiliza el dashboard operativo)."""
class OrdenesTrabajoWindow(GMAODashboardWindow): """Vista de OT (reutiliza el dashboard operativo)."""
