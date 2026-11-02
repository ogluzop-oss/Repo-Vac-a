"""
`src.services.catalogo.ia_contenido` — asistente IA de contenido de ficha de producto (Fase 1,
e-commerce PIM). Reutiliza el cliente Anthropic degradable y el modelo de
`services.copilot.motor_llm`, y el único punto de ejecución medida `ia_control_uso.
ejecutar_tarea_ia` — este test NO reimplementa esas piezas, las monkeypatchea para probar
ÚNICAMENTE la lógica propia de este módulo (construcción del prompt, tono, límites, degradación
honesta)."""

import pytest

from src.services.catalogo import ia_contenido as ic
from src.services.ia_control_uso import LimiteUsoIAExcedido


class _BloqueTexto:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _RespuestaFalsa:
    def __init__(self, texto):
        self.content = [_BloqueTexto(texto)]


def test_campo_invalido_degrada_sin_llamar_a_nada(monkeypatch):
    llamado = []
    monkeypatch.setattr(ic, "_cliente", lambda: llamado.append(1) or object())
    r = ic.generar_texto("no_existe", "Camiseta", usuario={"id": 1}, id_empresa="emp1")
    assert r == {"ok": False, "motivo": "campo_invalido"}
    assert not llamado, "no debe ni intentar crear el cliente para un campo inválido"


def test_sin_api_key_degrada_honestamente(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: None)
    r = ic.generar_texto("descripcion", "Camiseta", usuario={"id": 1}, id_empresa="emp1")
    assert r == {"ok": False, "motivo": "sin_api_key"}


def test_sin_producto_o_sin_empresa_degrada(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: object())
    assert ic.generar_texto("descripcion", "", usuario={"id": 1}, id_empresa="emp1")["motivo"] == "sin_contexto"
    assert ic.generar_texto("descripcion", "Camiseta", usuario={"id": 1}, id_empresa=None)["motivo"] == "sin_contexto"


def test_exito_devuelve_texto_y_respeta_el_limite(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: object())

    capturado = {}

    def _falso_ejecutar_tarea_ia(id_empresa, id_usuario, feature_name, fn_llamada):
        capturado["id_empresa"] = id_empresa
        capturado["id_usuario"] = id_usuario
        capturado["feature_name"] = feature_name
        return _RespuestaFalsa("x" * 9999)   # deliberadamente más largo que cualquier límite

    monkeypatch.setattr(ic, "ejecutar_tarea_ia", _falso_ejecutar_tarea_ia)

    r = ic.generar_texto("seo_descripcion", "Camiseta", {"Color": "Rojo"}, "elegante",
                         usuario={"id": 42}, id_empresa="emp1")
    assert r["ok"] is True
    assert len(r["texto"]) == 155   # límite de seo_descripcion respetado
    assert capturado == {"id_empresa": "emp1", "id_usuario": 42, "feature_name": "catalogo_ia_contenido"}


def test_prompt_incluye_tono_y_atributos(monkeypatch):
    prompts = []

    class _ClienteEspia:
        class messages:
            @staticmethod
            def create(model, max_tokens, messages):
                prompts.append(messages[0]["content"])
                return _RespuestaFalsa("ok")

    monkeypatch.setattr(ic, "_cliente", lambda: _ClienteEspia())
    monkeypatch.setattr(ic, "ejecutar_tarea_ia",
                        lambda id_empresa, id_usuario, feature_name, fn_llamada: fn_llamada())

    ic.generar_texto("descripcion", "Camiseta", {"Talla": "M", "Color": "Azul"}, "tecnico",
                     usuario={"id": 1}, id_empresa="emp1")
    assert len(prompts) == 1
    assert "preciso" in prompts[0] or "especificaciones" in prompts[0]
    assert "Talla: M" in prompts[0] and "Color: Azul" in prompts[0]
    assert "Camiseta" in prompts[0]


def test_limite_de_uso_ia_degrada_sin_lanzar(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: object())

    def _lanza(*a, **k):
        raise LimiteUsoIAExcedido("tope diario alcanzado")

    monkeypatch.setattr(ic, "ejecutar_tarea_ia", _lanza)
    r = ic.generar_texto("descripcion", "Camiseta", usuario={"id": 1}, id_empresa="emp1")
    assert r == {"ok": False, "motivo": "limite_ia"}


def test_respuesta_vacia_degrada(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: object())
    monkeypatch.setattr(ic, "ejecutar_tarea_ia",
                        lambda *a, **k: _RespuestaFalsa("   "))
    r = ic.generar_texto("descripcion", "Camiseta", usuario={"id": 1}, id_empresa="emp1")
    assert r == {"ok": False, "motivo": "respuesta_vacia"}


def test_error_inesperado_degrada_sin_propagar(monkeypatch):
    monkeypatch.setattr(ic, "_cliente", lambda: object())

    def _rompe(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ic, "ejecutar_tarea_ia", _rompe)
    r = ic.generar_texto("descripcion", "Camiseta", usuario={"id": 1}, id_empresa="emp1")
    assert r == {"ok": False, "motivo": "error_inesperado"}
