"""
Gmail (lectura) y Google Calendar (lectura) reales en Correo / Planificar Citas.

Cubre: GOOGLE_SCOPES ampliado (envío + lectura), `sincronizar_gmail_api` (Gmail API →
correos_recibidos, idempotente), `calendario.sincronizar_google` (Calendar API →
calendario_eventos, upsert idempotente por ref_entidad/ref_id), `citas.pendientes_hoy()`
reescrito sobre la agenda única (BD) en vez del JSON legado huérfano, y el manejo honesto
del fallo de scope insuficiente (403 de Google) en ambas sincronizaciones.

Mocks en la frontera de `googleapiclient`/`_credenciales_google`/`integraciones.calendario`
(sin cuenta Google real disponible en CI) — mismo criterio que test_correo_oauth.py. Los tests
que tocan `correos_recibidos`/`calendario_eventos` usan la BD de pruebas real (marca `db`).
"""

import base64
import os
import uuid
from datetime import date

import pytest

from src.db import correo as correo_db
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services import calendario as CAL
from src.services.correo import servicio as S
from src.utils import citas as CITAS

pytestmark = pytest.mark.db

E = EMPRESA_DEFAULT_ID


# ── Helpers: Gmail API falsa (misma forma encadenada que googleapiclient.discovery) ──
def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode("utf-8")).decode("ascii")


class _Exec:
    def __init__(self, data=None, error=None):
        self._data, self._error = data, error

    def execute(self):
        if self._error:
            raise self._error
        return self._data


class _FakeGmailMessages:
    def __init__(self, ids, por_id, error_en_list=None):
        self._ids, self._por_id, self._error_en_list = ids, por_id, error_en_list

    def list(self, **_kw):
        if self._error_en_list:
            return _Exec(error=self._error_en_list)
        return _Exec({"messages": [{"id": i} for i in self._ids]})

    def get(self, *, id, **_kw):
        return _Exec(self._por_id[id])


class _FakeGmailService:
    def __init__(self, ids, por_id, error_en_list=None):
        self._messages = _FakeGmailMessages(ids, por_id, error_en_list)

    def users(self):
        return self

    def messages(self):
        return self._messages


def _mensaje_gmail(mid, de, asunto, cuerpo):
    return {
        "id": mid,
        "payload": {
            "headers": [{"name": "From", "value": de}, {"name": "Subject", "value": asunto}],
            "mimeType": "text/plain",
            "body": {"data": _b64(cuerpo)},
        },
    }


def _http_error_403_scope():
    """HttpError 403 'insufficient scope', con la MISMA forma (resp.status/reason + content
    JSON) que produce la librería real de Google ante un token con scope insuficiente."""
    from googleapiclient.errors import HttpError

    class _Resp:
        status = 403
        reason = "Forbidden"

    content = (b'{"error": {"message": "Request had insufficient authentication scopes.", '
              b'"errors": [{"reason": "insufficientPermissions"}]}}')
    return HttpError(_Resp(), content)


