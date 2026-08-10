"""
Enrolamiento MFA en la interfaz (Gobernanza MFA · Fase 1). UI de AUTOSERVICIO para que un usuario
autenticado configure su propio segundo factor. Reutiliza EXCLUSIVAMENTE el motor existente
(`services.seguridad.mfa`: TOTP + recovery codes cifrados/hasheados), la política de empresa
(`mfa_politica`) y la auditoría (`mfa_eventos`). No crea motor nuevo, no toca el login.

Reglas de seguridad respetadas:
  · El secreto TOTP se muestra SOLO durante el enrolamiento (clave manual + QR); nunca se re-muestra.
  · Los recovery codes se muestran UNA sola vez; se guardan hasheados (motor existente).
  · Nunca se registran secretos en logs (eventos vía `mfa_eventos`, que además sanea).
  · Desactivar exige autenticación reciente y respeta la política obligatoria de la empresa.
"""

import io
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QStackedWidget, QTextEdit, QVBoxLayout, QWidget)

logger = logging.getLogger("gui.mfa")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_BORDE = "#30363D"
_ROJO = "#F85149"
_VERDE = "#2ECC71"
_FONT = "Segoe UI"


def _lbl(txt, *, size=13, color=_TEXT, bold=False, wrap=False):
    l = QLabel(txt)
    l.setStyleSheet(f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
                    f"font-weight:{'900' if bold else '500'};background:transparent;border:none;")
    l.setWordWrap(wrap)
    return l


def _btn(txt, slot=None, *, color=_CIAN, relleno=False, h=42):
    b = QPushButton(txt)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(h)
    if relleno:
        b.setStyleSheet(f"QPushButton{{background:{color};color:#0D1117;border:2px solid {color};"
                        f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:13px;"
                        f"padding:0 16px;}}QPushButton:hover{{background:#FFF;}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{color};border:2px solid {color};"
                        f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:13px;"
                        f"padding:0 16px;}}QPushButton:hover{{background:{color};color:#0D1117;}}")
    if slot:
        b.clicked.connect(slot)
    return b


def _input(ph="", password=False):
    e = QLineEdit()
    e.setPlaceholderText(ph)
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setMinimumHeight(40)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:0 12px;font-size:15px;font-family:'{_FONT}';}}"
                    f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _qr_pixmap(uri, size=220):
    """QR del URI otpauth → QPixmap. Degradable: None si `qrcode` no está disponible."""
    try:
        import qrcode
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())
        return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    except Exception as e:
        logger.debug("QR no disponible: %s", e)
        return None


def _marco(dialog, ancho=520):
    """Contenedor neón estándar de los diálogos MFA. Devuelve el layout interior."""
    dialog.setModal(True)
    dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dialog.setFixedWidth(ancho)
    main = QVBoxLayout(dialog)
    main.setContentsMargins(0, 0, 0, 0)
    cont = QFrame()
    cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
    main.addWidget(cont)
    ly = QVBoxLayout(cont)
    ly.setContentsMargins(26, 22, 26, 24)
    ly.setSpacing(12)
    return ly


