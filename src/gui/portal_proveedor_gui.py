"""
Portal de proveedor — lado EMPRESA (embebido en el módulo Proveedores).

Orquesta `services.compras.portal` (la lógica vive allí; esta capa es solo interfaz). Pestañas:
- Proveedores conectados: invitar / ver enlace / revocar / regenerar token + estado de conexión.
- RFQ / Subasta inversa: crear peticiones de precio, ver ofertas y adjudicar (crea el pedido real).
- Mensajería: conversación empresa↔proveedor.

DEGRADABLE: funciona en local aunque el enlace remoto no esté desplegado; muestra el modo actual.
Reutiliza los helpers visuales de `catalogo_gestion` (coherencia con el resto del módulo de compras).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo,
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
        tabs.addTab(self._tab_rfq(), "RFQ / Subasta")
        tabs.addTab(self._tab_mensajes(), "Mensajería")
        root.addWidget(tabs)
        self._refrescar_modo()
        self._cargar_cuentas()

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
        fila.addWidget(_btn("✉  Invitar", self._invitar, primary=True))
        ly.addLayout(fila)
        bar = QHBoxLayout()
        bar.addWidget(_btn("✉  Enviar invitación", self._enviar_correo, primary=True))
        bar.addWidget(_btn("🔑  Ver enlace", self._ver_enlace, primary=True))
        bar.addWidget(_btn("♻  Regenerar token", self._regenerar, primary=True))
        bar.addWidget(_btn("Revocar", self._revocar, danger=True))
        bar.addStretch()
        bar.addWidget(_btn("🔄  Actualizar", self._cargar_cuentas, primary=True))
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

    # ── RFQ / Subasta inversa ─────────────────────────────────────────────────
    def _tab_rfq(self):
        w = QWidget(); ly = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.in_rfq_cod = _inp("Código de artículo"); self.in_rfq_cod.setFixedWidth(180)
        self.in_rfq_cant = _inp("Cantidad"); self.in_rfq_cant.setFixedWidth(110)
        self.cmb_rfq_uni = _combo([("unidad", "unidad"), ("caja", "caja"), ("palé", "pale"), ("kg", "kg")])
        for x in (QLabel("Artículo:"), self.in_rfq_cod, self.in_rfq_cant, self.cmb_rfq_uni):
            fila.addWidget(x)
        fila.addWidget(_btn("➕  Crear RFQ", self._crear_rfq, primary=True))
        fila.addStretch()
        fila.addWidget(_btn("🔄  Actualizar", self._cargar_rfq, primary=True))
        ly.addLayout(fila)
        self.tbl_rfq = _tabla(["ID", "Artículo", "Cantidad", "Unidad", "Estado", "Pedido", "Fecha"])
        self.tbl_rfq.cellClicked.connect(lambda *_: self._cargar_ofertas())
        ly.addWidget(self.tbl_rfq)
        ofb = QHBoxLayout()
        ofb.addWidget(QLabel("Ofertas de la RFQ seleccionada (mejor precio arriba):"))
        ofb.addStretch()
        ofb.addWidget(_btn("✓  Adjudicar seleccionada", self._adjudicar, primary=True))
        ly.addLayout(ofb)
        self.tbl_ofertas = _tabla(["Proveedor", "Precio", "Unidad", "Plazo (d)", "Estado", "Fecha"])
        ly.addWidget(self.tbl_ofertas)
        self._cargar_rfq()
        return w

    def _crear_rfq(self):
        cod = (self.in_rfq_cod.text() or "").strip().upper()
        try:
            cant = float(self.in_rfq_cant.text() or 0)
        except ValueError:
            cant = 0
        if not cod or cant <= 0:
            _aviso(self, "RFQ", "Indica un artículo y una cantidad válida.", "warning"); return
        rid = portal.crear_rfq(cod, cant, unidad_medida=self.cmb_rfq_uni.currentData(),
                               creado_por=self.usuario.get("nombre"), id_empresa=self._emp())
        if rid:
            self.in_rfq_cod.clear(); self.in_rfq_cant.clear()
            self._cargar_rfq()

    def _cargar_rfq(self):
        data = portal.listar_rfq(id_empresa=self._emp())
        self.tbl_rfq.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id"), d.get("codigo_articulo"), d.get("cantidad"),
                                   d.get("unidad_medida"), d.get("estado"),
                                   d.get("id_pedido_adjudicado"), str(d.get("creado_en") or "")[:16]]):
                self.tbl_rfq.setItem(i, j, _it(v))
        self.tbl_ofertas.setRowCount(0)

    def _rfq_sel(self):
        r = self.tbl_rfq.currentRow()
        if r < 0:
            return None
        try:
            return int(self.tbl_rfq.item(r, 0).text())
        except Exception:
            return None

    def _cargar_ofertas(self):
        rid = self._rfq_sel()
        self.tbl_ofertas.setRowCount(0)
        if not rid:
            return
        self._ofertas = portal.ofertas_de_rfq(rid, self._emp())
        self.tbl_ofertas.setRowCount(len(self._ofertas))
        for i, o in enumerate(self._ofertas):
            for j, v in enumerate([o.get("proveedor"), o.get("precio"), o.get("unidad_medida"),
                                   o.get("plazo_dias"), o.get("estado"), str(o.get("creado_en") or "")[:16]]):
                self.tbl_ofertas.setItem(i, j, _it(v))

    def _adjudicar(self):
        rid = self._rfq_sel()
        r = self.tbl_ofertas.currentRow()
        ofertas = getattr(self, "_ofertas", []) or []
        if not rid or r < 0 or r >= len(ofertas):
            _aviso(self, "RFQ", "Selecciona una RFQ y una oferta.", "warning"); return
        idp = ofertas[r]["id_proveedor"]
        res = portal.adjudicar_rfq(rid, idp, id_empresa=self._emp(), usuario=self.usuario.get("nombre"))
        if res.get("ok"):
            _aviso(self, "RFQ", f"Adjudicada. Pedido {res['id_pedido']} enviado (ver Recepciones).",
                   "success")
            self._cargar_rfq()
        else:
            _aviso(self, "RFQ", f"No se pudo adjudicar: {res.get('error')}", "error")

    # ── Mensajería ────────────────────────────────────────────────────────────
    def _tab_mensajes(self):
        w = QWidget(); ly = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.cmb_prov_msg = _combo(self._provs() or [("(sin proveedores)", None)])
        self.cmb_prov_msg.currentIndexChanged.connect(lambda *_: self._cargar_hilo())
        fila.addWidget(QLabel("Proveedor:")); fila.addWidget(self.cmb_prov_msg, 1)
        fila.addWidget(_btn("🔄  Actualizar", self._cargar_hilo, primary=True))
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
