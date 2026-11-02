"""
Fase 2 (e-commerce, Catálogo Web) — motor de descuentos/promociones: condiciones reales de
cupón (fecha de inicio, límite de usos TOTALES configurable, importe mínimo, restricción por
cliente), tipo "envío gratis", y el cierre de un bug real: el checkout nunca REDIMÍA el cupón que
él mismo había validado (`comercial.redimir_cupon` llevaba su propio docstring diciendo "lo usará
el checkout al confirmar" sin que nada lo llamara)."""

import pytest

EMP = "T-DESC-FASE2"
COD = "DESC2-ART"


@pytest.fixture()
def limpio(db):
    def _clean(cur):
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial", "cd_reservas", "cupones", "promociones"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda, "
                    "Stock_central) VALUES (%s,%s,'Descuentos F2 Test',100.0,0,50)", (COD, EMP))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


# ── db.fidelizacion: condiciones del cupón ───────────────────────────────────

def test_uso_maximo_por_defecto_sigue_siendo_un_solo_uso(limpio):
    """Regresión crítica: NO debe cambiar el comportamiento de un cupón creado sin especificar
    `uso_maximo` — sigue siendo de un solo uso, exactamente como antes de esta fase."""
    from src.db import fidelizacion as fid
    fid.emitir_cupon("UNICO1", tipo="importe_fijo", valor=5, id_empresa=EMP)
    assert fid.redimir_cupon("UNICO1", id_empresa=EMP) is True
    assert fid.validar_cupon("UNICO1", id_empresa=EMP) is None   # agotado tras 1 uso
    assert fid.redimir_cupon("UNICO1", id_empresa=EMP) is False


def test_uso_maximo_configurable_permite_varios_usos(limpio):
    from src.db import fidelizacion as fid
    fid.emitir_cupon("MULTI3", tipo="importe_fijo", valor=5, uso_maximo=3, id_empresa=EMP)
    assert fid.redimir_cupon("MULTI3", id_empresa=EMP) is True
    assert fid.redimir_cupon("MULTI3", id_empresa=EMP) is True
    assert fid.validar_cupon("MULTI3", id_empresa=EMP) is not None   # aún le queda 1 uso
    assert fid.redimir_cupon("MULTI3", id_empresa=EMP) is True
    assert fid.redimir_cupon("MULTI3", id_empresa=EMP) is False   # agotado (3/3)


def test_fecha_inicio_futura_invalida_el_cupon(limpio):
    import datetime as dt
    from src.db import fidelizacion as fid
    manana = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    fid.emitir_cupon("FUTURO1", tipo="descuento_pct", valor=10, fecha_inicio=manana, id_empresa=EMP)
    assert fid.validar_cupon("FUTURO1", id_empresa=EMP) is None


def test_fecha_inicio_pasada_es_valida(limpio):
    import datetime as dt
    from src.db import fidelizacion as fid
    ayer = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    fid.emitir_cupon("PASADO1", tipo="descuento_pct", valor=10, fecha_inicio=ayer, id_empresa=EMP)
    assert fid.validar_cupon("PASADO1", id_empresa=EMP) is not None


def test_importe_minimo_bloquea_pedidos_por_debajo(limpio):
    from src.db import fidelizacion as fid
    fid.emitir_cupon("MIN50", tipo="descuento_pct", valor=10, importe_minimo=50.0, id_empresa=EMP)
    assert fid.validar_cupon("MIN50", id_empresa=EMP, importe_pedido=30.0) is None
    assert fid.validar_cupon("MIN50", id_empresa=EMP, importe_pedido=50.0) is not None
    assert fid.validar_cupon("MIN50", id_empresa=EMP, importe_pedido=75.0) is not None


def test_restriccion_por_cliente_se_respeta(limpio):
    from src.db import fidelizacion as fid
    fid.emitir_cupon("SOLOCLI", tipo="descuento_pct", valor=10, id_cliente=999, id_empresa=EMP)
    assert fid.validar_cupon("SOLOCLI", id_empresa=EMP, id_cliente=111) is None
    assert fid.validar_cupon("SOLOCLI", id_empresa=EMP, id_cliente=999) is not None
    assert fid.validar_cupon("SOLOCLI", id_empresa=EMP) is not None   # sin id_cliente: no se comprueba


# ── comercial.cotizar: tipo "envío gratis" ───────────────────────────────────

def test_cotizar_envio_gratis_no_descuenta_subtotal_pero_marca_el_flag(limpio):
    from src.db import fidelizacion as fid
    from src.services.comercio_digital import comercial as com
    fid.emitir_cupon("ENVIOGRATIS", tipo="envio_gratis", valor=0, id_empresa=EMP)
    q = com.cotizar([{"codigo": COD, "cantidad": 1, "precio_unitario": 100.0}],
                    cupon="ENVIOGRATIS", id_empresa=EMP)
    assert q["cupon"]["valido"] is True
    assert q["cupon"]["envio_gratis"] is True
    assert q["envio_gratis"] is True
    assert q["descuento_cupon"] == 0.0   # no toca el precio de los productos
    assert q["total"] == 100.0


def test_cotizar_sin_cupon_envio_gratis_false(limpio):
    from src.services.comercio_digital import comercial as com
    q = com.cotizar([{"codigo": COD, "cantidad": 1, "precio_unitario": 100.0}], id_empresa=EMP)
    assert q["envio_gratis"] is False


# ── checkout.confirmar: cierre del bug real (cupón validado pero nunca redimido) ──

def test_checkout_confirmar_redime_de_verdad_el_cupon(limpio):
    from src.db import fidelizacion as fid
    from src.services.comercio_digital import checkout
    fid.emitir_cupon("CHKREDIME", tipo="importe_fijo", valor=10, id_empresa=EMP)

    antes = fid.validar_cupon("CHKREDIME", id_empresa=EMP)
    assert antes is not None and int(antes["usos_actuales"]) == 0

    r = checkout.confirmar(id_empresa=EMP, origen="web", cupon="CHKREDIME",
                           lineas=[{"codigo": COD, "cantidad": 1, "precio_unitario": 100.0}])
    assert r["ok"] is True

    despues = fid.validar_cupon("CHKREDIME", id_empresa=EMP)
    # Cupón de un solo uso: tras confirmar, ya debe estar agotado (bug real: antes se quedaba
    # SIEMPRE "activo" porque nadie llamaba nunca a redimir_cupon desde el checkout).
    assert despues is None


def test_checkout_confirmar_sin_cupon_no_falla(limpio):
    from src.services.comercio_digital import checkout
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": COD, "cantidad": 1, "precio_unitario": 100.0}])
    assert r["ok"] is True


def test_checkout_confirmar_con_cupon_invalido_no_rompe_el_pedido(limpio):
    """Best-effort: un cupón que deja de ser válido justo antes de confirmar (p. ej. caducó hace un
    instante) no debe impedir que el pedido se confirme — `cotizar()` ya lo marcó `valido=False`."""
    from src.services.comercio_digital import checkout
    r = checkout.confirmar(id_empresa=EMP, origen="web", cupon="NOEXISTE123",
                           lineas=[{"codigo": COD, "cantidad": 1, "precio_unitario": 100.0}])
    assert r["ok"] is True
