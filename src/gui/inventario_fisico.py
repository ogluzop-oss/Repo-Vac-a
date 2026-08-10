"""
Inventario físico (INV.2) — GUI de recuento e inventario auditado.

Pantalla NUEVA dentro de INVENTARIO (no modifica las existentes). Permite crear/abrir
inventarios, contar artículos, ver diferencias, cerrar (con ajuste auditado vía INV.1) y
consultar históricos. Multiempresa/multitienda por contexto activo. Reutiliza helpers de
catalogo_gestion.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.db import inventario_fisico as inv
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo,
                                      _inp, _tabla)

logger = logging.getLogger("inventario.fisico.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class InventarioFisicoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._inv_id = None
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Inventario físico · Recuento auditado")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        # ── selector de inventario ──
        sel = QHBoxLayout()
        self.f_estado = _combo([("(todos)", None), ("BORRADOR", inv.BORRADOR),
                                ("ABIERTO", inv.ABIERTO), ("CERRADO", inv.CERRADO),
                                ("ANULADO", inv.ANULADO)])
        self.f_estado.setMinimumWidth(150)   # evita texto cortado (BORRADOR/CERRADO/ANULADO)
        self.cmb_inv = _combo([])
        self.cmb_inv.currentIndexChanged.connect(self._cargar_lineas)
        sel.addWidget(QLabel("Estado:")); sel.addWidget(self.f_estado)
        self.f_estado.currentIndexChanged.connect(self._recargar)
        sel.addWidget(QLabel("Inventario:")); sel.addWidget(self.cmb_inv, 1)
        sel.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        sel.addWidget(_btn("Abrir", self._abrir))
        sel.addWidget(_btn("Cerrar", self._cerrar))
        sel.addWidget(_btn("Anular", self._anular, danger=True))
        root.addLayout(sel)

        # ── barra INLINE "Nuevo inventario" (sin QInputDialog modal, que en este entorno puede
        # aflorar la corrupción de heap del stack de audio de SOMA). Oculta hasta pulsar "Nuevo". ──
        self._nuevo_bar = QWidget()
        nb = QHBoxLayout(self._nuevo_bar); nb.setContentsMargins(0, 0, 0, 0)
        self.in_nombre = _inp("Nombre del inventario"); self.in_nombre.setMinimumWidth(220)
        self.cmb_almacen = _combo([("(agregado / sin almacén)", None)])
        self.cmb_almacen.setMinimumWidth(220)
        self.in_nombre.returnPressed.connect(self._crear_inventario_inline)
        nb.addWidget(QLabel("Nuevo:")); nb.addWidget(self.in_nombre)
        nb.addWidget(QLabel("Almacén:")); nb.addWidget(self.cmb_almacen)
        nb.addWidget(_btn("Crear", self._crear_inventario_inline, primary=True))
        nb.addWidget(_btn("Cancelar", lambda: self._nuevo_bar.setVisible(False)))
        nb.addStretch()
        self._nuevo_bar.setVisible(False)
        root.addWidget(self._nuevo_bar)

        # ── barra INLINE de confirmación (sustituye a QMessageBox.question, que es modal) ──
        self._confirm_bar = QWidget()
        cbl = QHBoxLayout(self._confirm_bar); cbl.setContentsMargins(0, 0, 0, 0)
        self._confirm_lbl = QLabel(""); self._confirm_lbl.setStyleSheet(f"color:{_TEXT};")
        self._confirm_cb = None
        cbl.addWidget(self._confirm_lbl)
        cbl.addWidget(_btn("Confirmar", self._confirm_ok, primary=True))
        cbl.addWidget(_btn("Cancelar", lambda: self._confirm_bar.setVisible(False)))
        cbl.addStretch()
        self._confirm_bar.setVisible(False)
        root.addWidget(self._confirm_bar)

        self.lbl_estado = QLabel(""); self.lbl_estado.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl_estado)

        # ── recuento ──
        rec = QHBoxLayout()
        self.in_cod = _inp("Código artículo"); self.in_cod.setFixedWidth(180)
        self.in_cant = _inp("Contado"); self.in_cant.setFixedWidth(110)
        rec.addWidget(QLabel("Contar:")); rec.addWidget(self.in_cod)
        rec.addWidget(self.in_cant)
        rec.addWidget(_btn("Registrar recuento", self._contar, primary=True))
        rec.addStretch()
        rec.addWidget(_btn("📡 Barrido RFID (PDA/MDE)", self._barrido_rfid))
        root.addLayout(rec)

        self.tabla = _tabla(["Artículo", "Esperado", "Contado", "Diferencia", "Observaciones"])
        root.addWidget(self.tabla)
        self.lbl_resumen = QLabel(""); self.lbl_resumen.setStyleSheet(f"color:{_TEXT};")
        root.addWidget(self.lbl_resumen)
        # Feedback INLINE del barrido RFID (sin diálogos modales: evita crear ventanas top-level
        # que en este entorno pueden aflorar corrupción de heap del stack de audio de SOMA).
        self.lbl_barrido = QLabel(""); self.lbl_barrido.setWordWrap(True)
        self.lbl_barrido.setStyleSheet(f"color:{_CIAN};font-size:12px;")
        self.lbl_barrido.setVisible(False)
        root.addWidget(self.lbl_barrido)

        self._recargar()

    # ── helpers ──
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _recargar(self):
        self.cmb_inv.blockSignals(True)
        self.cmb_inv.clear()
        for c in inv.listar_inventarios(self._id_empresa(), estado=self.f_estado.currentData()):
            self.cmb_inv.addItem(f"#{c['id']} · {c['nombre']} [{c['estado']}]", c["id"])
        self.cmb_inv.blockSignals(False)
        self._cargar_lineas()

    def _inv_actual(self):
        return self.cmb_inv.currentData()

    def _cargar_lineas(self):
        iid = self._inv_actual()
        self._inv_id = iid
        if not iid:
            self.tabla.setRowCount(0); self.lbl_estado.setText(""); self.lbl_resumen.setText("")
            return
        cab = inv.obtener_inventario(iid, self._id_empresa()) or {}
        self.lbl_estado.setText(f"Estado: {cab.get('estado','')} · tienda {cab.get('id_tienda')}")
        lineas = inv.listar_lineas(iid, self._id_empresa())
        self.tabla.setRowCount(len(lineas))
        for i, l in enumerate(lineas):
            for j, v in enumerate([l.get("codigo_articulo"), l.get("stock_esperado"),
                                   l.get("stock_contado"), l.get("diferencia"),
                                   l.get("observaciones")]):
                self.tabla.setItem(i, j, _it(v))
        r = inv.resumen(iid, self._id_empresa())
        self.lbl_resumen.setText(
            f"Líneas {r['lineas']} · contadas {r['contadas']} · con diferencia "
            f"{r['con_diferencia']} · sobrante +{r['sobrante']} · faltante {r['faltante']}")

    def _usuario(self):
        return (self.usuario or {}).get("nombre")

    def _feedback(self, msg, color="#F0A020"):
        """Mensaje INLINE en la pestaña (sin diálogos modales)."""
        self.lbl_barrido.setStyleSheet(f"color:{color};font-size:12px;")
        self.lbl_barrido.setText(msg)
        self.lbl_barrido.setVisible(True)

    # ── acciones ──
    def _nuevo(self):
        """Muestra el formulario INLINE de nuevo inventario (sin QInputDialog modal). Rellena el
        selector de almacenes (INV.7.3: opcional → inventario agregado si no se elige)."""
        self.cmb_almacen.clear()
        self.cmb_almacen.addItem("(agregado / sin almacén)", None)
        try:
            from src.db import stock_almacen as SA
            for a in SA.listar_almacenes(self._id_empresa()):
                self.cmb_almacen.addItem(f"{a['nombre']} [{a['tipo_almacen']}]", a["id"])
        except Exception:
            pass
        self.in_nombre.clear()
        self._nuevo_bar.setVisible(True)
        self.in_nombre.setFocus()

    def _crear_inventario_inline(self):
        nombre = self.in_nombre.text().strip()
        if not nombre:
            self._feedback("⚠️ Escribe un nombre para el inventario."); return
        id_almacen = self.cmb_almacen.currentData()
        iid = inv.crear_inventario(nombre, id_empresa=self._id_empresa(),
                                   usuario=self._usuario(), id_almacen=id_almacen)
        self._nuevo_bar.setVisible(False)
        if iid:
            self._recargar()
            i = self.cmb_inv.findData(iid)
            if i >= 0:
                self.cmb_inv.setCurrentIndex(i)
            self._feedback(f"✅ Inventario «{nombre}» creado. Pulsa «Abrir» y luego "
                           "«Barrido RFID (PDA/MDE)».", _CIAN)
        else:
            self._feedback("❌ No se pudo crear el inventario.", "#F85149")

    def _pedir_confirmacion(self, texto, callback):
        """Confirmación INLINE (sin QMessageBox modal): muestra la barra con el callback armado."""
        self._confirm_lbl.setText(texto)
        self._confirm_cb = callback
        self._confirm_bar.setVisible(True)

    def _confirm_ok(self):
        self._confirm_bar.setVisible(False)
        cb = self._confirm_cb
        self._confirm_cb = None
        if cb:
            cb()

    def _abrir(self):
        iid = self._inv_actual()
        if not iid:
            return
        try:
            inv.abrir_inventario(iid, self._id_empresa())
        except inv.InventarioError as e:
            self._feedback(f"⚠️ {e}", "#F0A020"); return
        self._recargar()
        self._feedback("Inventario ABIERTO. Ya puedes contar o usar el «Barrido RFID (PDA/MDE)».",
                       _CIAN)

    def _anular(self):
        iid = self._inv_actual()
        if not iid:
            return
        self._pedir_confirmacion("¿Anular este inventario?", lambda: self._anular_confirmado(iid))

    def _anular_confirmado(self, iid):
        try:
            inv.anular_inventario(iid, self._id_empresa())
        except inv.InventarioError as e:
            self._feedback(f"⚠️ {e}", "#F0A020"); return
        self._recargar()
        self._feedback("Inventario anulado.", _DIM)

    def _contar(self):
        iid = self._inv_actual()
        if not iid:
            self._feedback("⚠️ Selecciona un inventario."); return
        cod = self.in_cod.text().strip()
        try:
            cant = int(self.in_cant.text().strip())
        except ValueError:
            self._feedback("⚠️ Cantidad contada no válida."); return
        try:
            inv.registrar_recuento(iid, cod, cant, id_empresa=self._id_empresa())
        except inv.InventarioError as e:
            self._feedback(f"⚠️ {e}", "#F0A020"); return
        self.in_cod.clear(); self.in_cant.clear()
        self._cargar_lineas()

    def _cerrar(self):
        iid = self._inv_actual()
        if not iid:
            return
        self._pedir_confirmacion(
            "Al cerrar se aplicarán los AJUSTES de stock auditados. ¿Continuar?",
            lambda: self._cerrar_confirmado(iid))

    def _cerrar_confirmado(self, iid):
        try:
            res = inv.cerrar_inventario(iid, usuario=self._usuario(), id_empresa=self._id_empresa())
        except inv.InventarioError as e:
            self._feedback(f"⚠️ {e}", "#F0A020"); return
        self._recargar()
        self._feedback(f"✅ Inventario cerrado. Ajustes de stock aplicados: "
                       f"{res['ajustes_aplicados']}.", _CIAN)

    # ── barrido RFID (PDA/MDE) ────────────────────────────────────────────────
    def _barrido_rfid(self):
        """Recuento automático mediante barrido con PDA/MDE (RFID activo): detecta todos los
        artículos por sus alarmas, registra el recuento y muestra las discrepancias frente al
        stock esperado. Degradable (real si hay lector RFID; si no, barrido simulado).

        TODO el feedback es INLINE (etiqueta en la propia pestaña) — sin QMessageBox/QDialog.
        En este entorno, crear ventanas modales top-level mientras el stack de audio de SOMA
        (pyaudio/pygame/edge-tts) corre en segundo plano puede aflorar corrupción de heap
        (0xC0000374) y cerrar la app. Evitando ventanas nuevas, el barrido no toca esa superficie."""
        def aviso(msg, color="#F0A020"):
            self.lbl_barrido.setStyleSheet(f"color:{color};font-size:12px;")
            self.lbl_barrido.setText(msg)
            self.lbl_barrido.setVisible(True)

        iid = self._inv_actual()
        if not iid:
            aviso("⚠️ Barrido RFID: selecciona o crea un inventario antes de barrer."); return
        cab = inv.obtener_inventario(iid, self._id_empresa()) or {}
        if cab.get("estado") not in inv._EDITABLES:
            aviso(f"⚠️ Barrido RFID: el inventario '{cab.get('estado','')}' no es editable. "
                  "Ábrelo (o usa un BORRADOR) para barrer."); return

        # Barrido + registro SÍNCRONO en el hilo de la GUI (1 consulta + 1 transacción → rápido).
        # Sin QThread, sin processEvents, sin diálogos modales. El registro masivo ignora tags ajenos.
        aviso("📡 Barrido RFID en curso… detectando artículos por sus alarmas.", _CIAN)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = None
        res = None
        registrados = 0
        try:
            from src.services.rfid import barrido_inventario
            res = barrido_inventario(self._id_empresa(), cab.get("id_tienda"))
            filas = res.get("detectados", [])
            if filas:
                items = [(f["codigo"], f["detectado"], "Barrido RFID") for f in filas]
                registrados = inv.registrar_recuentos_masivo(
                    iid, items, id_empresa=self._id_empresa())
        except Exception as e:
            error = str(e)
        finally:
            QApplication.restoreOverrideCursor()

        if error:
            aviso(f"❌ Barrido RFID: no se pudo completar ({error}).", "#F85149"); return
        self._cargar_lineas()   # repuebla la tabla y el resumen del inventario
        if not res.get("detectados"):
            aviso("Barrido RFID: no se detectó ningún artículo con alarma en la tienda.", _DIM)
            return
        modo = "lector RFID" if res.get("modo") == "RFID" else "simulado (sin hardware)"
        disc = res.get("discrepancias", 0)
        col = "#F85149" if disc else _CIAN
        aviso(f"📡 Barrido RFID completado ({modo}) · "
              f"{res.get('total_articulos', 0)} artículos · {res.get('total_unidades', 0)} uds · "
              f"{registrados} recuentos registrados · {disc} discrepancia(s) con el stock esperado. "
              + ("Revísalas en la tabla (columna Diferencia)." if disc
                 else "El stock detectado coincide con el esperado. ✅"), col)
