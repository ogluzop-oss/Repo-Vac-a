"""
Gestión de almacenes (INV.7.1) — GUI CRUD sobre la tabla `almacen`.

Pantalla NUEVA dentro de INVENTARIO. Alta/edición/activación/baja lógica de almacenes
(nombre, código, tipo, tienda asociada, estado). No elimina físicamente (conserva
existencias e histórico). Multiempresa por contexto activo.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                             QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import stock_almacen as SA
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_x, _combo, _dialogo_frameless,
                                      _inp, _tabla)
from src.gui.foundation import tokens as T

logger = logging.getLogger("inventario.almacenes.gui")

_TIPOS = ["central", "regional", "logistico", "tienda", "temporal"]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class _RenombrarDialog(QDialog):
    """Diálogo de renombrar propio (sustituye a QInputDialog.getText): sin barra de Windows,
    esquinas redondeadas y botones con el estilo estándar de la app."""

    def __init__(self, nombre_actual, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Renombrar almacén", ancho=380)
        v.addWidget(QLabel("Nuevo nombre:"))
        self.inp = QLineEdit(nombre_actual or "")
        self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:white;border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;font-size:13px;}")
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def valor(self):
        return self.inp.text()


class _InfoDialog(QDialog):
    """Aviso propio (sustituye a QMessageBox.information/.warning): sin barra de Windows, esquinas
    redondeadas y un único botón «Aceptar». Los QMessageBox nativos, sobre una ventana anfitriona
    frameless (`FramelessWindowHint`, como todas las ventanas completas de la app), pueden quedar sin
    handle nativo correcto y comportarse de forma errática (incluida la ventana cerrándose de golpe) —
    mismo criterio ya aplicado a `_RenombrarDialog`/`_pedir_texto` en el resto de la app."""

    def __init__(self, titulo, mensaje, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{_DIM};font-size:13px;")
        v.addWidget(lbl)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)


def _info(parent, titulo, mensaje):
    _InfoDialog(titulo, mensaje, parent).exec()


class AlmacenesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._main = main
        self.setStyleSheet(f"background:{_BG};")

        # Ubicación (lat/long) gateada a SUPERADMIN/ADMINISTRADOR — mismo patrón de resolución de
        # perfil que `menu_principal.py::MenuPrincipal.__init__` (usuario_actual.get("perfil", ...)
        # normalizado en mayúsculas), reutilizado tal cual en vez de inventar un mecanismo nuevo.
        self._perfil = str(self.usuario.get("perfil", "OPERARIO")).strip().upper()
        self._es_admin = self._perfil in ("SUPERADMIN", "ADMINISTRADOR")

        # La ventana se convierte en ANFITRIONA con pestañas (reutilizando su acceso de menú): la
        # primera pestaña es la gestión de almacenes actual; Distribución/Rutas hace su propia
        # consulta a BD durante la construcción. MRP/Fabricación y GMAO/Mantenimiento se EXTRAJERON
        # de aquí a módulos de nivel superior propios (tarjetas "Fabricación"/"Mantenimiento" en el
        # menú principal, v_id "mrp"/"gmao") — sus dashboards (`MRPDashboardWindow`/
        # `GMAODashboardWindow`) siguen intactos, solo cambió el punto de entrada.
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
        f.setSpacing(6)   # los pares etiqueta→campo se veían muy separados con el espaciado por defecto
        self.in_nombre = _inp("Nombre", 220); self.in_codigo = _inp("Código"); self.in_codigo.setFixedWidth(120)
        self.cmb_tipo = _combo([(t, t) for t in _TIPOS])
        self.cmb_tipo.setMinimumWidth(150)   # evita texto cortado en el desplegable
        f.addWidget(QLabel("Nombre:")); f.addWidget(self.in_nombre)
        f.addSpacing(18)
        f.addWidget(QLabel("Código:")); f.addWidget(self.in_codigo)
        f.addSpacing(18)
        f.addWidget(QLabel("Tipo:")); f.addWidget(self.cmb_tipo)
        f.addSpacing(18)
        f.addWidget(_btn("Crear", self._crear, primary=True))
        f.addSpacing(18)
        f.addWidget(_btn("Renombrar", self._renombrar, primary=True))
        f.addWidget(_btn("Activar", lambda: self._activar(True), primary=True))
        f.addWidget(_btn("Desactivar", lambda: self._activar(False), danger=True))
        f.addWidget(_btn("Eliminar", self._eliminar, danger=True))
        # Sin esto, las etiquetas (política de tamaño "Preferred", sin `setFixedWidth`) absorbían todo
        # el espacio sobrante de la fila en vez de quedarse en su tamaño natural — se veían enormes,
        # con el texto pegado a la izquierda y un hueco antes de su propio campo.
        f.addStretch()
        for w in (f.itemAt(i).widget() for i in range(f.count())):
            if isinstance(w, QLabel):
                w.setStyleSheet(f"color:{_DIM};")
        root.addLayout(f)

        self.tabla = _tabla(["id", "Nombre", "Código", "Tipo", "Tienda", "Estado", "Activo"])
        root.addWidget(self.tabla)

        # Primera pestaña: gestión de almacenes (contenido original, ligera). Distribución/Rutas hace
        # su propia consulta a BD durante la construcción, así que se carga de forma perezosa (lazy
        # loading: solo al visitarla) en vez de todo de golpe, que es lo que hacía tardar la apertura.
        # Envuelta en scroll de página completa (igual que Tareas/`workflow_gui.py::_add_tab`): sin
        # esto, en pantallas con escalado de Windows por encima del 100% el contenido (tabla de 7
        # columnas + fila de alta) podía quedar más ancho que el viewport real y recortarse sin forma
        # de alcanzarlo, en vez de poder desplazarse hasta él.
        self.tabs.addTab(self._envolver_scroll(_pagina), "Almacenes")
        entradas = []
        entradas.append(("Slotting / Rotación", lambda: self._envolver_scroll(self._construir_tab_slotting())))
        from src.gui.transiciones import instalar_pestanas_lazy
        instalar_pestanas_lazy(self.tabs, entradas)
        self._cargar()

    def _envolver_scroll(self, w):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        sc.setWidget(w)
        return sc

    # ── Slotting inteligente (WMS, sin coste externo) ──────────────────────────
    # El visor de "ruta óptima de preparación" que vivía aquí se RETIRÓ: es redundante con el que ya
    # ofrece el módulo "Distribución" del menú principal para los pickings que él mismo genera
    # (`services/expediciones.py::ruta_optima`, mismo motor `picking_ruta.ruta_picking`). Lo que NO
    # tiene equivalente en ningún otro módulo, y por eso se conserva aquí, es el análisis ABC/rotación
    # y sus sugerencias de intercambio de ubicación — ver `_slotting_aplicar` para la regla de
    # negocio de que son SOLO sugerencias, nunca una reasignación automática.
    def _construir_tab_slotting(self):
        w = QWidget(); ly = QVBoxLayout(w)
        lbl1 = QLabel("Distribución inteligente — coloca los productos de más rotación en las "
                     "ubicaciones más accesibles")
        lbl1.setWordWrap(True)
        ly.addWidget(lbl1)
        lbl2 = QLabel("Solo SUGERENCIAS: no reasignan nada por sí solas — hace falta seleccionar "
                     "una fila y pulsar «Aplicar intercambio» a propósito. Si una persona coloca "
                     "un artículo en una ubicación distinta a la sugerida, esa decisión manual "
                     "no se revierte ni se corrige automáticamente.")
        lbl2.setWordWrap(True)
        ly.addWidget(lbl2)
        bar = QHBoxLayout()
        bar.addWidget(_btn("🔎 Analizar", self._slotting_analizar, primary=True))
        bar.addWidget(_btn("↔ Aplicar intercambio", self._slotting_aplicar, primary=True))
        bar.addStretch()
        self.lbl_abc = QLabel(""); self.lbl_abc.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        bar.addWidget(self.lbl_abc)
        ly.addLayout(bar)
        self.tbl_slot = _tabla(["Producto", "Clase", "Rotación", "Ubicación actual",
                                "→ Intercambiar con", "Ubicación sugerida"])
        ly.addWidget(self.tbl_slot)
        return w

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
            _info(self, "Slotting", "Analiza y selecciona una recomendación.")
            return
        rec = recs[row]
        from src.services.inventario import slotting as SL
        if SL.aplicar_intercambio(rec["id_ubicacion"], rec["id_ubicacion_sugerida"],
                                  id_empresa=self._id_empresa()):
            _info(self, "Slotting",
                 f"Intercambio aplicado: {rec['codigo']} ↔ {rec['codigo_intercambio']}.")
            self._slotting_analizar()
        else:
            _info(self, "Slotting", "No se pudo aplicar el intercambio.")

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
            _info(self, "Almacenes", "Indica nombre y código."); return
        rid = SA.crear_almacen(nombre, codigo, self.cmb_tipo.currentData(),
                               id_empresa=self._id_empresa())
        if rid:
            self.in_nombre.clear(); self.in_codigo.clear(); self._cargar()
        else:
            _info(self, "Almacenes", "No se pudo crear (¿nombre/código duplicado?).")

    def _renombrar(self):
        a = self._sel()
        if not a:
            _info(self, "Almacenes", "Selecciona primero un almacén en la tabla.")
            return
        dlg = _RenombrarDialog(a.get("nombre") or "", self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.valor().strip():
            SA.actualizar_almacen(a["id"], id_empresa=self._id_empresa(), nombre=dlg.valor().strip())
            self._cargar()

    def _activar(self, activo):
        a = self._sel()
        if not a:
            _info(self, "Almacenes", "Selecciona primero un almacén en la tabla.")
            return
        SA.activar_almacen(a["id"], activo=activo, id_empresa=self._id_empresa())
        self._cargar()

    def _eliminar(self):
        a = self._sel()
        if not a:
            _info(self, "Almacenes", "Selecciona primero un almacén en la tabla.")
            return
        try:
            from assets.estilo_global import mostrar_confirmacion
            ok = mostrar_confirmacion(
                self, "Eliminar almacén",
                f"¿Eliminar el almacén «{a.get('nombre')}»? Se rechaza si todavía tiene existencias.")
        except Exception:
            ok = True
        if not ok:
            return
        r = SA.eliminar_almacen(a["id"], id_empresa=self._id_empresa())
        if r.get("ok"):
            self._cargar()
        else:
            _info(self, "Almacenes", r.get("error") or "No se pudo eliminar el almacén.")
