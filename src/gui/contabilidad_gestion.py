"""
Ventana de CONTABILIDAD (E6.7) — expone el motor contable en la interfaz principal.

Reutiliza los patrones visuales de `catalogo_gestion`/`compras_gestion` (sidebar `sw`
+ QStackedWidget + helpers _btn/_inp/_tabla/_combo + estilo global). Solo presentación;
la lógica vive en `src.services.contabilidad.*` (ya probada en E6.1-E6.6).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _btn, _btn_salir_sidebar,
                                      _combo, _inp, _tabla)
from src.services.contabilidad import asientos as A
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import informes as I
from src.services.contabilidad import iva as IVA
from src.services.contabilidad import mapeo as M
from src.services.contabilidad import posting as Pg
from src.utils.i18n import tr

logger = logging.getLogger("gui.contabilidad")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _tabla_c(cols):
    """Igual que _tabla pero con las CABECERAS +2pt (11px → 13px), solo para Contabilidad.
    No toca el helper global _tabla (compartido por el resto de módulos)."""
    t = _tabla(cols)
    t.setStyleSheet(t.styleSheet().replace("font-size:11px", "font-size:13px"))
    return t


class ContabilidadWindow(QWidget):
    _SECCIONES = [
        ("plan", "📒", "Plan de cuentas"),
        ("diario", "📓", "Diario"),
        ("mayor", "📚", "Mayor"),
        ("balances", "⚖️", "Balances"),
        ("gastos", "💸", "Gastos"),
        ("iva", "🧾", "Libros IVA"),
        ("cierres", "🔒", "Cierres"),
        # Migrados (módulo fiscal): AEAT (embebido) + documentos fiscales, ahora en 3 pestañas separadas
        # (con los campos a rellenar EN LA PROPIA pestaña, sin ventana emergente).
        ("aeat", "📑", "AEAT"),
        ("libro_ing", "📈", "Libro de Ingresos"),
        ("libro_gas", "📉", "Libro de Gastos"),
        ("auditoria", "🔍", "Informe Auditoría"),
    ]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.anio = _dt.date.today().year
        self.setWindowTitle("Smart Manager — " + tr("contab.titulo", default="CONTABILIDAD"))

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._sidebar())
        right = QWidget(); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_plan())
        self.stack.addWidget(self._page_diario())
        self.stack.addWidget(self._page_mayor())
        self.stack.addWidget(self._page_balances())
        self.stack.addWidget(self._page_gastos())
        self.stack.addWidget(self._page_iva())
        self.stack.addWidget(self._page_cierres())
        self.stack.addWidget(self._page_aeat())
        self.stack.addWidget(self._page_libro_ingresos())
        self.stack.addWidget(self._page_libro_gastos())
        self.stack.addWidget(self._page_auditoria())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self._ir(0)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="contabilidad")
        except Exception:
            pass

    # ── Cabecera / sidebar ───────────────────────────────────────────────────
    def _header(self):
        cab = QHBoxLayout()
        t = QLabel("📊  " + tr("contab.titulo", default="CONTABILIDAD"))
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch(1)
        if not K.contabilidad_activa():
            cab.addWidget(_btn(tr("contab.activar", default="ACTIVAR CONTABILIDAD"),
                               self._activar, primary=True))
        return cab

    def _sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230); self.sidebar = wrap  # P3
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("contab.secciones", default="CONTABILIDAD"))
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:16px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb = []
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"   {tr('contab.sec_' + sid, default=defecto)}")   # sin icono
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setProperty("lg", "true")      # +2pt (14px) vía QSS global
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb.append(b); lay.addWidget(b)
        lay.addStretch(1)
        if self._volver:   # SALIR AL MENÚ (rojo) al fondo del sidebar
            lay.addWidget(_btn_salir_sidebar(self._volver_menu))
        return wrap

    _ON = (f"QPushButton{{background:#1A2230;color:{_CIAN};text-align:left;padding:8px 8px 8px 24px;"
           f"border:none;border-left:4px solid {_CIAN};border-radius:0px;font-size:13px;font-weight:900;}}")
    _OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;padding:8px 8px 8px 24px;"
            f"border:none;border-left:4px solid transparent;border-radius:0px;font-size:13px;font-weight:900;}}"
            f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")

    def _ir(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb):
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar:checked
        [self._load_plan, self._load_diario, lambda: None, self._load_balances,
         self._load_gastos, self._load_iva, lambda: None, lambda: None,
         lambda: None, lambda: None, lambda: None][idx]()   # aeat + libro_ing/gas + auditoría: sin carga

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

    # ── Migrados: AEAT (embebido) + documentos fiscales (libros/auditoría) ───────
    def _page_aeat(self):
        """Pestaña AEAT con 3 apartados: Generar (modelos AEAT) · Certificados · Registros Verifactu.
        El módulo Fiscal del menú principal se MIGRA aquí reutilizando `FiscalPanels` (misma implementación
        que la ventana Fiscal; sin duplicar). Degradable: si algo falla, se muestra solo lo disponible."""
        from PyQt6.QtWidgets import QTabWidget
        tabs = QTabWidget()
        # 1) Generar — modelos AEAT (303/390/111/190/347/349): el AEATWindow existente.
        try:
            from src.gui.aeat_gui import AEATWindow
            tabs.addTab(AEATWindow(callback_vuelta=None, usuario=self.usuario, main=self), "Generar")
        except Exception as e:
            logger.error("embed AEAT (Generar) en Contabilidad: %s", e)
            tabs.addTab(QWidget(), "Generar")
        # 2) + 3) Certificados y Registros Verifactu — módulo Fiscal migrado (reutiliza FiscalPanels).
        try:
            from src.gui.fiscal_gui import FiscalPanels
            self._fiscal_panels = FiscalPanels(usuario=self.usuario, host=self)
            tabs.addTab(self._fiscal_panels.pagina_certificados, "Certificados")
            tabs.addTab(self._fiscal_panels.pagina_verifactu, "Registros Verifactu")
        except Exception as e:
            logger.error("embed Fiscal (Certificados/Verifactu) en AEAT: %s", e)
        return tabs

    # ── Documentos fiscales: 3 pestañas con campos INLINE (sin ventana emergente) ─────────────
    def _page_libro_ingresos(self):
        return self._panel_fiscal("LIBRO INGRESOS", "📈  Libro de Ingresos",
                                  "Genera el libro de ingresos de la empresa para el período indicado.")

    def _page_libro_gastos(self):
        return self._panel_fiscal("LIBRO GASTOS", "📉  Libro de Gastos",
                                  "Genera el libro de gastos de la empresa para el período indicado.")

    def _page_auditoria(self):
        return self._panel_fiscal("INFORME AUDIT", "🔍  Informe de Auditoría",
                                  "Genera un informe de auditoría del ámbito elegido para el período indicado.",
                                  subtipos=["CAJA", "RRHH", "ACCESOS", "MOVIMIENTOS", "DOCUMENTOS"])

    def _datos_empresa(self):
        try:
            from src.db import empresa as _emp
            emp = (_emp.datos_corporativos().get("empresa")) or {}
            return {"nombre": emp.get("razon_social") or emp.get("nombre_empresa") or emp.get("nombre") or "",
                    "cif": emp.get("cif") or emp.get("nif") or "",
                    "dir": emp.get("direccion") or emp.get("domicilio") or emp.get("direccion_fiscal") or ""}
        except Exception:
            return {"nombre": "", "cif": "", "dir": ""}

    def _panel_fiscal(self, tipo, titulo, subtitulo, subtipos=None):
        """Panel embebido con los campos del documento fiscal + generación (reutiliza el motor de PDF del
        asistente existente, SIN mostrar la ventana emergente)."""
        from PyQt6.QtWidgets import QFormLayout
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(12)
        t = QLabel(titulo); t.setStyleSheet(f"color:{_CIAN};font-size:17px;font-weight:900;")
        ly.addWidget(t)
        sub = QLabel(subtitulo); sub.setStyleSheet(f"color:{_DIM};"); sub.setWordWrap(True); ly.addWidget(sub)

        e = self._datos_empresa()
        form = QFormLayout(); form.setSpacing(10)

        def _lbl(txt):
            la = QLabel(txt); la.setStyleSheet(f"color:{_DIM};font-weight:700;"); return la

        in_nombre = _inp("Nombre / Razón social"); in_nombre.setText(e["nombre"])
        in_cif = _inp("CIF"); in_cif.setText(e["cif"])
        in_dir = _inp("Domicilio fiscal"); in_dir.setText(e["dir"])
        in_ini = _inp("dd/mm/aaaa"); in_ini.setText("01/01/" + str(_dt.date.today().year))
        in_fin = _inp("dd/mm/aaaa"); in_fin.setText(_dt.date.today().strftime("%d/%m/%Y"))
        form.addRow(_lbl("Empresa:"), in_nombre)
        form.addRow(_lbl("CIF:"), in_cif)
        form.addRow(_lbl("Domicilio fiscal:"), in_dir)
        form.addRow(_lbl("Período · desde:"), in_ini)
        form.addRow(_lbl("Período · hasta:"), in_fin)
        cmb_sub = None
        if subtipos:
            cmb_sub = _combo([(s, s) for s in subtipos]); cmb_sub.setMinimumWidth(220)
            form.addRow(_lbl("Ámbito de auditoría:"), cmb_sub)
        ly.addLayout(form)

        panel = {"tipo": tipo, "nombre": in_nombre, "cif": in_cif, "dir": in_dir,
                 "ini": in_ini, "fin": in_fin, "sub": cmb_sub, "ruta": None}
        ly.addWidget(_btn("📄  GENERAR DOCUMENTO", lambda: self._generar_doc_fiscal(panel), primary=True))
        lbl_res = QLabel(""); lbl_res.setWordWrap(True); lbl_res.setVisible(False)
        lbl_res.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        panel["res"] = lbl_res; ly.addWidget(lbl_res)
        btn_open = _btn("📂  ABRIR PDF", lambda: self._abrir_pdf(panel), primary=True)
        btn_open.setVisible(False); panel["open"] = btn_open
        ly.addWidget(btn_open, alignment=Qt.AlignmentFlag.AlignLeft)
        ly.addStretch()
        return w

    def _generar_doc_fiscal(self, panel):
        datos = {"emp_nombre": panel["nombre"].text().strip(), "emp_cif": panel["cif"].text().strip(),
                 "emp_dir": panel["dir"].text().strip(), "periodo_ini": panel["ini"].text().strip(),
                 "periodo_fin": panel["fin"].text().strip()}
        if panel["sub"] is not None:
            datos["subtipo"] = panel["sub"].currentText()
        try:
            # Reutiliza EXACTAMENTE la generación del asistente fiscal (no se duplica el PDF): se instancia
            # el wizard, se le inyectan los datos y se genera, SIN mostrarlo (los campos ya están en la pestaña).
            from src.gui.gestion_usuarios import _WizardDocumentoFiscal
            wiz = _WizardDocumentoFiscal(tipo_inicial=panel["tipo"], parent=self)
            wiz._tipo = panel["tipo"]
            wiz._datos.update(datos)
            wiz._generar_pdf()
            ruta = getattr(wiz, "_pdf_ruta", None)
            wiz.deleteLater()
        except Exception as ex:
            logger.error("generar doc fiscal (%s): %s", panel["tipo"], ex)
            _aviso(self, "Documentos fiscales", f"No se pudo generar el documento: {ex}", "error")
            return
        if ruta and os.path.exists(ruta):
            panel["ruta"] = ruta
            panel["res"].setText("✅  Documento generado correctamente."); panel["res"].setVisible(True)
            panel["open"].setVisible(True)
        else:
            _aviso(self, "Documentos fiscales", "No se pudo generar el documento.", "error")

    def _abrir_pdf(self, panel):
        ruta = panel.get("ruta")
        if not ruta:
            return
        try:
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        except Exception as ex:
            logger.error("abrir pdf fiscal: %s", ex)

    def _activar(self):
        if K.activar(id_empresa=None, anio=self.anio):
            _aviso(self, "Contabilidad", tr("contab.activada", default="Contabilidad activada."))
            self._load_plan()

    @staticmethod
    def _fill(tabla, filas, claves):
        tabla.setRowCount(0)
        for f in filas:
            r = tabla.rowCount(); tabla.insertRow(r)
            for c, k in enumerate(claves):
                tabla.setItem(r, c, QTableWidgetItem("" if f.get(k) is None else str(f.get(k))))

    # ── Plan de cuentas ──────────────────────────────────────────────────────
    def _page_plan(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        self.in_plan_buscar = _inp(tr("contab.buscar_cuenta", default="Buscar cuenta…"))
        fila.addWidget(self.in_plan_buscar, 1)
        fila.addWidget(_btn(tr("contab.buscar", default="BUSCAR"), self._load_plan, primary=True))
        ly.addLayout(fila)
        self.tbl_plan = _tabla_c(["Código", "Nombre", "Grupo", "Tipo", "Naturaleza"])
        ly.addWidget(self.tbl_plan, 1)
        return w

    def _load_plan(self):
        filas = K.listar_cuentas(texto=self.in_plan_buscar.text().strip() or None)
        self._fill(self.tbl_plan, filas, ("codigo", "nombre", "grupo", "tipo", "naturaleza"))

    # ── Diario ───────────────────────────────────────────────────────────────
    def _page_diario(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("contab.diario", default="Libro Diario")))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("contab.refrescar", default="REFRESCAR"), self._load_diario))
        ly.addLayout(fila)
        self.tbl_diario = _tabla_c(["Nº", "Fecha", "Concepto", "Origen", "Debe", "Haber", "Estado"])
        ly.addWidget(self.tbl_diario, 1)
        return w

    def _load_diario(self):
        filas = A.listar_diario(anio=self.anio)
        self._fill(self.tbl_diario, filas,
                   ("numero", "fecha", "concepto", "origen", "total_debe", "total_haber", "estado"))

    # ── Mayor ────────────────────────────────────────────────────────────────
    def _page_mayor(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        self.in_mayor_cta = _inp(tr("contab.cuenta", default="Cuenta (p.ej. 700)"))
        self.in_mayor_cta.setFixedWidth(180)
        fila.addWidget(self.in_mayor_cta)
        fila.addWidget(_btn(tr("contab.ver_mayor", default="VER MAYOR"), self._load_mayor, primary=True))
        self.lbl_mayor = QLabel(""); self.lbl_mayor.setStyleSheet(f"color:{_CIAN};")
        fila.addWidget(self.lbl_mayor); fila.addStretch(1)
        ly.addLayout(fila)
        self.tbl_mayor = _tabla_c(["Fecha", "Asiento", "Concepto", "Debe", "Haber", "Saldo"])
        ly.addWidget(self.tbl_mayor, 1)
        return w

    def _load_mayor(self):
        cod = self.in_mayor_cta.text().strip()
        if not cod:
            return
        m = I.mayor(cod, anio=self.anio)
        self._fill(self.tbl_mayor, m["apuntes"], ("fecha", "numero", "descripcion", "debe", "haber", "saldo"))
        self.lbl_mayor.setText(f"{cod} · saldo {m['saldo']}")

    # ── Balances ─────────────────────────────────────────────────────────────
    def _page_balances(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("contab.sumas_saldos", default="Balance de sumas y saldos")))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("contab.refrescar", default="REFRESCAR"), self._load_balances))
        ly.addLayout(fila)
        self.lbl_bal = QLabel(""); self.lbl_bal.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_bal)
        self.tbl_bal = _tabla_c(["Código", "Nombre", "Debe", "Haber", "Saldo"])
        ly.addWidget(self.tbl_bal, 1)
        return w

    def _load_balances(self):
        b = I.balance_sumas_saldos(anio=self.anio)
        self._fill(self.tbl_bal, b["cuentas"], ("codigo", "nombre", "debe", "haber", "saldo"))
        bs = I.balance_situacion(anio=self.anio)
        pyg = I.perdidas_ganancias(anio=self.anio)
        self.lbl_bal.setText(
            f"Σ debe {b['total_debe']} = Σ haber {b['total_haber']} ({'cuadra' if b['cuadra'] else 'DESCUADRE'})  ·  "
            f"Activo {bs['activo']} = Pasivo {bs['pasivo']} + PN {bs['patrimonio_neto']}  ·  "
            f"Resultado {pyg['resultado']}")

    # ── Gastos (entrada directa de suministros/servicios/dietas…) ────────────────
    def _page_gastos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel(tr("contab.gastos_titulo",
                               default="Registro de gastos (suministros, servicios, dietas…)")))
        # Fila 1: tipo · importe · forma de pago · IVA
        f1 = QHBoxLayout()
        self.cmb_gasto_tipo = _combo([(et, cod) for cod, et, _c, _iva in M.TIPOS_GASTO])
        self.cmb_gasto_tipo.setMinimumWidth(240)          # combo cerrado
        self.cmb_gasto_tipo.view().setMinimumWidth(300)   # popup: el global ::item gasta 40px pad+margen
        self._gasto_lleva_iva = {cod: iva for cod, _et, _c, iva in M.TIPOS_GASTO}
        self.in_gasto_importe = _inp(tr("contab.g_importe_ph", default="Importe total €"))
        self.in_gasto_importe.setFixedWidth(150)
        self.cmb_gasto_fp = _combo([("Banco / Tarjeta", "banco"), ("Efectivo", "efectivo"),
                                    ("A crédito", "credito")])
        self.cmb_gasto_fp.setMinimumWidth(150)
        self.cmb_gasto_fp.view().setMinimumWidth(190)
        self.cmb_gasto_iva = _combo([("IVA automático", "auto"), ("21%", "21"), ("10%", "10"),
                                     ("4%", "4"), ("Sin IVA", "no")])
        self.cmb_gasto_iva.setMinimumWidth(150)
        self.cmb_gasto_iva.view().setMinimumWidth(190)
        for et, wd in ((tr("contab.g_tipo", default="Tipo:"), self.cmb_gasto_tipo),
                       (tr("contab.g_importe", default="Importe:"), self.in_gasto_importe),
                       (tr("contab.g_pago", default="Pago:"), self.cmb_gasto_fp),
                       (tr("contab.g_iva", default="IVA:"), self.cmb_gasto_iva)):
            lb = QLabel(et); lb.setStyleSheet(f"color:{_DIM};"); f1.addWidget(lb); f1.addWidget(wd)
        f1.addStretch(1)
        ly.addLayout(f1)
        # Fila 2: concepto · fecha · botón registrar
        f2 = QHBoxLayout()
        self.in_gasto_concepto = _inp(tr("contab.g_concepto_ph", default="Concepto / proveedor (opcional)"))
        # Fecha: mismo selector de calendario neón que Ventas (Fecha Inicio/Fin). Fallback a texto.
        try:
            from PyQt6.QtCore import QDate
            from src.gui.ventas import _date_neon
            self.in_gasto_fecha = _date_neon(QDate.currentDate())
            self.in_gasto_fecha.setMinimumWidth(140)
        except Exception:
            self.in_gasto_fecha = _inp("YYYY-MM-DD"); self.in_gasto_fecha.setFixedWidth(130)
            self.in_gasto_fecha.setText(_dt.date.today().strftime("%Y-%m-%d"))
        lc = QLabel(tr("contab.g_concepto", default="Concepto:")); lc.setStyleSheet(f"color:{_DIM};")
        lf = QLabel(tr("contab.g_fecha", default="Fecha:")); lf.setStyleSheet(f"color:{_DIM};")
        f2.addWidget(lc); f2.addWidget(self.in_gasto_concepto, 1)
        f2.addWidget(lf); f2.addWidget(self.in_gasto_fecha)
        f2.addWidget(_btn(tr("contab.g_registrar", default="REGISTRAR GASTO"), self._registrar_gasto, primary=True))
        ly.addLayout(f2)
        self.cmb_gasto_tipo.currentIndexChanged.connect(self._gasto_tipo_cambiado)
        self.lbl_gasto = QLabel(""); self.lbl_gasto.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_gasto)
        self.tbl_gastos = _tabla_c(["Nº", "Fecha", "Concepto", "Importe", "Estado"])
        ly.addWidget(self.tbl_gastos, 1)
        acc = QHBoxLayout(); acc.addStretch(1)
        acc.addWidget(_btn(tr("contab.g_anular", default="ANULAR SELECCIONADO"), self._anular_gasto, danger=True))
        ly.addLayout(acc)
        self._gastos_cache = []
        return w

    def _gasto_fecha_str(self):
        """Fecha del formulario como 'YYYY-MM-DD', tanto si es calendario (QDateEdit) como texto."""
        w = self.in_gasto_fecha
        try:
            from PyQt6.QtWidgets import QDateEdit
            if isinstance(w, QDateEdit):
                return w.date().toString("yyyy-MM-dd")
        except Exception:
            pass
        return (w.text() or "").strip() or None

    def _gasto_tipo_cambiado(self):
        """Si el tipo de gasto es exento (seguros, comisiones bancarias) preselecciona 'Sin IVA'."""
        cod = self.cmb_gasto_tipo.currentData()
        lleva = self._gasto_lleva_iva.get(cod, True)
        self.cmb_gasto_iva.setCurrentIndex(0 if lleva else 4)   # 0=IVA automático · 4=Sin IVA

    def _registrar_gasto(self):
        tipo = self.cmb_gasto_tipo.currentData()
        try:
            total = float((self.in_gasto_importe.text() or "0").replace(",", ".").strip())
        except ValueError:
            total = 0.0
        if total <= 0:
            _aviso(self, "Gastos", tr("contab.g_importe_invalido", default="Introduce un importe válido."), "warning")
            return
        sel = self.cmb_gasto_iva.currentData()
        con_iva = sel != "no"
        tipo_iva = None if sel in ("auto", "no") else float(sel)
        fecha = self._gasto_fecha_str()
        concepto = (self.in_gasto_concepto.text() or "").strip() or None
        fp = self.cmb_gasto_fp.currentData()
        r = Pg.registrar_gasto(tipo, total, fecha=fecha, forma_pago=fp, concepto=concepto,
                               con_iva=con_iva, tipo_iva=tipo_iva)
        if r:
            self.lbl_gasto.setText(
                tr("contab.g_ok", default="Gasto registrado") + f": asiento nº {r.get('numero')} · {total:.2f} €")
            self.in_gasto_importe.clear(); self.in_gasto_concepto.clear()
            self._load_gastos(); self._load_diario()
        else:
            _aviso(self, "Gastos", tr("contab.g_error",
                                      default="No se pudo registrar (¿contabilidad activada?)."), "warning")

    def _anular_gasto(self):
        row = self.tbl_gastos.currentRow()
        if row < 0 or row >= len(self._gastos_cache):
            _aviso(self, "Gastos", tr("contab.g_selecc", default="Selecciona un gasto en la tabla."), "warning")
            return
        a = self._gastos_cache[row]
        if a.get("estado") != "contabilizado":
            _aviso(self, "Gastos", tr("contab.g_no_anulable",
                                      default="Solo se pueden anular gastos contabilizados."), "warning")
            return
        r = Pg.anular_gasto(a["id"])
        if r:
            self.lbl_gasto.setText(
                tr("contab.g_anulado", default="Gasto anulado (contraasiento nº") + f" {r.get('numero')}).")
            self._load_gastos(); self._load_diario()
        else:
            _aviso(self, "Gastos", tr("contab.g_no_anulado", default="No se pudo anular."), "warning")

    def _load_gastos(self):
        self._gastos_cache = Pg.listar_gastos(anio=self.anio)
        self.tbl_gastos.setRowCount(0)
        for a in self._gastos_cache:
            r = self.tbl_gastos.rowCount(); self.tbl_gastos.insertRow(r)
            vals = [a.get("numero"), a.get("fecha"), a.get("concepto"), a.get("total_debe"), a.get("estado")]
            for c, v in enumerate(vals):
                self.tbl_gastos.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))

    # ── Libros IVA ───────────────────────────────────────────────────────────
    def _page_iva(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("contab.iva_rep", default="REPERCUTIDO"), lambda: self._load_iva("repercutido")))
        fila.addWidget(_btn(tr("contab.iva_sop", default="SOPORTADO"), lambda: self._load_iva("soportado")))
        fila.addWidget(_btn(tr("contab.m303", default="BORRADOR 303"), self._mostrar_303, primary=True))
        fila.addStretch(1)
        ly.addLayout(fila)
        self.lbl_iva = QLabel(""); self.lbl_iva.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_iva)
        self.tbl_iva = _tabla_c(["Fecha", "Asiento", "Ref", "Tipo IVA", "Base", "Cuota"])
        ly.addWidget(self.tbl_iva, 1)
        return w

    def _load_iva(self, tipo="repercutido"):
        lib = IVA.libro_iva(tipo, anio=self.anio)
        self._fill(self.tbl_iva, lib["lineas"], ("fecha", "numero", "ref", "tipo_iva", "base", "cuota"))
        self.lbl_iva.setText(f"{tipo}: base {lib['total_base']} · cuota {lib['total_cuota']}")

    def _mostrar_303(self):
        r = IVA.resumen_303(anio=self.anio)
        _aviso(self, "Borrador modelo 303",
               f"Devengado: {r['iva_devengado_cuota']} · Deducible: {r['iva_deducible_cuota']}\n"
               f"Resultado: {r['resultado']} ({r['sentido']})")

    # ── Cierres ──────────────────────────────────────────────────────────────
    def _page_cierres(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(14)
        ly.addWidget(QLabel(tr("contab.cierres", default="Cierres y posting")))
        ly.addWidget(_btn(tr("contab.procesar", default="PROCESAR POSTING PENDIENTE"), self._procesar, primary=True))
        ly.addWidget(_btn(tr("contab.cerrar_ej", default=f"CERRAR EJERCICIO {self.anio}"), self._cerrar))
        ly.addStretch(1)
        return w

    def _procesar(self):
        res = Pg.procesar_cola()
        _aviso(self, "Contabilidad",
               tr("contab.posting_ok", default="Posting procesado") + f": {res['asientos']} asientos.")
        self._load_diario()

    def _cerrar(self):
        from src.services.contabilidad import cierre as Ci
        usuario = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        r = Ci.cerrar_ejercicio_formal(self.anio, usuario=usuario)
        if r.get("ok"):
            destino = r.get("destino")
            extra = f" Apertura {destino} generada." if r.get("apertura") else ""
            _aviso(self, "Contabilidad",
                   tr("contab.cerrado", default=f"Ejercicio {self.anio} cerrado (regularización + cierre).{extra}"))
        elif r.get("motivo") == "ya_cerrado":
            _aviso(self, "Contabilidad", tr("contab.ya_cerrado", default="El ejercicio ya estaba cerrado."), "warning")
        else:
            _aviso(self, "Contabilidad", tr("contab.no_cerrado", default="No se pudo cerrar."), "warning")
