"""
Destinatarios reales (Para/CC/Cco) y reenvío de circulares/encuestas internas — migración 0286
(`com_destinatarios`). Cubre, sobre todo, el aislamiento MULTIEMPRESA: ni `listar_usuarios_empresa`
(fuente única de sugerencias Para/CC/Cco) ni `listar_circulares`/`listar_encuestas(usuario_id=...)`
ni `reenviar_circular`/`reenviar_encuesta` pueden filtrar usuarios/mensajes de otra empresa.

También cubre, desde la extensión de Para/CC/Cco a 3 orígenes (usuario interno por EMAIL — migración
0287 —, centro de trabajo con fan-out, contacto externo con histórico): `listar_usuarios_empresa`
excluyendo usuarios sin email, `listar_centros_empresa`/`listar_contactos_externos` (aislamiento
tenant) y la expansión `centro_codigo` -> empleados en `crear_circular`/`reenviar_circular`
(y el mismo núcleo para encuestas), con especial atención a que un `codigo_centro` COINCIDENTE entre
dos empresas (autogenerado independientemente, p. ej. "CDT-001" en ambas) jamás haga fan-out cruzado.
"""

import pytest

from src.db import centros as CENTROS
from src.db.conexion import obtener_conexion
from src.services.comunicacion_interna import circulares as C
from src.services.comunicacion_interna import encuestas as E
from src.services.comunicacion_interna.usuarios_internos import (
    listar_centros_empresa, listar_contactos_externos, listar_usuarios_empresa)
from src.services.destinatarios import historico as HIST

pytestmark = pytest.mark.db


@pytest.fixture
def dos_empresas(fab):
    """Dos empresas con usuarios cruzados, para los tests de aislamiento. Todos con EMAIL (migración
    0287): desde que `listar_usuarios_empresa` exige email, un usuario sin él no sería sugerible."""
    emp_a = fab.empresa("EMP A COM")
    emp_b = fab.empresa("EMP B COM")
    creador = fab.usuario(nombre="CREADOR_COM_A", id_empresa=emp_a, email="creador.coma@test.com")
    para_a = fab.usuario(nombre="PARA_COM_A", id_empresa=emp_a, email="para.coma@test.com")
    cc_a = fab.usuario(nombre="CC_COM_A", id_empresa=emp_a, email="cc.coma@test.com")
    otro_a = fab.usuario(nombre="OTRO_COM_A", id_empresa=emp_a,   # misma empresa, sin relación
                         email="otro.coma@test.com")
    user_b = fab.usuario(nombre="USER_COM_B", id_empresa=emp_b, email="user.comb@test.com")
    return {
        "emp_a": emp_a, "emp_b": emp_b, "creador": creador, "para_a": para_a,
        "cc_a": cc_a, "otro_a": otro_a, "user_b": user_b,
    }


# ── 1. listar_usuarios_empresa: aislamiento estricto (fuente única de Para/CC/Cco) ───────────────

def test_listar_usuarios_empresa_nunca_cruza_compania(dos_empresas):
    d = dos_empresas
    res_a = listar_usuarios_empresa(d["emp_a"])
    nombres_a = {u["nombre"] for u in res_a}
    assert d["para_a"]["nombre"] in nombres_a
    assert d["user_b"]["nombre"] not in nombres_a

    res_b = listar_usuarios_empresa(d["emp_b"])
    nombres_b = {u["nombre"] for u in res_b}
    assert d["user_b"]["nombre"] in nombres_b
    assert d["para_a"]["nombre"] not in nombres_b
    assert d["creador"]["nombre"] not in nombres_b

    # Sin id_empresa: jamás "todos" — lista vacía.
    assert listar_usuarios_empresa(None) == []


def test_listar_usuarios_empresa_filtro_texto_y_exclusion(dos_empresas):
    d = dos_empresas
    emp_a = d["emp_a"]
    res = listar_usuarios_empresa(emp_a, "PARA_COM_A")
    assert {u["nombre"] for u in res} == {d["para_a"]["nombre"]}

    res2 = listar_usuarios_empresa(emp_a, excluir_id=d["para_a"]["id"])
    nombres2 = {u["nombre"] for u in res2}
    assert d["para_a"]["nombre"] not in nombres2
    assert d["cc_a"]["nombre"] in nombres2


