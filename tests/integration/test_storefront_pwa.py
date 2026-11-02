"""
Generador de Apps Móviles (PWA) · Fase 1: manifest.webmanifest + Service Worker + branding
(color secundario) — reutiliza 100% `web_config`/`storefront.py`, sin motor ni tabla nuevos."""

import json

import pytest

pytestmark = pytest.mark.db


def test_manifest_pwa_sin_logo_no_inventa_iconos(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo", color="#FF0000")
    m = sf.manifest_pwa(fab.EMP_DEFECTO)
    assert m["name"] == "Tienda Demo"
    assert m["theme_color"] == "#FF0000"
    assert m["icons"] == []  # sin logo_url -> nunca se inventa un icono
    assert m["start_url"].startswith(f"/tienda/{fab.EMP_DEFECTO}")
    assert m["scope"] == f"/tienda/{fab.EMP_DEFECTO}/"
    assert m["display"] == "standalone"


def test_manifest_pwa_con_logo_y_color_secundario(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo", color="#00FFC6", color_secundario="#161B22",
            logo_url="https://ejemplo.test/logo.png")
    m = sf.manifest_pwa(fab.EMP_DEFECTO)
    assert m["background_color"] == "#161B22"
    assert m["theme_color"] == "#00FFC6"
    assert len(m["icons"]) == 2
    assert all(i["src"] == "https://ejemplo.test/logo.png" for i in m["icons"])


def test_manifest_pwa_sin_color_secundario_cae_al_primario(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo", color="#ABCDEF")
    m = sf.manifest_pwa(fab.EMP_DEFECTO)
    assert m["background_color"] == "#ABCDEF"


def test_service_worker_js_cachea_el_app_shell_de_esta_empresa(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo")
    js = sf.service_worker_js(fab.EMP_DEFECTO)
    assert f"/tienda/{fab.EMP_DEFECTO}" in js
    assert "manifest.webmanifest" in js
    assert "install" in js and "fetch" in js and "activate" in js


def test_service_worker_cachea_cualquier_ruta_de_la_tienda_no_solo_el_shell(db, fab):
    """El fetch handler intercepta CUALQUIER GET del mismo origen bajo /tienda/<eid>/ (no una
    lista cerrada) — por eso las páginas de fidelización (Fase 3: /cuenta, /cuenta/tickets,
    /cuenta/recogidas, la tarjeta QR) quedan cacheadas para offline en cuanto el cliente las
    visita una vez con red, sin tener que añadirlas una a una al app shell precacheado."""
    import json
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo")
    eid = fab.EMP_DEFECTO
    js = sf.service_worker_js(eid)
    assert f"indexOf({json.dumps(f'/tienda/{eid}')})" in js


def test_http_manifest_endpoint(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=1, nombre="Tienda Demo", color="#112233", logo_url="https://x.test/l.png")
    cli = crear_app().test_client()
    r = cli.get(f"/tienda/{fab.EMP_DEFECTO}/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/manifest+json")
    data = json.loads(r.data)
    assert data["name"] == "Tienda Demo"
    assert data["theme_color"] == "#112233"


def test_http_service_worker_endpoint(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=1, nombre="Tienda Demo")
    cli = crear_app().test_client()
    r = cli.get(f"/tienda/{fab.EMP_DEFECTO}/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["Content-Type"]
    assert r.headers["Service-Worker-Allowed"] == f"/tienda/{fab.EMP_DEFECTO}/"
    assert b"self.addEventListener" in r.data


def test_http_manifest_y_sw_404_si_tienda_inactiva(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=0)
    cli = crear_app().test_client()
    assert cli.get(f"/tienda/{fab.EMP_DEFECTO}/manifest.webmanifest").status_code == 404
    assert cli.get(f"/tienda/{fab.EMP_DEFECTO}/sw.js").status_code == 404


def test_pagina_home_incluye_las_etiquetas_pwa(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo", color="#00FFC6")
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "manifest.webmanifest" in html
    assert "serviceWorker" in html
    assert 'name="theme-color" content="#00FFC6"' in html


def test_web_tienda_color_secundario_roundtrip(db, fab):
    from src.db import web_tienda
    eid = fab.web(activa=1, color="#111111", color_secundario="#222222")
    cfg = web_tienda.obtener_config(eid)
    assert cfg["color"] == "#111111"
    assert cfg["color_secundario"] == "#222222"
