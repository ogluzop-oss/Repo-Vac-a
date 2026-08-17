"""
Segmentación por tipo de comercio (ediciones/verticales). Producto SEPARADO por build/instalación
(`SMART_MANAGER_EDITION`), misma base y tarifas. Según la edición se ocultan/sustituyen funciones y se siembran
datos por defecto. Nombre de la app: "Smart Manager <Edición>".
"""

import pytest

from src.services import verticales as V


@pytest.fixture(autouse=True)
def _sin_env(monkeypatch, tmp_path):
    monkeypatch.delenv("SMART_MANAGER_EDITION", raising=False)
    monkeypatch.delenv("SM_EDITION", raising=False)
    # Aísla la persistencia de onboarding en un fichero temporal (no toca el config_edicion.json real).
    monkeypatch.setattr(V, "RUTA_CONFIG", str(tmp_path / "config_edicion.json"))


def test_bascula_segmentada_por_vertical():
    assert V.visible("tpv.bascula", vertical="SUPERMARKET") is True
    # En Bakery se vende por unidad (nunca a granel) → báscula oculta.
    assert V.visible("tpv.bascula", vertical="BAKERY") is False
    assert V.estado("tpv.bascula", vertical="BAKERY") == "oculto"
    assert V.visible("tpv.bascula", vertical="RETAIL") is False
    assert V.estado("tpv.bascula", vertical="RETAIL") == "oculto"
    # en textil se SUSTITUYE por variantes talla/color
    assert V.estado("tpv.bascula", vertical="TEXTIL") == "sustituida"
    assert V.sustituto("tpv.bascula", vertical="TEXTIL") == "productos.tallas"


def test_subastas_solo_supermarket_y_retail():
    # Las subastas (pujas) del mercado solo en comercio general de volumen.
    assert V.visible("compras.subastas", vertical="SUPERMARKET") is True
    assert V.visible("compras.subastas", vertical="RETAIL") is True
    assert V.visible("compras.subastas", vertical="PHARMACY") is False
    assert V.visible("compras.subastas", vertical="TEXTIL") is False
    assert V.visible("compras.subastas", vertical="BAKERY") is False


def test_funciones_exclusivas():
    assert V.visible("pharmacy.recetas", vertical="PHARMACY") is True
    assert V.visible("pharmacy.recetas", vertical="RETAIL") is False
    assert V.visible("bakery.obrador", vertical="BAKERY") is True
    assert V.visible("bakery.obrador", vertical="SUPERMARKET") is False


def test_supermarket_superset_variantes_sin_flujos_de_nicho():
    # Supermarket = "vende de todo": muestra el asistente de variantes talla/color (venden ropa)...
    assert V.visible("productos.tallas", vertical="SUPERMARKET") is True
    assert V.visible("productos.tallas", vertical="RETAIL") is True
    assert V.visible("productos.tallas", vertical="TEXTIL") is True
    # ...pero NO los flujos especializados de farmacia/panadería.
    assert V.visible("pharmacy.recetas", vertical="SUPERMARKET") is False
    assert V.visible("bakery.obrador", vertical="SUPERMARKET") is False
    # y báscula/granel/lotes siguen visibles (sin limitación de contenido).
    assert V.visible("tpv.bascula", vertical="SUPERMARKET") is True
    assert V.visible("productos.lotes", vertical="SUPERMARKET") is True


def test_bolsa_y_portal_solo_supermarket_y_retail():
    # La bolsa de proveedores + mercado (Lonja) + Portal proveedor = solo comercio general (Super/Retail).
    for ed in ("SUPERMARKET", "RETAIL"):
        assert V.visible("compras.bolsa", vertical=ed) is True
    for ed in ("PHARMACY", "TEXTIL", "BAKERY"):
        assert V.visible("compras.bolsa", vertical=ed) is False


def test_autocobro_solo_supermarket():
    # El autocobro (self-checkout con verificación de edad) es EXCLUSIVO de Supermarket.
    assert V.visible("tpv.autocobro", vertical="SUPERMARKET") is True
    for ed in ("RETAIL", "PHARMACY", "TEXTIL", "BAKERY"):
        assert V.visible("tpv.autocobro", vertical=ed) is False


def test_mrp_industrial_gateado_por_edicion():
    # MRP/Fabricación industrial: oculto en Bakery (sustituido por el Obrador) y en Pharmacy; visible en el resto.
    assert V.visible("almacenes.mrp", vertical="BAKERY") is False
    assert V.sustituto("almacenes.mrp", vertical="BAKERY") == "bakery.obrador"
    assert V.visible("almacenes.mrp", vertical="PHARMACY") is False
    assert V.estado("almacenes.mrp", vertical="PHARMACY") == "oculto"
    for ed in ("SUPERMARKET", "RETAIL", "TEXTIL"):
        assert V.visible("almacenes.mrp", vertical=ed) is True


