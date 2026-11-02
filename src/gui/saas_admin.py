"""
SaaS — Administración de tenants + Portal del cliente (FASE SAAS-H / SAAS-N).

Panel de plataforma (SUPERADMIN): empresas, plan, estado, métricas SaaS (MRR/ARR/churn).
Portal del cliente: plan actual, consumo, suscripción. Estilo dark+cian.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_cargando, _btn_x, _combo, _dialogo_frameless, _tabla
from src.services.saas import ia_plan as _IA
from src.services.saas import licensing as _L, metricas as _M, planes as _P, suscripciones as _S
from src.services.saas import voz_plan as _VOZ

logger = logging.getLogger("saas.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _color_pct_ia(pct):
    """Umbral de color para el % de gasto diario de IA consumido — INVERTIDO respecto al patrón
    de "% completado" de `gestion_usuarios.py` (ahí 100% es bueno/verde; aquí un % ALTO de un
    límite de GASTO es la zona de peligro): verde por debajo de 50%, ámbar 50-89%, rojo desde 90%."""
    if pct >= 90:
        return "#F85149"
    if pct >= 50:
        return "#F5A623"
    return "#00FFC6"


class _PedirTextoDialog(QDialog):
    """Reemplazo de `QInputDialog.getText` (sin barra de Windows, esquinas redondeadas, botones
    con texto visible) — mismo criterio ya aplicado en `tesoreria_gui.py`/`rrhh_gestion.py`."""

    def __init__(self, titulo, prompt, texto="", parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        lbl = QLabel(prompt); lbl.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        v.addWidget(lbl)
        self.inp = QLineEdit(texto); self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;}")
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def valor(self):
        return self.inp.text()


def _pedir_texto(parent, titulo, prompt, texto=""):
    d = _PedirTextoDialog(titulo, prompt, texto, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class SaaSAdminWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        try:
            _P.sincronizar_planes()
        except Exception:
            pass
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("SaaS · Administración y Portal")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; }")
        root.addWidget(self.tabs)
        self._tab_portal()
        self._tab_ia()
        self._tab_voz()
        # "Empresas (plataforma)" y "CRM SaaS (embudo)" (MRR/ARR/licencias de TODAS las empresas
        # cliente + embudo de ventas del propio Smart Manager) se retiraron de aquí: el gate por
        # perfil == "SUPERADMIN" NO distinguía "el fundador" de "el SUPERADMIN de cualquier empresa
        # cliente" (SUPERADMIN es un rol interno de cada tenant, no una identidad única de
        # plataforma) — exponía datos confidenciales de otras empresas y del propio negocio del
        # operador a cualquier cliente. Esa información vive correctamente aislada en el Panel del
        # Fundador (`src/backend_central/` + `services/licencia_central/panel_fundador.py`, cuenta
        # única, sin relación con `usuarios` de ningún tenant).

    # ── Portal cliente (empresa activa) ───────────────────────────────────────
    def _tab_portal(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.lbl_plan = QLabel(""); self.lbl_plan.setStyleSheet(f"color:{_CIAN};font-size:15px;")
        lay.addWidget(self.lbl_plan)
        # Banner de aviso de vencimiento de la suscripción (oculto si no procede).
        self.lbl_aviso = QLabel(""); self.lbl_aviso.setWordWrap(True); self.lbl_aviso.setVisible(False)
        lay.addWidget(self.lbl_aviso)
        bar = QHBoxLayout()
        self.cmb_plan = _combo([(c, c) for c in _P.PLANES])
        self.cmb_plan.setMinimumWidth(150)   # evita texto cortado en el desplegable
        bar.addWidget(QLabel("Plan:")); bar.addWidget(self.cmb_plan)
        bar.addWidget(_btn("Cambiar plan", self._cambiar_plan, primary=True))
        bar.addWidget(_btn("Renovar", self._renovar, primary=True))
        bar.addWidget(_btn("Descargar última factura", self._descargar_factura, primary=True))
        bar.addWidget(_btn("Enviar factura por email", self._enviar_factura, primary=True))
        bar.addStretch()
        lay.addLayout(bar)

        # Domiciliación bancaria del cobro mensual: el IBAN se guarda cifrado y NUNCA se
        # vuelve a mostrar completo tras guardarlo — solo los 4 últimos dígitos.
        bar_iban = QHBoxLayout()
        bar_iban.addWidget(QLabel("Domiciliación bancaria:"))
        self.inp_iban = QLineEdit()
        self.inp_iban.setPlaceholderText("ES00 0000 0000 0000 0000 0000")
        self.inp_iban.setMinimumWidth(260)
        bar_iban.addWidget(self.inp_iban)
        bar_iban.addWidget(_btn("Guardar cuenta bancaria", self._guardar_iban, primary=True))
        self.lbl_iban = QLabel("")
        self.lbl_iban.setStyleSheet(f"color:{_DIM};font-size:13px;")
        bar_iban.addWidget(self.lbl_iban)
        bar_iban.addStretch()
        lay.addLayout(bar_iban)

        # `cancelar`/`suspender`/`reactivar` (services.saas.suscripciones) no tenían ningún botón —
        # mismo alcance que `cambiar_plan`/`renovar` (la suscripción de la EMPRESA ACTIVA, self-service;
        # no confundir con gestión de OTROS tenants, retirada del escritorio — ver comentario más abajo).
        bar_estado = QHBoxLayout()
        bar_estado.addWidget(QLabel("Estado de la suscripción:"))
        bar_estado.addWidget(_btn("Suspender", self._suspender_suscripcion, danger=True))
        bar_estado.addWidget(_btn("Reactivar", self._reactivar_suscripcion, primary=True))
        bar_estado.addWidget(_btn("Cancelar suscripción", self._cancelar_suscripcion, danger=True))
        bar_estado.addStretch()
        lay.addLayout(bar_estado)

        # "Actualizar" anclado a la esquina superior derecha de la TABLA (mismo criterio que
        # `EnterpriseTable(con_actualizar=..., actualizar_pos="derecha")` en `panel_prediccion.py`):
        # barra propia pegada justo encima de la tabla, con stretch a la izquierda del botón.
        bar_tabla = QHBoxLayout()
        bar_tabla.addStretch()
        bar_tabla.addWidget(_btn_cargando("🔄 Actualizar", self.refrescar, primary=True))
        lay.addLayout(bar_tabla)
        self.tbl_consumo = _tabla(["Recurso", "Consumo"])
        lay.addWidget(self.tbl_consumo)
        self.tabs.addTab(w, "Mi plan")
        self._load_portal()

    def _load_portal(self):
        lic = _L.licencia_activa(_empresa())
        sus = _S.estado(_empresa())
        self.lbl_plan.setText(f"Plan: {lic['codigo_plan'] if lic else '(sin licencia)'} · "
                              f"Estado: {lic['estado'] if lic else 'sin_licencia'}"
                              + (f" · Suscripción: {sus['estado']}" if sus else ""))
        # Aviso de vencimiento (banner): rojo si urgente/vencida, ámbar si próximo; oculto si no procede.
        try:
            av = _S.aviso_vencimiento(_empresa())
        except Exception:
            av = None
        if av:
            rojo = av["nivel"] in ("urgente", "vencida")
            color = "#F85149" if rojo else "#FFB86C"
            icono = "⛔" if rojo else "⚠️"
            self.lbl_aviso.setText(f"{icono}  {av['mensaje']}")
            self.lbl_aviso.setStyleSheet(
                f"color:{color}; font-size:14px; font-weight:900; border:1px solid {color};"
                f" border-radius:10px; padding:10px 14px; background:rgba(248,81,73,0.06);")
            self.lbl_aviso.setVisible(True)
        else:
            self.lbl_aviso.setVisible(False)
            self.lbl_aviso.setText("")
        cons = _M.consumo_empresa(_empresa())
        self.tbl_consumo.setRowCount(len(cons))
        for i, (k, v) in enumerate(cons.items()):
            self.tbl_consumo.setItem(i, 0, _it(k)); self.tbl_consumo.setItem(i, 1, _it(v))
        try:
            enmascarado = _S.iban_enmascarado(_empresa())
        except Exception:
            enmascarado = None
        self.lbl_iban.setText(f"Cuenta actual: {enmascarado}" if enmascarado else "Sin cuenta domiciliada.")
        self.inp_iban.clear()

    def _guardar_iban(self):
        # Validación barata ANTES del step-up MFA: no tiene sentido pedirle al usuario una
        # reautenticación para, después, decirle que se dejó el campo vacío.
        if not self.inp_iban.text().strip():
            self._aviso("Introduce primero el número de cuenta bancario.", "warning")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        r = _S.guardar_iban(_empresa(), self.inp_iban.text())
        if r.get("ok"):
            self._aviso("Cuenta bancaria guardada correctamente.", "success")
            self._load_portal()
        else:
            self._aviso(r.get("error") or "No se pudo guardar el IBAN.", "error")

    def _aviso(self, mensaje, nivel="info"):
        # `QMessageBox` nativo puede quedar sin handle correcto y no llegar a mostrarse sobre una
        # ventana anfitriona FRAMELESS (todas las ventanas completas de la app) — mismo criterio ya
        # documentado en `catalogo_gestion._InfoDialog`. Se usa el diálogo propio de la app.
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "SaaS", mensaje, nivel)
        except Exception:
            QMessageBox.information(self, "SaaS", mensaje)

    def _cambiar_plan(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.cambiar_plan(_empresa(), self.cmb_plan.currentData())
            self._load_portal()
            self._aviso(f"Plan cambiado a «{self.cmb_plan.currentText()}».", "success")
        except Exception as e:
            self._aviso(str(e), "error")

    def _renovar(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.renovar(_empresa())
            self._load_portal()
            self._aviso("Suscripción renovada correctamente.", "success")
        except Exception as e:
            self._aviso(str(e), "error")

    def _descargar_factura(self):
        try:
            from src.services.saas import facturas as _F
            fs = _F.listar_facturas(_empresa())
            if not fs:
                self._aviso("No hay facturas.", "info"); return
            ruta = _F.factura_pdf(fs[0]["id"], id_empresa=_empresa())
            if ruta:
                self._aviso(f"Factura generada: {ruta}", "success")
            else:
                self._aviso("No disponible (falta reportlab).", "warning")
        except Exception as e:
            self._aviso(str(e), "error")

    def _enviar_factura(self):
        try:
            from src.db import correo as _CO
            from src.services.saas import facturas as _F
            cuentas = _CO.listar_correos(id_empresa=_empresa())
            if not cuentas:
                self._aviso("No hay ninguna cuenta de correo corporativa configurada.", "warning")
                return
            fs = _F.listar_facturas(_empresa())
            if not fs:
                self._aviso("No hay facturas.", "info")
                return
            destinatario, ok = _pedir_texto(self, "Enviar factura por email", "Correo del destinatario:")
            destinatario = (destinatario or "").strip()
            if not ok or not destinatario:
                return
            enviado = _F.enviar_factura(fs[0]["id"], cuentas[0]["id_correo"], destinatario, id_empresa=_empresa())
            if enviado:
                self._aviso(f"Factura enviada a {destinatario}.", "success")
            else:
                self._aviso("No se pudo enviar la factura.", "error")
        except Exception as e:
            self._aviso(str(e), "error")

    def _suspender_suscripcion(self):
        from assets.estilo_global import mostrar_confirmacion
        if not mostrar_confirmacion(self, "Suspender suscripción",
                                     "¿Seguro que quieres suspender la suscripción de tu empresa?\n"
                                     "El acceso quedará bloqueado hasta reactivarla."):
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.suspender(_empresa())
            self._aviso("Suscripción suspendida.", "success")
            self._load_portal()
        except Exception as e:
            self._aviso(str(e), "error")

    def _reactivar_suscripcion(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.reactivar(_empresa())
            self._aviso("Suscripción reactivada.", "success")
            self._load_portal()
        except Exception as e:
            self._aviso(str(e), "error")

    def _cancelar_suscripcion(self):
        from assets.estilo_global import mostrar_confirmacion
        if not mostrar_confirmacion(self, "Cancelar suscripción",
                                     "¿Seguro que quieres CANCELAR la suscripción de tu empresa?\n"
                                     "Esta acción bloquea el acceso y no es una simple pausa."):
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.cancelar(_empresa())
            self._aviso("Suscripción cancelada.", "success")
            self._load_portal()
        except Exception as e:
            self._aviso(str(e), "error")

    # ── Uso y coste de IA (Anthropic) — Fase C ────────────────────────────────
    def _tab_ia(self):
        """Sección propia (nueva pestaña, no se mezcla con la tabla `tbl_consumo` de "Mi plan",
        que hoy solo muestra recuentos sin coste — ver `_M.consumo_empresa`) para el gasto REAL de
        IA (`ai_usage_logs.estimated_cost_usd`) y la modalidad de plan (`empresas.ai_plan_type`),
        con el mismo alcance self-service/empresa-activa que el resto de este archivo."""
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        titulo = QLabel("Uso y coste de IA (Anthropic)")
        titulo.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:bold;")
        lay.addWidget(titulo)

        self.lbl_ia_modo = QLabel("")
        self.lbl_ia_modo.setStyleSheet("color:#E6EDF3;font-size:14px;")
        lay.addWidget(self.lbl_ia_modo)

        self.barra_ia = QProgressBar()
        self.barra_ia.setRange(0, 100)
        self.barra_ia.setFixedHeight(24)
        self.barra_ia.setTextVisible(True)
        lay.addWidget(self.barra_ia)

        self.lbl_ia_hoy = QLabel("")
        self.lbl_ia_hoy.setStyleSheet(f"color:{_DIM};font-size:13px;")
        lay.addWidget(self.lbl_ia_hoy)

        self.lbl_ia_mes = QLabel("")
        self.lbl_ia_mes.setStyleSheet(f"color:{_DIM};font-size:13px;")
        lay.addWidget(self.lbl_ia_mes)

        bar = QHBoxLayout()
        self.btn_ia_modo = _btn("Cambiar modalidad de IA", self._cambiar_modo_ia, primary=True)
        bar.addWidget(self.btn_ia_modo)
        bar.addStretch()
        lay.addLayout(bar)
        lay.addStretch()
        self.tabs.addTab(w, "Uso de IA")
        self._load_ia()

    def _load_ia(self):
        try:
            r = _IA.resumen_uso_ia(_empresa())
        except Exception as e:
            self.lbl_ia_modo.setText(f"No se pudo cargar el uso de IA: {e}")
            self.barra_ia.setVisible(False)
            return
        plan = r.get("plan_type") or "(desconocido)"
        estado = r.get("ai_status") or "(desconocido)"
        self.lbl_ia_modo.setText(f"Modalidad actual: {plan}  ·  Estado: {estado}")
        if plan == "LIMITED":
            self.barra_ia.setVisible(True)
            pct_real = float(r.get("porcentaje_limite_usado") or 0.0)
            pct_barra = max(0, min(100, int(round(pct_real))))
            self.barra_ia.setValue(pct_barra)
            self.barra_ia.setFormat(f"{pct_real:.0f}%")
            color = _color_pct_ia(pct_real)
            self.barra_ia.setStyleSheet(
                "QProgressBar{background:#11181D;border:1px solid #2A3A47;border-radius:8px;"
                "color:#E6EDF3;text-align:center;font-family:'Segoe UI';font-weight:bold;}"
                f"QProgressBar::chunk{{background:{color};border-radius:8px;}}"
            )
            self.lbl_ia_hoy.setText(
                f"Gasto de hoy: ${r.get('gasto_hoy_usd', 0):.2f} de ${r.get('limite_diario_usd', 0):.2f} "
                f"(límite diario de seguridad)."
            )
        else:
            self.barra_ia.setVisible(False)
            self.lbl_ia_hoy.setText("Modalidad de consumo ilimitado (Pay As You Go): sin límite diario.")
        self.lbl_ia_mes.setText(f"Gasto acumulado este mes: ${r.get('gasto_mes_usd', 0):.2f}")
        self.btn_ia_modo.setText(
            "Cambiar a PAY_AS_YOU_GO (ilimitado)" if plan == "LIMITED" else "Cambiar a LIMITED (con límite diario)"
        )

    def _cambiar_modo_ia(self):
        try:
            actual = _IA.resumen_uso_ia(_empresa()).get("plan_type")
        except Exception as e:
            self._aviso(str(e), "error")
            return
        nuevo = "PAY_AS_YOU_GO" if actual == "LIMITED" else "LIMITED"
        if nuevo == "PAY_AS_YOU_GO":
            from assets.estilo_global import mostrar_confirmacion
            if not mostrar_confirmacion(
                self, "Cambiar a consumo ilimitado de IA",
                "Vas a cambiar la modalidad de IA a PAY_AS_YOU_GO (consumo ilimitado).\n\n"
                "Esto ELIMINA el límite diario de seguridad de gasto: la empresa podrá seguir "
                "usando la IA aunque el gasto del día supere el límite actualmente configurado. "
                "El consumo se seguirá registrando igualmente.\n\n¿Quieres continuar?"
            ):
                return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("ai.plan.cambiar", self):
            return
        try:
            _IA.cambiar_plan_ia(_empresa(), nuevo)
            self._load_ia()
            self._aviso(f"Modalidad de IA cambiada a «{nuevo}».", "success")
        except Exception as e:
            self._aviso(str(e), "error")

    # ── Uso y coste de voz (ElevenLabs / SOMA) — Fase C ───────────────────────
    def _tab_voz(self):
        """Sección propia (nueva pestaña), copia del patrón de `_tab_ia`, para el uso/coste/
        facturado REAL de voz (`voice_usage_logs`) y el límite de SEGURIDAD mensual de caracteres
        propio de la empresa (`empresas.voice_monthly_limit_chars`). Mismo alcance self-service/
        empresa-activa: la tarifa/margen de reventa NO se edita aquí — es una decisión de
        PLATAFORMA, solo disponible en el Panel del Fundador (`backend_central/rutas_admin.py`),
        nunca en esta pantalla (ver cabecera de este fichero sobre la frontera SUPERADMIN)."""
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        titulo = QLabel("Uso y coste de voz (ElevenLabs / SOMA)")
        titulo.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:bold;")
        lay.addWidget(titulo)

        self.lbl_voz_limite = QLabel("")
        self.lbl_voz_limite.setStyleSheet("color:#E6EDF3;font-size:14px;")
        lay.addWidget(self.lbl_voz_limite)

        self.barra_voz = QProgressBar()
        self.barra_voz.setRange(0, 100)
        self.barra_voz.setFixedHeight(24)
        self.barra_voz.setTextVisible(True)
        lay.addWidget(self.barra_voz)

        self.lbl_voz_mes = QLabel("")
        self.lbl_voz_mes.setStyleSheet(f"color:{_DIM};font-size:13px;")
        lay.addWidget(self.lbl_voz_mes)

        self.lbl_voz_facturado = QLabel("")
        self.lbl_voz_facturado.setStyleSheet(f"color:{_DIM};font-size:13px;")
        lay.addWidget(self.lbl_voz_facturado)

        bar = QHBoxLayout()
        bar.addWidget(_btn("Ajustar límite mensual de caracteres", self._cambiar_limite_voz, primary=True))
        bar.addStretch()
        lay.addLayout(bar)
        lay.addStretch()
        self.tabs.addTab(w, "Uso de voz")
        self._load_voz()

    def _load_voz(self):
        try:
            r = _VOZ.resumen_uso_voz(_empresa())
        except Exception as e:
            self.lbl_voz_limite.setText(f"No se pudo cargar el uso de voz: {e}")
            self.barra_voz.setVisible(False)
            return
        limite = r.get("limite_mensual_chars")
        caracteres = int(r.get("caracteres_mes") or 0)
        if limite is not None:
            self.barra_voz.setVisible(True)
            pct_real = float(r.get("porcentaje_limite_usado") or 0.0)
            pct_barra = max(0, min(100, int(round(pct_real))))
            self.barra_voz.setValue(pct_barra)
            self.barra_voz.setFormat(f"{pct_real:.0f}%")
            color = _color_pct_ia(pct_real)
            self.barra_voz.setStyleSheet(
                "QProgressBar{background:#11181D;border:1px solid #2A3A47;border-radius:8px;"
                "color:#E6EDF3;text-align:center;font-family:'Segoe UI';font-weight:bold;}"
                f"QProgressBar::chunk{{background:{color};border-radius:8px;}}"
            )
            self.lbl_voz_limite.setText(
                f"Límite mensual de seguridad: {caracteres:,} de {limite:,} caracteres."
            )
        else:
            self.barra_voz.setVisible(False)
            self.lbl_voz_limite.setText(
                f"Sin límite mensual configurado. Caracteres usados este mes: {caracteres:,}."
            )
        self.lbl_voz_mes.setText(
            f"Coste base del proveedor este mes: ${r.get('coste_mes_usd', 0):.4f}"
        )
        self.lbl_voz_facturado.setText(
            f"Importe facturado este mes: ${r.get('facturado_mes_usd', 0):.4f}"
        )

    def _cambiar_limite_voz(self):
        try:
            actual = _VOZ.resumen_uso_voz(_empresa()).get("limite_mensual_chars")
        except Exception as e:
            self._aviso(str(e), "error")
            return
        texto_actual = "" if actual is None else str(actual)
        texto, ok = _pedir_texto(
            self, "Límite mensual de caracteres de voz",
            "Caracteres/mes (vacío = sin límite):", texto_actual
        )
        if not ok:
            return
        texto = (texto or "").strip()
        nuevo = None
        if texto:
            try:
                nuevo = int(texto)
            except ValueError:
                self._aviso(
                    "Introduce un número entero de caracteres, o déjalo vacío para quitar el límite.",
                    "error",
                )
                return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("voz.limite.cambiar", self):
            return
        try:
            _VOZ.cambiar_limite_voz(_empresa(), nuevo)
            self._load_voz()
            self._aviso("Límite mensual de voz actualizado.", "success")
        except Exception as e:
            self._aviso(str(e), "error")

    def refrescar(self):
        self._load_portal()
        self._load_ia()
        self._load_voz()
