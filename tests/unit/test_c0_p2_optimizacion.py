"""
Tests Etapa C0 · Prioridad 2: optimización N+1 (Checkout + Catálogo Comercial Global).

Verifica que las optimizaciones NO cambian el resultado funcional: `variantes_batch` equivale a
llamar `variantes` por publicación; `ficha_comercial` con valores precomputados da el MISMO resultado;
`catalogo` compone igual; y el checkout memoiza el Plan de Cumplimiento por línea (evita recomputar
para códigos repetidos) sin alterar el resultado.
"""

import pytest

EMP = "T-OPT-A"


@pytest.fixture()
def dos_pubs(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()
    from src.services.comercio_digital import catalogo, publicaciones as ppl
    pids = []
    for n, precio in (("A", 100.0), ("B", 50.0)):
        pid = ppl.crear_publicacion(n, contenido={"nombre": n, "precio_escaparate": precio},
                                    id_empresa=EMP)
        ppl.marcar_estado(pid, "PUBLICADA", id_empresa=EMP)
        catalogo.agregar_variante(pid, f"{n}-L", precio_delta=10, id_empresa=EMP)
        pids.append(pid)
    yield pids
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()


def test_variantes_batch_equivale(dos_pubs):
    from src.services.comercio_digital import catalogo
    vmap = catalogo.variantes_batch(dos_pubs, id_empresa=EMP)
    for pid in dos_pubs:
        assert vmap[pid] == catalogo.variantes(pid, id_empresa=EMP)   # mismo resultado que N consultas


def test_ficha_precomputada_identica(dos_pubs):
    from src.services.comercio_digital import catalogo
    pid = dos_pubs[0]
    normal = catalogo.ficha_comercial(pid, pais="ES", moneda="EUR", id_empresa=EMP)
    iva = catalogo._iva_pct("ES", EMP)
    vs = catalogo.variantes(pid, id_empresa=EMP)
    optimizada = catalogo.ficha_comercial(pid, pais="ES", moneda="EUR", id_empresa=EMP,
                                          iva_pct=iva, variantes_pre=vs)
    assert normal == optimizada                                       # resultado idéntico


def test_catalogo_compone_igual(dos_pubs):
    from src.services.comercio_digital import catalogo
    fichas = catalogo.catalogo(EMP, pais="ES", moneda="EUR")
    assert len(fichas) == 2
    por_id = {f["id_publicacion"]: f for f in fichas}
    for pid in dos_pubs:
        assert por_id[pid] == catalogo.ficha_comercial(pid, pais="ES", moneda="EUR", id_empresa=EMP)
    # Precio con IVA e variante correctos.
    fa = por_id[dos_pubs[0]]
    assert fa["precio"]["neto"] == 100.0 and fa["variantes"][0]["precio"]["neto"] == 110.0


def test_checkout_memoiza_resolver(db, monkeypatch):
    from src.services.comercio_digital import checkout, inventario
    COD = "OPT1"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_reservas", "transaccion_lineas", "transaccion_comercial", "transaccion_eventos",
                  "transaccion_decisiones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_central) "
                    "VALUES (%s,%s,'Opt',10,50)", (COD, EMP))
        conn.commit()
    llamadas = {"n": 0}
    orig = inventario.resolver

    def _contando(*a, **k):
        llamadas["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(inventario, "resolver", _contando)
    # Dos líneas del MISMO código+cantidad → el memo llama a resolver UNA sola vez.
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": COD, "cantidad": 1, "precio_unitario": 10.0},
                                   {"codigo": COD, "cantidad": 1, "precio_unitario": 10.0}])
    assert r["ok"] and llamadas["n"] == 1                              # memoizado (antes serían 2)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_reservas", "transaccion_lineas", "transaccion_comercial", "transaccion_eventos",
                  "transaccion_decisiones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()