# ── 1. Scopes OAuth ampliados ─────────────────────────────────────────────────
def test_google_scopes_contiene_los_3_scopes_esperados():
    assert S.GOOGLE_SCOPES == [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    # Alias retrocompatible: cualquier import existente de GMAIL_SCOPES sigue funcionando.
    assert S.GMAIL_SCOPES is S.GOOGLE_SCOPES


def test_mensaje_si_scope_insuficiente_detecta_403_insuficiente():
    assert S._mensaje_si_scope_insuficiente(_http_error_403_scope()) == S.MSG_RECONECTAR_GOOGLE
    # Texto plano (como el 'detalle' que guarda conectores.google_calendar) también se detecta.
    assert S._mensaje_si_scope_insuficiente(
        "<HttpError 403 ... insufficient authentication scopes>") == S.MSG_RECONECTAR_GOOGLE
    # Ni un error genérico ni un éxito disparan el mensaje.
    assert S._mensaje_si_scope_insuficiente(RuntimeError("timeout de red")) is None
    assert S._mensaje_si_scope_insuficiente("todo ok") is None


# ── 2. sincronizar_gmail_api → correos_recibidos (idempotente) ───────────────
@pytest.fixture
def buzon_google(db):
    direccion = f"gmail-test-{uuid.uuid4().hex[:8]}@example.com"
    cid = correo_db.crear_correo(direccion, proveedor="google")
    assert cid
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM correos_recibidos WHERE id_correo=%s", (cid,))
        conn.commit()
    correo_db.eliminar_correo(cid)


def test_sincronizar_gmail_api_guarda_mensajes_nuevos_e_idempotente(monkeypatch, buzon_google):
    monkeypatch.setattr(S, "_credenciales_google", lambda _id: object())
    por_id = {
        "m1": _mensaje_gmail("m1", "ana@proveedor.com", "Pedido #1", "Cuerpo del pedido 1"),
        "m2": _mensaje_gmail("m2", "luis@proveedor.com", "Pedido #2", "Cuerpo del pedido 2"),
    }
    fake_service = _FakeGmailService(["m1", "m2"], por_id)
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: fake_service)

    n1, msg1 = S.sincronizar_gmail_api(buzon_google, limite=20)
    assert n1 == 2
    assert "2" in msg1

    recibidos = correo_db.listar_recibidos(id_correo=buzon_google)
    assert len(recibidos) == 2
    asuntos = {r["asunto"] for r in recibidos}
    assert asuntos == {"Pedido #1", "Pedido #2"}
    cuerpos = {r["asunto"]: r["cuerpo"] for r in recibidos}
    assert cuerpos["Pedido #1"] == "Cuerpo del pedido 1"

    # Re-sincronizar los MISMOS mensajes (mismo message_id) no duplica FILAS — guardar_recibido
    # ya es idempotente por message_id (INSERT IGNORE + UNIQUE KEY uq_corr_rx) — y, gracias a
    # `existe_recibido` (comprobado ANTES de guardar), tampoco los vuelve a contar como "nuevos":
    # guardar_recibido devuelve el id de la fila tanto si la crea como si ya existía, así que sin
    # esa comprobación previa el contador los recontaría en cada resincronización.
    n2, msg2 = S.sincronizar_gmail_api(buzon_google, limite=20)
    assert n2 == 0
    assert "0" in msg2
    assert len(correo_db.listar_recibidos(id_correo=buzon_google)) == 2


def test_existe_recibido_distingue_nuevo_de_ya_sincronizado(buzon_google):
    mid = f"msg-{uuid.uuid4().hex[:8]}@example.com"
    assert correo_db.existe_recibido(buzon_google, mid) is False
    rid1 = correo_db.guardar_recibido(buzon_google, "a@b.com", "Asunto", "cuerpo", message_id=mid)
    assert rid1
    assert correo_db.existe_recibido(buzon_google, mid) is True
    # guardar_recibido sigue devolviendo el MISMO id en un reintento (idempotente) — existe_recibido
    # es justamente lo que permite a quien sincroniza distinguir ese caso de una inserción real.
    rid2 = correo_db.guardar_recibido(buzon_google, "a@b.com", "Asunto", "cuerpo", message_id=mid)
    assert rid2 == rid1
    # Sin message_id no hay forma de deduplicar: se trata siempre como "no existe".
    assert correo_db.existe_recibido(buzon_google, None) is False


def test_sincronizar_gmail_api_scope_insuficiente_mensaje_honesto(monkeypatch, buzon_google):
    monkeypatch.setattr(S, "_credenciales_google", lambda _id: object())
    fake_service = _FakeGmailService([], {}, error_en_list=_http_error_403_scope())
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: fake_service)

    n, msg = S.sincronizar_gmail_api(buzon_google)
    assert n == 0
    assert msg == S.MSG_RECONECTAR_GOOGLE
    assert "reconect" in msg.lower()
    # Nunca llega nada a correos_recibidos cuando falla.
    assert correo_db.listar_recibidos(id_correo=buzon_google) == []


