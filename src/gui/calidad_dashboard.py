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

from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_cargando, _dialogo_frameless, _tabla
from src.gui.components.completer_articulos import instalar_sugerencias_articulo

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
        cab.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        # Sin línea gris alrededor del contenido de cada sub-pestaña (el contorno lo pone la tabla).
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;}")
        try:
            from src.gui.transiciones import instalar_transicion_tabs
            instalar_transicion_tabs(self.tabs)   # deslizamiento al cambiar de sub-pestaña
        except Exception:
            pass

        self.tbl_insp = _tabla(["ID", "Fase", "Artículo", "Inspecc.", "Rechaz.", "Resultado", "Fecha"])
        self.tbl_nc = _tabla(["ID", "Código", "Origen", "Severidad", "Estado", "Fecha"])
        self.tbl_capa = _tabla(["ID", "Tipo", "NC", "Estado", "Fecha"])
        self.tbl_aud = _tabla(["ID", "Código", "Tipo", "Estado", "Resultado", "Fecha"])
        self.tbl_equipos = _tabla(["ID", "Código", "Nombre", "Última calib.", "Próxima", "Estado"])
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
        self.tabs.addTab(self._page(self.tbl_capa, capa_bar), "Acciones correctivas")
        aud_bar = [("➕  Planificar auditoría", self._nueva_auditoria, True),
                   ("Registrar hallazgo", self._hallazgo_auditoria, True),
                   ("Marcar realizada", self._cerrar_auditoria, True)]
        self.tabs.addTab(self._page(self.tbl_aud, aud_bar), "Auditorías")
        # Calibración de equipos (metrología) — Calidad PRO.
        equipos_bar = [("➕  Nuevo equipo", self._nuevo_equipo, True),
                       ("Registrar calibración", self._registrar_calibracion, True)]
        self.tabs.addTab(self._page(self.tbl_equipos, equipos_bar), "Calibración de equipos")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        self.tabs.addTab(self._tab_trazabilidad(), "Trazabilidad")
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
            try:
                from src.services.calidad import calidad_pro
                equipos = calidad_pro.equipos_a_calibrar(id_empresa=eid, dias=365)
                self.tbl_equipos.setRowCount(len(equipos))
                for i, x in enumerate(equipos):
                    for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("nombre"),
                                           _f(x.get("ultima_calibracion")), _f(x.get("proxima_calibracion")),
                                           x.get("estado")]):
                        self.tbl_equipos.setItem(i, j, _it(v))
            except Exception as e:
                logger.error("load equipos calidad: %s", e)
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

    # ── Auditorías ────────────────────────────────────────────────────────────
    def _nueva_auditoria(self):
        if not _puede(self.usuario, "auditorias.gestionar"):
            self._aviso("Auditoría", "Permiso requerido: auditorias.gestionar", "warning"); return
        dlg = _NuevaAuditoriaDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import auditorias
            aid = auditorias.planificar(id_empresa=_empresa(), auditor=(self.usuario or {}).get("id"),
                                        **dlg.resultado)
            self._load()
            if aid:
                self._aviso("Auditoría", f"Auditoría planificada correctamente (ID {aid}).", "success")
            else:
                self._aviso("Auditoría", "No se pudo planificar la auditoría.", "error")

    def _hallazgo_auditoria(self):
        if not _puede(self.usuario, "auditorias.gestionar"):
            self._aviso("Auditoría", "Permiso requerido: auditorias.gestionar", "warning"); return
        aid = self._sel_id(self.tbl_aud)
        if not aid:
            self._aviso("Auditoría", "Selecciona una auditoría en la tabla.", "info"); return
        dlg = _HallazgoAuditoriaDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import auditorias
            r = auditorias.registrar_hallazgo(aid, id_empresa=_empresa(), **dlg.resultado)
            self._load()
            if r.get("ok"):
                nc = r.get("no_conformidad")
                self._aviso("Auditoría",
                            f"Hallazgo {r['hallazgo']} registrado en la auditoría {aid}." +
                            (f"\nNC generada automáticamente: {nc}" if nc else ""),
                            "success")
            else:
                self._aviso("Auditoría", f"No se pudo registrar el hallazgo: {r.get('error')}", "error")

    def _cerrar_auditoria(self):
        if not _puede(self.usuario, "auditorias.gestionar"):
            self._aviso("Auditoría", "Permiso requerido: auditorias.gestionar", "warning"); return
        aid = self._sel_id(self.tbl_aud)
        if not aid:
            self._aviso("Auditoría", "Selecciona una auditoría en la tabla.", "info"); return
        from PyQt6.QtWidgets import QInputDialog
        resultado, ok = QInputDialog.getItem(self, "Marcar realizada", "Resultado:",
                                             ["conforme", "no_conforme"], 0, False)
        if not ok:
            return
        from src.services.calidad import auditorias
        realizado = auditorias.cerrar(aid, resultado=resultado, id_empresa=_empresa())
        self._load()
        if realizado:
            self._aviso("Auditoría", f"Auditoría {aid} marcada como realizada (resultado: {resultado}).",
                       "success")
        else:
            self._aviso("Auditoría", f"No se pudo actualizar la auditoría {aid}.", "error")

    # ── Calibración de equipos (metrología) ────────────────────────────────────
    def _nuevo_equipo(self):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("Equipo", "Permiso requerido: calidad.admin", "warning"); return
        dlg = _NuevoEquipoDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import calidad_pro
            eid = calidad_pro.alta_equipo(id_empresa=_empresa(), **dlg.resultado)
            self._load()
            if eid:
                self._aviso("Equipo", f"Equipo de medida dado de alta correctamente (ID {eid}).", "success")
            else:
                self._aviso("Equipo", "No se pudo dar de alta el equipo.", "error")

    def _registrar_calibracion(self):
        if not _puede(self.usuario, "calidad.admin"):
            self._aviso("Calibración", "Permiso requerido: calidad.admin", "warning"); return
        eid_equipo = self._sel_id(self.tbl_equipos)
        if not eid_equipo:
            self._aviso("Calibración", "Selecciona un equipo en la tabla.", "info"); return
        dlg = _RegistrarCalibracionDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.calidad import calidad_pro
            r = calidad_pro.registrar_calibracion(eid_equipo, id_empresa=_empresa(), **dlg.resultado)
            self._load()
            if r.get("ok"):
                prox = r.get("proxima_calibracion")
                self._aviso("Calibración",
                            f"Calibración registrada para el equipo {eid_equipo}." +
                            (f"\nPróxima calibración: {prox}" if prox else ""),
                            "success")
            else:
                self._aviso("Calibración", f"No se pudo registrar la calibración: {r.get('motivo')}", "error")

    # ── Trazabilidad (solo lectura) ─────────────────────────────────────────────
    def _tab_trazabilidad(self):
        """Búsqueda de trazabilidad por lote (ID numérico) o código de artículo. Reutiliza
        `services.calidad.trazabilidad` (une kardex/lotes + inspecciones + NC); solo lectura."""
        w = QWidget(); l = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.in_traz = QLineEdit()
        self.in_traz.setPlaceholderText("🔍 Lote (ID numérico) o código de artículo")
        self.in_traz.setMinimumHeight(34)
        instalar_sugerencias_articulo(self.in_traz)
        bar.addWidget(self.in_traz)
        bar.addWidget(_btn("🔍", self._buscar_trazabilidad, primary=True))
        bar.addWidget(_btn("🔒 Bloquear lote", self._bloquear_lote_traz))
        bar.addStretch()
        l.addLayout(bar)
        self.lbl_traz = QLabel(""); self.lbl_traz.setStyleSheet(f"color:{_DIM};")
        self.lbl_traz.setWordWrap(True)
        l.addWidget(self.lbl_traz)
        self.lbl_traz_origen = QLabel(""); self.lbl_traz_origen.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        self.lbl_traz_origen.setWordWrap(True)
        l.addWidget(self.lbl_traz_origen)
        lbl_dist = QLabel("Distribución (ventas)"); lbl_dist.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        l.addWidget(lbl_dist)
        self.tbl_traz_dist = _tabla(["Venta", "Fecha", "Cantidad", "Empleado", "Caja"])
        l.addWidget(self.tbl_traz_dist)
        lbl_mov = QLabel("Movimientos"); lbl_mov.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        l.addWidget(lbl_mov)
        self.tbl_traz_mov = _tabla(["Fecha", "Tipo", "Cantidad", "Observaciones"])
        l.addWidget(self.tbl_traz_mov)
        lbl_insp = QLabel("Inspecciones"); lbl_insp.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        l.addWidget(lbl_insp)
        self.tbl_traz_insp = _tabla(["ID", "Fase", "Resultado", "Fecha"])
        l.addWidget(self.tbl_traz_insp)
        lbl_nc = QLabel("No conformidades"); lbl_nc.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        l.addWidget(lbl_nc)
        self.tbl_traz_nc = _tabla(["ID", "Código", "Severidad", "Estado"])
        l.addWidget(self.tbl_traz_nc)
        return w

    def _buscar_trazabilidad(self):
        texto = self.in_traz.text().strip()
        if "–" in texto:  # viene del autocompletado "CÓDIGO – NOMBRE"
            texto = texto.split("–")[0].strip()
        if not texto:
            self._aviso("Trazabilidad", "Introduce un lote o código de artículo.", "info"); return
        eid = _empresa()
        from src.services.calidad import trazabilidad
        datos = None
        if texto.isdigit():
            try:
                datos = trazabilidad.trazabilidad_lote(int(texto), id_empresa=eid)
            except Exception as e:
                logger.error("trazabilidad_lote: %s", e)
        if not datos or not any(datos.get(k) for k in ("movimientos", "inspecciones", "no_conformidades")):
            try:
                datos = trazabilidad.trazabilidad_articulo(texto, id_empresa=eid)
            except Exception as e:
                logger.error("trazabilidad_articulo: %s", e)
                datos = {}
        datos = datos or {}

        def _f(v):
            return str(v)[:16] if v is not None else ""
        movs = datos.get("movimientos") or []
        self.tbl_traz_mov.setRowCount(len(movs))
        for i, x in enumerate(movs):
            for j, v in enumerate([_f(x.get("fecha")), x.get("tipo"), x.get("cantidad"),
                                   x.get("observaciones")]):
                self.tbl_traz_mov.setItem(i, j, _it(v))
        insp = datos.get("inspecciones") or []
        self.tbl_traz_insp.setRowCount(len(insp))
        for i, x in enumerate(insp):
            for j, v in enumerate([x.get("id"), x.get("fase"), x.get("resultado"), _f(x.get("fecha"))]):
                self.tbl_traz_insp.setItem(i, j, _it(v))
        ncs = datos.get("no_conformidades") or []
        self.tbl_traz_nc.setRowCount(len(ncs))
        for i, x in enumerate(ncs):
            for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("severidad"), x.get("estado")]):
                self.tbl_traz_nc.setItem(i, j, _it(v))
        msg = f"{len(movs)} movimiento(s) · {len(insp)} inspección(es) · {len(ncs)} NC"
        of_origen = datos.get("of_origen")
        if of_origen:
            msg += f" · OF origen: {of_origen.get('codigo')}"
        self.lbl_traz.setText(msg)

        # Punto 3 (INV.3/FEFO): proveedor de origen/pedido B2B, ubicación y estado de bloqueo —
        # solo disponibles cuando la búsqueda fue por ID de lote (trazabilidad_lote).
        dist = datos.get("distribucion_ventas") or []
        self.tbl_traz_dist.setRowCount(len(dist))
        for i, x in enumerate(dist):
            for j, v in enumerate([x.get("venta_id"), _f(x.get("fecha")), x.get("cantidad"),
                                   x.get("empleado"), x.get("numero_caja")]):
                self.tbl_traz_dist.setItem(i, j, _it(v))
        self._traz_id_lote = int(texto) if texto.isdigit() else None
        self._traz_bloqueado = bool(datos.get("bloqueado"))
        partes = []
        lote_row = datos.get("lote")
        if lote_row is not None:
            partes.append("🔒 BLOQUEADO" if self._traz_bloqueado else "🟢 Activo")
            if datos.get("ubicacion") is not None:
                partes.append(f"Almacén: {datos.get('ubicacion')}")
        origen_compra = datos.get("origen_compra")
        if origen_compra:
            prov = origen_compra.get("proveedor") or f"proveedor #{origen_compra.get('id_proveedor')}" \
                if origen_compra.get("id_proveedor") else None
            if prov:
                partes.append(f"Proveedor origen: {prov}")
            if origen_compra.get("numero_pedido") or origen_compra.get("id_pedido"):
                partes.append(f"Pedido: {origen_compra.get('numero_pedido') or origen_compra.get('id_pedido')}")
        self.lbl_traz_origen.setText("  ·  ".join(partes))

    def _bloquear_lote_traz(self):
        """Bloquea el lote actualmente cargado en Trazabilidad (para NC/cuarentena), sin salir de
        este panel. Reutiliza `db.lotes.bloquear_lote` (Punto 3); FEFO lo excluye automáticamente."""
        id_lote = getattr(self, "_traz_id_lote", None)
        if id_lote is None:
            self._aviso("Bloquear lote", "Busca primero un lote por su ID numérico.", "warning")
            return
        if getattr(self, "_traz_bloqueado", False):
            self._aviso("Bloquear lote", "Ese lote ya está bloqueado.", "info")
            return
        from PyQt6.QtWidgets import QInputDialog
        motivo, ok = QInputDialog.getText(
            self, "Bloquear lote",
            "Motivo del bloqueo (p. ej. NC abierta, cuarentena, retirada del proveedor):")
        if not ok or not motivo.strip():
            return
        from src.db import lotes
        if lotes.bloquear_lote(id_lote, motivo.strip(), usuario=_nombre(self.usuario),
                               id_empresa=_empresa()):
            self._aviso("Bloquear lote", f"Lote {id_lote} bloqueado correctamente.", "success")
            self._buscar_trazabilidad()
        else:
            self._aviso("Bloquear lote", "No se pudo bloquear el lote.", "error")


