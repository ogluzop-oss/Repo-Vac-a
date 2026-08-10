"""
GUIs MRP / Fabricación (BLOQUE 3) — AHORA OPERATIVAS.

  · MRPDashboardWindow  — cuadro de mando + BARRA DE ACCIONES sobre Órdenes de Fabricación
                          (nueva OF, planificar, liberar, iniciar, pausar, consumir, producir,
                          finalizar, cancelar) + pestaña BOM. Se embebe en Almacenes · Operaciones
                          (pestaña "MRP / Fabricación").
  · BOMWindow           — listado + ALTA de listas de materiales (BOM); pestaña de MRPDashboardWindow.
  · OrdenesFabricacionWindow / FabricacionWindow — alias de compatibilidad.

Reutiliza ÍNTEGRAMENTE los servicios MRP existentes (`services.mrp.bom/ordenes/costes/analitica/
planificador`). El consumo de componentes y el alta de producto terminado pasan por el MOTOR OFICIAL de
stock/kardex a través de `ordenes.consumir_materiales` / `ordenes.registrar_produccion` (NO hay motor de
stock paralelo). La auditoría (`FAB_*`) la emite el backend. RBAC único vía `services.autorizacion`.
"""

import logging

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn as _btn_base, _btn_x,
                                      _dialogo_frameless, _tabla)

logger = logging.getLogger("gui.mrp")


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


def _nombre(usuario) -> str:
    u = usuario or {}
    return u.get("nombre") or u.get("usuario") or "sistema"


def _puede(usuario, permiso) -> bool:
    """RBAC ÚNICO (services.autorizacion). Degradable a True SOLO si el subsistema no está disponible
    (la ventana ya está restringida por rol en el menú)."""
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


