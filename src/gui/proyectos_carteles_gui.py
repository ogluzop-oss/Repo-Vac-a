"""
Carteles/Folletos publicitarios — 4ª pestaña del módulo Proyectos (incrustada por
`gui/proyectos_gui.py`). Galería de diseños + editor de lienzo interactivo (QGraphicsView) +
borrador asistido por el Asistente SOMA (IA). Solo orquesta: el CRUD vive en
`services.proyectos.carteles`, el renderizado PNG/PDF en `services.proyectos.render_cartel`.
"""

import logging
import os
import shutil
import uuid

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDoubleSpinBox,
                             QFileDialog, QFrame, QGraphicsEllipseItem, QGraphicsLineItem,
                             QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                             QGraphicsTextItem, QGraphicsView, QGridLayout, QHBoxLayout, QLabel,
                             QMessageBox, QPlainTextEdit, QScrollArea, QSpinBox,
                             QStackedWidget, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _BG2, _BORDE, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo, _inp
from src.services.proyectos import carteles as C
from src.services.proyectos import render_cartel as R

logger = logging.getLogger("gui.proyectos.carteles")

_ROJO = "#F85149"
_VERDE = "#22C55E"
_ESCALA_PX_MM = 3.0           # factor de pantalla: px por mm en el lienzo interactivo
_GRID_MM = 5.0                # paso de la rejilla de ajuste (snap to grid)
_MAX_IMAGEN_MB = 10


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _toast(parent, titulo, mensaje, nivel="info", ms=2400):
    """Aviso breve no modal que se cierra solo — mismo patrón ya usado en `gui/tpv.py::_toast`
    (SmartMessageDialog no modal), pero como función libre (no acoplada a ningún widget
    concreto de esta pantalla)."""
    try:
        from assets.estilo_global import SmartMessageDialog, aplicar_estilo_widget
        box = SmartMessageDialog(parent=parent, title=titulo, message=mensaje, level=nivel, buttons=[])
        box.setModal(False)
        try:
            aplicar_estilo_widget(box)
        except Exception:
            pass
        box.show()
        QTimer.singleShot(ms, box.close)
    except Exception as e:
        logger.debug("toast fallback (%s/%s): %s", titulo, mensaje, e)


def _confirmar(parent, titulo, mensaje) -> bool:
    try:
        from assets.estilo_global import mostrar_confirmacion
        return mostrar_confirmacion(parent, titulo, mensaje)
    except Exception:
        return QMessageBox.question(parent, titulo, mensaje) == QMessageBox.StandardButton.Yes


def _mm_a_px(v):
    return float(v or 0) * _ESCALA_PX_MM


def _px_a_mm(v):
    return float(v or 0) / _ESCALA_PX_MM


# ── Diálogo: elegir formato/orientación/título para un diseño nuevo ──────────────────────────
class _NuevoDisenoDialog(QDialog):
    def __init__(self, parent=None, *, titulo_ventana="Nuevo diseño"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(460)
        outer = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_CIAN};border-radius:15px;}}"
                           f"QLabel{{color:{_TEXT};border:none;font-weight:bold;background:transparent;}}")
        outer.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel(titulo_ventana); t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;")
        cab.addWidget(t); cab.addStretch(); cab.addWidget(_btn_x(self.reject))
        ly.addLayout(cab)

        ly.addWidget(QLabel("Título:"))
        self.inp_titulo = _inp("Nombre del diseño…")
        ly.addWidget(self.inp_titulo)

        ly.addWidget(QLabel("Formato:"))
        opciones = [(f["etiqueta"], clave) for clave, f in C.FORMATOS.items() if clave != "personalizado"]
        opciones.append(("Dimensiones personalizadas", "personalizado"))
        self.cmb_formato = _combo(opciones)
        self.cmb_formato.currentIndexChanged.connect(self._actualizar_visibilidad)
        ly.addWidget(self.cmb_formato)

        fila_orient = QHBoxLayout()
        fila_orient.addWidget(QLabel("Orientación:"))
        self.cmb_orientacion = _combo([("Vertical", "vertical"), ("Horizontal", "horizontal")])
        fila_orient.addWidget(self.cmb_orientacion)
        ly.addLayout(fila_orient)

        self._fila_custom = QHBoxLayout()
        self._fila_custom_w = QLabel("Ancho (mm):"); self._fila_custom.addWidget(self._fila_custom_w)
        self.inp_ancho = QDoubleSpinBox(); self.inp_ancho.setRange(10, 3000); self.inp_ancho.setValue(210)
        self._fila_custom.addWidget(self.inp_ancho)
        self._fila_custom_h = QLabel("Alto (mm):"); self._fila_custom.addWidget(self._fila_custom_h)
        self.inp_alto = QDoubleSpinBox(); self.inp_alto.setRange(10, 3000); self.inp_alto.setValue(297)
        self._fila_custom.addWidget(self.inp_alto)
        ly.addLayout(self._fila_custom)

        fila_dpi = QHBoxLayout()
        fila_dpi.addWidget(QLabel("Resolución de impresión (DPI):"))
        self.inp_dpi = QSpinBox(); self.inp_dpi.setRange(72, 600); self.inp_dpi.setValue(300)
        fila_dpi.addWidget(self.inp_dpi)
        ly.addLayout(fila_dpi)

        bar = QHBoxLayout()
        bar.addWidget(_btn("Crear diseño", self.accept, primary=True))
        ly.addLayout(bar)
        self._actualizar_visibilidad()

    def _actualizar_visibilidad(self):
        personalizado = self.cmb_formato.currentData() == "personalizado"
        for w in (self._fila_custom_w, self.inp_ancho, self._fila_custom_h, self.inp_alto):
            w.setVisible(personalizado)

    def datos(self) -> dict:
        return {"titulo": self.inp_titulo.text().strip() or "Sin título",
               "formato": self.cmb_formato.currentData(),
               "orientacion": self.cmb_orientacion.currentData(),
               "ancho_mm": self.inp_ancho.value() if self.cmb_formato.currentData() == "personalizado" else None,
               "alto_mm": self.inp_alto.value() if self.cmb_formato.currentData() == "personalizado" else None,
               "dpi": self.inp_dpi.value()}


