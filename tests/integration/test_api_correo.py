"""
Integración · router `/correo` (REST): bandeja unificada (circulares + encuestas; Gmail no se cubre
aquí — exige un buzón Google conectado vía OAuth real, fuera de alcance de un test de aislamiento),
creación con las 3 formas de destinatario (usuario_id/centro_codigo/email_externo) y autocompletado
de destinatarios — todo tenant-aislado, mismo criterio que `tests/integration/
test_circulares_destinatarios.py` (al que este test complementa, ahora a través de la REST API en
vez de llamar directamente al servicio)."""

import pytest

from src.db import centros as CENTROS

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


def _token(db, fab, nombre, id_empresa=None, email=None):
    u = fab.usuario(nombre=nombre, password="Clave_Api_123456", perfil="ADMINISTRADOR",
                    id_empresa=id_empresa, email=email)
    body = {"usuario": nombre, "password": "Clave_Api_123456"}
    if id_empresa:
        body["id_empresa"] = id_empresa
    from src.backend.app import crear_app
    cli = crear_app().test_client()
    r = cli.post("/api/v1/auth/login", json=body)
    tok = r.get_json()["access"]
    fab.al_limpiar(lambda: _borra_sesiones(db, u["id"]))
    return tok, u


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _borra_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()


@pytest.fixture
def dos_empresas(fab):
    """Dos empresas con usuarios cruzados (todos con email, requisito de `listar_usuarios_empresa`
    desde la migración 0287) — mismo seed que `test_circulares_destinatarios.py::dos_empresas`."""
    emp_a = fab.empresa("EMP API CORREO A")
    emp_b = fab.empresa("EMP API CORREO B")
    para_a = fab.usuario(nombre="API_CORREO_PARA_A", id_empresa=emp_a, email="para.apicorreoa@test.com")
    otro_a = fab.usuario(nombre="API_CORREO_OTRO_A", id_empresa=emp_a, email="otro.apicorreoa@test.com")
    user_b = fab.usuario(nombre="API_CORREO_USER_B", id_empresa=emp_b, email="user.apicorreob@test.com")
    return {"emp_a": emp_a, "emp_b": emp_b, "para_a": para_a, "otro_a": otro_a, "user_b": user_b}


# ── 1. /correo/bandeja: fusiona circulares + encuestas del usuario, tenant-aislado ────────────────

def test_bandeja_requiere_token(cliente):
    assert cliente.get("/api/v1/correo/bandeja").status_code == 401


def test_bandeja_fusiona_circulares_y_encuestas_y_aisla_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_CREADOR_A", id_empresa=d["emp_a"],
                                    email="creador.apicorreoa@test.com")
    # PARA_A ya existe (creado por la fixture `dos_empresas`, no por login): emitimos un token
    # directamente para él en vez de pasar por /auth/login (que exigiría conocer su password).
    from src.seguridad import tokens as TOK
    tok_para_a = TOK.emitir_access({"id": d["para_a"]["id"], "id_empresa": d["emp_a"],
                                    "perfil": "OPERARIO", "nombre": d["para_a"]["nombre"]})
    tok_b, u_b = _token(db, fab, "API_CORREO_CREADOR_B", id_empresa=d["emp_b"],
                        email="creador.apicorreob@test.com")

    from src.services.comunicacion_interna import circulares as C
    from src.services.comunicacion_interna import encuestas as E

    rc = C.crear_circular(
        "Circular API dirigida", "cuerpo",
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
        usuario=u_creador, id_empresa=d["emp_a"])
    assert rc["ok"] is True
    re_ = E.crear_encuesta(
        "Encuesta API dirigida", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
        usuario=u_creador, id_empresa=d["emp_a"])
    assert re_["ok"] is True
    try:
        r = cliente.get("/api/v1/correo/bandeja", headers=_h(tok_para_a))
        assert r.status_code == 200
        filas = r.get_json()
        tipos_ids = {(f["tipo"], f["id"]) for f in filas}
        assert ("circular", rc["id"]) in tipos_ids
        assert ("encuesta", re_["id"]) in tipos_ids

        # Aislamiento: el usuario de la empresa B jamás ve nada de la empresa A.
        r_b = cliente.get("/api/v1/correo/bandeja", headers=_h(tok_b))
        filas_b = r_b.get_json()
        tipos_ids_b = {(f["tipo"], f["id"]) for f in filas_b}
        assert ("circular", rc["id"]) not in tipos_ids_b
        assert ("encuesta", re_["id"]) not in tipos_ids_b
    finally:
        C.eliminar_circular(rc["id"])
        E.eliminar_encuesta(re_["id"])


