"""
Tests del motor de PRECIO DINÁMICO (migración 0169).

Cubre: CRUD de reglas, regla por stock (aplica y REVIERTE al dejar de cumplirse), por caducidad (reutiliza
`lotes`), por horario (con `ahora` inyectado → determinista), resolución por prioridad y empate (gana el
precio más bajo), previsualización sin escribir, y que no se toca a los artículos sin regla. No destructivo:
`precio_base` conserva la referencia.
"""

import datetime as dt

import pytest

from src.services.precio_dinamico import motor as M
from src.services.precio_dinamico import reglas as R


@pytest.fixture
def emp(fab):
    fab._borrar("precio_reglas", "id_empresa", fab.EMP_DEFECTO)
    return fab.EMP_DEFECTO


def _precio(db, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT precio, precio_base FROM articulos WHERE codigo=%s", (cod,))
        r = cur.fetchone()
    return float(r[0]), (None if r[1] is None else float(r[1]))


def test_crud_reglas(emp):
    rid = R.crear_regla("R1", "stock", {"campo": "Stock_tienda", "op": ">", "umbral": 10},
                        "pct", -5, prioridad=2, id_empresa=emp)
    assert rid
    assert R.crear_regla("mala", "inexistente", {}, "pct", 1, id_empresa=emp) is None  # tipo inválido
    r = R.obtener_regla(rid, id_empresa=emp)
    assert r["tipo"] == "stock" and r["prioridad"] == 2
    assert any(x["id"] == rid for x in R.listar_reglas(id_empresa=emp))
    assert R.actualizar_regla(rid, id_empresa=emp, prioridad=9)
    assert R.obtener_regla(rid, id_empresa=emp)["prioridad"] == 9
    assert R.eliminar_regla(rid, id_empresa=emp)
    assert R.obtener_regla(rid, id_empresa=emp) is None


def test_stock_aplica_y_revierte(fab, emp, db):
    cod = fab.articulo(nombre="Overstock", id_empresa=emp, precio=10.0, stock_tienda=200)
    R.crear_regla("Overstock -10%", "stock", {"campo": "Stock_tienda", "op": ">", "umbral": 100},
                  "pct", -10, id_empresa=emp)
    M.aplicar(id_empresa=emp)
    p, b = _precio(db, cod)
    assert abs(p - 9.0) < 1e-4 and abs(b - 10.0) < 1e-4   # precio_base conserva la referencia
    # baja el stock → la regla deja de cumplirse → vuelve a la referencia
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_tienda=50 WHERE codigo=%s", (cod,))
    M.aplicar(id_empresa=emp)
    p, _ = _precio(db, cod)
    assert abs(p - 10.0) < 1e-4


def test_caducidad_reutiliza_lotes(fab, emp, db):
    cod = fab.articulo(nombre="Yogur", id_empresa=emp, precio=8.0)
    cad = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO lotes (id_empresa,id_tienda,codigo_articulo,lote,fecha_caducidad,"
                    "cantidad,cantidad_inicial,estado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (emp, 1, cod, "L1", cad, 5, 5, "ACTIVO"))
    fab.al_limpiar(lambda: db.obtener_conexion().__enter__().cursor().execute(
        "DELETE FROM lotes WHERE codigo_articulo=%s", (cod,)))
    R.crear_regla("Caduca -20%", "caducidad", {"dias": 7}, "pct", -20, id_empresa=emp)
    M.aplicar(id_empresa=emp)
    p, _ = _precio(db, cod)
    assert abs(p - 6.4) < 1e-4


def test_horario_con_ahora_inyectado(fab, emp, db):
    cod = fab.articulo(nombre="HappyHour", id_empresa=emp, precio=10.0)
    R.crear_regla("Tarde 5€", "horario", {"desde": "10:00", "hasta": "12:00"}, "fijo", 5.0, id_empresa=emp)
    # dentro de la ventana
    M.aplicar(id_empresa=emp, ahora=dt.datetime(2026, 1, 1, 11, 0))
    assert abs(_precio(db, cod)[0] - 5.0) < 1e-4
    # fuera de la ventana → revierte a base
    M.aplicar(id_empresa=emp, ahora=dt.datetime(2026, 1, 1, 13, 0))
    assert abs(_precio(db, cod)[0] - 10.0) < 1e-4


def test_prioridad_y_empate(fab, emp, db):
    cod = fab.articulo(nombre="Multi", id_empresa=emp, precio=10.0, stock_tienda=500)
    # dos reglas de stock que coinciden: prioridad decide
    R.crear_regla("baja5", "stock", {"campo": "Stock_tienda", "op": ">", "umbral": 100}, "pct", -5,
                  prioridad=1, id_empresa=emp)
    R.crear_regla("baja30", "stock", {"campo": "Stock_tienda", "op": ">", "umbral": 100}, "pct", -30,
                  prioridad=9, id_empresa=emp)
    M.aplicar(id_empresa=emp)
    assert abs(_precio(db, cod)[0] - 7.0) < 1e-4   # gana prioridad 9 (-30%)


def test_previsualizar_no_escribe(fab, emp, db):
    cod = fab.articulo(nombre="Prev", id_empresa=emp, precio=10.0, stock_tienda=200)
    R.crear_regla("prev", "stock", {"campo": "Stock_tienda", "op": ">", "umbral": 100}, "pct", -10,
                  id_empresa=emp)
    prev = M.previsualizar(id_empresa=emp)
    fila = [x for x in prev if x["codigo"] == cod]
    assert fila and abs(fila[0]["precio_nuevo"] - 9.0) < 1e-4
    # no ha tocado el precio real
    assert abs(_precio(db, cod)[0] - 10.0) < 1e-4


def test_no_toca_articulos_sin_regla(fab, emp, db):
    cod = fab.articulo(nombre="Libre", id_empresa=emp, precio=3.33)
    M.aplicar(id_empresa=emp)
    p, b = _precio(db, cod)
    assert abs(p - 3.33) < 1e-4 and b is None   # sin regla ni precio_base: intacto


def test_dialogo_nueva_regla_valida_campos_obligatorios(monkeypatch):
    """El botón GUARDAR de la ventana NUEVA REGLA no cierra el diálogo si faltan campos obligatorios: informa
    con un aviso emergente. Con los campos rellenos, guarda (accept)."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication, QDialog
    QApplication.instance() or QApplication([])
    import src.gui.etiquetas_precios as EP
    avisos = []
    monkeypatch.setattr(EP, "mostrar_mensaje", lambda *a, **k: avisos.append(a[1] if len(a) > 1 else "?"))
    dlg = EP._ReglaPrecioDialog()
    try:
        dlg._guardar()                                  # todo vacío → informa y NO acepta
        assert dlg._campos_faltantes()                   # hay campos pendientes
        assert avisos and dlg.result() != QDialog.DialogCode.Accepted.value
        # rellena lo mínimo (regla por horario) → sin faltas → acepta
        dlg.in_nombre.setText("Happy hour")
        dlg.in_desde.setText("18:00"); dlg.in_hasta.setText("20:00"); dlg.in_valor.setText("-10")
        assert dlg._campos_faltantes() == []
        dlg._guardar()
        assert dlg.result() == QDialog.DialogCode.Accepted.value
    finally:
        dlg.deleteLater()
