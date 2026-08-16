"""
Portal de proveedor — lado EMPRESA (embebido en el módulo Proveedores).

Orquesta `services.compras.portal` (la lógica vive allí; esta capa es solo interfaz). Pestañas:
- Proveedores conectados: invitar / ver enlace / revocar / regenerar token + publicar en el mercado.
- Invitaciones pendientes: proveedores invitados que aún no han entrado.
- Mensajería: conversación empresa↔proveedor.
(Las subastas/RFQ viven en la BOLSA UNIFICADA de la pestaña Pedidos: tarifas fijas + ofertas en vivo,
Comprar ya / Pujar.)

DEGRADABLE: funciona en local aunque el enlace remoto no esté desplegado; muestra el modo actual.
Reutiliza los helpers visuales de `catalogo_gestion` (coherencia con el resto del módulo de compras).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_cargando, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _tabla)
from src.services.compras import portal

logger = logging.getLogger("gui.portal_proveedor")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class PortalProveedorWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("🔗  Portal de proveedor")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t)
        self.lbl_modo = QLabel("")
        self.lbl_modo.setStyleSheet(f"color:{_DIM};font-size:12px;font-weight:700;")
        cab.addWidget(self.lbl_modo); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        tabs.addTab(self._tab_conectados(), "Proveedores conectados")
        tabs.addTab(self._tab_pendientes(), "Invitaciones pendientes")
        tabs.addTab(self._tab_mensajes(), "Mensajería")
        # La antigua pestaña "RFQ / Subasta" se retiró: las subastas viven ahora en la BOLSA UNIFICADA
        # de la pestaña Pedidos (mercado Lonja: tarifas fijas + ofertas en vivo, Comprar ya / Pujar).
        root.addWidget(tabs)
        self._refrescar_modo()
        self._cargar_cuentas()   # también refresca la pestaña de pendientes

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _provs(self):
        try:
            return [(f"{p['razon_social']}", p["id_proveedor"])
                    for p in P.listar_proveedores(estado="activo")]
        except Exception:
            return []

    def _refrescar_modo(self):
        if portal.portal_activo():
            self.lbl_modo.setText("· enlace remoto EN VIVO")
        else:
            self.lbl_modo.setText("· modo local (preparado, sin desplegar)")

    # ── Proveedores conectados ────────────────────────────────────────────────
    def _tab_conectados(self):
        w = QWidget(); ly = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.cmb_prov_inv = _combo(self._provs() or [("(sin proveedores)", None)])
        self.in_email_inv = _inp("Email del proveedor (opcional)")
        fila.addWidget(QLabel("Proveedor:")); fila.addWidget(self.cmb_prov_inv, 1)
        fila.addWidget(self.in_email_inv, 1)
        fila.addWidget(_btn("✉️  Invitar", self._invitar, primary=True))
        ly.addLayout(fila)
        bar = QHBoxLayout()
        bar.addWidget(_btn("✉️  Enviar invitación", self._enviar_correo, primary=True))
        bar.addWidget(_btn("🔑  Ver enlace", self._ver_enlace, primary=True))
        bar.addWidget(_btn("♻  Regenerar token", self._regenerar, primary=True))
        bar.addWidget(_btn("🏷️  Publicar en el mercado", self._publicar_mercado, primary=True))
        bar.addWidget(_btn("Revocar", self._revocar, danger=True))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._cargar_cuentas))
        ly.addLayout(bar)
        self.tbl_cuentas = _tabla(["ID", "Proveedor", "Email", "Estado", "Última conexión"])
        ly.addWidget(self.tbl_cuentas)
        return w

    def _cargar_cuentas(self):
        data = portal.listar_cuentas(id_empresa=self._emp())
        self.tbl_cuentas.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id_proveedor"), d.get("proveedor"), d.get("email"),
                                   d.get("estado"), str(d.get("ultima_conexion") or "")[:16]]):
                self.tbl_cuentas.setItem(i, j, _it(v))
        if hasattr(self, "tbl_pend"):   # mantiene sincronizada la pestaña de pendientes
            self._cargar_pendientes()

    def _cuenta_sel(self):
        r = self.tbl_cuentas.currentRow()
        if r < 0:
            return None
        try:
            return int(self.tbl_cuentas.item(r, 0).text())
        except Exception:
            return None

    def _invitar(self):
        """Invita al proveedor y ENVÍA (o prepara) el correo de invitación."""
        pid = self.cmb_prov_inv.currentData()
        if not pid:
            _aviso(self, "Portal", "Selecciona un proveedor.", "warning"); return
        res = portal.enviar_invitacion(pid, email=self.in_email_inv.text().strip() or None,
                                       id_empresa=self._emp(), usuario=self.usuario.get("nombre"))
        self._cargar_cuentas()
        self._mostrar_invitacion(res)

    def _enviar_correo(self):
        """Reenvía el correo de invitación al proveedor seleccionado."""
        pid = self._cuenta_sel()
        if not pid:
            _aviso(self, "Portal", "Selecciona un proveedor de la tabla.", "warning"); return
        res = portal.enviar_invitacion(pid, id_empresa=self._emp(), usuario=self.usuario.get("nombre"))
        self._mostrar_invitacion(res)

    def _ver_enlace(self):
        pid = self._cuenta_sel()
        if not pid:
            _aviso(self, "Portal", "Selecciona un proveedor de la tabla.", "warning"); return
        self._mostrar_invitacion(portal.render_invitacion(pid, id_empresa=self._emp()))

    def _mostrar_invitacion(self, res):
        if not res or not res.get("token"):
            _aviso(self, "Portal", "No se pudo preparar la invitación.", "error"); return
        _DialogoInvitacion(res, self).exec()

    def _regenerar(self):
        pid = self._cuenta_sel()
        if not pid:
            _aviso(self, "Portal", "Selecciona un proveedor de la tabla.", "warning"); return
        tok = portal.regenerar_token(pid, id_empresa=self._emp())
        self._cargar_cuentas()
        if tok:
            self._mostrar_invitacion(portal.render_invitacion(pid, id_empresa=self._emp()))

    def _revocar(self):
        pid = self._cuenta_sel()
        if not pid:
            _aviso(self, "Portal", "Selecciona un proveedor de la tabla.", "warning"); return
        if portal.revocar(pid, self._emp()):
            self._cargar_cuentas()

    def _cuenta_sel_nombre(self):
        r = self.tbl_cuentas.currentRow()
        it = self.tbl_cuentas.item(r, 1) if r >= 0 else None
        return it.text() if it else None

    def _publicar_mercado(self):
        """Publica un artículo del proveedor seleccionado en el MERCADO (Lonja), eligiendo su divisa,
        precio de compra directa, puja mínima y cantidad. Queda visible para todas las empresas."""
        pid = self._cuenta_sel()
        if not pid:
            _aviso(self, "Mercado", "Selecciona un proveedor de la tabla.", "warning"); return
        nombre = self._cuenta_sel_nombre() or f"Proveedor {pid}"
        dlg = _DialogoPublicarMercado(nombre, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.datos:
            return
        from src.services import lonja
        d = dlg.datos
        vid = lonja.vendedor_de_proveedor(self._emp(), pid, nombre=nombre, divisa=d["divisa"],
                                          tipo_comercio=d.get("tipo_comercio"))
        if not vid:
            _aviso(self, "Mercado", "No se pudo crear el vendedor de la Lonja.", "error"); return
        lid = lonja.publicar(vid, d["codigo"], d["precio"], divisa=d["divisa"],
                             puja_minima=d["puja_minima"], cantidad=d["cantidad"],
                             unidad_medida=d["unidad"], duracion_horas=d.get("duracion_horas"),
                             precio_reserva=d.get("precio_reserva"),
                             incremento_minimo=d.get("incremento_minimo", 0))
        if lid:
            _aviso(self, "Mercado",
                   f"Publicado en el mercado: {d['codigo']} · {d['precio']:.2f} {d['divisa']} "
                   f"(puja mín. {d['puja_minima']:.2f}). Visible en la bolsa de todas las empresas.",
                   "success")
        else:
            _aviso(self, "Mercado", "No se pudo publicar en el mercado.", "error")

    # ── Invitaciones pendientes ───────────────────────────────────────────────
    def _tab_pendientes(self):
        """Registro de proveedores invitados que aún NO han entrado al portal (misma fuente que el job)."""
        w = QWidget(); ly = QVBoxLayout(w)
        info = QLabel("Proveedores invitados que todavía no han aceptado (no han entrado al portal).")
        info.setStyleSheet(f"color:{_DIM};font-size:12px;")
        ly.addWidget(info)
        bar = QHBoxLayout()
        bar.addWidget(_btn("✉️  Reenviar invitación", self._reenviar_pendiente, primary=True))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._cargar_pendientes))
        ly.addLayout(bar)
        self.tbl_pend = _tabla(["Proveedor", "Email", "Invitado el"])
        ly.addWidget(self.tbl_pend)
        return w

    def _cargar_pendientes(self):
        self._pend_rows = portal.invitaciones_pendientes(id_empresa=self._emp())
        self.tbl_pend.setRowCount(len(self._pend_rows))
        for i, d in enumerate(self._pend_rows):
            for j, v in enumerate([d.get("proveedor"), d.get("email"),
                                   str(d.get("creado_en") or "")[:16]]):
                self.tbl_pend.setItem(i, j, _it(v))

    def _reenviar_pendiente(self):
        r = self.tbl_pend.currentRow()
        rows = getattr(self, "_pend_rows", []) or []
        if r < 0 or r >= len(rows):
            _aviso(self, "Portal", "Selecciona una invitación pendiente.", "warning"); return
        pid = rows[r].get("id_proveedor")
        res = portal.enviar_invitacion(pid, id_empresa=self._emp(), usuario=self.usuario.get("nombre"))
        self._mostrar_invitacion(res)
        self._cargar_pendientes()

    # ── Mensajería ────────────────────────────────────────────────────────────
    def _tab_mensajes(self):
        w = QWidget(); ly = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.cmb_prov_msg = _combo(self._provs() or [("(sin proveedores)", None)])
        self.cmb_prov_msg.currentIndexChanged.connect(lambda *_: self._cargar_hilo())
        fila.addWidget(QLabel("Proveedor:")); fila.addWidget(self.cmb_prov_msg, 1)
        fila.addWidget(_btn_cargando("🔄  Actualizar", self._cargar_hilo))
        ly.addLayout(fila)
        self.txt_hilo = QPlainTextEdit(); self.txt_hilo.setReadOnly(True)
        self.txt_hilo.setStyleSheet(f"QPlainTextEdit{{background:#0D1117;color:{_TEXT};"
                                    f"border:2px solid {_CIAN};border-radius:10px;padding:8px;}}")
        ly.addWidget(self.txt_hilo, 1)
        envio = QHBoxLayout()
        self.in_msg = _inp("Escribe un mensaje…")
        self.in_msg.returnPressed.connect(self._enviar_msg)
        envio.addWidget(self.in_msg, 1)
        envio.addWidget(_btn("Enviar", self._enviar_msg, primary=True))
        ly.addLayout(envio)
        return w

    def _cargar_hilo(self):
        pid = self.cmb_prov_msg.currentData()
        self.txt_hilo.clear()
        if not pid:
            return
        portal.marcar_leido(pid, autor="proveedor", id_empresa=self._emp())
        for m in portal.hilo(pid, id_empresa=self._emp()):
            quien = "Tú (empresa)" if m.get("autor") == "empresa" else "Proveedor"
            self.txt_hilo.appendPlainText(f"[{str(m.get('creado_en') or '')[:16]}] {quien}: {m.get('cuerpo')}")

    def _enviar_msg(self):
        pid = self.cmb_prov_msg.currentData()
        cuerpo = self.in_msg.text().strip()
        if not pid or not cuerpo:
            return
        if portal.enviar_mensaje(pid, cuerpo, autor="empresa", id_empresa=self._emp()):
            self.in_msg.clear()
            self._cargar_hilo()


class _DialogoInvitacion(QDialog):
    """Muestra la invitación al proveedor: token, enlace del panel, estado del correo y vista previa
    del mensaje (frameless, esquinas redondeadas)."""

    def __init__(self, res, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo="Invitación al proveedor", ancho=560)
        # Estado del correo (enviado / preparado / sin email).
        if res.get("enviado"):
            estado = f"✅ Correo enviado a {res.get('email')}"
        elif res.get("error") == "sin_email":
            estado = "⚠ El proveedor no tiene email: comparte el token/enlace manualmente."
        elif "enviado" in res:
            estado = f"📝 Correo preparado (sin canal configurado). Destinatario: {res.get('email') or '—'}"
        else:
            estado = "Comparte este token/enlace con el proveedor."
        lbl_est = QLabel(estado)
        lbl_est.setStyleSheet(f"color:{_TEXT};background:transparent;font-size:12px;font-weight:700;")
        lbl_est.setWordWrap(True)
        v.addWidget(lbl_est)

        v.addWidget(self._campo("Token de acceso", res.get("token", "")))
        v.addWidget(self._campo("Enlace del panel web", res.get("enlace", "")))

        prev = QPlainTextEdit()
        prev.setReadOnly(True)
        prev.setPlainText(res.get("cuerpo") or res.get("cuerpo_texto") or "")
        prev.setFixedHeight(180)
        prev.setStyleSheet(f"QPlainTextEdit{{background:#0D1117;color:{_DIM};border:2px solid {_DIM};"
                           f"border-radius:8px;padding:8px;font-size:11px;}}")
        v.addWidget(QLabel("Vista previa del correo:"))
        v.addWidget(prev)

        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(row)

    def _campo(self, etiqueta, valor):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(3)
        cap = QLabel(etiqueta); cap.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        campo = _inp(""); campo.setText(str(valor)); campo.setReadOnly(True); campo.setCursorPosition(0)
        l.addWidget(cap); l.addWidget(campo)
        return w


def _divisas_soportadas():
    try:
        from src.utils import divisas
        ms = list(divisas.monedas_soportadas() or [])
        if ms:
            return [(str(m), str(m)) for m in ms]
    except Exception:
        pass
    return [("EUR", "EUR"), ("USD", "USD"), ("GBP", "GBP")]


class _DialogoPublicarMercado(QDialog):
    """Publica un artículo del proveedor en la Lonja: divisa, precio de compra directa, puja mínima,
    cantidad y unidad (frameless, esquinas redondeadas)."""

    def __init__(self, nombre_proveedor, parent=None):
        super().__init__(parent)
        self.datos = None
        v = _dialogo_frameless(self, titulo=f"Publicar en el mercado · {nombre_proveedor}", ancho=460)
        self.in_cod = _inp("Código de artículo")
        self.cmb_div = _combo(_divisas_soportadas())
        self.cmb_div.setMinimumWidth(120); self.cmb_div.view().setMinimumWidth(120)
        self.in_precio = _inp("Precio (compra directa)")
        self.in_pmin = _inp("Puja mínima")
        self.in_cant = _inp("Cantidad disponible"); self.in_cant.setText("1")
        self.cmb_uni = _combo([("unidad", "unidad"), ("caja", "caja"), ("palé", "pale"), ("kg", "kg")])
        self.cmb_uni.setMinimumWidth(120); self.cmb_uni.view().setMinimumWidth(120)
        self.in_dur = _inp("Duración de la subasta (horas)"); self.in_dur.setText("24")
        self.in_res = _inp("Precio de reserva (opcional)")
        self.in_inc = _inp("Incremento mínimo de puja"); self.in_inc.setText("0")
        # Tipo de comercio al que suministra (gating por edición). Vacío = todas.
        self._tc_chks = []
        tcrow = QHBoxLayout()
        for cod_tc, etq_tc in (("SUPERMARKET", "Supermercado"), ("RETAIL", "Retail"),
                               ("PHARMACY", "Farmacia"), ("TEXTIL", "Textil"), ("BAKERY", "Panadería")):
            ch = QCheckBox(etq_tc); ch.setProperty("tc", cod_tc)
            ch.setStyleSheet(f"color:{_TEXT};font-size:11px;")
            self._tc_chks.append(ch); tcrow.addWidget(ch)
        for etq, wdg in (("Artículo", self.in_cod), ("Divisa", self.cmb_div),
                         ("Precio (compra directa)", self.in_precio), ("Puja mínima", self.in_pmin),
                         ("Cantidad", self.in_cant), ("Unidad", self.cmb_uni),
                         ("Duración subasta (h)", self.in_dur), ("Precio de reserva (opc.)", self.in_res),
                         ("Incremento mínimo", self.in_inc)):
            cap = QLabel(etq); cap.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
            v.addWidget(cap); v.addWidget(wdg)
        tccap = QLabel("Tipo de comercio (vacío = todas las ediciones)")
        tccap.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        v.addWidget(tccap); v.addLayout(tcrow)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn("Cancelar", self.reject))
        row.addWidget(_btn("Publicar", self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        cod = (self.in_cod.text() or "").strip().upper()

        def _f(le, d=0.0):
            try:
                return float((le.text() or "").replace(",", "."))
            except ValueError:
                return d
        precio = _f(self.in_precio); cant = _f(self.in_cant, 1)
        if not cod or precio <= 0 or cant <= 0:
            return
        res_txt = (self.in_res.text() or "").strip()
        tipos = [c.property("tc") for c in self._tc_chks if c.isChecked()]
        self.datos = {"codigo": cod, "divisa": self.cmb_div.currentData(), "precio": precio,
                      "puja_minima": _f(self.in_pmin), "cantidad": cant,
                      "unidad": self.cmb_uni.currentData(),
                      "duracion_horas": _f(self.in_dur, 24), "incremento_minimo": _f(self.in_inc),
                      "precio_reserva": (_f(self.in_res) if res_txt else None),
                      "tipo_comercio": tipos}
        self.accept()
