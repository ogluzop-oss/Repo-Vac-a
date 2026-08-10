"""
Tests PCD · Fase 8 (RFC-CD-003/004): Digital Presence Generator.

Verifica: la IA SOLO PROPONE (no publica, no ejecuta negocio); la propuesta se almacena como versión
PPL `origen='ia_propuesta'`; el estado de la publicación NO cambia (lo gobierna Workflow); IA
Provider-Agnostic (solo capabilities.ia, sin proveedor concreto) y degradable/determinista; sin
mover stock ni sincronizar. Aislamiento multiempresa.
"""

import inspect

import pytest

EMP = "T-PRES-A"
COD = "PRES1"


@pytest.fixture()
def pub(db):
    """Crea una publicación base (v1) para EMP y limpia al terminar."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "Té Verde 100g"}, objetivo="vender",
                                id_empresa=EMP)
    yield pid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()


def test_propone_version_ia_sin_publicar(pub):
    from src.services.comercio_digital import presencia, publicaciones as ppl
    r = presencia.proponer(pub, id_empresa=EMP)
    assert r and r["publicado"] is False and r["version"] == 2
    v2 = ppl.obtener_version(pub, 2, id_empresa=EMP)
    assert v2["origen"] == "ia_propuesta"                      # IA solo PROPONE (versión, no publica)
    # La publicación NO se publica: su estado sigue gobernado por Workflow (BORRADOR).
    assert ppl.obtener(pub, EMP)["estado"] == "BORRADOR"


def test_propuesta_contiene_contenido_y_seo(pub):
    from src.services.comercio_digital import presencia, publicaciones as ppl
    r = presencia.proponer(pub, tipos=("descripcion", "seo"), id_empresa=EMP)
    v = ppl.obtener_version(pub, r["version"], id_empresa=EMP)
    assert v["contenido"]["nombre"] == "Té Verde 100g"        # conserva la base
    assert v["contenido"]["descripcion"]                       # propuesta de descripción
    assert v["seo"]["slug"] == "te-verde-100g"                 # slug SEO propuesto (determinista)


def test_provider_agnostic_y_degradable(pub):
    from src.services.comercio_digital import presencia
    # Sin proveedor de IA en el entorno → degrada a heurístico DETERMINISTA (misma propuesta).
    r1 = presencia.proponer(pub, id_empresa=EMP)
    r2 = presencia.proponer(pub, id_empresa=EMP)
    assert r1["motor"] == "heuristico" and r1["provider_agnostic"] is True
    assert r1["propuesta"] == r2["propuesta"]                  # determinista
    # No acopla a ningún proveedor concreto; usa la capacidad de IA.
    src = inspect.getsource(presencia)
    for prov in ("openai", "anthropic", "import gpt", "gemini", "from src.services.agents_platform"):
        assert prov not in src
    assert "capabilities" in src and "cap.ia()" in src


def test_solo_propone_no_ejecuta_negocio():
    """La presencia no mueve stock/reservas ni sincroniza ni publica en canal; no cambia estados."""
    from src.services.comercio_digital import presencia
    src = inspect.getsource(presencia)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for p in ("availability", "fulfillment", "reservas", "transacciones",
              "comercio_digital.canales", "comercio_digital.sync"):
        assert not any(p in l for l in imports), f"presencia acopla a {p}"
    # No publica ni fuerza estados (eso es de Workflow): no llama a marcar_estado.
    assert "marcar_estado" not in src
    d = presencia.descriptor()
    assert d["solo_propone"] and d["publica"] is False and d["ejecuta_negocio"] is False
    assert d["gobernado_por"] == "workflow" and d["origen_version"] == "ia_propuesta"


def test_aislamiento_multiempresa(pub):
    from src.services.comercio_digital import presencia
    assert presencia.proponer(pub, id_empresa="T-PRES-OTRA") is None   # otra empresa no ve la pub
    assert presencia.proponer(pub, id_empresa=EMP) is not None
