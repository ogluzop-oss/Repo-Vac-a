"""
Eventos — módulo standalone (extraído de la pestaña "PLANIFICAR CITAS" de `ConfiguracionWindow`,
petición explícita). Calendario + agenda única (`services.calendario`, BD) con sincronización de
solo lectura desde Google Calendar. Reutiliza TAL CUAL los widgets ya existentes de
`configuracion.py` (`_VentasCalendarWidget`/`_TimeDropdown`/`_CloseCircleBtn` — no se duplica
ningún dibujado ni estilo, solo se importan) y mueve aquí la lógica de la pestaña, que vivía
exclusivamente en ella (sin otro consumidor).

Acceso: SOLO SUPERADMIN (petición explícita) — ver el gate en `menu_principal.py`/
`services.seguridad.modulos_menu` (ausente de `DEFAULT_ADMINISTRADOR`/`DEFAULT_OPERARIO`, lo que lo
hace exclusivo de SUPERADMIN por la regla general de `default_visible`).
"""

import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import _blindar_tamano_fijo
from src.gui.configuracion import _CloseCircleBtn, _TimeDropdown, _VentasCalendarWidget
from src.utils.i18n import tr

_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_VENTAS_SIDEBAR = "#111418"
_VENTAS_BG = "#0E1117"
_EVENTS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "eventos_citas.json"))


