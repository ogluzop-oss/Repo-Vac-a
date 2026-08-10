"""
Tests Etapa C0 · Prioridad 1: endurecimiento RBAC comercial.

Verifica que TODOS los permisos comerciales quedan registrados en el catálogo RBAC EXISTENTE (sin
segundo sistema), asignados a los roles del sistema con herencia correcta, sembrables en la tabla
`permisos`, y resolubles por `autorizacion.puede`. Sin romper el catálogo previo.
"""

COMERCIO = ["comercio.ver", "comercio.admin", "comercio.transaccion", "comercio.checkout",
            "comercio.catalogo", "comercio.publicaciones", "comercio.presencia", "comercio.canales",
            "comercio.conexiones", "comercio.sync", "comercio.marketplaces", "comercio.pagos",
            "comercio.logistica", "comercio.campanas", "comercio.feeds", "comercio.automatizacion"]


def test_permisos_comerciales_en_catalogo():
    from src.services.seguridad import catalogo as cat
    for p in COMERCIO:
        assert p in cat.CATALOGO, f"falta {p} en el catálogo RBAC"
    # stock desde TPV ya estaba integrado (no se duplica).
    assert "stock.consultar_desde_tpv" in cat.CATALOGO


def test_roles_del_sistema():
    from src.services.seguridad import catalogo as cat
    admin = cat.permisos_de_perfil("ADMINISTRADOR")
    gerente = cat.permisos_de_perfil("GERENTE")
    operario = cat.permisos_de_perfil("OPERARIO")
    # ADMIN/SUPERADMIN heredan todo por comodín "*".
    assert set(COMERCIO) <= admin
    assert set(COMERCIO) <= cat.permisos_de_perfil("SUPERADMIN")
    # GERENTE gobierna todo el dominio comercial.
    assert set(COMERCIO) <= gerente
    # OPERARIO: operativa de venta, sin administración/sincronización.
    assert "comercio.ver" in operario and "comercio.checkout" in operario
    assert "comercio.admin" not in operario and "comercio.sync" not in operario


def test_resolucion_puede():
    from src.services import autorizacion as az
    assert az.puede({"id": "g", "perfil": "GERENTE"}, "comercio.logistica") is True
    assert az.puede({"id": "o", "perfil": "OPERARIO"}, "comercio.ver") is True
    assert az.puede({"id": "o", "perfil": "OPERARIO"}, "comercio.sync") is False
    assert az.puede({"id": "a", "perfil": "ADMINISTRADOR"}, "comercio.pagos") is True


def test_siembra_en_tabla_permisos(db):
    from src.services.seguridad import catalogo as cat
    cat.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo LIKE 'comercio.%%'")
        cods = {(r["codigo"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
    assert set(COMERCIO) <= cods                     # todos sembrados en el sistema RBAC existente


def test_no_segundo_sistema_de_permisos():
    import inspect

    from src.services.comercio_digital import gobernanza
    from src.services.seguridad import catalogo as cat
    # La PCD consume RBAC por capacidad; sus PERMISOS son un subconjunto del catálogo canónico.
    assert set(gobernanza.PERMISOS) <= set(cat.CATALOGO)
    src = inspect.getsource(gobernanza)
    assert "capabilities" in src and "CREATE TABLE" not in src   # no crea su propia tabla de permisos