def test_bakery_tpv_simplificado_gateado():
    # En Bakery el TPV se simplifica: sin venta desde almacén, tarjeta regalo ni devoluciones; y sin
    # Catálogo Web (carta física en el local). En el resto de ediciones estas funciones están disponibles.
    for f in ("tpv.venta_almacen", "tpv.tarjeta_regalo", "tpv.devolucion", "catalogo.web"):
        assert V.visible(f, vertical="BAKERY") is False
        for ed in ("SUPERMARKET", "RETAIL", "PHARMACY", "TEXTIL"):
            assert V.visible(f, vertical=ed) is True


def test_nombre_edicion():
    assert V.nombre_edicion(vertical="SUPERMARKET") == "Smart Manager Supermarket"
    assert V.nombre_edicion(vertical="RETAIL") == "Smart Manager Retail"
    assert V.nombre_edicion(vertical="BAKERY") == "Smart Manager Bakery & Coffee"


def test_edicion_fijada_por_entorno(monkeypatch):
    assert V.vertical_actual() == V.DEFECTO == "SUPERMARKET"   # sin env → defecto
    monkeypatch.setenv("SMART_MANAGER_EDITION", "PHARMACY")
    assert V.vertical_actual() == "PHARMACY" and V.edicion() == "PHARMACY"
    monkeypatch.setenv("SMART_MANAGER_EDITION", "bakery & coffee")   # tolera variantes
    assert V.vertical_actual() == "BAKERY"
    monkeypatch.setenv("SMART_MANAGER_EDITION", "NO_EXISTE")
    assert V.vertical_actual() == "SUPERMARKET"                # inválido → defecto


def test_onboarding_persiste_y_prioridad(monkeypatch):
    # Primera ejecución: sin env ni elección → hay que preguntar; resuelve al defecto.
    assert V.edicion_definida() is False
    assert V.edicion_configurada() is None
    assert V.vertical_actual() == "SUPERMARKET"
    # El negocio elige su tipo de comercio en el onboarding → se persiste.
    assert V.fijar_edicion("bakery & coffee") is True             # tolera variantes de nombre
    assert V.edicion_configurada() == "BAKERY"
    assert V.edicion_definida() is True                           # ya no se vuelve a preguntar
    assert V.vertical_actual() == "BAKERY"
    assert V.nombre_edicion() == "Smart Manager Bakery & Coffee"
    # El entorno (override / aprovisionamiento SaaS) tiene prioridad sobre el onboarding.
    monkeypatch.setenv("SMART_MANAGER_EDITION", "PHARMACY")
    assert V.vertical_actual() == "PHARMACY"


def test_onboarding_rechaza_edicion_invalida():
    assert V.fijar_edicion("NO_EXISTE") is False
    assert V.edicion_configurada() is None and V.edicion_definida() is False


def test_matriz_funciones_para_admin():
    d = {f["funcion"]: f for f in V.funciones(vertical="TEXTIL")}
    assert d["tpv.bascula"]["estado"] == "sustituida" and d["tpv.bascula"]["sustituto"] == "productos.tallas"
    assert d["productos.tallas"]["estado"] == "visible"
    assert d["pharmacy.recetas"]["estado"] == "oculto"


def test_datos_por_defecto_por_edicion(fab, db):
    emp = fab.EMP_DEFECTO
    fams = V.familias_por_defecto(vertical="PHARMACY")
    assert "Medicamentos" in fams and "Parafarmacia" in fams
    with db.obtener_conexion() as c, c.cursor() as cur:   # poda INMEDIATA de restos previos (fab._borrar difiere)
        for n in fams:
            cur.execute("DELETE FROM familias_producto WHERE nombre=%s", (n,))
        c.commit()
    for n in fams:
        fab._borrar("familias_producto", "nombre", n)     # limpieza al teardown
    res = V.aplicar_datos_por_defecto(emp, vertical="PHARMACY")
    assert res["ok"] and res["familias_creadas"] == len(fams)      # todas nuevas
    # idempotente: segunda pasada no vuelve a crear
    assert V.aplicar_datos_por_defecto(emp, vertical="PHARMACY")["familias_creadas"] == 0
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM familias_producto WHERE nombre='Medicamentos' AND id_empresa=%s",
                    (emp,))
        assert cur.fetchone()[0] == 1                              # sin duplicar