# ── 2. crear_circular con destinatarios: validación + filas com_destinatarios ────────────────────

def test_crear_circular_rechaza_sin_destinatario_para(dos_empresas):
    d = dos_empresas
    antes = len(C.listar_circulares(id_empresa=d["emp_a"]))
    r = C.crear_circular("Sin para", "cuerpo",
                         destinatarios=[{"usuario_id": d["cc_a"]["id"], "tipo": "CC"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is False
    assert "para" in r["error"].lower()
    # No se creó ninguna fila (ni circular ni destinatarios).
    assert len(C.listar_circulares(id_empresa=d["emp_a"])) == antes


def test_crear_circular_con_destinatarios_vacio_preserva_difusion_legacy(dos_empresas):
    """destinatarios=[] (vacío, no None) NO se rechaza: se trata como "no especificado"."""
    d = dos_empresas
    r = C.crear_circular("Legacy por lista vacía", "cuerpo", destinatarios=[],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}
    finally:
        C.eliminar_circular(cid)


def test_crear_circular_con_destinatarios_targetea_y_lista_por_usuario(dos_empresas):
    d = dos_empresas
    r = C.crear_circular(
        "Circular dirigida", "cuerpo",
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"},
                       {"usuario_id": d["cc_a"]["id"], "tipo": "CC"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        # Visible para el destinatario PARA, para el CC, y para el creador.
        for uid in (d["para_a"]["id"], d["cc_a"]["id"], int(d["creador"]["id"])):
            ids = {c["id"] for c in C.listar_circulares(id_empresa=d["emp_a"], usuario_id=uid)}
            assert cid in ids, f"no visible para usuario_id={uid}"
        # NO visible para un usuario de la MISMA empresa sin relación con la circular.
        ids_otro = {c["id"] for c in
                   C.listar_circulares(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}
        assert cid not in ids_otro
        # El visor expone los destinatarios resueltos.
        detalle = C.obtener_circular(cid)
        tipos = {(x["usuario_id"], x["tipo"]) for x in detalle["destinatarios"]}
        assert (d["para_a"]["id"], "PARA") in tipos
        assert (d["cc_a"]["id"], "CC") in tipos
    finally:
        C.eliminar_circular(cid)


def test_crear_circular_filtra_destinatario_de_otra_empresa(dos_empresas):
    """Regresión: `crear_circular` NUNCA debe confiar en que el llamador ya filtró los
    `usuario_id` por empresa — la frontera de seguridad real es esta función (igual que ya hacía
    `reenviar_circular`), no solo la GUI. Un destinatario de otra empresa mezclado con uno válido
    se descarta en silencio; si tras filtrar no queda ningún PARA, no se crea nada."""
    d = dos_empresas
    # Mezclado: un PARA válido (misma empresa) + un CC de OTRA empresa → se crea, pero el de
    # otra empresa NUNCA llega a com_destinatarios.
    r = C.crear_circular(
        "Circular mixta", "cuerpo",
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"},
                       {"usuario_id": d["user_b"]["id"], "tipo": "CC"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        detalle = C.obtener_circular(cid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert d["para_a"]["id"] in ids_dest
        assert d["user_b"]["id"] not in ids_dest, "un usuario de OTRA empresa no debe quedar registrado"
        # El usuario de la otra empresa tampoco debe ver la circular en su propia bandeja.
        ids_b = {c["id"] for c in C.listar_circulares(id_empresa=d["emp_b"], usuario_id=d["user_b"]["id"])}
        assert cid not in ids_b
    finally:
        C.eliminar_circular(cid)
    # Solo-cruzada: el ÚNICO destinatario es de otra empresa → tras filtrar no queda ningún PARA
    # válido → no se crea la circular en absoluto.
    r2 = C.crear_circular(
        "Circular solo cruzada", "cuerpo",
        destinatarios=[{"usuario_id": d["user_b"]["id"], "tipo": "PARA"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r2["ok"] is False


def test_listar_circulares_legacy_sin_destinatarios_visible_a_todos(dos_empresas):
    """Compatibilidad hacia atrás: una circular SIN ninguna fila en com_destinatarios (como las
    creadas antes de esta migración) sigue siendo difusión a toda la empresa."""
    d = dos_empresas
    r = C.crear_circular("Circular legacy", "cuerpo", usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        ids = {c["id"] for c in
              C.listar_circulares(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}
        assert cid in ids
    finally:
        C.eliminar_circular(cid)


# ── 3. reenviar_circular: añade destinatario sin duplicar, nunca cruza empresas ───────────────────

def test_reenviar_circular_anade_sin_duplicar(dos_empresas):
    d = dos_empresas
    r = C.crear_circular("Circular a reenviar", "cuerpo",
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    cid = r["id"]
    try:
        # otro_a todavía no la ve (hay destinatarios registrados y no es ninguno de ellos).
        assert cid not in {c["id"] for c in
                           C.listar_circulares(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}

        rf = C.reenviar_circular(cid, [{"usuario_id": d["otro_a"]["id"], "tipo": "PARA"}],
                                 usuario=d["para_a"], id_empresa=d["emp_a"])
        assert rf["ok"] is True
        assert rf["n"] == 1

        # Ahora sí, y sigue siendo LA MISMA circular (no se duplicó la fila/id).
        ids = [c["id"] for c in
              C.listar_circulares(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])]
        assert ids.count(cid) == 1
        assert len(C.listar_circulares(id_empresa=d["emp_a"])) == 1

        detalle = C.obtener_circular(cid)
        reenviada = [x for x in detalle["destinatarios"] if x["usuario_id"] == d["otro_a"]["id"]]
        assert reenviada and reenviada[0]["reenviado_por"]
    finally:
        C.eliminar_circular(cid)


def test_reenviar_circular_rechaza_destinatario_de_otra_empresa(dos_empresas):
    d = dos_empresas
    r = C.crear_circular("Circular A", "cuerpo",
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    cid = r["id"]
    try:
        rf = C.reenviar_circular(cid, [{"usuario_id": d["user_b"]["id"], "tipo": "PARA"}],
                                 usuario=d["para_a"], id_empresa=d["emp_a"])
        assert rf["ok"] is False

        # El usuario de la empresa B JAMÁS ve la circular de la empresa A.
        ids_b = {c["id"] for c in
                C.listar_circulares(id_empresa=d["emp_b"], usuario_id=d["user_b"]["id"])}
        assert cid not in ids_b
        # Tampoco se insertó ninguna fila de destinatario para ese usuario.
        detalle = C.obtener_circular(cid)
        assert all(x["usuario_id"] != d["user_b"]["id"] for x in detalle["destinatarios"])
    finally:
        C.eliminar_circular(cid)


def test_reenviar_circular_rechaza_contexto_de_empresa_distinta(dos_empresas):
    """Si se reenvía con un `id_empresa` que no es el de la propia circular, se rechaza (no
    depende de si el destinatario sería válido o no)."""
    d = dos_empresas
    r = C.crear_circular("Circular A2", "cuerpo",
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    cid = r["id"]
    try:
        rf = C.reenviar_circular(cid, [{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                                 id_empresa=d["emp_b"])
        assert rf["ok"] is False
    finally:
        C.eliminar_circular(cid)


def test_reenviar_circular_inexistente(dos_empresas):
    d = dos_empresas
    rf = C.reenviar_circular(999999999, [{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}])
    assert rf["ok"] is False


# ── 4. Encuestas — mismos casos núcleo + aislamiento cross-tenant ─────────────────────────────────

def test_encuestas_destinatarios_y_aislamiento_multiempresa(dos_empresas):
    d = dos_empresas

    # Rechaza sin "Para" (lista NO vacía, pero sin ningún PARA).
    r0 = E.crear_encuesta("Sin para", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         destinatarios=[{"usuario_id": d["cc_a"]["id"], "tipo": "CC"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r0["ok"] is False

    r = E.crear_encuesta(
        "Encuesta dirigida", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        # Visible al destinatario PARA y al creador; NO a otro usuario de la MISMA empresa.
        assert eid in {e["id"] for e in
                      E.listar_encuestas(id_empresa=d["emp_a"], usuario_id=d["para_a"]["id"])}
        assert eid in {e["id"] for e in
                      E.listar_encuestas(id_empresa=d["emp_a"], usuario_id=int(d["creador"]["id"]))}
        assert eid not in {e["id"] for e in
                           E.listar_encuestas(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}

        # Reenvío cross-tenant: rechazado, jamás llega al usuario de la empresa B.
        rf = E.reenviar_encuesta(eid, [{"usuario_id": d["user_b"]["id"], "tipo": "PARA"}],
                                 usuario=d["para_a"], id_empresa=d["emp_a"])
        assert rf["ok"] is False
        assert eid not in {e["id"] for e in
                           E.listar_encuestas(id_empresa=d["emp_b"], usuario_id=d["user_b"]["id"])}

        # Reenvío legítimo DENTRO de la misma empresa: añade sin duplicar la encuesta.
        rf2 = E.reenviar_encuesta(eid, [{"usuario_id": d["otro_a"]["id"], "tipo": "PARA"}],
                                  usuario=d["para_a"], id_empresa=d["emp_a"])
        assert rf2["ok"] is True
        ids = [e["id"] for e in
              E.listar_encuestas(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])]
        assert ids.count(eid) == 1
        assert len(E.listar_encuestas(id_empresa=d["emp_a"])) == 1
    finally:
        E.eliminar_encuesta(eid)


def test_crear_encuesta_filtra_destinatario_de_otra_empresa(dos_empresas):
    """Mismo caso que `test_crear_circular_filtra_destinatario_de_otra_empresa`, para encuestas:
    `crear_encuesta` también debe re-validar cada `usuario_id` contra la empresa real."""
    d = dos_empresas
    r = E.crear_encuesta(
        "Encuesta mixta", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"},
                       {"usuario_id": d["user_b"]["id"], "tipo": "CC"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        detalle = E.obtener_encuesta(eid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert d["para_a"]["id"] in ids_dest
        assert d["user_b"]["id"] not in ids_dest
        ids_b = {e["id"] for e in E.listar_encuestas(id_empresa=d["emp_b"], usuario_id=d["user_b"]["id"])}
        assert eid not in ids_b
    finally:
        E.eliminar_encuesta(eid)
    r2 = E.crear_encuesta(
        "Encuesta solo cruzada", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"usuario_id": d["user_b"]["id"], "tipo": "PARA"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r2["ok"] is False


def test_listar_encuestas_legacy_sin_destinatarios_visible_a_todos(dos_empresas):
    d = dos_empresas
    r = E.crear_encuesta("Encuesta legacy", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        ids = {e["id"] for e in
              E.listar_encuestas(id_empresa=d["emp_a"], usuario_id=d["otro_a"]["id"])}
        assert eid in ids
    finally:
        E.eliminar_encuesta(eid)


# ── 5. listar_usuarios_empresa: migración 0287 — requiere email, excluye a quien no tenga ────────

def test_listar_usuarios_empresa_excluye_sin_email(dos_empresas, fab):
    d = dos_empresas
    sin_email = fab.usuario(nombre="SIN_EMAIL_COM_A", id_empresa=d["emp_a"])  # sin email (default)
    res = listar_usuarios_empresa(d["emp_a"])
    nombres = {u["nombre"] for u in res}
    assert sin_email["nombre"] not in nombres
    assert d["para_a"]["nombre"] in nombres
    fila_para = next(u for u in res if u["nombre"] == d["para_a"]["nombre"])
    assert fila_para["email"] == "para.coma@test.com"


# ── 6. listar_centros_empresa: aislamiento multiempresa ───────────────────────────────────────────

def test_listar_centros_empresa_aislamiento(dos_empresas, fab):
    d = dos_empresas
    cid_a = CENTROS.crear_centro(id_empresa=d["emp_a"], nombre_centro="Centro Dest A",
                                 email="centroa@test.com")
    fab._borrar("centros_trabajo", "id_centro", cid_a)
    cid_b = CENTROS.crear_centro(id_empresa=d["emp_b"], nombre_centro="Centro Dest B",
                                 email="centrob@test.com")
    fab._borrar("centros_trabajo", "id_centro", cid_b)

    res_a = listar_centros_empresa(d["emp_a"])
    nombres_a = {c["nombre"] for c in res_a}
    assert "Centro Dest A" in nombres_a
    assert "Centro Dest B" not in nombres_a

    res_b = listar_centros_empresa(d["emp_b"])
    nombres_b = {c["nombre"] for c in res_b}
    assert "Centro Dest B" in nombres_b
    assert "Centro Dest A" not in nombres_b

    assert listar_centros_empresa(None) == []


def test_listar_centros_empresa_excluye_sin_email(dos_empresas):
    d = dos_empresas
    cid = CENTROS.crear_centro(id_empresa=d["emp_a"], nombre_centro="Centro Sin Email")
    try:
        res = listar_centros_empresa(d["emp_a"])
        assert "Centro Sin Email" not in {c["nombre"] for c in res}
    finally:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM centros_trabajo WHERE id_centro=%s", (cid,))
            conn.commit()


# ── 7. listar_contactos_externos: histórico tenant-safe, NUNCA el directorio completo ────────────

def test_listar_contactos_externos_aislamiento_y_filtro(dos_empresas):
    d = dos_empresas
    HIST.registrar_envio("cliente.a@externo.com", "Cliente A", id_empresa=d["emp_a"],
                        id_usuario="tester")
    HIST.registrar_envio("cliente.b@externo.com", "Cliente B", id_empresa=d["emp_b"],
                        id_usuario="tester")
    try:
        res_a = listar_contactos_externos(d["emp_a"], None)
        emails_a = {c["email"] for c in res_a}
        assert "cliente.a@externo.com" in emails_a
        assert "cliente.b@externo.com" not in emails_a

        res_b = listar_contactos_externos(d["emp_b"], None)
        emails_b = {c["email"] for c in res_b}
        assert "cliente.b@externo.com" in emails_b
        assert "cliente.a@externo.com" not in emails_b

        filtrado = listar_contactos_externos(d["emp_a"], None, "cliente.a")
        assert {c["email"] for c in filtrado} == {"cliente.a@externo.com"}

        assert listar_contactos_externos(None, None) == []
    finally:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM destinatarios_historico WHERE correo IN (%s,%s)",
                       ("cliente.a@externo.com", "cliente.b@externo.com"))
            conn.commit()


# ── 8. Fan-out de centro en crear_circular/reenviar_circular: SOLO los empleados de ESE centro ───

def test_crear_circular_centro_fanout_aislado(dos_empresas, fab):
    """Seed deliberado: un centro en la empresa A con 2 empleados, un empleado de la empresa A SIN
    relación con ese centro (`otro_a`, de la fixture), y un centro en la empresa B que recibe EL
    MISMO código (`codigo_centro` se autogenera de forma independiente por empresa, empezando por
    "CDT-001" en ambas) con su propio empleado — cero fuga en cualquier dirección."""
    d = dos_empresas
    emp_a, emp_b = d["emp_a"], d["emp_b"]

    centro_a = CENTROS.crear_centro(id_empresa=emp_a, nombre_centro="Tienda Centro A",
                                    email="centro_fo_a@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_a)
    codigo_a = CENTROS.obtener_centro(centro_a)["codigo_centro"]

    centro_b = CENTROS.crear_centro(id_empresa=emp_b, nombre_centro="Tienda Centro B",
                                    email="centro_fo_b@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_b)
    codigo_b = CENTROS.obtener_centro(centro_b)["codigo_centro"]

    emp1 = fab.usuario(nombre="EMP1_CENTRO_A", id_empresa=emp_a, centro_codigo=codigo_a,
                       email="emp1_fo@test.com")
    emp2 = fab.usuario(nombre="EMP2_CENTRO_A", id_empresa=emp_a, centro_codigo=codigo_a,
                       email="emp2_fo@test.com")
    # Mismo código de centro que `centro_a`, pero en la OTRA empresa.
    emp_otra = fab.usuario(nombre="EMP_CENTRO_B", id_empresa=emp_b, centro_codigo=codigo_b,
                           email="empb_fo@test.com")

    r = C.crear_circular("Circular a centro", "cuerpo",
                         destinatarios=[{"centro_codigo": codigo_a, "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=emp_a)
    assert r["ok"] is True
    cid = r["id"]
    try:
        detalle = C.obtener_circular(cid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert emp1["id"] in ids_dest
        assert emp2["id"] in ids_dest
        # Empleado de la MISMA empresa pero sin relación con el centro: NO debe estar.
        assert d["otro_a"]["id"] not in ids_dest
        # Empleado de la OTRA empresa con el MISMO código de centro: NUNCA debe colarse.
        assert emp_otra["id"] not in ids_dest
        # Tampoco ve la circular en su propia bandeja de la empresa B.
        ids_b = {c["id"] for c in
                C.listar_circulares(id_empresa=emp_b, usuario_id=emp_otra["id"])}
        assert cid not in ids_b
    finally:
        C.eliminar_circular(cid)


def test_crear_circular_centro_de_otra_empresa_no_se_expande(dos_empresas, fab):
    """Un `centro_codigo` que no pertenece a `id_empresa` se descarta en silencio — nunca se expande.
    Si es el ÚNICO destinatario, no queda ningún PARA válido y no se crea la circular."""
    d = dos_empresas
    centro_b = CENTROS.crear_centro(id_empresa=d["emp_b"], nombre_centro="Centro Solo B",
                                    email="solob@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_b)
    codigo_b = CENTROS.obtener_centro(centro_b)["codigo_centro"]
    fab.usuario(nombre="EMP_SOLO_B", id_empresa=d["emp_b"], centro_codigo=codigo_b,
               email="emp_solo_b@test.com")

    r = C.crear_circular("Circular centro ajeno", "cuerpo",
                         destinatarios=[{"centro_codigo": codigo_b, "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is False


def test_reenviar_circular_centro_fanout(dos_empresas, fab):
    d = dos_empresas
    emp_a = d["emp_a"]
    centro_a = CENTROS.crear_centro(id_empresa=emp_a, nombre_centro="Centro Reenvio",
                                    email="reenv@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_a)
    codigo_a = CENTROS.obtener_centro(centro_a)["codigo_centro"]
    emp1 = fab.usuario(nombre="EMP1_REENV", id_empresa=emp_a, centro_codigo=codigo_a,
                       email="e1r@test.com")
    emp2 = fab.usuario(nombre="EMP2_REENV", id_empresa=emp_a, centro_codigo=codigo_a,
                       email="e2r@test.com")

    r = C.crear_circular("Circular base reenvio", "cuerpo",
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=emp_a)
    cid = r["id"]
    try:
        rf = C.reenviar_circular(cid, [{"centro_codigo": codigo_a, "tipo": "PARA"}],
                                 usuario=d["para_a"], id_empresa=emp_a)
        assert rf["ok"] is True
        assert rf["n"] == 2
        detalle = C.obtener_circular(cid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert emp1["id"] in ids_dest
        assert emp2["id"] in ids_dest
    finally:
        C.eliminar_circular(cid)


# ── 9. Destinatario email_externo: nunca rompe el flujo, degrada honesto sin buzón ────────────────

def test_crear_circular_email_externo_sin_buzon_no_rompe(dos_empresas):
    d = dos_empresas
    r = C.crear_circular(
        "Circular con externo", "cuerpo",
        destinatarios=[{"email_externo": "externo@cliente.com", "nombre": "Cliente Externo",
                        "tipo": "PARA"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        assert r.get("externos_fallidos") == ["externo@cliente.com"]
        # No genera ninguna fila com_destinatarios (no es usuario_id-addressable).
        detalle = C.obtener_circular(cid)
        assert detalle["destinatarios"] == []
    finally:
        C.eliminar_circular(cid)


def test_crear_circular_mixta_interno_y_externo_sin_buzon(dos_empresas):
    """Un PARA interno válido + un PARA externo (sin buzón conectado): la circular SÍ se crea (el
    interno ya cuenta como PARA válido) y el fallo externo queda reflejado, nunca oculto."""
    d = dos_empresas
    r = C.crear_circular(
        "Circular mixta externo", "cuerpo",
        destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"},
                       {"email_externo": "mixto@cliente.com", "tipo": "CC"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        assert r.get("externos_fallidos") == ["mixto@cliente.com"]
    finally:
        C.eliminar_circular(cid)


# ── 10. Mismo núcleo para encuestas: fan-out de centro + externo sin buzón ────────────────────────

def test_crear_encuesta_centro_fanout_aislado(dos_empresas, fab):
    d = dos_empresas
    emp_a, emp_b = d["emp_a"], d["emp_b"]
    centro_a = CENTROS.crear_centro(id_empresa=emp_a, nombre_centro="Tienda Centro A Enc",
                                    email="centro_enc_a@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_a)
    codigo_a = CENTROS.obtener_centro(centro_a)["codigo_centro"]
    centro_b = CENTROS.crear_centro(id_empresa=emp_b, nombre_centro="Tienda Centro B Enc",
                                    email="centro_enc_b@test.com")
    fab._borrar("centros_trabajo", "id_centro", centro_b)
    codigo_b = CENTROS.obtener_centro(centro_b)["codigo_centro"]

    emp1 = fab.usuario(nombre="EMP1_CENTRO_A_ENC", id_empresa=emp_a, centro_codigo=codigo_a,
                       email="emp1_enc@test.com")
    emp_otra = fab.usuario(nombre="EMP_CENTRO_B_ENC", id_empresa=emp_b, centro_codigo=codigo_b,
                           email="empb_enc@test.com")

    r = E.crear_encuesta("Encuesta a centro", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         destinatarios=[{"centro_codigo": codigo_a, "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=emp_a)
    assert r["ok"] is True
    eid = r["id"]
    try:
        detalle = E.obtener_encuesta(eid)
        ids_dest = {x["usuario_id"] for x in detalle["destinatarios"]}
        assert emp1["id"] in ids_dest
        assert d["otro_a"]["id"] not in ids_dest
        assert emp_otra["id"] not in ids_dest
    finally:
        E.eliminar_encuesta(eid)


def test_crear_encuesta_email_externo_sin_buzon_no_rompe(dos_empresas):
    d = dos_empresas
    r = E.crear_encuesta(
        "Encuesta con externo", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"email_externo": "externo_enc@cliente.com", "tipo": "PARA"}],
        usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        assert r.get("externos_fallidos") == ["externo_enc@cliente.com"]
        detalle = E.obtener_encuesta(eid)
        assert detalle["destinatarios"] == []
    finally:
        E.eliminar_encuesta(eid)


# ─── responder_circular / responder_encuesta_autenticado: identidad YA AUTENTICADA, sin contraseña ──
# Paralelos de `confirmar_lectura`/`responder_encuesta` (que siguen intactos, para el escenario de
# terminal compartido): deben escribir en la MISMA tabla, respetar el MISMO aislamiento tenant que
# `reenviar_circular`/`reenviar_encuesta`, y coexistir sin romper el flujo con contraseña.

def test_responder_circular_sin_password_registra_confirmacion(dos_empresas):
    d = dos_empresas
    r = C.crear_circular("Circular a responder", "cuerpo",
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        u_para = {"id": d["para_a"]["id"], "nombre": d["para_a"]["nombre"]}
        rr = C.responder_circular(cid, usuario=u_para, comentario="Leído, gracias",
                                  id_empresa=d["emp_a"])
        assert rr["ok"] is True
        assert rr["usuario"] == d["para_a"]["nombre"]
        detalle = C.obtener_circular(cid)
        confs = detalle["confirmaciones"]
        assert len(confs) == 1
        assert confs[0]["usuario_nombre"] == d["para_a"]["nombre"]
        assert confs[0]["comentario"] == "Leído, gracias"
    finally:
        C.eliminar_circular(cid)


def test_responder_circular_aisla_tenant(dos_empresas):
    d = dos_empresas
    r = C.crear_circular("Circular tenant resp", "cuerpo", usuario=d["creador"], id_empresa=d["emp_a"])
    cid = r["id"]
    try:
        u_b = {"id": d["user_b"]["id"], "nombre": d["user_b"]["nombre"]}
        rr = C.responder_circular(cid, usuario=u_b, id_empresa=d["emp_b"])
        assert rr["ok"] is False
        detalle = C.obtener_circular(cid)
        assert detalle["confirmaciones"] == []
    finally:
        C.eliminar_circular(cid)


def test_responder_circular_coexiste_con_confirmar_lectura(dos_empresas, fab):
    d = dos_empresas
    empleado = fab.usuario(nombre="EMP_CONFIRMA_PWD", password="Clave_Resp_123456",
                           id_empresa=d["emp_a"], email="emp_confirma_pwd@test.com")
    r = C.crear_circular("Circular mixta", "cuerpo", usuario=d["creador"], id_empresa=d["emp_a"])
    cid = r["id"]
    try:
        r1 = C.confirmar_lectura(cid, usuario_nombre=empleado["nombre"], password="Clave_Resp_123456",
                                 comentario="via password", id_empresa=d["emp_a"])
        assert r1["ok"] is True
        u_para = {"id": d["para_a"]["id"], "nombre": d["para_a"]["nombre"]}
        r2 = C.responder_circular(cid, usuario=u_para, comentario="via token", id_empresa=d["emp_a"])
        assert r2["ok"] is True
        detalle = C.obtener_circular(cid)
        nombres = {c["usuario_nombre"] for c in detalle["confirmaciones"]}
        assert empleado["nombre"] in nombres
        assert d["para_a"]["nombre"] in nombres
        assert len(detalle["confirmaciones"]) == 2
    finally:
        C.eliminar_circular(cid)


def test_responder_encuesta_autenticado_sin_password(dos_empresas):
    d = dos_empresas
    r = E.crear_encuesta("Encuesta a responder", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         destinatarios=[{"usuario_id": d["para_a"]["id"], "tipo": "PARA"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        detalle = E.obtener_encuesta(eid)
        pid = detalle["preguntas"][0]["id"]
        u_para = {"id": d["para_a"]["id"], "nombre": d["para_a"]["nombre"]}
        rr = E.responder_encuesta_autenticado(
            eid, usuario=u_para, respuestas={pid: {"texto": "Mi respuesta"}},
            comentario="gracias", id_empresa=d["emp_a"])
        assert rr["ok"] is True
        assert rr["usuario"] == d["para_a"]["nombre"]
        detalle2 = E.obtener_encuesta(eid)
        assert len(detalle2["respuestas"]) == 1
        assert detalle2["respuestas"][0]["usuario_nombre"] == d["para_a"]["nombre"]
        items = detalle2["respuestas"][0]["items"]
        assert any(it["texto"] == "Mi respuesta" for it in items)
    finally:
        E.eliminar_encuesta(eid)


def test_responder_encuesta_autenticado_aisla_tenant(dos_empresas):
    d = dos_empresas
    r = E.crear_encuesta("Encuesta tenant resp", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    eid = r["id"]
    try:
        u_b = {"id": d["user_b"]["id"], "nombre": d["user_b"]["nombre"]}
        rr = E.responder_encuesta_autenticado(eid, usuario=u_b, respuestas={}, id_empresa=d["emp_b"])
        assert rr["ok"] is False
        detalle = E.obtener_encuesta(eid)
        assert detalle["respuestas"] == []
    finally:
        E.eliminar_encuesta(eid)


def test_responder_encuesta_coexiste_con_responder_encuesta_password(dos_empresas, fab):
    d = dos_empresas
    empleado = fab.usuario(nombre="EMP_ENC_PWD", password="Clave_Resp_654321",
                           id_empresa=d["emp_a"], email="emp_enc_pwd@test.com")
    r = E.crear_encuesta("Encuesta mixta", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
                         usuario=d["creador"], id_empresa=d["emp_a"])
    eid = r["id"]
    try:
        detalle = E.obtener_encuesta(eid)
        pid = detalle["preguntas"][0]["id"]
        r1 = E.responder_encuesta(eid, usuario_nombre=empleado["nombre"], password="Clave_Resp_654321",
                                  respuestas={pid: {"texto": "via password"}}, id_empresa=d["emp_a"])
        assert r1["ok"] is True
        u_para = {"id": d["para_a"]["id"], "nombre": d["para_a"]["nombre"]}
        r2 = E.responder_encuesta_autenticado(eid, usuario=u_para, respuestas={pid: {"texto": "via token"}},
                                              id_empresa=d["emp_a"])
        assert r2["ok"] is True
        detalle2 = E.obtener_encuesta(eid)
        assert len(detalle2["respuestas"]) == 2
    finally:
        E.eliminar_encuesta(eid)
