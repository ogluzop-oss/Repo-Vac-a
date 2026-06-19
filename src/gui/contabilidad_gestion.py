"""
Ventana de CONTABILIDAD (E6.7) — expone el motor contable en la interfaz principal.

Reutiliza los patrones visuales de `catalogo_gestion`/`compras_gestion` (sidebar `sw`
+ QStackedWidget + helpers _btn/_inp/_tabla/_combo + estilo global). Solo presentación;
la lógica vive en `src.services.contabilidad.*` (ya probada en E6.1-E6.6).
"""

from __future__ import annotations

import datetime as _dt
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _btn, _inp, _tabla)
from src.services.contabilidad import asientos as A
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import informes as I
from src.services.contabilidad import iva as IVA
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


class ContabilidadWindow(QWidget):
    _SECCIONES = [
        ("plan", "📒", "Plan de cuentas"),
        ("diario", "📓", "Diario"),
        ("mayor", "📚", "Mayor"),
        ("balances", "⚖️", "Balances"),
        ("iva", "🧾", "Libros IVA"),
        ("cierres", "🔒", "Cierres"),
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
        self.stack.addWidget(self._page_iva())
        self.stack.addWidget(self._page_cierres())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self._ir(0)

    # ── Cabecera / sidebar ───────────────────────────────────────────────────
    def _header(self):
        cab = QHBoxLayout()
        t = QLabel("📊  " + tr("contab.titulo", default="CONTABILIDAD"))
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch(1)
        if not K.contabilidad_activa():
            cab.addWidget(_btn(tr("contab.activar", default="ACTIVAR CONTABILIDAD"),
                               self._activar, primary=True))
        if self._volver:
            cab.addWidget(_btn(tr("contab.volver", default="VOLVER AL MENÚ"), self._volver_menu, primary=True))
        return cab

    def _sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230)
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("contab.secciones", default="CONTABILIDAD"))
        cab.setStyleSheet(f"color:{_DIM};padding:0 0 8px 24px;font-size:11px;font-weight:bold;")
        lay.addWidget(cab)
        self._sb = []
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"  {icono}   {tr('contab.sec_' + sid, default=defecto)}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb.append(b); lay.addWidget(b)
        lay.addStretch(1)
        return wrap

    _ON = (f"QPushButton{{background:{_CIAN};color:{_BG};text-align:left;padding:8px 8px 8px 24px;"
           f"border:none;font-size:13px;font-weight:bold;}}")
    _OFF = (f"QPushButton{{background:transparent;color:{_DIM};text-align:left;padding:8px 8px 8px 24px;"
            f"border:none;font-size:13px;}}QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")

    def _ir(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb):
            b.setStyleSheet(self._ON if i == idx else self._OFF)
        [self._load_plan, self._load_diario, lambda: None, self._load_balances,
         self._load_iva, lambda: None][idx]()

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

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
        self.tbl_plan = _tabla(["Código", "Nombre", "Grupo", "Tipo", "Naturaleza"])
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
        self.tbl_diario = _tabla(["Nº", "Fecha", "Concepto", "Origen", "Debe", "Haber", "Estado"])
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
        self.tbl_mayor = _tabla(["Fecha", "Asiento", "Concepto", "Debe", "Haber", "Saldo"])
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
        self.tbl_bal = _tabla(["Código", "Nombre", "Debe", "Haber", "Saldo"])
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
        self.tbl_iva = _tabla(["Fecha", "Asiento", "Ref", "Tipo IVA", "Base", "Cuota"])
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
        if K.cerrar_ejercicio(self.anio):
            _aviso(self, "Contabilidad", tr("contab.cerrado", default=f"Ejercicio {self.anio} cerrado."))
        else:
            _aviso(self, "Contabilidad", tr("contab.no_cerrado", default="No se pudo cerrar."), "warning")
