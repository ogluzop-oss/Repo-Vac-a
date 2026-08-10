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


_PRIO_COLOR = {"alta": "#F85149", "media": "#F5A623", "baja": "#2ECC71"}


class _FormDialog(QDialog):
    """Diálogo de formulario genérico. `campos`: lista de dicts {key,label,tipo,default,opciones}."""

    def __init__(self, parent, titulo, campos):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(440)
        self._w = {}
        outer = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_CIAN};border-radius:15px;}}"
                           f"QLabel{{color:{_TEXT};border:none;font-weight:bold;background:transparent;}}")
        outer.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(28, 24, 28, 24); ly.setSpacing(10)
        t = QLabel(titulo); t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        ly.addWidget(t)
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
        bar.addWidget(_btn("Cancelar", self.reject))
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
        cab.addWidget(t); cab.addSpacing(16)
        self.cmb_proy = _combo([]); self.cmb_proy.setMinimumWidth(240)
        self.cmb_proy.currentIndexChanged.connect(self._cambiar_proyecto)
        cab.addWidget(QLabel("Proyecto:")); cab.addWidget(self.cmb_proy)
        self._btn_nuevo = _btn("➕ Nuevo proyecto", self._nuevo_proyecto, primary=True)
        self._btn_edit = _btn("✏️ Editar", self._editar_proyecto)
        self._btn_del = _btn("🗑 Eliminar", self._eliminar_proyecto, danger=True)
        cab.addWidget(self._btn_nuevo); cab.addWidget(self._btn_edit); cab.addWidget(self._btn_del)
        cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        self.lbl_rent = QLabel("")
        self.lbl_rent.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        root.addWidget(self.lbl_rent)

        self.tabs = QTabWidget()
        self._tab_kanban = QWidget(); self._kanban_host = QVBoxLayout(self._tab_kanban)
        self.tabs.addTab(self._tab_kanban, "Tablero (Kanban)")
        self.tbl_crono = _tabla(["Tarea", "Estado", "Inicio", "Fin", "Cronograma"])
        self.tabs.addTab(self.tbl_crono, "Cronograma")
        self.tabs.addTab(self._tab_seguimiento(), "Horas y costes")
        root.addWidget(self.tabs)

        self._aplicar_permisos()
        self._cargar_proyectos()

    # ── permisos ──
    def _puede(self, permiso):
        try:
            from src.services.autorizacion import puede
            return puede(self.usuario, permiso)
        except Exception:
            return True

    def _aplicar_permisos(self):
        gest = self._puede("proyectos.gestionar")
        for b in (self._btn_nuevo, self._btn_edit, self._btn_del):
            b.setEnabled(gest)

    # ── selección de proyecto ──
    def _cargar_proyectos(self, sel_id=None):
        self.cmb_proy.blockSignals(True)
        self.cmb_proy.clear()
        proys = P.listar_proyectos(id_empresa=_empresa())
        for p in proys:
            self.cmb_proy.addItem(f"{p['nombre']}  ·  {p['estado']}", p["id"])
        self.cmb_proy.blockSignals(False)
        if proys:
            idx = self.cmb_proy.findData(sel_id) if sel_id else 0
            self.cmb_proy.setCurrentIndex(idx if idx >= 0 else 0)
            self._pid = self.cmb_proy.currentData()
        else:
            self._pid = None
        self._refrescar()

    def _cambiar_proyecto(self):
        self._pid = self.cmb_proy.currentData()
        self._refrescar()

    def _refrescar(self):
        self._pintar_rentabilidad()
        self._pintar_kanban()
        self._pintar_cronograma()
        self._cargar_seguimiento()

    def _pintar_rentabilidad(self):
        if not self._pid:
            self.lbl_rent.setText("Sin proyectos. Crea uno para empezar.")
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
        while self._kanban_host.count():
            it = self._kanban_host.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not self._pid:
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
            if col == "pendiente" and gest:
                cab.addWidget(_btn("➕", lambda _=None: self._nueva_tarea()))
            colv.addLayout(cab)
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            scroll.setStyleSheet(f"QScrollArea{{background:{_BG2};border:1px solid {_BORDE};"
                                 f"border-radius:10px;}}")
            inner = QWidget(); inner.setStyleSheet(f"background:{_BG2};")
            iv = QVBoxLayout(inner); iv.setSpacing(8); iv.setContentsMargins(8, 8, 8, 8)
            for t in tab[col]:
                iv.addWidget(self._card(t, ci, gest))
            iv.addStretch()
            scroll.setWidget(inner)
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
                row.addWidget(_btn("←", lambda _=None, i=t["id"]: self._mover(i, -1)))
            if ci < len(T.COLUMNAS) - 1:
                row.addWidget(_btn("→", lambda _=None, i=t["id"]: self._mover(i, 1)))
            row.addStretch()
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
        T.crear_tarea(self._pid, v["titulo"], prioridad=v["prioridad"] or "media",
                      responsable=v["responsable"] or None, fecha_inicio=v["fecha_inicio"] or None,
                      fecha_fin=v["fecha_fin"] or None, id_empresa=_empresa())
        self._refrescar()

    def _borrar_tarea(self, id_tarea):
        if QMessageBox.question(self, "Eliminar tarea", "¿Eliminar la tarea?") == QMessageBox.StandardButton.Yes:
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
        self._btn_coste = _btn("💶 Añadir coste", self._anadir_coste)
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
            return
        ch = None
        if v["coste_hora"]:
            try:
                ch = float(v["coste_hora"].replace(",", "."))
            except ValueError:
                ch = None
        S.registrar_horas(self._pid, horas, coste_hora=ch, usuario=v["usuario"] or None,
                          descripcion=v["descripcion"] or None, id_empresa=_empresa())
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
            return
        try:
            imp = float(v["importe"].replace(",", "."))
        except ValueError:
            return
        S.registrar_coste(self._pid, v["concepto"], imp, tipo=v["tipo"] or "gasto", id_empresa=_empresa())
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
        if QMessageBox.question(self, "Eliminar proyecto",
                                "¿Eliminar el proyecto y todas sus tareas, horas y costes?") \
                == QMessageBox.StandardButton.Yes:
            P.eliminar_proyecto(self._pid, id_empresa=_empresa())
            self._cargar_proyectos()


def _num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return 0