class EventosWindow(QWidget):
    """Calendario + agenda de eventos/citas. Ventana de nivel superior — antes pestaña
    "PLANIFICAR CITAS" de Configuración. Exclusivo de SUPERADMIN."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self.callback_vuelta = callback_vuelta
        self.usuario = usuario or {}
        self._json_migrado = False
        self._cal_popup = None
        self.setStyleSheet(f"background-color:{_FONDO};")
        self.setWindowTitle("EVENTOS")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color:{_FONDO};")
        h_ly = QHBoxLayout(header)
        h_ly.setContentsMargins(28, 0, 28, 0)
        titulo = QLabel(tr("cfg.eventos_title", default="EVENTOS"))
        titulo.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;letter-spacing:1px;")
        h_ly.addWidget(titulo)
        h_ly.addStretch()
        btn_volver = QPushButton("✕")
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_volver.setFixedSize(50, 50)
        btn_volver.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;"
            "border-radius:25px;padding:0;font-family:'Segoe UI';font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0E1117;}"
        )
        btn_volver.setProperty("sin_glow", True)
        _blindar_tamano_fijo(btn_volver, 50, 50)
        btn_volver.clicked.connect(self.ejecutar_regreso)
        h_ly.addWidget(btn_volver)
        root.addWidget(header)

        root.addWidget(self._crear_contenido(), 1)

    def ejecutar_regreso(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()

    # --- CONTENIDO: CALENDARIO + AGENDA ---
    # (extraído verbatim de `ConfiguracionWindow._crear_page_citas` en configuracion.py.)
    def _crear_contenido(self):
        self._eventos = self._load_eventos()
        self._cal_popup = None
        page = QWidget()
        self._citas_page = page
        ly = QHBoxLayout(page)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        self._cal_widget = _VentasCalendarWidget()
        self._cal_widget.set_events(self._eventos)
        self._cal_widget.clicked.connect(self._on_calendar_clicked)

        cal_frame = QFrame()
        cal_frame.setStyleSheet(f"""
            QFrame {{
                background: {_VENTAS_SIDEBAR};
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        cal_frame_ly = QVBoxLayout(cal_frame)
        cal_frame_ly.setContentsMargins(12, 12, 12, 12)
        cal_frame_ly.addWidget(self._cal_widget)
        ly.addWidget(cal_frame, 2)

        form = QFrame()
        form.setStyleSheet(f"background: {_VENTAS_BG}; padding: 20px;")
        fl = QVBoxLayout(form)
        fl.setSpacing(15)
        fl.addWidget(
            QLabel(
                tr("cfg.detalles_del_evento", default="DETALLES DEL EVENTO"),
                styleSheet=f"color: {_CIAN}; font-weight: 900; font-family: 'Segoe UI';",
            )
        )

        fl.addWidget(QLabel(tr("cfg.asunto_lbl", default="ASUNTO:"), styleSheet="color: white; font-weight: bold;"))
        self._cal_asunto = QLineEdit()
        self._cal_asunto.setPlaceholderText(tr("cfg.asunto_ph", default="Introduzca el nombre del asunto"))
        self._cal_asunto.setStyleSheet(f"""
            QLineEdit {{
                background: #161B22; color: white; border: 2px solid {_CIAN};
                border-radius: 12px; padding: 10px 14px;
                font-family: 'Segoe UI'; font-size: 14px;
            }}
            QLineEdit::placeholder {{
                color: #6B737E;
            }}
        """)
        fl.addWidget(self._cal_asunto)

        fl.addWidget(QLabel(tr("cfg.hora_inicio", default="HORA INICIO:"), styleSheet="color: white; font-weight: bold;"))
        ly_inicio, self._inicio_h, self._inicio_m = self._crear_selector_tiempo_windows()
        fl.addLayout(ly_inicio)

        fl.addWidget(QLabel(tr("cfg.hora_fin", default="HORA FIN:"), styleSheet="color: white; font-weight: bold;"))
        ly_fin, self._fin_h, self._fin_m = self._crear_selector_tiempo_windows()
        fl.addLayout(ly_fin)

        fl.addStretch()
        btn_save = QPushButton(tr("cfg.save_event", default="Guardar evento"))
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #0E1117; color: #238636; border: 2px solid #238636; border-radius: 10px;
                padding: 12px; font-weight: 900;
            }
            QPushButton:hover {
                background: #238636; color: #0E1117;
            }
        """)
        btn_save.clicked.connect(self._guardar_evento)

        btn_sync_google = QPushButton("🔄  " + tr("cfg.sync_google", default="SINCRONIZAR CON GOOGLE"))
        btn_sync_google.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sync_google.setStyleSheet(f"""
            QPushButton {{
                background: #0E1117; color: {_CIAN}; border: 2px solid {_CIAN}; border-radius: 10px;
                padding: 12px; font-weight: 900;
            }}
            QPushButton:hover {{
                background: {_CIAN}; color: #0E1117;
            }}
        """)
        btn_sync_google.clicked.connect(self._sincronizar_google_calendar)

        fila_btns = QHBoxLayout(); fila_btns.setSpacing(10)
        fila_btns.addWidget(btn_save)
        fila_btns.addWidget(btn_sync_google)
        fl.addLayout(fila_btns)

        ly.addWidget(form, 1)
        return page

    # ── Agenda unificada (services/calendario) ───────────────────────────────
    def _load_eventos(self):
        """Agenda UNIFICADA desde services/calendario (BD): incluye las citas del usuario Y los eventos
        generados por CRM/SAT (misma agenda, sin módulos paralelos). Migra una sola vez las citas del
        JSON legado. Devuelve {yyyy-mm-dd: [ {_id, asunto, hora_inicio, hora_fin, tipo}, ... ]}."""
        self._migrar_json_citas()
        out = {}
        try:
            from src.services import calendario
            import datetime as _dt
            hoy = _dt.date.today()
            desde = f"{hoy.year - 1}-01-01 00:00:00"
            hasta = f"{hoy.year + 2}-12-31 23:59:59"
            for e in calendario.eventos_rango(desde, hasta):
                fecha_str, hi = self._fmt_fecha_hora(e.get("inicio"))
                _, hf = self._fmt_fecha_hora(e.get("fin")) if e.get("fin") else (None, hi)
                if not fecha_str:
                    continue
                out.setdefault(fecha_str, []).append({
                    "_id": e.get("id"),
                    "asunto": e.get("titulo") or e.get("descripcion") or "Evento",
                    "hora_inicio": hi, "hora_fin": hf or hi,
                    "tipo": e.get("tipo") or "evento",
                })
        except Exception:
            pass
        return out

    def _usuario_id(self):
        return (self.usuario or {}).get("id")

    def _fmt_fecha_hora(self, valor):
        """(yyyy-mm-dd, 'Hh MMmin') desde un datetime/str de BD, o (None, '0h 00min')."""
        import datetime as _dt
        if valor is None:
            return None, "0h 00min"
        try:
            if isinstance(valor, str):
                valor = _dt.datetime.fromisoformat(valor.replace("T", " ").split(".")[0])
            return valor.strftime("%Y-%m-%d"), f"{valor.hour}h {valor.minute:02d}min"
        except Exception:
            return None, "0h 00min"

    def _hora_a_dt(self, fecha_str, hora_txt):
        """'yyyy-mm-dd' + 'Hh MMmin' → 'yyyy-mm-dd HH:MM:00'."""
        h = m = 0
        try:
            toks = (hora_txt or "").split()
            if toks:
                h = int(toks[0].rstrip("h") or 0)
            if len(toks) > 1:
                m = int(toks[1].rstrip("min") or 0)
        except Exception:
            h = m = 0
        return f"{fecha_str} {h:02d}:{m:02d}:00"

    def _migrar_json_citas(self):
        """Importa UNA sola vez las citas del JSON legado (documentos/eventos_citas.json) a
        services/calendario y archiva el fichero, para no perder las citas previas del usuario."""
        if getattr(self, "_json_migrado", False):
            return
        self._json_migrado = True
        try:
            path = _EVENTS_FILE
            if not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
            if data:
                from src.services import calendario
                for fecha_str, evs in data.items():
                    for ev in (evs or []):
                        calendario.crear_evento(
                            ev.get("asunto") or "Cita",
                            self._hora_a_dt(fecha_str, ev.get("hora_inicio", "0h 00min")),
                            fin=self._hora_a_dt(fecha_str, ev.get("hora_fin", "0h 00min")),
                            tipo="cita", creado_por=self._usuario_id())
            os.replace(path, path + ".migrado.bak")
        except Exception:
            pass

    def _recargar_eventos(self):
        self._eventos = self._load_eventos()
        if getattr(self, "_cal_widget", None):
            self._cal_widget.set_events(self._eventos)
            self._cal_widget.update()

    def _sincronizar_google_calendar(self):
        """Trae los eventos reales de Google Calendar (solo lectura) de los buzones Google
        conectados de la empresa hacia la agenda única (services.calendario). Si no hay ningún
        buzón Google conectado, avisa apuntando a Correo → Buzones; si hay varios, se sincronizan
        todos y se suma el total."""
        from src.db import correo as correo_db
        from src.services import calendario
        from src.services.correo import servicio as correo_svc

        buzones = [c for c in correo_db.listar_correos()
                  if c.get("proveedor") == "google"
                  and correo_svc.estado_oauth(c["id_correo"]).get("conectado")]
        if not buzones:
            self._mostrar_cita_dialogo(
                "SIN CUENTA DE GOOGLE CONECTADA",
                "No hay ninguna cuenta de Google conectada. Ve a Correo → Buzones y pulsa "
                "«CONECTAR (OAuth)» sobre un buzón de proveedor Google.",
                es_error=True,
                btn_texto="ENTENDIDO",
            )
            return

        total = 0
        mensajes = []
        hubo_error_scope = False
        for b in buzones:
            n, msg = calendario.sincronizar_google(b["id_correo"])
            total += n
            mensajes.append(msg)
            if "reconectarse" in msg.lower():
                hubo_error_scope = True
        self._recargar_eventos()
        self._mostrar_cita_dialogo(
            "SINCRONIZACIÓN CON GOOGLE",
            f"{total} evento(s) sincronizado(s) en total.\n\n" + "\n".join(mensajes),
            es_error=hubo_error_scope,
            btn_texto="ACEPTAR",
        )

    def _mostrar_cita_dialogo(self, titulo, mensaje, es_error, btn_texto):
        """Dialog estilizado con texto de botón garantizado visible."""
        accent = "#E3B341" if es_error else "#238636"
        icono = "!" if es_error else "✓"

        from PyQt6.QtWidgets import QDialog
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dlg.setModal(True)
        dlg.setMinimumWidth(380)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame(dlg)
        panel.setStyleSheet(f"""
            QFrame {{
                background: #0D1117;
                border: 2px solid {accent};
                border-radius: 14px;
            }}
        """)
        p_ly = QVBoxLayout(panel)
        p_ly.setContentsMargins(24, 20, 24, 20)
        p_ly.setSpacing(14)

        h_ly = QHBoxLayout()
        h_ly.setSpacing(14)
        icon_lbl = QLabel(icono)
        icon_lbl.setFixedSize(42, 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            QLabel {{
                background: {accent}; color: #0D1117;
                border-radius: 21px; font-size: 22px; font-weight: 900;
                font-family: 'Segoe UI'; border: none;
            }}
        """)
        title_lbl = QLabel(titulo)
        title_lbl.setStyleSheet(
            f"color: {accent}; font-weight: 900; font-size: 15px;"
            " background: transparent; border: none; font-family: 'Segoe UI';"
        )
        h_ly.addWidget(icon_lbl)
        h_ly.addWidget(title_lbl, 1)
        p_ly.addLayout(h_ly)

        msg_lbl = QLabel(mensaje)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            "color: #E6EDF3; font-size: 13px; background: transparent;"
            " border: none; font-family: 'Segoe UI';"
        )
        p_ly.addWidget(msg_lbl)

        btn = QPushButton(btn_texto)
        btn.setFixedHeight(44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #0D1117; color: {accent};
                border-radius: 10px; font-weight: 900; font-size: 13px;
                font-family: 'Segoe UI'; border: 2px solid {accent};
            }}
            QPushButton:hover {{
                background: {accent}; color: #0D1117;
            }}
        """)
        btn.clicked.connect(dlg.accept)
        p_ly.addWidget(btn)

        outer.addWidget(panel)
        dlg.exec()

    def _guardar_evento(self):
        self._cerrar_cal_popup()

        asunto = self._cal_asunto.text().strip()
        if not asunto:
            self._mostrar_cita_dialogo(
                "INFORMACIÓN INCOMPLETA",
                "Para guardar un evento es necesario completar toda la información antes de guardarlo.",
                es_error=True,
                btn_texto="ENTENDIDO",
            )
            return

        fecha = self._cal_widget.selectedDate()
        fecha_str = fecha.toString("yyyy-MM-dd")
        hora_inicio = f"{self._inicio_h.currentText()} {self._inicio_m.currentText()}"
        hora_fin = f"{self._fin_h.currentText()} {self._fin_m.currentText()}"

        from src.services import calendario
        eid = calendario.crear_evento(
            asunto, self._hora_a_dt(fecha_str, hora_inicio),
            fin=self._hora_a_dt(fecha_str, hora_fin), tipo="cita", creado_por=self._usuario_id())
        self._recargar_eventos()
        self._cal_asunto.clear()

        if eid:
            self._mostrar_cita_dialogo(
                "EVENTO GUARDADO",
                f"El evento '{asunto}' se ha guardado para el {fecha.toString('dd/MM/yyyy')}.",
                es_error=False,
                btn_texto="ACEPTAR",
            )
        else:
            self._mostrar_cita_dialogo(
                "NO SE PUDO GUARDAR",
                "No se pudo guardar el evento en la agenda. Inténtalo de nuevo.",
                es_error=True,
                btn_texto="ENTENDIDO",
            )

    def _cerrar_cal_popup(self):
        if self._cal_popup is not None:
            try:
                self._cal_popup.hide()
                self._cal_popup.deleteLater()
            except Exception:
                pass
            self._cal_popup = None

    def _on_calendar_clicked(self, qdate):
        self._cerrar_cal_popup()
        fecha_str = qdate.toString("yyyy-MM-dd")
        eventos = self._eventos.get(fecha_str, [])
        if not eventos:
            return

        popup = QFrame(self._citas_page)
        popup.setMinimumWidth(240)
        popup.setStyleSheet(f"""
            QFrame {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        self._cal_popup = popup

        outer_ly = QVBoxLayout(popup)
        outer_ly.setContentsMargins(14, 12, 14, 18)
        outer_ly.setSpacing(8)

        hdr = QHBoxLayout()
        title = QLabel(f"📅  {qdate.toString('dd/MM/yyyy')}")
        title.setStyleSheet(
            f"color: {_CIAN}; font-weight: 900; font-size: 13px; background: transparent; border: none;"
        )
        btn_x = _CloseCircleBtn(self._cerrar_cal_popup)
        hdr.addWidget(title, 1)
        hdr.addWidget(btn_x)
        outer_ly.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_CIAN}; border: none;")
        outer_ly.addWidget(sep)

        def _hacer_editar(idx, pop):
            ev = self._eventos[fecha_str][idx]
            self._cal_asunto.setText(ev["asunto"])
            self._inicio_h._valor = ev["hora_inicio"].split()[0]
            self._inicio_h._refresh_btn()
            self._inicio_m._valor = ev["hora_inicio"].split()[1]
            self._inicio_m._refresh_btn()
            self._fin_h._valor = ev["hora_fin"].split()[0]
            self._fin_h._refresh_btn()
            self._fin_m._valor = ev["hora_fin"].split()[1]
            self._fin_m._refresh_btn()
            if ev.get("_id"):
                from src.services import calendario
                calendario.eliminar_evento(ev["_id"])
            self._recargar_eventos()
            self._cerrar_cal_popup()

        def _hacer_borrar(idx):
            ev = self._eventos[fecha_str][idx]
            if ev.get("_id"):
                from src.services import calendario
                calendario.eliminar_evento(ev["_id"])
            self._recargar_eventos()
            self._cerrar_cal_popup()

        for i, ev in enumerate(list(eventos)):
            ev_frame = QFrame()
            ev_frame.setStyleSheet(
                "QFrame { background: #161B22; border-radius: 10px; border: none; }"
            )
            ev_ly = QVBoxLayout(ev_frame)
            ev_ly.setContentsMargins(12, 8, 12, 12)
            ev_ly.setSpacing(6)

            lbl_asunto = QLabel(ev["asunto"])
            lbl_asunto.setStyleSheet(
                "color: white; font-weight: 900; font-size: 12px; background: transparent; border: none;"
            )
            lbl_asunto.setWordWrap(True)

            lbl_tiempo = QLabel(f"⏰  {ev['hora_inicio']} — {ev['hora_fin']}")
            lbl_tiempo.setStyleSheet(
                f"color: {_CIAN}; font-size: 11px; background: transparent; border: none;"
            )

            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            btn_edit = QPushButton("✏  " + tr("cfg.edit", default="EDITAR"))
            btn_edit.setFixedHeight(34)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setStyleSheet(f"""
                QPushButton {{
                    background: #1A2230; color: {_CIAN}; border: 1px solid {_CIAN};
                    border-radius: 6px; font-size: 11px; font-weight: 900;
                }}
                QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
            """)
            btn_edit.clicked.connect(lambda _c=False, idx=i: _hacer_editar(idx, popup))

            btn_del = QPushButton("🗑  " + tr("cfg.borrar", default="BORRAR"))
            btn_del.setFixedHeight(34)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background: #1A2230; color: #F85149; border: 1px solid #F85149;
                    border-radius: 6px; font-size: 11px; font-weight: 900;
                }
                QPushButton:hover { background: #F85149; color: #0E1117; border: 1px solid #F85149; }
            """)
            btn_del.clicked.connect(lambda _c=False, idx=i: _hacer_borrar(idx))

            btn_row.addWidget(btn_edit)
            btn_row.addWidget(btn_del)

            ev_ly.addWidget(lbl_asunto)
            ev_ly.addWidget(lbl_tiempo)
            ev_ly.addLayout(btn_row)
            outer_ly.addWidget(ev_frame)

        popup.show()
        popup.adjustSize()
        cur = self._citas_page.mapFromGlobal(QCursor.pos())
        pw, ph = popup.width(), popup.height()
        pr = self._citas_page.rect()
        x = min(cur.x() + 12, pr.width() - pw - 4)
        y = min(cur.y() + 12, pr.height() - ph - 4)
        popup.move(max(4, x), max(4, y))
        popup.raise_()

    def _crear_selector_tiempo_windows(self):
        """Crea un par de _TimeDropdown (Horas y Minutos) con estilo neón y scroll."""
        h_ly = QHBoxLayout()
        h_ly.setSpacing(10)

        combo_h = _TimeDropdown([f"{i}h" for i in range(24)], max_visible=5)
        combo_h.setFixedWidth(110)
        combo_h._btn.setFixedHeight(44)

        combo_m = _TimeDropdown(
            [f"{i:02}min" for i in range(0, 60, 5)], max_visible=5
        )
        combo_m.setFixedWidth(120)
        combo_m._btn.setFixedHeight(44)

        h_ly.addWidget(combo_h)
        h_ly.addWidget(combo_m)
        h_ly.addStretch()
        return h_ly, combo_h, combo_m
