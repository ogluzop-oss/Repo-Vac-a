"""
Migrar datos · Granularidad real de stock por ubicación (pedido explícito): además del campo
genérico "stock" (tienda/shelf, YA existente), la entidad PRODUCTOS admite ahora "stock_central"
(almacén central, vía `stock_almacen.ajustar_stock` — fuente de verdad real) y "stock_esperado"
(umbral mínimo de reposición, vía `db.articulos.marcar_stock_esperado`, función NUEVA y estrecha
que NUNCA reutiliza `marcar_repuesto_exportado` — ese tiene efectos secundarios de otro flujo)."""

import pytest

pytestmark = pytest.mark.db

EMP_COD = "IMPGRAN-TEST-1"


@pytest.fixture()
def limpio(db):
    from src.db.conexion import EMPRESA_DEFAULT_ID
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (EMP_COD,))
            cur.execute("DELETE FROM stock_almacen WHERE codigo_articulo=%s", (EMP_COD,))
            conn.commit()
    _b()
    yield
    _b()


def test_modelo_reconoce_los_dos_campos_nuevos():
    from src.services.importacion.modelo import CAMPOS, PRODUCTOS
    assert "stock_central" in CAMPOS[PRODUCTOS]
    assert "stock_esperado" in CAMPOS[PRODUCTOS]
    # Ninguno es obligatorio (no rompe el mapeo automático de ficheros que no los traigan).
    assert CAMPOS[PRODUCTOS]["stock_central"][0] is False
    assert CAMPOS[PRODUCTOS]["stock_esperado"][0] is False


def test_sinonimos_viejos_de_stock_tienda_y_total_siguen_mapeando_a_stock():
    """Las columnas del importador legado retirado (`Stock_tienda`/`Stock_total`) siguen
    funcionando — ahora como sinónimos del campo "stock" ya existente, no se pierde compatibilidad."""
    from src.services.importacion.mapeo import sugerir_mapeo
    from src.services.importacion.modelo import PRODUCTOS
    mapeo = sugerir_mapeo(["codigo", "nombre", "Stock_tienda"], PRODUCTOS)
    assert mapeo.get("stock") == "Stock_tienda"


def test_auto_mapeo_reconoce_stock_central_y_stock_esperado():
    from src.services.importacion.mapeo import sugerir_mapeo
    from src.services.importacion.modelo import PRODUCTOS
    mapeo = sugerir_mapeo(["codigo", "nombre", "Stock_central", "Stock_esperado"], PRODUCTOS)
    assert mapeo.get("stock_central") == "Stock_central"
    assert mapeo.get("stock_esperado") == "Stock_esperado"


def test_marcar_stock_esperado_fija_el_campo(limpio, db):
    from src.db import articulos as art_db
    art_db.crear_articulo(EMP_COD, "Prod Granular Esperado", precio=1.0)
    art_db.marcar_stock_esperado([(EMP_COD, 7)])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_esperado FROM articulos WHERE codigo=%s", (EMP_COD,))
        (esperado,) = cur.fetchone()
    assert int(esperado) == 7


def test_marcar_stock_esperado_distinto_de_marcar_repuesto_exportado():
    """A diferencia de `marcar_repuesto_exportado` (mismo tipo de bulk, pero del flujo de
    reposición: marca `repuesto=1` y `ultima_recepcion`), `marcar_stock_esperado` toma SOLO
    (codigo, valor) — una fila de 3 campos (codigo, stock_esperado, fecha) le haría UPDATE con el
    valor equivocado, confirmando que son funciones realmente distintas, no un alias."""
    import inspect
    from src.db import articulos as art_db
    assert art_db.marcar_stock_esperado is not art_db.marcar_repuesto_exportado
    cuerpo = inspect.getsource(art_db.marcar_stock_esperado)
    assert "UPDATE articulos SET Stock_esperado=" in cuerpo
    assert "UPDATE articulos SET repuesto=1" not in cuerpo


def test_flujo_completo_stock_central_y_esperado_via_motor(limpio, db):
    from src.db.conexion import EMPRESA_DEFAULT_ID
    from src.services.importacion import motor
    filas = [{"codigo": EMP_COD, "nombre": "Prod Granular", "stock_central": "25",
             "stock_esperado": "5"}]
    mapeo = {"codigo": "codigo", "nombre": "nombre", "stock_central": "stock_central",
            "stock_esperado": "stock_esperado"}
    r = motor._cargar_productos(filas, mapeo, EMPRESA_DEFAULT_ID, None, None, True)
    assert r["ok"] is True and r["cargados"] == 1
    assert r["con_stock_central"] == 1
    assert r["con_stock_esperado"] == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central, Stock_esperado FROM articulos WHERE codigo=%s", (EMP_COD,))
        central, esperado = cur.fetchone()
    assert int(central) == 25 and int(esperado) == 5


def test_stock_central_pasa_por_la_fuente_de_verdad_stock_almacen(limpio, db):
    """El stock central escrito debe reflejarse en `stock_almacen` (la fuente de verdad real), no
    solo en la columna caché `articulos.Stock_central`."""
    from src.db.conexion import EMPRESA_DEFAULT_ID
    from src.db import stock_almacen as salm
    from src.services.importacion import motor
    filas = [{"codigo": EMP_COD, "nombre": "Prod Granular", "stock_central": "12"}]
    mapeo = {"codigo": "codigo", "nombre": "nombre", "stock_central": "stock_central"}
    motor._cargar_productos(filas, mapeo, EMPRESA_DEFAULT_ID, None, None, True)
    id_almacen_central = salm.almacen_central(EMPRESA_DEFAULT_ID)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT cantidad FROM stock_almacen WHERE id_empresa=%s AND codigo_articulo=%s "
                   "AND id_almacen=%s", (EMPRESA_DEFAULT_ID, EMP_COD, id_almacen_central))
        fila = cur.fetchone()
    assert fila and int(fila[0]) == 12


def test_sin_mapear_los_campos_nuevos_no_hace_nada_con_ellos(limpio, db):
    """Compatibilidad total: una fila sin "stock_central"/"stock_esperado" mapeados no toca esas
    columnas (comportamiento idéntico al de antes de esta ampliación)."""
    from src.db.conexion import EMPRESA_DEFAULT_ID
    from src.services.importacion import motor
    filas = [{"codigo": EMP_COD, "nombre": "Prod Sin Granular"}]
    mapeo = {"codigo": "codigo", "nombre": "nombre"}
    r = motor._cargar_productos(filas, mapeo, EMPRESA_DEFAULT_ID, None, None, True)
    assert r["con_stock_central"] == 0 and r["con_stock_esperado"] == 0
