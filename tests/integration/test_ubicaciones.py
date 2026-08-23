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


def test_asignar_almacen_escribe_columnas_almacen(db, fab):
    """La asignación de ALMACÉN escribe articulos.ubicacion_almacen y las columnas
    pasillo_almacen/estanteria_almacen (antes escribía en las lineales → invisible para el GPS)."""
    cod = fab.articulo()
    fab.al_limpiar(lambda: _limpia_ubi(db, codigo_articulo=cod))

    res = U.asignar_ubicacion(cod, "ALM7", "ESTA7", "3", es_lineal=False)
    assert res["ok"] is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT ubicacion_almacen FROM articulos WHERE codigo=%s", (cod,))
        r = cur.fetchone()
        assert (r[0] if not isinstance(r, dict) else r["ubicacion_almacen"]) == "ALM7-ESTA7-3"
        cur.execute("SELECT pasillo_almacen, estanteria_almacen, pasillo, estanteria "
                    "FROM ubicaciones WHERE codigo_articulo=%s", (cod,))
        pa, ea, p, e = cur.fetchone()
        assert (pa, ea) == ("ALM7", "ESTA7")
        assert not p and not e   # NO se tocan las columnas lineales


def test_estanterias_registradas_por_ambito(db, fab):
    """estanterias_registradas separa lineal (pasillo/estanteria) de almacén (pasillo_almacen/…)."""
    c1, c2 = fab.articulo(), fab.articulo()
    fab.al_limpiar(lambda: (_limpia_ubi(db, codigo_articulo=c1), _limpia_ubi(db, codigo_articulo=c2)))
    U.asignar_ubicacion(c1, "PL10", "EL10", "1", es_lineal=True)
    U.asignar_ubicacion(c2, "PA20", "EA20", "1", es_lineal=False)

    lineal = U.estanterias_registradas("LINEAL")
    almacen = U.estanterias_registradas("ALMACEN")
    assert ("PL10", "EL10") in lineal and ("PL10", "EL10") not in almacen
    assert ("PA20", "EA20") in almacen and ("PA20", "EA20") not in lineal


def test_estanterias_registradas_todas_combina_ambitos(db, fab):
    """estanterias_registradas_todas junta local + almacén y adjunta el EPC del nodo si está ubicada."""
    c1, c2 = fab.articulo(), fab.articulo()
    epc = "EST-TODAS-0001"
    fab.al_limpiar(lambda: (_limpia_ubi(db, codigo_articulo=c1),
                            _limpia_ubi(db, codigo_articulo=c2), _limpia_ubi(db, epc=epc)))
    _limpia_ubi(db, epc=epc)
    U.asignar_ubicacion(c1, "PLT1", "ELT1", "1", es_lineal=True)
    U.asignar_ubicacion(c2, "PAT2", "EAT2", "1", es_lineal=False)
    # Ubicar la estantería lineal → su nodo tiene EPC.
    U.flush_iconos([{"epc": epc, "pasillo": "PLT1", "estanteria": "ELT1", "ambito": "LINEAL",
                     "planta_index": 0, "mapa_x": 5, "mapa_y": 6, "real_x": 0.5, "real_y": 0.6}])

    todas = U.estanterias_registradas_todas()
    idx = {(p, e, a): epc_ for (p, e, a, epc_) in todas}
    assert ("PLT1", "ELT1", "LINEAL") in idx and idx[("PLT1", "ELT1", "LINEAL")] == epc  # con EPC
    assert ("PAT2", "EAT2", "ALMACEN") in idx and idx[("PAT2", "EAT2", "ALMACEN")] is None  # sin ubicar

    # El selector RFID solo lista las UBICADAS (con etiqueta/EPC): la ubicada sí, la no-ubicada no.
    ubic = {(p, e, a): epc_ for (p, e, a, epc_) in U.estanterias_ubicadas()}
    assert ("PLT1", "ELT1", "LINEAL") in ubic and ubic[("PLT1", "ELT1", "LINEAL")] == epc
    assert ("PAT2", "EAT2", "ALMACEN") not in ubic


def test_propagacion_estanteria_conecta_gps(db, fab):
    """Flujo end-to-end del arreglo de la desconexión: asignar (sin coords) → ubicar la estantería
    (flush_iconos con su pasillo/estantería/ámbito) → el artículo hereda coordenadas y el GPS las
    resuelve por ámbito."""
    cod = fab.articulo()
    epc = "EST-PROP-0001"
    fab.al_limpiar(lambda: (_limpia_ubi(db, codigo_articulo=cod), _limpia_ubi(db, epc=epc)))
    _limpia_ubi(db, epc=epc)

    # 1) Asignación lineal SIN estantería ubicada aún → sin coordenadas.
    res = U.asignar_ubicacion(cod, "PZ1", "EZ1", "1", es_lineal=True)
    assert res["ok"] is True and res["con_coordenadas"] is False

    # 2) Ubicar la estantería (nodo) con su pasillo/estantería/ámbito → propaga coords al artículo.
    U.flush_iconos([{
        "epc": epc, "pasillo": "PZ1", "estanteria": "EZ1", "ambito": "LINEAL",
        "planta_index": 9987, "mapa_x": 111, "mapa_y": 222, "real_x": 1.1, "real_y": 2.2,
    }])

    # El nodo resuelve coordenadas por ámbito…
    coord = U.coords_de_estanteria("PZ1", "EZ1", "LINEAL")
    assert coord is not None and int(coord[0]) == 111 and int(coord[1]) == 222
    # …y el artículo ya asignado heredó las coordenadas (conexión con el GPS).
    cx, cy = U.coords_por_articulo(cod)
    assert int(cx) == 111 and int(cy) == 222
    assert cod in U.articulos_ubicados()

    # El selector sigue mostrando la estantería aunque ya esté ubicada (la GUI pedirá confirmación
    # para actualizar sus coordenadas al re-seleccionarla).
    assert ("PZ1", "EZ1") in U.estanterias_registradas("LINEAL")
    # ubicacion_texto_articulo devuelve la cadena legible del ámbito (para el aviso de cambio).
    assert U.ubicacion_texto_articulo(cod, es_lineal=True) == "PZ1-EZ1-1"
    assert U.ubicacion_texto_articulo(cod, es_lineal=False) is None

    # La confirmación de re-ubicación se basa en un NODO real (no en coords heredadas del artículo).
    assert U.estanteria_tiene_nodo("PZ1", "EZ1", "LINEAL") is True

    # Al eliminar el nodo, se borran también las coordenadas heredadas por el artículo, y ya NO hay nodo.
    assert U.eliminar_estanteria_por_epc(epc) is True
    assert U.estanteria_tiene_nodo("PZ1", "EZ1", "LINEAL") is False
    cx2, cy2 = U.coords_por_articulo(cod)
    assert int(cx2) == 0 and int(cy2) == 0


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
