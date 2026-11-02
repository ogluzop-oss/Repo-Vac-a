"""
Gestión de proyectos — GUI (v_id "proyectos").

Tablero Kanban (mover tareas ← →), Cronograma (Gantt-lite por fechas), Horas y costes, y rentabilidad en
vivo. Solo orquesta: toda la lógica vive en `services/proyectos`. RBAC `proyectos.*`.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo, _inp,
                                      _tabla)
from src.gui.proyectos_carteles_gui import CartelesTab
from src.services.proyectos import proyectos as P
from src.services.proyectos import seguimiento as S
from src.services.proyectos import tareas as T

logger = logging.getLogger("gui.proyectos")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _confirmar(titulo, mensaje, parent) -> bool:
    """Confirmación con el diálogo neón propio de la app en vez de `QMessageBox` (nativo del SO): no
    solo por coherencia visual — un `QMessageBox.question` nativo se ha visto cerrar la app entera sin
    aviso alguno en la ventana de Proyectos (interacción con la superposición SIEMPRE-ENCIMA de SOMA
    y/o con esta ventana sin marco, no reproducible de forma aislada). `mostrar_confirmacion` usa un
    `QDialog` propio de la app, ya probado de forma fiable en el resto de diálogos de confirmación."""
    try:
        from assets.estilo_global import mostrar_confirmacion
        return mostrar_confirmacion(parent, titulo, mensaje)
    except Exception:
        return QMessageBox.question(parent, titulo, mensaje) == QMessageBox.StandardButton.Yes


_PRIO_COLOR = {"alta": "#F85149", "media": "#F5A623", "baja": "#2ECC71"}


class _FormDialog(QDialog):
    """Diálogo de formulario genérico. `campos`: lista de dicts {key,label,tipo,default,opciones}."""

    def __init__(self, parent, titulo, campos):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(440)
        from PyQt6.QtCore import QTimer

        from src.gui.catalogo_gestion import centrar_en_pantalla
        QTimer.singleShot(0, lambda: centrar_en_pantalla(self))
        self._w = {}
        outer = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_CIAN};border-radius:15px;}}"
                           f"QLabel{{color:{_TEXT};border:none;font-weight:bold;background:transparent;}}")
        outer.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(10)
        # Cabecera con título + "X" roja (cierra = Cancelar) — el botón "Cancelar" separado junto a la
        # X era redundante (mismo criterio ya aplicado en `tesoreria_gui._PedirTextoDialog`).
        cab = QHBoxLayout()
        t = QLabel(titulo); t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn_x(self.reject))
        ly.addLayout(cab)
        for c in campos:
            ly.addWidget(QLabel(c["label"]))
            tipo = c.get("tipo", "text")
            if tipo == "combo":
                w = _combo(c["opciones"], c.get("default"))
            else:
                w = _inp(c.get("ph", "")); w.setText("" if c.get("default") is None else str(c["default"]))
            self._w[c["key"]] = (w, tipo)
            ly.addWidget(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Guardar", self.accept, primary=True))
        ly.addLayout(bar)

    def datos(self):
        out = {}
        for k, (w, tipo) in self._w.items():
            out[k] = w.currentData() if tipo == "combo" else w.text().strip()
        return out


class ProyectosWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._pid = None
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Proyectos · Kanban · Rentabilidad")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t)
        cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        # Barra de selección/gestión de proyecto: en su PROPIA fila, justo debajo del título (antes
        # compartía fila con el título; a petición del usuario baja aquí, al sitio que antes ocupaba
        # el texto de estado vacío "Sin proyectos. Crea uno para empezar." — ese texto ya no hace
        # falta con el selector+botones a la vista en esta misma posición, ver `_pintar_rentabilidad`).
        barra_proy = QHBoxLayout()
        self.cmb_proy = _combo([]); self.cmb_proy.setMinimumWidth(240)
        self.cmb_proy.currentIndexChanged.connect(self._cambiar_proyecto)
        barra_proy.addWidget(QLabel("Proyecto:")); barra_proy.addWidget(self.cmb_proy)
        self._btn_nuevo = _btn("➕ Nuevo proyecto", self._nuevo_proyecto, primary=True)
        self._btn_edit = _btn("✏️ Editar", self._editar_proyecto, primary=True)
        self._btn_del = _btn("🗑 Eliminar", self._eliminar_proyecto, danger=True)
        barra_proy.addWidget(self._btn_nuevo); barra_proy.addWidget(self._btn_edit)
        barra_proy.addWidget(self._btn_del)
        barra_proy.addStretch()
        root.addLayout(barra_proy)

        self.lbl_rent = QLabel("")
        self.lbl_rent.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        root.addWidget(self.lbl_rent)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; }")
        # El botón "Nueva tarea" vive en una barra PROPIA del tablero (fuera de las cabeceras de
        # columna, que antes lo llevaban solo en "Pendiente" y descuadraba su altura frente a las
        # otras 3) y fuera de `_kanban_host`, que `_pintar_kanban` vacía y repinta por completo en
        # cada refresco — si viviera dentro, desaparecería en cada repintado.
        self._tab_kanban = QWidget()
        _kanban_ly = QVBoxLayout(self._tab_kanban)
        _kanban_ly.setContentsMargins(0, 12, 0, 0)   # separa el botón de la pestaña de arriba
        _kanban_ly.setSpacing(12)                    # y de las columnas de abajo, a partes iguales
        _barra_kanban = QHBoxLayout()
        self._btn_nueva_tarea = _btn("➕ Nueva tarea", self._nueva_tarea, primary=True)
        _barra_kanban.addWidget(self._btn_nueva_tarea)
        _barra_kanban.addStretch()
        _kanban_ly.addLayout(_barra_kanban)
        self._kanban_host = QVBoxLayout()
        _kanban_ly.addLayout(self._kanban_host)
        self.tabs.addTab(self._tab_kanban, "Tablero (Kanban)")
        self.tbl_crono = _tabla(["Tarea", "Estado", "Inicio", "Fin", "Cronograma"])
        _tab_crono = QWidget()
        _crono_ly = QVBoxLayout(_tab_crono)
        _crono_ly.setContentsMargins(0, 12, 0, 0)   # separa la tabla de la pestaña de arriba
        _crono_ly.addWidget(self.tbl_crono)
        self.tabs.addTab(_tab_crono, "Cronograma")
        self.tabs.addTab(self._tab_seguimiento(), "Horas y costes")
        self._tab_carteles = CartelesTab(usuario=self.usuario, puede_fn=self._puede, parent=self)
        self.tabs.addTab(self._tab_carteles, "Carteles/Folletos publicitarios")

        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo, todas visibles
        # por defecto; sin acceso completo (entró solo por una concesión de pestaña suelta), solo
        # la(s) concedida(s).
        from src.services.seguridad import pestanas_app
        _tiene_completo = pestanas_app.tiene_modulo_completo("proyectos", self.usuario, False)
        for _i, _slug in enumerate(["kanban", "cronograma", "seguimiento", "carteles"]):
            if not pestanas_app.visible(f"proyectos.{_slug}", self.usuario, _tiene_completo):
                self.tabs.setTabVisible(_i, False)

        # Carteles/Folletos publicitarios es una rama funcional independiente del tablero Kanban
        # (no depende de `self._pid`) — se repone a la vista de galería cada vez que se ENTRA en
        # la pestaña, en vez de sincronizarse con `_refrescar()` (que es del proyecto Kanban).
        self.tabs.currentChanged.connect(self._al_cambiar_pestana)

        root.addWidget(self.tabs)

        self._aplicar_permisos()
        self._cargar_proyectos()
        self._tab_carteles.cargar()

    # ── permisos ──
    def _puede(self, permiso):
        try:
            from src.services.autorizacion import puede
            return puede(self.usuario, permiso)
        except Exception:
            return True

    def _aplicar_permisos(self):
        gest = self._puede("proyectos.gestionar")
        for b in (self._btn_nuevo, self._btn_edit, self._btn_del, self._btn_nueva_tarea):
            b.setEnabled(gest)

    # ── selección de proyecto ──
    def _cargar_proyectos(self, sel_id=None):
        # `blockSignals` envuelve TAMBIÉN el `setCurrentIndex` de abajo: sin esto, seleccionar un
        # proyecto que no sea el primero dispara `currentIndexChanged` → `_cambiar_proyecto` →
        # `_refrescar()` AQUÍ, y el `_refrescar()` explícito de la línea final lo repite una segunda
        # vez — pintando el tablero Kanban dos veces seguidas (fuente del solapamiento visual al
        # cambiar de proyecto).
        self.cmb_proy.blockSignals(True)
        self.cmb_proy.clear()
        proys = P.listar_proyectos(id_empresa=_empresa())
        for p in proys:
            self.cmb_proy.addItem(f"{p['nombre']}  ·  {p['estado']}", p["id"])
        if proys:
            idx = self.cmb_proy.findData(sel_id) if sel_id else 0
            self.cmb_proy.setCurrentIndex(idx if idx >= 0 else 0)
            self._pid = self.cmb_proy.currentData()
        else:
            self._pid = None
        self.cmb_proy.blockSignals(False)
        self._refrescar()

    def _cambiar_proyecto(self):
        self._pid = self.cmb_proy.currentData()
        self._refrescar()

    def _refrescar(self):
        self._pintar_rentabilidad()
        self._pintar_kanban()
        self._pintar_cronograma()
        self._cargar_seguimiento()

    def _al_cambiar_pestana(self, indice):
        if self.tabs.widget(indice) is self._tab_carteles:
            self._tab_carteles.cargar()

    def _pintar_rentabilidad(self):
        if not self._pid:
            self.lbl_rent.setText("")
            return
        r = S.rentabilidad(self._pid, id_empresa=_empresa()) or {}
        m = r.get("margen", 0)
        pct = r.get("margen_pct")
        color = "#2ECC71" if (m or 0) >= 0 else "#F85149"
        self.lbl_rent.setText(
            f"Presupuesto: {r.get('presupuesto', 0):.2f} €   ·   Coste real: {r.get('coste_total', 0):.2f} € "
            f"(horas {r.get('coste_horas', 0):.2f} € + extra {r.get('coste_extra', 0):.2f} €)   ·   "
            f"Horas: {r.get('horas_totales', 0):.2f} h")
        self.lbl_rent.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        self.lbl_rent.setText(self.lbl_rent.text() + "   ·   ")
        # margen destacado por color (segundo label embebido no; usamos rich text)
        self.lbl_rent.setText(
            f"<span style='color:{_DIM}'>Presupuesto {r.get('presupuesto', 0):.2f} € · "
            f"Coste real {r.get('coste_total', 0):.2f} € · Horas {r.get('horas_totales', 0):.2f} h · </span>"
            f"<span style='color:{color};font-weight:900'>Margen {m:.2f} €"
            f"{'' if pct is None else f' ({pct:.1f}%)'}</span>")

    # ── Kanban ──
    def _pintar_kanban(self):
        # `deleteLater()` por sí solo NO retira el widget de la vista al instante (solo agenda su
        # destrucción C++ para el próximo ciclo del bucle de eventos): al cambiar de proyecto varias
        # veces seguidas, el tablero VIEJO puede quedar visible y solaparse con el nuevo hasta que
        # ese ciclo llega. `setParent(None)` sí es inmediato y lo desengancha de la jerarquía visual
        # ya en esta misma pasada; `deleteLater()` se mantiene para la limpieza C++ segura.
        while self._kanban_host.count():
            it = self._kanban_host.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if not self._pid:
            # Sin proyecto seleccionado: mensaje-guía (antes quedaba en blanco y parecía roto).
            ph = QLabel("Crea o selecciona un proyecto para ver su tablero Kanban.")
            ph.setStyleSheet(f"color:{_DIM};font-size:14px;font-weight:700;")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._kanban_host.addWidget(ph)
            return
        cont = QWidget(); fila = QHBoxLayout(cont); fila.setSpacing(12)
        tab = T.tablero(self._pid, id_empresa=_empresa())
        gest = self._puede("proyectos.gestionar")
        for ci, col in enumerate(T.COLUMNAS):
            colw = QWidget(); colv = QVBoxLayout(colw); colv.setSpacing(8)
            cab = QHBoxLayout()
            h = QLabel(f"{T.COLUMNA_ETIQUETA[col]}  ({len(tab[col])})")
            h.setStyleSheet(f"color:{_CIAN};font-weight:900;")
            cab.addWidget(h); cab.addStretch()
            colv.addLayout(cab)
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet(f"QScrollArea{{background:{_BG2};border:none;}}"
                                 f"QScrollArea > QWidget > QWidget{{background:{_BG2};}}")
            inner = QWidget(); inner.setStyleSheet(f"background:{_BG2};")
            iv = QVBoxLayout(inner); iv.setSpacing(8); iv.setContentsMargins(8, 8, 8, 8)
            for t in tab[col]:
                iv.addWidget(self._card(t, ci, gest))
            iv.addStretch()
            scroll.setWidget(inner)
            # Esquinas redondeadas + contorno neón turquesa coherente con el resto de la app (antes:
            # borde gris plano de 1px) — mismo mecanismo ya usado por las tablas estilizadas
            # (`instalar_corner_cover`), que enmascara el overlay a solo el anillo+esquinas realmente
            # pintados (ver `assets/estilo_global.py::_mascara_solo_esquinas`) para que nunca pueda
            # interceptar clics reales aunque Windows lo promueva a ventana nativa.
            try:
                from assets.estilo_global import instalar_corner_cover
                instalar_corner_cover(scroll, radius=14, bg=_BG2, border=_CIAN)
            except Exception:
                pass
            colv.addWidget(scroll)
            fila.addWidget(colw)
        self._kanban_host.addWidget(cont)

    def _card(self, t, ci, gest):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{_BG};border:1px solid {_BORDE};border-radius:8px;}}"
                        f"QLabel{{border:none;background:transparent;}}")
        v = QVBoxLayout(f); v.setContentsMargins(10, 8, 10, 8); v.setSpacing(4)
        tit = QLabel(t["titulo"]); tit.setWordWrap(True)
        tit.setStyleSheet(f"color:{_TEXT};font-weight:bold;")
        v.addWidget(tit)
        prio = t.get("prioridad", "media")
        meta = QLabel(f"● {prio}" + (f"  ·  {t['responsable']}" if t.get("responsable") else ""))
        meta.setStyleSheet(f"color:{_PRIO_COLOR.get(prio, _DIM)};font-size:11px;font-weight:bold;")
        v.addWidget(meta)
        if gest:
            row = QHBoxLayout(); row.setSpacing(4)
            if ci > 0:
                btn_izq = _btn("←", lambda _=None, i=t["id"]: self._mover(i, -1), primary=True)
                btn_izq.setStyleSheet(btn_izq.styleSheet() + "QPushButton{padding-bottom:1px;}")
                row.addWidget(btn_izq)
            if ci < len(T.COLUMNAS) - 1:
                btn_der = _btn("→", lambda _=None, i=t["id"]: self._mover(i, 1), primary=True)
                btn_der.setStyleSheet(btn_der.styleSheet() + "QPushButton{padding-bottom:1px;}")
                row.addWidget(btn_der)
            row.addStretch()
            btn_edit = _btn("✏️", lambda _=None, tt=t: self._editar_tarea(tt), primary=True)
            btn_edit.setStyleSheet(btn_edit.styleSheet() + "QPushButton{padding-bottom:1px;}")
            row.addWidget(btn_edit)
            row.addWidget(_btn("🗑", lambda _=None, i=t["id"]: self._borrar_tarea(i), danger=True))
            v.addLayout(row)
        return f

    def _mover(self, id_tarea, delta):
        # calcula la columna destino a partir de la actual
        actual = next((t for t in T.listar_tareas(self._pid, id_empresa=_empresa()) if t["id"] == id_tarea),
                      None)
        if not actual:
            return
        idx = T.COLUMNAS.index(actual["estado"]) + delta
        if 0 <= idx < len(T.COLUMNAS):
            T.mover_tarea(id_tarea, T.COLUMNAS[idx], id_empresa=_empresa())
            self._refrescar()

    def _nueva_tarea(self):
        if not self._pid:
            self._avisar_seleccion()
            return
        d = _FormDialog(self, "Nueva tarea", [
            {"key": "titulo", "label": "Título:"},
            {"key": "prioridad", "label": "Prioridad:", "tipo": "combo",
             "opciones": [("Baja", "baja"), ("Media", "media"), ("Alta", "alta")], "default": "media"},
            {"key": "responsable", "label": "Responsable (opcional):"},
            {"key": "fecha_inicio", "label": "Inicio (YYYY-MM-DD, opcional):"},
            {"key": "fecha_fin", "label": "Fin (YYYY-MM-DD, opcional):"},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        if not v["titulo"]:
            return
        tid = T.crear_tarea(self._pid, v["titulo"], prioridad=v["prioridad"] or "media",
                            responsable=v["responsable"] or None, fecha_inicio=v["fecha_inicio"] or None,
                            fecha_fin=v["fecha_fin"] or None, id_empresa=_empresa())
        # Antes no se comprobaba el resultado: si la creación fallaba (p. ej. error de BD), el
        # tablero se "refrescaba" igual y quedaba tal cual estaba, sin ningún aviso — parecía que la
        # tarea sencillamente no aparecía, sin ninguna pista de qué había pasado.
        if tid:
            self._aviso("Tarea creada correctamente.", "success")
        else:
            self._aviso("No se pudo crear la tarea.", "error")
        self._refrescar()

    def _editar_tarea(self, t):
        # `T.actualizar_tarea` no tenía ningún botón que lo llamara — el tablero solo permitía
        # mover ← → o eliminar, nunca corregir título/prioridad/responsable/fechas sin borrar y
        # recrear la tarea (huella de la auditoría app-wide).
        d = _FormDialog(self, f"Editar tarea — {t['titulo']}", [
            {"key": "titulo", "label": "Título:", "default": t.get("titulo")},
            {"key": "prioridad", "label": "Prioridad:", "tipo": "combo",
             "opciones": [("Baja", "baja"), ("Media", "media"), ("Alta", "alta")],
             "default": t.get("prioridad") or "media"},
            {"key": "responsable", "label": "Responsable (opcional):", "default": t.get("responsable")},
            {"key": "fecha_inicio", "label": "Inicio (YYYY-MM-DD, opcional):", "default": t.get("fecha_inicio")},
            {"key": "fecha_fin", "label": "Fin (YYYY-MM-DD, opcional):", "default": t.get("fecha_fin")},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        if not v["titulo"]:
            self._aviso("El título es obligatorio.", "warning")
            return
        ok = T.actualizar_tarea(t["id"], id_empresa=_empresa(), titulo=v["titulo"],
                                prioridad=v["prioridad"] or "media", responsable=v["responsable"] or None,
                                fecha_inicio=v["fecha_inicio"] or None, fecha_fin=v["fecha_fin"] or None)
        self._aviso("Tarea actualizada correctamente." if ok else "No se pudo actualizar la tarea.",
                    "success" if ok else "error")
        self._refrescar()

    def _aviso(self, mensaje, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "Proyectos", mensaje, nivel)
        except Exception:
            QMessageBox.information(self, "Proyectos", mensaje)

    def _borrar_tarea(self, id_tarea):
        if _confirmar("Eliminar tarea", "¿Eliminar la tarea?", self):
            T.eliminar_tarea(id_tarea, id_empresa=_empresa())
            self._refrescar()

    # ── Cronograma (Gantt-lite) ──
    def _pintar_cronograma(self):
        self.tbl_crono.setRowCount(0)
        if not self._pid:
            return
        filas = T.cronograma(self._pid, id_empresa=_empresa())
        self.tbl_crono.setRowCount(len(filas))
        for i, t in enumerate(filas):
            ini, fin = str(t.get("fecha_inicio"))[:10], str(t.get("fecha_fin") or "")[:10]
            barra = self._barra_gantt(ini, fin)
            for j, v in enumerate([t["titulo"], T.COLUMNA_ETIQUETA.get(t["estado"], t["estado"]), ini,
                                   fin or "—", barra]):
                self.tbl_crono.setItem(i, j, _it(v))

    @staticmethod
    def _barra_gantt(ini, fin):
        import datetime as dt
        try:
            di = dt.date.fromisoformat(ini)
            df = dt.date.fromisoformat(fin) if fin else di
            dias = max((df - di).days + 1, 1)
        except Exception:
            dias = 1
        return "▮" * min(dias, 40) + (f"  {dias}d" if dias else "")

    # ── Horas y costes ──
    def _tab_seguimiento(self):
        w = QWidget(); ly = QVBoxLayout(w)
        bar = QHBoxLayout()
        self._btn_horas = _btn("🕒 Imputar horas", self._imputar_horas, primary=True)
        self._btn_coste = _btn("💶 Añadir coste", self._anadir_coste, primary=True)
        bar.addWidget(self._btn_horas); bar.addWidget(self._btn_coste); bar.addStretch()
        ly.addLayout(bar)
        ly.addWidget(QLabel("Horas imputadas"))
        self.tbl_horas = _tabla(["Fecha", "Usuario", "Horas", "Coste/h", "Importe", "Descripción"])
        ly.addWidget(self.tbl_horas)
        ly.addWidget(QLabel("Costes"))
        self.tbl_costes = _tabla(["Fecha", "Concepto", "Tipo", "Importe"])
        ly.addWidget(self.tbl_costes)
        for b in (self._btn_horas, self._btn_coste):
            b.setEnabled(self._puede("proyectos.horas"))
        return w

    def _cargar_seguimiento(self):
        for tbl in (self.tbl_horas, self.tbl_costes):
            tbl.setRowCount(0)
        if not self._pid:
            return
        hs = S.listar_horas(self._pid, id_empresa=_empresa())
        self.tbl_horas.setRowCount(len(hs))
        for i, h in enumerate(hs):
            imp = float(h.get("horas") or 0) * float(h.get("coste_hora") or 0)
            vals = [str(h.get("fecha") or "")[:10], h.get("usuario"), f"{float(h.get('horas') or 0):.2f}",
                    f"{float(h.get('coste_hora') or 0):.2f}", f"{imp:.2f}", h.get("descripcion")]
            for j, v in enumerate(vals):
                self.tbl_horas.setItem(i, j, _it(v))
        cs = S.listar_costes(self._pid, id_empresa=_empresa())
        self.tbl_costes.setRowCount(len(cs))
        for i, c in enumerate(cs):
            vals = [str(c.get("fecha") or "")[:10], c.get("concepto"), c.get("tipo"),
                    f"{float(c.get('importe') or 0):.2f}"]
            for j, v in enumerate(vals):
                self.tbl_costes.setItem(i, j, _it(v))

    def _imputar_horas(self):
        if not self._pid:
            return
        d = _FormDialog(self, "Imputar horas", [
            {"key": "horas", "label": "Horas:"},
            {"key": "coste_hora", "label": "Coste/hora (vacío = por defecto del proyecto):"},
            {"key": "usuario", "label": "Usuario (opcional):"},
            {"key": "descripcion", "label": "Descripción (opcional):"},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        try:
            horas = float((v["horas"] or "0").replace(",", "."))
        except ValueError:
            self._aviso("Indica unas horas válidas.", "warning"); return
        if horas <= 0:
            self._aviso("Indica unas horas válidas.", "warning"); return
        ch = None
        if v["coste_hora"]:
            try:
                ch = float(v["coste_hora"].replace(",", "."))
            except ValueError:
                ch = None
        try:
            S.registrar_horas(self._pid, horas, coste_hora=ch, usuario=v["usuario"] or None,
                              descripcion=v["descripcion"] or None, id_empresa=_empresa())
        except Exception as e:
            self._aviso(f"No se pudieron imputar las horas: {e}", "error"); return
        self._aviso(f"{horas:.2f} h imputadas correctamente.", "success")
        self._refrescar()

    def _anadir_coste(self):
        if not self._pid:
            return
        d = _FormDialog(self, "Añadir coste", [
            {"key": "concepto", "label": "Concepto:"},
            {"key": "importe", "label": "Importe (€):"},
            {"key": "tipo", "label": "Tipo:", "tipo": "combo",
             "opciones": [("Gasto", "gasto"), ("Material", "material"), ("Otro", "otro")], "default": "gasto"},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        if not v["concepto"] or not v["importe"]:
            self._aviso("Indica el concepto y el importe.", "warning"); return
        try:
            imp = float(v["importe"].replace(",", "."))
        except ValueError:
            self._aviso("Indica un importe válido.", "warning"); return
        try:
            S.registrar_coste(self._pid, v["concepto"], imp, tipo=v["tipo"] or "gasto", id_empresa=_empresa())
        except Exception as e:
            self._aviso(f"No se pudo añadir el coste: {e}", "error"); return
        self._aviso(f"Coste «{v['concepto']}» añadido correctamente.", "success")
        self._refrescar()

    # ── proyecto CRUD ──
    def _dialogo_proyecto(self, p=None):
        return _FormDialog(self, "Editar proyecto" if p else "Nuevo proyecto", [
            {"key": "nombre", "label": "Nombre:", "default": (p or {}).get("nombre")},
            {"key": "presupuesto", "label": "Presupuesto (€):", "default": (p or {}).get("presupuesto", 0)},
            {"key": "coste_hora_defecto", "label": "Coste/hora por defecto (€):",
             "default": (p or {}).get("coste_hora_defecto", 0)},
            {"key": "responsable", "label": "Responsable (opcional):",
             "default": (p or {}).get("responsable")},
            {"key": "estado", "label": "Estado:", "tipo": "combo",
             "opciones": [(e.replace("_", " ").capitalize(), e) for e in P.ESTADOS],
             "default": (p or {}).get("estado", "planificado")},
        ])

    def _nuevo_proyecto(self):
        d = self._dialogo_proyecto()
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        if not v["nombre"]:
            return
        pid = P.crear_proyecto(v["nombre"], presupuesto=_num(v["presupuesto"]),
                               coste_hora_defecto=_num(v["coste_hora_defecto"]),
                               responsable=v["responsable"] or None, estado=v["estado"] or "planificado",
                               id_empresa=_empresa())
        self._cargar_proyectos(sel_id=pid)

    def _avisar_seleccion(self):
        """Aviso informativo: hay que seleccionar un proyecto antes de editar/eliminar."""
        msg = ("Antes de continuar, selecciona al menos un proyecto en el desplegable «Proyecto» "
               "para poder realizar esta acción.")
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "Selecciona un proyecto", msg, "warning")
        except Exception:
            QMessageBox.information(self, "Selecciona un proyecto", msg)

    def _editar_proyecto(self):
        if not self._pid:
            self._avisar_seleccion()
            return
        p = P.obtener_proyecto(self._pid, id_empresa=_empresa())
        d = self._dialogo_proyecto(p)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        P.actualizar_proyecto(self._pid, nombre=v["nombre"], presupuesto=_num(v["presupuesto"]),
                              coste_hora_defecto=_num(v["coste_hora_defecto"]),
                              responsable=v["responsable"] or None, estado=v["estado"] or "planificado",
                              id_empresa=_empresa())
        self._cargar_proyectos(sel_id=self._pid)

    def _eliminar_proyecto(self):
        if not self._pid:
            self._avisar_seleccion()
            return
        if _confirmar("Eliminar proyecto",
                     "¿Eliminar el proyecto y todas sus tareas, horas y costes?", self):
            P.eliminar_proyecto(self._pid, id_empresa=_empresa())
            self._cargar_proyectos()


def _num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return 0
