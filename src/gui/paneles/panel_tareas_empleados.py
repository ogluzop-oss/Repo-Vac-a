"""
Tareas de tienda — contenido embebido en el módulo "Tareas" (restructuración Aprobaciones/Tareas,
2026-09). Reemplaza a la antigua pestaña "Pendientes" (movida al nuevo módulo "Aprobaciones") con un
concepto distinto: no aprobación de acciones del sistema, sino encargos que un SUPERADMIN programa para
el personal de una tienda concreta (ver `services.tareas_empleados`).

Vista por rol (mismo panel, contenido distinto):
- SUPERADMIN: programa tareas para la tienda a la que esté conectado en ese momento (selector de
  tienda ya existente, F1/`SelectorTiendaDialog`) — sin tienda conectada, no hay a quién asignar.
- OPERARIO/ADMINISTRADOR: ve solo las tareas de SU PROPIA tienda (`usuario.centro_codigo`), de solo
  lectura salvo "Marcar como finalizada".
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QTableWidgetItem, QTextEdit, QVBoxLayout,
                             QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _TEXT, _btn, _btn_cargando,
                                      _combo, _dialogo_frameless, _inp, _tabla)

logger = logging.getLogger("gui.paneles.tareas_empleados")

_FRECUENCIAS = [("Puntual", "puntual"), ("Diaria", "diaria"), ("Semanal", "semanal"),
               ("Mensual", "mensual")]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class _DescripcionDialog(QDialog):
    """Ver la descripción completa de una tarea (la celda de la tabla la recorta visualmente) — con
    edición opcional in-situ, sin diálogos anidados. Reutiliza `_dialogo_frameless` (misma cabecera
    con ✕ para cerrar que el resto de la app) — el botón "Cerrar" del pie es una segunda vía,
    explícitamente pedida, sobre la misma acción."""

    def __init__(self, titulo_tarea, descripcion, *, editable, parent=None):
        super().__init__(parent)
        self.guardar_solicitado = False
        self.nueva_descripcion = None
        self._en_edicion = False
        v = _dialogo_frameless(self, f"Descripción — {titulo_tarea}", ancho=480)
        self.txt = QTextEdit()
        self.txt.setPlainText(descripcion or "(sin descripción)")
        self.txt.setReadOnly(True)
        self.txt.setMinimumHeight(220)
        self.txt.setStyleSheet(f"QTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                               "border-radius:8px;padding:8px;font-size:13px;}"
                               f"QTextEdit:focus{{border-color:{_CIAN};}}")
        v.addWidget(self.txt)
        if editable:
            self.btn_editar = _btn("✏️ Editar", self._alternar_edicion, primary=True)
            # El relleno simétrico (14px) del botón compartido deja de más el lado izquierdo —el
            # emoji del lápiz ya trae su propio margen visual—, así que aquí se recorta solo ese
            # lado; el derecho conserva el mismo relleno que el resto de botones de la app.
            self.btn_editar.setStyleSheet(
                self.btn_editar.styleSheet() + "QPushButton{padding:0 14px 0 6px;}")
            fila = QHBoxLayout()
            fila.addStretch()
            fila.addWidget(self.btn_editar)
            v.addLayout(fila)

    def _alternar_edicion(self):
        if not self._en_edicion:
            self._en_edicion = True
            if self.txt.toPlainText() == "(sin descripción)":
                self.txt.clear()
            self.txt.setReadOnly(False)
            self.txt.setFocus()
            self.btn_editar.setText("💾 Guardar cambios")
        else:
            self.nueva_descripcion = self.txt.toPlainText()
            self.guardar_solicitado = True
            self.accept()


class PanelTareasEmpleados(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = id_empresa
        self.setStyleSheet(f"background:{_BG};")
        self._id_tienda_activa = None
        self._sel_tarea = None
        root = QVBoxLayout(self)
        if str(self.usuario.get("perfil", "")).upper() == "SUPERADMIN":
            self._build_superadmin(root)
        else:
            self._build_empleado(root)

    # ── SUPERADMIN: programación por tienda conectada ───────────────────────
    def _tienda_conectada(self):
        try:
            from src.db.empresa import tienda_actual_id
            return tienda_actual_id()
        except Exception:
            return None

    def _nombre_tienda(self, id_tienda):
        try:
            from src.db import tiendas as tiendas_db
            t = tiendas_db.obtener_tienda(id_tienda)
            if t:
                return f"{t.get('codigo_tienda', '')} · {t.get('nombre', '')}".strip(" ·")
        except Exception:
            pass
        return str(id_tienda)

    def _build_superadmin(self, root):
        self.lbl_tienda = QLabel("")
        self.lbl_tienda.setStyleSheet(f"color:{_CIAN};font-size:13px;font-weight:700;")
        cab = QHBoxLayout()
        cab.addWidget(self.lbl_tienda); cab.addStretch()
        root.addLayout(cab)

        bar = QHBoxLayout()
        self.in_titulo = _inp("Título de la tarea", 260)
        self.cmb_frec = _combo(_FRECUENCIAS)
        self.cmb_frec.setFixedWidth(140)
        self.in_desc = _inp("Descripción (opcional)", 260)
        bar.addWidget(QLabel("Título:")); bar.addWidget(self.in_titulo)
        bar.addWidget(QLabel("Frecuencia:")); bar.addWidget(self.cmb_frec)
        bar.addWidget(self.in_desc)
        bar.addStretch()
        root.addLayout(bar)

        bar2 = QHBoxLayout()
        bar2.addStretch()
        bar2.addWidget(_btn_cargando("🔄  Actualizar", self._cargar, primary=True))
        bar2.addWidget(_btn("Cambiar de centro", self._cambiar_tienda, primary=True))
        bar2.addWidget(_btn("Programar tarea", self._crear, primary=True))
        bar2.addWidget(_btn("Cancelar tarea", self._cancelar, danger=True))
        root.addLayout(bar2)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.status)

        self.tbl = _tabla(["ID", "Título", "Descripción", "Frecuencia", "Estado", "Creada"])
        self.tbl.cellClicked.connect(self._sel)
        self.tbl.cellDoubleClicked.connect(lambda r, c: self._ver_descripcion(r, c, editable=True))
        root.addWidget(self.tbl)

        self._refrescar_tienda()

    def _cambiar_tienda(self):
        from src.gui.selector_tienda import SelectorTiendaDialog
        dlg = SelectorTiendaDialog(self)
        dlg.exec()
        if dlg.get_resultado():
            self._refrescar_tienda()

    def _refrescar_tienda(self):
        tid = self._tienda_conectada()
        if not tid:
            self.lbl_tienda.setText("Sin tienda conectada — pulsa «Cambiar de centro» y elige una tienda.")
            self._id_tienda_activa = None
            self.tbl.setRowCount(0)
            return
        self.lbl_tienda.setText(f"Programando tareas para: {self._nombre_tienda(tid)}")
        self._id_tienda_activa = tid
        self._cargar()

    def _crear(self):
        from src.services import tareas_empleados as TE
        titulo = self.in_titulo.text()
        r = TE.crear_tarea(self._id_tienda_activa, titulo, descripcion=self.in_desc.text(),
                           frecuencia=self.cmb_frec.currentData(), creado_por=self.usuario.get("id"))
        if r.get("ok"):
            self.status.setStyleSheet(f"color:{_CIAN};font-size:11px;")
            self.status.setText(f"Tarea «{titulo}» programada.")
            self.in_titulo.clear(); self.in_desc.clear()
            self._cargar()
        else:
            self.status.setStyleSheet("color:#FF5C5C;font-size:11px;")
            self.status.setText(r.get("error", "No se pudo programar."))

    def _cancelar(self):
        if not self._sel_tarea:
            return
        if not self._confirmar("Cancelar tarea",
                               "¿Seguro que quieres cancelar esta tarea? Desaparecerá de esta lista "
                               "y de la del personal de la tienda."):
            return
        from src.services import tareas_empleados as TE
        r = TE.cancelar_tarea(self._sel_tarea)
        self.status.setStyleSheet((f"color:{_CIAN};" if r.get("ok") else "color:#FF5C5C;") + "font-size:11px;")
        self.status.setText("Tarea cancelada." if r.get("ok") else r.get("error", ""))
        if r.get("ok"):
            self._cargar()

    # ── OPERARIO/ADMINISTRADOR: lista de solo lectura + marcar finalizada ──
    def _build_empleado(self, root):
        tid = self.usuario.get("centro_codigo")
        self._id_tienda_activa = tid
        cab = QHBoxLayout()
        lbl = QLabel("Tareas programadas para tu tienda" if tid else
                     "Tu usuario no tiene tienda asignada.")
        lbl.setStyleSheet(f"color:{_CIAN};font-size:13px;font-weight:700;")
        cab.addWidget(lbl); cab.addStretch()
        cab.addWidget(_btn_cargando("🔄  Actualizar", self._cargar, primary=True))
        root.addLayout(cab)

        bar2 = QHBoxLayout()
        bar2.addStretch()
        bar2.addWidget(_btn("Marcar como finalizada", self._completar, primary=True))
        root.addLayout(bar2)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.status)

        self.tbl = _tabla(["ID", "Título", "Descripción", "Frecuencia", "Estado", "Creada"])
        self.tbl.cellClicked.connect(self._sel)
        self.tbl.cellDoubleClicked.connect(lambda r, c: self._ver_descripcion(r, c, editable=False))
        root.addWidget(self.tbl)

        if tid:
            self._cargar()

    def _completar(self):
        if not self._sel_tarea:
            return
        from src.services import tareas_empleados as TE
        r = TE.completar_tarea(self._sel_tarea, usuario_id=self.usuario.get("id"))
        self.status.setStyleSheet((f"color:{_CIAN};" if r.get("ok") else "color:#FF5C5C;") + "font-size:11px;")
        self.status.setText("Tarea marcada como finalizada." if r.get("ok") else r.get("error", ""))
        if r.get("ok"):
            self._cargar()

    # ── Compartido ────────────────────────────────────────────────────────
    def _confirmar(self, titulo, mensaje) -> bool:
        try:
            from assets.estilo_global import mostrar_confirmacion
            return mostrar_confirmacion(self, titulo, mensaje)
        except Exception:
            from PyQt6.QtWidgets import QMessageBox
            return QMessageBox.question(self, titulo, mensaje) == QMessageBox.StandardButton.Yes

    def _sel(self, row, _c):
        try:
            self._sel_tarea = int(self.tbl.item(row, 0).text())
        except Exception:
            self._sel_tarea = None

    def _ver_descripcion(self, row, col, *, editable):
        if col != 2:   # solo la columna "Descripción"
            return
        id_item = self.tbl.item(row, 0)
        titulo_item = self.tbl.item(row, 1)
        desc_item = self.tbl.item(row, 2)
        if id_item is None:
            return
        try:
            id_tarea = int(id_item.text())
        except (TypeError, ValueError):
            return
        titulo = titulo_item.text() if titulo_item else ""
        descripcion = desc_item.text() if desc_item else ""
        dlg = _DescripcionDialog(titulo, descripcion, editable=editable, parent=self)
        dlg.exec()
        if dlg.guardar_solicitado:
            from src.services import tareas_empleados as TE
            r = TE.actualizar_descripcion(id_tarea, dlg.nueva_descripcion)
            self.status.setStyleSheet((f"color:{_CIAN};" if r.get("ok") else "color:#FF5C5C;")
                                      + "font-size:11px;")
            self.status.setText("Descripción actualizada." if r.get("ok") else r.get("error", ""))
            if r.get("ok"):
                self._cargar()

    def _cargar(self):
        from src.services import tareas_empleados as TE
        if not self._id_tienda_activa:
            return
        filas = TE.listar_tareas_tienda(self._id_tienda_activa)
        self.tbl.setRowCount(len(filas))
        for i, f in enumerate(filas):
            vals = [f.get("id"), f.get("titulo"), f.get("descripcion"), f.get("frecuencia"),
                    f.get("estado"), f.get("fecha_creacion")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _it(v))