class MRPDashboardWindow(QWidget):
    """Cuadro de mando de fabricación + acciones OPERATIVAS sobre Órdenes de Fabricación."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("MRP / Fabricación · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()

        # ── Órdenes de Fabricación: barra de acciones OPERATIVAS + tabla ──
        of_page = QWidget(); of_l = QVBoxLayout(of_page)
        bar = QHBoxLayout()
        bar.addWidget(_btn("➕  Nueva OF", self._nueva_of, primary=True))
        for txt, fn in (("Planificar", lambda: self._accion("planificar")),
                        ("Liberar", lambda: self._accion("liberar")),
                        ("Iniciar", lambda: self._accion("iniciar")),
                        ("Pausar", lambda: self._accion("pausar")),
                        ("Consumir materiales", self._consumir),
                        ("Registrar producción", self._producir),
                        ("Finalizar", self._finalizar),
                        ("Cancelar", lambda: self._accion("cancelar"))):
            bar.addWidget(_btn(txt, fn))
        bar.addStretch()
        of_l.addLayout(bar)
        self.tbl_of = _tabla(["ID", "Código", "Artículo", "Cant", "Producido", "Estado"])
        of_l.addWidget(self.tbl_of)

        self.tbl_sug = _tabla(["Tipo", "Artículo", "Cantidad", "Estado"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(of_page, "Órdenes de Fabricación")
        self.tabs.addTab(self.tbl_sug, "Sugerencias MRP")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        # BOM (alta/listado de listas de materiales): integrado como pestaña del cuadro de mando para que
        # esté disponible allá donde se use MRPDashboardWindow (p. ej. Almacenes · Operaciones → MRP).
        self.tabs.addTab(BOMWindow(usuario=self.usuario, main=main), "BOM")
        root.addWidget(self.tabs)
        self._load()

    # ── carga (solo lectura) ──────────────────────────────────────────────────
    def _load(self):
        eid = _empresa()
        try:
            from src.services.mrp import analitica, ordenes, planificador
            ofs = ordenes.listar(id_empresa=eid)
            self.tbl_of.setRowCount(len(ofs))
            for i, o in enumerate(ofs):
                for j, v in enumerate([o.get("id"), o.get("codigo"), o.get("articulo_final"),
                                       o.get("cantidad"), o.get("cantidad_producida"), o.get("estado")]):
                    self.tbl_of.setItem(i, j, _it(v))
            sug = planificador.listar_sugerencias(id_empresa=eid)
            self.tbl_sug.setRowCount(len(sug))
            for i, s in enumerate(sug):
                for j, v in enumerate([s.get("tipo"), s.get("articulo"), s.get("cantidad"), s.get("estado")]):
                    self.tbl_sug.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"OF en curso: {k.get('of_en_curso', 0)} · Eficiencia: {k.get('eficiencia_pct', 0)}%")
        except Exception as e:
            logger.error("load MRP: %s", e)
            self.lbl.setText(f"Error: {e}")

    # ── acciones operativas ───────────────────────────────────────────────────
    def _set(self, msg):
        self.lbl.setText(msg)

    def _of_sel(self):
        row = self.tbl_of.currentRow()
        if row < 0:
            return None
        it = self.tbl_of.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _accion(self, accion):
        # planificar exige mrp.planificar; el resto de transiciones (liberar/iniciar/pausar/cancelar)
        # exigen mrp.admin (gestión). RBAC único, sin sistema paralelo.
        perm = "mrp.planificar" if accion == "planificar" else "mrp.admin"
        if not _puede(self.usuario, perm):
            self._set(f"Permiso requerido: {perm}"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OF en la tabla."); return
        from src.services.mrp import ordenes
        try:
            r = getattr(ordenes, accion)(oid, id_empresa=_empresa())
        except Exception as e:
            self._set(f"Error: {e}"); return
        self._set(f"OF {oid} → {r.get('estado')}" if r.get("ok") else f"OF {oid}: {r.get('error')}")
        self._load()

    def _consumir(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OF."); return
        from src.services.mrp import ordenes
        r = ordenes.consumir_materiales(oid, id_empresa=_empresa(), usuario=_nombre(self.usuario))
        if not r.get("ok"):
            self._set(f"OF {oid}: {r.get('error')}")
        elif r.get("faltantes"):
            self._set(f"OF {oid}: consumido con ROTURAS → {r['faltantes']}")
        else:
            self._set(f"OF {oid}: materiales consumidos ({len(r.get('consumidos', []))} componentes) vía kardex oficial.")
        self._load()

    def _producir(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OF."); return
        cant, ok = QInputDialog.getInt(self, "Registrar producción",
                                       "Cantidad de producto terminado a dar de alta:", 1, 1, 100000000, 1)
        if not ok:
            return
        from src.services.mrp import ordenes
        r = ordenes.registrar_produccion(oid, cant, id_empresa=_empresa(), usuario=_nombre(self.usuario))
        self._set(f"OF {oid}: producidas {cant} uds (lote {r.get('lote')}) → entrada de stock oficial."
                  if r.get("ok") else f"OF {oid}: {r.get('error')}")
        self._load()

    def _finalizar(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OF."); return
        from src.services.mrp import ordenes
        r = ordenes.finalizar(oid, id_empresa=_empresa(), usuario=_nombre(self.usuario))
        if r.get("ok"):
            c = r.get("costes") or {}
            self._set(f"OF {oid} FINALIZADA. Coste real: {c.get('coste_total', '—')}")
        else:
            self._set(f"OF {oid}: {r.get('error')}")
        self._load()

    def _nueva_of(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin"); return
        dlg = _NuevaOFDialog(self)
        if dlg.exec() and dlg.resultado:
            art, cant, alm = dlg.resultado
            from src.services.mrp import ordenes
            oid = ordenes.crear_orden(art, cant, id_almacen=alm, id_empresa=_empresa(),
                                      responsable=_nombre(self.usuario))
            self._set(f"OF creada: {oid} ({art} x{cant})" if oid
                      else "No se pudo crear la OF (¿existe BOM activa del artículo?).")
            self._load()


class _NuevaOFDialog(QDialog):
    """Alta de una Orden de Fabricación (reutiliza ordenes.crear_orden: explosiona la BOM activa)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva Orden de Fabricación")
        body = _dialogo_frameless(self, "Nueva Orden de Fabricación")
        f = QFormLayout(); body.addLayout(f)
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Código del artículo a fabricar")
        self.in_cant = QDoubleSpinBox(); self.in_cant.setRange(0.001, 1e9)
        self.in_cant.setDecimals(3); self.in_cant.setValue(1)
        self.in_alm = QLineEdit(); self.in_alm.setPlaceholderText("(opcional) ID de almacén")
        f.addRow("Artículo final:", self.in_art)
        f.addRow("Cantidad:", self.in_cant)
        f.addRow("Almacén:", self.in_alm)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        body.addLayout(row)

    def _ok(self):
        art = self.in_art.text().strip()
        if not art:
            return
        alm = self.in_alm.text().strip()
        self.resultado = (art, self.in_cant.value(), alm or None)
        self.accept()


