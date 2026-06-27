"""Credito y riesgo — scoring, evaluacion de operacion (limite/bloqueo/aprobacion), alertas, RBAC."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def _cliente(db, limite=0):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO clientes (nombre, id_empresa, estado, limite_credito) VALUES (%s,%s,'activo',%s)",
                    ("CliCred", E, limite))
        cid = cur.lastrowid
        conn.commit()
    return cid


@pytest.fixture
def limpia(db):
    creados = []
    yield creados
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("credit_scoring", "alertas_credito", "bloqueos_credito"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        for cid in creados:
            cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def test_scoring(db, limpia):
    from src.services.finanzas import credito
    cid = _cliente(db, limite=5000); limpia.append(cid)
    sc = credito.calcular_score(cid, id_empresa=E)
    assert 0 <= sc["score"] <= 100 and sc["nivel_riesgo"] in ("bajo", "medio", "alto", "critico")
    assert isinstance(sc["explicacion"], list)


def test_evaluar_operacion_limite(db, limpia):
    from src.services.finanzas import credito
    cid = _cliente(db, limite=1000); limpia.append(cid)
    assert credito.evaluar_operacion(cid, 500, id_empresa=E)["decision"] == "permitido"
    # supera limite sin impagos -> requiere aprobacion
    assert credito.evaluar_operacion(cid, 5000, id_empresa=E)["decision"] == "requiere_aprobacion"


def test_bloqueo(db, limpia):
    from src.services.finanzas import credito
    cid = _cliente(db, limite=1000); limpia.append(cid)
    assert credito.bloquear(cid, motivo="impago", id_empresa=E)
    assert credito.bloqueo_activo(cid, id_empresa=E)
    assert credito.evaluar_operacion(cid, 100, id_empresa=E)["decision"] == "bloqueado"
    assert credito.desbloquear(cid, id_empresa=E)
    assert credito.bloqueo_activo(cid, id_empresa=E) is False


def test_alertas(db, limpia):
    from src.services.finanzas import credito
    cid = _cliente(db, limite=100); limpia.append(cid)
    credito.evaluar_operacion(cid, 9999, id_empresa=E)   # genera alerta limite_superado
    assert any(a["id_cliente"] == cid for a in credito.listar_alertas(id_empresa=E))


def test_rbac_finanzas(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN "
                    "('finanzas.ver','presupuestos.gestionar','financiacion.gestionar','credito.gestionar')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"finanzas.ver", "presupuestos.gestionar", "financiacion.gestionar", "credito.gestionar"} <= enc
