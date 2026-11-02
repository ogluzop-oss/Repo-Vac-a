"""
CRM — Ficha avanzada de clientes (VTA.1).

Pantalla NUEVA. Búsqueda/listado + alta + edición de crédito/segmento + historial comercial
(ventas/devoluciones/saldo) + puntos de fidelización. Multiempresa. No modifica el TPV.
"""

import logging

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QStackedWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.db import clientes as CL
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_cargando, _btn_x,
                                      _combo, _dialogo_frameless, _inp, _lbl, _tabla)
from src.services import autorizacion

logger = logging.getLogger("ventas.clientes.gui")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class _NuevoClienteDialog(QDialog):
    """Alta rápida de cliente (mismo diseño frameless + X roja que el resto de la app — antes usaba
    `QInputDialog.getText`, que muestra la barra de título nativa de Windows).

    Incluye también los datos de contacto (email/teléfono) — la tabla `clientes` ya tiene esas
    columnas (usadas por `CL.crear_cliente`/`actualizar_cliente`), así que no hace falta migración:
    es la misma información que antes solo se recogía en la pestaña "Contactos" (leads), ahora
    disponible desde el alta del cliente mismo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Nuevo cliente", ancho=360)
        v.addWidget(_lbl("Nombre *"))
        self.in_nombre = _inp("Nombre del cliente")
        v.addWidget(self.in_nombre)
        v.addWidget(_lbl("Email (opcional)"))
        self.in_email = _inp("correo@ejemplo.com")
        v.addWidget(self.in_email)
        v.addWidget(_lbl("Teléfono (opcional)"))
        self.in_telefono = _inp("600000000")
        v.addWidget(self.in_telefono)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Crear", self.accept, primary=True))
        v.addLayout(fila)


class _EditarSegmentoDialog(QDialog):
    """Editar segmento + límite de crédito (frameless, reemplaza los `QInputDialog` nativos que
    mostraban la barra de título de Windows)."""

    def __init__(self, parent=None, segmento="", limite_credito=0.0):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Segmento y crédito", ancho=360)
        v.addWidget(_lbl("Segmento"))
        self.in_segmento = _inp("Segmento del cliente")
        self.in_segmento.setText(segmento or "")
        v.addWidget(self.in_segmento)
        v.addWidget(_lbl("Límite de crédito (€)"))
        self.in_limite = _inp("0.00")
        self.in_limite.setText(f"{float(limite_credito or 0):.2f}")
        from PyQt6.QtGui import QDoubleValidator
        val = QDoubleValidator(0.0, 1e9, 2, self.in_limite)
        val.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_limite.setValidator(val)
        v.addWidget(self.in_limite)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)


class _EditarContactoDialog(QDialog):
    """Editar email/teléfono del cliente en cualquier momento (frameless), para que los datos de
    contacto recogidos en el alta se puedan revisar/corregir después."""

    def __init__(self, parent=None, email="", telefono=""):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Datos de contacto", ancho=360)
        v.addWidget(_lbl("Email"))
        self.in_email = _inp("correo@ejemplo.com")
        self.in_email.setText(email or "")
        v.addWidget(self.in_email)
        v.addWidget(_lbl("Teléfono"))
        self.in_telefono = _inp("600000000")
        self.in_telefono.setText(telefono or "")
        v.addWidget(self.in_telefono)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)


class _NuevoLeadDialog(QDialog):
    """Alta de un lead/contacto (pre-cliente, aún no en la tabla `clientes`) — mismo formulario que
    tenía la extinta pestaña "Contactos" del CRM (`crm_dashboard.py`), movido aquí al fusionarse esa
    pestaña dentro de "Clientes"."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Nuevo contacto (lead)", ancho=380)
        v.addWidget(_lbl("Nombre *"))
        self.in_nombre = _inp("Nombre del contacto")
        v.addWidget(self.in_nombre)
        v.addWidget(_lbl("Empresa (opcional)"))
        self.in_empresa = _inp("Empresa")
        v.addWidget(self.in_empresa)
        v.addWidget(_lbl("Email (opcional)"))
        self.in_email = _inp("correo@ejemplo.com")
        v.addWidget(self.in_email)
        v.addWidget(_lbl("Teléfono (opcional)"))
        self.in_telefono = _inp("600000000")
        v.addWidget(self.in_telefono)
        v.addWidget(_lbl("Valor estimado (€)"))
        self.in_valor = _inp("0")
        self.in_valor.setText("0")
        v.addWidget(self.in_valor)
        v.addWidget(_lbl("Prioridad"))
        self.cb_prioridad = _combo([("Normal", "normal"), ("Alta", "alta"), ("Baja", "baja")], "normal")
        v.addWidget(self.cb_prioridad)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Crear", self.accept, primary=True))
        v.addLayout(fila)