def test_sincronizar_gmail_api_sin_conexion_oauth(monkeypatch, buzon_google):
    monkeypatch.setattr(S, "_credenciales_google", lambda _id: None)
    n, msg = S.sincronizar_gmail_api(buzon_google)
    assert n == 0
    assert "no está conectada" in msg.lower()


# ── 3. calendario.sincronizar_google → calendario_eventos (upsert idempotente) ──
@pytest.fixture
def limpiar_eventos_google(db):
    ref_id = f"gevt-{uuid.uuid4().hex[:10]}"
    yield ref_id
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM calendario_eventos WHERE id_empresa=%s AND ref_entidad=%s "
                    "AND ref_id=%s", (E, "google_calendar", ref_id))
        conn.commit()


def _resp_calendar_ok(gid, titulo, inicio_iso, fin_iso):
    return {"ok": True, "estado": "ok", "eventos": [{
        "id": gid, "summary": titulo,
        "start": {"dateTime": inicio_iso}, "end": {"dateTime": fin_iso},
        "description": "importado de prueba",
    }]}


def test_sincronizar_google_calendar_resync_no_duplica_y_actualiza_titulo(
        monkeypatch, db, limpiar_eventos_google):
    from src.services import integraciones as I
    gid = limpiar_eventos_google

    monkeypatch.setattr(I, "calendario", lambda *a, **kw: _resp_calendar_ok(
        gid, "Reunión de equipo", "2026-10-03T10:00:00+02:00", "2026-10-03T11:00:00+02:00"))
    n1, msg1 = CAL.sincronizar_google("buzon-fake")
    assert n1 == 1
    assert "1" in msg1

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, titulo FROM calendario_eventos WHERE id_empresa=%s AND "
                    "ref_entidad=%s AND ref_id=%s", (E, "google_calendar", gid))
        fila1 = cur.fetchone()
    assert fila1 is not None
    id_fila, titulo1 = fila1
    assert titulo1 == "Reunión de equipo"

    # Re-sincronizar el MISMO evento (mismo id de Google) dos veces no duplica la fila.
    n2, _ = CAL.sincronizar_google("buzon-fake")
    assert n2 == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM calendario_eventos WHERE id_empresa=%s AND "
                    "ref_entidad=%s AND ref_id=%s", (E, "google_calendar", gid))
        total = cur.fetchone()[0]
    assert total == 1

    # El título cambió en Google: al re-sincronizar, actualiza la MISMA fila (no crea otra).
    monkeypatch.setattr(I, "calendario", lambda *a, **kw: _resp_calendar_ok(
        gid, "Reunión de equipo (reprogramada)", "2026-10-03T12:00:00+02:00",
        "2026-10-03T13:00:00+02:00"))
    CAL.sincronizar_google("buzon-fake")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, titulo FROM calendario_eventos WHERE id_empresa=%s AND "
                    "ref_entidad=%s AND ref_id=%s", (E, "google_calendar", gid))
        id_fila2, titulo2 = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM calendario_eventos WHERE id_empresa=%s AND "
                    "ref_entidad=%s AND ref_id=%s", (E, "google_calendar", gid))
        total2 = cur.fetchone()[0]
    assert id_fila2 == id_fila        # misma fila, no una nueva
    assert titulo2 == "Reunión de equipo (reprogramada)"
    assert total2 == 1


def test_sincronizar_google_calendar_evento_dia_completo(monkeypatch, db, limpiar_eventos_google):
    """Eventos de día completo ('date', sin hora) también se sincronizan correctamente."""
    from src.services import integraciones as I
    gid = limpiar_eventos_google
    monkeypatch.setattr(I, "calendario", lambda *a, **kw: {
        "ok": True, "estado": "ok", "eventos": [{
            "id": gid, "summary": "Cierre de inventario",
            "start": {"date": "2026-11-01"}, "end": {"date": "2026-11-02"},
        }]})
    n, _ = CAL.sincronizar_google("buzon-fake")
    assert n == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT titulo, inicio, fin FROM calendario_eventos WHERE id_empresa=%s AND "
                    "ref_entidad=%s AND ref_id=%s", (E, "google_calendar", gid))
        titulo, inicio, fin = cur.fetchone()
    assert titulo == "Cierre de inventario"
    assert str(inicio).startswith("2026-11-01")
    assert str(fin).startswith("2026-11-02")


