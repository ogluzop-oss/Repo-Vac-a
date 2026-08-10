"""
Tests PCD · Fase 7 (RFC-CD-001/002/004): Product Publication Layer.

Verifica: representación comercial reutilizable e independiente del canal; "la publicación no es el
producto" (no modifica el ERP); versionado INMUTABLE + recuperable + rollback no destructivo; objetivo
y estado (estados gobernados por Workflow, sin motor paralelo); media SOLO por referencia; SEO e i18n
(multi-idioma sin duplicar); publicación preparada para adaptadores; restricciones (no IA/canal/stock).
"""

import inspect

import pytest

EMP = "T-PUB-A"
COD = "PUB1"


@pytest.fixture()
def art(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda, "
                    "Stock_central) VALUES (%s,%s,'Producto Publicable',12.5,3,7)", (COD, EMP))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


def test_crear_y_semilla_no_modifica_producto(art, db):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, tipo="producto", objetivo="vender", id_empresa=EMP,
                                sembrar=True, actor="u1")
    assert pid
    v1 = ppl.obtener_version(pid, id_empresa=EMP)
    assert v1["version"] == 1 and v1["estado"] == "BORRADOR"
    assert v1["contenido"]["nombre"] == "Producto Publicable"        # semilla read-only
    assert v1["contenido"]["precio_escaparate"] == 12.5
    # El producto ERP NO se ha modificado.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, precio, Stock_central FROM articulos WHERE codigo=%s AND "
                    "id_empresa=%s", (COD, EMP))
        r = cur.fetchone()
        vals = list(r.values()) if isinstance(r, dict) else list(r)
    assert vals[0] == "Producto Publicable" and float(vals[1]) == 12.5 and int(vals[2]) == 7


def test_versionado_inmutable_y_recuperable(art):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "v1"}, id_empresa=EMP)
    v2 = ppl.nueva_version(pid, contenido={"nombre": "v2"}, id_empresa=EMP)
    v3 = ppl.nueva_version(pid, contenido={"nombre": "v3"}, id_empresa=EMP)
    assert (v2, v3) == (2, 3)
    # Todas las versiones siguen recuperables (inmutables).
    assert ppl.obtener_version(pid, 1, id_empresa=EMP)["contenido"]["nombre"] == "v1"
    assert ppl.obtener_version(pid, 2, id_empresa=EMP)["contenido"]["nombre"] == "v2"
    assert len(ppl.versiones(pid, id_empresa=EMP)) == 3
    assert ppl.obtener(pid, EMP)["version_actual"] == 3


def test_rollback_no_destructivo(art):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "v1"}, id_empresa=EMP)
    ppl.nueva_version(pid, contenido={"nombre": "v2"}, id_empresa=EMP)
    v3 = ppl.rollback(pid, 1, id_empresa=EMP)         # vuelve a v1 → crea v3
    assert v3 == 3
    assert ppl.obtener_version(pid, 3, id_empresa=EMP)["contenido"]["nombre"] == "v1"
    # v2 sigue existiendo (no se destruyó nada).
    assert ppl.obtener_version(pid, 2, id_empresa=EMP)["contenido"]["nombre"] == "v2"


def test_estado_sin_motor_paralelo(art):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, id_empresa=EMP)
    assert ppl.marcar_estado(pid, "VALIDADA", id_empresa=EMP)
    assert ppl.marcar_estado(pid, "PUBLICADA", id_empresa=EMP)
    assert ppl.obtener(pid, EMP)["estado"] == "PUBLICADA"
    assert ppl.marcar_estado(pid, "ESTADO_INVENTADO", id_empresa=EMP) is False   # vocab controlado
    # No hay matriz de transición rígida (Workflow gobierna): el código no define TRANSICIONES.
    assert "TRANSICIONES" not in inspect.getsource(ppl)


def test_media_solo_referencias(art):
    from src.services.comercio_digital import publicaciones as ppl
    m = [ppl.media_ref("imagen", documento_id="doc-1"),
         ppl.media_ref("video", backend="cdn", url="https://cdn/x.mp4")]
    pid = ppl.crear_publicacion(COD, media=m, id_empresa=EMP)
    v = ppl.obtener_version(pid, id_empresa=EMP)
    assert v["media"][0]["documento_id"] == "doc-1" and v["media"][1]["backend"] == "cdn"
    # La PPL nunca almacena ficheros: no abre/escribe archivos.
    src = inspect.getsource(ppl)
    assert "open(" not in src and ".write(" not in src


def test_i18n_sin_duplicar_y_preparar_para_canal(art):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "Aceite", "desc": "ES"},
                                seo={"titulo": "Aceite"}, id_empresa=EMP)
    ppl.set_i18n(pid, "en", {"contenido": {"nombre": "Oil", "desc": "EN"}}, id_empresa=EMP)
    # Misma publicación (no se duplica) con contenido localizado.
    base = ppl.preparar_para_canal(pid, id_empresa=EMP)
    ingles = ppl.preparar_para_canal(pid, idioma="en", id_empresa=EMP)
    assert base["contenido"]["nombre"] == "Aceite"
    assert ingles["contenido"]["nombre"] == "Oil"                 # overlay i18n
    assert base["id_publicacion"] == ingles["id_publicacion"]     # no duplica la publicación


def test_ppl_no_ia_no_canal_no_dominio():
    """Restricciones: la PPL no usa IA, no publica en canales, no llama sync/adaptadores ni mueve stock."""
    from src.services.comercio_digital import publicaciones as ppl
    src = inspect.getsource(ppl) + inspect.getsource(ppl.modelo)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for p in ("agents_platform", "availability", "fulfillment", "reservas", "transacciones",
              "from src.services.comercio_digital.canales", "from src.services.comercio_digital.sync"):
        assert not any(p in l for l in imports), f"PPL acopla a {p}"
    # No modifica el producto ERP (solo lo lee para la semilla).
    codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for w in ("UPDATE articulos", "INSERT INTO articulos", "DELETE FROM articulos"):
        assert w not in codigo
    d = ppl.descriptor()
    assert d["genera_ia"] is False and d["publica_en_canal"] is False
    assert d["mueve_stock"] is False and d["modifica_producto"] is False and d["estados_por"] == "workflow"


def test_aislamiento_multiempresa(art):
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "x"}, id_empresa=EMP)
    assert ppl.obtener(pid, "T-PUB-OTRA") is None        # otra empresa no la ve
    assert ppl.obtener(pid, EMP) is not None
