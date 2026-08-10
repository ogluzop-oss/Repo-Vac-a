"""
Tests Etapa E · Fase E1: convención uniforme de paginación/orden/filtrado de la Enterprise REST API.

Verifica que la convención es ADITIVA y RETROCOMPATIBLE: sin los parámetros nuevos la respuesta es
IDÉNTICA (lista simple); con ellos se devuelve el sobre estándar {data,total,limit,offset,page,
page_size,sort,order,next_cursor}. El helper es puro (opera sobre la lista que el router ya obtiene);
no toca servicios ni BD. `limite` (legacy) NO activa el sobre; `limit` (nuevo) sí.
"""

from src.api import paginacion


def _datos(n=10):
    return [{"id": i, "nombre": f"item-{i:02d}", "canal": ("email" if i % 2 else "sms")}
            for i in range(n)]


def test_retrocompatible_sin_params():
    # Sin parámetros nuevos → envolver devuelve la MISMA lista (contrato intacto).
    items = _datos(5)
    p = paginacion.parametros({})
    assert p["activo"] is False
    assert paginacion.envolver(items, p) is items


def test_limite_legacy_no_activa_sobre():
    # `limite` (castellano, legacy) NO debe activar la convención.
    p = paginacion.parametros({"limite": "25", "q": "x"})
    assert p["activo"] is False
    items = _datos(3)
    assert paginacion.envolver(items, p) == items


def test_limit_activa_sobre_estandar():
    p = paginacion.parametros({"limit": "2"})
    assert p["activo"] is True
    sobre = paginacion.envolver(_datos(5), p)
    assert isinstance(sobre, dict)
    for k in ("data", "total", "count", "limit", "offset", "page", "page_size", "sort", "order",
              "next_cursor"):
        assert k in sobre
    assert sobre["total"] == 5 and sobre["count"] == 2 and len(sobre["data"]) == 2
    assert sobre["next_cursor"]                       # hay más → cursor presente


def test_offset_y_cursor():
    p1 = paginacion.parametros({"limit": "2", "offset": "0"})
    s1 = paginacion.envolver(_datos(5), p1)
    assert [d["id"] for d in s1["data"]] == [0, 1]
    # Seguir por el cursor devuelto.
    p2 = paginacion.parametros({"limit": "2", "cursor": s1["next_cursor"]})
    s2 = paginacion.envolver(_datos(5), p2)
    assert [d["id"] for d in s2["data"]] == [2, 3]
    # Última página: sin next_cursor.
    p3 = paginacion.parametros({"limit": "2", "offset": "4"})
    s3 = paginacion.envolver(_datos(5), p3)
    assert [d["id"] for d in s3["data"]] == [4] and s3["next_cursor"] is None


def test_page_y_page_size():
    p = paginacion.parametros({"page": "2", "page_size": "3"})
    assert p["offset"] == 3 and p["limit"] == 3
    s = paginacion.envolver(_datos(10), p)
    assert [d["id"] for d in s["data"]] == [3, 4, 5] and s["page"] == 2 and s["page_size"] == 3


def test_sort_order():
    p = paginacion.parametros({"sort": "id", "order": "desc"})
    s = paginacion.envolver(_datos(4), p)
    assert [d["id"] for d in s["data"]] == [3, 2, 1, 0]


def test_filters_json_y_corchetes():
    # Filtro por JSON.
    p = paginacion.parametros({"filters": '{"canal":"sms"}'})
    s = paginacion.envolver(_datos(10), p)
    assert all(d["canal"] == "sms" for d in s["data"]) and s["total"] == 5
    # Filtro por par filter[campo]=valor.
    p2 = paginacion.parametros({"filter[canal]": "email"})
    s2 = paginacion.envolver(_datos(10), p2)
    assert all(d["canal"] == "email" for d in s2["data"]) and s2["total"] == 5


def test_limit_saturado_a_maximo():
    p = paginacion.parametros({"limit": "99999"})
    assert p["limit"] == paginacion._LIMIT_MAX


def test_openapi_parametros_completo():
    nombres = {q["name"] for q in paginacion.openapi_parametros()}
    assert {"limit", "offset", "cursor", "page", "page_size", "sort", "order", "filters"} <= nombres
    assert all(q["in"] == "query" and q["required"] is False for q in paginacion.openapi_parametros())


def test_aplicar_no_muta_entrada():
    items = _datos(5)
    copia = list(items)
    p = paginacion.parametros({"sort": "id", "order": "desc", "limit": "2"})
    paginacion.aplicar(items, p)
    assert items == copia                              # la lista original no se altera
