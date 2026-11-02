"""
Renderizador headless de carteles/folletos (`services.proyectos.render_cartel`) — sin BD, sin Qt:
lee el modelo de contenido del lienzo y produce PNG (Pillow) / PDF (reportlab) deterministas.
"""

import os

import pytest

from src.services.proyectos import render_cartel as R

pytestmark = pytest.mark.unit


def _doc(**kw):
    base = {"ancho_mm": 210, "alto_mm": 297, "modo": None, "fondo_color": "#FFFFFF", "elementos": []}
    base.update(kw)
    return base


def test_render_png_devuelve_png_valido_del_tamano_correcto():
    doc = _doc()
    png = R.render_png(doc, dpi=72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(png))
    # 210mm a 72dpi ~= 595px, 297mm ~= 842px (tolerancia de redondeo).
    assert abs(img.width - 595) <= 2
    assert abs(img.height - 842) <= 2


def test_render_png_dibuja_texto_imagen_qr_y_formas_sin_lanzar(tmp_path):
    logo = tmp_path / "logo.png"
    from PIL import Image
    Image.new("RGB", (40, 40), "red").save(logo)
    doc = _doc(elementos=[
        {"tipo": "texto", "x": 10, "y": 10, "w": 190, "h": 40,
         "texto": "Menú del día italiano " * 5, "fuente": "negrita", "tamano_pt": 24,
         "color": "#111111", "alineacion": "centro", "interlineado": 1.2, "z": 0},
        {"tipo": "imagen", "x": 10, "y": 60, "w": 30, "h": 30, "ruta": str(logo), "z": 1},
        {"tipo": "qr", "x": 150, "y": 250, "w": 30, "h": 30, "payload": "https://x.test/promo", "z": 2},
        {"tipo": "forma", "forma": "rectangulo", "x": 20, "y": 100, "w": 100, "h": 50,
         "color": "#00FFC6", "relleno": False, "grosor_mm": 1, "z": 3},
        {"tipo": "forma", "forma": "circulo", "x": 20, "y": 160, "w": 50, "h": 50,
         "color": "#F85149", "relleno": True, "grosor_mm": 0.5, "z": 4},
        {"tipo": "forma", "forma": "linea", "x": 20, "y": 220, "w": 150, "h": 0,
         "color": "#000000", "grosor_mm": 1, "z": 5},
    ])
    png = R.render_png(doc, dpi=72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_png_omite_elemento_con_imagen_inexistente_sin_lanzar():
    doc = _doc(elementos=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                          "ruta": "/no/existe/nunca.png", "z": 0}])
    png = R.render_png(doc, dpi=72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_pdf_sin_sangrado_tamano_exacto(tmp_path):
    doc = _doc(ancho_mm=100, alto_mm=150)
    ruta = str(tmp_path / "sin_sangrado.pdf")
    assert R.render_pdf(doc, ruta, sangrado_mm=0, marcas_corte=False) is True
    assert os.path.exists(ruta)
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    from reportlab.lib.units import mm
    page = PdfReader(ruta).pages[0]
    assert abs(float(page.mediabox.width) / mm - 100) < 0.1
    assert abs(float(page.mediabox.height) / mm - 150) < 0.1


def test_render_pdf_con_sangrado_amplia_la_pagina(tmp_path):
    doc = _doc(ancho_mm=100, alto_mm=150)
    ruta = str(tmp_path / "con_sangrado.pdf")
    assert R.render_pdf(doc, ruta, sangrado_mm=3, marcas_corte=True) is True
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    from reportlab.lib.units import mm
    page = PdfReader(ruta).pages[0]
    assert abs(float(page.mediabox.width) / mm - 106) < 0.1
    assert abs(float(page.mediabox.height) / mm - 156) < 0.1


def test_render_pdf_dimensiones_invalidas_falla_honesto(tmp_path):
    doc = _doc(ancho_mm=0, alto_mm=0)
    assert R.render_pdf(doc, str(tmp_path / "x.pdf"), sangrado_mm=3) is False


def test_render_pdf_con_elementos_completos_no_lanza(tmp_path):
    doc = _doc(modo="diptico", elementos=[
        {"tipo": "texto", "x": 10, "y": 10, "w": 190, "h": 40, "texto": "Título impactante",
         "fuente": "negrita", "tamano_pt": 28, "color": "#111111", "alineacion": "centro",
         "interlineado": 1.2, "z": 0},
        {"tipo": "qr", "x": 150, "y": 250, "w": 30, "h": 30, "payload": "https://x.test", "z": 1},
        {"tipo": "forma", "forma": "rectangulo", "x": 20, "y": 60, "w": 170, "h": 100,
         "color": "#00FFC6", "relleno": True, "grosor_mm": 0, "z": 2},
    ])
    ruta = str(tmp_path / "completo.pdf")
    assert R.render_pdf(doc, ruta, sangrado_mm=3, marcas_corte=True) is True
    assert os.path.getsize(ruta) > 0


def test_render_pdf_sin_reportlab_degrada(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "reportlab.pdfgen":
            raise ImportError("sin reportlab")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert R.render_pdf(_doc(), "/tmp/no_debe_crearse.pdf") is False
