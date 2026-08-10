"""
App Store · Plugins y Extensiones — GUI (Fase IV · Bloque 2).

App Store OFICIAL del ERP: instala y administra PLUGINS, EXTENSIONES y conectores oficiales que
AMPLÍAN las capacidades del sistema. NO es un canal de comercio electrónico ni un canal de venta: los
marketplaces de e-commerce (Amazon/WooCommerce/…) son CANALES de Comercio Digital, no este módulo.
El módulo solo INSTALA/ADMINISTRA; la EJECUCIÓN de los conectores pertenece a los módulos consumidores
(p. ej. Canal Web). (Rearquitectura Comercio Digital · Fase 3.)

Pantalla profesional para navegar el catálogo de plugins: categorías, búsqueda, instalar,
desinstalar, actualizar, ver detalles, dependencias e historial. Consume ÚNICAMENTE el servicio
`src.services.marketplace` (nunca BD directa). Feedback 100% INLINE (sin QMessageBox/QDialog: en
esta app los modales pueden aflorar la corrupción de heap del stack de audio de SOMA — se usa una
etiqueta en la propia pantalla). Aislamiento por empresa (empresa activa).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn as _btn_base,
                                      _btn_x, _combo, _inp, _tabla)
from src.services import marketplace as mk

logger = logging.getLogger("marketplace.gui")


def _btn(txt, slot=None, primary=False, danger=False):
    # Estilo global: los botones secundarios (grises) se muestran turquesa (contorno/texto
    # turquesa, fondo azul oscuro, hover swap), como el resto de la app. Instalar (primary) y
    # Desinstalar (danger) conservan su color propio.
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class MarketplaceWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self._items = []
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("🧩 App Store · Plugins y Extensiones")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        # Subtítulo aclaratorio: elimina la ambigüedad con el comercio electrónico (Fase 3).
        sub = QLabel("Instala y administra plugins, extensiones y conectores oficiales que amplían el "
                     "ERP. No es un canal de venta.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{_DIM};font-size:12px;")
        root.addWidget(sub)

        # Barra: buscar + categoría + política + refrescar.
        barra = QHBoxLayout()
        self.in_buscar = _inp("Buscar plugin…"); self.in_buscar.setFixedWidth(220)
        self.in_buscar.textChanged.connect(self._recargar)
        self.cmb_categoria = _combo([("(todas)", None)])
        self.cmb_categoria.setMinimumWidth(150)   # evita texto cortado en el desplegable
        self.cmb_categoria.currentIndexChanged.connect(self._recargar)
        self.cmb_politica = _combo([(p, p) for p in mk.POLITICAS])
        self.cmb_politica.setMinimumWidth(150)    # evita texto cortado (oficiales/firmados/internos)
        self.cmb_politica.currentIndexChanged.connect(self._cambiar_politica)
        barra.addWidget(QLabel("Buscar:")); barra.addWidget(self.in_buscar)
        barra.addWidget(QLabel("Categoría:")); barra.addWidget(self.cmb_categoria)
        barra.addStretch()
        barra.addWidget(QLabel("Política:")); barra.addWidget(self.cmb_politica)
        barra.addWidget(_btn("🔄 Actualizar catálogo", self._recargar))
        root.addLayout(barra)

        self.tabla = _tabla(["Plugin", "Versión", "Categoría", "Autor", "Firma", "Instalado"])
        self.tabla.itemSelectionChanged.connect(self._on_sel)
        root.addWidget(self.tabla)

        # Acciones (inline, sin modales).
        acc = QHBoxLayout()
        acc.addWidget(_btn("Instalar", self._instalar, primary=True))
        acc.addWidget(_btn("Actualizar", self._actualizar))
        acc.addWidget(_btn("Verificar", self._verificar))
        acc.addWidget(_btn("Historial", self._historial))
        acc.addWidget(_btn("Rollback", self._rollback))
        acc.addStretch()
        acc.addWidget(_btn("Desinstalar", self._desinstalar, danger=True))
        root.addLayout(acc)

        # Detalle del plugin seleccionado: fondo TRANSPARENTE (antes _BG2, que dibujaba una barra gris a
        # todo lo ancho de la ventana incluso vacío). Ahora se integra con el fondo del resto de la vista.
        self.lbl_detalle = QLabel("")
        self.lbl_detalle.setWordWrap(True)
        self.lbl_detalle.setStyleSheet(f"color:{_TEXT};font-size:12px;background:transparent;padding:4px;")
        root.addWidget(self.lbl_detalle)
        self.lbl_feedback = QLabel(""); self.lbl_feedback.setWordWrap(True)
        self.lbl_feedback.setStyleSheet(f"color:{_CIAN};font-size:12px;")
        root.addWidget(self.lbl_feedback)

        self._sincronizar_politica()
        self._cargar_categorias()
        self._recargar()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _usuario(self):
        return (self.usuario or {}).get("nombre")

    def _feedback(self, msg, color=_CIAN):
        self.lbl_feedback.setStyleSheet(f"color:{color};font-size:12px;")
        self.lbl_feedback.setText(msg)

    def _clave_sel(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self._items):
            return None
        return self._items[fila].get("clave")

    def _sincronizar_politica(self):
        pol = mk.politica(self._id_empresa())
        i = self.cmb_politica.findData(pol)
        if i >= 0:
            self.cmb_politica.blockSignals(True); self.cmb_politica.setCurrentIndex(i)
            self.cmb_politica.blockSignals(False)

    def _cargar_categorias(self):
        self.cmb_categoria.blockSignals(True)
        self.cmb_categoria.clear(); self.cmb_categoria.addItem("(todas)", None)
        for c in mk.categorias(self._id_empresa()):
            self.cmb_categoria.addItem(c, c)
        self.cmb_categoria.blockSignals(False)

    # ── datos ────────────────────────────────────────────────────────────────
    def _recargar(self, *_):
        emp = self._id_empresa()
        self._items = mk.catalogo(emp, categoria=self.cmb_categoria.currentData(),
                                  texto=self.in_buscar.text().strip())
        self.tabla.setRowCount(len(self._items))
        for i, it in enumerate(self._items):
            fila = [it.get("clave"), it.get("version"), it.get("categoria"), it.get("autor"),
                    it.get("firma"), "Sí" if it.get("instalado") else "—"]
            for j, v in enumerate(fila):
                self.tabla.setItem(i, j, _it(v))
        if not self._items:
            self._feedback("No hay plugins en el catálogo para el filtro actual.", _DIM)

    def _on_sel(self):
        it = None
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self._items):
            it = self._items[fila]
        if not it:
            self.lbl_detalle.setText(""); return
        det = mk.detalle(it["clave"], self._id_empresa()) or it
        deps = ", ".join(det.get("dependencias") or []) or "ninguna"
        self.lbl_detalle.setText(
            f"<b>{det.get('nombre')}</b> v{det.get('version')} · {det.get('categoria')} · "
            f"autor: {det.get('autor') or '—'}<br>{det.get('descripcion') or ''}<br>"
            f"Firma: {det.get('firma')} · Licencia: {det.get('licencia') or '—'} · "
            f"Dependencias: {deps} · Repo: {det.get('repo')}")

    # ── acciones (inline) ──────────────────────────────────────────────────────
    def _cambiar_politica(self):
        pol = self.cmb_politica.currentData()
        if mk.fijar_politica(pol, id_empresa=self._id_empresa()):
            self._feedback(f"Política del marketplace fijada a «{pol}».")
        self._recargar()

    def _accion(self, fn, ok_msg):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin en la lista.", "#F0A020"); return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = fn(clave)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self._feedback(f"❌ Error: {e}", "#F85149"); return
        QApplication.restoreOverrideCursor()
        if isinstance(res, dict) and res.get("ok"):
            self._feedback(ok_msg(res), _CIAN)
            self._cargar_categorias(); self._recargar()
        else:
            err = (res or {}).get("errores") if isinstance(res, dict) else None
            self._feedback(f"⚠️ No se pudo completar: {err or res}", "#F0A020")

    def _instalar(self):
        self._accion(lambda c: mk.instalar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"✅ Instalado «{r['clave']}» ({', '.join(r.get('instalados', []))}).")

    def _desinstalar(self):
        self._accion(lambda c: mk.desinstalar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"🗑 Desinstalado «{r['clave']}».")

    def _actualizar(self):
        self._accion(lambda c: mk.actualizar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"⬆ Actualizado «{r['clave']}» {r.get('desde')}→{r.get('hasta')}.")

    def _rollback(self):
        self._accion(lambda c: mk.rollback(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"↩ Rollback de «{r['clave']}» a v{r.get('version')}.")

    def _verificar(self):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin.", "#F0A020"); return
        r = mk.verificar_integridad(clave, id_empresa=self._id_empresa())
        ok = r.get("ok")
        self._feedback(f"{'✅' if ok else '⚠️'} Integridad de «{clave}»: firma={r.get('firma')} · "
                       f"hash instalado={str(r.get('hash_instalado'))[:12]}…",
                       _CIAN if ok else "#F0A020")

    def _historial(self):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin.", "#F0A020"); return
        hist = mk.historial(clave, self._id_empresa())
        if not hist:
            self._feedback(f"Sin historial para «{clave}».", _DIM); return
        lineas = " · ".join(f"{h.get('accion')} v{h.get('version') or '?'}" for h in hist[:8])
        self._feedback(f"Historial de «{clave}»: {lineas}", _TEXT)
