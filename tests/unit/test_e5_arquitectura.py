"""
Tests Etapa E · Fase E5: documentación de arquitectura (ADR + diagramas).

Solo verifica CONSISTENCIA documental (no toca código): que el índice de ADR referencia ficheros que
existen y viceversa, que cada ADR tiene los apartados obligatorios, que el documento de diagramas
contiene las 10 vistas requeridas en Mermaid, y que los enlaces relativos del índice resuelven.
"""

import pathlib
import re

ARQ = pathlib.Path(__file__).resolve().parents[2] / "docs" / "architecture"
ADR = ARQ / "adr"


def test_estructura_basica_existe():
    for f in (ARQ / "README.md", ADR / "README.md", ADR / "template.md", ARQ / "diagrams.md"):
        assert f.exists() and f.stat().st_size > 0, f"falta: {f}"


def _adrs():
    return sorted(p for p in ADR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_indice_adr_coincide_con_ficheros():
    indice = (ADR / "README.md").read_text(encoding="utf-8")
    referenciados = set(re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", indice))
    ficheros = {p.name for p in _adrs()}
    assert referenciados == ficheros, (
        f"desalineado: solo en índice={referenciados - ficheros}, "
        f"solo en disco={ficheros - referenciados}")
    assert len(ficheros) >= 13


def test_numeracion_adr_sin_huecos_ni_duplicados():
    nums = [int(p.name[:4]) for p in _adrs()]
    assert nums == list(range(1, len(nums) + 1)), f"numeración con huecos/duplicados: {nums}"


def test_cada_adr_tiene_apartados_obligatorios():
    for p in _adrs():
        txt = p.read_text(encoding="utf-8")
        assert txt.lstrip().startswith("# ADR-"), f"{p.name}: título ADR ausente"
        assert "**Estado**" in txt, f"{p.name}: sin Estado"
        assert "## Contexto" in txt and "## Decisión" in txt and "## Consecuencias" in txt, \
            f"{p.name}: faltan apartados obligatorios"


def test_diagramas_incluye_las_10_vistas_mermaid():
    txt = (ARQ / "diagrams.md").read_text(encoding="utf-8")
    bloques = txt.count("```mermaid")
    assert bloques >= 10, f"solo {bloques} diagramas Mermaid (se esperan 10)"
    requeridas = ["Contexto", "Contenedores", "Componentes", "Dependencias", "Flujo",
                  "Integraciones", "Eventos", "Marketplace", "SDK", "API"]
    for vista in requeridas:
        assert vista in txt, f"falta la vista: {vista}"


def test_enlaces_relativos_del_indice_general_resuelven():
    readme = (ARQ / "README.md").read_text(encoding="utf-8")
    for destino in re.findall(r"\]\((adr/|diagrams\.md)\)", readme):
        ruta = ARQ / destino.rstrip("/")
        assert ruta.exists(), f"enlace roto en README: {destino}"
