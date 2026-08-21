"""Ficha del proveedor · capa de datos (migr 0210 + tarifas). `db`.

Verifica que: (1) los campos comerciales/contacto nuevos de `proveedores` (web/persona_contacto/
forma_pago/pedido_minimo) persisten vía `actualizar_proveedor` y se leen en `obtener_proveedor`; (2)
`proveedores_pro.listar_tarifas_proveedor` devuelve la tarifa MÁS RECIENTE por artículo y
`eliminar_tarifa` borra una tarifa concreta dentro del tenant. Estas tarifas son las que alimentan el
origen 'tarifa' de la bolsa de Pedidos.
"""

import pytest

pytestmark = pytest.mark.db


def test_ficha_campos_y_tarifas(db, fab):
    from src.db import empresa as EMP
    from src.db import proveedores as P
    from src.services.compras import proveedores_pro as PP

    emp = fab.empresa("EMP ficha")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedor_precios_negociados WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    pid = P.crear_proveedor("Proveedor Ficha SL", id_empresa=emp)

    # 1) Campos nuevos (migr 0210) persisten y se leen.
    assert P.actualizar_proveedor(
        pid, id_empresa=emp, web="https://prov.example", persona_contacto="Ana",
        forma_pago="Transferencia", pedido_minimo=150.0, plazo_pago=30, lead_time_dias=5)
    prov = P.obtener_proveedor(pid, id_empresa=emp)
    assert prov["web"] == "https://prov.example"
    assert prov["persona_contacto"] == "Ana"
    assert prov["forma_pago"] == "Transferencia"
    assert float(prov["pedido_minimo"]) == 150.0

    # 2) Tarifas: dos versiones del mismo artículo → la bolsa/ficha muestra la MÁS RECIENTE.
    PP.set_precio_negociado(pid, "ARTF", 9.0, unidad_medida="unidad", id_empresa=emp)
    PP.set_precio_negociado(pid, "ARTF", 7.5, descuento=10, unidad_medida="unidad", id_empresa=emp)
    PP.set_precio_negociado(pid, "OTRO", 3.0, unidad_medida="caja", id_empresa=emp)

    tarifas = PP.listar_tarifas_proveedor(pid, id_empresa=emp)
    por_codigo = {t["codigo"]: t for t in tarifas}
    assert set(por_codigo) == {"ARTF", "OTRO"}                 # una fila por artículo (la reciente)
    assert float(por_codigo["ARTF"]["precio"]) == 7.5
    assert float(por_codigo["ARTF"]["descuento"]) == 10

    # 3) Eliminar una tarifa concreta por id.
    assert PP.eliminar_tarifa(por_codigo["OTRO"]["id"], id_empresa=emp)
    restantes = {t["codigo"] for t in PP.listar_tarifas_proveedor(pid, id_empresa=emp)}
    assert restantes == {"ARTF"}
