"""
Tests Etapa C0 · Prioridad 4: consolidación de utilidades internas en `comercio_digital/_base.py`.

Verifica que las utilidades duplicadas ahora tienen UNA fuente única (`_base`) y que los servicios
delegan en ella (sin lógica duplicada), manteniendo el mismo comportamiento y sin cambiar contratos.
"""

import inspect


def test_base_es_fuente_unica():
    from src.services.comercio_digital import _base
    for fn in ("emp", "correlation_id", "publicar_evento", "hmac_valido", "verificar_firma_webhook",
               "fila_a_dict"):
        assert hasattr(_base, fn), f"falta {fn} en _base"
    # emp resuelve el tenant; hmac_valido calcula la firma.
    assert _base.emp("EMP-X") == "EMP-X"
    import hashlib
    import hmac
    firma = hmac.new(b"s", b"cuerpo", hashlib.sha256).hexdigest()
    assert _base.hmac_valido("s", "cuerpo", firma) is True
    assert _base.hmac_valido("s", "cuerpo", "mala") is False
    assert _base.hmac_valido(None, "x", "y") is None       # degradable
    assert _base.fila_a_dict((1, 2), ("a", "b")) == {"a": 1, "b": 2}


def test_emp_delegado_en_todos_los_servicios():
    from src.services.comercio_digital import _base
    from src.services.comercio_digital import (automatizacion, catalogo, checkout, comercial,
                                               conexiones, envios, pagos, presencia, publicaciones)
    for mod in (automatizacion, catalogo, checkout, comercial, conexiones, envios, pagos, presencia,
                publicaciones):
        src = inspect.getsource(mod._emp)
        assert "_emp_base" in src or "_base" in src        # delega, no reimplementa
        assert mod._emp("EMP-Y") == _base.emp("EMP-Y")     # mismo resultado


def test_helpers_pesados_sin_logica_duplicada():
    from src.services.comercio_digital import pagos, presencia, publicaciones, sync
    # _correlation_id: sin uuid/observabilidad inline (todo en _base).
    for mod in (sync, publicaciones, presencia):
        s = inspect.getsource(mod._correlation_id)
        assert "_base" in s and "uuid" not in s and "observabilidad" not in s
        p = inspect.getsource(mod._publicar)
        assert "_base" in p and "bus.publish" not in p
    # _verificar_firma: sin HMAC inline (delegado a _base).
    for mod in (sync, pagos):
        v = inspect.getsource(mod._verificar_firma)
        assert "_base" in v and "hashlib" not in v and "compare_digest" not in v


def test_firma_sigue_funcionando_via_base(db):
    """El HMAC delegado en _base sigue validando igual (comportamiento intacto)."""
    import hashlib
    import hmac

    from src.services.comercio_digital import conexiones, sync
    EMP = "T-P4-A"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
        conn.commit()
    conexiones.registrar("p4canal", id_empresa=EMP, tipo_auth="hmac",
                         credenciales={"webhook_secret": "K"})
    cuerpo = '{"x":1}'
    firma = hmac.new(b"K", cuerpo.encode(), hashlib.sha256).hexdigest()
    assert sync._verificar_firma("p4canal", cuerpo, firma, EMP) is True
    assert sync._verificar_firma("p4canal", cuerpo, "mala", EMP) is False
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
        conn.commit()
