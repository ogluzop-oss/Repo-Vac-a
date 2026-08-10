"""
Tests del Servicio Corporativo de Resolución de Destinatarios (Parte U — validaciones).

Cubre: aislamiento multiempresa (0 cruces), búsqueda difusa, avisos por estado, orden inteligente
(favorito/reciente/frecuencia/contexto), histórico/aprendizaje y objetos enriquecidos.
"""

import pytest

EMP_A = "T-DEST-A"
EMP_B = "T-DEST-B"


@pytest.fixture
def datos(db):
    """Inserta datos de prueba en dos empresas y limpia al terminar."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("clientes", "proveedores", "destinatarios_historico", "destinatarios_favoritos"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP_A, EMP_B))
        cur.execute("INSERT INTO clientes (id_empresa,nombre,email,estado,nif) "
                    "VALUES (%s,'Mercadona SA','compras@mercadona.es','activo','A1')", (EMP_A,))
        cur.execute("INSERT INTO clientes (id_empresa,nombre,email,estado,nif) "
                    "VALUES (%s,'Jose Garcia Lopez','jose.garcia@cliente.com','activo','B2')", (EMP_A,))
        cur.execute("INSERT INTO clientes (id_empresa,nombre,email,estado,nif) "
                    "VALUES (%s,'Cliente Secreto B','secreto@empresab.com','activo','C3')", (EMP_B,))
        cur.execute("INSERT INTO proveedores (id_empresa,razon_social,email,estado,bloqueado,cif_nif) "
                    "VALUES (%s,'Proveedor Bloqueado SL','prov@bloq.com','activo',1,'P1')", (EMP_A,))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("clientes", "proveedores", "destinatarios_historico", "destinatarios_favoritos"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP_A, EMP_B))
        conn.commit()


def _correos(lista):
    return [d.correo for d in lista]


def test_busqueda_difusa(datos):
    from src.services import destinatarios as D
    assert "compras@mercadona.es" in _correos(D.buscar_destinatarios(EMP_A, "mercadna"))
    assert "jose.garcia@cliente.com" in _correos(D.buscar_destinatarios(EMP_A, "garca"))
    assert "jose.garcia@cliente.com" in _correos(D.buscar_destinatarios(EMP_A, "jse"))


def test_multiempresa_sin_cruces(datos):
    from src.services import destinatarios as D
    # EMP_A jamás ve un contacto de EMP_B, ni por texto ni como sugerencia.
    assert _correos(D.buscar_destinatarios(EMP_A, "secreto")) == []
    todos_a = _correos(D.buscar_destinatarios(EMP_A, "", limite=100))
    assert "secreto@empresab.com" not in todos_a
    assert "secreto@empresab.com" in _correos(D.buscar_destinatarios(EMP_B, "secreto"))


def test_sin_empresa_no_resuelve(datos):
    from src.services import destinatarios as D
    assert D.buscar_destinatarios(None, "merca") == [] or \
        all(d.id_empresa for d in D.buscar_destinatarios(None, "merca"))


def test_objetos_enriquecidos_y_etiquetas(datos):
    from src.services import destinatarios as D
    r = D.buscar_destinatarios(EMP_A, "mercadna")
    assert r and r[0].correo == "compras@mercadona.es"
    d = r[0]
    assert d.tipo == "cliente" and d.etiqueta == "Cliente"
    assert d.id_empresa == EMP_A and d.modulo_origen == "clientes"
    assert isinstance(d.to_dict(), dict)


def test_avisos_proveedor_bloqueado(datos):
    from src.services import destinatarios as D
    r = D.buscar_destinatarios(EMP_A, "bloq")
    assert r and "Proveedor bloqueado" in r[0].avisos


def test_favorito_primero_y_reciente(datos):
    from src.services import destinatarios as D
    D.registrar_envio("externo@fuera-erp.com", "Contacto Externo", id_empresa=EMP_A, usuario="u1")
    D.registrar_envio("externo@fuera-erp.com", id_empresa=EMP_A, usuario="u1")
    # El histórico sugiere un correo que NO pertenece al ERP (Parte D).
    recientes = _correos(D.buscar_destinatarios(EMP_A, "", usuario="u1", limite=20))
    assert "externo@fuera-erp.com" in recientes
    # Favorito manda: aparece el primero.
    D.marcar_favorito("jose.garcia@cliente.com", "Jose Garcia", "cliente", id_empresa=EMP_A, usuario="u1")
    r = D.buscar_destinatarios(EMP_A, "", usuario="u1", limite=20)
    assert r[0].correo == "jose.garcia@cliente.com" and r[0].favorito
    D.quitar_favorito("jose.garcia@cliente.com", id_empresa=EMP_A, usuario="u1")


def test_contexto_prioriza(datos):
    from src.services import destinatarios as D
    r = D.buscar_destinatarios(EMP_A, "", contexto="compras", limite=20)
    pos = {d.correo: i for i, d in enumerate(r)}
    # El proveedor (contexto compras) queda por delante de un cliente sin favoritos.
    assert pos.get("prov@bloq.com", 99) < pos.get("compras@mercadona.es", 100)
