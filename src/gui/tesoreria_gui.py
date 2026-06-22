"""
Tesorería — interfaz unificada (rama Tesorería, FASE 12).

Pantalla NUEVA (no modifica las existentes) con 8 paneles en pestañas, coherentes con el
estilo del ERP (dark + cian): Posición, Cuentas, Movimientos, Vencimientos, Conciliación,
Remesas SEPA, Cash Flow y Previsión. Siempre acotada a la empresa activa. Reutiliza los
servicios de las FASES 1-11. Las consultas son best-effort: un fallo de datos no rompe la UI.
"""

import datetime as _dt
import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.db import tesoreria as _T
from src.db import vencimientos as _V
from src.db import sepa as _S
from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _combo, _inp, _tabla
from src.services.tesoreria import cashflow as _CF
from src.services.tesoreria import conciliacion as _CC
from src.services.tesoreria import posicion as _POS
from src.services.tesoreria import prevision_financiera as _PF
from src.services.tesoreria import sepa as _SEPA

logger = logging.getLogger("tesoreria.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class TesoreriaWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Tesorería · Bancos · SEPA")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self.refrescar))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabBar::tab{{background:{_BG};color:{_DIM};padding:8px 16px;}}"
                                f"QTabBar::tab:selected{{color:{_CIAN};}}")
        root.addWidget(self.tabs)

        self._tab_posicion()
        self._tab_cuentas()
        self._tab_movimientos()
        self._tab_vencimientos()
        self._tab_conciliacion()
        self._tab_remesas()
        self._tab_cashflow()
        self._tab_prevision()

    # ── Posición ──────────────────────────────────────────────────────────────
    def _tab_posicion(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.lbl_pos = QLabel(""); self.lbl_pos.setStyleSheet(f"color:{_CIAN};font-size:15px;")
        lay.addWidget(self.lbl_pos)
        self.tbl_pos = _tabla(["Cuenta", "Tienda", "Moneda", "Saldo"])
        lay.addWidget(self.tbl_pos)
        self.tabs.addTab(w, "Posición")
        self._load_posicion()

    def _load_posicion(self):
        try:
            p = _POS.posicion(_empresa(), horizonte_dias=90)
            self.lbl_pos.setText(
                f"Disponible: {p['disponible']:.2f} €   |   Por cobrar: {p['por_cobrar']:.2f} €   "
                f"|   Comprometido: {p['comprometido']:.2f} €   |   Previsto: {p['previsto']:.2f} €   "
                f"|   Futuro 90d: {p.get('futuro', 0):.2f} €")
            cuentas = p.get("por_cuenta", [])
            self.tbl_pos.setRowCount(len(cuentas))
            for i, c in enumerate(cuentas):
                for j, v in enumerate([c["nombre_cuenta"], c.get("id_tienda"), c.get("moneda"),
                                       f"{c['saldo']:.2f}"]):
                    self.tbl_pos.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("posicion: %s", e)

    # ── Cuentas ───────────────────────────────────────────────────────────────
    def _tab_cuentas(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Nueva cuenta", self._nueva_cuenta, primary=True))
        bar.addStretch(); lay.addLayout(bar)
        self.tbl_cuentas = _tabla(["ID", "Cuenta", "Titular", "IBAN", "BIC", "Entidad", "Moneda", "Saldo"])
        lay.addWidget(self.tbl_cuentas)
        self.tabs.addTab(w, "Cuentas")
        self._load_cuentas()

    def _load_cuentas(self):
        try:
            filas = _T.listar_cuentas(id_empresa=_empresa())
            self.tbl_cuentas.setRowCount(len(filas))
            for i, c in enumerate(filas):
                vals = [c["id"], c["nombre_cuenta"], c.get("titular"), c.get("iban"),
                        c.get("bic"), c.get("entidad"), c.get("moneda"),
                        f"{_T.saldo_cuenta(c['id'], _empresa()):.2f}"]
                for j, v in enumerate(vals):
                    self.tbl_cuentas.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("cuentas: %s", e)

    def _nueva_cuenta(self):
        nombre, ok = QInputDialog.getText(self, "Nueva cuenta", "Nombre de la cuenta:")
        if not ok or not nombre:
            return
        iban, ok = QInputDialog.getText(self, "Nueva cuenta", "IBAN:")
        if not ok:
            return
        try:
            _T.crear_cuenta(nombre, iban, usuario=self.usuario.get("nombre"), id_empresa=_empresa())
            self._load_cuentas(); self._load_posicion()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Movimientos ───────────────────────────────────────────────────────────
    def _tab_movimientos(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.tbl_mov = _tabla(["Fecha", "Tipo", "Concepto", "Importe", "Saldo", "Origen", "Doc."])
        lay.addWidget(self.tbl_mov)
        self.tabs.addTab(w, "Movimientos")
        self._load_movimientos()

    def _load_movimientos(self):
        try:
            filas = _T.listar_movimientos(id_empresa=_empresa(), limite=500)
            self.tbl_mov.setRowCount(len(filas))
            for i, m in enumerate(filas):
                vals = [m["fecha"], m["tipo"], m.get("concepto"), f"{float(m['importe']):.2f}",
                        ("" if m.get("saldo_resultante") is None else f"{float(m['saldo_resultante']):.2f}"),
                        m.get("origen"), m.get("id_documento")]
                for j, v in enumerate(vals):
                    self.tbl_mov.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("movimientos: %s", e)

    # ── Vencimientos ──────────────────────────────────────────────────────────
    def _tab_vencimientos(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Marcar vencidos", self._marcar_vencidos))
        bar.addStretch(); lay.addLayout(bar)
        self.tbl_venc = _tabla(["ID", "Tipo", "Vence", "Importe", "Pendiente", "Estado", "Tercero", "Origen"])
        lay.addWidget(self.tbl_venc)
        self.tabs.addTab(w, "Vencimientos")
        self._load_vencimientos()

    def _load_vencimientos(self):
        try:
            filas = _V.listar_vencimientos(id_empresa=_empresa())
            self.tbl_venc.setRowCount(len(filas))
            for i, v in enumerate(filas):
                vals = [v["id"], v["tipo"], v["fecha_vencimiento"], f"{float(v['importe']):.2f}",
                        f"{float(v['pendiente']):.2f}", v["estado"], v.get("tercero"), v.get("origen")]
                for j, val in enumerate(vals):
                    self.tbl_venc.setItem(i, j, _it(val))
        except Exception as e:
            logger.error("vencimientos: %s", e)

    def _marcar_vencidos(self):
        try:
            n = _V.marcar_vencidos(_empresa())
            QMessageBox.information(self, "Vencimientos", f"{n} vencimiento(s) marcados como VENCIDO.")
            self._load_vencimientos()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Conciliación ──────────────────────────────────────────────────────────
    def _tab_conciliacion(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.in_extracto = _inp("ID extracto"); self.in_extracto.setFixedWidth(120)
        bar.addWidget(QLabel("Extracto:")); bar.addWidget(self.in_extracto)
        bar.addWidget(_btn("Conciliar automático", self._conciliar_auto, primary=True))
        bar.addStretch(); lay.addLayout(bar)
        self.lbl_conc = QLabel(""); self.lbl_conc.setStyleSheet(f"color:{_DIM};")
        lay.addWidget(self.lbl_conc)
        self.tbl_conc = _tabla(["Línea", "Fecha", "Importe", "Concepto", "Conciliado"])
        lay.addWidget(self.tbl_conc)
        self.tabs.addTab(w, "Conciliación")

    def _conciliar_auto(self):
        try:
            eid = int(self.in_extracto.text() or 0)
        except ValueError:
            return
        try:
            r = _CC.conciliar_automatico(eid, id_empresa=_empresa())
            self.lbl_conc.setText(f"Conciliadas: {r['conciliadas']}  Ambiguas: {r['ambiguas']}  "
                                  f"Sin match: {r['sin_match']}")
            difs = _CC.diferencias(eid, id_empresa=_empresa())
            self.tbl_conc.setRowCount(len(difs))
            for i, d in enumerate(difs):
                for j, v in enumerate([d["id"], d["fecha"], f"{float(d['importe']):.2f}",
                                       d.get("concepto"), "No"]):
                    self.tbl_conc.setItem(i, j, _it(v))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Remesas SEPA ──────────────────────────────────────────────────────────
    def _tab_remesas(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.in_remesa = _inp("ID remesa"); self.in_remesa.setFixedWidth(120)
        bar.addWidget(QLabel("Remesa:")); bar.addWidget(self.in_remesa)
        bar.addWidget(_btn("Generar XML", self._generar_remesa, primary=True))
        bar.addStretch(); lay.addLayout(bar)
        self.tbl_rem = _tabla(["ID", "Tipo", "Estado", "Operaciones", "Importe", "Mensaje"])
        lay.addWidget(self.tbl_rem)
        self.tabs.addTab(w, "Remesas SEPA")
        self._load_remesas()

    def _load_remesas(self):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, tipo, estado, num_operaciones, importe_total, mensaje_id "
                            "FROM remesas_sepa WHERE id_empresa=%s ORDER BY id DESC LIMIT 200", (_empresa(),))
                filas = [r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
                         for r in cur.fetchall()]
            self.tbl_rem.setRowCount(len(filas))
            for i, r in enumerate(filas):
                vals = [r["id"], r["tipo"], r["estado"], r["num_operaciones"],
                        f"{float(r['importe_total']):.2f}", r.get("mensaje_id")]
                for j, v in enumerate(vals):
                    self.tbl_rem.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("remesas: %s", e)

    def _generar_remesa(self):
        try:
            rid = int(self.in_remesa.text() or 0)
        except ValueError:
            return
        try:
            res = _SEPA.generar_xml(rid, id_empresa=_empresa())
            if res.get("ok"):
                QMessageBox.information(self, "SEPA", f"XML generado y validado (XSD).\n"
                                       f"Mensaje: {res['mensaje_id']}")
            else:
                QMessageBox.warning(self, "SEPA", f"No válido: {res.get('errores')}")
            self._load_remesas()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    def _tab_cashflow(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.cmb_gran = _combo([("Mensual", "mensual"), ("Semanal", "semanal"),
                                ("Diario", "diario"), ("Anual", "anual")])
        self.cmb_esc = _combo([("Real", "real"), ("Previsto", "previsto")])
        bar.addWidget(QLabel("Granularidad:")); bar.addWidget(self.cmb_gran)
        bar.addWidget(QLabel("Escenario:")); bar.addWidget(self.cmb_esc)
        bar.addWidget(_btn("Calcular", self._load_cashflow, primary=True))
        bar.addStretch(); lay.addLayout(bar)
        self.tbl_cf = _tabla(["Periodo", "Entradas", "Salidas", "Neto", "Acumulado"])
        lay.addWidget(self.tbl_cf)
        self.tabs.addTab(w, "Cash Flow")
        self._load_cashflow()

    def _load_cashflow(self):
        try:
            gran = self.cmb_gran.currentData() or "mensual"
            esc = self.cmb_esc.currentData() or "real"
            anio = _dt.date.today().year
            filas = _CF.flujo(_empresa(), desde=f"{anio}-01-01", hasta=f"{anio}-12-31",
                              granularidad=gran, escenario=esc)
            self.tbl_cf.setRowCount(len(filas))
            for i, f in enumerate(filas):
                for j, v in enumerate([f["periodo"], f"{f['entradas']:.2f}", f"{f['salidas']:.2f}",
                                       f"{f['neto']:.2f}", f"{f['acumulado']:.2f}"]):
                    self.tbl_cf.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("cashflow: %s", e)

    # ── Previsión ─────────────────────────────────────────────────────────────
    def _tab_prevision(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.tbl_prev = _tabla(["Horizonte", "Fecha", "Por cobrar", "Comprometido",
                                "Operativo est.", "Liquidez est.", "Tensión"])
        lay.addWidget(self.tbl_prev)
        self.tabs.addTab(w, "Previsión")
        self._load_prevision()

    def _load_prevision(self):
        try:
            proy = _PF.proyeccion_liquidez(_empresa())
            ps = proy["proyecciones"]
            self.tbl_prev.setRowCount(len(ps))
            for i, p in enumerate(ps):
                vals = [f"{p['horizonte_dias']} d", p["fecha"], f"{p['por_cobrar']:.2f}",
                        f"{p['comprometido']:.2f}", f"{p['flujo_operativo_estimado']:.2f}",
                        f"{p['liquidez_estimada']:.2f}", "⚠️" if p["tension"] else "OK"]
                for j, v in enumerate(vals):
                    self.tbl_prev.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("prevision: %s", e)

    # ── Refresco global ───────────────────────────────────────────────────────
    def refrescar(self):
        for fn in (self._load_posicion, self._load_cuentas, self._load_movimientos,
                   self._load_vencimientos, self._load_remesas, self._load_cashflow,
                   self._load_prevision):
            try:
                fn()
            except Exception as e:
                logger.debug("refrescar: %s", e)