# ── Diálogo: Generar con Asistente SOMA (IA) ──────────────────────────────────────────────────
class _AsistenteIADialog(_NuevoDisenoDialog):
    def __init__(self, parent=None):
        super().__init__(parent, titulo_ventana="✨ Generar con Asistente SOMA (IA)")
        # Inserta el campo de descripción justo encima del botón final.
        ly = self.layout().itemAt(0).widget().layout()
        ly.insertWidget(ly.count() - 1, QLabel("Describe brevemente tu cartel/folleto:"))
        self.txt_descripcion = QPlainTextEdit()
        self.txt_descripcion.setFixedHeight(70)
        self.txt_descripcion.setPlaceholderText(
            "Ej: Cartel A3 para promoción de menú del día en restaurante italiano con 20% de "
            "descuento los martes")
        self.txt_descripcion.setStyleSheet(
            f"QPlainTextEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px;}}QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        ly.insertWidget(ly.count() - 1, self.txt_descripcion)

    def datos(self) -> dict:
        d = super().datos()
        d["descripcion"] = self.txt_descripcion.toPlainText().strip()
        return d


# ── Escena del lienzo: snap-to-grid + notificación de selección ──────────────────────────────
class _CartelScene(QGraphicsScene):
    def __init__(self, tab):
        super().__init__()
        self._tab = tab

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not getattr(self._tab, "chk_snap", None) or not self._tab.chk_snap.isChecked():
            return
        paso_px = _mm_a_px(_GRID_MM)
        for item in self.selectedItems():
            if not (item.flags() & item.GraphicsItemFlag.ItemIsMovable):
                continue
            p = item.pos()
            nx = round(p.x() / paso_px) * paso_px
            ny = round(p.y() / paso_px) * paso_px
            item.setPos(nx, ny)


class CartelesTab(QWidget):
    """Pestaña completa (galería + editor) — rama funcional INDEPENDIENTE del tablero Kanban
    (los diseños no pertenecen a ningún proyecto; `id_proyecto` queda disponible en la capa de
    servicio para quien quiera asociarlos manualmente, pero la GUI nunca lo exige). `cargar()` se
    llama cada vez que se ENTRA en esta pestaña (vía `ProyectosWindow.tabs.currentChanged`) y
    siempre repone la vista de galería, aunque el usuario se hubiera quedado dentro del editor de
    otra visita anterior. `puede_fn(permiso) -> bool` gatea las acciones de escritura."""

    def __init__(self, usuario=None, puede_fn=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self._puede_fn = puede_fn or (lambda _p: True)
        self._cartel_actual = None
        self._contador_z = 0
        self._build()
        self._aplicar_permisos()

    # ── construcción ──
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 10, 0, 0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._construir_galeria())
        self.stack.addWidget(self._construir_editor())
        self.stack.setCurrentIndex(0)

    def _construir_galeria(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0)
        barra = QHBoxLayout()
        self._btn_nuevo = _btn("➕ Nuevo diseño", self._nuevo_diseno, primary=True)
        self._btn_ia = _btn("✨ Generar con Asistente SOMA (IA)", self._abrir_asistente_ia, primary=True)
        barra.addWidget(self._btn_nuevo); barra.addWidget(self._btn_ia); barra.addStretch()
        self.inp_buscar = _inp("Buscar diseños…")
        self.inp_buscar.textChanged.connect(self._cargar_galeria)
        self.cmb_filtro = _combo([("Todos los formatos", None), ("Carteles", "cartel"),
                                  ("Folletos", "folleto")])
        self.cmb_filtro.setMinimumWidth(190)   # evita que "Todos los formatos" se corte
        self.cmb_filtro.currentIndexChanged.connect(self._cargar_galeria)
        barra.addWidget(self.inp_buscar); barra.addWidget(self.cmb_filtro)
        ly.addLayout(barra)

        self._lbl_vacio = QLabel("Todavía no hay diseños. Crea el primero con «Nuevo diseño».")
        self._lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vacio.setStyleSheet(f"color:{_DIM};font-size:14px;font-weight:700;")
        ly.addWidget(self._lbl_vacio)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cont_grid = QWidget()
        self._grid = QGridLayout(self._cont_grid); self._grid.setSpacing(14)
        self._scroll.setWidget(self._cont_grid)
        ly.addWidget(self._scroll, 1)
        return w

    def _construir_editor(self):
        w = QWidget(); root = QVBoxLayout(w); root.setContentsMargins(0, 0, 0, 0)
        cab = QHBoxLayout()
        cab.addWidget(_btn("← Galería", self._volver_galeria))
        self.inp_titulo_cartel = _inp("Título del diseño")
        self.inp_titulo_cartel.editingFinished.connect(self._guardar_titulo)
        cab.addWidget(self.inp_titulo_cartel, 1)
        self._btn_guardar = _btn("💾 Guardar", self._guardar, primary=True)
        cab.addWidget(self._btn_guardar)
        cab.addWidget(_btn("📄 PDF", lambda: self._exportar("pdf")))
        cab.addWidget(_btn("🖼 PNG", lambda: self._exportar("png")))
        cab.addWidget(_btn("🖼 JPG", lambda: self._exportar("jpg")))
        root.addLayout(cab)

        barra = QHBoxLayout()
        barra.addWidget(_btn("🔤 Texto", self._anadir_texto, primary=True))
        barra.addWidget(_btn("🖼 Imagen", self._anadir_imagen, primary=True))
        barra.addWidget(_btn("▦ QR", self._anadir_qr, primary=True))
        barra.addWidget(_btn("▭ Rectángulo", lambda: self._anadir_forma("rectangulo"), primary=True))
        barra.addWidget(_btn("◯ Círculo", lambda: self._anadir_forma("circulo"), primary=True))
        barra.addWidget(_btn("╱ Línea", lambda: self._anadir_forma("linea"), primary=True))
        barra.addWidget(_btn("⬆ Al frente", self._traer_al_frente))
        barra.addWidget(_btn("⬇ Al fondo", self._enviar_al_fondo))
        barra.addWidget(_btn("🗑 Elemento", self._borrar_seleccion, danger=True))
        self.chk_sangrado = QCheckBox("Sangrado 3mm")
        self.chk_plegado = QCheckBox("Marcas de plegado")
        self.chk_snap = QCheckBox("Ajustar a rejilla")
        for chk, inicial in ((self.chk_sangrado, True), (self.chk_plegado, True), (self.chk_snap, False)):
            chk.setChecked(inicial)
            chk.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            chk.stateChanged.connect(self._refrescar_guias)
            barra.addWidget(chk)
        barra.addStretch()
        root.addLayout(barra)

        cuerpo = QHBoxLayout()
        self.view = QGraphicsView()
        self.view.setStyleSheet(
            f"QGraphicsView{{border:2px solid {_CIAN};background:#2B2F36;border-radius:12px;}}")
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene = _CartelScene(self)
        self.scene.selectionChanged.connect(self._actualizar_panel_propiedades)
        self.view.setScene(self.scene)
        cuerpo.addWidget(self.view, 3)

        self._panel = QFrame(); self._panel.setFixedWidth(260)
        self._panel.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}"
                                  f"QLabel{{color:{_TEXT};border:none;background:transparent;}}")
        self._panel_ly = QVBoxLayout(self._panel); self._panel_ly.setContentsMargins(12, 12, 12, 12)
        self._panel_ly.addWidget(QLabel("Propiedades"))
        self._panel_cuerpo = QVBoxLayout()
        self._panel_ly.addLayout(self._panel_cuerpo)
        self._panel_ly.addStretch()
        cuerpo.addWidget(self._panel, 1)
        root.addLayout(cuerpo, 1)
        return w

    # ── permisos ──
    def _puede(self, permiso):
        try:
            return self._puede_fn(permiso)
        except Exception:
            return True

    def _aplicar_permisos(self):
        gest = self._puede("proyectos.gestionar")
        for b in (self._btn_nuevo, self._btn_ia):
            b.setEnabled(gest)

    # ── entrada en la pestaña (llamado por ProyectosWindow al cambiar de pestaña) ──
    def cargar(self):
        """Repone siempre la vista de galería al entrar en la pestaña (aunque el usuario se
        hubiera quedado dentro del editor en una visita anterior) y recarga el listado."""
        self.stack.setCurrentIndex(0)
        self._cargar_galeria()

    # ── Galería ──
    def _limpiar_grid(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()

    def _cargar_galeria(self):
        self._limpiar_grid()
        filas = C.listar_carteles(id_empresa=_empresa(),
                                  texto=self.inp_buscar.text().strip() or None,
                                  tipo=self.cmb_filtro.currentData())
        if not filas:
            self._lbl_vacio.setText("Todavía no hay diseños. Crea el primero con «Nuevo diseño».")
            self._lbl_vacio.setVisible(True)
            self._scroll.setVisible(False)
            return
        self._lbl_vacio.setVisible(False)
        self._scroll.setVisible(True)
        cols = 3
        for i, c in enumerate(filas):
            self._grid.addWidget(self._tarjeta(c), i // cols, i % cols)

    def _miniatura_pixmap(self, c) -> QPixmap | None:
        ruta = c.get("thumbnail_path")
        if ruta and os.path.exists(ruta):
            pix = QPixmap(ruta)
            if not pix.isNull():
                return pix
        try:
            png = R.render_png(c["contenido"], dpi=72)
            img = QImage.fromData(png)
            return QPixmap.fromImage(img)
        except Exception as e:
            logger.debug("miniatura_pixmap(%s): %s", c.get("id"), e)
            return None

    def _tarjeta(self, c):
        f = QFrame(); f.setFixedWidth(220)
        f.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}"
                        f"QLabel{{border:none;background:transparent;}}")
        v = QVBoxLayout(f); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(6)
        lbl_img = QLabel(); lbl_img.setFixedSize(196, 140)
        lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_img.setStyleSheet(f"background:{_BG};border:1px solid {_BORDE};border-radius:6px;")
        pix = self._miniatura_pixmap(c)
        if pix:
            lbl_img.setPixmap(pix.scaled(196, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
        v.addWidget(lbl_img)
        tit = QLabel(c["titulo"]); tit.setWordWrap(True)
        tit.setStyleSheet(f"color:{_TEXT};font-weight:900;font-size:13px;")
        v.addWidget(tit)
        meta = QLabel(f"{c['tipo'].capitalize()} · {float(c['ancho_mm']):.0f}×{float(c['alto_mm']):.0f} mm "
                     f"· {c['orientacion'].capitalize()}")
        meta.setStyleSheet(f"color:{_DIM};font-size:11px;")
        v.addWidget(meta)
        mod = QLabel(f"Modificado: {str(c.get('modificado') or '')[:16]}")
        mod.setStyleSheet(f"color:{_DIM};font-size:10px;")
        v.addWidget(mod)
        acciones = QHBoxLayout(); acciones.setSpacing(4)
        acciones.addWidget(_btn("✏️", lambda _=None, cid=c["id"]: self._abrir_editor(cid), primary=True))
        acciones.addWidget(_btn("⧉", lambda _=None, cid=c["id"]: self._duplicar(cid)))
        acciones.addWidget(_btn("📄", lambda _=None, cid=c["id"]: self._exportar_desde_galeria(cid, "pdf")))
        acciones.addWidget(_btn("🖼", lambda _=None, cid=c["id"]: self._exportar_desde_galeria(cid, "png")))
        acciones.addWidget(_btn("🗑", lambda _=None, cid=c["id"]: self._eliminar(cid), danger=True))
        v.addLayout(acciones)
        return f

    def _nuevo_diseno(self):
        d = _NuevoDisenoDialog(self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        cid = C.crear_cartel(v["titulo"], formato=v["formato"], orientacion=v["orientacion"],
                             ancho_mm=v["ancho_mm"], alto_mm=v["alto_mm"], dpi=v["dpi"],
                             id_empresa=_empresa())
        if not cid:
            _toast(self, "Carteles", "Error al guardar los cambios.", "error")
            return
        _toast(self, "Carteles", "Diseño guardado correctamente.", "success")
        self._abrir_editor(cid)

    def _abrir_asistente_ia(self):
        d = _AsistenteIADialog(self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        if not v["descripcion"]:
            _toast(self, "Asistente SOMA", "Describe brevemente el cartel o folleto a generar.",
                  "warning")
            return
        cid = C.crear_cartel(v["titulo"], formato=v["formato"], orientacion=v["orientacion"],
                             ancho_mm=v["ancho_mm"], alto_mm=v["alto_mm"], dpi=v["dpi"],
                             id_empresa=_empresa())
        if not cid:
            _toast(self, "Carteles", "Error al guardar los cambios.", "error")
            return
        _toast(self, "Asistente SOMA", "Generando borrador con el Asistente SOMA…", "info", ms=1600)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        c = C.obtener_cartel(cid, id_empresa=_empresa())
        tipo = (C.FORMATOS.get(v["formato"]) or {}).get("tipo", "cartel")
        r = C.generar_copy_ia(v["descripcion"], tipo=tipo, usuario=self.usuario, id_empresa=_empresa())
        _MOTIVOS = {
            "sin_api_key": "El Asistente SOMA no tiene configurada la conexión con la IA.",
            "sin_contexto": "Falta contexto para generar el borrador.",
            "limite_ia": "Se ha alcanzado el límite de uso de IA de tu plan.",
            "respuesta_invalida": "El Asistente SOMA no pudo estructurar una respuesta válida.",
            "error_inesperado": "Error en la conexión con la API de SOMA.",
        }
        if r.get("ok"):
            layout = C.construir_layout_desde_copy(r, float(c["ancho_mm"]), float(c["alto_mm"]))
            C.actualizar_cartel(cid, id_empresa=_empresa(), contenido=layout, titulo=r["titulo"] or v["titulo"])
            _toast(self, "Asistente SOMA", "Borrador generado por SOMA correctamente.", "success")
        else:
            _toast(self, "Asistente SOMA",
                  _MOTIVOS.get(r.get("motivo"), "No se pudo generar el borrador con IA.") +
                  " Puedes seguir editando el diseño manualmente.", "error")
        self._abrir_editor(cid)

    def _duplicar(self, id_cartel):
        cid = C.duplicar_cartel(id_cartel, id_empresa=_empresa())
        if cid:
            C.generar_miniatura(cid, id_empresa=_empresa())
            _toast(self, "Carteles", "Diseño duplicado correctamente.", "success")
            self._cargar_galeria()
        else:
            _toast(self, "Carteles", "Error al guardar los cambios.", "error")

    def _eliminar(self, id_cartel):
        if _confirmar(self, "Eliminar diseño", "¿Eliminar este diseño publicitario?"):
            ok = C.eliminar_cartel(id_cartel, id_empresa=_empresa())
            _toast(self, "Carteles", "Diseño eliminado correctamente." if ok else
                  "Error al guardar los cambios.", "success" if ok else "error")
            self._cargar_galeria()

    def _exportar_desde_galeria(self, id_cartel, formato):
        self._exportar_cartel(id_cartel, formato)

    # ── Editor: apertura/guardado ──
    def _volver_galeria(self):
        self.stack.setCurrentIndex(0)
        self._cargar_galeria()

    def _abrir_editor(self, id_cartel):
        c = C.obtener_cartel(id_cartel, id_empresa=_empresa())
        if not c:
            _toast(self, "Carteles", "No se pudo abrir el diseño.", "error")
            return
        self._cartel_actual = c
        self.inp_titulo_cartel.setText(c["titulo"])
        self._pintar_lienzo(c["contenido"])
        self.stack.setCurrentIndex(1)

    def _guardar_titulo(self):
        if not self._cartel_actual:
            return
        nuevo = self.inp_titulo_cartel.text().strip() or "Sin título"
        self._cartel_actual["titulo"] = nuevo
        C.actualizar_cartel(self._cartel_actual["id"], id_empresa=_empresa(), titulo=nuevo)

    def _guardar(self):
        if not self._cartel_actual:
            return
        doc = self._exportar_modelo_desde_escena()
        ok = C.actualizar_cartel(self._cartel_actual["id"], id_empresa=_empresa(), contenido=doc,
                                 titulo=self.inp_titulo_cartel.text().strip() or "Sin título")
        if ok:
            C.generar_miniatura(self._cartel_actual["id"], id_empresa=_empresa())
            _toast(self, "Carteles", "Diseño guardado correctamente.", "success")
        else:
            _toast(self, "Carteles", "Error al guardar los cambios.", "error")

    def _exportar(self, formato):
        if self._cartel_actual:
            self._guardar()
            self._exportar_cartel(self._cartel_actual["id"], formato)

    def _exportar_cartel(self, id_cartel, formato):
        c = C.obtener_cartel(id_cartel, id_empresa=_empresa())
        if not c:
            _toast(self, "Carteles", "No se pudo exportar el diseño.", "error")
            return
        if formato == "pdf":
            _toast(self, "Carteles", "Generando marcas de corte para imprenta…", "info", ms=1500)
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            ruta_sugerida, _ = QFileDialog.getSaveFileName(
                self, "Exportar PDF para imprenta", f"{c['titulo']}.pdf", "PDF (*.pdf)")
            if not ruta_sugerida:
                return
            ok, resultado = C.exportar_pdf(id_cartel, ruta_sugerida, id_empresa=_empresa())
            _toast(self, "Carteles", "PDF exportado a 300 DPI con éxito." if ok else
                  "Error al guardar los cambios.", "success" if ok else "error")
        else:
            _toast(self, "Carteles", "Ajustando resolución a 300 DPI…", "info", ms=1200)
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            ext = "jpg" if formato == "jpg" else "png"
            ruta_sugerida, _ = QFileDialog.getSaveFileName(
                self, "Exportar imagen", f"{c['titulo']}.{ext}", f"{ext.upper()} (*.{ext})")
            if not ruta_sugerida:
                return
            ok, resultado = C.exportar_imagen(id_cartel, ruta_sugerida, formato=ext.upper(),
                                              dpi=150, id_empresa=_empresa())
            _toast(self, "Carteles",
                  f"Imagen exportada correctamente ({ext.upper()})." if ok else
                  "Error al guardar los cambios.", "success" if ok else "error")

    # ── Lienzo: pintado y guías ──
    def _pintar_lienzo(self, doc):
        self.scene.clear()
        ancho_px, alto_px = _mm_a_px(doc["ancho_mm"]), _mm_a_px(doc["alto_mm"])
        self.scene.setSceneRect(-200, -200, ancho_px + 400, alto_px + 400)
        fondo = QGraphicsRectItem(0, 0, ancho_px, alto_px)
        fondo.setBrush(QColor(doc.get("fondo_color") or "#FFFFFF"))
        fondo.setPen(QPen(Qt.PenStyle.NoPen))
        fondo.setZValue(-1000)
        fondo.setFlag(fondo.GraphicsItemFlag.ItemIsSelectable, False)
        self.scene.addItem(fondo)
        self._fondo_item = fondo
        self._doc_modo = doc.get("modo")
        self._doc_dims_mm = (doc["ancho_mm"], doc["alto_mm"])

        self._contador_z = 0
        for el in sorted(doc.get("elementos") or [], key=lambda e: e.get("z", 0)):
            item = self._crear_item(el)
            if item is not None:
                self.scene.addItem(item)
                self._contador_z = max(self._contador_z, int(el.get("z", 0)))
        self._refrescar_guias()
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._actualizar_panel_propiedades()

    def _refrescar_guias(self):
        if not getattr(self, "_fondo_item", None):
            return
        for item in list(self.scene.items()):
            if item.data(1) == "guia":
                self.scene.removeItem(item)
        ancho_px, alto_px = _mm_a_px(self._doc_dims_mm[0]), _mm_a_px(self._doc_dims_mm[1])
        if self.chk_sangrado.isChecked():
            s = _mm_a_px(3)
            guia = QGraphicsRectItem(-s, -s, ancho_px + 2 * s, alto_px + 2 * s)
            pen = QPen(QColor("#F85149")); pen.setStyle(Qt.PenStyle.DashLine); pen.setWidthF(1.2)
            guia.setPen(pen); guia.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            guia.setFlag(guia.GraphicsItemFlag.ItemIsSelectable, False)
            guia.setZValue(900); guia.setData(1, "guia")
            self.scene.addItem(guia)
        if self.chk_plegado.isChecked() and self._doc_modo in ("diptico", "triptico"):
            cortes = [self._doc_dims_mm[0] / 2] if self._doc_modo == "diptico" else \
                [self._doc_dims_mm[0] / 3, 2 * self._doc_dims_mm[0] / 3]
            for x_mm in cortes:
                x = _mm_a_px(x_mm)
                linea = QGraphicsLineItem(x, 0, x, alto_px)
                pen = QPen(QColor("#8B949E")); pen.setStyle(Qt.PenStyle.DashLine); pen.setWidthF(1)
                linea.setPen(pen)
                linea.setFlag(linea.GraphicsItemFlag.ItemIsSelectable, False)
                linea.setZValue(900); linea.setData(1, "guia")
                self.scene.addItem(linea)

    # ── Creación de items a partir del modelo de contenido ──
    def _crear_item(self, el):
        tipo = el.get("tipo")
        x, y, w, h = _mm_a_px(el.get("x")), _mm_a_px(el.get("y")), _mm_a_px(el.get("w")), _mm_a_px(el.get("h"))
        item = None
        try:
            if tipo == "texto":
                item = QGraphicsTextItem(el.get("texto") or "")
                negrita = "negrita" in (el.get("fuente") or "")
                f = QFont("Arial", max(6, int(el.get("tamano_pt") or 14)))
                f.setBold(negrita)
                item.setFont(f)
                item.setDefaultTextColor(QColor(el.get("color") or "#000000"))
                if w > 0:
                    item.setTextWidth(w)
                item.setPos(x, y)
            elif tipo == "imagen" and el.get("ruta") and os.path.exists(el["ruta"]):
                pix = QPixmap(el["ruta"])
                if w > 0 and h > 0:
                    pix = pix.scaled(int(w), int(h), Qt.AspectRatioMode.IgnoreAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                item = QGraphicsPixmapItem(pix)
                item.setPos(x, y)
            elif tipo == "qr" and el.get("payload"):
                item = QGraphicsPixmapItem(self._qr_pixmap(el["payload"], int(w) or 100, int(h) or 100))
                item.setPos(x, y)
            elif tipo == "forma":
                forma = el.get("forma")
                color = QColor(el.get("color") or "#000000")
                relleno = bool(el.get("relleno"))
                grosor = max(1.0, _mm_a_px(el.get("grosor_mm") or 1))
                pen = QPen(color); pen.setWidthF(grosor)
                if forma == "rectangulo":
                    item = QGraphicsRectItem(0, 0, w, h)
                elif forma == "circulo":
                    item = QGraphicsEllipseItem(0, 0, w, h)
                elif forma == "linea":
                    item = QGraphicsLineItem(0, 0, w, h)
                if item is not None:
                    item.setPen(pen)
                    if forma != "linea":
                        item.setBrush(color if relleno else QBrush(Qt.BrushStyle.NoBrush))
                    item.setPos(x, y)
        except Exception as e:
            logger.debug("crear_item(%s): %s", tipo, e)
            return None
        if item is None:
            return None
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setZValue(el.get("z", 0))
        item.setData(0, dict(el))
        return item

    @staticmethod
    def _qr_pixmap(payload, w, h) -> QPixmap:
        import io
        import qrcode
        buf = io.BytesIO()
        qrcode.make(payload).save(buf, format="PNG")
        img = QImage.fromData(buf.getvalue())
        return QPixmap.fromImage(img).scaled(max(1, w), max(1, h), Qt.AspectRatioMode.IgnoreAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)

    def _siguiente_z(self):
        self._contador_z += 1
        return self._contador_z

    def _items_de_contenido(self):
        return [it for it in self.scene.items() if it.data(1) != "guia" and it is not getattr(
            self, "_fondo_item", None)]

    # ── Añadir elementos ──
    def _anadir_texto(self):
        if not self._cartel_actual:
            return
        el = {"tipo": "texto", "x": 10, "y": 10, "w": 100, "h": 20, "texto": "Texto",
             "fuente": "regular", "tamano_pt": 18, "color": "#111111", "alineacion": "izquierda",
             "interlineado": 1.2, "z": self._siguiente_z()}
        item = self._crear_item(el)
        if item:
            self.scene.addItem(item)
            self.scene.clearSelection()
            item.setSelected(True)

    def _anadir_imagen(self):
        if not self._cartel_actual:
            return
        ruta, _f = QFileDialog.getOpenFileName(self, "Insertar imagen", "",
                                               "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not ruta:
            return
        try:
            if os.path.getsize(ruta) > _MAX_IMAGEN_MB * 1024 * 1024:
                _toast(self, "Carteles",
                      f"El archivo de imagen excede el tamaño máximo permitido ({_MAX_IMAGEN_MB} MB).",
                      "error")
                return
        except OSError:
            pass
        destino = self._copiar_imagen_a_assets(ruta)
        if not destino:
            _toast(self, "Carteles", "Error al guardar los cambios.", "error")
            return
        pix = QPixmap(destino)
        w_mm, h_mm = 60.0, 60.0 * (pix.height() / pix.width()) if pix.width() else 60.0
        el = {"tipo": "imagen", "x": 10, "y": 10, "w": w_mm, "h": h_mm, "ruta": destino,
             "z": self._siguiente_z()}
        item = self._crear_item(el)
        if item:
            self.scene.addItem(item)
            self.scene.clearSelection()
            item.setSelected(True)

    def _copiar_imagen_a_assets(self, ruta_origen) -> str | None:
        try:
            id_cartel = (self._cartel_actual or {}).get("id", "temp")
            base = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "documentos", "proyectos", "carteles", "assets", str(id_cartel))
            os.makedirs(base, exist_ok=True)
            ext = os.path.splitext(ruta_origen)[1] or ".png"
            destino = os.path.join(base, f"{uuid.uuid4().hex}{ext}")
            shutil.copyfile(ruta_origen, destino)
            return destino
        except Exception as e:
            logger.error("copiar_imagen_a_assets: %s", e)
            return None

    def _anadir_qr(self):
        if not self._cartel_actual:
            return
        from PyQt6.QtWidgets import QInputDialog
        payload, ok = QInputDialog.getText(self, "Código QR", "URL, promoción o datos de contacto:")
        if not ok or not payload.strip():
            return
        el = {"tipo": "qr", "x": 10, "y": 10, "w": 30, "h": 30, "payload": payload.strip(),
             "z": self._siguiente_z()}
        item = self._crear_item(el)
        if item:
            self.scene.addItem(item)
            self.scene.clearSelection()
            item.setSelected(True)

    def _anadir_forma(self, forma):
        if not self._cartel_actual:
            return
        dims = {"rectangulo": (40, 25), "circulo": (30, 30), "linea": (50, 0)}[forma]
        el = {"tipo": "forma", "forma": forma, "x": 10, "y": 10, "w": dims[0], "h": dims[1],
             "color": "#00FFC6", "relleno": forma != "linea" and False, "grosor_mm": 1,
             "z": self._siguiente_z()}
        item = self._crear_item(el)
        if item:
            self.scene.addItem(item)
            self.scene.clearSelection()
            item.setSelected(True)

    def _traer_al_frente(self):
        for item in self.scene.selectedItems():
            self._contador_z += 1
            item.setZValue(self._contador_z)

    def _enviar_al_fondo(self):
        for item in self.scene.selectedItems():
            item.setZValue(-1)

    def _borrar_seleccion(self):
        for item in self.scene.selectedItems():
            self.scene.removeItem(item)
        self._actualizar_panel_propiedades()

    # ── Panel de propiedades ──
    def _limpiar_panel(self):
        while self._panel_cuerpo.count():
            it = self._panel_cuerpo.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
            elif it.layout():
                self._vaciar_layout(it.layout())

    @staticmethod
    def _vaciar_layout(layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()

    def _actualizar_panel_propiedades(self):
        self._limpiar_panel()
        seleccion = self.scene.selectedItems() if hasattr(self, "scene") else []
        if not seleccion:
            self._panel_cuerpo.addWidget(QLabel("Selecciona un elemento del lienzo."))
            return
        item = seleccion[0]
        datos = item.data(0) or {}
        tipo = datos.get("tipo")

        self._panel_cuerpo.addWidget(QLabel(f"Tipo: {tipo or '—'}"))
        if tipo == "texto":
            txt = QPlainTextEdit(datos.get("texto") or "")
            txt.setFixedHeight(70)
            txt.textChanged.connect(lambda: self._aplicar_texto(item, txt.toPlainText()))
            self._panel_cuerpo.addWidget(QLabel("Texto:")); self._panel_cuerpo.addWidget(txt)

            fila_t = QHBoxLayout()
            spin_tam = QSpinBox(); spin_tam.setRange(6, 200)
            spin_tam.setValue(int(datos.get("tamano_pt") or 14))
            spin_tam.valueChanged.connect(lambda v: self._aplicar_tamano_texto(item, v))
            fila_t.addWidget(QLabel("Tamaño pt:")); fila_t.addWidget(spin_tam)
            self._panel_cuerpo.addLayout(fila_t)

            cmb_align = _combo([("Izquierda", "izquierda"), ("Centro", "centro"),
                                ("Derecha", "derecha")], datos.get("alineacion") or "izquierda")
            cmb_align.currentIndexChanged.connect(
                lambda: self._aplicar_dato(item, "alineacion", cmb_align.currentData()))
            self._panel_cuerpo.addWidget(QLabel("Alineación:")); self._panel_cuerpo.addWidget(cmb_align)

            chk_negrita = QCheckBox("Negrita"); chk_negrita.setChecked("negrita" in (datos.get("fuente") or ""))
            chk_negrita.setStyleSheet(f"color:{_TEXT};")
            chk_negrita.stateChanged.connect(lambda v: self._aplicar_negrita(item, bool(v)))
            self._panel_cuerpo.addWidget(chk_negrita)

            self._panel_cuerpo.addWidget(_btn("🎨 Color de texto", lambda: self._elegir_color(item)))
        elif tipo == "qr":
            inp = _inp(""); inp.setText(datos.get("payload") or "")
            self._panel_cuerpo.addWidget(QLabel("Contenido del QR:")); self._panel_cuerpo.addWidget(inp)
            self._panel_cuerpo.addWidget(_btn("Actualizar QR", lambda: self._regenerar_qr(item, inp.text())))
        elif tipo == "imagen":
            self._panel_cuerpo.addWidget(_btn("🖼 Cambiar imagen", lambda: self._cambiar_imagen(item)))
        elif tipo == "forma":
            self._panel_cuerpo.addWidget(_btn("🎨 Color", lambda: self._elegir_color(item)))
            chk_relleno = QCheckBox("Relleno"); chk_relleno.setChecked(bool(datos.get("relleno")))
            chk_relleno.setStyleSheet(f"color:{_TEXT};")
            chk_relleno.stateChanged.connect(lambda v: self._aplicar_relleno(item, bool(v)))
            self._panel_cuerpo.addWidget(chk_relleno)

        self._panel_cuerpo.addWidget(QLabel("Posición y tamaño (mm):"))
        fila_xy = QHBoxLayout()
        spin_x = QDoubleSpinBox(); spin_x.setRange(-500, 5000); spin_x.setValue(_px_a_mm(item.pos().x()))
        spin_y = QDoubleSpinBox(); spin_y.setRange(-500, 5000); spin_y.setValue(_px_a_mm(item.pos().y()))
        spin_x.valueChanged.connect(lambda v: item.setPos(_mm_a_px(v), item.pos().y()))
        spin_y.valueChanged.connect(lambda v: item.setPos(item.pos().x(), _mm_a_px(v)))
        fila_xy.addWidget(QLabel("X")); fila_xy.addWidget(spin_x)
        fila_xy.addWidget(QLabel("Y")); fila_xy.addWidget(spin_y)
        self._panel_cuerpo.addLayout(fila_xy)

        if tipo in ("imagen", "qr", "forma"):
            fila_wh = QHBoxLayout()
            ancho_actual, alto_actual = self._tamano_actual_mm(item)
            spin_w = QDoubleSpinBox(); spin_w.setRange(1, 5000); spin_w.setValue(ancho_actual)
            spin_h = QDoubleSpinBox(); spin_h.setRange(0, 5000); spin_h.setValue(alto_actual)
            spin_w.valueChanged.connect(lambda v: self._aplicar_tamano(item, v, spin_h.value()))
            spin_h.valueChanged.connect(lambda v: self._aplicar_tamano(item, spin_w.value(), v))
            fila_wh.addWidget(QLabel("Ancho")); fila_wh.addWidget(spin_w)
            fila_wh.addWidget(QLabel("Alto")); fila_wh.addWidget(spin_h)
            self._panel_cuerpo.addLayout(fila_wh)

    def _tamano_actual_mm(self, item):
        if isinstance(item, QGraphicsPixmapItem):
            return _px_a_mm(item.pixmap().width()), _px_a_mm(item.pixmap().height())
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            r = item.rect()
            return _px_a_mm(r.width()), _px_a_mm(r.height())
        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            return _px_a_mm(ln.dx()), _px_a_mm(ln.dy())
        return 0.0, 0.0

    def _aplicar_dato(self, item, clave, valor):
        d = item.data(0) or {}
        d[clave] = valor
        item.setData(0, d)

    def _aplicar_texto(self, item, texto):
        item.setPlainText(texto)
        self._aplicar_dato(item, "texto", texto)

    def _aplicar_tamano_texto(self, item, pt):
        f = item.font(); f.setPointSize(pt); item.setFont(f)
        self._aplicar_dato(item, "tamano_pt", pt)

    def _aplicar_negrita(self, item, negrita):
        f = item.font(); f.setBold(negrita); item.setFont(f)
        self._aplicar_dato(item, "fuente", "negrita" if negrita else "regular")

    def _elegir_color(self, item):
        d = item.data(0) or {}
        col = QColorDialog.getColor(QColor(d.get("color") or "#000000"), self, "Elegir color")
        if not col.isValid():
            return
        hexcolor = col.name()
        self._aplicar_dato(item, "color", hexcolor)
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(col)
        elif isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem)):
            pen = item.pen(); pen.setColor(col); item.setPen(pen)
            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)) and (d.get("relleno")):
                item.setBrush(col)

    def _aplicar_relleno(self, item, relleno):
        self._aplicar_dato(item, "relleno", relleno)
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            item.setBrush(item.pen().color() if relleno else QBrush(Qt.BrushStyle.NoBrush))

    def _regenerar_qr(self, item, payload):
        payload = (payload or "").strip()
        if not payload:
            return
        w, h = item.pixmap().width(), item.pixmap().height()
        item.setPixmap(self._qr_pixmap(payload, w, h))
        self._aplicar_dato(item, "payload", payload)

    def _cambiar_imagen(self, item):
        ruta, _f = QFileDialog.getOpenFileName(self, "Cambiar imagen", "",
                                               "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not ruta:
            return
        try:
            if os.path.getsize(ruta) > _MAX_IMAGEN_MB * 1024 * 1024:
                _toast(self, "Carteles",
                      f"El archivo de imagen excede el tamaño máximo permitido ({_MAX_IMAGEN_MB} MB).",
                      "error")
                return
        except OSError:
            pass
        destino = self._copiar_imagen_a_assets(ruta)
        if not destino:
            return
        w, h = item.pixmap().width(), item.pixmap().height()
        item.setPixmap(QPixmap(destino).scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        self._aplicar_dato(item, "ruta", destino)

    def _aplicar_tamano(self, item, ancho_mm, alto_mm):
        w_px, h_px = _mm_a_px(ancho_mm), _mm_a_px(alto_mm)
        if isinstance(item, QGraphicsPixmapItem):
            d = item.data(0) or {}
            pix = QPixmap(d.get("ruta")) if d.get("ruta") and os.path.exists(d.get("ruta") or "") else item.pixmap()
            item.setPixmap(pix.scaled(max(1, int(w_px)), max(1, int(h_px)),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        elif isinstance(item, QGraphicsRectItem):
            item.setRect(0, 0, w_px, h_px)
        elif isinstance(item, QGraphicsEllipseItem):
            item.setRect(0, 0, w_px, h_px)
        elif isinstance(item, QGraphicsLineItem):
            item.setLine(0, 0, w_px, h_px)

    # ── Exportar el modelo de contenido desde el estado actual de la escena ──
    def _exportar_modelo_desde_escena(self) -> dict:
        elementos = []
        for item in self._items_de_contenido():
            d = dict(item.data(0) or {})
            if not d.get("tipo"):
                continue
            d["x"] = _px_a_mm(item.pos().x())
            d["y"] = _px_a_mm(item.pos().y())
            d["z"] = item.zValue()
            if d["tipo"] == "texto":
                d["w"] = _px_a_mm(item.textWidth() if item.textWidth() > 0 else item.boundingRect().width())
                d["h"] = _px_a_mm(item.boundingRect().height())
            else:
                w_mm, h_mm = self._tamano_actual_mm(item)
                d["w"], d["h"] = w_mm, h_mm
            elementos.append(d)
        ancho_mm, alto_mm = self._doc_dims_mm
        return {"ancho_mm": ancho_mm, "alto_mm": alto_mm, "modo": self._doc_modo,
               "fondo_color": "#FFFFFF", "elementos": elementos}
