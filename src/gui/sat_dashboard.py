"""
GUIs SAT/Helpdesk (BLOQUE 4) — AHORA OPERATIVAS.

  · SATDashboardWindow — cuadro de mando + ACCIONES sobre Tickets (ciclo abierto→asignado→en_proceso→
                         pendiente→resuelto→cerrado/reabierto, asignación de técnico, comentarios,
                         registro de intervenciones) + Contratos/SLA + Bolsa de horas (facturación por
                         horas prepago) + KPIs.
  · KnowledgeBaseWindow / PortalSATWindow — intactas (ya operativas).
  · TicketsWindow / ContratosSATWindow / IntervencionesWindow — alias de compatibilidad.

Reutiliza ÍNTEGRAMENTE `services.sat.{tickets,intervenciones,contratos_sla,sat_pro,analitica}`. Auditoría
(`SAT_*`) la emite el backend. RBAC único vía `services.autorizacion` (permisos `tickets.crear`,
`tickets.gestionar`, `sat.admin`). `tecnico`/`autor` son columnas INT (id de usuario).

NOTA de honestidad (alcance): el backend SAT actual NO consume stock por repuestos ni genera facturas
comerciales desde el ticket (eso NO existe en `services.sat`). La facturación disponible es la BOLSA DE
HORAS prepago (`sat_pro.consumir_horas`). No se inventa un motor de repuestos ni de facturación SAT.
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _ROJO, _btn as _btn_base, _btn_cargando as _btn_cargando_base, _btn_x,
                                      _dialogo_frameless, _inp, _lbl, _tabla)

logger = logging.getLogger("gui.sat")


class _EtiquetaX(QLabel):
    """'✕' clicable sobre QLabel, no QPushButton — mismo workaround ya documentado en
    `tpv.py::_EtiquetaX`: en ciertos diálogos frameless un QPushButton de cierre pequeño puede
    renderizarse mal (promovido por Qt/Windows a su propia ventana nativa mal posicionada); un
    QLabel clicable no entra en ese camino de Qt. Se usa aquí en `_FormDialog`/`_NuevoTicketDialog`
    (formularios cortos), donde se confirmó el mismo defecto visual."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(34, 34)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._pintar()

    def _pintar(self):
        bg = _ROJO if self._hover else "transparent"
        fg = "#0D1117" if self._hover else _ROJO
        self.setStyleSheet(
            f"QLabel{{background:{bg};color:{fg};border:none;border-radius:17px;"
            f"font-weight:900;font-size:18px;}}")

    def enterEvent(self, ev):
        self._hover = True; self._pintar(); super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False; self._pintar(); super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


def _btn(txt, slot=None, primary=False, danger=False):
    """Diseño global: los botones secundarios (antes grises) usan el estilo turquesa (contorno azul
    turquesa, fondo azul oscuro, texto turquesa, hover swap) — igual que 'Actualizar'. Los 'danger'
    (rojo) se conservan. Reutiliza el `_btn` compartido sin modificarlo (solo local a este módulo)."""
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


def _btn_cargando(txt, slot=None, primary=False, danger=False):
    return _btn_cargando_base(txt, slot, primary=(primary or not danger), danger=danger)


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


def _usuario_sesion(fallback=None):
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or fallback or {}
    except Exception:
        return fallback or {}


def _puede(usuario, permiso) -> bool:
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


def _combo(valores):
    cb = QComboBox(); cb.addItems(valores); return cb


