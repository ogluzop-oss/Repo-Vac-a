"""
GUIs Calidad (BLOQUE 3) — AHORA OPERATIVAS.

  · CalidadDashboardWindow — cuadro de mando + ACCIONES sobre Inspecciones (recepción/producción/final),
                             No Conformidades (ciclo abierta→en_análisis→accionada→cerrada/rechazada) y
                             CAPA (abierta→en_curso→cerrada/cancelada). Acceso: pestaña Calidad de Proveedores.

Reutiliza ÍNTEGRAMENTE `services.calidad.{inspecciones,no_conformidades,capa,auditorias,trazabilidad,
analitica}`. La integración Compras→Calidad ya vive en el backend: una inspección de recepción con
resultado "rechazada" ABRE automáticamente una NC. Auditoría (`CAL_*`/`NC_*`/`CAPA_*`) la emite el
backend. RBAC único vía `services.autorizacion` (permisos `inspecciones.crear`, `nc.crear`,
`auditorias.gestionar`, `calidad.admin`). Sin motores ni pantallas duplicadas.
"""

import logging

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _dialogo_frameless, _tabla

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.calidad")


def _dlg_body(dialog, titulo, ancho):
    """Cabecera frameless común (sin barra de Windows, esquinas redondeadas) + QFormLayout listo.
    Devuelve (body_vbox, form). Los QLabel del formulario se colorean vía stylesheet del diálogo."""
    dialog.setStyleSheet("QLabel{color:#E6EDF3;background:transparent;font-weight:700;}")
    v = _dialogo_frameless(dialog, titulo=titulo, ancho=ancho)
    form = QFormLayout(); form.setSpacing(10)
    v.addLayout(form)
    return v, form


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
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


def _combo(valores):
    cb = QComboBox()
    cb.addItems(valores)
    return cb


