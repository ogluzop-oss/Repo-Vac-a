"""
Tests PCD · Fase 3 (RFC-CD-005): Availability Engine.

Garantías verificadas: 100 % LECTURA (no reservas, no decide origen, no conoce Fulfillment);
reutiliza el inventario existente; fachada compatible con consultar_disponibilidad/localizar_articulo
(delegación byte-idéntica, firmas intactas); ATP + buckets + ETA DETERMINISTAS y reconstruibles;
aislamiento multiempresa.
"""

import inspect

import pytest

EMP = "T-AV-A"
EMP_B = "T-AV-B"


@pytest.fixture
def arts(db):
    # `articulos.codigo` es PK GLOBAL (no por empresa): se usan códigos distintos por empresa.
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE codigo IN ('AVX','AVXB')")
            conn.commit()
    _b()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo, nombre, precio, Stock_tienda, Stock_central, "
                    "id_empresa) VALUES ('AVX','Artículo AV',9.5,5,3,%s)", (EMP,))
        cur.execute("INSERT INTO articulos (codigo, nombre, precio, Stock_tienda, Stock_central, "
                    "id_empresa) VALUES ('AVXB','Secreto B',1,99,99,%s)", (EMP_B,))
        conn.commit()
    yield
    _b()


def test_consultar_disponibilidad_forma_legacy(arts):
    from src.services.comercio_digital.inventario import availability as av
    d = av.consultar_disponibilidad("AVX", id_empresa=EMP)
    assert set(d) >= {"codigo", "nombre", "precio", "tienda", "central", "otras_tiendas", "online"}
    assert d["tienda"] == 5 and d["central"] == 3 and d["nombre"] == "Artículo AV"


def test_localizar_articulo_derivados(arts):
    from src.services.comercio_digital.inventario import availability as av
    d = av.localizar_articulo("AVX", id_empresa=EMP)
    assert d["disponible_tienda"] is True and d["sugerencia"] == "tienda"


def test_atp_buckets_eta_determinista(arts):
    from src.services.comercio_digital.inventario import availability as av
    r1 = av.disponibilidad("AVX", cantidad=4, id_empresa=EMP)
    r2 = av.disponibilidad("AVX", cantidad=4, id_empresa=EMP)
    assert r1 == r2                                   # determinista/reconstruible
    b = {x["bucket"]: x for x in r1["buckets"]}
    assert b["tienda_activa"]["disponible"] == 5 and b["tienda_activa"]["eta_dias"] == 0
    assert b["central"]["disponible"] == 3
    assert r1["disponible_total"] == 8 and r1["cubre_solicitud"] is True
    # ATP = on_hand − reservado − safety (0/0 en Fase 3).
    assert r1["reservado"] == 0 and r1["safety"] == 0


def test_availability_es_solo_lectura():
    from src.services.comercio_digital.inventario import availability as av
    d = av.descriptor()
    assert d["solo_lectura"] and not d["crea_reservas"] and not d["decide_origen"]
    assert not d["conoce_fulfillment"]
    src = inspect.getsource(av)
    # No IMPORTA a Fulfillment (independencia de motores, CD-005).
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    assert not any("fulfillment" in l for l in imports)
    # No ESCRIBE (motor 100 % de lectura): sin sentencias de escritura.
    codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for escritura in ("INSERT ", "UPDATE ", "DELETE ", "transaccion("):
        assert escritura not in codigo, f"Availability escribe: {escritura}"


def test_delegacion_byte_identica(arts):
    """online_orders_service.consultar_disponibilidad DELEGA en Availability y da el MISMO resultado."""
    from src.db.empresa import set_empresa_actual, set_tienda_actual
    set_empresa_actual(EMP); set_tienda_actual(None)
    from src.services.tpv import online_orders_service as OS
    from src.services.comercio_digital.inventario import availability as av
    assert OS.consultar_disponibilidad("AVX") == av.consultar_disponibilidad("AVX", id_empresa=EMP)
    assert OS.localizar_articulo("AVX") == av.localizar_articulo("AVX", id_empresa=EMP)


def test_aislamiento_multiempresa(arts):
    from src.services.comercio_digital.inventario import availability as av
    # Cada empresa ve SU artículo; el de otra empresa no es visible (aislamiento estricto).
    assert av.consultar_disponibilidad("AVX", id_empresa=EMP)["tienda"] == 5
    assert av.consultar_disponibilidad("AVX", id_empresa=EMP_B)["tienda"] == 0   # no visible
    assert av.consultar_disponibilidad("AVXB", id_empresa=EMP_B)["tienda"] == 99
    assert av.consultar_disponibilidad("AVXB", id_empresa=EMP)["tienda"] == 0    # no visible
