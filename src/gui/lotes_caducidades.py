"""
Lotes y caducidades (INV.3) — GUI de existencias por lote, alertas de caducidad y
entrada manual de lotes.

Pantalla NUEVA dentro de INVENTARIO (no modifica las existentes). Solo consulta + entrada
manual de lotes (el consumo FEFO ocurre automáticamente en ventas/mermas/inventario).
Multiempresa por contexto activo. Reutiliza helpers de catalogo_gestion.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.db import lotes
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _inp, _tabla)

logger = logging.getLogger("inventario.lotes.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class LotesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Lotes y caducidades")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        tabs.addTab(self._tab_stock(), "Existencias por lote")
        tabs.addTab(self._tab_alertas(), "Alertas de caducidad")
        root.addWidget(tabs)

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    # ── existencias ──
    def _tab_stock(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.in_cod = _inp("Filtrar por código (vacío = todos)"); self.in_cod.setFixedWidth(240)
        f.addWidget(self.in_cod)
        f.addWidget(_btn("Buscar", self._buscar, primary=True))
        f.addWidget(_btn("Entrada de lote", self._entrada))
        f.addStretch()
        ly.addLayout(f)
        self.tabla = _tabla(["Artículo", "Lote", "Caducidad", "Cantidad", "Origen", "Estado"])
        ly.addWidget(self.tabla)
        self._buscar()
        return w

    def _buscar(self):
        cod = self.in_cod.text().strip() or None
        data = lotes.listar_lotes(id_empresa=self._id_empresa(), codigo=cod)
        self.tabla.setRowCount(len(data))
        for i, l in enumerate(data):
            for j, v in enumerate([l.get("codigo_articulo"), l.get("lote"),
                                   l.get("fecha_caducidad"), l.get("cantidad"),
                                   l.get("origen"), l.get("estado")]):
                self.tabla.setItem(i, j, _it(v))

    def _entrada(self):
        cod, ok = QInputDialog.getText(self, "Entrada de lote", "Código de artículo:")
        if not ok or not cod.strip():
            return
        lote, ok = QInputDialog.getText(self, "Entrada de lote", "Identificador de lote:")
        if not ok or not lote.strip():
            return
        cant, ok = QInputDialog.getInt(self, "Entrada de lote", "Cantidad:", 1, 1)
        if not ok:
            return
        cad, ok = QInputDialog.getText(self, "Entrada de lote",
                                       "Caducidad AAAA-MM-DD (vacío = sin caducidad):")
        if not ok:
            return
        # INV.7.3: selector de almacén destino (opcional).
        id_almacen = None
        try:
            from src.db import stock_almacen as SA
            alms = SA.listar_almacenes(self._id_empresa())
            if alms:
                etqs = ["(sin almacén)"] + [f"{a['nombre']} [{a['tipo_almacen']}]" for a in alms]
                etq, ok2 = QInputDialog.getItem(self, "Entrada de lote", "Almacén:", etqs, 0, False)
                if ok2 and etq != "(sin almacén)":
                    id_almacen = alms[etqs.index(etq) - 1]["id"]
        except Exception:
            pass
        rid = lotes.registrar_entrada(cod.strip(), lote.strip(), cant,
                                      fecha_caducidad=cad.strip() or None,
                                      id_empresa=self._id_empresa(), origen="manual",
                                      usuario=(self.usuario or {}).get("nombre"),
                                      id_almacen=id_almacen)
        if rid:
            self._buscar()
        else:
            QMessageBox.warning(self, "Lotes", "No se pudo registrar la entrada de lote.")

    # ── alertas ──
    def _tab_alertas(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.in_dias = _inp("Días (def. 30)"); self.in_dias.setFixedWidth(110)
        f.addWidget(QLabel("Próximas a caducar en:")); f.addWidget(self.in_dias)
        f.addWidget(_btn("Actualizar", self._alertas, primary=True))
        f.addStretch()
        ly.addLayout(f)
        for lab in w.findChildren(QLabel):
            lab.setStyleSheet(f"color:{_DIM};")
        self.lbl_caducados = QLabel(""); self.lbl_caducados.setStyleSheet(f"color:{_TEXT};")
        ly.addWidget(self.lbl_caducados)
        self.tabla_al = _tabla(["Artículo", "Lote", "Caducidad", "Cantidad", "Estado"])
        ly.addWidget(self.tabla_al)
        self._alertas()
        return w

    def _alertas(self):
        try:
            dias = int(self.in_dias.text().strip() or 30)
        except ValueError:
            dias = 30
        emp = self._id_empresa()
        proximos = lotes.lotes_por_caducar(dias, id_empresa=emp)
        caducados = lotes.lotes_caducados(id_empresa=emp)
        self.lbl_caducados.setText(f"⚠ {len(caducados)} lote(s) ya caducado(s) con existencias")
        filas = ([("CADUCADO", l) for l in caducados] +
                 [("Próximo", l) for l in proximos])
        self.tabla_al.setRowCount(len(filas))
        for i, (estado, l) in enumerate(filas):
            for j, v in enumerate([l.get("codigo_articulo"), l.get("lote"),
                                   l.get("fecha_caducidad"), l.get("cantidad"), estado]):
                self.tabla_al.setItem(i, j, _it(v))
