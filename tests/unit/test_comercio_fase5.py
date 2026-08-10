"""
Tests PCD · Fase 5 (RFC-CD-005): Reservation Ledger + reservas + Scheduler + parcialidades.

Verifica el CONTRATO ratificado: ledger append-only (libro contable), estados válidos, las reservas
son el ÚNICO bloqueo del ATP, toda reserva pertenece a una Transacción+Línea (sin huérfanas), TTL vía
capacidades, barrido de caducidades, parcialidades multi-origen y omnicanalidad. Sin mover stock.
"""

import uuid

import pytest

EMP = "T-RSV-A"
COD = "RSV1"


@pytest.fixture()
def art(db):
    """Artículo con stock central y ledger limpio para EMP."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_reservas WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda, "
                    "Stock_central) VALUES (%s,%s,'Reserva Test',1.0,0,10)", (COD, EMP))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_reservas WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


def _rows(db, id_reserva):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado FROM cd_reservas WHERE id_reserva=%s ORDER BY id", (id_reserva,))
        return [(list(r.values())[0] if isinstance(r, dict) else r[0]) for r in cur.fetchall()]


def test_ledger_append_only_y_estados(art, db):
    from src.services.comercio_digital.inventario import reservas as rsv
    tx = str(uuid.uuid4())
    rid = rsv.reservar(tx, COD, 3, "central", tipo="soft", id_linea=1, id_empresa=EMP)
    assert rid and rsv.estado(rid) == "SOFT_CREATED"
    assert rsv.confirmar(rid, id_empresa=EMP) and rsv.estado(rid) == "HARD_CONFIRMED"
    assert rsv.consumir(rid, id_empresa=EMP) and rsv.estado(rid) == "CONSUMED"
    # Append-only: 3 apuntes, nunca se modificó el anterior.
    assert _rows(db, rid) == ["SOFT_CREATED", "HARD_CONFIRMED", "CONSUMED"]
    # Terminal: transición inválida rechazada.
    assert rsv.confirmar(rid, id_empresa=EMP) is False


def test_sin_reservas_huerfanas(art):
    from src.services.comercio_digital.inventario import reservas as rsv
    assert rsv.reservar(None, COD, 1, "central", id_empresa=EMP) is None       # sin id_tx → rechazada
    assert rsv.reservar("", COD, 1, "central", id_empresa=EMP) is None


def test_reserva_es_unico_bloqueo_de_atp(art):
    from src.services.comercio_digital.inventario import availability as av, reservas as rsv
    # Sin reservas: central=10.
    d0 = av.disponibilidad(COD, 5, id_empresa=EMP, id_tienda=None)
    central0 = next(b for b in d0["buckets"] if b["bucket"] == "central")
    assert central0["disponible"] == 10 and d0["reservado"] == 0
    # Hard reserve de 4 en central → ATP central = 6.
    tx = str(uuid.uuid4())
    rsv.reservar(tx, COD, 4, "central", tipo="hard", id_linea=1, id_empresa=EMP)
    d1 = av.disponibilidad(COD, 5, id_empresa=EMP, id_tienda=None)
    central1 = next(b for b in d1["buckets"] if b["bucket"] == "central")
    assert central1["disponible"] == 6 and d1["reservado"] == 4
    # Legacy consultar_disponibilidad NO se ve afectado (stock físico crudo, byte-idéntico).
    assert av.consultar_disponibilidad(COD, id_empresa=EMP, id_tienda=None)["central"] == 10


def test_liberar_devuelve_atp(art):
    from src.services.comercio_digital.inventario import availability as av, reservas as rsv
    tx = str(uuid.uuid4())
    rid = rsv.reservar(tx, COD, 4, "central", tipo="hard", id_empresa=EMP)
    assert rsv.liberar(rid, id_empresa=EMP)
    d = av.disponibilidad(COD, 5, id_empresa=EMP, id_tienda=None)
    central = next(b for b in d["buckets"] if b["bucket"] == "central")
    assert central["disponible"] == 10 and d["reservado"] == 0      # RELEASED deja de bloquear


def test_barrido_de_caducidades(art):
    from src.services.comercio_digital.inventario import reservas as rsv
    tx = str(uuid.uuid4())
    rid = rsv.reservar(tx, COD, 2, "central", tipo="soft", ttl_min=-1, id_empresa=EMP)  # ya vencida
    assert rsv.reservado(COD, EMP) == 2
    n = rsv.barrer_expiradas(EMP)
    assert n == 1 and rsv.estado(rid) == "EXPIRED" and rsv.reservado(COD, EMP) == 0


def test_omnicanal_mismo_ledger(art):
    from src.services.comercio_digital.inventario import reservas as rsv
    tx1, tx2 = str(uuid.uuid4()), str(uuid.uuid4())
    rsv.reservar(tx1, COD, 2, "central", tipo="hard", id_empresa=EMP, canal="web")
    rsv.reservar(tx2, COD, 3, "central", tipo="soft", id_empresa=EMP, canal="tpv")
    # Distinto canal, MISMO ledger → ambas cuentan.
    assert rsv.reservado(COD, EMP, "central") == 5


def test_parcialidades_y_reservar_desde_plan(art, db):
    from src.services.comercio_digital.inventario import fulfillment as ff, reservas as rsv
    # Disponibilidad que exige 2 orígenes para cubrir 12 (central 8 + otras 5).
    disp = {"codigo": COD, "cantidad_solicitada": 12, "buckets": [
        {"bucket": "central", "ubicacion": "central", "disponible": 8, "eta_dias": 0},
        {"bucket": "otras_tiendas", "ubicacion": "TND-2", "id_tienda": 2, "disponible": 5,
         "eta_dias": 0}]}
    plan = ff.planificar(disp, estrategia="equilibrado")
    assert len(plan.asignaciones) == 2 and plan.cubre is True
    assert sum(a["cantidad"] for a in plan.asignaciones) == 12       # parcialidad multi-origen
    # reservar_desde_plan crea una reserva por asignación (todas ligadas a la misma transacción).
    tx = str(uuid.uuid4())
    ids = rsv.reservar_desde_plan(tx, plan, tipo="hard", id_linea=1, id_empresa=EMP)
    assert len(ids) == 2
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT id_tx FROM cd_reservas WHERE id_empresa=%s", (EMP,))
        assert [(list(r.values())[0] if isinstance(r, dict) else r[0]) for r in cur.fetchall()] == [tx]


def test_ttl_por_defecto_soft_y_hard(art, db):
    from src.services.comercio_digital.inventario import reservas as rsv
    tx = str(uuid.uuid4())
    rsv.reservar(tx, COD, 1, "central", tipo="soft", id_empresa=EMP)
    rsv.reservar(tx, COD, 1, "central", tipo="hard", id_empresa=EMP)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT tipo, TIMESTAMPDIFF(MINUTE, NOW(), ttl_expira) FROM cd_reservas "
                    "WHERE id_empresa=%s ORDER BY id", (EMP,))
        ttls = {(list(r.values())[0] if isinstance(r, dict) else r[0]):
                (list(r.values())[1] if isinstance(r, dict) else r[1]) for r in cur.fetchall()}
    assert 25 <= ttls["soft"] <= 30                    # ~30 min
    assert 2870 <= ttls["hard"] <= 2880                # ~48 h


def test_reservas_solo_capacidades_no_kardex(art):
    """El ledger no mueve stock ni toca el Kárdex; TTL/Scheduler via capacidades (no import directo)."""
    import inspect
    from src.services.comercio_digital.inventario import reservas as rsv
    src = inspect.getsource(rsv)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for prohibido in ("from src.services.rules", "from src.services.scheduler", "kardex"):
        assert not any(prohibido in l for l in imports), f"reservas acopla a {prohibido}"
    assert "capabilities" in src
    d = rsv.descriptor()
    assert d["unico_bloqueo_atp"] and d["mueve_stock"] is False and d["toca_kardex"] is False
