"""
Modelos AEAT — interfaz (FASE AEAT-1).

Pantalla NUEVA (no modifica las existentes). En esta fase cubre el Modelo 303: selección de
ejercicio/periodo, generación (borrador por casillas + PDF), consulta y exportación JSON/CSV.
Estilo coherente con el ERP (dark + cian). Acotada a la empresa activa.
"""

import datetime as _dt
import logging
import os

from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _combo, _inp, _tabla
from src.services.aeat import base as _B
from src.services.aeat import exportacion as _X
from src.services.aeat import modelo_303 as _M303
from src.services.aeat import modelo_390 as _M390
from src.services.aeat import modelo_111 as _M111
from src.services.aeat import modelo_190 as _M190
from src.services.aeat import modelo_347 as _M347
from src.services.aeat import modelo_349 as _M349

logger = logging.getLogger("aeat.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class AEATWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._sel_id = None
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Modelos AEAT · IVA (303/390) · Retenciones (111/190) · Terceros (347) · Intracom (349)")
        t.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        bar = QHBoxLayout()
        self.cmb_modelo = _combo([("303", "303"), ("390", "390"), ("111", "111"),
                                  ("190", "190"), ("347", "347"), ("349", "349")])
        self.cmb_modelo.currentIndexChanged.connect(self._sync_modelo)
        self.in_ej = _inp("Ejercicio"); self.in_ej.setFixedWidth(90)
        self.in_ej.setText(str(_dt.date.today().year))
        self.cmb_per = _combo([(p, p) for p in _M303.periodos_validos()])
        bar.addWidget(QLabel("Modelo:")); bar.addWidget(self.cmb_modelo)
        bar.addWidget(QLabel("Ejercicio:")); bar.addWidget(self.in_ej)
        bar.addWidget(QLabel("Periodo:")); bar.addWidget(self.cmb_per)
        bar.addWidget(_btn("Generar", self._generar, primary=True))
        bar.addWidget(_btn("Ver", self._ver))
        bar.addWidget(_btn("Exportar JSON", lambda: self._exportar("json")))
        bar.addWidget(_btn("Exportar CSV", lambda: self._exportar("csv")))
        bar.addStretch()
        root.addLayout(bar)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_CIAN};font-size:14px;")
        root.addWidget(self.lbl)

        cuerpo = QHBoxLayout()
        self.tbl_decl = _tabla(["ID", "Modelo", "Ejercicio", "Periodo", "Estado", "Resultado"])
        self.tbl_decl.cellClicked.connect(self._sel_decl)
        cuerpo.addWidget(self.tbl_decl, 1)
        self.tbl_cas = _tabla(["Casilla", "Descripción", "Importe"])
        cuerpo.addWidget(self.tbl_cas, 1)
        root.addLayout(cuerpo)

        self._load_decl()

    def _sync_modelo(self):
        """390 y 190 son anuales: fuerzan periodo 0A y deshabilitan el selector de periodo."""
        es_anual = self.cmb_modelo.currentData() in ("390", "190", "347", "349")
        self.cmb_per.setEnabled(not es_anual)
        if es_anual:
            i = self.cmb_per.findData("0A")
            if i >= 0:
                self.cmb_per.setCurrentIndex(i)

    def _load_decl(self):
        try:
            filas = _B.listar_declaraciones(id_empresa=_empresa())
            self.tbl_decl.setRowCount(len(filas))
            for i, d in enumerate(filas):
                for j, v in enumerate([d["id"], d["modelo"], d["ejercicio"], d["periodo"],
                                       d["estado"], f"{float(d['resultado']):.2f}"]):
                    self.tbl_decl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load_decl: %s", e)

    def _generar(self):
        try:
            ej = int(self.in_ej.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "AEAT", "Ejercicio inválido"); return
        modelo = self.cmb_modelo.currentData()
        per = "0A" if modelo in ("390", "190", "347", "349") else self.cmb_per.currentData()
        try:
            if modelo == "390":
                res = _M390.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "349":
                res = _M349.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "347":
                res = _M347.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "190":
                res = _M190.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "111":
                res = _M111.generar(ej, per, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            else:
                res = _M303.generar(ej, per, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            if not res.get("ok"):
                QMessageBox.warning(self, "AEAT", res.get("errores", "No se pudo generar")); return
            self._sel_id = res["id"]
            self.lbl.setText(f"{modelo} {ej}/{per} generado · Resultado: {res['resultado']:.2f} € "
                             f"({res['sentido']}){'  · PDF ✔' if res.get('pdf') else ''}")
            self._load_decl(); self._mostrar_casillas(res["casillas"])
        except Exception as e:
            QMessageBox.warning(self, "AEAT", str(e))

    def _sel_decl(self, row, _col):
        try:
            self._sel_id = int(self.tbl_decl.item(row, 0).text())
        except Exception:
            self._sel_id = None

    def _ver(self):
        if not self._sel_id:
            QMessageBox.information(self, "AEAT", "Selecciona o genera una declaración."); return
        d = _B.obtener_declaracion(self._sel_id, id_empresa=_empresa())
        if d:
            self.lbl.setText(f"303 {d['ejercicio']}/{d['periodo']} [{d['estado']}] · "
                             f"Resultado: {float(d['resultado']):.2f} €")
            self._mostrar_casillas(d.get("casillas", []))

    def _mostrar_casillas(self, casillas):
        self.tbl_cas.setRowCount(len(casillas))
        for i, c in enumerate(casillas):
            for j, v in enumerate([c["casilla"], c.get("descripcion"), f"{float(c['importe']):.2f}"]):
                self.tbl_cas.setItem(i, j, _it(v))

    def _exportar(self, fmt):
        if not self._sel_id:
            QMessageBox.information(self, "AEAT", "Selecciona o genera una declaración."); return
        d = _B.obtener_declaracion(self._sel_id, id_empresa=_empresa())
        if not d:
            return
        contenido = _X.a_json(d) if fmt == "json" else _X.a_csv(d)
        sugerido = f"303_{d['ejercicio']}_{d['periodo']}.{fmt}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar", sugerido,
                                              f"{fmt.upper()} (*.{fmt})")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                QMessageBox.information(self, "AEAT", f"Exportado a {os.path.basename(ruta)}")
            except Exception as e:
                QMessageBox.warning(self, "AEAT", str(e))
