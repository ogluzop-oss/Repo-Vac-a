"""
Asistente de PRIMEROS PASOS (R1) — deja la empresa lista y crea la PRIMERA FACTURA en pocos pasos,
para que un dueño de pyme empiece a facturar en minutos (competir con Holded).

La GUI SOLO orquesta: toda la lógica reutiliza los motores existentes
(``db/empresa``, ``utils/fiscalidad``, ``db/clientes``, ``db/facturas_cliente``,
``services/facturacion/distribucion``). Al terminar puede activar el MODO PYME SIMPLE
(``services/onboarding``). Ningún fallo de un paso rompe el arranque (best-effort + avisos).
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QRadioButton, QStackedWidget, QVBoxLayout, QWidget)

from assets.estilo_global import mostrar_mensaje
from src.gui._neon_ui import _btn

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_FONT = "Segoe UI"


def _lbl(txt, *, bold=False, size=13, color=_TEXT):
    lb = QLabel(txt)
    lb.setWordWrap(True)
    lb.setStyleSheet(f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
                     f"font-weight:{'900' if bold else '500'};background:transparent;border:none;")
    return lb


def _input(placeholder=""):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(38)
    e.setStyleSheet(
        f"QLineEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};border-radius:9px;"
        f"padding:0 10px;font-family:'{_FONT}';font-size:13px;}}"
        f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _num(txt):
    """Convierte un texto a float tolerando coma decimal; 0.0 si no es válido."""
    try:
        return float(str(txt).strip().replace(",", "."))
    except Exception:
        return 0.0


class OnboardingWizard(QDialog):
    """Asistente por pasos. `id_empresa` opcional (por defecto, la empresa activa)."""

    def __init__(self, parent=None, *, id_empresa=None):
        super().__init__(parent)
        self._emp = id_empresa
        self._cliente_id = None
        self._factura_id = None
        self._pdf = None
        self._drag = None
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build()

    # ────────────────────────────────────────────────────────────────────────
    # LÓGICA (reutiliza motores; separada de la UI para poder testarla)
    # ────────────────────────────────────────────────────────────────────────
    def _emp_id(self):
        if self._emp:
            return self._emp
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def guardar_empresa(self, campos: dict):
        """Guarda datos de empresa vía el motor único `db.empresa.actualizar_empresa`."""
        try:
            from src.db.empresa import actualizar_empresa
            ok = actualizar_empresa(self._emp_id(), **{k: v for k, v in campos.items() if v})
            return (bool(ok), "" if ok else "No se pudieron guardar los datos de empresa.")
        except Exception as e:
            return (False, str(e))

    def crear_cliente(self, nombre, nif=None, email=None):
        try:
            from src.db.clientes import crear_cliente
            cid = crear_cliente(nombre, nif=nif or None, email=email or None, id_empresa=self._emp_id())
            if cid:
                self._cliente_id = cid
                return (True, "")
            return (False, "No se pudo crear el cliente.")
        except Exception as e:
            return (False, str(e))

    def crear_factura(self, descripcion, cantidad, precio, *, emitir_real: bool):
        """Crea la primera factura reutilizando `db.facturas_cliente.crear_factura` (+ emitir si es
        real) y genera el PDF con `facturacion.distribucion.exportar_factura`."""
        try:
            from src.db import facturas_cliente as FC
            lineas = [{"descripcion": descripcion, "cantidad": float(cantidad or 0),
                       "precio_unitario": float(precio or 0)}]
            fid = FC.crear_factura(id_cliente=self._cliente_id, lineas=lineas,
                                   tipo_documento="factura", id_empresa=self._emp_id())
            if not fid:
                return (False, "No se pudo crear la factura.")
            self._factura_id = fid
            if emitir_real:
                try:
                    FC.emitir(fid, id_empresa=self._emp_id())
                except Exception:
                    pass
            try:
                from src.services.facturacion.distribucion import exportar_factura
                self._pdf = exportar_factura(fid, formato="pdf", id_empresa=self._emp_id())
            except Exception:
                self._pdf = None
            return (True, "")
        except Exception as e:
            return (False, str(e))

    def _correo_id(self):
        try:
            from src.db.correo import listar_correos
            cuentas = listar_correos(self._emp_id()) or []
            if cuentas:
                c = cuentas[0]
                return c.get("id") or c.get("id_correo")
        except Exception:
            pass
        return None

    def enviar_email(self, destinatario=None):
        cid = self._correo_id()
        if not cid:
            return (False, "No hay correo corporativo configurado (Ajustes → Correo).")
        if not self._factura_id:
            return (False, "Primero crea la factura.")
        try:
            from src.services.facturacion.distribucion import enviar_factura_email
            r = enviar_factura_email(self._factura_id, cid, destinatario=destinatario or None,
                                     id_empresa=self._emp_id()) or {}
            return (bool(r.get("ok")), r.get("mensaje") or "")
        except Exception as e:
            return (False, str(e))

    # ────────────────────────────────────────────────────────────────────────
    # UI
    # ────────────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(26, 22, 26, 22)
        ly.setSpacing(14)

        # Cabecera
        cab = QHBoxLayout()
        self._titulo = _lbl("🚀  PRIMEROS PASOS", bold=True, size=17, color=_CIAN)
        cab.addWidget(self._titulo)
        cab.addStretch()
        bx = _btn("✕", color_fg="#F85149", color_border="#F85149", hover_bg="#F85149", h=32)
        bx.setFixedWidth(40)
        bx.clicked.connect(self._cerrar_sin_completar)
        cab.addWidget(bx)
        ly.addLayout(cab)

        self._stack = QStackedWidget()
        ly.addWidget(self._stack, 1)
        self._stack.addWidget(self._page_bienvenida())   # 0
        self._stack.addWidget(self._page_empresa())       # 1
        self._stack.addWidget(self._page_cliente())       # 2
        self._stack.addWidget(self._page_factura())       # 3
        self._stack.addWidget(self._page_emitir())        # 4
        self._stack.addWidget(self._page_fin())           # 5

        # Barra de navegación
        nav = QHBoxLayout()
        self._btn_atras = _btn("←  Atrás", h=40)
        self._btn_atras.clicked.connect(self._atras)
        self._btn_sig = _btn("Siguiente  →", color_bg=_CIAN, color_fg="#0D1117",
                             color_border=_CIAN, hover_bg=_BG2, hover_fg=_CIAN, h=40)
        self._btn_sig.clicked.connect(self._siguiente)
        nav.addWidget(self._btn_atras)
        nav.addStretch()
        nav.addWidget(self._btn_sig)
        ly.addLayout(nav)

        self._ir(0)

    def _sec_titulo(self, txt):
        return _lbl(txt, bold=True, size=15, color=_CIAN)

    def _page_bienvenida(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        v.addWidget(self._sec_titulo("Bienvenido a Smart Manager"))
        v.addWidget(_lbl("Te guiamos en 4 pasos para dejar tu empresa lista y crear tu PRIMERA "
                         "FACTURA en pocos minutos:\n\n① Datos de tu empresa\n② Tu primer cliente\n"
                         "③ Tu primera factura\n④ Emitirla (o guardarla como práctica) y su PDF"))
        v.addStretch()
        mas = _btn("Configurar más tarde", h=34)
        mas.clicked.connect(self._cerrar_sin_completar)
        v.addWidget(mas, alignment=Qt.AlignmentFlag.AlignLeft)
        return w

    def _page_empresa(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)
        v.addWidget(self._sec_titulo("① Datos de tu empresa"))
        self._e_nombre = _input("Nombre / razón social de tu empresa *")
        self._e_cif = _input("CIF / NIF")
        self._e_pais = QComboBox()
        self._e_pais.setFixedHeight(38)
        self._e_pais.setStyleSheet(
            f"QComboBox{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};border-radius:9px;"
            f"padding:0 10px;font-family:'{_FONT}';font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:{_BG2};color:{_TEXT};"
            f"selection-background-color:{_CIAN};selection-color:#0D1117;}}")
        self._paises = []
        try:
            from src.utils import fiscalidad
            self._paises = fiscalidad.paises_disponibles() or []
        except Exception:
            self._paises = []
        for p in self._paises:
            self._e_pais.addItem(f"{p['nombre']}  ·  IVA {p['iva']:.0f}%", p["code"])
        self._e_pais.currentIndexChanged.connect(self._sync_iva_lbl)
        self._e_iva = _lbl("", color=_CIAN, bold=True)
        self._e_email = _input("Email de la empresa")
        self._e_dir = _input("Dirección fiscal")
        for lb, wdg in (("Nombre *", self._e_nombre), ("CIF / NIF", self._e_cif),
                        ("País fiscal (determina el IVA)", self._e_pais), ("", self._e_iva),
                        ("Email", self._e_email), ("Dirección", self._e_dir)):
            if lb:
                v.addWidget(_lbl(lb, size=11, color="#8B949E"))
            v.addWidget(wdg)
        v.addStretch()
        self._sync_iva_lbl()
        return w

    def _sync_iva_lbl(self, *_):
        code = self._e_pais.currentData()
        try:
            from src.utils import fiscalidad
            self._e_iva.setText(f"Se aplicará un IVA del {fiscalidad.iva_de_pais(code):.0f}% en tus facturas.")
        except Exception:
            self._e_iva.setText("")

    def _page_cliente(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)
        v.addWidget(self._sec_titulo("② Tu primer cliente"))
        self._c_nombre = _input("Nombre del cliente *")
        self._c_nif = _input("NIF / DNI")
        self._c_email = _input("Email (para enviarle la factura)")
        for lb, wdg in (("Nombre *", self._c_nombre), ("NIF / DNI", self._c_nif), ("Email", self._c_email)):
            v.addWidget(_lbl(lb, size=11, color="#8B949E")); v.addWidget(wdg)
        v.addStretch()
        return w

    def _page_factura(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)
        v.addWidget(self._sec_titulo("③ Tu primera factura"))
        self._f_desc = _input("Concepto (p. ej. 'Servicio de consultoría') *")
        self._f_cant = _input("Cantidad")
        self._f_cant.setText("1")
        self._f_precio = _input("Precio (IVA incluido) *")
        for e in (self._f_cant, self._f_precio):
            e.textChanged.connect(self._sync_total)
        self._f_total = _lbl("", color=_CIAN, bold=True, size=14)
        for lb, wdg in (("Concepto *", self._f_desc), ("Cantidad", self._f_cant), ("Precio *", self._f_precio)):
            v.addWidget(_lbl(lb, size=11, color="#8B949E")); v.addWidget(wdg)
        v.addWidget(self._f_total)
        v.addStretch()
        self._sync_total()
        return w

    def _sync_total(self, *_):
        total = _num(self._f_cant.text()) * _num(self._f_precio.text())
        try:
            from src.utils import fiscalidad
            d = fiscalidad.desglose_iva(total, id_empresa=self._emp_id())
            self._f_total.setText(f"Total: {total:.2f}  (base {d['base']:.2f} + IVA {d['cuota']:.2f})")
        except Exception:
            self._f_total.setText(f"Total: {total:.2f}")

    def _page_emitir(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        v.addWidget(self._sec_titulo("④ Emitir tu factura"))
        self._rb_real = QRadioButton("Emitir de verdad (cuenta fiscalmente; no se puede borrar, solo rectificar)")
        self._rb_borrador = QRadioButton("Guardar como borrador de práctica (podrás revisarla o descartarla)")
        self._rb_real.setChecked(True)
        for rb in (self._rb_real, self._rb_borrador):
            rb.setStyleSheet(f"color:{_TEXT};font-family:'{_FONT}';font-size:13px;")
            v.addWidget(rb)
        self._btn_crear = _btn("🧾  Crear factura", color_bg=_CIAN, color_fg="#0D1117",
                               color_border=_CIAN, hover_bg=_BG2, hover_fg=_CIAN, h=42)
        self._btn_crear.clicked.connect(self._do_crear_factura)
        v.addWidget(self._btn_crear)
        self._lbl_res = _lbl("")
        v.addWidget(self._lbl_res)
        fila = QHBoxLayout()
        self._btn_pdf = _btn("📄  Ver PDF", h=38); self._btn_pdf.clicked.connect(self._abrir_pdf)
        self._btn_mail = _btn("✉  Enviar por email", h=38); self._btn_mail.clicked.connect(self._do_email)
        self._btn_pdf.setEnabled(False); self._btn_mail.setEnabled(False)
        fila.addWidget(self._btn_pdf); fila.addWidget(self._btn_mail); fila.addStretch()
        v.addLayout(fila)
        v.addStretch()
        return w

    def _page_fin(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(12)
        v.addWidget(self._sec_titulo("¡Listo! 🎉"))
        v.addWidget(_lbl("Ya tienes tu empresa configurada y tu primera factura creada. Desde aquí puedes "
                         "seguir facturando cuando quieras."))
        self._chk_simple = QCheckBox("Activar MODO PYME SIMPLE (muestra solo lo esencial en el menú)")
        self._chk_simple.setChecked(True)
        self._chk_simple.setStyleSheet(f"color:{_TEXT};font-family:'{_FONT}';font-size:13px;")
        v.addWidget(self._chk_simple)
        v.addWidget(_lbl("Podrás desactivarlo cuando quieras en Configuración.", size=11, color="#8B949E"))
        v.addStretch()
        return w

    # ── Navegación / acciones ────────────────────────────────────────────────
    def _ir(self, idx):
        idx = max(0, min(idx, self._stack.count() - 1))
        self._stack.setCurrentIndex(idx)
        self._btn_atras.setVisible(idx not in (0, self._stack.count() - 1))
        if idx == self._stack.count() - 1:
            self._btn_sig.setText("Finalizar  ✓")
        elif idx == 4:
            self._btn_sig.setText("Siguiente  →")
        else:
            self._btn_sig.setText("Siguiente  →")

    def _atras(self):
        self._ir(self._stack.currentIndex() - 1)

    def _siguiente(self):
        i = self._stack.currentIndex()
        if i == 1:      # empresa
            nombre = self._e_nombre.text().strip()
            if not nombre:
                return self._aviso("Indica el nombre de tu empresa.")
            ok, msg = self.guardar_empresa({
                "nombre_empresa": nombre, "razon_social": nombre, "cif_nif": self._e_cif.text().strip(),
                "pais_fiscal": self._e_pais.currentData(), "email_principal": self._e_email.text().strip(),
                "direccion_fiscal": self._e_dir.text().strip()})
            if not ok:
                return self._aviso(msg)
        elif i == 2:    # cliente
            nombre = self._c_nombre.text().strip()
            if not nombre:
                return self._aviso("Indica el nombre del cliente.")
            ok, msg = self.crear_cliente(nombre, self._c_nif.text().strip(), self._c_email.text().strip())
            if not ok:
                return self._aviso(msg)
        elif i == 3:    # factura (validación previa)
            if not self._f_desc.text().strip():
                return self._aviso("Indica el concepto de la factura.")
            if _num(self._f_precio.text()) <= 0:
                return self._aviso("Indica un precio mayor que 0.")
        elif i == 4:    # emitir: exigir que la factura esté creada
            if not self._factura_id:
                return self._aviso("Pulsa «Crear factura» antes de continuar.")
        elif i == self._stack.count() - 1:   # fin
            return self._finalizar()
        self._ir(i + 1)

    def _do_crear_factura(self):
        ok, msg = self.crear_factura(self._f_desc.text().strip(), _num(self._f_cant.text()),
                                     _num(self._f_precio.text()), emitir_real=self._rb_real.isChecked())
        if not ok:
            return self._aviso(msg)
        estado = "emitida" if self._rb_real.isChecked() else "borrador de práctica"
        self._lbl_res.setText(f"✓ Factura creada ({estado}).")
        self._btn_pdf.setEnabled(bool(self._pdf))
        self._btn_mail.setEnabled(True)

    def _abrir_pdf(self):
        if self._pdf and os.path.exists(self._pdf):
            try:
                os.startfile(self._pdf)  # noqa: S606
            except Exception:
                self._aviso("No se pudo abrir el PDF.")
        else:
            self._aviso("El PDF no está disponible.")

    def _do_email(self):
        ok, msg = self.enviar_email(self._c_email.text().strip())
        self._aviso("Factura enviada por email." if ok else (msg or "No se pudo enviar."),
                    exito=ok)

    def _finalizar(self):
        try:
            from src.services import onboarding
            onboarding.fijar_modo_simple(self._chk_simple.isChecked())
            onboarding.marcar_completado()
        except Exception:
            pass
        if self._pdf and os.path.exists(self._pdf):
            try:
                os.startfile(self._pdf)  # noqa: S606
            except Exception:
                pass
        self.accept()

    def _cerrar_sin_completar(self):
        # "Configurar más tarde": marca completado para no volver a molestar en cada inicio.
        try:
            from src.services import onboarding
            onboarding.marcar_completado()
        except Exception:
            pass
        self.reject()

    def _aviso(self, texto, *, exito=False):
        try:
            mostrar_mensaje(self, "Primeros pasos", texto, "success" if exito else "warning")
        except Exception:
            pass

    # Arrastre (ventana sin barra de título)
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
