"""
Delegación a SOMA — panel REUTILIZABLE embebido como pestaña "Delegación IA" dentro de la ventana
de cada módulo (Correo, CRM, Posventa, Compras, Configuración…), SOLO SUPERADMIN. NO existe
ninguna ventana/tarjeta de menú propia: el encargo es explícito en que esto se integra donde
corresponda delegar cada acción, no como un módulo aparte.

El SUPERADMIN decide qué tareas repetitivas delega al agente IA SOMA (catálogo extensible en
`services.soma_delegacion.catalogo`) y SIEMPRE debe definir, en texto libre, cómo debe proceder
SOMA en esa situación — el formulario de alta no deja guardar sin instrucciones. Solo orquesta:
toda la lógica vive en `services.soma_delegacion`.
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
                             QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo,
                                      _tabla, centrar_en_pantalla)
from src.services.soma_delegacion import catalogo as CAT
from src.services.soma_delegacion import historial as H
from src.services.soma_delegacion import reglas as R

logger = logging.getLogger("gui.soma_delegacion")

_ROJO = "#F85149"
_VERDE = "#22C55E"
_AMBAR = "#F1C40F"

_ESTADO_ETIQUETA = {
    "aplicado": ("Aplicado", _VERDE),
    "pendiente_revision": ("Pendiente de revisión", _AMBAR),
    "descartado": ("Descartado", _DIM),
    "error": ("Error", _ROJO),
}
_MODOS = [("Revisar antes de aplicar", "revisar_antes"), ("Automático", "automatico")]
_MODOS_ETIQUETA = {codigo: etiqueta for etiqueta, codigo in _MODOS}


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _toast(parent, titulo, mensaje, nivel="info", ms=2600):
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


class _ReglaDialog(QDialog):
    """Alta/edición de una regla de delegación. Las instrucciones son OBLIGATORIAS — el diálogo
    nunca se puede aceptar (`accept`) sin texto, ni aunque se edite una regla ya existente.
    `tipos`: lista de tipos del catálogo a ofrecer (ya filtrada por la pantalla que lo abre)."""

    def __init__(self, parent=None, tipos=None, regla: dict | None = None):
        super().__init__(parent)
        self._regla = regla
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(560)
        QTimer.singleShot(0, lambda: centrar_en_pantalla(self))

        outer = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_CIAN};border-radius:15px;}}"
                           f"QLabel{{color:{_TEXT};border:none;font-weight:bold;background:transparent;}}")
        outer.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)

        cab = QHBoxLayout()
        t = QLabel("Editar delegación" if regla else "Nueva delegación a SOMA")
        t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;")
        cab.addWidget(t); cab.addStretch(); cab.addWidget(_btn_x(self.reject))
        ly.addLayout(cab)

        ly.addWidget(QLabel("Tarea a delegar:"))
        self.cmb_tipo = _combo([(t["nombre"], t["codigo"]) for t in (tipos or [])],
                               (regla or {}).get("tipo"))
        self.cmb_tipo.setEnabled(regla is None)   # el tipo no se cambia al editar
        self.cmb_tipo.currentIndexChanged.connect(self._actualizar_descripcion)
        ly.addWidget(self.cmb_tipo)

        self.lbl_descripcion = QLabel("")
        self.lbl_descripcion.setWordWrap(True)
        self.lbl_descripcion.setStyleSheet(f"color:{_DIM};font-size:11px;font-weight:600;")
        ly.addWidget(self.lbl_descripcion)

        ly.addWidget(QLabel("Instrucciones para SOMA (obligatorio):"))
        self.txt_instrucciones = QPlainTextEdit((regla or {}).get("instrucciones") or "")
        self.txt_instrucciones.setFixedHeight(110)
        self.txt_instrucciones.setStyleSheet(
            f"QPlainTextEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;}}QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        ly.addWidget(self.txt_instrucciones)

        fila_modo = QHBoxLayout()
        fila_modo.addWidget(QLabel("Modo de aplicación:"))
        self.cmb_modo = _combo(_MODOS, (regla or {}).get("modo_aplicacion") or "revisar_antes")
        fila_modo.addWidget(self.cmb_modo)
        self.chk_activa = QCheckBox("Activa")
        self.chk_activa.setChecked(bool((regla or {}).get("activa", True)))
        # Sin esto, el checkbox hereda el fondo de casilla POR DEFECTO del tema global de Qt (un
        # gris más oscuro que `_BG2`, visible como un parche desentonado junto al combo de al
        # lado, que sí fija su propio fondo) — mismo criterio que el resto de la ventana: cada
        # control fija explícitamente su fondo a `_BG2` (el de la propia tarjeta del diálogo),
        # nunca se deja al tema por defecto.
        self.chk_activa.setStyleSheet(
            f"QCheckBox{{background:transparent;color:{_TEXT};font-weight:700;spacing:8px;}}"
            f"QCheckBox::indicator{{width:18px;height:18px;border-radius:4px;"
            f"border:2px solid {_BORDE};background:{_BG2};}}"
            f"QCheckBox::indicator:checked{{background:{_CIAN};border-color:{_CIAN};}}")
        fila_modo.addWidget(self.chk_activa)
        fila_modo.addStretch()
        ly.addLayout(fila_modo)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color:{_ROJO};font-weight:800;font-size:12px;")
        ly.addWidget(self.lbl_error)

        bar = QHBoxLayout()
        bar.addWidget(_btn("Guardar", self._intentar_aceptar, primary=True))
        ly.addLayout(bar)
        self._actualizar_descripcion()

    def _actualizar_descripcion(self):
        t = CAT.obtener(self.cmb_tipo.currentData())
        if not t:
            self.lbl_descripcion.setText("")
            return
        self.lbl_descripcion.setText(t["descripcion"])
        if not self.txt_instrucciones.toPlainText().strip():
            self.txt_instrucciones.setPlaceholderText(t.get("ejemplo_instrucciones") or "")

    def _intentar_aceptar(self):
        # Gate explícito, independiente de la validación de `reglas.crear_regla`: el usuario debe
        # VER por qué no se guarda, no solo que el diálogo no hace nada.
        if not self.txt_instrucciones.toPlainText().strip():
            self.lbl_error.setText(
                "Tienes que indicarle a SOMA cómo debe proceder en esta situación antes de "
                "poder delegarla.")
            return
        self.accept()

    def datos(self) -> dict:
        return {"tipo": self.cmb_tipo.currentData(),
               "instrucciones": self.txt_instrucciones.toPlainText().strip(),
               "modo_aplicacion": self.cmb_modo.currentData(),
               "activa": self.chk_activa.isChecked()}


# Para los tipos cuyo "revisar antes de aplicar" deja un borrador pendiente en vez de actuar,
# `_APLICAR_PENDIENTE[tipo](contexto, decision, id_empresa) -> (ok, mensaje)` ejecuta la acción
# diferida desde el historial. Extensible: un tipo nuevo con staging solo añade una entrada aquí.
def _aplicar_pendiente_correo(contexto, decision, id_empresa):
    from src.services.correo import servicio as correo_srv
    respuesta = (decision.get("respuesta") or "").strip()
    if not respuesta or not contexto.get("id_recibido"):
        return False, "No hay borrador de respuesta que enviar."
    return correo_srv.responder_correo(contexto.get("id_correo"), contexto.get("id_recibido"),
                                       respuesta, id_empresa=id_empresa)


def _aplicar_pendiente_ticket(contexto, decision, id_empresa):
    from src.services.sat import tickets
    respuesta = (decision.get("respuesta") or "").strip()
    if not respuesta or not contexto.get("id_ticket"):
        return False, "No hay borrador de respuesta que publicar."
    cid = tickets.comentar(contexto.get("id_ticket"), respuesta, autor="SOMA", es_cliente=False,
                           interno=False, id_empresa=id_empresa)
    return (cid is not None), ("Respuesta publicada en el ticket." if cid else
                               "No se pudo publicar la respuesta.")


_APLICAR_PENDIENTE = {
    "correo.responder_automatico": _aplicar_pendiente_correo,
    "sat.responder_ticket": _aplicar_pendiente_ticket,
}


class DelegacionSomaPanel(QWidget):
    """Pestaña "Delegación IA" embebida en la ventana de un módulo — `pantalla` filtra qué tipos
    del catálogo se gestionan aquí (`catalogo.por_pantalla(pantalla)`). `puede_fn(permiso)->bool`
    gatea las acciones de escritura (además del gate SUPERADMIN duro que ya aplica la ventana
    anfitriona antes de abrirse)."""

    def __init__(self, pantalla: str, usuario=None, puede_fn=None, parent=None):
        super().__init__(parent)
        self.pantalla = pantalla
        self.usuario = usuario or {}
        self._puede_fn = puede_fn or (lambda _p: True)
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        sub = QLabel("Define cuándo y cómo debe actuar SOMA por su cuenta en este módulo, para "
                    "que puedas centrarte en lo que de verdad requiere una decisión humana.")
        sub.setStyleSheet(f"color:{_DIM};font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        barra = QHBoxLayout()
        self._btn_nueva = _btn("➕ Nueva delegación", self._nueva_regla, primary=True)
        barra.addWidget(self._btn_nueva); barra.addStretch()
        root.addLayout(barra)

        root.addWidget(QLabel("Reglas"))
        self.tbl_reglas = _tabla(["Tarea", "Instrucciones", "Modo", "Activa", "Creada"])
        self.tbl_reglas.setMaximumHeight(220)
        root.addWidget(self.tbl_reglas)
        barra_reglas = QHBoxLayout()
        barra_reglas.addStretch()
        barra_reglas.addWidget(_btn("✏️ Editar", self._editar_regla, primary=True))
        barra_reglas.addWidget(_btn("⏯ Activar/Desactivar", self._alternar_regla))
        barra_reglas.addWidget(_btn("🗑 Eliminar", self._eliminar_regla, danger=True))
        root.addLayout(barra_reglas)

        root.addWidget(QLabel("Historial"))
        self.tbl_historial = _tabla(["Fecha", "Tarea", "Estado", "Detalle"])
        root.addWidget(self.tbl_historial, 1)
        barra_hist = QHBoxLayout()
        barra_hist.addStretch()
        barra_hist.addWidget(_btn("✔ Aplicar pendiente", self._aplicar_pendiente, primary=True))
        barra_hist.addWidget(_btn("✕ Descartar", self._descartar_pendiente, danger=True))
        root.addLayout(barra_hist)

        if not self._puede_fn("soma_delegacion.admin"):
            for b in (self._btn_nueva,):
                b.setEnabled(False)

        self._cargar_reglas()
        self._cargar_historial()

    def _tipos(self) -> list:
        return CAT.por_pantalla(self.pantalla)

    # ── Reglas ──
    def _cargar_reglas(self):
        tipos_codigos = {t["codigo"] for t in self._tipos()}
        filas = [r for r in R.listar_reglas(id_empresa=_empresa()) if r["tipo"] in tipos_codigos]
        self._reglas = filas
        self.tbl_reglas.setRowCount(len(filas))
        for i, r in enumerate(filas):
            t = CAT.obtener(r["tipo"])
            nombre = t["nombre"] if t else r["tipo"]
            vals = [nombre, (r.get("instrucciones") or "")[:80],
                   _MODOS_ETIQUETA.get(r.get("modo_aplicacion"), r.get("modo_aplicacion")),
                   "Sí" if r.get("activa") else "No", str(r.get("creado") or "")[:16]]
            for j, v in enumerate(vals):
                self.tbl_reglas.setItem(i, j, QTableWidgetItem(str(v)))

    def _regla_seleccionada(self):
        row = self.tbl_reglas.currentRow()
        if row < 0 or row >= len(getattr(self, "_reglas", [])):
            return None
        return self._reglas[row]

    def _nueva_regla(self):
        d = _ReglaDialog(self, tipos=self._tipos())
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        rid = R.crear_regla(v["tipo"], v["instrucciones"], modo_aplicacion=v["modo_aplicacion"],
                            activa=v["activa"], creado_por=self.usuario.get("nombre"),
                            id_empresa=_empresa())
        _toast(self, "Delegación SOMA", "Delegación guardada correctamente." if rid else
              "Error al guardar los cambios.", "success" if rid else "error")
        self._cargar_reglas()

    def _editar_regla(self):
        r = self._regla_seleccionada()
        if not r:
            _toast(self, "Delegación SOMA", "Selecciona una delegación de la lista.", "warning")
            return
        d = _ReglaDialog(self, tipos=self._tipos(), regla=r)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        ok = R.actualizar_regla(r["id"], id_empresa=_empresa(), instrucciones=v["instrucciones"],
                                modo_aplicacion=v["modo_aplicacion"], activa=v["activa"])
        _toast(self, "Delegación SOMA", "Delegación actualizada correctamente." if ok else
              "Error al guardar los cambios.", "success" if ok else "error")
        self._cargar_reglas()

    def _alternar_regla(self):
        r = self._regla_seleccionada()
        if not r:
            _toast(self, "Delegación SOMA", "Selecciona una delegación de la lista.", "warning")
            return
        ok = R.actualizar_regla(r["id"], id_empresa=_empresa(), activa=not r.get("activa"))
        if ok:
            _toast(self, "Delegación SOMA",
                  "Delegación desactivada." if r.get("activa") else "Delegación activada.", "success")
        self._cargar_reglas()

    def _eliminar_regla(self):
        r = self._regla_seleccionada()
        if not r:
            _toast(self, "Delegación SOMA", "Selecciona una delegación de la lista.", "warning")
            return
        if _confirmar(self, "Eliminar delegación",
                     "¿Eliminar esta delegación? SOMA dejará de actuar en esta situación."):
            R.eliminar_regla(r["id"], id_empresa=_empresa())
            self._cargar_reglas()

    # ── Historial ──
    def _cargar_historial(self):
        tipos_codigos = {t["codigo"] for t in self._tipos()}
        filas = [h for h in H.listar(id_empresa=_empresa()) if h["tipo"] in tipos_codigos]
        self._historial = filas
        self.tbl_historial.setRowCount(len(filas))
        for i, h in enumerate(filas):
            t = CAT.obtener(h["tipo"])
            etiqueta, _color = _ESTADO_ETIQUETA.get(h["estado"], (h["estado"], _DIM))
            vals = [str(h.get("creado") or "")[:16], t["nombre"] if t else h["tipo"], etiqueta,
                   (h.get("resultado") or "")[:120]]
            for j, v in enumerate(vals):
                self.tbl_historial.setItem(i, j, QTableWidgetItem(str(v)))

    def _historial_seleccionado(self):
        row = self.tbl_historial.currentRow()
        if row < 0 or row >= len(getattr(self, "_historial", [])):
            return None
        return self._historial[row]

    def _aplicar_pendiente(self):
        h = self._historial_seleccionado()
        if not h or h.get("estado") != "pendiente_revision":
            _toast(self, "Delegación SOMA",
                  "Selecciona una entrada «Pendiente de revisión» del historial.", "warning")
            return
        aplicar = _APLICAR_PENDIENTE.get(h.get("tipo"))
        if not aplicar:
            _toast(self, "Delegación SOMA",
                  "Esta tarea no tiene una acción diferida que aplicar manualmente.", "warning")
            return
        ok, msg = aplicar(h.get("contexto") or {}, h.get("decision") or {}, _empresa())
        H.actualizar_estado(h["id"], "aplicado" if ok else "error", resultado=msg, id_empresa=_empresa())
        _toast(self, "Delegación SOMA", msg, "success" if ok else "error")
        self._cargar_historial()

    def _descartar_pendiente(self):
        h = self._historial_seleccionado()
        if not h or h.get("estado") != "pendiente_revision":
            _toast(self, "Delegación SOMA",
                  "Selecciona una entrada «Pendiente de revisión» del historial.", "warning")
            return
        H.actualizar_estado(h["id"], "descartado", resultado="Descartado manualmente por el SUPERADMIN.",
                            id_empresa=_empresa())
        _toast(self, "Delegación SOMA", "Borrador descartado.", "success")
        self._cargar_historial()