class _ReautenticarDialog(QDialog):
    """Autenticación reciente (contraseña) para operaciones sensibles (desactivar MFA)."""

    def __init__(self, cuenta, parent=None):
        super().__init__(parent)
        self._cuenta = cuenta
        self.ok = False
        ly = _marco(self, 440)
        ly.addWidget(_lbl("Confirma tu identidad", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl("Introduce tu contraseña para continuar.", size=12, color=_TEXT2, wrap=True))
        self.inp = _input("Contraseña", password=True)
        self.inp.returnPressed.connect(self._validar)
        ly.addWidget(self.inp)
        self.err = _lbl("", size=11, color=_ROJO, wrap=True)
        ly.addWidget(self.err)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Cancelar", self.reject, color=_ROJO))
        fila.addWidget(_btn("Confirmar", self._validar, color=_VERDE, relleno=True))
        ly.addLayout(fila)

    def _validar(self):
        try:
            from src.db.usuario import validar_login_usuario
            u = validar_login_usuario(self._cuenta, self.inp.text())
        except Exception:
            u = None
        if u:
            self.ok = True
            self.accept()
        else:
            self.err.setText("Contraseña incorrecta.")


class _CodigoTOTPDialog(QDialog):
    """Pide un código TOTP válido del propio usuario (para regenerar recovery codes)."""

    def __init__(self, id_usuario, parent=None):
        super().__init__(parent)
        self._uid = id_usuario
        self.ok = False
        ly = _marco(self, 440)
        ly.addWidget(_lbl("Verificación en dos pasos", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl("Introduce el código actual de tu app de autenticación.",
                          size=12, color=_TEXT2, wrap=True))
        self.inp = _input("Código de 6 dígitos")
        self.inp.returnPressed.connect(self._validar)
        ly.addWidget(self.inp)
        self.err = _lbl("", size=11, color=_ROJO, wrap=True)
        ly.addWidget(self.err)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Cancelar", self.reject, color=_ROJO))
        fila.addWidget(_btn("Verificar", self._validar, color=_VERDE, relleno=True))
        ly.addLayout(fila)

    def _validar(self):
        try:
            from src.services.seguridad import mfa
            ok = mfa.verificar_totp(mfa._secreto(self._uid), self.inp.text().strip())
        except Exception:
            ok = False
        if ok:
            self.ok = True
            self.accept()
        else:
            self.err.setText("Código no válido.")


class _RecoveryCodesView(QWidget):
    """Vista de recovery codes (UNA sola vez): copiar / descargar + confirmación de guardado."""

    def __init__(self, codigos, on_finalizar):
        super().__init__()
        self._codigos = list(codigos or [])
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(10)
        ly.addWidget(_lbl("Códigos de recuperación", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl("Guarda estos códigos en un lugar seguro. Te permitirán entrar si pierdes tu "
                          "dispositivo. NO se volverán a mostrar.", size=12, color=_TEXT2, wrap=True))
        self.box = QTextEdit()
        self.box.setReadOnly(True)
        self.box.setPlainText("\n".join(self._codigos))
        self.box.setFixedHeight(150)
        self.box.setStyleSheet(f"QTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                               f"border-radius:8px;font-family:'Consolas','{_FONT}';font-size:15px;"
                               f"letter-spacing:1px;}}")
        ly.addWidget(self.box)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Copiar", self._copiar))
        fila.addWidget(_btn("Descargar", self._descargar))
        fila.addStretch()
        ly.addLayout(fila)
        self.chk = QCheckBox("He guardado los códigos en un lugar seguro")
        self.chk.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-family:'{_FONT}';font-size:12px;}}")
        self.chk.stateChanged.connect(lambda _=0: self.btn_fin.setEnabled(self.chk.isChecked()))
        ly.addWidget(self.chk)
        self.btn_fin = _btn("Finalizar", on_finalizar, color=_VERDE, relleno=True)
        self.btn_fin.setEnabled(False)
        ly.addWidget(self.btn_fin)

    def _copiar(self):
        QGuiApplication.clipboard().setText("\n".join(self._codigos))

    def _descargar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar códigos de recuperación",
                                              "recovery_codes.txt", "Texto (*.txt)")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write("\n".join(self._codigos) + "\n")
            except OSError as e:
                logger.debug("descargar recovery: %s", e)