class _NuevaBOMDialog(QDialog):
    """Alta de una lista de materiales (reutiliza bom.crear_bom)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva Lista de Materiales (BOM)")
        v = _dialogo_frameless(self, "Nueva Lista de Materiales (BOM)", ancho=560)
        f = QFormLayout()
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Artículo final (producto fabricable)")
        self.in_ver = QLineEdit("1")
        self.in_base = QDoubleSpinBox(); self.in_base.setRange(0.001, 1e9)
        self.in_base.setDecimals(3); self.in_base.setValue(1)
        f.addRow("Artículo final:", self.in_art)
        f.addRow("Versión:", self.in_ver)
        f.addRow("Cantidad base:", self.in_base)
        v.addLayout(f)
        v.addWidget(QLabel("Componentes:"))
        self.tbl = _tabla(["Componente", "Cantidad", "Merma %"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.tbl.setRowCount(6)
        for r in range(self.tbl.rowCount()):
            for c in range(3):
                self.tbl.setItem(r, c, _it(""))
        v.addWidget(self.tbl)
        row = QHBoxLayout()
        row.addWidget(_btn("Añadir fila", self._add_row))
        row.addStretch()
        row.addWidget(_btn("Crear BOM", self._ok, primary=True))
        row.addWidget(_btn_base("Cancelar", self.reject))
        v.addLayout(row)

    def _add_row(self):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        for c in range(3):
            self.tbl.setItem(r, c, _it(""))

    def _ok(self):
        art = self.in_art.text().strip()
        if not art:
            return
        lineas = []
        for r in range(self.tbl.rowCount()):
            it0 = self.tbl.item(r, 0)
            comp = it0.text().strip() if it0 else ""
            if not comp:
                continue

            def _num(c, d=0.0):
                it = self.tbl.item(r, c)
                try:
                    return float(it.text()) if it and it.text().strip() else d
                except ValueError:
                    return d
            lineas.append({"componente": comp, "cantidad": _num(1, 1), "merma_pct": _num(2, 0)})
        if not lineas:
            return
        self.resultado = (art, self.in_ver.text().strip() or "1", self.in_base.value(), lineas)
        self.accept()


class BOMWindow(QWidget):
    """Listado + ALTA de listas de materiales (BOM) por empresa."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Listas de materiales (BOM)")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("➕  Nueva BOM", self._nueva, primary=True))
        cab.addWidget(_btn("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tbl = _tabla(["ID", "Artículo final", "Versión", "Estado"])
        root.addWidget(self.tbl)
        self._load()

    def _nueva(self):
        if not _puede(self.usuario, "mrp.bom"):
            self.lbl.setText("Permiso requerido: mrp.bom"); return
        dlg = _NuevaBOMDialog(self)
        if dlg.exec() and dlg.resultado:
            art, ver, base, lineas = dlg.resultado
            from src.services.mrp import bom
            bid = bom.crear_bom(art, version=ver, cantidad_base=base, lineas=lineas, id_empresa=_empresa())
            self.lbl.setText(f"BOM creada: {bid} ({art} v{ver}, {len(lineas)} componentes)"
                             if bid else "No se pudo crear la BOM.")
            self._load()

    def _load(self):
        from src.db.conexion import obtener_conexion
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, articulo_final, version, estado FROM bom WHERE id_empresa=%s "
                            "ORDER BY id DESC", (_empresa(),))
                filas = cur.fetchall()
            self.tbl.setRowCount(len(filas))
            for i, r in enumerate(filas):
                r = list(r.values()) if isinstance(r, dict) else r
                for j, v in enumerate(r):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load BOM: %s", e)


class OrdenesFabricacionWindow(MRPDashboardWindow):
    """Vista centrada en órdenes de fabricación (reutiliza el cuadro de mando operativo)."""


class FabricacionWindow(MRPDashboardWindow):
    """Alias operativo de fabricación (reutiliza el cuadro de mando operativo)."""
