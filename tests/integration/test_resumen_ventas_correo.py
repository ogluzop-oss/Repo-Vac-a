"""Resumen de ventas → Correo interno con adjunto PDF. `db`.

Verifica: (1) correo.buzon_de_usuario resuelve el buzón personal de un perfil (y hace fallback al primer
buzón de la empresa); (2) guardar_recibido con adjunto persiste el correo + su adjunto (la vía que usa
"Enviar por Correo" del Resumen de Ventas).
"""

import pytest

pytestmark = pytest.mark.db


def test_buzon_de_usuario_y_adjunto(db, fab):
    from src.db import empresa as EMP
    from src.db import correo as CORREO

    emp = fab.empresa("EMP resumen correo")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM correos_adjuntos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM correos_recibidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM correos_corporativos WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    # Sin buzones aún → None.
    assert CORREO.buzon_de_usuario(7, id_empresa=emp) is None

    # Buzón de EMPRESA (sin usuario) → fallback lo resuelve para cualquier perfil.
    bz_emp = CORREO.crear_correo("general@empresa.test", id_empresa=emp)
    assert CORREO.buzon_de_usuario(7, id_empresa=emp) == bz_emp     # fallback

    # Buzón PERSONAL del perfil 7 → tiene prioridad sobre el de empresa.
    bz7 = CORREO.crear_correo("ana@empresa.test", id_usuario=7, id_empresa=emp)
    assert CORREO.buzon_de_usuario(7, id_empresa=emp) == bz7

    # Entrega del resumen con adjunto PDF a la bandeja del perfil.
    rid = CORREO.guardar_recibido(bz7, "Smart Manager · Ventas", "📊 Resumen de ventas",
                                  "Adjunto el resumen.", message_id="resumen-test-1",
                                  adjuntos=[{"nombre": "Resumen.pdf", "ruta": "/tmp/Resumen.pdf"}],
                                  id_empresa=emp)
    assert rid
    recibidos = CORREO.listar_recibidos(id_correo=bz7, id_empresa=emp)
    assert any("resumen de ventas" in (r.get("asunto") or "").lower() for r in recibidos)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM correos_adjuntos WHERE id_correo_recibido=%s", (rid,))
        assert int(cur.fetchone()[0]) == 1