class _CambiarEstadoLeadDialog(QDialog):
    """Cambiar el estado de un lead (nuevo/contactado/calificado/no_interesado/convertido/perdido)."""

    def __init__(self, parent=None, estados=(), actual="contactado"):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Cambiar estado del contacto", ancho=340)
        v.addWidget(_lbl("Nuevo estado"))
        self.cb_estado = _combo([(e.capitalize(), e) for e in estados], actual)
        v.addWidget(self.cb_estado)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)


class ClientesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        # Sin título propio: la pestaña "Clientes" del CRM (crm_dashboard.py) ya da ese contexto en
        # la barra de pestañas — un rótulo "Clientes (CRM)" repetido debajo era redundante. El botón
        # de cierre (✕) se conserva SOLO cuando esta ventana se embebe con `callback_vuelta` real
        # (no ocurre hoy desde `crm_dashboard._construir_tab_clientes`, que pasa `None`, pero sí en
        # cualquier otro contexto futuro que la abra como ventana independiente).
        if callback_vuelta:
            cab = QHBoxLayout()
            cab.addStretch()
            cab.addWidget(_btn_x(self._volver))
            root.addLayout(cab)

        # Alternador Clientes / Leads (pre-clientes): la extinta pestaña "Contactos" del CRM
        # (`crm_dashboard.py`) se fusionó aquí — son entidades con ciclo de vida distinto (un lead
        # NO está en la tabla `clientes` hasta que se convierte), así que se mantienen como dos
        # vistas conmutables en vez de una sola tabla mezclada que perdería el estado del pipeline.
        toggle = QHBoxLayout()
        self.btn_vista_clientes = _btn("👥 Clientes", self._mostrar_vista_clientes, primary=True)
        self.btn_vista_leads = _btn("🧲 Leads (pre-clientes)", self._mostrar_vista_leads, primary=True)
        toggle.addWidget(self.btn_vista_clientes)
        toggle.addWidget(self.btn_vista_leads)
        toggle.addStretch()
        root.addLayout(toggle)

        self.stack_vista = QStackedWidget()
        self.stack_vista.addWidget(self._construir_pagina_clientes())
        self.stack_vista.addWidget(self._construir_pagina_leads())
        root.addWidget(self.stack_vista)

        self._leads_cargados = False
        self._mostrar_vista_clientes()
        self._buscar()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _mostrar_vista_clientes(self):
        self.stack_vista.setCurrentIndex(0)
        self.btn_vista_clientes.setEnabled(False)
        self.btn_vista_leads.setEnabled(True)

    def _mostrar_vista_leads(self):
        self.stack_vista.setCurrentIndex(1)
        self.btn_vista_clientes.setEnabled(True)
        self.btn_vista_leads.setEnabled(False)
        if not self._leads_cargados:
            self._leads_cargados = True
            self._load_leads()

    def _construir_pagina_clientes(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        f = QHBoxLayout()
        self.in_busca = _inp("Buscar (nombre/NIF/email)")
        f.addWidget(self.in_busca)
        f.addWidget(_btn("🔍", self._buscar, primary=True))
        f.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        f.addWidget(_btn("Editar crédito/segmento", self._editar, primary=True))
        f.addWidget(_btn("Editar contacto", self._editar_contacto, primary=True))
        f.addWidget(_btn("Fiscalidad", self._fiscalidad, primary=True))
        f.addWidget(_btn("Historial", self._historial, primary=True))
        f.addStretch()
        f.addWidget(_btn_cargando("🔄  Actualizar", self._buscar, primary=True))
        ly.addLayout(f)

        self.tabla = _tabla(["id", "Nombre", "NIF", "Segmento", "Límite crédito",
                             "Riesgo", "Puntos", "Estado"])
        ly.addWidget(self.tabla)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_TEXT};")
        ly.addWidget(self.lbl)
        return w

    def _construir_pagina_leads(self):
        """Pestaña "Leads (pre-clientes)" = tabla + alta + cambio de estado + conversión a cliente
        — las 4 acciones que tenía la antigua pestaña independiente "Contactos" del CRM."""
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        barra = QHBoxLayout()
        barra.addWidget(_btn("➕ Nuevo contacto", self._nuevo_lead, primary=True))
        barra.addWidget(_btn("✏️ Cambiar estado", self._cambiar_estado_lead, primary=True))
        barra.addWidget(_btn("👤 Convertir a cliente", self._convertir_lead_a_cliente, primary=True))
        barra.addStretch()
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_leads, primary=True))
        ly.addLayout(barra)
        self.tbl_leads = _tabla(["ID", "Nombre", "Empresa", "Estado", "Prioridad", "Valor", "Score"])
        ly.addWidget(self.tbl_leads)
        return w

    def _buscar(self):
        txt = self.in_busca.text().strip()
        self._data = (CL.buscar_clientes(txt, self._emp()) if txt
                      else CL.listar_clientes(self._emp()))
        self.tabla.setRowCount(len(self._data))
        for i, c in enumerate(self._data):
            for j, v in enumerate([c.get("id"), c.get("nombre"), c.get("nif"), c.get("segmento"),
                                   c.get("limite_credito"), c.get("riesgo_actual"),
                                   c.get("saldo_puntos"), c.get("estado")]):
                self.tabla.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tabla.currentRow()
        return self._data[i] if 0 <= i < len(self._data) else None

    def _nuevo(self):
        dlg = _NuevoClienteDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nombre = dlg.in_nombre.text().strip()
        if not nombre:
            _aviso(self, "Clientes", "El nombre es obligatorio.", "warning")
            return
        email = dlg.in_email.text().strip() or None
        telefono = dlg.in_telefono.text().strip() or None
        cid = CL.crear_cliente(nombre, telefono=telefono, email=email, id_empresa=self._emp(),
                               origen_flujo="ficha")
        _aviso(self, "Clientes", f"Cliente creado (#{cid})." if cid else "No se pudo crear el cliente.",
              "success" if cid else "error")
        self._buscar()

    def _editar(self):
        c = self._sel()
        if not c:
            _aviso(self, "Clientes", "Selecciona antes un cliente en la tabla.", "warning")
            return
        dlg = _EditarSegmentoDialog(self, segmento=c.get("segmento"),
                                    limite_credito=c.get("limite_credito"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        seg = dlg.in_segmento.text().strip()
        try:
            lim = float((dlg.in_limite.text() or "0").replace(",", "."))
        except ValueError:
            lim = 0.0
        ok3 = CL.actualizar_cliente(c["id"], id_empresa=self._emp(), segmento=seg or None,
                                    limite_credito=lim)
        _aviso(self, "Clientes", "Crédito/segmento actualizado." if ok3 else "No se pudo actualizar el cliente.",
              "success" if ok3 else "error")
        self._buscar()

    def _editar_contacto(self):
        """Ver/editar el email y teléfono del cliente en cualquier momento (no solo en el alta)."""
        c = self._sel()
        if not c:
            _aviso(self, "Clientes", "Selecciona antes un cliente en la tabla.", "warning")
            return
        c = CL.obtener_cliente(c["id"]) or c
        dlg = _EditarContactoDialog(self, email=c.get("email"), telefono=c.get("telefono"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ok4 = CL.actualizar_cliente(c["id"], id_empresa=self._emp(),
                                    email=dlg.in_email.text().strip() or None,
                                    telefono=dlg.in_telefono.text().strip() or None)
        _aviso(self, "Clientes", "Datos de contacto actualizados." if ok4 else "No se pudo actualizar el cliente.",
              "success" if ok4 else "error")
        self._buscar()

    def _fiscalidad(self):
        """Edita los atributos fiscales del cliente (FASE 3.1): el CRM es el ORIGEN
        ÚNICO de decisión fiscal de la factura (IVA/recargo/ISP/intracom/IRPF)."""
        c = self._sel()
        if not c:
            _aviso(self, "Clientes", "Selecciona antes un cliente en la tabla.", "warning")
            return
        c = CL.obtener_cliente(c["id"]) or c
        dlg = QDialog(self)
        dlg.setWindowTitle("Fiscalidad del cliente")
        dlg.setStyleSheet(f"background:{_BG};color:{_TEXT};")
        form = QFormLayout(dlg)
        cb_reg = QComboBox(); cb_reg.addItems(list(CL.REGIMENES_FISCALES))
        cb_reg.setCurrentText((c.get("regimen_fiscal") or "general"))
        in_nifiva = QLineEdit(c.get("nif_iva") or "")
        # VIES (FASE C): el desplegable manual sigue como FALLBACK honesto (sin red no hay forma
        # de verificar), pero el botón "Verificar" es ahora el camino PRINCIPAL — llama de verdad
        # al servicio público VIES en vez de que la persona elija a ciegas.
        cb_vies = QComboBox(); cb_vies.addItems(["", "pendiente", "valido", "invalido"])
        cb_vies.setCurrentText(c.get("validacion_vies") or "")
        fila_vies = QWidget()
        fila_vies_ly = QHBoxLayout(fila_vies)
        fila_vies_ly.setContentsMargins(0, 0, 0, 0)
        fila_vies_ly.setSpacing(6)
        fila_vies_ly.addWidget(cb_vies, 1)

        def _verificar_vies():
            nif_txt = in_nifiva.text().strip()
            if not nif_txt:
                _aviso(dlg, "VIES", "Introduce antes el NIF-IVA a verificar.", "warning")
                return
            from src.utils import vies as VIES
            ok_fmt, pais_det = VIES.validar_formato_nif_iva(nif_txt, c.get("pais_fiscal"))
            if not pais_det:
                _aviso(dlg, "VIES",
                      "No se reconoce el prefijo de país como miembro de la UE.", "warning")
                return
            res = VIES.consultar_vies(pais_det, nif_txt)
            if not res.get("ok"):
                _aviso(dlg, "VIES",
                      "No se pudo verificar contra VIES ahora mismo ({m}). Puede fijar el estado "
                      "manualmente en el desplegable.".format(m=res.get("error") or "sin red"),
                      "warning")
                return
            if res.get("valido"):
                cb_vies.setCurrentText("valido")
                _aviso(dlg, "VIES",
                      "NIF-IVA VÁLIDO.\n{n}\n{d}".format(
                          n=res.get("nombre") or "", d=res.get("direccion") or "").strip(),
                      "success")
            else:
                cb_vies.setCurrentText("invalido")
                _aviso(dlg, "VIES", "NIF-IVA NO VÁLIDO según VIES.", "warning")

        btn_verificar = _btn_cargando("🔎 Verificar", _verificar_vies, primary=True,
                                      cargando="⏳ Verificando…")
        fila_vies_ly.addWidget(btn_verificar)
        ck_recargo = QCheckBox("Aplica recargo de equivalencia")
        ck_recargo.setChecked(bool(int(c.get("aplica_recargo_equivalencia") or 0)))
        ck_isp = QCheckBox("Operación con inversión del sujeto pasivo (ISP)")
        ck_isp.setChecked(bool(int(c.get("aplica_isp") or 0)))
        ck_irpf = QCheckBox("Retención de IRPF")
        ck_irpf.setChecked(bool(int(c.get("aplica_retencion_irpf") or 0)))
        # QLineEdit + validador en vez de QDoubleSpinBox: la app oculta sus flechas arriba/abajo vía
        # QSS y eso rompía su foco/clic en varios diálogos (confirmado por el usuario) — mismo
        # criterio ya aplicado en `sat_dashboard._FormDialog`.
        from PyQt6.QtGui import QDoubleValidator
        sp_irpf = QLineEdit(f"{float(c.get('porcentaje_retencion') or 0):.2f}")
        sp_irpf.setPlaceholderText("% retención (0-100)")
        val_irpf = QDoubleValidator(0.0, 100.0, 2, sp_irpf)
        val_irpf.setNotation(QDoubleValidator.Notation.StandardNotation)
        sp_irpf.setValidator(val_irpf)
        in_cond = QLineEdit(c.get("condiciones_pago") or "")
        in_cond.setPlaceholderText("contado / 15 / 30 / 60 / 30-60-90")
        form.addRow("Régimen fiscal:", cb_reg)
        form.addRow("NIF-IVA (intracom.):", in_nifiva)
        form.addRow("Validación VIES:", fila_vies)
        form.addRow("", ck_recargo)
        form.addRow("", ck_isp)
        form.addRow("", ck_irpf)
        form.addRow("% retención IRPF:", sp_irpf)
        form.addRow("Condiciones de pago:", in_cond)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        reg = cb_reg.currentText()
        try:
            pct_irpf = float((sp_irpf.text() or "0").replace(",", "."))
        except ValueError:
            pct_irpf = 0.0
        okf = CL.actualizar_cliente(
            c["id"], id_empresa=self._emp(),
            regimen_fiscal=reg,
            nif_iva=in_nifiva.text().strip() or None,
            validacion_vies=cb_vies.currentText() or None,
            aplica_recargo_equivalencia=1 if ck_recargo.isChecked() else 0,
            aplica_isp=1 if ck_isp.isChecked() else 0,
            aplica_retencion_irpf=1 if ck_irpf.isChecked() else 0,
            porcentaje_retencion=pct_irpf if ck_irpf.isChecked() else None,
            es_intracomunitario=1 if reg == "intracomunitario" else 0,
            es_extranjero=1 if reg == "extranjero" else 0,
            condiciones_pago=in_cond.text().strip() or None)
        _aviso(self, "Clientes",
              "Datos fiscales actualizados." if okf else "No se pudieron actualizar los datos fiscales.",
              "success" if okf else "error")
        self._buscar()

    def _historial(self):
        c = self._sel()
        if not c:
            _aviso(self, "Clientes", "Selecciona antes un cliente en la tabla.", "warning")
            return
        h = CL.historial_comercial(c["id"], self._emp())
        msg = (f"{c['nombre']}: ventas {len(h['ventas'])} ({h['total_ventas']}) · "
              f"devoluciones {len(h['devoluciones'])} ({h['total_devoluciones']}) · saldo {h['saldo']}")
        self.lbl.setText(msg)
        _aviso(self, "Historial del cliente", msg, "info")

    # ── Leads / pre-clientes (fusionado desde la extinta pestaña "Contactos" del CRM) ──────────
    # Backend reutilizado tal cual de `src/services/crm/leads.py` — no se reimplementa la
    # conversión a cliente (`convertir_a_cliente`, ya cubierta por tests/unit/test_crm_conversion.py).

    def _load_leads(self):
        from src.services.crm import leads
        self._leads = leads.listar_leads(id_empresa=self._emp())
        self.tbl_leads.setRowCount(len(self._leads))
        for i, l in enumerate(self._leads):
            for j, v in enumerate([l.get("id"), l.get("nombre"), l.get("empresa"), l.get("estado"),
                                   l.get("prioridad"), l.get("valor_estimado"), l.get("score")]):
                self.tbl_leads.setItem(i, j, _it(v))

    def _lead_seleccionado(self):
        r = self.tbl_leads.currentRow()
        if r < 0 or self.tbl_leads.item(r, 0) is None:
            _aviso(self, "Contactos", "Selecciona antes un contacto en la tabla.", "warning")
            return None
        try:
            return int(self.tbl_leads.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _nuevo_lead(self):
        if not autorizacion.puede(self.usuario, "crm.leads"):
            _aviso(self, "Contactos", "No tiene permiso para crear contactos.", "warning")
            return
        dlg = _NuevoLeadDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nombre = dlg.in_nombre.text().strip()
        if not nombre:
            _aviso(self, "Contactos", "El nombre es obligatorio.", "warning")
            return
        try:
            valor = float((dlg.in_valor.text() or "0").replace(",", ".") or 0)
        except ValueError:
            valor = 0
        from src.services.crm import leads
        lid = leads.crear_lead(nombre, empresa=dlg.in_empresa.text().strip() or None,
                               email=dlg.in_email.text().strip() or None,
                               telefono=dlg.in_telefono.text().strip() or None,
                               valor_estimado=valor, prioridad=dlg.cb_prioridad.currentData(),
                               id_empresa=self._emp())
        if lid:
            _aviso(self, "Contactos", "Contacto creado correctamente.", "success")
            self._load_leads()
        else:
            _aviso(self, "Contactos", "No se pudo crear el contacto.", "error")

    def _cambiar_estado_lead(self):
        lid = self._lead_seleccionado()
        if not lid:
            return
        if not autorizacion.puede(self.usuario, "crm.leads"):
            _aviso(self, "Contactos", "No tiene permiso para editar contactos.", "warning")
            return
        from src.services.crm import leads
        dlg = _CambiarEstadoLeadDialog(self, estados=leads.ESTADOS, actual="contactado")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if leads.actualizar_lead(lid, estado=dlg.cb_estado.currentData()):
            _aviso(self, "Contactos", "Estado actualizado.", "success")
            self._load_leads()
        else:
            _aviso(self, "Contactos", "No se pudo actualizar.", "error")

    def _convertir_lead_a_cliente(self):
        lid = self._lead_seleccionado()
        if not lid:
            return
        if not autorizacion.puede(self.usuario, "crm.leads"):
            _aviso(self, "Contactos", "No tiene permiso para convertir contactos.", "warning")
            return
        from src.services.crm import leads
        r = leads.convertir_a_cliente(lid, id_empresa=self._emp())
        if r.get("ok"):
            if r.get("ya_convertido"):
                _aviso(self, "Contactos", f"Ya estaba convertido a cliente #{r['id_cliente']}.")
            else:
                _aviso(self, "Contactos", f"Convertido a cliente #{r['id_cliente']} correctamente.", "success")
            self._load_leads()
            self._buscar()  # el cliente recién creado por la conversión ya debe verse en "Clientes"
        else:
            _aviso(self, "Contactos", "No se pudo convertir: " + (r.get("error") or ""), "error")
