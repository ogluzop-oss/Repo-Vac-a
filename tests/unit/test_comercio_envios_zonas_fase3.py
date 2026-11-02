"""
Fase 3 (e-commerce, Catálogo Web) — zonas de envío: cálculo de coste por zona geográfica/peso/
importe de pedido, pieza genuinamente nueva (no existía ningún cálculo de envío en el código),
enganchada en `comercial.cotizar` sin romper a ningún llamador existente (sin `pais_destino`,
comportamiento idéntico a siempre — sin línea de envío)."""

import pytest

EMP = "T-ENVIOS-F3"
COD = "ENV3-ART"


@pytest.fixture()
def limpio(db):
    def _clean(cur):
        for t in ("cd_envios_zonas", "cupones", "promociones"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, peso_unitario) "
                    "VALUES (%s,%s,'Envios F3 Test',40.0,2.0)", (COD, EMP))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


# ── envios.zonas: CRUD + cálculo ─────────────────────────────────────────────

def test_sin_zonas_configuradas_degrada_a_coste_cero(limpio):
    from src.services.comercio_digital.envios import zonas
    r = zonas.calcular_envio("ES", 1.0, 50.0, id_empresa=EMP)
    assert r == {"zona": None, "coste": 0.0, "gratis": False, "motivo": "sin_zonas_configuradas",
                "umbral_envio_gratis": None, "falta_para_envio_gratis": 0.0}


def test_tarifa_base_mas_por_kg(limpio):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, tarifa_por_kg=1.5, id_empresa=EMP)
    r = zonas.calcular_envio("ES", 2.0, 30.0, id_empresa=EMP)
    assert r["zona"] == "España"
    assert r["coste"] == 8.0   # 5 + 1.5*2
    assert r["gratis"] is False


def test_pais_no_cubierto_cae_a_zona_por_defecto(limpio):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, id_empresa=EMP)
    zonas.crear_zona("Resto del mundo", paises=None, tarifa_base=20.0, id_empresa=EMP)
    r = zonas.calcular_envio("US", 1.0, 30.0, id_empresa=EMP)
    assert r["zona"] == "Resto del mundo" and r["coste"] == 20.0


def test_sin_zona_por_defecto_y_pais_no_cubierto_no_inventa_tarifa(limpio):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, id_empresa=EMP)
    r = zonas.calcular_envio("US", 1.0, 30.0, id_empresa=EMP)
    assert r == {"zona": None, "coste": 0.0, "gratis": False, "motivo": "sin_zona_para_destino",
                "umbral_envio_gratis": None, "falta_para_envio_gratis": 0.0}


def test_umbral_de_envio_gratis_de_la_zona(limpio):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, envio_gratis_desde=50.0, id_empresa=EMP)
    barato = zonas.calcular_envio("ES", 1.0, 30.0, id_empresa=EMP)
    caro = zonas.calcular_envio("ES", 1.0, 60.0, id_empresa=EMP)
    assert barato["gratis"] is False and barato["coste"] == 5.0
    assert caro["gratis"] is True and caro["coste"] == 0.0 and caro["motivo"] == "umbral_zona"


def test_falta_para_envio_gratis_se_calcula_para_la_barra_de_progreso(limpio):
    """Pedido explícito (carrito flotante): la barra de progreso de envío gratis necesita saber
    CUÁNTO falta, no solo si ya se alcanzó — `calcular_envio` lo expone sin romper el contrato
    existente (campos nuevos, no se tocan los de siempre)."""
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, envio_gratis_desde=50.0, id_empresa=EMP)
    lejos = zonas.calcular_envio("ES", 1.0, 30.0, id_empresa=EMP)
    cerca = zonas.calcular_envio("ES", 1.0, 45.5, id_empresa=EMP)
    ya = zonas.calcular_envio("ES", 1.0, 60.0, id_empresa=EMP)
    assert lejos["umbral_envio_gratis"] == 50.0 and lejos["falta_para_envio_gratis"] == 20.0
    assert cerca["falta_para_envio_gratis"] == 4.5
    assert ya["falta_para_envio_gratis"] == 0.0