def test_sincronizar_google_calendar_scope_insuficiente_mensaje_honesto(monkeypatch):
    from src.services import integraciones as I
    monkeypatch.setattr(I, "calendario", lambda *a, **kw: {
        "ok": False, "estado": "error", "conector": "google_calendar",
        "detalle": str(_http_error_403_scope())})
    n, msg = CAL.sincronizar_google("buzon-fake")
    assert n == 0
    assert msg == S.MSG_RECONECTAR_GOOGLE


def test_sincronizar_google_calendar_no_configurado(monkeypatch):
    from src.services import integraciones as I
    monkeypatch.setattr(I, "calendario", lambda *a, **kw: {
        "ok": False, "estado": "no_configurado", "conector": "google_calendar"})
    n, msg = CAL.sincronizar_google("buzon-fake")
    assert n == 0
    assert "no está conectada" in msg.lower()


# ── 4. citas.pendientes_hoy() sobre la agenda única (BD), no el JSON legado ──
@pytest.fixture
def _citas_sin_json_legado(monkeypatch, tmp_path):
    """Aísla citas.py de cualquier fichero real en documentos/: usa un directorio vacío
    (SIN eventos_citas.json ni citas_avisos_vistos.json), simulando una instalación recién
    migrada a BD. Si el bug antiguo (leer el JSON huérfano) siguiera presente, estas pruebas
    fallarían porque ese fichero simplemente no existe aquí."""
    monkeypatch.setattr(CITAS, "_DOCS", str(tmp_path))
    monkeypatch.setattr(CITAS, "_VISTOS_FILE", str(tmp_path / "citas_avisos_vistos.json"))
    yield tmp_path


@pytest.fixture
def evento_hoy(db, _citas_sin_json_legado):
    hoy = date.today().strftime("%Y-%m-%d")
    eid = CAL.crear_evento("Cita de prueba (sync test)", f"{hoy} 09:30:00",
                           fin=f"{hoy} 10:00:00", tipo="cita", id_empresa=E)
    assert eid
    yield eid
    CAL.eliminar_evento(eid, id_empresa=E)


def test_pendientes_hoy_ve_evento_real_de_bd(evento_hoy):
    hoy, pend = CITAS.pendientes_hoy()
    assert hoy == date.today().strftime("%Y-%m-%d")
    coincide = [e for e in pend if e["id"] == evento_hoy]
    assert len(coincide) == 1
    ev = coincide[0]
    assert ev["asunto"] == "Cita de prueba (sync test)"
    assert ev["hora_inicio"] == "9h 30min"
    assert ev["hora_fin"] == "10h 00min"


def test_pendientes_hoy_desaparece_tras_marcar_vistos(evento_hoy):
    hoy, pend = CITAS.pendientes_hoy()
    ev = next(e for e in pend if e["id"] == evento_hoy)
    CITAS.marcar_vistos(hoy, [ev])
    _hoy2, pend2 = CITAS.pendientes_hoy()
    assert all(e["id"] != evento_hoy for e in pend2)


def test_pendientes_hoy_regresion_sin_eventos_citas_json(evento_hoy, _citas_sin_json_legado):
    """Regresión del bug corregido: con NINGÚN eventos_citas.json presente (instalación
    post-migración), pendientes_hoy() debe seguir viendo el evento de HOY porque ahora lee de
    la agenda única (BD) y ya no del JSON legado. Antes de la corrección esto devolvía []."""
    ruta_json_legado = os.path.join(str(_citas_sin_json_legado), "eventos_citas.json")
    assert not os.path.exists(ruta_json_legado)
    _hoy, pend = CITAS.pendientes_hoy()
    assert any(e["id"] == evento_hoy for e in pend)
