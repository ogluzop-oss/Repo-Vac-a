"""
`gui/gestion_usuarios.py::ConfiguracionWindow.ejecutar_creacion_usuario` — el email dejó de ser
opcional en el alta de empleados (pedido explícito del usuario: "no hace falta que lo especifiques
con ningún texto", es decir, basta con una validación genérica igual que el resto de campos
requeridos de este formulario — nombre/contraseña).

Desde la confirmación por email (código de 6 dígitos, `services.seguridad.
confirmacion_perfil_empleado`), el perfil YA NO se crea llamando a `crear_perfil` directamente desde
este método: primero se invoca `confirmacion_perfil_empleado.solicitar(...)` (que envía el código) y,
solo si acepta, se abre `_ConfirmarPerfilEmpleadoDialog` — es ese diálogo quien, al confirmarse el
código, termina llamando a `crear_perfil` (en otro módulo). Por eso los tests de aquí monkeypatchean
`solicitar`/`_ConfirmarPerfilEmpleadoDialog`, no `crear_perfil` (que ya no se invoca desde esta
función en absoluto).

Test ligero y aislado: en vez de instanciar `ConfiguracionWindow` completa (pesada: sesión BD,
decenas de sub-widgets), se llama al método SIN BINDING sobre un objeto mínimo que solo expone los
atributos que el método realmente lee (`input_nombre/input_pass/input_pass2/input_email/
combo_perfil`) — exactamente el mismo patrón de test unitario "duck-typed" ya usado para métodos de
validación de formularios en este proyecto.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit

from src.gui import gestion_usuarios as GU
from src.services.seguridad import confirmacion_perfil_empleado as CONF


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _ComboFalso:
    def currentText(self):
        return "OPERARIO"


class _DialogoConfirmacionFalso:
    """Sustituye a `_ConfirmarPerfilEmpleadoDialog`: simula que el código se confirmó bien
    (Accepted) sin abrir ninguna ventana real."""
    resultado = QDialog.DialogCode.Accepted

    def __init__(self, *a, **k):
        pass

    def exec(self):
        return self.resultado


def _formulario_falso(*, nombre="Empleado Test", pw="1234", pw2="1234", email=""):
    falso = type("FormularioFalso", (), {})()
    falso.input_nombre = QLineEdit(nombre)
    falso.input_pass = QLineEdit(pw)
    falso.input_pass2 = QLineEdit(pw2)
    falso.input_email = QLineEdit(email)
    falso.combo_perfil = _ComboFalso()
    return falso


def test_email_vacio_bloquea_el_alta(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(CONF, "solicitar",
                        lambda *a, **k: llamadas.append((a, k)) or {"ok": True})
    monkeypatch.setattr(GU, "mostrar_mensaje", lambda *a, **k: None)
    falso = _formulario_falso(email="")

    GU.ConfiguracionWindow.ejecutar_creacion_usuario(falso)

    assert llamadas == [], "con email vacío NO debe llegar a solicitar confirmación (ahora es obligatorio)"


def test_email_con_formato_invalido_bloquea_el_alta(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(CONF, "solicitar",
                        lambda *a, **k: llamadas.append((a, k)) or {"ok": True})
    monkeypatch.setattr(GU, "mostrar_mensaje", lambda *a, **k: None)
    falso = _formulario_falso(email="sin-arroba")

    GU.ConfiguracionWindow.ejecutar_creacion_usuario(falso)

    assert llamadas == []


def test_email_valido_solicita_codigo_y_el_alta_se_completa_al_confirmar(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(CONF, "solicitar",
                        lambda *a, **k: llamadas.append((a, k)) or
                        {"ok": True, "id_confirmacion": 42, "motivo": "Código enviado."})
    monkeypatch.setattr(GU, "mostrar_mensaje", lambda *a, **k: None)
    monkeypatch.setattr(GU, "_ConfirmarPerfilEmpleadoDialog", _DialogoConfirmacionFalso)
    falso = _formulario_falso(email="empleado@test.com")
    refrescos = []
    falso.refrescar_datos_usuarios = lambda: refrescos.append(1)

    GU.ConfiguracionWindow.ejecutar_creacion_usuario(falso)

    assert len(llamadas) == 1
    args, kwargs = llamadas[0]
    assert kwargs.get("email") == "empleado@test.com"
    assert refrescos == [1], "al confirmarse el código (Accepted) debe refrescar la tabla"


def test_email_valido_pero_envio_de_codigo_falla_no_crea_nada(app, monkeypatch):
    """Degradación honesta: si `solicitar` no pudo enviar el código (p. ej. sin buzón de correo
    activo), no debe abrirse el diálogo de confirmación ni refrescar la tabla."""
    monkeypatch.setattr(CONF, "solicitar",
                        lambda *a, **k: {"ok": False, "motivo": "Sin buzón activo."})
    mensajes = []
    monkeypatch.setattr(GU, "mostrar_mensaje", lambda *a, **k: mensajes.append(a))

    def _dialogo_no_debe_abrirse(*a, **k):
        raise AssertionError("no debe abrirse el diálogo de confirmación si solicitar() falló")
    monkeypatch.setattr(GU, "_ConfirmarPerfilEmpleadoDialog", _dialogo_no_debe_abrirse)

    falso = _formulario_falso(email="empleado@test.com")
    falso.refrescar_datos_usuarios = lambda: (_ for _ in ()).throw(
        AssertionError("no debe refrescar si no se creó el perfil"))

    GU.ConfiguracionWindow.ejecutar_creacion_usuario(falso)

    assert len(mensajes) == 1
