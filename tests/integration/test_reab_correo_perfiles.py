"""Reabastecimiento → Correo interno de perfiles (migr 0213). `db`.

Verifica: (1) articulos_bajo_umbral lista los artículos por debajo del umbral; (2) guardar/cargar_schedule
con perfiles; (3) enviar_reabastecimiento_a_perfiles entrega UNA solicitud a la bandeja de Correo del
perfil (correos_recibidos) SIN modificar el stock.
"""

import pytest

pytestmark = pytest.mark.db


def test_reabastecimiento_a_correo(db, fab):
    from src.db import empresa as EMP
    from src.db import articulos as A
    from src.db import reabastecimiento as R
    from src.db import correo as CORREO

    emp = fab.empresa("EMP reab correo")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM reab_config WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM correos_recibidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM correos_corporativos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    # Artículo con stock 3 y umbral 10 → bajo umbral; objetivo 20 → reponer 17.
    assert A.crear_articulo("ARTREAB", "Harina T45", precio=1.0, id_empresa=emp)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_tienda=3, Stock_total=0, Stock_central=0 "
                    "WHERE codigo='ARTREAB' AND id_empresa=%s", (emp,))
        conn.commit()
    R.upsert_config("ARTREAB", 10, 20, id_empresa=emp)

    bajo = R.articulos_bajo_umbral(id_empresa=emp)
    assert len(bajo) == 1 and bajo[0]["codigo"] == "ARTREAB"
    assert bajo[0]["cantidad"] == 17            # objetivo(20) - stock(3)

    # Schedule con perfiles (roundtrip).
    assert R.guardar_schedule("LUN,MIE", 22, 45, perfiles=["7", "9"])
    sch = R.cargar_schedule()
    assert sch["dias"] == "LUN,MIE" and sch["hora"] == 22 and sch["perfiles"] == ["7", "9"]

    # Buzón del perfil 7 + envío informativo → llega a correos_recibidos; el stock NO cambia.
    id_correo = CORREO.crear_correo("resp.logistica@empresa.test", id_usuario=7, id_empresa=emp)
    assert id_correo
    res = R.enviar_reabastecimiento_a_perfiles(["7"], id_empresa=emp)
    assert res["enviados"] == 1 and res["articulos"] == 1
    recibidos = CORREO.listar_recibidos(id_correo=id_correo, id_empresa=emp)
    assert any("reabastecimiento" in (r.get("asunto") or "").lower() for r in recibidos)
    # El stock del artículo NO se ha tocado por enviar la solicitud.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo='ARTREAB' AND id_empresa=%s", (emp,))
        assert int(cur.fetchone()[0]) == 3
