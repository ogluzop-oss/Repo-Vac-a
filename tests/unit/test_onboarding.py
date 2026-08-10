"""R1 · services/onboarding: estado del asistente (completado) + MODO PYME SIMPLE + esenciales.

Aísla la persistencia en un fichero temporal (monkeypatch de RUTA_CONFIG) para no tocar el
`config_onboarding.json` real del repo.
"""

import pytest

from src.services import onboarding as O


@pytest.fixture
def onb(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RUTA_CONFIG", str(tmp_path / "config_onboarding.json"))
    return O


def test_defaults(onb):
    assert onb.completado() is False
    assert onb.modo_simple() is False


def test_marcar_completado(onb):
    assert onb.marcar_completado() is True
    assert onb.completado() is True
    onb.marcar_completado(False)
    assert onb.completado() is False


def test_modo_simple_persistente(onb):
    assert onb.fijar_modo_simple(True) is True
    assert onb.modo_simple() is True
    onb.fijar_modo_simple(False)
    assert onb.modo_simple() is False


def test_flags_independientes(onb):
    # Cambiar un flag no debe pisar el otro.
    onb.fijar_modo_simple(True)
    onb.marcar_completado(True)
    assert onb.modo_simple() is True and onb.completado() is True


def test_esencial_solo_los_del_dia_a_dia(onb):
    for v in ("tpv", "contabilidad", "clientes_crm", "tesoreria", "gestion_caja",
              "info", "stock", "compras", "configuracion", "logout"):
        assert onb.esencial(v), f"{v} debería ser esencial"
    for v in ("bi", "camaras", "gmao", "calidad", "marketplace", "seguridad", "saas",
              "rrhh", "workflow", "almacenes", "proyectos", "obrador"):
        assert not onb.esencial(v), f"{v} NO debería ser esencial"
    assert onb.esencial(None) is False


def test_datos_empresa_incompletos(onb, monkeypatch):
    import src.db.empresa as EMP
    monkeypatch.setattr(EMP, "info_documento", lambda *a, **k: {"nombre": "SMART MANAGER", "cif": ""})
    assert onb.datos_empresa_incompletos() is True          # nombre por defecto + sin CIF
    monkeypatch.setattr(EMP, "info_documento", lambda *a, **k: {"nombre": "Kik SL", "cif": "B123"})
    assert onb.datos_empresa_incompletos() is False         # datos ya cumplimentados
