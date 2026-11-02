"""
Carteles/Folletos publicitarios (4ª pestaña de Proyectos) — CRUD (`services.proyectos.carteles`),
catálogo de formatos, miniatura/exportación (delega en `render_cartel`, verificado por separado en
`test_render_cartel.py`) y borrador asistido por IA (reutiliza el cliente Anthropic de SOMA).

Rama funcional INDEPENDIENTE del tablero Kanban (corrección de diseño, feedback directo del
usuario): un diseño NO requiere ningún proyecto — `id_proyecto` es opcional (None por defecto,
migración 0303) y se conserva solo por si alguien quiere asociarlo manualmente.
"""

import os

import pytest

from src.services.proyectos import carteles as C
from src.services.proyectos import proyectos as P

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _proyecto(fab, emp, **kw):
    pid = P.crear_proyecto(kw.pop("nombre", "Proyecto Carteles Test"), id_empresa=emp, **kw)
    fab._borrar("proyectos", "id", pid)
    return pid


@pytest.fixture(autouse=True)
def _limpia_carteles(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT thumbnail_path FROM proyecto_carteles WHERE id_empresa=%s", (emp,))
        rutas = [r[0] if not isinstance(r, dict) else r["thumbnail_path"] for r in cur.fetchall()]
        cur.execute("DELETE FROM proyecto_carteles WHERE id_empresa=%s", (emp,))
        conn.commit()
    for r in rutas:
        if r and os.path.exists(r):
            try:
                os.remove(r)
            except OSError:
                pass


def test_crear_cartel_no_requiere_proyecto(emp):
    cid = C.crear_cartel("Oferta de verano", formato="cartel_a3", orientacion="vertical",
                         id_empresa=emp)
    assert cid
    c = C.obtener_cartel(cid, id_empresa=emp)
    assert c["id_proyecto"] is None
    assert c["tipo"] == "cartel"
    assert float(c["ancho_mm"]) == 297 and float(c["alto_mm"]) == 420
    assert c["contenido"]["elementos"] == []


def test_crear_cartel_puede_asociarse_a_un_proyecto_si_se_pide_explicitamente(fab, emp):
    pid = _proyecto(fab, emp)
    cid = C.crear_cartel("Asociado", formato="cartel_a3", id_proyecto=pid, id_empresa=emp)
    assert C.obtener_cartel(cid, id_empresa=emp)["id_proyecto"] == pid


def test_crear_cartel_orientacion_horizontal_intercambia_dimensiones(emp):
    cid = C.crear_cartel("Banner horizontal", formato="folleto_a5", orientacion="horizontal",
                         id_empresa=emp)
    c = C.obtener_cartel(cid, id_empresa=emp)
    assert float(c["ancho_mm"]) == 210 and float(c["alto_mm"]) == 148  # A5: 148x210 -> intercambiado


def test_crear_cartel_personalizado_respeta_dimensiones_dadas(emp):
    cid = C.crear_cartel("Tamaño libre", formato="personalizado", ancho_mm=123, alto_mm=456,
                         id_empresa=emp)
    c = C.obtener_cartel(cid, id_empresa=emp)
    assert float(c["ancho_mm"]) == 123 and float(c["alto_mm"]) == 456


def test_diptico_y_triptico_guardan_el_modo_de_plegado(emp):
    d = C.crear_cartel("Díptico", formato="folleto_a4_diptico", id_empresa=emp)
    t = C.crear_cartel("Tríptico", formato="folleto_a4_triptico", id_empresa=emp)
    assert C.obtener_cartel(d, id_empresa=emp)["modo"] == "diptico"
    assert C.obtener_cartel(t, id_empresa=emp)["modo"] == "triptico"


def test_listar_carteles_sin_filtro_de_proyecto_devuelve_todos(fab, emp):
    pid = _proyecto(fab, emp)
    C.crear_cartel("Independiente", formato="cartel_a3", id_empresa=emp)
    C.crear_cartel("Asociado a un proyecto", formato="cartel_a3", id_proyecto=pid, id_empresa=emp)
    assert len(C.listar_carteles(id_empresa=emp)) == 2


def test_listar_carteles_filtra_por_texto_y_tipo(emp):
    C.crear_cartel("Cartel de rebajas", formato="cartel_a3", id_empresa=emp)
    C.crear_cartel("Folleto de menú", formato="folleto_a5", id_empresa=emp)
    assert len(C.listar_carteles(id_empresa=emp)) == 2
    assert len(C.listar_carteles(id_empresa=emp, texto="rebajas")) == 1
    assert len(C.listar_carteles(id_empresa=emp, tipo="folleto")) == 1


def test_listar_carteles_filtra_explicitamente_por_proyecto_o_independientes(fab, emp):
    pid = _proyecto(fab, emp)
    C.crear_cartel("Independiente", formato="cartel_a3", id_empresa=emp)
    C.crear_cartel("Asociado", formato="cartel_a3", id_proyecto=pid, id_empresa=emp)
    assert len(C.listar_carteles(id_empresa=emp, id_proyecto=None)) == 1
    assert len(C.listar_carteles(id_empresa=emp, id_proyecto=pid)) == 1


def test_actualizar_cartel_contenido_y_titulo(emp):
    cid = C.crear_cartel("Original", formato="cartel_a3", id_empresa=emp)
    nuevo_contenido = {"ancho_mm": 297, "alto_mm": 420, "modo": None, "fondo_color": "#FFFFFF",
                      "elementos": [{"tipo": "texto", "x": 1, "y": 1, "w": 10, "h": 10,
                                    "texto": "Hola", "fuente": "regular", "tamano_pt": 12,
                                    "color": "#000000", "alineacion": "izquierda",
                                    "interlineado": 1.2, "z": 0}]}
    assert C.actualizar_cartel(cid, id_empresa=emp, titulo="Renombrado", contenido=nuevo_contenido)
    c = C.obtener_cartel(cid, id_empresa=emp)
    assert c["titulo"] == "Renombrado"
    assert len(c["contenido"]["elementos"]) == 1


def test_duplicar_cartel_copia_contenido_y_dimensiones(emp):
    cid = C.crear_cartel("Base", formato="cartel_a2", id_empresa=emp)
    contenido = {"ancho_mm": 420, "alto_mm": 594, "modo": None, "fondo_color": "#FFFFFF",
                "elementos": [{"tipo": "forma", "forma": "circulo", "x": 1, "y": 1, "w": 5, "h": 5,
                              "color": "#00FFC6", "relleno": True, "grosor_mm": 0, "z": 0}]}
    C.actualizar_cartel(cid, id_empresa=emp, contenido=contenido)
    cid2 = C.duplicar_cartel(cid, id_empresa=emp)
    assert cid2 and cid2 != cid
    c2 = C.obtener_cartel(cid2, id_empresa=emp)
    assert c2["titulo"] == "Base (copia)"
    assert c2["contenido"]["elementos"] == contenido["elementos"]


def test_eliminar_cartel(emp):
    cid = C.crear_cartel("A borrar", formato="cartel_a3", id_empresa=emp)
    assert C.eliminar_cartel(cid, id_empresa=emp)
    assert C.obtener_cartel(cid, id_empresa=emp) is None


def test_aislamiento_multiempresa(fab, emp):
    cid = C.crear_cartel("Propio", formato="cartel_a3", id_empresa=emp)
    otra = fab.empresa("OTRA EMPRESA CARTELES")
    assert C.obtener_cartel(cid, id_empresa=otra) is None
    assert C.listar_carteles(id_empresa=otra) == []


def test_generar_miniatura_crea_png_y_guarda_la_ruta(emp):
    cid = C.crear_cartel("Con miniatura", formato="cartel_a3", id_empresa=emp)
    ruta = C.generar_miniatura(cid, id_empresa=emp)
    assert ruta and os.path.exists(ruta)
    assert C.obtener_cartel(cid, id_empresa=emp)["thumbnail_path"] == ruta
    with open(ruta, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_exportar_pdf_y_png(emp, tmp_path):
    cid = C.crear_cartel("Exportable", formato="folleto_a5", id_empresa=emp)
    ok_pdf, ruta_pdf = C.exportar_pdf(cid, str(tmp_path / "x.pdf"), id_empresa=emp)
    assert ok_pdf and os.path.exists(ruta_pdf)
    ok_png, ruta_png = C.exportar_imagen(cid, str(tmp_path / "x.png"), formato="PNG", id_empresa=emp)
    assert ok_png and os.path.exists(ruta_png)


def test_exportar_cartel_inexistente_falla_honesto(emp, tmp_path):
    ok, motivo = C.exportar_pdf(999999999, str(tmp_path / "x.pdf"), id_empresa=emp)
    assert ok is False and motivo == "cartel_no_encontrado"


def test_generar_copy_ia_sin_api_key_degrada_honesto(emp, monkeypatch):
    monkeypatch.setattr("src.services.copilot.motor_llm._cliente", lambda: None)
    r = C.generar_copy_ia("Cartel A3 para menú del día", tipo="cartel", id_empresa=emp)
    assert r == {"ok": False, "motivo": "sin_api_key"}


def test_generar_copy_ia_sin_contexto_degrada_honesto(emp, monkeypatch):
    monkeypatch.setattr("src.services.copilot.motor_llm._cliente", lambda: object())
    assert C.generar_copy_ia("", tipo="cartel", id_empresa=emp)["motivo"] == "sin_contexto"
    assert C.generar_copy_ia("algo", tipo="cartel", id_empresa=None)["motivo"] == "sin_contexto"


def test_generar_copy_ia_exito_con_json_limpio(emp, monkeypatch):
    class _Bloque:
        type = "text"
        text = ('{"titulo":"20% en menú del día","subtitulo":"Solo los martes",'
               '"cuerpo":"Disfruta de nuestra cocina italiana con un descuento especial.",'
               '"cta":"¡Reserva ya!"}')

    class _Resp:
        content = [_Bloque()]

    monkeypatch.setattr("src.services.copilot.motor_llm._cliente",
                        lambda: type("C", (), {"messages": type("M", (), {
                            "create": staticmethod(lambda **kw: _Resp())})()})())
    monkeypatch.setattr("src.services.ia_control_uso.ejecutar_tarea_ia",
                        lambda eid, uid, tarea, fn: fn())
    r = C.generar_copy_ia("Menú del día italiano, 20% martes", tipo="cartel", id_empresa=emp)
    assert r["ok"] is True
    assert r["titulo"] == "20% en menú del día"
    assert r["cta"] == "¡Reserva ya!"


def test_generar_copy_ia_json_envuelto_en_markdown_se_extrae(emp, monkeypatch):
    class _Bloque:
        type = "text"
        text = ('Aquí tienes tu borrador:\n```json\n{"titulo":"T","subtitulo":"S",'
               '"cuerpo":"C","cta":"CTA"}\n```')

    class _Resp:
        content = [_Bloque()]

    monkeypatch.setattr("src.services.copilot.motor_llm._cliente",
                        lambda: type("C", (), {"messages": type("M", (), {
                            "create": staticmethod(lambda **kw: _Resp())})()})())
    monkeypatch.setattr("src.services.ia_control_uso.ejecutar_tarea_ia",
                        lambda eid, uid, tarea, fn: fn())
    r = C.generar_copy_ia("algo", tipo="cartel", id_empresa=emp)
    assert r["ok"] is True and r["titulo"] == "T"


def test_generar_copy_ia_respuesta_no_json_degrada_honesto(emp, monkeypatch):
    class _Bloque:
        type = "text"
        text = "Lo siento, no puedo generar eso."

    class _Resp:
        content = [_Bloque()]

    monkeypatch.setattr("src.services.copilot.motor_llm._cliente",
                        lambda: type("C", (), {"messages": type("M", (), {
                            "create": staticmethod(lambda **kw: _Resp())})()})())
    monkeypatch.setattr("src.services.ia_control_uso.ejecutar_tarea_ia",
                        lambda eid, uid, tarea, fn: fn())
    r = C.generar_copy_ia("algo", tipo="cartel", id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == "respuesta_invalida"


def test_generar_copy_ia_limite_excedido_degrada_honesto(emp, monkeypatch):
    from src.services.ia_control_uso import LimiteUsoIAExcedido

    def _raise(*a, **k):
        raise LimiteUsoIAExcedido("límite")

    monkeypatch.setattr("src.services.copilot.motor_llm._cliente", lambda: object())
    monkeypatch.setattr("src.services.ia_control_uso.ejecutar_tarea_ia", _raise)
    r = C.generar_copy_ia("algo", tipo="cartel", id_empresa=emp)
    assert r == {"ok": False, "motivo": "limite_ia"}


def test_construir_layout_desde_copy_distribuye_elementos():
    copy = {"titulo": "T", "subtitulo": "S", "cuerpo": "C", "cta": "Comprar"}
    doc = C.construir_layout_desde_copy(copy, 210, 297)
    assert doc["ancho_mm"] == 210 and doc["alto_mm"] == 297
    tipos = [e["tipo"] for e in doc["elementos"]]
    assert tipos.count("texto") == 4          # título, subtítulo, cuerpo, texto del CTA
    # El bloque CTA añade una forma (franja) + un texto encima, no un tipo "cta" propio.
    assert tipos.count("forma") == 1
    from src.services.proyectos import render_cartel as R
    png = R.render_png(doc, dpi=72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_construir_layout_sin_cta_no_anade_forma():
    doc = C.construir_layout_desde_copy({"titulo": "T"}, 210, 297)
    assert all(e["tipo"] != "forma" for e in doc["elementos"])
