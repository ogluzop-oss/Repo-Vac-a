"""
Calidad — inspecciones (con NC automatica), no conformidades (ciclo), CAPA (cierre -> NC accionada),
auditorias + hallazgos, trazabilidad, KPIs, IA (deteccion anomalias) y RBAC.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


@pytest.fixture
def limpia(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("hallazgos_auditoria", "auditorias_calidad", "acciones_correctivas",
                  "no_conformidades", "inspecciones", "planes_inspeccion"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        conn.commit()


def test_inspeccion_genera_nc(db, limpia):
    from src.services.calidad import inspecciones, no_conformidades
    art = f"Q_{uuid.uuid4().hex[:5]}"
    r = inspecciones.registrar_inspeccion(fase="recepcion", articulo=art, cantidad_inspeccionada=100,
                                          cantidad_rechazada=10, resultado="rechazada", id_empresa=E)
    assert r["ok"] and r["no_conformidad"]
    nc = no_conformidades.obtener(r["no_conformidad"])
    assert nc["estado"] == "abierta" and nc["articulo"] == art
    with pytest.raises(ValueError):
        inspecciones.registrar_inspeccion(resultado="zzz", id_empresa=E)


def test_nc_ciclo(db, limpia):
    from src.services.calidad import no_conformidades as NC
    nid = NC.abrir("Defecto critico", origen="produccion", severidad="alta", id_empresa=E)
    assert nid
    assert NC.cambiar_estado(nid, "en_analisis", id_empresa=E)["ok"]
    assert NC.cambiar_estado(nid, "accionada", id_empresa=E)["ok"]
    assert NC.cambiar_estado(nid, "cerrada", id_empresa=E)["ok"]
    # transicion invalida abierta->cerrada (otra NC)
    nid2 = NC.abrir("Otro", id_empresa=E)
    assert NC.cambiar_estado(nid2, "cerrada", id_empresa=E)["ok"] is False
    with pytest.raises(ValueError):
        NC.cambiar_estado(nid2, "xxx", id_empresa=E)


def test_capa_cierra_nc(db, limpia):
    from src.services.calidad import capa, no_conformidades as NC
    nid = NC.abrir("NC con CAPA", id_empresa=E)
    a1 = capa.crear_accion("Accion 1", id_nc=nid, tipo="correctiva", id_empresa=E)
    a2 = capa.crear_accion("Accion 2", id_nc=nid, tipo="preventiva", id_empresa=E)
    assert a1 and a2
    capa.cambiar_estado(a1, "cerrada", eficacia="eficaz", id_empresa=E)
    assert NC.obtener(nid)["estado"] in ("abierta", "en_analisis")   # aun queda a2 abierta
    capa.cambiar_estado(a2, "cerrada", eficacia="eficaz", id_empresa=E)
    assert NC.obtener(nid)["estado"] == "accionada"                  # todas cerradas -> accionada
    with pytest.raises(ValueError):
        capa.crear_accion("bad", tipo="zzz", id_empresa=E)


def test_auditorias_y_hallazgos(db, limpia):
    from src.services.calidad import auditorias, no_conformidades as NC
    aid = auditorias.planificar("proveedor", "Auditoria X", id_empresa=E)
    assert aid
    h = auditorias.registrar_hallazgo(aid, "No cumple", severidad="alta", generar_nc=True, id_empresa=E)
    assert h["ok"] and h["no_conformidad"]
    assert NC.obtener(h["no_conformidad"])
    assert auditorias.cerrar(aid, resultado="con_hallazgos", id_empresa=E)
    with pytest.raises(ValueError):
        auditorias.planificar("zzz", "bad", id_empresa=E)


def test_kpis_y_anomalias(db, limpia):
    from src.services.calidad import analitica, inspecciones
    # tres articulos: uno con rechazo anomalo
    for art, rech in ((f"OK1_{uuid.uuid4().hex[:4]}", 1), (f"OK2_{uuid.uuid4().hex[:4]}", 1),
                      (f"BAD_{uuid.uuid4().hex[:4]}", 90)):
        inspecciones.registrar_inspeccion(fase="recepcion", articulo=art, cantidad_inspeccionada=100,
                                          cantidad_rechazada=rech, resultado="aceptada",
                                          abrir_nc_si_rechazo=False, id_empresa=E)
    k = analitica.kpis(id_empresa=E)
    assert "tasa_rechazo_pct" in k and k["unidades_inspeccionadas"] == 300
    anom = analitica.deteccion_anomalias(id_empresa=E, factor=1.0)
    assert any("BAD_" in a["articulo"] for a in anom)


def test_trazabilidad_calidad(db, limpia):
    from src.services.calidad import inspecciones, trazabilidad
    art = f"TR_{uuid.uuid4().hex[:5]}"
    inspecciones.registrar_inspeccion(fase="recepcion", articulo=art, cantidad_inspeccionada=5,
                                      resultado="aceptada", id_empresa=E)
    tr = trazabilidad.trazabilidad_articulo(art, id_empresa=E)
    assert "inspecciones" in tr and len(tr["inspecciones"]) == 1


def test_rbac_permisos_calidad(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN "
                    "('mrp.ver','fabricacion.crear','calidad.ver','nc.gestionar','auditorias.gestionar')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"mrp.ver", "fabricacion.crear", "calidad.ver", "nc.gestionar", "auditorias.gestionar"} <= enc
