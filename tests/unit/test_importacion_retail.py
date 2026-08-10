"""
Fase 3: formatos semánticos de retail (BMEcat XML, EDIFACT PRICAT) → columnas canónicas casi automáticas, y
Parquet DEGRADABLE (sin motor → error honesto). Los lectores stdlib se cargan de verdad en los motores oficiales.
"""

import pytest

from src.services import importacion as I
from src.services.importacion import lectores

_BMECAT = """<?xml version="1.0" encoding="UTF-8"?>
<BMECAT version="2005">
 <T_NEW_CATALOG>
  <ARTICLE>
   <SUPPLIER_AID>RET-1</SUPPLIER_AID>
   <ARTICLE_DETAILS>
     <DESCRIPTION_SHORT>Cola 1L</DESCRIPTION_SHORT>
     <DESCRIPTION_LONG>Refresco de cola 1 litro</DESCRIPTION_LONG>
     <EAN>8412345000013</EAN>
   </ARTICLE_DETAILS>
   <ARTICLE_PRICE_DETAILS>
     <ARTICLE_PRICE price_type="net_list"><PRICE_AMOUNT>1.50</PRICE_AMOUNT></ARTICLE_PRICE>
   </ARTICLE_PRICE_DETAILS>
   <ARTICLE_REFERENCE><REFERENCE_FEATURE_GROUP_NAME>Bebidas</REFERENCE_FEATURE_GROUP_NAME></ARTICLE_REFERENCE>
  </ARTICLE>
 </T_NEW_CATALOG>
</BMECAT>"""

_PRICAT = ("UNA:+.? '"
           "UNB+UNOC:3+SENDER+RECIPIENT+240101:1200+1'"
           "UNH+1+PRICAT:D:96A:UN'"
           "BGM+9+DOC1+9'"
           "LIN+1++8412345000020:EN'"
           "IMD+F++:::Agua Mineral 1L'"
           "PRI+AAA:0.90'"
           "QTY+21:250'"
           "LIN+2++RET-3:SA'"
           "IMD+F++:::Zumo Naranja'"
           "PRI+AAA:1.20'"
           "UNT+10+1'UNZ+1+1'")


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(fab):
    for cod in ("RET-1", "RET-3", "8412345000020"):
        fab._borrar("articulos", "codigo", cod)
        fab._borrar("stock_tienda", "codigo_articulo", cod)
        fab._borrar("movimientos_stock", "codigo_articulo", cod)
    fab.al_limpiar(lambda: fab._borrar("familias_producto", "nombre", "Bebidas"))


def _art(db, codigo):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT nombre, precio, Stock_total, id_familia FROM articulos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        return None if not r else dict(zip(["nombre", "precio", "stock", "id_familia"], r))


def test_bmecat_columnas_canonicas(tmp_path):
    ruta = tmp_path / "cat.xml"
    ruta.write_text(_BMECAT, encoding="utf-8")
    assert lectores.detectar_formato(str(ruta)) == "xml"
    plan = I.analizar(str(ruta))
    assert plan["ok"] and plan["mapeo_sugerido"]["codigo"] == "codigo"    # ya viene canónico
    filas, _ = lectores.leer(str(ruta))
    assert filas[0]["codigo"] == "RET-1" and filas[0]["familia"] == "Bebidas"


def test_bmecat_se_carga(emp, db, tmp_path):
    ruta = tmp_path / "cat.xml"
    ruta.write_text(_BMECAT, encoding="utf-8")
    res = I.ejecutar(str(ruta), id_empresa=emp)
    assert res["ok"] and res["cargados"] == 1
    a = _art(db, "RET-1")
    assert a["nombre"] == "Cola 1L" and float(a["precio"]) == 1.50 and a["id_familia"] is not None


def test_edifact_pricat_parsea_y_carga(emp, db, tmp_path):
    ruta = tmp_path / "precios.edi"
    ruta.write_text(_PRICAT, encoding="utf-8")
    assert lectores.detectar_formato(str(ruta)) == "edifact"
    filas, _ = lectores.leer(str(ruta))
    assert [f["codigo"] for f in filas] == ["8412345000020", "RET-3"]
    assert filas[0]["nombre"] == "Agua Mineral 1L" and filas[0]["stock"] == "250"
    res = I.ejecutar(str(ruta), id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2
    assert _art(db, "8412345000020")["stock"] == 250 and float(_art(db, "RET-3")["precio"]) == 1.20


def test_parquet_degradable_sin_motor(tmp_path):
    ruta = tmp_path / "x.parquet"
    ruta.write_bytes(b"esto no es parquet")
    assert lectores.detectar_formato(str(ruta)) == "parquet"
    plan = I.analizar(str(ruta))                       # sin pyarrow (o fichero inválido) → error honesto
    assert plan["ok"] is False and "parquet" in plan["error"].lower()
