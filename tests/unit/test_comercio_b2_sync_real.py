"""
Tests PCD · Etapa B · Fase B2: Conector REST real + Sync real.

Verifica: adaptador REST con transporte real (inyectable, degradable); sincronización incremental
(watermark) vs completa; deduplicación; detección de conflictos; webhooks firmados (HMAC) con
verificación por conexión; recuperación dead-letter; reconciliación; cadena Dominio→Adaptador→externo.
"""

import hashlib
import hmac
import inspect

import pytest

EMP = "T-SYNC2-A"


class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class _FakeHTTP:
    """Transporte HTTP simulado (sin red): registra llamadas y devuelve respuestas predefinidas."""
    def __init__(self, get_data=None, post_status=200):
        self.get_data = get_data if get_data is not None else {"items": []}
        self.post_status = post_status
        self.llamadas = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.llamadas.append(("GET", url, params, headers))
        return _FakeResp(self.get_data)

    def post(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append(("POST", url, json, headers))
        return _FakeResp({"recibido": True}, self.post_status)


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_sync_inbox", "cd_sync_outbox", "cd_sync_estado", "cd_conexiones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.services.comercio_digital import canales
    for c in list(canales.adaptadores()):
        canales.desregistrar(c)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_sync_inbox", "cd_sync_outbox", "cd_sync_estado", "cd_conexiones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_rest_adapter_transporte_real_y_degradable(limpio):
    from src.services.comercio_digital import canales, conexiones
    http = _FakeHTTP(get_data={"items": [{"id": "R1"}]})
    canales.registrar_adaptador(canales.RestChannelAdapter("shop", transporte=http))
    # Sin conexión → degradable (sin endpoint, no llama).
    ctx_vacio = conexiones.contexto("shop", id_empresa=EMP)
    assert canales.obtener("shop").recibir(contexto=ctx_vacio) == []
    # Con conexión (endpoint) → transporte real (GET a la URL).
    conexiones.registrar("shop", id_empresa=EMP, endpoint_base="https://api.shop.tld",
                         tipo_auth="apikey", credenciales={"api_key": "K1"})
    ctx = conexiones.contexto("shop", id_empresa=EMP)
    items = canales.obtener("shop").recibir(contexto=ctx)
    assert items == [{"id": "R1"}]
    assert http.llamadas and http.llamadas[-1][0] == "GET"
    assert "Bearer K1" in http.llamadas[-1][3]["Authorization"]     # credenciales aplicadas


def test_sincronizacion_incremental_watermark(limpio):
    from src.services.comercio_digital import canales, conexiones, sync
    http = _FakeHTTP(get_data={"items": [{"id": "A", "cursor": "100"},
                                         {"id": "B", "cursor": "200"}]})
    canales.registrar_adaptador(canales.RestChannelAdapter("mk", transporte=http))
    conexiones.registrar("mk", id_empresa=EMP, endpoint_base="https://mk.tld", tipo_auth="none")
    r1 = sync.sincronizar("mk", modo="incremental", id_empresa=EMP)
    assert r1["recibidos"] == 2 and r1["cursor"] == "200"
    assert sync.estado.cursor("mk", EMP) == "200"                  # watermark avanzado
    # Segunda pasada con los mismos ids → todo duplicado (dedup por Inbox).
    r2 = sync.sincronizar("mk", modo="incremental", id_empresa=EMP)
    assert r2["recibidos"] == 0 and r2["duplicados"] == 2
    # El GET incremental envía el cursor guardado.
    assert http.llamadas[-1][2].get("since") == "200"


def test_sincronizacion_detecta_conflictos(limpio):
    from src.services.comercio_digital import canales, conexiones, sync
    # Mismo external_id 'X' dos veces con contenido distinto → 1 conflicto.
    http = _FakeHTTP(get_data={"items": [{"id": "X", "precio": 10}, {"id": "X", "precio": 20}]})
    canales.registrar_adaptador(canales.RestChannelAdapter("cf", transporte=http))
    conexiones.registrar("cf", id_empresa=EMP, endpoint_base="https://cf.tld", tipo_auth="none")
    r = sync.sincronizar("cf", modo="completa", id_empresa=EMP)
    assert r["recibidos"] == 1 and r["conflictos"] == 1


def test_webhook_firmado_hmac(limpio):
    from src.services.comercio_digital import canales, conexiones, sync
    canales.registrar_adaptador(canales.ReferenceAdapter())
    canales.registrar_adaptador(canales.RestChannelAdapter("wh", transporte=_FakeHTTP()))
    conexiones.registrar("wh", id_empresa=EMP, tipo_auth="hmac",
                         credenciales={"webhook_secret": "S3CR3T"})
    cuerpo = '{"externo":{"id":"E1"}}'
    firma_ok = hmac.new(b"S3CR3T", cuerpo.encode(), hashlib.sha256).hexdigest()
    # Firma válida → procesa.
    r_ok = sync.procesar_webhook("wh", {"externo": {"id": "E1"}}, id_empresa=EMP, external_id="E1",
                                 firma=firma_ok, cuerpo_raw=cuerpo)
    assert r_ok["ok"] is True and r_ok["verificado"] is True
    # Firma inválida → rechazo.
    r_bad = sync.procesar_webhook("wh", {"externo": {"id": "E2"}}, id_empresa=EMP, external_id="E2",
                                  firma="deadbeef", cuerpo_raw='{"externo":{"id":"E2"}}')
    assert r_bad["ok"] is False and r_bad["motivo"] == "firma inválida"


def test_recuperacion_dead_letter(limpio):
    from src.services.comercio_digital import sync
    from src.services.comercio_digital.sync import outbox
    oid = sync.encolar("x", "t", {"a": 1}, id_empresa=EMP, idempotencia_key="k1")
    # Fuerza el descarte (agota reintentos).
    for _ in range(6):
        outbox.marcar_error(oid, "fallo")
    assert len(outbox.descartados(id_empresa=EMP)) == 1
    n = sync.reprocesar_descartados(id_empresa=EMP)
    assert n == 1 and outbox.descartados(id_empresa=EMP) == []       # vuelto a PENDIENTE


def test_reconciliacion(limpio):
    from src.services.comercio_digital import canales, conexiones, sync
    http = _FakeHTTP(get_data={"items": [{"id": "P1"}, {"id": "P2"}]})
    canales.registrar_adaptador(canales.RestChannelAdapter("rc", transporte=http))
    conexiones.registrar("rc", id_empresa=EMP, endpoint_base="https://rc.tld", tipo_auth="none")
    sync.sincronizar("rc", modo="completa", id_empresa=EMP)          # recibe P1, P2
    rec = sync.reconciliar("rc", ["P1", "P2", "P3"], id_empresa=EMP)
    assert rec["presentes"] == 2 and rec["faltantes"] == ["P3"]


def test_cadena_dominio_adaptador_externo():
    """El dominio nunca llama a la API externa directamente: lo hace el adaptador REST."""
    from src.services.comercio_digital import sync
    from src.services.comercio_digital.canales import rest_adapter
    dom = inspect.getsource(sync)
    assert "requests" not in dom                    # el dominio no usa el cliente HTTP
    assert "import requests" in inspect.getsource(rest_adapter)   # el adaptador sí
    assert sync.descriptor()["capacidades"].count("incremental") == 1
