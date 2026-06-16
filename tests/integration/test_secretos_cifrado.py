"""Integración · cifrado en reposo de secretos (pasarela/ecommerce)."""

import pytest

pytestmark = pytest.mark.db


def _raw(db, tabla, col, eid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {col} FROM {tabla} WHERE id_empresa=%s", (eid,))
        r = cur.fetchone()
        return r[0] if r else None


def test_pasarela_secreto_cifrado_en_reposo(db, fab):
    from src.db import pagos
    from src.utils import cripto
    if not cripto.cifrado_disponible():
        pytest.skip("Sin backend de cifrado")
    eid = fab.empresa("EMP CIFRA")
    fab.pasarela(id_empresa=eid, proveedor="stripe",
                 api_secret="sk_test_SECRETO", webhook_secret="whsec_ABC")
    # En la BD está cifrado (no en claro)…
    bruto = _raw(db, "pasarela_config", "api_secret", eid)
    assert cripto.parece_cifrado(bruto) and "sk_test_SECRETO" not in str(bruto)
    # …pero la capa de servicio lo devuelve descifrado.
    cfg = pagos.obtener_config(eid)
    assert cfg["api_secret"] == "sk_test_SECRETO" and cfg["webhook_secret"] == "whsec_ABC"


def test_migra_secreto_legado_en_claro(db, fab):
    from src.db import pagos
    from src.utils import cripto
    if not cripto.cifrado_disponible():
        pytest.skip("Sin backend de cifrado")
    eid = fab.empresa("EMP LEGADO")
    # Inserta un secreto EN CLARO directamente (simula dato legado).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO pasarela_config (id_empresa, proveedor, api_secret) "
                    "VALUES (%s,'redsys','claveEnClaro123')", (eid,))
        conn.commit()
    fab._borrar("pasarela_config", "id_empresa", eid)
    # Se lee bien aunque esté en claro (retrocompatibilidad).
    assert pagos.obtener_config(eid)["api_secret"] == "claveEnClaro123"
    # Tras migrar, queda cifrado en reposo y sigue leyéndose igual.
    pagos.migrar_cifrado()
    assert cripto.parece_cifrado(_raw(db, "pasarela_config", "api_secret", eid))
    assert pagos.obtener_config(eid)["api_secret"] == "claveEnClaro123"


def test_ecommerce_secreto_cifrado(db, fab):
    from src.db import ecommerce
    from src.utils import cripto
    if not cripto.cifrado_disponible():
        pytest.skip("Sin backend de cifrado")
    eid = fab.empresa("EMP ECOM")
    ecommerce.guardar_config(plataforma="woocommerce", api_key="ck_123",
                             api_secret="cs_456", id_empresa=eid)
    fab._borrar("ecommerce_config", "id_empresa", eid)
    assert cripto.parece_cifrado(_raw(db, "ecommerce_config", "api_secret", eid))
    cfg = ecommerce.obtener_config(eid)
    assert cfg["api_key"] == "ck_123" and cfg["api_secret"] == "cs_456"
