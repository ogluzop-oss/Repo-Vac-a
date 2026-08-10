"""
Tests · Fase WEB-14 — Adaptador Hostinger real (primera integración operativa).

Verifica: registro en el motor WEB-13 (sin tocarlo), degradabilidad HONESTA sin credenciales (nada de red),
flujo completo con transporte INYECTADO (autenticar→crear→esperar→dominio→registrar→conectar→sync), registro
§6, secretos vía SecretManager (nunca en claro), auditoría HOSTINGER_*, recuperación ante errores, y
multiempresa. Sin conexiones reales (transporte inyectado).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.hostinger import \
    transporte as T  # noqa: E402


class _FakeTransport:
    """Transporte inyectado (costura de test): respuestas tipo Hostinger, sin red."""

    def __init__(self, estado_web="READY", fallar=None):
        self.estado_web = estado_web
        self.fallar = fallar
        self.llamadas = []

    def request(self, method, path, *, token=None, json=None, params=None):
        self.llamadas.append((method, path, token))
        if self.fallar:
            raise self.fallar
        if path.endswith("/account"):
            return {"id": "acc", "email": "a@b.c"}
        if path.endswith("/websites/ai"):
            return {"id": "web1", "status": "CREATING"}
        if path.endswith("/websites/web1"):
            return {"status": self.estado_web}
        if path.endswith("/domain"):
            return {"domain": "miempresa.com", "url": "https://miempresa.com", "status": "LIVE"}
        return {}


def _con_credenciales(tok="tok-secreto"):
    os.environ["HOSTINGER_API_TOKEN"] = tok


def _sin_credenciales():
    os.environ.pop("HOSTINGER_API_TOKEN", None)


def teardown_function(_):
    T.reset_transporte()
    _sin_credenciales()


# ── 1 · Registrado en el motor sin modificarlo; contrato WEB-13 intacto ───────
def test_registrado_en_motor_web13_intacto():
    a = ic.motor.adaptador("hostinger")
    assert type(a).__name__ == "HostingerAdapter"
    assert a.plataforma == "hostinger"
    # Sin credenciales → NO disponible (honesto) y contrato WEB-13 preservado.
    _sin_credenciales()
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})           # método de contrato heredado (no se usa en el flujo real)


# ── 2 · Degradable sin credenciales: NO toca la red ───────────────────────────
def test_degradable_sin_credenciales():
    _sin_credenciales()
    ft = _FakeTransport()
    T.set_transporte(ft)
    a = ic.motor.adaptador("hostinger")
    assert a.autenticar()["codigo"] == "MISSING_CREDENTIALS"
    r = a.crear_y_conectar(id_empresa="E1", datos={"nombre_empresa": "X"})
    assert r["ok"] is False and r["error"]["codigo"] == "MISSING_CREDENTIALS"
    assert ft.llamadas == []      # nunca se llamó al transporte (sin credenciales)


# ── 3 · Flujo completo con transporte inyectado + secreto por SecretManager ───
def test_flujo_completo_inyectado():
    _con_credenciales()
    ft = _FakeTransport(estado_web="READY")
    T.set_transporte(ft)
    a = ic.motor.adaptador("hostinger")
    assert a.disponible() is True and a.descriptor()["estado"] == "OPERATIVO"
    pasos = []
    r = a.crear_y_conectar(id_empresa="E-HOST", datos={
        "nombre_empresa": "Mi Empresa", "actividad": "retail", "pais": "ES",
        "idioma": "es", "correo": "x@y.z"}, on_progreso=pasos.append, timeout=3, intervalo=0)
    assert r["ok"] is True and r["dominio"] == "miempresa.com"
    # UX §11 (mensajes que ve el usuario).
    assert pasos == ["Crear página web", "Hostinger", "Esperando creación...",
                     "Página web creada correctamente", "Conectando Smart Manager...",
                     "Sincronizando datos...", "Proceso finalizado"]
    # Registro §6 con estados EXISTENTES.
    reg = r["conexion"]["registro"]
    assert reg["proveedor"] == "hostinger" and reg["dominio"] == "miempresa.com"
    assert reg["id_externo"] == "web1" and reg["estado"] == ic.estados.SINCRONIZADA
    assert reg["ultima_sync"] is not None and reg["canal_web"] is True
    # El token viajó (desde SecretManager), nunca aparece en el registro.
    assert "tok-secreto" not in str(reg)
    assert any(tok == "tok-secreto" for _m, _p, tok in ft.llamadas)


# ── 4 · Recuperación ante errores (transporte que falla → error canónico) ─────
def test_recuperacion_errores():
    _con_credenciales()
    from src.services.marketplace.integraciones_comerciales.motor.errores import (
        CodigoError, IntegracionError)
    T.set_transporte(_FakeTransport(fallar=IntegracionError(CodigoError.NETWORK_ERROR, "sin red",
                                                            plataforma="hostinger")))
    a = ic.motor.adaptador("hostinger")
    r = a.crear_y_conectar(id_empresa="E1", datos={"nombre_empresa": "X"})
    assert r["ok"] is False and r["error"]["codigo"] in ("NETWORK_ERROR", "AUTH_ERROR", "API_ERROR")


# ── 5 · Multiempresa: aislamiento de dos creaciones ───────────────────────────
def test_multiempresa():
    _con_credenciales()
    T.set_transporte(_FakeTransport())
    a = ic.motor.adaptador("hostinger")
    r1 = a.crear_y_conectar(id_empresa="EMP_A", datos={"nombre_empresa": "A"}, timeout=2, intervalo=0)
    r2 = a.crear_y_conectar(id_empresa="EMP_B", datos={"nombre_empresa": "B"}, timeout=2, intervalo=0)
    assert r1["ok"] and r2["ok"]
    assert r1["conexion"]["registro"]["empresa"] == "EMP_A"
    assert r2["conexion"]["registro"]["empresa"] == "EMP_B"


# ── 6 · Auditoría HOSTINGER_* + secretos (SecretManager, no en claro) ─────────
def test_auditoria_y_secretos():
    from src.services.marketplace.integraciones_comerciales.hostinger import (
        auditoria, secretos)
    assert auditoria.EVENTOS == ("HOSTINGER_AUTH", "HOSTINGER_CREATE", "HOSTINGER_COMPLETE",
                                 "HOSTINGER_CONNECTED", "HOSTINGER_REGISTERED", "HOSTINGER_SYNC",
                                 "HOSTINGER_ERROR")
    # Los secretos se resuelven por el SecretManager existente (no hay tokens en el código).
    _con_credenciales("abc123")
    assert secretos.token() == "abc123"
    _sin_credenciales()
    assert secretos.token() is None
    import inspect
    src = inspect.getsource(secretos)
    assert "secret_manager" in src and "HOSTINGER_API_TOKEN" in src
