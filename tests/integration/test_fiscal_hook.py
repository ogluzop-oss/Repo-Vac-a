"""Integración · hook TPV (tras fiscal_config.activo) + worker de cola (C3.2)."""

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def _venta(db, emp, fab, total=12.0):
    """Registra una venta de la empresa `emp` y devuelve su id."""
    from src.db import conexion as cx
    from src.db.empresa import contexto_tenant
    cod = fab.articulo(id_empresa=emp, precio=total, stock_tienda=100)
    with contexto_tenant(emp, None):
        return cx.registrar_venta_con_items(
            [{"codigo": cod, "cantidad": 1, "precio_unitario": total}])


def test_hook_off_por_defecto_no_genera_registro(db, fab):
    """Sin activar el módulo (por defecto), la venta NO crea registro fiscal."""
    from src.db import fiscal as F
    emp = fab.empresa("HOOK OFF")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    vid = _venta(db, emp, fab)
    assert vid is not None                      # la venta funciona igual que siempre
    assert F.listar_registros(id_empresa=emp) == []


def test_hook_on_genera_y_encola(db, fab):
    from src.db import fiscal as F
    emp = fab.empresa("HOOK ON")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    assert F.guardar_config(activo=1, serie="A", serie_por="empresa", id_empresa=emp)
    vid = _venta(db, emp, fab, total=33.0)
    regs = F.listar_registros(id_empresa=emp)
    assert len(regs) == 1 and regs[0]["referencia"] == str(vid)
    assert regs[0]["tipo"] == "ticket" and float(regs[0]["total"]) == 33.0
    # Encolado para firma/envío asíncronos.
    cola = F.listar_cola(id_empresa=emp)
    assert cola and cola[0]["id_registro"] == regs[0]["id"]


def test_worker_sin_emisor_deja_en_espera(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    from src.services.fiscal.worker import procesar_cola
    emp = fab.empresa("WORKER ESPERA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(activo=1, id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_fiscal_actual().registrar("ticket", referencia="V1", total=5.0)
    F.encolar(r.id, id_empresa=emp)
    res = procesar_cola(id_empresa=emp)
    assert res["en_espera"] == 1 and res["enviados"] == 0
    # Sigue pendiente pero con backoff (no aparece como "listo").
    assert F.listar_cola(id_empresa=emp, listos=True) == []
    assert len(F.listar_cola(id_empresa=emp)) == 1


def test_worker_idempotente_si_ya_enviado(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    from src.services.fiscal.worker import procesar_cola
    emp = fab.empresa("WORKER IDEMP")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(activo=1, id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_fiscal_actual().registrar("ticket", referencia="V1", total=5.0)
    F.encolar(r.id, id_empresa=emp)
    F.actualizar_estado(r.id, "enviado")        # ya gestionado fuera de banda
    res = procesar_cola(id_empresa=emp)
    assert res["enviados"] == 1
    assert F.listar_cola(id_empresa=emp) == []   # la entrada se cierra sin reenviar


def test_worker_emisor_ok_marca_enviado(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    from src.services.fiscal.base import Emisor
    from src.services.fiscal.worker import procesar_cola
    emp = fab.empresa("WORKER OK")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(activo=1, id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_fiscal_actual().registrar("factura", referencia="F1", total=9.0)
    F.encolar(r.id, id_empresa=emp)

    class EmisorOK(Emisor):
        def disponible(self):
            return True
        def enviar(self, registro, config):
            return {"ok": True, "estado": "enviado"}

    res = procesar_cola(id_empresa=emp, emisor=EmisorOK())
    assert res["enviados"] == 1
    assert F.obtener_registro(r.id)["estado"] == "enviado"
    assert F.listar_cola(id_empresa=emp) == []
