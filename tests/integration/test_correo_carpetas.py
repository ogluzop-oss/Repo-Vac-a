"""
Carpetas REALES del módulo de Correo (migración 0288): Borradores, Papelera, Programados,
Pospuestos, Importantes — item 5 de la tarea de rediseño del correo (reemplaza el "aviso honesto
de no disponible" por backend genuino).

Cubre, por circulares y por el correo Gmail sincronizado donde aplica:
  · Borradores: guardar/reabrir/editar/publicar (ciclo completo, destinatarios reales tras publicar).
  · Papelera: mover/restaurar (circular y fila Gmail), LOCAL siempre (nunca toca la API de Gmail).
  · Programados: NO aparece en Recibidos hasta que el job `disparar_programadas_vencidas` lo
    dispara (simulado con una `fecha_programada` en el pasado, sin esperar tiempo real).
  · Pospuestos: excluido de Recibidos mientras `pospuesto_hasta` está en el futuro, reaparece solo
    con la consulta normal una vez vencido (sin job alguno).
  · Importantes: toggle persistente y filtrado correcto.
"""

import datetime

import pytest

from src.db import correo as correo_db
from src.services.comunicacion_interna import circulares as C
from src.services.comunicacion_interna import encuestas as E

pytestmark = pytest.mark.db


@pytest.fixture
def entorno(fab):
    emp = fab.empresa("EMPRESA CARPETAS CORREO")
    creador = fab.usuario(nombre="CREADOR_CARPETAS", id_empresa=emp, email="creador.cp@test.com")
    destino = fab.usuario(nombre="DESTINO_CARPETAS", id_empresa=emp, email="destino.cp@test.com")
    cid = fab.buzon_correo(id_empresa=emp)
    u = {"id": creador["id"], "nombre": creador["nombre"]}
    return {"emp": emp, "creador": creador, "destino": destino, "u": u, "id_correo": cid}


# ── Borradores: ciclo guardar -> reabrir -> editar -> publicar ───────────────────────────────────

