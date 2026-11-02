"""
Transporte / Flota + rutas de reparto (función base `transporte.reparto`, R8). La ventana SOLO orquesta
`services.transporte` (flota + rutas; la entrega descuenta stock por el motor oficial). Acceso gateado con
`verticales.visible("transporte.reparto")`. Compatible con el menú (firma estándar).
"""

import datetime as _dt
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.gui.components.completer_articulos import instalar_sugerencias_articulo
from src.gui.components.completer_centros import instalar_sugerencias_centro, resolver_id_centro
from src.gui.foundation import tokens as T
from src.services import transporte as _S

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.transporte")


def _btn(txt, cb, *, primary=False, rojo=False, h=36):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(h)
    col = T.CRITICO if rojo else T.INFO
    if primary:
        # Mismo criterio que el resto de la app (`catalogo_gestion._btn`): contorno turquesa + fondo
        # oscuro en reposo, relleno turquesa al pasar el ratón — antes este rama estaba invertida
        # (rellena en reposo, transparente al hover), el único botón de este fichero que no coincidía
        # con el resto de la app.
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:2px solid {col};border-radius:8px;"
                        f"font-weight:800;padding:6px 14px;}}QPushButton:hover{{background:{col};color:{T.BG};}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:2px solid {col};border-radius:8px;"
                        f"font-weight:800;padding:6px 14px;}}QPushButton:hover{{background:{col};color:{T.BG};}}")
    if cb:
        b.clicked.connect(cb)
    return b


def _btn_cargando(txt, cb, *, primary=False, rojo=False, h=36, cargando="⏳  Actualizando…"):
    """Como `_btn`, pero al pulsarse muestra un estado de carga y se deshabilita mientras `cb`
    se ejecuta (petición: TODOS los botones «Actualizar» de la app con esta animación)."""
    b = _btn(txt, None, primary=primary, rojo=rojo, h=h)

    def _run():
        orig = b.text()
        b.setText(cargando); b.setEnabled(False)
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            cb()
        finally:
            b.setText(orig); b.setEnabled(True)
    b.clicked.connect(_run)
    return b


def _inp(ph=""):
    e = QLineEdit(); e.setPlaceholderText(ph); e.setFixedHeight(34)
    e.setStyleSheet(f"QLineEdit{{background:{T.BG};color:{T.TEXT};border:2px solid #30363D;border-radius:8px;"
                    f"padding:0 10px;}}QLineEdit:focus{{border-color:{T.INFO};}}")
    return e


def _tabla(cols):
    t = QTableWidget(0, len(cols)); t.setHorizontalHeaderLabels(cols)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.horizontalHeader().setHighlightSections(False)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setFrameShape(QTableWidget.Shape.NoFrame)
    t.setStyleSheet(_ss_tabla_neon())
    t._round = _RoundTableCorners(t, radius=10)
    return t


def _aviso(parent, titulo, msg, tipo="info"):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, msg, tipo)


class TransporteWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        self._cargar_vehiculos()
        self._cargar_rutas()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        cab = QHBoxLayout()
        tit = QLabel("🚚  TRANSPORTE · FLOTA Y REPARTO")
        tit.setStyleSheet(f"color:{T.INFO};font-size:20px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            from src.gui.catalogo_gestion import _btn_x
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{border:none;}}"
            f"QTabBar::tab{{background:transparent;color:{T.TEXT};padding:8px 18px;font-weight:800;"
            f"border:1px solid #30363D;border-bottom:none;border-top-left-radius:8px;border-top-right-radius:8px;}}"
            f"QTabBar::tab:selected{{background:{T.INFO};color:{T.BG};}}")
        tabs.addTab(self._tab_flota(), "Flota")
        tabs.addTab(self._tab_rutas(), "Rutas de reparto")

        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo, todas visibles
        # por defecto; sin acceso completo (entró solo por una concesión de pestaña suelta), solo
        # la(s) concedida(s).
        from src.services.seguridad import pestanas_app
        _tiene_completo = pestanas_app.tiene_modulo_completo("transporte", self.usuario, False)
        for _i, _slug in enumerate(["flota", "rutas"]):
            if not pestanas_app.visible(f"transporte.{_slug}", self.usuario, _tiene_completo):
                tabs.setTabVisible(_i, False)

        root.addWidget(tabs, 1)

    # ── Flota ────────────────────────────────────────────────────────────────
    def _tab_flota(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        fila = QHBoxLayout()
        self._v_mat = _inp("Matrícula *"); self._v_desc = _inp("Descripción")
        # QLineEdit + validador en vez de QSpinBox: la app oculta sus flechas arriba/abajo vía QSS y
        # eso rompía su foco/clic en varios diálogos (confirmado por el usuario) — mismo criterio ya
        # aplicado en `sat_dashboard._FormDialog`.
        self._v_cap = _inp("Capacidad (kg)")
        self._v_cap.setValidator(QIntValidator(0, 100000, self._v_cap))
        self._v_cap.setFixedHeight(38)   # alto suficiente para que el texto no se corte por debajo
        self._v_cond = _inp("Conductor")
        self._v_precio = _inp("Precio (€) *")
        val_precio = QDoubleValidator(0.0, 1e9, 2, self._v_precio)
        val_precio.setNotation(QDoubleValidator.Notation.StandardNotation)
        self._v_precio.setValidator(val_precio)
        for x in (self._v_mat, self._v_desc, self._v_cap, self._v_cond, self._v_precio):
            fila.addWidget(x)
        fila.addWidget(_btn("＋  Añadir vehículo", self._add_vehiculo, primary=True))
        v.addLayout(fila)
        self._tbl_veh = _tabla(["Matrícula", "Descripción", "Capacidad", "Conductor", "Estado"])
        v.addWidget(self._tbl_veh, 1)
        return w

    def _add_vehiculo(self):
        mat = self._v_mat.text().strip()
        if not mat:
            return _aviso(self, "Flota", "Indica la matrícula del vehículo.", "warning")
        try:
            cap = int(self._v_cap.text() or 0)
        except ValueError:
            cap = 0
        try:
            precio = float((self._v_precio.text() or "0").replace(",", "."))
        except ValueError:
            precio = 0.0
        if precio <= 0:
            return _aviso(self, "Flota", "Indica el precio de adquisición del vehículo (obligatorio, mayor que 0).",
                         "warning")
        vid = _S.crear_vehiculo(mat, descripcion=self._v_desc.text().strip() or None,
                                capacidad_kg=cap or None,
                                conductor=self._v_cond.text().strip() or None,
                                coste_adquisicion=precio, id_empresa=self._emp())
        if not vid:
            return _aviso(self, "Flota", "No se pudo añadir el vehículo.", "error")
        self._v_mat.clear(); self._v_desc.clear(); self._v_cap.clear(); self._v_cond.clear(); self._v_precio.clear()
        self._cargar_vehiculos()
        _aviso(self, "Flota", "Vehículo añadido.", "success")

    def _cargar_vehiculos(self):
        self._tbl_veh.setRowCount(0)
        for veh in _S.listar_vehiculos(id_empresa=self._emp()):
            r = self._tbl_veh.rowCount(); self._tbl_veh.insertRow(r)
            cap = f"{veh.get('capacidad_kg')} kg" if veh.get("capacidad_kg") else "—"
            for c, val in enumerate((veh.get("matricula"), veh.get("descripcion") or "—", cap,
                                     veh.get("conductor") or "—", veh.get("estado"))):
                self._tbl_veh.setItem(r, c, QTableWidgetItem(str(val)))

    # ── Rutas ────────────────────────────────────────────────────────────────
    def _tab_rutas(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        barra = QHBoxLayout()
        barra.addWidget(_btn("＋  Nueva ruta", self._nueva_ruta, primary=True))
        barra.addWidget(_btn("▶  Iniciar", self._iniciar_ruta))
        barra.addWidget(_btn("📦  Entregas / ver", self._ver_ruta))
        barra.addWidget(_btn("✔  Cerrar ruta", self._cerrar_ruta))
        barra.addStretch()
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._cargar_rutas))
        v.addLayout(barra)
        self._tbl_rutas = _tabla(["ID", "Fecha", "Vehículo", "Conductor", "Estado"])
        v.addWidget(self._tbl_rutas, 1)
        return w

    def _cargar_rutas(self):
        self._tbl_rutas.setRowCount(0)
        for rt in _S.listar_rutas(id_empresa=self._emp()):
            r = self._tbl_rutas.rowCount(); self._tbl_rutas.insertRow(r)
            for c, val in enumerate((rt.get("id"), rt.get("fecha"), rt.get("id_vehiculo") or "—",
                                     rt.get("conductor") or "—", rt.get("estado"))):
                self._tbl_rutas.setItem(r, c, QTableWidgetItem(str(val)))

    def _ruta_sel(self):
        r = self._tbl_rutas.currentRow()
        if r < 0:
            _aviso(self, "Rutas", "Selecciona una ruta.", "warning"); return None
        try:
            return int(self._tbl_rutas.item(r, 0).text())
        except Exception:
            return None

    def _nueva_ruta(self):
        dlg = _NuevaRutaDialog(self._emp(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cargar_rutas()

    def _iniciar_ruta(self):
        rid = self._ruta_sel()
        if rid is None:
            return
        ok = _S.iniciar_ruta(rid, id_empresa=self._emp())
        _aviso(self, "Rutas", "Ruta iniciada." if ok else "La ruta no estaba planificada.",
               "success" if ok else "warning")
        self._cargar_rutas()

    def _cerrar_ruta(self):
        rid = self._ruta_sel()
        if rid is None:
            return
        r = _S.cerrar_ruta(rid, id_empresa=self._emp())
        _aviso(self, "Rutas", "Ruta cerrada." if r.get("ok") else r.get("error", "No se pudo cerrar."),
               "success" if r.get("ok") else "warning")
        self._cargar_rutas()

    def _ver_ruta(self):
        rid = self._ruta_sel()
        if rid is None:
            return
        _EntregaDialog(rid, self._emp(), self).exec()
        self._cargar_rutas()


class _NuevaRutaDialog(QDialog):
    """Crea una ruta con paradas (cada una con líneas: código + cantidad)."""

    def __init__(self, id_empresa, parent=None):
        super().__init__(parent)
        self._emp = id_empresa
        self._paradas = []          # [{cliente, direccion, lineas:[{codigo,cantidad}]}]
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True); self.setMinimumWidth(560)
        self._build()

    def showEvent(self, e):
        # Ventana COMPLETA: ocupa toda la ventana padre para que la tabla tenga altura (no aplastada).
        super().showEvent(e)
        try:
            w = self.parent().window() if self.parent() is not None else None
            if w is not None:
                self.setGeometry(w.geometry())
        except Exception:
            pass

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("dlg_card")
        card.setStyleSheet(f"QFrame#dlg_card{{background:{T.BG};border:2px solid {T.INFO};border-radius:16px;}}")
        root.addWidget(card)
        v = QVBoxLayout(card); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        cab = QHBoxLayout(); tit = QLabel("＋  NUEVA RUTA DE REPARTO")
        tit.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        from src.gui.catalogo_gestion import _btn_x
        cab.addWidget(tit); cab.addStretch(); cab.addWidget(_btn_x(self.reject))
        v.addLayout(cab)

        top = QHBoxLayout()
        self._fecha = _inp("AAAA-MM-DD"); self._fecha.setText(_dt.date.today().strftime("%Y-%m-%d"))
        self._veh = QComboBox(); self._veh.setFixedHeight(34)
        self._veh.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:2px solid #30363D;"
                                f"border-radius:8px;padding:0 10px;}}"
                                f"QComboBox::drop-down{{border:none;width:22px;background:transparent;}}")
        self._veh.addItem("— Sin vehículo —", None)
        for veh in _S.listar_vehiculos(id_empresa=self._emp):
            self._veh.addItem(f"{veh.get('matricula')} ({veh.get('conductor') or '—'})", veh.get("id"))
        self._cond = _inp("Conductor")
        self._id_cond = _inp("(opcional) ID de usuario del conductor")
        self._id_cond.setValidator(QIntValidator(0, 10_000_000, self._id_cond))
        self._id_cond.setFixedHeight(34)
        self._id_cond.setToolTip("ID de usuario del conductor (opcional) — para que vea esta ruta en el móvil")
        top.addWidget(self._fecha); top.addWidget(self._veh); top.addWidget(self._cond)
        top.addWidget(self._id_cond)
        v.addLayout(top)

        # Añadir parada
        pf = QHBoxLayout()
        self._p_cli = _inp("Cliente"); self._p_dir = _inp("Dirección")
        self._p_centro = _inp("Centro destino (buscar, opcional)")
        instalar_sugerencias_centro(self._p_centro)
        self._p_cod = _inp("Código artículo"); self._p_cant = _inp("Cantidad")
        instalar_sugerencias_articulo(self._p_cod)
        self._p_cant.setValidator(QIntValidator(1, 100000, self._p_cant))
        self._p_cant.setText("1")
        self._p_cant.setFixedHeight(34)
        for x in (self._p_cli, self._p_dir, self._p_centro, self._p_cod, self._p_cant):
            pf.addWidget(x)
        pf.addWidget(_btn("＋ Parada", self._add_parada))
        v.addLayout(pf)
        v.addWidget(QLabel("Centro destino (petición de cross-docking automático): si la parada "
                           "lleva un centro REGISTRADO de la empresa, Producción/Logística pueden "
                           "enlazar mercancía a esta ruta automáticamente, sin pasar por almacén.",
                           styleSheet=f"color:{T.DIM};font-size:11px;"))

        self._tbl = _tabla(["Cliente", "Dirección", "Centro destino", "Artículo", "Cantidad"])
        v.addWidget(self._tbl, 1)

        acc = QHBoxLayout(); acc.addStretch()
        acc.addWidget(_btn("Crear ruta", self._crear, primary=True))
        v.addLayout(acc)

    def _add_parada(self):
        cli = self._p_cli.text().strip(); cod = self._p_cod.text().strip()
        if "–" in cod:  # viene del autocompletado "CÓDIGO – NOMBRE"
            cod = cod.split("–")[0].strip()
        if not cli or not cod:
            return _aviso(self, "Nueva ruta", "Indica al menos cliente y código de artículo.", "warning")
        try:
            cant = int(self._p_cant.text() or 1)
        except ValueError:
            cant = 1
        id_centro_destino = resolver_id_centro(self._p_centro.text())
        self._paradas.append({"cliente": cli, "direccion": self._p_dir.text().strip(),
                              "id_centro_destino": id_centro_destino,
                              "lineas": [{"codigo": cod, "cantidad": cant}]})
        r = self._tbl.rowCount(); self._tbl.insertRow(r)
        centro_txt = self._p_centro.text().strip() or "—"
        for c, val in enumerate((cli, self._p_dir.text().strip() or "—", centro_txt, cod, cant)):
            self._tbl.setItem(r, c, QTableWidgetItem(str(val)))
        self._p_cli.clear(); self._p_dir.clear(); self._p_centro.clear()
        self._p_cod.clear(); self._p_cant.setText("1")

    def _crear(self):
        if not self._paradas:
            return _aviso(self, "Nueva ruta", "Añade al menos una parada.", "warning")
        try:
            id_cond = int(self._id_cond.text()) if self._id_cond.text().strip() else None
        except ValueError:
            id_cond = None
        rid = _S.crear_ruta(self._fecha.text().strip(), id_vehiculo=self._veh.currentData(),
                            conductor=self._cond.text().strip() or None, paradas=self._paradas,
                            id_empresa=self._emp,
                            id_conductor=id_cond)
        if rid:
            _aviso(self, "Nueva ruta", f"Ruta #{rid} creada con {len(self._paradas)} parada(s).", "success")
            self.accept()
        else:
            _aviso(self, "Nueva ruta", "No se pudo crear la ruta.", "error")


