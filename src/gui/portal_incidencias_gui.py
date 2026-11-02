"""
Portal de Incidencias / Helpdesk interno (petición explícita — módulo de nivel superior propio en
el menú principal, reemplaza la tarjeta retirada "Portal del empleado"). Orquesta ÚNICAMENTE
`services.incidencias_internas.tickets` (toda la lógica vive ahí) — RBAC por pantalla, NO por
backend: ADMINISTRADOR ve "Enviar incidencia" (solo las suyas); SUPERADMIN ve "Gestionar
incidencias" (todas las de la empresa). Cualquier otro perfil no debería llegar aquí (la tarjeta del
menú ya está vedada a OPERARIO), pero por si acaso se degrada a la vista de envío (fail-closed: más
restrictiva, nunca expone las incidencias de otros).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem,
                             QTextEdit, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _BORDE, _CIAN, _DIM, _btn, _btn_x, _inp, _tabla
from src.services.incidencias_internas import tickets as T

logger = logging.getLogger("gui.portal_incidencias")

_CATEGORIAS_LBL = {
    "equipo_informatico": "Equipamiento informático", "soporte_tecnico": "Soporte técnico",
    "consulta_rrhh": "Consulta a RRHH", "reputacion_redes": "Reputación en redes sociales",
    "otro": "Otro",
}
_ESTADOS_LBL = {"pendiente": "Pendiente", "en_proceso": "En proceso",
               "resuelto": "Resuelto", "cerrado": "Cerrado"}
_PRIORIDADES_LBL = {"baja": "Baja", "media": "Media", "alta": "Alta"}


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _mensaje(parent, titulo, texto, nivel="info"):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, texto, nivel)
    except Exception:
        logger.info("%s: %s", titulo, texto)


class PortalIncidenciasWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Portal de Incidencias")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        perfil = str(self.usuario.get("perfil") or "").upper()
        if perfil == "SUPERADMIN":
            root.addWidget(self._panel_gestion())
        else:
            # Fail-closed: cualquier perfil que no sea SUPERADMIN ve SOLO la vista de envío/
            # autoservicio, nunca el listado completo de incidencias de la empresa.
            root.addWidget(self._panel_enviar())

    # ══════════════════════════════════════════════════════════════════
    # ADMINISTRADOR — Enviar incidencia (autoservicio)
    # ══════════════════════════════════════════════════════════════════
    def _panel_enviar(self):
        w = QWidget(); ly = QVBoxLayout(w)

        card = QWidget(); card.setStyleSheet(
            f"background:#161B22;border:1px solid {_BORDE};border-radius:10px;")
        cly = QVBoxLayout(card); cly.setSpacing(10)
        cly.addWidget(QLabel("NUEVA INCIDENCIA", styleSheet=f"color:{_CIAN};font-weight:900;"))

        self.cb_categoria = QComboBox()
        for k, et in _CATEGORIAS_LBL.items():
            self.cb_categoria.addItem(et, k)
        self.cb_prioridad = QComboBox()
        for k, et in _PRIORIDADES_LBL.items():
            self.cb_prioridad.addItem(et, k)
        self.cb_prioridad.setCurrentIndex(1)  # media por defecto
        fila_combos = QHBoxLayout()
        fila_combos.addWidget(QLabel("Categoría:", styleSheet=f"color:{_DIM};"))
        fila_combos.addWidget(self.cb_categoria)
        fila_combos.addWidget(QLabel("Prioridad:", styleSheet=f"color:{_DIM};"))
        fila_combos.addWidget(self.cb_prioridad)
        cly.addLayout(fila_combos)

        self.in_asunto = _inp("Asunto *")
        cly.addWidget(self.in_asunto)
        self.in_desc = QTextEdit(); self.in_desc.setPlaceholderText("Describe la incidencia…")
        self.in_desc.setFixedHeight(100)
        cly.addWidget(self.in_desc)

        fila_btn = QHBoxLayout(); fila_btn.addStretch()
        fila_btn.addWidget(_btn("Enviar incidencia", self._enviar, primary=True))
        cly.addLayout(fila_btn)
        ly.addWidget(card)

        ly.addWidget(QLabel("MIS INCIDENCIAS", styleSheet=f"color:{_CIAN};font-weight:900;margin-top:10px;"))
        self.tbl_mias = _tabla(["Código", "Categoría", "Asunto", "Prioridad", "Estado", "Fecha"])
        ly.addWidget(self.tbl_mias)

        self._refrescar_mias()
        return w

    def _enviar(self):
        asunto = self.in_asunto.text().strip()
        if not asunto:
            _mensaje(self, "Incidencias", "El asunto es obligatorio.", "warning")
            return
        try:
            r = T.crear_ticket(
                asunto, self.in_desc.toPlainText().strip(), self.cb_categoria.currentData(),
                prioridad=self.cb_prioridad.currentData(),
                id_usuario_solicitante=self.usuario.get("id"),
                nombre_solicitante=self.usuario.get("nombre") or self.usuario.get("usuario"))
        except T.IncidenciaError as e:
            _mensaje(self, "Incidencias", str(e), "warning")
            return
        _mensaje(self, "Incidencias", f"Incidencia {r['codigo']} enviada correctamente.", "success")
        self.in_asunto.clear(); self.in_desc.clear()
        self._refrescar_mias()

    def _refrescar_mias(self):
        filas = T.listar_tickets(id_usuario_solicitante=self.usuario.get("id"))
        self.tbl_mias.setRowCount(len(filas))
        for i, f in enumerate(filas):
            valores = [f.get("codigo"), _CATEGORIAS_LBL.get(f.get("categoria"), f.get("categoria")),
                      f.get("asunto"), _PRIORIDADES_LBL.get(f.get("prioridad"), f.get("prioridad")),
                      _ESTADOS_LBL.get(f.get("estado"), f.get("estado")), f.get("fecha_creacion")]
            for j, val in enumerate(valores):
                self.tbl_mias.setItem(i, j, _it(val))

    # ══════════════════════════════════════════════════════════════════
    # SUPERADMIN — Gestionar incidencias (todas las de la empresa)
    # ══════════════════════════════════════════════════════════════════
    def _panel_gestion(self):
        w = QWidget(); ly = QVBoxLayout(w)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Estado:", styleSheet=f"color:{_DIM};"))
        self.cb_filtro_estado = QComboBox()
        self.cb_filtro_estado.addItem("(Todos)", None)
        for k, et in _ESTADOS_LBL.items():
            self.cb_filtro_estado.addItem(et, k)
        self.cb_filtro_estado.currentIndexChanged.connect(lambda *_: self._refrescar_todas())
        filtros.addWidget(self.cb_filtro_estado)
        filtros.addWidget(_btn("🔄 Actualizar", self._refrescar_todas))
        filtros.addStretch()
        ly.addLayout(filtros)

        self.tbl_todas = _tabla(["ID", "Código", "Categoría", "Asunto", "Prioridad", "Estado",
                                 "Solicitante", "Fecha"])
        self.tbl_todas.cellClicked.connect(self._seleccionar_ticket)
        ly.addWidget(self.tbl_todas, 2)

        # Panel de detalle: hilo de comentarios + respuesta + cambio de estado.
        self.detalle_card = QWidget(); self.detalle_card.setStyleSheet(
            f"background:#161B22;border:1px solid {_BORDE};border-radius:10px;")
        dly = QVBoxLayout(self.detalle_card)
        self.lbl_detalle = QLabel("Selecciona una incidencia en la tabla.", styleSheet=f"color:{_DIM};")
        dly.addWidget(self.lbl_detalle)
        self.lbl_hilo = QLabel(""); self.lbl_hilo.setWordWrap(True)
        self.lbl_hilo.setStyleSheet(f"color:{_DIM};")
        dly.addWidget(self.lbl_hilo)
        self.in_respuesta = QTextEdit(); self.in_respuesta.setPlaceholderText("Responder / nota de resolución…")
        self.in_respuesta.setFixedHeight(70)
        dly.addWidget(self.in_respuesta)
        acc = QHBoxLayout()
        acc.addWidget(_btn("Comentar", self._comentar))
        acc.addWidget(_btn("En proceso", lambda: self._cambiar_estado("en_proceso")))
        acc.addWidget(_btn("Resuelto", lambda: self._cambiar_estado("resuelto"), primary=True))
        acc.addWidget(_btn("Cerrar", lambda: self._cambiar_estado("cerrado")))
        acc.addStretch()
        dly.addLayout(acc)
        ly.addWidget(self.detalle_card, 1)

        self._ticket_sel = None
        self._refrescar_todas()
        return w

    def _refrescar_todas(self, *_args):
        estado = self.cb_filtro_estado.currentData()
        self._todas = T.listar_tickets(estado=estado)
        self.tbl_todas.setRowCount(len(self._todas))
        for i, f in enumerate(self._todas):
            solicitante = f.get("nombre_solicitante")
            if f.get("origen") == "reputacion_auto":
                solicitante = f"🚨 {solicitante or 'Sistema'} (automático)"
            valores = [f.get("id"), f.get("codigo"),
                      _CATEGORIAS_LBL.get(f.get("categoria"), f.get("categoria")), f.get("asunto"),
                      _PRIORIDADES_LBL.get(f.get("prioridad"), f.get("prioridad")),
                      _ESTADOS_LBL.get(f.get("estado"), f.get("estado")),
                      solicitante, f.get("fecha_creacion")]
            for j, val in enumerate(valores):
                self.tbl_todas.setItem(i, j, _it(val))

    def _seleccionar_ticket(self, row, _col):
        try:
            self._ticket_sel = self._todas[row]
        except (IndexError, AttributeError):
            self._ticket_sel = None
            return
        t = self._ticket_sel
        self.lbl_detalle.setText(
            f"{t.get('codigo')} — {t.get('asunto')}  ·  {_CATEGORIAS_LBL.get(t.get('categoria'), '')}  ·  "
            f"Solicitante: {t.get('nombre_solicitante') or '—'}  ·  Estado: {_ESTADOS_LBL.get(t.get('estado'), '')}")
        comentarios = T.listar_comentarios(t["id"])
        if t.get("descripcion"):
            lineas = [f"[Descripción inicial] {t['descripcion']}"]
        else:
            lineas = []
        for c in comentarios:
            quien = c.get("autor") or ("Solicitante" if c.get("es_solicitante") else "Equipo")
            lineas.append(f"[{c.get('fecha')}] {quien}: {c.get('cuerpo')}")
        self.lbl_hilo.setText("\n".join(lineas) or "Sin comentarios todavía.")

    def _comentar(self):
        if not self._ticket_sel:
            _mensaje(self, "Incidencias", "Selecciona primero una incidencia.", "warning")
            return
        cuerpo = self.in_respuesta.toPlainText().strip()
        if not cuerpo:
            return
        try:
            T.comentar(self._ticket_sel["id"], cuerpo,
                      autor=self.usuario.get("nombre") or self.usuario.get("usuario"))
        except T.IncidenciaError as e:
            _mensaje(self, "Incidencias", str(e), "warning"); return
        self.in_respuesta.clear()
        self._seleccionar_ticket(self.tbl_todas.currentRow(), 0)

    def _cambiar_estado(self, nuevo):
        if not self._ticket_sel:
            _mensaje(self, "Incidencias", "Selecciona primero una incidencia.", "warning")
            return
        respuesta = self.in_respuesta.toPlainText().strip() or None
        try:
            r = T.cambiar_estado(self._ticket_sel["id"], nuevo,
                                 usuario=self.usuario.get("nombre") or self.usuario.get("usuario"),
                                 respuesta=respuesta)
        except T.IncidenciaError as e:
            _mensaje(self, "Incidencias", str(e), "warning"); return
        if not r.get("ok"):
            _mensaje(self, "Incidencias", r.get("error") or "No se pudo actualizar.", "error")
            return
        self.in_respuesta.clear()
        self._refrescar_todas()
