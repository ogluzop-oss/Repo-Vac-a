"""
Lotes y caducidades (INV.3) — GUI de existencias por lote, alertas de caducidad,
entrada manual de lotes y Rastreo (búsqueda por lote + Track & Trace).

Pantalla dentro de INVENTARIO (no modifica las existentes). Solo consulta + entrada
manual de lotes (el consumo FEFO ocurre automáticamente en ventas/mermas/inventario).
Multiempresa por contexto activo. Reutiliza helpers de catalogo_gestion.

Punto 3 bis (Rastreo): ubicación CANÓNICA del buscador por número de lote + Panel de Rastreo (
proveedor de origen, pedido B2B/clásico, ubicación, distribución a clientes, estado de bloqueo) —
vive AQUÍ, dentro de la pestaña "Lotes" del módulo de Stock (`mostrar_stock`), no en Logística.
Reutiliza ÍNTEGRAMENTE `services.calidad.trazabilidad.trazabilidad_lote/trazabilidad_articulo`
(mismo motor de datos que ya usa la pestaña Trazabilidad de Calidad — no se duplica su lógica de
consulta, solo se repite el patrón de presentación con los widgets propios de esta pantalla).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QScrollArea, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.db import lotes
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_cargando, _btn_x, _inp, _tabla)
from src.gui.components.completer_articulos import instalar_sugerencias_articulo

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
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        # Visual: el borde gris fino del QSS global (`QTabWidget::pane{border:1px solid ...}`)
        # envuelve todo el área de contenido de la pestaña activa — se anula SOLO en esta
        # instancia (no se toca el QSS global, que usan el resto de pantallas de la app).
        tabs.setStyleSheet("QTabWidget::pane{border:none;}")
        tabs.addTab(self._tab_stock(), "Existencias por lote")
        tabs.addTab(self._tab_alertas(), "Alertas de caducidad")
        tabs.addTab(self._tab_rastreo(), "Rastreo")
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
        f.addWidget(_btn("🔍", self._buscar, primary=True))
        f.addWidget(_btn("Entrada de lote", self._entrada, primary=True))
        f.addWidget(_btn("🔒 Bloquear lote", self._bloquear, danger=True))
        f.addWidget(_btn("🔓 Desbloquear lote", self._desbloquear, success=True))
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
                it = _it(v)
                if j == 0:
                    it.setData(Qt.ItemDataRole.UserRole, l.get("id"))
                self.tabla.setItem(i, j, it)

    def _lote_seleccionado(self):
        row = self.tabla.currentRow()
        if row < 0:
            return None, None
        it = self.tabla.item(row, 0)
        id_lote = it.data(Qt.ItemDataRole.UserRole) if it else None
        estado_it = self.tabla.item(row, 5)
        estado = estado_it.text() if estado_it else ""
        return id_lote, estado

    # ── bloqueo/desbloqueo (Punto 3 · INV.3/FEFO) ──
    def _bloquear(self):
        id_lote, estado = self._lote_seleccionado()
        if id_lote is None:
            QMessageBox.warning(self, "Bloquear lote", "Selecciona primero un lote en la tabla.")
            return
        if str(estado).strip().lower() == "bloqueado":
            QMessageBox.information(self, "Bloquear lote", "Ese lote ya está bloqueado.")
            return
        motivo, ok = QInputDialog.getText(
            self, "Bloquear lote",
            "Motivo del bloqueo (p. ej. NC abierta, cuarentena, retirada del proveedor):")
        if not ok or not motivo.strip():
            return
        if lotes.bloquear_lote(id_lote, motivo.strip(),
                              usuario=(self.usuario or {}).get("nombre"),
                              id_empresa=self._id_empresa()):
            self._buscar()
        else:
            QMessageBox.warning(self, "Bloquear lote", "No se pudo bloquear el lote.")

    def _desbloquear(self):
        id_lote, estado = self._lote_seleccionado()
        if id_lote is None:
            QMessageBox.warning(self, "Desbloquear lote", "Selecciona primero un lote en la tabla.")
            return
        if str(estado).strip().lower() != "bloqueado":
            QMessageBox.information(self, "Desbloquear lote", "Ese lote no está bloqueado.")
            return
        if lotes.desbloquear_lote(id_lote, usuario=(self.usuario or {}).get("nombre"),
                                  id_empresa=self._id_empresa()):
            self._buscar()
        else:
            QMessageBox.warning(self, "Desbloquear lote", "No se pudo desbloquear el lote.")

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
        f.addWidget(_btn_cargando("Actualizar", self._alertas, primary=True))
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

    # ── Rastreo (búsqueda por lote + Track & Trace) ──
    def _tab_rastreo(self):
        """Búsqueda por ID de lote (numérico) o código de artículo + panel completo de rastreo:
        proveedor de origen (clásico o Smart Suppliers B2B), pedido, ubicación, estado de bloqueo
        y distribución a clientes (ventas). Reutiliza `services.calidad.trazabilidad` — no
        reimplementa ninguna consulta."""
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.in_rastreo = _inp("Lote (ID numérico) o código de artículo")
        instalar_sugerencias_articulo(self.in_rastreo)
        f.addWidget(self.in_rastreo)
        f.addWidget(_btn("🔍", self._buscar_rastreo, primary=True))
        f.addWidget(_btn("🔒 Bloquear lote", self._bloquear_rastreo, danger=True))
        f.addWidget(_btn("🔓 Desbloquear lote", self._desbloquear_rastreo, success=True))
        f.addStretch()
        ly.addLayout(f)

        # El buscador queda fijo arriba (fuera del área con scroll, igual que la barra de
        # acciones en `horarios_gui.py`); las 4 tablas apiladas debajo sí pueden exceder la
        # altura visible, así que viven dentro de un QScrollArea — mismo patrón que usa
        # `recepcion_pale.py` (objectName "scroll_transparente", que engancha con las reglas
        # QSS globales de `assets/estilo_global.py`: fondo/borde transparentes para el
        # QScrollArea y su contenedor, y la barra de scroll cian ya estilada globalmente por
        # `QSS_SCROLLBARS`). No se define ningún QSS de scrollbar nuevo aquí.
        scroll = QScrollArea()
        scroll.setObjectName("scroll_transparente")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cont = QWidget()
        cont.setObjectName("scroll_transparente")
        cly = QVBoxLayout(cont)

        self.lbl_rastreo = QLabel(""); self.lbl_rastreo.setStyleSheet(f"color:{_DIM};")
        self.lbl_rastreo.setWordWrap(True)
        cly.addWidget(self.lbl_rastreo)
        self.lbl_rastreo_origen = QLabel("")
        self.lbl_rastreo_origen.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        self.lbl_rastreo_origen.setWordWrap(True)
        cly.addWidget(self.lbl_rastreo_origen)

        lbl_dist = QLabel("Distribución a clientes (ventas)")
        lbl_dist.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        cly.addWidget(lbl_dist)
        self.tbl_rastreo_dist = _tabla(["Venta", "Fecha", "Cantidad", "Empleado", "Caja"])
        cly.addWidget(self.tbl_rastreo_dist)

        lbl_mov = QLabel("Movimientos"); lbl_mov.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        cly.addWidget(lbl_mov)
        self.tbl_rastreo_mov = _tabla(["Fecha", "Tipo", "Cantidad", "Observaciones"])
        cly.addWidget(self.tbl_rastreo_mov)

        lbl_insp = QLabel("Inspecciones de calidad")
        lbl_insp.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        cly.addWidget(lbl_insp)
        self.tbl_rastreo_insp = _tabla(["ID", "Fase", "Resultado", "Fecha"])
        cly.addWidget(self.tbl_rastreo_insp)

        lbl_nc = QLabel("No conformidades")
        lbl_nc.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        cly.addWidget(lbl_nc)
        self.tbl_rastreo_nc = _tabla(["ID", "Código", "Severidad", "Estado"])
        cly.addWidget(self.tbl_rastreo_nc)

        scroll.setWidget(cont)
        ly.addWidget(scroll)
        return w

    def _f_fecha(self, v):
        return str(v)[:16] if v is not None else ""

    def _buscar_rastreo(self):
        texto = self.in_rastreo.text().strip()
        if "–" in texto:  # viene del autocompletado "CÓDIGO – NOMBRE"
            texto = texto.split("–")[0].strip()
        if not texto:
            QMessageBox.information(self, "Rastreo", "Introduce un lote (ID numérico) o un código de artículo.")
            return
        from src.services.calidad import trazabilidad
        eid = self._id_empresa()
        datos = None
        if texto.isdigit():
            try:
                datos = trazabilidad.trazabilidad_lote(int(texto), id_empresa=eid)
            except Exception as e:
                logger.error("trazabilidad_lote: %s", e)
        if not datos or not any(datos.get(k) for k in ("movimientos", "inspecciones", "no_conformidades")):
            try:
                datos = trazabilidad.trazabilidad_articulo(texto, id_empresa=eid)
            except Exception as e:
                logger.error("trazabilidad_articulo: %s", e)
                datos = {}
        datos = datos or {}

        movs = datos.get("movimientos") or []
        self.tbl_rastreo_mov.setRowCount(len(movs))
        for i, x in enumerate(movs):
            for j, v in enumerate([self._f_fecha(x.get("fecha")), x.get("tipo"), x.get("cantidad"),
                                   x.get("observaciones")]):
                self.tbl_rastreo_mov.setItem(i, j, _it(v))
        insp = datos.get("inspecciones") or []
        self.tbl_rastreo_insp.setRowCount(len(insp))
        for i, x in enumerate(insp):
            for j, v in enumerate([x.get("id"), x.get("fase"), x.get("resultado"),
                                   self._f_fecha(x.get("fecha"))]):
                self.tbl_rastreo_insp.setItem(i, j, _it(v))
        ncs = datos.get("no_conformidades") or []
        self.tbl_rastreo_nc.setRowCount(len(ncs))
        for i, x in enumerate(ncs):
            for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("severidad"), x.get("estado")]):
                self.tbl_rastreo_nc.setItem(i, j, _it(v))
        dist = datos.get("distribucion_ventas") or []
        self.tbl_rastreo_dist.setRowCount(len(dist))
        for i, x in enumerate(dist):
            for j, v in enumerate([x.get("venta_id"), self._f_fecha(x.get("fecha")), x.get("cantidad"),
                                   x.get("empleado"), x.get("numero_caja")]):
                self.tbl_rastreo_dist.setItem(i, j, _it(v))

        msg = f"{len(movs)} movimiento(s) · {len(insp)} inspección(es) · {len(ncs)} NC"
        of_origen = datos.get("of_origen")
        if of_origen:
            msg += f" · OF origen: {of_origen.get('codigo')}"
        self.lbl_rastreo.setText(msg)

        self._rastreo_id_lote = int(texto) if texto.isdigit() else None
        self._rastreo_bloqueado = bool(datos.get("bloqueado"))
        partes = []
        if datos.get("lote") is not None:
            partes.append("🔒 BLOQUEADO" if self._rastreo_bloqueado else "🟢 Activo")
            if datos.get("ubicacion") is not None:
                partes.append(f"Almacén: {datos.get('ubicacion')}")
        origen_compra = datos.get("origen_compra")
        if origen_compra:
            prov = origen_compra.get("proveedor")
            if not prov and origen_compra.get("id_proveedor"):
                prov = f"proveedor #{origen_compra.get('id_proveedor')}"
            if not prov and origen_compra.get("id_suministrador"):
                prov = f"proveedor B2B #{origen_compra.get('id_suministrador')}"
            if prov:
                partes.append(f"Proveedor origen: {prov}")
            if origen_compra.get("origen") == "compra_b2b" and origen_compra.get("id_tx"):
                partes.append(f"Pedido B2B: {origen_compra.get('id_tx')}")
            elif origen_compra.get("numero_pedido") or origen_compra.get("id_pedido"):
                partes.append(f"Pedido: {origen_compra.get('numero_pedido') or origen_compra.get('id_pedido')}")
        self.lbl_rastreo_origen.setText("  ·  ".join(partes))

    def _bloquear_rastreo(self):
        id_lote = getattr(self, "_rastreo_id_lote", None)
        if id_lote is None:
            QMessageBox.warning(self, "Bloquear lote", "Busca primero un lote por su ID numérico.")
            return
        if getattr(self, "_rastreo_bloqueado", False):
            QMessageBox.information(self, "Bloquear lote", "Ese lote ya está bloqueado.")
            return
        motivo, ok = QInputDialog.getText(
            self, "Bloquear lote",
            "Motivo del bloqueo (p. ej. NC abierta, cuarentena, retirada del proveedor):")
        if not ok or not motivo.strip():
            return
        if lotes.bloquear_lote(id_lote, motivo.strip(), usuario=(self.usuario or {}).get("nombre"),
                               id_empresa=self._id_empresa()):
            self._buscar_rastreo()
        else:
            QMessageBox.warning(self, "Bloquear lote", "No se pudo bloquear el lote.")

    def _desbloquear_rastreo(self):
        id_lote = getattr(self, "_rastreo_id_lote", None)
        if id_lote is None:
            QMessageBox.warning(self, "Desbloquear lote", "Busca primero un lote por su ID numérico.")
            return
        if not getattr(self, "_rastreo_bloqueado", False):
            QMessageBox.information(self, "Desbloquear lote", "Ese lote no está bloqueado.")
            return
        if lotes.desbloquear_lote(id_lote, usuario=(self.usuario or {}).get("nombre"),
                                  id_empresa=self._id_empresa()):
            self._buscar_rastreo()
        else:
            QMessageBox.warning(self, "Desbloquear lote", "No se pudo desbloquear el lote.")