class CalidadDashboardWindow(QWidget):
    """Cuadro de mando de calidad + acciones OPERATIVAS (inspecciones, NC, CAPA)."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Calidad · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        # Sin línea gris alrededor del contenido de cada sub-pestaña (el contorno lo pone la tabla).
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;}")

        self.tbl_insp = _tabla(["ID", "Fase", "Artículo", "Inspecc.", "Rechaz.", "Resultado", "Fecha"])
        self.tbl_nc = _tabla(["ID", "Código", "Origen", "Severidad", "Estado", "Fecha"])
        self.tbl_capa = _tabla(["ID", "Tipo", "NC", "Estado", "Fecha"])
        self.tbl_aud = _tabla(["ID", "Código", "Tipo", "Estado", "Resultado", "Fecha"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])

        # Inspecciones (con acción de alta = flujo de recepción/calidad en compras).
        insp_bar = [("➕  Nueva inspección", self._nueva_inspeccion, True)]
        self.tabs.addTab(self._page(self.tbl_insp, insp_bar), "Inspecciones")
        # No Conformidades (alta + transiciones de estado).
        nc_bar = [("➕  Nueva NC", self._nueva_nc, True),
                  ("En análisis", lambda: self._nc_estado("en_analisis"), True),
                  ("Accionar", lambda: self._nc_estado("accionada"), True),
                  ("Cerrar", lambda: self._nc_estado("cerrada"), True),
                  ("Rechazar", lambda: self._nc_estado("rechazada"), True)]
        self.tabs.addTab(self._page(self.tbl_nc, nc_bar), "No conformidades")
        # CAPA (alta + transiciones).
        capa_bar = [("➕  Nueva acción (CAPA)", self._nueva_capa, True),
                    ("En curso", lambda: self._capa_estado("en_curso"), True),
                    ("Cerrar (eficacia)", self._capa_cerrar, True),
                    ("Cancelar", lambda: self._capa_estado("cancelada"), True)]
        self.tabs.addTab(self._page(self.tbl_capa, capa_bar), "CAPA")
        self.tabs.addTab(self.tbl_aud, "Auditorías")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _page(self, tabla, botones):
        w = QWidget(); l = QVBoxLayout(w)
        bar = QHBoxLayout()
        for txt, fn, primary in botones:
            bar.addWidget(_btn(txt, fn, primary=primary))
        bar.addStretch()
        l.addLayout(bar)
        l.addWidget(tabla)
        return w

    # ── carga (solo lectura) ──────────────────────────────────────────────────
    def _load(self):
        eid = _empresa()
        try:
            from src.services.calidad import (analitica, auditorias, capa, inspecciones,
                                              no_conformidades)
            def _f(v):
                return str(v)[:16] if v is not None else ""
            ins = inspecciones.listar(id_empresa=eid)
            self.tbl_insp.setRowCount(len(ins))
            for i, x in enumerate(ins):
                for j, v in enumerate([x.get("id"), x.get("fase"), x.get("articulo"),
                                       x.get("cantidad_inspeccionada"), x.get("cantidad_rechazada"),
                                       x.get("resultado"), _f(x.get("fecha"))]):
                    self.tbl_insp.setItem(i, j, _it(v))
            ncs = no_conformidades.listar(id_empresa=eid)
            self.tbl_nc.setRowCount(len(ncs))
            for i, x in enumerate(ncs):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("origen"),
                                       x.get("severidad"), x.get("estado"), _f(x.get("fecha_apertura"))]):
                    self.tbl_nc.setItem(i, j, _it(v))
            cps = capa.listar(id_empresa=eid)
            self.tbl_capa.setRowCount(len(cps))
            for i, x in enumerate(cps):
                for j, v in enumerate([x.get("id"), x.get("tipo"), x.get("id_nc"), x.get("estado"),
                                       _f(x.get("creado_en"))]):
                    self.tbl_capa.setItem(i, j, _it(v))
            auds = auditorias.listar(id_empresa=eid)
            self.tbl_aud.setRowCount(len(auds))
            for i, x in enumerate(auds):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("tipo"),
                                       x.get("estado"), x.get("resultado"), _f(x.get("fecha_plan"))]):
                    self.tbl_aud.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"Tasa rechazo: {k.get('tasa_rechazo_pct', 0)}% · NC abiertas: {k.get('nc_abiertas', 0)}")
        except Exception as e:
            logger.error("load calidad: %s", e)
            self.lbl.setText(f"Error: {e}")

    # ── helpers de selección ──────────────────────────────────────────────────
    def _set(self, msg):
        self.lbl.setText(msg)

    def _aviso(self, titulo, mensaje, nivel="info"):
        """Feedback emergente (éxito/aviso/error) para que los botones no parezcan 'muertos'.
        Actualiza también la barra de estado superior."""
        self.lbl.setText(mensaje)
        if mostrar_mensaje is not None:
            try:
                mostrar_mensaje(self, titulo, mensaje, nivel=nivel)
                return
            except Exception:
                pass
        from PyQt6.QtWidgets import QMessageBox
        (QMessageBox.information if nivel in ("info", "success") else QMessageBox.warning)(
            self, titulo, mensaje)

    def _sel_id(self, tabla):
        row = tabla.currentRow()
        if row < 0:
            return None
        it = tabla.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    # ── Inspecciones ──────────────────────────────────────────────────────────
    def _nueva_inspeccion(self):
        if not _puede(self.usuario, "inspecciones.crear"):
            self._aviso("Inspección", "Permiso requerido: inspecciones.crear", "warning"); return
        dlg = _NuevaInspeccionDialog((self.usuario or {}).get("id"), self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import inspecciones
            r = inspecciones.registrar_inspeccion(id_empresa=_empresa(), **dlg.resultado)
            self._load()
            if r.get("ok"):
                nc = r.get("no_conformidad")
                self._aviso("Inspección",
                            f"Inspección {r['inspeccion']} registrada." +
                            (f"\nNC generada automáticamente: {nc}" if nc else ""),
                            "success")
            else:
                self._aviso("Inspección", f"No se pudo registrar: {r.get('error')}", "error")

    # ── No Conformidades ──────────────────────────────────────────────────────
    def _nueva_nc(self):
        if not _puede(self.usuario, "nc.crear"):
            self._aviso("No conformidad", "Permiso requerido: nc.crear", "warning"); return
        dlg = _NuevaNCDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import no_conformidades
            nid = no_conformidades.abrir(id_empresa=_empresa(),
                                         responsable=(self.usuario or {}).get("id"), **dlg.resultado)
            self._load()
            if nid:
                self._aviso("No conformidad", f"NC abierta correctamente (ID {nid}).", "success")
            else:
                self._aviso("No conformidad", "No se pudo abrir la NC.", "error")

    def _nc_estado(self, nuevo):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("No conformidad", "Permiso requerido: calidad.admin", "warning"); return
        nid = self._sel_id(self.tbl_nc)
        if not nid:
            self._aviso("No conformidad", "Selecciona una NC en la tabla.", "info"); return
        from src.services.calidad import no_conformidades
        r = no_conformidades.cambiar_estado(nid, nuevo, id_empresa=_empresa())
        self._load()
        if r.get("ok"):
            self._aviso("No conformidad", f"NC {nid} actualizada a «{r.get('estado')}».", "success")
        else:
            self._aviso("No conformidad", f"NC {nid}: {r.get('error')}", "error")

    # ── CAPA ──────────────────────────────────────────────────────────────────
    def _nueva_capa(self):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("CAPA", "Permiso requerido: calidad.admin", "warning"); return
        dlg = _NuevaCAPADialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import capa
            cid = capa.crear_accion(id_empresa=_empresa(),
                                    responsable=(self.usuario or {}).get("id"), **dlg.resultado)
            self._load()
            if cid:
                self._aviso("CAPA", f"Acción CAPA creada correctamente (ID {cid}).", "success")
            else:
                self._aviso("CAPA", "No se pudo crear la acción CAPA.", "error")

    def _capa_estado(self, estado):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("CAPA", "Permiso requerido: calidad.admin", "warning"); return
        cid = self._sel_id(self.tbl_capa)
        if not cid:
            self._aviso("CAPA", "Selecciona una acción CAPA en la tabla.", "info"); return
        from src.services.calidad import capa
        r = capa.cambiar_estado(cid, estado, id_empresa=_empresa())
        self._load()
        if r.get("ok"):
            self._aviso("CAPA", f"CAPA {cid} actualizada a «{r.get('estado')}».", "success")
        else:
            self._aviso("CAPA", f"CAPA {cid}: {r.get('error')}", "error")

    def _capa_cerrar(self):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("CAPA", "Permiso requerido: calidad.admin", "warning"); return
        cid = self._sel_id(self.tbl_capa)
        if not cid:
            self._aviso("CAPA", "Selecciona una acción CAPA en la tabla.", "info"); return
        from PyQt6.QtWidgets import QInputDialog
        efi, ok = QInputDialog.getItem(self, "Cerrar CAPA", "Eficacia verificada:",
                                       ["eficaz", "no_eficaz", "pendiente"], 0, False)
        if not ok:
            return
        from src.services.calidad import capa
        r = capa.cambiar_estado(cid, "cerrada", eficacia=efi, id_empresa=_empresa())
        self._load()
        if r.get("ok"):
            self._aviso("CAPA", f"CAPA {cid} cerrada (eficacia: {efi}).", "success")
        else:
            self._aviso("CAPA", f"CAPA {cid}: {r.get('error')}", "error")


class _NuevaInspeccionDialog(QDialog):
    """Alta de inspección (reutiliza inspecciones.registrar_inspeccion; rechazo → NC automática)."""

    def __init__(self, inspector, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(620, 620)
        v, f = _dlg_body(self, "Nueva inspección de calidad", ancho=620)
        self.cb_fase = _combo(["recepcion", "produccion", "final"])
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Código de artículo")
        self.in_lote = QLineEdit(); self.in_lote.setPlaceholderText("(opcional) ID lote")
        self.in_prov = QLineEdit(); self.in_prov.setPlaceholderText("(opcional) ID proveedor")
        self.sp_insp = QSpinBox(); self.sp_insp.setRange(0, 10_000_000)
        self.sp_rech = QSpinBox(); self.sp_rech.setRange(0, 10_000_000)
        self.cb_res = _combo(["aceptada", "rechazada", "condicional", "pendiente"])
        self._inspector = inspector
        for wdg in (self.cb_fase, self.in_art, self.in_lote, self.in_prov,
                    self.sp_insp, self.sp_rech, self.cb_res):
            wdg.setMinimumHeight(34)
        f.addRow("Fase:", self.cb_fase)
        f.addRow("Artículo:", self.in_art)
        f.addRow("Lote:", self.in_lote)
        f.addRow("Proveedor:", self.in_prov)
        f.addRow("Cantidad inspeccionada:", self.sp_insp)
        f.addRow("Cantidad rechazada:", self.sp_rech)
        f.addRow("Resultado:", self.cb_res)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Registrar", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        art = self.in_art.text().strip()
        if not art:
            return

        def _int(le):
            t = le.text().strip()
            try:
                return int(t) if t else None
            except ValueError:
                return None
        self.resultado = {
            "fase": self.cb_fase.currentText(),
            "articulo": art,
            "id_lote": _int(self.in_lote),
            "id_proveedor": _int(self.in_prov),
            "cantidad_inspeccionada": self.sp_insp.value(),
            "cantidad_rechazada": self.sp_rech.value(),
            "resultado": self.cb_res.currentText(),
            "inspector": self._inspector,
        }
        self.accept()


class _NuevaNCDialog(QDialog):
    """Alta de No Conformidad (reutiliza no_conformidades.abrir)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 460)
        v, f = _dlg_body(self, "Nueva No Conformidad", ancho=580)
        self.in_desc = QLineEdit(); self.in_desc.setPlaceholderText("Descripción de la no conformidad")
        self.cb_origen = _combo(["interna", "recepcion", "produccion", "cliente", "proveedor"])
        self.cb_sev = _combo(["baja", "media", "alta", "critica"])
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("(opcional) artículo")
        for wdg in (self.in_desc, self.cb_origen, self.cb_sev, self.in_art):
            wdg.setMinimumHeight(34)
        f.addRow("Descripción:", self.in_desc)
        f.addRow("Origen:", self.cb_origen)
        f.addRow("Severidad:", self.cb_sev)
        f.addRow("Artículo:", self.in_art)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Abrir NC", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        desc = self.in_desc.text().strip()
        if not desc:
            return
        self.resultado = {"descripcion": desc, "origen": self.cb_origen.currentText(),
                          "severidad": self.cb_sev.currentText(),
                          "articulo": self.in_art.text().strip() or None}
        self.accept()