class _NuevaInspeccionDialog(QDialog):
    """Alta de inspección (reutiliza inspecciones.registrar_inspeccion; rechazo → NC automática)."""

    def __init__(self, inspector, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(620, 620)
        v, f = _dlg_body(self, "Nueva inspección de calidad", ancho=620)
        self.cb_fase = _combo(["recepcion", "produccion", "final"])
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Código de artículo")
        instalar_sugerencias_articulo(self.in_art)
        self.in_lote = QLineEdit(); self.in_lote.setPlaceholderText("(opcional) ID lote")
        self.in_prov = QLineEdit(); self.in_prov.setPlaceholderText("(opcional) ID proveedor")
        # QLineEdit + validador en vez de QSpinBox: la app oculta sus flechas arriba/abajo vía QSS y
        # eso rompía su foco/clic en varios diálogos (confirmado por el usuario) — mismo criterio ya
        # aplicado en `sat_dashboard._FormDialog`.
        self.sp_insp = QLineEdit("0"); self.sp_insp.setValidator(QIntValidator(0, 10_000_000, self.sp_insp))
        self.sp_rech = QLineEdit("0"); self.sp_rech.setValidator(QIntValidator(0, 10_000_000, self.sp_rech))
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
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
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
            "cantidad_inspeccionada": _int(self.sp_insp) or 0,
            "cantidad_rechazada": _int(self.sp_rech) or 0,
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
        instalar_sugerencias_articulo(self.in_art)
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
        art = self.in_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        self.resultado = {"descripcion": desc, "origen": self.cb_origen.currentText(),
                          "severidad": self.cb_sev.currentText(),
                          "articulo": art or None}
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

class _NuevaAuditoriaDialog(QDialog):
    """Alta de auditoría de calidad (reutiliza auditorias.planificar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 420)
        v, f = _dlg_body(self, "Planificar auditoría de calidad", ancho=580)
        from src.services.calidad import auditorias
        self.cb_tipo = _combo(list(auditorias.TIPOS))
        self.in_alcance = QLineEdit(); self.in_alcance.setPlaceholderText("Alcance de la auditoría")
        for wdg in (self.cb_tipo, self.in_alcance):
            wdg.setMinimumHeight(34)
        f.addRow("Tipo:", self.cb_tipo)
        f.addRow("Alcance:", self.in_alcance)
        # Nota: "auditor" es id de usuario (columna INT, mismo criterio que inspector/responsable en
        # GMAO/SAT) — no un campo de texto libre; el auditor se rellena con el usuario de sesión
        # (ver CalidadDashboardWindow._nueva_auditoria), igual que responsable en NC/CAPA.
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Planificar", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        alcance = self.in_alcance.text().strip()
        if not alcance:
            return
        self.resultado = {"tipo": self.cb_tipo.currentText(), "alcance": alcance}
        self.accept()


class _HallazgoAuditoriaDialog(QDialog):
    """Registro de hallazgo sobre una auditoría (reutiliza auditorias.registrar_hallazgo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 420)
        v, f = _dlg_body(self, "Registrar hallazgo de auditoría", ancho=580)
        self.in_desc = QLineEdit(); self.in_desc.setPlaceholderText("Descripción del hallazgo")
        self.cb_sev = _combo(["baja", "media", "alta", "critica"])
        self.cb_nc = _combo(["No", "Sí"])
        for wdg in (self.in_desc, self.cb_sev, self.cb_nc):
            wdg.setMinimumHeight(34)
        f.addRow("Descripción:", self.in_desc)
        f.addRow("Severidad:", self.cb_sev)
        f.addRow("Generar NC:", self.cb_nc)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Registrar", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        desc = self.in_desc.text().strip()
        if not desc:
            return
        self.resultado = {"descripcion": desc, "severidad": self.cb_sev.currentText(),
                          "generar_nc": self.cb_nc.currentText() == "Sí"}
        self.accept()


class _NuevoEquipoDialog(QDialog):
    """Alta de equipo de medida (reutiliza calidad_pro.alta_equipo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 420)
        v, f = _dlg_body(self, "Nuevo equipo de medida", ancho=580)
        self.in_codigo = QLineEdit(); self.in_codigo.setPlaceholderText("Código del equipo")
        self.in_nombre = QLineEdit(); self.in_nombre.setPlaceholderText("Nombre del equipo")
        self.in_ubicacion = QLineEdit(); self.in_ubicacion.setPlaceholderText("(opcional) ubicación")
        self.in_frecuencia = QLineEdit("365")
        self.in_frecuencia.setValidator(QIntValidator(1, 10_000, self.in_frecuencia))
        for wdg in (self.in_codigo, self.in_nombre, self.in_ubicacion, self.in_frecuencia):
            wdg.setMinimumHeight(34)
        f.addRow("Código:", self.in_codigo)
        f.addRow("Nombre:", self.in_nombre)
        f.addRow("Ubicación:", self.in_ubicacion)
        f.addRow("Frecuencia (días):", self.in_frecuencia)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Dar de alta", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        codigo = self.in_codigo.text().strip()
        nombre = self.in_nombre.text().strip()
        if not codigo or not nombre:
            return
        frec = self.in_frecuencia.text().strip()
        try:
            frec = int(frec) if frec else 365
        except ValueError:
            frec = 365
        self.resultado = {"codigo": codigo, "nombre": nombre,
                          "ubicacion": self.in_ubicacion.text().strip() or None,
                          "frecuencia_dias": frec}
        self.accept()


class _RegistrarCalibracionDialog(QDialog):
    """Registro de calibración de un equipo (reutiliza calidad_pro.registrar_calibracion)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setFixedSize(580, 420)
        v, f = _dlg_body(self, "Registrar calibración", ancho=580)
        self.cb_res = _combo(["CONFORME", "NO_CONFORME"])
        self.in_prov = QLineEdit(); self.in_prov.setPlaceholderText("(opcional) proveedor/laboratorio")
        self.in_obs = QLineEdit(); self.in_obs.setPlaceholderText("(opcional) observaciones")
        for wdg in (self.cb_res, self.in_prov, self.in_obs):
            wdg.setMinimumHeight(34)
        f.addRow("Resultado:", self.cb_res)
        f.addRow("Proveedor:", self.in_prov)
        f.addRow("Observaciones:", self.in_obs)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Registrar", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        self.resultado = {"resultado": self.cb_res.currentText(),
                          "proveedor": self.in_prov.text().strip() or None,
                          "observaciones": self.in_obs.text().strip() or None}
        self.accept()


# Nota: se retiraron los alias de compatibilidad InspeccionesWindow/NoConformidadesWindow/CAPAWindow/
# AuditoriasWindow (código muerto: no los referenciaba ni el menú ni ningún módulo). El acceso a Calidad
# es `CalidadDashboardWindow`, embebido en la pestaña Calidad de Compras/Proveedores.