def test_envio_gratis_forzado_por_cupon_anula_tarifa(limpio):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=99.0, id_empresa=EMP)
    r = zonas.calcular_envio("ES", 5.0, 10.0, envio_gratis_forzado=True, id_empresa=EMP)
    assert r["gratis"] is True and r["coste"] == 0.0 and r["motivo"] == "cupon_envio_gratis"


def test_zona_inactiva_no_se_usa(limpio):
    from src.services.comercio_digital.envios import zonas
    id_z = zonas.crear_zona("España", paises="ES", tarifa_base=5.0, id_empresa=EMP)
    zonas.actualizar_zona(id_z, activa=0, id_empresa=EMP)
    r = zonas.calcular_envio("ES", 1.0, 30.0, id_empresa=EMP)
    assert r["motivo"] == "sin_zonas_configuradas"


def test_peso_total_lineas_usa_el_peso_unitario_real_del_articulo(limpio):
    from src.services.comercio_digital.envios import zonas
    peso = zonas.peso_total_lineas([{"codigo": COD, "cantidad": 3}], id_empresa=EMP)
    assert peso == 6.0   # 2.0 kg/unidad * 3


def test_peso_total_lineas_sin_peso_registrado_no_inventa_nada(limpio, db):
    from src.services.comercio_digital.envios import zonas
    cod2 = "ENV3-SINPESO"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod2, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio) "
                    "VALUES (%s,%s,'Sin peso',10.0)", (cod2, EMP))
        conn.commit()
    try:
        peso = zonas.peso_total_lineas([{"codigo": cod2, "cantidad": 5}], id_empresa=EMP)
        assert peso == 0.0
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod2, EMP))
            conn.commit()


def test_eliminar_zona(limpio):
    from src.services.comercio_digital.envios import zonas
    id_z = zonas.crear_zona("Temporal", tarifa_base=1.0, id_empresa=EMP)
    assert zonas.eliminar_zona(id_z, id_empresa=EMP) is True
    assert zonas.listar_zonas(EMP) == []


# ── Integración con comercial.cotizar ────────────────────────────────────────

def test_cotizar_sin_pais_destino_no_cambia_el_comportamiento_de_siempre(limpio):
    """Regresión crítica: la inmensa mayoría de llamadores de `cotizar` (TPV, pedidos internos,
    todos los tests ya existentes) NO pasan `pais_destino` — deben seguir sin ninguna línea de
    envío, exactamente como antes de esta fase."""
    from src.services.comercio_digital.envios import zonas
    from src.services.comercio_digital import comercial as com
    zonas.crear_zona("España", paises="ES", tarifa_base=99.0, id_empresa=EMP)   # a propósito, caro
    q = com.cotizar([{"codigo": COD, "cantidad": 1, "precio_unitario": 40.0}], id_empresa=EMP)
    assert q["envio"] == {"zona": None, "coste": 0.0, "gratis": False, "motivo": None}
    assert q["total"] == 40.0


def test_cotizar_con_pais_destino_anade_el_coste_de_envio(limpio):
    from src.services.comercio_digital.envios import zonas
    from src.services.comercio_digital import comercial as com
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, tarifa_por_kg=1.0, id_empresa=EMP)
    q = com.cotizar([{"codigo": COD, "cantidad": 2, "precio_unitario": 40.0}],
                    pais_destino="ES", id_empresa=EMP)
    # peso: 2kg/u * 2 = 4kg -> envío = 5 + 1*4 = 9
    assert q["envio"]["coste"] == 9.0
    assert q["total"] == 80.0 + 9.0


def test_cotizar_cupon_envio_gratis_mas_pais_destino_no_cobra_envio(limpio):
    from src.db import fidelizacion as fid
    from src.services.comercio_digital.envios import zonas
    from src.services.comercio_digital import comercial as com
    zonas.crear_zona("España", paises="ES", tarifa_base=15.0, id_empresa=EMP)
    fid.emitir_cupon("ENVIOGRATISF3", tipo="envio_gratis", valor=0, id_empresa=EMP)
    q = com.cotizar([{"codigo": COD, "cantidad": 1, "precio_unitario": 40.0}],
                    cupon="ENVIOGRATISF3", pais_destino="ES", id_empresa=EMP)
    assert q["envio"]["gratis"] is True and q["envio"]["coste"] == 0.0
    assert q["total"] == 40.0
