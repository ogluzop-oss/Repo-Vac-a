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
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn as _btn_base, _btn_cargando as _btn_cargando_base, _btn_x,
                                      _dialogo_frameless, _tabla)
from src.gui.components.completer_articulos import instalar_sugerencias_articulo

logger = logging.getLogger("gui.gmao")


def _btn(txt, slot=None, primary=False, danger=False):
    """Diseño global: los botones secundarios (antes grises) usan el estilo turquesa (contorno azul
    turquesa, fondo azul oscuro, texto turquesa, hover swap) — igual que 'Actualizar'. Los 'danger'
    (rojo) se conservan. Reutiliza el `_btn` compartido sin modificarlo (solo local a este módulo)."""
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


def _btn_cargando(txt, slot=None, primary=False, danger=False):
    return _btn_cargando_base(txt, slot, primary=(primary or not danger), danger=danger)


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


def _generar_qr_activo(codigo, nombre):
    """Etiqueta QR imprimible de un activo (mismo patrón que
    `gui.ubicacion_tienda.generar_qr_estanteria`, sin coordenadas ni satélite): payload
    `{"tipo":"ACTIVO","codigo":...,"nombre":...}`. El móvil la escanea para localizar el activo
    (`services.gmao.activos.buscar_por_codigo`) y abrir sus OTs in situ."""
    import json
    import os

    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        logger.error("_generar_qr_activo (dependencias): %s", e)
        return None

    try:
        carpeta = os.path.join("documentos", "qr_activos")
        os.makedirs(carpeta, exist_ok=True)
        datos_qr = {"tipo": "ACTIVO", "codigo": codigo, "nombre": nombre or codigo}
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
                           box_size=10, border=4)
        qr.add_data(json.dumps(datos_qr))
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        ancho, alto = img_qr.size
        espacio_texto = 60
        img = Image.new("RGB", (ancho, alto + espacio_texto), "white")
        img.paste(img_qr, (0, 0))
        draw = ImageDraw.Draw(img)
        try:
            fuente = ImageFont.truetype("segoebl.ttf", 22)
        except Exception:
            try:
                fuente = ImageFont.truetype("arialbd.ttf", 22)
            except Exception:
                fuente = ImageFont.load_default()
        texto = str(codigo)
        bbox = draw.textbbox((0, 0), texto, font=fuente)
        tw = bbox[2] - bbox[0]
        draw.text(((ancho - tw) / 2, alto - 10), texto, fill="black", font=fuente)
        ruta = os.path.join(carpeta, f"QR_ACTIVO_{codigo}.png")
        img.save(ruta)
        return ruta
    except Exception as e:
        logger.error("_generar_qr_activo: %s", e)
        return None


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
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;}")

        self.tbl_act = _tabla(["ID", "Código", "Nombre", "Tipo", "Estado", "Criticidad"])
        self.tbl_ot = _tabla(["ID", "Código", "Tipo", "Activo", "Estado", "Prioridad"])
        self.tbl_plan = _tabla(["ID", "Código", "Nombre", "Frecuencia", "Próxima"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])

        self.tabs.addTab(self._page(self.tbl_act, [
            ("➕  Nuevo activo", self._nuevo_activo, True),
            ("Poner en mantenimiento", lambda: self._activo_estado("mantenimiento"), False),
            ("Marcar operativo", lambda: self._activo_estado("operativo"), False),
            ("Dar de baja", lambda: self._activo_estado("baja"), False),
            ("🏷  Imprimir QR", self._imprimir_qr_activo, False),
            ("📋  Ver ficha", self._ver_ficha_activo, False)]), "Activos")
        self.tabs.addTab(self._page(self.tbl_ot, [
            ("➕  Nueva OT", self._nueva_ot, True),
            ("Asignar", self._asignar, False),
            ("Iniciar", lambda: self._ot_estado("iniciar"), False),
            ("Pausar", lambda: self._ot_estado("pausar"), False),
            ("Añadir repuesto", self._anadir_repuesto, False),
            ("Devolver repuesto", self._devolver_repuesto, False),
            ("Consumir repuestos", self._consumir_repuestos, False),
            ("Finalizar", self._finalizar, False),
            ("Cancelar", lambda: self._ot_estado("cancelar"), False)]), "Órdenes de trabajo")
        self.tabs.addTab(self._page(self.tbl_plan, [
            ("➕  Nuevo plan", self._nuevo_plan, True),
            ("Generar OT preventivas vencidas", self._generar_preventivas, False)]), "Planes preventivos")
        self.tabs.addTab(self._page(self.tbl_kpi, []), "KPIs")
        self.tabs.addTab(self._page_gmao_pro(), "Medidores / Rondas")
        root.addWidget(self.tabs)
        self._load()

    def _page(self, tabla, botones):
        """Cada pestaña lleva su PROPIO botón 'Actualizar', arriba a la derecha de su tabla —
        antes había uno solo, compartido, en la cabecera de toda la ventana."""
        w = QWidget(); l = QVBoxLayout(w)
        bar = QHBoxLayout()
        for txt, fn, primary in botones:
            bar.addWidget(_btn(txt, fn, primary=primary))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
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
    def _set(self, msg, nivel="info"):
        self.lbl.setText(msg)
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "GMAO · Mantenimiento", msg, nivel=nivel)
        except Exception:
            pass

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
            self._set("Permiso requerido: activos.gestionar", nivel="warning"); return
        dlg = _NuevoActivoDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import activos
            aid = activos.crear_activo(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Activo creado: {aid}" if aid else "No se pudo crear el activo.",
                     nivel="success" if aid else "error")
            self._load()

    def _activo_estado(self, estado):
        if not _puede(self.usuario, "activos.gestionar"):
            self._set("Permiso requerido: activos.gestionar", nivel="warning"); return
        aid = self._sel_id(self.tbl_act)
        if not aid:
            self._set("Selecciona un activo.", nivel="warning"); return
        from src.services.gmao import activos
        ok = activos.cambiar_estado(aid, estado, id_empresa=_empresa())
        self._set(f"Activo {aid} → {estado}" if ok else f"No se pudo cambiar el activo {aid}.",
                 nivel="success" if ok else "error")
        self._load()

    def _imprimir_qr_activo(self):
        aid = self._sel_id(self.tbl_act)
        if not aid:
            self._set("Selecciona un activo.", nivel="warning"); return
        from src.services.gmao import activos
        activo = activos.obtener(aid)
        if not activo:
            self._set(f"Activo {aid} no encontrado.", nivel="error"); return
        ruta = _generar_qr_activo(activo.get("codigo"), activo.get("nombre"))
        if not ruta:
            self._set("No se pudo generar el QR del activo.", nivel="error"); return
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))
        except Exception:
            pass
        self._set(f"QR del activo {activo.get('codigo')} generado: {ruta}", nivel="success")

    def _ver_ficha_activo(self):
        aid = self._sel_id(self.tbl_act)
        if not aid:
            self._set("Selecciona un activo.", nivel="warning"); return
        from src.services.gmao import activos
        activo = activos.obtener(aid)
        if not activo:
            self._set(f"Activo {aid} no encontrado.", nivel="error"); return
        _FichaActivoDialog(activo, self).exec()

    # ── Órdenes de trabajo ────────────────────────────────────────────────────
    def _nueva_ot(self):
        if not _puede(self.usuario, "ot.crear"):
            self._set("Permiso requerido: ot.crear", nivel="warning"); return
        dlg = _NuevaOTDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import ordenes
            oid = ordenes.crear_ot(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"OT creada: {oid}" if oid else "No se pudo crear la OT.",
                     nivel="success" if oid else "error")
            self._load()

    def _asignar(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        tec, ok = QInputDialog.getInt(self, "Asignar OT", "ID del técnico:", self._uid() or 0, 0, 10_000_000, 1)
        if not ok:
            return
        from src.services.gmao import ordenes
        r = ordenes.asignar(oid, tec, id_empresa=_empresa())
        self._set(f"OT {oid} asignada al técnico {tec}" if r.get("ok") else f"OT {oid}: {r.get('error')}",
                 nivel="success" if r.get("ok") else "error")
        self._load()

    def _ot_estado(self, accion):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        from src.services.gmao import ordenes
        fn = {"iniciar": ordenes.iniciar, "cancelar": ordenes.cancelar,
              "pausar": lambda o, **k: ordenes.cambiar_estado(o, "pausada", **k)}[accion]
        r = fn(oid, id_empresa=_empresa())
        self._set(f"OT {oid} → {r.get('estado')}" if r.get("ok") else f"OT {oid}: {r.get('error')}",
                 nivel="success" if r.get("ok") else "error")
        self._load()

    def _anadir_repuesto(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        dlg = _RepuestoDialog(self)
        if dlg.exec() and dlg.resultado:
            ref, cant, coste = dlg.resultado
            from src.services.gmao import ordenes
            rid = ordenes.añadir_repuesto(oid, ref, cant, coste_unitario=coste, id_empresa=_empresa())
            self._set(f"Repuesto {ref} x{cant} añadido a OT {oid}" if rid else "No se pudo añadir el repuesto.",
                     nivel="success" if rid else "error")
            self._load()

    def _devolver_repuesto(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        dlg = _DevolverRepuestoDialog(self)
        if dlg.exec() and dlg.resultado:
            ref, cant = dlg.resultado
            from src.services.gmao import ordenes
            ok = ordenes.devolver_repuesto(oid, ref, cant, id_empresa=_empresa(), usuario=self._uid())
            self._set(f"Repuesto {ref} x{cant} devuelto al stock desde OT {oid}." if ok
                     else "No se pudo devolver el repuesto.", nivel="success" if ok else "error")
            self._load()

    def _consumir_repuestos(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        from src.services.gmao import ordenes
        r = ordenes.consumir_repuestos(oid, id_empresa=_empresa(), usuario=self._uid())
        self._set(f"OT {oid}: repuestos consumidos vía kárdex oficial ({len(r.get('consumidos', []))})."
                  if r.get("ok") else f"OT {oid}: {r.get('error')}", nivel="success" if r.get("ok") else "error")
        self._load()

    def _finalizar(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        oid = self._sel_id(self.tbl_ot)
        if not oid:
            self._set("Selecciona una OT.", nivel="warning"); return
        horas, ok = QInputDialog.getDouble(self, "Finalizar OT", "Horas de mano de obra:", 1, 0, 1000, 2)
        if not ok:
            return
        from src.services.gmao import ordenes
        r = ordenes.finalizar(oid, horas_mano_obra=horas, id_empresa=_empresa(), usuario=self._uid())
        self._set(f"OT {oid} FINALIZADA. Coste: {r.get('coste_total', '—')}" if r.get("ok")
                  else f"OT {oid}: {r.get('error')}", nivel="success" if r.get("ok") else "error")
        self._load()

    # ── Planes preventivos ────────────────────────────────────────────────────
    def _nuevo_plan(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        dlg = _NuevoPlanDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.gmao import planes
            pid = planes.crear_plan(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Plan preventivo creado: {pid}" if pid else "No se pudo crear el plan.",
                     nivel="success" if pid else "error")
            self._load()

    def _generar_preventivas(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        from src.services.gmao import planes
        ots = planes.generar_ot_preventivas(id_empresa=_empresa())
        self._set(f"Generadas {len(ots)} OT preventivas de planes vencidos.", nivel="success")
        self._load()

    # ── GMAO Pro: mantenimiento por uso (medidores) + rondas/checklists ────────
    # Motor en `src.services.gmao.gmao_pro` — existía sin ningún frontend antes de esta auditoría.
    def _page_gmao_pro(self):
        w = QWidget(); ly = QVBoxLayout(w)

        ly.addWidget(QLabel("Medidores / mantenimiento por uso"))
        f = QHBoxLayout()
        self.gp_med_activo = QComboBox()
        self.gp_med_tipo = _combo(["horas", "km", "ciclos"])
        self.gp_med_umbral = QLineEdit(); self.gp_med_umbral.setPlaceholderText("Umbral preventivo")
        self.gp_med_lectura = QLineEdit("0"); self.gp_med_lectura.setPlaceholderText("Lectura inicial")
        for wd in (self.gp_med_activo, self.gp_med_tipo, self.gp_med_umbral, self.gp_med_lectura):
            f.addWidget(wd)
        f.addWidget(_btn("Dar de alta medidor", self._gp_alta_medidor, primary=True))
        ly.addLayout(f)
        self.tbl_gp_med = _tabla(["ID", "Activo", "Tipo", "Lectura actual", "Umbral", "Desde última OT"])
        self.tbl_gp_med.cellClicked.connect(self._gp_sel_medidor)
        ly.addWidget(self.tbl_gp_med)
        f2 = QHBoxLayout()
        self.gp_med_valor = QLineEdit(); self.gp_med_valor.setPlaceholderText("Nueva lectura")
        self.gp_med_operario = QLineEdit(); self.gp_med_operario.setPlaceholderText("Operario")
        f2.addWidget(self.gp_med_valor); f2.addWidget(self.gp_med_operario)
        f2.addWidget(_btn("Registrar lectura", self._gp_registrar_lectura, primary=True))
        ly.addLayout(f2)

        ly.addWidget(QLabel("Rondas / checklists de inspección"))
        f3 = QHBoxLayout()
        self.gp_chk_codigo = QLineEdit(); self.gp_chk_codigo.setPlaceholderText("Código")
        self.gp_chk_nombre = QLineEdit(); self.gp_chk_nombre.setPlaceholderText("Nombre")
        self.gp_chk_items = QLineEdit(); self.gp_chk_items.setPlaceholderText("Ítems separados por comas")
        for wd in (self.gp_chk_codigo, self.gp_chk_nombre, self.gp_chk_items):
            f3.addWidget(wd)
        f3.addWidget(_btn("Crear checklist", self._gp_crear_checklist, primary=True))
        ly.addLayout(f3)
        self.tbl_gp_chk = _tabla(["ID", "Código", "Nombre"])
        self.tbl_gp_chk.cellClicked.connect(self._gp_sel_checklist)
        ly.addWidget(self.tbl_gp_chk)
        f4 = QHBoxLayout()
        self.gp_ron_activo = QComboBox()
        self.gp_ron_resultados = QLineEdit()
        self.gp_ron_resultados.setPlaceholderText("Resultados: ítem=ok, ítem=ko…")
        self.gp_ron_operario = QLineEdit(); self.gp_ron_operario.setPlaceholderText("Operario")
        for wd in (self.gp_ron_activo, self.gp_ron_resultados, self.gp_ron_operario):
            f4.addWidget(wd)
        f4.addWidget(_btn("Ejecutar ronda", self._gp_ejecutar_ronda, primary=True))
        ly.addLayout(f4)
        self.tbl_gp_ron = _tabla(["ID", "Activo", "Conforme", "Fecha"])
        ly.addWidget(self.tbl_gp_ron)

        self._gp_medidor_sel = None
        self._gp_checklist_sel = None
        self._gp_cargar_combos_activos()
        self._gp_cargar_medidores()
        self._gp_cargar_checklists()
        return w

    def _gp_cargar_combos_activos(self):
        from src.services.gmao import activos
        acts = activos.listar(id_empresa=_empresa())
        for cb in (self.gp_med_activo, self.gp_ron_activo):
            cb.clear()
            for a in acts:
                cb.addItem(f"{a.get('codigo')} — {a.get('nombre')}", a.get("id"))

    def _gp_cargar_medidores(self):
        from src.services.gmao import activos, gmao_pro as GP
        nombres = {a["id"]: a.get("codigo") for a in activos.listar(id_empresa=_empresa())}
        self._gp_medidores = GP.listar_medidores(_empresa())
        self.tbl_gp_med.setRowCount(len(self._gp_medidores))
        for i, m in enumerate(self._gp_medidores):
            vals = [m.get("id"), nombres.get(m.get("id_activo"), m.get("id_activo")), m.get("tipo"),
                    m.get("lectura_actual"), m.get("umbral_preventivo"), m.get("lectura_ultima_ot")]
            for j, v in enumerate(vals):
                self.tbl_gp_med.setItem(i, j, _it(v))
        self._gp_medidor_sel = None

    def _gp_sel_medidor(self, row, _c):
        try:
            self._gp_medidor_sel = self._gp_medidores[row]
        except (IndexError, AttributeError):
            self._gp_medidor_sel = None

    def _gp_alta_medidor(self):
        if not _puede(self.usuario, "activos.gestionar"):
            self._set("Permiso requerido: activos.gestionar", nivel="warning"); return
        aid = self.gp_med_activo.currentData()
        if not aid:
            self._set("No hay activos disponibles.", nivel="warning"); return
        try:
            umbral = float(self.gp_med_umbral.text().strip().replace(",", ".")) if self.gp_med_umbral.text().strip() else None
            lectura = float(self.gp_med_lectura.text().strip().replace(",", ".") or 0)
        except ValueError:
            self._set("Umbral/lectura deben ser numéricos.", nivel="error"); return
        from src.services.gmao import gmao_pro as GP
        mid = GP.alta_medidor(aid, tipo=self.gp_med_tipo.currentText(), umbral_preventivo=umbral,
                              lectura_actual=lectura, id_empresa=_empresa())
        self._set(f"Medidor creado: {mid}" if mid else "No se pudo crear el medidor.",
                 nivel="success" if mid else "error")
        if mid:
            self._gp_cargar_medidores()

    def _gp_registrar_lectura(self):
        if not self._gp_medidor_sel:
            self._set("Selecciona primero un medidor en la tabla.", nivel="warning"); return
        try:
            valor = float(self.gp_med_valor.text().strip().replace(",", "."))
        except ValueError:
            self._set("La lectura debe ser numérica.", nivel="error"); return
        from src.services.gmao import gmao_pro as GP
        r = GP.registrar_lectura(self._gp_medidor_sel["id"], valor,
                                 operario=self.gp_med_operario.text().strip() or None, id_empresa=_empresa())
        if r.get("ok"):
            msg = f"Lectura registrada (uso desde última OT: {r.get('uso_desde_ot')})."
            if r.get("ot_generada"):
                msg += f" OT preventiva generada: #{r['ot_generada']}."
            self._set(msg, nivel="success")
            self.gp_med_valor.clear()
            self._gp_cargar_medidores()
        else:
            self._set(r.get("motivo") or "No se pudo registrar la lectura.", nivel="error")

    def _gp_cargar_checklists(self):
        from src.services.gmao import gmao_pro as GP
        self._gp_checklists = GP.listar_checklists(_empresa())
        self.tbl_gp_chk.setRowCount(len(self._gp_checklists))
        for i, c in enumerate(self._gp_checklists):
            for j, v in enumerate([c.get("id"), c.get("codigo"), c.get("nombre")]):
                self.tbl_gp_chk.setItem(i, j, _it(v))
        self._gp_checklist_sel = None

    def _gp_sel_checklist(self, row, _c):
        try:
            self._gp_checklist_sel = self._gp_checklists[row]
        except (IndexError, AttributeError):
            self._gp_checklist_sel = None
        self._gp_cargar_rondas()

    def _gp_cargar_rondas(self):
        from src.services.gmao import gmao_pro as GP
        if not self._gp_checklist_sel:
            self.tbl_gp_ron.setRowCount(0); return
        rondas = GP.listar_rondas(_empresa(), id_checklist=self._gp_checklist_sel["id"])
        self.tbl_gp_ron.setRowCount(len(rondas))
        for i, r in enumerate(rondas):
            for j, v in enumerate([r.get("id"), r.get("id_activo"),
                                   "Sí" if r.get("conforme") else "No", r.get("fecha")]):
                self.tbl_gp_ron.setItem(i, j, _it(v))

    def _gp_crear_checklist(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        codigo = self.gp_chk_codigo.text().strip()
        nombre = self.gp_chk_nombre.text().strip()
        if not codigo or not nombre:
            self._set("Indica código y nombre del checklist.", nivel="warning"); return
        items = [{"texto": t.strip(), "tipo": "ok_ko"} for t in self.gp_chk_items.text().split(",") if t.strip()]
        from src.services.gmao import gmao_pro as GP
        cid = GP.crear_checklist(codigo, nombre, items, id_empresa=_empresa())
        self._set(f"Checklist creado: {cid}" if cid else "No se pudo crear el checklist.",
                 nivel="success" if cid else "error")
        if cid:
            self.gp_chk_codigo.clear(); self.gp_chk_nombre.clear(); self.gp_chk_items.clear()
            self._gp_cargar_checklists()

    def _gp_ejecutar_ronda(self):
        if not _puede(self.usuario, "gmao.admin"):
            self._set("Permiso requerido: gmao.admin", nivel="warning"); return
        if not self._gp_checklist_sel:
            self._set("Selecciona primero un checklist en la tabla.", nivel="warning"); return
        aid = self.gp_ron_activo.currentData()
        resultados = []
        for par in self.gp_ron_resultados.text().split(","):
            if "=" not in par:
                continue
            item, res = par.split("=", 1)
            item = item.strip()
            if item:
                resultados.append({"item": item, "texto": item, "resultado": res.strip()})
        from src.services.gmao import gmao_pro as GP
        r = GP.ejecutar_ronda(self._gp_checklist_sel["id"], id_activo=aid, resultados=resultados,
                              operario=self.gp_ron_operario.text().strip() or None, id_empresa=_empresa())
        if r.get("ok"):
            estado = "conforme" if r.get("conforme") else f"{r.get('fallos')} fallo(s)"
            msg = f"Ronda registrada — {estado}."
            if r.get("ot_generada"):
                msg += f" OT correctiva generada: #{r['ot_generada']}."
            self._set(msg, nivel="success" if r.get("conforme") else "warning")
            self.gp_ron_resultados.clear()
            self._gp_cargar_rondas()
        else:
            self._set(r.get("motivo") or "No se pudo registrar la ronda.", nivel="error")


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
        # QLineEdit + validador en vez de QDoubleSpinBox: la app oculta las flechas arriba/abajo de
        # esos widgets vía QSS y eso rompía su foco/clic en varios diálogos — mismo criterio ya
        # aplicado en `_RepuestoDialog.in_coste` de este mismo fichero.
        from PyQt6.QtGui import QDoubleValidator
        self.in_precio = QLineEdit(); self.in_precio.setPlaceholderText("Precio de adquisición (obligatorio)")
        val_precio = QDoubleValidator(0.0, 1e9, 2, self.in_precio)
        val_precio.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_precio.setValidator(val_precio)
        for lbl, w in (("Código:", self.in_cod), ("Nombre:", self.in_nom), ("Tipo:", self.cb_tipo),
                       ("Nº serie:", self.in_serie), ("Fabricante:", self.in_fab),
                       ("Modelo:", self.in_mod), ("Ubicación:", self.in_ubi), ("Criticidad:", self.cb_crit),
                       ("Precio de adquisición (€) *:", self.in_precio)):
            f.addRow(lbl, w)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        body.addLayout(row)
        # El centrado sobre pantalla real (no sobre el padre) ya lo aplica `_dialogo_frameless`
        # para TODOS los diálogos que lo usan — ver `catalogo_gestion.centrar_en_pantalla`.

    def _ok(self):
        cod = self.in_cod.text().strip(); nom = self.in_nom.text().strip()
        if not cod or not nom:
            from assets.estilo_global import mostrar_mensaje
            return mostrar_mensaje(self, "Nuevo activo", "Código y nombre son obligatorios.", nivel="warning")
        try:
            precio = float((self.in_precio.text() or "0").replace(",", "."))
        except ValueError:
            precio = 0.0
        if precio <= 0:
            from assets.estilo_global import mostrar_mensaje
            return mostrar_mensaje(self, "Nuevo activo",
                                   "Indica el precio de adquisición (obligatorio, mayor que 0).", nivel="warning")
        import datetime as _dt
        self.resultado = {"codigo": cod, "nombre": nom, "tipo": self.cb_tipo.currentText(),
                          "numero_serie": self.in_serie.text().strip() or None,
                          "fabricante": self.in_fab.text().strip() or None,
                          "modelo": self.in_mod.text().strip() or None,
                          "ubicacion": self.in_ubi.text().strip() or None,
                          "criticidad": self.cb_crit.currentText(),
                          "coste_adquisicion": precio,
                          "fecha_compra": _dt.date.today().strftime("%Y-%m-%d")}
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
        # QLineEdit + validador en vez de QSpinBox/QDoubleSpinBox: la app oculta las flechas
        # arriba/abajo de esos widgets vía QSS y eso rompía su foco/clic en varios diálogos
        # (confirmado por el usuario) — mismo criterio ya aplicado en `sat_dashboard._FormDialog`.
        from PyQt6.QtGui import QDoubleValidator, QIntValidator
        self.in_ref = QLineEdit(); self.in_ref.setPlaceholderText("Referencia/código del repuesto")
        instalar_sugerencias_articulo(self.in_ref)
        self.in_cant = QLineEdit("1")
        self.in_cant.setValidator(QIntValidator(1, 1_000_000, self.in_cant))
        self.in_coste = QLineEdit("0.00")
        val_coste = QDoubleValidator(0.0, 1e9, 2, self.in_coste)
        val_coste.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_coste.setValidator(val_coste)
        f.addRow("Referencia:", self.in_ref)
        f.addRow("Cantidad:", self.in_cant)
        f.addRow("Coste unitario:", self.in_coste)
        row = QHBoxLayout()
        row.addWidget(_btn("Añadir", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        ref = self.in_ref.text().strip()
        if "–" in ref:  # viene del autocompletado "CÓDIGO – NOMBRE"
            ref = ref.split("–")[0].strip()
        if not ref:
            return
        try:
            cant = int(self.in_cant.text() or 1)
        except ValueError:
            cant = 1
        try:
            coste = float((self.in_coste.text() or "0").replace(",", "."))
        except ValueError:
            coste = 0.0
        self.resultado = (ref, cant, coste)
        self.accept()


class _DevolverRepuestoDialog(QDialog):
    """Devolver repuesto sobrante de una OT al stock (reutiliza ordenes.devolver_repuesto —
    entrada real en kárdex/lotes, sin motor de stock paralelo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Devolver repuesto")
        body = _dialogo_frameless(self, "Devolver repuesto")
        f = QFormLayout(); body.addLayout(f)
        from PyQt6.QtGui import QIntValidator
        self.in_ref = QLineEdit(); self.in_ref.setPlaceholderText("Referencia/código del repuesto")
        instalar_sugerencias_articulo(self.in_ref)
        self.in_cant = QLineEdit("1")
        self.in_cant.setValidator(QIntValidator(1, 1_000_000, self.in_cant))
        f.addRow("Referencia:", self.in_ref)
        f.addRow("Cantidad:", self.in_cant)
        row = QHBoxLayout()
        row.addWidget(_btn("Devolver", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        ref = self.in_ref.text().strip()
        if "–" in ref:  # viene del autocompletado "CÓDIGO – NOMBRE"
            ref = ref.split("–")[0].strip()
        if not ref:
            return
        try:
            cant = int(self.in_cant.text() or 1)
        except ValueError:
            cant = 1
        self.resultado = (ref, cant)
        self.accept()


class _GarantiaDialog(QDialog):
    """Alta de garantía de un activo (reutiliza activos.registrar_garantia)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Registrar garantía")
        body = _dialogo_frameless(self, "Registrar garantía")
        f = QFormLayout(); body.addLayout(f)
        self.in_prov = QLineEdit(); self.in_prov.setPlaceholderText("Proveedor")
        self.in_ini = QLineEdit(); self.in_ini.setPlaceholderText("Fecha inicio AAAA-MM-DD")
        self.in_fin = QLineEdit(); self.in_fin.setPlaceholderText("Fecha fin AAAA-MM-DD")
        self.in_cob = QLineEdit(); self.in_cob.setPlaceholderText("Cobertura")
        f.addRow("Proveedor:", self.in_prov)
        f.addRow("Fecha inicio:", self.in_ini)
        f.addRow("Fecha fin:", self.in_fin)
        f.addRow("Cobertura:", self.in_cob)
        row = QHBoxLayout()
        row.addWidget(_btn("Registrar", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        self.resultado = {"proveedor": self.in_prov.text().strip() or None,
                          "fecha_inicio": self.in_ini.text().strip() or None,
                          "fecha_fin": self.in_fin.text().strip() or None,
                          "cobertura": self.in_cob.text().strip() or None}
        self.accept()


class _FichaActivoDialog(QDialog):
    """Ficha completa de un activo — historial, garantías y documentos (`services.gmao.activos.
    historial/registrar_garantia/adjuntar_documento`), sin ningún frontend hasta esta auditoría."""

    def __init__(self, activo, parent=None):
        super().__init__(parent)
        self.id_activo = activo.get("id")
        self.setWindowTitle(f"Ficha · {activo.get('codigo')}")
        body = _dialogo_frameless(self, f"Ficha del activo · {activo.get('codigo')} — {activo.get('nombre')}",
                                  ancho=680)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_BG};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid #30363D;}}")

        w_hist = QWidget(); l_hist = QVBoxLayout(w_hist)
        self.tbl_hist = _tabla(["Fecha", "Tipo", "Detalle"])
        l_hist.addWidget(self.tbl_hist)
        tabs.addTab(w_hist, "Historial")

        w_gar = QWidget(); l_gar = QVBoxLayout(w_gar)
        self.tbl_gar = _tabla(["Proveedor", "Inicio", "Fin", "Cobertura"])
        l_gar.addWidget(self.tbl_gar)
        row_gar = QHBoxLayout()
        row_gar.addWidget(_btn("Registrar garantía", self._registrar_garantia, primary=True))
        row_gar.addStretch()
        l_gar.addLayout(row_gar)
        tabs.addTab(w_gar, "Garantías")

        w_doc = QWidget(); l_doc = QVBoxLayout(w_doc)
        self.tbl_doc = _tabla(["Nombre", "Ruta"])
        l_doc.addWidget(self.tbl_doc)
        row_doc = QHBoxLayout()
        row_doc.addWidget(_btn("Adjuntar documento", self._adjuntar_documento, primary=True))
        row_doc.addStretch()
        l_doc.addLayout(row_doc)
        tabs.addTab(w_doc, "Documentos")

        body.addWidget(tabs)
        row = QHBoxLayout(); row.addStretch()
        row.addWidget(_btn("Cerrar", self.accept, primary=True))
        body.addLayout(row)
        self._cargar()

    def _cargar(self):
        from src.services.gmao import activos
        hist = activos.historial(self.id_activo)
        self.tbl_hist.setRowCount(len(hist))
        for i, h in enumerate(hist):
            for j, v in enumerate([h.get("fecha"), h.get("evento"), h.get("detalle")]):
                self.tbl_hist.setItem(i, j, _it(v))
        gar = activos.listar_garantias(self.id_activo)
        self.tbl_gar.setRowCount(len(gar))
        for i, g in enumerate(gar):
            for j, v in enumerate([g.get("proveedor"), g.get("fecha_inicio"), g.get("fecha_fin"),
                                   g.get("cobertura")]):
                self.tbl_gar.setItem(i, j, _it(v))
        doc = activos.listar_documentos(self.id_activo)
        self.tbl_doc.setRowCount(len(doc))
        for i, d in enumerate(doc):
            for j, v in enumerate([d.get("nombre"), d.get("ruta")]):
                self.tbl_doc.setItem(i, j, _it(v))

    def _registrar_garantia(self):
        from src.services.gmao import activos
        dlg = _GarantiaDialog(self)
        if dlg.exec() and dlg.resultado:
            gid = activos.registrar_garantia(self.id_activo, id_empresa=_empresa(), **dlg.resultado)
            if gid:
                self._cargar()

    def _adjuntar_documento(self):
        from PyQt6.QtWidgets import QFileDialog
        from src.services.gmao import activos
        ruta, _f = QFileDialog.getOpenFileName(self, "Adjuntar documento")
        if not ruta:
            return
        import os
        nombre = os.path.basename(ruta)
        did = activos.adjuntar_documento(self.id_activo, nombre, ruta=ruta, id_empresa=_empresa())
        if did:
            self._cargar()


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
