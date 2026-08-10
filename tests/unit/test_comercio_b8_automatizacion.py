"""
Tests PCD · Etapa B · Fase B8: Automatización comercial (cierre de la Etapa B).

Verifica que la automatización REUTILIZA lo construido: feed desde el Catálogo Comercial Global +
encolado al Sync Engine; republicación/SEO que la IA solo PROPONE (versión ia_propuesta, no publica);
campañas programables (Scheduler); análisis; y que no publica en canal directamente. Multiempresa.
"""

import inspect

import pytest

EMP = "T-AUT-A"
COD = "AUT1"


@pytest.fixture()
def pub(db):
    def _clean(cur):
        for t in ("cd_campanas", "cd_sync_outbox", "cd_catalogo_variantes"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "Reloj", "precio_escaparate": 200.0},
                                objetivo="vender", id_empresa=EMP)
    ppl.marcar_estado(pid, "PUBLICADA", id_empresa=EMP)
    yield pid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_generar_feed_desde_catalogo(pub):
    from src.services.comercio_digital import automatizacion as aut
    feed = aut.generar_feed(EMP, canal="google", pais="ES", moneda="EUR")
    assert feed and feed[0]["titulo"] == "Reloj" and feed[0]["precio"] > 200  # con IVA
    assert feed[0]["moneda"] == "EUR"


def test_publicar_feed_encola_en_sync(pub, db):
    from src.services.comercio_digital import automatizacion as aut
    r = aut.publicar_feed(EMP, canal="google", pais="ES", moneda="EUR")
    assert r["ok"] and r["encolados"] >= 1
    # Quedó encolado en el Outbox del Sync Engine (no publica directo).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cd_sync_outbox WHERE id_empresa=%s AND canal='google'", (EMP,))
        n = cur.fetchone()
        assert int(list(n.values())[0] if isinstance(n, dict) else n[0]) >= 1


def test_seo_ia_solo_propone(pub):
    from src.services.comercio_digital import automatizacion as aut, publicaciones as ppl
    r = aut.optimizar_seo(pub, id_empresa=EMP)
    assert r and r["version"] == 2                    # nueva versión
    v = ppl.obtener_version(pub, 2, id_empresa=EMP)
    assert v["origen"] == "ia_propuesta"              # la IA PROPONE, no publica
    assert ppl.obtener(pub, EMP)["estado"] == "PUBLICADA"   # el estado no lo fuerza la IA


def test_republicar_propone_y_encola(pub, db):
    from src.services.comercio_digital import automatizacion as aut
    r = aut.republicar(pub, canal="meta", id_empresa=EMP)
    assert r["ok"] and r["propuesta"]["version"] >= 2 and r["encolado"] is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cd_sync_outbox WHERE id_empresa=%s AND canal='meta'", (EMP,))
        n = cur.fetchone()
        assert int(list(n.values())[0] if isinstance(n, dict) else n[0]) >= 1


def test_campana_crear_ejecutar_programar(pub):
    from src.services.comercio_digital import automatizacion as aut
    cid = aut.crear_campana("Feed Google", tipo="feed", canal="google",
                            parametros={"pais": "ES", "moneda": "EUR"}, id_empresa=EMP)
    assert cid
    r = aut.ejecutar_campana(cid, id_empresa=EMP)
    assert r["ok"] and r["tipo"] == "feed"
    assert aut.programar(cid, id_empresa=EMP) in (True, False)   # Scheduler (capacidad, degradable)
    assert any(c["id"] == cid for c in aut.listar_campanas(EMP, estado="activa"))


def test_analisis_y_no_publica_directo():
    from src.services.comercio_digital import automatizacion as aut
    src = inspect.getsource(aut)
    # La automatización no fuerza la publicación (no llama a marcar_estado 'PUBLICADA').
    assert "marcar_estado" not in src
    # Reutiliza presencia (IA) + sync; no reimplementa IA ni pasarela de canal.
    assert "presencia" in src and "sync" in src
    d = aut.descriptor()
    assert d["ia_solo_propone"] is True and d["publica_directo"] is False and d["crea_motor_nuevo"] is False


def test_aislamiento_multiempresa(pub):
    from src.services.comercio_digital import automatizacion as aut
    aut.crear_campana("X", tipo="feed", canal="google", id_empresa=EMP)
    assert aut.listar_campanas(EMP)
    assert aut.listar_campanas("T-AUT-OTRA") == []
