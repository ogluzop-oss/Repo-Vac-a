"""
Fase B: asistente Enterprise de 5 pasos de Migración de datos (smoke offscreen). Ejerce el flujo real
(sin diálogo de archivo ni modales bloqueantes, que se monkeypatchean) a través de los mismos métodos
que dispara la GUI: cargar fichero → Origen y Entidad → Mapeo de Campos → Simulación y Validaciones
(stage/validate/simulate en background) → confirmar → Carga Definitiva (commit en background, con
progreso) → Resumen, verificando que la carga real llega a `articulos`.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _esperar(cond, *, tick_ms=25, intentos=400):
    """Bombea el bucle de eventos hasta que `cond()` sea verdad (los workers en segundo plano de la
    ventana emiten señales que solo se procesan si el bucle de eventos avanza)."""
    for _ in range(intentos):
        if cond():
            return True
        QTest.qWait(tick_ms)
    return cond()


def test_asistente_flujo_completo(app, fab, db, tmp_path, monkeypatch):
    import src.gui.migracion_gui as MG
    from src.db import empresa as emp_db
    monkeypatch.setattr(MG, "mostrar_mensaje", lambda *a, **k: None)          # evita el modal en headless
    monkeypatch.setattr(MG, "mostrar_confirmacion", lambda *a, **k: True)     # simula "Sí" en la confirmación
    fab._borrar("articulos", "codigo", "IMPGUI-1")
    fab._borrar("stock_tienda", "codigo_articulo", "IMPGUI-1")
    fab._borrar("movimientos_stock", "codigo_articulo", "IMPGUI-1")
    # El asistente exige un centro/tienda conectado (pedido explícito: la migración va SIEMPRE al
    # centro de la sesión activa, nunca a "todos los centros") — se fija uno real para este test.
    tienda_previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(1)

    ruta = tmp_path / "cat.csv"
    ruta.write_text("codigo;nombre;precio;stock\nIMPGUI-1;Producto GUI;2,50;9\n", encoding="utf-8")

    win = MG.MigracionDatosWindow(usuario={"perfil": "ADMINISTRADOR"})
    try:
        asis = win.asistente                                       # pestaña construida en el arranque (lazy)

        # ── Paso 1: Origen y Entidad ─────────────────────────────────────────
        asis.cargar_fichero(str(ruta))
        assert asis._stack.currentIndex() == 0
        assert asis._btn_sig.isEnabled()                            # habilitado tras cargar un origen válido
        assert asis._mapeo_sugerido.get("codigo") == "codigo"

        # ── Paso 1 → 2: Mapeo de Campos (mismo botón "Siguiente" real) ──────
        asis._siguiente()
        assert asis._stack.currentIndex() == 1
        assert asis._combos["codigo"].currentData() == "codigo"      # auto-mapeo correcto
        assert asis._combos["precio"].currentData() == "precio"

        # ── Paso 2 → 3: Simulación y Validaciones (stage+validate+simulate) ─
        asis._siguiente()
        assert asis._stack.currentIndex() == 2
        assert _esperar(lambda: not asis._diagnostico_en_curso), "el diagnóstico no terminó a tiempo"
        assert asis._id_lote, "no se generó lote de staging"
        val = asis._val_resumen
        assert val["validos"] == 1 and val["advertencias"] == 0 and val["errores"] == 0, val
        assert asis._registros_a_importar() == 1

        # ── Paso 3 → 4: confirmación (monkeypatchada) + Carga Definitiva ───
        asis._siguiente()
        assert _esperar(lambda: asis._commit_resultado is not None), "el commit no terminó a tiempo"
        r = asis._commit_resultado
        assert r["confirmados"] == 1 and r["fallidos"] == 0, r
        assert asis._stack.currentIndex() == 4                       # avanzó solo a Resumen

        # Limpieza de las tablas de staging/trabajos que crea esta corrida real.
        fab._borrar("migracion_filas_staging", "id_lote_staging", asis._id_lote)
        fab._borrar("migracion_lotes_staging", "id", asis._id_lote)
        if r.get("id_trabajo"):
            fab._borrar("import_trabajos_errores", "id_trabajo", r["id_trabajo"])
            fab._borrar("import_trabajos", "id", r["id_trabajo"])

        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT nombre, Stock_total FROM articulos WHERE codigo='IMPGUI-1'")
            fila = cur.fetchone()
        assert fila and fila[0] == "Producto GUI" and fila[1] == 9   # cargado por el asistente real
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_tienda, stock FROM stock_tienda WHERE codigo_articulo='IMPGUI-1'")
            fila_st = cur.fetchone()
        # Escribe en el centro de la sesión activa (tienda 1, fijada arriba) — nunca en la tienda
        # por defecto de la empresa ni en "todos los centros".
        assert fila_st and int(fila_st[0]) == 1 and float(fila_st[1]) == 9
    finally:
        emp_db.set_tienda_actual(tienda_previa)
        win.deleteLater()