class _NuevaCAPADialog(QDialog):
    """Alta de acción correctiva/preventiva (reutiliza capa.crear_accion)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 420)
        v, f = _dlg_body(self, "Nueva acción correctiva / preventiva (CAPA)", ancho=580)
        self.in_desc = QLineEdit(); self.in_desc.setPlaceholderText("Descripción de la acción")
        self.cb_tipo = _combo(["correctiva", "preventiva"])
        self.in_nc = QLineEdit(); self.in_nc.setPlaceholderText("(opcional) ID de NC asociada")
        for wdg in (self.in_desc, self.cb_tipo, self.in_nc):
            wdg.setMinimumHeight(34)
        f.addRow("Descripción:", self.in_desc)
        f.addRow("Tipo:", self.cb_tipo)
        f.addRow("NC asociada:", self.in_nc)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Crear", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        desc = self.in_desc.text().strip()
        if not desc:
            return
        nc = self.in_nc.text().strip()
        try:
            nc = int(nc) if nc else None
        except ValueError:
            nc = None
        self.resultado = {"descripcion": desc, "tipo": self.cb_tipo.currentText(), "id_nc": nc}
        self.accept()

# Nota: se retiraron los alias de compatibilidad InspeccionesWindow/NoConformidadesWindow/CAPAWindow/
# AuditoriasWindow (código muerto: no los referenciaba ni el menú ni ningún módulo). El acceso a Calidad
# es `CalidadDashboardWindow`, embebido en la pestaña Calidad de Compras/Proveedores.