class _EntregaDialog(QDialog):
    """Muestra las paradas de una ruta y permite ENTREGAR cada una (descuenta stock)."""

    def __init__(self, id_ruta, id_empresa, parent=None):
        super().__init__(parent)
        self._rid = id_ruta; self._emp = id_empresa
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True); self.setMinimumWidth(560)
        self._build(); self._cargar()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("dlg_card")
        card.setStyleSheet(f"QFrame#dlg_card{{background:{T.BG};border:2px solid {T.INFO};border-radius:16px;}}")
        root.addWidget(card)
        self._v = QVBoxLayout(card); self._v.setContentsMargins(22, 18, 22, 18); self._v.setSpacing(10)
        cab = QHBoxLayout(); tit = QLabel(f"📦  RUTA #{self._rid} · PARADAS")
        tit.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        from src.gui.catalogo_gestion import _btn_x
        cab.addWidget(tit); cab.addStretch(); cab.addWidget(_btn_x(self.accept))
        self._v.addLayout(cab)
        self._tbl = _tabla(["Orden", "Cliente", "Dirección", "Estado"])
        self._v.addWidget(self._tbl, 1)
        self._v.addWidget(_btn("📦  Entregar parada seleccionada", self._entregar, primary=True))

    def _cargar(self):
        self._ruta = _S.obtener_ruta(self._rid, id_empresa=self._emp) or {}
        self._tbl.setRowCount(0)
        for p in self._ruta.get("paradas", []):
            r = self._tbl.rowCount(); self._tbl.insertRow(r)
            for c, val in enumerate((p.get("orden"), p.get("cliente") or "—", p.get("direccion") or "—",
                                     p.get("estado"))):
                self._tbl.setItem(r, c, QTableWidgetItem(str(val)))

    def _entregar(self):
        r = self._tbl.currentRow()
        paradas = self._ruta.get("paradas", [])
        if r < 0 or r >= len(paradas):
            return _aviso(self, "Entrega", "Selecciona una parada.", "warning")
        res = _S.entregar_parada(paradas[r]["id"], id_empresa=self._emp)
        if res.get("ok"):
            msg = "Parada ya entregada." if res.get("ya") else f"Entregadas {res.get('entregadas', 0)} línea(s)."
            _aviso(self, "Entrega", msg, "success")
            self._cargar()
        else:
            _aviso(self, "Entrega", res.get("error", "No se pudo entregar."), "error")
