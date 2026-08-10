"""
Tests PCD · Etapa B · Fase B4: Gestión Comercial.

Verifica que la cotización comercial REUTILIZA los motores existentes (db.promociones, db.fidelizacion)
y añade listas de precios + cross/up-selling: precio de lista sobre el base, mejor promoción por línea,
cupón sobre el total, cupón inválido, up-sell desde variantes, y que NO se crea un motor de promociones
paralelo. Multiempresa.
"""

import inspect

import pytest

EMP = "T-COM-A"


@pytest.fixture()
def limpio(db):
    def _clean(cur):
        for t in ("cd_precios_lista", "cupones", "promociones"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_lista_de_precios(limpio):
    from src.services.comercio_digital import comercial as com
    assert com.fijar_precio("mayorista", "P1", 80.0, moneda="EUR", id_empresa=EMP)
    assert com.precio_de_lista("P1", lista="mayorista", moneda="EUR", id_empresa=EMP) == 80.0
    assert com.precio_de_lista("P1", lista="inexistente", id_empresa=EMP) is None    # → base
    # La cotización usa el precio de lista si existe.
    q = com.cotizar([{"codigo": "P1", "cantidad": 1, "precio_unitario": 100.0}], lista="mayorista",
                    id_empresa=EMP)
    assert q["lineas"][0]["precio_unitario"] == 80.0 and q["subtotal"] == 80.0


def test_reutiliza_promociones(limpio):
    from src.db import promociones as promo
    from src.services.comercio_digital import comercial as com
    promo.crear_promocion("10% P2", tipo="descuento_pct", valor=10, ambito="articulo",
                          reglas=[{"clave": "codigo", "valor": "P2"}], id_empresa=EMP)
    q = com.cotizar([{"codigo": "P2", "cantidad": 1, "precio_unitario": 100.0}], id_empresa=EMP)
    assert q["descuento_promociones"] == 10.0 and q["total"] == 90.0
    assert q["lineas"][0]["tipo_promo"] == "descuento_pct"


def test_reutiliza_cupones(limpio):
    from src.db import fidelizacion as fid
    from src.services.comercio_digital import comercial as com
    fid.emitir_cupon("CUP5", tipo="descuento_pct", valor=5, id_empresa=EMP)
    q = com.cotizar([{"codigo": "P3", "cantidad": 1, "precio_unitario": 100.0}], cupon="CUP5",
                    id_empresa=EMP)
    assert q["cupon"]["valido"] is True and q["descuento_cupon"] == 5.0 and q["total"] == 95.0
    # Cupón inexistente → inválido, sin descuento.
    q2 = com.cotizar([{"codigo": "P3", "cantidad": 1, "precio_unitario": 100.0}], cupon="NOEXISTE",
                     id_empresa=EMP)
    assert q2["cupon"]["valido"] is False and q2["descuento_cupon"] == 0.0


def test_promocion_y_cupon_combinados(limpio):
    from src.db import fidelizacion as fid
    from src.db import promociones as promo
    from src.services.comercio_digital import comercial as com
    promo.crear_promocion("10% P4", tipo="descuento_pct", valor=10, ambito="articulo",
                          reglas=[{"clave": "codigo", "valor": "P4"}], id_empresa=EMP)
    fid.emitir_cupon("CUP10", tipo="importe_fijo", valor=10, id_empresa=EMP)
    q = com.cotizar([{"codigo": "P4", "cantidad": 1, "precio_unitario": 100.0}], cupon="CUP10",
                    id_empresa=EMP)
    # 100 - 10 (promo) = 90; cupón fijo 10 → 80.
    assert q["descuento_promociones"] == 10.0 and q["descuento_cupon"] == 10.0 and q["total"] == 80.0


def test_up_selling_desde_variantes(db):
    from src.services.comercio_digital import catalogo, comercial as com, publicaciones as ppl
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_empresa=%s", ("T-COM-UP",))
        cur.execute("DELETE FROM cd_publicaciones WHERE id_empresa=%s", ("T-COM-UP",))
        conn.commit()
    pid = ppl.crear_publicacion("UP", contenido={"nombre": "x"}, id_empresa="T-COM-UP")
    catalogo.agregar_variante(pid, "BASIC", precio_delta=0, id_empresa="T-COM-UP")
    catalogo.agregar_variante(pid, "PRO", precio_delta=30, id_empresa="T-COM-UP")
    up = com.sugerencias(pid, tipo="up", id_empresa="T-COM-UP")
    assert up and up[0]["sku"] == "PRO"        # up-sell = variante de mayor precio
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, p FROM cd_publicaciones p LEFT JOIN cd_catalogo_variantes v "
                    "ON v.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", ("T-COM-UP",))
        conn.commit()


def test_no_motor_paralelo(limpio):
    from src.services.comercio_digital import comercial as com
    src = inspect.getsource(com)
    # Reutiliza los motores existentes; NO redefine el cálculo de promociones/cupones.
    assert "db import promociones" in src and "db import fidelizacion" in src
    for redef in ("def evaluar_articulo", "def crear_promocion", "def validar_cupon"):
        assert redef not in src           # no reimplementa el motor, solo lo invoca
    d = com.descriptor()
    assert d["motor_promociones_nuevo"] is False
    assert set(d["reutiliza"]) >= {"db.promociones", "db.fidelizacion"}


def test_aislamiento_multiempresa(limpio):
    from src.services.comercio_digital import comercial as com
    com.fijar_precio("pvp", "Z", 50.0, id_empresa=EMP)
    assert com.precio_de_lista("Z", lista="pvp", id_empresa=EMP) == 50.0
    assert com.precio_de_lista("Z", lista="pvp", id_empresa="T-COM-OTRA") is None