def test_bandeja_no_muestra_mensaje_no_dirigido_a_otro_usuario_misma_empresa(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_CREADOR_A2", id_empresa=d["emp_a"],
                                    email="creador2.apicorreoa@test.com")
    from src.seguridad import tokens as TOK
    tok_otro_a = TOK.emitir_access({"id": d["otro_a"]["id"], "id_empresa": d["emp_a"],
                                    "perfil": "OPERARIO", "nombre": d["otro_a"]["nombre"]})

    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular(
        "Circular API no dirigida a otro", "cuerpo",
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
        usuario=u_creador, id_empresa=d["emp_a"])
    assert rc["ok"] is True
    try:
        r = cliente.get("/api/v1/correo/bandeja", headers=_h(tok_otro_a))
        ids = {f["id"] for f in r.get_json() if f["tipo"] == "circular"}
        assert rc["id"] not in ids
    finally:
        C.eliminar_circular(rc["id"])


# ── 2. POST /correo/circular y /correo/encuesta: las 3 formas de destinatario ─────────────────────

def test_crear_circular_destinatario_usuario_interno(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok, u = _token(db, fab, "API_CORREO_CREA_U", id_empresa=d["emp_a"],
                    email="crea_u.apicorreoa@test.com")
    r = cliente.post("/api/v1/correo/circular", headers=_h(tok), json={
        "titulo": "Circular usuario interno", "cuerpo": "cuerpo",
        "destinatarios": [{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
    })
    assert r.status_code == 201
    body = r.get_json()
    assert body["ok"] is True
    cid = body["id"]
    from src.services.comunicacion_interna import circulares as C
    try:
        detalle = C.obtener_circular(cid)
        assert str(detalle["id_empresa"]) == str(d["emp_a"])
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert d["para_a"]["id"] in ids_dest
    finally:
        C.eliminar_circular(cid)


def test_crear_circular_destinatario_centro_fanout(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok, u = _token(db, fab, "API_CORREO_CREA_C", id_empresa=d["emp_a"],
                    email="crea_c.apicorreoa@test.com")
    centro = CENTROS.crear_centro(id_empresa=d["emp_a"], nombre_centro="Centro API Correo",
                                  email="centro_api_correo@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro)
    codigo = CENTROS.obtener_centro(centro)["codigo_centro"]
    empleado = fab.usuario(nombre="API_CORREO_EMP_CENTRO", id_empresa=d["emp_a"],
                           centro_codigo=codigo, email="emp_centro.apicorreoa@test.com")

    r = cliente.post("/api/v1/correo/circular", headers=_h(tok), json={
        "titulo": "Circular centro", "cuerpo": "cuerpo",
        "destinatarios": [{"centro_codigo": codigo, "tipo": "PARA"}],
    })
    assert r.status_code == 201
    cid = r.get_json()["id"]
    from src.services.comunicacion_interna import circulares as C
    try:
        detalle = C.obtener_circular(cid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert empleado["id"] in ids_dest
    finally:
        C.eliminar_circular(cid)


def test_crear_encuesta_destinatario_email_externo_sin_buzon(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok, u = _token(db, fab, "API_CORREO_CREA_E", id_empresa=d["emp_a"],
                    email="crea_e.apicorreoa@test.com")
    r = cliente.post("/api/v1/correo/encuesta", headers=_h(tok), json={
        "titulo": "Encuesta externa", "intro": "intro",
        "preguntas": [{"texto": "P1", "tipo": "TEXTO"}],
        "destinatarios": [{"email_externo": "externo_api@cliente.com", "tipo": "PARA"}],
    })
    assert r.status_code == 201
    body = r.get_json()
    assert body["ok"] is True
    # Sin buzón corporativo activo en el entorno de test: el envío externo falla honestamente,
    # pero la encuesta SÍ se crea (mismo comportamiento que el servicio, ver circulares._enviar_externos).
    assert body.get("externos_fallidos") == ["externo_api@cliente.com"]
    from src.services.comunicacion_interna import encuestas as E
    E.eliminar_encuesta(body["id"])


def test_crear_circular_rechaza_sin_para(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok, u = _token(db, fab, "API_CORREO_SINPARA", id_empresa=d["emp_a"],
                    email="sinpara.apicorreoa@test.com")
    r = cliente.post("/api/v1/correo/circular", headers=_h(tok), json={
        "titulo": "Sin para", "cuerpo": "cuerpo",
        "destinatarios": [{"usuario_id": d["otro_a"]["id"], "tipo": "CC"}],
    })
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_crear_circular_filtra_destinatario_de_otra_empresa_via_api(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok, u = _token(db, fab, "API_CORREO_CRUZ", id_empresa=d["emp_a"],
                    email="cruz.apicorreoa@test.com")
    r = cliente.post("/api/v1/correo/circular", headers=_h(tok), json={
        "titulo": "Circular cruzada API", "cuerpo": "cuerpo",
        "destinatarios": [{"usuario_id": d["user_b"]["id"], "tipo": "PARA"}],
    })
    # Único destinatario de otra empresa -> tras filtrar no queda ningún PARA válido.
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


# ── 3. Detalle + reenvío + leído: tenant-checked ──────────────────────────────────────────────────

def test_detalle_circular_tenant_checked(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_DET_A", id_empresa=d["emp_a"],
                        email="det_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_DET_B", id_empresa=d["emp_b"],
                        email="det_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular detalle", "cuerpo", usuario=u_a, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        r_a = cliente.get(f"/api/v1/correo/circular/{cid}", headers=_h(tok_a))
        assert r_a.status_code == 200
        r_b = cliente.get(f"/api/v1/correo/circular/{cid}", headers=_h(tok_b))
        assert r_b.status_code == 404
    finally:
        C.eliminar_circular(cid)


def test_reenviar_y_marcar_leido_circular_via_api(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_REENV_CREADOR", id_empresa=d["emp_a"],
                                    email="reenv_creador.apicorreoa@test.com")
    from src.seguridad import tokens as TOK
    tok_otro_a = TOK.emitir_access({"id": d["otro_a"]["id"], "id_empresa": d["emp_a"],
                                    "perfil": "OPERARIO", "nombre": d["otro_a"]["nombre"]})
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular a reenviar API", "cuerpo",
                          destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                          usuario=u_creador, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        r = cliente.post(f"/api/v1/correo/circular/{cid}/reenviar", headers=_h(tok_creador),
                         json={"destinatarios": [{"usuario_id": d["otro_a"]["id"], "tipo": "PARA"}]})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

        r_leido = cliente.post(f"/api/v1/correo/circular/{cid}/leido", headers=_h(tok_otro_a))
        assert r_leido.status_code == 200
        assert r_leido.get_json()["ok"] is True

        detalle = C.obtener_circular(cid)
        fila = next(x for x in detalle["destinatarios"] if x["usuario_id"] == d["otro_a"]["id"])
        assert fila["leido"] == 1
    finally:
        C.eliminar_circular(cid)


# ── 4. /correo/destinatarios/sugerencias: 3 orígenes, tenant-aislado ──────────────────────────────

def test_sugerencias_destinatarios_tenant_aislado(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_SUG_A", id_empresa=d["emp_a"],
                        email="sug_a.apicorreoa@test.com")

    r = cliente.get("/api/v1/correo/destinatarios/sugerencias?q=API_CORREO_PARA_A",
                    headers=_h(tok_a))
    assert r.status_code == 200
    resultados = r.get_json()
    nombres = {x["texto"] for x in resultados if x["origen"] == "usuario"}
    assert d["para_a"]["nombre"] in nombres

    # Nunca el usuario de la empresa B.
    r2 = cliente.get("/api/v1/correo/destinatarios/sugerencias?q=API_CORREO_USER_B",
                     headers=_h(tok_a))
    nombres2 = {x["texto"] for x in r2.get_json() if x["origen"] == "usuario"}
    assert d["user_b"]["nombre"] not in nombres2


def test_sugerencias_requiere_token(cliente):
    assert cliente.get("/api/v1/correo/destinatarios/sugerencias?q=x").status_code == 401


# ── 5. POST /correo/circular|encuesta/<id>/responder: identidad del token, sin contraseña ─────────

def test_responder_circular_via_api(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_RESP_CREADOR", id_empresa=d["emp_a"],
                                    email="resp_creador.apicorreoa@test.com")
    from src.seguridad import tokens as TOK
    tok_para_a = TOK.emitir_access({"id": d["para_a"]["id"], "id_empresa": d["emp_a"],
                                    "perfil": "OPERARIO", "nombre": d["para_a"]["nombre"]})
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular API responder", "cuerpo",
                          destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                          usuario=u_creador, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        r = cliente.post(f"/api/v1/correo/circular/{cid}/responder", headers=_h(tok_para_a),
                         json={"comentario": "Respuesta vía API"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        detalle = C.obtener_circular(cid)
        assert any(c["comentario"] == "Respuesta vía API" for c in detalle["confirmaciones"])
    finally:
        C.eliminar_circular(cid)


def test_responder_circular_via_api_aisla_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_RESP_CREADOR2", id_empresa=d["emp_a"],
                                    email="resp_creador2.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_RESP_B", id_empresa=d["emp_b"],
                        email="resp_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular API responder cruzada", "cuerpo",
                          usuario=u_creador, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        r = cliente.post(f"/api/v1/correo/circular/{cid}/responder", headers=_h(tok_b),
                         json={"comentario": "intento cruzado"})
        assert r.status_code == 400
        assert r.get_json()["ok"] is False
        detalle = C.obtener_circular(cid)
        assert detalle["confirmaciones"] == []
    finally:
        C.eliminar_circular(cid)


def test_responder_encuesta_via_api(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_RESP_ENC_CREADOR", id_empresa=d["emp_a"],
                                    email="resp_enc_creador.apicorreoa@test.com")
    from src.seguridad import tokens as TOK
    tok_para_a = TOK.emitir_access({"id": d["para_a"]["id"], "id_empresa": d["emp_a"],
                                    "perfil": "OPERARIO", "nombre": d["para_a"]["nombre"]})
    from src.services.comunicacion_interna import encuestas as E
    re_ = E.crear_encuesta("Encuesta API responder", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                          destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                          usuario=u_creador, id_empresa=d["emp_a"])
    eid = re_["id"]
    try:
        detalle = E.obtener_encuesta(eid)
        pid = detalle["preguntas"][0]["id"]
        r = cliente.post(f"/api/v1/correo/encuesta/{eid}/responder", headers=_h(tok_para_a),
                         json={"respuestas": {str(pid): {"texto": "Mi respuesta API"}}})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        detalle2 = E.obtener_encuesta(eid)
        assert len(detalle2["respuestas"]) == 1
    finally:
        E.eliminar_encuesta(eid)


def test_responder_encuesta_via_api_aisla_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_creador, u_creador = _token(db, fab, "API_CORREO_RESP_ENC_CREADOR2", id_empresa=d["emp_a"],
                                    email="resp_enc_creador2.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_RESP_ENC_B", id_empresa=d["emp_b"],
                        email="resp_enc_b.apicorreob@test.com")
    from src.services.comunicacion_interna import encuestas as E
    re_ = E.crear_encuesta("Encuesta API responder cruzada", "intro",
                          [{"texto": "P1", "tipo": "TEXTO"}], usuario=u_creador, id_empresa=d["emp_a"])
    eid = re_["id"]
    try:
        r = cliente.post(f"/api/v1/correo/encuesta/{eid}/responder", headers=_h(tok_b),
                         json={"respuestas": {}})
        assert r.status_code == 400
        assert r.get_json()["ok"] is False
        detalle = E.obtener_encuesta(eid)
        assert detalle["respuestas"] == []
    finally:
        E.eliminar_encuesta(eid)


# ── 6. Las 5 carpetas reales + Enviados: aislamiento tenant en listas Y en acciones cruzadas ───────

def test_carpetas_borradores_y_papelera_aislan_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_CARP_A", id_empresa=d["emp_a"],
                        email="carp_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_CARP_B", id_empresa=d["emp_b"],
                        email="carp_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rb = C.guardar_borrador(titulo="Borrador API", cuerpo="x", usuario=u_a, id_empresa=d["emp_a"])
    assert rb["ok"] is True
    cid = rb["id"]
    try:
        r_a = cliente.get("/api/v1/correo/borradores", headers=_h(tok_a))
        assert r_a.status_code == 200
        ids_a = {f["id"] for f in r_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_a

        r_b = cliente.get("/api/v1/correo/borradores", headers=_h(tok_b))
        ids_b = {f["id"] for f in r_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_b

        # Publicar (para poder papelearla) y mover a papelera vía API.
        rp = C.publicar_borrador(cid, destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                                 usuario=u_a, id_empresa=d["emp_a"])
        assert rp["ok"] is True

        # La empresa B no puede moverla a su papelera.
        r_cross = cliente.post(f"/api/v1/correo/circular/{cid}/papelera", headers=_h(tok_b))
        assert r_cross.status_code == 400

        r_pap = cliente.post(f"/api/v1/correo/circular/{cid}/papelera", headers=_h(tok_a))
        assert r_pap.status_code == 200 and r_pap.get_json()["ok"] is True

        r_pap_a = cliente.get("/api/v1/correo/papelera", headers=_h(tok_a))
        ids_pap_a = {f["id"] for f in r_pap_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_pap_a
        r_pap_b = cliente.get("/api/v1/correo/papelera", headers=_h(tok_b))
        ids_pap_b = {f["id"] for f in r_pap_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_pap_b
    finally:
        C.eliminar_circular(cid)


def test_carpeta_importantes_marcar_via_api_y_aisla_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_IMP_A", id_empresa=d["emp_a"],
                        email="imp_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_IMP_B", id_empresa=d["emp_b"],
                        email="imp_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular API importante", "cuerpo", usuario=u_a, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        # La empresa B no puede marcarla importante.
        r_cross = cliente.post(f"/api/v1/correo/circular/{cid}/importante", headers=_h(tok_b),
                               json={"valor": True})
        assert r_cross.status_code == 400

        r = cliente.post(f"/api/v1/correo/circular/{cid}/importante", headers=_h(tok_a),
                         json={"valor": True})
        assert r.status_code == 200 and r.get_json()["ok"] is True

        r_a = cliente.get("/api/v1/correo/importantes", headers=_h(tok_a))
        ids_a = {f["id"] for f in r_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_a

        r_b = cliente.get("/api/v1/correo/importantes", headers=_h(tok_b))
        ids_b = {f["id"] for f in r_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_b
    finally:
        C.eliminar_circular(cid)


def test_carpetas_programados_aisla_tenant_y_bloquea_cancelacion_cruzada(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_PROG_A", id_empresa=d["emp_a"],
                        email="prog_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_PROG_B", id_empresa=d["emp_b"],
                        email="prog_b.apicorreob@test.com")
    import datetime
    futuro = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cliente.post("/api/v1/correo/circular/programar", headers=_h(tok_a), json={
        "titulo": "Circular programada API", "cuerpo": "cuerpo", "fecha_programada": futuro,
        "destinatarios": [{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    cid = body["id"]
    from src.services.comunicacion_interna import circulares as C
    try:
        r_a = cliente.get("/api/v1/correo/programados", headers=_h(tok_a))
        ids_a = {f["id"] for f in r_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_a
        r_b = cliente.get("/api/v1/correo/programados", headers=_h(tok_b))
        ids_b = {f["id"] for f in r_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_b

        r_cross = cliente.post(f"/api/v1/correo/circular/{cid}/cancelar_programacion", headers=_h(tok_b))
        assert r_cross.status_code == 400
        detalle = C.obtener_circular(cid)
        assert detalle["estado"] == "PROGRAMADA"

        r_ok = cliente.post(f"/api/v1/correo/circular/{cid}/cancelar_programacion", headers=_h(tok_a))
        assert r_ok.status_code == 200 and r_ok.get_json()["ok"] is True
    finally:
        C.eliminar_circular(cid)


def test_carpeta_pospuestos_aisla_tenant_y_bloquea_accion_cruzada(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_POSP_A", id_empresa=d["emp_a"],
                        email="posp_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_POSP_B", id_empresa=d["emp_b"],
                        email="posp_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular API pospuesta", "cuerpo",
                          destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                          usuario=u_a, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        import datetime
        futuro = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        r_cross = cliente.post(f"/api/v1/correo/circular/{cid}/posponer", headers=_h(tok_b),
                               json={"hasta": futuro})
        assert r_cross.status_code == 400

        r_ok = cliente.post(f"/api/v1/correo/circular/{cid}/posponer", headers=_h(tok_a),
                            json={"hasta": futuro})
        assert r_ok.status_code == 200 and r_ok.get_json()["ok"] is True

        r_a = cliente.get("/api/v1/correo/pospuestos", headers=_h(tok_a))
        ids_a = {f["id"] for f in r_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_a
        r_b = cliente.get("/api/v1/correo/pospuestos", headers=_h(tok_b))
        ids_b = {f["id"] for f in r_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_b
    finally:
        C.eliminar_circular(cid)


def test_carpeta_enviados_aisla_tenant(db, fab, cliente, dos_empresas):
    d = dos_empresas
    tok_a, u_a = _token(db, fab, "API_CORREO_ENV_A", id_empresa=d["emp_a"],
                        email="env_a.apicorreoa@test.com")
    tok_b, u_b = _token(db, fab, "API_CORREO_ENV_B", id_empresa=d["emp_b"],
                        email="env_b.apicorreob@test.com")
    from src.services.comunicacion_interna import circulares as C
    rc = C.crear_circular("Circular API enviada", "cuerpo", usuario=u_a, id_empresa=d["emp_a"])
    cid = rc["id"]
    try:
        r_a = cliente.get("/api/v1/correo/enviados", headers=_h(tok_a))
        ids_a = {f["id"] for f in r_a.get_json() if f["tipo"] == "circular"}
        assert cid in ids_a
        r_b = cliente.get("/api/v1/correo/enviados", headers=_h(tok_b))
        ids_b = {f["id"] for f in r_b.get_json() if f["tipo"] == "circular"}
        assert cid not in ids_b
    finally:
        C.eliminar_circular(cid)