class MFAEnrolamientoDialog(QDialog):
    """Flujo de enrolamiento: iniciar_activacion → QR + clave manual → código TOTP → confirmar →
    recovery codes (una vez). Reutiliza el motor `seguridad.mfa` sin modificarlo."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self._usuario = usuario or {}
        self._uid = self._usuario.get("id")
        self.activado = False
        from src.services.seguridad import mfa, mfa_eventos
        self._mfa = mfa
        self._eventos = mfa_eventos
        r = mfa.iniciar_activacion(self._uid, self._usuario.get("nombre") or "usuario")
        self._secreto = r.get("secreto") or ""
        self._uri = r.get("uri") or ""
        mfa_eventos.emitir("MFA_ENROLLMENT_STARTED", id_usuario=self._uid,
                           actor=self._usuario.get("nombre"))

        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        outer = QVBoxLayout(cont)
        outer.setContentsMargins(26, 22, 26, 24)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)
        self._stack.addWidget(self._paso_configurar())  # 0
        # el paso de recovery codes se añade tras confirmar

    def _paso_configurar(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(12)
        ly.addWidget(_lbl("Configurar verificación en dos pasos", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl("1) Escanea el QR con Google/Microsoft Authenticator o Authy.  "
                          "2) Introduce el código de 6 dígitos.", size=12, color=_TEXT2, wrap=True))
        fila = QHBoxLayout()
        pix = _qr_pixmap(self._uri)
        lbl_qr = QLabel()
        lbl_qr.setFixedSize(220, 220)
        lbl_qr.setStyleSheet(f"background:#FFFFFF;border-radius:10px;")
        lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pix:
            lbl_qr.setPixmap(pix)
        else:
            lbl_qr.setText("QR no disponible")
        fila.addWidget(lbl_qr)
        col = QVBoxLayout(); col.setSpacing(8)
        col.addWidget(_lbl("Clave manual (si no puedes escanear):", size=12, color=_TEXT2))
        clave = QLineEdit(self._secreto); clave.setReadOnly(True)
        clave.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_CIAN};border:2px solid {_BORDE};"
                            f"border-radius:8px;padding:8px;font-family:'Consolas';font-size:14px;"
                            f"letter-spacing:2px;}}")
        col.addWidget(clave)
        col.addWidget(_btn("Copiar clave",
                           lambda: QGuiApplication.clipboard().setText(self._secreto)))
        col.addStretch()
        col.addWidget(_lbl("Código de verificación:", size=12, color=_TEXT2))
        self._code = _input("6 dígitos")
        self._code.returnPressed.connect(self._activar)
        col.addWidget(self._code)
        fila.addLayout(col)
        ly.addLayout(fila)
        self._err = _lbl("", size=11, color=_ROJO, wrap=True)
        ly.addWidget(self._err)
        bl = QHBoxLayout()
        bl.addWidget(_btn("Cancelar", self.reject, color=_ROJO))
        bl.addWidget(_btn("Activar MFA", self._activar, color=_VERDE, relleno=True))
        ly.addLayout(bl)
        return w

    def _activar(self):
        r = self._mfa.confirmar_activacion(self._uid, (self._code.text() or "").strip())
        if not r.get("ok"):
            self._err.setText("Código inválido. Verifica la hora de tu dispositivo e inténtalo de nuevo.")
            return
        self._eventos.emitir("MFA_ENROLLED", id_usuario=self._uid,
                             actor=self._usuario.get("nombre"))
        self.activado = True
        codigos = r.get("recovery_codes") or []
        vista = _RecoveryCodesView(codigos, on_finalizar=self.accept)
        self._stack.addWidget(vista)  # 1
        self._stack.setCurrentWidget(vista)


class _StepUpDialog(QDialog):
    """Reto MFA para STEP-UP (acción de alto riesgo): pide TOTP/recovery y abre la ventana de confianza
    reciente (`mfa_stepup`). Feedback inline."""

    def __init__(self, usuario, accion, parent=None):
        super().__init__(parent)
        self._usuario = usuario or {}
        self._accion = accion
        self.ok = False
        ly = _marco(self, 440)
        ly.addWidget(_lbl("Confirmación de seguridad", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl("Esta acción requiere verificación en dos pasos reciente. Introduce el código "
                          "de tu app de autenticación (o un código de recuperación).",
                          size=12, color=_TEXT2, wrap=True))
        self.inp = _input("Código")
        self.inp.returnPressed.connect(self._validar)
        ly.addWidget(self.inp)
        self.err = _lbl("", size=11, color=_ROJO, wrap=True)
        ly.addWidget(self.err)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Cancelar", self.reject, color=_ROJO))
        fila.addWidget(_btn("Verificar", self._validar, color=_VERDE, relleno=True))
        ly.addLayout(fila)

    def _validar(self):
        from src.services.seguridad import mfa_stepup
        if mfa_stepup.verificar(self._usuario.get("id"), (self.inp.text() or "").strip(),
                                id_empresa=self._usuario.get("id_empresa"), accion=self._accion):
            self.ok = True
            self.accept()
        else:
            self.err.setText("Código no válido.")


def pedir_step_up(usuario, accion, parent=None) -> bool:
    """Guard REUTILIZABLE de step-up. Devuelve True si la acción puede continuar. Si el usuario tiene MFA
    activo y no hay step-up reciente, exige el 2º factor. Si no tiene MFA activo → True (el control queda
    en la reautenticación/RBAC propios del llamador). Uso: `if not pedir_step_up(u, 'roles.cambiar'): return`."""
    usuario = usuario or {}
    uid = usuario.get("id")
    try:
        from src.services.seguridad import mfa, mfa_stepup
        if not uid or not mfa.mfa_activo(uid):
            return True
        if mfa_stepup.reciente(uid, id_empresa=usuario.get("id_empresa")):
            return True
    except Exception:
        return True
    dlg = _StepUpDialog(usuario, accion, parent)
    return bool(dlg.exec()) and dlg.ok


def step_up_sesion(accion, parent=None) -> bool:
    """Atajo de `pedir_step_up` que toma el usuario de la SESIÓN activa (`sesion_global`). Guard oficial
    de step-up para las acciones críticas de negocio en el escritorio. Degradable (True si no hay sesión
    o si falla, para no bloquear flujos legítimos por un error del subsistema MFA)."""
    try:
        from src.db.usuario import sesion_global
        return pedir_step_up(sesion_global.usuario_actual or {}, accion, parent=parent)
    except Exception:
        return True


class MFAResetAdminDialog(QDialog):
    """Reset MFA ADMINISTRATIVO (Fase 3): reautenticación del administrador + step-up (si el admin tiene
    MFA activo) + motivo → resetea el MFA del usuario objetivo (reutiliza `mfa_admin.reset_mfa`).
    Feedback INLINE. La comprobación de permiso `mfa.admin.reset` la hace el llamador y el servicio."""

    def __init__(self, objetivo_id, objetivo_nombre, actor, parent=None):
        super().__init__(parent)
        self._oid = objetivo_id
        self._actor = actor or {}
        self.hecho = False
        ly = _marco(self, 480)
        ly.addWidget(_lbl("Resetear verificación en dos pasos", size=16, color=_CIAN, bold=True))
        ly.addWidget(_lbl(f"Usuario: {objetivo_nombre}. Se eliminará su MFA y sus códigos de "
                          "recuperación; deberá volver a configurarlo.", size=12, color=_TEXT2, wrap=True))
        ly.addWidget(_lbl("Confirma tu identidad (administrador):", size=12, color=_TEXT2))
        self.inp_pass = _input("Tu contraseña", password=True)
        ly.addWidget(self.inp_pass)
        self._admin_mfa = False
        try:
            from src.services.seguridad import mfa
            self._admin_mfa = mfa.mfa_activo(self._actor.get("id"))
        except Exception:
            self._admin_mfa = False
        if self._admin_mfa:
            ly.addWidget(_lbl("Código de tu app de autenticación (step-up):", size=12, color=_TEXT2))
            self.inp_totp = _input("6 dígitos")
            ly.addWidget(self.inp_totp)
        self.inp_motivo = _input("Motivo (opcional)")
        ly.addWidget(self.inp_motivo)
        self.err = _lbl("", size=11, color=_ROJO, wrap=True)
        ly.addWidget(self.err)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Cancelar", self.reject, color=_ROJO))
        fila.addWidget(_btn("Resetear MFA", self._reset, color=_VERDE, relleno=True))
        ly.addLayout(fila)

    def _reset(self):
        try:
            from src.db.usuario import validar_login_usuario
            u = validar_login_usuario(self._actor.get("nombre") or "", self.inp_pass.text())
        except Exception:
            u = None
        if not u:
            self.err.setText("Contraseña incorrecta.")
            return
        if self._admin_mfa:
            from src.services.seguridad import mfa
            if not mfa.verificar_totp(mfa._secreto(self._actor.get("id")),
                                      (self.inp_totp.text() or "").strip()):
                self.err.setText("Código de administrador no válido.")
                return
        from src.services.seguridad import mfa_admin
        r = mfa_admin.reset_mfa(self._oid, usuario_actor=self._actor,
                                id_empresa=self._actor.get("id_empresa"),
                                motivo=(self.inp_motivo.text() or "").strip() or None)
        if r.get("ok"):
            self.hecho = True
            self.accept()
        else:
            self.err.setText("No se pudo resetear: " + str(r.get("error") or "error"))


class MFASeguridadPanel(QWidget):
    """Panel de autoservicio MFA (pestaña 'Seguridad de la cuenta' en Configuración). Muestra el estado
    y permite activar / desactivar (según política) / regenerar recovery codes."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        if usuario is None:
            try:
                from src.db.usuario import sesion_global
                usuario = sesion_global.usuario_actual or {}
            except Exception:
                usuario = {}
        self._usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(_lbl("Verificación en dos pasos (MFA)", size=18, color=_CIAN, bold=True))
        root.addWidget(_lbl("Añade una capa extra de seguridad con una app de autenticación (TOTP). "
                            "Compatible con Google/Microsoft Authenticator y Authy.",
                            size=12, color=_TEXT2, wrap=True))
        self.lbl_estado = _lbl("", size=14, bold=True)
        root.addWidget(self.lbl_estado)
        fila = QHBoxLayout(); fila.setSpacing(10)
        self.btn_activar = _btn("Configurar MFA", self._configurar, color=_VERDE, relleno=True)
        self.btn_regenerar = _btn("Regenerar códigos de recuperación", self._regenerar)
        self.btn_desactivar = _btn("Desactivar MFA", self._desactivar, color=_ROJO)
        fila.addWidget(self.btn_activar)
        fila.addWidget(self.btn_regenerar)
        fila.addWidget(self.btn_desactivar)
        fila.addStretch()
        root.addLayout(fila)
        self.lbl_feedback = _lbl("", size=12, color=_TEXT2, wrap=True)
        root.addWidget(self.lbl_feedback)
        # Dispositivos de confianza del usuario (Fase 4).
        root.addSpacing(8)
        root.addWidget(_lbl("Dispositivos de confianza", size=14, color=_CIAN, bold=True))
        root.addWidget(_lbl("Terminales donde no se te vuelve a pedir el 2º factor al iniciar sesión. "
                            "Puedes revocarlos en cualquier momento.", size=11, color=_TEXT2, wrap=True))
        self._disp_cont = QVBoxLayout()
        self._disp_cont.setSpacing(6)
        _dw = QWidget()
        _dw.setLayout(self._disp_cont)
        root.addWidget(_dw)
        # Passkeys / WebAuthn (Fase 5): segundo método MFA adicional a TOTP.
        root.addSpacing(8)
        root.addWidget(_lbl("Passkeys (WebAuthn)", size=14, color=_CIAN, bold=True))
        try:
            from src.services.seguridad import mfa_webauthn
            _wa_ok = mfa_webauthn.disponible()
            _wa_rec = mfa_webauthn.webauthn_recomendado((self._usuario or {}).get("perfil"))
        except Exception:
            _wa_ok, _wa_rec = False, False
        _nota = (("Recomendado para tu perfil. " if _wa_rec else "")
                 + ("Registra una passkey (huella/rostro/Windows Hello/llave FIDO2) desde el portal web; "
                    "aquí puedes ver y revocar las existentes." if _wa_ok else
                    "No disponible en este servidor (falta la librería WebAuthn). TOTP sigue activo."))
        root.addWidget(_lbl(_nota, size=11, color=(_VERDE if _wa_rec else _TEXT2), wrap=True))
        self._pk_cont = QVBoxLayout()
        self._pk_cont.setSpacing(6)
        _pw = QWidget()
        _pw.setLayout(self._pk_cont)
        root.addWidget(_pw)
        root.addStretch()
        self._refrescar()

    def _refrescar_passkeys(self):
        if not hasattr(self, "_pk_cont"):
            return
        while self._pk_cont.count():
            it = self._pk_cont.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        try:
            from src.services.seguridad import mfa_webauthn
            keys = mfa_webauthn.listar(self._uid()) if self._uid() else []
        except Exception:
            keys = []
        if not keys:
            self._pk_cont.addWidget(_lbl("No hay passkeys registradas.", size=11, color=_TEXT2))
            return
        for k in keys:
            fila = QHBoxLayout()
            fila.addWidget(_lbl(f"🔑  {k.get('nombre') or 'Passkey'}", size=12))
            fila.addStretch()
            b = _btn("Revocar", color=_ROJO, h=32)
            b.clicked.connect(lambda _=False, kid=k.get("id"): self._revocar_passkey(kid))
            fila.addWidget(b)
            w = QWidget()
            w.setLayout(fila)
            self._pk_cont.addWidget(w)

    def _revocar_passkey(self, kid):
        try:
            from src.services.seguridad import mfa_webauthn
            mfa_webauthn.revocar(kid, actor=(self._usuario or {}).get("nombre"))
        except Exception:
            pass
        self._refrescar_passkeys()

    def _uid(self):
        return (self._usuario or {}).get("id")

    def _refrescar_dispositivos(self):
        if not hasattr(self, "_disp_cont"):
            return
        while self._disp_cont.count():
            it = self._disp_cont.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        try:
            from src.services.seguridad import mfa_dispositivos
            devs = mfa_dispositivos.listar(id_usuario=self._uid()) if self._uid() else []
        except Exception:
            devs = []
        if not devs:
            self._disp_cont.addWidget(_lbl("No hay dispositivos de confianza.", size=11, color=_TEXT2))
            return
        for d in devs:
            fila = QHBoxLayout()
            nombre = d.get("nombre") or d.get("codigo_terminal") or "—"
            fila.addWidget(_lbl(f"🖥  {nombre}  ({d.get('codigo_terminal')})", size=12))
            fila.addStretch()
            b = _btn("Revocar", color=_ROJO, h=32)
            b.clicked.connect(lambda _=False, did=d.get("id"): self._revocar_dispositivo(did))
            fila.addWidget(b)
            w = QWidget()
            w.setLayout(fila)
            self._disp_cont.addWidget(w)

    def _revocar_dispositivo(self, did):
        try:
            from src.services.seguridad import mfa_dispositivos
            mfa_dispositivos.revocar(did, actor=(self._usuario or {}).get("nombre"))
        except Exception:
            pass
        self._refrescar_dispositivos()

    def _feedback(self, txt, color=_TEXT2):
        self.lbl_feedback.setStyleSheet(f"color:{color};font-family:'{_FONT}';font-size:12px;"
                                        f"background:transparent;border:none;")
        self.lbl_feedback.setText(txt)

    def _refrescar(self):
        if not self._uid():
            self.lbl_estado.setText("No hay usuario en sesión.")
            for b in (self.btn_activar, self.btn_regenerar, self.btn_desactivar):
                b.setVisible(False)
            return
        try:
            from src.services.seguridad import mfa
            activo = mfa.mfa_activo(self._uid())
        except Exception:
            activo = False
        if activo:
            self.lbl_estado.setText("Estado:  ✅ ACTIVO")
            self.lbl_estado.setStyleSheet(f"color:{_VERDE};font-family:'{_FONT}';font-size:14px;"
                                          f"font-weight:900;background:transparent;border:none;")
        else:
            self.lbl_estado.setText("Estado:  ⚠ INACTIVO")
            self.lbl_estado.setStyleSheet(f"color:{_TEXT2};font-family:'{_FONT}';font-size:14px;"
                                          f"font-weight:900;background:transparent;border:none;")
        self.btn_activar.setVisible(not activo)
        self.btn_regenerar.setVisible(activo)
        self.btn_desactivar.setVisible(activo)
        self._refrescar_dispositivos()
        self._refrescar_passkeys()

    def _configurar(self):
        dlg = MFAEnrolamientoDialog(self._usuario, parent=self)
        dlg.exec()
        if getattr(dlg, "activado", False):
            self._feedback("MFA activado correctamente.", _VERDE)
        self._refrescar()

    def _politica_obliga(self):
        try:
            from src.services.seguridad import mfa_politica
            return bool(mfa_politica.politica_efectiva(
                self._usuario, id_empresa=self._usuario.get("id_empresa")).get("obligatorio"))
        except Exception:
            return False

    def _desactivar(self):
        if self._politica_obliga():
            self._feedback("Tu empresa exige MFA para tu perfil; no puede desactivarse.", _ROJO)
            return
        # Acción de alto riesgo → STEP-UP oficial (MFA reciente). Mecanismo ÚNICO (no reauth ad-hoc).
        if not pedir_step_up(self._usuario, "mfa.desactivar", parent=self):
            return
        try:
            from src.services.seguridad import mfa, mfa_eventos
            if mfa.desactivar(self._uid()):
                mfa_eventos.emitir("MFA_DISABLED", id_usuario=self._uid(),
                                   actor=(self._usuario or {}).get("nombre"))
                self._feedback("MFA desactivado.", _TEXT2)
        except Exception as e:
            logger.debug("desactivar MFA: %s", e)
        self._refrescar()

    def _regenerar(self):
        # Acción de alto riesgo → STEP-UP (MFA reciente). Reutiliza el guard `pedir_step_up`.
        if not pedir_step_up(self._usuario, "mfa.recovery.regenerar", parent=self):
            return
        try:
            from src.services.seguridad import mfa
            codigos = mfa.generar_recovery_codes(self._uid())
        except Exception as e:
            logger.debug("regenerar recovery: %s", e)
            codigos = []
        d = QDialog(self)
        ly = _marco(d, 520)
        ly.addWidget(_RecoveryCodesView(codigos, on_finalizar=d.accept))
        d.exec()
        self._feedback("Se generaron nuevos códigos de recuperación (los anteriores dejan de ser "
                       "válidos).", _TEXT2)