class SATDashboardWindow(QWidget):
    """Cuadro de mando de soporte + acciones OPERATIVAS (tickets, intervenciones, SLA, bolsa de horas)."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Posventa")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; }")

        self.tbl_tk = _tabla(["ID", "Código", "Asunto", "Prioridad", "Estado", "Técnico"])
        self.tbl_int = _tabla(["ID", "Ticket", "Tipo", "Técnico", "Horas", "Descripción"])
        # KPIs UNIFICADOS: Soporte (SAT) + Mantenimiento (GMAO). Ámbito distingue el origen.
        self.tbl_kpi = _tabla(["Ámbito", "KPI", "Valor"])

        self.tabs.addTab(self._page(self.tbl_tk, [
            ("➕  Nueva incidencia", self._nueva_incidencia, True),
            ("Asignar técnico", self._asignar, False),
            ("En proceso", lambda: self._ticket_estado("en_proceso"), False),
            ("Pendiente", lambda: self._ticket_estado("pendiente"), False),
            ("Resuelto", lambda: self._ticket_estado("resuelto"), False),
            ("Cerrar", lambda: self._ticket_estado("cerrado"), False),
            ("Reabrir", lambda: self._ticket_estado("reabierto"), False),
            ("Comentar", self._comentar, False),
            ("Registrar intervención", self._intervencion, False)]), "Incidencias")
        self.tabs.addTab(self._page(self.tbl_int, [
            ("Ver intervenciones del ticket seleccionado", self._ver_intervenciones, True)]),
            "Intervenciones")
        self.tabs.addTab(self._page(_tabla(["Contratos y bolsas de horas — usa los botones"]), [
            ("➕  Nuevo contrato SLA", self._nuevo_contrato, True),
            ("➕  Nueva bolsa de horas", self._nueva_bolsa, False),
            ("Consumir horas", self._consumir_horas, False)]), "Contratos / SLA")
        # ── Mantenimiento (GMAO) MIGRADO: Activos · Órdenes de trabajo · Planes preventivos ──
        # Composición: se reutiliza ÍNTEGRAMENTE `GMAODashboardWindow` (sus tablas, acciones y motor
        # `services/gmao`) reparentando sus 3 páginas operativas aquí. No se duplica lógica (N7).
        try:
            from src.gui.gmao_dashboard import GMAODashboardWindow
            self._gmao = GMAODashboardWindow(usuario=self.usuario, callback_vuelta=None)
            pag_act = self._gmao.tabs.widget(0)
            pag_ot = self._gmao.tabs.widget(1)
            pag_plan = self._gmao.tabs.widget(2)
            self.tabs.addTab(pag_act, "Activos")
            self.tabs.addTab(pag_ot, "Órdenes de trabajo")
            self.tabs.addTab(pag_plan, "Planes preventivos")
        except Exception as e:
            logger.error("embed GMAO en Soporte Posventa: %s", e)
            self._gmao = None

        self.tabs.addTab(self._page(self.tbl_kpi, []), "KPIs")   # unificados (SAT + GMAO)
        # Delegación a SOMA — SOLO SUPERADMIN: respuesta automática a tickets de soporte nuevos
        # (ver services.soma_delegacion.catalogo, pantalla="sat").
        if str((self.usuario or {}).get("perfil", "")).strip().upper() == "SUPERADMIN":
            from src.gui.soma_delegacion_gui import DelegacionSomaPanel
            self.tabs.addTab(DelegacionSomaPanel(pantalla="sat", usuario=self.usuario),
                            "Delegación IA")
        root.addWidget(self.tabs)
        self._load()

    def _page(self, tabla, botones):
        """Cada pestaña lleva su PROPIO botón 'Actualizar', arriba a la derecha de su tabla —
        antes había uno solo, compartido, encima de todo el QTabWidget."""
        w = QWidget(); l = QVBoxLayout(w)
        bar = QHBoxLayout()
        for txt, fn, primary in botones:
            bar.addWidget(_btn(txt, fn, primary=primary))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        l.addLayout(bar); l.addWidget(tabla)
        return w

    def _load(self):
        eid = _empresa()
        filas_kpi = []            # (ámbito, kpi, valor) — tabla KPIs unificada
        ksat, kgmao = {}, {}
        # ── Soporte (SAT): tickets + KPIs ──
        try:
            from src.services.sat import analitica as _sat_an, tickets
            tks = tickets.listar(id_empresa=eid)
            self.tbl_tk.setRowCount(len(tks))
            for i, x in enumerate(tks):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("asunto"),
                                       x.get("prioridad"), x.get("estado"), x.get("tecnico")]):
                    self.tbl_tk.setItem(i, j, _it(v))
            ksat = _sat_an.kpis(id_empresa=eid) or {}
            for nombre, val in ksat.items():
                filas_kpi.append(("Soporte (SAT)", nombre, val))
        except Exception as e:
            logger.error("load SAT: %s", e)
        # ── Satisfacción (CSAT): respuestas a la encuesta enviada al resolver/cerrar un ticket ──
        try:
            from src.services.sat import sat_pro
            kcsat = sat_pro.csat(id_empresa=eid) or {}
            for nombre, val in kcsat.items():
                filas_kpi.append(("Satisfacción (CSAT)", nombre, val))
        except Exception as e:
            logger.error("csat KPI: %s", e)
        # ── Mantenimiento (GMAO) migrado: refresca activos/OT/planes + KPIs ──
        if getattr(self, "_gmao", None) is not None:
            try:
                self._gmao._load()
            except Exception as e:
                logger.error("load GMAO embebido: %s", e)
        try:
            from src.services.gmao import analitica as _gmao_an
            kgmao = _gmao_an.kpis(id_empresa=eid) or {}
            for nombre, val in kgmao.items():
                filas_kpi.append(("Mantenimiento (GMAO)", nombre, val))
        except Exception as e:
            logger.error("kpis GMAO: %s", e)
        # ── Tabla KPIs UNIFICADA ──
        self.tbl_kpi.setRowCount(len(filas_kpi))
        for i, (ambito, nombre, val) in enumerate(filas_kpi):
            self.tbl_kpi.setItem(i, 0, _it(ambito))
            self.tbl_kpi.setItem(i, 1, _it(nombre))
            self.tbl_kpi.setItem(i, 2, _it(val))
        self.lbl.setText(
            f"SAT — Abiertos: {ksat.get('tickets_abiertos', 0)} · SLA: {ksat.get('cumplimiento_sla_pct', 0)}%"
            f"   |   Mantenimiento — MTTR: {kgmao.get('mttr_horas', 0)}h · "
            f"Disponibilidad: {kgmao.get('disponibilidad_pct', 0)}%")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _set(self, msg, nivel="info"):
        self.lbl.setText(msg)
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "Posventa", msg, nivel=nivel)
        except Exception:
            pass

    def _ticket_sel(self):
        row = self.tbl_tk.currentRow()
        if row < 0:
            return None
        it = self.tbl_tk.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _uid(self):
        return (self.usuario or {}).get("id")

    # ── Tickets ───────────────────────────────────────────────────────────────
    def _nueva_incidencia(self):
        if not _puede(self.usuario, "tickets.crear"):
            self._set("Permiso requerido: tickets.crear", nivel="warning"); return
        dlg = _NuevoTicketDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.sat import tickets
            tid = tickets.crear_ticket(id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Ticket creado: {tid}" if tid else "No se pudo crear el ticket.",
                     nivel="success" if tid else "error")
            self._load()

    def _asignar(self):
        if not _puede(self.usuario, "tickets.gestionar"):
            self._set("Permiso requerido: tickets.gestionar", nivel="warning"); return
        tid = self._ticket_sel()
        if not tid:
            self._set("Selecciona un ticket.", nivel="warning"); return
        tec, ok = QInputDialog.getInt(self, "Asignar ticket", "ID del técnico:", self._uid() or 0, 0, 10_000_000, 1)
        if not ok:
            return
        from src.services.sat import tickets
        r = tickets.asignar(tid, tec, id_empresa=_empresa())
        self._set(f"Ticket {tid} asignado al técnico {tec}" if r.get("ok") else f"Ticket {tid}: {r.get('error')}",
                 nivel="success" if r.get("ok") else "error")
        self._load()

    def _ticket_estado(self, nuevo):
        if not _puede(self.usuario, "tickets.gestionar"):
            self._set("Permiso requerido: tickets.gestionar", nivel="warning"); return
        tid = self._ticket_sel()
        if not tid:
            self._set("Selecciona un ticket.", nivel="warning"); return
        from src.services.sat import tickets
        r = tickets.cambiar_estado(tid, nuevo, id_empresa=_empresa())
        if r.get("ok") and nuevo in ("resuelto", "cerrado"):
            try:
                from src.services.sat import sat_pro
                # id_cliente no viene en cambiar_estado(); se busca el ticket para tener el dato si es posible.
                tk = None
                try:
                    tk = tickets.obtener(tid)
                except Exception:
                    pass
                sat_pro.enviar_encuesta(tid, id_cliente=(tk or {}).get("id_cliente"), id_empresa=_empresa())
            except Exception as e:
                logger.debug("enviar_encuesta: %s", e)
        self._set(f"Ticket {tid} → {r.get('estado')}" if r.get("ok") else f"Ticket {tid}: {r.get('error')}",
                 nivel="success" if r.get("ok") else "error")
        self._load()

    def _comentar(self):
        if not _puede(self.usuario, "tickets.gestionar"):
            self._set("Permiso requerido: tickets.gestionar", nivel="warning"); return
        tid = self._ticket_sel()
        if not tid:
            self._set("Selecciona un ticket.", nivel="warning"); return
        texto, ok = QInputDialog.getMultiLineText(self, "Comentar ticket", "Comentario:")
        if not ok or not texto.strip():
            return
        from src.services.sat import tickets
        cid = tickets.comentar(tid, texto.strip(), autor=self._uid(), id_empresa=_empresa())
        self._set(f"Comentario añadido al ticket {tid}" if cid else "No se pudo comentar.",
                 nivel="success" if cid else "error")

    def _intervencion(self):
        if not _puede(self.usuario, "tickets.gestionar"):
            self._set("Permiso requerido: tickets.gestionar", nivel="warning"); return
        tid = self._ticket_sel()
        if not tid:
            self._set("Selecciona un ticket.", nivel="warning"); return
        dlg = _IntervencionDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.sat import intervenciones
            iid = intervenciones.registrar_intervencion(id_ticket=tid, tecnico=self._uid(),
                                                         id_empresa=_empresa(), **dlg.resultado)
            self._set(f"Intervención {iid} registrada en el ticket {tid}" if iid
                      else "No se pudo registrar la intervención.", nivel="success" if iid else "error")

    def _ver_intervenciones(self):
        tid = self._ticket_sel()
        if not tid:
            self._set("Selecciona un ticket en la pestaña Tickets.", nivel="warning"); return
        from src.services.sat import intervenciones
        ivs = intervenciones.listar(id_ticket=tid, id_empresa=_empresa())
        self.tbl_int.setRowCount(len(ivs))
        for i, x in enumerate(ivs):
            for j, v in enumerate([x.get("id"), x.get("id_ticket"), x.get("tipo"), x.get("tecnico"),
                                   x.get("horas"), x.get("descripcion")]):
                self.tbl_int.setItem(i, j, _it(v))
        self._set(f"Intervenciones del ticket {tid}: {len(ivs)}", nivel="info")

    # ── Contratos / SLA / Bolsa de horas ──────────────────────────────────────
    def _nuevo_contrato(self):
        if not _puede(self.usuario, "sat.admin"):
            self._set("Permiso requerido: sat.admin", nivel="warning"); return
        d = _FormDialog("Nuevo contrato SLA", [
            ("cli", "ID del cliente:", "int", 0, None),
            ("cob", "Cobertura:", "combo", None, ["estandar", "premium", "24x7"]),
        ], self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.valores(); cli = int(v["cli"]); cob = v["cob"]
        from src.services.sat import contratos_sla
        cid = contratos_sla.crear_contrato(cli, cobertura=cob, id_empresa=_empresa())
        self._set(f"Contrato SLA creado: {cid} (cliente {cli}, {cob})" if cid else "No se pudo crear el contrato.",
                 nivel="success" if cid else "error")

    def _nueva_bolsa(self):
        if not _puede(self.usuario, "sat.admin"):
            self._set("Permiso requerido: sat.admin", nivel="warning"); return
        d = _FormDialog("Nueva bolsa de horas", [
            ("cli", "ID del cliente:", "int", 0, None),
            ("horas", "Horas totales:", "double", 10, None),
        ], self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.valores(); cli = int(v["cli"]); horas = float(v["horas"])
        from src.services.sat import sat_pro
        r = sat_pro.crear_bolsa_horas(horas, id_cliente=cli, id_empresa=_empresa())
        bid = r.get("id_bolsa") if isinstance(r, dict) else r
        self._set(f"Bolsa de horas creada: {bid} ({horas}h, cliente {cli})" if bid else "No se pudo crear la bolsa.",
                 nivel="success" if bid else "error")

    def _consumir_horas(self):
        if not _puede(self.usuario, "sat.admin"):
            self._set("Permiso requerido: sat.admin", nivel="warning"); return
        d = _FormDialog("Consumir horas", [
            ("bid", "ID de la bolsa:", "int", 0, None),
            ("horas", "Horas a consumir:", "double", 1, None),
        ], self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.valores(); bid = int(v["bid"]); horas = float(v["horas"])
        tid = self._ticket_sel()
        from src.services.sat import sat_pro
        r = sat_pro.consumir_horas(bid, horas, id_ticket=tid, id_empresa=_empresa())
        if isinstance(r, dict) and r.get("ok"):
            self._set(f"Consumidas {horas}h de la bolsa {bid}. Saldo: {r.get('saldo', '—')}", nivel="success")
        else:
            self._set(f"Bolsa {bid}: {r.get('error') if isinstance(r, dict) else 'no disponible'}", nivel="error")


class _FormDialog(QDialog):
    """Formulario frameless reutilizable (sustituye a las secuencias de QInputDialog): SIN barra negra de
    Windows, esquinas redondeadas con contorno neón y botones con texto visible + hover swap. `campos` =
    lista de (clave, etiqueta, tipo, default, opciones); tipo ∈ {'int','double','combo'}. `valores()` devuelve
    un dict clave→valor."""

    def __init__(self, titulo, campos, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{color:#E6EDF3;background:transparent;border:none;}}")
        self.setMinimumWidth(440)
        self._drag = None
        self._campos = campos
        self._widgets = {}
        f = QFormLayout(self); f.setContentsMargins(22, 18, 22, 18); f.setSpacing(10)
        _tit = QLabel(titulo)
        _tit.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;background:transparent;border:none;")
        hdr = QHBoxLayout()
        hdr.addWidget(_tit); hdr.addStretch()
        _x = _EtiquetaX(); _x.clicked.connect(self.reject)
        hdr.addWidget(_x)
        f.addRow(hdr)
        # Nota: ni QSpinBox ni QDoubleSpinBox se usan aquí — el QSpinBox no aceptaba clic/foco en
        # este formulario (confirmado por el usuario) y el QDoubleSpinBox, con el mismo origen
        # (la app oculta sus flechas arriba/abajo vía QSS `::up-button/::down-button{width:0px;...}`,
        # lo que rompe su hit-test/pintado en el estilo nativo de Windows), dejaba de mostrarse por
        # completo. Se sustituyen ambos por un QLineEdit + validador, igual que el resto de la app
        # introduce cualquier valor numérico.
        for clave, etq, tipo, default, opciones in campos:
            if tipo == "int":
                from PyQt6.QtGui import QIntValidator
                w = QLineEdit(str(int(default or 0)))
                w.setValidator(QIntValidator(0, 10_000_000, w))
            elif tipo == "double":
                from PyQt6.QtGui import QDoubleValidator
                w = QLineEdit(f"{float(default or 0):.2f}")
                val = QDoubleValidator(0.0, 1_000_000.0, 2, w)
                val.setNotation(QDoubleValidator.Notation.StandardNotation)
                w.setValidator(val)
            else:  # combo
                w = _combo(list(opciones or []))
            self._widgets[clave] = w
            f.addRow(etq, w)
        row = QHBoxLayout()
        row.addWidget(_btn("Aceptar", self.accept, primary=True))
        f.addRow(row)

    def valores(self):
        out = {}
        for clave, _etq, tipo, _d, _o in self._campos:
            w = self._widgets[clave]
            if tipo == "int":
                out[clave] = int(w.text() or 0)
            elif tipo == "double":
                try:
                    out[clave] = float((w.text() or "0").replace(",", "."))
                except ValueError:
                    out[clave] = 0.0
            else:
                out[clave] = w.currentText()
        return out

    # Arrastre (ventana sin barra de título de Windows).
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)


class _NuevoTicketDialog(QDialog):
    """Alta de ticket/incidencia (reutiliza tickets.crear_ticket)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva incidencia / ticket")
        # SIN barra negra de Windows + contorno neón con esquinas redondeadas (se cierra con Cancelar).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"QDialog{{background:{_BG};color:#E6EDF3;border:2px solid {_CIAN};"
                           f"border-radius:14px;}}QLabel{{color:#E6EDF3;background:transparent;border:none;}}")
        self.setMinimumWidth(460)
        self._drag = None
        f = QFormLayout(self)
        f.setContentsMargins(22, 18, 22, 18); f.setSpacing(10)
        _tit = QLabel("🎫  Nueva incidencia / ticket")
        _tit.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;background:transparent;border:none;")
        hdr = QHBoxLayout()
        hdr.addWidget(_tit); hdr.addStretch()
        _x = _EtiquetaX(); _x.clicked.connect(self.reject)
        hdr.addWidget(_x)
        f.addRow(hdr)
        self.in_asunto = QLineEdit(); self.in_asunto.setPlaceholderText("Asunto")
        self.in_desc = QTextEdit(); self.in_desc.setMaximumHeight(90)
        self.in_desc.setPlaceholderText("Descripción de la incidencia")
        self.in_cli = QLineEdit(); self.in_cli.setPlaceholderText("(opcional) ID de cliente")
        self.cb_prio = _combo(["media", "baja", "alta", "critica"])
        f.addRow("Asunto:", self.in_asunto)
        f.addRow("Descripción:", self.in_desc)
        f.addRow("Cliente:", self.in_cli)
        f.addRow("Prioridad:", self.cb_prio)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        f.addRow(row)

    def _ok(self):
        asunto = self.in_asunto.text().strip()
        if not asunto:
            return
        cli = self.in_cli.text().strip()
        try:
            cli = int(cli) if cli else None
        except ValueError:
            cli = None
        self.resultado = {"asunto": asunto, "descripcion": self.in_desc.toPlainText().strip() or None,
                          "id_cliente": cli, "prioridad": self.cb_prio.currentText()}
        self.accept()

    # Arrastre de la ventana sin marco (no hay barra de título de Windows).
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)


