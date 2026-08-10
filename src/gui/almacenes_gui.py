"""
Gestión de almacenes (INV.7.1) — GUI CRUD sobre la tabla `almacen`.

Pantalla NUEVA dentro de INVENTARIO. Alta/edición/activación/baja lógica de almacenes
(nombre, código, tipo, tienda asociada, estado). No elimina físicamente (conserva
existencias e histórico). Multiempresa por contexto activo.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import stock_almacen as SA
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_x, _combo, _inp, _tabla)
from src.gui.foundation import tokens as T

logger = logging.getLogger("inventario.almacenes.gui")

_TIPOS = ["central", "regional", "logistico", "tienda", "temporal"]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class AlmacenesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")

        # La ventana se convierte en ANFITRIONA con pestañas (reutilizando su acceso de menú): la
        # primera pestaña es la gestión de almacenes actual; se añaden MRP/Fabricación y GMAO como
        # operaciones físicas del dominio, reutilizando sus dashboards sin duplicarlos.
        _outer = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Almacenes · Operaciones")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        _outer.addLayout(cab)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())
        _outer.addWidget(self.tabs)

        _pagina = QWidget()
        root = QVBoxLayout(_pagina)

        # alta
        f = QHBoxLayout()
        self.in_nombre = _inp("Nombre"); self.in_codigo = _inp("Código"); self.in_codigo.setFixedWidth(120)
        self.cmb_tipo = _combo([(t, t) for t in _TIPOS])
        self.cmb_tipo.setMinimumWidth(150)   # evita texto cortado en el desplegable
        f.addWidget(QLabel("Nombre:")); f.addWidget(self.in_nombre)
        f.addWidget(QLabel("Código:")); f.addWidget(self.in_codigo)
        f.addWidget(QLabel("Tipo:")); f.addWidget(self.cmb_tipo)
        f.addWidget(_btn("Crear", self._crear, primary=True))
        for w in (f.itemAt(i).widget() for i in range(f.count())):
            if isinstance(w, QLabel):
                w.setStyleSheet(f"color:{_DIM};")
        root.addLayout(f)

        self.tabla = _tabla(["id", "Nombre", "Código", "Tipo", "Tienda", "Estado", "Activo"])
        root.addWidget(self.tabla)

        acc = QHBoxLayout()
        acc.addWidget(_btn("Renombrar", self._renombrar))
        acc.addWidget(_btn("Activar", lambda: self._activar(True)))
        acc.addWidget(_btn("Desactivar", lambda: self._activar(False), danger=True))
        acc.addStretch()
        root.addLayout(acc)

        # Primera pestaña: gestión de almacenes (contenido original). Luego los dominios de operaciones.
        self.tabs.addTab(_pagina, "Almacenes")
        # La pestaña MRP / Fabricación (industrial) se adapta a la EDICIÓN: en Bakery se sustituye por el Obrador,
        # así que no se muestra aquí (gate por `verticales`). En el resto se muestra salvo que la matriz lo oculte.
        try:
            from src.services import verticales as _vert
            _mrp_visible = _vert.visible("almacenes.mrp")
        except Exception:
            _mrp_visible = True
        if _mrp_visible:
            try:
                from src.gui.mrp_dashboard import MRPDashboardWindow
                self.tabs.addTab(MRPDashboardWindow(callback_vuelta=None, usuario=self.usuario, main=main),
                                 "MRP / Fabricación")
            except Exception as e:
                logger.debug("tab MRP: %s", e)
        try:
            from src.gui.gmao_dashboard import GMAODashboardWindow
            self.tabs.addTab(GMAODashboardWindow(callback_vuelta=None, usuario=self.usuario, main=main),
                             "GMAO / Mantenimiento")
        except Exception as e:
            logger.debug("tab GMAO: %s", e)
        self._tab_slotting()
        self._cargar()

    # ── Slotting inteligente + rutas de picking (WMS, sin coste externo) ───────
    def _tab_slotting(self):
        w = QWidget(); ly = QVBoxLayout(w)
        ly.addWidget(QLabel("Slotting inteligente — coloca los productos de más rotación en las "
                            "ubicaciones más accesibles"))
        bar = QHBoxLayout()
        bar.addWidget(_btn("🔎 Analizar", self._slotting_analizar, primary=True))
        bar.addWidget(_btn("↔ Aplicar intercambio", self._slotting_aplicar))
        bar.addStretch()
        self.lbl_abc = QLabel(""); self.lbl_abc.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        bar.addWidget(self.lbl_abc)
        ly.addLayout(bar)
        self.tbl_slot = _tabla(["Producto", "Clase", "Rotación", "Ubicación actual",
                                "→ Intercambiar con", "Ubicación sugerida"])
        ly.addWidget(self.tbl_slot)
        ly.addWidget(QLabel("Ruta óptima de picking (recorrido serpentín)"))
        bar2 = QHBoxLayout()
        self.cmb_pick = _combo([]); self.cmb_pick.setMinimumWidth(240)
        bar2.addWidget(QLabel("Picking:")); bar2.addWidget(self.cmb_pick)
        bar2.addWidget(_btn("🧭 Ver ruta óptima", self._ruta_picking, primary=True)); bar2.addStretch()
        ly.addLayout(bar2)
        self.tbl_ruta = _tabla(["Orden", "Producto", "Cantidad", "Ubicación", "Pasillo"])
        ly.addWidget(self.tbl_ruta)
        self.tabs.addTab(w, "Slotting / Rutas")
        self._cargar_pickings()

    def _slotting_analizar(self):
        from src.services.inventario import slotting as SL
        r = SL.analizar(self._id_empresa())
        a = r["abc"]
        self.lbl_abc.setText(f"ABC → A:{a['A']}  B:{a['B']}  C:{a['C']}   ·   {r['ubicaciones']} ubicaciones")
        self._recs = r["recomendaciones"]
        self.tbl_slot.setRowCount(len(self._recs))
        for i, rec in enumerate(self._recs):
            vals = [rec["codigo"], rec["clase"], f"{rec['rotacion']:.0f}", rec["ubicacion_actual"],
                    rec["codigo_intercambio"], rec["ubicacion_sugerida"]]
            for j, v in enumerate(vals):
                self.tbl_slot.setItem(i, j, _it(v))
        if not self._recs:
            self.lbl_abc.setText(self.lbl_abc.text() + "   ·   Sin mejoras de colocación.")

    def _slotting_aplicar(self):
        row = self.tbl_slot.currentRow()
        recs = getattr(self, "_recs", None)
        if row < 0 or not recs or row >= len(recs):
            QMessageBox.information(self, "Slotting", "Analiza y selecciona una recomendación.")
            return
        rec = recs[row]
        from src.services.inventario import slotting as SL
        if SL.aplicar_intercambio(rec["id_ubicacion"], rec["id_ubicacion_sugerida"],
                                  id_empresa=self._id_empresa()):
            QMessageBox.information(self, "Slotting",
                                    f"Intercambio aplicado: {rec['codigo']} ↔ {rec['codigo_intercambio']}.")
            self._slotting_analizar()
        else:
            QMessageBox.warning(self, "Slotting", "No se pudo aplicar el intercambio.")

    def _cargar_pickings(self):
        try:
            from src.services.inventario import almacen_pro as AP
            self.cmb_pick.clear()
            for p in AP.listar_picking(self._id_empresa()):
                self.cmb_pick.addItem(f"#{p.get('id')} · {p.get('referencia') or p.get('estado') or ''}",
                                      p.get("id"))
        except Exception as e:
            logger.debug("cargar_pickings: %s", e)

    def _ruta_picking(self):
        pid = self.cmb_pick.currentData()
        if not pid:
            return
        from src.services.inventario import picking_ruta as PR
        ordenadas, _met = PR.ruta_picking(pid, self._id_empresa())
        self.tbl_ruta.setRowCount(len(ordenadas))
        for i, o in enumerate(ordenadas):
            vals = [o.get("orden"), o.get("codigo_articulo"), o.get("cantidad"), o.get("ubicacion"),
                    o.get("_pasillo")]
            for j, v in enumerate(vals):
                self.tbl_ruta.setItem(i, j, _it(v))

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _cargar(self):
        self._data = SA.listar_almacenes(self._id_empresa(), solo_activos=False)
        self.tabla.setRowCount(len(self._data))
        for i, a in enumerate(self._data):
            for j, v in enumerate([a.get("id"), a.get("nombre"), a.get("codigo_almacen"),
                                   a.get("tipo_almacen"), a.get("id_tienda"),
                                   a.get("estado"), a.get("activo")]):
                self.tabla.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tabla.currentRow()
        return self._data[i] if 0 <= i < len(self._data) else None

    def _crear(self):
        nombre = self.in_nombre.text().strip()
        codigo = self.in_codigo.text().strip()
        if not nombre or not codigo:
            QMessageBox.information(self, "Almacenes", "Indica nombre y código."); return
        rid = SA.crear_almacen(nombre, codigo, self.cmb_tipo.currentData(),
                               id_empresa=self._id_empresa())
        if rid:
            self.in_nombre.clear(); self.in_codigo.clear(); self._cargar()
        else:
            QMessageBox.warning(self, "Almacenes", "No se pudo crear (¿nombre/código duplicado?).")

    def _renombrar(self):
        a = self._sel()
        if not a:
            return
        nuevo, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=a.get("nombre") or "")
        if ok and nuevo.strip():
            SA.actualizar_almacen(a["id"], id_empresa=self._id_empresa(), nombre=nuevo.strip())
            self._cargar()

    def _activar(self, activo):
        a = self._sel()
        if not a:
            return
        SA.activar_almacen(a["id"], activo=activo, id_empresa=self._id_empresa())
        self._cargar()
