"""Fase 3 · cliente fino — capa de datos `db/ubicaciones` (mapa de tienda + ubicaciones de artículos).

Verifica que las funciones extraídas de `gui/ubicacion_tienda` operan sobre `configuracion_mapa` y
`ubicaciones` con la misma semántica que el SQL inline original. BD de pruebas (`*_test`).
"""

import pytest

from src.db import ubicaciones as U

pytestmark = pytest.mark.db

PLANTA = 9987  # índice de planta improbable en la semilla, aislado para estos tests


def _limpia_planta(db, planta):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM configuracion_mapa WHERE planta_index=%s", (planta,))
        conn.commit()


def _limpia_ubi(db, **filtros):
    campo, valor = next(iter(filtros.items()))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM ubicaciones WHERE {campo}=%s", (valor,))
        conn.commit()


# ── configuracion_mapa (plano) ────────────────────────────────────────────────
def test_ciclo_plano_configuracion_mapa(db, fab):
    fab.al_limpiar(lambda: _limpia_planta(db, PLANTA))
    _limpia_planta(db, PLANTA)

    assert U.existe_planta(PLANTA) is False

    # Registrar plano (carga de imagen)
    assert U.registrar_plano(PLANTA, "plano.png", "NAVE NORTE", "ALMACEN") is True
    assert U.existe_planta(PLANTA) is True
    assert U.plano_info(PLANTA) == ("ALMACEN", "NAVE NORTE")
    tipo, titulo, ruta = U.plano_info_completo(PLANTA)
    assert (tipo, titulo, ruta) == ("ALMACEN", "NAVE NORTE", "plano.png")
    assert U.ruta_imagen(PLANTA) == "plano.png"
    assert PLANTA in U.plantas_con_imagen()
    assert U.max_planta_con_imagen() >= PLANTA

    # Calibración → esta_calibrada True + config_plano
    assert U.esta_calibrada(PLANTA) is False
    assert U.guardar_calibracion(PLANTA, 12.5, 3.0, 4.0, "plano.png") is True
    assert U.esta_calibrada(PLANTA) is True
    cfg = U.config_plano(PLANTA)
    assert cfg is not None and float(cfg[1]) == 12.5 and float(cfg[2]) == 3.0

    # Altura + puntos de infraestructura (round-trip JSON)
    U.guardar_altura(PLANTA, 7.5)
    pts = [{"epc": "S1", "x": 1, "y": 2}, {"epc": "S2", "x": 3, "y": 4}]
    assert U.guardar_puntos_infraestructura(PLANTA, pts) is True
    assert U.puntos_infraestructura(PLANTA) == pts

    # Reset de calibración vuelve a descalibrar
    assert U.reset_calibracion(PLANTA) is True
    assert U.esta_calibrada(PLANTA) is False

    # Eliminar
    assert U.eliminar_planta(PLANTA) is True
    assert U.existe_planta(PLANTA) is False


# ── ubicaciones (puntos de artículo/QR) ───────────────────────────────────────
def test_nodo_qr_y_coordenadas(db, fab):
    cod = fab.articulo()
    fab.al_limpiar(lambda: _limpia_ubi(db, codigo_articulo=cod))

    assert U.upsert_nodo_qr(cod, "P1", "E1", 10.0, 20.0) is True
    mx, my, verificado, pas, est = U.ubicacion_por_articulo(cod)
    assert (float(mx), float(my), int(verificado), pas, est) == (10.0, 20.0, 1, "P1", "E1")
    assert (float(U.coords_por_articulo(cod)[0]), float(U.coords_por_articulo(cod)[1])) == (10.0, 20.0)
    assert cod in U.articulos_ubicados()


def test_satelite_y_eliminar_por_epc(db, fab):
    epc = "SAT-TEST-0001"
    fab.al_limpiar(lambda: _limpia_ubi(db, epc=epc))
    _limpia_ubi(db, epc=epc)

    assert U.upsert_satelite(epc, "Satélite A", 5.0, 6.0, 1.5, 2.5) is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT pasillo, mapa_x FROM ubicaciones WHERE epc=%s", (epc,))
        assert cur.fetchone() is not None

    assert U.eliminar_por_epc(epc) is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM ubicaciones WHERE epc=%s", (epc,))
        assert cur.fetchone() is None


# ── FIX del bug latente: operaciones que antes fallaban por columnas inexistentes ──────────────
def test_asignar_ubicacion_persiste_de_verdad(db, fab):
    """Antes fallaba (articulos.pasillo inexistente) y no persistía nada. Ahora: guarda la cadena
    legible en articulos.ubicacion_tienda y la ubicación estructurada en `ubicaciones`."""
    cod = fab.articulo()
    fab.al_limpiar(lambda: _limpia_ubi(db, codigo_articulo=cod))

    res = U.asignar_ubicacion(cod, "PAS3", "EST3", "2", es_lineal=True)
    assert res["ok"] is True

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT ubicacion_tienda FROM articulos WHERE codigo=%s", (cod,))
        r = cur.fetchone()
        assert (r[0] if not isinstance(r, dict) else r["ubicacion_tienda"]) == "PAS3-EST3-2"
    # fila estructurada en `ubicaciones`
    u = U.ubicacion_por_articulo(cod)
    assert u is not None and u[3] == "PAS3" and u[4] == "EST3"


def test_reportar_incidencia_marca_en_ubicaciones(db, fab):
    cod = fab.articulo()
    fab.al_limpiar(lambda: _limpia_ubi(db, codigo_articulo=cod))
    U.upsert_nodo_qr(cod, "P9", "E9", 1.0, 2.0)

    assert U.reportar_incidencia_ubicacion(cod) is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT incidencia_ubicacion FROM ubicaciones WHERE codigo_articulo=%s", (cod,))
        assert int(cur.fetchone()[0]) == 1
    # el listado admin refleja la incidencia (join con ubicaciones)
    fila = [r for r in U.buscar_articulos_admin(cod) if r[0] == cod]
    assert fila and int(fila[0][2]) == 1


def test_cola_impresion_y_coords_metricas_por_epc(db, fab):
    epc = "EPC-PRINT-0001"
    fab.al_limpiar(lambda: _limpia_ubi(db, epc=epc))
    _limpia_ubi(db, epc=epc)
    # alta de un satélite (impreso=0 por defecto)
    U.upsert_satelite(epc, "SAT", 3.0, 4.0, 0.0, 0.0)

    pendientes = {e[0] for e in U.epcs_sin_imprimir()}
    assert epc in pendientes

    U.marcar_epcs_impresos([epc])
    pendientes2 = {e[0] for e in U.epcs_sin_imprimir()}
    assert epc not in pendientes2

    # coordenadas métricas por EPC
    assert U.actualizar_coords_epc(epc, 30.0, 40.0, 1.25, 2.5) is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT x_metros, y_metros FROM ubicaciones WHERE epc=%s", (epc,))
        r = cur.fetchone()
        assert (float(r[0]), float(r[1])) == (1.25, 2.5)
