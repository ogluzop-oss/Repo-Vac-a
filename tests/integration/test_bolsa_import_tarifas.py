"""Bolsa de proveedores · import de tarifas (Fase 1 · paso 4).

`importar_tarifas_proveedor` reutiliza los lectores del Importador Maestro (aquí, CSV) para poblar la
bolsa. Verifica el alta, la autodetección de columnas y que re-importar actualiza el precio SIN duplicar
la fila en la bolsa (se muestra la tarifa más reciente por proveedor/unidad).
"""

import pytest

from src.db import proveedores as PROV
from src.services.compras import proveedores_pro as PP

pytestmark = pytest.mark.db


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedor_precios_negociados WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_importar_tarifas_y_dedup(db, fab, tmp_path):
    emp = fab.empresa("EMP import")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Tarifas", id_empresa=emp)

    csv = tmp_path / "tarifas.csv"
    csv.write_text("codigo;precio;unidad;descuento\nA1;3,50;caja;5\nA2;1,20;unidad;0\n", encoding="utf-8")

    r = PP.importar_tarifas_proveedor(prov, str(csv), id_empresa=emp)
    assert r == {"total": 2, "importadas": 2, "errores": 0}

    # la bolsa muestra la tarifa importada (autodetección de columnas: precio con coma decimal)
    b = PP.bolsa_precios("A1", id_proveedor=prov, id_empresa=emp)
    assert len(b) == 1 and float(b[0]["precio"]) == 3.5 and b[0]["unidad_medida"] == "caja"
    assert float(b[0]["descuento"]) == 5.0

    # re-importar con precio distinto → la bolsa muestra el NUEVO precio, sin duplicar la fila
    csv.write_text("codigo;precio;unidad\nA1;4,00;caja\n", encoding="utf-8")
    PP.importar_tarifas_proveedor(prov, str(csv), id_empresa=emp)
    b2 = PP.bolsa_precios("A1", id_proveedor=prov, id_empresa=emp)
    assert len(b2) == 1 and float(b2[0]["precio"]) == 4.0