def test_borrador_circular_ciclo_completo(entorno):
    d = entorno
    r = C.guardar_borrador(titulo="Borrador inicial", cuerpo="cuerpo v1", usuario=d["u"],
                           id_empresa=d["emp"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        # No aparece en "mi bandeja" (Recibidos/Enviados) — solo PUBLICADA se lista con usuario_id.
        assert cid not in {c["id"] for c in C.listar_circulares(id_empresa=d["emp"],
                                                                usuario_id=d["creador"]["id"])}
        # Sí aparece en Borradores.
        borradores = C.listar_borradores(d["creador"]["id"], id_empresa=d["emp"])
        assert cid in {b["id"] for b in borradores}

        # Reabrir y editar (mismo id_circular -> UPDATE, no duplica fila).
        r2 = C.guardar_borrador(cid, titulo="Borrador editado", cuerpo="cuerpo v2", usuario=d["u"],
                                id_empresa=d["emp"])
        assert r2["ok"] is True and r2["id"] == cid
        detalle = C.obtener_circular(cid)
        assert detalle["titulo"] == "Borrador editado"
        assert len(C.listar_borradores(d["creador"]["id"], id_empresa=d["emp"])) == len(borradores)

        # Publicar: exige un "Para" real.
        r3 = C.publicar_borrador(cid, destinatarios=[], usuario=d["u"], id_empresa=d["emp"])
        assert r3["ok"] is False

        r4 = C.publicar_borrador(
            cid, destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
            usuario=d["u"], id_empresa=d["emp"])
        assert r4["ok"] is True
        # Ya NO está en Borradores; SÍ en la bandeja del destinatario.
        assert cid not in {b["id"] for b in C.listar_borradores(d["creador"]["id"], id_empresa=d["emp"])}
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
    finally:
        C.eliminar_circular(cid)


def test_borrador_encuesta_ciclo_completo(entorno):
    d = entorno
    r = E.guardar_borrador(titulo="Encuesta borrador", intro="intro",
                           preguntas=[{"texto": "P1", "tipo": "TEXTO"}], usuario=d["u"],
                           id_empresa=d["emp"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        assert eid in {b["id"] for b in E.listar_borradores(d["creador"]["id"], id_empresa=d["emp"])}
        r2 = E.publicar_borrador(
            eid, destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
            usuario=d["u"], id_empresa=d["emp"])
        assert r2["ok"] is True
        assert eid in {e["id"] for e in
                      E.listar_encuestas(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
    finally:
        E.eliminar_encuesta(eid)


def test_eliminar_borrador_ajeno_rechazado(entorno, fab):
    d = entorno
    otro = fab.usuario(nombre="OTRO_CARPETAS", id_empresa=d["emp"], email="otro.cp@test.com")
    r = C.guardar_borrador(titulo="Borrador privado", cuerpo="x", usuario=d["u"], id_empresa=d["emp"])
    cid = r["id"]
    try:
        rr = C.guardar_borrador(cid, titulo="hack", cuerpo="x",
                                usuario={"id": otro["id"], "nombre": otro["nombre"]},
                                id_empresa=d["emp"])
        assert rr["ok"] is False
    finally:
        C.eliminar_circular(cid)


# ── Papelera: circular/encuesta (solo creador) + fila Gmail (siempre local) ──────────────────────

def test_papelera_circular_mover_y_restaurar(entorno):
    d = entorno
    r = C.crear_circular("Circular a papelear", "cuerpo",
                         destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                         usuario=d["u"], id_empresa=d["emp"])
    cid = r["id"]
    try:
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        rm = C.mover_papelera(cid, usuario=d["u"], id_empresa=d["emp"])
        assert rm["ok"] is True
        # Ya no aparece como "publicada" en ninguna bandeja…
        assert cid not in {c["id"] for c in
                          C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        # …pero sí en Papelera del creador.
        assert cid in {c["id"] for c in C.listar_papelera(d["creador"]["id"], id_empresa=d["emp"])}

        rr = C.restaurar_de_papelera(cid, usuario=d["u"], id_empresa=d["emp"])
        assert rr["ok"] is True
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        assert cid not in {c["id"] for c in C.listar_papelera(d["creador"]["id"], id_empresa=d["emp"])}
    finally:
        C.eliminar_circular(cid)


def test_papelera_circular_solo_creador_puede_moverla(entorno, fab):
    d = entorno
    r = C.crear_circular("Circular ajena", "cuerpo",
                         destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                         usuario=d["u"], id_empresa=d["emp"])
    cid = r["id"]
    try:
        rm = C.mover_papelera(cid, usuario={"id": d["destino"]["id"], "nombre": "DESTINO"},
                              id_empresa=d["emp"])
        assert rm["ok"] is False
    finally:
        C.eliminar_circular(cid)


def test_papelera_gmail_local_mover_restaurar_y_excluye_de_recibidos(entorno):
    d = entorno
    rid = correo_db.guardar_recibido(d["id_correo"], "remitente@test.com", "Asunto papelera",
                                     "cuerpo", message_id="MID-PAPELERA-1", id_empresa=d["emp"])
    assert rid
    try:
        assert rid in {m["id"] for m in correo_db.listar_recibidos(id_empresa=d["emp"])}
        assert correo_db.mover_recibido_papelera(rid, id_empresa=d["emp"])
        assert rid not in {m["id"] for m in correo_db.listar_recibidos(id_empresa=d["emp"])}
        assert rid in {m["id"] for m in correo_db.listar_recibidos_papelera(id_empresa=d["emp"])}
        assert correo_db.restaurar_recibido(rid, id_empresa=d["emp"])
        assert rid in {m["id"] for m in correo_db.listar_recibidos(id_empresa=d["emp"])}
    finally:
        correo_db.eliminar_recibido_definitivo(rid, id_empresa=d["emp"])


# ── Programados: no aparece hasta que el job lo dispara (fecha pasada, sin esperar tiempo real) ──

def test_programados_no_aparece_hasta_que_el_job_lo_dispara(entorno):
    d = entorno
    pasado = datetime.datetime.now() - datetime.timedelta(minutes=5)
    r = C.programar(titulo="Circular programada", cuerpo="cuerpo",
                    fecha_programada=pasado,
                    destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                    usuario=d["u"], id_empresa=d["emp"])
    assert r["ok"] is True
    cid = r["id"]
    try:
        # Todavía NO visible en la bandeja del destinatario (sigue en PROGRAMADA).
        assert cid not in {c["id"] for c in
                          C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        assert cid in {c["id"] for c in C.listar_programadas(d["creador"]["id"], id_empresa=d["emp"])}

        # Simula el job del scheduler (fecha ya vencida) — llama a la función directamente, sin
        # esperar tiempo real ni pasar por `services.scheduler`.
        resumen = C.disparar_programadas_vencidas(d["emp"])
        assert resumen == "circulares_disparadas=1"

        # Ahora SÍ visible (PUBLICADA) y ya no en Programados.
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        assert cid not in {c["id"] for c in C.listar_programadas(d["creador"]["id"], id_empresa=d["emp"])}
    finally:
        C.eliminar_circular(cid)


def test_programar_rechaza_sin_destinatario_interno(entorno):
    d = entorno
    futuro = datetime.datetime.now() + datetime.timedelta(hours=1)
    r = C.programar(titulo="Sin para", cuerpo="x", fecha_programada=futuro, destinatarios=[],
                    usuario=d["u"], id_empresa=d["emp"])
    assert r["ok"] is False


def test_programar_encuesta_dispara_con_job(entorno):
    d = entorno
    pasado = datetime.datetime.now() - datetime.timedelta(minutes=1)
    r = E.programar(titulo="Encuesta programada", intro="intro",
                    preguntas=[{"texto": "P1", "tipo": "TEXTO"}], fecha_programada=pasado,
                    destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                    usuario=d["u"], id_empresa=d["emp"])
    assert r["ok"] is True
    eid = r["id"]
    try:
        assert eid not in {e["id"] for e in
                          E.listar_encuestas(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        E.disparar_programadas_vencidas(d["emp"])
        assert eid in {e["id"] for e in
                      E.listar_encuestas(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
    finally:
        E.eliminar_encuesta(eid)


# ── Pospuestos: excluido de Recibidos mientras pospuesto_hasta está en el futuro ──────────────────

def test_pospuesto_circular_excluye_y_reaparece(entorno):
    d = entorno
    r = C.crear_circular("Circular a posponer", "cuerpo",
                         destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                         usuario=d["u"], id_empresa=d["emp"])
    cid = r["id"]
    try:
        futuro = datetime.datetime.now() + datetime.timedelta(hours=2)
        assert C.posponer(cid, futuro, id_empresa=d["emp"])["ok"] is True
        assert cid not in {c["id"] for c in
                          C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        assert cid in {c["id"] for c in C.listar_pospuestos(d["destino"]["id"], id_empresa=d["emp"])}

        # Simula que ya venció (sin esperar tiempo real): fija `pospuesto_hasta` en el pasado.
        pasado = datetime.datetime.now() - datetime.timedelta(minutes=1)
        assert C.posponer(cid, pasado, id_empresa=d["emp"])["ok"] is True
        assert cid in {c["id"] for c in
                      C.listar_circulares(id_empresa=d["emp"], usuario_id=d["destino"]["id"])}
        assert cid not in {c["id"] for c in C.listar_pospuestos(d["destino"]["id"], id_empresa=d["emp"])}
    finally:
        C.eliminar_circular(cid)


def test_pospuesto_gmail_excluye_y_reaparece(entorno):
    d = entorno
    rid = correo_db.guardar_recibido(d["id_correo"], "remitente@test.com", "Asunto pospuesto",
                                     "cuerpo", message_id="MID-POSPUESTO-1", id_empresa=d["emp"])
    try:
        futuro = datetime.datetime.now() + datetime.timedelta(hours=2)
        assert correo_db.posponer_recibido(rid, futuro, id_empresa=d["emp"])
        assert rid not in {m["id"] for m in correo_db.listar_recibidos(id_empresa=d["emp"])}
        assert rid in {m["id"] for m in correo_db.listar_recibidos_pospuestos(id_empresa=d["emp"])}

        pasado = datetime.datetime.now() - datetime.timedelta(minutes=1)
        assert correo_db.posponer_recibido(rid, pasado, id_empresa=d["emp"])
        assert rid in {m["id"] for m in correo_db.listar_recibidos(id_empresa=d["emp"])}
    finally:
        correo_db.eliminar_recibido_definitivo(rid, id_empresa=d["emp"])


# ── Importantes: toggle persistente y filtrado correcto ──────────────────────────────────────────

def test_importante_circular_toggle(entorno):
    d = entorno
    r = C.crear_circular("Circular importante", "cuerpo",
                         destinatarios=[{"usuario_id": d["destino"]["id"], "tipo": "PARA"}],
                         usuario=d["u"], id_empresa=d["emp"])
    cid = r["id"]
    try:
        assert cid not in {c["id"] for c in C.listar_importantes(d["destino"]["id"], id_empresa=d["emp"])}
        assert C.marcar_importante(cid, True, id_empresa=d["emp"])["ok"] is True
        assert cid in {c["id"] for c in C.listar_importantes(d["destino"]["id"], id_empresa=d["emp"])}
        assert C.marcar_importante(cid, False, id_empresa=d["emp"])["ok"] is True
        assert cid not in {c["id"] for c in C.listar_importantes(d["destino"]["id"], id_empresa=d["emp"])}
    finally:
        C.eliminar_circular(cid)


def test_importante_gmail_toggle(entorno):
    d = entorno
    rid = correo_db.guardar_recibido(d["id_correo"], "remitente@test.com", "Asunto importante",
                                     "cuerpo", message_id="MID-IMPORTANTE-1", id_empresa=d["emp"])
    try:
        assert rid not in {m["id"] for m in correo_db.listar_recibidos_importantes(id_empresa=d["emp"])}
        assert correo_db.marcar_recibido_importante(rid, True, id_empresa=d["emp"])
        assert rid in {m["id"] for m in correo_db.listar_recibidos_importantes(id_empresa=d["emp"])}
        assert correo_db.marcar_recibido_importante(rid, False, id_empresa=d["emp"])
        assert rid not in {m["id"] for m in correo_db.listar_recibidos_importantes(id_empresa=d["emp"])}
    finally:
        correo_db.eliminar_recibido_definitivo(rid, id_empresa=d["emp"])
