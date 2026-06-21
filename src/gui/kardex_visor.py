"""
Visor de Kárdex (INV.1) — consulta de movimientos de stock.

Pantalla NUEVA (no modifica las existentes). Filtra por artículo, referencia, tipo,
fechas y tienda; muestra el historial cronológico con trazabilidad completa. Multiempresa:
siempre acotado a la empresa activa. Solo lectura.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.db import kardex
from src.gui.catalogo_gestion import (_BG, _BORDE, _CIAN, _DIM, _TEXT, _btn,
                                      _combo, _inp, _tabla)

logger = logging.getLogger("inventario.kardex.gui")

_COLS = ["Fecha", "Artículo", "Movimiento", "Cantidad", "Origen", "Destino",
         "Documento", "Usuario"]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class KardexVisorWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Kárdex · Movimientos de stock")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        # ── filtros ──
        f = QHBoxLayout()
        self.f_codigo = _inp("Artículo (código)"); self.f_codigo.setFixedWidth(150)
        self.f_ref = _inp("Referencia / documento"); self.f_ref.setFixedWidth(160)
        self.f_tipo = _combo([("(todos)", None)] + [(t, t) for t in kardex.TIPOS])
        self.f_desde = _inp("Desde AAAA-MM-DD"); self.f_desde.setFixedWidth(130)
        self.f_hasta = _inp("Hasta AAAA-MM-DD"); self.f_hasta.setFixedWidth(130)
        self.f_tienda = _combo(self._tiendas())
        self.f_almacen = _combo(self._almacenes())
        for w in (QLabel("Artículo:"), self.f_codigo, QLabel("Ref:"), self.f_ref,
                  QLabel("Tipo:"), self.f_tipo, QLabel("Tienda:"), self.f_tienda,
                  QLabel("Almacén:"), self.f_almacen,
                  self.f_desde, self.f_hasta):
            if isinstance(w, QLabel):
                w.setStyleSheet(f"color:{_DIM};")
            f.addWidget(w)
        f.addWidget(_btn("Buscar", self._buscar, primary=True))
        f.addStretch()
        root.addLayout(f)

        self.lbl_total = QLabel(""); self.lbl_total.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl_total)

        self.tabla = _tabla(_COLS)
        root.addWidget(self.tabla)
        self._buscar()

    # ── datos ──
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _tiendas(self):
        opts = [("(todas)", None)]
        try:
            from src.db import tiendas
            for tnd in tiendas.listar_tiendas(self._id_empresa()):
                etq = (f"{tnd.get('codigo_tienda') or ''} {tnd.get('nombre') or ''}".strip()
                       or str(tnd.get("id")))
                opts.append((etq, tnd.get("id")))
        except Exception as e:
            logger.warning("listar tiendas: %s", e)
        return opts

    def _almacenes(self):
        opts = [("(todos)", None)]
        try:
            from src.db import stock_almacen as SA
            for a in SA.listar_almacenes(self._id_empresa()):
                opts.append((f"{a.get('nombre')} [{a.get('tipo_almacen')}]", a.get("id")))
        except Exception as e:
            logger.warning("listar almacenes: %s", e)
        return opts

    def _buscar(self):
        movs = kardex.listar_movimientos(
            id_empresa=self._id_empresa(),
            codigo=self.f_codigo.text().strip() or None,
            referencia=self.f_ref.text().strip() or None,
            tipo=self.f_tipo.currentData(),
            desde=self.f_desde.text().strip() or None,
            hasta=self.f_hasta.text().strip() or None,
            id_tienda=self.f_tienda.currentData(),
            id_almacen=self.f_almacen.currentData())
        self.tabla.setRowCount(len(movs))
        for i, m in enumerate(movs):
            for j, v in enumerate([
                    m.get("fecha_movimiento"), m.get("codigo_articulo"),
                    m.get("tipo_movimiento"), m.get("cantidad"), m.get("origen"),
                    m.get("destino"), m.get("id_documento") or m.get("id_pale"),
                    m.get("usuario")]):
                self.tabla.setItem(i, j, _it(v))
        self.lbl_total.setText(f"{len(movs)} movimiento(s)")
