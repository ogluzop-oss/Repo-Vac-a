"""Anti-hurto: alarma de salida sin pagar → push al móvil del guardia. `db`.

Verifica el manejador interno services.rfid.antihurto.alarma_salida_no_pagada: resolución del artículo
(EAN/EPC), aviso a los guardias registrados, anti-falsa-alarma (pagado reciente) y artículo desconocido.
"""

import pytest

pytestmark = pytest.mark.db


def test_antihurto_alarma(db, fab):
    from src.services.rfid import antihurto as A

    emp = fab.EMP_DEFECTO
    cod = fab.articulo(nombre="Zapatilla Run", precio=59.99, id_empresa=emp)

    # Guardia registrado (su app se registra al iniciar sesión).
    assert A.registrar_guardia("7", "tok-abc", id_empresa=emp) is True
    fab.al_limpiar(lambda: A.baja_guardia("7", id_empresa=emp))
    assert "7" in A.guardias(emp)

    # Alarma por EAN → notifica al guardia con la ficha del artículo.
    r = A.alarma_salida_no_pagada(ean=cod, id_empresa=emp, id_tienda=1)
    assert r["ok"] is True and r["notificados"] >= 1
    art = r["articulo"]
    assert art["ean"] == cod and art["nombre"] == "Zapatilla Run"
    assert abs(art["precio"] - 59.99) < 0.01 and art["evento"] == "salida_no_pagada"

    # EAN detectado pero fuera del catálogo → SÍ avisa (con el EAN como nombre; mejor avisar).
    r_desc = A.alarma_salida_no_pagada(ean="NOEXISTE-" + cod, id_empresa=emp)
    assert r_desc["ok"] is True and r_desc["articulo"]["nombre"] == "NOEXISTE-" + cod

    # Sin EAN y con EPC que no resuelve → no identificado, no se dispara.
    assert A.alarma_salida_no_pagada(epc="EPC-INEXISTENTE-XYZ", id_empresa=emp)["ok"] is False

    # Resolución por EPC (etiqueta RFID → código).
    epc = "EPC-ANTIHURTO-1"
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO ubicaciones (epc, codigo_articulo, verificado) VALUES (%s,%s,1)", (epc, cod))
        c.commit()
    fab.al_limpiar(lambda: _del(db, "ubicaciones", "epc", epc))
    assert A.alarma_salida_no_pagada(epc=epc, id_empresa=emp)["articulo"]["ean"] == cod

    # Anti falsa-alarma: si se pagó hace un momento, NO se dispara.
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total) VALUES (NOW(), 59.99)")
        vid = cur.lastrowid
        cur.execute("INSERT INTO venta_items (venta_id, codigo_articulo, cantidad, precio_unitario, "
                    "subtotal) VALUES (%s,%s,1,59.99,59.99)", (vid, cod))
        c.commit()
    fab.al_limpiar(lambda: (_del(db, "venta_items", "venta_id", vid), _del(db, "ventas", "id", vid)))
    r2 = A.alarma_salida_no_pagada(ean=cod, id_empresa=emp)
    assert r2["ok"] is False and r2["motivo"] == "pagado_recientemente"
    # …salvo que se desactive la verificación.
    assert A.alarma_salida_no_pagada(ean=cod, id_empresa=emp, verificar_pago=False)["ok"] is True


def _del(db, tabla, campo, valor):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla} WHERE {campo}=%s", (valor,))
        c.commit()
