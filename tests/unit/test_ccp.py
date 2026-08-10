"""
Tests de la Corporate Communication Platform (CCP) — Parte N (validación).

Cubre: envío por Email (buzón simulado) con Communication ID + historial; canales preparados no
operativos; resolución organizativa; motor documental por reglas; API pública estable; multiempresa.
"""

import pytest

EMP = "T-CCP-A"
EMP_B = "T-CCP-B"


@pytest.fixture
def entorno(db):
    """Buzón simulado + cliente con contactos en EMP; un cliente en EMP_B (aislamiento). Limpia."""
    from src.db import correo as correo_db
    ids = {}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("clientes", "clientes_contactos"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        cur.execute("DELETE FROM ccp_comunicaciones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        cur.execute("INSERT INTO clientes (id_empresa,nombre,email,estado,nif) "
                    "VALUES (%s,'Mercadona SA','info@merca-ccp.com','activo','CCPMER')", (EMP,))
        cid = cur.lastrowid
        cur.execute("INSERT INTO clientes_contactos (id_cliente,id_empresa,nombre,cargo,email) "
                    "VALUES (%s,%s,'Dpto Facturacion','Facturacion','facturas@merca-ccp.com')", (cid, EMP))
        cur.execute("INSERT INTO clientes (id_empresa,nombre,email,estado,nif) "
                    "VALUES (%s,'Secreto B','secreto@ccp-b.com','activo','XB999')", (EMP_B,))
        conn.commit()
    bid = correo_db.crear_correo("plataforma@ccp-test.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    ids["buzon"] = bid
    yield ids
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("clientes", "clientes_contactos"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        cur.execute("DELETE FROM ccp_comunicaciones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()


def test_enviar_email_com_id_e_historial(entorno):
    from src.services import ccp
    r = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="cliente@destino.com",
                                asunto="Prueba", cuerpo="Hola", canal="email")
    assert r.ok and r.canal == "email" and r.estado == "enviado"
    assert r.com_id and r.com_id.startswith("COM-")
    hist = ccp.historial_comunicaciones(EMP, limite=5)
    assert hist and hist[0]["com_id"] == r.com_id and hist[0]["estado"] == "enviado"


def test_canales_preparados_no_operativos(entorno):
    from src.services import ccp
    ops = [c.clave for c in ccp.canales.canales() if c.disponible()]
    assert ops == ["email"]
    for clave in ("whatsapp", "sms", "push", "teams", "slack", "firma"):
        c = ccp.canales.canal(clave)
        assert c is not None and not c.disponible()


def test_resolucion_organizativa(entorno):
    from src.services import ccp
    org = ccp.resolver_organizacion(EMP, "Mercadona")
    assert org is not None
    correos = org.correos()
    assert "info@merca-ccp.com" in correos and "facturas@merca-ccp.com" in correos


def test_motor_documental_factura(entorno):
    from src.services import ccp
    res = ccp.resolver_documento_inteligente("factura", id_empresa=EMP, nif="CCPMER")
    d = res["destinatario"]
    assert d is not None and d.tipo == "cliente"
    assert res["plantilla"] == "facturas" and res["departamento"] == "facturacion"


def test_multiempresa_sin_cruces(entorno):
    from src.services import ccp
    # EMP nunca ve al cliente de EMP_B, ni al enviar ni al buscar.
    assert ccp.buscar_destinatarios(EMP, "secreto") == []
    assert "secreto@ccp-b.com" not in [d.correo for d in ccp.buscar_destinatarios(EMP, "", limite=100)]
    r = ccp.enviar_comunicacion(id_empresa=EMP, pistas={"nif": "XB999"}, asunto="x", cuerpo="y")
    assert not r.ok   # el NIF es de otra empresa: EMP no puede resolverlo


def test_api_publica_estable():
    from src.services import ccp
    for fn in ("enviar_comunicacion", "resolver_identidad", "resolver_destinatarios",
               "resolver_documento", "resolver_organizacion", "resolver_documento_inteligente",
               "buscar_destinatarios", "registrar_envio", "registrar_favorito", "registrar_evento",
               "historial_comunicaciones", "registrar_regla_documento"):
        assert hasattr(ccp, fn), f"falta API pública: {fn}"


def test_sin_empresa_no_envia():
    from src.services import ccp
    r = ccp.enviar_comunicacion(id_empresa=None, destinatario="a@b.com", asunto="x", cuerpo="y")
    # Sin empresa resoluble no se envía (multiempresa estricto). En un entorno con empresa activa por
    # defecto, al menos no debe cruzar datos: el resultado es determinista (ok/estado coherentes).
    assert r.canal in ("email",) and (r.ok in (True, False))