class _IntervencionDialog(QDialog):
    """Registro de intervención de un ticket (reutiliza intervenciones.registrar_intervencion). Usa
    `_dialogo_frameless` (X roja + centrado ya resueltos) en vez del `QDoubleSpinBox` que llevaba
    antes para "Horas" — mismo defecto ya corregido en `_FormDialog` (las flechas arriba/abajo
    ocultas por QSS rompen su pintado/foco en el estilo nativo de Windows)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        v = _dialogo_frameless(self, "Registrar intervención", ancho=420)
        v.addWidget(_lbl("Tipo"))
        self.cb_tipo = _combo(["visita", "remoto", "taller", "telefonica"])
        v.addWidget(self.cb_tipo)
        v.addWidget(_lbl("Descripción"))
        self.in_desc = _inp("Descripción del trabajo realizado")
        v.addWidget(self.in_desc)
        v.addWidget(_lbl("Horas"))
        self.in_horas = _inp("1,00")
        self.in_horas.setText("1.00")
        from PyQt6.QtGui import QDoubleValidator
        val = QDoubleValidator(0.0, 1000.0, 2, self.in_horas)
        val.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_horas.setValidator(val)
        v.addWidget(self.in_horas)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Registrar", self._ok, primary=True))
        v.addLayout(fila)

    def _ok(self):
        try:
            horas = float((self.in_horas.text() or "0").replace(",", "."))
        except ValueError:
            horas = 0.0
        self.resultado = {"tipo": self.cb_tipo.currentText(),
                          "descripcion": self.in_desc.text().strip() or None,
                          "horas": horas}
        self.accept()


class TicketsWindow(SATDashboardWindow): """Vista de tickets (reutiliza el dashboard operativo)."""
class ContratosSATWindow(SATDashboardWindow): """Vista de contratos/SLA (reutiliza el dashboard operativo)."""
class IntervencionesWindow(SATDashboardWindow): """Vista de intervenciones (reutiliza el dashboard operativo)."""


class _ArticuloDialog(QDialog):
    """Alta/edición de un artículo de la Base de conocimiento (reutiliza `kb.crear_articulo`/
    `kb.editar_articulo`). En modo edición, `kb.editar_articulo` solo admite versionar el CUERPO
    (crea una fila en `kb_versiones`) — título/categoría/etiquetas no se pueden cambiar tras la
    creación en el servicio actual, así que en ese modo se muestran de solo lectura y únicamente
    el cuerpo es editable (no se inventa soporte que el backend no tiene)."""

    def __init__(self, parent=None, articulo=None):
        super().__init__(parent)
        self.resultado = None
        self._editar = articulo is not None
        titulo_dlg = "✏️  Editar artículo" if self._editar else "➕  Nuevo artículo"
        v = _dialogo_frameless(self, titulo_dlg, ancho=480)
        v.addWidget(_lbl("Título"))
        self.in_titulo = _inp("Título del artículo")
        v.addWidget(self.in_titulo)
        v.addWidget(_lbl("Cuerpo"))
        self.in_cuerpo = QTextEdit(); self.in_cuerpo.setMaximumHeight(160)
        self.in_cuerpo.setPlaceholderText("Contenido del artículo")
        v.addWidget(self.in_cuerpo)
        v.addWidget(_lbl("Categoría"))
        self.in_cat = _inp("(opcional) nombre de categoría")
        v.addWidget(self.in_cat)
        v.addWidget(_lbl("Etiquetas"))
        self.in_etq = _inp("etiqueta1, etiqueta2, ...")
        v.addWidget(self.in_etq)
        if self._editar:
            self.in_titulo.setText(articulo.get("titulo") or "")
            self.in_titulo.setReadOnly(True)
            self.in_cuerpo.setPlainText(articulo.get("cuerpo") or "")
            self.in_cat.setText("")
            self.in_cat.setEnabled(False)
            self.in_etq.setText(articulo.get("etiquetas") or "")
            self.in_etq.setEnabled(False)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar" if self._editar else "Crear", self._ok, primary=True))
        v.addLayout(fila)

    def _ok(self):
        cuerpo = self.in_cuerpo.toPlainText().strip()
        if not cuerpo:
            return
        if self._editar:
            self.resultado = {"cuerpo": cuerpo}
        else:
            titulo = self.in_titulo.text().strip()
            if not titulo:
                return
            self.resultado = {"titulo": titulo, "cuerpo": cuerpo,
                              "categoria": self.in_cat.text().strip() or None,
                              "etiquetas": self.in_etq.text().strip() or None}
        self.accept()


class KnowledgeBaseWindow(QWidget):
    """Base de conocimiento: búsqueda/lectura de artículos + alta/edición/publicación (`kb.gestionar`)."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Base de conocimiento")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        self.txt = QLineEdit(); self.txt.setPlaceholderText("🔍 Buscar...")
        cab.addWidget(self.txt); cab.addWidget(_btn("🔍", self._buscar, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        acciones = QHBoxLayout()
        acciones.addWidget(_btn("➕ Nuevo artículo", self._nuevo_articulo, primary=True))
        acciones.addWidget(_btn("✏️ Editar", self._editar_articulo, primary=False))
        acciones.addWidget(_btn("Publicar/Despublicar", self._publicar_articulo, primary=False))
        acciones.addStretch()
        root.addLayout(acciones)
        self.tbl = _tabla(["ID", "Titulo", "Etiquetas", "Publicado", "Vistas"])
        root.addWidget(self.tbl)
        self._buscar()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _set(self, msg, nivel="info"):
        self.lbl.setText(msg)
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "Base de conocimiento", msg, nivel=nivel)
        except Exception:
            pass

    def _articulo_sel(self):
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _buscar(self):
        try:
            from src.services.sat import kb
            # Quien puede gestionar la KB ve también los borradores (sin publicar) para poder
            # editarlos/publicarlos; el resto solo ve lo ya publicado (comportamiento original).
            solo_pub = not _puede(self.usuario, "kb.gestionar")
            arts = kb.buscar(self.txt.text(), solo_publicados=solo_pub, id_empresa=_empresa())
            self.tbl.setRowCount(len(arts))
            for i, a in enumerate(arts):
                pub = "Sí" if a.get("publicado") else "No"
                for j, v in enumerate([a.get("id"), a.get("titulo"), a.get("etiquetas"), pub, a.get("vistas")]):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("buscar KB: %s", e)

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _nuevo_articulo(self):
        if not _puede(self.usuario, "kb.gestionar"):
            self._set("Permiso requerido: kb.gestionar", nivel="warning"); return
        dlg = _ArticuloDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.resultado:
            from src.services.sat import kb
            r = dlg.resultado
            id_cat = kb.crear_categoria(r["categoria"], id_empresa=_empresa()) if r.get("categoria") else None
            aid = kb.crear_articulo(r["titulo"], r["cuerpo"], id_categoria=id_cat,
                                    etiquetas=r.get("etiquetas"), publicado=False,
                                    autor=(self.usuario or {}).get("id"), id_empresa=_empresa())
            self._set("Artículo creado correctamente (sin publicar)." if aid else
                      "No se pudo crear el artículo.", nivel="success" if aid else "error")
            if aid:
                self._buscar()

    def _editar_articulo(self):
        if not _puede(self.usuario, "kb.gestionar"):
            self._set("Permiso requerido: kb.gestionar", nivel="warning"); return
        aid = self._articulo_sel()
        if not aid:
            self._set("Selecciona un artículo.", nivel="warning"); return
        from src.services.sat import kb
        art = kb.ver_articulo(aid)
        if not art:
            self._set("No se pudo cargar el artículo.", nivel="error"); return
        dlg = _ArticuloDialog(self, articulo=art)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.resultado:
            ok = kb.editar_articulo(aid, dlg.resultado["cuerpo"], autor=(self.usuario or {}).get("id"),
                                    id_empresa=_empresa())
            self._set("Artículo actualizado." if ok else "No se pudo actualizar el artículo.",
                     nivel="success" if ok else "error")
            if ok:
                self._buscar()

    def _publicar_articulo(self):
        if not _puede(self.usuario, "kb.gestionar"):
            self._set("Permiso requerido: kb.gestionar", nivel="warning"); return
        aid = self._articulo_sel()
        if not aid:
            self._set("Selecciona un artículo.", nivel="warning"); return
        from src.services.sat import kb
        art = kb.ver_articulo(aid)
        if not art:
            self._set("No se pudo cargar el artículo.", nivel="error"); return
        nuevo_estado = not bool(art.get("publicado"))
        ok = kb.publicar(aid, publicado=nuevo_estado)
        self._set(("Publicado." if nuevo_estado else "Despublicado.") if ok else
                  "No se pudo cambiar el estado.", nivel="success" if ok else "error")
        if ok:
            self._buscar()


class PortalSATWindow(QWidget):
    """SAT-G — Portal de cliente: crear ticket, consultar tickets/SLA/intervenciones."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, id_cliente=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.id_cliente = id_cliente or (usuario or {}).get("id_cliente")
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Portal de soporte")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        root.addWidget(QLabel("Nuevo ticket"))
        self.asunto = QLineEdit(); self.asunto.setPlaceholderText("Asunto")
        self.desc = QTextEdit(); self.desc.setPlaceholderText("Describe tu incidencia...")
        self.desc.setMaximumHeight(90)
        root.addWidget(self.asunto); root.addWidget(self.desc)
        root.addWidget(_btn("Crear ticket", self._crear, primary=True))
        self.tbl = _tabla(["Codigo", "Asunto", "Estado", "SLA"])
        root.addWidget(QLabel("Mis tickets")); root.addWidget(self.tbl)
        self._load()

    def _crear(self):
        if not self.asunto.text().strip():
            QMessageBox.warning(self, "Portal", "Indica un asunto."); return
        try:
            from src.services.sat import tickets
            tid = tickets.crear_ticket(self.asunto.text().strip(), descripcion=self.desc.toPlainText(),
                                       id_cliente=self.id_cliente, canal="portal", id_empresa=_empresa())
            QMessageBox.information(self, "Portal", f"Ticket creado: TK{tid:06d}" if tid else "Error")
            self.asunto.clear(); self.desc.clear(); self._load()
        except Exception as e:
            QMessageBox.critical(self, "Portal", str(e))

    def _load(self):
        try:
            from src.services.sat import tickets
            tks = tickets.listar(id_cliente=self.id_cliente, id_empresa=_empresa()) if self.id_cliente else []
            self.tbl.setRowCount(len(tks))
            for i, x in enumerate(tks):
                for j, v in enumerate([x.get("codigo"), x.get("asunto"), x.get("estado"),
                                       x.get("sla_vencimiento")]):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("portal load: %s", e)
