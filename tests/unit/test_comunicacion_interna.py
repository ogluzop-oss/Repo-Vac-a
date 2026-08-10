"""
Tests · Comunicación interna (circulares y encuestas entre centros).

Verifica creación, bandeja, lectura, confirmación de circular (perfil+contraseña), respuesta de encuesta
(opciones/texto/«Otro»), aislamiento por empresa y clasificación de adjuntos (imagen vs texto).
"""

import hashlib

import pytest

from src.services.comunicacion_interna import adjuntos as ADJ
from src.services.comunicacion_interna import circulares as C
from src.services.comunicacion_interna import encuestas as E

pytestmark = pytest.mark.db

EMP = "T-CI"
OTRA = "T-CI-OTRA"
U = {"id": 1, "nombre": "ADMIN", "perfil": "ADMINISTRADOR"}


def _crear_usuario(db, nombre, password, id_empresa):
    from src.db.usuario import _columnas_usuarios
    h = hashlib.sha256(password.encode()).hexdigest()
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cols = _columnas_usuarios(cur)
        cur.execute("DELETE FROM usuarios WHERE nombre=%s", (nombre,))
        campos, vals = ["nombre", "password", "perfil"], [nombre, h, "GERENTE"]
        if "id_empresa" in cols:
            campos.append("id_empresa"); vals.append(id_empresa)
        if "tienda_id" in cols:
            campos.append("tienda_id"); vals.append("T01")
        if "activo" in cols:
            campos.append("activo"); vals.append(1)
        cur.execute(f"INSERT INTO usuarios ({','.join(campos)}) VALUES ({','.join(['%s']*len(campos))})",
                    tuple(vals))
        c.commit()


@pytest.fixture()
def entorno(db):
    _crear_usuario(db, "CENTRO-CI", "clave123", EMP)
    _crear_usuario(db, "CENTRO-OTRA", "clave123", OTRA)
    yield db
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("DELETE FROM usuarios WHERE nombre IN ('CENTRO-CI','CENTRO-OTRA')")
        cur.execute("DELETE FROM com_circulares WHERE id_empresa IN (%s,%s)", (EMP, OTRA))
        cur.execute("DELETE FROM com_encuestas WHERE id_empresa IN (%s,%s)", (EMP, OTRA))
        c.commit()


def test_circular_crear_confirmar(entorno):
    r = C.crear_circular("Horario", "De 9 a 15h.", usuario=U, id_empresa=EMP)
    assert r["ok"]
    cid = r["id"]
    assert any(x["titulo"] == "Horario" for x in C.listar_circulares(id_empresa=EMP))
    full = C.obtener_circular(cid)
    assert full["creador_nombre"] == "ADMIN" and full["creado"]           # subtítulo automático
    # Confirmación con contraseña incorrecta → falla.
    assert C.confirmar_lectura(cid, usuario_nombre="CENTRO-CI", password="mala")["ok"] is False
    # Confirmación correcta con comentario.
    ok = C.confirmar_lectura(cid, usuario_nombre="CENTRO-CI", password="clave123",
                             comentario="Recibido", id_empresa=EMP)
    assert ok["ok"] and ok["usuario"] == "CENTRO-CI"
    full = C.obtener_circular(cid)
    assert len(full["confirmaciones"]) == 1
    assert full["confirmaciones"][0]["comentario"] == "Recibido"


def test_circular_aislamiento_empresa(entorno):
    cid = C.crear_circular("Solo EMP", "x", usuario=U, id_empresa=EMP)["id"]
    # Un perfil de OTRA empresa no puede confirmar una circular de EMP.
    r = C.confirmar_lectura(cid, usuario_nombre="CENTRO-OTRA", password="clave123", id_empresa=EMP)
    assert r["ok"] is False
    # La bandeja de OTRA empresa no ve la circular de EMP.
    assert all(x["titulo"] != "Solo EMP" for x in C.listar_circulares(id_empresa=OTRA))


def test_encuesta_crear_responder(entorno):
    preg = [{"texto": "¿Valoras el horario?", "tipo": "OPCIONES", "opciones": ["Bien", "Mal"]},
            {"texto": "Sugerencias", "tipo": "TEXTO", "opciones": []}]
    r = E.crear_encuesta("Encuesta", "Intro explicativa.", preg, usuario=U, id_empresa=EMP)
    assert r["ok"]
    eid = r["id"]
    full = E.obtener_encuesta(eid)
    assert full["intro"] == "Intro explicativa."
    assert [p["tipo"] for p in full["preguntas"]] == ["OPCIONES", "TEXTO"]
    assert len(full["preguntas"][0]["opciones"]) == 2
    p1, p2 = full["preguntas"][0], full["preguntas"][1]
    op_bien = p1["opciones"][0]["id"]
    resp = {p1["id"]: {"opciones": [op_bien], "otro": "Sin horario partido"},
            p2["id"]: {"texto": "Todo correcto"}}
    rr = E.responder_encuesta(eid, usuario_nombre="CENTRO-CI", password="clave123", respuestas=resp,
                              comentario="ok", id_empresa=EMP)
    assert rr["ok"]
    full = E.obtener_encuesta(eid)
    assert len(full["respuestas"]) == 1
    items = full["respuestas"][0]["items"]
    # Opción marcada + «Otro» (texto) + respuesta de texto de la P2 = 3 items.
    assert len(items) == 3
    otros = [i["texto"] for i in items if i.get("texto")]
    assert "Sin horario partido" in otros and "Todo correcto" in otros


def test_encuesta_password_incorrecta(entorno):
    eid = E.crear_encuesta("E2", "", [{"texto": "P", "tipo": "TEXTO"}], usuario=U, id_empresa=EMP)["id"]
    r = E.responder_encuesta(eid, usuario_nombre="CENTRO-CI", password="mala", respuestas={})
    assert r["ok"] is False


def test_adjuntos_clase():
    assert ADJ.clase_por_extension("foto.PNG") == "imagen"
    assert ADJ.clase_por_extension("foto.jpeg") == "imagen"
    assert ADJ.clase_por_extension("acta.pdf") == "texto"
    assert ADJ.clase_por_extension("nota.txt") == "texto"
