"""
Centralización de importaciones (limpieza de duplicidades): el histórico de ventas de
`gui/ventas.py` ("HISTÓRICO IMPORTADO") ahora se lee de `ventas_historicas` —la MISMA tabla que
alimenta el módulo centralizado "Migrar datos" (entidad VENTAS_HIST)— en vez de la antigua
`prevision_historico` (subida directa, sin aislamiento por empresa, ahora retirada). Mismas
firmas/formas de retorno que antes: los llamantes de `gui/ventas.py` no necesitan cambios, solo
ven los datos importados desde el wizard centralizado."""

import pytest

pytestmark = pytest.mark.db

EMP = "T-VENTAS-ANALITICA-CENTR"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_historicas WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def _sembrar(vh):
    vh.registrar_venta_historica("2024-01-10", "ART1", cantidad=5, importe=100.0, id_empresa=EMP)
    vh.registrar_venta_historica("2024-01-10", "ART2", cantidad=2, importe=50.0, id_empresa=EMP)
    vh.registrar_venta_historica("2024-01-11", "ART1", cantidad=3, importe=60.0, id_empresa=EMP)
    vh.registrar_venta_historica("2023-12-25", "ART1", cantidad=1, importe=20.0, id_empresa=EMP)


def test_resumen_historico_agrega_por_anio_desde_ventas_historicas(limpia):
    from src.db import ventas_analitica as va
    from src.db import ventas_historicas as vh
    _sembrar(vh)
    filas = {anio: (dias, float(total), fuente) for anio, dias, total, fuente in va.resumen_historico(EMP)}
    assert filas[2024] == (2, 210.0, "IMPORTADO")
    assert filas[2023] == (1, 20.0, "IMPORTADO")


def test_contar_historico_cuenta_filas_de_la_empresa(limpia):
    from src.db import ventas_analitica as va
    from src.db import ventas_historicas as vh
    _sembrar(vh)
    assert va.contar_historico(EMP) == 4


def test_serie_historico_agrupa_por_fecha_sumando_articulos(limpia):
    from src.db import ventas_analitica as va
    from src.db import ventas_historicas as vh
    _sembrar(vh)
    serie = {str(fecha): float(total) for fecha, total in va.serie_historico(EMP)}
    assert serie["2024-01-10"] == 150.0   # ART1 (100) + ART2 (50), mismo día
    assert serie["2024-01-11"] == 60.0


def test_serie_historico_agrupada_es_equivalente_a_serie_historico(limpia):
    from src.db import ventas_analitica as va
    from src.db import ventas_historicas as vh
    _sembrar(vh)
    assert va.serie_historico_agrupada(EMP) == va.serie_historico(EMP)


def test_aisla_por_empresa(limpia, db):
    """Mejora real sobre la antigua `prevision_historico` (sin id_empresa): dos empresas distintas
    nunca mezclan su histórico."""
    from src.db import ventas_analitica as va
    from src.db import ventas_historicas as vh
    EMP2 = "T-VENTAS-ANALITICA-CENTR-2"
    vh.registrar_venta_historica("2024-05-01", "ARTX", importe=999.0, id_empresa=EMP2)
    try:
        assert va.contar_historico(EMP) == 0
        assert va.contar_historico(EMP2) == 1
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_historicas WHERE id_empresa=%s", (EMP2,))
            conn.commit()


def test_importar_prevision_historico_ya_no_existe(limpia):
    """Función retirada (la escritura ahora ocurre solo vía el wizard centralizado →
    `ventas_historicas`, nunca directo desde `gui/ventas.py`)."""
    from src.db import ventas_analitica as va
    assert not hasattr(va, "importar_prevision_historico")


def test_flujo_completo_wizard_alimenta_el_historico_de_ventas(limpia):
    """Fin a fin: una fila importada vía el motor del wizard (igual que haría la entidad
    VENTAS_HIST) aparece inmediatamente en las funciones que lee `gui/ventas.py`."""
    from src.db.ventas_historicas import registrar_venta_historica
    ok = registrar_venta_historica("2024-03-15", "SKU-1", cantidad=10, importe=250.5, id_empresa=EMP)
    assert ok is True
    from src.db import ventas_analitica as va
    assert va.contar_historico(EMP) == 1
    anio, dias, total, fuente = va.resumen_historico(EMP)[0]
    assert anio == 2024 and dias == 1 and float(total) == 250.5 and fuente == "IMPORTADO"
